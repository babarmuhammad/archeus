"""T-766: the highest-risk uncovered branches of `archeus/infra/artifacts/store.py`.

The store is content-addressed: the address IS the sha256, so a blob is
immutable, one copy serves all readers, and a reader can verify what it got
(domain-model S 7.9). Its existing coverage is a single integration test
(`test_artifacts_are_content_addressed_under_archeus_home` in
tests/v1/integration/test_recovery.py) plus incidental use through the
application; no unit test drives the store itself. The style and fixtures here
follow the closest unit consumer, tests/v1/unit/test_gaps_core_application_-
verification.py: the autouse `archeus_home` fixture of tests/v1/conftest.py
pins `ARCHEUS_HOME` into the test's own tmp_path, blobs are written as bytes
with explicit newlines, and nothing spawns a process or touches the network.
The two publish-path tests replace `store.os` with a delegating fake (the
seam the module already dangles: `os.fsync` / `os.replace` are looked up on
the `os` module at call time), so they make no assertion about OS error text
and run the same on Windows and Linux.

The ten branches, with file:line and the mutation each catches, are listed in
/work/QWEN-DONE-T-766.md.
"""

import hashlib
import os

import pytest

from archeus.infra.artifacts import store

DATA = b'checkpoint body\nsecond line\n'          # explicit newlines, platform-neutral
SHA_DATA = hashlib.sha256(DATA).hexdigest()


def _shard_dir(sha, home):
    return os.path.join(str(home), 'artifacts', sha[:2], sha[2:4])


class _FakeOs:
    """A seam for `store.os`: delegates everything, records fsync/replace, and
    can fail the rename to simulate a crash between write and publish."""

    def __init__(self):
        self.path = os.path
        self.calls = []
        self.replace_args = None
        self.dest_at_replace = None
        self.fail_replace = False

    def exists(self, p):
        return os.path.exists(p)

    def makedirs(self, p, exist_ok=False):
        return os.makedirs(p, exist_ok=True) if exist_ok else os.makedirs(p)

    def getpid(self):
        return os.getpid()

    def fsync(self, fd):
        self.calls.append('fsync')
        return os.fsync(fd)

    def replace(self, src, dest):
        self.calls.append('replace')
        self.replace_args = (src, dest)
        self.dest_at_replace = os.path.exists(dest)
        if self.fail_replace:
            raise OSError('simulated crash before the rename')
        return os.replace(src, dest)


# ── denial / fail-closed paths ──

def test_get_refuses_a_tampered_blob_and_never_returns_it(tmp_path):
    """store.py:50-51 (`if hashlib.sha256(data).hexdigest() != sha: raise`).
    Removing the comparison, inverting it, or returning `data` anyway makes a
    forged blob indistinguishable from an honest one — the reader is the only
    party that can detect tampering, so this raise is the whole security
    property of the store."""
    home = tmp_path / 'h-tamper'
    sha = store.put(DATA, home=str(home))
    with open(store.path_for(sha, home=str(home)), 'wb') as f:
        f.write(b'forged body\n')
    with pytest.raises(ValueError, match='corrupt'):
        store.get(sha, home=str(home))


def test_get_of_an_absent_blob_raises_and_validates_before_touching_disk(tmp_path):
    """store.py:48 (`open(path_for(sha, home))`): a missing blob surfaces as the
    OSError from open — never a silent `None`/empty read a caller could record
    as evidence. The second half pins that `get` runs the address through
    `path_for` *before* any open: a get that validated lazily or skipped
    validation could be walked out of the artifacts tree with '../x'."""
    home = tmp_path / 'h-absent'
    with pytest.raises(FileNotFoundError):
        store.get('a' * 64, home=str(home))       # valid address, never stored
    with pytest.raises(ValueError):
        store.get('../x', home=str(home))         # refused before any open


