"""T-453: the copy-only seeder, on synthetic trees only.

No Windows API, no network, no process and no real alias: a link or a reparse point is
presented through a faked `os.lstat`, and the scan is a fake the test hands in, so every
branch named here is the branch that fires (C-1013 audit slice 7)."""

import hashlib
import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import seed

CLEAN = {'one.txt': b'first\n', 'nested/two.bin': b'\x00\xff\xfe\x01binary'}
ESCAPES = [
    ('/etc/passwd', 'absolute path'),
    ('//server/share/x', 'absolute path'),
    ('C:/Windows/win.ini', 'drive or UNC prefix'),
    ('D:x', 'drive or UNC prefix'),
    ('\\server\\share\\x', 'drive or UNC prefix'),
    ('a/b:c', 'drive or UNC prefix'),
    ('a\x00b', 'drive or UNC prefix'),
    ('../escape', 'parent segment'),
    ('a/../../b', 'parent segment'),
    ('a/../b', 'parent segment'),
    ('./x', 'refused path segment'),
    ('a//b', 'refused path segment'),
    ('a/', 'refused path segment'),
    ('file.', 'refused path segment'),
    ('file ', 'refused path segment'),
    ('dir./x', 'refused path segment'),
    ('x/./y', 'refused path segment'),
    ('...', 'refused path segment'),
    (' ', 'refused path segment'),
]
REMOVALS = ('remove', 'unlink', 'rmdir', 'removedirs', 'replace', 'rename')


def source_tree(tmp_path, files=None, name='src'):
    root = tmp_path / name
    for rel, data in (CLEAN if files is None else files).items():
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


def scan_raises(err):
    calls = []

    def scan(root):
        calls.append(root)
        raise err

    return scan, calls


def _same(path, target):
    return os.path.normcase(os.path.abspath(os.fspath(path))) == os.path.normcase(str(target))


def fake_lstat(monkeypatch, target, st):
    real = os.lstat

    def lstat(path, *args):
        if _same(path, target):
            return st
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'lstat', lstat)


def seeded(tmp_path, scan=None):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    active = scan or (lambda root: [])
    seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, active)
    return src, dest


def test_seed_copy_writes_a_fresh_tree_byte_for_byte(tmp_path):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    assert seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan) is dest
    assert calls == [dest]
    for rel, data in CLEAN.items():
        assert (dest / rel).read_bytes() == data
    assert (dest / 'nested').is_dir()


