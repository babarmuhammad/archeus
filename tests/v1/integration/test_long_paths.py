"""T-078 (B): every worktree Core makes or removes checks out a tracked file
whose path passes 260 characters, without writing the user's git config.

On Windows Git stops at MAX_PATH unless `core.longpaths` is set, and with the
default ARCHEUS_HOME a task worktree's root is about 109 characters long, so a
repository path past about 149 characters failed every execution (T-077 §3).

T-078 (A): a worktree whose `.git` path Git for Windows would refuse ("'$GIT_DIR'
too big", past 220 characters) is refused by Core first, before anything is
made, with the path, its length, the limit and what to change. The check runs
on the path itself, so the mission worktree (home + 51) hits it before a task's
(home + 45) does (T-079 section 2, the layout T-080 made)."""
import os
import subprocess

import pytest

from v1.integration.test_verification import FIX, _mission, _t, _task, _write, pump
from v1.judge import support
from v1.judge.client import InProcessClient
from v1.judge.conftest import recorded_brain
from v1.judge.support import Rig

from archeus.core.domain import entities
from archeus.infra import paths
from archeus.infra.db import rows
from archeus.node import local
from archeus.node.local import LocalNode

ROOT_LEN = 109      # a worktree root under the default %LOCALAPPDATA%\Archeus (T-077 §5)
FILE_LEN = 270      # past MAX_PATH, the length T-077 measured failing


@pytest.fixture
def git_env(monkeypatch, tmp_path):
    """No global or system config: `core.longpaths` comes from Core's own `-c`
    or nowhere, so a passing test cannot be the machine's config passing it."""
    empty = tmp_path / 'empty.gitconfig'
    empty.write_text('')
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(empty))
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    monkeypatch.delenv('GIT_CONFIG_COUNT', raising=False)


def _git(cwd, *args, stdin=None):
    return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *args], cwd=cwd,
                          input=stdin, capture_output=True, text=True, check=True).stdout.strip()


def _worktree_path(tmp_path, name):
    stem = os.path.join(str(tmp_path), name)
    if len(stem) + 2 > ROOT_LEN:
        pytest.skip('pytest basetemp too long for a %d-character worktree root' % ROOT_LEN)
    return stem + '_' + 'w' * (ROOT_LEN - len(stem) - 1)


def _repo_with_deep_file(tmp_path, root_len):
    repo = str(tmp_path / 'repo')
    os.makedirs(repo)
    _git(repo, 'init', '-q', '-b', 'main')
    rel_len = FILE_LEN - root_len - 1
    rel = 'a/' * 20 + 'f' * (rel_len - 40)
    blob = _git(repo, 'hash-object', '-w', '--stdin', stdin='deep\n')
    _git(repo, 'update-index', '--add', '--cacheinfo', '100644,%s,%s' % (blob, rel))
    _git(repo, 'commit', '-q', '-m', 'a file past MAX_PATH')
    return repo, rel


def test_a_task_worktree_checks_out_a_file_past_max_path(git_env, tmp_path):
    path = _worktree_path(tmp_path, 'task')
    repo, rel = _repo_with_deep_file(tmp_path, len(path))
    assert len(os.path.join(path, rel)) == FILE_LEN
    assert LocalNode.add_worktree(repo, path, 'archeus/m.t1', base='main') == path
    assert _git(path, '-c', 'core.longpaths=true', 'ls-files') == rel
    assert _git(path, '-c', 'core.longpaths=true', 'status', '--porcelain') == ''
    assert _local_longpaths(repo) == ''


def test_the_mission_worktree_checks_out_a_file_past_max_path(git_env, tmp_path):
    path = _worktree_path(tmp_path, 'mission')
    repo, rel = _repo_with_deep_file(tmp_path, len(path))
    _git(repo, 'branch', 'archeus/m')
    assert LocalNode.mission_worktree(repo, path, 'archeus/m', 'main') == path
    assert _git(path, '-c', 'core.longpaths=true', 'ls-files') == rel
    assert _git(path, '-c', 'core.longpaths=true', 'status', '--porcelain') == ''


