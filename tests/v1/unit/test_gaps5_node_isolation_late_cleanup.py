"""T-1242 — the highest-risk uncovered branches of `archeus/node/isolation.py`
lines 980-1110 inclusive at tip 6bbd3b44 (the round-8 slice): the late cleanup
cancellation (`_settle`, `_abandon_late`, `_fail`, `_ensure_job`) and the closed
admission composition (`close_admission`). Denial/fail-closed first, then boundaries,
then error paths. Every ordering is forced with a seam, an event or a test-owned clock;
nothing sleeps beyond 0.05 s and nothing reaches Win32.

Selected branches (each test names its own in its docstring, with the mutation it
catches; these are candidates weighed against existing assertions, never measured
coverage):

  1. 1028-1037 `_abandon_late`: the release raises `OSError` and the registry note is
     taken → `IsolationClosed` carries the error type and a non-ASCII detail, the record
     stays owned/pending with its SID, nothing is failed and no tombstone is written.
  2. 1035 `_abandon_late`: the release and the note both raise, with different
     `OSError`s → the cancellation keeps the FIRST cleanup error, the note is attempted
     exactly once, and no `_fail` path is entered.
  3. 984 `_settle`: a published stop refuses before `_ensure_job`, `job_facts` and the
     invariant, with the record deliberately not `pending` — closure dominates the
     985 unsettled-record refusal.
  4. 985 `_settle`: a record a concurrent Core settled is refused before any Job is
     created, even where every fake invariant check would have passed.
  5. 990/993→994-995 `_settle`: `job_facts` or `check_invariant` raises
     `IsolationUnavailable` → `_fail` receives the original reason and detail; nothing
     is saved as established.
  6. 1001-1003 `_settle`: several unmet conditions at once are preserved as one named
     failure and prevent the established save, even when A4 would have passed.
  7. 1004-1010 `_settle`: a verifier request bypasses A4 eligibility but never the
     invariant checks, and a normal request whose A4 facts are unmet is failed as
     `a4_unmet`.
  8. 1014 `_settle`: the stop begins after the invariant and before the final save →
     `_save_establishment` refuses, and the caller's cancellation cleanup is the sole
     release path.
  9. 1103-1104/1110 `close_admission`: the stop is published before the timed acquire,
     which is observed from inside a fake acquire that calls `_check_establishment`.
 10. 1105-1108 `close_admission`: an expired deadline clamps the drain timeout to zero,
     a failed acquire never releases a lock it does not own, and a reentrant acquire
     releases exactly one level.

Everything runs against a synthetic boundary and synthetic homes: no AppContainer, Job,
process, handle or DLL call, no subprocess, no wall-clock wait over 0.05 s, no real
`ARCHEUS_HOME`, no environment value and no OS record lock. The autouse tripwires below
fail any test that reaches a real Win32 mutation primitive, a real record lock or a
path outside `tmp_path`.
"""

import json
import logging
import os
import threading
import time
import zlib

import pytest

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.infra.paths import ExecPaths
from archeus.node import isolation as iso
from archeus.node.pv20_switches import Pv20Switches

#: bounded ceiling for every event wait and thread join in this file; the only wait on
#: the clock is the 0.05 s probe of a lock held by another thread (RULES: no sleep > 0.2 s)
JOIN_S = 5.0
PROBE_S = 0.05

#: A4 open: `_settle` asks `a4_eligibility` for a non-verifier request. Every switch
#: shares one value, which is what `Pv20Switches` insists on.
ALL_OPEN = Pv20Switches(True, True, True, True, True, True, True, True, True, True)


# ── the tripwires: no real Win32, no real home, no real OS lock ───────────────

@pytest.fixture(autouse=True)
def no_real_win32(monkeypatch):
    """The synthetic boundary is the reason none of this is reachable; the guard is the
    belt (RULES: written on Linux, reviewed on Windows, never a real DLL)."""
    hits = []
    for name in ('_CreateAppContainerProfile', '_DeleteAppContainerProfile',
                 '_GetSecurityInfoByNameW', '_CreateProcessW', '_CreateJobObjectW',
                 '_AssignProcessToJobObject', '_TerminateProcess', '_CloseHandle',
                 '_SetInformationJobObject', '_ResumeThread', '_OpenProcess',
                 '_OpenProcessToken', '_GetCurrentProcess'):
        def trip(*a, _name=name):
            hits.append(_name)
            raise AssertionError('the real %s was reached' % _name)
        monkeypatch.setattr(iso, name, trip, raising=False)
    yield hits
    assert hits == [], 'a real mutation primitive was reached: %r' % (hits,)