def test_seed_copy_survives_chunking(tmp_path):
    big = (b'a\x00\xff\x7f' * ((1 << 20) // 4 + 1)) + b'tail'
    src = source_tree(tmp_path, {'big.bin': big})
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    seed.seed_copy({'big.bin': src / 'big.bin'}, dest, scan)
    assert calls == [dest]
    digest = hashlib.sha256((dest / 'big.bin').read_bytes()).hexdigest()
    assert digest == hashlib.sha256(big).hexdigest()


def test_seed_copy_accepts_a_list_of_pairs(tmp_path):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    seed.seed_copy([('one.txt', src / 'one.txt'), ('a/b/c.txt', src / 'one.txt')],
                   dest, scan)
    assert calls == [dest]
    assert (dest / 'a' / 'b' / 'c.txt').read_bytes() == CLEAN['one.txt']


def test_destination_that_cannot_be_looked_at_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    real = os.lstat

    def lstat(path, *args):
        if _same(path, dest):
            raise PermissionError('denied')
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'lstat', lstat)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'the destination cannot be looked at' in str(err.value)
    assert isinstance(err.value.__cause__, PermissionError)
    assert calls == []


@pytest.mark.parametrize('alias', ['symlink', 'junction'])
def test_source_alias_refused(tmp_path, monkeypatch, alias):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    fake_lstat(monkeypatch, src / 'one.txt', SimpleNamespace(
        st_mode=stat.S_IFLNK if alias == 'symlink' else stat.S_IFREG, st_nlink=2,
        st_file_attributes=0x400 if alias == 'junction' else 0))
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'an alias, never followed: one.txt' in str(err.value)
    assert not dest.exists()
    assert calls == []


@pytest.mark.parametrize('mode', [stat.S_IFDIR, stat.S_IFIFO, stat.S_IFSOCK])
def test_source_not_a_regular_file_refused(tmp_path, monkeypatch, mode):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    fake_lstat(monkeypatch, src / 'one.txt', SimpleNamespace(st_mode=mode, st_nlink=1))
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'not a regular file: one.txt' in str(err.value)
    assert not dest.exists()
    assert calls == []


@pytest.mark.parametrize('kind', ['missing', 'denied'])
def test_source_that_cannot_be_looked_at_refused(tmp_path, monkeypatch, kind):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    if kind == 'missing':
        gone = src / 'gone.txt'
    else:
        gone = src / 'one.txt'
        real = os.lstat

        def lstat(path, *args):
            if _same(path, gone):
                raise PermissionError('denied')
            return real(path, *args)

        monkeypatch.setattr(seed.os, 'lstat', lstat)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': gone}, dest, scan)
    assert 'the source cannot be looked at: one.txt' in str(err.value)
    assert isinstance(err.value.__cause__,
                      FileNotFoundError if kind == 'missing' else PermissionError)
    assert not dest.exists()


def test_destination_that_exists_refused(tmp_path):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    (dest / 'nested').mkdir(parents=True)
    (dest / 'one.txt').write_bytes(b'user data')
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'the destination already exists' in str(err.value)
    assert (dest / 'one.txt').read_bytes() == b'user data'
    assert calls == []


def test_destination_leaf_never_overwritten(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    real_under = seed._under

    def under(root, rel):
        dst = real_under(root, rel)
        with open(dst, 'wb') as f:
            f.write(b'someone else got there first')
        return dst

    monkeypatch.setattr(seed, '_under', under)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'refusing to overwrite: one.txt' in str(err.value)
    assert (dest / 'one.txt').read_bytes() == b'someone else got there first'
    assert calls == []


def test_destination_directory_never_overwritten(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    real_sha = seed._sha

    def sha(path):
        if not (dest / 'nested').exists():
            os.mkdir(dest / 'nested')
        return real_sha(path)

    monkeypatch.setattr(seed, '_sha', sha)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'refusing to overwrite: nested' in str(err.value)
    assert calls == []


def test_destination_root_alias_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    real = os.lstat
    seen = {'looks': 0}

    def lstat(path, *args):
        if _same(path, dest):
            seen['looks'] += 1
            if seen['looks'] > 1:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_nlink=1,
                                       st_file_attributes=0x400)
            raise FileNotFoundError(2, 'gone')
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'lstat', lstat)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'an alias appeared in the destination: .' in str(err.value)
    assert calls == []
    assert os.listdir(dest) == []


def test_written_file_that_vanished_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    real = os.lstat
    seen = {'misses': 0}

    def lstat(path, *args):
        if _same(path, dest / 'one.txt') and seen['misses'] == 0:
            seen['misses'] += 1
            raise FileNotFoundError(2, 'gone')
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'lstat', lstat)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'the destination cannot be looked at: one.txt' in str(err.value)
    assert isinstance(err.value.__cause__, FileNotFoundError)
    assert (dest / 'one.txt').read_bytes() == CLEAN['one.txt']
    assert calls == []


def test_destination_directory_that_is_a_file_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    real_sha = seed._sha

    def sha(path):
        if not (dest / 'nested').exists():
            (dest / 'nested').write_bytes(b'in the way')
        return real_sha(path)

    monkeypatch.setattr(seed, '_sha', sha)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'not the directory expected: nested' in str(err.value)
    assert calls == []


def test_destination_alias_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    fake_lstat(monkeypatch, dest / 'one.txt', SimpleNamespace(
        st_mode=stat.S_IFREG, st_nlink=1, st_file_attributes=0x400))
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'an alias appeared in the destination: one.txt' in str(err.value)
    assert calls == []


def test_destination_directory_alias_refused_by_the_walk(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    fake_lstat(monkeypatch, dest / 'nested', SimpleNamespace(
        st_mode=stat.S_IFDIR, st_nlink=2, st_file_attributes=0x400))
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'an alias appeared in the destination: nested' in str(err.value)
    assert calls == []


def test_destination_that_cannot_be_listed_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    real = os.scandir

    def scandir(path, *args):
        if _same(path, dest):
            raise PermissionError('denied')
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'scandir', scandir)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'the destination cannot be listed: .' in str(err.value)
    assert isinstance(err.value.__cause__, PermissionError)
    assert calls == []


