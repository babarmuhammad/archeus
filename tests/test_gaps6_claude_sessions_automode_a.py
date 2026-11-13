"""T-1280: claude_sessions/automode.py lines 45-143 at tip 6bbd3b44 (the CLI
runner, the account settings block and the default-mode delegation). Selected
probes, not measured coverage.

Selected branches: 123 one leading sentinel, siblings kept; 119 clearing removes
only environment; 117 non-dict autoMode refuses without a save; 128 save False is
a refusal; 143 default mode delegates to ccsettings.write; 101 non-list
environment; 53 no executable; 62 nonzero and None results; 58 argv, cfgdir and
timeout; 88 reset sends --yes only for the requested account.
"""

import copy
from types import SimpleNamespace

import pytest

from claude_sessions import automode, hooks, proc


@pytest.fixture
def settings(monkeypatch):
    store = {}
    saves = []
    loads = []
    state = SimpleNamespace(store=store, saves=saves, loads=loads, save_ok=True)

    def load(cfgdir=None):
        loads.append(cfgdir)
        return copy.deepcopy(store.get(cfgdir, {}))

    def save(d, cfgdir=None):
        saves.append(cfgdir)
        if state.save_ok:
            store[cfgdir] = copy.deepcopy(d)
        return state.save_ok

    monkeypatch.setattr(hooks, '_load', load)
    monkeypatch.setattr(hooks, '_save', save)
    return state


@pytest.fixture
def runs(monkeypatch):
    calls = []
    reply = {'value': SimpleNamespace(returncode=0, stdout='{}', stderr='')}

    def run(args, env=None, timeout=None, **kw):
        calls.append({'args': list(args), 'env': env, 'timeout': timeout})
        return reply['value']

    monkeypatch.setattr(automode, '_claude', lambda: '/fake/claude')
    monkeypatch.setattr(proc, 'run', run)
    return SimpleNamespace(calls=calls, reply=reply)


def test_environment_keeps_one_leading_sentinel_and_sibling_rules(settings):
    settings.store['acct'] = {'autoMode': {'environment': ['$defaults', 'old'],
                                           'soft_deny': ['$defaults', 'x'], 'allow': ['y']}}
    ok, _ = automode.set_environment(['  $defaults ', ' a ', '', 'a', '$defaults', '\tb\n'], 'acct')
    assert ok
    am = settings.store['acct']['autoMode']
    assert am['environment'] == ['$defaults', 'a', 'b']
    assert am['soft_deny'] == ['$defaults', 'x']
    assert am['allow'] == ['y']


def test_clearing_entries_removes_only_environment(settings):
    settings.store['acct'] = {'autoMode': {'environment': ['$defaults', 'a'], 'allow': ['y']},
                              'model': 'keep'}
    assert automode.set_environment([], 'acct')[0]
    assert settings.store['acct'] == {'autoMode': {'allow': ['y']}, 'model': 'keep'}

    settings.store['acct'] = {'autoMode': {'environment': ['$defaults', 'a']}}
    assert automode.set_environment([], 'acct')[0]
    assert 'autoMode' not in settings.store['acct']


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/automode.py:117 calls dict() on a non-dict autoMode, which raises "
    "ValueError instead of refusing; nothing is saved, but the caller gets an exception"))
def test_non_dict_auto_mode_refuses_without_saving(settings):
    settings.store['acct'] = {'autoMode': 'oops'}
    ok, _msg = automode.set_environment(['a'], 'acct')
    assert ok is False
    assert settings.saves == []


def test_save_failure_is_a_refusal_and_cfgdir_is_forwarded(settings):
    settings.save_ok = False
    ok, msg = automode.set_environment(['a'], 'explicit-acct')
    assert ok is False
    assert 'saved' not in msg
    assert settings.loads == ['explicit-acct']
    assert settings.saves == ['explicit-acct']


def test_default_mode_delegates_to_ccsettings_and_keeps_rules(settings):
    settings.store['acct'] = {'permissions': {'allow': ['Bash(ls)'], 'defaultMode': 'default'}}
    ok, _ = automode.set_default_mode('auto', 'acct')
    assert ok
    assert settings.store['acct']['permissions'] == {'allow': ['Bash(ls)'], 'defaultMode': 'auto'}
    before = copy.deepcopy(settings.store['acct'])
    assert automode.set_default_mode('turbo', 'acct')[0] is False
    assert settings.store['acct'] == before


def test_non_list_environment_is_empty_and_scalars_are_stringified(settings):
    settings.store['bad'] = {'autoMode': {'environment': 'not-a-list'}}
    assert automode.environment('bad') == []
    settings.store['ok'] = {'autoMode': {'environment': ['a', 1, None, True]}}
    assert automode.environment('ok') == ['a', '1', 'None', 'True']


def test_missing_executable_runs_nothing_and_writes_nothing(settings, runs, monkeypatch):
    monkeypatch.setattr(automode, '_claude', lambda: None)
    assert automode.reset('acct') == (False, 'claude.exe not found')
    assert runs.calls == []
    assert settings.saves == []


def test_nonzero_result_falls_back_to_bounded_text_and_none_is_refused(runs):
    runs.reply['value'] = SimpleNamespace(returncode=2, stdout='{"ok": true}\n', stderr='')
    ok, msg = automode.config_json('acct')
    assert ok is False
    assert msg == '{"ok": true}'

    runs.reply['value'] = SimpleNamespace(returncode=2, stdout='', stderr='e' * 900)
    ok, msg = automode.config_json('acct')
    assert ok is False
    assert msg == 'e' * 400

    runs.reply['value'] = None
    assert automode.config_json('acct') == (False, 'auto-mode config did not complete')


def test_argv_cfgdir_and_timeout_are_fixed(runs):
    runs.reply['value'] = SimpleNamespace(returncode=0, stdout='{"rules": []}', stderr='')
    ok, data = automode.config_json('explicit-acct')
    assert ok and data == {'rules': []}
    call = runs.calls[0]
    assert call['args'] == ['/fake/claude', 'auto-mode', 'config']
    assert call['env']['CLAUDE_CONFIG_DIR'] == 'explicit-acct'
    assert call['timeout'] == automode._TIMEOUT == 25


def test_reset_sends_yes_only_for_the_requested_account(runs, settings):
    runs.reply['value'] = SimpleNamespace(returncode=0, stdout='Removed autoMode settings\n', stderr='')
    ok, msg = automode.reset('explicit-acct')
    assert (ok, msg) == (True, 'Removed autoMode settings')
    call = runs.calls[0]
    assert call['args'][-1] == '--yes'
    assert call['env']['CLAUDE_CONFIG_DIR'] == 'explicit-acct'
    assert settings.saves == []

    automode.config_json('explicit-acct')
    assert '--yes' not in runs.calls[1]['args']
