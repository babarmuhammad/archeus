"""T-715: the highest-risk uncovered branches of
`archeus/core/application/knowledge.py`, as unit tests.

Fail-closed and denial paths first (a `forget` selector that names nothing, a
mode outside retract/purge, a confirm whose predecessor has already ended, a
supersede of anything but a CONFIRMED item, a feedback subject outside
FEEDBACK_SUBJECTS, the promotion gates, a `contradicts` towards an item the
call was never shown), then the boundary values (identity by `key`, the
distinct-mission corroboration count, the already-superseded relation, replay
of the same request), then the error paths.

Same style and fixtures as the closest existing tests of this module,
tests/v1/unit/test_fix_knowledge.py, and of the other gaps file,
tests/v1/unit/test_gaps_core_application_conversation.py: the real writer and
the real state machines over the test's own home (`Database.open()`), the
brain-call end as the monkeypatched seam `C.end_call` the conversation gaps
test already uses, real entities so every domain validation still runs.
Platform-neutral: no OS call, no file of its own, no network, no process, no
sleep; every temp path comes from tmp_path through the conftest's archeus_home
fixture.
"""

import pytest

from archeus.core.application import calls as CALLS
from archeus.core.application import knowledge as K
from archeus.core.application import queries
from archeus.core.application.lifecycle import IllegalTrigger
from archeus.core.application.lifecycle import NotFound, VersionConflict
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows
from archeus.infra.db.writer import IdempotencyConflict

SHA = 'a' * 64
SHA2 = 'b' * 64
#: taken before the autouse fixture below replaces it (one test needs the real end)
REAL_END_CALL = CALLS.end_call
CONSTRAINT = {'kind': 'module_exists', 'spec': {'path': 'app/core.py'}}


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    try:
        yield d
    finally:
        d.close()


USER = Ref('user_device', ids.new_id('principal'))


# ── the seeds (one writer transaction each, as every gaps test does) ──

