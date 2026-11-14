import pytest

from archeus.core.application import executions as X, lifecycle
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import rows

from v1.unit.test_gaps_core_application_executions import _row, _world


def _spend(db, user, eid):
    def run(tx, **_):
        rd = entities.RouteDecision(id=ids.new_id('route_decision'),
                                    subject=Ref('archeus_call', 'brain'), decided_by='router',
                                    result='selected', outcome={'state': 'ok'})
        tx.insert(rd, actor=user)
        tx.update(entities.Execution, eid, {'route_decision_id': rd.id,
                                            'usage': {'tokens_in': 7}}, actor=user)
        tx.append(new_event('execution.progress', Ref('execution', eid), user, payload={},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})


def _ledger(db, eid):
    with db.read() as r:
        return [x.entity for x in rows.where(r, entities.UsageLedger, execution_id=eid)]


@pytest.mark.parametrize('state', ['PAUSED', 'AWAITING_APPROVAL'])
def test_a_discarded_execution_that_ran_still_leaves_its_ledger_row(state):
    db, user, system, k = _world(state, process_seq=1)
    try:
        _spend(db, user, k['eid'])
        db.writer.execute(X.stop, {'actor': system, 'execution_id': k['eid'],
                                   'reason': 'stopped by the user'})
        assert _row(db, entities.Execution, k['eid']).entity.state == 'ENDED_KILLED'
        assert [x.tokens_in for x in _ledger(db, k['eid'])] == [7]
    finally:
        db.close()


def test_a_rejected_approval_ends_with_its_ledger_row():
    db, user, system, k = _world('AWAITING_APPROVAL', process_seq=1, approval_state='REJECTED')
    try:
        _spend(db, user, k['eid'])
        db.writer.execute(X.approval_answered, {'actor': system, 'execution_id': k['eid']})
        assert _row(db, entities.Execution, k['eid']).entity.state == 'ENDED_REJECTED'
        assert [x.tokens_in for x in _ledger(db, k['eid'])] == [7]
    finally:
        db.close()


def _t(epoch):
    return X._iso(epoch)


def test_the_start_wait_follows_decided_time_not_creation_order():
    db, user, system, k = _world('ABANDONED', stop_reason='spawn')
    try:
        def run(tx, **_):
            tx.update(entities.Execution, k['eid'], {'ended_at': _t(1_000_100)}, actor=user)
            tx.insert(entities.Execution(
                id=ids.new_id('execution'), task_id=k['tid'], mission_id=k['mid'],
                plan_id=k['pid'], attempt=2, state='ENDED_OK', started_at=_t(1_000_050),
                ended_at=_t(1_000_060)), actor=user)
            tx.append(new_event('execution.progress', Ref('execution', k['eid']), user,
                                payload={}, workspace=ids.GLOBAL_WORKSPACE))
        db.writer.execute(run, {})
        with db.read() as r:
            assert X.spawn_wait(r, k['tid'], 1_000_101) == 1_000_100 + X.SPAWN_WAIT_S
    finally:
        db.close()


def test_an_unknown_served_level_is_not_a_fact():
    db, user, system, k = _world('RUNNING', process_seq=1)
    try:
        for served in ({'model': 'claude-x'}, {'level': 'served', 'model': 'claude-x'}):
            out = db.writer.execute(X.record_progress, {'actor': system,
                                                        'execution_id': k['eid'], 'offset': 5,
                                                        'served': served})
            assert out['offset'] == 5
        assert _row(db, entities.Execution, k['eid']).entity.served_level is None
    finally:
        db.close()


def test_the_breaker_names_the_newest_failure_by_instant_not_by_text():
    db, user, system, k = _world('RUNNING')
    try:
        def run(tx, **_):
            tx.append(new_event('execution.progress', Ref('execution', k['eid']), user,
                                payload={}, workspace=ids.GLOBAL_WORKSPACE))
            for n, (at, why) in enumerate((('2026-10-30T11:00:00+01:00', 'old'),
                                           ('2026-10-30T10:00:30Z', 'new'),
                                           ('2026-10-30T10:00:10Z', 'mid'))):
                tx.insert(entities.Execution(
                    id=ids.new_id('execution'), task_id=k['tid'], mission_id=k['mid'],
                    plan_id=k['pid'], attempt=n + 2, state='ABANDONED', stop_reason='spawn',
                    harness_id='claude', ended_at=at, summary=why), actor=user)
        db.writer.execute(run, {})
        with db.read() as r:
            got = X.spawn_breaker(r, 'claude', X._epoch('2026-10-30T10:00:40Z'))
        assert got['error'] == 'new'
    finally:
        db.close()


def test_a_late_progress_report_cannot_touch_an_ended_execution():
    db, user, system, k = _world('ENDED_OK', process_seq=1)
    try:
        with pytest.raises(lifecycle.IllegalTrigger):
            db.writer.execute(X.record_progress, {'actor': system, 'execution_id': k['eid'],
                                                  'offset': 9, 'usage': {'input_tokens': 5}})
        assert _row(db, entities.Execution, k['eid']).entity.stream_offset == 0
    finally:
        db.close()
