"""Hand-mutant pins on archeus/node/isolation.py lines 1300-1850.

Each test here names a condition that would let an existing test survive a mutation
(inversion, removal or loosening) if it were not pinned. Tests fail when the logic
breaks; they pass against the real source."""

import os
import stat
import time
from types import SimpleNamespace

import pytest

from archeus.node import isolation as iso

WRITE_DAC, WRITE_OWNER, GENERIC_ALL = 0x40000, 0x80000, 0x10000000
FILE_READ_DATA, FILE_WRITE_DATA, FILE_EXECUTE = 0x1, 0x2, 0x20


class _FakeSt:
    def __init__(self, mode, size=0, attrs=0):
        self.st_mode = mode
        self.st_size = size
        self.st_file_attributes = attrs


class TestTreeBytesUnclassifiable:

    def test_unclassifiable_entry_raises(self, tmp_path, monkeypatch):
        """_tree_bytes else branch (line ~1422): an entry that is not a plain dir,
        regular file, symlink or reparse point must raise OSError."""
        root = tmp_path / 'r'
        root.mkdir()

        class WeirdEntry:
            name = 'weird'
            path = os.path.join(str(root), 'weird')

            def stat(self, follow_symlinks=False):
                return _FakeSt(0o170000)

        class Listing:
            def __init__(self, path):
                pass

            def __enter__(self):
                return [WeirdEntry()]

            def __exit__(self, *exc):
                pass

        monkeypatch.setattr(os, 'scandir', Listing)
        with pytest.raises(OSError, match='cannot be classified'):
            iso._tree_bytes([str(root)])


class TestOverLimitBoundary:

    def test_out_at_cap_is_not_over(self, tmp_path, monkeypatch):
        """_over_limit (line ~1439): exactly CONFINED_OUT_MAX bytes is not over."""
        monkeypatch.setattr(iso, 'CONFINED_OUT_MAX', 100)
        out = tmp_path / 'o.log'
        data = b'x' * 100
        out.write_bytes(data)
        roots = [str(tmp_path / 'empty')]
        os.makedirs(str(tmp_path / 'empty'), exist_ok=True)
        start = iso._tree_bytes(roots)
        result = iso._over_limit(str(out), roots, start)
        assert result is None

    def test_out_one_over_cap_is_over(self, tmp_path, monkeypatch):
        """_over_limit (line ~1439): CONFINED_OUT_MAX+1 bytes must be over."""
        monkeypatch.setattr(iso, 'CONFINED_OUT_MAX', 100)
        out = tmp_path / 'o.log'
        out.write_bytes(b'x' * 101)
        roots = [str(tmp_path / 'empty')]
        os.makedirs(str(tmp_path / 'empty'), exist_ok=True)
        start = iso._tree_bytes(roots)
        result = iso._over_limit(str(out), roots, start)
        assert result is not None and 'limit_exceeded' in result

    def test_growth_at_cap_is_not_over(self, tmp_path, monkeypatch):
        """_over_limit (line ~1441): exactly CONFINED_GROWTH_MAX growth is not over."""
        monkeypatch.setattr(iso, 'CONFINED_GROWTH_MAX', 100)
        root = tmp_path / 'g'
        root.mkdir()
        out = tmp_path / 'o.log'
        out.write_bytes(b's')
        start = 0
        (root / 'f').write_bytes(b'x' * 100)
        result = iso._over_limit(str(out), [str(root)], start)
        assert result is None

    def test_growth_one_over_cap_is_over(self, tmp_path, monkeypatch):
        """_over_limit (line ~1441): CONFINED_GROWTH_MAX+1 growth must be over."""
        monkeypatch.setattr(iso, 'CONFINED_GROWTH_MAX', 100)
        root = tmp_path / 'g'
        root.mkdir()
        out = tmp_path / 'o.log'
        out.write_bytes(b's')
        start = 0
        (root / 'f').write_bytes(b'x' * 101)
        result = iso._over_limit(str(out), [str(root)], start)
        assert result is not None and 'limit_exceeded' in result


class TestCaptured:

    def test_keep_larger_than_file_returns_all(self, tmp_path):
        """_captured (line ~1463): max(0, size-keep) prevents negative seek."""
        out = tmp_path / 'o.log'
        out.write_bytes(b'hello')
        tail, size = iso._captured(str(out), 999)
        assert tail == b'hello' and size == 5

    def test_keep_equals_size_returns_all(self, tmp_path):
        """_captured: seek(max(0, 0)) reads the whole file."""
        out = tmp_path / 'o.log'
        out.write_bytes(b'abc')
        tail, size = iso._captured(str(out), 3)
        assert tail == b'abc' and size == 3


class TestConfinedResultTruncated:

    def test_exact_keep_is_not_truncated(self, tmp_path):
        """_confined_result (line ~1456): size > keep, not size >= keep."""
        out = tmp_path / 'o.log'
        payload = b'a' * 10
        out.write_bytes(payload)
        result = iso._confined_result(str(out), 10, time.monotonic(), None, 0, {})
        assert result['truncated'] is False
        assert result['output'] == payload

    def test_one_over_keep_is_truncated(self, tmp_path):
        """_confined_result: size > keep triggers truncated=True."""
        out = tmp_path / 'o.log'
        out.write_bytes(b'a' * 11)
        result = iso._confined_result(str(out), 10, time.monotonic(), None, 0, {})
        assert result['truncated'] is True


