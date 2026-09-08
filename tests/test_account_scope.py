"""Anything written into Claude Code's settings.json must reach EVERY account.

The bug this file exists for: `hooks.settings_path` was computed at import time
from the single active account dir, and `statusline.install/remove/is_installed`
route through `hooks._load`/`_save` on purpose so there is one reader and one
writer for that file. So they inherited the binding, and on a machine with three
accounts configured only `~/.claude` ever got a statusLine or a hooks block —
while every surface reported a confident "installed".

The shape of the fix is what these tests pin down:
  · the accessors take a cfgdir, and cfgdir=None still means the active account
    (so the module attribute stays patchable and nothing else had to move);
  · "installed" is reported PER ACCOUNT, because partial installation is the
    real state of a machine that ran the old code;
  · a refusal in one account does not abort the others.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import config, hooks
from claude_sessions import statusline as sl


def _accounts(monkeypatch, tmp_path, names=('default', 'personal', 'Lorenzo')):
    """A multi-account world. `Sandbox` deliberately pins a single-account one,
    so these tests build their own rather than fighting it."""
    dirs = []
    for n in names:
        d = tmp_path / f'cfg-{n}'
        d.mkdir()
        (d / 'settings.json').write_text('{}', encoding='utf-8')
        dirs.append((n, str(d)))
    monkeypatch.setattr(config, 'all_config_dirs', lambda: list(dirs))
    # cfgdir=None must still resolve somewhere inside tmp_path
    monkeypatch.setattr(hooks, 'settings_path', os.path.join(dirs[0][1], 'settings.json'))
    return dirs


def _read(cfgdir):
    with open(os.path.join(cfgdir, 'settings.json'), encoding='utf-8') as f:
        return json.load(f)


# ── the reported bug ─────────────────────────────────────────

def test_installing_the_statusline_reaches_every_account(monkeypatch, tmp_path):
    """The regression test for what the user actually hit.

    Mutation-verified: pinning `_load`/`_save` back to the module-level
    `settings_path` (the pre-fix behaviour) leaves the other two accounts at
    `{}` and this fails on the first of them.
    """
    dirs = _accounts(monkeypatch, tmp_path)

    ok, msg = sl.install_all()

    assert ok, msg
    for name, d in dirs:
        cmd = _read(d).get('statusLine', {}).get('command', '')
        assert 'claude_sessions' in cmd, f'{name} did not get a statusline'


def test_removing_the_statusline_reaches_every_account(monkeypatch, tmp_path):
    dirs = _accounts(monkeypatch, tmp_path)
    sl.install_all()

    ok, _ = sl.remove_all()

    assert ok
    for name, d in dirs:
        assert 'statusLine' not in _read(d), f'{name} kept its statusline'


def test_a_targeted_install_writes_exactly_one_account(monkeypatch, tmp_path):
    """Fan-out is the default, not the only option — the per-account row in the
    UI has to be able to act on its own account alone."""
    dirs = _accounts(monkeypatch, tmp_path)
    target = dirs[1]

    ok, _ = sl.install(target[1])

    assert ok
    assert 'statusLine' in _read(target[1])
    for name, d in dirs:
        if d != target[1]:
            assert 'statusLine' not in _read(d), f'{name} was written unasked'


def test_installed_state_is_reported_per_account(monkeypatch, tmp_path):
    """Partial installation is exactly the state the old code left behind, so
    a single collapsed bool cannot be the answer."""
    dirs = _accounts(monkeypatch, tmp_path)
    sl.install(dirs[0][1])

    state = dict((name, done) for name, _d, done, _blocked in sl.by_account())

    assert state == {'default': True, 'personal': False, 'Lorenzo': False}


def test_one_account_refusing_does_not_abort_the_others(monkeypatch, tmp_path):
    """statusLine is single-valued and archeus refuses to clobber someone
    else's. That refusal is per account: it must not cost the other accounts
    their install, and it must be reported rather than swallowed."""
    dirs = _accounts(monkeypatch, tmp_path)
    mine = dirs[1][1]
    with open(os.path.join(mine, 'settings.json'), 'w', encoding='utf-8') as f:
        json.dump({'statusLine': {'type': 'command', 'command': '~/mine.sh'}}, f)

    ok, msg = sl.install_all()

    assert ok                                   # the others still went in
    assert 'personal' in msg                    # and the skip is named
    assert _read(mine)['statusLine']['command'] == '~/mine.sh'
    assert 'claude_sessions' in _read(dirs[0][1])['statusLine']['command']
    assert 'claude_sessions' in _read(dirs[2][1])['statusLine']['command']


# ── the same fix, one layer down ─────────────────────────────

def test_hooks_fan_out_across_every_account(monkeypatch, tmp_path):
    """`across_accounts` is the generic helper, so every install_*/uninstall_*
    inherits the fix instead of each growing its own `_all` variant."""
    dirs = _accounts(monkeypatch, tmp_path)

    hooks.across_accounts(hooks.install_memory_hook)

    for name, d in dirs:
        entries = _read(d).get('hooks', {}).get('UserPromptSubmit') or []
        cmds = [h.get('command', '') for e in entries for h in (e.get('hooks') or [])]
        assert any('recall_hook.py' in c for c in cmds), f'{name} missing the recall hook'
    assert hooks.across_accounts(hooks.memory_hook_installed) == {
        n: True for n, _ in dirs}


def test_hooks_uninstall_fans_out_too(monkeypatch, tmp_path):
    dirs = _accounts(monkeypatch, tmp_path)
    hooks.across_accounts(hooks.install_memory_hook)

    hooks.across_accounts(hooks.uninstall_memory_hook)

    assert hooks.across_accounts(hooks.memory_hook_installed) == {
        n: False for n, _ in dirs}


def test_settings_path_for_none_is_still_the_module_attribute(monkeypatch, tmp_path):
    """The compatibility hinge. Nine existing tests redirect writes by patching
    `hooks.settings_path`; if cfgdir=None stopped honouring it they would all
    silently start writing to the real ~/.claude."""
    p = tmp_path / 'redirected.json'
    monkeypatch.setattr(hooks, 'settings_path', str(p))

    assert hooks.settings_path_for(None) == str(p)
    assert hooks.settings_path_for(str(tmp_path)) == str(tmp_path / 'settings.json')


def test_claude_config_dir_env_wins_over_the_saved_setting(monkeypatch, tmp_path):
    """The other half of the reported bug.

    archeus WRITES `CLAUDE_CONFIG_DIR` into the child environment at five
    spawn sites to pick the account, but `get_config_dir` never read it back —
    it went straight to the saved setting. So the statusline running inside a
    session launched under another account resolved the wrong dir and labelled
    every session 'default'. Env first is also Claude Code's own precedence.

    Mutation-verified: dropping the env lookup makes this return the setting.
    """
    env_dir = tmp_path / 'from-env'
    env_dir.mkdir()
    monkeypatch.setattr(config, 'load_settings',
                        lambda: {'claude_config_dir': str(tmp_path / 'from-setting')})

    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(env_dir))
    assert config.get_config_dir() == str(env_dir)

    monkeypatch.delenv('CLAUDE_CONFIG_DIR')
    assert config.get_config_dir() == str(tmp_path / 'from-setting')


def test_an_empty_config_dir_env_does_not_shadow_the_setting(monkeypatch, tmp_path):
    """An exported-but-empty var is how a shell says "unset"; treating '' as a
    real override would silently send everything to ~/.claude."""
    monkeypatch.setattr(config, 'load_settings',
                        lambda: {'claude_config_dir': str(tmp_path / 'from-setting')})
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', '   ')

    assert config.get_config_dir() == str(tmp_path / 'from-setting')


def test_the_account_segment_names_the_account_the_session_runs_under(
        monkeypatch, tmp_path):
    """End to end: the segment exists to tell you WHICH account is being spent,
    so reporting 'default' inside a `personal` session was worse than useless."""
    dirs = _accounts(monkeypatch, tmp_path)
    monkeypatch.setattr(config, 'config_dir', dirs[1][1])

    assert 'personal' in sl.plain(sl._account_bit())


def test_an_account_scoped_write_never_touches_the_active_account(monkeypatch, tmp_path):
    """The inverse of the original bug: now that cfgdir exists, it must actually
    be used rather than being accepted and ignored."""
    dirs = _accounts(monkeypatch, tmp_path)
    hooks.install_memory_hook(cfgdir=dirs[2][1])

    assert _read(dirs[0][1]) == {}
    assert _read(dirs[1][1]) == {}
    assert 'UserPromptSubmit' in _read(dirs[2][1])['hooks']
