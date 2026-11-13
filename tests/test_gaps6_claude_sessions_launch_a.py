"""T-1278: claude_sessions/launch.py lines 17-103 at tip 6bbd3b44 (the account,
project folder, telemetry, terminal and alternate-harness branches of
build_launch_command). Selected probes, not measured coverage.

Selected branches: 31 explicit cfgdir vs rotate.elect; 32 invalid encoded name;
40 account_env with the chosen home; 48 telemetry from one settings snapshot;
54 terminal returns no argv; 68 opts copied before harness adjustments; 70
existing add_dirs only; 73 project system prompt; 86 bare Anthropic model and
unsupported effort cleared for alternate harnesses only; 77 missing CLI refusal.
"""

import os
from types import SimpleNamespace

import pytest

from claude_sessions import config, harnesses, launch, rotate, sessions


@pytest.fixture
def seams(monkeypatch, tmp_path):
    s = SimpleNamespace(elect_calls=0, elected=str(tmp_path / 'elected'), settings={'launch_fallback_models': []},
                        settings_calls=0, claude_calls=0, account_env_calls=[], otel_seen=[])

    def elect(current=None):
        s.elect_calls += 1
        return s.elected

    def load_settings():
        s.settings_calls += 1
        return s.settings

    def get_claude_exe():
        s.claude_calls += 1
        return 'C:/fake/claude.exe'

    real_account_env = config.account_env

    def account_env(cfgdir=None, harness=None):
        s.account_env_calls.append(cfgdir)
        return real_account_env(cfgdir, harness)

    def otel_env(st=None):
        s.otel_seen.append(st)
        return {}

    monkeypatch.setattr(rotate, 'elect', elect)
    monkeypatch.setattr(launch, 'load_settings', load_settings)
    monkeypatch.setattr(launch, 'get_claude_exe', get_claude_exe)
    monkeypatch.setattr(config, 'account_env', account_env)
    monkeypatch.setattr(config, 'otel_env', otel_env)
    monkeypatch.setattr(sessions, 'read_extra_paths', lambda p: [])
    monkeypatch.setattr(sessions, 'load_add_dirs', lambda p: [])
    monkeypatch.setattr(harnesses, 'of', lambda cfgdir=None: harnesses.descriptor())
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: 'C:/fake/claude.exe')
    return s


@pytest.fixture
def alt(monkeypatch):
    seen = {}
    desc = dict(harnesses.descriptor(), id='codex', label='Codex', efforts=['low', 'medium'])

    def launch_argv(exe, choice, o, path):
        seen['opts'] = o
        return ['codex', exe]

    monkeypatch.setattr(harnesses, 'of', lambda cfgdir=None: desc)
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: 'C:/fake/codex.exe')
    monkeypatch.setattr(harnesses, 'impl', lambda key, hid=None: launch_argv)
    return seen


def opts(**kw):
    base = {'cfgdir': '', 'model': '', 'effort': '', 'perm': '', 'name': '', 'worktree': '',
            'agent': '', 'prompt': '', 'provider': '', 'provider_model': ''}
    base.update(kw)
    return base


def test_explicit_cfgdir_wins_and_skips_rotation_election(seams, tmp_path):
    acct = str(tmp_path / 'explicit')
    args, env, proj = launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=acct))
    assert seams.elect_calls == 0
    assert seams.account_env_calls == [acct]
    assert proj == store_project(acct, 'p-x')


def test_elected_account_used_only_without_explicit_cfgdir(seams, tmp_path):
    launch.build_launch_command('p-x', 'p-x', 'new', opts())
    assert seams.elect_calls == 1
    assert seams.account_env_calls == [seams.elected]


def test_invalid_encoded_name_refuses_before_account_side_work(seams, tmp_path):
    with pytest.raises(ValueError):
        launch.build_launch_command('p-x', '../escape', 'new', opts(cfgdir=str(tmp_path / 'acct')))
    assert seams.account_env_calls == []
    assert seams.settings_calls == 0
    assert seams.claude_calls == 0


def test_account_env_pins_selected_home_and_drops_api_key(seams, tmp_path, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-key')
    acct = str(tmp_path / 'acct')
    args, env, _ = launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=acct))
    assert env['CLAUDE_CONFIG_DIR'] == acct
    assert 'ANTHROPIC_API_KEY' not in env
    assert os.environ['ANTHROPIC_API_KEY'] == 'synthetic-key'


