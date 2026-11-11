"""T-1111: the highest-risk uncovered branches of `archeus/core/runtime.py`
lines 630-704 inclusive at HEAD 56d53504 (2026-11-10) — `request_stop`,
`wait` and `stop(drain=...)` — as tests.  The repository in this container is
the MXC integration branch; git is not installed here, so the line numbers
below were read from the working tree and match the card's named range.

Final selected branches (fail-closed/denial first, then boundaries, then
error paths, then concurrency orderings forced with seams/events):

  1. runtime.py:676-679  a failing quiesce must not stop the stop: every
     later shutdown stage (joins, pv20.close, db.close, core.json/lock, log
     handler, api=None, _done) still runs, and the error surfaces last
     (runtime.py:702-703).
  2. runtime.py:679 + 681-684 (combined fault)  quiesce fails AND every
     worker join times out: each late worker is still reported by name via
     log.warning, close is still attempted, and the FIRST error (quiesce's)
     is what stop raises.
  3. runtime.py:636-638 + 631-632  wait()'s timeout arm: `_done.wait(0.5)`
     returning False keeps the Ctrl+C window and re-waits; the exit code is
     read only after the release, and request_stop() from a thread releases.
  4. runtime.py:679 + 687-688 + 702-703  quiesce and activation-close both
     fail: the first failure is preserved through the DB cleanup
     (`closing = closing or error`), not overwritten by the later one.
  5. runtime.py:680-682  a spent join budget is clamped: `max(0.0, ...)`
     gives later joins exactly 0.0, never a negative timeout.
  6. runtime.py:681-682  `if worker is not None and ...`: a None worker
     neither joins nor consumes the shared deadline for the workers after it.
  7. runtime.py:689-691  the drain flag reaches the database (exactly one
     db.close with the right kwarg) despite activation failures.
  8. runtime.py:681-684  a worker join raising is never swallowed: stop
     stops right there — no activation close, no db.close, no lock release,
     no core.json removal — so a half-stopped Core cannot look clean.
  9. runtime.py:676-690  order, with a real dispatch thread gated by events:
     the dispatch resumes inside the join window and finds admission already
     closed (quiesce at 677 precedes the joins at 681-684, which precede the
     close at 686); a forbidden grant is denied, not merely "not called".
 10. runtime.py:671/689/692/696  a repeated stop after a partial failure
     (quiesce raised) resumes no admission and closes nothing twice: the
     cleared db, lock and log handler arms stay closed on the second call.

Replacements with evidence (card rule: probes already covered are replaced,
never reproduced):
  - probe "late exec worker cannot acquire grant after quiesce" is covered
    by tests/v1/unit/test_pv20_activate.py::
    test_no_listener_is_bound_after_the_activation_closed (after a full
    stop(), broker.issue raises BrokerClosed and no transport is created);
    replaced by branch 2 above.
  - probe "late verify worker cannot create Job after quiesce" is covered
    by tests/v1/unit/test_pv20_activate.py::
    test_a_late_worker_can_create_no_job_once_core_is_stopping (establish
    and _ensure_job raise IsolationClosed after quiesce, record kept, no
    Job); replaced by branch 3 above — wait()'s False arm is uncovered:
    test_the_engine_failure_wakes_the_wait_with_exit_code_3 sets _done
    before calling, so it runs zero iterations of the loop body and never
    pins the 0.5 s timeout or the early-return inversion.
  - the join-timeout warning and the shared deadline are covered by
    test_the_workers_share_one_quiesce_deadline_and_a_late_one_is_reported,
    the quiesce→joins→close order by
    test_stop_closes_admission_before_it_joins_and_the_workloads_after, and
    the order-only stop by test_stop_runs_start_backwards_... in
    tests/v1/unit/test_gaps_core_runtime.py — none of those runs a FAILING
    stage (per the review lead int10 #2: probe late-worker resource use and
    combined faults, not their existing happy path), so branches 2, 4, 7, 8
    and 10 and the faked-clock clamps 5 and 6 remain open.

Style follows tests/v1/unit/test_gaps_core_runtime.py: a bare Core built
with object.__new__, recorder objects, and the autouse `archeus_home`
fixture of tests/v1/conftest.py (a synthetic tmp_path home; no real
environment value is read, printed or copied — RULES.md rule 8). Nothing
here touches the filesystem, the network or a real process; the only real
threads are the test's own, gated by threading.Events with bounded waits,
released in finally and joined. The fake activation enforces exactly the
documented quiesce contract (archeus/core/pv20.py:56-62: "no grant is
issued ... no identity established, no Job created"), so no new policy is
invented.
"""