def test_path_for_refuses_non_strings(tmp_path):
    """store.py:25 (`isinstance(sha, str)`): dropped, a bytes sha would pass
    fullmatch in some paths and None/int would reach os.path.join and raise the
    wrong error, or worse, name a file. The store's contract is a *text*
    lowercase hex digest, and only that."""
    for bad in (None, 42, b'0' * 64, ['a' * 64], 0.5):
        with pytest.raises(ValueError):
            store.path_for(bad, home=str(tmp_path))


@pytest.mark.parametrize('sha', [
    'A' * 64,          # uppercase: two addresses for one blob on any reader
    'a' * 63,          # short: not every hex is an address
    'a' * 65,          # long: fullmatch, not match
    '',                # empty
    'g' * 64,          # not hex
    'a' * 63 + '\n',   # trailing newline: the classic re.match leak
    'ab/c' + 'a' * 60,  # a separator inside the digest: no directory escape
], ids=['upper', 'short', 'long', 'empty', 'nonhex', 'newline', 'slash'])
def test_path_for_refuses_malformed_digests(sha, tmp_path):
    """store.py:25-26 (`_SHA.fullmatch(sha)` -> ValueError). `fullmatch` of
    `[0-9a-f]{64}` is the only thing between a caller's string and a filename:
    any loosening (match instead of fullmatch, `re.I`, dropping the class)
    lets a second, colliding or escaping name address the store."""
    with pytest.raises(ValueError):
        store.path_for(sha, home=str(tmp_path))


def test_put_refuses_to_overwrite_an_existing_address(tmp_path):
    """store.py:34 (`if not os.path.exists(dest):`): the writer never touches a
    published address, even when its bytes are wrong — immutability is enforced
    by absence of any write path, and corruption is the *reader's* to report.
    Removing the exists check (always rewrite) would let a late put silently
    "repair" — i.e. silently rewrite through — an address a reader already saw
    as corrupt; this test pins that put returns the sha and the disk keeps the
    forged bytes."""
    home = tmp_path / 'h-immutable'
    sha = store.put(DATA, home=str(home))
    with open(store.path_for(sha, home=str(home)), 'wb') as f:
        f.write(b'forged body\n')
    assert store.put(DATA, home=str(home)) == sha
    with pytest.raises(ValueError, match='corrupt'):
        store.get(sha, home=str(home))


# ── boundary values ──

def test_empty_bytes_round_trip_through_the_store(tmp_path):
    """store.py:32 + 48-52 with `data == b''`: the empty blob is a real address
    (sha256 of nothing) that must store, verify and return as exactly nothing.
    An `if data:` anywhere in put/get — the classic truthiness bug — loses the
    empty artifact or reads it back as a failure."""
    home = tmp_path / 'h-empty'
    sha = store.put(b'', home=str(home))
    assert sha == hashlib.sha256(b'').hexdigest()
    assert store.get(sha, home=str(home)) == b''
    big = bytes(range(256)) * 64                   # NULs and high bytes survive too
    sha2 = store.put(big, home=str(home))
    assert store.get(sha2, home=str(home)) == big


def test_path_for_shards_on_the_first_four_hex_digits(tmp_path):
    """store.py:27 (`sha[:2], sha[2:4], sha`): the fan-out boundary. A digest
    starting with '0000' or 'ffff' must land in exactly `ab/cd/<sha>` under the
    artifacts root; an off-by-one (`sha[:1]`, `sha[2:3]`, no split) changes
    every address and silently orphanes existing blobs."""
    for sha in ('0' * 64, 'f' * 64, SHA_DATA):
        got = store.path_for(sha, home=str(tmp_path))
        assert got == os.path.join(str(tmp_path), 'artifacts', sha[:2], sha[2:4], sha)