def _seed(db, *ents):
    """Rows the test needs already there. One transaction, and the single event
    the writer's own rule asks a mutation to carry (infra/db/writer.py `_one`:
    a command that changes state and records no event is refused)."""
    def work(tx, ents):
        for e in ents:
            tx.insert(e, actor=USER)
        tx.append(new_event('project.created', Ref('project', ids.new_id('project')), USER,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(work, {'ents': list(ents)})


def _run(db, command, key=None, actor=None, **kw):
    return db.writer.execute(command, dict(kw, actor=actor or USER), idempotency_key=key)


def _row(db, cls, id_):
    with db.read() as c:
        r = rows.get(c, cls, id_)
    return None if r is None else r.entity


def _all(db, cls, **eq):
    with db.read() as c:
        return [r.entity for r in rows.where(c, cls, **eq)]


def _version(db, cls, id_):
    with db.read() as c:
        r = rows.get(c, cls, id_)
    return None if r is None else r.version


def _n_events(db):
    with db.read() as c:
        return len(queries.events(c, 0))


def _all_events(db, etype):
    with db.read() as c:
        return [e for e in queries.events(c, 0) if e['type'] == etype]


def _project(db, name='repo'):
    p = entities.Project(id=ids.new_id('project'), workspace_id=ids.GLOBAL_WORKSPACE,
                         name=name)
    _seed(db, p)
    return p.id


def _mission(db, project_id=None, state='COMPLETED'):
    m = entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                         title='Ship it', objective='Ship it once', state=state,
                         project_id=project_id)
    _seed(db, m)
    return m.id


def _meeting(db, project_id=None, held_at='2026-09-20'):
    m = entities.Meeting(id=ids.new_id('meeting'), workspace_id=ids.GLOBAL_WORKSPACE,
                         name='kickoff', held_at=held_at, project_id=project_id,
                         notes_artifact_id=SHA, imported_from='n.md')
    _seed(db, m)
    return m.id


def _item(db, *, type_='FACT', title='Prefer the seam', state='CANDIDATE', project_id=None,
          source_kind='user', origin='explicit', supersedes_id=None, constraint=None,
          text='', anchors=(), source_ref=None, route_decision_id=None, purged=False,
          workspace_id=None):
    k = entities.KnowledgeItem(id=ids.new_id('knowledge_item'),
                               workspace_id=workspace_id or ids.GLOBAL_WORKSPACE, type=type_, title=title,
                               text=text, origin=origin, state=state, project_id=project_id,
                               source_kind=source_kind, source_ref=source_ref,
                               supersedes_id=supersedes_id, constraint=constraint,
                               anchors=anchors, route_decision_id=route_decision_id,
                               purged=purged)
    _seed(db, k)
    return k.id


def _relation(db, src, dst, rel='depends_on', dst_kind='knowledge_item', **kw):
    r = entities.Relation(id=ids.new_id('relation'), src_kind='knowledge_item', src_id=src,
                          rel=rel, dst_kind=dst_kind, dst_id=dst,
                          **kw)
    _seed(db, r)
    return r.id


def _route_decision(db, purpose='knowledge_extraction'):
    r = entities.RouteDecision(id=ids.new_id('route_decision'), subject=Ref('archeus_call', '1'),
                               purpose=purpose, decided_by='router', result='selected',
                               harness_id='pi', account_ref='fake:pi', model='pi/smart')
    _seed(db, r)
    return r.id


def called(usage=None, rd_id=None, attempts=1):
    """The `called` dict the caller of these commands hands in (the exact shape
    of core/knowledge/passes.py `_called`)."""
    return {'route_decision_id': rd_id or ids.new_id('route_decision'),
            'context_package_id': ids.new_id('context_package'), 'attempts': attempts,
            'account_ref': 'fake:pi', 'usage': usage}


@pytest.fixture(autouse=True)
def ends(monkeypatch):
    """The end of a brain call: recorded, not executed (these tests have no
    RouteDecision to end), the same seam
    tests/v1/unit/test_gaps_core_application_conversation.py uses. Autouse: a
    record_* command that reached its `_end` with no row to write would fail on
    the plumbing instead of the branch. The one test that checks the real end
    puts it back."""
    seen = []
    monkeypatch.setattr(K.C, 'end_call', lambda tx, **kw: (seen.append(kw), {'state': 'ok'})[1])
    return seen


def _result(**over):
    r = {'entities': [{'name': 'core', 'summary': 'The domain.', 'module': 'app/core'},
                      {'name': 'api', 'summary': 'The HTTP layer.', 'module': 'app/api'}],
         'relations': [{'from': 'api', 'rel': 'depends_on', 'to': 'core'}],
         'contradicts': []}
    r.update(over)
    return r


# ── 1. forget: the one entry point that may destroy, refused before it selects ──

@pytest.mark.parametrize('mode', ['RETRACT', 'delete', 'erase', '', None, 0])
def test_forget_refuses_a_mode_that_is_neither_retract_nor_purge(db, mode):
    """knowledge.py:173 (`if mode not in ('retract', 'purge')`): widened, a
    typo or a client's `delete` quietly takes the `retract` path on data the
    user asked to purge. The refusal is first, so it also precedes the select."""
    pid = _project(db)
    kid = _item(db, project_id=pid, state='CONFIRMED')
    before = _n_events(db)
    with pytest.raises(ValueError, match='mode is retract or purge'):
        _run(db, K.forget, selector={'project_id': pid}, mode=mode, dry_run=False)
    assert _row(db, entities.KnowledgeItem, kid).state == 'CONFIRMED'
    assert _version(db, entities.KnowledgeItem, kid) == 1
    assert _n_events(db) == before


@pytest.mark.parametrize('selector', [None, {}, [], '', 7, {'ids': 'x'}, {'ids': [1]},
                                      {'source_id': 'x'}, {'state': 'CONFIRMED'}])
def test_forget_refuses_a_selector_that_names_nothing_at_all(db, selector):
    """knowledge.py:148-149 + 159-160 (`if not isinstance(selector, dict) or not
    selector` and `if not eq`): an empty or unrecognised selector must never
    mean "everything"; it is refused, and the live item is left alone."""
    pid = _project(db)
    kid = _item(db, project_id=pid, state='CONFIRMED', type_='FACT')
    before = _n_events(db)
    with pytest.raises(ValueError):
        _run(db, K.forget, selector=selector, dry_run=False)
    assert _row(db, entities.KnowledgeItem, kid).state == 'CONFIRMED'
    assert _n_events(db) == before


def test_a_selector_naming_only_a_type_is_refused_like_any_other_unscoped_one(db):
    """knowledge.py:158-160 (`eq = {k: selector[k] ...}` then `if not eq: raise`): a type is an
    adjective of a scope, never a scope of its own — without this the one command
    that may destroy data walks out of one project into every other one."""
    p1, p2 = _project(db, 'one'), _project(db, 'two')
    one = _item(db, project_id=p1, state='CONFIRMED', type_='FACT', title='One')
    two = _item(db, project_id=p2, state='CONFIRMED', type_='FACT', title='Two')
    with pytest.raises(ValueError, match='needs a project_id'):
        _run(db, K.forget, selector={'type': 'FACT'}, dry_run=False)
    assert _row(db, entities.KnowledgeItem, one).state == 'CONFIRMED'
    assert _row(db, entities.KnowledgeItem, two).state == 'CONFIRMED'


@pytest.mark.parametrize('bad', [{'project_id': 7}, {'type': 7}, {'source_id': 7},
                                 {'project_id': ['p']}])
def test_forget_refuses_a_selector_whose_scope_is_not_a_string(db, bad):
    """knowledge.py:150-152 (the `any(not isinstance(...))` guard): a non-string
    scope would reach `tx.where` as a column comparison and answer "nothing",
    the same result as a selector that matched no row."""
    _project(db)
    with pytest.raises(ValueError, match='are strings'):
        _run(db, K.forget, selector=bad, dry_run=False)


def test_forget_naming_an_empty_id_list_forgets_nothing_rather_than_everything(db):
    """knowledge.py:153-157 (`isinstance(selector['ids'], list)` with all() over
    the empty list): `{'ids': []}` is a valid, empty choice — not the whole
    project and not the "no selector" refusal."""
    pid = _project(db)
    kid = _item(db, project_id=pid, state='CONFIRMED')
    out = _run(db, K.forget, selector={'ids': []}, dry_run=False)
    assert (out['changes'], out['changed']) == ([], False)
    assert _row(db, entities.KnowledgeItem, kid).state == 'CONFIRMED'


def test_forget_reaches_for_exactly_the_items_it_names(db):
    """knowledge.py:153 (`if 'ids' in selector`): ids win over the scope
    keys, and the sibling in the same project is untouched."""
    pid = _project(db)
    named = _item(db, project_id=pid, state='CONFIRMED', title='Named one')
    other = _item(db, project_id=pid, state='CONFIRMED', title='Other one')
    out = _run(db, K.forget, selector={'ids': [named], 'project_id': pid}, dry_run=False)
    assert [c['id'] for c in out['changes']] == [named]
    assert _row(db, entities.KnowledgeItem, named).state == 'RETRACTED'
    assert _row(db, entities.KnowledgeItem, other).state == 'CONFIRMED'


def test_forget_of_an_id_that_is_not_there_writes_nothing_at_all(db):
    """knowledge.py:157 (`[_load(tx, i) for i in selector['ids']]`) via
    lifecycle.load: one unknown id aborts the whole command, so a partial
    forget — half the user's data retracted, the rest not — cannot happen."""
    pid = _project(db)
    kid = _item(db, project_id=pid, state='CONFIRMED')
    before = _n_events(db)
    with pytest.raises(NotFound):
        _run(db, K.forget, selector={'ids': [kid, ids.new_id('knowledge_item')]},
             dry_run=False)
    assert _row(db, entities.KnowledgeItem, kid).state == 'CONFIRMED'
    assert _version(db, entities.KnowledgeItem, kid) == 1
    assert _n_events(db) == before


def test_forget_dry_run_is_the_default_and_changes_nothing(db):
    """knowledge.py:182-184 (`if dry_run: continue`) and the `changed` rule:
    the answer says what would move, the rows do not move."""
    pid = _project(db)
    kid = _item(db, project_id=pid, state='CONFIRMED')
    out = _run(db, K.forget, selector={'project_id': pid})
    assert out['dry_run'] is True
    assert [(c['from'], c['to'], c['purge']) for c in out['changes']] == [
        ('CONFIRMED', 'RETRACTED', False)]
    assert out['changed'] is False
    assert _row(db, entities.KnowledgeItem, kid).state == 'CONFIRMED'
    assert _version(db, entities.KnowledgeItem, kid) == 1


@pytest.mark.parametrize('state', ['RETRACTED', 'SUPERSEDED', 'EXPIRED'])
def test_forget_retract_never_touches_a_row_that_has_already_ended(db, state):
    """knowledge.py:178-181 (`trigger = {...}.get(e.state)` then `if trigger is
    None and not purge: continue`): a dead row has no edge to take; retracted
    items are never retracted twice and superseded ones never resurrected."""
    pid = _project(db)
    kid = _item(db, project_id=pid, state=state)
    before = _n_events(db)
    out = _run(db, K.forget, selector={'project_id': pid}, dry_run=False)
    assert (out['changes'], out['changed']) == ([], False)
    assert _row(db, entities.KnowledgeItem, kid).state == state
    assert _version(db, entities.KnowledgeItem, kid) == 1
    assert _n_events(db) == before


def test_forget_purge_blanks_the_content_and_keeps_the_tombstone(db):
    """knowledge.py:189-197 (the `if purge:` block): the row survives with its
    provenance event, the content is gone, and the state moved by its edge —
    nothing is deleted and nothing is left readable."""
    pid = _project(db)
    rd = ids.new_id('route_decision')
    kid = _item(db, project_id=pid, state='CONFIRMED', text='the secret plan',
                anchors=('app/core.py',), constraint=CONSTRAINT, type_='ARCHITECTURE',
                route_decision_id=rd)
    out = _run(db, K.forget, selector={'ids': [kid]}, mode='purge', dry_run=False)
    assert out['changed'] is True and out['changes'][0]['purge'] is True
    e = _row(db, entities.KnowledgeItem, kid)
    assert (e.state, e.title, e.text, e.anchors, e.constraint, e.purged) == (
        'RETRACTED', '[purged]', '', (), None, True)
    purge = [x for x in _all_events(db, 'knowledge_item.purged')]
    assert [p['subject']['id'] for p in purge] == [kid]
    assert purge[0]['payload']['provenance'] == {'source_kind': 'user',
                                                 'route_decision_id': rd}


def test_forget_purge_of_an_already_purged_row_changes_nothing(db):
    """knowledge.py:179 (`purge = mode == 'purge' and not e.purged`): the second
    purge is not a second tombstone and not a second event."""
    pid = _project(db)
    kid = _item(db, project_id=pid, state='RETRACTED', purged=True, title='[purged]')
    before = _n_events(db)
    out = _run(db, K.forget, selector={'project_id': pid}, mode='purge', dry_run=False)
    assert (out['changes'], out['changed']) == ([], False)
    assert _version(db, entities.KnowledgeItem, kid) == 1
    assert _n_events(db) == before


def test_forget_purge_still_blanks_a_row_that_had_no_state_move_left(db):
    """knowledge.py:178-181 + 189-197: a RETRACTED, not yet purged row has no trigger but
    is still purged — the content is what the user asked gone."""
    pid = _project(db)
    kid = _item(db, project_id=pid, state='RETRACTED', text='still readable')
    out = _run(db, K.forget, selector={'project_id': pid}, mode='purge', dry_run=False)
    assert [(c['from'], c['to'], c['purge']) for c in out['changes']] == [
        ('RETRACTED', 'RETRACTED', True)]
    e = _row(db, entities.KnowledgeItem, kid)
    assert (e.state, e.text, e.purged) == ('RETRACTED', '', True)


@pytest.mark.parametrize('state, mode', [('CONFIRMED', 'retract'), ('CANDIDATE', 'retract'),
                                         ('CANDIDATE', 'purge')])
def test_forget_moves_a_live_row_by_its_own_edge(db, state, mode):
    """knowledge.py:178 (`trigger = {'CONFIRMED': 'retract', 'CANDIDATE':
    'reject'}`): a candidate is rejected, a confirmed item retracted; neither is
    ever taken to RETRACTED by the wrong edge, and the reason says which mode
    asked for it."""
    pid = _project(db)
    kid = _item(db, project_id=pid, state=state)
    out = _run(db, K.forget, selector={'project_id': pid}, mode=mode, dry_run=False)
    assert out['changed'] is True
    assert _row(db, entities.KnowledgeItem, kid).state == 'RETRACTED'
    moved = _all_events(db, 'knowledge_item.state_changed')
    assert [m['payload']['reason'] for m in moved] == ['forgotten (%s)' % mode]


def test_forget_on_an_empty_project_reports_no_change(db):
    """knowledge.py:161-165 on nothing at all: an empty selection is an answer,
    not an error, and `changed` stays False."""
    pid = _project(db)
    out = _run(db, K.forget, selector={'project_id': pid}, dry_run=False)
    assert out == {'dry_run': False, 'mode': 'retract', 'changes': [], 'changed': False}


def test_forget_by_source_id_only_reaches_what_came_from_that_source(db):
    """knowledge.py:162-164 (the `source_id` filter, applied after `where`): a
    sibling with no source at all is not collateral."""
    pid = _project(db)
    fb = ids.new_id('feedback')
    from_there = _item(db, project_id=pid, state='CONFIRMED', title='From there',
                       source_ref=Ref('feedback', fb))
    unprovenanced = _item(db, project_id=pid, state='CONFIRMED', title='No source',
                          source_kind=None)
    out = _run(db, K.forget, selector={'project_id': pid, 'source_id': fb}, dry_run=False)
    assert [c['id'] for c in out['changes']] == [from_there]
    assert _row(db, entities.KnowledgeItem, unprovenanced).state == 'CONFIRMED'


# ── 2. confirm: the one move that makes a model's word authoritative ──

@pytest.mark.parametrize('was', ['RETRACTED', 'SUPERSEDED', 'EXPIRED'])
def test_confirm_refuses_when_what_it_supersedes_has_already_ended(db, was):
    """knowledge.py:95 (`if old is not None and was not in ('CONFIRMED',
    'CANDIDATE')`): an item whose predecessor is already dead would otherwise
    confirm into a broken chain and move a dead row back into play."""
    pid = _project(db)
    old = _item(db, project_id=pid, state=was, title='Old')
    kid = _item(db, project_id=pid, title='New', supersedes_id=old)
    before = _n_events(db)
    with pytest.raises(ValueError, match='which is %s' % was):
        _run(db, K.confirm, knowledge_item_id=kid)
    assert _row(db, entities.KnowledgeItem, kid).state == 'CANDIDATE'
    assert _row(db, entities.KnowledgeItem, old).state == was
    assert _row(db, entities.KnowledgeItem, kid).superseded_by_id is None
    assert _n_events(db) == before


def test_confirm_of_an_item_superseding_a_confirmed_one_supersedes_it_in_the_same_move(db):
    """knowledge.py:100-110: one command, two rows, one answer naming which."""
    pid = _project(db)
    old = _item(db, project_id=pid, state='CONFIRMED', title='Old')
    kid = _item(db, project_id=pid, title='New', supersedes_id=old)
    out = _run(db, K.confirm, knowledge_item_id=kid)
    assert (out['superseded'], out['replaced']) == (old, None)
    assert out['changed'] is True
    assert _row(db, entities.KnowledgeItem, kid).state == 'CONFIRMED'
    gone = _row(db, entities.KnowledgeItem, old)
    assert (gone.state, gone.superseded_by_id, gone.valid_until) == (
        'SUPERSEDED', kid, out['knowledge_item']['updated_at'])


def test_confirm_of_an_item_replacing_a_candidate_rejects_it_and_keeps_the_chain(db):
    """knowledge.py:101-106 (the P7 D4 branch: `('reject', ... REPLACED ...)`) —
    a replaced-before-confirmed predecessor never becomes authoritative and is
    never SUPERSEDED, and the chain still names it."""
    pid = _project(db)
    old = _item(db, project_id=pid, state='CANDIDATE', title='Old')
    kid = _item(db, project_id=pid, title='New', supersedes_id=old)
    out = _run(db, K.confirm, knowledge_item_id=kid)
    assert (out['superseded'], out['replaced']) == (None, old)
    gone = _row(db, entities.KnowledgeItem, old)
    assert (gone.state, gone.superseded_by_id) == ('RETRACTED', kid)
    assert gone.valid_until is not None
    assert _row(db, entities.KnowledgeItem, kid).supersedes_id == old
    reasons = [e['payload']['reason'] for e in _all_events(db, 'knowledge_item.state_changed')]
    assert any(K.REPLACED in r for r in reasons)


def test_confirm_is_taken_once_and_a_second_confirm_is_refused(db):
    """knowledge.py:97-98 through lifecycle.fire: CONFIRMED has no `confirm` edge,
    so a replayed confirm cannot bump the row or write a second event."""
    _project(db)
    kid = _item(db, state='CANDIDATE')
    assert _run(db, K.confirm, knowledge_item_id=kid)['changed'] is True
    before = _n_events(db)
    with pytest.raises(IllegalTrigger):
        _run(db, K.confirm, knowledge_item_id=kid)
    assert _version(db, entities.KnowledgeItem, kid) == 2
    assert _n_events(db) == before


def test_confirm_with_a_version_the_caller_did_not_see_changes_nothing(db):
    """knowledge.py:105 (`expected_version` through lifecycle.fire): a confirm
    built on a stale read is refused, the row keeps its version."""
    _project(db)
    kid = _item(db, state='CANDIDATE')
    with pytest.raises(VersionConflict):
        _run(db, K.confirm, knowledge_item_id=kid, expected_version=99)
    assert _row(db, entities.KnowledgeItem, kid).state == 'CANDIDATE'
    assert _version(db, entities.KnowledgeItem, kid) == 1


def test_confirm_of_an_item_that_does_not_exist_is_a_not_found(db):
    """knowledge.py:79 (`_load`): the id the caller invented is not silently
    confirmed into existence."""
    with pytest.raises(NotFound):
        _run(db, K.confirm, knowledge_item_id=ids.new_id('knowledge_item'))


@pytest.mark.parametrize('state, trigger', [('CANDIDATE', 'retract'),
                                            ('CONFIRMED', 'reject')])
def test_reject_and_retract_take_their_own_edge_only(db, state, trigger):
    """knowledge.py:118-130 (reject/retract through the table): a candidate is
    never "retracted" and a confirmed item never "rejected" — the two reasons
    are different facts in the audit trail."""
    _project(db)
    kid = _item(db, state=state)
    cmd = K.retract if trigger == 'retract' else K.reject
    before = _n_events(db)
    with pytest.raises(IllegalTrigger):
        _run(db, cmd, knowledge_item_id=kid)
    assert _row(db, entities.KnowledgeItem, kid).state == state
    assert _n_events(db) == before


def test_retract_of_a_confirmed_item_keeps_the_row(db):
    """knowledge.py:120-124: nothing is deleted; the row stays and reads back."""
    _project(db)
    kid = _item(db, state='CONFIRMED', text='kept')
    out = _run(db, K.retract, knowledge_item_id=kid)
    assert out['changed'] is True and out['knowledge_item']['state'] == 'RETRACTED'
    assert _row(db, entities.KnowledgeItem, kid).text == 'kept'


@pytest.mark.parametrize('state', ['CANDIDATE', 'RETRACTED', 'SUPERSEDED'])
def test_only_a_confirmed_item_can_be_superseded(db, state):
    """knowledge.py:133 (`if old.state != 'CONFIRMED'`): superseding what
    was never authoritative would rewrite history that never was."""
    _project(db)
    kid = _item(db, state=state)
    before = _n_events(db)
    with pytest.raises(ValueError, match='only a CONFIRMED item can be superseded'):
        _run(db, K.supersede, knowledge_item_id=kid, title='The replacement')
    assert _version(db, entities.KnowledgeItem, kid) == 1
    assert _all(db, entities.KnowledgeItem) == [_row(db, entities.KnowledgeItem, kid)]
    assert _n_events(db) == before


def test_supersede_writes_the_replacement_and_keeps_the_old_as_history(db):
    """knowledge.py:136-142: the new item is origin explicit (so it confirms
    itself), same type and scope, linked `supersedes`, and the old one is
    SUPERSEDED — two rows, no delete."""
    pid = _project(db)
    old = _item(db, project_id=pid, state='CONFIRMED', title='Old', type_='DECISION',
                anchors=('app/api.py',), text='body')
    out = _run(db, K.supersede, knowledge_item_id=old, title='New', text='newer')
    new = out['knowledge_item']
    assert (new['state'], new['origin'], new['supersedes_id'], new['project_id'],
            new['type'], new['anchors']) == ('CONFIRMED', 'explicit', old, pid, 'DECISION',
                                             ['app/api.py'])
    assert new['source_kind'] == 'user' and new['source_ref'] == {'kind': 'knowledge_item',
                                                                  'id': old}
    assert _row(db, entities.KnowledgeItem, old).state == 'SUPERSEDED'
    assert len(_all(db, entities.KnowledgeItem)) == 2
    links = [r for r in _all(db, entities.Relation) if r.rel == 'supersedes']
    assert [(l.src_id, l.dst_id, l.confidence_tier) for l in links] == [(new['id'], old,
                                                                         'EXTRACTED')]
    # and the chain cannot be rewritten from its dead end
    with pytest.raises(ValueError, match='only a CONFIRMED item'):
        _run(db, K.supersede, knowledge_item_id=old, title='Again')


def test_supersede_of_an_item_that_does_not_exist_is_a_not_found(db):
    """knowledge.py:133 (`_load` before the state check)."""
    with pytest.raises(NotFound):
        _run(db, K.supersede, knowledge_item_id=ids.new_id('knowledge_item'), title='x')


# ── 3. feedback: history, and the only explicit step that proposes knowledge ──

@pytest.mark.parametrize('kind', ['artifact', 'project', 'account', 'task', 'execution',
                                  'repository', 'relation', 'MEETING'])
def test_feedback_about_anything_but_the_five_subjects_is_refused(db, kind):
    """knowledge.py:212 (`if subject.kind not in FEEDBACK_SUBJECTS`): the
    closed vocabulary is what keeps feedback from pointing at Core's own
    objects; the whole transaction is refused, so no half-written history."""
    before = _n_events(db)
    with pytest.raises(ValueError, match='feedback is about one of'):
        _run(db, K.record_feedback, subject={'kind': kind, 'id': ids.new_id('mission')},
             signal='negative')
    assert _all(db, entities.Feedback) == []
    assert _n_events(db) == before


@pytest.mark.parametrize('subject', [{'kind': '', 'id': 'x'}, {'kind': 'mission', 'id': ''}])
def test_feedback_about_an_unnamed_subject_is_refused_by_the_value_type(db, subject):
    """knowledge.py:211 (`subject = Ref(**subject)`) with values.py
    `Ref.__post_init__`: a subject whose kind or id is not a non-empty string is
    refused before the vocabulary is consulted, and writes no row."""
    before = _n_events(db)
    with pytest.raises(ValueError, match='Ref needs a non-empty kind and id'):
        _run(db, K.record_feedback, subject=subject, signal='negative')
    assert _all(db, entities.Feedback) == []
    assert _n_events(db) == before


@pytest.mark.parametrize('subject', [{'kind': 'mission'}, {'id': 'x'}, {}])
def test_a_subject_that_is_not_even_a_pair_writes_nothing(db, subject):
    """knowledge.py:211 (`subject = Ref(**subject)`): a body missing `kind` or
    `id` never reaches the vocabulary. It leaves the command as a TypeError (a
    missing keyword argument) rather than the ValueError the other refusals
    give — recorded here as it is, because what the branch must guarantee is
    that nothing is written, and nothing is."""
    before = _n_events(db)
    with pytest.raises((TypeError, ValueError)):
        _run(db, K.record_feedback, subject=subject, signal='negative')
    assert _all(db, entities.Feedback) == []
    assert _n_events(db) == before


def test_feedback_about_a_mission_that_is_not_there_is_a_not_found(db):
    """knowledge.py:216 (`m = lifecycle.load(tx, entities.Mission, subject.id).entity`): the
    subject must exist; its scope is taken from it, never invented."""
    with pytest.raises(NotFound):
        _run(db, K.record_feedback, subject={'kind': 'mission', 'id': ids.new_id('mission')},
             signal='positive')
    assert _all(db, entities.Feedback) == []


def test_feedback_about_a_knowledge_item_takes_that_items_scope(db):
    """knowledge.py:218-220: the item's workspace and project, so a later forget
    by project finds it."""
    pid = _project(db)
    kid = _item(db, project_id=pid, state='CONFIRMED')
    out = _run(db, K.record_feedback, subject={'kind': 'knowledge_item', 'id': kid},
               signal='correction', text='wrong')
    fb = _row(db, entities.Feedback, out['feedback_id'])
    assert (fb.project_id, fb.workspace_id, fb.principal_id, fb.signal) == (
        pid, ids.GLOBAL_WORKSPACE, USER.id, 'correction')
    assert out['promoted'] is None


def test_feedback_about_a_mission_takes_the_missions_scope(db):
    """knowledge.py:215-217: scope from the mission (not the caller's), and the
    global fallback only for a subject that has none."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    out = _run(db, K.record_feedback, subject={'kind': 'mission', 'id': mid},
               signal='positive')
    fb = _row(db, entities.Feedback, out['feedback_id'])
    assert (fb.project_id, fb.workspace_id) == (pid, ids.GLOBAL_WORKSPACE)
    plain = _run(db, K.record_feedback,
                 subject={'kind': 'message', 'id': ids.new_id('message')},
                 signal='negative')
    assert _row(db, entities.Feedback, plain['feedback_id']).project_id is None


@pytest.mark.parametrize('type_', ['FACT', 'ENTITY', 'ARCHITECTURE', 'DECISION', None, ''])
def test_feedback_may_only_promote_a_preference_or_a_lesson(db, type_):
    """knowledge.py:226 (`if promote.get('type') not in PROMOTABLE`): a
    promote that is not a PREFERENCE/LESSON is refused before anything is
    written — neither the Feedback row nor a knowledge item appears."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    before = _n_events(db)
    with pytest.raises(ValueError, match='promotes into one of'):
        _run(db, K.record_feedback, subject={'kind': 'mission', 'id': mid},
             signal='negative', promote={'type': type_, 'title': 'Always the seam'})
    assert _all(db, entities.Feedback) == []
    assert _all(db, entities.KnowledgeItem) == []
    assert _n_events(db) == before


@pytest.mark.parametrize('state', ['RETRACTED', 'SUPERSEDED', 'EXPIRED'])
def test_nothing_may_be_promoted_onto_an_item_that_is_no_longer_live(db, state):
    """knowledge.py:229 (`_load(tx, sup).entity.state not in ('CONFIRMED',
    'CANDIDATE')`): a promotion onto a dead row would give a dead claim a
    successor and a second event."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    dead = _item(db, project_id=pid, state=state, title='Dead')
    before = _n_events(db)
    with pytest.raises(ValueError, match='no longer live'):
        _run(db, K.record_feedback, subject={'kind': 'mission', 'id': mid},
             signal='negative',
             promote={'type': 'LESSON', 'title': 'New', 'supersedes_id': dead})
    assert _all(db, entities.Feedback) == [] and _all(db, entities.KnowledgeItem) == [
        _row(db, entities.KnowledgeItem, dead)]
    assert _n_events(db) == before


@pytest.mark.parametrize('state', ['CONFIRMED', 'CANDIDATE'])
def test_promoting_feedback_proposes_a_candidate_and_changes_nothing_else(db, state):
    """knowledge.py:231-242: the promoted item is a CANDIDATE of origin explicit
    citing the feedback row, linked `supersedes`, and neither item moves —
    feedback never auto-confirms (§3)."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    old = _item(db, project_id=pid, state=state, title='Old')
    out = _run(db, K.record_feedback, subject={'kind': 'mission', 'id': mid},
               signal='correction', text='no, the seam',
               promote={'type': 'PREFERENCE', 'title': 'Use the seam', 'text': 'why',
                        'supersedes_id': old})
    new = _row(db, entities.KnowledgeItem, out['promoted']['id'])
    assert (new.state, new.type, new.origin, new.supersedes_id, new.project_id,
            new.source_kind) == ('CANDIDATE', 'PREFERENCE', 'explicit', old, pid, 'user')
    assert (new.source_ref.kind, new.source_ref.id) == ('feedback', out['feedback_id'])
    assert _row(db, entities.Feedback, out['feedback_id']).promoted_knowledge_id == new.id
    assert _row(db, entities.KnowledgeItem, old).state == state
    links = [r for r in _all(db, entities.Relation) if r.rel == 'supersedes']
    assert [(l.src_id, l.dst_id, l.confidence_tier) for l in links] == [(new.id, old,
                                                                         'EXTRACTED')]
    assert out['promoted']['state'] == 'CANDIDATE'


def test_promoting_feedback_without_naming_a_predecessor_still_links_nothing(db):
    """knowledge.py:238-241 (`if sup is not None:` guards the relate): a plain
    promotion is one CANDIDATE and a Feedback row, with no relation at all."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    out = _run(db, K.record_feedback, subject={'kind': 'mission', 'id': mid},
               signal='positive', promote={'type': 'LESSON', 'title': 'A lesson'})
    assert _all(db, entities.Relation) == []
    assert _row(db, entities.KnowledgeItem, out['promoted']['id']).supersedes_id is None


# ── 4. meeting import: idempotent, undated is asked for, hostile date refused ──

@pytest.mark.parametrize('held_at', ['2026-09-20T24:00', '', '   ', '2026-09-20 09:00:61',
                                     '2026-02-30', '2026-09-20T09:60:00'])
def test_a_meeting_is_never_dated_with_a_moment_the_context_cannot_read(db, held_at):
    """knowledge.py:262-266 (the `datetime.fromisoformat` guard): a date the
    context cannot read is refused, and no Meeting and no Artifact row is left
    behind by the failed import."""
    before = _n_events(db)
    with pytest.raises(ValueError, match='held_at is an ISO date'):
        _run(db, K.import_meeting, name='kickoff', held_at=held_at, notes_sha256=SHA,
             notes_size=3, imported_from='n.md')
    assert _all(db, entities.Meeting) == []
    assert _all(db, entities.Artifact) == []
    assert _n_events(db) == before


def test_importing_notes_that_carry_no_date_asks_for_the_date(db):
    """knowledge.py:283-285 (`if held_at is None:` `ask_meeting_date(tx, ...)` in the same transaction): the meeting
    is undated and the user is asked, in the same transaction."""
    out = _run(db, K.import_meeting, name='kickoff', held_at=None, notes_sha256=SHA,
               notes_size=3, imported_from='n.md')
    assert out['meeting']['held_at'] is None and out['changed'] is True
    asked = [m for m in _all(db, entities.Message) if m.author == 'archeus']
    assert len(asked) == 1 and 'When was it' in asked[0].text
    assert [c['type'] for c in asked[0].cards] == ['clarification']
    assert asked[0].cards[0]['ref'] == {'kind': 'meeting', 'id': out['meeting']['id']}


def test_importing_the_same_notes_into_the_same_scope_again_changes_nothing(db):
    """knowledge.py:270-271 (the `r.entity.notes_artifact_id == notes_sha256` scan): the
    replay returns the meeting that is there, with no second row and no second
    event."""
    first = _run(db, K.import_meeting, name='kickoff', held_at='2026-09-20',
                 notes_sha256=SHA, notes_size=3, imported_from='n.md')
    head = _n_events(db)
    again = _run(db, K.import_meeting, name='kickoff renamed', held_at='2026-09-21',
                 notes_sha256=SHA, notes_size=3, imported_from='elsewhere.md')
    assert (again['changed'], again['meeting']['id']) == (False, first['meeting']['id'])
    assert again['meeting']['name'] == 'kickoff'
    assert len(_all(db, entities.Meeting)) == 1 and len(_all(db, entities.Artifact)) == 1
    assert _n_events(db) == head


def test_the_same_notes_imported_into_another_project_are_another_meeting(db):
    """knowledge.py:271 (`r.entity.project_id == project_id and r.entity.notes_artifact_id == notes_sha256`): the scope
    is half the identity, so a global import does not swallow a project's."""
    one = _run(db, K.import_meeting, name='global', held_at='2026-09-20', notes_sha256=SHA,
               notes_size=3, imported_from='n.md')
    pid = _project(db)
    two = _run(db, K.import_meeting, name='project', held_at='2026-09-20', notes_sha256=SHA,
               notes_size=3, imported_from='n.md', project_id=pid)
    assert (one['meeting']['project_id'], two['meeting']['project_id']) == (None, pid)
    assert two['meeting']['id'] != one['meeting']['id']
    assert two['changed'] is True


def test_importing_notes_writes_the_artifact_row_once(db):
    """knowledge.py:273-275 (`if tx.get(entities.Artifact, notes_sha256) is
    None`): the second import of the same bytes neither rewrites nor doubles it,
    and different bytes get their own."""
    _run(db, K.import_meeting, name='a', held_at='2026-09-20', notes_sha256=SHA,
         notes_size=3, imported_from='n.md')
    _run(db, K.import_meeting, name='a', held_at='2026-09-20', notes_sha256=SHA,
         notes_size=99, imported_from='n.md')
    _run(db, K.import_meeting, name='b', held_at='2026-09-20', notes_sha256=SHA2,
         notes_size=5, imported_from='m.md')
    arts = {a.id: a.size for a in _all(db, entities.Artifact)}
    assert sorted(arts) == [SHA, SHA2] and arts[SHA] == 3


def test_importing_into_a_project_that_does_not_exist_writes_nothing(db):
    """knowledge.py:269 (`workspace = lifecycle.load(tx, entities.Project, project_id).entity.workspace_id`):
    an unknown scope is a NotFound, not a meeting with a dangling project."""
    before = _n_events(db)
    with pytest.raises(NotFound):
        _run(db, K.import_meeting, name='kickoff', held_at='2026-09-20', notes_sha256=SHA,
             notes_size=3, imported_from='n.md', project_id=ids.new_id('project'))
    assert _all(db, entities.Meeting) == [] and _all(db, entities.Artifact) == []
    assert _n_events(db) == before


def test_a_date_that_is_not_a_string_is_refused_the_same_way(db):
    """knowledge.py:264-266: `held_at.replace` is only a string's method; the
    guard's own contract ("held_at is an ISO date or time") says ValueError."""
    with pytest.raises(ValueError, match='held_at is an ISO date'):
        _run(db, K.import_meeting, name='kickoff', held_at=20260101, notes_sha256=SHA,
             notes_size=3, imported_from='n.md')
    assert _all(db, entities.Meeting) == []


# ── 5. what a call produced: never confirmed, never duplicated, never a lie ──

def test_a_knowledge_pass_with_nothing_in_it_still_ends_the_call(db, ends):
    """knowledge.py:342 (`_end` after the loops) with an empty result: the call
    is ended once with zero counts — a pass that recorded nothing may not leave
    a RouteDecision with no outcome."""
    pid = _project(db)
    out = _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
               workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'),
               result={'entities': []})
    assert out == {'items': 0, 'duplicates': 0, 'relations': 0, 'dropped': 0}
    assert len(ends) == 1 and ends[0]['outcome']['items'] == 0
    assert ends[0]['usage'] is None
    assert _all(db, entities.KnowledgeItem) == []