@pytest.mark.parametrize('rel,token', ESCAPES)
def test_seeded_path_that_escapes_refused(tmp_path, rel, token):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / 'one.txt'}, dest, scan)
    assert token in str(err.value)
    assert not dest.exists()
    assert calls == []


@pytest.mark.parametrize('rel', [5, '', None, b'one.txt', ('a', 'b')])
def test_seeded_path_that_is_not_a_relative_path(tmp_path, rel):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / 'one.txt'}, dest, scan)
    assert 'not a relative path' in str(err.value)
    assert not dest.exists()


def test_seeded_path_escape_still_caught_after_the_shape_check(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    monkeypatch.setattr(seed, '_rel', lambda value: value)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'../../escape': src / 'one.txt'}, dest, scan)
    assert 'path escapes the destination' in str(err.value)
    assert os.listdir(dest) == []


@pytest.mark.parametrize('second', ['A.TXT', 'a.txt'])
def test_duplicate_destination_after_case_folding_refused(tmp_path, second):
    src = source_tree(tmp_path, {'a.txt': b'one\n', 'A.TXT': b'two\n'})
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy([('a.txt', src / 'a.txt'), (second, src / 'A.TXT')], dest, scan)
    assert 'the same destination twice: %s' % second in str(err.value)
    assert not dest.exists()


def test_scan_finding_refuses_the_seed_and_removes_nothing(tmp_path, monkeypatch):
    def boom(*args):
        raise AssertionError('a removal primitive was called')

    for name in REMOVALS:
        monkeypatch.setattr(seed.os, name, boom)
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    scan, calls = scan_returns(['nested/two.bin'])
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert calls == [dest]
    assert 'the scan refused: nested/two.bin' in str(err.value)
    assert str(dest) not in str(err.value) and str(tmp_path) not in str(err.value)
    for rel, data in CLEAN.items():
        assert (dest / rel).read_bytes() == data


def test_scan_exception_refuses_the_seed_and_removes_nothing(tmp_path):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    cause = RuntimeError('the scanner itself broke')
    scan, calls = scan_raises(cause)
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert calls == [dest]
    assert err.value.__cause__ is cause
    for rel, data in CLEAN.items():
        assert (dest / rel).read_bytes() == data


def test_scan_of_a_typed_error_propagates_and_removes_nothing(tmp_path):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    cause = seed.SeedError('the scan refused: nested')
    scan, calls = scan_raises(cause)
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert err.value is cause
    assert calls == [dest]
    for rel, data in CLEAN.items():
        assert (dest / rel).read_bytes() == data


def test_clean_scan_runs_once_per_seed_and_again_on_recheck(tmp_path):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    assert seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan) is dest
    assert calls == [dest]
    assert seed.recheck(dest, scan) is dest
    assert calls == [dest, dest]
    for rel, data in CLEAN.items():
        assert (dest / rel).read_bytes() == data


def test_recheck_finding_names_only_the_relative_path(tmp_path):
    _, dest = seeded(tmp_path)
    scan, calls = scan_returns(['nested/two.bin'])
    with pytest.raises(seed.SeedError) as err:
        seed.recheck(dest, scan)
    assert calls == [dest]
    assert 'nested/two.bin' in str(err.value)
    assert str(dest) not in str(err.value) and str(tmp_path) not in str(err.value)
    for rel, data in CLEAN.items():
        assert (dest / rel).read_bytes() == data


def test_recheck_exception_becomes_a_typed_error(tmp_path):
    _, dest = seeded(tmp_path)
    cause = RuntimeError('the scanner itself broke')
    scan, calls = scan_raises(cause)
    with pytest.raises(seed.SeedError) as err:
        seed.recheck(dest, scan)
    assert calls == [dest]
    assert err.value.__cause__ is cause
    for rel, data in CLEAN.items():
        assert (dest / rel).read_bytes() == data


def test_recheck_refuses_a_destination_that_is_a_file(tmp_path):
    (tmp_path / 'seed').write_bytes(b'not a tree')
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.recheck(tmp_path / 'seed', scan)
    assert 'not the directory expected: .' in str(err.value)
    assert calls == []


def test_recheck_missing_root_refused(tmp_path):
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.recheck(tmp_path / 'never-seeded', scan)
    assert 'the destination cannot be looked at' in str(err.value)
    assert calls == []


