"""T-837: pins on the security-relevant branches of `archeus/node/isolation.py`
lines 650-1300. Each test names one branch (comparison, early return, membership
check, default) and fails when that branch is removed, inverted or loosened.

Everything runs on a synthetic boundary: no Windows API, no network, no real
process, and nothing is assumed about the host's paths or its error text.
"""

import os
import subprocess
import time
import zlib
from types import SimpleNamespace

import pytest
from claude_sessions import config

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.infra.paths import ExecPaths, isolation_state
from archeus.node import isolation as iso

#: the real OS entry points the module owns; reaching one fails the test that got there
NATIVE = ('_CreateAppContainerProfile', '_DeleteAppContainerProfile',
          '_GetSecurityInfoByNameW', '_GetAclInformation', '_GetAce',
          '_ConvertSidToStringSidW', '_OpenProcess', '_GetExitCodeProcess',
          '_GetProcessTimes', '_DeriveAppContainerSidFromAppContainerName',
          '_CreateProcessW', '_ResumeThread', '_TerminateProcess',
          '_AssignProcessToJobObject', '_CreateJobObjectW', '_SetInformationJobObject',
          '_QueryInformationJobObject', '_CreateFileW', '_CloseHandle',
          '_InitializeProcThreadAttributeList', '_UpdateProcThreadAttribute',
          '_DeleteProcThreadAttributeList', '_SetHandleInformation',
          '_GetHandleInformation')


@pytest.fixture(autouse=True)
def no_real_os(monkeypatch):
    """No test here may start a process or reach a native call, on any platform."""
    for name in NATIVE:
        def trip(*args, _name=name):
            raise AssertionError('the real %s was reached' % _name)
        monkeypatch.setattr(iso, name, trip, raising=False)
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: (_ for _ in ()).throw(
        AssertionError('a real process was started')))
    monkeypatch.setattr(os, 'system', lambda *a, **k: (_ for _ in ()).throw(
        AssertionError('a real command was run')))


def sid_for(name):
    return 'S-1-15-3-9-%08d' % (zlib.crc32(str(name).encode('utf-8')) % 10 ** 8)


class Boundary:
    """The OS's answers, as knobs. It records what it was asked to do and decides
    nothing; nothing in it launches or reads anything real."""
    id = 'fake'

    def __init__(self):
        self.available_ok = True
        self.profiles = set()
        self.created = []
        self.deleted = []
        self.closed = []
        self.looked = []
        self.probed = []
        self.processes = {}

    def available(self):
        return self.available_ok

    def create_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        existed = name in self.profiles
        self.profiles.add(name)
        self.created.append(name)
        return {'profile': name, 'sid': sid_for(name), 'created': True,
                'existed': existed, 'package_dir': 'materialized'}

    def delete_profile(self, execution_id):
        name = iso.validated_profile(execution_id)
        self.deleted.append(name)
        self.profiles.discard(name)

    def profile_exists(self, execution_id):
        name = iso.profile_name(execution_id)
        self.looked.append(name)
        return name in self.profiles

    def process_started(self, pid):
        self.probed.append(pid)
        return self.processes.get(pid)

    def derive_sid(self, execution_id):
        return sid_for(iso.profile_name(execution_id))

    def create_job(self, execution_id):
        return {'job': execution_id}

    def job_facts(self, handle):
        return {'type': 'Job', 'name': '', 'inheritable': False}

    def job_active_processes(self, job):
        return 0

    def assign_job(self, job, process_handle):
        pass

    def close_job(self, job):
        self.closed.append(job)

    def open_inherited(self, path, mode):
        return {'path': path, 'mode': mode}

    def close_handle(self, handle):
        pass


class Node:
    def __init__(self):
        self.registry = []

    def _registry(self, line):
        self.registry.append(line)


def new_id():
    return ids.new_id('execution')


def wired(boundary=None):
    node = Node()
    b = boundary or Boundary()
    return iso.Isolation(node, boundary=b), b, node


def record_for(eid, **over):
    return iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid), **over)


def saved(a, rec):
    a._save(rec)
    return rec


def clock(monkeypatch, start=1000.0):
    """The module clock, moved only by the test. `monotonic` and `sleep` stay real."""
    now = [float(start)]
    monkeypatch.setattr(iso, 'time', SimpleNamespace(
        time=lambda: now[0], monotonic=time.monotonic, sleep=time.sleep))
    return now


# ── the record's own writes (lines 699-712) ──────────────────────────────────

def test_an_invalid_record_is_never_written():
    a, _b, _node = wired()
    eid = new_id()
    rec = record_for(eid, state='invalid', reason='unreadable')
    with pytest.raises(ValueError):
        a._save(rec)
    assert not os.path.lexists(isolation_state(eid))


def test_the_first_write_of_a_record_fixes_its_time(monkeypatch):
    a, _b, _node = wired()
    eid = new_id()
    now = clock(monkeypatch, 1000.0)
    rec = saved(a, record_for(eid))
    assert rec.at == 1000.0 and rec.updated == 1000.0
    now[0] = 2000.0
    saved(a, rec)
    kept = a.record(eid)
    assert kept.at == 1000.0 and kept.updated == 2000.0
    fresh = saved(a, record_for(new_id()))
    assert fresh.at == 2000.0


