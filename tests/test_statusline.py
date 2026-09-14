"""`archeus statusline` — the line under every Claude Code prompt.

There is a whole category of statusline tools and they all show the same four
things, because that is all the stdin payload has: model, cwd, cost, context.
The reason archeus should ship one is the two fields nobody else can compute —
how stale this project's memory is, and how many lessons are waiting. Those are
the only bits that change what you do next.

The other half of this file is about not being a nuisance: it runs on every
conversation turn, and a statusline that throws leaves a traceback under the
user's prompt for the rest of the session.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import statusline as sl


def _plain(s):
    import re
    return re.sub(r'\033\[[0-9;]*m', '', s)


# ── it says the things only archeus knows ───────────────────

def test_it_reports_how_stale_the_memory_is(monkeypatch):
    """The one field no other statusline can print. A graph nobody has rebuilt
    in six days is quietly feeding the agent a stale codebase."""
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
    monkeypatch.setattr(sl, '_load', lambda p: {
        'entities': [{'name': 'X', 'type': 'component'}], 'generated_at': old})
    out = _plain(sl.render({'cwd': 'D:/p', 'model': {'display_name': 'Opus 5'}}))
    assert 'memory 6d' in out, out


def test_stale_memory_is_coloured_by_how_stale(monkeypatch):
    """Dim / amber / red. A number with no urgency attached is decoration.

    The constants are imported rather than spelled out: the row shares a line
    with `render.meter`, which paints its bar from config's palette, and two
    different greys in one row read as a rendering bug.
    """
    from datetime import datetime, timedelta, timezone
    from claude_sessions.config import C_DIM, C_WARN, C_ERR

    def at(days):
        stamp = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        monkeypatch.setattr(sl, '_load', lambda p: {
            'entities': [{'name': 'X'}], 'generated_at': stamp})
        return sl.render({'cwd': 'D:/p'})

    assert C_DIM in at(1)      # fresh-ish: dim
    assert C_WARN in at(9)     # over a week: amber
    assert C_ERR in at(20)     # over two: red


def test_it_surfaces_lessons_waiting_for_review(monkeypatch):
    """These now go unnoticed BECAUSE the mining became automatic — nothing
    else puts them in front of you mid-session."""
    monkeypatch.setattr(sl, '_load', lambda p: {'entities': [
        {'type': 'lesson', 'status': 'pending'},
        {'type': 'lesson', 'status': 'pending'},
        {'type': 'lesson', 'status': 'approved'},
        {'type': 'component'}]})
    out = _plain(sl.render({'cwd': 'D:/p'}))
    assert '2 to review' in out, out


def test_no_memory_says_so_rather_than_going_blank(monkeypatch):
    monkeypatch.setattr(sl, '_load', lambda p: {'entities': []})
    assert 'no memory' in _plain(sl.render({'cwd': 'D:/p'}))


def test_the_account_shows_only_when_there_are_several(monkeypatch):
    """On a single-account setup it is noise."""
    from claude_sessions import config as cfg
    monkeypatch.setattr(sl, '_load', lambda p: {'entities': [{'name': 'X'}]})
    monkeypatch.setattr(cfg, 'all_config_dirs', lambda: [('default', cfg.config_dir)])
    assert 'default' not in _plain(sl.render({'cwd': 'D:/p'}))
    monkeypatch.setattr(cfg, 'all_config_dirs',
                        lambda: [('default', cfg.config_dir), ('work', 'X')])
    assert 'default' in _plain(sl.render({'cwd': 'D:/p'}))


def test_context_pressure_reads_the_field_claude_code_actually_sends(monkeypatch):
    """This segment was DEAD in production for its whole life.

    It read `context_used_pct` / `contextUsedPercent` / `context.used|total` —
    none of which Claude Code has ever sent. The real field is
    `context_window.used_percentage`. The old test passed because it asserted
    against the same invented shape, so it was testing the bug, not the
    behaviour. The last two assertions are the regression guard.
    """
    from claude_sessions.config import C_ERR
    monkeypatch.setattr(sl, '_load', lambda p: {'entities': []})

    hot = sl.render({'cwd': 'D:/p', 'context_window': {'used_percentage': 90}})
    assert '90% ctx' in _plain(hot), hot
    assert C_ERR in hot, 'past 85% has to be red'

    calm = sl.render({'cwd': 'D:/p', 'context_window': {'used_percentage': 30}})
    assert '30% ctx' in _plain(calm), calm
    assert C_ERR not in calm, 'a third full is not an emergency'

    for dead in ({'context': {'used': 180, 'total': 200}},
                 {'context_used_pct': 90}, {'contextUsedPercent': 90}):
        assert 'ctx' not in _plain(sl.render(dict(dead, cwd='D:/p'))), dead


def test_the_context_meter_is_drawn_not_just_the_number():
    """It leads row 2 and anchors it — a bare integer does not read as pressure."""
    out = sl.render({'cwd': 'D:/p', 'context_window': {'used_percentage': 50}})
    assert '█' in out and '░' in out, out


def test_exceeding_200k_is_red_at_any_percentage():
    """That flag means the premium pricing tier is live, which is actionable
    even at 10% — so it must not wait for the 85% threshold."""
    from claude_sessions.config import C_ERR
    out = sl.render({'cwd': 'D:/p', 'context_window': {'used_percentage': 10},
                     'exceeds_200k_tokens': True})
    assert C_ERR in out and '200k+' in _plain(out), out


def test_rate_limits_come_from_stdin_and_never_from_the_api():
    """`usage.py` gets these by polling the OAuth endpoint on a background
    thread. A thread started per turn, in a process Claude Code cancels the
    moment a new update arrives, is the wrong shape — and the payload already
    carries the numbers for free."""
    import inspect
    out = _plain(sl.render({'cwd': 'D:/p', 'rate_limits': {
        'five_hour': {'used_percentage': 41},
        'seven_day': {'used_percentage': 18}}}))
    assert '5h 41%' in out and '7d 18%' in out, out
    assert 'import usage' not in inspect.getsource(sl), 'no OAuth poll on the turn path'


def test_rate_limit_windows_say_when_they_reset():
    """A percentage alone does not answer the question you have when you read
    it. `resets_at` is Unix epoch SECONDS in this payload — usage.py's own
    formatter takes ISO, because the endpoint IT polls returns ISO."""
    import time
    from datetime import datetime
    soon = time.time() + 3600
    out = _plain(sl.render({'cwd': 'D:/p', 'rate_limits': {
        'five_hour': {'used_percentage': 32, 'resets_at': soon}}}))
    assert '5h 32%' in out, out
    assert datetime.fromtimestamp(soon).astimezone().strftime('%H:%M') in out, out


def test_a_missing_or_millisecond_reset_never_prints_a_wrong_time():
    """Absent is the documented normal case (each window may be independently
    absent), and this codebase has already been bitten once by epoch
    milliseconds read as seconds — which renders a plausible-looking date."""
    import time
    assert sl._reset_at(None) == ''
    assert sl._reset_at('2026-01-01T00:00:00Z') == ''
    assert sl._reset_at(True) == ''          # bool is an int; must not format
    now = time.time()
    assert sl._reset_at(now * 1000) == sl._reset_at(now)
    # the percentage still renders when the window carries no reset time
    out = _plain(sl.render({'cwd': 'D:/p',
                            'rate_limits': {'seven_day': {'used_percentage': 45}}}))
    assert '7d 45%' in out and '→' not in out, out


def test_mode_segments_stay_quiet_on_an_ordinary_session():
    """They cost nothing when there is nothing to say — that is the whole
    reason they can be afforded at all."""
    assert sl._mode_bit({'effort': {'level': 'high'},
                         'output_style': {'name': 'default'}}) == ''
    loud = _plain(sl._mode_bit({'effort': {'level': 'xhigh'},
                                'output_style': {'name': 'terse'},
                                'pr': {'number': 412}, 'fast_mode': True,
                                'workspace': {'git_worktree': 'feat-x'}}))
    for token in ('xhigh', 'terse', 'PR #412', 'fast', 'wt:feat-x'):
        assert token in loud, (token, loud)


def test_a_narrow_terminal_drops_segments_instead_of_wrapping(monkeypatch):
    """A wrapped statusline eats the prompt. COLUMNS is the only width source
    that works — stdout is a pipe, so terminal-size detection reports 80."""
    monkeypatch.setattr(sl, '_load', lambda p: {'entities': []})
    payload = {'cwd': 'D:/p', 'model': {'display_name': 'Opus 5'},
               'context_window': {'used_percentage': 72},
               'rate_limits': {'five_hour': {'used_percentage': 41}},
               'cost': {'total_cost_usd': 15.7}}
    monkeypatch.setenv('COLUMNS', '48')
    rows = sl.render_rows(payload)
    for row in rows:
        assert sl._r.disp_width(row) <= 48, (sl._r.disp_width(row), _plain(row))
    assert 'Opus 5' in _plain(rows[0]), rows
    assert 'ctx' in _plain(rows[1]), rows


# ── it must never become the problem ──────────────────────────

def test_no_payload_can_make_it_raise():
    """It runs every turn. A traceback here sits under the prompt for the rest
    of the session."""
    for bad in ({}, {'cwd': None}, {'model': None}, {'cost': {'total_cost_usd': 'x'}},
                {'context': {'used': 'a', 'total': 0}}, {'cwd': 12},
                {'model': {'display_name': None}}, {'cost': None}):
        sl.render(bad)          # must not raise


def test_a_broken_memory_read_degrades_to_a_shorter_line(monkeypatch):
    def boom(_p):
        raise RuntimeError('disk gone')
    monkeypatch.setattr(sl, '_load', boom)
    out = _plain(sl.render({'cwd': 'D:/p', 'model': {'display_name': 'Opus 5'}}))
    # the memory-derived bits drop out; everything else still renders
    assert 'Opus 5' in out, out
    assert 'memory' not in out and 'to review' not in out, out


def test_a_payload_cannot_add_rows_of_its_own(tmp_path):
    """Claude Code renders EVERY printed line as a row, so the row count is now
    ours to control. The old test asserted a single line, which was true of the
    old renderer and is not the property worth protecting: what matters is that
    a newline inside a free-text field cannot smuggle in a row of its own.
    """
    r = subprocess.run(
        [sys.executable, '-m', 'claude_sessions', 'statusline'],
        input=json.dumps({'cwd': str(tmp_path),
                          'model': {'display_name': 'A\nB'},
                          'context_window': {'used_percentage': 40}}),
        capture_output=True, text=True, encoding='utf-8',
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr
    assert r.stdout.count('\n') == 2, repr(r.stdout)      # two rows, one trailing \n
    assert 'A B' in r.stdout, repr(r.stdout)
    assert r.stderr.strip() == '', r.stderr


def test_the_glyphs_survive_a_pipe(tmp_path):
    """The reported `Opus 5 <?> default <?> memory 21m`.

    Claude Code captures stdout as a PIPE, so CPython falls back to the locale
    codepage — cp1252 on Windows. The row's block glyphs are unencodable there
    and even `·` reaches the terminal as a byte it decodes as broken UTF-8.
    Without the reconfigure() in main() this exits non-zero with a
    UnicodeEncodeError traceback under the user's prompt.
    """
    env = dict(os.environ)
    env.pop('PYTHONIOENCODING', None)
    r = subprocess.run(
        [sys.executable, '-m', 'claude_sessions', 'statusline'],
        input=json.dumps({'cwd': str(tmp_path),
                          'context_window': {'used_percentage': 72}}).encode(),
        capture_output=True, cwd=os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))), env=env)
    assert r.returncode == 0, r.stderr
    assert r.stderr.strip() == b'', r.stderr
    assert '█'.encode('utf-8') in r.stdout, r.stdout


def test_the_statusline_does_not_import_the_tui_stack():
    """It runs on every turn. `main.py` pulls the whole TUI plus `usage`, which
    drags in urllib/ssl/http.client for an OAuth poll this must never make —
    48ms of import that the dispatch in __main__ exists to skip."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', '__main__.py'),
        encoding='utf-8').read()
    assert src.index("== 'statusline'") < src.index('from .main import run')


