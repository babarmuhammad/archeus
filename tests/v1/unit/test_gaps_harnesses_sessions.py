"""T-722: the highest-risk gaps in archeus/harnesses/sessions.py — the fail-closed
and denial paths of discovery, of `locate` answering about hostile provider state,
of `turns` parsing malformed transcripts, and of `find` refusing to guess.

Style and seams copied from the closest existing tests of this module,
tests/v1/unit/test_session_units.py and tests/v1/unit/test_pi_discovery.py:
every OS call goes through those seams (`claude_sessions.config.get_claude_exe`,
`harnesses.exe/disabled`, `launch.build_launch_command`), every byte on disk is
written through tmp_path with explicit newlines, and nothing spawns a process.
The test marked xfail(strict=True) documents a parsed-hostile-input path where
THE SOURCE is wrong (the real Claude/pi readers survive what FakeSessions
crashes on).
"""

import json
import os

import pytest

from archeus.harnesses.sessions import ClaudeCodeSessions, FakeSessions, PiSessions, SessionSpec
from claude_sessions import config, harnesses, launch, paths, store

#: a fixed wall-clock epoch for the pi `find` boundary tests; mtimes are set,
#: never slept, so these are deterministic on every platform
BASE = 1700000000.0


def _write_lines(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for line in lines:
            f.write(line + '\n')


def _write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


# ── FakeSessions: discovery, locate denial, launch, hostile transcripts ─────

def test_the_fake_discovery_announces_no_source_when_not_installed():
    on = FakeSessions('f_d').discover()
    assert (on.id, on.installed, on.executable) == ('f_d', True, 'fake')
    off = FakeSessions('f_d', installed=False).discover()
    assert (off.installed, off.executable, off.version) == (False, None, None)


def test_the_fake_locate_refuses_an_empty_ref_and_a_missing_file(archeus_home):
    a = FakeSessions('f_loc')
    assert a.locate(None, None, '/w') is None
    assert a.locate('', None, '/w') is None
    assert a.locate('never-written', None, '/w') is None
    p = a.write('here', [('user', 'x')])
    got = a.locate('here', None, '/w')
    assert got is not None and got.transcript_path == p


def test_resuming_a_fake_session_never_rewrites_its_transcript(archeus_home):
    a = FakeSessions('f_res')
    p = a.write('ref-1', [('user', 'precious')])
    got = a.launch_argv(SessionSpec('ses_1', '/w', resume_ref='ref-1'))
    assert got.ref == 'ref-1'
    assert a.turns(p, 5) == [('user', 'precious')]        # always-writing would empty this
    assert [s.resume_ref for s in a.launched] == ['ref-1']
    new = a.launch_argv(SessionSpec('ses_2', '/w'))
    assert new.ref != 'ref-1'
    assert a.locate(new.ref, None, '/w') is not None      # a new launch leaves an empty file
    assert a.turns(a.path(new.ref), 5) == []


def test_the_fake_turns_survive_a_garbage_transcript(archeus_home):
    a = FakeSessions('f_garb')
    p = a.path('r1')
    _write_lines(p, ['',
                     '   ',
                     '{not json at all',
                     '{"role": "system", "text": "not a turn"}',
                     '{"role": "user"}',
                     '{"role": "user", "text": ""}',
                     '{"role": "assistant", "text": 42}',
                     '{"role": "user", "text": "h\\u00e9llo"}'])
    assert a.turns(p, 10) == [('assistant', '42'), ('user', 'h\u00e9llo')]   # str() on a number
    assert a.turns(p, 1) == [('user', 'h\u00e9llo')]                         # tail, not head


def test_the_fake_turns_drop_a_json_line_that_is_not_an_object(archeus_home):
    a = FakeSessions('f_nd')
    p = a.path('r1')
    _write_lines(p, ['123', '"just a string"', '[1, 2]', 'null', 'true',
                     '{"role": "assistant", "text": "kept"}'])
    assert a.turns(p, 5) == [('assistant', 'kept')]


@pytest.mark.xfail(strict=True,
                   reason='sessions.py:117 — FakeSessions.turns opens the transcript '
                          'without errors="replace", so a byte string that is not valid '
                          'UTF-8 raises UnicodeDecodeError; the real reader '
                          '(transcripts.iter_json) replaces and never raises')
def test_the_fake_turns_survive_invalid_utf8(archeus_home):
    a = FakeSessions('f_utf')
    p = a.path('r1')
    _write_bytes(p, b'{"role": "assistant", "text": "kept"}\n\xff\xfe not utf-8\n')
    assert a.turns(p, 5) == [('assistant', 'kept')]


def test_an_empty_effort_level_is_never_offered():
    caps = FakeSessions('f_caps', models=('m1', 'm2'), efforts=('low', '', None)).capabilities()
    assert caps.efforts == ('low',)
    assert caps.capabilities == frozenset({'interactive', 'resume'})
    assert caps.enforcement == 'none'
    assert [m.id for m in caps.models] == ['m1', 'm2']


# ── Claude Code: discovery, locate denial and hostile model claims ───────────

def test_claude_code_discovery_only_reports_installed_when_the_exe_is_found(monkeypatch,
                                                                             tmp_path):
    monkeypatch.setattr(config, 'get_claude_exe', lambda: None)
    gone = ClaudeCodeSessions().discover()
    assert (gone.id, gone.installed, gone.executable, gone.version) == \
        ('claude_code', False, None, None)
    exe = str(tmp_path / 'claude.exe')
    monkeypatch.setattr(config, 'get_claude_exe', lambda: exe)
    on = ClaudeCodeSessions().discover()
    assert on.installed is True and on.executable == exe


def _cc_rig(tmp_path):
    """(home, cwd, project folder) with the folder real but empty of transcripts."""
    home = tmp_path / 'cfg'
    cwd = tmp_path / 'work'
    cwd.mkdir(exist_ok=True)
    folder = os.path.join(str(home), 'projects', paths.encode_component(str(cwd)))
    os.makedirs(folder, exist_ok=True)
    return str(home), str(cwd), folder


@pytest.mark.parametrize('ref', ['../escape', 'a/b'], ids=('parent', 'nested'))
def test_claude_code_locate_refuses_a_ref_that_is_a_path(tmp_path, ref):
    home, cwd, folder = _cc_rig(tmp_path)
    line = '{"message": {"model": "claude-sonnet-4-5"}}'
    _write_lines(os.path.join(home, 'projects', 'escape.jsonl'), [line])  # reachable by ../escape
    _write_lines(os.path.join(folder, 'a', 'b.jsonl'), [line])            # reachable by a/b
    assert ClaudeCodeSessions().locate(ref, home, cwd) is None


def test_claude_code_locate_refuses_when_the_project_folder_cannot_be_named(tmp_path,
                                                                             monkeypatch):
    home, cwd, _folder = _cc_rig(tmp_path)

    def boom(cfgdir, enc):
        raise ValueError('not a project folder name: %r' % enc)

    monkeypatch.setattr(store, 'project_folder', boom)
    assert ClaudeCodeSessions().locate('abc123', home, cwd) is None


def test_claude_code_locate_refuses_a_transcript_that_is_not_a_file(tmp_path):
    home, cwd, folder = _cc_rig(tmp_path)
    os.makedirs(os.path.join(folder, 'dir-ref.jsonl'))       # a directory wearing .jsonl
    a = ClaudeCodeSessions()
    assert a.locate('no-file', home, cwd) is None
    assert a.locate('dir-ref', home, cwd) is None


def test_claude_code_locate_reports_the_transcript_and_claims_no_model_from_it(tmp_path):
    home, cwd, folder = _cc_rig(tmp_path)
    _write_lines(os.path.join(folder, 'ref-1.jsonl'),
                 ['{"message": {"model": "model-a"}}',
                  '{"message": {"model": "',                    # garbage: never raises
                  '{"message": {"model": "<synthetic>"}}'])
    got = ClaudeCodeSessions().locate('ref-1', home, cwd)
    assert got is not None
    assert got.transcript_path == os.path.join(folder, 'ref-1.jsonl')
    assert got.model is None and got.effort is None


def test_claude_code_turns_keep_only_conversation_text(tmp_path):
    p = str(tmp_path / 'transcript.jsonl')
    _write_lines(p, [json.dumps(o) for o in [
        {'message': {'role': 'user', 'content': 'hello'}},
        {'message': {'role': 'assistant', 'content': [{'type': 'thinking', 'text': 'hidden'},
                                                      {'type': 'tool_use', 'name': 'Bash'}]}},
        {'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'done'}]}},
        {'isApiErrorMessage': True, 'message': {'role': 'assistant', 'content': 'api glitch'}},
        {'message': {'role': 'toolResult', 'content': 'tool noise'}},
        {'type': 'summary', 'summary': 'not a message'},
        {'message': {'role': 'user', 'content': {'a': 1}}},          # hostile content shape
        {'message': {'role': 'user', 'content': [{'type': 'text', 'text': '  '},
                                                 {'type': 'text', 'text': 'and now?'}]}},
    ]])
    a = ClaudeCodeSessions()
    assert a.turns(p, 10) == [('user', 'hello'), ('assistant', 'done'), ('user', 'and now?')]
    assert a.turns(p, 2) == [('assistant', 'done'), ('user', 'and now?')]   # tail, not head


# ── the launch argv through the faked build_launch_command seam ──────────────

class _Builder:
    """`launch.build_launch_command` answering a canned argv and recording every call."""

    def __init__(self, args, env=None):
        self.args, self.env, self.calls = args, dict(env or {}), []

    def __call__(self, path, encoded_name, choice, opts):
        self.calls.append({'path': path, 'encoded': encoded_name,
                           'choice': choice, 'opts': dict(opts)})
        return list(self.args), dict(self.env), None


@pytest.fixture
def builder(monkeypatch):
    def install(args, env=None):
        fake = _Builder(args, env)
        monkeypatch.setattr(launch, 'build_launch_command', fake)
        return fake

    return install


def test_a_new_claude_launch_invents_no_ref_the_builder_never_named(builder, tmp_path):
    b = builder(['claude.exe'])                                  # no --session-id in the argv
    got = ClaudeCodeSessions().launch_argv(
        SessionSpec('ses_1', str(tmp_path), home=str(tmp_path / 'cfg')))
    assert got.ref is None                                       # never a guess
    (call,) = b.calls
    assert call['choice'] == 'new'
    assert call['encoded'] == paths.encode_component(str(tmp_path))
    assert call['opts']['cfgdir'] == str(tmp_path / 'cfg')


def test_a_claude_resume_asks_for_the_ref_it_was_given(builder, tmp_path):
    b = builder(['claude.exe'])
    got = ClaudeCodeSessions().launch_argv(
        SessionSpec('ses_1', str(tmp_path), home=str(tmp_path / 'cfg'),
                    resume_ref='abc-123', opening='read it'))
    (call,) = b.calls
    assert call['choice'] == 'resume:abc-123'
    assert call['opts']['prompt'] == 'read it'
    assert got.ref == 'abc-123'


def test_the_launch_command_is_a_copy_not_an_alias(builder, tmp_path):
    args, env = ['claude.exe'], {'K': 'mine'}
    builder(args, env)
    got = ClaudeCodeSessions().launch_argv(
        SessionSpec('ses_1', str(tmp_path), home=str(tmp_path / 'cfg'), resume_ref='r-1'))
    args.append('planted')
    env['K'] = 'tampered'
    assert got.argv == ['claude.exe'] and got.env == {'K': 'mine'}


def test_a_new_pi_launch_never_borrows_a_ref(builder, tmp_path):
    b = builder(['pi.cmd'])
    got = PiSessions().launch_argv(
        SessionSpec('ses_1', str(tmp_path), home=str(tmp_path / 'pi-home'),
                    model='anthropic/claude-y'))
    (call,) = b.calls
    assert call['choice'] == 'new'
    assert got.ref is None                                       # pi names its own sessions
    assert call['opts']['model'] == 'anthropic/claude-y'         # pi vocabulary passes through


# ── pi: discovery, locate denial, find refusing to guess, hostile records ────

def test_a_disabled_pi_is_never_installed_even_with_its_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: str(tmp_path / 'pi.cmd'))
    monkeypatch.setattr(harnesses, 'disabled', lambda: {'pi'})
    got = PiSessions().discover()
    assert (got.id, got.installed, got.executable) == ('pi', False, None)


def test_pi_discovery_follows_the_binary(monkeypatch, tmp_path):
    exe = str(tmp_path / 'pi.cmd')
    monkeypatch.setattr(harnesses, 'disabled', lambda: set())
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: exe)
    on = PiSessions().discover()
    assert on.installed is True and on.executable == exe
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: None)
    gone = PiSessions().discover()
    assert gone.installed is False and gone.executable is None


