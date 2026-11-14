"""T-1418: the uncovered branches of `archeus/node/mxc_cancel.py` lines 62-132, the
cancellation order and disposal verdict, with its helpers _owned_ids (42-50) and
_recorded (53-59).

Ten selected probes, denial and fail-closed first, then boundaries, then error paths:

1  cancel 67-68        a non-callable effect (record included) refused before any effect or clock read
                       -> test_a_non_callable_effect_is_refused_before_anything_runs
2  cancel 69-70        wait_s that is a bool, zero, negative or a string refused before any effect
                       -> test_a_bad_quiescence_bound_is_refused_before_anything_runs
3  cancel 74-75        a prior DISPOSED_VERIFIED returns at once, record read once and nothing run
                       -> test_a_recorded_disposal_is_returned_without_running_anything
4  cancel 125-126      a prior QUARANTINE is never lifted by a fresh clean read-back
                       -> test_a_prior_quarantine_is_not_lifted_by_a_clean_run
5  cancel 78-88        revoke raising records its type name and end_job still runs; end_job raising quarantines
                       -> test_a_revoke_that_raises_does_not_stop_the_end_job
                       -> test_an_end_job_that_raises_quarantines
6  cancel 93-98        wait_quiescent answering neither True nor False, or raising, quarantines
                       -> test_a_wait_that_answers_neither_true_nor_false_is_unverified
                       -> test_a_wait_that_raises_is_recorded_by_its_type
7  _owned_ids 42-50 and 106-111   True is absent; a list of text ids is still owned, sorted;
                       a list with '' or a non-str item, or any other answer, is unknown ownership
                       -> test_only_true_or_text_ids_answer_the_read_back
8  cancel 112-113      a read-back that finds ids at or after the bound is still_owned, not timed_out
                       -> test_owned_ids_past_the_bound_are_still_owned
9  cancel 131-132      record's return outside VERDICTS yields the computed verdict; a raising record propagates
                       -> test_a_recorder_answering_nothing_known_keeps_the_computed_verdict
                       -> test_a_recorder_that_raises_is_not_swallowed
10 cancel 128-130      the facts the recorder gets: the steps actually run, faults copied, prior, wait_s, owned
                       -> test_the_facts_hold_the_steps_that_ran
                       -> test_a_skipped_read_back_is_missing_from_the_order

Replaces a probe that was covered already: the read-back that returns True at the bound is pinned by
tests/v1/unit/test_mxc_cancel.py (a_read_back_that_overruns_the_bound_verifies_nothing).

No MXC, no Win32, no process and no ledger: every effect is a recording fake and the clock is scripted.
The premise on mxc_cancel.py 101-102 (a bound that elapsed records timed_out and quarantines, not
STILL_RUNNING) is not xfailed: tests/v1/unit/test_mxc_cancel.py a_bound_already_elapsed_reads_back_nothing_and_quarantines
pins it on purpose and archeus/node/local.py 167-168 documents it, so no strict xfail is kept.
"""

from types import SimpleNamespace

import pytest

from archeus.node import mxc_cancel as cancel


EXECUTION = SimpleNamespace(id='exec-1418')
STEPS = ('revoke_admission', 'end_job', 'wait_quiescent', 'read_back_resources')


class Ledger:
    """The record seam: a lookup is record(execution, None, None); a write stores the verdict."""

    def __init__(self, known=None, answer=None, boom=None):
        self.known = known
        self.answer = answer
        self.boom = boom
        self.calls = []

    def __call__(self, execution, verdict, facts):
        self.calls.append((execution, verdict, facts))
        if self.boom is not None:
            raise self.boom
        if verdict is None:
            return self.known
        return self.answer if self.answer is not None else verdict


class Clock:
    """Scripted readings; once the script is spent every reading is the last value."""

    def __init__(self, *values):
        self.values = list(values)
        self.reads = 0

    def __call__(self):
        self.reads += 1
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


class Effects:
    """Recording effects in the order they run; each step can be overridden."""

    def __init__(self, seen):
        self.seen = seen
        self.revoke = self._step('revoke_admission', None)
        self.end = self._step('end_job', None)
        self.wait = self._step('wait_quiescent', True)
        self.read = self._step('read_back_resources', True)

    def _step(self, name, answer):
        def effect(execution, *rest):
            assert execution is EXECUTION
            self.seen.append(name)
            return answer
        return effect

    def all(self):
        return [self.revoke, self.end, self.wait, self.read]


@pytest.fixture
def seen():
    return []


@pytest.fixture
def effects(seen):
    return Effects(seen)


