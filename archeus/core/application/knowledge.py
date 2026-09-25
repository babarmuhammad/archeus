"""Knowledge commands (P6; context-and-knowledge §3, state-machines §11,
p6-design-gate §6).

The invariant every command here keeps: **model output is never confirmed
truth.** What a call produced enters as CANDIDATE with its provenance (the
source it was read from, the RouteDecision naming harness, account and model,
and the ContextPackage it was given). CANDIDATE becomes CONFIRMED only by the
user, by an explicit origin, or — for a LESSON — by corroboration from two
distinct missions. Nothing is deleted: supersession keeps the old item as
history, retraction keeps the row, and purge keeps a tombstone.
"""

from ..domain import entities, ids
from ..domain.events import new_event
from ..domain.values import Ref
from . import calls as C
from . import lifecycle
from .queries import view

#: a relation's endpoints that a model may name (the rest are Core's)
FEEDBACK_SUBJECTS = ('message', 'mission', 'plan', 'route_decision', 'knowledge_item')
PROMOTABLE = ('PREFERENCE', 'LESSON')
#: distinct missions a LESSON needs before it confirms itself (§3)
CORROBORATION = 2


def key(title):
    """The identity two items share when they are the same claim: the title,
    casefolded, whitespace collapsed. Equality, never similarity."""
    return ' '.join(title.casefold().split())


def _live(tx, *, type_, project_id, workspace_id, k, source_ref=None):
    """A CANDIDATE or CONFIRMED item of this type and scope with key *k* (and,
    when given, from *source_ref*), or None."""
    for r in tx.where(entities.KnowledgeItem, type=type_):   # project None: `= NULL` is never
        e = r.entity
        if (e.project_id == project_id and e.state in ('CANDIDATE', 'CONFIRMED')
                and e.workspace_id == workspace_id
                and key(e.title) == k
                and (source_ref is None or e.source_ref == Ref(**source_ref))):
            return r
    return None


def new_item(tx, *, actor, **fields):
    k = entities.KnowledgeItem(id=ids.new_id('knowledge_item'), observed_at=tx.now, **fields)
    tx.insert(k, actor=actor)
    tx.append(new_event('knowledge_item.created', Ref('knowledge_item', k.id), actor,
                        payload={'type': k.type, 'title': k.title, 'origin': k.origin,
                                 'source_kind': k.source_kind},
                        workspace=k.workspace_id, project=k.project_id))
    return k


def relate(tx, *, actor, src, rel, dst, tier, project_id=None, source_kind=None,
           source_ref=None, route_decision_id=None):
    """A relation, or the identical one already there (same ends, same rel)."""
    for r in tx.where(entities.Relation, src_kind=src[0], src_id=src[1], rel=rel):
        if (r.entity.dst_kind, r.entity.dst_id) == tuple(dst) and r.entity.valid_until is None:
            return r.entity.id, False
    rel_ = entities.Relation(id=ids.new_id('relation'), src_kind=src[0], src_id=src[1],
                             rel=rel, dst_kind=dst[0], dst_id=dst[1], confidence_tier=tier,
                             project_id=project_id, source_kind=source_kind,
                             source_ref=source_ref, route_decision_id=route_decision_id)
    tx.insert(rel_, actor=actor)
    tx.append(new_event('relation.created', Ref('relation', rel_.id), actor,
                        payload={'src': list(src), 'rel': rel, 'dst': list(dst), 'tier': tier},
                        project=project_id))
    return rel_.id, True


# ── the lifecycle (state-machines §11) ─────────────────────────────────────

def _load(tx, knowledge_item_id):
    return lifecycle.load(tx, entities.KnowledgeItem, knowledge_item_id)


def confirm(tx, *, actor, knowledge_item_id, reason='confirmed by the user',
            expected_version=None):
    """CANDIDATE -> CONFIRMED. An item that supersedes another sets the older
    one SUPERSEDED in the same move (valid_until, superseded_by_id); the older
    must itself be CONFIRMED, since only a confirmed item can be superseded."""
    row = _load(tx, knowledge_item_id)
    old = row.entity.supersedes_id
    if old is not None and _load(tx, old).entity.state != 'CONFIRMED':
        raise ValueError('%s supersedes %s, which is not CONFIRMED' % (knowledge_item_id, old))
    krow, e = lifecycle.fire(tx, entities.KnowledgeItem, knowledge_item_id, 'confirm',
                             actor=actor, reason=reason, expected_version=expected_version)
    moved = [e]
    if old is not None:
        _r, e2 = lifecycle.fire(tx, entities.KnowledgeItem, old, 'superseded', actor=actor,
                                reason='superseded by %s' % knowledge_item_id,
                                fields={'valid_until': tx.now,
                                        'superseded_by_id': knowledge_item_id})
        moved.append(e2)
    return {'knowledge_item': view(krow), 'changed': True,
            'superseded': old, 'seq': moved[-1].seq}


