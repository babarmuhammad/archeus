"""T-1030 gap tests: archeus/node/local.py lines 1679-1712 inclusive (the slice
``_stamp`` / ``_same`` / ``_read_object`` that guards every hostile request and answer
file Core re-reads each tick). No source file is edited here.

The ten branches covered, listed in source order (the T-1030 report ranks them
fail-closed / denial first, then boundaries, then error paths):

1. local.py:1705-1707   growth after the stat: the read is capped at the *stamped*
                        size + 1, so a file rewritten between stat and open is denied,
                        never slurped whole.
2. local.py:1707        stat says zero, file holds bytes: read(min(0, MAX)+1) takes one
                        byte and the parse of that byte denies - the empty-stat file is
                        never trusted.
3. local.py:1706        open fails after a successful stat (ENOENT race, EACCES): the
                        OSError is caught, the object is None.
4. local.py:1707        the read itself fails (EIO mid-file): caught, None.
5. local.py:1708, 1709  bad UTF-8: UnicodeDecodeError (a ValueError) is caught before
                        json.loads ever sees the bytes.
6. local.py:1697        NaN must not equal a different nonce: a stale answer whose
                        nonce is NaN must not answer a 0/'NaN'/None request.
7. local.py:1695-1697   NaN inside a list or dict still equals its twin (the comment's
                        "nor is a list or dict holding one" case: the existing nonce
                        test's nonce is a scalar by the time _same sees it).
8. local.py:1697        dict nonces match whatever their key insertion order
                        (json.dumps(sort_keys=True); the existing dict-nonce case is
                        single-key, so order never mattered).
9. local.py:1707        boundary: a stat lying far past MAX_REQUEST_BYTES still asks
                        the reader for at most MAX_REQUEST_BYTES + 1, never for what
                        the lie invites.
10. local.py:1691       the stamp's content: (mtime_ns, size, ino) exactly, so a
                        same-mtime same-inode rewrite that only moves the size still
                        fails the answered-pair memo (existing memo tests move the
                        time, or delete: neither notices a dropped st_size or st_ino).

OS calls are seam-faked the way the existing tests fake them (monkeypatch on os.stat
and on local.open with raising=False, spy on local.json.loads); tmp files go through
tmp_path only; nothing here needs Windows or any OS error text.
"""

import errno
import json
import os
from types import SimpleNamespace

import pytest

from archeus.node import local


class _Counted:
    """Wraps a real file so the *n* handed to read() is observable, as in the
    existing bound tests (test_execution_units.py)."""

    def __init__(self, f, sink):
        self.f, self.sink = f, sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.f.close()

    def read(self, n=-1):
        self.sink.append(n)
        return self.f.read(n)


def _fake_local_open(monkeypatch, target, factory):
    real_open = open

    def fake_open(path, *a, **k):
        return factory(path, a, k) if os.fspath(path) == target else real_open(path, *a, **k)

    monkeypatch.setattr(local, 'open', fake_open, raising=False)
    return real_open


# ── 1-2: the size the stat reported is the size the read may ask for ──────────


def test_growth_after_the_stat_is_read_to_the_stamped_size_and_denied(tmp_path, monkeypatch):
    """local.py:1705-1707. The execution grew the file between the stat and the open:
    it is now a *complete* JSON object, so only reading no more than the stamped size
    denies it - a reader that trusts the live file would hand Core an answer the
    stamped pair never had."""
    path = str(tmp_path / 'growth.req.json')
    with open(path, 'wb') as f:
        f.write(b'{"ask": 1111}')                      # 13 bytes now, all valid JSON
    events, reads = [], []
    real_stat, real_open = os.stat, open

    def fake_stat(p, *a, **k):
        if os.fspath(p) == path:
            events.append('stat')
            return SimpleNamespace(st_size=9, st_mtime_ns=1, st_ino=1)   # stat saw 9
        return real_stat(p, *a, **k)

    def factory(p, a, k):
        events.append('open')
        return _Counted(real_open(p, *a, **k), reads)

    monkeypatch.setattr(os, 'stat', fake_stat)
    _fake_local_open(monkeypatch, path, factory)
    assert local._read_object(path) is None            # the grown tail is denial, not data
    assert reads == [10]                               # stamped 9 + 1: never the 13 live bytes
    assert events == ['stat', 'open']                  # the stat comes before the read
    assert real_stat(path).st_size == 13               # nothing was truncated or rewritten