def run(effects, ledger, clock=None, wait_s=5.0, **overrides):
    steps = [effects.revoke, effects.end, effects.wait, effects.read]
    for index, name in enumerate(STEPS):
        if name in overrides:
            steps[index] = overrides[name]
    clock = clock or Clock(0.0, 1.0, 2.0)
    verdict = cancel.cancel(EXECUTION, *steps, ledger, clock=clock, wait_s=wait_s)
    return verdict, clock


# ── 1-2: refusals before anything runs ──────────────────────────────────────

@pytest.mark.parametrize('index', range(5), ids=['revoke', 'end', 'wait', 'read', 'record'])
def test_a_non_callable_effect_is_refused_before_anything_runs(effects, seen, index):
    steps = [effects.revoke, effects.end, effects.wait, effects.read, Ledger()]
    steps[index] = 'not-callable'
    clock = Clock(0.0)
    with pytest.raises(ValueError, match='callable'):
        cancel.cancel(EXECUTION, *steps, clock=clock)
    assert seen == [] and clock.reads == 0


@pytest.mark.parametrize('wait_s', [True, False, 0, -1.0, '5', None],
                         ids=['true', 'false', 'zero', 'negative', 'text', 'none'])
def test_a_bad_quiescence_bound_is_refused_before_anything_runs(effects, seen, wait_s):
    ledger = Ledger()
    clock = Clock(0.0)
    with pytest.raises(ValueError, match='bound'):
        cancel.cancel(EXECUTION, effects.revoke, effects.end, effects.wait, effects.read,
                      ledger, clock=clock, wait_s=wait_s)
    assert seen == [] and ledger.calls == [] and clock.reads == 0


# ── 3-4: a prior verdict ────────────────────────────────────────────────────

def test_a_recorded_disposal_is_returned_without_running_anything(effects, seen):
    ledger = Ledger(known=cancel.DISPOSED_VERIFIED)
    verdict, _ = run(effects, ledger)
    assert verdict == cancel.DISPOSED_VERIFIED
    assert seen == []
    assert ledger.calls == [(EXECUTION, None, None)]


def test_a_prior_quarantine_is_not_lifted_by_a_clean_run(effects, seen):
    ledger = Ledger(known=cancel.QUARANTINE_UNVERIFIED)
    verdict, _ = run(effects, ledger)
    assert verdict == cancel.QUARANTINE_UNVERIFIED
    assert seen == list(STEPS)
    (_, written, facts) = ledger.calls[-1]
    assert written == cancel.QUARANTINE_UNVERIFIED
    assert facts['prior'] == cancel.QUARANTINE_UNVERIFIED
    assert facts['faults'] == {}


def test_a_prior_quarantine_is_not_lifted_by_a_still_running_answer(effects, seen):
    # the card called this "stays QUARANTINE"; the source gives STILL_RUNNING here, because
    # line 125 only downgrades DISPOSED. The assertion keeps what the source does: never disposed.
    ledger = Ledger(known=cancel.QUARANTINE_UNVERIFIED)
    verdict, _ = run(effects, ledger, wait_quiescent=lambda e, d: False)
    assert verdict == cancel.STILL_RUNNING
    assert verdict != cancel.DISPOSED_VERIFIED


# ── 5-6: step faults ────────────────────────────────────────────────────────

def test_a_revoke_that_raises_does_not_stop_the_end_job(effects, seen):
    def revoke(execution):
        seen.append('revoke_admission')
        raise PermissionError('broker refused')

    ledger = Ledger()
    verdict, _ = run(effects, ledger, revoke_admission=revoke)
    assert verdict == cancel.QUARANTINE_UNVERIFIED
    assert seen == list(STEPS)
    assert ledger.calls[-1][2]['faults']['revoke_admission'] == 'PermissionError'


def test_an_end_job_that_raises_quarantines(effects, seen):
    def end(execution):
        seen.append('end_job')
        raise RuntimeError('job not terminated')

    ledger = Ledger()
    verdict, _ = run(effects, ledger, end_job=end)
    assert verdict == cancel.QUARANTINE_UNVERIFIED
    assert ledger.calls[-1][2]['faults'] == {'end_job': 'RuntimeError'}


@pytest.mark.parametrize('answer', [None, 'yes', 1], ids=['none', 'text', 'one'])
def test_a_wait_that_answers_neither_true_nor_false_is_unverified(effects, seen, answer):
    # 1 == True in Python, but the test is `is True`, so the integer one is unverified too
    ledger = Ledger()
    verdict, _ = run(effects, ledger, wait_quiescent=lambda e, d: answer)
    assert verdict == cancel.QUARANTINE_UNVERIFIED
    facts = ledger.calls[-1][2]
    assert facts['faults'] == {'wait_quiescent': 'unverified'}
    assert facts['quiescent'] is None