def test_a_write_that_answers_failure_is_a_failure(monkeypatch):
    a, _b, _node = wired()
    eid = new_id()
    real = config.write_json_atomic
    monkeypatch.setattr(config, 'write_json_atomic', lambda *args, **kw: False)
    with pytest.raises(OSError) as err:
        a._save(record_for(eid))
    assert eid in str(err.value)
    assert not os.path.lexists(isolation_state(eid))
    monkeypatch.setattr(config, 'write_json_atomic', real)
    assert saved(a, record_for(eid)).state == 'pending'
    assert a.record(eid).state == 'pending'


# ── the spawn-failure note (lines 746-762) ───────────────────────────────────

def test_a_spawn_that_was_never_isolated_is_left_alone():
    a, _b, node = wired()
    err = base.SpawnFailed('isolation: synthetic')
    assert a.note_failure(SimpleNamespace(isolation=None,
                                         execution_id=new_id()), err) is None
    assert a.note_failure(SimpleNamespace(execution_id=new_id()), err) is None
    assert node.registry == []


@pytest.mark.parametrize('state', ['failed', 'quarantined'], ids=['failed', 'quarantined'])
def test_a_record_that_already_failed_is_noted_no_second_time(state):
    a, _b, node = wired()
    eid = new_id()
    saved(a, record_for(eid, state=state, reason='process_alive', owned=True))
    a.note_failure(SimpleNamespace(isolation=object(), execution_id=eid),
                   base.SpawnFailed('isolation: synthetic'))
    assert node.registry == []


def test_the_note_of_a_failure_with_no_record_says_unknown():
    a, _b, node = wired()
    eid = new_id()
    assert a.record(eid) is None                 # nothing was ever written for it
    a.note_failure(SimpleNamespace(isolation=object(), execution_id=eid),
                   base.SpawnFailed('isolation: synthetic'))
    assert [(x['op'], x['reason'], x['state']) for x in node.registry] == [
        ('isolation_failed', 'unknown', 'isolation_failed')]
    assert node.registry[0]['execution_id'] == eid


def test_an_empty_record_reason_falls_back_to_the_error():
    a, b, node = wired()
    eid = new_id()
    saved(a, record_for(eid, state='established', sid=b.derive_sid(eid)))
    a.note_failure(SimpleNamespace(isolation=object(), execution_id=eid),
                   base.SpawnFailed('isolation: launch_failed'))
    assert [x['reason'] for x in node.registry] == ['isolation: launch_failed']


# ── the failed establishment and its tombstone (lines 859-889) ───────────────

def test_a_failed_establishment_marks_the_execution_ended_and_never_twice():
    a, _b, _node = wired()
    eid = new_id()
    paths = ExecPaths(eid)
    with pytest.raises(iso.IsolationUnavailable) as err:
        a._fail(record_for(eid, state='pending'), 'platform', 'no boundary here', paths)
    assert err.value.reason == 'platform'
    tomb = base.read_json(paths.ended)
    assert tomb['isolation_state'] == 'failed' and tomb['isolation_reason'] == 'platform'
    assert tomb['error'] == 'isolation: platform' and tomb['exit_code'] is None
    written = open(paths.ended, encoding='utf-8').read()
    with pytest.raises(iso.IsolationUnavailable):
        a._fail(record_for(eid, state='pending', reason='platform'),
               'os_error', 'disk gone', paths)
    assert open(paths.ended, encoding='utf-8').read() == written


def test_a_failed_establishment_without_tombstone_files_still_raises():
    a, _b, _node = wired()
    with pytest.raises(iso.IsolationUnavailable) as err:
        a._fail(record_for(new_id(), state='pending'), 'platform', 'detail', None)
    assert err.value.reason == 'platform' and err.value.detail == 'detail'


# ── what may be deleted, and by whom (lines 982-1095) ────────────────────────

def test_a_torn_down_record_that_still_names_a_sid_is_still_deleted():
    a, b, _node = wired()
    eid = new_id()
    name = iso.profile_name(eid)
    b.profiles.add(name)
    saved(a, record_for(eid, state='torn_down', owned=True, sid=b.derive_sid(eid)))
    assert a.teardown(eid, reason='ended')['profile'] == 'torn_down'
    assert b.deleted == [name] and a.record(eid) is None


def test_nothing_is_deleted_when_the_boundary_does_not_answer():
    a, b, _node = wired()
    eid = new_id()
    name = iso.profile_name(eid)
    b.profiles.add(name)
    rec = saved(a, record_for(eid, state='failed', owned=True, sid=b.derive_sid(eid)))
    b.available_ok = False
    a._release_best_effort(rec)
    assert b.deleted == [] and name in b.profiles
    b.available_ok = True
    a._release_best_effort(rec)
    assert b.deleted == [name] and name not in b.profiles
