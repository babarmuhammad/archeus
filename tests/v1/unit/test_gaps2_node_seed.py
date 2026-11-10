"""T-1020: the guard branches of archeus/node/seed.py lines 1-274 that no other v1 test reaches.

The ranked list of the ten selected branches — each with the branch's file:line, the
closest existing test, the assertion that makes that test miss it, and the test name
below — is in the card report. Ranking is fail-closed and denial first, then boundaries,
then error paths. Nothing here reads the real OS for the thing under test: the calls a
branch needs are faked at the module's own seams (`seed.os.lstat`, `seed.os.scandir`,
`seed.os.mkdir`, `seed._read`), the scan is the fake the test hands in, and the removal
primitives are poisoned, so a branch that fires is proven to fire and a refused tree is
proven to still stand.

Branches, in the order the report ranks them:
  seed.py:90   a destination directory that cannot be looked at while `_make` prepares it
  seed.py:164  a destination subdirectory that cannot be listed, named by its own path
  seed.py:201  an alias above a `seed_copy` source, where there is no source root to check
  seed.py:183  source files that is not a container at all
  seed.py:190  import files that is not a container at all
  seed.py:206  two names that collide only after a non-ASCII case fold
  seed.py:138  an empty source file: the chunk loops that never run
  seed.py:137  a copy that ends up shorter than its source
  seed.py:244  an import refused halfway: what stands, what was made, what never ran
  seed.py:153  a `mkdir` refused for a reason other than the directory already being there
"""

import hashlib
import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import seed, staging

CLEAN = {'one.txt': b'first\n', 'nested/two.bin': b'\x00\xff\xfe\x01binary'}
REMOVALS = ('remove', 'unlink', 'rmdir', 'removedirs', 'replace', 'rename')
JUNCTION = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_nlink=1,
                           st_file_attributes=0x400)


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


def _same(path, target):
    return os.path.normcase(os.path.abspath(os.fspath(path))) == os.path.normcase(str(target))


def fake_lstat(monkeypatch, target, st=None, raises=None):
    real = os.lstat

    def lstat(path, *args):
        if _same(path, target):
            if raises is not None:
                raise raises
            return st
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'lstat', lstat)


def fake_scandir(monkeypatch, target, raises):
    real = os.scandir

    def scandir(path, *args):
        if _same(path, target):
            raise raises
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'scandir', scandir)


def poison_removals(monkeypatch):
    """`SeedError` promises a refused tree stays exactly as it was; a seed that
    tidied up after itself would satisfy every message assertion above."""

    def forbidden(name):
        def gone(*args, **kwargs):
            raise AssertionError('the seeder holds no deletion primitive: %s' % name)
        return gone

    for name in REMOVALS:
        monkeypatch.setattr(seed.os, name, forbidden(name))


# ── fail-closed and denial first ─────────────────────────────────────────────

# ID: t1020.look_denied_while_making covers: a destination subdirectory whose lstat is denied
# while _make is preparing it is refused as that relative path, before it is mkdir'ed
def test_a_denied_look_at_a_subdirectory_being_made_refuses_the_seed(tmp_path, monkeypatch):
    """`_entry` is called with missing_ok=True here, so the one thing it must not do is
    read any OS error as 'not there yet' and go on to create the directory anyway."""
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    fake_lstat(monkeypatch, dest / 'nested', raises=PermissionError('denied'))
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'the destination cannot be looked at: nested' in str(err.value)
    assert isinstance(err.value.__cause__, PermissionError)
    assert calls == []                                  # the scan is never reached
    assert (dest / 'one.txt').read_bytes() == CLEAN['one.txt']   # the row already copied stands
    assert not (dest / 'nested').exists()               # the refused directory was never made
    assert sorted(os.listdir(dest)) == ['one.txt']


