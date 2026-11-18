"""T-1237 — the ten highest-risk uncovered branches of `archeus/node/isolation.py`
lines **107-122 inclusive** (tip 6bbd3b44): the OS-held record lock — acquisition,
timeout, release. Denial/fail-closed first, then boundaries, then error paths. No source
file is edited by this card; the slice is exactly:

    106  @contextlib.contextmanager
    107  def _record_lock(path):
    108      fd = os.open(path + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
    109      end = time.monotonic() + RECORD_LOCK_WAIT_S
    110      while True:
    111          try:
    112              discovery._try_lock(fd)
    113              break
    114          except OSError:
    115              if time.monotonic() >= end:
    116                  os.close(fd)
    117                  raise OSError('the isolation record %s is busy' % path) from None
    118              time.sleep(0.02)
    119      try:
    120          yield
    121      finally:
    122          discovery.CoreLock(fd).release()

(the numbering above is the file's own; the card's slice 107-122 is `def _record_lock` through
the release, with the decorator at 106.)

Selected branches (each test repeats its own in its docstring; these are candidate
branches read off the source, not measured coverage):
  1. 115 contention then success just before the deadline: exactly one yield, and the
     body never sees the descriptor unlocked.
  2. 115 busy until exactly `end`: the `>=` boundary closes the fd exactly once and the
     body is never entered.
  3. 108 `os.open` fails: its own error propagates, with no `_try_lock`, no release, no
     body and no fabricated descriptor cleanup.
  4. 112 acquisition precedes the body and every attempt reuses the one descriptor.
  5. 122 a `BaseException` from the body survives and `CoreLock.release` still runs once.
  6. 122 an `OSError` from the body still releases through `CoreLock`, and the slice never
     closes the fd itself.
  7. 118 every contended attempt but the last sleeps the poll interval.
  8. 109 one absolute deadline computed on entry, never reset by a contended attempt.
  9. 108 the lock path is the record path plus `.lock`, opened O_RDWR|O_CREAT mode 0o600,
     and the only destination is the tmp_path record home.
 10. 122 a failing release is never a success, and a failing release wins over a failing
     body with the body kept as context (no exception grouping assumed).

Everything is a seam: `os.open`/`os.close`, `time.monotonic`/`time.sleep`,
`discovery._try_lock` and `discovery.CoreLock(fd).release()` are all replaced per test,
the record home is patched to `tmp_path`, and the autouse tripwire below fails the run if
a real advisory lock, a real `CoreLock.release` or any native primitive (msvcrt, Win32
profile/Job/process entry points) is reached. No thread, no subprocess, no sleep, no real
network, no real home, no environment value; it runs unchanged on Linux and Windows.
"""

import os
import sys
import time as _time_module

import pytest

from archeus.core.domain import ids
from archeus.infra import discovery
from archeus.node import isolation as iso

#: the poll interval the slice must keep (118); it is asserted, never slept
POLL_S = 0.02
#: how many first attempts answer "busy" forever (`busy=-1`) in these fixtures
ALWAYS_BUSY = -1

NATIVE_ENTRY_POINTS = ('_CreateAppContainerProfile', '_DeleteAppContainerProfile',
                       '_GetSecurityInfoByNameW', '_CreateProcessW', '_CreateJobObjectW',
                       '_AssignProcessToJobObject', '_TerminateProcess', '_CloseHandle',
                       '_SetInformationJobObject', '_ResumeThread', '_OpenProcess')


