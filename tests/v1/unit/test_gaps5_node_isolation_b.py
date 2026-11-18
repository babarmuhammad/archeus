import json
import logging
import os
import threading
import time

import pytest

from archeus.core.domain import ids
from archeus.infra.paths import ExecPaths, isolation_state
from archeus.node import isolation as iso
JOIN_S = 5.0
LOGGER = 'archeus.node.isolation'


@pytest.fixture(autouse=True)
def no_real_win32(monkeypatch):
    hits = []
    for name in ('_CloseHandle', '_CreateFileW', '_CreateJobObjectW',
                 '_QueryInformationJobObject', '_SetInformationJobObject',
                 '_AssignProcessToJobObject', '_TerminateJobObject', '_GetExitCodeProcess',
                 '_GetProcessTimes', '_OpenProcess', '_GetCurrentProcess', '_DuplicateHandle',
                 '_SetHandleInformation', '_GetHandleInformation', '_QueryObject',
                 '_OpenProcessToken', '_GetTokenInformation', '_GetSecurityInfoByNameW'):
        def trip(*a, _name=name):
            hits.append(_name)
            raise AssertionError('the real %s was reached' % _name)
        monkeypatch.setattr(iso, name, trip, raising=False)
    yield hits
    assert hits == [], 'a real mutation primitive was reached: %r' % (hits,)


class FakeBoundary:
    id = 'fake'

    def __init__(self):
        self.available_ok = True
        self.profiles = set()
        self.created = []
        self.deleted = []
        self.closed = []
        self.assigned = []
        self.job_creates = []
        self.job_handle = None
        self.create_job_hook = None
        self.close_job_hook = None
        self.close_job_fail = None

    def available(self):
        return self.available_ok

    def create_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        self.profiles.add(name)
        self.created.append(name)
        return {'profile': name, 'sid': 'S-1-15-3-9-00000001', 'created': True,
                'existed': False, 'package_dir': 'materialized'}

    def delete_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        self.deleted.append(name)
        self.profiles.discard(name)

    def profile_exists(self, execution_id):
        return iso.profile_name(execution_id) in self.profiles

    def derive_sid(self, execution_id):
        return 'S-1-15-3-9-00000001'

    def grant_established(self, path, sid, access):
        return True

    def granted_to(self, path, sid):
        return False

    def capability_grants(self):
        return ()

    def create_job(self, execution_id):
        self.job_creates.append(execution_id)
        if self.create_job_hook is not None:
            self.create_job_hook(execution_id)
        return {'job': execution_id} if self.job_handle is None else self.job_handle

    def close_job(self, job):
        self.closed.append(job)
        if self.close_job_hook is not None:
            self.close_job_hook(job)
        if self.close_job_fail is not None:
            raise self.close_job_fail

    def assign_job(self, job, process_handle):
        self.assigned.append((job, process_handle))

    def job_active_processes(self, job):
        return 0

    def mutations(self):
        return self.created + self.deleted + self.closed + self.assigned


class FakeNode:
    id = 'fake-node'

    def __init__(self):
        self.registry = []
        self.registry_fail = None

    def _registry(self, line):
        if self.registry_fail is not None:
            raise self.registry_fail
        self.registry.append(line)


class LockSeam:
    def __init__(self):
        self._real = threading.RLock()
        self._depth = 0
        self._owner = None
        self.calls = []
        self.releasers = []

    def acquire(self, blocking=True, timeout=-1):
        ok = self._real.acquire(blocking, timeout)
        self.calls.append(('acquire', timeout, ok))
        if ok:
            self._depth += 1
            self._owner = threading.current_thread()
        return ok

    def release(self):
        me = threading.current_thread()
        if self._depth == 0 or me is not self._owner:
            raise RuntimeError('cannot release un-acquired lock')
        self.calls.append(('release', self._depth))
        self.releasers.append(me)
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
        self._real.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    @property
    def depth(self):
        return self._depth

    @property
    def owner(self):
        return self._owner

    def locked(self):
        return self._depth > 0

    def timeouts(self):
        return [c[1] for c in self.calls if c[0] == 'acquire']

    def acquired(self):
        return [c[2] for c in self.calls if c[0] == 'acquire']

    def releases(self):
        return [c[1] for c in self.calls if c[0] == 'release']


def authority(boundary=None, node=None):
    node = node or FakeNode()
    boundary = boundary or FakeBoundary()
    return iso.Isolation(node, boundary=boundary), boundary, node


def new_execution_id():
    return ids.new_id('execution')


