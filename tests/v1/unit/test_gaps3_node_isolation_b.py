"""T-1114: the highest-risk uncovered branches of `archeus/node/isolation.py` lines
1316-1467 (HEAD 56d53504, 2026-11-10) — the confined verifier attempt's poll, its
unwind on a stop, and the verdict the shutdown leaves behind. Round B of the gap
cards; nothing here imports another `test_gaps3` file or depends on queue order.

The selected branches, in the order of the card's risk list (fail-closed and denial
first, then boundaries, then error paths, then concurrency orderings): the ten of the
card's probes that hold up as uncovered, plus entry 11, which replaces the one probe
that did not:

  1 `run_confined` 1389-1391   a check launched after Core stopped never polls the
                              child it started (`wait` is reached only after the stop
                              is read, so `child.waits` stays empty)
  2 `run_confined` 1392-1393   a deadline the launch itself ate still polls with zero:
                              the argument is clamped, never negative (Windows reads a
                              negative poll timeout as INFINITE)
  3 `run_confined` 1389-1393   Core stopping inside the second poll ends the run at
                              that poll: exactly two waits, never a third
  4 `run_confined` 1389-1391 + 1335/1344 + 1230 two concurrent confined checks, one
                              Core stop: each ends at its own poll, closes its own Job,
                              records nothing, and stays reclaimable
  5 `run_confined` 1396,1424   a drain that faulted is never read as a clean exit: the
                              fault is the error, no exit code is read after it, and
                              the Job is closed only after the child ended its launch
  6 `run_confined` 1365-1371   an establishment refused because Core is stopping
                              (`IsolationClosed`, not `IsolationUnavailable`) propagates
                              unrecorded, creates nothing, and leaves the attempt consumed
  7 `run_confined` 1406-1416   a stopped run whose child *and* Job both fault keeps the
                              stop error and still closes the Job (kill-on-close)
  8 `run_confined` 1335/1344   the confined set is cleared by the unwind, so the sweep
                              still reclaims the profile instead of sparing it forever
  9 `run_confined` 1417-1423   a child that will not end its own launch still loses its
                              Job, and the run is a recorded `shutdown_failed`, never an
                              exit code
 10 `run_confined` 1422-1423   a timeout verdict is not replaced by the failing shutdown
                              that followed it (`error or`, both failure classes)
 11 `run_confined` 1375-1377   the accounting roots of a nested checkout/scratch pair:
                              the outer root is never dropped and bytes are never twice
                              counted

Entries 4 and 8 are the card's probes 9 and 10, which both land on the cleared-set
branch; entry 11 replaces card probe 7, whose shape the accounting loop already covers.

Nothing here starts a process, opens a Job, loads a DLL or touches a real security
descriptor: every OS answer is the scripted `Boundary` of `test_confined_run.py` (the
`FakeBoundary` of `test_pv20_isolation.py` with an event log), and the OS tripwire
imported below fails the test that reaches a real primitive. Ordering is
forced with fake clocks, boundary event logs and `threading.Event` seams with bounded
waits and `finally` releases — never with a timing sleep — and every thread started is
joined. Each test names the source branch whose removal or inversion it catches.
"""

import os
import threading

import pytest

from archeus.node import isolation as iso
# os_tripwire is armed for this file by the autouse fixture below: no test here may
# reach a real process, Job, handle or security-descriptor primitive
from v1.unit.test_pv20_isolation import (FakeNode, _verify_key,  # noqa: F401
                                         make_verifier_request, os_tripwire)
# the scripted process, the counting boundary and the fake clock, reused as they stand
from v1.unit.test_confined_run import Boundary, Child, Clock  # noqa: F401

#: a synthetic bound: one writer over it is the end of the run, one under it is not
GROWTH_BOUND = 1000


@pytest.fixture(autouse=True)
def armed(os_tripwire):  # noqa: F811 - requesting the imported fixture arms it here
    """The real-primitive tripwire of `test_pv20_isolation`, requested so that it runs
    for every test in this file too (an import alone would not arm it)."""
    return os_tripwire


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    """No test here waits on a real bound: the poll step and the quiescence wait are
    shortened, so every bounded fake wait stays far under a second and nothing sleeps."""
    monkeypatch.setattr(iso, 'EXIT_WAIT_S', 0.05)
    monkeypatch.setattr(iso, 'CONFINED_POLL_S', 0.02)


