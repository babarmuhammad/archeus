"""T-249: close the highest-risk test gaps in the hardlink gate and grant scans.

Every OS call is faked through the seams the existing tests use
(monkeypatching the `os` attribute of the module under test, or the module
seams `linkscan.multi_linked_files` and `staging._write`); fixtures are
platform-neutral: bytes written, no hardlinks required, no case sensitivity,
no `?` or `:` in names, no localized OS text, no sleeps.
"""

import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import linkscan, mxc, staging


class Refusal(Exception):
    """Stand-in grant error, the way mxc.MxcUnavailable and StageError are used."""


# ---------------------------------------------------------------- linkscan


@pytest.mark.parametrize('nlink,expected', [
    (1, []), (2, ['dup']), (3, ['dup']),
])
def test_multi_linked_files_nlink_boundary(tmp_path, monkeypatch, nlink, expected):
    dup = tmp_path / 'dup'
    dup.write_bytes(b'x')
    original = os.lstat

    def lstat(path):
        if os.fspath(path) == str(dup):
            return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=nlink)
        return original(path)

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    assert linkscan.multi_linked_files(tmp_path) == expected


def test_multi_linked_files_deep_tree_reported(tmp_path, monkeypatch):
    deep = tmp_path
    parts = ['d%02d' % i for i in range(40)]
    for part in parts:
        deep = deep / part
    deep.mkdir(parents=True)
    bottom = deep / 'bottom'
    bottom.write_bytes(b'x')
    original = os.lstat

    def lstat(path):
        if os.fspath(path) == str(bottom):
            return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=2)
        return original(path)

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    assert linkscan.multi_linked_files(tmp_path) == ['/'.join(parts + ['bottom'])]


def test_multi_linked_files_wide_tree_sorted_unique(tmp_path, monkeypatch):
    names = ['f%02d' % i for i in range(50)]
    for name in names:
        (tmp_path / name).write_bytes(b'x')
    bad = {'f05', 'f07', 'f20', 'f33', 'f49'}
    with os.scandir(tmp_path) as entries:
        shuffled = sorted(entries, key=lambda e: e.name, reverse=True)
    original_lstat = os.lstat

    def lstat(path):
        if os.path.basename(os.fspath(path)) in bad:
            return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=2)
        return original_lstat(path)

    class _Scan:
        def __init__(self, items):
            self._items = list(items)

        def __enter__(self):
            return iter(self._items)

        def __exit__(self, *exc):
            return False

    original_scandir = os.scandir

    def scandir(path):
        if os.fspath(path) == str(tmp_path):
            return _Scan(shuffled)
        return original_scandir(path)

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    monkeypatch.setattr(linkscan.os, 'scandir', scandir)
    found = linkscan.multi_linked_files(tmp_path)
    assert found == sorted(bad)
    assert len(found) == len(set(found))


def test_multi_linked_files_relative_path_uses_forward_slash(tmp_path, monkeypatch):
    sub = tmp_path / 'sub'
    sub.mkdir()
    dup = sub / 'dup'
    dup.write_bytes(b'x')
    original_lstat = os.lstat

    def lstat(path):
        if os.fspath(path) == str(dup):
            return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=2)
        return original_lstat(path)

    original_relpath = os.path.relpath

    def relpath(path, start=None):
        if os.fspath(path) == str(dup):
            return 'sub' + os.sep + 'dup'
        return original_relpath(path, start)

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    monkeypatch.setattr(linkscan.os, 'sep', '\\')
    monkeypatch.setattr(linkscan.os.path, 'relpath', relpath)
    assert linkscan.multi_linked_files(tmp_path) == ['sub/dup']


@pytest.mark.parametrize('kind', ['missing', 'file', 'symlink-root', 'reparse-root'])
def test_multi_linked_files_root_kinds(tmp_path, monkeypatch, kind):
    if kind == 'missing':
        with pytest.raises(ValueError, match='scan root must be a directory$'):
            linkscan.multi_linked_files(tmp_path / 'missing')
        return
    if kind == 'file':
        root = tmp_path / 'plain-file'
        root.write_bytes(b'x')
        with pytest.raises(ValueError, match='scan root must be a directory without aliases'):
            linkscan.multi_linked_files(root)
        return
    original = os.lstat

    def lstat(path):
        if os.fspath(path) == str(tmp_path):
            if kind == 'symlink-root':
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_nlink=1)
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_nlink=1,
                                   st_file_attributes=0x400)
        return original(path)

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    if kind == 'symlink-root':
        with pytest.raises(ValueError, match='scan root must be a directory without aliases'):
            linkscan.multi_linked_files(tmp_path)
    else:
        with pytest.raises(ValueError, match='without aliases'):
            linkscan.multi_linked_files(tmp_path)