import logging
import threading

import pytest

from archeus.core import runtime

SILENT_WORKERS = ('metrics', 'automation', 'policy', 'plan', 'intent',
                  'knowledge', 'world')


class QuiesceFailure(RuntimeError):
    pass


class CloseFailure(RuntimeError):
    pass


class Admitted(RuntimeError):
    """Raised by the fake activation when a grant is refused after quiesce."""


class FakeWorker:
    """Stand-in for a loop thread: records stop/join; join replays `stuck`
    (True means 'did not stop within the deadline', runtime.py:682-684) or
    raises `boom` (a worker whose join itself fails)."""

    def __init__(self, log, name, stuck=False, boom=None):
        self.log, self.name = log, name
        self.stuck, self._boom = stuck, boom
        self.timeouts = []

    def stop(self):
        self.log.append('%s.stop' % self.name)

    def join(self, timeout):
        self.log.append('%s.join' % self.name)
        self.timeouts.append(timeout)
        if self._boom is not None:
            raise self._boom
        return self.stuck


class FakeActivation:
    """Enforces the documented quiesce contract (archeus/core/pv20.py:56-62):
    once quiesce() has run, no grant is issued. close() releases any worker
    parked in the join window, exactly like the real close ends the workloads
    Core holds; it never holds a join hostage."""

    def __init__(self, log, quiesce_error=None, close_error=None):
        self.log = log
        self._qe, self._ce = quiesce_error, close_error
        self.quiesced = self.closed = False
        self.close_count = 0
        self.grants = 0
        self.resume = threading.Event()

    def quiesce(self, *, deadline=None):
        self.log.append('quiesce')
        self.quiesced = True
        if self._qe is not None:
            raise self._qe

    def close(self):
        self.close_count += 1
        self.log.append('close')
        self.closed = True
        self.resume.set()
        if self._ce is not None:
            raise self._ce

    def grant(self):
        if self.quiesced or self.closed:                 # the documented refusal
            self.log.append('grant_denied')
            raise Admitted('the activation is quiesced: no grant is issued')
        self.grants += 1
        self.log.append('grant')
        return True


class FakeDb:
    def __init__(self, log):
        self.log, self.closed = log, []

    def close(self, *, drain):
        self.log.append('db.close')
        self.closed.append(drain)


class FakeLock:
    def __init__(self, log):
        self.log, self.releases = log, 0

    def release(self):
        self.log.append('lock.release')
        self.releases += 1


class _Sse:
    def __init__(self, log):
        self.log = log

    def close_all(self):
        self.log.append('sse.close_all')


class FakeApi:
    def __init__(self, log):
        self.log, self.stopping = log, False
        self.sse = _Sse(log)


class FakeClock:
    """The time.monotonic seam for runtime.py:680/682 only; anything else
    delegates to the real module so no other code can drift during the test."""

    def __init__(self, values=None, at=1000.0):
        import time as _t
        self._real, self.at = _t, at
        self.values = list(values) if values is not None else []
        self.now_calls = 0

    def monotonic(self):
        self.now_calls += 1
        return self.values.pop(0) if self.values else self.at

    def __getattr__(self, name):
        return getattr(self._real, name)


def stop_core(log, *, activation, exec_worker='auto', verify_worker='auto',
              loop_worker='auto'):
    """A bare Core (the health_core pattern of test_gaps_core_runtime.py)
    wired with the recorders this scenario names; returns (core, db, lock)."""
    core = object.__new__(runtime.Core)
    core._done = threading.Event()
    core.exit_code = 0
    core._log_handler = logging.NullHandler()
    core.api = FakeApi(log)
    core.server = None
    for name in SILENT_WORKERS:
        setattr(core, name, FakeWorker(log, name))
    for name, given in (('exec', exec_worker), ('verify', verify_worker),
                        ('loop', loop_worker)):
        setattr(core, name, FakeWorker(log, name) if given == 'auto' else given)
    core.pv20 = activation(log) if callable(activation) else activation
    core.db = FakeDb(log)
    core.lock = FakeLock(log)
    return core


@pytest.fixture
def core_json(monkeypatch):
    calls = []
    monkeypatch.setattr(runtime.discovery, 'remove_core_json',
                        lambda: calls.append('remove_core_json'))
    return calls


# ── fail-closed and denial paths ─────────────────────────────────────────────


