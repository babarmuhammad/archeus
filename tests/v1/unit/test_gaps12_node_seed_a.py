"""T-1436: the uncovered branches of `archeus/node/seed.py` lines 46-130 inclusive
(`_fold`, `_under`, `_relative`, `_alias`, `_source`, `_entry`, `_ancestors`, `_list`,
`_sha`, `_read`) at tip 026ea58e. No source file is edited.

Ten selected branches, denial first, then boundaries, then error paths:

1. 54-59 _under: a `..` climb out of the root is refused.
   Catches: the escape test removed.
2. 54-59 _under: a sibling sharing the root's name prefix (`dest2` for `dest`) is refused.
   Catches: the `+ os.sep` suffix dropped from the prefix test.
3. 86-98 _entry: with missing_ok, only FileNotFoundError returns None; PermissionError raises;
   an alias raises before the kind check. Catches: missing_ok widened, or the alias test moved
   after the kind test.
4. 74-83 _source: an lstat OSError, an alias (reparse bit on a regular file) and a directory
   are each refused by name. Catches: any one of the three tests removed.
5. 101-107 _ancestors: each ancestor is checked once, in order, up to the filesystem root;
   a missing ancestor raises; an alias among them raises. Catches: the loop stopping early,
   the root skipped, or missing_ok passed as True.
6. 70-71 _alias: a symlink mode, the reparse bit, and a stat without st_file_attributes are
   classified as the card says. Catches: the S_ISLNK clause or the reparse mask removed.
7. 95-97 _entry kind mismatch: a file asked for as a directory and a directory asked for as a
   file are refused; None accepts either. Catches: the _KINDS lookup or the wanted set inverted.
8. 117-128 _sha and _read: chunked hashing over a file larger than _CHUNK equals the whole-byte
   hash; _read yields chunks no larger than _CHUNK; an empty file hashes to sha256(b'').
   Catches: a chunk loop that drops data or ignores _CHUNK.
9. 110-114 _list: an OSError from scandir raises SeedError naming the rel; success returns a list.
   Catches: the error translation removed, or the list() wrapper dropped.
10. 62-63 _relative and 46-47 _fold: a path under root is a POSIX relative string, the root is
    '.', and names fold through casefold. Catches: the separator replace or the casefold removed.
    On Linux the separator replace is a no-op, so it is only observable on Windows.

Real files under tmp_path for plain files and directories. Aliases are faked through
os.lstat results: seed.os is replaced by a namespace, so the real os module is not patched.
No symlink, junction, git, subprocess or network.
"""

import hashlib
import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import seed


def _fake_os(monkeypatch, **fns):
    monkeypatch.setattr(seed, 'os', SimpleNamespace(path=os.path, sep=os.sep, **fns))


def _denied(path):
    raise PermissionError(13, 'denied', path)


def _link(path):
    return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0,
                           st_ino=1, st_dev=1, st_size=0)


def test_a_climb_out_of_the_root_is_refused(tmp_path):
    root = os.path.abspath(str(tmp_path / 'dest'))
    with pytest.raises(seed.SeedError, match='escapes the destination'):
        seed._under(root, '../outside/a')


def test_a_sibling_sharing_the_root_name_prefix_is_refused(tmp_path):
    root = os.path.abspath(str(tmp_path / 'dest'))
    with pytest.raises(seed.SeedError, match='escapes the destination'):
        seed._under(root, '../dest2/a')
    assert seed._under(root, 'a/b') == os.path.normpath(os.path.join(root, 'a', 'b'))
    assert seed._under(root, '.') == os.path.normpath(root)


def test_missing_ok_forgives_only_a_missing_entry(tmp_path, monkeypatch):
    assert seed._entry(str(tmp_path / 'absent'), 'absent', False, missing_ok=True) is None
    _fake_os(monkeypatch, lstat=_denied)
    with pytest.raises(seed.SeedError, match='cannot be looked at: a'):
        seed._entry(str(tmp_path / 'a'), 'a', False, missing_ok=True)


def test_an_alias_at_the_destination_is_refused_before_its_kind_is_read(tmp_path, monkeypatch):
    _fake_os(monkeypatch, lstat=_link)
    with pytest.raises(seed.SeedError, match='an alias appeared in the destination: f'):
        seed._entry(str(tmp_path / 'f'), 'f', False)


def test_a_source_that_cannot_be_looked_at_is_refused(tmp_path, monkeypatch):
    _fake_os(monkeypatch, lstat=_denied)
    with pytest.raises(seed.SeedError, match='the source cannot be looked at: f'):
        seed._source(str(tmp_path / 'f'), 'f')