def test_multi_linked_files_scandir_failure_mid_walk(tmp_path, monkeypatch):
    (tmp_path / 'ok').mkdir()
    (tmp_path / 'bad').mkdir()
    original = os.scandir

    def scandir(path):
        if os.fspath(path) == str(tmp_path / 'bad'):
            raise PermissionError('denied by fixture')
        return original(path)

    monkeypatch.setattr(linkscan.os, 'scandir', scandir)
    with pytest.raises(PermissionError):
        linkscan.multi_linked_files(tmp_path)


def test_multi_linked_files_entry_lstat_failure_mid_walk(tmp_path, monkeypatch):
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'child').write_bytes(b'x')
    original = os.lstat

    def lstat(path):
        if os.fspath(path) == str(sub / 'child'):
            raise OSError('denied by fixture')
        return original(path)

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    with pytest.raises(OSError):
        linkscan.multi_linked_files(tmp_path)


@pytest.mark.parametrize('failure', ['value-error', 'os-error'])
def test_check_grants_refuses_failed_scan(tmp_path, monkeypatch, failure):
    if failure == 'value-error':
        root = tmp_path / 'plain-file'
        root.write_bytes(b'x')
    else:
        root = tmp_path

        def scandir(*args):
            raise PermissionError('denied by fixture')

        monkeypatch.setattr(linkscan.os, 'scandir', scandir)
    with pytest.raises(Refusal, match='hardlink scan failed; grant refused'):
        linkscan.check_grants((root,), Refusal)


def test_check_grants_error_names_only_first_relative(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    (root / 'nested').mkdir(parents=True)
    (root / 'z').write_bytes(b'x')
    (root / 'nested' / 'a').write_bytes(b'x')
    original = os.lstat

    def lstat(path):
        if os.fspath(path) in (str(root / 'z'), str(root / 'nested' / 'a')):
            return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=2)
        return original(path)

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    with pytest.raises(Refusal) as caught:
        linkscan.check_grants((root,), Refusal)
    assert str(caught.value) == 'multiple links in grant (a second name): nested/a'
    assert str(root) not in str(caught.value)


# ---------------------------------------------------------------- mxc grant scan


@pytest.mark.parametrize('alias', ['symlink', 'reparse'])
def test_scan_grant_refuses_alias_ancestor(tmp_path, monkeypatch, alias):
    work = tmp_path / 'work'
    work.mkdir()
    original = os.lstat

    def lstat(path, *args, **kwargs):
        if os.path.abspath(os.fspath(path)) == str(tmp_path):
            if alias == 'symlink':
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_nlink=1)
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_nlink=1,
                                   st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(mxc.os, 'lstat', lstat)
    with pytest.raises(mxc.MxcUnavailable, match='alias in grant ancestor'):
        mxc.scan_grant(work)


def test_scan_grant_refuses_unreadable_ancestor(tmp_path, monkeypatch):
    work = tmp_path / 'work'
    work.mkdir()
    original = os.lstat

    def lstat(path, *args, **kwargs):
        if os.path.abspath(os.fspath(path)) == str(tmp_path):
            raise PermissionError('denied by fixture')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(mxc.os, 'lstat', lstat)
    with pytest.raises(mxc.MxcUnavailable, match='unreadable grant ancestor'):
        mxc.scan_grant(work)


def test_scan_grant_refuses_unsupported_grant_object(tmp_path, monkeypatch):
    work = tmp_path / 'work'
    (work / 'weird').mkdir(parents=True)
    original = os.lstat

    def lstat(path, *args, **kwargs):
        st = original(path, *args, **kwargs)
        if os.path.abspath(os.fspath(path)) == str(work / 'weird'):
            return SimpleNamespace(st_mode=stat.S_IFIFO, st_nlink=1)
        return st

    monkeypatch.setattr(mxc.os, 'lstat', lstat)
    with pytest.raises(mxc.MxcUnavailable, match='unsupported grant object'):
        mxc.scan_grant(work)


def test_scan_grant_refuses_unreadable_grant_mid_walk(tmp_path, monkeypatch):
    work = tmp_path / 'work'
    (work / 'locked').mkdir(parents=True)
    original = os.lstat

    def lstat(path, *args, **kwargs):
        if os.path.abspath(os.fspath(path)) == str(work / 'locked'):
            raise PermissionError('denied by fixture')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(linkscan, 'multi_linked_files', lambda root: [])
    monkeypatch.setattr(mxc.os, 'lstat', lstat)
    with pytest.raises(mxc.MxcUnavailable, match='unreadable grant:'):
        mxc.scan_grant(work)


