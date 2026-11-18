"""Cancellation order and disposal verdicts: injected effects only, no MXC, no Win32, no process."""

import types
from types import SimpleNamespace

import pytest

from archeus.node import mxc_cancel as cancel_mod


EXECUTION = SimpleNamespace(id='exec-454')

STEPS = ('revoke_admission', 'end_job', 'wait_quiescent', 'read_back_resources')


class Recorder:
    """The ledger seam, deliberately naive: it stores whatever verdict it is handed,
    so a downgrade can only be prevented by the orchestration under test."""

    def __init__(self, verdict=None):
        self.writes = []
        self.factsets = []
        self.on_record = verdict
        self.lookups = 0

    def __call__(self, execution, verdict, facts):
        assert execution is EXECUTION
        if verdict is None:
            assert facts is None
            self.lookups += 1
            return self.on_record
        self.writes.append(verdict)
        self.factsets.append(facts)
        self.on_record = verdict
        return verdict


class Clock:
    """The only time this orchestration is allowed to see: successive readings, scripted."""

    def __init__(self, *values):
        self.values = list(values)
        self.readings = []

    def __call__(self):
        self.readings.append(len(self.readings))
        return self.values.pop(0) if self.values else 0.0


@pytest.fixture
def seen():
    return {'calls': [], 'deadline': None}


@pytest.fixture
def healthy(seen):
    """Every effect answering well: the broker grant goes, the Job ends, the Job
    drains inside the bound, and every owned resource reads back gone."""
    def revoke(execution):
        assert execution is EXECUTION
        seen['calls'].append('revoke_admission')

    def end(execution):
        assert execution is EXECUTION
        seen['calls'].append('end_job')

    def wait(execution, deadline):
        assert execution is EXECUTION
        seen['calls'].append('wait_quiescent')
        seen['deadline'] = deadline
        return True

    def read(execution):
        assert execution is EXECUTION
        seen['calls'].append('read_back_resources')
        return True

    return SimpleNamespace(revoke=revoke, end=end, wait=wait, read=read)


def run(healthy, recorder=None, overrides=(), **kwargs):
    effects = [healthy.revoke, healthy.end, healthy.wait, healthy.read]
    for name, effect in zip(STEPS, overrides):
        if effect is not None:
            effects[STEPS.index(name)] = effect
    clock = kwargs.pop('clock', None) or Clock(*kwargs.pop('clock_values', (0.0, 1.0, 2.0)))
    recorder = Recorder() if recorder is None else recorder
    verdict = cancel_mod.cancel(EXECUTION, *effects, recorder, clock=clock, **kwargs)
    return verdict, recorder, clock


def test_a_clean_cancel_disposes_in_the_locked_order(healthy, seen):
    verdict, recorder, clock = run(healthy)
    assert verdict == cancel_mod.DISPOSED_VERIFIED
    assert seen['calls'] == list(STEPS)
    assert recorder.writes == [cancel_mod.DISPOSED_VERIFIED]
    assert recorder.factsets[0]['order'] == [*STEPS, 'record']
    assert clock.readings == [0, 1, 2]


def test_admission_is_revoked_before_the_job_ends(healthy, seen):
    run(healthy)
    assert seen['calls'][:2] == ['revoke_admission', 'end_job']


def test_the_quiescence_wait_is_bounded_by_the_injected_clock(healthy, seen):
    run(healthy, wait_s=5)
    assert seen['deadline'] == 5.0


def test_a_revoke_fault_still_ends_waits_reads_back_and_quarantines(healthy, seen):
    def revoke(execution):
        seen['calls'].append('revoke_admission')
        raise TimeoutError('broker unreachable')

    verdict, recorder, _ = run(healthy, overrides=(revoke,))
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert seen['calls'] == list(STEPS)
    assert recorder.factsets[0]['faults'] == {'revoke_admission': 'TimeoutError'}


def test_an_end_job_fault_still_waits_and_reads_back(healthy, seen):
    def end(execution):
        seen['calls'].append('end_job')
        raise OSError('close_handle failed')

    verdict, recorder, _ = run(healthy, overrides=(None, end))
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert seen['calls'] == list(STEPS)
    assert recorder.factsets[0]['faults'] == {'end_job': 'OSError'}


@pytest.mark.parametrize('answer', [None, 'quiet', 1, 0])
def test_a_wait_that_answers_nothing_about_quiescence_quarantines(healthy, seen, answer):
    def wait(execution, deadline):
        seen['calls'].append('wait_quiescent')
        return answer

    verdict, recorder, _ = run(healthy, overrides=(None, None, wait))
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert recorder.factsets[0]['faults'] == {'wait_quiescent': 'unverified'}
    assert recorder.factsets[0]['quiescent'] is None


