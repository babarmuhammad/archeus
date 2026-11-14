"""T-1356: claude_sessions/transcript.py lines 143-237 at tip 10d688c0 (the
view_transcript pager loop, export_transcript naming, target choice and
failure, and _slug).

Selected candidates, not measured coverage. Ranked denial/fail-closed first,
then boundaries, then error paths:

1.  224-225  missing or non-writable project_path falls back to proj_folder;
             a writable one wins
    -> test_export_falls_back_to_proj_folder_when_project_path_not_writable
       test_export_falls_back_to_proj_folder_when_project_path_missing
       test_export_writes_into_writable_project_path
2.  227-229  an existing claude-session file is never overwritten; a stamped
             name is used instead
    -> test_export_never_overwrites_existing_file_and_uses_stamped_name
       test_export_never_overwrites_when_stamped_name_also_exists (strict xfail)
3.  231-235  write failure returns (False, 'Export failed: ...') and
             open_in_editor is not called
    -> test_export_write_failure_returns_false_and_skips_editor
4.  200-201  _slug removes separators and dots, an empty result becomes
             'session', the result is capped at 40 characters
    -> test_export_title_slug_keeps_file_inside_target_dir
5.  213      title falls back name, stats title, then the first 8 characters of sid
    -> test_export_heading_title_fallback_chain
6.  214-215  metadata lines pass through render.strip_ansi, so no escape bytes
             reach the file
    -> test_export_metadata_lines_carry_no_escape_bytes
       test_export_file_carries_no_escape_bytes (strict xfail)
7.  217-218  a role other than 'user' gets the Assistant heading
    -> test_export_non_user_role_gets_assistant_heading
8.  177-179  no conversation text gives the placeholder line and empty marks
    -> test_viewer_with_no_conversation_shows_placeholder_and_no_marks
9.  188-195  'i' toggles the header and redraws; 'e' exports and flashes;
             any other key returns
    -> test_viewer_key_loop_toggles_info_exports_then_returns_on_other_key
10. 163-166  a zero-epoch or unparseable timestamp shows no time and no
             exception escapes the pager build
    -> test_viewer_zero_epoch_or_bad_timestamp_shows_no_time
       test_viewer_valid_timestamp_shows_local_hour_minute

Seams: tmp_path project and work folders; transcript.iter_transcript,
transcript.load_name, transcript.open_in_editor, transcript.store.transcript_path,
stats.get_session_stats_cached, ui.pager and ui.flash are faked. The stats and
ui names are patched at their defining module because view_transcript and
export_transcript import them inside the function body. The stamped name is
driven by a fixed datetime subclass.
"""

import datetime as _dt
import os

import pytest

import claude_sessions.render as render_mod
import claude_sessions.stats as stats_mod
import claude_sessions.transcript as transcript
import claude_sessions.ui as ui_mod
from claude_sessions.config import C_ACCENT, C_DIM, C_OK, C_RESET

SID = 'abcdef1234567'
STAMP = '20261114-032005'


class FixedDatetime(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 14, 3, 20, 5)


def _msg(role, text, ts=''):
    return {'role': role, 'text': text, 'ts': ts}


def _seed(monkeypatch, tmp_path, *, msgs=(), name=None, stats=None):
    proj = tmp_path / 'proj'
    proj.mkdir(exist_ok=True)
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    editor = []
    monkeypatch.setattr(transcript.store, 'transcript_path',
                        lambda folder, sid: str(tmp_path / 'x.jsonl'))
    monkeypatch.setattr(transcript, 'iter_transcript',
                        lambda path, **kw: list(msgs))
    monkeypatch.setattr(transcript, 'load_name', lambda folder, sid: name)
    monkeypatch.setattr(stats_mod, 'get_session_stats_cached',
                        lambda path: dict(stats or {}))
    monkeypatch.setattr(transcript, 'open_in_editor', lambda p: editor.append(p))
    monkeypatch.setattr(render_mod, 'content_width', lambda: 80)
    return proj, work, editor