def test_garbage_on_stdin_is_survivable():
    r = subprocess.run(
        [sys.executable, '-m', 'claude_sessions', 'statusline'],
        input='not json at all {{{', capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr
    assert r.stderr.strip() == ''


# ── install ───────────────────────────────────────────────────

def test_it_refuses_to_clobber_someone_elses_statusline(monkeypatch, tmp_path):
    """statusLine is single-valued. Silently replacing a line the user built is
    the same class of overwrite the memory work went to lengths to avoid."""
    from claude_sessions import hooks
    p = tmp_path / 'settings.json'
    p.write_text(json.dumps({'statusLine': {'type': 'command',
                                            'command': '~/mine.sh'}}), encoding='utf-8')
    monkeypatch.setattr(hooks, 'settings_path', str(p))

    ok, msg = sl.install()
    assert ok is False
    assert 'already set' in msg
    assert json.loads(p.read_text(encoding='utf-8'))['statusLine']['command'] == '~/mine.sh'


def test_install_and_remove_round_trip(monkeypatch, tmp_path):
    from claude_sessions import hooks
    p = tmp_path / 'settings.json'
    p.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(hooks, 'settings_path', str(p))

    assert sl.is_installed() is False
    ok, _ = sl.install()
    assert ok and sl.is_installed()
    cmd = json.loads(p.read_text(encoding='utf-8'))['statusLine']['command']
    assert 'claude_sessions' in cmd and 'statusline' in cmd
    ok, _ = sl.remove()
    assert ok and not sl.is_installed()
    # and it left the rest of settings.json alone — `tui` is there because
    # install turns the fullscreen renderer on, and removing the statusline is
    # not a reason to change the user's interface back
    assert json.loads(p.read_text(encoding='utf-8')) == {'tui': 'fullscreen'}


# ── the hook events ───────────────────────────────────────────

def test_the_events_a_workspace_manager_needs_are_covered():
    """5 of 32 was the starting point, and the missing ones were exactly the
    ones archeus has a reason to want."""
    from claude_sessions.hooks import EVENTS, TEMPLATES
    for e in ('PostCompact', 'SubagentStart', 'PermissionRequest',
              'PermissionDenied', 'WorktreeCreate', 'WorktreeRemove',
              'TaskCreated', 'TaskCompleted', 'FileChanged'):
        assert e in EVENTS, e
    # every template must name an event the manager can actually place
    for name, t in TEMPLATES.items():
        assert t['event'] in EVENTS, f'{name} -> {t["event"]}'


def test_compaction_recovery_uses_the_real_signal():
    """archeus advertises context-loss insurance after /compact. Until
    PostCompact existed the only available moment was SessionStart — i.e.
    before the loss, not after it."""
    from claude_sessions.hooks import TEMPLATES
    t = TEMPLATES['reinject-after-compact']
    assert t['event'] == 'PostCompact'
    assert 'recall_hook' in t['entry']['hooks'][0]['command']


# ── OTEL export ───────────────────────────────────────────────

def test_otel_is_off_unless_both_switch_and_endpoint_are_set():
    """An enabled flag with no endpoint would set CLAUDE_CODE_ENABLE_TELEMETRY
    and then have nowhere to send it — a half-configured export that looks on."""
    from claude_sessions.config import otel_env
    assert otel_env({}) == {}
    assert otel_env({'otel_enabled': True}) == {}
    assert otel_env({'otel_endpoint': 'http://x'}) == {}
    assert otel_env({'otel_enabled': True, 'otel_endpoint': 'http://x'})


def test_otel_never_turns_on_prompt_content_logging():
    """OTEL_LOG_USER_PROMPTS=1 exports the prompts themselves. It is the first
    thing anyone asks about and it is deliberately not a checkbox here."""
    from claude_sessions.config import otel_env
    import inspect
    from claude_sessions import config as cfg
    env = otel_env({'otel_enabled': True, 'otel_endpoint': 'http://x',
                    'otel_headers': 'Authorization=Bearer k'})
    assert 'OTEL_LOG_USER_PROMPTS' not in env
    src = inspect.getsource(cfg.otel_env)
    assert 'OTEL_LOG_USER_PROMPTS' in src, 'the caveat is not documented'


def test_otel_reaches_the_launch_environment():
    """archeus owns the launch env, which is the only reason this can be one
    toggle instead of a shell profile edit."""
    import inspect
    from claude_sessions import main as main_mod
    src = inspect.getsource(main_mod.build_launch_command)
    assert 'otel_env()' in src


def test_otel_keys_survive_a_reload():
    """Same trap as the appearance keys: undeclared means written once then
    deleted by the next settings save."""
    from claude_sessions.config import _DEFAULT_SETTINGS
    for k in ('otel_enabled', 'otel_endpoint', 'otel_protocol', 'otel_headers'):
        assert k in _DEFAULT_SETTINGS, k


# ── installed is not the same question as visible ────────────

def _acct(tmp_path, monkeypatch, settings):
    import json as _json
    from claude_sessions import hooks
    p = tmp_path / 'settings.json'
    p.write_text(_json.dumps(settings), encoding='utf-8')
    monkeypatch.setattr(hooks, 'settings_path', str(p))
    return str(tmp_path)


def test_a_cwd_dependent_command_is_reported_as_a_blocker(tmp_path, monkeypatch):
    """The bug this exists for. `-m claude_sessions` resolves the package off
    sys.path[0], which for -m is the CURRENT DIRECTORY — so the statusline
    printed in the archeus checkout and nowhere else. Claude Code swallows
    the command's failure, so the only symptom was a blank line, and it looked
    like an account problem for exactly as long as the accounts were tested in
    different directories."""
    d = _acct(tmp_path, monkeypatch, {'statusLine': {
        'command': '"py.exe" -m claude_sessions statusline'}})
    codes = [c for c, _why in sl.blockers(d)]
    assert 'cwd-dependent-command' in codes
    assert 'reinstall' in dict(sl.blockers(d))['cwd-dependent-command']


def test_the_installed_command_does_not_depend_on_the_working_directory():
    assert sl._LEGACY not in sl._command()
    assert 'statusline_cli.py' in sl._command()


def test_the_current_command_reports_no_blocker(tmp_path, monkeypatch):
    d = _acct(tmp_path, monkeypatch,
              {'tui': 'fullscreen',
               'statusLine': {'type': 'command', 'command': sl._command()}})
    assert sl.blockers(d) == []


def test_the_entry_script_runs_from_any_directory(tmp_path):
    """Not a shape check: the script is RUN, from a directory that is not the
    checkout, exactly as a session in someone else's project would."""
    import json as _json
    import subprocess as _sp
    payload = {'model': {'display_name': 'Opus 5'}, 'cwd': str(tmp_path),
               'workspace': {'current_dir': str(tmp_path)},
               'context_window': {'used_percentage': 42},
               'cost': {'total_cost_usd': 1.0}}
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'claude_sessions', 'statusline_cli.py')
    r = _sp.run([sys.executable, script], input=_json.dumps(payload),
                capture_output=True, text=True, encoding='utf-8',
                errors='replace', cwd=str(tmp_path), timeout=120)
    assert r.returncode == 0, r.stderr
    assert 'Opus 5' in r.stdout, (r.stdout, r.stderr)


