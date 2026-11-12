"""fx32: the stop's admission, the Job table and the record store under a late writer.

Two Cores share one record store and one boundary (the OS) here; every interleaving is a
threading.Event seam in the fake boundary. Nothing sleeps, nothing reaches Win32."""

import json
import os
import subprocess
import sys
import threading
import time
import types

import pytest

from archeus.infra.paths import isolation_state, verify_consumed
from archeus.node import isolation as iso

from .test_gaps3_node_isolation_a import (JOIN_S, FakeNode, _verify_key, authority,  # noqa: F401
                                          make_verify_request, new_execution_id, no_real_win32)


def _run(target, *args):
    box = []

    def body():
        try:
            box.append(target(*args))
        except BaseException as error:
            box.append(error)
    t = threading.Thread(target=body, daemon=True, name='worker')
    t.start()
    return t, box


def _record(a, eid):
    return a.record(eid)


def test_a_stop_is_not_recorded_as_an_isolation_failure(tmp_path):
    a, _b, req, node = authority(tmp_path)
    spec = types.SimpleNamespace(execution_id=req.execution_id, isolation=object())
    a.note_failure(spec, iso.IsolationClosed())
    assert node.registry == []


def test_a_job_that_finishes_after_the_stop_began_is_never_published(tmp_path):
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    entered, release = threading.Event(), threading.Event()

    class Seam(dict):
        def __setitem__(self, key, value):
            entered.set()
            assert release.wait(JOIN_S)
            super().__setitem__(key, value)

    a._jobs = Seam()
    worker, out = _run(a._ensure_job, eid)
    assert entered.wait(JOIN_S)
    snapshot = []
    closer = threading.Thread(target=lambda: (a.close_admission(deadline=0.0),
                                              snapshot.append(a.held_jobs())), daemon=True)
    closer.start()
    closer.join(0.2)
    release.set()
    worker.join(JOIN_S)
    closer.join(JOIN_S)
    assert set(a.held_jobs()) <= set(snapshot[0]), 'a Job was inserted after the stop snapshot'


def test_a_record_saved_on_a_stale_read_is_refused_and_the_stored_one_stays(tmp_path):
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    first = iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid))
    a._save(first)
    stale = _record(a, eid)
    a._save(_record(a, eid))
    with pytest.raises(OSError):
        a._save(stale)
    assert _record(a, eid).gen == first.gen + 1


def test_ownership_is_never_turned_back_to_unowned_by_a_write_from_an_older_read(tmp_path):
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    unowned = iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid))
    a._save(unowned)
    stale = _record(a, eid)
    owned = _record(a, eid)
    owned.owned = True
    a._save(owned)
    with pytest.raises(OSError):
        a._save(stale)
    assert _record(a, eid).owned is True


def test_a_record_write_that_cannot_take_its_lock_fails_and_leaves_the_record(tmp_path,
                                                                              monkeypatch):
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    a._save(iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid)))
    before = open(isolation_state(eid), 'rb').read()
    monkeypatch.setattr(iso, 'RECORD_LOCK_WAIT_S', 0.05)
    with iso._record_lock(isolation_state(eid)):
        with pytest.raises(OSError):
            a._save(_record(a, eid))
    assert open(isolation_state(eid), 'rb').read() == before


