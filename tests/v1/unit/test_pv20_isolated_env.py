"""T-033 (T-031 E1, Correction C-1012-T031; ADR-0053 A2): an isolated execution's
environment is built from nothing, from a pinned table of names, each from its one
authority. `spec.env` is a request: a name Core puts there is accepted only as the
value Core derives, anything else refuses before any launch. Synthetic values and a
fake launcher only: no process, no real environment read back, no Windows boundary.

What these tests do NOT show: that a kept PATH entry is unwritable by the execution,
where DLLs or modules are searched for, or what the real CLI needs to run."""

import dataclasses
import json
import os
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.harnesses import base

PINNED = {'SystemRoot', 'windir', 'SystemDrive', 'ComSpec', 'PATH', 'TEMP', 'TMP',
          'CLAUDE_CONFIG_DIR', 'USERPROFILE', 'HOME', 'APPDATA', 'LOCALAPPDATA', 'HOMEDRIVE',
          'HOMEPATH', 'ARCHEUS_EXECUTION_ID', 'ARCHEUS_HOME', 'ARCHEUS_HOOK_TOKEN',
          'GIT_TERMINAL_PROMPT', 'GIT_ASKPASS', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_KEY_0',
          'GIT_CONFIG_VALUE_0', 'GIT_CONFIG_NOSYSTEM'}
#: names that must never reach an isolated execution, whoever offers them
FORBIDDEN = ('ANTHROPIC_API_KEY', 'GITHUB_TOKEN', 'AWS_SECRET_ACCESS_KEY', 'GIT_DIR',
             'GIT_CONFIG_PARAMETERS', 'NODE_OPTIONS', 'PYTHONPATH', 'PYTHONSTARTUP',
             'HTTPS_PROXY', 'ARCHEUS_HOOK_ACTIVE', 'ARCHEUS_HOOK_WAIT', 'SSH_AUTH_SOCK')
SECRET = 'synthetic-value-never-reported'
TOKEN = 'hook_' + 'A' * 43


