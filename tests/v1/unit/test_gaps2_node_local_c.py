# ruff: noqa: F811  (the imported wire fixtures are taken as arguments)
"""T-1027: the ten highest-risk uncovered branches of archeus/node/local.py lines
579-753 inclusive — the ending of `MxcLaunch` (`_end`, `_revoke`, `_end_job_step`,
`_wait_step`, `_now`, `_read_back_step`, `_owner`, `_record`, `_stand_down`,
`_quiescence_text`, `_quarantine`, `_quarantined`).

Everything is faked through the seams the wire tests already use (the Win32 api, Core's
Job boundary, the broker, the ledger, the clock, the pause, the outcome and the resource
readers): no DLL, no process, no Job, no network, and the ledger is the real journal
under tmp_path. The file runs identically on Linux and on Windows.

The selected branches, in source order, with the fail-closed property each one holds:

  A. local.py:597-599 + 605 `_end`'s `except BaseException` and `raise fatal` —
     test_an_ending_interrupted_by_a_signal_still_quarantines_and_ends_once
  B. local.py:597-599 (`except BaseException` with an ordinary Exception, `fatal` None)
     — test_a_clock_that_raises_stops_the_ending_without_raising_it
  C. local.py:645 `_wait_step`'s `type(n) is int` —
     test_a_job_count_that_is_zero_but_not_an_integer_proves_nothing
  D. local.py:647 `_wait_step`'s `self._now() >= limit` (the bound reached exactly)
     — test_the_quiescence_bound_is_reached_and_never_passed
  E. local.py:617-618 `_end_job_step`'s `self._end_job is not None` false side
     — test_an_end_with_no_end_job_callback_ends_nothing_and_is_never_clean
  F. local.py:664-665 `_read_back_step`'s `self.ledger is None` (with the `_record`
     and `_quarantine` no-journal guards at 689 and 735) —
     test_an_end_with_no_ledger_is_never_clean_and_touches_no_ownership_hook
  G. local.py:679-680 `_owner`'s `invalid or [row['op'] ...] != ['intent', 'ownership']`
     — test_ownership_that_is_not_exactly_intent_and_ownership_never_reaches_the_cleanup
  H. local.py:667-669 `_read_back_step`'s `self.disposal is not None` while the disposal
     is unproved — test_the_cleanup_hook_runs_even_when_the_disposal_cannot_be_proved
  I. local.py:740-744 `_quarantine`'s `except Exception: pass` (a quarantine the journal
     refuses) — test_a_quarantine_the_journal_refuses_still_ends_unverified
  J. local.py:724-730 `_quiescence_text` with several step faults AND the wait's own
     reason — test_every_ending_fault_reaches_the_recorded_quiescence

Card probes already covered by the existing suite are replaced, with the evidence in
/work/QWEN-DONE-T-1027.md: the revoke and end-Job faults, the still-live Job, the
unusable clock reading, the stand-down refusal and the repeated quarantine.
"""

import pytest

from archeus.node import local, mxc_cancel, mxc_ledger as ledger_mod

from .test_mxc_wire import (args, fail_op, journal_ops, journal_records,  # noqa: F401
                            native_parts, wire)

OK = dict(outcome=lambda process: 0, reader=lambda execution_id, owner: True)


def started(wire, **options):
    h = wire(**dict(OK, **options))
    h.launch.start(job=h.job)
    return h


class Clock:
    """The injected clock with exactly the readings a bound needs; the last reading
    repeats, so a test that proves the bound was honoured can never spin."""

    def __init__(self, *readings):
        self.readings, self.calls = list(readings), 0

    def __call__(self):
        index = min(self.calls, len(self.readings) - 1)
        self.calls += 1
        return float(self.readings[index])


# ── A. the ending interrupted by something `except Exception` does not catch ──