@pytest.fixture(autouse=True)
def no_real_win32(monkeypatch):
    """The belt: this file has one reason to touch the OS and it is faked, so reaching a
    real primitive is a fixture mistake, not a passing test."""
    hits = []

    def trip(name):
        def gone(*a, **k):
            hits.append(name)
            raise AssertionError('the real %s was reached' % name)
        return gone

    for name in NATIVE_ENTRY_POINTS:
        monkeypatch.setattr(iso, name, trip(name), raising=False)

    def trip_try_lock(fd):
        hits.append('discovery._try_lock')
        raise AssertionError('the real advisory lock was reached')

    def trip_release(self):
        hits.append('discovery.CoreLock.release')
        raise AssertionError('the real CoreLock.release was reached')

    monkeypatch.setattr(discovery, '_try_lock', trip_try_lock)
    monkeypatch.setattr(discovery.CoreLock, 'release', trip_release)
    before = set(sys.modules)
    yield hits
    assert hits == [], 'a real lock/native primitive was reached: %r' % (hits,)
    assert 'msvcrt' not in set(sys.modules) - before, 'msvcrt was loaded by this test'


@pytest.fixture
def record_home(tmp_path, monkeypatch):
    """Core's record store moved under tmp_path, so a lock path derived from a record path
    is observable and nothing can reach the real home."""
    home = str(tmp_path / 'run' / 'isolation')
    monkeypatch.setattr(iso, 'isolation_dir', lambda: home)
    monkeypatch.setattr(iso, 'isolation_state',
                        lambda key: os.path.join(home, '%s.json' % key))
    monkeypatch.setattr(iso, 'quarantine_log', lambda: os.path.join(home, 'quarantine.jsonl'))
    monkeypatch.setattr(iso, 'verify_consumed', lambda key: os.path.join(home, 'consumed'))
    return home


@pytest.fixture
def record_path(record_home):
    """One execution record's path, as Core names it (the slice only ever adds `.lock`)."""
    return iso.isolation_state(ids.new_id('execution'))


class _Os:
    """`isolation.py`'s `os` boundary: opens are answered from a counter and recorded,
    closes are recorded. No descriptor is ever created or closed for real."""

    def __init__(self, seam, open_error=None):
        self.seam, self.open_error, self._next_fd = seam, open_error, 987

    def open(self, path, flags, mode=0o777):
        self.seam.open_calls.append((path, flags, mode))
        self.seam.order.append('open')
        if self.open_error is not None:
            raise self.open_error
        self._next_fd += 1
        self.seam.fd = self._next_fd
        return self._next_fd

    def close(self, fd):
        self.seam.closes.append(fd)
        self.seam.order.append('close')

    def __getattr__(self, name):
        return getattr(os, name)               # everything else the module may ask the OS


class _Time:
    """`isolation.py`'s clock: `monotonic()` drains a scripted list (a fourth reading
    than the branch is allowed is a fixture-visible failure, never a hang) and `sleep()`
    is recorded and moves the fake clock, so no test ever waits on the wall clock."""

    def __init__(self, seam, script=()):
        self.seam, self.script = seam, list(script)

    def monotonic(self):
        if not self.script:
            raise AssertionError('the fake clock ran dry: the slice read the clock more '
                                 'times than its branch allows (seen=%r)' % self.seam.seen)
        value = float(self.script.pop(0))
        self.seam.seen.append(value)
        self.seam.order.append('clock')
        return value

    def sleep(self, seconds):
        self.seam.sleeps.append(seconds)
        self.seam.order.append('sleep')
        self.seam.now += float(seconds)

    def __getattr__(self, name):
        return getattr(_time_module, name)      # time.time, perf_counter, ... never used