def test_the_end_of_a_knowledge_pass_carries_the_calls_own_figures(db, monkeypatch):
    """knowledge.py:291-295 (`_end`: `attempts`, `account_ref`, `**counts`): the
    outcome the RouteDecision keeps is the call's own figures plus this pass's
    counts, and the usage is ledgered from them."""
    monkeypatch.setattr(K.C, 'end_call', REAL_END_CALL)
    pid = _project(db)
    rd = _route_decision(db)
    out = _run(db, K.record_knowledge_pass,
               called=called(rd_id=rd, usage={'tokens_in': 120, 'tokens_out': 40}),
               project_id=pid, workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'), result=_result())
    assert (out['items'], out['relations']) == (2, 1)
    e = _row(db, entities.RouteDecision, rd)
    assert e.outcome == {'state': 'ok', 'attempts': 1, 'account_ref': 'fake:pi',
                         'items': 2, 'duplicates': 0, 'relations': 1, 'dropped': 0}
    ledger = [u for u in _all(db, entities.UsageLedger) if u.route_decision_id == rd]
    assert [(u.basis, u.tokens_in, u.tokens_out) for u in ledger] == [('reported_total', 120,
                                                                       40)]


def test_an_entity_already_live_under_the_same_name_is_not_written_twice(db, ends):
    """knowledge.py:315-318 (`live = _live(...)` then `if live is not None`):
    identity is the casefolded, whitespace-collapsed title, and a live item is
    counted as a duplicate rather than duplicated."""
    pid = _project(db)
    live = _item(db, project_id=pid, type_='ENTITY', title='  Core ', state='CONFIRMED')
    out = _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
               workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'),
               result={'entities': [{'name': 'core', 'summary': 'again'}]})
    assert (out['items'], out['duplicates']) == (0, 1)
    items = _all(db, entities.KnowledgeItem)
    assert [i.id for i in items] == [live] and ends[0]['outcome']['duplicates'] == 1


