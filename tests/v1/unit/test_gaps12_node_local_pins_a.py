"""T-1439: the uncovered branches of `archeus/node/local.py` lines 2027-2110 inclusive
(`_store_pin`, `_pin_area`, `_pin_files`, `_outside_executions`) at tip 026ea58e. No source
file is edited. Lines 2100-2110 were read: a refusal in `_outside_executions` raises StoreError
(2104), and the caller `_source` (2107) sits below it.

Ten selected branches, denial first, then boundaries, then error paths:

1. 2032-2036 _store_pin environment: only SYSTEMROOT, WINDIR, TEMP and TMP survive from the
   inherited environment; PATH is the git exe's directory; GIT_ALLOW_PROTOCOL 'file';
   GIT_TERMINAL_PROMPT '0'. Catches: the inherited-name filter widened, PATH or the protocol
   and prompt settings removed.
2. 2038-2040 _store_pin with no git dir: GIT_CEILING_DIRECTORIES is repos; cwd is empty for
   'version' and repos otherwise; no --git-dir in argv. Catches: the ceiling or the cwd branch removed.
3. 2042-2047 _store_pin with a git dir: --git-dir and --no-replace-objects, cwd is the git dir,
   --attr-source EMPTY_TREE only for 'trusted', -c core.logAllRefUpdates=false only for 'seed'.
   Catches: either mode branch removed or inverted.
4. 2048-2050 _store_pin hardening: the six -c settings appear for every mode and with or without
   a git dir. Catches: any one of them removed.
5. 2054-2057 _pin_area layout: repos, repos/.pin, .pin/empty, .pin/empty.cfg. Catches: any path
   component changed.
6. 2065-2066 _pin_files: a pin path inside a recorded workdir is refused before anything is made.
   Catches: the _outside_executions call removed or moved after the mkdir loop.
7. 2082-2083 _pin_files: a non-empty empty directory, or a cfg file with bytes, raises 'a pin file is
   not empty'. Catches: either half of the test removed.
8. 2077-2081 _pin_files: an absent cfg is created empty; a present one is left alone (same inode and
   mtime). Catches: the _present test or the write removed.
9. 2092-2093 _outside_executions: a str, bytes, or one-shot iterator workdirs raises 'workdirs is a
   collection of paths'. Catches: the type or iterator test removed.
10. 2094-2104 _outside_executions: an empty workdirs list is allowed; None and '' are ignored; a path
    equal to run_dir() and one under archeus_home()/worktrees are refused; a path outside passes.
    Catches: the `if w` filter, the run_dir area, or the worktrees area removed.

Every path helper is faked to a fixed location under tmp_path or to a string: repos_dir, run_dir,
archeus_home and _git_exe. Environment probes set and clear their own variables and never read
os.environ. No git, no subprocess, no Win32, no network.
"""

import os
from types import SimpleNamespace

import pytest

from archeus.node import local
from archeus.node.local import StoreError

EXE_NAME = 'git.exe' if os.name == 'nt' else 'git'


@pytest.fixture
def layout(tmp_path, monkeypatch):
    home, repos, run = tmp_path / 'home', tmp_path / 'home' / 'repos', tmp_path / 'home' / 'run'
    exe = str(tmp_path / 'bin' / EXE_NAME)
    monkeypatch.setattr(local, 'archeus_home', lambda: str(home))
    monkeypatch.setattr(local, 'repos_dir', lambda: str(repos))
    monkeypatch.setattr(local, 'run_dir', lambda: str(run))
    monkeypatch.setattr(local, '_git_exe', lambda: exe)
    pin = os.path.join(str(repos), '.pin')
    return SimpleNamespace(tmp=tmp_path, home=home, repos=repos, run=run, exe=exe, pin=pin,
                           empty=os.path.join(pin, 'empty'), cfg=os.path.join(pin, 'empty.cfg'))


def test_the_pinned_environment_keeps_only_the_platform_names_and_pins_git(layout, monkeypatch):
    monkeypatch.setenv('PATH', '/inherited/path')
    monkeypatch.setenv('HOME', '/inherited/home')
    monkeypatch.setenv('GIT_DIR', '/inherited/gitdir')
    monkeypatch.setenv('GIT_CONFIG_PARAMETERS', 'inherited')
    monkeypatch.setenv('ARCHEUS_PROBE_VAR', 'inherited')
    monkeypatch.setenv('TMP', 'the-tmp-kept')
    _argv, env, _cwd = local._store_pin('seed', None)
    assert 'ARCHEUS_PROBE_VAR' not in env
    assert 'GIT_DIR' not in env and env.get('GIT_CONFIG_PARAMETERS') is None
    assert env['PATH'] == os.path.dirname(layout.exe)
    assert env['HOME'] == layout.empty
    assert env['TMP'] == 'the-tmp-kept'
    assert env['GIT_ALLOW_PROTOCOL'] == 'file'
    assert env['GIT_TERMINAL_PROMPT'] == '0'


