"""T-1129: the highest-risk uncovered branches of archeus/node/seed.py lines 1-276.

The ten branches below are the ones no other v1 test reaches at HEAD 56d53504
(checked against `test_seed.py`, `test_gaps2_node_seed.py`, `test_pins_node_seed.py`,
`test_staging_seed.py`, `test_mxc_wire_seed.py` and a search of every test that names
`seed_copy`, `import_back`, `recheck`, `_copy`, `_sha` or `_read`); ranking is
fail-closed and denial first, then boundaries, then error paths, then a concurrency
ordering. The copied-byte fidelity check of 0ab756e1 (`seed.py:141-142` and
`seed.py:250-251`) is the changed range this card owns; the card authorizes overlap
with round 2 exactly for those branches and their direct interactions. Nothing here
reads the real OS for the thing under test: an alias is a faked `os.lstat` returning a
reparse `st_file_attributes` and never a real symlink, a denied read is a narrow
`open` fake aimed at one path, a short or grown copy is forced through the module's
own seams (`seed._read`, `seed._copy`, `seed._sha`), the one race is forced with
`threading.Event` handshakes and bounded waits (never a sleep), the scan is the fake
the test hands in, and the removal primitives are poisoned, so a refused tree that
still stands is proven, not assumed. Every file lives under `tmp_path`.

Branches, in the order the report ranks them (file:line at HEAD 56d53504):
  seed.py:141-142  a destination tampered to an equal length after the write fails the
                   digest, and only the digest, can see it
  seed.py:250-251  a copy that wrote no bytes at all from a nonempty source is refused
                   although the copy's own digest matched itself
  seed.py:250-251  a destination that grew after the copy fails the size check, the
                   copy's own digest having passed
  seed.py:243-253  a fidelity failure on a later row never admits the tree to the walk
                   or to the scan
  seed.py:141-142  the same fidelity refusal guards `import_back`, and an unlisted
                   source file is never touched
  seed.py:166      a copied leaf that shows reparse bits during the walk is refused
                   there, its row check having passed as a plain file
  seed.py:126,138  a source whose read is denied never reports success and never
                   reaches the walk or the scan
  seed.py:119,141  a denied re-read of the destination under the fidelity check must
                   be a SeedError with the partial write standing (strict xfail)
  seed.py:92       a denied lstat of the copied leaf is refused by its relative path,
                   cause attached, the written bytes standing
  seed.py:246-251  a source that grew after its pre-copy signature check is never
                   admitted as a faithful original (forced with Events, no sleeps)
"""

import hashlib
import os
import stat
import threading
from types import SimpleNamespace

import pytest

from archeus.node import seed

REMOVALS = ('remove', 'unlink', 'rmdir', 'removedirs', 'replace', 'rename')


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


def _same(path, target):
    return os.path.normcase(os.path.abspath(os.fspath(path))) == os.path.normcase(str(target))


def poison_removals(monkeypatch):
    """`SeedError` promises a refused tree stays exactly as it was; a seeder that
    tidied up after a refusal would satisfy every message assertion above."""

    def forbidden(name):
        def gone(*args, **kwargs):
            raise AssertionError('the seeder holds no deletion primitive: %s' % name)
        return gone

    for name in REMOVALS:
        monkeypatch.setattr(seed.os, name, forbidden(name))