class DrainChild(Child):
    """A `mxc_verifier.ConfinedChild`-shaped child: it ends its own launch through
    `cancel`, which needs the Job still open (mxc_verifier.py:60-68), and a drain that
    stopped on a bound or a transport fault carries `fault` (mxc_verifier.py:46-58),
    whose `wait` then reports an exit of 1 for it (mxc_verifier.py:70-78)."""

    def __init__(self, step=None, fault=None, cancel_fail=None, log=None):
        super().__init__(step)
        self.fault = fault
        self.cancel_fail = cancel_fail
        self.cancelled, self.log = [], (log if log is not None else [])

    def cancel(self, reason):
        self.cancelled.append(reason)
        self.log.append('cancel')                      # ordered against the Job's close
        if self.cancel_fail is not None:
            raise self.cancel_fail


def _stopping(authority):
    """A child step: Core reached its stop while this poll was in flight."""
    def step(child):
        authority.close_admission()
    return step


def _nested_request(key, root):
    """A verifier inventory whose scratch row sits *inside* its checkout row: the §3.4
    invariant holds for a verifier on separated rows only, so this is a shape a plan
    really can hand Core, and the accounting of 1375-1377 must survive it."""
    def d(name):
        p = os.path.join(root, name)
        os.makedirs(p, exist_ok=True)
        return p
    checkout = d('checkout')
    scratch = os.path.join(checkout, 'scratch')
    os.makedirs(scratch, exist_ok=True)
    return iso.IsolationRequest(execution_id=key, workspace=checkout,
                                grants=(iso.Grant(checkout, 'rw', 'checkout'),
                                        iso.Grant(scratch, 'rw', 'scratch'),
                                        iso.Grant(d('toolchain'), 'rx', 'toolchain')),
                                core_state=d('core_state'))


@pytest.fixture
def run(tmp_path):
    """`run(boundary, ...)` -> (result, recorded, authority, request, at_record) for one
    attempt over the verifier inventory built under `tmp_path/a<n>`. `at_record` holds
    what the child and the boundary had already done *when the verdict was written*, so
    the teardown's own reads cannot soften an ordering assertion."""
    attempt = [0]

    def go(boundary, *, authority=None, timeout=5, keep=1024, record=None, request=None,
           prepare=None):
        n = attempt[0]
        attempt[0] += 1
        a = authority or iso.Isolation(FakeNode(), boundary=boundary)
        req = request or make_verifier_request(_verify_key(n), str(tmp_path / ('a%d' % n)))
        out, stdin = str(tmp_path / ('out%d.log' % n)), str(tmp_path / ('stdin%d' % n))
        for f in (out, stdin):
            open(f, 'wb').close()
        recorded, at_record = [], []

        def sink(result):
            boundary.events.append('record')
            at_record.append({'waits': list(boundary.child.waits),
                              'events': list(boundary.events)})
            recorded.append(dict(result))
            if record:
                record(result, req)
        result = a.run_confined(req, ['tool', 'check'], env={'PATH': 'x'}, timeout=timeout,
                                out_path=out, stdin_path=stdin, record=sink, keep=keep,
                                prepare=prepare)
        return result, recorded, a, req, at_record
    return go


# ── the poll and the stop: a check never outlives the Core that started it ──────

def test_a_check_launched_after_core_stopped_never_polls_the_child(run):
    """isolation.py:1389-1391 (the closed poll of 6027a5f9) — the stop is read *before*
    the child is waited on, so a check whose launch finished after `close_admission`
    never polls the process it had already started: `child.waits` stays empty. Moving
    the `if self.closed` test after the `child.wait` (or checking it once outside the
    loop) leaves `test_a_confined_check_running_when_core_stops_ends_at_its_next_poll`
    green, because that one stops the Core from *inside* the first wait, where a poll
    has been spent either way."""
    b = Boundary()
    a = iso.Isolation(FakeNode(), boundary=b)
    started = []
    asked = b.launch

    def launch(argv, **kw):
        child = asked(argv, **kw)                    # the process exists from here on
        started.append(child)
        a.close_admission()                          # Core.stop reached its admission
        return child
    b.launch = launch
    with pytest.raises(iso.IsolationClosed):
        run(b, authority=a)
    child, = started
    assert child.waits == []                         # not one poll of it
    assert len(b.launch_calls) == 1                  # it was launched, and ...
    assert b.closed == [{'job': _verify_key()}]      # ... it died with the Job it ran in
    assert b.events == ['close']                     # no count, no verdict, no delete
    assert a.record(_verify_key()) is not None       # left standing for the sweep
    assert a._confined == set() and a._admitted == set()


