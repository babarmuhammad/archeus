import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import linkscan


def hardlink(source, destination):
    try:
        os.link(source, destination)
    except OSError as err:
        pytest.skip('hardlinks unavailable: %s' % err)


def test_nested_links_sorted_relative(tmp_path):
    root = tmp_path / 'root'
    (root / 'nested').mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.write_text('data')
    hardlink(outside, root / 'z')
    hardlink(outside, root / 'nested' / 'a')
    (root / 'single').write_text('clean')
    assert linkscan.multi_linked_files(root) == ['nested/a', 'z']


@pytest.mark.parametrize('kind', ['missing', 'file'])
def test_invalid_root(tmp_path, kind):
    root = tmp_path / kind
    if kind == 'file':
        root.write_text('data')
    with pytest.raises(ValueError):
        linkscan.multi_linked_files(root)


@pytest.mark.parametrize('mode,expected', [
    (stat.S_IFREG, ['entry']), (stat.S_IFDIR, []),
    (stat.S_IFIFO, []), (stat.S_IFSOCK, []),
])
def test_only_regular_files_reported(tmp_path, monkeypatch, mode, expected):
    entry = tmp_path / 'entry'
    entry.mkdir()
    original = os.lstat

    def lstat(path):
        if os.fspath(path) == str(entry):
            return SimpleNamespace(st_mode=mode, st_nlink=3)
        return original(path)

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    assert linkscan.multi_linked_files(tmp_path) == expected


@pytest.mark.parametrize('alias', ['symlink', 'junction'])
def test_aliases_not_traversed(tmp_path, monkeypatch, alias):
    entry = tmp_path / 'alias'
    entry.mkdir()
    original = os.lstat
    scandir = os.scandir

    def lstat(path):
        if os.fspath(path) == str(entry):
            return SimpleNamespace(st_mode=stat.S_IFLNK if alias == 'symlink'
                                   else stat.S_IFDIR, st_nlink=2,
                                   st_file_attributes=0x400 if alias == 'junction' else 0)
        return original(path)

    def scan(path):
        assert os.fspath(path) != str(entry)
        return scandir(path)

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    monkeypatch.setattr(linkscan.os, 'scandir', scan)
    assert linkscan.multi_linked_files(tmp_path) == []


def test_clean_folder(tmp_path):
    (tmp_path / 'nested').mkdir()
    (tmp_path / 'nested' / 'file').write_text('clean')
    assert linkscan.multi_linked_files(tmp_path) == []


@pytest.mark.parametrize('alias', ['symlink', 'junction'])
def test_alias_root_refused(tmp_path, monkeypatch, alias):
    original = os.lstat

    def lstat(path):
        if os.fspath(path) == str(tmp_path):
            return SimpleNamespace(st_mode=stat.S_IFLNK if alias == 'symlink'
                                   else stat.S_IFDIR, st_file_attributes=0x400)
        return original(path)

    monkeypatch.setattr(linkscan.os, 'lstat', lstat)
    with pytest.raises(ValueError):
        linkscan.multi_linked_files(tmp_path)


@pytest.mark.parametrize('operation', ['lstat', 'scandir'])
def test_scan_errors_propagate(tmp_path, monkeypatch, operation):
    def fail(*args):
        raise PermissionError('denied')

    monkeypatch.setattr(linkscan.os, operation, fail)
    with pytest.raises(PermissionError):
        linkscan.multi_linked_files(tmp_path)