def test_a_stat_of_zero_before_the_read_reads_one_byte_and_denies(tmp_path, monkeypatch):
    """local.py:1707. stat reported 0 (the execution had not flushed yet) and then the
    file held bytes: min(0, MAX)+1 is one byte, and one byte never parses - the
    half-written file cannot answer anything."""
    path = str(tmp_path / 'zero.req.json')
    with open(path, 'wb') as f:
        f.write(b'{"ask": 1}')                          # a whole object, 10 bytes
    events, reads = [], []
    real_stat, real_open = os.stat, open

    def fake_stat(p, *a, **k):
        if os.fspath(p) == path:
            events.append('stat')
            return SimpleNamespace(st_size=0, st_mtime_ns=1, st_ino=1)
        return real_stat(p, *a, **k)

    def factory(p, a, k):
        events.append('open')
        return _Counted(real_open(p, *a, **k), reads)

    monkeypatch.setattr(os, 'stat', fake_stat)
    _fake_local_open(monkeypatch, path, factory)
    assert local._read_object(path) is None
    assert reads == [1]                                # min(0, MAX) + 1, not 0 and not the file
    assert events == ['stat', 'open']
    assert real_stat(path).st_size == 10


# ── 3-4: the OSError inside the try is denial, not a raised crash ─────────────


def test_an_open_error_after_a_good_stat_is_denied_not_raised(tmp_path, monkeypatch):
    """local.py:1706, 1709-1710. The stat passed and the open then failed (the
    file vanished in the race, or was opened with a deny-share): the OSError is
    caught, and no second path is opened to get at the content anyway."""
    path = str(tmp_path / 'gone.req.json')
    with open(path, 'wb') as f:
        f.write(b'{"ask": 1}')
    opens, real_open = [], open

    def factory(p, a, k):
        opens.append(os.fspath(p))
        raise OSError(errno.ENOENT, 'gone between stat and open')

    _fake_local_open(monkeypatch, path, factory)
    assert local._read_object(path) is None            # no retry, no substitute reader
    assert opens == [path]                             # exactly one privileged attempt
    assert real_open(path, 'rb').read() == b'{"ask": 1}'   # the file was left alone


def test_a_failing_read_after_open_is_denied_not_raised(tmp_path, monkeypatch):
    """local.py:1707, 1709-1710. open succeeded and read() itself raised (a raw EIO
    mid-file on the shared drive): the OSError is caught and the object is None."""
    path = str(tmp_path / 'eio.req.json')
    with open(path, 'wb') as f:
        f.write(b'{"ask": 1}')

    class FailRead:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n=-1):
            raise OSError(errno.EIO, 'device failure')

    _fake_local_open(monkeypatch, path, lambda p, a, k: FailRead())
    assert local._read_object(path) is None
    assert os.path.getsize(path) == 10                 # denial touched nothing else


# ── 5: undecodable bytes never reach the parser ───────────────────────────────


@pytest.mark.parametrize('body,ids', [
    (b'{"tool": "\xff\xfe"}', 'badbyte'),               # not UTF-8 at all
    (b'{"tool": "\xc3"}', 'halfchar'),                  # a two-byte char cut in half
])
def test_undecodable_bytes_are_denied_before_any_parse(tmp_path, monkeypatch, body, ids):
    """local.py:1708, 1709-1710. data.decode('utf-8') raises UnicodeDecodeError - a
    ValueError - so json.loads must never see the hostile bytes; the closest existing
    test ('not json', test_execution_units.py:1005) only exercises ASCII garbage that
    decode lets through to loads."""
    path = str(tmp_path / ('badutf8.req.json'))
    with open(path, 'wb') as f:
        f.write(body)
    parsed, real_loads = [], json.loads
    monkeypatch.setattr(local.json, 'loads', lambda s, *a, **k: parsed.append(s) or real_loads(s))
    assert local._read_object(path) is None
    assert parsed == []                                # refused at decode, before the parse


# ── 6-8: what _same's json.dumps equality does, and must keep doing ───────────


