import json
from collections import Counter

import pytest

from archeus.api import routes, schemas
from archeus.core.application import executions, replay
from archeus.core.domain import entities, ids, states
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes, public_account_id
from archeus.infra.db.writer import NotFound
from archeus.infra.eventlog import retention
from v1.integration.test_ui_seams import _approval, _mission, _plan, _task, _tx


def _read(db, mid, **kwargs):
    with db.read() as conn:
        result = replay.replay(conn, mid, **kwargs)
    schemas.validate(result, schemas.TYPES['Replay'])
    return result


def _execution(db, actor, mid, tid, **kwargs):
    eid = ids.new_id('execution')
    _tx(db, lambda tx: tx.insert(entities.Execution(
        id=eid, task_id=tid, mission_id=mid, harness_id='fake', **kwargs), actor=actor))
    return eid


def _record(result, eid, machine='execution'):
    return next(r for r in result['records'] if r['ref']['id'] == eid and r['machine'] == machine)


def _edge(db, actor, eid, machine, frm, to, trigger):
    _tx(db, lambda tx: tx.append(new_event(machine + '.state_changed',
        Ref(ids.kind_of(eid), eid), actor, payload={'from': frm, 'to': to, 'trigger': trigger},
        workspace=ids.GLOBAL_WORKSPACE)))


def test_vocabulary_covers_130_states_once_and_pins_totals():
    declared = [(machine, state, answer) for machine, names, answer in replay.CATEGORIES
                for state in names.split()]
    pairs = [(m, s) for m, s, _ in declared]
    expected = {(m, s) for m in (*states.MACHINES, *states.STATE_SETS) for s in states.states(m)}
    assert len(pairs) == len(set(pairs)) == len(expected) == 130
    assert set(pairs) == expected
    assert Counter(a for _, _, a in declared) == {
        'INTENDED': 29, 'RECORDED': 46, 'SUSPENDED': 16, 'MAY-HAVE-TAKEN-EFFECT': 12,
        'AUTHORIZED': 9, 'UNCERTAIN': 5, 'RECONCILED': 5, 'UNKNOWN': 5, 'NONE': 3}
    assert set(replay.ANSWER) == set(a for _, _, a in declared) - {'UNKNOWN'}
    assert len(replay.ANSWER) == 8
    assert replay.category('execution', 'ENDED_REJECTED') == 'RECORDED'


def test_unclassified_state_is_unknown():
    assert replay.category('execution', 'FUTURE_STATE') == 'UNKNOWN'
    assert replay.category('future_machine', 'RUNNING') == 'UNKNOWN'


def test_unknown_is_never_none(db, actor):
    mid = _mission(db, actor)
    sid = ids.new_id('session')
    _tx(db, lambda tx: tx.insert(entities.Session(
        id=sid, mission_id=mid, harness_id='fake', workspace_id=ids.GLOBAL_WORKSPACE,
        cwd='D:/project', mode='manual'), actor=actor))
    record = _record(_read(db, mid), sid, 'session')
    assert record['answer'] == 'UNKNOWN'
    assert record['reason'] == 'state_meaning_undeclared'


def test_rows_survive_without_events_and_missing_rows_are_not_rebuilt(db, actor):
    mid = _mission(db, actor)
    tid = _task(db, actor, mid, _plan(db, actor, mid))
    eid = _execution(db, actor, mid, tid, state='ENDED_OK', summary='Tests passed')
    ghost = ids.new_id('execution')
    _edge(db, actor, ghost, 'execution', 'RUNNING', 'ENDED_OK', 'exited_success')
    _edge(db, actor, eid, 'execution', 'RUNNING', 'ENDED_ERROR', 'exited_error')
    before = _read(db, mid)
    assert _record(before, eid)['answer'] == 'RECORDED'
    assert ghost not in json.dumps(before)
    _tx(db, lambda tx: tx.execute('DELETE FROM events'))
    after = _read(db, mid)
    assert _record(after, eid)['answer'] == 'RECORDED'
    assert after['verifications'] == []
    assert after['history']['answer'] == 'UNKNOWN'
    assert ghost not in json.dumps(after)