@pytest.mark.parametrize('state', ['RETRACTED', 'SUPERSEDED', 'EXPIRED'])
def test_a_dead_item_under_the_same_name_does_not_hide_a_new_one(db, state):
    """knowledge.py:42-45 (`e.state in ('CANDIDATE', 'CONFIRMED')` in `_live`):
    a retracted claim is not the reason the same claim is never recorded again,
    and the new one is a fresh CANDIDATE with its own provenance."""
    pid = _project(db)
    dead = _item(db, project_id=pid, type_='ENTITY', title='core', state=state)
    out = _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
               workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'),
               result={'entities': [{'name': 'core'}]})
    assert (out['items'], out['duplicates']) == (1, 0)
    fresh = [i for i in _all(db, entities.KnowledgeItem) if i.id != dead]
    assert len(fresh) == 1 and (fresh[0].state, fresh[0].type) == ('CANDIDATE', 'ENTITY')


def test_an_item_of_the_same_name_in_another_project_is_its_own_item(db):
    """knowledge.py:41-45 (the project and workspace comparison in `_live`): the
    scope is half the identity, so a project never inherits another's claims."""
    p1, p2 = _project(db, 'one'), _project(db, 'two')
    _item(db, project_id=p1, type_='ENTITY', title='core', state='CONFIRMED')
    out = _run(db, K.record_knowledge_pass, called=called(), project_id=p2,
               workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'),
               result={'entities': [{'name': 'core'}]})
    assert (out['items'], out['duplicates']) == (1, 0)
    assert {i.project_id for i in _all(db, entities.KnowledgeItem)} == {p1, p2}