def test_without_a_git_dir_the_ceiling_is_repos_and_the_cwd_is_empty_only_for_version(layout):
    argv, env, cwd = local._store_pin('version', None)
    assert '--git-dir' not in argv
    assert env['GIT_CEILING_DIRECTORIES'] == str(layout.repos)
    assert cwd == layout.empty
    _argv, _env, cwd = local._store_pin('init', None)
    assert cwd == str(layout.repos)


def test_a_git_dir_adds_its_flags_and_the_trusted_and_seed_modes_add_theirs(layout):
    gd = str(layout.tmp / 'store.git')
    argv, _env, cwd = local._store_pin('read', gd)
    assert argv[1:4] == ['--git-dir', gd, '--no-replace-objects']
    assert cwd == gd
    assert '--attr-source' not in argv and 'core.logAllRefUpdates=false' not in argv
    argv, _env, _cwd = local._store_pin('trusted', gd)
    assert argv[argv.index('--attr-source') + 1] == local.EMPTY_TREE
    assert 'core.logAllRefUpdates=false' not in argv
    argv, _env, _cwd = local._store_pin('seed', gd)
    assert 'core.logAllRefUpdates=false' in argv
    assert '--attr-source' not in argv


@pytest.mark.parametrize('mode,gd', [('version', None), ('read', None), ('trusted', 'g'),
                                     ('seed', 'g')])
def test_the_six_hardening_settings_are_in_every_argv(layout, mode, gd):
    git_dir = os.path.join(str(layout.tmp), gd) if gd else None
    argv, _env, _cwd = local._store_pin(mode, git_dir)
    for setting in ('core.hooksPath=' + layout.empty, 'core.fsmonitor=false',
                    'core.attributesFile=' + layout.cfg, 'submodule.recurse=false',
                    'gc.auto=0', 'maintenance.auto=false'):
        assert setting in argv


def test_the_pin_area_is_repos_dot_pin_with_its_empty_directory_and_file(layout):
    assert local._pin_area() == (str(layout.repos), layout.pin, layout.empty, layout.cfg)


def test_a_pin_path_inside_a_recorded_workdir_is_refused_before_anything_is_made(layout):
    with pytest.raises(StoreError, match='a store call at or inside an execution area'):
        local._pin_files([str(layout.repos)])
    assert not layout.home.exists() and not layout.repos.exists()


def test_a_non_empty_empty_directory_or_a_cfg_with_bytes_is_refused(layout):
    local._pin_files([])
    open(os.path.join(layout.empty, 'stray'), 'wb').close()
    with pytest.raises(StoreError, match='a pin file is not empty'):
        local._pin_files([])
    os.remove(os.path.join(layout.empty, 'stray'))
    with open(layout.cfg, 'wb') as f:
        f.write(b'[core]\n')
    with pytest.raises(StoreError, match='a pin file is not empty'):
        local._pin_files([])


def test_an_absent_cfg_is_created_empty_and_a_present_one_is_left_alone(layout):
    assert local._pin_files([]) == layout.pin
    assert os.path.getsize(layout.cfg) == 0
    before = os.lstat(layout.cfg)
    assert local._pin_files([]) == layout.pin
    after = os.lstat(layout.cfg)
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


@pytest.mark.parametrize('workdirs', ['/some/path', b'/some/path', iter(['/a', '/b'])])
def test_a_bare_string_bytes_or_one_shot_iterator_of_workdirs_is_refused(layout, workdirs):
    with pytest.raises(StoreError, match='workdirs is a collection of paths'):
        local._outside_executions([str(layout.tmp / 'x')], workdirs)


def test_the_run_dir_and_the_worktrees_area_are_refused_and_none_or_blank_workdirs_are_ignored(
        layout):
    local._outside_executions([str(layout.tmp / 'elsewhere')], [])
    local._outside_executions([str(layout.tmp / 'elsewhere')], [None, ''])
    local._outside_executions([os.path.join(os.getcwd(), 'x')], [None, ''])
    with pytest.raises(StoreError, match='a store call at or inside an execution area'):
        local._outside_executions([str(layout.run)], [])
    with pytest.raises(StoreError, match='a store call at or inside an execution area'):
        local._outside_executions([str(layout.home / 'worktrees' / 't1')], [])
    with pytest.raises(StoreError, match='a store call at or inside an execution area'):
        local._outside_executions([os.path.join(os.getcwd(), 'x')], [os.getcwd()])