def test_a_wait_that_raises_quarantines_and_still_reads_back(healthy, seen):
    def wait(execution, deadline):
        seen['calls'].append('wait_quiescent')
        raise RuntimeError('query refused')

    verdict, recorder, _ = run(healthy, overrides=(None, None, wait))
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert seen['calls'] == list(STEPS)
    assert recorder.factsets[0]['faults'] == {'wait_quiescent': 'RuntimeError'}


def test_quiescence_not_reached_within_the_bound_reports_still_running(healthy, seen):
    def wait(execution, deadline):
        seen['calls'].append('wait_quiescent')
        return False

    verdict, recorder, _ = run(healthy, overrides=(None, None, wait))
    assert verdict == cancel_mod.STILL_RUNNING
    assert seen['calls'] == list(STEPS)                 # the read-back is read-only: it runs
    assert recorder.writes == [cancel_mod.STILL_RUNNING]
    assert recorder.factsets[0]['quiescent'] is False


def test_a_still_running_job_is_not_disposed_even_with_a_clean_read_back(healthy, seen):
    def wait(execution, deadline):
        return False

    verdict, _, _ = run(healthy, overrides=(None, None, wait))
    assert verdict == cancel_mod.STILL_RUNNING


def test_a_step_fault_outranks_a_still_running_job(healthy, seen):
    def revoke(execution):
        raise TimeoutError('broker unreachable')

    def wait(execution, deadline):
        return False

    verdict, recorder, _ = run(healthy, overrides=(revoke, None, wait))
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert recorder.factsets[0]['quiescent'] is False    # the fact is kept, not lost


@pytest.mark.parametrize('answer', [None, 'all gone', 1, 0, {}, {'res-1': 'exec-454'},
                                    ('pid:1', None), ('',), object()])
def test_a_read_back_that_answers_nothing_about_ownership_quarantines(healthy, seen, answer):
    def read(execution):
        seen['calls'].append('read_back_resources')
        return answer

    verdict, recorder, _ = run(healthy, overrides=(None, None, None, read))
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert recorder.factsets[0]['faults'] == {'read_back': 'unknown_ownership'}


def test_a_read_back_that_raises_quarantines_without_any_disposal_being_claimed(healthy, seen):
    def read(execution):
        seen['calls'].append('read_back_resources')
        raise PermissionError('handle unreadable')

    verdict, recorder, _ = run(healthy, overrides=(None, None, None, read))
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert recorder.factsets[0]['faults'] == {'read_back': 'PermissionError'}
    assert 'DISPOSED_VERIFIED' not in recorder.writes


@pytest.mark.parametrize('owned', [('res-1',), ['res-2', 'res-1'], {'res-1', 'res-2'}])
def test_resources_still_owned_by_the_execution_quarantine(healthy, seen, owned):
    def read(execution):
        return owned

    verdict, recorder, _ = run(healthy, overrides=(None, None, None, read))
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert recorder.factsets[0]['faults'] == {'read_back': 'still_owned'}
    assert recorder.factsets[0]['owned'] == ['res-1', 'res-2'][:len(owned)]


@pytest.mark.parametrize('empty', [True, (), [], frozenset()])
def test_every_ownership_answer_that_means_gone_verifies_disposal(healthy, seen, empty):
    def read(execution):
        return empty

    verdict, recorder, _ = run(healthy, overrides=(None, None, None, read))
    assert verdict == cancel_mod.DISPOSED_VERIFIED
    assert recorder.factsets[0]['read_back'] == 'absent'


def test_a_bound_already_elapsed_reads_back_nothing_and_quarantines(healthy, seen):
    def read(execution):
        seen['calls'].append('read_back_resources')
        return True

    verdict, recorder, _ = run(healthy, overrides=(None, None, None, read),
                               clock_values=(0.0, 5.0), wait_s=5)
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert seen['calls'] == list(STEPS[:3])
    assert recorder.factsets[0]['faults'] == {'read_back': 'timed_out'}
    assert recorder.factsets[0]['read_back'] == 'timed_out'


def test_a_read_back_that_overruns_the_bound_verifies_nothing(healthy, seen):
    verdict, recorder, _ = run(healthy, clock_values=(0.0, 1.0, 5.0), wait_s=5)
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert seen['calls'] == list(STEPS)
    assert recorder.factsets[0]['faults'] == {'read_back': 'timed_out'}


