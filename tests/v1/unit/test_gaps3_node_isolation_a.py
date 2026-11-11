"""T-1113 — the highest-risk uncovered branches of `archeus/node/isolation.py`
lines 615-1005 (HEAD 56d53504, 2026-11-10): closed establishment and atomic Job
admission (changed by 6027a5f9), fail-closed and denial first, then boundaries,
then error paths, then concurrency orderings forced with seams/events, never sleeps.

Selected branches (each test names its own in its docstring):
  1. establish 802-803 precedes the verifier's once-only `_admit` (804-808):
     a stopped core never consumes a verifier attempt.
  2. establish 802-803 precedes every record write: a stopped core leaves a
     resumable `established` record byte-for-byte as found.
  3. `_ensure_job` 934-935 precedes the memo-table read (936-937): a closed
     authority refuses even a Job it already holds, and neither hands it back
     nor drops it.
  4. `_ensure_job` 934-935 via `assign` (990-992) and fresh ids: a closed
     authority never reaches `boundary.create_job` (938-939).
  5. `_ensure_job` 938 raises: no phantom held Job at 939, and the lock is
     released.
  6. `_ensure_job`'s `with self._lock` (933) around the create (938) vs
     `close_admission` (950-954): an in-flight create makes close wait — the
     Job is created whole or not at all.
  7. the same lock, the other order: a close that wins the lock refuses the
     create queued behind it (933-935).
  8. a closure landing between establish's entry check (802) and `_ensure_job`
     (871): `IsolationClosed` is SpawnFailed (83-90), not OSError, so the
     establish catch-all at 826-827 must not turn the stop into `_fail` — the
     record stays the resumable `pending` evidence, never `failed`.
  9. `close_admission` (950-954) repeated: held Jobs, records and profiles are
     untouched; only the explicit fence closes a Job, exactly once.
 10. `_save` 729-734, the `state == 'invalid'` half: an untrusted record is
     evidence and can never be written back (the `applied` half of the same
     guard already has a regression test).

Everything runs against a synthetic boundary — no AppContainer, Job, process,
handle or DLL call, no subprocess, no sleep, no real environment value; it runs
unchanged on Linux and is reviewable on Windows. The autouse tripwire below
fails any test that reaches a real Win32 primitive.
"""

import json
import os
import threading
import zlib

import pytest

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.infra.paths import isolation_dir, isolation_state, quarantine_log, \
    verify_consumed
from archeus.node import isolation as iso

#: bounded ceiling for every event wait and thread join in this file (no sleeps)
JOIN_S = 5.0


# ── the lowest mutation boundary, armed for every test in this file ───────────

@pytest.fixture(autouse=True)
def no_real_win32(monkeypatch):
    """The synthetic boundary is the reason none of this is reachable; the guard is
    the belt (RULES: written on Linux, reviewed on Windows, never a real DLL)."""
    hits = []
    for name in ('_CreateAppContainerProfile', '_DeleteAppContainerProfile',
                 '_GetSecurityInfoByNameW', '_CreateProcessW', '_CreateJobObjectW',
                 '_AssignProcessToJobObject', '_TerminateProcess', '_CloseHandle',
                 '_SetInformationJobObject', '_ResumeThread', '_OpenProcess'):
        def trip(*a, _name=name):
            hits.append(_name)
            raise AssertionError('the real %s was reached' % _name)
        monkeypatch.setattr(iso, name, trip, raising=False)
    yield hits
    assert hits == [], 'a real mutation primitive was reached: %r' % (hits,)


@pytest.fixture
def fence_clock(monkeypatch):
    """The fence's clock, moved only by its own polls (never a wall sleep)."""
    now = [0.0]
    monkeypatch.setattr(iso, '_clock', lambda: now[0])
    monkeypatch.setattr(iso, '_sleep', lambda s: now.__setitem__(0, now[0] + s))
    return now