def test_quiesce_failure_still_runs_every_shutdown_stage(core_json):
    # runtime.py:676-679 `try: self.pv20.quiesce() except Exception as error:
    # closing = error`. No existing test drives stop() with quiesce raising
    # (tests/v1/unit/test_pv20_activate.py only fails the CLOSE side, via a
    # broker that will not close, and its assertions stop at `isolation.closed
    # is True and core.db is None` — never the joins, the log handler or the
    # raised object). Catching-and-reraising here, or moving the later stages
    # behind the quiesce success, is caught: a Core whose broker died mid-stop
    # would otherwise keep run/core.lock, its writer thread and its log
    # handler open forever, and the operator would see no error at all until
    # the next Core reports the lock held.
    log = []
    core = stop_core(log, activation=FakeActivation(log, quiesce_error=QuiesceFailure('q')))
    db, lock = core.db, core.lock
    with pytest.raises(QuiesceFailure, match='q'):
        core.stop()
    names = [e for e in log if not e.startswith(SILENT_WORKERS)]
    assert names == ['sse.close_all', 'verify.stop', 'exec.stop', 'loop.stop',
                     'quiesce', 'exec.join', 'verify.join', 'loop.join',
                     'close', 'db.close', 'lock.release']
    assert core.pv20.close_count == 1 and db.closed == [True]
    assert core.db is None and core.lock is None and core.api is None
    assert core._log_handler is None and core._done.is_set()
    assert core_json == ['remove_core_json'] and lock.releases == 1


def test_a_quiesce_failure_and_stuck_joins_still_report_and_raise_first(
        core_json, monkeypatch, caplog):
    # runtime.py:679 + 681-684: the combined fault.
    # test_the_workers_share_one_quiesce_deadline_and_a_late_one_is_reported
    # counts its three warnings with a WORKING quiesce, and the broker test
    # joins real joinable workers; neither proves the join loop keeps warning
    # per stuck worker (with the worker's type name and QUIESCE_S) once
    # `closing` is already set, nor that quiesce's error is the one stop
    # raises. Break any of that and an operator loses the evidence that a
    # never-stopped worker still holds the machine while Core "stopped".
    caplog.set_level(logging.WARNING, logger='archeus.core')
    log = []
    monkeypatch.setattr(runtime, 'time', FakeClock())          # budget always 10.0
    act = FakeActivation(log, quiesce_error=QuiesceFailure('q'))
    core = stop_core(log, activation=act)
    for name in ('exec', 'verify', 'loop'):
        setattr(core, name, FakeWorker(log, name, stuck=True))
    db = core.db
    with pytest.raises(QuiesceFailure, match='q'):
        core.stop()
    assert caplog.text.count('did not stop') == 3
    assert 'FakeWorker' in caplog.text and '10' in caplog.text
    assert [w.timeouts for w in (core.exec, core.verify, core.loop)] == \
        [[10.0], [10.0], [10.0]]
    assert act.close_count == 1 and db.closed == [True]


# ── boundaries ───────────────────────────────────────────────────────────────


def test_wait_survives_its_timeout_ticks_and_a_threaded_request_stop():
    # runtime.py:636-638 `while not self._done.wait(0.5)` with 631-632. The
    # only existing wait() test (test_the_engine_failure_wakes_the_wait_...)
    # sets _done first, so it runs zero iterations of the loop body. A
    # scripted event pins the missed arms: dropping the 0.5 timeout (or
    # raising it) strands Ctrl+C — the fake records every timeout; inverting
    # the `not` returns the exit code on the first False, before any release;
    # and request_stop() from a real joined thread must end a real wait().
    core = object.__new__(runtime.Core)
    core.exit_code = 3

    class ScriptedDone:
        def __init__(self, results):
            self.results, self.timeouts = list(results), []

        def wait(self, timeout):
            self.timeouts.append(timeout)
            return self.results.pop(0)

    done = ScriptedDone([False, False, True])
    core._done = done
    assert core.wait() == 3
    assert done.timeouts == [0.5, 0.5, 0.5] and done.results == []

    core._done = threading.Event()
    core.exit_code = 0
    started = threading.Event()

    def stopper():
        started.set()
        core.request_stop()

    t = threading.Thread(target=stopper)
    t.start()
    try:
        assert started.wait(2.0) and core.wait() == 0
    finally:
        t.join(2.0)
    assert not t.is_alive()