# ID: t1020.nested_listing_names_itself covers: a destination subdirectory that cannot be
# listed is refused by its own relative path, not by the root, and the scan never runs
def test_a_subdirectory_that_cannot_be_listed_is_named_by_its_own_path(tmp_path, monkeypatch):
    """The walk's `_list` is given the relative name of the directory it is opening; a
    refusal that named '.' instead would send a human to the wrong half of the tree."""
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    fake_scandir(monkeypatch, dest / 'nested', PermissionError('denied'))
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert 'the destination cannot be listed: nested' in str(err.value)
    assert isinstance(err.value.__cause__, PermissionError)
    assert calls == []
    assert (dest / 'one.txt').read_bytes() == CLEAN['one.txt']
    assert (dest / 'nested' / 'two.bin').read_bytes() == CLEAN['nested/two.bin']


# ID: t1020.junction_above_a_seeded_source covers: an alias above a seed_copy source is
# refused before anything is written, with no source root in play
def test_a_junction_above_a_seeded_source_is_refused_before_anything_is_written(
        tmp_path, monkeypatch):
    """`seed_copy` has no source root, so the ancestor walk of `_rows` is the only check
    between a workspace and a source that is a junction's target: `open(dst, 'xb')`
    would follow it and the tree would land wherever the junction points."""
    src = source_tree(tmp_path, {'sub/one.txt': b'data\n'})
    fake_lstat(monkeypatch, src / 'sub', st=JUNCTION)
    dest = tmp_path / 'seed'
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'sub/one.txt': src / 'sub' / 'one.txt'}, dest, scan)
    assert 'an alias appeared in the destination: an ancestor' in str(err.value)
    assert not dest.exists()
    assert calls == []


# ID: t1020.source_files_not_a_container covers: source files that is neither a mapping,
# a list of pairs, a string nor a bytes is refused as a bad shape, not as a TypeError
@pytest.mark.parametrize('given', [42, object(), 3.5])
def test_source_files_that_is_not_a_container_is_refused(tmp_path, given):
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy(given, dest, scan)
    assert 'source files must be a mapping or a list of pairs' in str(err.value)
    assert not dest.exists()
    assert calls == []


# ID: t1020.import_files_not_a_container covers: import files that is not iterable is
# refused as a bad shape by `_pairs`, before the source root is walked
@pytest.mark.parametrize('given', [42, object()])
def test_import_files_that_is_not_a_container_is_refused(tmp_path, given):
    root = source_tree(tmp_path, {'one.txt': b'x\n'}, name='node')
    dest = tmp_path / 'imported'
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.import_back(root, given, dest, scan)
    assert 'files must be a list of relative paths' in str(err.value)
    assert not dest.exists()
    assert calls == []


# ── boundaries ───────────────────────────────────────────────────────────────

# ID: t1020.unicode_fold_duplicate covers: two destination names that are equal only
# after casefolding (an ASCII look-alike) are refused as the same destination twice
def test_names_that_collide_only_after_a_unicode_fold_are_refused(tmp_path):
    """'ſ' (U+017F) casefolds to 's', so those two names are one file to the second
    `open(dst, 'xb')`. The names never reach the filesystem: the sources are ordinary
    files, so this tests the fold, not a platform's case-insensitive directory."""
    src = source_tree(tmp_path, {'one.txt': b'long s\n', 'two.txt': b'long s again\n'})
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'ſ.txt': src / 'one.txt', 's.txt': src / 'two.txt'}, dest, scan)
    assert 'the same destination twice: s.txt' in str(err.value)
    assert not dest.exists()
    assert calls == []


# ID: t1020.empty_source_copied covers: an empty source file is written as an empty file,
# through the chunk loops of `_read`, `_copy` and `_sha` that never run once
def test_an_empty_source_is_written_as_an_empty_file_and_scanned(tmp_path):
    src = source_tree(tmp_path, {'empty.bin': b'', 'one.txt': b'not empty\n'})
    dest = tmp_path / 'seed'
    scan, calls = scan_ok()
    assert seed.seed_copy({'empty.bin': src / 'empty.bin', 'one.txt': src / 'one.txt'},
                          dest, scan) is dest
    assert calls == [dest]
    assert (dest / 'empty.bin').read_bytes() == b''
    assert hashlib.sha256((dest / 'empty.bin').read_bytes()).hexdigest() \
        == hashlib.sha256(b'').hexdigest()
    assert (dest / 'one.txt').read_bytes() == b'not empty\n'