def record_for(execution_id, **kw):
    return iso.IsolationRecord(execution_id=execution_id,
                               profile=iso.profile_name(execution_id), **kw)


def raiser(exc):
    def step(*args, **kwargs):
        raise exc
    return step


def _spawn(tracked, fn):
    box = {}

    def body():
        try:
            box['result'] = fn()
        except BaseException as err:
            box['error'] = err
    t = threading.Thread(target=body)
    tracked.append(t)
    t.start()
    return t, box


def _join_all(tracked):
    for t in tracked:
        t.join(JOIN_S)
        assert not t.is_alive(), 'a test thread outlived its bounded join'


def _warnings(caplog):
    return [r.getMessage() for r in caplog.records if r.name == LOGGER]


def _free(lock):
    got = lock.acquire(blocking=False)
    if got:
        lock.release()
    return got


class TestTheClosedCheckRunsInsideTheStateLock:
    def test_a_refused_job_never_reads_the_table_and_leaks_neither_lock(self):
        a, b, node = authority()
        eid = new_execution_id()
        held = a._ensure_job(eid)
        assert b.job_creates == [eid]
        reads, writes = [], []

        class Table(dict):
            def get(self, key, default=None):
                reads.append(key)
                return dict.get(self, key, default)

            def __setitem__(self, key, value):
                writes.append(key)
                dict.__setitem__(self, key, value)

        a._jobs = Table(a._jobs)
        a.close_admission()
        with pytest.raises(iso.IsolationClosed):
            a._ensure_job(eid)
        assert reads == [] and writes == []
        assert b.job_creates == [eid] and b.closed == []
        assert b.mutations() == []
        assert node.registry == []
        assert _free(a._lock) and _free(a._state)
        assert dict(a._jobs) == {eid: held}


class TestTheBoundedDrain:
    def test_a_drain_that_cannot_take_the_lock_warns_and_holds_nothing_back(self, caplog):
        a, b, _node = authority()
        seam = LockSeam()
        a._lock = seam
        held, release = threading.Event(), threading.Event()
        done = threading.Event()
        threads = []

        def establishment():
            with seam:
                held.set()
                assert release.wait(JOIN_S)

        def stopper():
            a.close_admission(deadline=0.0)
            done.set()

        holder, _box = _spawn(threads, establishment)
        caplog.set_level(logging.WARNING, logger=LOGGER)
        try:
            assert held.wait(JOIN_S), 'the holder never took the lock'
            _stopper_thread, stop_box = _spawn(threads, stopper)
            assert done.wait(JOIN_S), 'the bounded stop waited on a lock it does not own'
            assert 'error' not in stop_box, stop_box.get('error')
            assert a.closed is True
            assert seam.timeouts() == [-1, 0.0]
            assert seam.acquired() == [True, False]
            assert seam.releases() == []
            assert _warnings(caplog) == ['isolation establishment drain timed out']
            assert seam.depth == 1 and seam.owner is holder
            assert b.job_creates == [] and b.mutations() == []
        finally:
            release.set()
            _join_all(threads)
        assert seam.releases() == [1] and seam.releasers == [holder]
        assert seam.depth == 0 and _free(seam)


class TestTheStopFromTheThreadThatAlreadyHoldsTheLock:
    def test_a_stop_from_the_owner_preserves_the_outer_lock(self):
        a, b, _node = authority()
        seam = LockSeam()
        a._lock = seam
        threads, probes = [], []
        inside, gate, seen = threading.Event(), threading.Event(), {}

        def establishment():
            with seam:
                a.close_admission()
                seen['calls'] = list(seam.calls)
                seen['depth'] = seam.depth
                seen['owner'] = seam.owner
                seen['closed'] = a.closed
                inside.set()
                assert gate.wait(JOIN_S)

        owner, box = _spawn(threads, establishment)
        try:
            assert inside.wait(JOIN_S), 'the establishment never took the lock'
            waiter, probe = _spawn(probes, lambda: seam.acquire(blocking=False))
            waiter.join(JOIN_S)
            assert not waiter.is_alive() and 'error' not in probe
            assert probe['result'] is False, 'the stop handed out a lock still held'
            assert 'error' not in box, box.get('error')
            assert seen['depth'] == 1 and seen['owner'] is owner
            assert seen['closed'] is True and a.closed is True
            assert b.job_creates == [] and b.mutations() == []
        finally:
            gate.set()
            _join_all(threads + probes)
        assert seam.depth == 0
        assert _free(seam)


