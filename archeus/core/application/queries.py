"""Queries: read-only views over one snapshot (`Database.read()`)."""

import json

from ...infra.db import rows
from ...infra.db.writer import NotFound
from ...infra.eventlog import outbox
from ..domain import entities, states


def view(row):
    """An entity row as the API shows it: the entity plus its row metadata."""
    return dict(row.entity.to_dict(), version=row.version, created_at=row.created_at,
                updated_at=row.updated_at)


def get_mission(conn, mission_id):
    """One mission, with the context package its `context_ready` move
    recorded (None before it has one)."""
    row = rows.get(conn, entities.Mission, mission_id)
    if row is None:
        raise NotFound(mission_id)
    pid = row.entity.context_package_id
    return dict(view(row), context_package=None if pid is None else get_context_package(conn, pid))


def get_context_package(conn, package_id):
    row = rows.get(conn, entities.ContextPackage, package_id)
    if row is None:
        raise NotFound(package_id)
    return view(row)


def list_missions(conn, state=None, project_id=None):
    """Every mission, oldest first; only those in *state*, and of *project_id*,
    when given (an unknown project is NotFound, not an empty list)."""
    if state is not None and state not in states.states('mission'):
        raise ValueError('%r is not a mission state' % (state,))
    eq = {} if state is None else {'state': state}
    if project_id is not None:
        if rows.get(conn, entities.Project, project_id) is None:
            raise NotFound(project_id)
        eq['project_id'] = project_id
    return [view(r) for r in rows.where(conn, entities.Mission, **eq)]


def system_principal(conn):
    """The oldest `system` principal (the engine's actor), or None."""
    return next((r.entity.id for r in rows.where(conn, entities.Principal)
                 if r.entity.kind == 'system'), None)


def credential(conn, token_hash):
    """The device a token hash belongs to: `{principal_id, device_id, scopes,
    expires_at, revoked_at, device_state}`, or None. Judging it (revoked,
    expired, inactive) is the caller's."""
    t = conn.execute("SELECT * FROM tokens WHERE token_hash = ? AND kind = 'device'",
                     (token_hash,)).fetchone()
    if t is None:
        return None
    dev = rows.where(conn, entities.Device, principal_id=t['principal_id'])
    return {'token_hash': t['token_hash'], 'principal_id': t['principal_id'],
            'device_id': dev[0].entity.id if dev else None,
            'device_state': dev[0].entity.state if dev else None,
            'scopes': tuple(json.loads(t['scopes'])), 'expires_at': t['expires_at'],
            'revoked_at': t['revoked_at']}


def events(conn, after_seq=0, *, limit=None):
    """Envelopes after *after_seq*; every one when *limit* is None (paged)."""
    out, cursor = [], after_seq
    while True:
        page = outbox.events_after(conn, cursor, limit=outbox.MAX_LIMIT if limit is None else limit)
        out += [e.to_envelope() for e in page]
        if limit is not None or len(page) < outbox.MAX_LIMIT:
            return out
        cursor = page[-1].seq


# ── knowledge and own calls (P6) ────────────────────────────────────────────

def list_knowledge(conn, project_id=None, state=None, type=None):
    """Knowledge items, oldest first; filtered by project, state and type."""
    if state is not None and state not in states.states('knowledge_item'):
        raise ValueError('%r is not a knowledge state' % (state,))
    if type is not None and type not in entities.KNOWLEDGE_TYPES:
        raise ValueError('%r is not a knowledge type' % (type,))
    eq = {k: v for k, v in (('project_id', project_id), ('state', state), ('type', type))
          if v is not None}
    return [view(r) for r in rows.where(conn, entities.KnowledgeItem, **eq)]