def test_import_back_copies_data_only(tmp_path):
    root = source_tree(tmp_path, {'data/in.json': b'{"a":1}', 'data/out.json': b'{}'},
                       name='node')
    dest = tmp_path / 'imported'
    scan, calls = scan_ok()
    got = seed.import_back(root, ['data/in.json', 'data/out.json'], dest, scan)
    assert got is dest
    assert calls == [dest]
    assert (dest / 'data' / 'in.json').read_bytes() == b'{"a":1}'
    assert (dest / 'data' / 'out.json').read_bytes() == b'{}'


def test_import_back_destination_that_exists_refused(tmp_path):
    root = source_tree(tmp_path, {'data/in.json': b'{"a":1}'}, name='node')
    dest = tmp_path / 'imported'
    dest.mkdir()
    (dest / 'old.json').write_bytes(b'kept')
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.import_back(root, ['data/in.json'], dest, scan)
    assert 'the destination already exists' in str(err.value)
    assert (dest / 'old.json').read_bytes() == b'kept' and calls == []


@pytest.mark.parametrize('rel,token', ESCAPES)
def test_imported_path_that_escapes_refused(tmp_path, rel, token):
    root = source_tree(tmp_path, {'one.txt': b'x'}, name='node')
    dest = tmp_path / 'imported'
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.import_back(root, [rel], dest, scan)
    assert token in str(err.value)
    assert not dest.exists()


def test_imported_path_escape_caught_after_the_shape_check(tmp_path, monkeypatch):
    root = source_tree(tmp_path, {'one.txt': b'x'}, name='node')
    (tmp_path / 'outside.txt').write_bytes(b'not mine')
    dest = tmp_path / 'imported'
    monkeypatch.setattr(seed, '_rel', lambda value: value)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.import_back(root, ['../outside.txt'], dest, scan)
    assert 'path escapes the source' in str(err.value)
    assert not dest.exists()


def test_import_back_alias_source_refused(tmp_path, monkeypatch):
    root = source_tree(tmp_path, {'one.txt': b'x'}, name='node')
    dest = tmp_path / 'imported'
    fake_lstat(monkeypatch, root / 'one.txt', SimpleNamespace(
        st_mode=stat.S_IFLNK, st_nlink=1, st_file_attributes=0))
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.import_back(root, ['one.txt'], dest, scan)
    assert 'an alias, never followed: one.txt' in str(err.value)
    assert not dest.exists()


REFUSED_NAMES = ['.git/config', '.GIT/hooks/post-checkout', 'GIT~1/config', 'a/.git/x', 'CONIN$',
                 'COM1', 'LPT1', 'aux.txt', 'x/NUL', 'nul', 'con.log', 'a/b.', 'a ']


@pytest.mark.parametrize('rel', REFUSED_NAMES)
def test_a_name_git_or_windows_treats_specially_is_never_seeded_or_imported(tmp_path, rel):
    """`.git/config` and `GIT~1/hooks/...` would carry hostile git config into a workspace
    Core's git later runs in; device names reach a device, not a file (review R7)."""
    src = source_tree(tmp_path, {'one.txt': b'x'}, name='src')
    scan, _ = scan_ok()
    with pytest.raises(seed.SeedError, match='refused path segment'):
        seed.seed_copy({rel: src / 'one.txt'}, tmp_path / 'seed', scan)
    with pytest.raises(seed.SeedError, match='refused path segment'):
        seed.import_back(src, [rel], tmp_path / 'imported', scan)
    assert not (tmp_path / 'seed').exists() and not (tmp_path / 'imported').exists()


def test_the_control_names_that_only_look_like_those_are_seeded(tmp_path):
    names = {'gitignore': b'a', 'git/config': b'b', 'console.txt': b'c', 'com10': b'd',
             '.gitignore': b'e', 'dot.git/x': b'f'}
    src = source_tree(tmp_path, names, name='src')
    scan, _ = scan_ok()
    seed.seed_copy({rel: src / rel for rel in names}, tmp_path / 'seed', scan)
    assert (tmp_path / 'seed' / 'git' / 'config').read_bytes() == b'b'


JUNCTION = SimpleNamespace(st_mode=stat.S_IFDIR, st_nlink=1, st_file_attributes=0x400)