class LockSeam:
    """Every call `_record_lock` makes to the OS or to `discovery`, as a recorded answer.

    `busy` — how many attempts answer "busy" before the lock is given (`-1`: forever).
    `script` — the exact answers `time.monotonic()` returns, in order.
    `open_error` / `release_error` — the injected failures of 108 and 122.
    `held` is what an acquirer may see; a body that ran before `_try_lock` succeeded, or
    after the release, is visible in `bodies` and in `order`."""

    def __init__(self, path, wait_s, busy, script, open_error, release_error):
        self.path = path
        self.wait_s = wait_s
        self.busy = busy
        self.open_error = open_error
        self.release_error = release_error
        self.order, self.open_calls, self.closes = [], [], []
        self.try_lock_fds, self.sleeps, self.seen, self.releases = [], [], [], []
        self.bodies, self.held, self.now = [], False, 0.0
        self.attempts, self.fd = 0, None
        self.busy_error = OSError('synthetic: the record lock is held')
        self._os = _Os(self, open_error)
        self._time = _Time(self, script)

    # ── the discovery seam: the advisory lock and who may close the descriptor ──
    def _try_lock(self, fd):
        self.attempts += 1
        self.order.append('try_lock')
        self.try_lock_fds.append(fd)
        if self.busy == ALWAYS_BUSY or self.attempts <= self.busy:
            raise self.busy_error
        self.held = True

    def CoreLock(self, fd):                       # noqa: N802 — the name the slice calls
        seam = self

        class _FakeCoreLock:
            def __init__(self, fd):
                self.fd = fd

            def release(self):
                seam.order.append('release')
                if seam.release_error is not None:
                    raise seam.release_error
                seam.releases.append(self.fd)
                seam.held = False

        return _FakeCoreLock(fd)

    def install(self, monkeypatch):
        monkeypatch.setattr(iso, 'os', self._os)
        monkeypatch.setattr(iso, 'time', self._time)
        monkeypatch.setattr(iso, 'discovery', self)
        monkeypatch.setattr(iso, 'RECORD_LOCK_WAIT_S', self.wait_s)
        return self


def _seam(monkeypatch, record_path, *, wait_s=2.0, busy=0, script=(), open_error=None,
          release_error=None):
    """Arm the four seams of the slice for one test. `wait_s` is patched, so no test
    waits the real 2.0 s and no assertion is about elapsed wall-clock time."""
    return LockSeam(record_path, wait_s, busy, script, open_error,
                    release_error).install(monkeypatch)


def _observe(seam):
    """What the with-block does: the state is captured *while* the block runs, so a body
    that ran unheld (or after the release) fails the test instead of passing quietly."""
    seam.order.append('body')
    seam.bodies.append({'held': seam.held, 'attempts': seam.attempts,
                        'releases': list(seam.releases), 'closes': list(seam.closes),
                        'order': list(seam.order)})


# ── 1 and 2: the timeout boundary, fail-closed first ──────────────────────────────

def test_two_contended_attempts_then_acquisition_just_before_the_deadline_yields_once(
        monkeypatch, record_path):
    """1 · isolation.py:115 — the deadline branch belongs to a lock that is *still* busy:
    two contended attempts, then acquisition at 1001.999 of a 1002.0 deadline yields
    exactly once and the body never sees the descriptor unlocked.
    Catches: `break` (113) moved above `_try_lock` (112), or `yield` (120) hoisted out of
    the acquisition loop — either one hands the record to the writer without the lock."""
    seam = _seam(monkeypatch, record_path, wait_s=2.0, busy=2,
                 script=[1000.0, 1001.98, 1001.999])
    with iso._record_lock(record_path):
        _observe(seam)
    assert len(seam.bodies) == 1, 'the body did not run exactly once'
    body = seam.bodies[0]
    assert body['held'] is True, 'the body observed an unlocked record descriptor'
    assert body['attempts'] == 3 and body['releases'] == [] and body['closes'] == []
    assert seam.order == ['open', 'clock', 'try_lock', 'clock', 'sleep', 'try_lock',
                          'clock', 'sleep', 'try_lock', 'body', 'release']
    assert seam.seen[-1] < 1002.0, 'acquisition happened past the deadline it must honour'
    assert seam.sleeps == [POLL_S, POLL_S]
    assert seam.releases == [seam.fd] and seam.closes == [], \
        'a held lock was closed by the slice instead of released by CoreLock'