def reject(tx, *, actor, knowledge_item_id, reason='rejected by the user',
           expected_version=None):
    krow, e = lifecycle.fire(tx, entities.KnowledgeItem, knowledge_item_id, 'reject',
                             actor=actor, reason=reason, expected_version=expected_version)
    return {'knowledge_item': view(krow), 'changed': True, 'seq': e.seq}


def retract(tx, *, actor, knowledge_item_id, reason='retracted by the user',
            expected_version=None):
    krow, e = lifecycle.fire(tx, entities.KnowledgeItem, knowledge_item_id, 'retract',
                             actor=actor, reason=reason, expected_version=expected_version)
    return {'knowledge_item': view(krow), 'changed': True, 'seq': e.seq}


def supersede(tx, *, actor, knowledge_item_id, title, text=''):
    """The user states the replacement of a CONFIRMED item: a new item of the
    same type and scope, origin explicit, so it confirms itself at once
    (state-machines §11) and the older one becomes SUPERSEDED. Nothing is
    deleted; the chain is `supersedes_id` / `superseded_by_id`."""
    old = _load(tx, knowledge_item_id).entity
    if old.state != 'CONFIRMED':
        raise ValueError('only a CONFIRMED item can be superseded, %s is %s'
                         % (old.id, old.state))
    k = new_item(tx, actor=actor, workspace_id=old.workspace_id, project_id=old.project_id,
                 type=old.type, title=title, text=text, origin='explicit',
                 supersedes_id=old.id, source_kind='user',
                 source_ref=Ref('knowledge_item', old.id), anchors=old.anchors)
    relate(tx, actor=actor, src=('knowledge_item', k.id), rel='supersedes',
           dst=('knowledge_item', old.id), tier='EXTRACTED', project_id=old.project_id,
           source_kind='user')
    return confirm(tx, actor=actor, knowledge_item_id=k.id,
                   reason='stated by the user (origin explicit)')


def _selected(tx, selector):
    if not isinstance(selector, dict) or not selector:
        raise ValueError('a selector names ids, or a project (and optionally a type/source)')
    if 'ids' in selector:
        return [_load(tx, i) for i in selector['ids']]
    eq = {k: selector[k] for k in ('project_id', 'type') if selector.get(k) is not None}
    if not eq:
        raise ValueError('a selector without ids needs a project_id')
    got = tx.where(entities.KnowledgeItem, **eq)
    if selector.get('source_id'):
        got = [r for r in got if r.entity.source_ref is not None
               and r.entity.source_ref.id == selector['source_id']]
    return got


def forget(tx, *, actor, selector, mode='retract', dry_run=True):
    """The one forget entry point (§3, Cognee's shape). `retract` keeps the
    row and takes it out of context; `purge` also blanks its content and keeps
    a tombstone with its provenance. A dry run (the default) says what would
    change and changes nothing."""
    if mode not in ('retract', 'purge'):
        raise ValueError('mode is retract or purge')
    changes = []
    for r in _selected(tx, selector):
        e = r.entity
        trigger = {'CONFIRMED': 'retract', 'CANDIDATE': 'reject'}.get(e.state)
        purge = mode == 'purge' and not e.purged
        if trigger is None and not purge:
            continue
        changes.append({'id': e.id, 'from': e.state, 'to': 'RETRACTED' if trigger else e.state,
                        'purge': purge})
        if dry_run:
            continue
        if trigger:
            lifecycle.fire(tx, entities.KnowledgeItem, e.id, trigger, actor=actor,
                           reason='forgotten (%s)' % mode)
        if purge:
            tx.update(entities.KnowledgeItem, e.id,
                      {'title': '[purged]', 'text': '', 'anchors': (), 'constraint': None,
                       'purged': True}, actor=actor)
            tx.append(new_event('knowledge_item.purged', Ref('knowledge_item', e.id), actor,
                                payload={'provenance': {'source_kind': e.source_kind,
                                                        'route_decision_id':
                                                            e.route_decision_id}},
                                workspace=e.workspace_id, project=e.project_id))
    return {'dry_run': dry_run, 'mode': mode, 'changes': changes, 'changed': bool(
        changes) and not dry_run}


# ── feedback (domain-model §7.8) ───────────────────────────────────────────

