"""Queries: read-only views over one snapshot (`Database.read()`)."""

import json

from ...infra.db import rows
from ...infra.db.writer import NotFound
from ...infra.eventlog import outbox
from ..domain import entities, states
from .commands import active_plan


def view(row):
    """An entity row as the API shows it: the entity plus its row metadata."""
    return dict(row.entity.to_dict(), version=row.version, created_at=row.created_at,
                updated_at=row.updated_at)


def get_mission(conn, mission_id):
    """One mission, with the context package its `context_ready` move
    recorded (None before it has one) and the plan in force (P8): its id and
    `plan_version`, derived from the plans and never stored twice."""
    row = rows.get(conn, entities.Mission, mission_id)
    if row is None:
        raise NotFound(mission_id)
    pid = row.entity.context_package_id
    plan = active_plan(conn, mission_id)
    pending = [r.entity.id for r in rows.where(conn, entities.Approval, mission_id=mission_id)
               if r.entity.state == 'PENDING']
    return dict(view(row), context_package=None if pid is None else get_context_package(conn, pid),
                plan_id=None if plan is None else plan.entity.id,
                plan_version=None if plan is None else plan.entity.plan_version,
                pending_approval_id=pending[-1] if pending else None)


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
    """Route decisions, oldest first; those about *source_id* when given (what
    the decision is about, or its subject: a task's decisions are found by the
    task and by its mission)."""
    eq = {} if purpose is None else {'purpose': purpose}
    got = rows.where(conn, entities.RouteDecision, **eq)
    if source_id is not None:
        got = [r for r in got if source_id in (r.entity.subject.id, r.entity.source
                                               and r.entity.source.id)]
    return [view(r) for r in got]


def get_account(conn, account_id):
    row = rows.get(conn, entities.Account, account_id)
    if row is None:
        raise NotFound(account_id)
    return view(row)


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


# ── plans (P8) ──────────────────────────────────────────────────────────────

def get_plan(conn, plan_id):
    """One exact PlanVersion with its tasks (by key), the parallel waves derived
    from its graph, and whether what it was planned from is still current."""
    from ..planning import planner, validate
    row = rows.get(conn, entities.Plan, plan_id)
    if row is None:
        raise NotFound(plan_id)
    p = row.entity
    tasks = sorted((view(t) for t in rows.where(conn, entities.Task, plan_id=p.id)),
                   key=lambda t: int(t['key'][1:]) if t['key'][1:].isdigit() else t['key'])
    current, why = True, 'planned without a recorded context package'
    if p.context_package_id is not None:
        mission = rows.get(conn, entities.Mission, p.mission_id).entity
        current, why = planner.currency(conn, mission, p.context_package_id)
    # P9 (§10.2): `current` keeps P8's meaning (context currency); these say
    # whether this exact version can be authorised now
    from . import authorization
    in_force = (p.state in ('PROPOSED', 'APPROVED')
                and active_plan(conn, p.mission_id).entity.id == p.id)
    whole = authorization.intact(conn, p)
    eligible_why = ('not in force' if not in_force else 'its content does not match its digest'
                    if not whole else None if current else why)
    return dict(view(row), tasks=tasks, waves=validate.waves(tasks),
                current=current, current_why=why, in_force=in_force,
                eligible=eligible_why is None, eligible_why=eligible_why)


def mission_plan(conn, mission_id):
    """The plan in force (None before the first) and every version, oldest first."""
    if rows.get(conn, entities.Mission, mission_id) is None:
        raise NotFound(mission_id)
    versions = sorted(rows.where(conn, entities.Plan, mission_id=mission_id),
                      key=lambda r: r.entity.plan_version)
    return {'mission_id': mission_id,
            'plan': get_plan(conn, versions[-1].entity.id) if versions else None,
            'versions': [{'id': r.entity.id, 'plan_version': r.entity.plan_version,
                          'state': r.entity.state,
                          'supersedes_plan_id': r.entity.supersedes_plan_id,
                          'digest': r.entity.digest} for r in versions]}


# ── policy and approvals (P9) ───────────────────────────────────────────────

def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def approval_view(conn, row, now=None):
    from . import authorization
    a = row.entity
    bad = (None if a.state != 'PENDING'
           else authorization.ineligible(conn, a, now=now or _now()))
    return dict(view(row), eligible=a.state == 'PENDING' and bad is None,
                eligible_why=None if bad is None else bad[0],
                eligible_detail=None if bad is None else bad[1])


def get_approval(conn, approval_id, now=None):
    row = rows.get(conn, entities.Approval, approval_id)
    if row is None:
        raise NotFound(approval_id)
    return approval_view(conn, row, now)


def list_approvals(conn, state=None, mission_id=None, now=None):
    if state is not None and state not in states.states('approval'):
        raise ValueError('%r is not an approval state' % (state,))
    eq = {k: v for k, v in (('state', state), ('mission_id', mission_id)) if v is not None}
    return [approval_view(conn, r, now) for r in rows.where(conn, entities.Approval, **eq)]


def get_policy_decision(conn, decision_id):
    row = rows.get(conn, entities.PolicyDecision, decision_id)
    if row is None:
        raise NotFound(decision_id)
    return view(row)


def list_policy_decisions(conn, mission_id=None, stage=None):
    if stage is not None and stage not in entities.POLICY_STAGES:
        raise ValueError('%r is not a policy stage' % (stage,))
    eq = {k: v for k, v in (('mission_id', mission_id), ('stage', stage)) if v is not None}
    return [view(r) for r in rows.where(conn, entities.PolicyDecision, **eq)]


def policies(conn):
    """The policy in force: Core's own rules, the profiles, the user's rules
    (retired ones kept, marked), the user's default profile and the version."""
    from ..policy import rules as R
    from . import authorization
    u = authorization.owner(conn)
    user = [view(r) for r in rows.where(conn, entities.PolicyRule)]
    return {'builtin': R.builtin(), 'profiles': {
        name: {c: {'decision': d, 'boundary': b} for c, (d, b) in table.items()}
        for name, table in R.PROFILES.items()},
        'profiles_version': R.PROFILES_VERSION, 'rules': user,
        'user_profile': u.autonomy_profile if u else 'standard',
        'policy_version': authorization.policy_version(authorization.user_rules(conn))}