def test_only_owned_mission_rows_are_read(db, actor):
    mine, other = _mission(db, actor), _mission(db, actor)
    mt = _task(db, actor, mine, _plan(db, actor, mine))
    ot = _task(db, actor, other, _plan(db, actor, other))
    me = _execution(db, actor, mine, mt)
    oe = _execution(db, actor, other, ot)
    result = _read(db, mine)
    assert me in json.dumps(result)
    assert all(s not in json.dumps(result) for s in (other, ot, oe))
    with db.read() as conn, pytest.raises(NotFound):
        replay.replay(conn, ids.new_id('mission'))


def test_route_is_observe_read_only_and_unknown_mission_is_404(tc):
    key = ('GET', '/v1/missions/{id}/replay')
    assert routes.CLASS[key] == 'observe' and key not in routes.PRIVILEGED
    route = next(r for r in routes.ROUTES if (r.method, r.path) == key)
    assert route.scope == 'observe' and route.idempotent is None and route.request_schema is None
    mid = tc.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
        'idempotency_key': 'k-replay'}).json()['id']
    result = tc.http('GET', '/v1/missions/%s/replay' % mid)
    assert result.status == 200 and result.json()['mission_id'] == mid
    schemas.validate(result.json(), schemas.TYPES['Replay'])
    assert tc.http('GET', '/v1/missions/%s/replay' % ids.new_id('mission')).status == 404


def test_scope_authority_and_existing_start_bindings(db, actor):
    mid = _mission(db, actor)
    pid = _plan(db, actor, mid)
    tid = _task(db, actor, mid, pid)
    seeded = _execution(db, actor, mid, tid, seed_revision='a' * 40)
    unseeded = _execution(db, actor, mid, tid, attempt=2, end_state_digest='b' * 64)
    aid = _approval(db, actor, mid, pid)
    pd = ids.new_id('policy_decision')
    _tx(db, lambda tx: tx.insert(entities.PolicyDecision(id=pd, mission_id=mid,
        stage='plan', decision='ALLOW', outcome='auto_approved', reason='policy'), actor=actor))
    _tx(db, lambda tx: tx.update(entities.Mission, mid,
        {'integration_head': 'c' * 40}, actor=actor))
    result = _read(db, mid)
    assert result['starting_state'] == {'source': 'Mission.integration_head',
        'revision': 'c' * 40, 'answer': 'RECORDED', 'reason': 'existing_commit_binding'}
    starts = {e['id']: e['starting_state'] for e in result['executions']}
    assert starts[seeded]['revision'] == 'a' * 40 and starts[seeded]['source'] == 'Execution.seed_revision'
    assert starts[unseeded]['answer'] == 'UNKNOWN' and starts[unseeded]['revision'] is None
    assert starts[unseeded]['reason'] == 'starting_state_not_recorded'
    assert result['tasks'] == [{'id': tid, 'scope': {
        'objective': '', 'expected_output': '', 'boundaries': [], 'acceptance': []}}]
    assert [a['id'] for a in result['approvals']] == [aid]
    assert result['approvals'][0]['action_hash']
    assert [d['id'] for d in result['policy_decisions']] == [pd]
    assert result['external_effects'] == {'answer': 'UNKNOWN', 'reason': 'external_effects_not_recorded'}


def test_checkpoint_shapes_and_clipping_are_honest(db, actor):
    mid = _mission(db, actor)
    tid = _task(db, actor, mid, _plan(db, actor, mid))
    ordinary = _execution(db, actor, mid, tid, isolated=False)
    seeded = _execution(db, actor, mid, tid, attempt=2, isolated=True,
                        seed_revision='a' * 40, import_revision='b' * 40)
    decision_only = _execution(db, actor, mid, tid, attempt=3, isolated=True)
    checkpoints = []
    for eid in (ordinary, seeded, decision_only):
        cid = ids.new_id('checkpoint')
        checkpoints.append(cid)
        _tx(db, lambda tx, cid=cid, eid=eid: tx.insert(entities.Checkpoint(
            id=cid, execution_id=eid, mission_id=mid, task_id=tid, trigger='task_boundary',
            files_changed=tuple('M file%d.py' % n for n in range(30))), actor=actor))
    result = _read(db, mid)['checkpoints']
    assert [c['id'] for c in result] == checkpoints
    assert [c['files_are'] for c in result] == ['summary', 'paths', 'unknown']
    assert all(c['complete'] is False and c['item_limit'] == 30 and len(c['files_changed']) == 30
               and c['reason'] == 'checkpoint_is_a_clipped_summary' for c in result)


