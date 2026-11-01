import pytest

from archeus.core.application import errors
from v1.unit.test_gaps_core_execution_manager import _hook_rig, _live


def test_a_closed_writer_is_not_answered_as_a_judged_halt(tmp_path):
    rig, m, node = _hook_rig(tmp_path, [(1, {'tool': 'Read', 'input': {'file_path': 'a.py'},
                                             'cwd': str(tmp_path / 'work')})])

    def closed(command, **kw):
        raise errors.WriterClosed('the writer is closed')
    m._do = closed
    try:
        with pytest.raises(errors.WriterClosed):
            m._hooks(_live(rig)[0], m._procs[rig.eid], False)
        assert node.responded == []
    finally:
        rig.db.close()


def test_boot_decides_orphans_after_its_own_reconciles():
    from types import SimpleNamespace
    from archeus.core.execution.manager import ExecutionManager
    first, second = [SimpleNamespace(id='exe_a')], []
    reads, seen = [(first, None), (second, None)], []
    fake = SimpleNamespace(
        node=SimpleNamespace(disarmed=lambda: False, compact_registry=lambda: None),
        _procs={}, _noted=set(), _read=lambda: reads.pop(0),
        _reconcile_one=lambda e, disarmed: None,
        _adopt_orphans=lambda live: seen.append([e.id for e in live]),
        _sweep_isolation=lambda live: None)
    ExecutionManager.boot(fake)
    assert seen == [[]]