class _FakeRecordLock:
    """`discovery.CoreLock` as this file needs it: the descriptor is closed and no
    `msvcrt`/`fcntl` locking call is ever made (card: fake `_try_lock` and
    `CoreLock.release`). One writer per record per test, so no real contention exists."""

    def __init__(self, fd):
        self.fd = fd

    def release(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


@pytest.fixture(autouse=True)
def synthetic_home(tmp_path, monkeypatch):
    """Every record, quarantine line and consumed marker is written under `tmp_path`:
    no test here resolves, reads or writes a real `ARCHEUS_HOME`, a user profile or an
    environment value."""
    root = tmp_path / 'home'
    iso_dir = root / 'run' / 'isolation'

    def _dir():
        return str(iso_dir)

    def _state(key):
        if isinstance(key, str) and key.startswith(iso.VERIFY_KEY):
            vid, n = iso.verify_key_parts(key)
            return str(iso_dir / 'verify' / ('%s.%d.json' % (vid, n)))
        return str(iso_dir / ('%s.json' % key))

    def _consumed(key):
        vid, n = iso.verify_key_parts(key)
        return str(iso_dir / 'verify' / ('%s.%d.consumed' % (vid, n)))

    monkeypatch.setattr(iso, 'isolation_dir', _dir)
    monkeypatch.setattr(iso, 'isolation_state', _state)
    monkeypatch.setattr(iso, 'quarantine_log', lambda: str(iso_dir / 'quarantine.jsonl'))
    monkeypatch.setattr(iso, 'verify_consumed', _consumed)
    monkeypatch.setattr(iso, 'run_dir', lambda: str(root / 'run'))
    # `_record_lock` itself runs for real (its busy path is fx32's territory); only the
    # OS locking syscalls under it are faked, as the card requires.
    monkeypatch.setattr(iso.discovery, '_try_lock', lambda fd: None)
    monkeypatch.setattr(iso.discovery, 'CoreLock', _FakeRecordLock)
    return root


# ── the synthetic boundary and the instrument: answers, decisions nothing ──────

def _stable_sid(name):
    """A SID derived from a profile name: deterministic (no `hash` salt), so a test
    reads the same answer on Windows as on Linux."""
    return 'S-1-15-3-9-%08d' % (zlib.crc32(str(name).encode('utf-8')) % (10 ** 8),)


class FakeBoundary:
    """A boundary whose every answer is a knob. It never launches a real process and
    never names the OS: it records what it was asked to do."""
    id = 'fake'

    def __init__(self):
        self.available_ok = True
        self.profiles = set()
        self.sids = {}
        self.created = []
        self.deleted = []
        self.closed = []                  # every close_job handle
        self.assigned = []
        self.job_creates = 0

    def available(self):
        return self.available_ok

    def create_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        existed = name in self.profiles
        self.profiles.add(name)
        self.created.append(name)
        return {'profile': name, 'sid': self.sids.get(name) or _stable_sid(name),
                'created': True, 'existed': existed, 'package_dir': 'materialized'}

    def delete_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        self.deleted.append(name)
        self.profiles.discard(name)

    def profile_exists(self, execution_id):
        return iso.validated_profile(execution_id) in self.profiles

    def derive_sid(self, execution_id):
        return _stable_sid(iso.validated_profile(execution_id))

    def grant_established(self, path, sid, access):
        return True

    def broad_write_grant(self, path, sid):
        return None

    def granted_to(self, path, sid):
        return False

    def capability_grants(self):
        return ()

    def create_job(self, execution_id):
        self.job_creates += 1
        return {'job': execution_id}

    def job_facts(self, handle):
        if handle is None:
            return None
        return {'type': 'Job', 'name': '', 'inheritable': False}

    def job_active_processes(self, job):
        return 0

    def assign_job(self, job, process_handle):
        self.assigned.append((job, process_handle))

    def close_job(self, job):
        self.closed.append(job)

    def mutations(self):
        """Every call that would change OS state: the profile store, a Job, a process."""
        return self.created + self.deleted + self.assigned


class FakeNode:
    """The registry as a list (card: registry notes to list). `fail` makes the very
    write that `_abandon_late` and `_fail` attempt raise, and `calls` counts attempts,
    so 'tried once' is an observation."""

    id = 'fake-node'

    def __init__(self):
        self.registry = []
        self.calls = 0
        self.fail = None

    def _registry(self, line):
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        self.registry.append(line)


def new_execution_id():
    return ids.new_id('execution')


def _dirs(root, *names):
    out = {}
    for name in names:
        path = os.path.join(str(root), name)
        os.makedirs(path, exist_ok=True)
        out[name] = path
    return out


def make_exec_request(execution_id, root):
    """An §3.1 inventory a synthetic fixture can satisfy but production cannot: every
    required row present, the broker present, the class 1, 2 and 3 directories
    separated, and Core's own state kept outside the boundary."""
    d = _dirs(root, 'workspace', 'mailbox', 'response', 'sentinel', 'state', 'runtime',
              'hook', 'core_state', 'broker')
    spawn_config = os.path.join(d['response'], 'spawn_config.json')
    with open(spawn_config, 'w', encoding='utf-8') as f:
        json.dump({'argv': []}, f)
    grants = (iso.Grant(d['workspace'], 'rw', 'workspace'),
              iso.Grant(d['runtime'], 'rx', 'runtime'),
              iso.Grant(d['hook'], 'rx', 'hook'),
              iso.Grant(d['mailbox'], 'rw', 'request'),
              iso.Grant(d['response'], 'rx', 'response'),
              iso.Grant(d['sentinel'], 'rx', 'sentinel'),
              iso.Grant(d['state'], 'rw', 'state'))
    return iso.IsolationRequest(execution_id=execution_id, workspace=d['workspace'],
                                grants=grants, mailbox=d['mailbox'], response=d['response'],
                                sentinel=d['sentinel'], spawn_config=spawn_config,
                                state_dir=d['state'], core_state=d['core_state'],
                                broker=d['broker'])


def make_verify_request(key, root):
    """A verifier attempt's whole inventory (A6): checkout, scratch, a read-only
    toolchain, and Core's own state named and kept apart."""
    d = _dirs(root, 'checkout', 'scratch', 'toolchain', 'core_state')
    return iso.IsolationRequest(execution_id=key, workspace=d['checkout'],
                                grants=(iso.Grant(d['checkout'], 'rw', 'checkout'),
                                        iso.Grant(d['scratch'], 'rw', 'scratch'),
                                        iso.Grant(d['toolchain'], 'rx', 'toolchain')),
                                core_state=d['core_state'])


def _verify_key(attempt=0, vid=None):
    return iso.Principal('verify', vid or ids.new_id('verification'), attempt).key


# ── the rig: an authority, its boundary, its instrument and the call spies ─────

class Spies:
    """Every call that reaches out of (or below) the slice is wrapped, counted in order
    and passed through, so 'never reached' is an observation and not a hope. A knob that
    raises or answers is keyed by the execution it belongs to, so one rig can drive
    several executions without one global patch deciding for all of them."""

    def __init__(self, monkeypatch, a, b):
        self.a, self.b = a, b
        self.calls = []
        self.fail_args = []
        self.mark_ended_args = []
        self.release_raises = {}            # execution_id -> OSError
        self.job_facts_raises = {}          # execution_id -> BaseException
        self.job_facts_answers = {}         # execution_id -> job_facts answer
        self.invariant_raises = {}          # execution_id -> BaseException
        self.invariant_answers = {}         # execution_id -> conditions
        self.on_invariant = {}              # execution_id -> callable(conditions), a seam
        self.unverified = set()             # normcase'd paths condition 2 finds ungranted
        self.broad_writes = set()           # normcase'd paths condition 3 finds broad
        self._real = {'job_facts': b.job_facts, 'invariant': iso.check_invariant,
                      'a4': iso.a4_eligibility, 'ensure_job': a._ensure_job,
                      'fail': a._fail, 'release': a._release_best_effort,
                      'grant': b.grant_established, 'broad': b.broad_write_grant,
                      'save_establishment': a._save_establishment,
                      'mark_ended': iso.base.mark_ended}
        monkeypatch.setattr(b, 'job_facts', self._job_facts)
        monkeypatch.setattr(b, 'grant_established', self._grant_established)
        monkeypatch.setattr(b, 'broad_write_grant', self._broad_write_grant)
        monkeypatch.setattr(iso, 'check_invariant', self._invariant)
        monkeypatch.setattr(iso, 'a4_eligibility', self._a4)
        monkeypatch.setattr(iso.base, 'mark_ended', self._mark_ended)
        monkeypatch.setattr(a, '_ensure_job', self._ensure_job)
        monkeypatch.setattr(a, '_fail', self._fail)
        monkeypatch.setattr(a, '_release_best_effort', self._release)
        monkeypatch.setattr(a, '_save_establishment', self._save_establishment)

    def names(self):
        return list(self.calls)

    def count(self, name):
        return self.calls.count(name)

    def _ensure_job(self, execution_id):
        self.calls.append('ensure_job')
        return self._real['ensure_job'](execution_id)

    def _job_facts(self, handle):
        self.calls.append('job_facts')
        eid = (handle or {}).get('job')
        if eid in self.job_facts_raises:
            raise self.job_facts_raises[eid]
        if eid in self.job_facts_answers:
            return self.job_facts_answers[eid]
        return self._real['job_facts'](handle)

    def _invariant(self, api, request, identity, job_facts=None):
        self.calls.append('invariant')
        eid = request.execution_id
        if eid in self.invariant_raises:
            raise self.invariant_raises[eid]
        if eid in self.invariant_answers:
            got = self.invariant_answers[eid]
        else:
            got = self._real['invariant'](api, request, identity, job_facts)
        seam = self.on_invariant.get(eid)
        if seam is not None:
            seam(got)
        return got

    def _a4(self, **facts):
        self.calls.append('a4')
        return self._real['a4'](**facts)

    def _fail(self, rec, reason, detail, paths=None):
        self.calls.append('fail')
        self.fail_args.append((rec.execution_id, reason, detail, paths))
        return self._real['fail'](rec, reason, detail, paths)

    def _release(self, rec):
        self.calls.append('release')
        if rec.execution_id in self.release_raises:
            raise self.release_raises[rec.execution_id]
        return self._real['release'](rec)

    def _save_establishment(self, rec):
        self.calls.append('save_establishment')
        return self._real['save_establishment'](rec)

    def _mark_ended(self, paths, exit_code=None, **extra):
        self.calls.append('mark_ended')
        self.mark_ended_args.append((paths, exit_code, extra))
        return self._real['mark_ended'](paths, exit_code, **extra)

    def _grant_established(self, path, sid, access):
        if os.path.normcase(os.path.abspath(path)) in self.unverified:
            return False
        return self._real['grant'](path, sid, access)

    def _broad_write_grant(self, path, sid):
        if os.path.normcase(os.path.abspath(path)) in self.broad_writes:
            return 'S-1-1-0'
        return self._real['broad'](path, sid)


class Rig:
    """One authority, one synthetic boundary, one instrument, one set of spies. A test
    uses one rig: `iso.check_invariant` and `iso.base.mark_ended` are module-level and
    a second rig's patch would silently answer for the first."""

    def __init__(self, tmp_path, monkeypatch, *, switches=None, executions=1):
        self.node = FakeNode()
        self.b = FakeBoundary()
        self.a = iso.Isolation(self.node, boundary=self.b, plan=lambda spec: None,
                               switches=switches)
        self.requests = {}
        for n in range(executions):
            eid = new_execution_id()
            self.requests[eid] = make_exec_request(eid, tmp_path / ('layout%d' % n))
        self.request = next(iter(self.requests.values()))
        self.spies = Spies(monkeypatch, self.a, self.b)

    def ops(self):
        """The registry's `op` values, in the order the instrument was asked for them."""
        return [line['op'] for line in self.node.registry]

    def record_bytes(self, execution_id):
        path = iso.isolation_state(execution_id)
        if not os.path.lexists(path):
            return None
        with open(path, 'rb') as f:
            return f.read()

    def quarantine_lines(self):
        path = iso.quarantine_log()
        if not os.path.lexists(path):
            return []
        with open(path, encoding='utf-8') as f:
            return [json.loads(x) for x in f.read().splitlines() if x.strip()]


def _owned_pending(rig, execution_id, state='pending'):
    """The record exactly as `_establish` leaves it after the ownership save: owned,
    pending, with the SID the boundary derived (the same seam fx32 uses). The profile is
    put in the synthetic store too, so "the profile survived" is a fact about the fake
    and not an absence of evidence."""
    name = iso.profile_name(execution_id)
    rig.b.profiles.add(name)
    rig.b.created.append(name)
    rec = iso.IsolationRecord(execution_id=execution_id,
                              profile=name, owned=True, state=state,
                              sid=rig.b.derive_sid(execution_id))
    rig.a._save(rec)
    return rec


def _identity(b, execution_id):
    """What the boundary answered when the profile was created (§3.4's *identity*)."""
    return {'profile': iso.profile_name(execution_id), 'sid': b.derive_sid(execution_id),
            'created': True, 'package_dir': 'materialized'}


def _all_holds():
    return {name: (True, '') for name in iso.CONDITIONS}


def _paths(tmp_path, execution_id):
    return ExecPaths(execution_id, run=str(tmp_path / 'run'))


class _Clock:
    """`time` as the slice uses it, with `monotonic` answering from a value the test
    owns: the drain timeout becomes arithmetic on a chosen number, never a wall race."""

    def __init__(self, now=0.0):
        self.now = now

    def monotonic(self):
        return self.now

    def __getattr__(self, name):
        return getattr(time, name)


class ProbeLock:
    """Stands in for the authority's establishment lock inside `close_admission`: it
    answers the timed acquire 1105 asks for and reports what the world looked like from
    inside that call, which is the only place 1103-1104's ordering can be observed."""

    def __init__(self, a, *, answer=True):
        self.a = a
        self.answer = answer
        self.acquires = []                  # (timeout, closed seen, refusal seen)
        self.releases = 0
        self.entered = 0

    def acquire(self, timeout=None):
        with self.a._state:
            published = self.a.closed
        refused = ''
        try:
            self.a._check_establishment()
        except iso.IsolationClosed:
            refused = 'IsolationClosed'
        self.acquires.append((timeout, published, refused))
        return self.answer

    def release(self):
        self.releases += 1

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *exc):
        return False