# ── the synthetic boundary: answers Core's OS questions, decides nothing ───────

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
        self.create_fail = None
        self.delete_fail = set()
        self.profiles = set()
        self.sids = {}
        self.on_create = None             # called inside create_profile (a seam)
        self.created = []
        self.deleted = []
        self.closed = []                  # every close_job handle
        self.assigned = []
        self.order = []                   # the Job query/close order
        self.active = []                  # job_active_processes answers (else 0)
        self.job_creates = 0
        self.create_job_hook = None       # called inside create_job (a seam)

    def available(self):
        return self.available_ok

    def create_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        if self.on_create is not None:
            self.on_create()
        if self.create_fail:
            raise iso.IsolationUnavailable(self.create_fail, 'synthetic')
        existed = name in self.profiles
        self.profiles.add(name)
        self.created.append(name)
        return {'profile': name, 'sid': self.sids.get(name) or _stable_sid(name),
                'created': True, 'existed': existed, 'package_dir': 'materialized'}

    def delete_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        self.deleted.append(name)
        if name in self.delete_fail:
            raise iso.IsolationUnavailable('profile_delete', 'in use (synthetic)')
        self.profiles.discard(name)

    def profile_exists(self, execution_id):
        return iso.profile_name(execution_id) in self.profiles

    def derive_sid(self, execution_id):
        return _stable_sid(iso.profile_name(execution_id))

    def derive(self, execution_id):
        return self.derive_sid(execution_id)

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
        if self.create_job_hook is not None:
            self.create_job_hook(execution_id)
        return {'job': execution_id}

    def job_facts(self, handle):
        if handle is None:
            return None
        return {'type': 'Job', 'name': '', 'inheritable': False}

    def job_active_processes(self, job):
        self.order.append('query')
        return self.active.pop(0) if self.active else 0

    def assign_job(self, job, process_handle):
        self.assigned.append((job, process_handle))

    def close_job(self, job):
        self.order.append('close')
        self.closed.append(job)

    def mutations(self):
        """Every call that would change OS state: the profile store, a Job, a process."""
        return self.created + self.deleted + self.assigned


class FakeNode:
    id = 'fake-node'

    def __init__(self):
        self.registry = []

    def _registry(self, line):
        self.registry.append(line)


def new_execution_id():
    return ids.new_id('execution')


def make_exec_request(execution_id, root):
    """An §3.1 inventory a synthetic fixture can satisfy but production cannot: every
    required row present on a real directory, the broker present, the class 1, 2 and 3
    directories separated, and Core's own state kept outside the boundary."""
    def d(name):
        p = os.path.join(root, name)
        os.makedirs(p, exist_ok=True)
        return p
    workspace = d('workspace')
    mailbox = d('mailbox')
    response = d('response')
    sentinel = d('sentinel')
    state = d('state')
    spawn_config = os.path.join(response, 'spawn_config.json')
    with open(spawn_config, 'w', encoding='utf-8') as f:
        json.dump({'argv': []}, f)
    grants = (iso.Grant(workspace, 'rw', 'workspace'),
              iso.Grant(d('runtime'), 'rx', 'runtime'),
              iso.Grant(d('hook'), 'rx', 'hook'),
              iso.Grant(mailbox, 'rw', 'request'),
              iso.Grant(response, 'rx', 'response'),
              iso.Grant(sentinel, 'rx', 'sentinel'),
              iso.Grant(state, 'rw', 'state'))
    return iso.IsolationRequest(execution_id=execution_id, workspace=workspace,
                                grants=grants, mailbox=mailbox, response=response,
                                sentinel=sentinel, spawn_config=spawn_config,
                                state_dir=state, core_state=d('core_state'),
                                broker=d('broker'))


def make_verify_request(key, root):
    """A verifier attempt's whole inventory (A6): checkout, scratch, a read-only
    toolchain, and Core's own state named and kept apart."""
    def d(name):
        p = os.path.join(root, name)
        os.makedirs(p, exist_ok=True)
        return p
    checkout = d('checkout')
    return iso.IsolationRequest(execution_id=key, workspace=checkout,
                                grants=(iso.Grant(checkout, 'rw', 'checkout'),
                                        iso.Grant(d('scratch'), 'rw', 'scratch'),
                                        iso.Grant(d('toolchain'), 'rx', 'toolchain')),
                                core_state=d('core_state'))