class TestTheDeadlineAlreadyPast:
    def test_a_deadline_behind_the_clock_is_a_zero_timeout_not_a_negative_wait(self, caplog):
        a, b, _node = authority()
        seam = LockSeam()
        a._lock = seam
        caplog.set_level(logging.WARNING, logger=LOGGER)
        a.close_admission(deadline=time.monotonic() - 5.0)
        a.close_admission(deadline=-1000.0)
        assert seam.timeouts() == [0.0, 0.0], seam.calls
        assert seam.acquired() == [True, True] and seam.releases() == [1, 1]
        assert seam.depth == 0 and _free(seam)
        assert a.closed is True
        assert _warnings(caplog) == []
        assert b.job_creates == [] and b.mutations() == []


class TestTheJobThatOutlivedTheDecision:
    def test_the_refused_job_is_closed_with_the_state_lock_put_down(self):
        a, b, node = authority()
        eid = new_execution_id()
        seen = {}
        b.create_job_hook = lambda execution_id: a.close_admission(deadline=0.0)

        def watch_close(job):
            seen['state_held'] = a._state.locked()
            seen['table'] = dict(a._jobs)

        b.close_job_hook = watch_close
        with pytest.raises(iso.IsolationClosed):
            a._ensure_job(eid)
        assert seen == {'state_held': False, 'table': {}}
        assert b.job_creates == [eid] and b.closed == [{'job': eid}]
        assert a.held_jobs() == {} and a.held_job(eid) is None
        assert b.assigned == [] and node.registry == []
        assert _free(a._lock) and _free(a._state)

    def test_a_held_job_that_answers_falsy_is_answered_from_the_table(self):
        a, b, node = authority()
        eid = new_execution_id()
        b.job_handle = 0
        assert a._ensure_job(eid) == 0
        assert a._ensure_job(eid) == 0
        a.assign(eid, 'PROCESS-HANDLE')
        assert b.job_creates == [eid]
        assert b.closed == []
        assert b.assigned == [(0, 'PROCESS-HANDLE')]
        assert a.held_job(eid) == 0 and a.held_jobs() == {eid: 0}
        assert node.registry == []
        out = a.teardown(eid, reason='ended')
        assert out['job'] == 'closed' and b.closed == [0]

    def test_a_job_that_could_not_be_closed_is_never_held(self):
        a, b, node = authority()
        eid = new_execution_id()
        b.create_job_hook = lambda execution_id: a.close_admission(deadline=0.0)
        b.close_job_fail = OSError('CloseJobObject refused (synthetic)')
        with pytest.raises(OSError) as got:
            a._ensure_job(eid)
        assert str(got.value) == 'CloseJobObject refused (synthetic)'
        assert not isinstance(got.value, iso.IsolationUnavailable)
        assert not isinstance(got.value, iso.IsolationClosed)
        assert b.job_creates == [eid] and b.closed == [{'job': eid}]
        assert a.held_jobs() == {} and a.held_job(eid) is None
        assert b.created == [] and b.assigned == [] and node.registry == []
        assert _free(a._lock) and _free(a._state)
        b.close_job_fail = None
        with pytest.raises(iso.IsolationClosed):
            a._ensure_job(eid)
        assert b.job_creates == [eid]


class TestAFailureWhoseRecordCouldNotBeWritten:
    def test_the_reason_survives_a_record_that_could_not_be_written(self, monkeypatch):
        a, b, node = authority()
        eid = new_execution_id()
        rec = record_for(eid, owned=True)
        job = a._ensure_job(eid)
        monkeypatch.setattr(iso.config, 'write_json_atomic',
                            raiser(OSError('the record store is full (synthetic)')))
        attempts = []
        real_release = a._release_best_effort
        monkeypatch.setattr(a, '_release_best_effort',
                            lambda r: (attempts.append(r.execution_id), real_release(r))[1])
        with pytest.raises(iso.IsolationUnavailable) as got:
            a._fail(rec, 'condition_unmet:sentinel', 'sentinel: missing', None)
        assert got.value.reason == 'condition_unmet:sentinel'
        assert got.value.detail == ('sentinel: missing; cleanup incomplete: '
                                    'the record store is full (synthetic)')
        assert not os.path.lexists(isolation_state(eid))
        assert [line['op'] for line in node.registry] == ['isolation_failed']
        assert node.registry[0]['reason'] == 'condition_unmet:sentinel'
        assert node.registry[0]['execution_id'] == eid
        assert attempts == [eid]
        assert b.closed == [job] and b.deleted == [rec.profile]
        assert (rec.state, rec.reason, rec.failure) == (
            'failed', 'condition_unmet:sentinel', 'condition_unmet:sentinel')