def test_a_lock_busy_until_exactly_the_deadline_closes_its_descriptor_once_and_never_yields(
        monkeypatch, record_path):
    """2 · isolation.py:115 — the `>=` itself, combined with contention (not the generic
    lock-timeout regression): the first check landing exactly on `end` must fail closed —
    the fd closed exactly once, no sleep, and the body never entered.
    Catches: `>=` weakened to `>` (one extra poll past the deadline, so a writer keeps
    waiting), the `os.close` (116) dropped (a leaked descriptor on every timeout) or the
    `raise ... from None` (117) turned into a bare re-raise of the OS answer."""
    seam = _seam(monkeypatch, record_path, wait_s=2.0, busy=ALWAYS_BUSY,
                 script=[1000.0, 1002.0])
    with pytest.raises(OSError) as got:
        with iso._record_lock(record_path):
            _observe(seam)
    assert seam.bodies == [], 'a timed-out lock still entered its body'
    assert seam.attempts == 1 and seam.sleeps == [], \
        'the deadline check did not fail closed at exactly end'
    assert seam.closes == [seam.fd] and seam.releases == []
    assert seam.order == ['open', 'clock', 'try_lock', 'clock', 'close']
    assert type(got.value) is OSError, 'the busy answer is no longer the slice\'s own error'
    assert record_path in str(got.value) and 'is busy' in str(got.value)
    assert got.value.__cause__ is None and got.value.__suppress_context__ is True


# ── 3: the open itself fails ───────────────────────────────────────────────────────

def test_a_lock_file_that_cannot_be_opened_propagates_its_own_error_with_no_lock_no_body(
        monkeypatch, record_path):
    """3 · isolation.py:108 — a denied `.lock` open is the end of the story: the original
    permission error propagates as the very object raised, and the slice must not call
    `_try_lock`, `CoreLock.release`, sleep, run the body, or invent a descriptor cleanup
    for a descriptor it never had.
    Catches: an `except OSError` widened around 108-109 (a denied open would become a
    silent retry or a generic "busy"), and any `finally: os.close(fd)` around the open."""
    denied = PermissionError(13, 'synthetic: the lock file cannot be opened')
    seam = _seam(monkeypatch, record_path, busy=0, script=[1000.0], open_error=denied)
    with pytest.raises(OSError) as got:
        with iso._record_lock(record_path):
            _observe(seam)
    assert got.value is denied, 'the original permission error was replaced, not propagated'
    assert type(got.value) is PermissionError
    assert seam.order == ['open']
    assert seam.attempts == 0 and seam.closes == [] and seam.releases == []
    assert seam.sleeps == [] and seam.bodies == []


# ── 4: order of acquisition vs the body ────────────────────────────────────────────

def test_acquisition_precedes_the_body_and_every_attempt_reuses_the_one_descriptor(
        monkeypatch, record_path):
    """4 · isolation.py:112 — one descriptor, opened once, is what every attempt must
    contend for, and it is held before the body is entered.
    Catches: a retry that re-opens (or re-locks a second fd) instead of contending on the
    same one — which leaves the record guarded by a descriptor nobody holds — and a `yield`
    that runs before the successful `_try_lock`."""
    seam = _seam(monkeypatch, record_path, wait_s=2.0, busy=1,
                 script=[1000.0, 1000.5])
    with iso._record_lock(record_path):
        _observe(seam)
    assert len(seam.open_calls) == 1, 'the retry opened a second descriptor'
    assert seam.try_lock_fds and set(seam.try_lock_fds) == {seam.fd}, \
        'an attempt locked a descriptor the slice never opened'
    body = seam.bodies[0]
    assert body['held'] is True and body['releases'] == [] and body['closes'] == []
    assert body['order'].index('body') > body['order'].index('try_lock')
    assert seam.order.index('release') > seam.order.index('body')
    assert seam.releases == [seam.fd] and seam.closes == []


# ── 5 and 6: the body fails, the release still happens ─────────────────────────────

