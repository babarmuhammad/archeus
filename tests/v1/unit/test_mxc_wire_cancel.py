# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""T-802: the ending is mxc_cancel's order and verdict, run on the launch's own seams;
the caller keeps the Job. Same fakes as the wire tests."""

import threading

import pytest

from archeus.node import mxc_cancel, mxc_ledger as ledger_mod

from .test_mxc_wire import (args, fail_op, journal_ops, native_parts, wire)  # noqa: F401

OK = dict(outcome=lambda process: 0, reader=lambda execution_id, owner: True)


def started(wire, **options):
    h = wire(**dict(OK, **options))
    h.launch.start(job=h.job)
    return h


def seen(h):
    return [event for event in h.api.events
            if event in ('revoke', 'end_job', 'quiesce', 'readback', 'disposal', 'completion')]


def test_a_verified_disposal_is_the_clean_end(wire):
    h = started(wire)
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert state == {'state': ledger_mod.DEAD_CLEAN, 'reason': 'host asked', 'quiescence': None}
    assert h.launch.verdict == mxc_cancel.DISPOSED_VERIFIED
    assert h.launch.facts['order'] == ['revoke_admission', 'end_job', 'wait_quiescent',
                                       'read_back_resources', 'record']
    assert journal_ops(h.journal) == ['intent', 'ownership', 'disposal', 'completion']


def test_the_steps_run_in_the_cancel_modules_order_on_an_open_job(wire):
    calls = []

    def end_job(job):
        calls.append(('end_job', job, job in h.boundary.open))
        h.api.events.append('end_job')

    def reader(execution_id, owner):
        h.api.events.append('readback')
        return True

    h = started(wire, reader=reader)
    h.launch._end_job = end_job
    assert h.launch.cancel(reason='host asked', outcome=0)['state'] == ledger_mod.DEAD_CLEAN
    assert seen(h) == ['revoke', 'end_job', 'quiesce', 'readback', 'disposal']
    assert calls == [('end_job', h.job, True)]
    assert h.boundary.closed == [] and h.job in h.boundary.open


def test_a_verdict_that_is_not_a_verified_disposal_quarantines(wire):
    still = started(wire, counts=[1] * 1000, execution_id='e2')
    assert still.launch.cancel(outcome=0)['state'] == ledger_mod.DEAD_UNVERIFIED
    assert still.launch.verdict == mxc_cancel.STILL_RUNNING
    unknown = started(wire, reader=lambda execution_id, owner: None, execution_id='e3')
    assert unknown.launch.cancel(outcome=0)['state'] == ledger_mod.DEAD_UNVERIFIED
    assert unknown.launch.verdict == mxc_cancel.QUARANTINE_UNVERIFIED
    owned = started(wire, reader=lambda execution_id, owner: ['res-1'], execution_id='e4')
    assert owned.launch.cancel(outcome=0)['state'] == ledger_mod.DEAD_UNVERIFIED
    assert owned.launch.facts['owned'] == ['res-1']
    for h, name in ((still, 'e2'), (unknown, 'e3'), (owned, 'e4')):
        ops = journal_ops(h.journal, name)
        assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops


@pytest.mark.parametrize('answer', [[], (), False, None, 'absent', 1])
def test_only_true_or_a_list_of_owned_ids_answers_the_read_back(wire, answer):
    h = started(wire, reader=lambda execution_id, owner: answer)
    assert h.launch.cancel(outcome=0)['state'] == ledger_mod.DEAD_UNVERIFIED
    assert 'completion' not in journal_ops(h.journal)


def test_an_end_without_a_workload_outcome_is_never_clean(wire):
    h = started(wire)
    assert h.launch.cancel(reason='timeout')['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.facts['read_back'] == 'absent' and not h.launch.facts['faults']
    assert h.launch.verdict == mxc_cancel.QUARANTINE_UNVERIFIED
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops


@pytest.mark.parametrize('broken', ['revoke', 'end_job', 'wait', 'readback'])
def test_a_step_that_raises_never_skips_the_next_and_is_never_clean(wire, broken):
    h = started(wire)

    def fail(*unused):
        raise OSError('step failed')

    if broken == 'revoke':
        h.broker.revoke = fail
    elif broken == 'end_job':
        h.launch._end_job = fail
    elif broken == 'wait':
        h.boundary.job_active_processes = fail
    else:
        h.launch.resource_reader = fail
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.verdict == mxc_cancel.QUARANTINE_UNVERIFIED
    assert len(h.launch.facts['faults']) == 1
    assert h.launch.facts['order'][:4] == ['revoke_admission', 'end_job', 'wait_quiescent',
                                           'read_back_resources']
    assert h.api.handles == {} and h.boundary.closed == []
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops


def test_a_read_back_past_the_bound_is_not_trusted(wire):
    now = [0.0]

    def reader(execution_id, owner):
        now[0] += 10000
        return True

    h = started(wire, reader=reader)
    h.launch.clock = lambda: now[0]
    assert h.launch.cancel(outcome=0)['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.facts['read_back'] == 'timed_out'


def test_an_earlier_quarantine_is_never_lifted(wire):
    h = started(wire)
    h.journal.append('e1', 'quarantine', reason='earlier')
    assert h.launch.cancel(outcome=0)['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.facts['prior'] == mxc_cancel.QUARANTINE_UNVERIFIED
    assert journal_ops(h.journal) == ['intent', 'ownership', 'quarantine']


@pytest.mark.parametrize('op', ['disposal', 'completion'])
def test_a_journal_that_refuses_the_verdict_is_never_clean(wire, op):
    h = started(wire)
    fail_op(h.journal, op)
    assert h.launch.cancel(outcome=0)['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.verdict == mxc_cancel.QUARANTINE_UNVERIFIED
    assert journal_ops(h.journal)[-1] == 'quarantine'


def test_a_launch_that_never_started_ends_unverified_and_calls_nothing(wire):
    h = wire(**OK)
    called = []
    h.launch._end_job = lambda job: called.append(job)
    state = h.launch.cancel(reason='before start')
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED and called == []
    assert h.broker.revoked == ['e1']


def test_cancel_and_the_drain_racing_end_the_launch_once(wire):
    h = started(wire)
    entered, release, results = threading.Event(), threading.Event(), []
    real = h.broker.revoke

    def revoke(execution_id):
        entered.set()
        release.wait(5)
        real(execution_id)

    h.broker.revoke = revoke
    drain = threading.Thread(target=lambda: results.append(
        h.launch.cancel(reason='drain', outcome=0)))
    drain.start()
    assert entered.wait(5)
    other = threading.Thread(target=lambda: results.append(h.launch.cancel(reason='host')))
    other.start()
    other.join(0.2)
    assert other.is_alive()
    release.set()
    drain.join(5)
    other.join(5)
    assert len(results) == 2 and results[0] is results[1]
    assert results[0]['reason'] == 'drain'
    assert h.broker.revoked == ['e1'] and h.api.events.count('quiesce') == 1
    assert journal_ops(h.journal).count('completion') == 1
