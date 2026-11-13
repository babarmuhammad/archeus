"""Plain-file refusal and copied-byte fidelity of n2_check.stage_toolchain and verify_copy.

Reparse points are fake stats, the image copy is synthetic bytes under tmp_path, and every
open() the module makes goes through the module-level `open` seam. Nothing launches a process
or creates a real link or junction.
"""

import hashlib
import os
import re
import stat
from types import SimpleNamespace

import pytest

from tools.pv20_mxc.native import n2_check as n2

#: the builtin, captured before any test can patch the module-level name
_REAL_OPEN = open

EMPTY_SHA256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
GOOD = b'MZ\x90\x00' + bytes(range(256)) * 4          # synthetic cmd.exe bytes


# ---------------------------------------------------------------- copied seams

def _lay(tmp_path):
    """The N2 layout, built for real under tmp_path (copied from test_pv20_n2_check)."""
    lay = n2.layout(str(tmp_path / 'root'))
    n2.make_dirs(lay)
    return lay


def _world(tmp_path, src_bytes=GOOD):
    """(lay, src, folder, dst) with a real plain source file and a real plain toolchain
    folder, exactly the pair diagnose() hands to stage_toolchain()."""
    lay = _lay(tmp_path)
    folder = os.path.join(lay['root'], 'toolchain')
    os.makedirs(folder, exist_ok=True)
    src_dir = os.path.join(str(tmp_path), 'host')
    os.makedirs(src_dir, exist_ok=True)
    src = os.path.join(src_dir, 'cmd.exe')
    with _REAL_OPEN(src, 'wb') as fh:
        fh.write(src_bytes)
    return lay, src, folder, os.path.join(folder, 'cmd.exe')


def _info(mode, attrs=None):
    """A stat-result stand-in. attrs=None leaves st_file_attributes absent, so plain()
    has to fall back to its getattr default."""
    info = SimpleNamespace(st_mode=mode)
    if attrs is not None:
        info.st_file_attributes = attrs
    return info


def _lstat(fakes):
    """Fake lstat seam: the named path gets its fake stat, anything else the real one."""
    calls = []

    def lstat(path):
        calls.append(str(path))
        if str(path) in fakes:
            return fakes[str(path)]
        return os.lstat(str(path))
    lstat.calls = calls
    return lstat


class _NoOpen:
    """open() that must never be reached: any call is the defect."""

    def __init__(self):
        self.calls = []

    def __call__(self, path, mode='r', *a, **kw):
        self.calls.append((str(path), mode))
        raise AssertionError('file opened before the plain-file refusal: %s %s' % (path, mode))


class _Opener:
    """Delegating open() seam: records (path, mode), fails the named opens, shortens the
    writes of the named ones. Everything else is the real builtin on real tmp_path bytes."""

    def __init__(self, fail=None, short=None):
        self.calls = []
        self.fail = fail or {}
        self.short = short or {}

    @property
    def modes(self):
        return list(self.calls)

    def __call__(self, path, mode='r', *a, **kw):
        path = str(path)
        self.calls.append((path, mode))
        if (path, mode) in self.fail:
            raise self.fail[(path, mode)]
        fh = _REAL_OPEN(path, mode, *a, **kw)
        if (path, mode) in self.short:
            return _ShortWrite(fh, self.short[(path, mode)])
        return fh


class _ShortWrite:
    """A file handle whose write() is short (returns what it really wrote)."""

    def __init__(self, fh, keep):
        self._fh = fh
        self._keep = keep
        self.written = None

    def write(self, data):
        self.written = self._fh.write(data[:self._keep])
        return self.written

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._fh.__exit__(*exc)


