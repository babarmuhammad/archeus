"""T-1290: claude_sessions/worktrees.py:329-368 at 6bbd3b44; same current slice.

Selected probes, not measured coverage; closest test_plugins_worktrees.py:
348 invalid branch no Git; :214 tests a valid slash branch with real Git.
350 metacharacters exact argv; :214 does not inspect argv or timeout.
352 None/empty/bounded merge result; :214 exercises successful merge only.
360 dirty refusal composition; :364 does not assert Git absence or force retry.
359 unknown dirty refusal; :529 reports unknown board state, not removal.
365 dash path option safety; :364 tests dirty guard only.
364 force argv parity; :364 never forces a clean/dirty removal.
366 removal failure vs empty success; :364 never calls remove Git seam.
333 staged/nonstaged diff; :214 does not inspect diff argv/None fallback.
365 parent cwd/relative refusal; :364 never asserts containment or timeout.
"""

import os

import pytest

from claude_sessions import worktrees as w


@pytest.fixture
def git(monkeypatch):
    calls = []
    result = {'out': ''}

    def run(args, cwd, **kwargs):
        calls.append((args, cwd, kwargs))
        return result['out']

    monkeypatch.setattr(w, '_git', run)
    return calls, result


@pytest.mark.parametrize('branch', ['', '-branch', '--help'])
def test_invalid_branch_refuses_before_git(git, tmp_path, branch):
    calls, _ = git
    assert w.merge_into_main(str(tmp_path), branch) == (False, 'not a branch name')
    assert calls == []


def test_merge_metacharacters_stay_single_delimited_argument(git, tmp_path):
    calls, result = git
    result['out'] = ' merged '
    branch = 'feature/x;echo $(ignored) & next'
    assert w.merge_into_main(str(tmp_path), branch) == (True, 'merged')
    assert calls == [(['merge', '--no-ff', '--no-edit', '--', branch],
                      str(tmp_path), {'timeout': 60})]


def test_merge_none_empty_and_long_stdout(git, tmp_path):
    calls, result = git
    result['out'] = None
    ok, message = w.merge_into_main(str(tmp_path), 'branch')
    assert ok is False and 'failed' in message
    result['out'] = ' \n'
    assert w.merge_into_main(str(tmp_path), 'branch') == (True, 'Merged branch')
    result['out'] = ' ' + 'x' * 500 + ' '
    assert w.merge_into_main(str(tmp_path), 'branch') == (True, 'x' * 400)
    assert len(calls) == 3


def test_dirty_refusal_has_no_removal_side_effect(git, monkeypatch, tmp_path):
    calls, _ = git
    monkeypatch.setattr(w, 'dirty', lambda p: (2, 9))
    ok, message = w.remove(str(tmp_path / 'tree'))
    assert ok is False and '2 uncommitted' in message
    assert calls == []
    assert w.remove(str(tmp_path / 'tree'), force=True)[0] is True
    assert len(calls) == 1 and calls[0][0].count('--force') == 1


def test_unknown_dirty_observation_refuses_remove(monkeypatch, tmp_path):
    calls = []

    def git(args, cwd, **kw):
        calls.append(args)
        return None if 'status' in args else ''

    monkeypatch.setattr(w, '_git', git)
    assert w.remove(str(tmp_path / 'tree'))[0] is False
    assert len(calls) == 1 and 'status' in calls[0]


def test_dash_path_is_refused_or_delimited(git, monkeypatch):
    calls, _ = git
    monkeypatch.setattr(w, 'dirty', lambda p: (0, 0))
    ok, _ = w.remove('--force')
    assert not ok or (len(calls) == 1 and calls[0][0][-2:] == ['--', '--force'])


@pytest.mark.parametrize('force', [False, True])
def test_remove_force_flag_exactly_matches_explicit_choice(git, monkeypatch, tmp_path, force):
    calls, _ = git
    path = str(tmp_path / 'tree')
    monkeypatch.setattr(w, 'dirty', lambda p: (0, 0))
    assert w.remove(path, force=force)[0] is True
    expected = ['worktree', 'remove'] + (['--force'] if force else []) + [path]
    assert calls == [(expected, str(tmp_path), {'timeout': 30})]


def test_remove_none_reports_failure_empty_stdout_success(git, monkeypatch, tmp_path):
    calls, result = git
    monkeypatch.setattr(w, 'dirty', lambda p: (0, 0))
    path = str(tmp_path / 'tree')
    result['out'] = None
    assert w.remove(path) == (False, 'git refused to remove that worktree')
    result['out'] = ''
    assert w.remove(path) == (True, 'Removed tree')
    assert len(calls) == 2


def test_diff_staged_flag_and_none_have_no_fallback(git, tmp_path):
    calls, result = git
    result['out'] = None
    assert w.diff(str(tmp_path), staged=False) == ''
    result['out'] = 'patch\n'
    assert w.diff(str(tmp_path), staged=True) == 'patch\n'
    assert calls == [(['diff', '--stat=200', '--patch'], str(tmp_path), {}),
                      (['diff', '--cached', '--stat=200', '--patch'], str(tmp_path), {})]


def test_relative_sibling_path_cannot_remove_other_tree(git, monkeypatch):
    calls, _ = git
    monkeypatch.setattr(w, 'dirty', lambda p: (0, 0))
    assert w.remove(os.path.join('..', 'sibling'))[0] is False
    assert calls == []