def _pager_script(monkeypatch, keys):
    calls = []
    script = list(keys)

    def fake_pager(crumbs, lines, **kw):
        calls.append({'lines': list(lines), **kw})
        return script.pop(0)

    flashes = []
    monkeypatch.setattr(ui_mod, 'pager', fake_pager)
    monkeypatch.setattr(ui_mod, 'flash', lambda msg, **kw: flashes.append((msg, kw)))
    return calls, flashes


def _export(proj, work):
    return transcript.export_transcript(str(proj), SID, str(work))


def test_export_falls_back_to_proj_folder_when_project_path_not_writable(monkeypatch, tmp_path):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')], name='Plan')
    real_access = os.access
    work_abs = os.path.abspath(str(work))
    monkeypatch.setattr(
        transcript.os, 'access',
        lambda p, mode: False if os.path.abspath(p) == work_abs else real_access(p, mode))
    ok, msg = _export(proj, work)
    assert ok is True
    assert os.path.isfile(proj / 'claude-session-Plan.md')
    assert os.listdir(work) == []
    assert editor == [str(proj / 'claude-session-Plan.md')]


def test_export_falls_back_to_proj_folder_when_project_path_missing(monkeypatch, tmp_path):
    proj, _work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')], name='Plan')
    gone = tmp_path / 'gone'
    ok, msg = transcript.export_transcript(str(proj), SID, str(gone))
    assert ok is True
    assert os.path.isfile(proj / 'claude-session-Plan.md')
    assert not gone.exists()


def test_export_writes_into_writable_project_path(monkeypatch, tmp_path):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')], name='Plan')
    ok, msg = _export(proj, work)
    assert ok is True
    assert os.listdir(work) == ['claude-session-Plan.md']
    assert os.listdir(proj) == []
    assert msg == 'Exported claude-session-Plan.md'


def test_export_never_overwrites_existing_file_and_uses_stamped_name(monkeypatch, tmp_path):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')], name='Plan')
    monkeypatch.setattr(transcript, 'datetime', FixedDatetime)
    base = work / 'claude-session-Plan.md'
    base.write_text('OLD-BASE', encoding='utf-8')
    ok, msg = _export(proj, work)
    assert ok is True
    assert base.read_text(encoding='utf-8') == 'OLD-BASE'
    stamped = work / f'claude-session-Plan-{STAMP}.md'
    assert msg == f'Exported {stamped.name}'
    assert 'hi' in stamped.read_text(encoding='utf-8')
    assert editor == [str(stamped)]


def test_export_never_overwrites_when_stamped_name_also_exists(monkeypatch, tmp_path):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')], name='Plan')
    monkeypatch.setattr(transcript, 'datetime', FixedDatetime)
    base = work / 'claude-session-Plan.md'
    stamped = work / f'claude-session-Plan-{STAMP}.md'
    base.write_text('OLD-BASE', encoding='utf-8')
    stamped.write_text('OLD-STAMP', encoding='utf-8')
    _export(proj, work)
    assert base.read_text(encoding='utf-8') == 'OLD-BASE'
    assert stamped.read_text(encoding='utf-8') == 'OLD-STAMP'


def test_export_write_failure_returns_false_and_skips_editor(monkeypatch, tmp_path):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')], name='Plan')

    def failing_open(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(transcript, 'open', failing_open, raising=False)
    ok, msg = _export(proj, work)
    assert ok is False
    assert msg == 'Export failed: disk full'
    assert editor == []


@pytest.mark.parametrize('title, fname', [
    ('../x', 'claude-session-x.md'),
    ('..\\..\\evil', 'claude-session-evil.md'),
    ('***', 'claude-session-session.md'),
    ('a' * 100, 'claude-session-' + 'a' * 40 + '.md'),
])
def test_export_title_slug_keeps_file_inside_target_dir(monkeypatch, tmp_path, title, fname):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')], name=title)
    ok, msg = _export(proj, work)
    assert ok is True
    assert os.listdir(work) == [fname]
    assert os.listdir(proj) == []
    assert editor == [str(work / fname)]


@pytest.mark.parametrize('name, stats_title, heading', [
    ('', 'Stat T', '# Claude session — Stat T'),
    ('', '', f'# Claude session — {SID[:8]}'),
    ('Named', 'Stat T', '# Claude session — Named'),
])
def test_export_heading_title_fallback_chain(monkeypatch, tmp_path, name, stats_title, heading):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')],
                               name=name, stats={'title': stats_title})
    ok, _ = _export(proj, work)
    assert ok is True
    content = (work / os.listdir(work)[0]).read_text(encoding='utf-8')
    assert content.splitlines()[0] == heading