def get_knowledge(conn, knowledge_item_id):
    """One item with its supersession chain (oldest first) and its relations."""
    row = rows.get(conn, entities.KnowledgeItem, knowledge_item_id)
    if row is None:
        raise NotFound(knowledge_item_id)
    chain, cur = [], row.entity
    while cur.supersedes_id is not None:                 # back to the first
        prev = rows.get(conn, entities.KnowledgeItem, cur.supersedes_id)
        if prev is None:
            break
        chain.insert(0, prev.entity.id)
        cur = prev.entity
    cur = row.entity
    after = []
    while cur.superseded_by_id is not None:
        nxt = rows.get(conn, entities.KnowledgeItem, cur.superseded_by_id)
        if nxt is None:
            break
        after.append(nxt.entity.id)
        cur = nxt.entity
    rels = [view(r) for r in rows.where(conn, entities.Relation, src_kind='knowledge_item',
                                        src_id=knowledge_item_id)]
    rels += [view(r) for r in rows.where(conn, entities.Relation, dst_kind='knowledge_item',
                                         dst_id=knowledge_item_id)]
    return dict(view(row), chain=chain + [knowledge_item_id] + after, relations=rels)


def get_route_decision(conn, route_decision_id):
    row = rows.get(conn, entities.RouteDecision, route_decision_id)
    if row is None:
        raise NotFound(route_decision_id)
    usage = [view(r) for r in rows.where(conn, entities.UsageLedger,
                                         route_decision_id=route_decision_id)]
    return dict(view(row), usage=usage)


def route_decisions(conn, source_id=None, purpose=None):
    """Route decisions, oldest first; those about *source_id* when given."""
    eq = {} if purpose is None else {'purpose': purpose}
    got = rows.where(conn, entities.RouteDecision, **eq)
    if source_id is not None:
        got = [r for r in got if r.entity.source is not None and r.entity.source.id == source_id]
    return [view(r) for r in got]


def provider_terms(conn, harness_ids=()):
    """Every ADR-0021 answer given, plus `unknown` for each named harness that
    has none (no row IS the unknown answer)."""
    have = {r.entity.id: view(r) for r in rows.where(conn, entities.ProviderTerms)}
    for h in harness_ids:
        have.setdefault(h, {'id': h, 'headless': 'unknown', 'rotation': 'unknown', 'note': '',
                            'version': 0, 'created_at': None, 'updated_at': None})
    return [have[k] for k in sorted(have)]



# ── conversation, intent, ideas (P7) ────────────────────────────────────────

def _conversation(conn, conversation_id):
    """A conversation id, or `primary` for the primary one (None before any
    message was written)."""
    if conversation_id == 'primary':
        got = rows.where(conn, entities.Conversation, kind='primary')
        return got[0].entity.id if got else None
    if rows.get(conn, entities.Conversation, conversation_id) is None:
        raise NotFound(conversation_id)
    return conversation_id


def messages(conn, conversation_id, after=None):
    """A conversation's messages, oldest first; those after message *after*."""
    cid = _conversation(conn, conversation_id)
    if cid is None:
        return []
    got = [view(r) for r in rows.where(conn, entities.Message, conversation_id=cid)]
    if after is not None:
        idx = [i for i, m in enumerate(got) if m['id'] == after]
        if not idx:
            raise NotFound(after)
        got = got[idx[0] + 1:]
    return got


def reply_to(conn, message_id):
    """Archeus's reply to a message, or None while it is still being read."""
    got = rows.where(conn, entities.Message, in_reply_to=message_id)
    got = [r for r in got if r.entity.author == 'archeus']
    return view(got[0]) if got else None


def get_intent(conn, intent_id):
    row = rows.get(conn, entities.Intent, intent_id)
    if row is None:
        raise NotFound(intent_id)
    return view(row)


def question_of(conn, intent_id):
    """The reply that asked the user about an intent (its clarification or
    challenge card), as a message view."""
    it = get_intent(conn, intent_id)
    reply = reply_to(conn, it['message_id'])
    if reply is None or it['resolution'] != 'clarification_requested':
        raise ValueError('intent %s is not waiting for an answer' % intent_id)
    return reply


def list_ideas(conn, state=None):
    if state is not None and state not in states.states('idea'):
        raise ValueError('%r is not an idea state' % (state,))
    eq = {} if state is None else {'state': state}
    return [view(r) for r in rows.where(conn, entities.Idea, **eq)]