def test_an_item_of_the_same_name_in_another_workspace_is_its_own_item(db):
    """knowledge.py:43 (`and e.workspace_id == workspace_id` in `_live`): the
    workspace is the other half of the scope, so an item of another workspace is
    not the reason this workspace's claim is "already known"."""
    pid = _project(db)
    elsewhere = ids.new_id('workspace')
    _item(db, project_id=pid, type_='ENTITY', title='core', state='CONFIRMED',
          workspace_id=elsewhere)
    out = _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
               workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'),
               result={'entities': [{'name': 'core'}]})
    assert (out['items'], out['duplicates']) == (1, 0)
    assert {i.workspace_id for i in _all(db, entities.KnowledgeItem)} == {
        ids.GLOBAL_WORKSPACE, elsewhere}


def test_a_relation_with_an_end_the_result_never_named_is_dropped_and_counted(db, ends):
    """knowledge.py:326 (`if a is None or b is None or a == b`): a dangling
    end is the partial answer the contract permits, so it is dropped and counted
    rather than written as a claim about nothing."""
    pid = _project(db)
    out = _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
               workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'),
               result={'entities': [{'name': 'core'}],
                       'relations': [{'from': 'core', 'rel': 'depends_on', 'to': 'nobody'},
                                     {'from': 'nobody', 'rel': 'uses', 'to': 'core'},
                                     {'from': 'core', 'rel': 'uses', 'to': 'Core'}]})
    assert (out['items'], out['relations'], out['dropped']) == (1, 0, 3)
    assert _all(db, entities.Relation) == []
    assert ends[0]['outcome']['dropped'] == 3


