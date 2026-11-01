import subprocess

from archeus.node.local import LocalNode


class _Unkillable:
    returncode = None

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired('x', timeout)


def test_a_check_that_survives_its_kill_is_a_timeout_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **kw: _Unkillable())
    monkeypatch.setattr('archeus.node.local.proc.kill_tree', lambda child: None)
    out = LocalNode.run_check(str(tmp_path), ['x'], timeout=1, out_path=str(tmp_path / 'o' / 'out'))
    assert out['exit_code'] is None and out['error'].startswith('timed out')


def test_a_process_registry_failure_stops_the_process_and_is_a_spawn_write_failure(monkeypatch):
    # T-660#10: the OSError escaped spawn (the manager catches only SpawnFailed and kin)
    # and left a live process that no registry line named
    from types import SimpleNamespace

    import pytest

    from archeus.core.domain import ids
    from archeus.harnesses import base

    handle = SimpleNamespace(pid=1, create_time=2)
    stopped = []

    class Adapter:
        id = 'fake'

        def start(self, spec):
            return handle

        def stop(self, h, *, grace_s):
            stopped.append(h)

    node = LocalNode()

    def full(line):
        raise OSError('disk full')

    monkeypatch.setattr(node, '_registry', full)
    spec = SimpleNamespace(execution_id=ids.new_id('execution'), process_seq=1, isolation=None)
    with pytest.raises(base.SpawnWriteFailed, match='disk full'):
        node.spawn(Adapter(), spec, isolated=False)
    assert stopped == [handle]
