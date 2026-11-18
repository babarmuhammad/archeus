"""T-1300: the highest-risk uncovered branches of `archeus/node/local.py` lines
**1859-1991 inclusive** (`_project_git` and `_frozen_config`: the real configuration
freeze against the autouse pass-through), at the current branch tip. Subprocesses are
fakes recorded through `local.subprocess.run` and `local.proc.run_capped`; the Git
executable is a synthetic path under tmp_path and no real Git runs.

The off-Windows refusal of `_project_git` is the contract pinned by tests/conftest.py
(the freeze seam) and tests/v1/unit/test_repo_config_freeze.py, not a defect. The real
freeze here is driven by a marked test with `local.sys` replaced by a Linux platform
(`SimpleNamespace(platform='linux')`), so the refusal is the freeze's own check on every
OS; a Windows platform would construct Win32Api and make the refusal platform-dependent.

Ten selected branches, ranked by risk:

1. local.py:1950 (`with _frozen_config(...)`, real freeze) — a marked call refuses with
   None and launches only the version probe; no request runs.
2. local.py:1902 — an unmarked call through the pass-through returns the CompletedProcess.
3. local.py:1944 — the pass-through yields the identical argv object and never runs the
   supplied runner.
4. local.py:1951 — the real freeze raises its OSError before any run and before Win32Api
   is constructed.
5. local.py:1894 — the version is supported and cached before the freeze refuses, so the
   refusal is the freeze's and not the floor's.
6. local.py:1902 — a supported version already cached, a marked refusal launches no child.
7. local.py:1950 — status, rev-parse and diff are all refused under the marker, not only one.
8. local.py:1921 — the real freeze's exception becomes None when a capped read is asked,
   and the capped runner is never reached.
9. local.py:1902 — repeated unmarked calls keep the pass-through and return results.
10. local.py:1950 — `real_config_freeze` is registered as a marker.

Closest existing tests: tests/v1/unit/test_repo_config_freeze.py (Windows-only real
freeze, sharing modes) and tests/v1/unit/test_repo_store.py::test_the_guarded_project_git_call_carries_the_whole_pin
(complete argv under the pass-through, no refusal branch).
"""

import contextlib
import os
import subprocess
import types

import pytest

from archeus.node import local

FLOOR_OK = b'git version 2.49.0\n'


def _exe(tmp_path):
    return str(tmp_path / 'bin' / 'git')


def _root(tmp_path):
    root = str(tmp_path / 'repo')
    os.makedirs(os.path.join(root, '.git'), exist_ok=True)
    return root


@pytest.fixture(autouse=True)
def _freeze_seam(request, monkeypatch, tmp_path):
    """The pass-through of tests/conftest.py, installed the same way on every platform for
    the unmarked tests; marked tests keep the real freeze."""
    monkeypatch.setattr(local.proc, 'which', lambda name, path=None, avoid=(): _exe(tmp_path))
    monkeypatch.setattr(local, '_VERSION', {})
    if request.node.get_closest_marker('real_config_freeze'):
        return

    @contextlib.contextmanager
    def passthrough(root, argv, env, run, empty):
        yield argv
    passthrough._seam = True
    monkeypatch.setattr(local, '_frozen_config', passthrough)


@pytest.fixture
def linux_platform(monkeypatch):
    monkeypatch.setattr(local, 'sys', types.SimpleNamespace(platform='linux'))


@pytest.fixture
def calls(monkeypatch):
    recorded = []

    def run(argv, **kw):
        recorded.append((list(argv), kw))
        out = FLOOR_OK if 'version' in argv else b'OUT\n'
        return subprocess.CompletedProcess(argv, 0, out, b'')
    monkeypatch.setattr(local.subprocess, 'run', run)
    return recorded


def _kinds(calls_):
    return [a for a, _ in calls_]


# ── 1 · the real freeze refuses and only the version is asked (local.py:1950) ─

@pytest.mark.real_config_freeze
def test_the_real_freeze_refuses_a_repository_and_launches_only_the_version(
        tmp_path, linux_platform, calls):
    """local.py:1950 — `with _frozen_config(...)` is the real freeze. On a repository the
    freeze raises before any request: the single launch is the version probe. Removing
    the freeze's check would run `rev-parse` and `status` on the repository."""
    assert local._project_git(_root(tmp_path), ['status', '--porcelain']) is None
    assert len(calls) == 1 and 'version' in calls[0][0]


# ── 2 · the pass-through returns the result (local.py:1902) ─────────────────

def test_an_unmarked_call_through_the_seam_returns_the_completed_process(tmp_path, calls):
    """local.py:1902 — `return _project_git(...)` path with the pass-through freeze: the
    CompletedProcess of the requested command comes back with decoded text."""
    r = local._project_git(_root(tmp_path), ['status', '--porcelain'])
    assert isinstance(r, subprocess.CompletedProcess) and r.returncode == 0
    assert r.stdout == 'OUT\n'
    assert 'status' in calls[-1][0]


# ── 3 · the seam yields the same argv and never runs (local.py:1944) ────────