def instrument(monkeypatch, name):
    """Record every call the module makes to its own seam *name*, still running it."""
    calls = []
    real = getattr(seed, name)

    def spy(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(seed, name, spy)
    return calls


def recording_sha(monkeypatch, tamper=None):
    """The real `_sha`, counted, with an optional one-shot tamper of the file about to
    be hashed: the comparison stays a genuine digest of what is on disk."""
    seen = []
    real_sha = seed._sha

    def sha(path):
        if tamper is not None:
            tamper(path)
        digest = real_sha(path)
        seen.append((os.fspath(path), digest))
        return digest

    monkeypatch.setattr(seed, '_sha', sha)
    return seen


# ── fail-closed and denial first ────────────────────────────────

# ID: t1129.equal_length_digest covers: a destination tampered to the SAME LENGTH
# between the write and the fidelity digest is refused by seed.py:141-142, and only the
# digest (not the size check of seed.py:250-251) can see this input
def test_a_destination_tampered_to_an_equal_length_is_refused_by_the_digest(tmp_path, monkeypatch):
    """The bytes written were faithful, then a same-user writer rewrote the destination
    with different bytes of the same length before the re-hash. The closest existing
    test, `test_copy_that_differs_from_its_source_refused`, replaces `_sha` wholesale
    with a constant wrong digest, so it cannot tell a check that hashes the destination
    from one that hashes the (intact) source: here the source is intact, the digest is
    real, and a refused seed is the only acceptable answer."""
    src = source_tree(tmp_path, {'one.txt': b'first\n'})
    dest = tmp_path / 'seed'

    def tamper(path):
        if _same(path, dest / 'one.txt'):
            with open(dest / 'one.txt', 'wb') as f:
                f.write(b'LASP\n!')          # six bytes again, none of them faithful

    seen = recording_sha(monkeypatch, tamper)
    walked = instrument(monkeypatch, '_verify_tree')
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'copy differs from its source: one.txt' in str(err.value)
    assert calls == [] and walked == []
    assert len(seen) == 1 and _same(seen[0][0], dest / 'one.txt')  # it hashed the destination
    assert (dest / 'one.txt').read_bytes() == b'LASP\n!'           # the tampered bytes stand
    assert (src / 'one.txt').read_bytes() == b'first\n'            # the source was never touched


# ID: t1129.zero_byte_copy covers: a copy that wrote NO bytes from a nonempty source is
# refused by the size check of seed.py:250-251 although the digest of the copy matched
# itself exactly (the fx20 zero-length neighbour of the short-copy regression)
def test_a_copy_that_wrote_no_bytes_from_a_nonempty_source_is_refused(tmp_path, monkeypatch):
    """`test_a_copy_shorter_than_its_source_is_refused` fakes a read that yields a
    partial head of the file; it passes even if the size check learns to accept an
    empty write ('nothing is the same as nothing'). Here the read yields nothing at
    all, so `_copy`'s digest compares an empty hash with an empty file and passes:
    only the planned-size comparison can refuse it."""
    src = source_tree(tmp_path, {'one.txt': b'twenty bytes here\n'})
    dest = tmp_path / 'seed'
    monkeypatch.setattr(seed, '_read', lambda path: iter(()))
    seen = recording_sha(monkeypatch)
    walked = instrument(monkeypatch, '_verify_tree')
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'copy differs from its source: one.txt' in str(err.value)
    assert calls == [] and walked == []
    assert len(seen) == 1 and seen[0][1] == hashlib.sha256(b'').hexdigest()
    assert (dest / 'one.txt').read_bytes() == b''                  # the empty write stands
    assert (src / 'one.txt').read_bytes() == b'twenty bytes here\n'


# ID: t1129.grown_destination covers: a destination that GROWS after the copy, digest
# already passed, is refused by the same size comparison of seed.py:250-251 (the other
# side of the boundary: st_size greater than the planned size, not smaller)
def test_a_destination_that_grew_after_the_copy_fails_the_fidelity_check(tmp_path, monkeypatch):
    """A same-user writer appends to the file between `_copy` returning and the row's
    size check. No existing test grows a destination:
    `test_a_copy_shorter_than_its_source_is_refused` only shrinks one, and the pins
    tests never arm the size comparison at all."""
    src = source_tree(tmp_path, {'one.txt': b'first\n'})
    dest = tmp_path / 'seed'
    seen = recording_sha(monkeypatch)
    real_copy = seed._copy

    def copy(source, dst, rel):
        real_copy(source, dst, rel)                               # faithful: digest passed
        with open(dst, 'ab') as f:
            f.write(b' grown after')

    monkeypatch.setattr(seed, '_copy', copy)
    walked = instrument(monkeypatch, '_verify_tree')
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'copy differs from its source: one.txt' in str(err.value)
    assert len(seen) == 1                                          # the digest had already passed
    assert calls == [] and walked == []
    assert (dest / 'one.txt').read_bytes() == b'first\n grown after'  # it stands, nothing removed


# ID: t1129.second_row_never_scanned covers: seed.py:243-253 as an ordering, a fidelity
# failure on the SECOND row must stop the walk AND the scan, so no unverified tree is
# ever admitted by the operator's scan
def test_a_fidelity_failure_on_the_second_row_never_admits_the_tree_to_the_scan(
        tmp_path, monkeypatch):
    """`test_an_import_refused_halfway_keeps_the_file_already_copied` refuses its second
    row at the signature check and `test_the_walk_of_a_seeded_tree_runs_before_the_scan`
    arms the walk, not the fidelity check; neither proves that a fidelity refusal also
    keeps the walk and the scan from running over a half-copied tree."""
    src = source_tree(tmp_path, {'one.txt': b'kept\n', 'two.txt': b'lost tail\n'})
    dest = tmp_path / 'seed'
    real_read = seed._read

    def read(path):
        if _same(path, src / 'two.txt'):
            return iter(())                                        # the second copy ends empty
        return real_read(path)

    monkeypatch.setattr(seed, '_read', read)
    walked = instrument(monkeypatch, '_verify_tree')
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt', 'two.txt': src / 'two.txt'}, dest, scan)
    assert 'copy differs from its source: two.txt' in str(err.value)
    assert 'kept' not in str(err.value)
    assert calls == [] and walked == []                            # no unverified tree is scanned
    assert (dest / 'one.txt').read_bytes() == b'kept\n'             # the row already copied stands
    assert (dest / 'two.txt').read_bytes() == b''
    assert sorted(os.listdir(dest)) == ['one.txt', 'two.txt']


# ID: t1129.import_shares_fidelity covers: the fidelity digest of seed.py:141-142 on the
# import_back path (not just seed_copy), with the unlisted source file proven untouched
def test_import_back_shares_the_fidelity_refusal_and_never_touches_the_unlisted_source(
        tmp_path, monkeypatch):
    """The import is the data-only way back; it shares `_seed` and must share its
    refusal. No import test arms the fidelity check: the existing import refusals use
    an occupied destination, an escaping name, an aliased source or a changed source."""
    root = source_tree(tmp_path, {'data/in.json': b'{"a":1}\n',
                                  'data/keep.json': b'{"keep":1}\n'}, name='node')
    dest = tmp_path / 'imported'
    before = {rel: (root / rel).read_bytes() for rel in ('data/in.json', 'data/keep.json')}

    def tamper(path):
        if _same(path, dest / 'data' / 'in.json'):
            (dest / 'data' / 'in.json').write_bytes(b'{"b":2}\n')  # eight bytes again

    seen = recording_sha(monkeypatch, tamper)
    walked = instrument(monkeypatch, '_verify_tree')
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.import_back(root, ['data/in.json'], dest, scan)
    assert 'copy differs from its source: data/in.json' in str(err.value)
    assert calls == [] and walked == []
    assert len(seen) == 1 and _same(seen[0][0], dest / 'data' / 'in.json')
    for rel, blob in before.items():          # the source tree was not written
        assert (root / rel).read_bytes() == blob
    assert (dest / 'data' / 'in.json').read_bytes() == b'{"b":2}\n'  # the partial write stands


# ID: t1129.leaf_alias_in_the_walk covers: seed.py:166 refusing a copied LEAF whose
# lstat answers reparse bits during the walk, its row check at seed.py:250 having seen
# a plain file; faked metadata only, never a real symlink
def test_a_copied_leaf_that_shows_reparse_bits_during_the_walk_is_refused(tmp_path, monkeypatch):
    """`test_destination_alias_refused` lies to every look, so the row check fires and
    the walk never runs; `test_alias_in_a_nested_directory_is_found_by_the_walk` fakes a
    directory, not a leaf, and `test_recheck_catches_an_alias_made_after_the_seed` fakes
    the recheck of a finished seed. Only this sequence proves the row check really
    looked (and passed) before the walk is the one that refuses."""
    src = source_tree(tmp_path, {'one.txt': b'first\n'})
    dest = tmp_path / 'seed'
    real = os.lstat
    looks = []

    def lstat(path, *args):
        if _same(path, dest / 'one.txt'):
            looks.append(1)
            if len(looks) > 1:
                return SimpleNamespace(st_mode=stat.S_IFREG, st_nlink=1, st_size=6,
                                       st_file_attributes=0x400)
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'lstat', lstat)
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'an alias appeared in the destination: one.txt' in str(err.value)
    assert len(looks) == 2          # passed the row check, refused by the walk
    assert calls == []
    assert (dest / 'one.txt').read_bytes() == b'first\n'    # the tree stands for a human


