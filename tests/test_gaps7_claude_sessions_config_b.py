"""T-1303 — close the highest-risk test gaps in claude_sessions/config.py,
lines 763-830 inclusive (tip 53865a4a of pv20-fx79n; re-located by reading the
source, the card's line numbers came from an older tip).

Slice: `write_atomic()` temp ownership, descriptor closure and mode handling,
and `write_json_atomic()`.

Selected branches, denial/fail-closed first, then boundaries, then error paths:

 1. :801  fdopen OSError after a real owned descriptor: the descriptor is
          closed, the owned temp is removed, the target is unchanged
 2. :802  fdopen BaseException: the descriptor is closed and the exception
          propagates; the outer Exception-only cleanup is not demanded
 3. :797  a foreign file already holds the generated temp name: O_EXCL refuses,
          the foreign file is neither deleted nor truncated
 4. :821  os.open fails before creation: no unlink of a guessed temp name
 5. :806  a write failure after creation closes the stream and deletes only the
          owned temp; a sibling temp is untouched
 6. :823  the cleanup unlink itself fails: the False result is kept and the
          unrelated sibling is untouched
 7. :798  Linux: the temp is created 0600, verified at the replace seam and on
          the final path; no chmod
 8. :798  mode=None creates with 0666; mode=0640 is passed through and never
          broadens the final file
 9. :796  different thread identities produce different temp names even with
          the same token
10. :830  unserializable JSON raises before any temp is opened; valid unicode
          JSON passes through the exact writer result and mode

Closest existing tests (tests/test_encoding_and_atomicity.py): a failed fdopen
closing the raw descriptor, a name collision not deleting the file, and a
secret file created with its mode. Those assert the outcome; these probes pin
the BaseException path, the unlink-of-guessed-name absence, the cleanup failure
and the exact os.open mode argument.

Fakes are installed with monkeypatch on os and secrets for the duration of one
test; every file lives under tmp_path. Mode-bit probes are POSIX-only and say so.
"""

import json
import os
import threading

import pytest

from claude_sessions import config as _c

POSIX = os.name == 'posix'


class _Sentinel(BaseException):
    pass


def _temps(d):
    return sorted(f.name for f in d.iterdir() if f.name.endswith('.tmp'))


def _recording_open(monkeypatch, opened):
    """Wrap os.open: record (name, flags, mode, fd) for every O_EXCL create and
    keep the real behaviour."""
    real_open = os.open

    def wrapper(path, flags, mode=0o777, *a, **k):
        fd = real_open(path, flags, mode, *a, **k)
        if flags & os.O_EXCL:
            opened.append({'name': path, 'mode': mode, 'fd': fd})
        return fd

    monkeypatch.setattr(os, 'open', wrapper)


def _fd_is_closed(fd):
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