class TestAccessCoveredControlBits:

    @pytest.mark.parametrize('bit,label', [
        (WRITE_DAC, 'WRITE_DAC'),
        (WRITE_OWNER, 'WRITE_OWNER'),
        (GENERIC_ALL, 'GENERIC_ALL'),
    ], ids=['wd', 'wo', 'ga'])
    def test_control_bit_blocks_rw_row(self, bit, label):
        """access_covered (line ~1634): mask & (WRITE_DAC|WRITE_OWNER|GENERIC_ALL)
        returns False unconditionally. Without the early return, READ|WRITE|bit would
        satisfy the 'rw' row since _write_like is never checked on that path."""
        mask = FILE_READ_DATA | FILE_WRITE_DATA | bit
        assert iso.access_covered(mask, 'rw') is False

    def test_x_row_with_read_is_false(self):
        """access_covered (line ~1645): 'x' requires not read."""
        mask = FILE_EXECUTE | FILE_READ_DATA
        assert iso.access_covered(mask, 'x') is False

    def test_x_row_execute_only_is_true(self):
        """access_covered 'x': execute alone without read passes."""
        assert iso.access_covered(FILE_EXECUTE, 'x') is True


class TestConfinedLaunchFailedChild:

    def test_failed_child_stored_in_live(self, tmp_path):
        """_confined_launch (line ~1368): when api.launch raises with a .child
        attribute, the child is stored in self._live so the end path can wait on it."""
        child = SimpleNamespace(pid=999)

        class ErrWithChild(Exception):
            pass

        err = ErrWithChild('boom')
        err.child = child

        class ApiWithChild:
            def open_inherited(self, path, mode):
                return object()

            def close_handle(self, h):
                pass

            def launch(self, *a, **kw):
                raise err

        fake_isolation = object.__new__(iso.Isolation)
        fake_isolation._live = {}
        fake_isolation.held_job = lambda eid: None
        req = SimpleNamespace(workspace=str(tmp_path))
        rec = SimpleNamespace(profile='p', execution_id='eid-1')
        result, result_child = fake_isolation._confined_launch(
            ApiWithChild(), rec, req, ['cmd'], {}, str(tmp_path / 'in'), str(tmp_path / 'out'), 5)
        assert result is not None and 'launch_failed' in result
        assert fake_isolation._live.get('eid-1') is child

    def test_no_child_attr_not_stored(self, tmp_path):
        """_confined_launch: when the exception has no .child, _live is not populated."""
        class Api:
            def open_inherited(self, path, mode):
                return object()

            def close_handle(self, h):
                pass

            def launch(self, *a, **kw):
                raise Exception('no child here')

        fake_isolation = object.__new__(iso.Isolation)
        fake_isolation._live = {}
        fake_isolation.held_job = lambda eid: None
        req = SimpleNamespace(workspace=str(tmp_path))
        rec = SimpleNamespace(profile='p', execution_id='eid-2')
        result, _ = fake_isolation._confined_launch(
            Api(), rec, req, ['x'], {}, str(tmp_path / 'in'), str(tmp_path / 'out'), 5)
        assert 'launch_failed' in result
        assert 'eid-2' not in fake_isolation._live


class TestPlainDir:

    def test_dir_with_reparse_is_not_plain(self):
        """_plain_dir (line ~1429): S_IFDIR + FILE_ATTRIBUTE_REPARSE_POINT => not plain."""
        st = _FakeSt(stat.S_IFDIR | 0o777, attrs=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        assert iso._plain_dir(st) is False

    def test_plain_dir_without_reparse(self):
        """_plain_dir: S_IFDIR with no reparse => plain."""
        st = _FakeSt(stat.S_IFDIR | 0o777, attrs=0)
        assert iso._plain_dir(st) is True


class TestQuiescentTypeCheck:

    def test_bool_false_is_not_zero(self, monkeypatch):
        """_quiescent (line ~1391): type(False) is bool, not int. Without the type
        guard, False == 0 would be True and falsely signal quiescence."""
        class Api:
            def job_active_processes(self, job):
                return False

        class TimeShim:
            t = 0.0

            @staticmethod
            def monotonic():
                return TimeShim.t

            @staticmethod
            def sleep(s):
                TimeShim.t += s

        monkeypatch.setattr(iso, 'time', TimeShim)
        monkeypatch.setattr(iso, 'EXIT_WAIT_S', 0.1)
        result = iso.Isolation._quiescent(Api(), 'job')
        assert result is not None and 'quiescence_unknown' in result

    def test_float_zero_is_not_int_zero(self, monkeypatch):
        """_quiescent: 0.0 == 0 but type(0.0) is float, not int: not quiescence."""
        class Api:
            def job_active_processes(self, job):
                return 0.0

        class TimeShim:
            t = 0.0

            @staticmethod
            def monotonic():
                return TimeShim.t

            @staticmethod
            def sleep(s):
                TimeShim.t += s

        monkeypatch.setattr(iso, 'time', TimeShim)
        monkeypatch.setattr(iso, 'EXIT_WAIT_S', 0.1)
        result = iso.Isolation._quiescent(Api(), 'job')
        assert result is not None and 'quiescence_unknown' in result