class CountingRLock:
    """A real `RLock` that says how many levels it was asked to take and give back."""

    def __init__(self, real):
        self.real = real
        self.acquires = []
        self.releases = 0

    def acquire(self, timeout=-1):
        self.acquires.append(timeout)
        return self.real.acquire(timeout=timeout)

    def release(self):
        self.releases += 1
        self.real.release()

    def __enter__(self):
        return self.real.__enter__()

    def __exit__(self, *exc):
        return self.real.__exit__(*exc)


def _free_from_another_thread(lock, wait=PROBE_S):
    """Ask from a second thread whether *lock* is free: bounded, and never asked by the
    thread that owns it (a reentrant acquire there would always lie yes)."""
    box = {}

    def body():
        box['got'] = lock.acquire(timeout=wait)
        if box['got']:
            lock.release()
    t = threading.Thread(target=body, name='lock-probe')
    t.start()
    t.join(JOIN_S)
    assert not t.is_alive(), 'the lock probe outlived its bounded join'
    return box['got']


# ── 1. §3.7: a cleanup that fails while the note is taken is still cancellation ──
#
# isolation.py:1028-1032 `_abandon_late`: the release raises, the note is attempted
# isolation.py:1037: the stop is raised with the cleanup fault in its detail

def test_a_release_that_fails_while_the_note_is_taken_stays_cancellation(tmp_path,
                                                                         monkeypatch):
    """Branch caught: 1029 raising past 1030 into 1031-1034, then 1037 raising
    `IsolationClosed(cleanup)`. Inverting the `except OSError` to a re-raise (or letting
    the note's success clear `cleanup`) turns the cancellation into an establishment
    failure or a bare stop, and the execution is charged for a fault only the OS had.

    Closest existing test: test_fx32_isolation_stop.py::test_a_late_cleanup_failure_
    keeps_the_cancellation_and_reports_the_fault. It asserts the detail substring and the
    note's `op`/`error` items, with an ASCII message; it never asserts that the fault is
    *typed* (`OSError: `), that the error type and a non-ASCII detail both ride the
    cancellation, that the note was attempted exactly once, that no tombstone and no
    quarantine line were written, or that the record file is byte-for-byte the ownership
    save. This is the same branch with those holes filled, as the card asks."""
    rig = Rig(tmp_path, monkeypatch)
    a, b, s = rig.a, rig.b, rig.spies
    eid = rig.request.execution_id
    rec = _owned_pending(rig, eid)
    before = rig.record_bytes(eid)
    name = iso.profile_name(eid)
    detail = 'il profilo non è eliminabile — Ùnicode ‹Øscar› \u202e reverse ‬'
    s.release_raises = {eid: OSError(detail)}
    paths = _paths(tmp_path, eid)

    with pytest.raises(iso.IsolationClosed) as got:
        a._abandon_late(rec)

    err = got.value
    assert isinstance(err, base.SpawnFailed)
    assert not isinstance(err, iso.IsolationUnavailable)
    assert not isinstance(err, OSError)               # the cleanup fault never escapes typed
    text = str(err)
    assert 'OSError: %s' % detail in text             # type AND detail, verbatim
    assert 'core_stopping' in text
    # the note was taken, once, and is the only line the instrument got
    assert rig.node.calls == 1 and len(rig.node.registry) == 1
    line = rig.node.registry[0]
    assert line['op'] == 'isolation_cleanup_failed' and line['error'] == 'OSError'
    assert line['detail'] == detail and line['execution_id'] == eid
    assert rig.ops() == ['isolation_cleanup_failed']  # never an establishment failure
    # the record is exactly what the ownership save left: reclaim, not `_fail`, settles it
    assert rig.record_bytes(eid) == before
    kept = a.record(eid)
    assert kept.state == 'pending' and kept.owned is True and kept.preexisting is False
    assert kept.sid == b.derive_sid(eid) and kept.failure == '' and kept.reason == ''
    assert kept.conditions == {} and list(kept.capabilities) == []
    # no privileged side effects: nothing failed, no tombstone, no ledger entry
    assert s.count('fail') == 0 and s.count('mark_ended') == 0
    assert not os.path.lexists(paths.ended)
    assert rig.quarantine_lines() == []
    assert s.count('release') == 1 and b.deleted == []   # the release was tried, not redone
    assert name in b.profiles and b.closed == [] and b.job_creates == 0