def authority(tmp_path, *, boundary=None, request=None):
    """An `Isolation` authority wired to a fake boundary and a satisfying plan."""
    node = FakeNode()
    b = boundary or FakeBoundary()
    req = request or make_exec_request(new_execution_id(), str(tmp_path))
    a = iso.Isolation(node, boundary=b, plan=lambda spec: req)
    return a, b, req, node


def _verify_key(attempt=0, vid=None):
    return iso.Principal('verify', vid or ids.new_id('verification'), attempt).key


def _read_record_bytes(execution_id):
    with open(isolation_state(execution_id), 'rb') as f:
        return f.read()


def _plant(execution_id, payload):
    """A record file written exactly as given, bypassing Core; returns the bytes."""
    os.makedirs(isolation_dir(), exist_ok=True)
    path = isolation_state(execution_id)
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
    with open(path, 'wb') as f:
        f.write(data)
    return data


def _ledger_ops():
    if not os.path.exists(quarantine_log()):
        return []
    with open(quarantine_log(), encoding='utf-8') as f:
        return [json.loads(x)['op'] for x in f.read().splitlines() if x.strip()]


def _start(threads, fn):
    """Run *fn* on a tracked thread; the result or error comes back in the box.
    Every started thread is joined by the caller's `finally`, bounded by JOIN_S."""
    box = {}

    def body():
        try:
            box['result'] = fn()
        except BaseException as err:            # carried, then asserted on the main thread
            box['error'] = err
    t = threading.Thread(target=body)
    threads.append(t)
    t.start()
    return box


def _drain(threads, release):
    """`finally` half of every race test: free the seam, join every thread started,
    each bounded, and surface any error a thread body deferred."""
    release()
    for t in threads:
        t.join(JOIN_S)
        assert not t.is_alive(), 'a test thread outlived its bounded join'


# ── 1. §3.4/A6: stopping never consumes a verifier attempt ────────────────────
#
# isolation.py:802-803 `establish`: `if self.closed: raise IsolationClosed()`
# isolation.py:804-808 `establish`: the verify branch's `_admit(request.execution_id)`

class TestClosedEstablishmentRefusesBeforeAnythingElse:
    def test_a_stopped_core_never_consumes_a_verifier_attempt(self, tmp_path):
        """Lines 802-803 run before the once-only `_admit` of 804-808. The closest
        existing tests — test_pv20_activate.py::test_a_late_worker_can_create_no_job_
        once_core_is_stopping (an exec-kind request, no marker involved) and
        test_pv20_isolation.py::test_an_attempt_that_cannot_be_marked_is_not_admitted
        (a marking failure while open) — never point a request with `kind == 'verify'`
        at a closed authority, so neither sees the consumed marker. If the closed
        check moved below the verify branch, `_admit` would create the marker for an
        attempt Core then refused: permanently consumed, unstartable after a restart,
        and the refusal would name `attempt_consumed`, not `core_stopping`."""
        key = _verify_key()
        a, b, _req, node = authority(
            tmp_path, request=make_verify_request(key, str(tmp_path / 'v')))
        a.close_admission()
        with pytest.raises(iso.IsolationClosed) as got:
            a.establish(make_verify_request(key, str(tmp_path / 'v2')))
        # IsolationClosed is the stop's SpawnFailed (83-90), never an establishment
        # failure the record or instrument could be written up for
        assert isinstance(got.value, base.SpawnFailed)
        assert not isinstance(got.value, iso.IsolationUnavailable)
        assert not os.path.lexists(verify_consumed(key))     # the attempt is NOT consumed
        assert not os.path.lexists(isolation_state(key))     # no record was started
        assert b.mutations() == [] and b.job_creates == 0    # nothing was created
        assert node.registry == []                           # and nothing was noted
        # and the attempt is still whole: a fresh, open authority admits and establishes
        # it exactly as if the stopped attempt had never happened
        a2, b2, _, _ = authority(tmp_path, boundary=FakeBoundary())
        assert a2.establish(make_verify_request(key, str(tmp_path / 'v3'))).state \
            == 'established'
        assert os.path.isfile(verify_consumed(key))


# ── 2. §3.7/O7: stopping leaves the record a resume reads, exactly as found ───
#
# isolation.py:802-803 `establish` before any write; isolation.py:850 `_establish`:
# `self._save(rec)`