def test_artifacts_remain_task_bound(db, actor):
    mid, other = _mission(db, actor), _mission(db, actor)
    tid = _task(db, actor, mid, _plan(db, actor, mid))
    ot = _task(db, actor, other, _plan(db, actor, other))
    eid = _execution(db, actor, mid, tid)
    _tx(db, lambda tx: tx.insert(entities.Artifact(
        id='d' * 64, media_type='text/x-diff', size=1), actor=actor))
    kept = []
    for task, mission in ((tid, mid), (tid, None), (None, mid), (ot, mid)):
        rid = ids.new_id('artifact_record')
        if task == tid:
            kept.append(rid)
        _tx(db, lambda tx, rid=rid, task=task, mission=mission: tx.insert(entities.ArtifactRecord(
            id=rid, artifact_id='d' * 64, produced_by=Ref('execution', eid), kind='patch',
            task_id=task, mission_id=mission), actor=actor))
    result = _read(db, mid)['artifacts']
    assert [a['id'] for a in result] == kept
    assert all(a['task_id'] == tid for a in result)


def test_validation_error_and_unknown_criteria_are_not_passes(db, actor):
    mid = _mission(db, actor)
    pid = _plan(db, actor, mid)
    tid = _task(db, actor, mid, pid)
    made = []
    for state, criterion in (('ERROR', 'satisfied'), ('PASSED', 'unknown'), ('PASSED', 'satisfied')):
        vid = ids.new_id('verification')
        made.append(vid)
        _tx(db, lambda tx, vid=vid, state=state, criterion=criterion: tx.insert(entities.Verification(
            id=vid, subject=Ref('task', tid), verifier='code', plan_id=pid, state=state,
            base_revision='e' * 40, checks=({'name': 'test', 'kind': 'command', 'result': 'pass',
            'output_sha256': 'f' * 64},), criteria=({'index': 0, 'text': 'works',
            'check': 'automatic', 'result': criterion},)), actor=actor))
    result = {v['id']: v for v in _read(db, mid)['verifications']}
    assert [result[v]['validation_recorded'] for v in made] == [False, True, True]
    assert [result[v]['passed'] for v in made] == [False, False, True]
    assert result[made[2]]['checks'][0]['output_sha256'] == 'f' * 64
    assert result[made[2]]['starting_state']['revision'] == 'e' * 40
    assert result[made[2]]['starting_state']['source'] == 'Verification.base_revision'


def test_boot_sweep_settlement_is_core(db, actor):
    mid = _mission(db, actor)
    tid = _task(db, actor, mid, _plan(db, actor, mid))
    eid = _execution(db, actor, mid, tid, state='LOST')
    core = Ref('system', ids.new_id('principal'))
    db.writer.execute(executions.lost, {'actor': core, 'execution_id': eid,
                                       'reason': 'boot sweep found no collectable process'})
    result = _read(db, mid)
    record = _record(result, eid)
    assert (record['answer'], record['settled_by'], record['settlement_reason']) == (
        'RECONCILED', 'core', 'event_actor')
    assert record['settlement_seq'] is not None
    assert result['executions'][0]['exit_reason'] == 'lost'
    assert result['executions'][0]['charged'] is True


def test_integration_abandonment_is_device(db, actor):
    mid = _mission(db, actor)
    tid = ids.new_id('task')
    pid = _plan(db, actor, mid)
    _tx(db, lambda tx: tx.insert(entities.Task(id=tid, mission_id=mid, plan_id=pid,
        key='t', title='t', kind='code_change', integration_state='ABANDONED'), actor=actor))
    _edge(db, actor, tid, 'integration', 'CONFLICT', 'ABANDONED', 'user_abandons')
    record = _record(_read(db, mid), tid, 'integration')
    assert (record['answer'], record['settled_by']) == ('RECONCILED', 'device')


def test_discarded_is_not_reconciled(db, actor):
    mid = _mission(db, actor)
    tid = _task(db, actor, mid, _plan(db, actor, mid))
    eid = _execution(db, actor, mid, tid, state='ENDED_KILLED')
    _edge(db, actor, eid, 'execution', 'PAUSED', 'ENDED_KILLED', 'discarded')
    record = _record(_read(db, mid), eid)
    assert (record['answer'], record['settled_by']) == ('RECORDED', 'unknown')
    assert record['settlement_reason'] == 'transition_does_not_reconcile'


