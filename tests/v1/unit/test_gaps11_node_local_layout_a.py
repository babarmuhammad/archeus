"""T-1415: the uncovered branches of `archeus/node/local.py` lines 2184-2298 inclusive
(`_objects_plain`, `_git_dir_of`, `_named_dirs`, `_plain`, `_layout`, the start of
`_pin_record`) at tip 6a32dc14 (re-located at 81d83030). No source file is edited.

Ten selected branches, denial and fail-closed first, then boundaries, then error paths:

1. 2222-2223 _git_dir_of: a .git file not starting with 'gitdir: ' or over _GITFILE_MAX is refused.
   Catches: the prefix test or the size test removed.
2. 2229-2231 _git_dir_of: an empty path, a NUL, CR or LF, or leading or trailing blanks is refused;
   invalid UTF-8 is refused. Catches: any one of those tests removed.
3. 2230 _git_dir_of on Windows rules (os.name 'nt'): a root-relative '\\foo' is refused, 'foo' and
   'C:\\x' accepted; a drive-relative 'C:foo' is refused on Windows only (its path form needs
   the Windows drive split). Catches: the os.name clause or the drive/root test inverted.
4. 2216, 2232 _git_dir_of: no .git returns root; a valid 'gitdir: rel' returns os.path.join(root, rel).
   Catches: the no-.git early return, or the join dropped.
5. 2244-2250 _named_dirs: a commondir with two lines, a '#' or '"' line, a CR, a non-directory,
   an unreadable file or non-UTF-8 bytes is refused. Catches: any one of those tests removed.
6. 2245 _named_dirs with one=False: blank lines skipped; an absolute line ignores base and is accepted.
   Catches: the blank filter removed, or base forced onto absolute names.
7. 2257-2258 _plain: a regular file with st_nlink > 1 is refused; a directory with a subdirectory
   is not refused by this check. Catches: the nlink test widened to directories.
8. 2282-2285 _layout: a non-empty hooks directory is refused naming the store; an empty one passes.
   Catches: the emptiness test inverted, or the hooks check removed.
9. 2286-2289 _layout: info/attributes, objects/info/alternates, commondir or config.worktree in the
   store is refused with its rel path named; a fresh empty store passes.
   Catches: any one of those rel names removed from the tuple.
10. 2195-2202 _objects_plain: a *.promisor file or http-alternates under objects/info or objects/pack
    (also nested) is refused; a plain objects/info/alternates is accepted here because the source walk
    (local.py:2178) follows it on purpose, with depth and outside-execution checks. No strict xfail:
    the caller reads it and the code refuses what Core cannot resolve.

Closest existing tests: tests/v1/unit/test_gaps_node_local_a.py, test_gaps_node_local_b.py,
test_gaps5_node_local.py and test_node_local_staging_gaps.py mention the module; none names these
helpers (round 14 grep). Real files under tmp_path only. No symlinks, junctions or real git.
"""

import os
import re
import sys

import pytest

from archeus.node import local as L


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# 1-2, 4: _git_dir_of
def test_git_dir_of_refuses_a_gitfile_that_does_not_start_with_the_prefix(tmp_path):
    _write(tmp_path / '.git', b'not gitdir: x')
    with pytest.raises(L.StoreError):
        L._git_dir_of(str(tmp_path))


def test_git_dir_of_refuses_a_gitfile_over_the_size_limit(tmp_path):
    _write(tmp_path / '.git', b'gitdir: ' + b'a' * L._GITFILE_MAX)
    with pytest.raises(L.StoreError):
        L._git_dir_of(str(tmp_path))


@pytest.mark.parametrize('data', [
    b'gitdir: \n',
    b'gitdir: a\x00b',
    b'gitdir: a\rb',
    b'gitdir:  x',
    b'gitdir: x  ',
    b'gitdir: \xff',
])
def test_git_dir_of_refuses_a_path_core_cannot_match_exactly(tmp_path, data):
    _write(tmp_path / '.git', data)
    with pytest.raises(L.StoreError):
        L._git_dir_of(str(tmp_path))


def test_git_dir_of_returns_root_without_a_gitfile_and_the_dot_git_directory_itself(tmp_path):
    assert L._git_dir_of(str(tmp_path)) == str(tmp_path)
    (tmp_path / '.git').mkdir()
    assert L._git_dir_of(str(tmp_path)) == os.path.join(str(tmp_path), '.git')


def test_git_dir_of_joins_a_relative_gitdir_against_the_root(tmp_path):
    (tmp_path / 'real').mkdir()
    _write(tmp_path / '.git', b'gitdir: real\n')
    assert L._git_dir_of(str(tmp_path)) == os.path.join(str(tmp_path), 'real')


# 3: _git_dir_of Windows-only path rules, the nt branch
def test_git_dir_of_on_nt_refuses_a_root_relative_path_and_accepts_plain_and_drive_paths(
        tmp_path, monkeypatch):
    monkeypatch.setattr(os, 'name', 'nt')
    _write(tmp_path / '.git', b'gitdir: \\foo')
    with pytest.raises(L.StoreError):
        L._git_dir_of(str(tmp_path))
    _write(tmp_path / '.git', b'gitdir: foo')
    assert L._git_dir_of(str(tmp_path)) == os.path.join(str(tmp_path), 'foo')
    _write(tmp_path / '.git', b'gitdir: C:\\x')
    assert L._git_dir_of(str(tmp_path)) == os.path.join(str(tmp_path), 'C:\\x')