def test_root_follows_archeus_home_or_the_explicit_home(archeus_home, tmp_path):
    """store.py:21 (`paths.archeus_home() if home is None else home`): both
    sides of the ternary. Resolved at call time, never an import constant: with
    a wrong branch here every blob of every test (and of the real user) lands
    in the wrong tree."""
    assert os.path.normcase(store.root()) == os.path.normcase(
        os.path.join(str(archeus_home), 'artifacts'))
    assert os.path.normcase(store.root(str(tmp_path))) == os.path.normcase(
        os.path.join(str(tmp_path), 'artifacts'))


def test_explicit_home_never_touches_archeus_home(archeus_home, tmp_path):
    """store.py:21/27/33, the `home=` override as a whole: if put ignored the
    argument (or path_for dropped it), blobs would land under the test's
    ARCHEUS_HOME — which stays provably empty here — instead of the home the
    caller named."""
    other = tmp_path / 'other-home'
    sha = store.put(DATA, home=str(other))
    expected = os.path.join(str(other), 'artifacts', sha[:2], sha[2:4], sha)
    assert store.path_for(sha, home=str(other)) == expected
    assert os.path.exists(expected)
    assert not os.path.exists(os.path.join(str(archeus_home), 'artifacts'))


# ── error / durability paths ──

def test_same_bytes_are_stored_once_with_no_tmp_debris(tmp_path):
    """store.py:34 (skip branch) + 36-41 (the tmp file must be *renamed*, not
    left behind): the shard directory holds exactly the one blob. A tmp file
    that survives (missing os.replace at 41) is the debris signature; a second
    copy is the dedup signature broken."""
    home = tmp_path / 'h-once'
    assert store.put(DATA, home=str(home)) == SHA_DATA
    assert store.put(DATA, home=str(home)) == SHA_DATA
    assert os.listdir(_shard_dir(SHA_DATA, home)) == [SHA_DATA]


def test_a_crash_before_the_rename_leaves_nothing_at_the_address(tmp_path, monkeypatch):
    """store.py:34-41 with `os.replace` failing (the crash window between
    writing bytes and publishing them): the module's whole reason for
    tmp+rename is that "a crash never leaves a partial file at a real
    address". Writing straight to dest (no tmp) or renaming the bytes into
    place before they are complete is caught here: after the simulated crash
    the real address must not exist, only the pid-named tmp — and the retry
    must then store and verify normally."""
    home = tmp_path / 'h-crash'
    fake = _FakeOs()
    fake.fail_replace = True
    monkeypatch.setattr(store, 'os', fake)
    with pytest.raises(OSError):
        store.put(DATA, home=str(home))
    dest = store.path_for(SHA_DATA, home=str(home))
    assert not os.path.exists(dest)
    assert [n for n in os.listdir(os.path.dirname(dest)) if n.endswith('.tmp')]
    fake.fail_replace = False
    assert store.put(DATA, home=str(home)) == SHA_DATA
    assert store.get(SHA_DATA, home=str(home)) == DATA
    assert os.listdir(os.path.dirname(dest)) == [SHA_DATA]


def test_bytes_are_fsynced_before_the_address_appears(tmp_path, monkeypatch):
    """store.py:37-41, the ordering `write -> flush -> fsync(tmp) ->
    os.replace(tmp, dest)`: on the power-loss models this code is written
    against, rename-before-fsync can publish an empty or partial file under a
    valid address. Removing os.fsync (40), doing the rename first, or renaming
    a source that *is* the destination (a direct write) all fail one of these
    assertions, and the src is checked to be the pid-named tmp of 36."""
    home = tmp_path / 'h-order'
    fake = _FakeOs()
    monkeypatch.setattr(store, 'os', fake)
    sha = store.put(DATA, home=str(home))
    assert fake.calls == ['fsync', 'replace']
    src, dest = fake.replace_args
    assert dest == store.path_for(sha, home=str(home))
    assert src != dest
    base = os.path.basename(src)
    assert base.endswith('.tmp') and str(os.getpid()) in base
    assert fake.dest_at_replace is False          # bytes only ever reached tmp