@pytest.mark.parametrize('readonly', [False, True])
def test_link_created_between_grant_scan_and_launch_refuses(tmp_path, monkeypatch, readonly):
    work = tmp_path / 'work'
    work.mkdir()
    granted = tmp_path / 'runtime' if readonly else work
    granted.mkdir(exist_ok=True)
    compiled = mxc.compile_policy(
        workspace=work, cwd=work, command_line='cmd.exe /d /c echo fixture',
        env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': str(work)},
        timeout_ms=1000, readonly=(granted,) if readonly else ())
    real_scan = linkscan.multi_linked_files

    def scan(root):
        if os.path.abspath(str(root)) == str(granted):
            return ['late']
        return real_scan(root)

    monkeypatch.setattr(linkscan, 'multi_linked_files', scan)
    fake = mxc.FakeMxc([mxc.FakeOutcome()])
    with pytest.raises(mxc.MxcUnavailable, match='multiple links in grant') as caught:
        mxc.spawn(compiled, exe='unused', job=object(), backend=fake)
    assert 'multiple links in grant (a second name): late' in str(caught.value)
    assert str(granted) not in str(caught.value)
    assert fake.calls == []


# ---------------------------------------------------------------- staging grant scan


@pytest.mark.parametrize('alias', ['symlink', 'reparse'])
def test_scan_grants_refuses_child_alias(tmp_path, monkeypatch, alias):
    grant = tmp_path / 'grant'
    grant.mkdir(parents=True)
    (grant / 'plain').write_bytes(b'x')
    link = grant / 'link'
    link.mkdir()
    original = os.lstat

    def lstat(path, *args, **kwargs):
        st = original(path, *args, **kwargs)
        if os.path.abspath(os.fspath(path)) == str(link):
            if alias == 'symlink':
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_nlink=1)
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_nlink=2,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return st

    monkeypatch.setattr(staging.os, 'lstat', lstat)
    with pytest.raises(staging.StageError, match='an alias, never followed'):
        staging.scan_grants((grant,))


def test_scan_grants_refuses_special_entry(tmp_path, monkeypatch):
    grant = tmp_path / 'grant'
    (grant / 'weird').mkdir(parents=True)
    original = os.lstat

    def lstat(path, *args, **kwargs):
        st = original(path, *args, **kwargs)
        if os.path.abspath(os.fspath(path)) == str(grant / 'weird'):
            return SimpleNamespace(st_mode=stat.S_IFIFO, st_nlink=1)
        return st

    monkeypatch.setattr(staging.os, 'lstat', lstat)
    with pytest.raises(staging.StageError, match='not the plain entry expected'):
        staging.scan_grants((grant,))


@pytest.mark.parametrize('nlink,refused', [(1, False), (2, True), (3, True)])
def test_scan_grants_file_nlink_busy_dirs_walked(tmp_path, monkeypatch, nlink, refused):
    grant = tmp_path / 'grant'
    (grant / 'd').mkdir(parents=True)
    (grant / 'f').write_bytes(b'x')
    original = os.lstat

    def lstat(path, *args, **kwargs):
        st = original(path, *args, **kwargs)
        target = os.path.abspath(os.fspath(path))
        if target == str(grant / 'd'):
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_nlink=4)
        if target == str(grant / 'f'):
            return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=nlink)
        return st

    monkeypatch.setattr(staging.os, 'lstat', lstat)
    if refused:
        with pytest.raises(staging.StageError, match='a second name for'):
            staging.scan_grants((grant,))
    else:
        staging.scan_grants((grant,))


def test_scan_grants_checks_every_grant(tmp_path, monkeypatch):
    clean = tmp_path / 'clean'
    clean.mkdir()
    (clean / 'ok').write_bytes(b'x')
    dirty = tmp_path / 'dirty'
    dirty.mkdir()
    (dirty / 'dup').write_bytes(b'x')
    original = os.lstat

    def lstat(path, *args, **kwargs):
        st = original(path, *args, **kwargs)
        if os.path.abspath(os.fspath(path)) == str(dirty / 'dup'):
            return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=2)
        return st

    monkeypatch.setattr(staging.os, 'lstat', lstat)
    with pytest.raises(staging.StageError, match='a second name for'):
        staging.scan_grants((clean, dirty))