def record_feedback(tx, *, actor, subject, signal, text='', promote=None):
    """Feedback is history. With `promote` it is also the explicit step that
    proposes a PREFERENCE or LESSON: a CANDIDATE (§3: feedback never
    auto-confirms), optionally superseding a CONFIRMED item once confirmed."""
    subject = Ref(**subject)
    if subject.kind not in FEEDBACK_SUBJECTS:
        raise ValueError('feedback is about one of %s' % (FEEDBACK_SUBJECTS,))
    workspace, project = ids.GLOBAL_WORKSPACE, None
    if subject.kind == 'mission':
        m = lifecycle.load(tx, entities.Mission, subject.id).entity
        workspace, project = m.workspace_id, m.project_id
    elif subject.kind == 'knowledge_item':
        k = _load(tx, subject.id).entity
        workspace, project = k.workspace_id, k.project_id
    fb = entities.Feedback(id=ids.new_id('feedback'), subject=subject, signal=signal,
                           text=text, workspace_id=workspace, project_id=project,
                           principal_id=actor.id)
    promoted = None
    if promote is not None:
        if promote.get('type') not in PROMOTABLE:
            raise ValueError('feedback promotes into one of %s' % (PROMOTABLE,))
        sup = promote.get('supersedes_id')
        if sup is not None and _load(tx, sup).entity.state != 'CONFIRMED':
            raise ValueError('%s is not CONFIRMED, so nothing can supersede it' % sup)
        promoted = new_item(tx, actor=actor, workspace_id=workspace, project_id=project,
                            type=promote['type'], title=promote['title'],
                            text=promote.get('text', ''), origin='explicit',
                            supersedes_id=sup, source_kind='user',
                            source_ref=Ref('feedback', fb.id))
        fb = entities.Feedback(**dict(fb.to_dict(), subject=subject,
                                      promoted_knowledge_id=promoted.id))
    tx.insert(fb, actor=actor)
    krow = None if promoted is None else tx.get(entities.KnowledgeItem, promoted.id)
    e = tx.append(new_event('feedback.received', Ref('feedback', fb.id), actor,
                            payload={'signal': signal, 'subject': {'kind': subject.kind,
                                                                   'id': subject.id},
                                     'promoted': None if krow is None else view(krow)},
                            workspace=workspace, project=project))
    return {'feedback_id': fb.id, 'promoted': None if krow is None else view(krow),
            'seq': e.seq}


# ── meeting import (context-and-knowledge §8) ──────────────────────────────

def import_meeting(tx, *, actor, name, held_at, notes_sha256, notes_size, imported_from,
                   project_id=None):
    """A Meeting over notes already in the artifact store. Importing the same
    notes into the same scope again returns the meeting there (idempotent)."""
    workspace = ids.GLOBAL_WORKSPACE
    if project_id is not None:
        workspace = lifecycle.load(tx, entities.Project, project_id).entity.workspace_id
    for r in tx.where(entities.Meeting):
        if r.entity.project_id == project_id and r.entity.notes_artifact_id == notes_sha256:
            return {'meeting': view(r), 'changed': False}
    if tx.get(entities.Artifact, notes_sha256) is None:
        tx.insert(entities.Artifact(id=notes_sha256, media_type='text/markdown',
                                    size=notes_size), actor=actor)
    m = entities.Meeting(id=ids.new_id('meeting'), workspace_id=workspace, name=name,
                         held_at=held_at, project_id=project_id,
                         notes_artifact_id=notes_sha256, imported_from=imported_from)
    tx.insert(m, actor=actor)
    tx.append(new_event('meeting.imported', Ref('meeting', m.id), actor,
                        payload={'name': name, 'held_at': held_at}, workspace=workspace,
                        project=project_id))
    return {'meeting': view(tx.get(entities.Meeting, m.id)), 'changed': True}


# ── recording what a call produced, with the call's end, in one command ─────

def _end(tx, actor, called, **counts):
    C.end_call(tx, actor=actor, route_decision_id=called['route_decision_id'],
               outcome={'state': 'ok', 'attempts': called['attempts'],
                        'account_ref': called['account_ref'], **counts},
               usage=called['usage'] or None)


def _provenance(called, source_kind, source_ref):
    return {'origin': 'inferred', 'source_kind': source_kind, 'source_ref': source_ref,
            'route_decision_id': called['route_decision_id'],
            'context_package_id': called['context_package_id']}


