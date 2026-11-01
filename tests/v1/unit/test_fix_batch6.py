"""Fix batch 6: an INTENT execution whose process was spawned and never recorded must end
through the state machine, never raise out of a pass or a boot (F-A).
Real database, fake node and adapter, as test_gaps_core_execution_manager.py builds them."""

from types import SimpleNamespace

import pytest

from archeus.core.domain import entities
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