def test_an_ending_interrupted_by_a_signal_still_quarantines_and_ends_once(wire):
    """local.py:597-599, 605. The revoke dies on a signal: the guard is
    `except BaseException`, so the end is still journalled as unverified, the state
    is still stored, and the fault is still handed back to the caller."""
    h = started(wire)

    def revoke(execution_id):
        raise KeyboardInterrupt()

    h.broker.revoke = revoke
    with pytest.raises(KeyboardInterrupt):
        h.launch.cancel(reason='host asked', outcome=0)
    assert h.launch.end_state == {'state': ledger_mod.DEAD_UNVERIFIED,
                                  'reason': 'host asked', 'quiescence': None}
    assert h.launch.verdict is None                        # no verdict was ever earned
    ops = journal_ops(h.journal)
    assert ops == ['intent', 'ownership', 'quarantine']
    assert (journal_records(h.journal)[-1]['reason']
            == 'the ending did not finish: KeyboardInterrupt')
    assert 'completion' not in ops and 'disposal' not in ops
    # nothing privileged happened on the way out: the Job is the caller's, untouched
    assert h.boundary.terminated == [] and h.boundary.closed == []
    assert h.job in h.boundary.open
    # and the interrupted ending is still the only ending this launch will have
    assert h.launch.cancel(reason='again') is h.launch.end_state
    assert h.broker.revoked == [] and h.api.events.count('quiesce') == 0


# ── B. the ending that never finished, reported without raising ──

def test_a_clock_that_raises_stops_the_ending_without_raising_it(wire):
    """local.py:597-599 with an ordinary Exception: the bound cannot be computed, so
    mxc_cancel itself dies. The launch must still be ended, journalled, closed and
    reported DEAD_UNVERIFIED — and it must not claim a verdict it never reached."""
    h = started(wire)

    def clock():
        raise OSError('the clock cannot be read')

    h.launch.clock = clock
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert state == {'state': ledger_mod.DEAD_UNVERIFIED, 'reason': 'host asked',
                     'quiescence': None}
    assert h.launch.verdict is None
    ops = journal_ops(h.journal)
    assert ops == ['intent', 'ownership', 'quarantine']
    assert journal_records(h.journal)[-1]['reason'] == 'the ending did not finish: OSError'
    assert 'completion' not in ops and 'disposal' not in ops
    # the steps that had already run are not undone, and the ones that never ran left
    # no trace: the Job count was never read, the Job was never closed
    assert h.broker.revoked == ['e1'] and h.boundary.terminated == [h.job]
    assert h.api.events.count('quiesce') == 0
    assert h.api.handles == {} and h.boundary.closed == [] and h.job in h.boundary.open


# ── C. a Job count that only looks like zero ──

@pytest.mark.parametrize('answer', [0.0, False], ids=['float-zero', 'bool-false'])
def test_a_job_count_that_is_zero_but_not_an_integer_proves_nothing(wire, answer):
    """local.py:645. Quiescence is proved by `type(n) is int and n == 0`: a boundary
    that answers 0.0 or False is answering something, not reporting an empty Job, and
    an empty-looking answer at the bound leaves the end unverified, never clean."""
    h = started(wire, counts=[answer], quiescence_wait=0.0)
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.verdict == mxc_cancel.STILL_RUNNING
    assert state['quiescence'] == 'the Job answered %r, not zero members' % (answer,)
    ops = journal_ops(h.journal)
    assert ops == ['intent', 'ownership', 'quarantine']
    assert 'completion' not in ops and 'disposal' not in ops
    assert h.boundary.closed == [] and h.job in h.boundary.open


# ── D. the bound is reached, not passed ──

def test_the_quiescence_bound_is_reached_and_never_passed(wire):
    """local.py:647. At the instant the bound is exactly reached the reading is final:
    the Job is not asked again, so a Job that would have emptied one poll later buys
    nothing. With `>` instead of `>=` this end would be journalled as clean."""
    h = wire(**dict(OK, counts=[3, 0], quiescence_wait=10.0))
    h.launch.clock = Clock(0.0, 0.0, 10.0)     # cancel's deadline, the limit, the check
    h.launch.start(job=h.job)
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert h.api.events.count('quiesce') == 1 and h.boundary.counts == [0]
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.verdict == mxc_cancel.STILL_RUNNING
    assert state['quiescence'] == 'the Job answered 3, not zero members'
    assert h.launch.facts['read_back'] == 'absent'          # verified read-back…
    ops = journal_ops(h.journal)                            # …and still not clean
    assert ops == ['intent', 'ownership', 'quarantine']
    assert 'completion' not in ops and 'disposal' not in ops
    assert h.boundary.closed == [] and h.job in h.boundary.open