# ── 2. §3.7: two faults, one cancellation, and the first fault is the one kept ──
#
# isolation.py:1032-1036 `_abandon_late`: the note raises OSError and is swallowed

def test_a_note_that_also_fails_keeps_the_first_cleanup_error_and_writes_nothing(
        tmp_path, monkeypatch):
    """Branch caught: 1033 raising into 1035-1036 (`except OSError: pass`) and then
    1037. Two mutations this pins that nothing else does: letting the note's `OSError`
    escape (the stop would become an unclassified crash, and the execution would be
    charged), and overwriting `cleanup` with the second error (1031), which would report
    a registry fault as the reason the profile is still there and hide the delete that
    never happened.

    Closest existing test: test_fx32_isolation_stop.py::test_a_failed_cleanup_note_
    does_not_change_the_cancellation, which asserts only `pytest.raises(IsolationClosed)`
    — it passes with the detail lost, with the note retried three times, with `_fail`
    reached, and with the record rewritten. Here the note is counted, the first error is
    required by name, the second is required absent, and the record is compared as
    bytes."""
    rig = Rig(tmp_path, monkeypatch)
    a, b, s = rig.a, rig.b, rig.spies
    eid = rig.request.execution_id
    rec = _owned_pending(rig, eid)
    before = rig.record_bytes(eid)
    first = 'the profile is still held by a handle (synthetic)'
    s.release_raises = {eid: OSError(first)}
    rig.node.fail = OSError('the registry is full — registré ïnkompatibël')
    paths = _paths(tmp_path, eid)

    with pytest.raises(iso.IsolationClosed) as got:
        a._abandon_late(rec)

    assert isinstance(got.value, base.SpawnFailed)
    assert not isinstance(got.value, OSError)
    text = str(got.value)
    assert 'OSError: %s' % first in text              # the FIRST cleanup error is retained
    assert 'registry is full' not in text             # the second never replaces it
    assert rig.node.calls == 1                        # the note was attempted exactly once
    assert rig.node.registry == []                    # and nothing was written
    assert rig.ops() == []                            # no isolation_failed line either
    assert s.count('fail') == 0                       # no _fail path, so nothing is charged
    assert s.count('mark_ended') == 0 and not os.path.lexists(paths.ended)
    assert rig.record_bytes(eid) == before
    kept = a.record(eid)
    assert kept.state == 'pending' and kept.owned is True and kept.sid == b.derive_sid(eid)
    assert kept.failure == '' and kept.attempts == 0
    assert rig.quarantine_lines() == [] and b.deleted == [] and b.closed == []