def test_a_worktree_holding_a_file_past_max_path_is_removed(git_env, tmp_path):
    path = _worktree_path(tmp_path, 'gone')
    repo, _rel = _repo_with_deep_file(tmp_path, len(path))
    LocalNode.add_worktree(repo, path, 'archeus/m.t1', base='main')
    assert LocalNode.remove_worktree(repo, path) is True
    assert not os.path.exists(path)
    assert path not in _git(repo, 'worktree', 'list', '--porcelain')


def test_the_users_git_config_is_never_written(git_env, tmp_path):
    path = _worktree_path(tmp_path, 'cfg')
    repo, _rel = _repo_with_deep_file(tmp_path, len(path))
    before = open(os.path.join(repo, '.git', 'config'), 'rb').read()
    LocalNode.add_worktree(repo, path, 'archeus/m.t1', base='main')
    LocalNode.remove_worktree(repo, path)
    assert open(os.path.join(repo, '.git', 'config'), 'rb').read() == before
    assert _local_longpaths(repo) == ''
    assert (tmp_path / 'empty.gitconfig').read_text() == ''


def _local_longpaths(repo):
    r = subprocess.run(['git', 'config', '--get-all', 'core.longpaths'], cwd=repo,
                       capture_output=True, text=True)
    return r.stdout.strip()



# ── T-078 (A): the length check, on the paths Core actually builds ──────────

PRJ, MSN = 'prj_' + '0' * 26, 'msn_' + '0' * 26


def _home(tmp_path, n):
    stem = os.path.join(str(tmp_path), 'h')
    if len(stem) + 1 > n:
        pytest.skip('pytest basetemp too long for a %d-character ARCHEUS_HOME' % n)
    return stem + 'x' * (n - len(stem))


def _task_wt(home):        # manager.py _workspace: worktrees/<mission ULID>/<task key>
    return os.path.join(home, 'worktrees', MSN[len('msn_'):], 't1')


def _plain_repo(tmp_path):
    repo = str(tmp_path / 'repo')
    os.makedirs(repo)
    _git(repo, 'init', '-q', '-b', 'main')
    _git(repo, 'commit', '-q', '--allow-empty', '-m', 'base')
    return repo


def _branches(repo):
    return _git(repo, 'branch', '--format=%(refname:short)').split()


@pytest.fixture
def capped(monkeypatch):
    """The Windows cap, on every platform: the check is Core's, not Git's."""
    monkeypatch.setattr(local, 'GIT_DIR_MAX', 220)


@pytest.mark.parametrize('n, made', [(175, True), (176, False)])
def test_a_task_worktree_is_made_up_to_home_175_and_refused_first_past_it(
        git_env, capped, tmp_path, n, made):
    home = _home(tmp_path, n)
    repo = _plain_repo(tmp_path)
    path = _task_wt(home)
    assert len(os.path.join(path, '.git')) == n + 45
    if made:
        assert LocalNode.add_worktree(repo, path, 'archeus/m.t1', base='main') == path
        assert os.path.isdir(path)
        return
    with pytest.raises(local.PathTooLong) as err:
        LocalNode.add_worktree(repo, path, 'archeus/m.t1', base='main')
    assert path in str(err.value) and '221 characters' in str(err.value)
    assert not os.path.exists(os.path.dirname(path))       # nothing made before the refusal
    assert 'archeus/m.t1' not in _branches(repo)          # and Git never ran


def test_the_mission_worktree_is_refused_where_the_task_worktree_still_fits(
        git_env, capped, monkeypatch, tmp_path):
    home = _home(tmp_path, 170)         # task .git 215 fits; mission .git 221 does not
    monkeypatch.setenv('ARCHEUS_HOME', home)
    repo = _plain_repo(tmp_path)
    task, mission = _task_wt(home), paths.mission_worktree_path(PRJ, MSN)
    assert (len(os.path.join(task, '.git')), len(os.path.join(mission, '.git'))) == (215, 221)
    assert LocalNode.add_worktree(repo, task, 'archeus/m.t1', base='main') == task
    for branch_first in (False, True):          # both of mission_worktree's paths
        if branch_first:
            _git(repo, 'branch', 'archeus/m', 'main')
        with pytest.raises(local.PathTooLong) as err:
            LocalNode.mission_worktree(repo, mission, 'archeus/m', 'main')
        assert mission in str(err.value) and '221 characters' in str(err.value)
        assert not os.path.exists(mission)
    assert _git(repo, 'worktree', 'list', '--porcelain').count('worktree ') == 2   # main + task