ESC_NAME = '\x1b[31mRed\x1b[0m'


def test_export_metadata_lines_carry_no_escape_bytes(monkeypatch, tmp_path):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')],
                               name=ESC_NAME, stats={'cwd': '\x1b[2Jdir'})
    ok, _ = _export(proj, work)
    assert ok is True
    content = (work / os.listdir(work)[0]).read_text(encoding='utf-8')
    meta = [ln for ln in content.splitlines() if ln.startswith('- ')]
    assert any('Red' in ln for ln in meta)
    assert not any('\x1b' in ln for ln in meta)


def test_export_file_carries_no_escape_bytes(monkeypatch, tmp_path):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')],
                               name=ESC_NAME, stats={'cwd': '\x1b[2Jdir'})
    _export(proj, work)
    content = (work / os.listdir(work)[0]).read_text(encoding='utf-8')
    assert '\x1b' not in content


def test_export_non_user_role_gets_assistant_heading(monkeypatch, tmp_path):
    msgs = [_msg('system', 'note'), _msg('user', 'hi')]
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=msgs, name='Plan')
    _export(proj, work)
    content = (work / os.listdir(work)[0]).read_text(encoding='utf-8')
    lines = content.splitlines()
    assert lines.count('### Assistant') == 1
    assert lines.count('### User') == 1
    assert lines.index('### Assistant') < lines.index('### User')


def test_viewer_with_no_conversation_shows_placeholder_and_no_marks(monkeypatch, tmp_path):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[])
    calls, _ = _pager_script(monkeypatch, ['z'])
    transcript.view_transcript(str(proj), SID, 'proj', str(work))
    assert calls[0]['lines'] == [f"{C_DIM}(no conversation text in this session){C_RESET}"]
    assert calls[0]['marks'] == []


def test_viewer_key_loop_toggles_info_exports_then_returns_on_other_key(monkeypatch, tmp_path):
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'hi')], name='Plan')
    calls, flashes = _pager_script(monkeypatch, ['i', 'e', 'z'])
    transcript.view_transcript(str(proj), SID, 'proj', str(work))
    assert len(calls) == 3
    assert calls[0]['header_lines'] is None
    assert calls[1]['header_lines'] and 'Plan' in calls[1]['header_lines'][0]
    assert calls[2]['header_lines'] is not None
    assert os.listdir(work) == ['claude-session-Plan.md']
    assert flashes == [('Exported claude-session-Plan.md', {'ok': True, 'secs': 1.2})]
    assert editor == [str(work / 'claude-session-Plan.md')]


def test_viewer_zero_epoch_or_bad_timestamp_shows_no_time(monkeypatch, tmp_path):
    msgs = [_msg('user', 'a', '1970-01-01T00:00:00Z'), _msg('assistant', 'b', 'not-a-time')]
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=msgs)
    calls, _ = _pager_script(monkeypatch, ['z'])
    transcript.view_transcript(str(proj), SID, 'proj', str(work))
    lines, marks = calls[0]['lines'], calls[0]['marks']
    assert lines[marks[0]] == f"{C_ACCENT}▸ You{C_RESET}"
    assert lines[marks[1]] == f"{C_OK}▸ Claude{C_RESET}"


def test_viewer_valid_timestamp_shows_local_hour_minute(monkeypatch, tmp_path):
    ts = '2026-11-14T03:20:00+00:00'
    expected = _dt.datetime.fromtimestamp(
        _dt.datetime.fromisoformat(ts).timestamp()).strftime('%H:%M')
    proj, work, editor = _seed(monkeypatch, tmp_path, msgs=[_msg('user', 'a', ts)])
    calls, _ = _pager_script(monkeypatch, ['z'])
    transcript.view_transcript(str(proj), SID, 'proj', str(work))
    lines, marks = calls[0]['lines'], calls[0]['marks']
    assert lines[marks[0]] == f"{C_ACCENT}▸ You{C_RESET}  {C_DIM}{expected}{C_RESET}"