def _pi_rig(tmp_path):
    """(home, cwd) with the sidecar project folder and pi's own sessions dir real."""
    home = tmp_path / 'pihome'
    cwd = tmp_path / 'work'
    cwd.mkdir(exist_ok=True)
    os.makedirs(os.path.join(str(home), 'sessions', '--s--'))
    os.makedirs(os.path.join(str(home), 'projects', paths.encode_component(str(cwd))))
    return str(home), str(cwd)


def _pi_session(home, cwd, name, mtime, header_id=None):
    """One pi session file whose header records *cwd*, stamped at *mtime* (never slept)."""
    p = os.path.join(home, 'sessions', '--s--', '%d_%s.jsonl' % (int(mtime), name))
    head = {'type': 'session', 'id': name if header_id is None else header_id, 'cwd': cwd}
    _write_lines(p, [json.dumps(head)])
    os.utime(p, (mtime, mtime))
    return p


def test_pi_locate_reports_only_a_path_pi_itself_names(tmp_path):
    home, cwd = _pi_rig(tmp_path)
    p = _pi_session(home, cwd, 'sid-hit', BASE - 10)
    a = PiSessions()
    got = a.locate('sid-hit', home, cwd)
    assert got is not None and got.transcript_path == p
    assert a.locate('sid-none', home, cwd) is None       # '' from pi: an empty Located is a lie
    assert a.locate('', home, cwd) is None