def test_a_deadline_the_launch_ate_still_polls_with_zero(run, monkeypatch):
    """isolation.py:1392-1393 — `min(CONFINED_POLL_S, max(0.0, deadline - now))`: a
    launch that outlasted the whole bound leaves a negative budget, and the poll that
    follows is `0.0`, never `-60`. Dropping the `max` hands a negative timeout to
    `Popen.wait`, whose Windows path reads `-1` as INFINITE: the confined check would
    then poll forever past its deadline, inside a Job Core is waiting to close."""
    clock = Clock()
    monkeypatch.setattr(iso, 'time', clock)
    b = Boundary()
    a = iso.Isolation(FakeNode(), boundary=b)
    asked = b.launch

    def launch(argv, **kw):
        clock.t += 60                                # the launch itself ate the bound
        return asked(argv, **kw)
    b.launch = launch
    result, recorded, _a, req, at = run(b, authority=a, timeout=5)
    assert at[0]['waits'] == [0.0]                   # clamped: the poll was asked for zero
    assert [w for w in b.child.waits if w is not None and w < 0] == []
    assert result['error'] == 'timed out after 5s'   # a late exit is a timeout, not a pass
    assert result['exit_code'] is None               # and its exit code is never read
    assert 'count' not in b.events                   # the Job was never asked to be empty
    assert b.events == ['close', 'record', 'delete'] and recorded == [result]
    assert a.held_job(req.execution_id) is None


def test_a_core_that_stops_during_the_second_poll_stops_at_that_poll(run):
    """isolation.py:1389-1393 — the stop is re-read on every iteration, so a Core that
    stops while the *second* poll is in flight ends the run there: two waits, never a
    third. The existing stop test only ever spends one poll, so a hoisted-once check
    would still pass it; here the third poll is what this assertion refuses."""
    in_poll, release = threading.Event(), threading.Event()

    def step(child):
        if len(child.waits) >= 2:                    # the poll Core is stopping inside
            in_poll.set()
            assert release.wait(5), 'the stop never released the second poll'
    b = Boundary(child=Child(step=step))
    a = iso.Isolation(FakeNode(), boundary=b)
    child = b.child

    def stopper():
        try:
            if in_poll.wait(5):                      # bounded: it cannot dangle here
                a.close_admission()
        finally:
            release.set()                            # released whatever happened
    thread = threading.Thread(target=stopper)
    thread.start()
    try:
        with pytest.raises(iso.IsolationClosed):
            run(b, authority=a, timeout=1)
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()                     # it was joined, not left behind
    assert child.waits == [iso.CONFINED_POLL_S] * 2  # exactly two: it stopped at that one
    assert b.events == ['close'] and a._confined == set()
    assert a.record(_verify_key()) is not None       # nothing recorded, nothing deleted


# ── two attempts, one stop: each ends alone and stays reclaimable ───────────────