class TestAFailureWhoseTombstoneCouldNotBeWritten:
    def test_the_end_that_could_not_be_written_is_detail_not_reason(self, monkeypatch):
        a, b, node = authority()
        eid = new_execution_id()
        paths = ExecPaths(eid)
        os.makedirs(paths.dir, exist_ok=True)
        rec = record_for(eid, owned=True)
        job = a._ensure_job(eid)
        calls = []

        def refused(p, exit_code, **extra):
            calls.append((p, exit_code, extra))
            raise OSError('the tombstone write was refused (synthetic)')

        monkeypatch.setattr(iso.base, 'mark_ended', refused)
        with pytest.raises(iso.IsolationUnavailable) as got:
            a._fail(rec, 'a4_unmet', 'row 3 missing', paths)
        assert len(calls) == 1
        assert calls[0][0] is paths and calls[0][1] is None
        assert calls[0][2] == {'error': 'isolation: a4_unmet', 'isolation_state': 'failed',
                               'isolation_reason': 'a4_unmet',
                               'isolation_detail': 'row 3 missing'}
        assert got.value.reason == 'a4_unmet'
        assert got.value.detail == ('row 3 missing; cleanup incomplete: the tombstone write '
                                    'was refused (synthetic)')
        stored = a.record(eid)
        assert stored.state == 'failed' and stored.reason == 'a4_unmet'
        assert stored.owned is True and stored.failure == 'a4_unmet'
        assert not os.path.lexists(paths.ended)
        assert [line['op'] for line in node.registry] == ['isolation_failed']
        assert b.closed == [job] and b.deleted == [rec.profile]


class TestTheCleanupNote:
    def test_the_only_cleanup_failure_is_named_without_a_separator(self, monkeypatch):
        a, b, node = authority()
        eid = new_execution_id()
        monkeypatch.setattr(a, '_release_best_effort',
                            raiser(OSError('the profile would not go (synthetic)')))
        with pytest.raises(iso.IsolationUnavailable) as got:
            a._fail(record_for(eid), 'platform', '')
        assert got.value.reason == 'platform'
        assert got.value.detail == 'cleanup incomplete: the profile would not go (synthetic)'
        assert not got.value.detail.startswith((';', ' '))
        assert str(got.value) == ('isolation unavailable (platform): cleanup incomplete: '
                                  'the profile would not go (synthetic)')
        with open(isolation_state(eid), encoding='utf-8') as f:
            assert json.load(f)['state'] == 'failed'
        assert [line['op'] for line in node.registry] == ['isolation_failed']
        assert b.mutations() == []
        a2, b2, node2 = authority()
        with pytest.raises(iso.IsolationUnavailable) as clean:
            a2._fail(record_for(new_execution_id()), 'platform', '')
        assert clean.value.reason == 'platform' and clean.value.detail == ''
        assert 'cleanup incomplete' not in str(clean.value)
        assert b2.mutations() == [] and node2.registry[0]['op'] == 'isolation_failed'

    def test_every_cleanup_failure_is_named(self, monkeypatch):
        a, b, node = authority()
        eid = new_execution_id()
        paths = ExecPaths(eid)
        os.makedirs(paths.dir, exist_ok=True)
        rec = record_for(eid)
        marked = []
        monkeypatch.setattr(iso.config, 'write_json_atomic',
                            raiser(OSError('record (synthetic)')))
        node.registry_fail = OSError('registry (synthetic)')
        monkeypatch.setattr(iso.base, 'mark_ended',
                            lambda p, code, **extra: marked.append((p, code, extra)))
        monkeypatch.setattr(a, '_release_best_effort',
                            raiser(OSError('release (synthetic)')))
        with pytest.raises(iso.IsolationUnavailable) as got:
            a._fail(rec, 'os_error', 'the create failed', paths)
        assert got.value.reason == 'os_error'
        prefix = 'the create failed; cleanup incomplete: '
        assert got.value.detail.startswith(prefix)
        assert set(got.value.detail[len(prefix):].split(' | ')) == {
            'record (synthetic)', 'registry (synthetic)', 'release (synthetic)'}
        assert len(marked) == 1 and marked[0][0] is paths and marked[0][1] is None
        assert marked[0][2]['isolation_detail'] == 'the create failed'
        assert marked[0][2]['isolation_state'] == 'failed'
        assert marked[0][2]['error'] == 'isolation: os_error'
        assert not os.path.lexists(isolation_state(eid))
        assert node.registry == []
        assert b.mutations() == []