def test_a_relation_the_pass_already_wrote_is_not_written_again(db):
    """knowledge.py:63-65 (`relate` returning `(id, False)` for the identical
    live relation): a replayed pass leaves one relation, not two."""
    pid = _project(db)
    args = dict(called=called(), project_id=pid, workspace_id=ids.GLOBAL_WORKSPACE,
                inspection_id=ids.new_id('repository_inspection'), result=_result())
    first = _run(db, K.record_knowledge_pass, **args)
    again = _run(db, K.record_knowledge_pass, **dict(args, called=called()))
    assert (first['relations'], again['relations']) == (1, 0)
    assert (again['items'], again['duplicates']) == (0, 2)
    assert len(_all(db, entities.Relation)) == 1


def test_a_relation_that_already_expired_is_not_taken_as_the_same_one(db):
    """knowledge.py:64 (`and r.entity.valid_until is None`): a superseded
    relation is history; treating it as the live one would silently drop the
    fact that is true now."""
    pid = _project(db)
    a = _item(db, project_id=pid, type_='ENTITY', title='api', state='CONFIRMED')
    b = _item(db, project_id=pid, type_='ENTITY', title='core', state='CONFIRMED')
    _relation(db, a, b, rel='depends_on', valid_until='2026-01-01T00:00:00+00:00')
    out = _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
               workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'),
               result={'entities': [{'name': 'api'}, {'name': 'core'}],
                       'relations': [{'from': 'api', 'rel': 'depends_on',
                                      'to': 'core'}]})
    assert (out['items'], out['duplicates'], out['relations'], out['dropped']) == (
        0, 2, 1, 0)
    links = [r for r in _all(db, entities.Relation) if r.rel == 'depends_on']
    assert len(links) == 2 and sum(1 for r in links if r.valid_until is None) == 1


def test_a_contradiction_is_drawn_only_towards_an_item_the_call_was_shown(db):
    """knowledge.py:335 (`if a is None or c['existing'] not in known_items`):
    the model may not claim a contradiction with a claim it never saw — that is
    how a hallucinated conflict would enter the graph."""
    pid = _project(db)
    existing = _item(db, project_id=pid, state='CONFIRMED', title='Core is standalone')
    out = _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
               workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'),
               result={'entities': [{'name': 'core'}],
                       'contradicts': [{'entity': 'core', 'existing': existing}]})
    assert (out['relations'], out['dropped']) == (0, 1)
    assert [r for r in _all(db, entities.Relation) if r.rel == 'contradicts'] == []


def test_a_contradiction_towards_a_shown_item_is_recorded_as_inferred(db):
    """knowledge.py:335-341: the same call, this time naming an item it was
    given, records it as INFERRED evidence — never as a supersession."""
    pid = _project(db)
    existing = _item(db, project_id=pid, state='CONFIRMED', title='Core is standalone')
    out = _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
               workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'),
               result={'entities': [{'name': 'core'}],
                       'contradicts': [{'entity': 'Core', 'existing': existing}]},
               known_items=(existing,))
    assert (out['relations'], out['dropped']) == (1, 0)
    link = [r for r in _all(db, entities.Relation) if r.rel == 'contradicts'][0]
    assert (link.confidence_tier, link.dst_id, link.source_kind) == (
        'INFERRED', existing, 'inspection')


def test_a_contradiction_about_an_entity_the_result_never_named_is_dropped(db):
    """knowledge.py:334-335 (`a is None`): a contradiction from a name that is
    not in this result cites nothing."""
    pid = _project(db)
    existing = _item(db, project_id=pid, state='CONFIRMED', title='Core is standalone')
    out = _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
               workspace_id=ids.GLOBAL_WORKSPACE,
               inspection_id=ids.new_id('repository_inspection'),
               result={'entities': [{'name': 'api'}],
                       'contradicts': [{'entity': 'ghost', 'existing': existing}]},
               known_items=(existing,))
    assert (out['relations'], out['dropped']) == (0, 1)
    assert _all(db, entities.Relation) == []