# ── E. no end-Job callback at all ──

def test_an_end_with_no_end_job_callback_ends_nothing_and_is_never_clean(wire):
    """local.py:617-618. A launch whose caller gave no `end_job` and whose boundary
    supplies none must invent no teardown: nothing is terminated, the caller's Job is
    neither closed nor read as empty, our own handles still go, and the end is a
    quarantine — not a step fault and not a clean verdict."""
    h = wire(**dict(OK, counts=[2], quiescence_wait=0.0))
    h.launch._end_job = None            # the caller owns the Job and ends nothing
    h.launch.start(job=h.job)
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.facts['faults'] == {} and h.launch.facts['quiescent'] is False
    assert h.launch.verdict == mxc_cancel.STILL_RUNNING
    assert h.boundary.terminated == [] and h.boundary.closed == []
    assert h.job in h.boundary.open
    assert h.api.handles == {}                               # our handles, never the Job's
    ops = journal_ops(h.journal)
    assert ops == ['intent', 'ownership', 'quarantine']
    assert 'completion' not in ops and 'disposal' not in ops


# ── F. an end with no journal: never clean, and no privileged cleanup either ──

class PlainChild:
    """The child a non-journalled backend hands back: drainable, closable, nothing more."""

    def __init__(self):
        self.closes, self.terminates = [], []
        self.pid, self.create_time = 4129, 133100000000000000

    def wait(self, timeout=None):
        return 0

    def close(self):
        self.closes.append(None)

    def terminate(self):
        self.terminates.append(None)


class PlainBackend:
    """A backend for a launch with no ledger: the thin wrapper the class docstring
    allows, with the real policy compiler and a child nobody started for real."""

    compile_policy = staticmethod(local.mxc.compile_policy)

    def __init__(self):
        self.child = PlainChild()
        self.spawned = []

    def spawn(self, policy, *, exe, job, **seam):
        self.spawned.append((exe, job, seam))
        return self.child


def test_an_end_with_no_ledger_is_never_clean_and_touches_no_ownership_hook(args,
                                                                            native_parts):
    """local.py:664-665 (and the matching guards in `_record` and `_quarantine`). With
    no journal there is no verified ownership record, so the end must not knock on the
    disposal or the read-back door at all — an unowned cleanup attempt is a privileged
    side effect — and it must report DEAD_UNVERIFIED whatever the readers would say."""
    backend = PlainBackend()
    calls = []
    launch = local.MxcLaunch(backend=backend, execution_id='e1',
                             outcome=lambda process: 0,
                             resource_reader=lambda execution_id, owner: (
                                 calls.append(('read', owner)), True)[1],
                             disposal=lambda owner: calls.append(('cleanup', owner)),
                             clock=lambda: 0.0, pause=lambda seconds: None,
                             quiescence_wait=0.0, **args)
    launch.start(job='caller-owned-job')
    assert launch.wait() == 0
    assert launch.completed == 0
    assert launch.end_state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert launch.end_state['quiescence'] == 'no boundary Job was held to read'
    assert calls == []                                   # no ownership, no cleanup
    assert backend.child.closes == [None]                # our handle went, once
    assert backend.child.terminates == []


# ── G. ownership that is not exactly the two durable records ──