# ── 3. §3.4/§3.7: a published stop outranks everything `_settle` would ask ──────
#
# isolation.py:984 `_settle`: `self._check_establishment()` before 985, 989, 990, 993

def test_a_published_stop_refuses_the_settle_before_the_job_the_facts_and_the_invariant(
        tmp_path, monkeypatch):
    """Branch caught: 984 raising for a record that is NOT pending. The composition is
    the point: read on its own, 984 must beat 985, so a stop that lands while a
    concurrent Core was settling the record must be cancellation with nothing below it
    asked — never the `record_unsettled` establishment failure of 985-987, which would
    charge the execution and delete its own profile.

    Closest existing test: test_fx32_isolation_stop.py::test_a_profile_created_after_
    the_stop_returned_is_deleted_by_its_own_establishment stops the authority before the
    profile exists, so `_settle` is reached with `rec.state == 'pending'` and 985 is
    never in play; and it infers the refusal from the outcome rather than from the calls
    that were not made. Here `_settle` is entered directly with a record already settled
    by another writer, and every call from 985 down is spied, so the emptiness of that
    log is the assertion."""
    rig = Rig(tmp_path, monkeypatch)
    a, b, s = rig.a, rig.b, rig.spies
    eid = rig.request.execution_id
    rec = _owned_pending(rig, eid, state='established')     # a concurrent Core settled it
    s.invariant_answers[eid] = _all_holds()                 # it would have passed, too
    paths = _paths(tmp_path, eid)

    # first, while open: the same call is the 985 establishment failure, and it is called
    with pytest.raises(iso.IsolationUnavailable) as unsettled:
        a._settle(b, rec, rig.request, _identity(b, eid), paths)
    assert unsettled.value.reason == 'record_unsettled'
    assert s.count('invariant') == 0 and s.count('ensure_job') == 0
    assert s.count('fail') == 1
    settled = rig.record_bytes(eid)

    # the open refusal failed and released `rec`, so the closed call gets a fresh
    # established record that is still owned, with the profile standing again
    name = iso.profile_name(eid)
    b.profiles.add(name)
    rec = iso.IsolationRecord(execution_id=eid, profile=name, owned=True,
                              state='established', sid=b.derive_sid(eid),
                              gen=a.record(eid).gen)
    a.close_admission()                                     # the stop is published
    before = len(s.calls)
    with pytest.raises(iso.IsolationClosed) as got:
        a._settle(b, rec, rig.request, _identity(b, eid), paths)

    assert isinstance(got.value, base.SpawnFailed)
    assert not isinstance(got.value, iso.IsolationUnavailable)
    assert not isinstance(got.value, OSError)
    assert s.names()[before:] == []                         # nothing at all was asked
    # the open refusal stopped at 985 too, so nothing below it was ever reached: not one
    # Job was created by either call, in either order
    assert s.count('ensure_job') == 0 and s.count('job_facts') == 0
    assert s.count('invariant') == 0 and s.count('fail') == 1
    assert b.job_creates == 0 and b.closed == []
    assert b.created == [iso.profile_name(eid)]         # the profile the record owns
    assert a.held_jobs() == {}                              # the stop holds no new Job
    assert rig.node.registry[0]['op'] == 'isolation_failed'  # the open refusal's line only
    assert rig.record_bytes(eid) == settled                 # the stop wrote nothing


# ── 4. §3.7: a record another Core settled is refused before a Job exists ───────
#
# isolation.py:985-987 `_settle`: `if rec.state != 'pending': return self._fail(...)`

def test_a_record_a_concurrent_core_settled_is_refused_before_any_job_is_created(
        tmp_path, monkeypatch):
    """Branch caught: 985 taken and 986-987 returning `_fail`, with 989-993 never
    reached. Deleting the guard lets a record that is already `established` (or failed,
    or quarantined) be walked over a fresh Job, its conditions re-read and the
    established save of 1011-1014 written over another Core's decision — O7 would read
    an identity Core never established here.

    Closest existing test: nothing calls `_settle` with a non-pending record — the
    `record_unsettled` regressions (test_pv20_isolation.py, test_gaps3_node_isolation_a.
    py) all stop the authority in `establish`, above this slice, where the refusal comes
    from `_admit_establishment` before the ownership save. The composition the card asks
    for is that every fake invariant check WOULD pass here: the invariant is armed with
    all-six-true answers and still never asked, which is what proves the refusal is the
    record's state and not the boundary's answer."""
    rig = Rig(tmp_path, monkeypatch)
    a, b, s = rig.a, rig.b, rig.spies
    eid = rig.request.execution_id
    rec = _owned_pending(rig, eid, state='established')
    s.invariant_answers[eid] = _all_holds()
    name = iso.profile_name(eid)
    paths = _paths(tmp_path, eid)

    with pytest.raises(iso.IsolationUnavailable) as got:
        a._settle(b, rec, rig.request, _identity(b, eid), paths)

    assert got.value.reason == 'record_unsettled'
    assert 'a concurrent Core settled it as established' in got.value.detail
    # nothing below the guard ran: no Job, no facts, no invariant, no A4
    assert s.names() == ['fail', 'mark_ended', 'release']
    assert s.count('ensure_job') == 0 and s.count('job_facts') == 0
    assert s.count('invariant') == 0 and s.count('a4') == 0
    assert b.job_creates == 0 and b.closed == [] and a.held_jobs() == {}
    # `_fail` was reached with the reason and detail 986-987 builds, unchanged
    assert s.fail_args == [(eid, 'record_unsettled',
                            'a concurrent Core settled it as established', paths)]
    assert s.count('save_establishment') == 0               # never saved as established
    kept = a.record(eid)
    assert kept.state == 'failed' and kept.reason == 'record_unsettled'
    assert kept.failure == 'record_unsettled' and kept.owned is True
    assert kept.sid == b.derive_sid(eid) and kept.conditions == {}
    assert list(kept.capabilities) == [] and list(kept.planned) == []
    assert rig.ops() == ['isolation_failed']
    assert rig.node.registry[0]['reason'] == 'record_unsettled'
    assert s.count('mark_ended') == 1
    assert os.path.isfile(paths.ended)                      # the deterministic tombstone
    with open(paths.ended, encoding='utf-8') as f:
        tomb = json.load(f)
    assert tomb['isolation_reason'] == 'record_unsettled' and tomb['exit_code'] is None
    assert b.deleted == [name] and name not in b.profiles   # the identity was released
    assert rig.quarantine_lines() == []