def test_a_model_that_names_a_relation_the_vocabulary_does_not_have_is_refused(db):
    """knowledge.py:329 (`relate` builds an entity, whose `_CHOICES` rejects the
    rel): the closed vocabulary is enforced at the write, and the whole pass is
    refused rather than stored as `relates_to`."""
    pid = _project(db)
    before = _n_events(db)
    with pytest.raises(ValueError, match='must be one of'):
        _run(db, K.record_knowledge_pass, called=called(), project_id=pid,
             workspace_id=ids.GLOBAL_WORKSPACE,
             inspection_id=ids.new_id('repository_inspection'),
             result={'entities': [{'name': 'api'}, {'name': 'core'}],
                     'relations': [{'from': 'api', 'rel': 'eats', 'to': 'core'}]})
    assert _all(db, entities.KnowledgeItem) == [] and _all(db, entities.Relation) == []
    assert _n_events(db) == before


def test_a_knowledge_pass_never_confirms_what_the_model_said(db, ends):
    """knowledge.py:319-322 (`new_item` with `_provenance(... 'inferred')`):
    every item a call produced is INFERRED origin, CANDIDATE state, and cites
    the inspection, the RouteDecision and the ContextPackage it was given."""
    pid = _project(db)
    rd, insp = ids.new_id('route_decision'), ids.new_id('repository_inspection')
    c = called(rd_id=rd)
    _run(db, K.record_knowledge_pass, called=c, project_id=pid,
         workspace_id=ids.GLOBAL_WORKSPACE, inspection_id=insp, result=_result())
    items = _all(db, entities.KnowledgeItem)
    assert [i.state for i in items] == ['CANDIDATE', 'CANDIDATE']
    assert [(i.origin, i.source_kind, i.route_decision_id, i.context_package_id)
            for i in items] == [('inferred', 'inspection', rd, c['context_package_id'])] * 2
    assert [(i.source_ref.kind, i.source_ref.id) for i in items] == [
        ('repository_inspection', insp)] * 2
    assert all(i.observed_at is not None for i in items)


# ── 6. decisions from a meeting: never auto-confirmed, deduped per meeting ──

def test_the_same_statement_twice_is_one_decision(db, ends):
    """knowledge.py:354-357 (`source_ref={'kind': 'meeting', 'id': meeting_id}) is not None`):
    the same claim from the same notes is a duplicate, not a second DECISION."""
    pid = _project(db)
    mid = _meeting(db, project_id=pid)
    out = _run(db, K.record_decisions, called=called(), meeting_id=mid,
               result={'decisions': [{'statement': 'We use SQLite'},
                                     {'statement': 'we   use  sqlite'}]})
    assert (out['items'], out['duplicates']) == (1, 1)
    items = _all(db, entities.KnowledgeItem)
    assert [i.title for i in items] == ['We use SQLite']
    assert (items[0].state, items[0].type, items[0].origin, items[0].project_id) == (
        'CANDIDATE', 'DECISION', 'inferred', pid)
    assert ends[0]['outcome'] == {'state': 'ok', 'attempts': 1, 'account_ref': 'fake:pi',
                                 'items': 1, 'duplicates': 1}


def test_the_same_statement_from_another_meeting_is_its_own_decision(db):
    """knowledge.py:45 + 354-356 (`source_ref is None or e.source_ref == Ref(**source_ref)`): two meetings that decided the same words are two facts with two
    provenances; the meeting link is EXTRACTED."""
    pid = _project(db)
    m1, m2 = _meeting(db, project_id=pid, held_at='2026-09-20'), _meeting(db, project_id=pid,
                                                                          held_at='2026-10-02')
    _run(db, K.record_decisions, called=called(), meeting_id=m1,
         result={'decisions': [{'statement': 'SQLite'}]})
    out = _run(db, K.record_decisions, called=called(), meeting_id=m2,
               result={'decisions': [{'statement': 'SQLite'}]})
    assert (out['items'], out['duplicates']) == (1, 0)
    assert len(_all(db, entities.KnowledgeItem)) == 2
    links = [(r.rel, r.dst_kind, r.dst_id, r.confidence_tier) for r in _all(db, entities.Relation)]
    assert links == [('decided_in', 'meeting', m1, 'EXTRACTED'),
                     ('decided_in', 'meeting', m2, 'EXTRACTED')]


def test_a_blank_statement_is_refused_and_leaves_no_decision(db):
    """knowledge.py:358-360 (`type='DECISION', title=d['statement'].strip()` → KnowledgeItem's `_TEXT` title): notes
    that yielded an empty claim record nothing at all."""
    pid = _project(db)
    mid = _meeting(db, project_id=pid)
    before = _n_events(db)
    with pytest.raises(ValueError, match='must be a non-empty string'):
        _run(db, K.record_decisions, called=called(), meeting_id=mid,
             result={'decisions': [{'statement': '   '}]})
    assert _all(db, entities.KnowledgeItem) == [] and _all(db, entities.Relation) == []
    assert _n_events(db) == before


def test_decisions_written_into_a_meeting_that_is_not_there_are_refused(db):
    """knowledge.py:349 (`m = lifecycle.load(tx, entities.Meeting, meeting_id).entity`): no
    meeting, no DECISION, and no invented scope."""
    with pytest.raises(NotFound):
        _run(db, K.record_decisions, called=called(), meeting_id=ids.new_id('meeting'),
             result={'decisions': [{'statement': 'SQLite'}]})
    assert _all(db, entities.KnowledgeItem) == []


def test_a_meeting_that_yielded_nothing_still_ends_its_call(db, ends):
    """knowledge.py:365 (`_end` after an empty loop)."""
    pid = _project(db)
    mid = _meeting(db, project_id=pid)
    out = _run(db, K.record_decisions, called=called(), meeting_id=mid,
               result={'decisions': []})
    assert out == {'items': 0, 'duplicates': 0} and len(ends) == 1


# ── 7. lessons: corroboration by DISTINCT missions is the only self-confirm ──

def test_a_lesson_the_model_got_from_one_mission_stays_a_candidate(db, ends):
    """knowledge.py:381-385 + 395-400: CORROBORATION is 2, so one mission never
    confirms anything, however the model scored its own confidence."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    out = _run(db, K.record_lessons, called=called(), mission_id=mid,
               result={'lessons': [{'title': 'Test the seam', 'text': 'it breaks'}]})
    assert (out['items'], out['corroborated'], out['confirmed']) == (1, 0, 0)
    item = _all(db, entities.KnowledgeItem)[0]
    assert (item.state, item.type, item.origin, item.project_id) == (
        'CANDIDATE', 'LESSON', 'inferred', pid)
    assert ends[0]['outcome']['confirmed'] == 0


def test_the_same_mission_never_corroborates_a_lesson_twice(db):
    """knowledge.py:393-396: the count is over the set of `learned_from`
    destinations, so a repeated pass of one mission is not corroboration."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    _run(db, K.record_lessons, called=called(), mission_id=mid,
         result={'lessons': [{'title': 'Test the seam'}]})
    out = _run(db, K.record_lessons, called=called(), mission_id=mid,
               result={'lessons': [{'title': 'TEST the  SEAM'}]})
    assert (out['items'], out['corroborated'], out['confirmed']) == (0, 0, 0)
    items = _all(db, entities.KnowledgeItem)
    assert len(items) == 1 and items[0].state == 'CANDIDATE'
    assert len([r for r in _all(db, entities.Relation) if r.rel == 'learned_from']) == 1


def test_a_lesson_seen_in_two_missions_confirms_itself_once(db):
    """knowledge.py:395-396 (`len(missions) >= CORROBORATION` and the
    `state == 'CANDIDATE'` read-back): two distinct missions are the whole of the second's
    authority, and the reason names them."""
    pid = _project(db)
    m1, m2 = _mission(db, project_id=pid), _mission(db, project_id=pid)
    first = _run(db, K.record_lessons, called=called(), mission_id=m1,
                 result={'lessons': [{'title': 'Test the seam'}]})
    kid = _all(db, entities.KnowledgeItem)[0].id
    out = _run(db, K.record_lessons, called=called(), mission_id=m2,
               result={'lessons': [{'title': 'Test the seam'}]})
    assert (first['items'], out['items'], out['corroborated'], out['confirmed']) == (
        1, 0, 1, 1)
    assert _row(db, entities.KnowledgeItem, kid).state == 'CONFIRMED'
    moved = [e for e in _all_events(db, 'knowledge_item.state_changed')
             if e['subject']['id'] == kid]
    assert [(m['payload']['to'], m['payload']['reason']) for m in moved] == [
        ('CONFIRMED', 'corroborated by 2 missions: %s' % ', '.join(sorted([m1, m2])))]