def test_a_wait_that_raises_is_recorded_by_its_type(effects, seen):
    def wait(execution, deadline):
        raise TimeoutError('query refused')

    ledger = Ledger()
    verdict, _ = run(effects, ledger, wait_quiescent=wait)
    assert verdict == cancel.QUARANTINE_UNVERIFIED
    facts = ledger.calls[-1][2]
    assert facts['faults'] == {'wait_quiescent': 'TimeoutError'}
    assert facts['quiescent'] is None


# ── 7-8: the read-back answer ───────────────────────────────────────────────

@pytest.mark.parametrize('answer, read_back, owned, verdict', [
    (True, 'absent', None, cancel.DISPOSED_VERIFIED),
    ((), 'absent', None, cancel.DISPOSED_VERIFIED),
    (('res-b', 'res-a'), 'still_owned', ['res-a', 'res-b'], cancel.QUARANTINE_UNVERIFIED),
    (['res-b'], 'still_owned', ['res-b'], cancel.QUARANTINE_UNVERIFIED),
    ({'res-z'}, 'still_owned', ['res-z'], cancel.QUARANTINE_UNVERIFIED),
    (frozenset({'res-y'}), 'still_owned', ['res-y'], cancel.QUARANTINE_UNVERIFIED),
    (['res-a', ''], 'unknown_ownership', None, cancel.QUARANTINE_UNVERIFIED),
    (['res-a', 7], 'unknown_ownership', None, cancel.QUARANTINE_UNVERIFIED),
    ('res-a', 'unknown_ownership', None, cancel.QUARANTINE_UNVERIFIED),
    (False, 'unknown_ownership', None, cancel.QUARANTINE_UNVERIFIED),
    (None, 'unknown_ownership', None, cancel.QUARANTINE_UNVERIFIED),
], ids=['true', 'empty-tuple', 'tuple', 'list', 'set', 'frozenset', 'empty-id-in-list',
        'non-text-in-list', 'bare-text', 'false', 'none'])
def test_only_true_or_text_ids_answer_the_read_back(effects, seen, answer, read_back, owned, verdict):
    ledger = Ledger()
    got, _ = run(effects, ledger, read_back_resources=lambda e: answer)
    assert got == verdict
    facts = ledger.calls[-1][2]
    assert facts['read_back'] == read_back
    assert facts['owned'] == owned
    if read_back == 'absent':
        assert facts['faults'] == {}


def test_owned_ids_past_the_bound_are_still_owned(effects, seen):
    # a read-back that finds ids is trusted as still_owned even when the clock is already past
    # the bound: only the empty answer checks the clock again (cancel 112-113)
    ledger = Ledger()
    now = [0.0]

    def read_back(execution):
        now[0] = 9.0                                    # the read itself runs past the bound
        return ('res-q',)

    verdict, _ = run(effects, ledger, clock=lambda: now[0], read_back_resources=read_back,
                     wait_s=5.0)
    assert verdict == cancel.QUARANTINE_UNVERIFIED
    facts = ledger.calls[-1][2]
    assert facts['read_back'] == 'still_owned'
    assert facts['owned'] == ['res-q']
    assert 'timed_out' not in facts['faults'].values()


# ── 9: the recorder's answer ────────────────────────────────────────────────

def test_a_recorder_answering_nothing_known_keeps_the_computed_verdict(effects, seen):
    ledger = Ledger(answer='not-a-verdict')
    verdict, _ = run(effects, ledger)
    assert verdict == cancel.DISPOSED_VERIFIED
    assert ledger.calls[-1][1] == cancel.DISPOSED_VERIFIED


def test_a_recorder_that_raises_is_not_swallowed(effects, seen):
    ledger = Ledger(boom=OSError('ledger write failed'))
    with pytest.raises(OSError, match='ledger write failed'):
        run(effects, ledger)


# ── 10: the facts ───────────────────────────────────────────────────────────

def test_the_facts_hold_the_steps_that_ran(effects, seen):
    ledger = Ledger()
    verdict, _ = run(effects, ledger, wait_s=7.5)
    assert verdict == cancel.DISPOSED_VERIFIED
    facts = ledger.calls[-1][2]
    assert facts == {'order': list(STEPS) + ['record'], 'faults': {}, 'quiescent': True,
                     'read_back': 'absent', 'owned': None, 'prior': None, 'wait_s': 7.5}


def test_a_skipped_read_back_is_missing_from_the_order(effects, seen):
    ledger = Ledger()
    verdict, _ = run(effects, ledger, clock=Clock(0.0, 5.0), wait_s=5.0)
    assert verdict == cancel.QUARANTINE_UNVERIFIED
    facts = ledger.calls[-1][2]
    assert facts['order'] == ['revoke_admission', 'end_job', 'wait_quiescent', 'record']
    assert facts['read_back'] == 'timed_out'
    assert seen == list(STEPS[:3])
