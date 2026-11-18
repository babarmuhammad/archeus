"""T-056 (T-054 A6-2; ADR-0053 A6): a confined verifier's environment is built from
nothing. Its scratch is its profile and temp, PATH is the Core-staged toolchain and
nothing else, and no caller can add a name. Synthetic directories and values only:
no process, no real environment read back, no Windows boundary.

What these tests do NOT show: that the toolchain is unwritable by the verifier, where
DLLs or modules are searched for, or that any real check can run in it."""

import inspect
import os

import pytest

from archeus.harnesses import base

PINNED = {'SystemRoot', 'windir', 'SystemDrive', 'ComSpec', 'PATH', 'TEMP', 'TMP',
          'USERPROFILE', 'HOME', 'APPDATA', 'LOCALAPPDATA', 'HOMEDRIVE', 'HOMEPATH'}
#: names Core's own environment carries that must never reach a verifier
LEAKS = {'ARCHEUS_HOME': None, 'ARCHEUS_EXECUTION_ID': 'execution_x',
         'ARCHEUS_HOOK_TOKEN': 'hook_' + 'A' * 43, 'ARCHEUS_HOOK_CMD': '[]',
         'CLAUDE_CONFIG_DIR': None, 'ANTHROPIC_API_KEY': 'synthetic',
         'ANTHROPIC_AUTH_TOKEN': 'brk_synthetic', 'ANTHROPIC_BASE_URL': 'http://127.0.0.1:1',
         'OPENAI_API_KEY': 'synthetic', 'GITHUB_TOKEN': 'synthetic', 'GIT_DIR': None,
         'GIT_CONFIG_GLOBAL': None, 'GIT_CONFIG_PARAMETERS': "'core.hookspath'='x'",
         'HTTPS_PROXY': 'http://proxy', 'HTTP_PROXY': 'http://proxy', 'NO_PROXY': '*',
         'PYTHONPATH': None, 'PYTHONSTARTUP': None, 'NODE_OPTIONS': '--require x',
         'SSH_AUTH_SOCK': 'pipe'}


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A synthetic Windows directory, Core's own profile, temp and PATH, a staged
    toolchain and a scratch, each its own directory; Windows rows pinned on."""
    d = {k: tmp_path / k for k in ('Windows', 'profile', 'core-temp', 'core-tools',
                                   'stage-py', 'stage-bin', 'scratch')}
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
    monkeypatch.setenv('PATH', str(d['core-tools']))
    for k, v in LEAKS.items():
        monkeypatch.setenv(k, v or str(tmp_path / k.lower()))
    return {k: str(v) for k, v in d.items()}


def _env(w, *dirs):
    return base._verifier_env([w[x] for x in dirs or ('stage-py',)], w['scratch'])


def test_the_environment_is_the_pinned_table_and_nothing_core_carries(world):
    env = _env(world)
    assert set(env) == PINNED
    assert not set(env) & set(LEAKS)
    assert not [k for k in env if k.upper().startswith(('ARCHEUS_', 'GIT_', 'CLAUDE_'))
                or 'PROXY' in k.upper() or 'TOKEN' in k.upper() or 'KEY' in k.upper()]


def test_path_is_exactly_the_staged_toolchain_in_order(world):
    assert _env(world)['PATH'] == world['stage-py']
    assert _env(world, 'stage-bin', 'stage-py')['PATH'] == os.pathsep.join(
        [world['stage-bin'], world['stage-py']])
    assert world['core-tools'] not in _env(world)['PATH']


def test_profile_and_temp_live_inside_scratch(world):
    env = _env(world)
    for k in ('TEMP', 'TMP', 'USERPROFILE', 'HOME', 'APPDATA', 'LOCALAPPDATA'):
        assert base._inside(env[k], [world['scratch']]), k
    assert env['HOMEDRIVE'] + env['HOMEPATH'] == env['HOME']


def test_the_windows_rows_come_from_system_root_only(world):
    env = _env(world)
    assert (env['SystemRoot'], env['windir']) == (world['Windows'], world['Windows'])
    assert env['ComSpec'] == os.path.join(world['Windows'], 'System32', 'cmd.exe')


def test_nothing_else_in_cores_environment_changes_it(world, monkeypatch):
    first = _env(world)
    for k, v in LEAKS.items():
        if v:
            monkeypatch.setenv(k, v + '-changed')
    monkeypatch.setenv('PATH', world['stage-bin'])
    monkeypatch.setenv('TEMP', world['profile'])
    assert _env(world) == first


def test_no_caller_can_add_a_name(world):
    assert list(inspect.signature(base._verifier_env).parameters) == ['toolchain_dirs', 'scratch']
    with pytest.raises(TypeError):
        base._verifier_env([world['stage-py']], world['scratch'], env={'HTTPS_PROXY': 'x'})


@pytest.mark.parametrize('dirs', [[], ['relative/bin'], ['<missing>'], ['<scratch>/bin']])
def test_a_toolchain_that_is_not_staged_outside_scratch_refuses(world, dirs):
    os.makedirs(os.path.join(world['scratch'], 'bin'))
    dirs = [d.replace('<missing>', os.path.join(world['scratch'], '..', 'nope'))
             .replace('<scratch>', world['scratch']) for d in dirs]
    with pytest.raises(ValueError):
        base._verifier_env(dirs, world['scratch'])


@pytest.mark.parametrize('scratch', ['relative', '<missing>'])
def test_a_scratch_that_is_not_an_absolute_directory_refuses(world, scratch):
    scratch = scratch.replace('<missing>', world['scratch'] + '-gone')
    with pytest.raises(ValueError):
        base._verifier_env([world['stage-py']], scratch)


def test_a_system_root_inside_the_scratch_refuses(world, monkeypatch):
    fake = os.path.join(world['scratch'], 'Windows')
    os.makedirs(os.path.join(fake, 'System32'))
    open(os.path.join(fake, 'System32', 'cmd.exe'), 'w').close()
    monkeypatch.setenv('SystemRoot', fake)
    with pytest.raises(ValueError):
        _env(world)


def test_off_windows_there_are_no_windows_rows(world, monkeypatch):
    monkeypatch.setattr(base, '_WINDOWS', False)
    assert set(_env(world)) == PINNED - {'SystemRoot', 'windir', 'SystemDrive', 'ComSpec'}
