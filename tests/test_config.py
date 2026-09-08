import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import claude_sessions.config as config


def test_load_settings_defaults_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'settings_file', str(tmp_path / 'nope.json'))
    s = config.load_settings()
    assert s['editor'] == ''
    assert s['project_defaults'] == {}


def test_settings_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'settings_file', str(tmp_path / 'archeus.json'))
    s = config.load_settings()
    s['default_effort'] = 'high'
    s['project_defaults']['D--repos'] = {'effort': 'low', 'model': ''}
    assert config.save_settings(s)
    s2 = config.load_settings()
    assert s2['default_effort'] == 'high'
    assert s2['project_defaults']['D--repos']['effort'] == 'low'


def test_a_settings_dict_never_shares_a_default_with_the_next_one(monkeypatch, tmp_path):
    """`dict(_DEFAULT_SETTINGS)` is shallow, so two loads of a file that names
    no `project_defaults` used to hand out the SAME dict — and every writer of
    one does `s.setdefault('project_defaults', {})[enc] = …`, mutating the
    module default. One project's pins then appeared in the next load, in a
    process (the GUI, a long TUI run) that never re-imports the module."""
    monkeypatch.setattr(config, 'settings_file', str(tmp_path / 'nope.json'))
    a = config.load_settings()
    a['project_defaults']['X--proj'] = {'hidden': True}
    a['cost_table']['x'] = 1
    b = config.load_settings()
    assert b['project_defaults'] == {} and b['cost_table'] == {}
    assert config._DEFAULT_SETTINGS['project_defaults'] == {}


def test_load_settings_ignores_unknown_keys(monkeypatch, tmp_path):
    f = tmp_path / 'archeus.json'
    f.write_text(json.dumps({'editor': 'x', 'evil_key': 1}), encoding='utf-8')
    monkeypatch.setattr(config, 'settings_file', str(f))
    s = config.load_settings()
    assert 'evil_key' not in s


def test_load_settings_corrupt_file(monkeypatch, tmp_path):
    f = tmp_path / 'archeus.json'
    f.write_text('{{{not json', encoding='utf-8')
    monkeypatch.setattr(config, 'settings_file', str(f))
    s = config.load_settings()
    assert s == config._DEFAULT_SETTINGS or s['editor'] == ''


def test_get_config_dir_default(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'settings_file', str(tmp_path / 'nope.json'))
    assert config.get_config_dir() == os.path.join(config._USERPROFILE, '.claude')


def test_get_config_dir_override(monkeypatch, tmp_path):
    f = tmp_path / 'archeus.json'
    f.write_text(json.dumps({'claude_config_dir': str(tmp_path / 'acct')}), encoding='utf-8')
    monkeypatch.setattr(config, 'settings_file', str(f))
    assert config.get_config_dir() == str(tmp_path / 'acct')


def test_get_config_dir_expands(monkeypatch, tmp_path):
    f = tmp_path / 'archeus.json'
    f.write_text(json.dumps({'claude_config_dir': '~/.claude-work'}), encoding='utf-8')
    monkeypatch.setattr(config, 'settings_file', str(f))
    assert config.get_config_dir() == os.path.expanduser('~/.claude-work')


def test_find_editor_returns_existing_or_none():
    e = config.find_editor()
    assert e is None or os.path.exists(e)


def test_every_editor_launch_goes_through_one_spawn_point(monkeypatch):
    """Sixteen call sites across eight modules import `open_in_editor` BY VALUE,
    so patching it has to be repeated per module — and four of those modules
    were missed, which is how a test run popped a real Notepad++ into the
    foreground. `_spawn_editor` is below that binding, so one patch covers
    every caller and a new caller cannot escape it."""
    seen = []
    monkeypatch.setattr(config, 'find_editor', lambda: 'EDITOR.EXE')
    monkeypatch.setattr(config, '_spawn_editor',
                        lambda exe, path: (seen.append((exe, path)), True)[1])
    assert config.open_in_editor('X.md') is True
    assert seen == [('EDITOR.EXE', 'X.md')]


@pytest.mark.real_editor          # reaches the real _spawn_editor; Popen is faked
def test_the_editor_window_does_not_take_the_foreground(monkeypatch):
    """archeus opens an editor as a side effect of a screen the user is
    already looking at; stealing focus interrupts them."""
    if os.name != 'nt':
        pytest.skip('STARTUPINFO is a Windows mechanism')
    import subprocess
    captured = {}

    def fake_popen(argv, **kw):
        captured.update(kw)
        return object()

    monkeypatch.setattr(subprocess, 'Popen', fake_popen)
    assert config._spawn_editor('EDITOR.EXE', 'X.md') is True
    si = captured.get('startupinfo')
    assert si is not None, 'no STARTUPINFO — the window will take focus'
    assert si.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert si.wShowWindow == 4          # SW_SHOWNOACTIVATE


def test_the_suite_cannot_spawn_a_real_editor():
    """conftest's autouse guard, asserted rather than assumed — otherwise the
    next module that opens an editor pops a window mid-run again."""
    assert config._spawn_editor.__name__ == '<lambda>', \
        'the editor spawn is not stubbed — a test run can open a real window'


def test_get_claude_exe_returns_existing_or_none():
    c = config.get_claude_exe()
    assert c is None or os.path.exists(c)