def test_a_spent_join_budget_is_clamped_to_zero_never_negative(core_json, monkeypatch):
    # runtime.py:680-682 `end = time.monotonic() + QUIESCE_S` and
    # `worker.join(max(0.0, end - time.monotonic()))`. The existing deadline
    # test measures wall-clock SUMS (< 0.6), so it cannot pin the clamp: drop
    # max(0.0, ...) and the third worker is handed a negative timeout — a
    # silently non-blocking join, i.e. the shared budget of int10 #2 stops
    # being "zero for those left". A faked monotonic drains the budget before
    # the last join, and the recorded timeouts must then be [10.0, 5.0, 0.0].
    log = []
    clock = FakeClock(values=[1000.0,          # end = 1000.0 + QUIESCE_S = 1010.0
                              1000.0, 1005.0, 1012.0])        # -2.0 raw for loop
    monkeypatch.setattr(runtime, 'time', clock)
    core = stop_core(log, activation=FakeActivation(log))
    core.stop()
    got = core.exec.timeouts + core.verify.timeouts + core.loop.timeouts
    assert got == [10.0, 5.0, 0.0]
    assert all(t >= 0.0 for t in got)


def test_none_workers_join_nothing_and_spend_no_deadline(core_json, monkeypatch):
    # runtime.py:681-682 `if worker is not None and worker.join(...)`: with
    # an activation and no exec worker (the pv20 fixtures run verify-only
    # Cores), the False arm must skip BOTH the join and the budget read — the
    # short-circuit means time.monotonic is never consulted for the None
    # worker, so the workers after it keep the FULL budget. Removing the
    # guard is an AttributeError on None.join that escapes stop() before
    # db.close and the lock release; reading the clock before the guard would
    # drain the deadline the later workers still need. Both inversions fail
    # the monotonic-call count or the recorded timeouts below.
    log = []
    clock = FakeClock(values=[1000.0] * 4)
    monkeypatch.setattr(runtime, 'time', clock)
    core = stop_core(log, activation=FakeActivation(log), exec_worker=None)
    core.stop()
    assert clock.now_calls == 3                                # end + verify + loop
    assert core.verify.timeouts == [10.0] and core.loop.timeouts == [10.0]
    assert not [e for e in log if e.startswith('exec')]


# ── error paths ──────────────────────────────────────────────────────────────


def test_first_failure_survives_the_activation_close_and_db_cleanup(core_json):
    # runtime.py:687-688 `closing = closing or error` + 702-703.
    # test_a_broker_that_will_not_close_does_not_stop_the_stop_short has only
    # the close side failing, so the `or` never had to choose: turning it
    # into `closing = error` reports the cleanup symptom while the real
    # fault — quiesce refusing, e.g. a dead broker pipe — disappears from the
    # exit path. And skipping db.close when closing is set would strand the
    # writer and the lock. The quiesce error must be what stop raises, AFTER
    # db.close, core.json removal and lock release all happened.
    log = []
    act = FakeActivation(log, quiesce_error=QuiesceFailure('first'),
                         close_error=CloseFailure('second'))
    core = stop_core(log, activation=act)
    db = core.db
    with pytest.raises(QuiesceFailure, match='first'):
        core.stop()
    assert db.closed == [True] and core.db is None and core.lock is None
    assert act.close_count == 1
    assert log.index('db.close') > log.index('close')
    assert core_json == ['remove_core_json']


@pytest.mark.parametrize('drain, want', [(True, True), (False, False)],
                         ids=['default', 'kill'])
def test_the_drain_flag_reaches_the_database_despite_activation_failures(
        core_json, drain, want):
    # runtime.py:689-691 under failing activation stages. The drain kwarg is
    # only pinned by test_stop_runs_start_backwards... with pv20 is None
    # (line 671 skipped), and the broker test asserts `core.db is None` but
    # never WHAT db.close received. A quiesce that raises and a close that
    # raises must not skip or duplicate the one db.close, and drain=False —
    # the in-process stand-in for a kill, "queued commands are dropped, not
    # run" — must still reach it exactly once, keyword-only.
    log = []
    act = FakeActivation(log, quiesce_error=QuiesceFailure('q'),
                         close_error=CloseFailure('c'))
    core = stop_core(log, activation=act)
    db = core.db
    with pytest.raises(QuiesceFailure, match='q'):
        core.stop(drain=drain)
    assert db.closed == [want]
    assert log.count('db.close') == 1 and core.db is None
    assert act.close_count == 1


# ── concurrency orderings (seams/events, never sleeps) ──────────────────────


