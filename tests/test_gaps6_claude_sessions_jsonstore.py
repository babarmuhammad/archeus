"""T-1268: the ten highest-risk uncovered branches of claude_sessions/jsonstore.py,
source lines 25-83 (load, save, _copy, _quarantine) at worktree d429bf96.

Selected branches and the test that catches each one:
- 71 _quarantine: os.replace into a whole-second name; a second corrupt read in the
  same second clobbers the first quarantined file (strict xfail, defect at 69-71).
- 37-44 load: truncated JSON is moved aside and a detached copy of the default returned.
- 45-48 load: a wrong top-level type takes the corruption path; a valid empty
  expected type is accepted and not quarantined.
- 37-40 load: an absent file and a PermissionError return a copy with no move,
  no marker and no event.
- 42 load: quarantine=False leaves the corrupt file in place with no replace and no
  event; the default still isolates it.
- 49 load: a good parse clears only this absolute path's corruption marker.
- 72-74 _quarantine: a failed move records an empty destination and says so in the event.
- 77-82 _quarantine: an events.record that raises cannot change the marker or the
  returned destination.
- 35 load: a UTF-8 BOM is accepted; malformed UTF-8 is quarantined and the bytes
  are never written back.
- 57 save: one write_json_atomic call with the given path and data, its answer
  returned unchanged, and no direct write to the path.

Seams: time.time (module attribute `time` of jsonstore), events.record and
config.write_json_atomic are replaced; os.replace and builtins.open are wrapped only
for the one path a test names. Every file lives under tmp_path. No subprocess, no
network, no real home or settings.
"""

import builtins
import errno
import os

import pytest

from claude_sessions import config, events, jsonstore

STAMP = 1_700_000_000


class _Clock:
    def time(self):
        return STAMP


@pytest.fixture(autouse=True)
def recorded_events(monkeypatch):
    log = []
    monkeypatch.setattr(events, 'record', lambda *a, **k: log.append((a, k)) or True)
    jsonstore.last_corruption.clear()
    yield log
    jsonstore.last_corruption.clear()


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(jsonstore, 'time', _Clock())


def _corrupt_files(folder):
    return sorted(f for f in os.listdir(folder) if '.corrupt-' in f)


def _key(path):
    return os.path.abspath(str(path))


@pytest.mark.xfail(strict=True, reason=(
    'claude_sessions/jsonstore.py:69-71: the quarantine name is whole-second and '
    'os.replace overwrites an existing file, so the first corrupt evidence is lost'))
def test_second_corrupt_read_in_the_same_second_keeps_the_first_evidence(tmp_path, clock):
    p = tmp_path / 'state.json'
    p.write_text('{"first": ', encoding='utf-8')
    jsonstore.load(str(p), expect=dict)
    p.write_text('{"second": ', encoding='utf-8')
    jsonstore.load(str(p), expect=dict)
    kept = {(tmp_path / f).read_text(encoding='utf-8') for f in _corrupt_files(tmp_path)}
    assert '{"first": ' in kept


def test_truncated_json_is_moved_aside_and_a_detached_default_returned(tmp_path, clock,
                                                                       recorded_events):
    p = tmp_path / 'graph.json'
    raw = '{"entities": [1,2,3'
    p.write_text(raw, encoding='utf-8')
    default = {'entities': []}
    got = jsonstore.load(str(p), default, expect=dict)
    assert got == {'entities': []}
    got['added'] = 9
    assert default == {'entities': []}
    assert not p.exists()
    dest = tmp_path / ('graph.json.corrupt-%d' % STAMP)
    assert dest.read_text(encoding='utf-8') == raw
    assert jsonstore.last_corruption[_key(p)] == str(dest)
    assert len(recorded_events) == 1


def test_wrong_top_level_type_takes_the_corruption_path_and_empty_list_is_kept(
        tmp_path, clock, recorded_events):
    wrong = tmp_path / 'w.json'
    wrong.write_text('{"a": 1}', encoding='utf-8')
    assert jsonstore.load(str(wrong), [], expect=list) == []
    assert not wrong.exists()
    assert jsonstore.last_corruption[_key(wrong)]
    assert len(recorded_events) == 1

    ok = tmp_path / 'ok.json'
    ok.write_text('[]', encoding='utf-8')
    assert jsonstore.load(str(ok), [9], expect=list) == []
    assert ok.exists()
    assert _key(ok) not in jsonstore.last_corruption
    assert len(recorded_events) == 1