def test_pi_find_waits_for_a_session_at_all(tmp_path):
    home, cwd = _pi_rig(tmp_path)
    _pi_session(home, cwd, 'sid-old', BASE - 3600)
    assert PiSessions().find(home, cwd, BASE) is None


def test_pi_find_names_the_one_session_started_after_the_launch(tmp_path):
    home, cwd = _pi_rig(tmp_path)
    _pi_session(home, cwd, 'sid-old', BASE - 3600)
    _pi_session(home, cwd, 'sid-new', BASE + 5)
    assert PiSessions().find(home, cwd, BASE) == 'sid-new'


def test_pi_find_never_guesses_between_two_new_sessions(tmp_path):
    home, cwd = _pi_rig(tmp_path)
    _pi_session(home, cwd, 'sid-a', BASE + 5)
    _pi_session(home, cwd, 'sid-b', BASE + 9)
    assert PiSessions().find(home, cwd, BASE) is None


def test_pi_find_counts_a_session_started_at_the_launch_instant(tmp_path):
    home, cwd = _pi_rig(tmp_path)
    _pi_session(home, cwd, 'sid-edge', BASE)             # mtime == since: `>=` counts it
    assert PiSessions().find(home, cwd, BASE) == 'sid-edge'


def test_pi_find_falls_back_to_the_name_when_the_header_says_nothing(tmp_path):
    home, cwd = _pi_rig(tmp_path)
    p = _pi_session(home, cwd, 'sid-fall', BASE + 7, header_id='')
    assert p.endswith('_sid-fall.jsonl')
    assert PiSessions().find(home, cwd, BASE) == 'sid-fall'