def test_a_worker_whose_join_raises_never_reports_a_clean_shutdown(core_json):
    # runtime.py:681-684: the join call is deliberately NOT wrapped. The
    # stuck-worker test replays join returning True; nothing drives join
    # RAISING. A well-meaning try/except around it (the obvious "harden the
    # shutdown" edit) would swallow the fault and fall through to close,
    # db.close and the lock release — an un-joined worker then runs while the
    # database and admission are gone under it, and the lock is handed to a
    # second Core over a writer that is still open. Assert the exception
    # surfaces AND the forbidden continuations are absent: stop halts at the
    # failed join with the activation close, db and lock all untouched.
    log = []
    act = FakeActivation(log)
    core = stop_core(log, activation=act,
                     exec_worker=FakeWorker(log, 'exec', boom=RuntimeError('join broke')))
    db, lock = core.db, core.lock
    with pytest.raises(RuntimeError, match='join broke'):
        core.stop()
    assert act.close_count == 0 and 'close' not in log
    assert db.closed == [] and core.db is not None          # fail-closed: still held
    assert lock.releases == 0 and core.lock is not None
    assert core_json == [] and core._log_handler is not None


def test_a_dispatch_resumed_at_the_teardown_boundary_finds_admission_closed(
        core_json, monkeypatch):
    # runtime.py:676-690, the order the whole PV-20 stop rests on, forced
    # with events instead of sleeps (probe 9). A real dispatch thread stands
    # for the exec worker's step in flight: it is parked until the join
    # window opens (join_entered, set inside worker.join at 682), and there
    # it attempts the activation grant; the join only ends once the dispatch
    # acted, so the attempt provably sits inside the stop window — after
    # quiesce (677), before close (686). Because quiesce ran before ANY join,
    # the attempt is denied per pv20.py:56-62; moving quiesce below the loop
    # lets the dispatch admit work after the workers were joined and before
    # close — the forbidden resource access — and this test fails on
    # outcomes/grants and the log order, not on a mock-call count.
    log = []
    act = FakeActivation(log)
    join_entered = threading.Event()
    dispatch_done = threading.Event()
    outcomes = []
    monkeypatch.setattr(runtime, 'time', FakeClock())

    class Gated:
        def __init__(self):
            self.timeouts = []

        def stop(self):
            log.append('gated.stop')

        def join(self, timeout):
            self.timeouts.append(timeout)
            log.append('exec.join')
            join_entered.set()                        # the step resumes NOW
            return not dispatch_done.wait(2.0)        # the step ended inside

    def dispatch():
        try:
            if join_entered.wait(2.0):
                log.append('dispatch_grant')
                try:
                    act.grant()
                    outcomes.append('granted')
                except Admitted:
                    outcomes.append('denied')
        finally:
            dispatch_done.set()                       # never hold the join

    gated = Gated()
    core = stop_core(log, activation=act, exec_worker=gated,
                     verify_worker=None, loop_worker=None)
    db = core.db
    t = threading.Thread(target=dispatch)
    t.start()
    try:
        core.stop()
    finally:
        join_entered.set()                            # bounded waits, always released
        dispatch_done.set()
        t.join(2.0)
    assert not t.is_alive() and outcomes == ['denied']
    assert act.grants == 0 and 'grant' not in log
    assert log.index('quiesce') < log.index('dispatch_grant') < log.index('close')
    assert gated.timeouts == [10.0]
    assert act.closed is True and db.closed == [True]


def test_a_second_stop_after_a_partial_failure_closes_nothing_twice(core_json):
    # runtime.py:671/689/692/696 on the SECOND stop. The order test's second
    # stop() runs with pv20 left None and nothing failed the first time, so
    # the cleared-db/cleared-lock/cleared-handler arms are untested after a
    # PARTIAL failure (quiesce raised, close succeeded, db already cleared).
    # The forbidden states: a second db.close on the cleared database (a
    # double drain of a writer that is gone), a second remove_core_json +
    # release for a lock no longer ours (deleting the NEXT Core's core.json),
    # and any admission reopen — grant must stay denied across both stops.
    log = []
    act = FakeActivation(log, quiesce_error=QuiesceFailure('q'))
    core = stop_core(log, activation=act)
    db, lock = core.db, core.lock
    with pytest.raises(QuiesceFailure, match='q'):
        core.stop()
    first_db_closes, first_releases = list(db.closed), lock.releases
    with pytest.raises(QuiesceFailure, match='q'):            # stop still reports it
        core.stop()
    assert first_db_closes == [True] and first_releases == 1
    assert db.closed == [True] and lock.releases == 1          # nothing twice
    assert core_json == ['remove_core_json']
    assert core.db is None and core.lock is None and core.api is None
    assert core._log_handler is None and core._done.is_set()
    assert act.quiesced and act.closed
    with pytest.raises(Admitted):                              # never reopened
        act.grant()
    assert act.grants == 0
