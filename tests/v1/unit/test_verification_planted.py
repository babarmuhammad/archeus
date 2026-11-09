"""T-1064: a program planted in the workspace is never the one Core runs in place
of the intended binary (pv20-threat-model H5 for the unconfined verifier, H6 for
Core's own Git calls). A planted file is a marker-writing stub that is never
executed: the assertions read where `shutil.which` and the argv Core hands to the
spawner point, so no process starts.

The cases that depend on Windows searching the current directory first (Python
3.10 `which`, CreateProcess) run only there; the rest hold on every platform."""

import os
import subprocess
from types import SimpleNamespace

import pytest

from archeus.core.verification import evidence
from archeus.node import local
from archeus.node.local import LocalNode, StoreError

WIN = os.name == 'nt'
windows_only = pytest.mark.skipif(not WIN, reason='the current directory is searched first only on Windows')
NAMES = ('npm', 'git', 'where', 'python')
STUB = '@echo planted> "%~dp0PLANTED.marker"\r\n'


def _file(name):
    return name + ('.cmd' if WIN and name == 'npm' else '.exe' if WIN else '')


def _plant(directory, names=NAMES):
    os.makedirs(directory, exist_ok=True)
    for n in names:
        p = os.path.join(str(directory), _file(n))
        with open(p, 'w') as f:
            f.write(STUB)
        os.chmod(p, 0o755)


def _inside(path, directory):
    d = os.path.normcase(os.path.abspath(str(directory)))
    p = os.path.normcase(os.path.abspath(path))
    return p == d or p.startswith(d + os.sep)


@pytest.fixture
def world(tmp_path, monkeypatch):
    ws, tools, core = tmp_path / 'ws', tmp_path / 'tools', tmp_path / 'core'
    _plant(ws)
    _plant(tools)
    core.mkdir()
    monkeypatch.setenv('PATH', str(tools))
    monkeypatch.setenv('PATHEXT', '.COM;.EXE;.BAT;.CMD')
    local._git_exe.cache_clear()
    yield SimpleNamespace(ws=ws, tools=tools, core=core)
    local._git_exe.cache_clear()


# ── the unconfined verifier: `argv_of` (H5) ─────────────────────────────────

@pytest.mark.parametrize('name', NAMES)
def test_argv_of_finds_a_program_on_path_not_in_the_workspace(world, monkeypatch, name):
    monkeypatch.chdir(world.core)
    found = evidence.argv_of('%s --version' % name)
    assert found[1:] == ['--version']
    assert _inside(found[0], world.tools) and not _inside(found[0], world.ws)


@windows_only
@pytest.mark.parametrize('name', NAMES)
def test_argv_of_ignores_a_planted_program_when_core_runs_in_the_workspace(world, monkeypatch, name):
    monkeypatch.chdir(world.ws)
    found = evidence.argv_of('%s --version' % name)
    assert found is None or (os.path.isabs(found[0]) and not _inside(found[0], world.ws))
    assert found is not None and _inside(found[0], world.tools)


@windows_only
def test_argv_of_does_not_take_a_planted_program_PATH_lacks(world, monkeypatch):
    monkeypatch.setenv('PATH', str(world.core))
    monkeypatch.chdir(world.ws)
    found = evidence.argv_of('git status')
    assert found is None or (os.path.isabs(found[0]) and not _inside(found[0], world.ws))
    assert found is None


def test_argv_of_skips_a_workspace_directory_on_path_and_fails_closed(world, monkeypatch):
    monkeypatch.chdir(world.core)
    monkeypatch.setenv('PATH', os.pathsep.join([str(world.ws), str(world.tools)]))
    found = evidence.argv_of('git status', str(world.ws))
    assert os.path.isabs(found[0]) and _inside(found[0], world.tools)
    monkeypatch.setenv('PATH', str(world.ws))
    assert evidence.argv_of('git status', str(world.ws)) is None


@pytest.mark.parametrize('entry', ['.', 'sub', 'workspace'])
def test_which_never_searches_the_current_directory_or_a_relative_entry(world, monkeypatch, entry):
    _plant(world.ws / 'sub')
    monkeypatch.chdir(world.ws)
    monkeypatch.setenv('PATH', str(world.ws) if entry == 'workspace' else entry)
    assert evidence.argv_of('git status') is None


@pytest.mark.parametrize('toolchain', ['absent', 'present'])
def test_confined_argv_never_returns_a_workspace_program(world, monkeypatch, toolchain):
    # a planted program in the current directory never shadows the staged one
    monkeypatch.chdir(world.ws)
    tc = [str(world.tools if toolchain == 'present' else world.core)]
    found = evidence.confined_argv('git status', tc)
    assert found is None or (found[1:] == ['status'] and _inside(found[0], world.tools))
    assert (found is None) == (toolchain == 'absent')