@pytest.mark.skipif(sys.platform != 'win32',
                    reason="a drive-relative path is only split into a drive by Windows path rules")
def test_git_dir_of_refuses_a_drive_relative_path_on_windows(tmp_path):
    _write(tmp_path / '.git', b'gitdir: C:foo')
    with pytest.raises(L.StoreError):
        L._git_dir_of(str(tmp_path))


# 5-6: _named_dirs
@pytest.fixture
def dirs(tmp_path):
    for n in ('one', 'two'):
        (tmp_path / n).mkdir()
    return tmp_path


@pytest.mark.parametrize('text', [b'one\ntwo', b'#one', b'"one"', b'\xff', b'missing', b'file'])
def test_named_dirs_refuses_an_indirection_it_cannot_resolve(dirs, text):
    _write(dirs / 'file', b'x')
    path = _write(dirs / 'commondir', text)
    with pytest.raises(L.StoreError):
        L._named_dirs(str(path), str(dirs), one=True)


@pytest.mark.parametrize('text', [b'#one\n', b'"one"\n', b'one\r\n', b'one\n\r'])
def test_named_dirs_refuses_a_comment_quote_or_carriage_return_line(dirs, text):
    path = _write(dirs / 'alternates', text)
    with pytest.raises(L.StoreError):
        L._named_dirs(str(path), str(dirs))


def test_named_dirs_refuses_an_unreadable_file(dirs):
    with pytest.raises(L.StoreError):
        L._named_dirs(str(dirs / 'nope'), str(dirs))


def test_named_dirs_skips_blank_lines_and_keeps_an_absolute_line_as_written(dirs, tmp_path):
    other = tmp_path / 'elsewhere'
    other.mkdir()
    path = _write(dirs / 'alternates', b'one\n\ntwo\n' + str(other).encode() + b'\n')
    assert L._named_dirs(str(path), str(dirs)) == [
        os.path.join(str(dirs), 'one'), os.path.join(str(dirs), 'two'), str(other)]


def test_named_dirs_one_resolves_a_single_relative_line(dirs):
    path = _write(dirs / 'commondir', b'two\n')
    assert L._named_dirs(str(path), str(dirs), one=True) == [os.path.join(str(dirs), 'two')]


# 7: _plain hard links
def test_plain_refuses_a_regular_file_with_a_second_hard_link(tmp_path):
    f = _write(tmp_path / 'a', b'x')
    os.link(f, tmp_path / 'b')
    with pytest.raises(L.StoreError):
        L._plain(str(f), False)


def test_plain_does_not_refuse_a_directory_with_several_links(tmp_path):
    d = tmp_path / 'dir'
    (d / 'sub').mkdir(parents=True)
    assert L._plain(str(d), True) is not None


# 8-9: _layout
def _store(tmp_path):
    owned = _write(tmp_path / 'owned', b'claim')
    store = tmp_path / 'store'
    (store / 'objects').mkdir(parents=True)
    (store / 'refs').mkdir()
    _write(store / 'config', b'[core]\n')
    _write(store / 'HEAD', b'ref: refs/heads/main\n')
    return str(owned), str(store)


def test_layout_passes_a_fresh_empty_store(tmp_path):
    owned, store = _store(tmp_path)
    L._layout(store, owned)


def test_layout_refuses_a_store_with_hooks_and_passes_an_empty_hooks_directory(tmp_path):
    owned, store = _store(tmp_path)
    (tmp_path / 'store' / 'hooks').mkdir()
    L._layout(store, owned)
    _write(tmp_path / 'store' / 'hooks' / 'pre-push', b'#!/bin/sh\n')
    with pytest.raises(L.StoreError, match=re.escape('a store with hooks')):
        L._layout(store, owned)


@pytest.mark.parametrize('rel', [
    ('info', 'attributes'),
    ('objects', 'info', 'alternates'),
    ('commondir',),
    ('config.worktree',),
])
def test_layout_refuses_a_metadata_entry_git_would_resolve(tmp_path, rel):
    owned, store = _store(tmp_path)
    _write(tmp_path / 'store' / os.path.join(*rel), b'x')
    with pytest.raises(L.StoreError, match=re.escape('/'.join(rel))):
        L._layout(store, owned)


# 10: _objects_plain
@pytest.mark.parametrize('rel', [
    ('pack', 'pack-1.promisor'),
    ('pack', 'nested', 'pack-2.promisor'),
    ('info', 'http-alternates'),
])
def test_objects_plain_refuses_a_promisor_pack_or_http_alternates(tmp_path, rel):
    objects = tmp_path / 'objects'
    _write(objects.joinpath(*rel), b'x')
    with pytest.raises(L.StoreError):
        L._objects_plain(str(objects))


def test_objects_plain_accepts_a_plain_alternates_file_because_the_source_walk_follows_it(
        tmp_path):
    objects = tmp_path / 'objects'
    _write(objects / 'info' / 'alternates', b'other/objects\n')
    L._objects_plain(str(objects))