# ── error paths ────────────────────────────────────────────────

# ID: t1129.source_read_denied covers: seed.py:126/138, a source whose read is denied
# mid-copy never reports success and never reaches the walk or the scan
def test_a_source_that_cannot_be_read_never_reports_success_or_reaches_the_scan(
        tmp_path, monkeypatch):
    """The lstat refusals are wrapped by `_source`; the read refusals are not wrapped
    anywhere, so what the contract owes here is the ABSENCE of success and of the scan,
    not a particular wrapper type: the error that surfaces must still be the denied
    read itself (raw, or a SeedError carrying it as its cause), never a swallowed pass."""
    src = source_tree(tmp_path, {'one.txt': b'first\n'})
    dest = tmp_path / 'seed'
    real_open = open

    def fake_open(file, mode='r', *args, **kwargs):
        if mode == 'rb' and _same(file, src / 'one.txt'):
            raise PermissionError('denied')
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr('builtins.open', fake_open)
    walked = instrument(monkeypatch, '_verify_tree')
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(OSError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    raised = err.value
    assert isinstance(raised, PermissionError) or (
        isinstance(raised, seed.SeedError) and isinstance(raised.__cause__, PermissionError))
    assert calls == [] and walked == []
    assert (dest / 'one.txt').read_bytes() == b''                   # the partial write stands
    assert (src / 'one.txt').read_bytes() == b'first\n'


# ID: t1129.destination_rehash_denied covers: seed.py:119/141, a denied re-read of the
# destination UNDER the fidelity check must be the typed refusal, with the partial
# write standing and the relative path named
@pytest.mark.xfail(strict=True, reason=(
    'specific defect: seed.py:141 calls _sha(dst), whose open at seed.py:119 is not '
    'wrapped, so a denied re-read escapes as the raw PermissionError instead of a '
    'SeedError, unlike _source/_entry/_list which wrap their OS failures; the fidelity '
    'check cannot observe the bytes and must fail closed as a typed refusal'))
def test_a_denied_re_read_of_the_destination_is_a_seederror_with_the_partial_write_standing(
        tmp_path, monkeypatch):
    src = source_tree(tmp_path, {'one.txt': b'first\n'})
    dest = tmp_path / 'seed'
    real_open = open

    def fake_open(file, mode='r', *args, **kwargs):
        if mode == 'rb' and _same(file, dest / 'one.txt'):
            raise PermissionError('denied')
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr('builtins.open', fake_open)
    walked = instrument(monkeypatch, '_verify_tree')
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    raised = None
    try:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    except BaseException as exc:                                    # noqa: BLE001
        raised = exc
    assert (dest / 'one.txt').read_bytes() == b'first\n'             # the partial write stands
    assert (src / 'one.txt').read_bytes() == b'first\n'
    assert calls == [] and walked == []
    assert isinstance(raised, seed.SeedError), 'a denied fidelity re-read must fail closed typed'
    assert isinstance(raised.__cause__, PermissionError)
    assert 'one.txt' in str(raised.value) and str(dest) not in str(raised.value)


# ID: t1129.leaf_stat_denied covers: seed.py:92, a denied lstat of the copied leaf at
# the row's size check is refused by the relative path with the cause attached, the
# written bytes standing (the stat half of the same refusal the digest guards)
def test_a_denied_stat_of_the_copied_leaf_is_refused_by_its_relative_path(tmp_path, monkeypatch):
    """`test_written_file_that_vanished_refused` is the FileNotFoundError of this same
    call and the gaps2 look-denial test is the missing_ok=True directory; a Permission
    Error on a file that IS there must not read as anything but a refusal, and the
    message may name only the relative path."""
    src = source_tree(tmp_path, {'one.txt': b'first\n'})
    dest = tmp_path / 'seed'
    real = os.lstat

    def lstat(path, *args):
        if _same(path, dest / 'one.txt'):
            raise PermissionError('denied')
        return real(path, *args)

    monkeypatch.setattr(seed.os, 'lstat', lstat)
    walked = instrument(monkeypatch, '_verify_tree')
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    with pytest.raises(seed.SeedError) as err:
        seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
    assert 'the destination cannot be looked at: one.txt' in str(err.value)
    assert str(dest) not in str(err.value)
    assert isinstance(err.value.__cause__, PermissionError)
    assert calls == [] and walked == []
    assert (dest / 'one.txt').read_bytes() == b'first\n'             # the write stands


# ── concurrency ordering, forced with Events and bounded waits, never a sleep ──

# ID: t1129.source_grew_after_the_check covers: seed.py:246-251 under a forced
# interleaving, a source that grew after its pre-copy signature check and before the
# read is caught by the planned-size comparison, never admitted as a faithful original
def test_a_source_that_grew_after_the_pre_copy_check_is_never_admitted_as_faithful(
        tmp_path, monkeypatch):
    """The signature check and the copy are not atomic (the module says so); what IS
    owed is that the grown bytes cannot pass as the planned file. The interleaving is
    forced with two Events: the copy seam only starts the writer, and only after the
    writer has appended and answered does the real copy read, so the digest of the
    copy matches the grown bytes and only the size check can refuse."""
    src = source_tree(tmp_path, {'one.txt': b'twelve bytes\n'})
    dest = tmp_path / 'seed'
    grown = b'twelve bytes\ngrown tail\n'
    go = threading.Event()
    done = threading.Event()
    real_copy = seed._copy

    def copy(source, dst, rel):
        go.set()                                                    # the row passed its check
        assert done.wait(5), 'the writer thread never answered'
        return real_copy(source, dst, rel)                          # the read now sees the growth

    def writer():
        if go.wait(5):
            with open(src / 'one.txt', 'ab') as f:
                f.write(b'grown tail\n')
            done.set()

    monkeypatch.setattr(seed, '_copy', copy)
    walked = instrument(monkeypatch, '_verify_tree')
    poison_removals(monkeypatch)
    scan, calls = scan_ok()
    thread = threading.Thread(target=writer, name='t1129-grow')
    thread.start()
    try:
        with pytest.raises(seed.SeedError) as err:
            seed.seed_copy({'one.txt': src / 'one.txt'}, dest, scan)
        assert 'copy differs from its source: one.txt' in str(err.value)
        assert 'changed while it was copied' not in str(err.value)  # the copy saw one steady file
    finally:
        go.set()
        done.set()                                                  # never leave the writer waiting
        thread.join(5)
    assert not thread.is_alive()                                    # every thread started is joined
    assert calls == [] and walked == []
    assert (src / 'one.txt').read_bytes() == grown                  # the source stands as grown
    assert (dest / 'one.txt').read_bytes() == grown   # the copy of it stands, removed nothing