def test_a_base_exception_from_the_body_survives_and_the_core_lock_still_releases_once(
        monkeypatch, record_path):
    """5 · isolation.py:122 — a `KeyboardInterrupt` (a BaseException: nothing in the slice
    catches it) must still release the lock exactly once and must survive the release
    unchanged, so Ctrl-C is never answered with a lock nobody can take again.
    Catches: the `finally` (121-122) becoming a plain call after the yield, and any
    `except Exception` around 120 that swallows the interrupt."""
    interrupt = KeyboardInterrupt('synthetic: the core is stopping')
    seam = _seam(monkeypatch, record_path, wait_s=2.0, busy=0, script=[1000.0])
    with pytest.raises(KeyboardInterrupt) as got:
        with iso._record_lock(record_path):
            _observe(seam)
            raise interrupt
    assert got.value is interrupt, 'the original BaseException was replaced'
    assert len(seam.bodies) == 1
    assert seam.releases == [seam.fd] and seam.closes == []
    assert seam.order == ['open', 'clock', 'try_lock', 'body', 'release']


def test_an_os_error_from_the_body_still_releases_through_core_lock_and_never_closes_itself(
        monkeypatch, record_path):
    """6 · isolation.py:122 — after a *successful* acquisition an `OSError` from the body
    leaves fd ownership with `CoreLock`: the release runs, the slice never closes the fd
    itself (the real release does, once), and the body's error is what propagates.
    Catches: an `except OSError: os.close(fd)` around the yield — a double close that
    can fail an unrelated descriptor — and a release skipped on the error path."""
    failure = OSError('synthetic: the record write failed')
    seam = _seam(monkeypatch, record_path, wait_s=2.0, busy=0, script=[1000.0])
    with pytest.raises(OSError) as got:
        with iso._record_lock(record_path):
            _observe(seam)
            raise failure
    assert got.value is failure
    assert seam.closes == [], 'the slice closed a descriptor CoreLock owns'
    assert seam.releases == [seam.fd]
    assert seam.order == ['open', 'clock', 'try_lock', 'body', 'release']


# ── 7 and 8: the poll interval and the one deadline ────────────────────────────────

def test_every_contended_attempt_but_the_last_sleeps_the_poll_interval(
        monkeypatch, record_path):
    """7 · isolation.py:118 — each nonterminal contention sleeps 0.02 and the terminal one
    sleeps nothing: the order is try/clock[/sleep]* then close, never try/sleep/close.
    Catches: `time.sleep` moved above the deadline check (a wait after the decision, which
    is what turns a 2.0 s bound into an unbounded one) and the interval widened away from
    the poll the other callers were tuned to."""
    seam = _seam(monkeypatch, record_path, wait_s=2.0, busy=ALWAYS_BUSY,
                 script=[1000.0, 1000.5, 1001.0, 1002.0])
    with pytest.raises(OSError):
        with iso._record_lock(record_path):
            _observe(seam)
    assert seam.attempts == 3 and seam.bodies == []
    assert seam.sleeps == [POLL_S, POLL_S], 'the last contended attempt still slept'
    assert len(seam.sleeps) == seam.attempts - 1
    assert seam.order == ['open', 'clock', 'try_lock', 'clock', 'sleep', 'try_lock',
                          'clock', 'sleep', 'try_lock', 'clock', 'close']
    assert seam.closes == [seam.fd]


def test_the_deadline_is_computed_once_on_entry_and_is_never_reset_by_a_contended_attempt(
        monkeypatch, record_path):
    """8 · isolation.py:109 — one absolute `end` on entry: the clock steps 0.9 s per
    attempt, well under `RECORD_LOCK_WAIT_S`, and the lock still gives up.
    Catches: `end = time.monotonic() + RECORD_LOCK_WAIT_S` moved inside the loop — a
    deadline renewed by every failure is a writer that waits forever for a lock whose
    holder never lets go, which is exactly the stall the record store cannot survive."""
    seam = _seam(monkeypatch, record_path, wait_s=2.0, busy=ALWAYS_BUSY,
                 script=[1000.0, 1000.9, 1001.8, 1002.7])
    with pytest.raises(OSError) as got:
        with iso._record_lock(record_path):
            _observe(seam)
    assert 'is busy' in str(got.value)
    assert seam.attempts == 3 and seam.sleeps == [POLL_S, POLL_S]
    assert seam.order == ['open', 'clock', 'try_lock', 'clock', 'sleep', 'try_lock',
                          'clock', 'sleep', 'try_lock', 'clock', 'close']
    assert seam.order[:2] == ['open', 'clock'], \
        'the deadline is not computed once, before the first attempt'
    assert seam.seen[1:] == [1000.9, 1001.8, 1002.7]