def test_running_it_as_a_module_from_elsewhere_is_what_used_to_fail(tmp_path):
    """The evidence for the fix, kept as a test: the old form still cannot
    resolve the package from another directory."""
    import subprocess as _sp
    r = _sp.run([sys.executable, '-m', 'claude_sessions', 'statusline'],
                input='{}', capture_output=True, text=True, encoding='utf-8',
                errors='replace', cwd=str(tmp_path), timeout=120)
    if r.returncode == 0:
        import pytest
        pytest.skip('archeus is installed here, so -m resolves anyway')
    assert 'No module named' in (r.stderr or '')


def test_disabling_every_hook_is_reported_too(tmp_path, monkeypatch):
    d = _acct(tmp_path, monkeypatch,
              {'disableAllHooks': True, 'tui': 'fullscreen',
               'statusLine': {'command': sl._command()}})
    assert [c for c, _w in sl.blockers(d)] == ['hooks-disabled']


def test_by_account_carries_the_blockers_next_to_installed(tmp_path, monkeypatch):
    from claude_sessions import hooks
    a, b = tmp_path / 'a', tmp_path / 'b'
    for p, cmd in ((a, '"py.exe" -m claude_sessions statusline'),
                   (b, sl._command())):
        p.mkdir()
        (p / 'settings.json').write_text(
            json.dumps({'tui': 'fullscreen', 'statusLine': {'command': cmd}}),
            encoding='utf-8')
    monkeypatch.setattr(hooks, 'account_dirs',
                        lambda: [('stale', str(a)), ('fixed', str(b))])
    rows = {n: (done, [c for c, _w in bl]) for n, _d, done, bl in sl.by_account()}
    assert rows['stale'] == (True, ['cwd-dependent-command'])
    assert rows['fixed'] == (True, [])


def test_installing_turns_the_fullscreen_tui_on(tmp_path, monkeypatch):
    """An installed statusline that Claude Code never draws is the failure
    mode `blockers()` was written for, and the classic renderer draws none."""
    d = _acct(tmp_path, monkeypatch, {'tui': 'default'})
    ok, _msg = sl.install(d)
    assert ok
    s = json.loads((tmp_path / 'settings.json').read_text(encoding='utf-8'))
    assert s['tui'] == 'fullscreen'
    assert sl.blockers(d) == []


def test_the_classic_tui_is_reported_as_a_blocker(tmp_path, monkeypatch):
    d = _acct(tmp_path, monkeypatch,
              {'statusLine': {'command': sl._command()}, 'tui': 'default'})
    assert [k for k, _ in sl.blockers(d)] == ['classic-tui']