class FakeIsolation:
    def __init__(self):
        self.launches = []

    def launch(self, argv, *, cwd, env, paths):
        self.launches.append(dict(env))
        return SimpleNamespace(pid=424242), None


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Synthetic Windows directory, Core profile and temp, account home and workdir,
    each its own directory; the Windows rows pinned on so they run on every OS."""
    d = {k: tmp_path / k for k in ('Windows', 'profile', 'core-temp', 'account-home', 'work',
                                   'tools', 'more-tools')}
    for p in d.values():
        p.mkdir()
    (d['Windows'] / 'System32').mkdir()
    (d['Windows'] / 'System32' / 'cmd.exe').write_text('')
    monkeypatch.setattr(base, '_WINDOWS', True)
    monkeypatch.setenv('SystemRoot', str(d['Windows']))
    for k in ('USERPROFILE', 'HOME'):
        monkeypatch.setenv(k, str(d['profile']))
    for k in ('TEMP', 'TMP'):
        monkeypatch.setenv(k, str(d['core-temp']))
    monkeypatch.setenv('PATH', os.pathsep.join([str(d['tools']), str(d['more-tools'])]))
    monkeypatch.setattr(base.proc, 'spawn_detached', lambda *a, **k: (_ for _ in ()).throw(
        AssertionError('the unisolated launcher was reached')))
    monkeypatch.setattr(base.proc, 'process_create_time', lambda pid: 1.0)
    return {k: str(v) for k, v in d.items()}


def _spec(world, env=None, **kw):
    kw.setdefault('isolation', FakeIsolation())
    return base.ExecutionSpec(execution_id=ids.new_id('execution'), prompt='go',
                              workdir=world['work'],
                              account=base.AccountRef('claude-code:test', world['account-home']),
                              env=dict(env or {}), **kw)


def _core_env(spec):
    """What the manager and the Claude Code adapter put in spec.env today."""
    return dict(base.CAPABILITY_ENV, ARCHEUS_HOOK_TOKEN=TOKEN,
                CLAUDE_CONFIG_DIR=base.ExecPaths(spec.execution_id).config,
                ANTHROPIC_API_KEY=None, ANTHROPIC_AUTH_TOKEN=None)


def _launch(spec):
    base.spawn(spec, ['claude'])
    (env,) = spec.isolation.launches
    return env


def _with_core_env(world, **extra):
    spec = _spec(world)
    return dataclasses.replace(spec, env=dict(_core_env(spec), **extra))


def _inside(path, root):
    p, r = (os.path.normcase(os.path.realpath(x)) for x in (path, root))
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def test_the_block_is_exactly_the_pinned_names_each_from_its_authority(world):
    spec = _with_core_env(world)
    env = _launch(spec)
    p = base.ExecPaths(spec.execution_id)
    assert set(env) == PINNED
    assert len({k.upper() for k in env}) == len(env)
    assert (env['TEMP'], env['TMP'], env['CLAUDE_CONFIG_DIR']) == (p.tmp, p.tmp, p.config)
    assert env['USERPROFILE'] == env['HOME'] == p.home
    assert (env['APPDATA'], env['LOCALAPPDATA']) == (
        os.path.join(p.home, 'AppData', 'Roaming'), os.path.join(p.home, 'AppData', 'Local'))
    assert env['HOMEDRIVE'] + env['HOMEPATH'] == p.home
    assert os.path.isdir(env['APPDATA']) and os.path.isdir(env['LOCALAPPDATA'])
    assert (env['SystemRoot'], env['windir']) == (world['Windows'], world['Windows'])
    assert env['ComSpec'] == os.path.join(world['Windows'], 'System32', 'cmd.exe')
    assert env['SystemDrive'] == os.path.splitdrive(world['Windows'])[0]
    assert env['ARCHEUS_HOOK_TOKEN'] == TOKEN and env['GIT_CONFIG_NOSYSTEM'] == '1'
    for k, v in env.items():
        for root in (world['account-home'], world['profile']):
            assert not any(_inside(x, root) for x in v.split(os.pathsep) if x), k


def test_names_in_cores_own_environment_never_reach_the_block(world, monkeypatch):
    for name in FORBIDDEN:
        monkeypatch.setenv(name, SECRET)
    env = _launch(_with_core_env(world))
    assert not set(FORBIDDEN) & set(env) and SECRET not in json.dumps(env)


@pytest.mark.parametrize('name', FORBIDDEN + ('Unexpected',))
def test_a_name_offered_through_spec_env_refuses_before_any_launch(world, name):
    spec = _with_core_env(world, **{name: SECRET})
    with pytest.raises(base.SpawnFailed) as err:
        base.spawn(spec, ['claude'])
    assert spec.isolation.launches == []
    assert name in str(err.value) and SECRET not in str(err.value)
    ended = base.read_json(base.ExecPaths(spec.execution_id).ended)
    assert name in ended['error'] and SECRET not in json.dumps(ended)


def test_a_removal_request_is_absent_by_construction(world, monkeypatch):
    monkeypatch.setenv('SSH_AUTH_SOCK', SECRET)
    env = _launch(_with_core_env(world, SSH_AUTH_SOCK=None, NODE_OPTIONS=None))
    assert 'SSH_AUTH_SOCK' not in env and 'NODE_OPTIONS' not in env


def test_two_spellings_of_one_name_refuse(world):
    spec = _spec(world, env={'GIT_ASKPASS': '', 'git_askpass': ''})
    with pytest.raises(base.SpawnFailed, match='one variable'):
        base.spawn(spec, ['claude'])
    assert spec.isolation.launches == []


def test_a_core_name_in_another_case_is_written_once_canonically(world):
    spec = _spec(world)
    spec = dataclasses.replace(spec, env={
        'claude_config_dir': base.ExecPaths(spec.execution_id).config,
        'git_terminal_prompt': '0'})
    env = _launch(spec)
    assert 'CLAUDE_CONFIG_DIR' in env and 'GIT_TERMINAL_PROMPT' in env
    assert 'claude_config_dir' not in env and 'git_terminal_prompt' not in env


@pytest.mark.skipif(os.name != 'nt', reason="Windows's own environment is case-insensitive")
def test_an_os_value_in_another_case_still_yields_one_canonical_name(world, monkeypatch):
    monkeypatch.delenv('SystemRoot')
    monkeypatch.setenv('SYSTEMROOT', world['Windows'])
    env = _launch(_with_core_env(world))
    assert env['SystemRoot'] == world['Windows'] and 'SYSTEMROOT' not in env


@pytest.mark.parametrize('name, value', [
    ('GIT_ASKPASS', 'C:\\askpass.exe'),
    ('GIT_CONFIG_VALUE_0', 'store'),
    ('CLAUDE_CONFIG_DIR', 'ACCOUNT'),
    ('ARCHEUS_HOOK_TOKEN', 'not-a-token'),
    ('ARCHEUS_HOME', 'elsewhere'),
    ('ARCHEUS_HOOK_CMD', '["elsewhere"]'),
])
def test_a_core_value_that_is_not_what_core_derives_refuses(world, name, value):
    spec = _with_core_env(world, **{name: world['account-home'] if value == 'ACCOUNT'
                                    else value})
    spec = dataclasses.replace(spec, hook_settings=('python', '-I', 'hook.py'))
    with pytest.raises(base.SpawnFailed) as err:
        base.spawn(spec, ['claude'])
    assert spec.isolation.launches == [] and name in str(err.value)


def test_the_fake_harness_hook_command_is_accepted_as_derived(world):
    spec = dataclasses.replace(_with_core_env(world), hook_settings=('python', '-I', 'hook.py'))
    spec = dataclasses.replace(spec, env=dict(
        spec.env, ARCHEUS_HOOK_CMD=json.dumps(['python', '-I', 'hook.py'])))
    assert set(_launch(spec)) == PINNED | {'ARCHEUS_HOOK_CMD'}


def test_path_keeps_only_absolute_existing_entries_outside_every_private_tree(world,
                                                                              monkeypatch):
    p_home = os.path.join(world['account-home'], 'bin')
    inside = [p_home, os.path.join(world['profile'], 'bin'), os.path.join(world['work'], 'bin'),
              os.path.join(world['core-temp'], 'bin'), os.path.join(base.archeus_home(), 'bin')]
    for d in inside:
        os.makedirs(d, exist_ok=True)
    entries = ['', '.', 'relative' + os.sep + 'bin', 'C:drive-relative',
               '\\\\server\\share\\bin', os.path.join(world['tools'], 'missing'),
               world['tools'], *inside, world['tools'] + os.sep, world['more-tools']]
    monkeypatch.setenv('PATH', os.pathsep.join(entries))
    env = _launch(_with_core_env(world))
    assert env['PATH'].split(os.pathsep) == [world['tools'], world['more-tools']]


def test_nothing_falls_back_to_cores_path_when_no_entry_survives(world, monkeypatch):
    monkeypatch.setenv('PATH', os.pathsep.join(['', '.', world['profile']]))
    assert _launch(_with_core_env(world))['PATH'] == ''


@pytest.mark.parametrize('damage', ['missing', 'inside the account home', 'no cmd.exe'])
def test_an_unusable_system_root_refuses(world, monkeypatch, tmp_path, damage):
    if damage == 'missing':
        monkeypatch.delenv('SystemRoot')
    elif damage == 'inside the account home':
        bad = os.path.join(world['account-home'], 'Windows')
        os.makedirs(os.path.join(bad, 'System32'))
        open(os.path.join(bad, 'System32', 'cmd.exe'), 'w').close()
        monkeypatch.setenv('SystemRoot', bad)
    else:
        os.remove(os.path.join(world['Windows'], 'System32', 'cmd.exe'))
    spec = _with_core_env(world)
    with pytest.raises(base.SpawnFailed):
        base.spawn(spec, ['claude'])
    assert spec.isolation.launches == []


def test_the_windows_rows_apply_only_where_the_isolation_exists(world, monkeypatch):
    monkeypatch.setattr(base, '_WINDOWS', False)
    env = _launch(_with_core_env(world))
    assert set(env) == PINNED - {'SystemRoot', 'windir', 'SystemDrive', 'ComSpec'}


def test_a_resume_keeps_the_private_paths_and_their_content_with_a_new_token(world):
    spec = _with_core_env(world)
    first = _launch(spec)
    p = base.ExecPaths(spec.execution_id)
    open(os.path.join(p.home, 'AppData', 'Roaming', 'kept.txt'), 'w').close()
    base.mark_ended(p, 0)
    resumed = dataclasses.replace(spec, process_seq=2, isolation=FakeIsolation(),
                                  env=dict(spec.env, ARCHEUS_HOOK_TOKEN='hook_' + 'B' * 43))
    second = _launch(resumed)
    assert {k: v for k, v in second.items() if k != 'ARCHEUS_HOOK_TOKEN'} == \
        {k: v for k, v in first.items() if k != 'ARCHEUS_HOOK_TOKEN'}
    assert second['ARCHEUS_HOOK_TOKEN'] != first['ARCHEUS_HOOK_TOKEN']
    assert os.listdir(os.path.join(p.home, 'AppData', 'Roaming')) == ['kept.txt']


def test_a_continuation_gets_its_own_private_paths(world):
    a, b = _launch(_with_core_env(world)), _launch(_with_core_env(world))
    for k in ('USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'CLAUDE_CONFIG_DIR'):
        assert a[k] != b[k]


def test_a_home_that_cannot_be_made_refuses_before_any_launch(world):
    spec = _with_core_env(world)
    p = base.ExecPaths(spec.execution_id)
    os.makedirs(os.path.dirname(p.home))
    open(p.home, 'w').close()
    with pytest.raises(base.SpawnFailed):
        base.spawn(spec, ['claude'])
    assert spec.isolation.launches == []
    assert base.read_json(p.ended)['error']


def test_an_ordinary_launch_environment_is_unchanged(world, monkeypatch):
    seen = {}

    def detached(argv, *, cwd, env, **kw):
        seen.update(env)
        return SimpleNamespace(pid=424242), None
    monkeypatch.setattr(base.proc, 'spawn_detached', detached)
    monkeypatch.setenv('NODE_OPTIONS', SECRET)
    monkeypatch.setenv('SSH_AUTH_SOCK', SECRET)
    spec = _spec(world, isolation=None, env={'GIT_ASKPASS': '', 'SSH_AUTH_SOCK': None,
                                             'EXTRA': 'kept'})
    base.spawn(spec, ['claude'])
    want = dict(os.environ, GIT_ASKPASS='', EXTRA='kept', ARCHEUS_EXECUTION_ID=spec.execution_id,
                ARCHEUS_HOME=base.archeus_home())
    want.pop('SSH_AUTH_SOCK')
    assert seen == want