# ID: t1020.short_copy_refused covers: a copy that ends up shorter than the source it was
# planned from is refused by its size; the digest is of what was read, so it cannot notice
def test_a_copy_shorter_than_its_source_is_refused(tmp_path, monkeypatch):
    src = source_tree(tmp_path, {'one.txt': b'twenty bytes here\n'})
    dest = tmp_path / 'seed'

    def short_read(path):
        """What a source that loses its tail mid-copy does to a plain chunked read:
        `f.read` answers fewer bytes than the size the row was planned with, and the
        loop simply ends."""
        with open(path, 'rb') as f:
            yield f.read(4)

    monkeypatch.setattr(seed, '_read', short_read)
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'copy differs from its source: one.txt' in str(err.value)
    assert calls == []
    assert (src / 'one.txt').read_bytes() == b'twenty bytes here\n'   # the source untouched
    assert (dest / 'one.txt').read_bytes() == b'twen'   # the short write stands, nothing removed


# ── error paths ──────────────────────────────────────────────────────────────

# ID: t1020.import_refused_halfway covers: an import refused on its second row keeps the
# file already copied, keeps the directory made for the refused row and never scans
def test_an_import_refused_halfway_keeps_the_file_already_copied(tmp_path, monkeypatch):
    """The partial-import state: nothing is removed, the scan never runs, and the tree
    that stands is exactly the tree the copy had reached."""
    root = source_tree(tmp_path, {'a/one.txt': b'kept\n', 'b/two.txt': b'lost\n'}, name='node')
    dest = tmp_path / 'imported'
    state = {'makes': 0}
    real_sig, real_make = seed._sig, seed._make

    def sig(st):
        value = real_sig(st)
        return value[:-1] + (value[-1] + 1,) if state['makes'] >= 2 else value

    def make(root_, rel, made):
        state['makes'] += 1
        return real_make(root_, rel, made)

    monkeypatch.setattr(seed, '_sig', sig)
    monkeypatch.setattr(seed, '_make', make)
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.import_back(root, ['a/one.txt', 'b/two.txt'], dest, scan)
    assert 'changed while it was copied: b/two.txt' in str(err.value)
    assert (dest / 'a' / 'one.txt').read_bytes() == b'kept\n'   # the row already copied stands
    assert os.path.isdir(dest / 'b')             # _make runs before the row is re-checked
    assert sorted(os.listdir(dest)) == ['a', 'b']
    assert calls == []


# ID: t1020.mkdir_denied_names_no_path covers: a mkdir inside the destination refused for a
# reason other than the directory existing leaves seed as the OS error it is (seed.py:153-156
# wraps only FileExistsError), and staging, seed's one caller, answers it without the OS text
def test_a_denied_mkdir_reaches_the_caller_of_staging_without_its_absolute_path(
        tmp_path, monkeypatch):
    src = source_tree(tmp_path)
    dest = tmp_path / 'seed'
    real_mkdir = os.mkdir

    def mkdir(path, *args):
        if os.path.basename(path) == 'nested':
            raise PermissionError('denied: %s' % path)
        return real_mkdir(path, *args)

    monkeypatch.setattr(seed.os, 'mkdir', mkdir)
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(PermissionError):
        seed.seed_copy({rel: src / rel for rel in CLEAN}, dest, scan)
    assert calls == []
    assert (dest / 'one.txt').read_bytes() == CLEAN['one.txt']   # the row already copied stands
    with pytest.raises(staging.StageError) as err:
        staging.seed_execution({rel: src / rel for rel in CLEAN}, tmp_path / 'staged')
    assert os.path.abspath(str(tmp_path)) not in str(err.value)
    assert isinstance(err.value.__cause__, PermissionError)
    assert not (tmp_path / 'staged' / 'nested').exists()
