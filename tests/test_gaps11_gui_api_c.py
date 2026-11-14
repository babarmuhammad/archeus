"""T-1406 — claude_sessions/gui_api.py worklog and memory toggle handlers, lines 2019-2070.

Candidate list, refusal and write ordering first:
 1. 2050-2061  a refused memory hook raises before 'rules' and 'budget' save anything
 2. 2038-2040  worklog set: a non-bool is a BadRequest and the installed check is not run
 3. 2060       budget is clamped to [0, 20000]; None becomes 0
 4. 2060       non-numeric budget raises ValueError from int(), nothing saved (gui.py maps it to 400)
 5. 2055-2057  rules applies with folder None when enc is empty
 6. 2062-2068  response defaults: hook off, rules on, budget 600
 7. 2063-2065  a project memory_hook overrides the global memory_prompt_hook
 8. 2024-2025  worklog get: 'on' defaults False; nothing is read without a path
 9. 2031       worklog get returns the newest ten entries
10. 2030/2042  'installed' reads across accounts, not one account

Seams: memhub.set_prompt_hook, memhub.set_memory_rules, worklog.load_worklog,
hooks.across_accounts, config.load_settings and config.save_settings are replaced
with fakes over an in-memory settings dict; gui_api._folder is replaced too.
No real settings file, no real config dir, no network.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import config, gui_api, hooks, memhub, worklog


@pytest.fixture()
def settings(monkeypatch):
    store = {'settings': {}, 'saves': []}
    monkeypatch.setattr(config, 'load_settings', lambda: store['settings'])

    def save(s):
        store['saves'].append(dict(s))
        store['settings'] = s

    monkeypatch.setattr(config, 'save_settings', save)
    return store


@pytest.fixture()
def folder(monkeypatch, tmp_path):
    proj_folder = str(tmp_path / 'folder')
    monkeypatch.setattr(gui_api, '_folder', lambda cfgdir, enc: proj_folder)
    return proj_folder


@pytest.fixture()
def no_install(monkeypatch):
    seen = []

    def fake(fn):
        seen.append(fn)
        return False

    monkeypatch.setattr(hooks, 'across_accounts', fake)
    return seen


# 2050-2061 — a refused hook stops the request before rules or budget are saved
def test_memory_toggles_refused_hook_writes_nothing_else(settings, monkeypatch, folder):
    rules_calls = []
    monkeypatch.setattr(memhub, 'set_memory_rules', lambda *a: rules_calls.append(a))
    with pytest.raises(gui_api.BadRequest, match='memory hook flag is a boolean'):
        gui_api.call(gui_api.api_memory_toggles, {},
                     {'enc': 'proj-1', 'hook': 'yes', 'rules': True, 'budget': 900})
    assert rules_calls == []
    assert settings['saves'] == []


# 2038-2040 — a non-bool worklog flag is a BadRequest, and no installed check runs
def test_worklog_set_value_error_is_bad_request(settings, no_install):
    with pytest.raises(gui_api.BadRequest, match='worklog flag is a boolean'):
        gui_api.call(gui_api.api_worklog_set, {}, {'enc': 'proj-1', 'on': 'yes'})
    assert no_install == []
    assert settings['saves'] == []


# 2060 — budget is clamped to [0, 20000]; a missing value is 0
def test_memory_budget_clamped_to_range(settings, monkeypatch):
    monkeypatch.setattr(memhub, 'set_memory_rules', lambda *a: None)
    monkeypatch.setattr(hooks, 'across_accounts', lambda fn: True)
    for given, saved in ((-5, 0), (99999, 20000), (None, 0), (750, 750)):
        out = gui_api.call(gui_api.api_memory_toggles, {}, {'budget': given})
        assert settings['settings']['memory_budget'] == saved
        assert out['budget'] == saved


# 2060 — a non-numeric budget is a ValueError from int(); nothing is saved
def test_memory_budget_non_numeric_saves_nothing(settings):
    settings['settings'] = {'memory_budget': 600}
    with pytest.raises(ValueError, match="invalid literal for int"):
        gui_api.call(gui_api.api_memory_toggles, {}, {'budget': 'abc'})
    assert settings['saves'] == []
    assert settings['settings']['memory_budget'] == 600


# 2055-2057 — rules get no folder when the request names no project
def test_memory_rules_folder_none_without_enc(settings, monkeypatch):
    calls = []
    monkeypatch.setattr(memhub, 'set_memory_rules', lambda *a: calls.append(a))
    gui_api.call(gui_api.api_memory_toggles, {}, {'rules': True, 'path': '/p'})
    assert calls == [(True, '/p', None)]


# 2062-2068 — the response defaults with empty settings
def test_memory_toggles_response_defaults(settings, monkeypatch):
    monkeypatch.setattr(hooks, 'across_accounts', lambda fn: True)
    out = gui_api.call(gui_api.api_memory_toggles, {}, {'enc': 'proj-1'})
    assert out == {'ok': True, 'hook_on': False, 'rules_on': True,
                   'budget': 600, 'installed': True}


# 2063-2065 — a project memory_hook overrides the global default
def test_memory_hook_project_setting_overrides_global(settings, monkeypatch):
    monkeypatch.setattr(hooks, 'across_accounts', lambda fn: False)
    settings['settings'] = {'memory_prompt_hook': True,
                            'project_defaults': {'proj-1': {'memory_hook': False}}}
    out = gui_api.call(gui_api.api_memory_toggles, {}, {'enc': 'proj-1'})
    assert out['hook_on'] is False

    settings['settings']['project_defaults'] = {}
    out = gui_api.call(gui_api.api_memory_toggles, {}, {'enc': 'proj-1'})
    assert out['hook_on'] is True


# 2024-2025 — 'on' defaults to False, and the worklog is read only when a path is given
def test_worklog_get_off_and_no_read_without_path(settings, monkeypatch, no_install):
    reads = []
    monkeypatch.setattr(worklog, 'load_worklog', lambda p: reads.append(p) or [])
    out = gui_api.call(gui_api.api_worklog_get, {'enc': 'proj-1'}, None)
    assert out == {'on': False, 'installed': False, 'entries': []}
    assert reads == []
    settings['settings'] = {'project_defaults': {'proj-1': {'worklog': True}}}
    gui_api.call(gui_api.api_worklog_get, {'enc': 'proj-1', 'path': '/p'}, None)
    assert reads == ['/p']


# 2031 — at most the newest ten entries, newest first
def test_worklog_get_newest_ten_entries(settings, monkeypatch, no_install):
    monkeypatch.setattr(worklog, 'load_worklog', lambda p: [{'n': i} for i in range(12)])
    out = gui_api.call(gui_api.api_worklog_get, {'enc': 'proj-1', 'path': '/p'}, None)
    assert [e['n'] for e in out['entries']] == [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]


# 2030/2042 — 'installed' comes from across_accounts, not from one account's predicate
def test_worklog_installed_reads_across_accounts(settings, monkeypatch):
    monkeypatch.setattr(hooks, 'worklog_hook_installed', lambda: True)
    monkeypatch.setattr(hooks, 'across_accounts', lambda fn: False)
    out = gui_api.call(gui_api.api_worklog_get, {'enc': 'proj-1'}, None)
    assert out['installed'] is False
    out = gui_api.call(gui_api.api_worklog_set, {}, {'enc': 'proj-1', 'on': False})
    assert out['installed'] is False