def test_a_nan_nonce_does_not_answer_a_different_nonce():
    """local.py:1697. Fail closed the other way: json.dumps makes NaN equal its twin,
    it must not make NaN equal *anything else*. The existing NaN test
    (test_execution_units.py:1154) only proves NaN answers its own echo, so an
    equality that said yes too often - NaN vs 0 or the string 'NaN' - passed unseen."""
    nan = float('nan')
    assert local._same(nan, 0.0) is False
    assert local._same(nan, 'NaN') is False
    assert local._same(nan, None) is False
    assert local._same([nan], ['NaN']) is False
    assert local._same({'k': [nan]}, 0) is False


def test_nan_inside_a_list_or_dict_nonce_still_matches_its_twin():
    """local.py:1695-1697. The comment names this case verbatim ("nor is a list or
    dict holding one"): the execution wrote "nonce": [NaN, {"d": NaN}]. Every
    existing NaN nonce is a plain scalar by the time _same is called, so a regression
    back to plain == (or to any element-wise compare) still passed them all."""
    nan = float('nan')
    twin = ['x', {'k': [nan, {'deep': nan}]}, nan]
    assert local._same(twin, list(twin)) is True
    assert local._same({'n': [nan]}, {'n': [float('nan')]}) is True


def test_dict_nonces_match_whatever_their_key_order():
    """local.py:1697. sort_keys=True is the whole point of the dumps: two equal
    multi-key nonces written by different dict-insertion orders are the same answer.
    The existing dict nonce ('{"a": NaN}', test_execution_units.py:1154) is
    single-key, so order could not matter there; drop sort_keys and only this fails."""
    a = {'b': 1, 'a': 2, 'c': [3, {'z': 0, 'y': 1}]}
    b = {'a': 2, 'c': [3, {'y': 1, 'z': 0}], 'b': 1}
    assert local._same(a, b) is True
    assert local._same(a, {'b': 1, 'a': 2, 'c': [3, {'z': 0, 'y': 2}]}) is False


# ── 9-10: boundaries and the state the memo runs on ───────────────────────────


def test_a_stat_lying_past_the_bound_never_asks_the_reader_for_more_than_it(
        tmp_path, monkeypatch):
    """local.py:1707. A stat claiming 1 GB must clamp the read to MAX_REQUEST_BYTES+1,
    and content that is genuinely under the bound is still judged on its bytes. The
    existing bound test uses a real 10 KB file and a real stat, so min(size, MAX)
    swapped for max(size, MAX) - reading whatever the lie invites - changed nothing
    it asserts."""
    path = str(tmp_path / 'lielarge.req.json')
    with open(path, 'wb') as f:
        f.write(b'{"ok": 1}')
    reads = []
    real_stat, real_open = os.stat, open

    def fake_stat(p, *a, **k):
        if os.fspath(p) == path:
            return SimpleNamespace(st_size=10 ** 9, st_mtime_ns=1, st_ino=1)
        return real_stat(p, *a, **k)

    monkeypatch.setattr(os, 'stat', fake_stat)
    _fake_local_open(monkeypatch, path,
                     lambda p, a, k: _Counted(real_open(p, *a, **k), reads))
    assert local._read_object(path) == {'ok': 1}
    assert reads == [local.MAX_REQUEST_BYTES + 1]      # never the 10**9 the stat claimed


def test_the_stamp_reports_mtime_size_and_inode_so_a_size_only_rewrite_is_seen(tmp_path):
    """local.py:1686-1691. Every existing answered-pair test moves the mtime
    (test_execution_units.py:1120) or deletes the file (:1127): neither notices
    _stamp dropping st_size or st_ino, because a dropped field still reports every
    change those tests make. Here the rewrite keeps the inode and restores the exact
    stamped times, so only the size field can catch it."""
    path = str(tmp_path / 'pair.req.json')
    with open(path, 'wb') as f:
        f.write(b'{"ask": 1}')
    os.utime(path, ns=(10 ** 9, 10 ** 9))              # a fixed clock, no timing races
    st = os.stat(path)
    before = local._stamp(path)
    assert before == (st.st_mtime_ns, st.st_size, st.st_ino)   # the triple, in order
    with open(path, 'r+b') as f:                       # same inode, longer body
        f.write(b'{"ask": 1111111111111}')
    os.utime(path, ns=(10 ** 9, 10 ** 9))              # same mtime as the stamp
    after_stat = os.stat(path)
    assert after_stat.st_size != st.st_size
    assert local._stamp(path) != before                # the memo must judge it again
    assert local._stamp(path) == (after_stat.st_mtime_ns, after_stat.st_size,
                                  after_stat.st_ino)
