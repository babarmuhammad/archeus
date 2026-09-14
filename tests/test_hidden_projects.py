"""Hiding a project takes it out of the lists — and out of nothing else.

The flag lives on `project_defaults[<enc>]['hidden']`, which is a settings key,
so a hidden project's transcripts stay exactly where Claude Code wrote them.
That is the property worth guarding: a "hide" that moved files would be an
archive, and restoring it would be a second chance to lose a session.

The index gate is the other half. The main menu's row values are
`__proj_<i>__`, and `i` indexes the FILTERED list — hiding the first project and
pressing Enter on the first row must open the second one, not fall back to the
unfiltered order and open the hidden one.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import Sandbox, run_flow, ENTER, ESC

from claude_sessions import config, gui, gui_api, main as main_mod


def flat(*parts):
    out = []
    for p in parts:
        out.extend(p)
    return out


def _by_enc(monkeypatch, mapping):
    """gui imports find_actual_path by value, and it cannot walk a fake tree."""
    monkeypatch.setattr(gui, 'find_actual_path',
                        lambda e, *a, **k: mapping.get(e))


def _run_catch_exit():
    try:
        main_mod.run()
        return 'returned'
    except SystemExit as e:
        if str(e) == 'OUT_OF_KEYS':
            raise
        return f'exit:{e.code}'


# ── the setting ──────────────────────────────────────────────

def test_hiding_a_project_writes_a_flag_and_moves_nothing(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, enc, folder, sids = sb.add_project('alpha', n_sessions=1)
    config.set_project_hidden(enc, True)
    assert config.hidden_projects() == {enc}
    assert os.path.isfile(os.path.join(folder, sids[0] + '.jsonl')), \
        'hiding a project must not touch its sessions'
    config.set_project_hidden(enc, False)
    assert config.hidden_projects() == set()


def test_hiding_keeps_the_projects_other_defaults(monkeypatch, tmp_path):
    """It shares a dict with the launch pins, so it must merge into them."""
    sb = Sandbox(monkeypatch, tmp_path)
    _a, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    s = config.load_settings()
    s.setdefault('project_defaults', {})[enc] = {'effort': 'high'}
    config.save_settings(s)
    config.set_project_hidden(enc, True)
    pd = config.load_settings()['project_defaults'][enc]
    assert pd == {'effort': 'high', 'hidden': True}


# ── the TUI list ─────────────────────────────────────────────

def test_a_hidden_project_is_not_in_the_main_menu(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _a, enc_a, _f, _s = sb.add_project('alpha', n_sessions=1)
    sb.add_project('beta', n_sessions=1)
    config.set_project_hidden(enc_a, True)
    cap = run_flow(monkeypatch, flat(ESC), _run_catch_exit)[1]
    plain = cap.plain
    assert 'beta' in plain
    assert 'alpha' not in plain
    assert '1 project(s) hidden' in plain, 'nothing told the user the list is filtered'


def test_a_hidden_projects_recent_session_is_not_offered(monkeypatch, tmp_path):
    """Quick-resume is the second way the same project reaches the screen."""
    sb = Sandbox(monkeypatch, tmp_path)
    actual, enc, _folder, sids = sb.add_project('alpha', n_sessions=1)
    sb.write_last_sessions([{
        'project_path': actual, 'encoded_name': enc, 'session_id': sids[0],
        'preview': 'recent work', 'timestamp': time.time()}])
    config.set_project_hidden(enc, True)
    cap = run_flow(monkeypatch, flat(ESC), _run_catch_exit)[1]
    assert 'recent work' not in cap.plain


def test_the_row_under_the_cursor_is_the_project_that_opens(monkeypatch, tmp_path):
    """`__proj_<i>__` indexes the filtered list, not the full one."""
    sb = Sandbox(monkeypatch, tmp_path)
    # both projects, then hide whichever one sorts FIRST (the list is by mtime)
    a_path, a_enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    b_path, b_enc, _f2, _s2 = sb.add_project('beta', n_sessions=1)
    _by_enc(monkeypatch, {a_enc: a_path, b_enc: b_path})
    first, other = gui.list_projects()[:2]
    config.set_project_hidden(first['encoded'], True)
    # Enter on the only project row -> Enter on 'new' -> Enter to launch
    run_flow(monkeypatch, flat(ENTER, ENTER, ENTER), _run_catch_exit)
    line = sb.choice_line() or ''
    assert other['path'] in line
    assert first['path'] not in line


def test_unhiding_puts_it_back(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _a, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    config.set_project_hidden(enc, True)
    config.set_project_hidden(enc, False)
    cap = run_flow(monkeypatch, flat(ESC), _run_catch_exit)[1]
    assert 'alpha' in cap.plain
    assert 'hidden' not in cap.plain


def test_the_hide_screen_toggles_the_row_it_is_on(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _a, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    grouped = [(0, _a, enc, str(sb.cfg), [])]
    # Enter hides it, the screen redraws, Enter restores it, ESC leaves
    run_flow(monkeypatch, flat(ENTER, ESC), main_mod._hidden_projects_menu, grouped)
    assert config.hidden_projects() == {enc}
    run_flow(monkeypatch, flat(ENTER, ESC), main_mod._hidden_projects_menu, grouped)
    assert config.hidden_projects() == set()


# ── the GUI ──────────────────────────────────────────────────

def test_list_projects_reports_the_flag(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _a, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    _by_enc(monkeypatch, {enc: _a})
    assert gui.list_projects()[0]['hidden'] is False
    config.set_project_hidden(enc, True)
    assert gui.list_projects()[0]['hidden'] is True


def test_the_endpoint_hides_and_restores(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _a, enc, _f, _s = sb.add_project('alpha', n_sessions=1)
    assert gui_api.api_project_hide({}, {'enc': enc, 'hidden': True}) == {'ok': True}
    assert config.hidden_projects() == {enc}
    gui_api.api_project_hide({}, {'enc': enc, 'hidden': False})
    assert config.hidden_projects() == set()


def test_the_endpoint_without_a_project_is_the_callers_fault(monkeypatch, tmp_path):
    """An empty body must be a 400, not a 500 carrying a bare KeyError — the
    endpoint floor's rule, asserted at the call() layer that enforces it."""
    Sandbox(monkeypatch, tmp_path)
    try:
        gui_api.call(gui_api.api_project_hide, {}, {})
    except gui_api.BadRequest as e:
        assert 'enc' in str(e)
    else:
        raise AssertionError('a missing enc must raise BadRequest')


def test_the_sidebar_filters_on_it():
    """The flag has to reach the one list it exists for."""
    js = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'claude_sessions', 'web', 'app.js'), encoding='utf-8').read()
    assert 'SHOW_HIDDEN||!p.hidden' in js
    assert "post('/api/project/hide'" in js