def test_pi_turns_reads_only_the_message_records_pi_means(tmp_path):
    p = str(tmp_path / 'session.jsonl')
    _write_lines(p, [json.dumps(o) for o in [
        {'type': 'session', 'id': 'sid-1', 'cwd': '/w'},
        {'type': 'message', 'message': {'role': 'user', 'content': 'hello'}},
        {'type': 'message', 'message': {'role': 'assistant', 'content': [
            {'type': 'text', 'text': 'a'}, {'type': 'thinking', 'text': 'hidden'},
            {'type': 'text', 'text': 'b'}]}},
        {'type': 'message', 'message': {'role': 'toolResult', 'content': 'tool noise'}},
        {'type': 'model_change', 'message': {'role': 'user', 'content': 'smuggled'}},
        {'type': 'message'},
        {'type': 'message', 'message': {'role': 'user',
                                        'content': [{'type': 'text', 'text': '   '}]}},
        {'type': 'message', 'message': {'role': 'assistant',
                                        'content': {'type': 'text', 'text': 'dict-not-blocks'}}},
        {'type': 'message', 'message': {'role': 'assistant', 'content': 'last'}},
    ]])
    a = PiSessions()
    assert a.turns(p, 10) == [('user', 'hello'), ('assistant', 'a b'), ('assistant', 'last')]
    assert a.turns(p, 1) == [('assistant', 'last')]                    # tail, not head
