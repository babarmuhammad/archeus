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