# ── 9: what the lock file actually is ──────────────────────────────────────────────

def test_the_lock_is_the_record_path_plus_lock_opened_read_write_create_mode_0600(
        monkeypatch, record_path, record_home):
    """9 · isolation.py:108 — the lock is the *record's own* path plus `.lock`, opened
    O_RDWR|O_CREAT with mode 0o600, and the only path opened in the whole slice is under
    the tmp_path record home.
    Catches: a shared or fixed lock name (two records, one lock: two Core writers in one
    each other's record), a dropped O_CREAT (every first write of a record fails), a
    widened mode (a world-readable lock file next to a record), and any side file written
    outside the record home."""
    seam = _seam(monkeypatch, record_path, wait_s=2.0, busy=0, script=[1000.0])
    with iso._record_lock(record_path):
        _observe(seam)
    assert len(seam.open_calls) == 1, 'the slice opened more than its own lock file'
    path, flags, mode = seam.open_calls[0]
    assert path == record_path + '.lock'
    assert (flags & (os.O_RDWR | os.O_CREAT)) == (os.O_RDWR | os.O_CREAT)
    assert mode == 0o600, 'the lock file is created with a mode other than 0o600'
    assert os.path.dirname(path) == record_home
    assert os.path.basename(path) == os.path.basename(record_path) + '.lock'
    assert {p for p, _f, _m in seam.open_calls} == {path}
    assert seam.releases == [seam.fd] and seam.closes == []


# ── 10: the release itself fails ───────────────────────────────────────────────────

def test_a_release_that_fails_is_never_reported_as_a_successful_lock(monkeypatch,
                                                                      record_path):
    """10a · isolation.py:122 — a release that raises is not a success: the with-block must
    not return as if the record had been unlocked, because a caller that believes it may
    write the record again while the OS still holds the lock.
    Catches: `contextlib.suppress(OSError)`/`contextlib.ignore` around the release, and a
    `finally` whose error is turned into a log line."""
    broken = OSError('synthetic: the lock cannot be unlocked')
    seam = _seam(monkeypatch, record_path, wait_s=2.0, busy=0, script=[1000.0],
                 release_error=broken)
    with pytest.raises(OSError) as got:
        with iso._record_lock(record_path):
            _observe(seam)
    assert got.value is broken, 'the release failure was swallowed'
    assert len(seam.bodies) == 1
    assert seam.releases == [], 'a release that failed was still recorded as released'
    assert seam.order == ['open', 'clock', 'try_lock', 'body', 'release']


def test_a_failing_release_propagates_when_the_body_also_fails(monkeypatch, record_path):
    """10b · isolation.py:122 — when both the body and the release fail, the release
    error is the one raised, so the caller learns the lock could not be released.
    Catches: the body error masking the release failure (the caller would retry into a
    lock that is still held)."""
    body_failure = ValueError('synthetic: the record is not writable')
    broken = OSError('synthetic: the lock cannot be unlocked')
    seam = _seam(monkeypatch, record_path, wait_s=2.0, busy=0, script=[1000.0],
                 release_error=broken)
    with pytest.raises(OSError) as got:
        with iso._record_lock(record_path):
            _observe(seam)
            raise body_failure
    assert got.value is broken
    assert seam.releases == [] and seam.closes == []