class TestTheResumableRecordSurvivesAStop:
    def test_a_stopped_core_leaves_a_resumable_record_byte_for_byte(self, tmp_path):
        """Lines 802-803 run before `_establish` can save (850) the `pending` state a
        resume would overwrite. test_pv20_isolation.py::test_resume_reuses_the_
        established_identity re-establishes while open, and test_pv20_activate.py's
        late-worker test has no record at all (`record(...) is None`); neither asserts
        that a *closed* establish leaves an existing `established` record untouched.
        If the closed check moved below the resume handling, the stopped establish
        would rewrite the record (pending, new updated/at): the execution loses the
        resume identity R7 promises, and O7 reads a failure Core never had."""
        a, b, req, node = authority(tmp_path)
        assert a.establish(req).state == 'established'
        before = _read_record_bytes(req.execution_id)
        noted = len(node.registry)
        a.close_admission()
        with pytest.raises(iso.IsolationClosed):
            a.establish(req)                          # the resume attempt, refused
        assert _read_record_bytes(req.execution_id) == before   # no write at all
        d = json.loads(before.decode('utf-8'))
        assert d['state'] == 'established' and d['failure'] == '' and d['owned'] is True
        assert b.created == [d['profile']] and b.job_creates == 1  # nothing further ran
        assert len(node.registry) == noted                        # no new instrument line


# ── 3-7. §3.7/R6-A: the Job table is created whole or refused, under one lock ─
#
# isolation.py:933-940 `_ensure_job`; isolation.py:950-954 `close_admission`;
# isolation.py:990-992 `assign`