def test_absent_and_unreadable_files_return_a_copy_without_moving_anything(
        tmp_path, clock, recorded_events, monkeypatch):
    assert jsonstore.load(str(tmp_path / 'nope.json'), {'a': 1}) == {'a': 1}
    assert not jsonstore.last_corruption
    assert recorded_events == []

    locked = tmp_path / 'locked.json'
    locked.write_text('{"keep": true}', encoding='utf-8')
    real_open = builtins.open

    def deny(file, *a, **k):
        if os.fspath(file) == str(locked):
            raise PermissionError(errno.EACCES, 'synthetic denial', str(locked))
        return real_open(file, *a, **k)
    monkeypatch.setattr(builtins, 'open', deny)

    assert jsonstore.load(str(locked), {'a': 1}) == {'a': 1}
    assert locked.read_text(encoding='utf-8') == '{"keep": true}'
    assert _corrupt_files(tmp_path) == []
    assert not jsonstore.last_corruption
    assert recorded_events == []


def test_quarantine_false_leaves_the_corrupt_file_and_default_still_isolates(
        tmp_path, clock, recorded_events, monkeypatch):
    p = tmp_path / 'external.json'
    p.write_text('{"half": ', encoding='utf-8')
    moves = []
    real_replace = os.replace
    monkeypatch.setattr(os, 'replace', lambda s, d: (moves.append((s, d)), real_replace(s, d))[1])

    assert jsonstore.load(str(p), expect=dict, quarantine=False) == {}
    assert moves == []
    assert p.read_text(encoding='utf-8') == '{"half": '
    assert recorded_events == []
    assert not jsonstore.last_corruption

    assert jsonstore.load(str(p), expect=dict) == {}
    assert len(moves) == 1
    assert not p.exists()


def test_a_good_parse_clears_only_its_own_marker(tmp_path, clock):
    a = tmp_path / 'a.json'
    b = tmp_path / 'b.json'
    a.write_text('{"x": ', encoding='utf-8')
    b.write_text('{"y": ', encoding='utf-8')
    jsonstore.load(str(a), expect=dict)
    jsonstore.load(str(b), expect=dict)
    assert _key(a) in jsonstore.last_corruption and _key(b) in jsonstore.last_corruption

    a.write_text('{"ok": 1}', encoding='utf-8')
    assert jsonstore.load(str(a), expect=dict) == {'ok': 1}
    assert _key(a) not in jsonstore.last_corruption
    assert _key(b) in jsonstore.last_corruption


def test_a_failed_move_records_an_empty_destination_and_says_so(tmp_path, clock,
                                                                recorded_events, monkeypatch):
    p = tmp_path / 'locked.json'
    p.write_text('{"bad": ', encoding='utf-8')

    def refuse(src, dst):
        raise PermissionError(errno.EACCES, 'synthetic denial', src)
    monkeypatch.setattr(os, 'replace', refuse)

    assert jsonstore.load(str(p), expect=dict) == {}
    assert jsonstore.last_corruption[_key(p)] == ''
    assert p.exists()
    assert _corrupt_files(tmp_path) == []
    (args, kwargs), = recorded_events
    assert '(move failed)' in kwargs['detail']


def test_an_event_failure_during_quarantine_keeps_the_marker_and_the_destination(
        tmp_path, clock, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError('synthetic event store failure')
    monkeypatch.setattr(events, 'record', broken)

    p = tmp_path / 'state.json'
    p.write_text('{"x": ', encoding='utf-8')
    assert jsonstore.load(str(p), {'d': 1}, expect=dict) == {'d': 1}
    assert jsonstore.last_corruption[_key(p)] == str(tmp_path / ('state.json.corrupt-%d' % STAMP))

    q = tmp_path / 'other.json'
    q.write_text('{"y": ', encoding='utf-8')
    assert jsonstore._quarantine(str(q)) == str(tmp_path / ('other.json.corrupt-%d' % STAMP))


def test_a_bom_is_accepted_and_malformed_bytes_are_quarantined_never_rewritten(
        tmp_path, clock, recorded_events):
    bom = tmp_path / 'bom.json'
    bom.write_bytes(b'\xef\xbb\xbf{"a": 1}')
    assert jsonstore.load(str(bom), expect=dict) == {'a': 1}
    assert bom.read_bytes() == b'\xef\xbb\xbf{"a": 1}'
    assert recorded_events == []

    bad = tmp_path / 'bad.json'
    bad.write_bytes(b'{"a": "\xff"}')
    assert jsonstore.load(str(bad), expect=dict) == {}
    assert not bad.exists()
    moved = tmp_path / ('bad.json.corrupt-%d' % STAMP)
    assert moved.read_bytes() == b'{"a": "\xff"}'


def test_save_makes_one_atomic_write_and_returns_its_answer(tmp_path, monkeypatch):
    calls = []
    answer = {'value': False}
    monkeypatch.setattr(config, 'write_json_atomic',
                        lambda path, data, **kw: calls.append((path, data, kw)) or answer['value'])
    target = str(tmp_path / 's.json')

    assert jsonstore.save(target, {'a': 1}) is False
    assert calls == [(target, {'a': 1}, {})]
    assert not os.path.exists(target)

    answer['value'] = True
    assert jsonstore.save(target, {'b': 2}) is True
    assert calls[-1] == (target, {'b': 2}, {})
