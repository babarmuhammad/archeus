"""Fix batch 6: an INTENT execution whose process was spawned and never recorded must end
through the state machine, never raise out of a pass or a boot (F-A); a live row whose
harness is not registered is ended with a recorded reason, never a KeyError (F-B).
Real database, fake node and adapter, as test_gaps_core_execution_manager.py builds them."""

import os
from types import SimpleNamespace

import pytest

from archeus.core.domain import entities, ids
from archeus.harnesses.registry import PolicyStubError
from archeus.infra import paths
from archeus.node.local import LocalNode
from v1.unit.test_gaps_core_execution_manager import Adapter, _row, _seed

_PID = {'pid': 4242, 'create_time': 7.5, 'process_seq': 1}


def _node(rig, pid=_PID, alive=False):
    node = rig.manager.node
    node.files = lambda xid: ({'process_seq': 1}, pid, False)
    node.alive = lambda handle: alive
    node.kill_identity = lambda handle: node.kills.append(('identity', handle)) or True
    return node


@pytest.mark.parametrize('adapter,reason', [
    (Adapter(state='exited', exit_code=0), 'the process exited without output'),
    (Adapter(state='exited', exit_code=3), 'the process exited without output'),
    (Adapter(state='running', exit_code=None),
     'Core restarted; the process is gone and left no exit')])
def test_an_intent_spawned_and_never_recorded_that_exited_ends_through_the_state_machine(
        adapter, reason):
    rig = _seed('INTENT', process_seq=1)
    try:
        m = rig.manager
        _node(rig)
        m.registry = SimpleNamespace(get=lambda hid: adapter)
        m._tombstone = lambda e: None
        e = _row(rig, entities.Execution, rig.eid)
        assert m._reconcile_one(e, False) is True        # was IllegalTrigger, every pass
        got = _row(rig, entities.Execution, rig.eid)
        assert (got.state, got.exit_reason, got.charged) == ('ENDED_KILLED', 'lost', True)
        assert _row(rig, entities.Task, rig.tid).state != 'RUNNING'
        assert m._procs == {}
    finally:
        rig.db.close()


def _unregistered(rig):
    def get(hid):
        raise KeyError(hid)
    rig.manager.registry = SimpleNamespace(get=get)
    rig.manager._tombstone = lambda e: None
    _node(rig, alive=True)
    return rig.manager


@pytest.mark.parametrize('state,seq,end,charged', [
    ('INTENT', 0, 'ABANDONED', False),
    ('INTENT', 1, 'ENDED_KILLED', True),
    ('STARTING', 1, 'ENDED_KILLED', True),
    ('RUNNING', 1, 'ENDED_KILLED', True),
    ('PAUSING', 1, 'ENDED_ERROR', True),
    ('STOPPING', 1, 'ENDED_KILLED', False),
    ('HANDING_OFF', 1, 'ENDED_ERROR', True),
    ('LOST', 1, 'ENDED_KILLED', True),
    ('PAUSED', 1, 'ENDED_KILLED', False),
    ('AWAITING_APPROVAL', 1, 'ENDED_KILLED', False)])
def test_a_live_row_with_an_unregistered_harness_ends_with_a_reason_and_never_raises(
        state, seq, end, charged):
    rig = _seed(state, process_seq=seq, stop_reason='user' if state == 'STOPPING' else None)
    try:
        m = _unregistered(rig)
        e = _row(rig, entities.Execution, rig.eid)
        assert m._reconcile_one(e, False) is True
        got = _row(rig, entities.Execution, rig.eid)
        assert (got.state, got.charged) == (end, charged)
        if seq:
            assert [k for k in m.node.kills if k[0] == 'identity']      # its process, by identity
    finally:
        rig.db.close()


def test_spawn_and_resume_end_an_unregistered_harness_instead_of_raising():
    rig = _seed('INTENT')
    try:
        m = _unregistered(rig)
        e = _row(rig, entities.Execution, rig.eid)
        mission = _row(rig, entities.Mission, rig.mid)
        assert m._spawn(e, mission) is True
        got = _row(rig, entities.Execution, rig.eid)
        assert (got.state, got.stop_reason) == ('ABANDONED', 'spawn')
        assert 'not served by this Core' in got.summary
    finally:
        rig.db.close()
    rig = _seed('AWAITING_APPROVAL', process_seq=1)
    try:
        m = _unregistered(rig)
        e = _row(rig, entities.Execution, rig.eid)
        assert m._resume(e, _row(rig, entities.Mission, rig.mid)) is True
        assert _row(rig, entities.Execution, rig.eid).state == 'ENDED_KILLED'
    finally:
        rig.db.close()


def test_a_stubbed_policy_refusal_is_treated_as_an_unserved_harness():
    rig = _seed('RUNNING', process_seq=1)
    try:
        m = rig.manager

        def get(hid):
            raise PolicyStubError('stub')
        m.registry = SimpleNamespace(get=get)
        m._tombstone = lambda e: None
        _node(rig)
        assert m._reconcile_one(_row(rig, entities.Execution, rig.eid), False) is True
        assert _row(rig, entities.Execution, rig.eid).state == 'ENDED_KILLED'
    finally:
        rig.db.close()




@pytest.mark.parametrize('body', ['{}', '{"nonce": 0}', '{"nonce": ""}'])
def test_a_falsy_request_is_answered_once_not_on_every_pass(body):
    eid = ids.new_id('execution')
    p = paths.ExecPaths(eid)
    os.makedirs(p.req)
    with open(os.path.join(p.req, '1.req.json'), 'w', encoding='utf-8') as f:
        f.write(body)
    ((seq, request),) = LocalNode.pending_requests(eid)
    LocalNode.respond(eid, seq, request, 'halt', 'x')
    assert LocalNode.pending_requests(eid) == []        # was [(1, {})]: re-answered forever