# ── 5. §3.4: a boundary read that cannot be answered keeps its own reason ────────
#
# isolation.py:989-993 → 994-995 `_settle`: `except IsolationUnavailable as err:` →
# `_fail(rec, err.reason, err.detail, paths)`

def test_a_boundary_read_that_cannot_be_answered_is_failed_under_its_own_reason(
        tmp_path, monkeypatch):
    """Branch caught: 994-995 for BOTH reads inside the try — `job_facts` (990) and
    `check_invariant` (993) — on two executions of one rig. Two mutations: dropping the
    caught exception's `detail` (the record then says which condition broke and not what
    the OS said, which is the half of O7 that makes a restart actionable), and letting
    either raise out of `_settle` (the caller's `except IsolationClosed` would not fire
    and the owned profile would stand undeleted).

    Closest existing test: test_pv20_isolation.py::test_a_failed_boundary_read_is_an_
    establishment_failure injects the raise from `broad_write_grant`, i.e. from inside
    `check_invariant`, through `establish`, and asserts `reason`, `state == 'failed'`
    and one deletion. `job_facts` is never made to fail anywhere in the suite, no test
    asserts the detail is forwarded verbatim, that the invariant was never asked when
    the facts failed, that the Job already held was closed, or that nothing reached
    `_save_establishment`."""
    rig = Rig(tmp_path, monkeypatch, executions=2)
    a, b, s = rig.a, rig.b, rig.spies
    facts_id, invariant_id = list(rig.requests)
    s.job_facts_raises[facts_id] = iso.IsolationUnavailable(
        'job_facts_unreadable', 'the Job name could not be read (synthetic)')
    s.invariant_raises[invariant_id] = iso.IsolationUnavailable(
        'token_unreadable', 'the DACL of ‹ït› could not be read (synthetic)')
    facts_rec = _owned_pending(rig, facts_id)
    invariant_rec = _owned_pending(rig, invariant_id)

    with pytest.raises(iso.IsolationUnavailable) as facts:
        a._settle(b, facts_rec, rig.requests[facts_id], _identity(b, facts_id), None)
    with pytest.raises(iso.IsolationUnavailable) as invariant:
        a._settle(b, invariant_rec, rig.requests[invariant_id],
                  _identity(b, invariant_id), None)

    # the original reason AND detail reach `_fail`, unmangled and unreplaced
    assert facts.value.reason == 'job_facts_unreadable'
    assert 'the Job name could not be read (synthetic)' in facts.value.detail
    assert invariant.value.reason == 'token_unreadable'
    assert 'the DACL of ‹ït› could not be read (synthetic)' in invariant.value.detail
    assert [a_[1] for a_ in s.fail_args] == ['job_facts_unreadable', 'token_unreadable']
    assert [a_[2] for a_ in s.fail_args] == [
        'the Job name could not be read (synthetic)',
        'the DACL of ‹ït› could not be read (synthetic)']
    # a Job whose facts could not be read never reached the invariant; the invariant's
    # own failure never reached A4, and neither saved an established record
    assert s.count('invariant') == 1 and s.count('a4') == 0
    assert s.count('save_establishment') == 0 and s.count('mark_ended') == 0
    for eid in (facts_id, invariant_id):
        kept = a.record(eid)
        assert kept.state == 'failed' and kept.failure == kept.reason
        assert kept.conditions == {} and list(kept.capabilities) == []
        assert kept.owned is True and kept.sid == b.derive_sid(eid)
        assert iso.profile_name(eid) in b.deleted and iso.profile_name(eid) not in b.profiles
    # the Job each execution had been given was Core's to close, and the release closed it
    assert b.job_creates == 2 and len(b.closed) == 2 and a.held_jobs() == {}
    assert rig.ops() == ['isolation_failed', 'isolation_failed']
    assert rig.quarantine_lines() == []


# ── 6. §3.4: every named failure is preserved, and A4 is never asked to forgive it ─
#
# isolation.py:1000-1003 `_settle`: `unmet = unmet_conditions(conditions)` → `_fail`

def test_several_unmet_conditions_are_named_in_one_reason_before_a4_can_be_asked(
        tmp_path, monkeypatch):
    """Branch caught: 1001 taken with more than one name unmet, returning `_fail` at
    1002-1003 and so skipping 1004-1014. Two mutations: joining only the first unmet
    name (the record then under-reports what broke, and a restarted Core reconciles
    against half the truth), and moving the A4 gate above the unmet check so an
    eligible-looking harness washes the unmet conditions out and reaches the
    established save of 1011-1014.

    Closest existing test: test_pv20_isolation.py::test_unmet_condition_raises_and_
    records turns ONE knob (`b.broad`) and asserts `reason` contains the name, the state
    and one registry line. Nothing asserts the multi-name reason and its ordering, the
    per-condition `why` strings in the detail, that A4 was never consulted although the
    card's A4 facts were all in place, or that the established save never happened."""
    rig = Rig(tmp_path, monkeypatch, switches=ALL_OPEN)
    a, b, s = rig.a, rig.b, rig.spies
    eid = rig.request.execution_id
    rec = _owned_pending(rig, eid)
    workspace = os.path.normcase(os.path.abspath(rig.request.workspace))
    s.broad_writes = {workspace}                                  # condition 3 unmet
    s.job_facts_answers[eid] = {'type': 'Job', 'name': 'a-named-job',
                                'inheritable': False}             # condition 4 unmet
    a._dispatch.add(eid)                    # the harness IS dispatched: A4 would pass now
    paths = _paths(tmp_path, eid)

    with pytest.raises(iso.IsolationUnavailable) as got:
        a._settle(b, rec, rig.request, _identity(b, eid), paths)

    assert got.value.reason == 'condition_unmet:no_broad_grants,job'
    assert 'a broad principal holds write' in got.value.detail
    assert 'the Job is named' in got.value.detail
    assert s.fail_args[0][:2] == (eid, 'condition_unmet:no_broad_grants,job')
    # A4 was never asked, and it is not a pass that would have saved this establishment
    assert s.count('a4') == 0
    kept = a.record(eid)
    assert s._real['a4'](harness_id='claude_code', isolated_launch=True, job_held=True,
                         sandbox=False, exception_claimed=False,
                         evidence=kept.conditions) == (True, ())
    assert s.count('a4') == 0
    assert s.count('save_establishment') == 0                     # no established save
    assert kept.state == 'failed' and kept.failure == got.value.reason
    assert kept.conditions['no_broad_grants'][0] is False          # what did not hold, kept
    assert kept.conditions['job'][0] is False
    assert kept.conditions['identity'][0] is True                  # and what did
    assert list(kept.capabilities) == [] and kept.planned == tuple(rig.request.grants)
    assert rig.ops() == ['isolation_failed']
    assert rig.node.registry[0]['conditions']['job'][0] is False
    assert b.deleted == [iso.profile_name(eid)] and b.closed and a.held_jobs() == {}