def test_a_junction_above_the_destination_is_refused_before_anything_is_written(
        tmp_path, monkeypatch):
    """`mkdir(root)` and `open(dst, 'xb')` follow a junction ancestor, so the tree landed in
    the junction's target (review R8)."""
    src = source_tree(tmp_path)
    dest = tmp_path / 'link' / 'deep' / 'seed'
    dest.parent.mkdir(parents=True)
    fake_lstat(monkeypatch, tmp_path / 'link', JUNCTION)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError, match='an alias appeared in the destination: an ancestor'):
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert os.listdir(dest.parent) == [] and calls == []


def test_a_junction_above_the_import_source_is_refused(tmp_path, monkeypatch):
    root = source_tree(tmp_path, {'one.txt': b'x'}, name='node')
    fake_lstat(monkeypatch, tmp_path, JUNCTION)
    scan, _ = scan_ok()
    with pytest.raises(seed.SeedError, match='an ancestor'):
        seed.import_back(root, ['one.txt'], tmp_path / 'imported', scan)
    assert not (tmp_path / 'imported').exists()


def test_a_junction_between_the_source_root_and_the_file_is_refused(tmp_path, monkeypatch):
    root = source_tree(tmp_path, {'sub/one.txt': b'x'}, name='node')
    fake_lstat(monkeypatch, root / 'sub', JUNCTION)
    scan, _ = scan_ok()
    with pytest.raises(seed.SeedError, match='an ancestor'):
        seed.import_back(root, ['sub/one.txt'], tmp_path / 'imported', scan)


@pytest.mark.parametrize('kind,token', [
    ('nothing', 'nothing to seed'),
    ('string', 'must be a mapping or a list of pairs'),
])
def test_seed_copy_bad_input(tmp_path, kind, token):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    given = {} if kind == 'nothing' else 'one.txt'
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy(given, dest, scan)
    assert token in str(err.value)
    assert not dest.exists()


@pytest.mark.parametrize('kind,token', [
    ('nothing', 'nothing to seed'),
    ('string', 'files must be a list of relative paths'),
])
def test_import_back_bad_input(tmp_path, kind, token):
    root = source_tree(tmp_path, {'one.txt': b'x'}, name='node')
    dest = tmp_path / 'imported'
    scan, calls = scan_ok()
    given = [] if kind == 'nothing' else 'one.txt'
    with pytest.raises(seed.SeedError) as err:
        seed.import_back(root, given, dest, scan)
    assert token in str(err.value)
    assert not dest.exists()


@pytest.mark.parametrize('call', ['seed_copy', 'import_back', 'recheck'])
@pytest.mark.parametrize('missing', [None, 'not a callable'])
def test_no_scan_given_refused(tmp_path, call, missing):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    with pytest.raises(seed.SeedError) as err:
        if call == 'seed_copy':
            seed.seed_copy({'one.txt': src / 'one.txt'}, dest, missing)
        elif call == 'import_back':
            seed.import_back(src, ['one.txt'], dest, missing)
        else:
            seed.recheck(dest, missing)
    assert 'no scan given' in str(err.value)
    assert not dest.exists()


def test_source_changed_after_planning_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    state = {'flip': False}
    real_sig, real_planned = seed._sig, seed._planned

    def sig(st):
        value = real_sig(st)
        return value[:-1] + (value[-1] + 1,) if state['flip'] else value

    def planned(source_files):
        rows = real_planned(source_files)
        state['flip'] = True
        return rows

    monkeypatch.setattr(seed, '_sig', sig)
    monkeypatch.setattr(seed, '_planned', planned)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'changed while it was seeded' in str(err.value)
    assert not dest.exists()


def test_source_changed_during_the_copy_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    state = {'flip': False}
    real_sig, real_make = seed._sig, seed._make

    def sig(st):
        value = real_sig(st)
        return value[:-1] + (value[-1] + 1,) if state['flip'] else value

    def make(root, rel, made):
        state['flip'] = True
        return real_make(root, rel, made)

    monkeypatch.setattr(seed, '_sig', sig)
    monkeypatch.setattr(seed, '_make', make)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'changed while it was copied' in str(err.value)
    assert not (dest / 'one.txt').exists()


def test_copy_that_differs_from_its_source_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    real_sha = seed._sha

    def sha(path):
        return hashlib.sha256(b'not what was written').hexdigest()

    monkeypatch.setattr(seed, '_sha', sha)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'copy differs from its source: one.txt' in str(err.value)
    assert calls == []


# ── B5: the destination may be a directory Core made and nothing has been put in ──

def made_dest(tmp_path):
    dest = tmp_path / 'workspace'
    dest.mkdir()
    return dest