def test_a_failed_fdopen_closes_the_owned_descriptor_and_removes_the_temp(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    opened = []
    _recording_open(monkeypatch, opened)

    def broken_fdopen(fd, *a, **k):
        raise OSError('simulated fdopen failure')

    monkeypatch.setattr(os, 'fdopen', broken_fdopen)
    assert _c.write_json_atomic(str(p), {'new': True}) is False
    assert len(opened) == 1
    assert _fd_is_closed(opened[0]['fd'])
    assert not os.path.exists(opened[0]['name'])
    assert p.read_text(encoding='utf-8') == '{"old": true}'
    assert _temps(tmp_path) == []


def test_a_base_exception_from_fdopen_closes_the_descriptor_and_propagates(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    opened = []
    _recording_open(monkeypatch, opened)

    def sentinel_fdopen(fd, *a, **k):
        raise _Sentinel()

    monkeypatch.setattr(os, 'fdopen', sentinel_fdopen)
    with pytest.raises(_Sentinel):
        _c.write_atomic(str(p), 'new')
    assert len(opened) == 1
    assert _fd_is_closed(opened[0]['fd'])
    assert p.read_text(encoding='utf-8') == '{"old": true}'


def test_a_foreign_file_at_the_generated_temp_name_is_neither_deleted_nor_truncated(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    monkeypatch.setattr(_c.secrets, 'token_hex', lambda n: 'cafe0001')
    foreign = tmp_path / f'settings.json.{os.getpid()}.{threading.get_ident()}.cafe0001.tmp'
    foreign.write_bytes(b'foreign data that must survive')
    assert _c.write_json_atomic(str(p), {'new': True}) is False
    assert foreign.read_bytes() == b'foreign data that must survive'
    assert p.read_text(encoding='utf-8') == '{"old": true}'


def test_an_open_failure_before_creation_never_unlinks_a_guessed_name(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    unlinked = []
    real_open = os.open
    real_unlink = os.unlink

    def refused_create(path, flags, mode=0o777, *a, **k):
        if flags & os.O_EXCL:
            raise PermissionError(13, 'Access is denied', path)
        return real_open(path, flags, mode, *a, **k)

    def recording_unlink(path, *a, **k):
        unlinked.append(path)
        return real_unlink(path, *a, **k)

    monkeypatch.setattr(os, 'open', refused_create)
    monkeypatch.setattr(os, 'unlink', recording_unlink)
    assert _c.write_json_atomic(str(p), {'new': True}) is False
    assert unlinked == []
    assert p.read_text(encoding='utf-8') == '{"old": true}'
    assert _temps(tmp_path) == []


def test_a_write_failure_after_creation_closes_the_stream_and_deletes_only_the_owned_temp(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    sibling = tmp_path / 'settings.json.other.tmp'
    sibling.write_text('sibling', encoding='utf-8')
    opened = []
    _recording_open(monkeypatch, opened)
    assert _c.write_atomic(str(p), 'bad \ud800 surrogate') is False
    assert len(opened) == 1
    assert not os.path.exists(opened[0]['name'])
    assert _fd_is_closed(opened[0]['fd'])
    assert p.read_text(encoding='utf-8') == '{"old": true}'
    assert sibling.read_text(encoding='utf-8') == 'sibling'


def test_a_failing_cleanup_unlink_keeps_the_false_result_and_leaves_siblings_alone(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    sibling = tmp_path / 'settings.json.other.tmp'
    sibling.write_text('sibling', encoding='utf-8')
    unlink_attempts = []

    def failing_replace(src, dst):
        raise OSError('simulated replace failure')

    def failing_unlink(path, *a, **k):
        unlink_attempts.append(path)
        raise OSError('simulated unlink failure')

    monkeypatch.setattr(os, 'replace', failing_replace)
    monkeypatch.setattr(os, 'unlink', failing_unlink)
    assert _c.write_atomic(str(p), 'new') is False
    assert len(unlink_attempts) == 1
    assert unlink_attempts[0].startswith(str(p) + '.')
    assert unlink_attempts[0] != str(sibling)
    assert sibling.read_text(encoding='utf-8') == 'sibling'
    assert p.read_text(encoding='utf-8') == '{"old": true}'


@pytest.mark.skipif(not POSIX, reason="POSIX mode bits; Windows ignores the 0600 request")
def test_a_0600_temp_is_created_that_way_and_the_final_file_keeps_it(tmp_path, monkeypatch):
    p = tmp_path / 'secret.json'
    opened = []
    _recording_open(monkeypatch, opened)
    real_replace = os.replace
    seen_at_replace = []

    def replace(src, dst):
        seen_at_replace.append(os.stat(src).st_mode & 0o777)
        return real_replace(src, dst)

    monkeypatch.setattr(os, 'replace', replace)
    assert _c.write_json_atomic(str(p), {'k': 'v'}, mode=0o600) is True
    assert opened[0]['mode'] == 0o600
    assert seen_at_replace == [0o600]
    assert os.stat(p).st_mode & 0o777 & ~0o600 == 0


def test_mode_none_creates_with_0666_and_mode_0640_is_passed_through_exactly(tmp_path, monkeypatch):
    opened = []
    _recording_open(monkeypatch, opened)
    assert _c.write_atomic(str(tmp_path / 'plain.txt'), 'x') is True
    assert _c.write_atomic(str(tmp_path / 'group.txt'), 'y', mode=0o640) is True
    assert [o['mode'] for o in opened] == [0o666, 0o640]


@pytest.mark.skipif(not POSIX, reason="POSIX mode bits; Windows reports only the read-only flag")
def test_mode_0640_never_broadens_the_final_file_past_0640(tmp_path):
    q = tmp_path / 'group.txt'
    assert _c.write_atomic(str(q), 'y', mode=0o640) is True
    assert os.stat(q).st_mode & 0o777 & ~0o640 == 0


def test_identical_tokens_under_different_thread_identities_make_different_names(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    opened = []
    _recording_open(monkeypatch, opened)
    monkeypatch.setattr(_c.secrets, 'token_hex', lambda n: 'abcd0002')
    idents = [1111, 2222]
    real_ident = threading.get_ident
    monkeypatch.setattr(_c.threading, 'get_ident',
                        lambda: idents.pop(0) if idents else real_ident())
    assert _c.write_atomic(str(p), 'first') is True
    assert _c.write_atomic(str(p), 'second') is True
    names = [os.path.basename(o['name']) for o in opened]
    assert names[0] != names[1]
    assert names[0].endswith('.1111.abcd0002.tmp')
    assert names[1].endswith('.2222.abcd0002.tmp')
    assert p.read_text(encoding='utf-8') == 'second'
    assert _temps(tmp_path) == []


def test_unserializable_json_raises_before_any_temp_is_opened(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    p.write_text('{"old": true}', encoding='utf-8')
    opened = []
    _recording_open(monkeypatch, opened)
    with pytest.raises(TypeError):
        _c.write_json_atomic(str(p), {'bad': object()})
    assert opened == []
    assert p.read_text(encoding='utf-8') == '{"old": true}'
    assert _temps(tmp_path) == []


def test_valid_unicode_json_passes_indent_and_mode_through_the_writer(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    opened = []
    _recording_open(monkeypatch, opened)
    obj = {'nome': 'perché €', 'lista': [1, 2]}
    assert _c.write_json_atomic(str(p), obj, indent=4, mode=0o600) is True
    assert opened[0]['mode'] == 0o600
    assert p.read_bytes() == json.dumps(obj, indent=4).encode('utf-8')
    assert json.loads(p.read_text(encoding='utf-8')) == obj