def test_a_late_ownership_write_is_not_undone_by_a_stale_reclaim(tmp_path):
    """Core 1 creates the profile and stalls before saving its ownership; the stop
    returns; Core 2 reads the profile and the record, and stalls inside its decision
    holding what it read (the profile was there). Core 1 then saves ownership, and the
    stop deletes the profile. Core 2 resumes from its stale read: its save must conflict,
    so the record stays owned with its SID. The next pass removes that record, with no
    second deletion, since the profile is already absent."""
    a1, b, req, _node = authority(tmp_path)
    eid = req.execution_id
    a2 = iso.Isolation(FakeNode(), boundary=b)
    created, release_create = threading.Event(), threading.Event()
    read, release_read = threading.Event(), threading.Event()
    real_create, real_exists = b.create_profile, b.profile_exists

    def stalled_create(execution_id):
        got = real_create(execution_id)
        created.set()
        assert release_create.wait(JOIN_S)
        return got

    def stalled_exists(execution_id):
        if threading.current_thread().name == 'reclaimer':
            seen = real_exists(execution_id)     # the read Core 2 decides from: profile present
            read.set()
            assert release_read.wait(JOIN_S)
            return seen
        return real_exists(execution_id)

    b.create_profile, b.profile_exists = stalled_create, stalled_exists
    establisher, errors = _run(a1.establish, req)
    assert created.wait(JOIN_S)
    a1.close_admission(deadline=0.0)
    passes = []
    reclaimer = threading.Thread(target=lambda: passes.append(a2.reclaim()),
                                 name='reclaimer', daemon=True)
    reclaimer.start()
    assert read.wait(JOIN_S)
    release_create.set()
    establisher.join(JOIN_S)
    release_read.set()
    reclaimer.join(JOIN_S)
    assert isinstance(errors[0], iso.IsolationClosed)
    rec = _record(a2, eid)
    assert rec is not None and rec.owned is True, 'a stale reclaim turned ownership back'
    assert rec.state == 'pending' and rec.sid != '' and rec.failure == ''
    assert iso.profile_name(eid) not in b.profiles
    assert b.deleted == [iso.profile_name(eid)], 'the profile was deleted more than once'
    assert a2.reclaim() == [eid]
    assert not os.path.lexists(isolation_state(eid))


def test_a_job_created_after_the_stop_began_is_closed_and_never_held(tmp_path):
    a, b, req, _node = authority(tmp_path)
    eid = req.execution_id
    entered, release = threading.Event(), threading.Event()

    def stalled_create(execution_id):
        entered.set()
        assert release.wait(JOIN_S)

    b.create_job_hook = stalled_create
    worker, out = _run(a._ensure_job, eid)
    assert entered.wait(JOIN_S)
    a.close_admission(deadline=0.0)
    release.set()
    worker.join(JOIN_S)
    assert isinstance(out[0], iso.IsolationClosed)
    assert a.held_jobs() == {} and len(b.closed) == 1


def test_the_held_jobs_snapshot_is_taken_under_the_state_lock(tmp_path):
    a, _b, req, _node = authority(tmp_path)
    seen = []

    class Probe(dict):
        def keys(self):
            seen.append(a._state.locked())
            return super().keys()

        def __iter__(self):
            seen.append(a._state.locked())
            return super().__iter__()

    a._jobs = Probe({req.execution_id: object()})
    assert a.held_jobs() == {req.execution_id: a._jobs[req.execution_id]}
    assert seen and all(seen)


def test_a_closed_authority_never_creates_a_job_for_an_unseen_execution(tmp_path):
    a, b, req, _node = authority(tmp_path)
    a.close_admission(deadline=0.0)
    with pytest.raises(iso.IsolationClosed):
        a._ensure_job(req.execution_id)
    assert b.job_creates == 0


def test_a_stopped_core_consumes_no_verifier_attempt_through_run_confined(tmp_path):
    key = _verify_key()
    a, _b, req, _node = authority(tmp_path, request=make_verify_request(key, str(tmp_path / 'v')))
    a.close_admission(deadline=0.0)
    result = a.run_confined(req, ['x'], env={}, timeout=1, out_path=str(tmp_path / 'out'),
                            stdin_path=str(tmp_path / 'in'), record=lambda r: None, keep=False)
    assert 'core_stopping' in repr(result)
    assert not os.path.lexists(verify_consumed(key))


