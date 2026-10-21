"""T-106, O7 as the owner answered T-110 Q1-Q10 (2026-10-21): a harness that
cannot start a process is retried under a per-task wait (15 s doubling to 5 min)
and a per-harness breaker (3 failed starts within 10 min open it; 5 min after
the last failure one task may try), both derived from the recorded starts.
Never charged to the task, never a new execution on every pass.

Time passing is written into the records (`_age`): the failed starts happened
that much earlier, which is all the derivation reads."""

import time

import pytest

from archeus.cli import gui
from archeus.core.application import executions as X, resources
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.harnesses import base
from archeus.harnesses.fake import FakeHarness
from archeus.node.local import LocalNode

from v1.integration.test_execution import DONE, Rig
from v1.integration.test_policy import task


@pytest.fixture
def x(db):
    rig = Rig(db)
    yield rig
    rig.cleanup()
    LocalNode.clear_estop()


REAL_SPAWN = base.proc.spawn_detached


def _no_popen(monkeypatch):
    monkeypatch.setattr(base.proc, 'spawn_detached', lambda *a, **k: (None, 'no process'))


def _spin(x, mid, seconds):
    """Engine steps and manager passes, as Core runs them, for *seconds*."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        x.engine.step(mid)
        x.manager.tick()
        time.sleep(0.01)


def _age(x, mid, seconds):
    """Every recorded end happened *seconds* earlier."""
    def run(tx, actor):
        for r in tx.where(entities.Execution):
            if r.entity.ended_at:
                tx.update(entities.Execution, r.entity.id, {'ended_at': X._iso(
                    X._epoch(r.entity.ended_at) - seconds)}, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', mid), actor,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    x.do(run)


def _breaker(x, harness_id='fake', now=None):
    with x.db.read() as r:
        return resources.breaker(r, harness_id, time.time() if now is None else now)


def _tripped(x, monkeypatch):
    """Three tasks fail to start, one after another: the third opens the breaker;
    the fourth finds only an open harness and waits READY."""
    _no_popen(monkeypatch)
    mid = x.ready(*(task('t%d' % i, 'write_repo') for i in range(1, 5)))
    x.drive(mid, lambda: x.all(entities.RouteDecision, task_id=x.task_of(mid, 't4').id))
    return mid


def test_T106_a_permanent_start_failure_is_retried_after_its_wait_not_on_every_pass(
        x, monkeypatch):
    _no_popen(monkeypatch)
    mid = x.ready(task('t1', 'write_repo'))
    _spin(x, mid, 2.0)
    runs = x.all(entities.Execution)
    assert [(r.state, r.stop_reason, r.charged) for r in runs] == [
        ('ABANDONED', 'spawn', False)]
    assert 'no process' in runs[0].summary
    assert (x.task_of(mid).state, x.m(mid).state) == ('READY', 'EXECUTING')
    # 15 s later it tries again; then it waits 30 s
    _age(x, mid, 16)
    _spin(x, mid, 1.0)
    assert len(x.all(entities.Execution)) == 2
    _age(x, mid, 16)
    _spin(x, mid, 1.0)
    assert len(x.all(entities.Execution)) == 2
    _age(x, mid, 15)
    _spin(x, mid, 1.0)
    assert len(x.all(entities.Execution)) == 3
    assert {(r.stop_reason, r.charged) for r in x.all(entities.Execution)} == {
        ('spawn', False)}


def test_T106_the_third_failure_opens_the_breaker_once_and_a_task_waits_ready(x, monkeypatch):
    mid = _tripped(x, monkeypatch)
    assert [(r.state, r.stop_reason, r.charged) for r in x.all(entities.Execution)] == [
        ('ABANDONED', 'spawn', False)] * 3
    (ev,) = x.events('harness.state_changed')
    assert (ev['subject'], ev['payload']['breaker']) == ({'kind': 'harness', 'id': 'fake'},
                                                        'open')
    assert gui.notice(ev) == 'fake cannot start a process; Archeus tries again in 5 minutes'
    b = _breaker(x)
    assert b['state'] == 'open' and 'no process' in b['error'] and b['until']
    t4 = x.task_of(mid, 't4')
    (rd,) = x.all(entities.RouteDecision, task_id=t4.id)
    assert (rd.result, rd.unblock_at) == ('blocked', b['until'])
    assert [c['eliminated_at_step'] for c in rd.candidates] == ['breaker']
    assert rd.explanation.startswith('Nothing could run this until')
    again = resources.replay(rd)
    assert (again['result'], again['candidates']) == (rd.result, list(rd.candidates))
    # the mission is not blocked: it waits for the harness, not for the user
    assert (t4.state, x.m(mid).state) == ('READY', 'EXECUTING')
    # and nothing more is written while it waits
    _spin(x, mid, 1.0)
    assert len(x.all(entities.Execution)) == 3
    assert len(x.all(entities.RouteDecision, task_id=t4.id)) == 1
    with x.db.read() as r:
        assert resources.route_wait(r, t4.id, time.time())
        assert not resources.route_wait(r, t4.id, time.time() + 301)


def test_T106_a_restart_rebuilds_the_breaker_from_the_records_and_gives_nothing_back(
        x, monkeypatch):
    mid = _tripped(x, monkeypatch)
    before = _breaker(x)
    fresh = Rig(x.db)                    # a new Core over the same records
    assert _breaker(fresh) == before
    _spin(fresh, mid, 1.0)
    assert len(fresh.all(entities.Execution)) == 3


def test_T106_half_open_lets_one_task_try_and_a_start_closes_it(x, monkeypatch):
    mid = _tripped(x, monkeypatch)
    _age(x, mid, 301)
    assert _breaker(x)['state'] == 'half_open'
    monkeypatch.setattr(base.proc, 'spawn_detached', REAL_SPAWN)  # it can start again
    x.scenarios['t1'] = [DONE]
    x.drive(mid, lambda: any(r.started_at for r in x.all(entities.Execution)))
    (trial,) = [r for r in x.all(entities.Execution) if r.started_at]
    assert x.task_of(mid, 't1').id == trial.task_id
    assert _breaker(x) is None
    assert len(x.events('harness.state_changed')) == 1


def test_T106_a_failed_trial_reopens_it_without_a_second_notice(x, monkeypatch):
    mid = _tripped(x, monkeypatch)
    _age(x, mid, 301)
    x.drive(mid, lambda: len(x.all(entities.Execution)) == 4)
    trial = x.all(entities.Execution)[-1]
    x.drive(mid, lambda: x.state(trial.id).state == 'ABANDONED')
    assert (x.state(trial.id).stop_reason, x.state(trial.id).charged) == ('spawn', False)
    assert _breaker(x)['state'] == 'open'
    assert len(x.events('harness.state_changed')) == 1
    _spin(x, mid, 1.0)
    assert len(x.all(entities.Execution)) == 4


def test_T106_an_open_harness_is_skipped_and_the_task_runs_on_another(db, monkeypatch):
    x = Rig(db, adapters=[FakeHarness(), FakeHarness('other')])
    try:
        real = x.manager.node.spawn

        def spawn(adapter, spec, **kw):
            if adapter.id == 'fake':
                raise base.SpawnFailed('no process')
            return real(adapter, spec, **kw)
        monkeypatch.setattr(x.manager.node, 'spawn', spawn)
        x.scenarios['t4'] = [DONE]
        mid = x.ready(*(task('t%d' % i, 'write_repo') for i in range(1, 5)))
        x.drive(mid, lambda: x.exe(task_id=x.task_of(mid, 't4').id))
        e = x.exe(task_id=x.task_of(mid, 't4').id)
        assert e.harness_id == 'other'
        (rd,) = x.all(entities.RouteDecision, task_id=e.task_id)
        assert {c['harness']: c['eliminated_at_step'] for c in rd.candidates} == {
            'fake': 'breaker', 'other': None}
    finally:
        x.cleanup()