def test_an_existing_empty_directory_is_seeded_in_place_and_scanned(tmp_path):
    src = source_tree(tmp_path)
    dest = made_dest(tmp_path)
    before = os.stat(dest).st_ino
    scan, calls = scan_ok()
    assert seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan) is dest
    assert os.stat(dest).st_ino == before and calls == [dest]
    for rel, data in CLEAN.items():
        assert (dest / rel).read_bytes() == data


def test_an_existing_empty_directory_takes_an_import_too(tmp_path):
    root = source_tree(tmp_path, {'data/in.json': b'{"a":1}'}, name='node')
    dest = made_dest(tmp_path)
    scan, calls = scan_ok()
    assert seed.import_back(root, ['data/in.json'], dest, scan) is dest
    assert (dest / 'data' / 'in.json').read_bytes() == b'{"a":1}' and calls == [dest]


@pytest.mark.parametrize('present', ['file', 'directory'])
def test_an_existing_directory_with_anything_in_it_is_refused_untouched(tmp_path, present):
    src = source_tree(tmp_path)
    dest = made_dest(tmp_path)
    (dest / 'x').mkdir() if present == 'directory' else (dest / 'x').write_bytes(b'user')
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError, match='already exists and is not empty'):
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert os.listdir(dest) == ['x'] and calls == []


def test_an_existing_destination_that_is_a_file_is_refused(tmp_path):
    src = source_tree(tmp_path)
    scan, calls = scan_ok()
    (tmp_path / 'workspace').write_bytes(b'in the way')
    with pytest.raises(seed.SeedError, match='not the directory expected: .'):
        seed.seed_copy({rel: src / rel for rel in CLEAN}, tmp_path / 'workspace', scan)
    assert (tmp_path / 'workspace').read_bytes() == b'in the way' and calls == []


@pytest.mark.parametrize('kind', ['symlink', 'reparse'])
def test_an_existing_destination_that_is_an_alias_is_refused_before_anything_is_written(
        tmp_path, monkeypatch, kind):
    src = source_tree(tmp_path)
    dest = made_dest(tmp_path)
    fields = (dict(st_mode=stat.S_IFLNK | 0o777, st_nlink=1, st_file_attributes=0)
              if kind == 'symlink' else
              dict(st_mode=stat.S_IFDIR, st_nlink=1, st_file_attributes=0x400))
    fake_lstat(monkeypatch, dest, SimpleNamespace(**fields))
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError, match='an alias appeared in the destination: .'):
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert os.listdir(dest) == [] and calls == []


def test_an_existing_destination_that_cannot_be_listed_is_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = made_dest(tmp_path)
    real = os.scandir

    def scandir(path, *args):
        if _same(path, dest):
            raise PermissionError('denied')
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'scandir', scandir)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError, match='the destination cannot be listed: .'):
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert os.listdir(dest) == [] and calls == []


def test_a_source_that_changed_leaves_an_existing_empty_destination_empty(tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = made_dest(tmp_path)
    real = os.lstat
    seen = {'looks': 0}

    def lstat(path, *args):
        st = real(path, *args)
        if _same(path, src / 'one.txt'):
            seen['looks'] += 1
            if seen['looks'] > 1:
                return SimpleNamespace(st_mode=st.st_mode, st_nlink=1, st_ino=st.st_ino,
                                       st_dev=st.st_dev, st_size=st.st_size + 1,
                                       st_mtime_ns=st.st_mtime_ns, st_file_attributes=0)
        return st

    monkeypatch.setattr(seed.os, 'lstat', lstat)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError, match='changed while it was seeded: one.txt'):
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert os.listdir(dest) == [] and calls == []


def test_a_scan_finding_in_an_existing_destination_keeps_what_was_written(tmp_path):
    src = source_tree(tmp_path)
    dest = made_dest(tmp_path)
    scan, calls = scan_returns(['one.txt'])
    with pytest.raises(seed.SeedError, match='the scan refused: one.txt'):
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert (dest / 'one.txt').read_bytes() == CLEAN['one.txt'] and calls == [dest]


def test_a_second_seed_into_the_filled_directory_is_refused(tmp_path):
    src = source_tree(tmp_path)
    dest = made_dest(tmp_path)
    scan, _ = scan_ok()
    seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    with pytest.raises(seed.SeedError, match='already exists and is not empty'):
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