class _NoLaunch:
    """Stand-in for the module's subprocess module: any use is a privileged side effect."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _refused(*a, **kw):
            self.calls.append(name)
            raise AssertionError('native launch attempted: subprocess.%s' % name)
        return _refused


@pytest.fixture(autouse=True)
def no_native_launch(monkeypatch):
    """Whole-file guarantee: this slice may not spawn, launch or shell out."""
    guard = _NoLaunch()
    monkeypatch.setattr(n2, 'subprocess', guard)
    yield guard
    assert guard.calls == []


# ------------------------------------------------------- P1..P2 denial / fail-closed

def test_01_refusal_happens_before_any_source_open_or_destination_creation(tmp_path, monkeypatch):
    """1106: a fake source stat (regular + reparse bit) must refuse the copy while the
    folder is a perfectly plain directory, and it must do so before touching the file.
    Catches: dropping `not getattr(info,'st_file_attributes',0) & REPARSE` from plain(),
    or moving the guard after the read at 1108 / the create at 1111."""
    lay, src, folder, dst = _world(tmp_path)
    # folder-plain control first: the same call with the real source stat stages the copy
    control = os.path.join(lay['root'], 'toolchain-control')
    os.makedirs(control, exist_ok=True)
    digest, written = n2.stage_toolchain(src, control)
    assert written == os.path.join(control, 'cmd.exe')
    assert digest == hashlib.sha256(GOOD).hexdigest()
    # the refused run: only the source stat is fake (regular + reparse), folder is real/plain
    opened = _NoOpen()
    monkeypatch.setattr(n2, 'open', opened, raising=False)
    stat_called = _lstat({src: _info(stat.S_IFREG, n2.REPARSE)})
    with pytest.raises(n2.SetupError) as exc:
        n2.stage_toolchain(src, folder, lstat=stat_called)
    assert 'refused' in str(exc.value)
    assert stat_called.calls[0] == src                                 # source is judged first
    assert opened.calls == []                                          # no read, no create
    assert not os.path.exists(dst)                                     # nothing left behind


def test_02_folder_reparse_bit_refuses_the_copy_before_the_write(tmp_path, monkeypatch):
    """1106: a folder stat that is a directory but carries the reparse attribute is a
    junction stand-in and must refuse before a single byte is written (pure fake stat, no
    real link/junction). Catches: dropping the second `plain(lstat(folder), S_ISDIR)`
    term, or checking only S_ISLNK so an attributed junction folder passes."""
    lay, src, folder, dst = _world(tmp_path)
    opened = _Opener()
    monkeypatch.setattr(n2, 'open', opened, raising=False)
    with pytest.raises(n2.SetupError) as exc:
        n2.stage_toolchain(src, folder, lstat=_lstat({folder: _info(stat.S_IFDIR, n2.REPARSE)}))
    assert 'refused' in str(exc.value)
    assert opened.modes == []                                          # source never read either
    assert not os.path.exists(dst)
    # control: a directory carrying only benign attributes (archive) is accepted and staged
    digest, written = n2.stage_toolchain(
        src, folder, lstat=_lstat({folder: _info(stat.S_IFDIR, 0x20)}))
    assert written == dst and digest == hashlib.sha256(GOOD).hexdigest()
    assert os.path.isdir(folder) and os.path.isfile(dst)


def test_03_copy_that_turns_non_plain_after_the_write_never_reports_a_hash(tmp_path, monkeypatch):
    """1113-1114: the destination stat going non-plain after the write must raise the
    not-a-plain-file SetupError and never reach the read-back/hash proof at 1115-1116.
    Catches: removing the post-write guard, or reordering so verify_copy runs first and
    a reparse-ified destination could still return a success digest."""
    lay, src, folder, dst = _world(tmp_path)
    opened = _Opener()
    monkeypatch.setattr(n2, 'open', opened, raising=False)
    with pytest.raises(n2.SetupError) as exc:
        n2.stage_toolchain(src, folder, lstat=_lstat({dst: _info(stat.S_IFLNK)}))
    msg = str(exc.value)
    assert 'not a plain file' in msg and 'mismatch' not in msg
    assert opened.modes == [(src, 'rb'), (dst, 'xb')]                  # no rb read-back at 1115
    assert os.path.dirname(dst) == folder and dst.startswith(str(tmp_path))   # confined


def test_04_plain_ignores_the_supplied_kind_for_links_and_defaults_attrs_to_zero():
    """390-392: `kind` is only an accepted-shape test, never an override — a symlink is
    refused even by a kind lambda that always returns True, the reparse bit is refused
    whatever else is set, and an info with no st_file_attributes falls back to 0.
    Catches: inverting `not stat.S_ISLNK(...)`, dropping the getattr default, or testing
    truthiness of the whole attribute word instead of masking REPARSE."""
    assert n2.plain(_info(stat.S_IFREG), stat.S_ISREG)
    assert n2.plain(_info(stat.S_IFDIR), stat.S_ISDIR)                  # missing attrs default
    assert n2.plain(_info(stat.S_IFREG, 0x20), stat.S_ISREG)             # benign attrs tolerated
    assert n2.plain(_info(stat.S_IFREG, n2.REPARSE - 1), stat.S_ISREG)  # neighbour bit, not reparse
    assert not n2.plain(_info(stat.S_IFLNK), lambda mode: True)          # kind cannot rescue a link
    assert not n2.plain(_info(stat.S_IFLNK, 0), stat.S_ISREG)   # a link also fails the kind term
    assert not n2.plain(_info(stat.S_IFREG, n2.REPARSE), stat.S_ISREG)
    assert not n2.plain(_info(stat.S_IFDIR, n2.REPARSE | 0x80), lambda mode: True)
    assert not n2.plain(_info(0), stat.S_ISREG)                          # kind still decides


# ------------------------------------------------------- P5 destination state

def test_05_existing_destination_is_never_overwritten_or_cleaned_up(tmp_path, monkeypatch):
    """1111: the destination already existing must fail the exclusive create, keep the
    old bytes, and leave the pre-existing file in place. Catches: `xb` weakened to `wb`
    (silent overwrite of a planted toolchain/cmd.exe) or an added cleanup/fallback path."""
    lay, src, folder, dst = _world(tmp_path)
    old = b'PLANTED-BY-SOMEONE-ELSE'
    with _REAL_OPEN(dst, 'wb') as fh:
        fh.write(old)
    opened = _Opener()
    monkeypatch.setattr(n2, 'open', opened, raising=False)
    with pytest.raises(OSError) as exc:
        n2.stage_toolchain(src, folder)
    assert type(exc.value) is FileExistsError and not isinstance(exc.value, n2.SetupError)
    assert opened.modes == [(src, 'rb'), (dst, 'xb')]                   # never 'wb', never a retry
    assert os.path.exists(dst) and _REAL_OPEN(dst, 'rb').read() == old   # untouched, not deleted
    assert _REAL_OPEN(src, 'rb').read() == GOOD                          # source untouched too


# ------------------------------------------------------- P6..P8 fidelity boundaries

def test_06_empty_source_copies_faithfully_and_names_the_destination(tmp_path):
    """1116 (boundary): a zero-byte source is a valid copy and must return SHA-256(empty)
    with dst exactly folder/cmd.exe, without any launch. Catches: an empty-source path
    that skips the write or the hash check, and any drift of dst out of the toolchain
    folder."""
    lay, src, folder, dst = _world(tmp_path, src_bytes=b'')
    assert os.path.getsize(src) == 0
    digest, written = n2.stage_toolchain(src, folder)
    assert written == dst == os.path.join(folder, 'cmd.exe')
    assert digest == hashlib.sha256(b'').hexdigest() == EMPTY_SHA256
    assert _REAL_OPEN(dst, 'rb').read() == b'' and os.path.getsize(dst) == 0
    back = os.stat(dst)                                                   # the host read-back shape
    assert stat.S_ISREG(back.st_mode) and back.st_nlink == 1 and not stat.S_ISLNK(back.st_mode)


def test_07_same_length_one_byte_corruption_refuses_and_names_both_digests():
    """1120-1122: a copy that is the right length but one byte off must refuse, and the
    error must carry both hex digests (the only evidence the operator gets) while never
    echoing the bytes. Catches: dropping `if a != b`, comparing sizes instead of the
    digests, or leaking the copied bytes into the SetupError text."""
    bad = bytearray(GOOD)
    bad[1001] ^= 0x01
    bad = bytes(bad)
    assert len(bad) == len(GOOD) and bad != GOOD
    with pytest.raises(n2.SetupError) as exc:
        n2.verify_copy(GOOD, bad)
    msg = str(exc.value)
    assert hashlib.sha256(GOOD).hexdigest() in msg                        # source digest
    assert hashlib.sha256(bad).hexdigest() in msg                         # copy digest
    assert 'MZ' not in msg and '\x00' not in msg                         # bytes are never echoed


def test_08_verify_copy_returns_a_stable_lowercase_digest_and_is_length_sensitive():
    """1120/1123 (boundary): equal bytes return one deterministic lowercase 64-hex digest
    — including for the empty/empty pair — and any length difference refuses. Catches:
    returning a per-call or base64/hex-of-the-bytes value, or accepting a truncated copy
    by comparing lengths rather than digests."""
    empty = n2.verify_copy(b'', b'')
    assert empty == EMPTY_SHA256 and re.fullmatch(r'[0-9a-f]{64}', empty)
    same = n2.verify_copy(GOOD, GOOD)
    assert same == n2.verify_copy(GOOD, GOOD) == hashlib.sha256(GOOD).hexdigest()
    pairs = ((b'', b'x'), (b'x', b''), (GOOD, GOOD[:-1]), (GOOD[:-1], GOOD), (GOOD, GOOD + b'\n'))
    for a, b in pairs:
        with pytest.raises(n2.SetupError):
            n2.verify_copy(a, b)


# ------------------------------------------------------- P9..P10 error paths

def test_09_source_read_failure_keeps_the_original_error_and_leaves_no_destination(tmp_path,
                                                                                    monkeypatch):
    """1108: when the source read fails, the original error must propagate unchanged, the
    destination must never be opened, and no partial copy may exist. Catches: wrapping the
    read error into SetupError (losing the OS failure) or creating dst before reading src."""
    lay, src, folder, dst = _world(tmp_path)
    boom = OSError(5, 'synthetic source read failure')
    opened = _Opener(fail={(src, 'rb'): boom})
    monkeypatch.setattr(n2, 'open', opened, raising=False)
    with pytest.raises(OSError) as exc:
        n2.stage_toolchain(src, folder)
    assert exc.value is boom and not isinstance(exc.value, n2.SetupError)
    assert opened.modes == [(src, 'rb')]                                # dst never opened at 1111
    assert not os.path.exists(dst)


def test_10a_short_destination_write_is_caught_by_the_real_reread(tmp_path, monkeypatch):
    """1112 (write) + 1115-1116 (reread): a short write is not detected by stage_toolchain
    itself, so the actual (truncated) reread must fail verify_copy instead of reporting a
    verified copy. Catches: trusting fh.write()'s return value, or rereading something
    other than what is on disk."""
    lay, src, folder, dst = _world(tmp_path)
    opened = _Opener(short={(dst, 'xb'): 7})
    monkeypatch.setattr(n2, 'open', opened, raising=False)
    with pytest.raises(n2.SetupError) as exc:
        n2.stage_toolchain(src, folder)
    assert 'hash mismatch' in str(exc.value)
    assert hashlib.sha256(GOOD).hexdigest() in str(exc.value)
    assert _REAL_OPEN(dst, 'rb').read() == GOOD[:7]              # still truncated on disk
    assert opened.modes.count((dst, 'rb')) == 1                          # one honest reread only


def test_10b_destination_reread_error_propagates_and_is_never_reported_verified(tmp_path,
                                                                                monkeypatch):
    """1115: if the destination cannot be read back, the original error propagates and no
    (digest, dst) pair is ever returned. Catches: swallowing the read error, or returning
    the source digest without checking the copy on disk."""
    lay, src, folder, dst = _world(tmp_path)
    boom = OSError(5, 'synthetic destination read-back failure')
    opened = _Opener(fail={(dst, 'rb'): boom})
    monkeypatch.setattr(n2, 'open', opened, raising=False)
    with pytest.raises(OSError) as exc:
        n2.stage_toolchain(src, folder)
    assert exc.value is boom and not isinstance(exc.value, n2.SetupError)
    assert opened.modes == [(src, 'rb'), (dst, 'xb'), (dst, 'rb')]
    assert _REAL_OPEN(dst, 'rb').read() == GOOD                            # written, but unproven
