"""T-814: mutation pins on archeus/node/seed.py.

Every test here names one branch of the module and fails when that branch is removed,
inverted or loosened; each pin was checked against a mutated copy of the module off-repo.
No Windows API, no network, no process and no real alias: an alias or an odd entry type
is presented through a faked `os.lstat`, the scan is a fake the test hands in."""

import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import seed

_REPARSE_ATTR = 0x400


def source_tree(tmp_path, files, name='src'):
    root = tmp_path / name
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def scan_ok():
    calls = []

    def scan(root):
        calls.append(root)
        return []

    return scan, calls


def scan_returns(found):
    calls = []

    def scan(root):
        calls.append(root)
        return list(found)

    return scan, calls


def _same(path, target):
    return os.path.normcase(os.path.abspath(os.fspath(path))) == os.path.normcase(str(target))


def fake_lstat(monkeypatch, target, st, ready=None):
    real = os.lstat

    def lstat(path, *args):
        if _same(path, target) and (ready is None or ready()):
            return st
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'lstat', lstat)


def reparse_dir():
    return SimpleNamespace(st_mode=stat.S_IFDIR, st_nlink=2,
                           st_file_attributes=_REPARSE_ATTR)


def seeded(tmp_path, files):
    src = source_tree(tmp_path, files)
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    seed.seed_copy({rel: src / rel for rel in files}, dest, scan)
    return dest


def test_under_refuses_a_sibling_whose_name_starts_with_the_destination(tmp_path):
    root = str(tmp_path / 'seed')
    (tmp_path / 'seedling').mkdir()
    inside = os.path.normpath(os.path.join(root, 'nested', 'x.txt'))
    assert seed._under(root, 'nested/x.txt') == inside
    with pytest.raises(seed.SeedError) as err:
        seed._under(root, '../seedling/x.txt')
    assert 'path escapes the destination' in str(err.value)


def test_changed_while_seeded_covers_inode_device_size_and_mtime(tmp_path):
    src = source_tree(tmp_path, {'one.txt': b'first\n'})
    st = os.stat(src / 'one.txt')
    assert seed._sig(st) == (st.st_ino, st.st_dev, st.st_size, st.st_mtime_ns)


@pytest.mark.parametrize('extra', [0x20, 0x800], ids=['archive', 'encrypted'])
def test_reparse_flag_beside_other_attribute_bits_refused(tmp_path, monkeypatch, extra):
    src = source_tree(tmp_path, {'one.txt': b'first\n'})
    dest = tmp_path / 'seed'
    fake_lstat(monkeypatch, src / 'one.txt', SimpleNamespace(
        st_mode=stat.S_IFREG, st_nlink=1,
        st_file_attributes=_REPARSE_ATTR | extra))
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'an alias, never followed: one.txt' in str(err.value)
    assert not dest.exists()
    assert calls == []


def test_destination_leaf_that_turned_into_a_directory_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path, {'one.txt': b'first\n'})
    dest = tmp_path / 'seed'
    fake_lstat(monkeypatch, dest / 'one.txt', SimpleNamespace(
        st_mode=stat.S_IFDIR, st_nlink=1, st_file_attributes=0))
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'not the file expected: one.txt' in str(err.value)
    assert (dest / 'one.txt').read_bytes() == b'first\n'
    assert calls == []


def test_walk_refuses_an_entry_that_is_neither_directory_nor_file(tmp_path, monkeypatch):
    dest = seeded(tmp_path, {'one.txt': b'first\n'})
    fake_lstat(monkeypatch, dest / 'one.txt', SimpleNamespace(
        st_mode=stat.S_IFIFO, st_nlink=1, st_file_attributes=0))
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.recheck(dest, scan)
    assert 'not the plain entry expected: one.txt' in str(err.value)
    assert calls == []


def test_two_files_sharing_a_parent_directory_are_seeded(tmp_path):
    src = source_tree(tmp_path, {'a/one.txt': b'first\n', 'a/two.txt': b'second\n'})
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    seed.seed_copy({'a/one.txt': src / 'a' / 'one.txt',
                    'a/two.txt': src / 'a' / 'two.txt'}, dest, scan)
    assert calls == [dest]
    assert (dest / 'a' / 'one.txt').read_bytes() == b'first\n'
    assert (dest / 'a' / 'two.txt').read_bytes() == b'second\n'