def test_unreadable_actor_never_means_device(db, actor):
    mid = _mission(db, actor)
    tid = _task(db, actor, mid, _plan(db, actor, mid))
    eid = _execution(db, actor, mid, tid, state='ENDED_KILLED')
    _edge(db, Ref('execution', ids.new_id('principal')), eid,
          'execution', 'LOST', 'ENDED_KILLED', 'reconciled_kill')
    record = _record(_read(db, mid), eid)
    assert record['answer'] == 'RECONCILED' and record['settled_by'] == 'unknown'
    assert record['settlement_reason'] == 'unreadable_event_actor'


def test_lost_is_unsettled_and_names_sweep(db, actor):
    mid = _mission(db, actor)
    tid = _task(db, actor, mid, _plan(db, actor, mid))
    eid = _execution(db, actor, mid, tid, state='LOST')
    record = _record(_read(db, mid), eid)
    assert (record['answer'], record['settled_by'], record['settlement_seq']) == ('UNCERTAIN', 'unknown', None)
    assert record['settlement_reason'] == 'unsettled_lost_awaiting_core_sweep'


def test_retention_pruning_loses_attribution_but_keeps_rows(db, actor):
    mid = _mission(db, actor)
    tid = _task(db, actor, mid, _plan(db, actor, mid))
    eid = _execution(db, actor, mid, tid, state='ENDED_KILLED')
    ok = _execution(db, actor, mid, tid, attempt=2, state='ENDED_OK')
    _edge(db, Ref('system', ids.new_id('principal')), eid,
          'execution', 'LOST', 'ENDED_KILLED', 'reconciled_kill')
    assert _record(_read(db, mid), eid)['settled_by'] == 'core'
    db.writer.execute(retention.prune, {'now': '2999-01-01T00:00:00.000Z'})
    result = _read(db, mid)
    assert _record(result, eid)['answer'] == 'UNKNOWN'
    assert _record(result, eid)['settlement_reason'] == 'retained_event_prefix_pruned'
    assert _record(result, ok)['answer'] == 'RECORDED'
    assert result['history']['answer'] == 'UNKNOWN'
    assert result['history']['reason'] == 'retained_event_prefix_pruned'
    assert result['history']['event_days'] == 180
    assert result['history']['open_mission_extension'] is False
    assert result['history']['oldest_retained_at'] is None
    assert result['history']['floor'] == result['history']['head'] > 0


def test_empty_event_range_is_unknown(db, actor):
    mid = _mission(db, actor)
    _tx(db, lambda tx: tx.execute('DELETE FROM events'))
    result = _read(db, mid)
    assert result['records'] and result['history']['answer'] == 'UNKNOWN'
    assert result['history']['reason'] == 'retained_event_prefix_pruned'


def test_all_replay_strings_use_trace_public_projection(db, actor, monkeypatch):
    home = 'C:/T148/Private-Home'
    key = 'fake:' + home.lower()
    monkeypatch.setattr('archeus.infra.discovery.public_account_secret', lambda: b't148-secret')
    homes = Homes([home], [('fake', key, home)], shorts=lambda _: None, path_flavour='windows')
    mid = _mission(db, actor)
    pid = _plan(db, actor, mid)
    tid = _task(db, actor, mid, pid)
    eid = _execution(db, actor, mid, tid, isolated=False)
    cid = ids.new_id('checkpoint')
    _tx(db, lambda tx: tx.insert(entities.Checkpoint(id=cid, execution_id=eid,
        mission_id=mid, task_id=tid, trigger='task_boundary', files_changed=(home + '/data', key)), actor=actor))
    pd = ids.new_id('policy_decision')
    _tx(db, lambda tx: tx.insert(entities.PolicyDecision(id=pd, mission_id=mid,
        stage='plan', decision='ALLOW', reason=home + ' ' + key), actor=actor))
    result = _read(db, mid, homes=homes)
    encoded = json.dumps(result)
    assert home.lower() not in encoded.lower() and key not in encoded
    assert result['checkpoints'][0]['files_changed'] == ['its home/data', public_account_id(key)]
    assert result['policy_decisions'][0]['reason'] == 'its home ' + public_account_id(key)
    with db.read() as conn:
        stored = conn.execute('SELECT body FROM checkpoints WHERE id = ?', (cid,)).fetchone()[0]
    assert home in stored and key in stored