# ── 7. §3.8/A6: a verifier never asks A4, and never skips the invariant ──────────
#
# isolation.py:1004 `_settle`: `if self.switches is not None and self.switches.a4 and
# request.kind != 'verify'`; 1005-1010 the eligibility refusal

def test_a_verifier_never_asks_a4_yet_never_skips_the_invariant(tmp_path, monkeypatch):
    """Branch caught: the `request.kind != 'verify'` half of 1004 (a verifier skips
    1005-1010 entirely) together with 1009-1010 for a normal request whose A4 facts are
    not facts. Dropping the `kind` test would fail every verifier attempt with
    `a4_unmet:production_dispatch` — A6's once-only attempt marker already spent, since
    the refusal lands after `_admit` — and a verifier is never production-dispatched in
    the first place. Dropping 1009-1010 the other way would let a harness that is not
    even admitted to dispatch reach the established save of 1011-1014.

    Closest existing test: test_pv20_activate.py::test_a4_requires_admission_and_
    invariant, which drives the whole activated core and only ever establishes an
    execution request; it never points a `kind == 'verify'` request at an A4-enforcing
    authority, never counts the `a4_eligibility` calls, and never asks whether a verify
    request that fails the invariant is still failed for its condition."""
    rig = Rig(tmp_path, monkeypatch, executions=2, switches=ALL_OPEN)
    a, b, s = rig.a, rig.b, rig.spies
    first_key = _verify_key()
    ok = a.establish(make_verify_request(first_key, tmp_path / 'v1'))
    assert ok.state == 'established' and a.held_job(first_key) is not None
    assert s.count('a4') == 0, 'a verifier asked A4 whether it may verify'

    # the bypass is A4 only: the six conditions still gate a verifier
    second_key = _verify_key()
    vreq = make_verify_request(second_key, tmp_path / 'v2')
    toolchain = os.path.normcase(os.path.abspath(
        [g.path for g in vreq.grants if g.row == 'toolchain'][0]))
    s.unverified = {toolchain}
    with pytest.raises(iso.IsolationUnavailable) as got:
        a.establish(vreq)
    assert got.value.reason == 'condition_unmet:grants'
    assert 'grant unreadable in the DACL' in got.value.detail
    assert s.count('a4') == 0
    assert a.record(second_key).state == 'failed'
    assert iso.profile_name(second_key) in b.deleted

    # and a normal request that is not admitted to dispatch is failed by A4 itself
    s.unverified = set()
    exec_id = list(rig.requests)[1]
    with pytest.raises(iso.IsolationUnavailable) as a4:
        a.establish(rig.requests[exec_id])
    assert a4.value.reason == 'a4_unmet' and a4.value.detail == 'production_dispatch'
    assert s.count('a4') == 1                        # asked for the execution, once
    kept = a.record(exec_id)
    assert kept.state == 'failed' and kept.failure == 'a4_unmet'
    # the six conditions it HAD met are kept as evidence: the refusal is A4's, not theirs
    assert kept.conditions['job'][0] is True and kept.conditions['grants'][0] is True
    assert list(kept.capabilities) == [] and s.count('mark_ended') == 0
    assert not os.path.lexists(_paths(tmp_path, exec_id).ended)
    assert iso.profile_name(exec_id) in b.deleted
    assert rig.ops().count('isolation_failed') == 2


# ── 8. §3.7: a stop that lands after the invariant refuses the established save ───
#
# isolation.py:1011-1014 `_settle`: `_save_establishment(rec)` → 875-879 refuses, and
# 977-978 `_establish` hands the owned profile to `_abandon_late`

def test_a_stop_after_the_invariant_refuses_the_established_save_and_leaves_one_release(
        tmp_path, monkeypatch):
    """Branch caught: 1014 reaching `_save_establishment`, whose own
    `_check_establishment` (875-878) raises for a stop that landed after the invariant
    completed, and 977-978 making the caller's cancellation cleanup the ONLY release.
    Removing that check is the dangerous mutation: the record would be written
    `established` with CAPABILITIES while Core is stopping, for a process that will
    never start — a later Core would resume an identity nothing ran, and the profile
    would never be deleted because release is driven by the cancellation path.

    Closest existing tests: test_gaps3_node_isolation_a.py's stop tests all stop the
    authority at `establish`'s entry check or inside `_ensure_job`, and
    test_fx32_isolation_stop.py::test_a_profile_created_after_the_stop_returned_is_
    deleted_by_its_own_establishment stops it before the profile exists. None stops
    between the invariant and the final save, so none asserts the call ORDER below: the
    invariant completed, the save refused, and exactly one release followed."""
    rig = Rig(tmp_path, monkeypatch)
    a, b, s = rig.a, rig.b, rig.spies
    eid = rig.request.execution_id
    name = iso.profile_name(eid)
    s.on_invariant[eid] = lambda _conditions: a.close_admission()   # the stop lands here
    ended = _paths(tmp_path, eid).ended

    with pytest.raises(iso.IsolationClosed) as got:
        a.establish(rig.request)

    assert isinstance(got.value, base.SpawnFailed)
    assert not isinstance(got.value, iso.IsolationUnavailable)
    assert not isinstance(got.value, OSError)
    assert str(got.value).count('cleanup failed') == 0        # the release succeeded
    # the order is the whole assertion: pending save, Job, facts, invariant, then the
    # established save refused, and the caller's cleanup the only release there was
    assert s.names() == ['save_establishment', 'ensure_job', 'job_facts', 'invariant',
                         'save_establishment', 'release']
    assert s.count('fail') == 0 and s.count('mark_ended') == 0
    assert s.count('release') == 1 and b.deleted == [name]    # the sole release path
    assert name not in b.profiles
    assert b.closed == [{'job': eid}] and a.held_jobs() == {}  # its Job died with it
    kept = a.record(eid)
    assert kept.state == 'pending' and kept.owned is True      # never established, never failed
    assert kept.sid == b.derive_sid(eid) and kept.failure == '' and kept.reason == ''
    assert kept.conditions == {} and list(kept.capabilities) == []
    assert not os.path.lexists(ended)
    assert rig.ops() == [] and rig.quarantine_lines() == []