def test_two_confined_checks_stopped_together_keep_their_own_reclaimable_profile(
        tmp_path):
    """isolation.py:1389-1391 with 1335/1344 and 1230 — two independent attempts run
    under one authority; one Core stop ends both at their own polls. Each closes its
    own Job, records nothing, and — once the `finally` has cleared the confined set —
    is still a sweep's job: a `_confined` entry that survived the unwind would spare
    that identity forever, and `reclaim` would silently never name it."""
    b = Boundary()
    a = iso.Isolation(FakeNode(), boundary=b)
    keys = [_verify_key(0), _verify_key(1)]
    by_profile = {iso.validated_profile(k): k for k in keys}
    children, in_poll, release, raised, recorded = {}, {}, {}, {}, {0: [], 1: []}
    for key in keys:
        in_poll[key], release[key] = threading.Event(), threading.Event()

    def step(child):
        in_poll[child.key].set()                     # this attempt is inside its poll
        assert release[child.key].wait(5), 'its poll never ended'
    asked = b.launch

    def launch(argv, **kw):
        key = by_profile[kw['profile']]
        child = Child(step=step)
        child.key = key
        children[key] = child
        asked(argv, **kw)                            # the boundary records the launch ...
        return child                                 # ... and each attempt gets its own
    b.launch = launch

    def go(n):
        key = keys[n]
        req = make_verifier_request(key, str(tmp_path / ('a%d' % n)))
        out, stdin = str(tmp_path / ('out%d.log' % n)), str(tmp_path / ('stdin%d' % n))
        for f in (out, stdin):
            open(f, 'wb').close()

        def sink(result):
            recorded[n].append(dict(result))
        try:
            a.run_confined(req, ['tool', 'check'], env={'PATH': 'x'}, timeout=5,
                           out_path=out, stdin_path=stdin, record=sink, keep=1024)
        except BaseException as err:                 # reported to this thread's owner
            raised[n] = err
    threads = [threading.Thread(target=go, args=(n,)) for n in (0, 1)]
    for thread in threads:
        thread.start()
    try:
        for key in keys:
            assert in_poll[key].wait(5), '%s never reached its own poll' % key
        assert [len(children[k].waits) for k in keys] == [1, 1]   # both inside poll one
        a.close_admission()                                        # one Core, one stop
        for key in keys:
            release[key].set()
    finally:
        for key in keys:
            release[key].set()
        for thread in threads:
            thread.join(5)
    assert [t.is_alive() for t in threads] == [False, False]
    assert [type(raised.get(n)) for n in (0, 1)] == [iso.IsolationClosed] * 2
    assert [list(children[k].waits) for k in keys] == [[iso.CONFINED_POLL_S]] * 2
    assert recorded == {0: [], 1: []}                # neither wrote a verdict
    assert sorted(b.closed, key=str) == [{'job': keys[0]}, {'job': keys[1]}]
    assert 'delete' not in b.events                  # neither profile was touched
    assert a._confined == set() and a._admitted == set()
    for key in keys:                                 # kill-on-close: each tree went with
        children[key].returncode = 0                 # the Job Core closed for it
    assert sorted(a.reclaim(())) == sorted(keys)     # the sweep can still act on both
    assert sorted(b.deleted) == sorted(iso.validated_profile(k) for k in keys)


# ── the faulted drain: an error result, never a verdict ────────────────────────

@pytest.mark.parametrize('label,fault,code,reads_code', [
    # the drain stopped on a transport fault and reports an exit of 1 for it: the run
    # is that fault, its exit code is never read back from the child, and the Job is
    # closed only after that child ended its own launch
    ('drain-fault', 'launcher_failed: the transport died (synthetic)', 1, False),
    # the same child with a drain that came back clean (`fault` still the empty string
    # it is born as): the `or` chain moves past it, the run is a pass, and its code is
    # read exactly once, with a zero timeout
    ('drain-clear', '', 0, True),
], ids=['drain-fault', 'drain-clear'])
def test_a_faulted_drain_is_never_the_verdict_of_a_clean_run(run, label, fault, code,
                                                             reads_code):
    """isolation.py:1396 with 1424 — `getattr(child, 'fault', None)` sits in the `or`
    chain before the deadline: a faulted drain ends the loop with its own reason, so no
    quiescence is asked and no exit code is read (a faulted `ConfinedChild.wait` answers
    1, mxc_verifier.py:78) while the profile is still released. Ignoring `fault`, or
    reading the code after the error, gives this run an `exit_code` it never earned."""
    b = Boundary()
    child = DrainChild(step=lambda c: setattr(c, 'returncode', code), fault=fault,
                       log=b.events)
    b.child = child
    result, recorded, a, req, at = run(b)
    # one poll; and the exit code is read again, once, only when there is no error
    assert at[0]['waits'] == [iso.CONFINED_POLL_S] + ([0] if reads_code else [])
    assert result['error'] == (fault or None)
    assert result['exit_code'] == (None if fault else 0)
    assert child.cancelled == [fault or 'the verifier run ended']
    assert recorded == [result] and 'record' in b.events and 'delete' in b.events
    assert a.held_job(req.execution_id) is None
    if fault:
        assert b.events[:2] == ['cancel', 'close']   # the loop ended on the fault, so ...
        assert 'count' not in b.events               # ... quiescence was never asked
    else:
        assert b.events[:3] == ['count', 'cancel', 'close']   # a clean one asked first
    # and in both: the drain ended its own launch while the Job was still open
    assert b.events.index('cancel') < b.events.index('close')