class TestClosedJobAdmission:
    def test_a_stopped_core_hands_back_no_job_not_even_one_it_holds(self, tmp_path):
        """Lines 934-935 run before the memo-table read of 936-937, so a closed
        authority cannot return — or act on — a Job it already holds. The closest
        existing tests call `_ensure_job` while open (test_gaps_isolation_650.py's
        TestTheJobTable) or after a stop with nothing held
        (test_pv20_activate.py::test_a_late_worker_can_create_no_job_once_core_is_
        stopping). If the closed check moved below the memo lookup, the stopped call
        would answer the held handle: a caller could keep assigning into a Job Core
        had just stopped admitting. The handle stays held here, unclosed, until the
        explicit teardown."""
        a, b, req, _ = authority(tmp_path)
        a._ensure_job(req.execution_id)
        held = a.held_job(req.execution_id)
        a.close_admission()
        with pytest.raises(iso.IsolationClosed):
            assert a._ensure_job(req.execution_id)          # never hands the held Job back
        assert a.held_job(req.execution_id) is held         # neither dropped nor replaced
        assert a.held_jobs() == {req.execution_id: held}
        assert b.closed == [] and b.job_creates == 1        # nothing closed, none added
        out = a.teardown(req.execution_id, reason='ended')  # the Job is still Core's to end
        assert out['job'] == 'closed' and b.closed == [held]

    def test_a_stopped_core_creates_no_job_for_an_unseen_execution(self, tmp_path):
        """Lines 934-935 before lines 938-939: neither `assign` (990-992) nor a fresh
        `establish` can reach `boundary.create_job` once closed. The activate suite's
        late-worker test asserts the table stays empty but never counts the boundary's
        own create call, and TestTheJobTable only assigns while open. Drop the check
        and a late worker mints a real kill-on-close Job after Core decided to stop —
        a Job nothing will close on the way out. The observable here is the boundary's
        own call count: zero, with no profile, no assign, no record and no note."""
        a, b, _req, node = authority(tmp_path)
        a.close_admission()
        unseen = new_execution_id()
        with pytest.raises(iso.IsolationClosed):
            a._ensure_job(unseen)
        with pytest.raises(iso.IsolationClosed):
            a.assign(unseen, 'PROCESS-HANDLE')
        with pytest.raises(iso.IsolationClosed):
            a.establish(make_exec_request(new_execution_id(), str(tmp_path / 'late')))
        assert b.job_creates == 0 and b.assigned == []      # the boundary was never asked
        assert b.created == [] and b.mutations() == []      # no identity, no process path
        assert a.held_jobs() == {} and a.held_job(unseen) is None
        assert node.registry == [] and _ledger_ops() == []  # the stop is not a failure

    def test_a_job_that_could_not_be_created_leaves_no_phantom_hold(self, tmp_path):
        """Line 938 raising must leave line 939 unexecuted: no half-entry in Core's
        sole table, and the `with self._lock` of 933 must still release. The crash
        tests around test_pv20_isolation.py::test_crash_after_the_ownership_save_is_
        recovered only read the record back; none asserts the live authority's own Job
        table, its close calls, or that the lock survived the raise. If the table were
        filled before (or despite) the failure, Core would later close_job a handle the
        OS never made — or poison the slot so the real create is skipped; if the raise
        escaped the lock, stopping would deadlock Core forever."""
        a, b, _req, _node = authority(tmp_path)
        eid = new_execution_id()
        boom = [OSError('create_job denied (synthetic)')]

        def flaky(execution_id):                    # first attempt raises, retry succeeds
            if boom:
                raise boom.pop(0)

        b.create_job_hook = flaky
        with pytest.raises(OSError):
            a._ensure_job(eid)
        assert a.held_jobs() == {} and a.held_job(eid) is None   # no phantom held Job
        assert b.closed == []                                    # nothing to close was had
        threads = []
        try:
            # both the retry and the stop must re-acquire the lock of 933: a raise
            # that leaked it would hang them, and the bounded join fails the test
            retry = _start(threads, lambda: a._ensure_job(eid))   # creates once, really
            _drain(threads, lambda: None)
            assert 'error' not in retry and retry['result'] == {'job': eid}
            stop = _start(threads, a.close_admission)
            _drain(threads, lambda: None)
        finally:
            for t in threads:
                t.join(JOIN_S)
        assert a.held_job(eid) == {'job': eid}                    # the retried Job is held
        assert b.job_creates == 2                                 # one refused, one real
        assert 'error' not in stop and a.closed is True           # the lock was never lost

    def test_a_create_in_flight_makes_core_wait_to_finish_stopping(self, tmp_path):
        """The create of 938 runs inside the lock of 933, and `close_admission`
        (950-954) takes that same lock: while a create is in flight, close cannot
        observe a half-admitted Job and must wait. The activate suite orders
        `core.stop` around held_jobs/fence stubs, never against the authority lock
        itself. Without the lock around 938-939, close could land between the create
        and the store — Core 'stopped' with a Job appearing after the decision. The
        seam is a create blocked on an Event, so the ordering is forced, never raced."""
        a, b, _req, _ = authority(tmp_path)
        eid = new_execution_id()
        inside, release = threading.Event(), threading.Event()
        seq = []

        def slow_create(execution_id):
            seq.append('create-start')
            inside.set()
            assert release.wait(JOIN_S)
            seq.append('create-end')

        b.create_job_hook = slow_create
        threads = []
        try:
            job = _start(threads, lambda: a._ensure_job(eid))
            assert inside.wait(JOIN_S), 'the create never entered the boundary'
            stop = _start(threads, lambda: (a.close_admission(),
                                            seq.append('closed')))  # queues behind the held lock
            assert a.closed is False                     # close cannot pass an in-flight
            assert list(seq) == ['create-start']         # admission: not started, not done
            assert 'closed' not in seq                   # it has not returned either
            release.set()
            for t in threads:
                t.join(JOIN_S)
                assert not t.is_alive()
            assert 'error' not in job and 'error' not in stop
            assert job['result'] == {'job': eid}         # the in-flight Job was admitted
        finally:
            release.set()
            for t in threads:
                t.join(JOIN_S)
        assert list(seq) == ['create-start', 'create-end', 'closed']  # whole, then stop
        assert a.closed is True and a.held_job(eid) == {'job': eid}
        assert b.job_creates == 1


