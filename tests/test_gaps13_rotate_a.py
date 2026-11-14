"""T-1444: claude_sessions/rotate.py lines 333-393 at tip 026ea58e (re-located at 44aaf17f).

Candidate gaps, not measured coverage. Ten ranked candidates, install-failure
visibility first:

1  :356-361 test_failing_account_does_not_hide_partial_install      DROPPED: no user-producible raise in the per-account hook writers
2  :358     test_enabled_raising_returns_empty_without_touching_hooks  (candidate, not written: no reach)
3  :364-369 test_hook_installed_error_is_distinct_from_no_accounts    (candidate, not written: no reach)
4  :358-359 test_enabled_selects_install_for_every_account
5  :358-359 test_disabled_uninstall_is_passed_through
6  :347-361 test_repeated_ensure_hook_does_not_duplicate_entries
7  :364-369 test_hook_installed_keeps_partial_state_per_account
8  :333-341 _launch_opts keys: already pinned by test_gaps6_claude_sessions_rotate_a/_b; SKIP
9  :372-390 next_account: already pinned by test_gaps6_claude_sessions_rotate_a/_b; SKIP
10 :347-349 test_mode_change_flips_action_between_calls

Seams: hooks.account_dirs, hooks.install_limit_hook, hooks.uninstall_limit_hook,
hooks.limit_hook_installed, hooks.across_accounts (real), rotate.enabled. Every
account dir is a tmp_path child; no real Claude config dir, no home, no subprocess.
"""

import json

import pytest

from claude_sessions import hooks
from claude_sessions import rotate


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    dirs = {}
    for name in ('a', 'b', 'c'):
        d = tmp_path / name
        d.mkdir()
        dirs[name] = str(d)
    monkeypatch.setattr(hooks, 'account_dirs', lambda: list(dirs.items()))
    return dirs


def _set_enabled(monkeypatch, value):
    monkeypatch.setattr(rotate, 'enabled', lambda: value)


def test_enabled_selects_install_for_every_account(accounts, monkeypatch):
    installed, removed = [], []
    _set_enabled(monkeypatch, True)
    monkeypatch.setattr(hooks, 'install_limit_hook',
                        lambda cfgdir=None: installed.append(cfgdir) or True)
    monkeypatch.setattr(hooks, 'uninstall_limit_hook',
                        lambda cfgdir=None: removed.append(cfgdir) or True)
    result = rotate.ensure_hook()
    assert installed == [accounts['a'], accounts['b'], accounts['c']]
    assert removed == []
    assert result == {'a': True, 'b': True, 'c': True}


def test_disabled_uninstall_is_passed_through(accounts, monkeypatch):
    installed = []
    _set_enabled(monkeypatch, False)
    monkeypatch.setattr(hooks, 'install_limit_hook',
                        lambda cfgdir=None: installed.append(cfgdir) or True)
    monkeypatch.setattr(hooks, 'uninstall_limit_hook',
                        lambda cfgdir=None: 'removed-' + cfgdir[-1])
    result = rotate.ensure_hook()
    assert installed == []
    assert result == {'a': 'removed-a', 'b': 'removed-b', 'c': 'removed-c'}


def test_hook_installed_keeps_partial_state_per_account(accounts, monkeypatch):
    partial = {accounts['a']: True, accounts['b']: False, accounts['c']: False}
    monkeypatch.setattr(hooks, 'limit_hook_installed', lambda cfgdir=None: partial[cfgdir])
    assert rotate.hook_installed() == {'a': True, 'b': False, 'c': False}


def test_repeated_ensure_hook_does_not_duplicate_entries(accounts, monkeypatch):
    _set_enabled(monkeypatch, True)
    rotate.ensure_hook()
    rotate.ensure_hook()
    for d in accounts.values():
        with open(f'{d}/settings.json', encoding='utf-8') as fh:
            stop = json.load(fh)['hooks']['StopFailure']
        commands = [h['command'] for e in stop for h in e['hooks']
                    if 'limit_hook.py' in h['command']]
        assert len(commands) == 1


def test_mode_change_flips_action_between_calls(accounts, monkeypatch):
    calls = []
    state = {'on': True}
    monkeypatch.setattr(rotate, 'enabled', lambda: state['on'])
    monkeypatch.setattr(hooks, 'install_limit_hook',
                        lambda cfgdir=None: calls.append('install') or True)
    monkeypatch.setattr(hooks, 'uninstall_limit_hook',
                        lambda cfgdir=None: calls.append('uninstall') or True)
    rotate.ensure_hook()
    state['on'] = False
    rotate.ensure_hook()
    assert calls == ['install'] * 3 + ['uninstall'] * 3