def test_a_check_refused_because_core_is_stopping_records_nothing_and_is_spent(run,
                                                                                tmp_path):
    """isolation.py:1365-1371 — `establish` answers `IsolationClosed`, which is *not* an
    `IsolationUnavailable`, so it is never turned into the recorded `isolation: ...`
    result the `except` below hands back: it propagates, no identity, Job or process is
    made, and the attempt stays consumed because `_admit` had already written its marker.
    A broad `except Exception` there would record a verdict-shaped refusal for a run
    that never began and let the same attempt be started again after the restart."""
    b = Boundary()
    a = iso.Isolation(FakeNode(), boundary=b)
    key = _verify_key()

    def prepare():                                   # the caller's file work, then stop
        a.close_admission()
        return {'PATH': 'x'}
    with pytest.raises(iso.IsolationClosed):
        run(b, authority=a, prepare=prepare)
    assert b.created == [] and b.closed == [] and b.launch_calls == []
    assert a.held_jobs() == {} and a.record(key) is None
    assert b.events == []                            # no count, no close, no delete
    assert a._admitted == set() and a._confined == set()
    # and the half-attempt can never be started again: its marker survived the stop, so
    # the restarted attempt is refused before a file of it is written, with no output
    root = str(tmp_path / 'late')
    os.makedirs(root, exist_ok=True)
    out, stdin = os.path.join(root, 'late.log'), os.path.join(root, 'late.stdin')
    for f in (out, stdin):
        open(f, 'wb').close()
    seen = []
    again = a.run_confined(make_verifier_request(key, root), ['tool'], env={'PATH': 'x'},
                           timeout=5, out_path=out, stdin_path=stdin, record=seen.append,
                           keep=1024)
    assert again['error'] == 'isolation: attempt_consumed' and seen == [again]
    assert again['output'] == b'' and again['confinement'] == {}
    assert b.created == [] and b.launch_calls == []


# ── the unwind: nothing that fails on the way out is allowed to hide the stop ───

def test_a_stopped_run_whose_child_and_job_both_fault_keeps_the_stop_error(run):
    """isolation.py:1406-1416 (with 1475-1479) — the stop raises while the child's own
    `cancel` raises `OSError` and the Job's close raises `IsolationUnavailable`: the
    stop is what propagates, and the Job is closed anyway by the `finally`. Neither of
    the existing unwind tests has a child with a `cancel` at all, so a close skipped
    when the child's end fails — leaving a live tree in a Job nobody holds — would pass
    them, and this one does not."""
    b = Boundary()
    a = iso.Isolation(FakeNode(), boundary=b)
    child = DrainChild(step=_stopping(a), log=b.events,
                       cancel_fail=OSError('TerminateProcess refused (synthetic)'))
    b.child = child
    b.close_fail = iso.IsolationUnavailable('job_close', 'CloseJobObject denied (synthetic)')
    with pytest.raises(iso.IsolationClosed):         # not the OSError, not the refusal
        run(b, authority=a)
    assert child.waits == [iso.CONFINED_POLL_S]      # one poll, then the stop
    assert child.cancelled == ['the verifier run failed']    # the unwind, not the end path
    assert b.events == ['cancel', 'close']           # the Job still died with the child in it
    assert b.closed == [{'job': _verify_key()}]
    assert 'record' not in b.events and 'delete' not in b.events
    assert a.record(_verify_key()).state == 'established'    # left for reclaim, intact
    assert a._confined == set() and a._admitted == set()


def test_a_run_the_stop_ended_is_still_the_sweeps_work(run):
    """isolation.py:1335 with 1344 and 1230 — `reclaim` spares every key in
    `_confined`; the `finally` that empties it runs on the `IsolationClosed` path too,
    or the profile of an attempt that died with a stopped Core is spared by every pass
    for the life of the node. `test_reclaim_spares_an_attempt_this_core_is_running`
    covers the spare on a clean run only, and never asserts the un-spare after a raise."""
    b = Boundary()
    a = iso.Isolation(FakeNode(), boundary=b)
    b.child = Child(step=_stopping(a))
    key = _verify_key()
    with pytest.raises(iso.IsolationClosed):
        run(b, authority=a)
    assert a._confined == set()                      # not one key held back
    b.child.returncode = 0                           # kill-on-close: its tree went with it
    assert a.reclaim(()) == [key]                    # the sweep names it, and acts
    assert b.deleted == [iso.validated_profile(key)]
    assert a.record(key) is None


# ── the shutdown the verdict must survive ───────────────────────────────────────