def test_a_reparse_point_is_refused_as_an_alias_even_when_it_is_a_regular_file(tmp_path,
                                                                              monkeypatch):
    reparse = SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_file_attributes=0x400,
                              st_ino=1, st_dev=1, st_size=0)
    _fake_os(monkeypatch, lstat=lambda p: reparse)
    with pytest.raises(seed.SeedError, match='an alias, never followed: f'):
        seed._source(str(tmp_path / 'f'), 'f')


def test_a_directory_is_not_a_source(tmp_path):
    (tmp_path / 'd').mkdir()
    with pytest.raises(seed.SeedError, match='not a regular file: d'):
        seed._source(str(tmp_path / 'd'), 'd')


def test_every_ancestor_is_checked_once_in_order_up_to_the_root(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(seed, '_entry',
                        lambda path, rel, is_dir, missing_ok=False: calls.append((path, rel, is_dir)))
    target = str(tmp_path / 'a' / 'b' / 'f')
    seed._ancestors(target)
    expected, p = [], target
    while os.path.dirname(p) != p:
        expected.append(os.path.dirname(p))
        p = os.path.dirname(p)
    assert calls == [(d, 'an ancestor', True) for d in expected]


def test_a_missing_ancestor_is_refused(tmp_path):
    with pytest.raises(seed.SeedError, match='cannot be looked at: an ancestor'):
        seed._ancestors(str(tmp_path / 'missing' / 'f'))


def test_an_alias_among_the_ancestors_is_refused(tmp_path, monkeypatch):
    (tmp_path / 'a' / 'b').mkdir(parents=True)
    alias_path = str(tmp_path / 'a')
    real_lstat = os.lstat
    _fake_os(monkeypatch, lstat=lambda p: _link(p) if p == alias_path else real_lstat(p))
    with pytest.raises(seed.SeedError, match='an alias appeared in the destination: an ancestor'):
        seed._ancestors(str(tmp_path / 'a' / 'b' / 'f'))


def test_alias_is_a_symlink_mode_or_the_reparse_bit_and_nothing_else():
    assert seed._alias(SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_file_attributes=0))
    assert seed._alias(SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_file_attributes=0x400))
    assert not seed._alias(SimpleNamespace(st_mode=stat.S_IFREG | 0o644, st_file_attributes=0x20))
    assert not seed._alias(SimpleNamespace(st_mode=stat.S_IFREG | 0o644))


def test_the_kind_asked_for_must_be_the_kind_found(tmp_path):
    f, d = tmp_path / 'f.txt', tmp_path / 'd'
    f.write_bytes(b'x')
    d.mkdir()
    with pytest.raises(seed.SeedError, match='not the directory expected: f'):
        seed._entry(str(f), 'f', True)
    with pytest.raises(seed.SeedError, match='not the file expected: d'):
        seed._entry(str(d), 'd', False)
    assert seed._entry(str(d), 'd', None) is not None
    assert seed._entry(str(f), 'f', False) is not None


def test_chunked_hashing_and_reading_match_the_whole_bytes(tmp_path, monkeypatch):
    data = b'0123456789abcdefghij'
    p = tmp_path / 'f.bin'
    p.write_bytes(data)
    monkeypatch.setattr(seed, '_CHUNK', 3)
    assert seed._sha(str(p)) == hashlib.sha256(data).hexdigest()
    chunks = list(seed._read(str(p)))
    assert b''.join(chunks) == data
    assert len(chunks) > 1 and all(len(c) <= 3 for c in chunks)


def test_an_empty_file_hashes_to_the_sha256_of_nothing(tmp_path):
    p = tmp_path / 'e'
    p.write_bytes(b'')
    assert seed._sha(str(p)) == hashlib.sha256(b'').hexdigest()
    assert list(seed._read(str(p))) == []


def test_a_listing_failure_is_named_and_a_listing_is_a_list(tmp_path, monkeypatch):
    (tmp_path / 'x').mkdir()
    (tmp_path / 'x' / 'a.txt').write_bytes(b'a')
    listed = seed._list(str(tmp_path / 'x'), 'x')
    assert isinstance(listed, list) and [e.name for e in listed] == ['a.txt']
    _fake_os(monkeypatch, scandir=_denied)
    with pytest.raises(seed.SeedError, match='cannot be listed: x'):
        seed._list(str(tmp_path / 'x'), 'x')


def test_relative_names_are_posix_and_the_root_is_dot(tmp_path):
    root = str(tmp_path)
    assert seed._relative(root, os.path.join(root, 'a', 'b.txt')) == 'a/b.txt'
    assert seed._relative(root, root) == '.'


def test_names_fold_through_casefold_so_case_and_eszett_do_not_separate_them():
    assert seed._fold('README.md') == seed._fold('readme.md')
    assert seed._fold('Straße') == seed._fold('STRASSE')
    assert seed._fold('a.txt') != seed._fold('b.txt')