def _start_two_racing(a, b):
    """Force the ordering of probe 7 deterministically: one create holds the authority
    lock inside the boundary (blocked on `release`); the close thread and a second
    create (different id) both queue behind it, started in that order while the lock
    is provably held. Releasing lets the queued close — first waiter in, CPython's
    lock wakes its waiters in arrival order — win the lock before the second create
    ever reaches line 936."""
    eid1, eid2 = new_execution_id(), new_execution_id()
    inside, release = threading.Event(), threading.Event()
    seq = []

    def gated(execution_id):
        if execution_id == eid1:
            seq.append('create-start')
            inside.set()
            assert release.wait(JOIN_S)
            seq.append('create-end')
        else:                                        # a create that must never run
            seq.append('second-create')

    b.create_job_hook = gated
    threads = []
    job1 = _start(threads, lambda: a._ensure_job(eid1))
    assert inside.wait(JOIN_S), 'the first create never entered the boundary'
    stop = _start(threads, a.close_admission)         # queued first
    late = _start(threads, lambda: a._ensure_job(eid2))   # queued second
    return threads, (job1, stop, late), release, seq, eid1, eid2


class TestTheCloseWinsTheLock:
    def test_a_close_that_wins_the_lock_admits_no_more_jobs(self, tmp_path):
        """Lines 933-935: the create queued behind `close_admission` re-checks
        `closed` only once it holds the lock, so a close that wins the lock refuses it
        (935) without ever reaching the boundary (938). test_pv20_activate.py's
        late-worker test closes first and then calls, which proves the flag, not the
        lock ordering; here the attempt is already queued inside `_ensure_job` when
        the stop lands. If lines 934-935 sat outside the lock of 933, the queued
        create could pass the check, leave, and be minted after Core stopped — a
        kill-on-close Job created past the stop. The queued second create publishes
        nothing here: no second boundary call, no second hold."""
        a, b, _req, _ = authority(tmp_path)
        threads, (job1, stop, late), release, seq, eid1, eid2 = _start_two_racing(a, b)
        try:
            release.set()
            for t in threads:
                t.join(JOIN_S)
                assert not t.is_alive()
        finally:
            release.set()
            for t in threads:
                t.join(JOIN_S)
        assert 'error' not in job1 and 'error' not in stop
        assert isinstance(late.get('error'), iso.IsolationClosed)     # refused at 935
        assert 'second-create' not in seq                             # never reached 938
        assert b.job_creates == 1                                     # only the in-flight one
        assert list(a.held_jobs()) == [eid1]          # the won close admitted nothing new
        assert a.held_job(eid1) == {'job': eid1}      # and emptied nothing on the way
        assert b.closed == []


# ── 8. §3.7/O7: a stop mid-flight fails the record nothing ────────────────────
#
# isolation.py:826-827 `establish`: `except OSError as err: return self._fail(...)`
# isolation.py:871 `_establish`: `job = self._ensure_job(request.execution_id)`

class TestAStopMidEstablishmentFailsNothing:
    def test_stopping_between_the_entry_check_and_the_job_keeps_the_pending_record(
            self, tmp_path):
        """The closed check of 802 passed, then the stop lands (here through the
        boundary seam inside `create_profile`), and `_ensure_job` (871 -> 935) raises
        `IsolationClosed`. Lines 826-827 catch `OSError` only, and IsolationClosed is
        `base.SpawnFailed` (83-90), so the stop escapes uncaught and `_fail` never
        runs: the record stays the `pending`, owned resume evidence of 850 and 865,
        NOT `failed`. The crash tests of test_pv20_isolation.py inject
        RuntimeError (a hard crash) and the establishment-failure tests inject
        IsolationUnavailable (charged at `_fail`); none stops between the entry
        check and the Job. Turn IsolationClosed into an IsolationUnavailable (or
        OSError) and this very stop writes a `failed` record for an execution that
        only stopped — the card's defect #9 — and the instrument accuses Core of an
        establishment failure it never had."""
        a, b, req, node = authority(tmp_path)
        b.on_create = a.close_admission               # the stop lands mid-establishment
        with pytest.raises(iso.IsolationClosed) as got:
            a.establish(req)
        assert isinstance(got.value, base.SpawnFailed)
        assert not isinstance(got.value, iso.IsolationUnavailable)
        on_disk = json.loads(_read_record_bytes(req.execution_id).decode('utf-8'))
        assert on_disk['state'] == 'pending'          # never marked failed merely for stopping
        assert on_disk['owned'] is True and on_disk['failure'] == ''
        assert on_disk['sid'] == b.derive_sid(req.execution_id)
        assert [l['op'] for l in node.registry] == []          # no isolation_failed line
        assert b.job_creates == 0 and b.closed == []           # no Job, nothing closed
        assert b.deleted == [] and _ledger_ops() == []         # nothing released or quarantined
        # and the record is exactly what a restarted Core resumes from (a retry of one
        # that stopped, Finding 1): the same authority, still stopping, refuses it again
        with pytest.raises(iso.IsolationClosed):
            a.establish(req)
        assert json.loads(_read_record_bytes(req.execution_id).decode('utf-8')) == on_disk