def test_a_second_cancel_never_turns_a_recorded_quarantine_into_disposed(healthy, seen):
    recorder = Recorder()

    def read(execution):
        seen['calls'].append('read_back_resources')
        if recorder.writes:                 # the retry now reads back clean
            return True
        raise PermissionError('handle unreadable')

    first, _, _ = run(healthy, recorder=recorder, overrides=(None, None, None, read))
    second, _, _ = run(healthy, recorder=recorder, overrides=(None, None, None, read))
    assert (first, second) == (cancel_mod.QUARANTINE_UNVERIFIED, cancel_mod.QUARANTINE_UNVERIFIED)
    assert recorder.writes == [cancel_mod.QUARANTINE_UNVERIFIED,
                               cancel_mod.QUARANTINE_UNVERIFIED]
    assert recorder.factsets[1]['prior'] == cancel_mod.QUARANTINE_UNVERIFIED
    assert seen['calls'] == [*STEPS, *STEPS]          # the safe steps run again, idempotently


def test_a_second_cancel_of_a_verified_disposal_changes_nothing(healthy, seen):
    recorder = Recorder()
    run(healthy, recorder=recorder)
    seen['calls'].clear()
    verdict, _, _ = run(healthy, recorder=recorder)
    assert verdict == cancel_mod.DISPOSED_VERIFIED
    assert seen['calls'] == []
    assert recorder.writes == [cancel_mod.DISPOSED_VERIFIED]
    assert recorder.lookups == 2


def test_a_recorded_still_running_can_be_verified_gone_later(healthy, seen):
    recorder = Recorder()

    def wait(execution, deadline):
        return bool(recorder.writes)        # busy the first time, quiet on the retry

    run(healthy, recorder=recorder, overrides=(None, None, wait))
    verdict, _, _ = run(healthy, recorder=recorder, overrides=(None, None, wait))
    assert recorder.writes == [cancel_mod.STILL_RUNNING, cancel_mod.DISPOSED_VERIFIED]
    assert verdict == cancel_mod.DISPOSED_VERIFIED


def test_a_quarantine_someone_else_recorded_holds_without_a_fresh_proof(healthy, seen):
    verdict, recorder, _ = run(
        healthy, recorder=Recorder(cancel_mod.QUARANTINE_UNVERIFIED))
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert recorder.writes == [cancel_mod.QUARANTINE_UNVERIFIED]


def test_a_verdict_that_cannot_be_read_back_is_never_reported_verified(healthy, seen):
    class Blind(Recorder):
        def __call__(self, execution, verdict, facts):
            if verdict is None:
                raise RuntimeError('ledger unreadable')
            return super().__call__(execution, verdict, facts)

    verdict, recorder, _ = run(healthy, recorder=Blind())
    assert verdict == cancel_mod.QUARANTINE_UNVERIFIED
    assert recorder.factsets[0]['faults'] == {'prior_verdict': 'RuntimeError'}
    assert recorder.writes == [cancel_mod.QUARANTINE_UNVERIFIED]

def test_a_verdict_the_recorder_cannot_persist_is_not_reported_as_recorded(healthy, seen):
    class Failing(Recorder):
        def __call__(self, execution, verdict, facts):
            if verdict is None:
                return super().__call__(execution, verdict, facts)
            raise OSError('ledger unwritable')

    with pytest.raises(OSError, match='ledger unwritable'):
        run(healthy, recorder=Failing())


def test_a_record_that_answers_with_nonsense_is_not_trusted_as_the_record(healthy, seen):
    class Odd(Recorder):
        def __call__(self, execution, verdict, facts):
            if verdict is None:
                return super().__call__(execution, verdict, facts)
            super().__call__(execution, verdict, facts)
            return 'MAYBE'

    verdict, recorder, _ = run(healthy, recorder=Odd())
    assert verdict == recorder.writes[0] == cancel_mod.DISPOSED_VERIFIED


def test_a_missing_effect_is_a_programming_error(healthy):
    with pytest.raises(ValueError, match='callable'):
        cancel_mod.cancel(EXECUTION, None, healthy.end, healthy.wait, healthy.read, Recorder())


def test_an_unbounded_wait_is_a_programming_error(healthy):
    with pytest.raises(ValueError, match='bound'):
        cancel_mod.cancel(EXECUTION, healthy.revoke, healthy.end, healthy.wait, healthy.read,
                          Recorder(), wait_s=0)


def test_the_orchestration_imports_no_transport():
    for value in vars(cancel_mod).values():
        if isinstance(value, types.ModuleType):
            assert value.__name__ == 'time'


def test_cancel_reaches_only_for_the_injected_effects(healthy, seen, monkeypatch):
    import subprocess

    def forbidden(*args, **kwargs):
        pytest.fail('cancellation reached for a real process')

    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    assert run(healthy)[0] == cancel_mod.DISPOSED_VERIFIED
    assert seen['calls'] == list(STEPS)
