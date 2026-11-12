"""fx32: the stop's admission, the Job table and the record store under a late writer.

Two Cores share one record store and one boundary (the OS) here; every interleaving is a
threading.Event seam in the fake boundary. Nothing sleeps, nothing reaches Win32."""

import os
import threading
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
    open(isolation_state(eid) + '.lock', 'w').close()
    with pytest.raises(OSError):
        a._save(_record(a, eid))
    assert open(isolation_state(eid), 'rb').read() == before


def test_a_late_ownership_write_is_not_undone_by_a_stale_reclaim(tmp_path):
    """Core 1 creates the profile and stalls before saving its ownership; the stop
    returns; Core 2 reads the still-unowned record and stalls inside its decision; Core 1
    saves ownership; Core 2 resumes from its stale read. The record must stay owned, and
    the next pass must delete the profile."""
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
            read.set()
            assert release_read.wait(JOIN_S)
        return real_exists(execution_id)

    b.create_profile, b.profile_exists = stalled_create, stalled_exists
    establisher, errors = _run(a1.establish, req)
    assert created.wait(JOIN_S)
    a1.close_admission(deadline=0.0)
    reclaimer, passes = _run(a2.reclaim)
    reclaimer.name = 'reclaimer'
    assert read.wait(JOIN_S)
    release_create.set()
    establisher.join(JOIN_S)
    release_read.set()
    reclaimer.join(JOIN_S)
    assert isinstance(errors[0], iso.IsolationClosed)
    assert _record(a2, eid).owned is True, 'a stale reclaim turned ownership back to unowned'
    assert a2.reclaim() == [eid] and iso.profile_name(eid) not in b.profiles
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