def test_ownership_that_is_not_exactly_intent_and_ownership_never_reaches_the_cleanup(wire):
    """local.py:679-680. The cleanup hooks are handed the *returned* ownership, and
    only when the journal holds exactly intent + ownership. A third record — here a
    disposal already on file — makes the ownership unverified: the reader and the
    disposal are never called, and the end cannot be bought clean."""
    calls = []
    h = started(wire, disposal=lambda owner: calls.append(('cleanup', owner)),
                reader=lambda execution_id, owner: (calls.append(('read', owner)), True)[1])
    h.journal.append('e1-p1', 'disposal', verified_absent=True)     # already on record
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert calls == []                              # neither hook is handed a forged owner
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.verdict == mxc_cancel.QUARANTINE_UNVERIFIED
    assert h.launch.facts['faults'] == {'read_back': 'ValueError'}
    assert state['quiescence'] is None                   # the fault is the read-back's own
    ops = journal_ops(h.journal)
    assert ops == ['intent', 'ownership', 'disposal', 'quarantine']
    assert 'completion' not in ops                       # the old disposal buys no completion


# ── H. cleanup attempted, disposal unproved: the quarantine stays ──

def test_the_cleanup_hook_runs_even_when_the_disposal_cannot_be_proved(wire):
    """local.py:667-669. The cleanup is owed whether or not it works, and it is owed
    before the read-back that judges it. Nothing is proved: no disposal record is
    journalled, the quarantine is, and the still-owned ids are reported."""
    calls = []
    h = started(wire, disposal=lambda owner: calls.append(('cleanup', owner)),
                reader=lambda execution_id, owner: (calls.append(('read', owner)),
                                                     ['res-1'])[1])
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert [name for name, _ in calls] == ['cleanup', 'read']
    assert [row['op'] for _, row in calls] == ['ownership', 'ownership']
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.verdict == mxc_cancel.QUARANTINE_UNVERIFIED
    assert h.launch.facts['owned'] == ['res-1']
    assert h.launch.facts['faults']['read_back'] == 'still_owned'
    ops = journal_ops(h.journal)
    assert ops == ['intent', 'ownership', 'quarantine']
    assert 'disposal' not in ops and 'completion' not in ops
    assert h.boundary.closed == [] and h.job in h.boundary.open


# ── I. a journal that refuses the quarantine ──

def test_a_quarantine_the_journal_refuses_still_ends_unverified(wire):
    """local.py:740-744. The evidence that an end was not verified is itself a write,
    and a write that fails must never turn into a clean end and must never escape the
    ending: the state stays DEAD_UNVERIFIED and the launch is still ended once."""
    h = started(wire, reader=lambda execution_id, owner: None)     # nothing proved
    fail_op(h.journal, 'quarantine')
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert h.launch.verdict == mxc_cancel.QUARANTINE_UNVERIFIED
    assert journal_ops(h.journal) == ['intent', 'ownership']       # nothing was invented
    assert h.launch.cancel(reason='again') is state
    assert h.broker.revoked == ['e1'] and h.api.events.count('quiesce') == 1
    assert h.api.handles == {} and h.boundary.closed == [] and h.job in h.boundary.open


# ── J. every fault of the ending reaches the record ──

def test_every_ending_fault_reaches_the_recorded_quiescence(wire):
    """local.py:724-730. The ending keeps three separate voices: the two steps that
    died, the reason the Job could not be read, and the quarantine that carries them.
    Losing either half of `_quiescence_text` is an audit trail that says nothing."""
    h = wire(**OK)

    def boom(*unused):
        raise OSError('step failed')

    h.broker.revoke = boom
    h.launch._end_job = boom
    h.boundary.job_active_processes = boom
    h.launch.start(job=h.job)
    state = h.launch.cancel(reason='host asked', outcome=0)
    assert state['state'] == ledger_mod.DEAD_UNVERIFIED
    assert state['quiescence'] == ('an ending step failed: revoke_admission OSError, '
                                   'end_job OSError; the Job count failed: OSError')
    ops = journal_ops(h.journal)
    assert ops[-1] == 'quarantine' and 'completion' not in ops and 'disposal' not in ops
    reason = journal_records(h.journal)[-1]['reason']
    assert reason.startswith('QUARANTINE_UNVERIFIED: ')
    assert 'revoke_admission OSError' in reason and 'end_job OSError' in reason
    assert 'the Job count failed: OSError' in reason and len(reason) <= 200
