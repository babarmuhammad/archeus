"""Internal-session filter and Claude folder scan of claude_sessions/sessions.py (lines 455-506)."""
import json
import os

from claude_sessions import sessions as s

SDK = json.dumps({'type': 'user', 'entrypoint': 'sdk-cli'})
CLI = json.dumps({'type': 'user', 'entrypoint': 'cli', 'message': 'hi'})


def _write(path, lines):
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def test_sdk_cli_marker_is_seen_only_within_five_lines(tmp_path):
    inside = tmp_path / 'inside.jsonl'
    _write(inside, [CLI] * 4 + [SDK])
    outside = tmp_path / 'outside.jsonl'
    _write(outside, [CLI] * 5 + [SDK])
    assert s.is_internal_session(str(inside)) is True
    assert s.is_internal_session(str(outside)) is False


def test_malformed_marker_line_is_skipped_not_fatal(tmp_path):
    bad_then_sdk = tmp_path / 'bad_then_sdk.jsonl'
    _write(bad_then_sdk, ['{"x": "sdk-cli" broken', SDK])
    bad_then_cli = tmp_path / 'bad_then_cli.jsonl'
    _write(bad_then_cli, ['{"x": "sdk-cli" broken', CLI])
    assert s.is_internal_session(str(bad_then_sdk)) is True
    assert s.is_internal_session(str(bad_then_cli)) is False


def test_sdk_cli_text_outside_entrypoint_is_not_internal(tmp_path):
    f = tmp_path / 'tagged.jsonl'
    _write(f, [json.dumps({'entrypoint': 'cli', 'tag': 'sdk-cli'})])
    assert s.is_internal_session(str(f)) is False


def test_unreadable_transcript_is_not_internal(tmp_path):
    assert s.is_internal_session(str(tmp_path / 'missing.jsonl')) is False


def test_empty_transcript_is_not_internal(tmp_path):
    f = tmp_path / 'empty.jsonl'
    f.write_text('', encoding='utf-8')
    assert s.is_internal_session(str(f)) is False


def test_scan_missing_or_none_folder_is_empty(tmp_path):
    assert s._scan_claude(None) == []
    assert s._scan_claude(str(tmp_path / 'missing')) == []


def test_scan_skips_non_jsonl_and_vanished_files(tmp_path, monkeypatch):
    _write(tmp_path / 'keep.jsonl', [CLI])
    _write(tmp_path / 'gone.jsonl', [CLI])
    (tmp_path / 'notes.txt').write_text('x', encoding='utf-8')
    real_getmtime = os.path.getmtime

    def getmtime(p):
        if os.path.basename(p) == 'gone.jsonl':
            raise OSError('vanished')
        return real_getmtime(p)

    monkeypatch.setattr(s.os.path, 'getmtime', getmtime)
    monkeypatch.setattr(s, 'get_session_info', lambda p: ('hello there', 3))
    rows = s._scan_claude(str(tmp_path))
    assert [(sid, preview, count) for _m, sid, preview, count in rows] == [('keep', 'hello there', 3)]


def test_internal_file_is_never_parsed(tmp_path, monkeypatch):
    _write(tmp_path / 'int.jsonl', [SDK])
    _write(tmp_path / 'ext.jsonl', [CLI])
    parsed = []

    def fake_info(p):
        parsed.append(os.path.basename(p))
        return ('p', 1)

    monkeypatch.setattr(s, 'get_session_info', fake_info)
    rows = s._scan_claude(str(tmp_path))
    assert parsed == ['ext.jsonl']
    assert [r[1] for r in rows] == ['ext']


def test_rows_newest_first_then_sid_descending(tmp_path, monkeypatch):
    for name, mtime in (('a', 3000), ('b', 2000), ('c', 2000)):
        f = tmp_path / (name + '.jsonl')
        _write(f, [CLI])
        os.utime(f, (mtime, mtime))
    monkeypatch.setattr(s, 'get_session_info', lambda p: ('p', 1))
    rows = s._scan_claude(str(tmp_path))
    assert [(m, sid) for m, sid, _p, _c in rows] == [(3000, 'a'), (2000, 'c'), (2000, 'b')]


def test_scan_dispatches_on_of_path_id(tmp_path, monkeypatch):
    calls = []

    def fake_impl(key, hid=None):
        calls.append((key, hid))
        return lambda folder: ['rows', folder]

    monkeypatch.setattr(s._harnesses, 'impl', fake_impl)

    codex_home = tmp_path / 'codex'
    folder = str(codex_home / 'sessions')
    monkeypatch.setattr(s._harnesses, '_homes', lambda: [('codex', str(codex_home))])
    assert s.scan_sessions(folder) == ['rows', folder]
    assert calls == [('scan', 'codex')]

    calls.clear()
    monkeypatch.setattr(s._harnesses, '_homes', lambda: [])
    assert s.scan_sessions(str(tmp_path / 'proj')) == ['rows', str(tmp_path / 'proj')]
    assert calls == [('scan', 'claude')]