def test_a_child_that_will_not_end_still_loses_the_job_it_ran_in(run):
    """isolation.py:1417-1423 (with 1475-1479) — `self._close_job(key)` is in the
    `finally` of the child's own end: a `cancel` that raises `OSError` still closes the
    Job (kill-on-close), turns the run into a recorded `shutdown_failed`, and reads no
    exit code for a tree nobody confirmed gone. No existing test has a child with a
    `cancel`, so a plain sequence there — close skipped, or the code read anyway —
    would leave a confined tree running and record a verdict for it."""
    b = Boundary()
    child = DrainChild(log=b.events,
                       cancel_fail=OSError('TerminateProcess refused (synthetic)'))
    b.child = child
    result, recorded, a, req, at = run(b)
    assert b.events[:3] == ['count', 'cancel', 'close']   # the child failed, the Job went
    assert b.closed == [{'job': req.execution_id}]
    assert result['error'].startswith('shutdown_failed:')
    assert 'TerminateProcess refused' in result['error']
    assert result['exit_code'] is None               # its code is never claimed
    assert at[0]['waits'] == [iso.CONFINED_POLL_S]   # the one poll, and no code read
    assert recorded == [result] and 'delete' in b.events
    assert a.held_job(req.execution_id) is None


@pytest.mark.parametrize('label,failure', [
    ('unavailable', iso.IsolationUnavailable('job_close', 'CloseJobObject denied (synthetic)')),
    ('os-error', OSError('CloseJobObject said no (synthetic)')),
], ids=['unavailable', 'os-error'])
def test_a_timed_out_verdict_outlives_the_shutdown_that_failed_after_it(run, monkeypatch,
                                                                        label, failure):
    """isolation.py:1422-1423 — `error = error or 'shutdown_failed: %s'`: the timeout
    the loop already found is the verdict, and a shutdown that fails afterwards cannot
    replace it, whatever the class of that failure. `error = 'shutdown_failed: ...'`
    would rewrite a run Core bounded into one whose Job would not close — a different
    fact for the reviewer, and a lost deadline. The existing shutdown test has *no*
    error of its own, so only the empty `error or` side of it is pinned today."""
    clock = Clock()
    monkeypatch.setattr(iso, 'time', clock)
    b = Boundary()
    b.close_fail = failure

    def late(child):
        clock.t += 60                                # the whole poll budget went by
        child.returncode = 0                         # and the exit landed after it
    b.child.step = late
    result, recorded, a, req, _at = run(b, timeout=5)
    assert result['error'] == 'timed out after 5s'   # the deadline, not the close's reason
    assert 'shutdown_failed' not in result['error']
    assert result['exit_code'] is None and 'count' not in b.events
    assert b.events == ['close', 'record', 'delete'] and recorded == [result]
    assert a.held_job(req.execution_id) is None


# ── accounting roots: a writable row Core is not watching is no bound at all ────

@pytest.mark.parametrize('label,where,written,error', [
    # the outer row is the only one walked: bytes written into the checkout itself are
    # seen (drop the outer root instead and this run passes clean, unbounded)
    ('outer-writer', 'checkout', GROWTH_BOUND + 500, 'grew %d bytes'),
    # and seen once: bytes under the nested row are not counted twice (count the pair
    # twice and the number this verdict names doubles)
    ('inner-writer', 'scratch', GROWTH_BOUND + 500, 'grew %d bytes'),
    # the same walk under the bound is a run, not a refusal: 1376-1377 keeps a root
    # that is not inside another, and never the other way round
    ('under-bound', 'scratch', GROWTH_BOUND - 500, None),
], ids=['outer-writer', 'inner-writer', 'under-bound'])
def test_a_nested_scratch_row_never_blinds_the_accounting_to_its_checkout(
        run, monkeypatch, tmp_path, label, where, written, error):
    """isolation.py:1375-1377 — `roots` keeps a row that is not inside another row: a
    verifier plan whose scratch lies inside its checkout is accounted by the checkout
    alone, exactly once. Invert the filter (keep the nested row) and a writer in the
    checkout runs unbounded; drop the dedupe and the same run is refused for bytes it
    never wrote. Both are checked here on the number the verdict names."""
    monkeypatch.setattr(iso, 'CONFINED_GROWTH_MAX', GROWTH_BOUND)
    key = _verify_key()
    req = _nested_request(key, str(tmp_path / 'nested'))
    target = os.path.join(req.grant_for(where).path, 'written.bin')

    def plant(child):
        with open(target, 'wb') as f:
            f.write(b'v' * written)
        child.returncode = 0
    b = Boundary(child=Child(step=plant))
    result, recorded, _a, _req, _at = run(b, request=req, timeout=5)
    if error is None:
        assert result['error'] is None and result['exit_code'] == 0
    else:
        assert result['error'] == 'limit_exceeded: the checkout and scratch ' + (
            error % written)
        assert result['exit_code'] is None            # a faulted tree claims no code
    assert recorded == [result] and 'delete' in b.events