def test_run_check_hands_the_program_and_path_on_unchanged(world, monkeypatch):
    seen = {}

    class Child:
        returncode = 0

        def wait(self, timeout=None):
            return 0

    def popen(argv, **kw):
        seen.update(argv=argv, **kw)
        return Child()
    monkeypatch.setattr(subprocess, 'Popen', popen)
    argv = evidence.argv_of('git status')
    LocalNode.run_check(str(world.ws), argv, timeout=5, out_path=str(world.core / 'o' / 'out'))
    assert seen['argv'] == argv and seen['cwd'] == str(world.ws)
    entries = seen['env']['PATH'].split(os.pathsep)
    assert entries == [str(world.tools)]
    assert not any(_inside(e, world.ws) for e in entries) and '' not in entries and '.' not in entries


# ── Core's own Git: the pinned store call and the bare-`git` helpers (H6) ───

@pytest.mark.parametrize('found', ['git.exe', r'.\git.exe', './git', None, ''])
def test_git_exe_refuses_what_which_gives_that_is_not_absolute(monkeypatch, found):
    monkeypatch.setattr(local.shutil, 'which', lambda name: found)
    local._git_exe.cache_clear()
    with pytest.raises(StoreError, match='no absolute git'):
        local._git_exe()


@windows_only
def test_git_exe_never_runs_a_git_planted_in_the_current_directory(world, monkeypatch):
    monkeypatch.chdir(world.ws)
    with pytest.raises(StoreError, match='no absolute git'):
        local._git_exe()


def test_git_exe_takes_the_git_on_path_when_core_is_elsewhere(world, monkeypatch):
    monkeypatch.chdir(world.core)
    exe = local._git_exe()
    assert os.path.isabs(exe) and _inside(exe, world.tools) and not _inside(exe, world.ws)


def test_the_store_pin_keeps_path_to_gits_own_directory_whatever_core_inherited(world, monkeypatch):
    monkeypatch.chdir(world.core)
    exe = local._git_exe()
    monkeypatch.setenv('PATH', os.pathsep.join([str(world.ws), os.curdir, '', str(world.tools)]))
    for mode, git_dir in (('version', None), ('init', None),
                          ('trusted', str(world.core / 'store')), ('base', str(world.core / 'store'))):
        argv, env, cwd = local._store_pin(mode, git_dir)
        assert argv[0] == exe and os.path.isabs(argv[0])
        assert env['PATH'] == os.path.dirname(exe)
        assert not _inside(cwd, world.ws)
        assert all(str(world.ws) not in v for v in env.values())


def _bare_git_calls(monkeypatch, ws):
    """Every program the Git helpers hand the spawner against *ws*, recorded and never started."""
    calls = []

    def run(argv, *, cwd=None, **kw):
        calls.append(SimpleNamespace(argv=list(argv), cwd=cwd))
        return SimpleNamespace(returncode=0, stdout='a' * 40 + '\n', stderr='')
    monkeypatch.setattr(local.proc.subprocess, 'run', run)
    w = str(ws)
    LocalNode.git_head(w)
    LocalNode.git_dirty(w)
    LocalNode.git_branch(w)
    LocalNode.git_merge_base(w, 'a', 'b')
    LocalNode.git_is_ancestor(w, 'a', 'b')
    LocalNode.git_numstat(w, 'a', 'b')
    LocalNode.git_snapshot(w, 'm')
    LocalNode.end_state(w)
    assert calls and all(c.cwd == w for c in calls)
    return calls


def test_a_bare_git_call_of_core_resolves_to_path_when_core_is_elsewhere(world, monkeypatch):
    monkeypatch.chdir(world.core)
    for c in _bare_git_calls(monkeypatch, world.ws):
        assert os.path.isabs(c.argv[0]) and not _inside(c.argv[0], world.ws), c.argv


@windows_only
def test_a_bare_git_call_of_core_ignores_a_planted_git_when_core_runs_in_the_workspace(world, monkeypatch):
    monkeypatch.chdir(world.ws)
    for c in _bare_git_calls(monkeypatch, world.ws):
        assert os.path.isabs(c.argv[0]) and not _inside(c.argv[0], world.ws), c.argv


def test_a_bare_git_call_fails_closed_when_only_the_workspace_holds_git(world, monkeypatch):
    monkeypatch.chdir(world.core)
    monkeypatch.setenv('PATH', str(world.ws))
    started = []
    monkeypatch.setattr(local.proc.subprocess, 'run', lambda *a, **k: started.append(a))
    assert LocalNode.git_head(str(world.ws)) is None and not started