def test_alias_in_a_nested_directory_is_found_by_the_walk(tmp_path, monkeypatch):
    src = source_tree(tmp_path, {'a/b/deep.txt': b'deep\n'})
    dest = tmp_path / 'seed'
    copied = {'done': False}
    real_copy = seed._copy

    def copy(source, dst, rel):
        real_copy(source, dst, rel)
        copied['done'] = True

    monkeypatch.setattr(seed, '_copy', copy)
    fake_lstat(monkeypatch, dest / 'a' / 'b', reparse_dir(), lambda: copied['done'])
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'a/b/deep.txt': src / 'a' / 'b' / 'deep.txt'}, dest, scan)
    assert 'an alias appeared in the destination: a/b' in str(err.value)
    assert calls == []
    assert (dest / 'a' / 'b' / 'deep.txt').read_bytes() == b'deep\n'


def test_the_walk_of_a_seeded_tree_runs_before_the_scan(tmp_path, monkeypatch):
    src = source_tree(tmp_path, {'a/b/deep.txt': b'deep\n'})
    dest = tmp_path / 'seed'
    copied = {'done': False}
    real_copy = seed._copy

    def copy(source, dst, rel):
        real_copy(source, dst, rel)
        copied['done'] = True

    monkeypatch.setattr(seed, '_copy', copy)
    fake_lstat(monkeypatch, dest / 'a' / 'b', reparse_dir(), lambda: copied['done'])
    scan, calls = scan_returns(['a/b/deep.txt'])
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'a/b/deep.txt': src / 'a' / 'b' / 'deep.txt'}, dest, scan)
    assert 'an alias appeared in the destination: a/b' in str(err.value)
    assert 'the scan refused' not in str(err.value)
    assert calls == []


def test_recheck_walks_the_tree_before_it_scans(tmp_path, monkeypatch):
    dest = seeded(tmp_path, {'a/b/deep.txt': b'deep\n'})
    fake_lstat(monkeypatch, dest / 'a' / 'b', reparse_dir())
    scan, calls = scan_returns(['a/b/deep.txt'])
    with pytest.raises(seed.SeedError) as err:
        seed.recheck(dest, scan)
    assert 'an alias appeared in the destination: a/b' in str(err.value)
    assert 'the scan refused' not in str(err.value)
    assert calls == []


def test_scan_finding_names_only_the_first_refusal(tmp_path):
    src = source_tree(tmp_path, {'one.txt': b'first\n'})
    dest = tmp_path / 'seed'
    scan, calls = scan_returns(['a/first.txt', 'b/second.txt'])
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'the scan refused: a/first.txt' in str(err.value)
    assert 'b/second.txt' not in str(err.value)
    assert calls == [dest]


def test_seed_copy_refuses_a_bytes_blob_of_source_files(tmp_path):
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy(b'one.txt', dest, scan)
    assert 'must be a mapping or a list of pairs' in str(err.value)
    assert not dest.exists()
    assert calls == []


def test_import_back_refuses_a_bytes_blob_of_files(tmp_path):
    root = source_tree(tmp_path, {'data/in.json': b'{"a":1}\n'}, name='node')
    dest = tmp_path / 'imported'
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.import_back(root, b'data/in.json', dest, scan)
    assert 'files must be a list of relative paths' in str(err.value)
    assert not dest.exists()
    assert calls == []


def test_rows_refuse_a_source_held_by_a_sibling_of_the_root(tmp_path):
    root = tmp_path / 'node'
    (root / 'data').mkdir(parents=True)
    (root / 'data' / 'ok.txt').write_bytes(b'ok\n')
    (tmp_path / 'node_evil').mkdir()
    (tmp_path / 'node_evil' / 'stolen.txt').write_bytes(b'not mine\n')
    rows = seed._rows([('data/ok.txt', root / 'data' / 'ok.txt')], str(root))
    assert [(rel, os.path.basename(src))
            for rel, src, _ in rows] == [('data/ok.txt', 'ok.txt')]
    with pytest.raises(seed.SeedError) as err:
        seed._rows([('stolen.txt', tmp_path / 'node_evil' / 'stolen.txt')], str(root))
    assert 'path escapes the source' in str(err.value)