def test_telemetry_reads_one_settings_snapshot_and_absent_adds_nothing(seams, tmp_path, monkeypatch):
    seams.settings['launch_fallback_models'] = []
    monkeypatch.setattr(config, 'otel_env', lambda st=None: seams.otel_seen.append(st) or {'CLAUDE_CODE_ENABLE_TELEMETRY': '1'})
    args, env, _ = launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=str(tmp_path / 'a')))
    assert seams.settings_calls == 1
    assert seams.otel_seen[0] is seams.settings
    assert env['CLAUDE_CODE_ENABLE_TELEMETRY'] == '1'

    monkeypatch.setattr(config, 'otel_env', lambda st=None: {})
    args, env, _ = launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=str(tmp_path / 'a')))
    assert 'CLAUDE_CODE_ENABLE_TELEMETRY' not in env


def test_terminal_returns_no_argv_before_claude_lookup(seams, tmp_path):
    acct = str(tmp_path / 'acct')
    args, env, proj = launch.build_launch_command('p-x', 'p-x', 'terminal', opts(cfgdir=acct))
    assert args is None
    assert proj == store_project(acct, 'p-x')
    assert env['CLAUDE_CONFIG_DIR'] == acct
    assert seams.claude_calls == 0


def test_alternate_harness_gets_a_copy_and_caller_dict_is_unchanged(seams, alt, tmp_path):
    o = opts(cfgdir=str(tmp_path / 'codex'), model='claude-opus-5', effort='max', perm='auto')
    before = dict(o)
    launch.build_launch_command('p-x', 'p-x', 'new', o)
    assert o == before
    assert alt['opts'] is not o


def test_add_dirs_keep_existing_derived_dirs_and_explicit_ones_survive(seams, monkeypatch, tmp_path):
    good = str(tmp_path / 'exists')
    gone = str(tmp_path / 'gone')
    monkeypatch.setattr(sessions, 'load_add_dirs', lambda p: [good, gone])
    monkeypatch.setattr(launch.os.path, 'isdir', lambda p: p == good)
    acct = str(tmp_path / 'acct')
    args, _env, _ = launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=acct))
    assert args[args.index('--add-dir') + 1:] == [good]

    args, _env, _ = launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=acct, add_dirs=[gone]))
    assert args[args.index('--add-dir') + 1:] == [gone]


def test_project_system_prompt_forwarded_when_present_and_explicit_override_kept(seams, alt, tmp_path):
    acct = str(tmp_path / 'acct')
    proj = store_project(acct, 'p-x')
    os.makedirs(proj)
    sp = os.path.join(proj, 'system-prompt.txt')
    with open(sp, 'w', encoding='utf-8') as f:
        f.write('be brief\n')
    launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=acct))
    assert alt['opts']['system_prompt_file'] == sp

    os.remove(sp)
    launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=acct))
    assert 'system_prompt_file' not in alt['opts']

    launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=acct, system_prompt_file='C:/x.txt'))
    assert alt['opts']['system_prompt_file'] == 'C:/x.txt'


def test_bare_anthropic_model_and_unsupported_effort_cleared_only_for_alternate(seams, alt, tmp_path, monkeypatch):
    acct = str(tmp_path / 'acct')
    launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=acct, model='claude-opus-5', effort='max'))
    assert alt['opts']['model'] == '' and alt['opts']['effort'] == ''

    launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=acct, model='openrouter/claude-x', effort='low'))
    assert alt['opts']['model'] == 'openrouter/claude-x' and alt['opts']['effort'] == 'low'

    monkeypatch.setattr(harnesses, 'of', lambda cfgdir=None: harnesses.descriptor())
    args, _env, _ = launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=acct, model='claude-opus-5'))
    assert args[args.index('--model') + 1] == 'claude-opus-5'


def test_missing_alternate_cli_refuses_without_claude_fallback(seams, alt, tmp_path, monkeypatch):
    monkeypatch.setattr(harnesses, 'exe', lambda hid=None: None)
    with pytest.raises(RuntimeError, match='Codex not found'):
        launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=str(tmp_path / 'codex')))
    assert seams.claude_calls == 0


def test_missing_default_cli_refuses_before_argv_completion(seams, tmp_path, monkeypatch):
    monkeypatch.setattr(launch, 'get_claude_exe', lambda: None)
    with pytest.raises(RuntimeError, match='claude.exe not found'):
        launch.build_launch_command('p-x', 'p-x', 'new', opts(cfgdir=str(tmp_path / 'acct')))


def store_project(acct, enc):
    from claude_sessions import store
    return store.project_folder(acct, enc)