# ── 9. §3.7/R6-A: the stop is published before the drain is asked for ────────────
#
# isolation.py:1103-1104 `close_admission`: `with self._state: self.closed = True`
# before 1105-1106 the timed acquire, and 1109-1110 the failed-acquire warning

def test_the_stop_is_published_before_the_drain_is_asked_for(tmp_path, monkeypatch,
                                                             caplog):
    """Branch caught: 1104 running before 1105, observed from inside the acquire. The
    comment at 1102 says an OS call may outlive the deadline, so the flag must be public
    *before* Core waits for the lock: `_ensure_job` re-checks `closed` only under that
    lock (1073-1076), and an establishment queued behind a close that had not published
    yet would be admitted after Core decided to stop. The mutation is to move the
    publication after the acquire (or to read the flag outside `_state`), which this test
    sees as the probe observing an open authority. Also pinned: an acquire that FAILED
    releases nothing (1107-1108 guards the release), and the drain timeout is logged.

    Closest existing test: test_gaps3_node_isolation_a.py's `_published` helper polls
    `closed` from a third thread while `close_admission` blocks on the lock; it shows the
    flag became true at some point, never what the acquire itself could observe, and no
    test anywhere asserts that a failed acquire leaves the lock alone."""
    rig = Rig(tmp_path, monkeypatch)
    a, b = rig.a, rig.b
    lock = ProbeLock(a, answer=False)
    monkeypatch.setattr(a, '_lock', lock)

    with caplog.at_level(logging.WARNING, logger='archeus.node.isolation'):
        a.close_admission()

    assert a.closed is True
    assert len(lock.acquires) == 1
    timeout, published, refused = lock.acquires[0]
    assert published is True, '1104 did not publish the stop before the acquire'
    assert refused == 'IsolationClosed', 'an establishment queued behind the close ' \
                                         'would have seen an open authority'
    assert timeout == -1                     # no deadline: wait without bound (1105)
    assert lock.releases == 0                # an acquire that failed owns nothing to give
    assert 'isolation establishment drain timed out' in caplog.text
    # the stop itself is inert: no profile, no Job, no note, no ledger line
    assert b.mutations() == [] and b.job_creates == 0 and b.closed == []
    assert rig.node.registry == [] and rig.quarantine_lines() == []


# ── 10. §3.7: the drain's timeout, its failed acquire and one level of release ───
#
# isolation.py:1105-1106 `close_admission`: `max(0.0, deadline - time.monotonic())`
# and 1107-1108 the guarded release

def test_an_expired_deadline_clamps_the_drain_and_a_reentrant_release_gives_one_level(
        tmp_path, monkeypatch, caplog):
    """Branch caught: the `max(0.0, ...)` clamp of 1106 for an expired deadline, 1107's
    false half (no release for an acquire that failed) and 1107-1108's true half under
    reentrancy: an establishment already holds the authority lock, so close's own
    acquire succeeds and its `release` must give back exactly one level. The mutations:
    dropping `max` hands `RLock.acquire` a negative timeout, which CPython treats as a
    *blocking* wait — Core's stop would then wait for an establishment it had already
    decided to refuse, past the deadline its caller gave it; and an unconditional
    release would let Core hand back a lock it never took, letting a second establishment
    start during the stop.

    Closest existing tests: test_fx32_isolation_stop.py calls `close_admission(deadline=
    0.0)` in six places and never asserts what the lock was asked for or what it was asked
    to give back; the drain timeout is load-bearing there and unobserved everywhere."""
    rig = Rig(tmp_path, monkeypatch)
    a = rig.a
    authority_lock = a._lock                     # the real RLock, captured before a probe
    clock = _Clock(1000.0)
    monkeypatch.setattr(iso, 'time', clock)

    # an expired deadline is a zero timeout, never a negative one
    expired = ProbeLock(a, answer=False)
    monkeypatch.setattr(a, '_lock', expired)
    with caplog.at_level(logging.WARNING, logger='archeus.node.isolation'):
        a.close_admission(deadline=clock.now - 25.0)
    assert expired.acquires and expired.acquires[0][0] == 0.0, \
        'the expired deadline reached acquire as %r' % (expired.acquires[0][0],)
    assert all(t >= 0.0 for t, _p, _r in expired.acquires)
    assert expired.releases == 0                    # a failed acquire releases nothing
    assert 'isolation establishment drain timed out' in caplog.text
    assert rig.b.mutations() == [] and rig.node.registry == []

    # the same call while an establishment holds the lock: acquired, and one level back
    caplog.clear()
    counter = CountingRLock(authority_lock)
    authority_lock.acquire()                             # the level one establishment holds
    authority_lock.acquire()                             # plus one more, as a nested path may
    monkeypatch.setattr(a, '_lock', counter)
    with caplog.at_level(logging.WARNING, logger='archeus.node.isolation'):
        a.close_admission(deadline=clock.now + 5.0)
    assert counter.acquires == [5.0] and counter.releases == 1
    assert 'isolation establishment drain timed out' not in caplog.text
    assert _free_from_another_thread(authority_lock) is False, \
        'close_admission handed back the levels it never took'
    authority_lock.release()
    authority_lock.release()
    assert _free_from_another_thread(authority_lock) is True, \
        'the level close_admission took was never given back'
    assert a.closed is True and rig.b.job_creates == 0