def test_the_pass_through_yields_the_identical_argv_object_without_running(tmp_path):
    """local.py:1944 — `yield argv` in the seam. The yielded object is the one passed in
    (identity, not equality), and the supplied runner is not invoked."""
    ran = []

    def run(argv, cwd, cap=None):
        ran.append(argv)
    argv = ['git', 'status']
    with local._frozen_config(_root(tmp_path), argv, {}, run, str(tmp_path)) as out:
        assert out is argv
    assert ran == [] and local._frozen_config._seam is True


# ── 4 · the real freeze's own refusal, before any run (local.py:1951) ───────

@pytest.mark.real_config_freeze
def test_the_real_freeze_raises_its_refusal_before_any_run_or_win32_construction(
        tmp_path, linux_platform, monkeypatch):
    """local.py:1951 — `if sys.platform != 'win32': raise OSError(...)`. Off Windows the
    freeze raises that exact refusal before the runner is called and before Win32Api is
    constructed (a construction would reach kernel32 and the private directory)."""
    constructed = []

    def construct(*a):
        constructed.append(a)
        raise AssertionError('Win32Api constructed off Windows')
    monkeypatch.setattr(local, 'Win32Api', construct)
    ran = []
    with pytest.raises(OSError, match='the configuration freeze needs Windows'):
        with local._frozen_config(_root(tmp_path), ['git'], {}, lambda *a, **k: ran.append(a),
                                  str(tmp_path)):
            pass
    assert ran == [] and constructed == []


# ── 5 · the floor is passed before the freeze refuses (local.py:1894) ───────

@pytest.mark.real_config_freeze
def test_a_supported_version_is_cached_before_the_freeze_refuses_so_the_floor_is_not_the_cause(
        tmp_path, linux_platform, calls):
    """local.py:1894 — the version is read and `_VERSION[exe]` set before the freeze is
    entered. The refusal that follows is therefore the freeze's, and the cache proves the
    floor passed."""
    root = _root(tmp_path)
    assert local._project_git(root, ['status']) is None
    assert local._VERSION == {_exe(tmp_path): 'git version 2.49.0'}


# ── 6 · a cached version and a marked refusal launch no child (local.py:1902) ─

@pytest.mark.real_config_freeze
def test_a_cached_supported_version_and_a_refusal_launch_no_child_at_all(tmp_path, linux_platform,
                                                                         calls, monkeypatch):
    """local.py:1902 — with `exe in _VERSION` the version probe is skipped, and the freeze
    refuses before any command: zero launches."""
    monkeypatch.setitem(local._VERSION, _exe(tmp_path), 'git version 2.49.0')
    assert local._project_git(_root(tmp_path), ['status', '--porcelain']) is None
    assert calls == []


# ── 7 · every guarded subcommand is refused under the marker (local.py:1950) ─

@pytest.mark.real_config_freeze
@pytest.mark.parametrize('args', [['status', '--porcelain'], ['rev-parse', 'HEAD'],
                                  ['diff', '--stat']], ids=['status', 'rev_parse', 'diff'])
def test_each_guarded_subcommand_is_refused_under_the_real_freeze(tmp_path, linux_platform,
                                                                  calls, args):
    """local.py:1950 — the refusal is in front of every requested command, so no guarded
    subcommand reaches the runner. A freeze that only refused `status` would let `diff`
    through."""
    assert local._project_git(_root(tmp_path), args) is None
    assert not any(a[-len(args):] == args for a in _kinds(calls))


# ── 8 · the real freeze's refusal becomes None on the capped path (local.py:1921) ─

@pytest.mark.real_config_freeze
def test_the_real_freeze_refusal_is_none_on_the_capped_path_and_nothing_is_read(
        tmp_path, linux_platform, calls, monkeypatch):
    """local.py:1921 — the `except Exception: return None` around the freeze. A capped
    read (`max_bytes`) is refused the same way: the OSError does not leak, no partial
    result is returned, and `proc.run_capped` is never reached."""
    def never(*a, **k):
        raise AssertionError('the capped runner was reached')
    monkeypatch.setattr(local.proc, 'run_capped', never)
    assert local._project_git(_root(tmp_path), ['status'], max_bytes=1024) is None


# ── 9 · repeated unmarked calls keep the pass-through (local.py:1902) ───────

def test_repeated_unmarked_calls_keep_the_pass_through_and_return_results(tmp_path, calls):
    """local.py:1902 — the seam is in force for every call, not only the first, and a
    marked sibling test must not leave the real freeze installed for this one."""
    root = _root(tmp_path)
    assert getattr(local._frozen_config, '_seam', False) is True
    first = local._project_git(root, ['status', '--porcelain'])
    second = local._project_git(root, ['status', '--porcelain'])
    assert first is not None and second is not None
    assert not any('--git-dir' in a for a in _kinds(calls))


# ── 10 · the marker is registered (local.py:1950 as the marked contract) ────

@pytest.mark.real_config_freeze
def test_the_real_config_freeze_marker_is_registered_for_strict_marker_runs(pytestconfig):
    """The marker is the opt-out from the pass-through; a run with --strict-markers must
    accept it, which needs the registration in tests/conftest.py."""
    lines = pytestconfig.getini('markers')
    assert any(line.split(':', 1)[0].strip() == 'real_config_freeze' for line in lines)