# ── 9. §3.7: the stop itself is inert; only the fence ends a held Job ─────────
#
# isolation.py:950-954 `close_admission`; isolation.py:956-985 `fence`

class TestRepeatedStopIsInert:
    def test_repeated_stopping_leaves_held_jobs_and_records_until_the_fence(
            self, tmp_path, fence_clock):
        """Lines 950-954 do one thing: set the flag under the lock. Twice more must
        be twice more of nothing — the held Job, its record and its profile stand
        until an explicit fence closes the Job (956-985) and only teardown deletes.
        test_pv20_activate.py covers `core.stop`'s own ordering and the fence tests
        never call `close_admission` at all, so nothing pins the stop's inertness:
        if 953-954 grew a pop or close, Core would kill live executions from a call
        documented to only refuse new work; if the fence's finally (983) were read as
        once-only-per-flag, the second stop would reopen the Job."""
        a, b, req, node = authority(tmp_path)
        rec = a.establish(req)
        held = a.held_job(req.execution_id)
        before = _read_record_bytes(req.execution_id)
        noted = len(node.registry)
        a.close_admission()
        a.close_admission()
        assert a.closed is True
        assert a.held_job(req.execution_id) is held and a.held_jobs() == {
            req.execution_id: held}                          # still Core's, still whole
        assert b.closed == [] and b.deleted == []            # nothing ended, nothing deleted
        assert _read_record_bytes(req.execution_id) == before  # the record is untouched
        assert rec.state == 'established'
        assert len(node.registry) == noted and _ledger_ops() == []
        assert a.fence(req.execution_id) is None             # quiescent on the fake clock
        assert b.order == ['query', 'close'] and b.closed == [held]
        assert a.held_job(req.execution_id) is None          # the fence ended the hold
        assert b.deleted == []                               # and deleted no profile
        assert _read_record_bytes(req.execution_id) == before  # the fence is no cleanup
        assert a.fence(req.execution_id) == 'no Job is held for it'   # the second one asks
        assert b.order == ['query', 'close']                            # nothing, twice over


# ── 10. §3.7/O7: an untrusted record is evidence and can never be written ─────
#
# isolation.py:729-734 `_save`: `if rec.state == 'invalid' ... raise ValueError`

class TestAnUntrustedRecordIsNeverWritten:
    def test_an_invalid_record_refuses_to_be_saved_and_stays_exactly_as_found(
            self, tmp_path):
        """The `state == 'invalid'` half of the guard of 729-734: the `applied` half
        already fails `test_pv20_isolation.py::test_applied_access_stays_empty_on_
        every_path`, and the forged-record tests only prove readers leave it alone —
        none attempts to *save* an invalid-state record. `record()` hands back an
        invalid-state object for exactly the execution whose file is untrustworthy;
        if 729-734 stopped refusing it, any later path that saves that object (a
        sweep, a cleanup retry) would overwrite the evidence O7's reconciliation and
        every later reader depend on, with a state Core only guessed. The observable
        is the untouched file bytes, not just the raise."""
        a, b, _req, node = authority(tmp_path)
        eid = new_execution_id()
        planted = _plant(eid, b'{ this is not json')          # unreadable: state invalid
        rec = a.record(eid)
        assert rec.state == 'invalid'
        with pytest.raises(ValueError):
            a._save(rec)
        assert _read_record_bytes(eid) == planted             # the evidence is as found
        assert [l['op'] for l in node.registry] == ['isolation_invalid']
        assert b.mutations() == []                            # and the stop of it is quiet
        assert _ledger_ops() == []