def test_a_profile_created_after_the_stop_returned_is_deleted_by_its_own_establishment(tmp_path):
    """The establishment is blocked before the profile is created. The stop's deadline
    passes and close_admission returns without waiting for it. Only then is the creation
    allowed to run. The establishment then saves its ownership, sees the stop, and deletes
    the profile itself: the record stays owned and pending with its SID and no failure, the
    profile is absent, no Job is created, and nothing is recorded as an isolation failure."""
    a, b, req, node = authority(tmp_path)
    eid = req.execution_id
    create_entered, allow_create = threading.Event(), threading.Event()
    stop_returned, worker_done = threading.Event(), threading.Event()
    real_create = b.create_profile
    errors = []

    def gated_create(execution_id):
        create_entered.set()
        assert allow_create.wait(JOIN_S)
        return real_create(execution_id)

    def work():
        try:
            a.establish(req)
        except BaseException as error:
            errors.append(error)
        finally:
            worker_done.set()

    b.create_profile = gated_create
    worker = threading.Thread(target=work, name='establisher', daemon=True)
    worker.start()
    assert create_entered.wait(JOIN_S)
    a.close_admission(deadline=0.0)              # the deadline passes; the creation is blocked
    stop_returned.set()
    assert worker.is_alive() and not worker_done.is_set()
    allow_create.set()                           # the creation runs only after the stop returned
    worker.join(JOIN_S)
    assert not worker.is_alive() and worker_done.is_set() and stop_returned.is_set()
    assert len(errors) == 1 and isinstance(errors[0], iso.IsolationClosed)
    assert b.created == [iso.profile_name(eid)]
    assert iso.profile_name(eid) not in b.profiles and b.deleted == [iso.profile_name(eid)]
    rec = _record(a, eid)
    assert rec.state == 'pending' and rec.owned is True and rec.sid != ''
    assert rec.failure == '' and b.job_creates == 0 and a.held_jobs() == {}
    assert 'isolation_failed' not in [line['op'] for line in node.registry]


def test_a_writer_stalled_after_its_generation_check_keeps_the_record_lock(tmp_path,
                                                                           monkeypatch):
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    a._save(iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid)))
    stale_a, stale_b = _record(a, eid), _record(a, eid)
    stale_a.reason, stale_b.reason = 'writer-a', 'writer-b'
    monkeypatch.setattr(iso, 'RECORD_LOCK_WAIT_S', 0.2)
    stalled, release, errors = threading.Event(), threading.Event(), []
    real_write = iso.config.write_json_atomic

    def stall_writer_a(path, data, **kw):
        if threading.current_thread() is writer:
            stalled.set()
            assert release.wait(JOIN_S)
        return real_write(path, data, **kw)

    def write_a():
        try:
            a._save(stale_a)
        except BaseException as err:
            errors.append(err)

    monkeypatch.setattr(iso.config, 'write_json_atomic', stall_writer_a)
    writer = threading.Thread(target=write_a, daemon=True)
    writer.start()
    assert stalled.wait(JOIN_S)
    lock = isolation_state(eid) + '.lock'
    if os.path.exists(lock):
        old_time = time.time() - 3600
        os.utime(lock, (old_time, old_time))
    with pytest.raises(OSError):
        a._save(stale_b)
    release.set()
    writer.join(JOIN_S)
    assert errors == []
    assert _record(a, eid).reason == 'writer-a'


def test_an_invalid_stored_record_with_a_matching_gen_refuses_the_write(tmp_path):
    a, _b, req, _node = authority(tmp_path)
    eid = req.execution_id
    path = isolation_state(eid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'gen': 0, 'junk': True}, f)
    before = open(path, 'rb').read()
    with pytest.raises(iso.RecordChanged):
        a._save(iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid)))
    assert open(path, 'rb').read() == before


def test_a_stale_cleanup_cannot_delete_a_record_a_newer_ownership_write_replaced(tmp_path):
    a, b, req, _node = authority(tmp_path)
    eid = req.execution_id
    a._save(iso.IsolationRecord(execution_id=eid, profile=iso.profile_name(eid)))
    stale = _record(a, eid)
    newer = _record(a, eid)
    newer.owned, newer.state, newer.sid = True, 'pending', b.derive_sid(eid)
    a._save(newer)
    with pytest.raises(iso.RecordChanged):
        a._unowned(stale)
    assert _record(a, eid).owned is True


def test_a_record_lock_is_released_when_its_holder_process_dies(tmp_path, monkeypatch):
    path = str(tmp_path / 'record.json')
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(iso.__file__))))
    code = ('import os, sys\n'
            'from archeus.node import isolation as iso\n'
            'iso._record_lock(sys.argv[1]).__enter__()\n'
            'print("held", flush=True)\n'
            'os._exit(0)\n')
    child = subprocess.run([sys.executable, '-c', code, path], cwd=root, capture_output=True,
                           text=True, timeout=JOIN_S)
    assert child.stdout.strip() == 'held', child.stderr
    monkeypatch.setattr(iso, 'RECORD_LOCK_WAIT_S', 0.05)
    with iso._record_lock(path):
        pass