# ── T-078 (A): the refusal is uncharged and the mission waits, once ─────────

STEPS = [_write(FIX), {'emit': {'type': 'result', 'summary': 'done'}}]


@pytest.fixture
def long_core(request, tmp_path, monkeypatch, capped):
    """An in-process Core (test_verification's rig) whose ARCHEUS_HOME is exactly
    `request.param` characters long."""
    home = _home(tmp_path, request.param)
    monkeypatch.setenv('ARCHEUS_HOME', home)
    c = InProcessClient(home, callers=[recorded_brain()], real_verification=True)
    monkeypatch.setattr(support, 'idle', c._idle)
    yield c
    c.close()


def _of(c, cls, **eq):
    with c._core().read() as conn:
        return [r.entity for r in rows.where(conn, cls, **eq)]


def _events(c, kind):
    import json
    with c._core().read() as conn:
        return [json.loads(p) for (p,) in conn.execute(
            'select payload from events where type = ? order by seq', (kind,))]


def _planner_calls(c):
    return sum(1 for p in _events(c, 'archeus_call.ended') if p.get('purpose') == 'planner')


def _blocks(c, mid):
    return [p for p in _events(c, 'mission.state_changed') if p.get('to') == 'BLOCKED']


@pytest.mark.parametrize('long_core', [176], indirect=True)
def test_past_home_175_a_task_is_refused_once_uncharged_and_its_mission_waits(long_core):
    c = long_core
    _repo, mid = _mission(c, Rig(c), steps=STEPS)
    pump(c, lambda: c.get_mission(mid)['state'] == 'BLOCKED')
    pump(c)                                     # and then nothing moves: no retry, no loop
    (e,) = _of(c, entities.Execution)
    assert (e.state, e.stop_reason, e.charged) == ('ABANDONED', 'path_too_long', False)
    assert _t(c, mid) == 'READY'                # not failed: no attempt spent, no replan
    assert _planner_calls(c) == 1               # the first plan's, and no other
    assert not [p for p in _events(c, 'mission.state_changed') if p.get('to') == 'REPLANNING']
    (block,) = _blocks(c, mid)
    why = block['reason']
    assert e.workdir is None and os.path.join('worktrees', '') in why
    assert '221 characters' in why and 'at most 220' in why and 'ARCHEUS_HOME' in why


@pytest.mark.parametrize('long_core', [175], indirect=True)
def test_at_home_175_the_task_runs_as_before(long_core):
    c = long_core
    _repo, mid = _mission(c, Rig(c), steps=STEPS)
    pump(c, lambda: _t(c, mid) == 'VERIFYING')
    assert [e.stop_reason for e in _of(c, entities.Execution)] == [None]
    assert not _blocks(c, mid)


@pytest.mark.parametrize('long_core', [170], indirect=True)
def test_a_mission_worktree_git_refuses_blocks_the_mission_once_at_merge_time(long_core):
    c = long_core                   # task .git 215 fits; the mission's 221 does not
    _repo, mid = _mission(c, Rig(c), steps=STEPS)
    pump(c, lambda: c.get_mission(mid)['state'] == 'BLOCKED')
    t = _task(c, mid)
    assert (t.state, t.integration_state) == ('SUCCEEDED', 'MERGING')
    pump(c)                         # the merge is not tried again while it waits
    (block,) = _blocks(c, mid)
    assert block['reason'].startswith('no mission worktree: the worktree ')
    assert '_mission' in block['reason'] and '221 characters' in block['reason']
    with c._core().read() as conn:
        assert not [d for d in c._verify.plan(conn) if d[0] == 'merge']
    assert [e.stop_reason for e in _of(c, entities.Execution)] == [None]   # nothing charged