def test_a_third_mission_does_not_confirm_the_lesson_again(db):
    """knowledge.py:396 (`and tx.get(entities.KnowledgeItem, lid).entity.state == 'CANDIDATE')`): a lesson
    that is already CONFIRMED is corroborated by the third mission but never
    fired again — no second state_changed, no version bump."""
    pid = _project(db)
    m1, m2, m3 = (_mission(db, project_id=pid) for _ in range(3))
    _run(db, K.record_lessons, called=called(), mission_id=m1,
         result={'lessons': [{'title': 'Test the seam'}]})
    kid = _all(db, entities.KnowledgeItem)[0].id
    _run(db, K.record_lessons, called=called(), mission_id=m2,
         result={'lessons': [{'title': 'Test the seam'}]})
    version = _version(db, entities.KnowledgeItem, kid)
    out = _run(db, K.record_lessons, called=called(), mission_id=m3,
               result={'lessons': [{'title': 'Test the seam'}]})
    assert (out['items'], out['corroborated'], out['confirmed']) == (0, 1, 0)
    assert _version(db, entities.KnowledgeItem, kid) == version
    assert _row(db, entities.KnowledgeItem, kid).state == 'CONFIRMED'


def test_a_lesson_of_another_project_is_its_own_lesson(db):
    """knowledge.py:379 (`live = _live(tx, type_='LESSON', project_id=m.project_id, workspace_id=m.workspace_id, k=k)`): the scope
    is half the identity, so a lesson of one project never borrows another
    project's corroboration to confirm itself."""
    p1, p2 = _project(db, 'one'), _project(db, 'two')
    m1 = _mission(db, project_id=p1)
    m2 = _mission(db, project_id=p2)
    _run(db, K.record_lessons, called=called(), mission_id=m1,
         result={'lessons': [{'title': 'Test the seam'}]})
    out = _run(db, K.record_lessons, called=called(), mission_id=m2,
               result={'lessons': [{'title': 'Test the seam'}]})
    assert (out['items'], out['corroborated'], out['confirmed']) == (1, 0, 0)
    items = _all(db, entities.KnowledgeItem)
    assert sorted(i.project_id for i in items) == sorted([p1, p2])
    assert [i.state for i in items] == ['CANDIDATE', 'CANDIDATE']


def test_corroboration_counts_missions_not_relation_rows(db):
    """knowledge.py:393-394 (`missions = {r.entity.dst_id for r in tx.where(...)}` — a *set*): an ended
    `learned_from` of the same mission is history, and a second row for it is
    still one mission. Two rows, one mission: no confirmation."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    kid = _item(db, project_id=pid, type_='LESSON', title='Test the seam', state='CANDIDATE',
                origin='inferred', source_kind='execution')
    _relation(db, kid, mid, rel='learned_from', dst_kind='mission',
              valid_until='2026-01-01T00:00:00+00:00')
    out = _run(db, K.record_lessons, called=called(), mission_id=mid,
               result={'lessons': [{'title': 'Test the seam'}]})
    assert (out['items'], out['corroborated'], out['confirmed']) == (0, 1, 0)
    assert _row(db, entities.KnowledgeItem, kid).state == 'CANDIDATE'
    links = [r for r in _all(db, entities.Relation) if r.rel == 'learned_from']
    assert len(links) == 2 and sum(1 for r in links if r.valid_until is None) == 1


def test_a_lesson_with_a_blank_title_is_refused_and_writes_nothing(db):
    """knowledge.py:382-383 (`type='LESSON', title=les['title'].strip()`): the
    whole command is refused, so no half-recorded lesson and no learned_from
    relation to a claim that does not exist."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    before = _n_events(db)
    with pytest.raises(ValueError, match='must be a non-empty string'):
        _run(db, K.record_lessons, called=called(), mission_id=mid,
             result={'lessons': [{'title': '   '}]})
    assert _all(db, entities.KnowledgeItem) == [] and _all(db, entities.Relation) == []
    assert _n_events(db) == before


def test_a_lesson_of_a_mission_that_is_not_there_is_a_not_found(db):
    """knowledge.py:374 (`m = lifecycle.load(tx, entities.Mission, mission_id).entity`):
    lessons are attributed to a mission that exists or not at all."""
    with pytest.raises(NotFound):
        _run(db, K.record_lessons, called=called(), mission_id=ids.new_id('mission'),
             result={'lessons': [{'title': 'Test the seam'}]})
    assert _all(db, entities.KnowledgeItem) == []


def test_a_mission_that_yielded_no_lessons_still_ends_its_call(db, ends):
    """knowledge.py:401 (`_end` after an empty loop): the call is ended with
    zeros rather than left with no outcome."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    out = _run(db, K.record_lessons, called=called(), mission_id=mid, result={'lessons': []})
    assert out == {'items': 0, 'corroborated': 0, 'confirmed': 0}
    assert len(ends) == 1 and ends[0]['outcome']['confirmed'] == 0


# ── 8. replay: the same request twice is the same answer, and changes nothing ──

def test_replaying_the_same_request_is_answered_from_the_row_and_changes_nothing(db):
    """infra/db/writer.py `_one`/`_recall` under the knowledge commands: a client
    that retries `record_lessons` gets its first answer back and the second
    commit writes no item, no relation and no event — the corroboration count in
    particular may not be paid for twice."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    args = {'actor': USER, 'called': called(), 'mission_id': mid,
            'result': {'lessons': [{'title': 'Test the seam', 'text': 'twice'}]}}
    first = db.writer.execute(K.record_lessons, args, idempotency_key='lessons-1')
    head, items = _n_events(db), len(_all(db, entities.KnowledgeItem))
    again = db.writer.execute(K.record_lessons, args, idempotency_key='lessons-1')
    assert again == first and again['items'] == 1
    assert _n_events(db) == head
    assert len(_all(db, entities.KnowledgeItem)) == items
    assert len([r for r in _all(db, entities.Relation) if r.rel == 'learned_from']) == 1


def test_replaying_a_confirm_does_not_take_the_edge_twice(db):
    """The same request under the same key: the confirm is not a second
    transition of the machine (knowledge.py:92-110 through lifecycle)."""
    _project(db)
    kid = _item(db, state='CANDIDATE')
    args = {'actor': USER, 'knowledge_item_id': kid}
    first = db.writer.execute(K.confirm, args, idempotency_key='confirm-1')
    head = _n_events(db)
    assert db.writer.execute(K.confirm, args, idempotency_key='confirm-1') == first
    assert _version(db, entities.KnowledgeItem, kid) == 2
    assert _n_events(db) == head
    # and the replayed answer is the answer, not the refusal a second fire gets
    with pytest.raises(IllegalTrigger):
        _run(db, K.confirm, knowledge_item_id=kid)


def test_a_different_request_under_a_used_key_is_refused(db):
    """infra/db/writer.py `_recall` (`IdempotencyConflict`): a client that reuses
    a key for other words may not have the earlier answer handed to it while its
    own request is silently dropped."""
    pid = _project(db)
    mid = _mission(db, project_id=pid)
    args = {'actor': USER, 'called': called(), 'mission_id': mid,
            'result': {'lessons': [{'title': 'Test the seam'}]}}
    db.writer.execute(K.record_lessons, args, idempotency_key='lessons-2')
    before = len(_all(db, entities.KnowledgeItem))
    with pytest.raises(IdempotencyConflict):
        db.writer.execute(K.record_lessons,
                          dict(args, result={'lessons': [{'title': 'Something else'}]}),
                          idempotency_key='lessons-2')
    assert len(_all(db, entities.KnowledgeItem)) == before