def record_knowledge_pass(tx, *, actor, called, project_id, workspace_id, inspection_id,
                          result, known_items=()):
    """Entities the model described, as INFERRED ENTITY CANDIDATEs citing the
    inspection; their relations INFERRED; a `contradicts` only towards a
    knowledge item the call was actually shown (`known_items`). An entity
    already live under the same name is not duplicated. Dangling relation ends
    are dropped and counted (the partial result the contract permits)."""
    src = Ref('repository_inspection', inspection_id)
    names, created, dup, rels, dropped = {}, 0, 0, 0, 0
    for e in result['entities']:
        k = key(e['name'])
        live = _live(tx, type_='ENTITY', project_id=project_id, workspace_id=workspace_id, k=k)
        if live is not None:
            names[k], dup = live.entity.id, dup + 1
            continue
        item = new_item(tx, actor=actor, workspace_id=workspace_id, project_id=project_id,
                        type='ENTITY', title=e['name'].strip(), text=e.get('summary') or '',
                        anchors=(e['module'],) if e.get('module') else (),
                        **_provenance(called, 'inspection', src))
        names[k], created = item.id, created + 1
    for r in result.get('relations') or ():
        a, b = names.get(key(r['from'])), names.get(key(r['to']))
        if a is None or b is None or a == b:
            dropped += 1
            continue
        rels += relate(tx, actor=actor, src=('knowledge_item', a), rel=r['rel'],
                       dst=('knowledge_item', b), tier='INFERRED', project_id=project_id,
                       source_kind='inspection', source_ref=src,
                       route_decision_id=called['route_decision_id'])[1]
    for c in result.get('contradicts') or ():
        a = names.get(key(c['entity']))
        if a is None or c['existing'] not in known_items:
            dropped += 1
            continue
        rels += relate(tx, actor=actor, src=('knowledge_item', a), rel='contradicts',
                       dst=('knowledge_item', c['existing']), tier='INFERRED',
                       project_id=project_id, source_kind='inspection', source_ref=src,
                       route_decision_id=called['route_decision_id'])[1]
    _end(tx, actor, called, items=created, duplicates=dup, relations=rels, dropped=dropped)
    return {'items': created, 'duplicates': dup, 'relations': rels, 'dropped': dropped}


def record_decisions(tx, *, actor, called, meeting_id, result):
    """DECISION candidates read from a meeting's notes (§8: never auto-confirmed),
    each linked `decided_in` to the meeting (EXTRACTED: that link is a fact)."""
    m = lifecycle.load(tx, entities.Meeting, meeting_id).entity
    src = Ref('meeting', meeting_id)
    created, dup = 0, 0
    for d in result['decisions']:
        k = key(d['statement'])
        if _live(tx, type_='DECISION', project_id=m.project_id, workspace_id=m.workspace_id,
                 k=k, source_ref={'kind': 'meeting', 'id': meeting_id}) is not None:
            dup += 1
            continue
        item = new_item(tx, actor=actor, workspace_id=m.workspace_id, project_id=m.project_id,
                        type='DECISION', title=d['statement'].strip(),
                        text=d.get('rationale') or '', **_provenance(called, 'import', src))
        relate(tx, actor=actor, src=('knowledge_item', item.id), rel='decided_in',
               dst=('meeting', meeting_id), tier='EXTRACTED', project_id=m.project_id,
               source_kind='import', source_ref=src)
        created += 1
    _end(tx, actor, called, items=created, duplicates=dup)
    return {'items': created, 'duplicates': dup}


def record_lessons(tx, *, actor, called, mission_id, result):
    """LESSON candidates from a mission that ended. The same lesson (same key,
    same scope) from another mission is not a second item: it is a second
    `learned_from`, and at CORROBORATION distinct missions the lesson confirms
    itself. Model confidence plays no part (p6-design-gate D4)."""
    m = lifecycle.load(tx, entities.Mission, mission_id).entity
    src = Ref('mission', mission_id)
    created, corroborated, confirmed = 0, 0, 0
    for les in result['lessons']:
        k = key(les['title'])
        live = _live(tx, type_='LESSON', project_id=m.project_id, workspace_id=m.workspace_id,
                     k=k)
        if live is None:
            item = new_item(tx, actor=actor, workspace_id=m.workspace_id,
                            project_id=m.project_id, type='LESSON', title=les['title'].strip(),
                            text=les.get('text') or '', **_provenance(called, 'execution', src))
            lid, created = item.id, created + 1
        else:
            lid = live.entity.id
        if relate(tx, actor=actor, src=('knowledge_item', lid), rel='learned_from',
                  dst=('mission', mission_id), tier='EXTRACTED', project_id=m.project_id,
                  source_kind='execution', source_ref=src,
                  route_decision_id=called['route_decision_id'])[1] and live is not None:
            corroborated += 1
        missions = {r.entity.dst_id for r in tx.where(
            entities.Relation, src_kind='knowledge_item', src_id=lid, rel='learned_from')}
        if (len(missions) >= CORROBORATION
                and tx.get(entities.KnowledgeItem, lid).entity.state == 'CANDIDATE'):
            lifecycle.fire(tx, entities.KnowledgeItem, lid, 'confirm', actor=actor,
                           reason='corroborated by %d missions: %s' % (
                               len(missions), ', '.join(sorted(missions))))
            confirmed += 1
    _end(tx, actor, called, items=created, corroborated=corroborated, confirmed=confirmed)
    return {'items': created, 'corroborated': corroborated, 'confirmed': confirmed}
