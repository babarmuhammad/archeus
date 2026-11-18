"""Workspace reads and the after-the-fact workspace verdict of verification worker.

Every external call goes through the node fake, so no real git, command, process, network or
sleep is involved on any platform. All writes stay under tmp_path.
"""

import os

import pytest

from archeus.core.execution.manager import mission_branch
from claude_sessions import proc

from . import test_gaps_core_verification_worker as W
from .test_gaps_core_verification_worker import BASE, REV, REV2, _result, _script

rig = W.rig

SNAP = 'e' * 40


@pytest.fixture(autouse=True)
def _tool_found_on_path(tmp_path, monkeypatch):
    real = proc.which
    found = os.path.join(str(tmp_path / 'bin'), 'tool.exe' if os.name == 'nt' else 'tool')

    def which(name, path=None, avoid=()):
        return found if name == 'tool' else real(name, path=path, avoid=avoid)
    monkeypatch.setattr(proc, 'which', which)


class _Node:
    def __init__(self, **fake):
        self.fake, self.calls = fake, []

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append((name, a, k))
            if name not in self.fake:
                raise AssertionError('the worker called node.%s%r' % (name, a))
            return self.fake[name](*a, **k)
        return call


def _names(node):
    return [n for n, _a, _k in node.calls]


def _calls(node, name):
    return [(a, k) for n, a, k in node.calls if n == name]


def _workspace(v):
    got = [c for c in v.checks if c['name'] == 'workspace']
    assert len(got) == 1, 'workspace checks: %r' % ([c['name'] for c in v.checks],)
    return got[0]


def test_an_unknown_dirty_status_escapes_the_pass_and_leaves_the_task_waiting(rig):
    node = _Node(git_head=_script(REV), git_dirty=_script(None),
                 branch_exists=_script(False), git_merge_base=_script(BASE),
                 git_snapshot=lambda *_a: pytest.fail('snapshotted an unknown status'),
                 run_check=lambda *_a, **_k: pytest.fail('a command ran after an unknown'))
    r = rig(workdir='ws', branch='task', node=node)
    seen = r.spy()
    with pytest.raises(OSError, match='git status could not read the task workspace'):
        r.worker.pass_once()
    assert seen == []
    assert r.rows() == []
    assert r.task().state == 'VERIFYING'
    assert r.missions.fired == []
    assert r.plan() == [('verify_task', r.tid, r.eid)]
    assert 'git_snapshot' not in _names(node) and 'run_check' not in _names(node)


def test_an_unreadable_head_short_circuits_the_read_and_becomes_a_persons(rig):
    node = _Node(git_head=_script(None),
                 git_dirty=lambda *a, **k: pytest.fail('dirty asked with no head'),
                 git_snapshot=lambda *a, **k: pytest.fail('snapshot with no head'),
                 branch_exists=_script(False), git_merge_base=_script(BASE),
                 run_check=lambda *_a, **_k: pytest.fail('a command ran with no head'))
    r = rig(workdir='ws', branch='task', node=node)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    v = r.one()
    assert (v.verifier, v.state) == ('generic_human', 'AWAITING_HUMAN')
    assert (v.revision, v.base_revision, v.workspace) == (None, None, 'ws')
    assert [c['result'] for c in v.criteria] == ['unknown']
    assert _names(node) == ['git_head']
    assert r.task().state == 'VERIFYING'
    assert [(m, t) for m, t, _w in r.missions.fired] == [(r.mid, 'block')]


def test_two_refused_reads_after_the_checks_name_both_and_pass_nothing(rig):
    node = _Node(git_head=_script(REV, None), git_dirty=_script(None),
                 branch_exists=_script(False), run_check=_script(_result()))
    r = rig(workdir='ws', node=node)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    v = r.one()
    assert v.checks[0]['result'] == 'pass'
    c = _workspace(v)
    assert c['result'] == 'error'
    assert c['detail'] == ('the workspace could not be checked after verification: '
                           'HEAD and git status refused or unavailable')
    assert 'moved' not in c['detail'] and ' -> ' not in c['detail']
    assert v.state == 'ERROR' and r.task().state == 'VERIFYING'
    assert r.missions.fired == []


def test_a_missing_workdir_is_never_read_and_never_decided_by_the_machine(rig):
    node = _Node(git_head=_script(REV), git_dirty=_script(True),
                 git_snapshot=_script(SNAP), branch_exists=_script(False),
                 git_merge_base=_script(BASE), run_check=_script(_result()))
    r = rig(workdir=None, branch='task', node=node)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    v = r.one()
    assert (v.verifier, v.state) == ('generic_human', 'AWAITING_HUMAN')
    assert (v.revision, v.workspace) == (None, None)
    assert [c['result'] for c in v.criteria] == ['unknown']
    assert node.calls == []
    assert r.task().state == 'VERIFYING'
    assert [(m, t) for m, t, _w in r.missions.fired] == [(r.mid, 'block')]


def test_a_non_task_branch_is_never_asked_whether_it_is_dirty_before_the_checks(rig):
    node = _Node(git_head=_script(REV), git_dirty=_script(None),
                 branch_exists=_script(False), run_check=_script(_result()))
    r = rig(workdir='ws', node=node)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    assert (('ws',), {'tracked_only': True}) in _calls(node, 'git_dirty')
    assert (('ws',), {}) not in _calls(node, 'git_dirty')
    assert 'git_snapshot' not in _names(node)
    v = r.one()
    c = _workspace(v)
    assert c['detail'] == ('the workspace could not be checked after verification: '
                           'git status refused or unavailable')
    assert v.state == 'ERROR' and r.task().state == 'VERIFYING'


def test_a_clean_task_tree_is_never_snapshotted_and_keeps_the_head_git_read(rig):
    node = _Node(git_head=_script(REV), git_dirty=_script(False),
                 branch_exists=_script(False), git_merge_base=_script(BASE),
                 git_numstat=_script([('1', '0', 'a.py')]), git_diff=_script(''),
                 git_snapshot=lambda *a, **k: pytest.fail('a clean tree was snapshotted'),
                 run_check=_script(_result()))
    r = rig(workdir='ws', branch='task', node=node)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    assert (('ws',), {}) in _calls(node, 'git_dirty')
    assert (('ws',), {'tracked_only': True}) in _calls(node, 'git_dirty')
    names = _names(node)
    assert names.index('git_dirty') < names.index('run_check')
    v = r.one()
    assert (v.revision, v.base_revision) == (REV, BASE)
    assert [c['name'] for c in v.checks] == ['changes', 'test: tool --check']
    assert v.state == 'PASSED' and r.task().state == 'SUCCEEDED'


def test_dirty_task_work_is_snapshotted_once_and_becomes_the_head(rig):
    node = _Node(git_head=_script(REV, SNAP), git_dirty=_script(True, False),
                 git_snapshot=_script(SNAP), branch_exists=_script(False),
                 git_merge_base=_script(BASE), git_numstat=_script([('1', '0', 'a.py')]),
                 git_diff=_script(''), run_check=_script(_result()))
    r = rig(workdir='ws', branch='task', attempt=2, node=node)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    assert _calls(node, 'git_snapshot') == [(
        ('ws', 'archeus: result of task t1 (attempt 2)'), {})]
    assert ((r.root, SNAP, 'HEAD'), {}) in _calls(node, 'git_merge_base')
    v = r.one()
    assert v.revision == SNAP
    assert v.state == 'PASSED' and r.task().state == 'SUCCEEDED'


@pytest.mark.parametrize('exists', [True, False], ids=['branch-there', 'branch-gone'])
def test_the_merge_base_is_asked_against_the_mission_branch_only_while_it_exists(
        rig, exists):
    node = _Node(git_head=_script(REV), git_dirty=_script(False),
                 branch_exists=_script(exists), git_merge_base=_script(BASE),
                 git_numstat=_script([('1', '0', 'a.py')]), git_diff=_script(''),
                 run_check=_script(_result()))
    r = rig(workdir='ws', branch='task', node=node)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    assert ((r.root, mission_branch(r.mid)), {}) in _calls(node, 'branch_exists')
    base = mission_branch(r.mid) if exists else 'HEAD'
    assert ((r.root, REV, base), {}) in _calls(node, 'git_merge_base')


def test_a_branchless_task_invents_no_base_and_no_changes_check(rig):
    node = _Node(git_head=_script(REV), git_dirty=_script(False),
                 branch_exists=_script(True), git_merge_base=_script(BASE),
                 git_numstat=_script([('1', '0', 'a.py')]), git_diff=_script(''),
                 run_check=_script(_result()))
    r = rig(workdir='ws', node=node)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    for name in ('git_merge_base', 'git_numstat', 'git_diff'):
        assert name not in _names(node)
    v = r.one()
    assert v.base_revision is None and v.revision == REV
    assert [c['name'] for c in v.checks] == ['test: tool --check']
    assert v.state == 'PASSED'


def test_a_moved_workspace_shows_both_revisions_short_and_never_long(rig):
    node = _Node(git_head=_script(REV, REV2), git_dirty=_script(False),
                 branch_exists=_script(False), git_merge_base=_script(BASE),
                 git_numstat=_script([('1', '0', 'a.py')]), git_diff=_script(''),
                 run_check=_script(_result()))
    r = rig(workdir='ws', branch='task', node=node)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    assert (('ws',), {'tracked_only': True}) not in _calls(node, 'git_dirty')
    v = r.one()
    c = _workspace(v)
    assert c['result'] == 'error'
    assert c['detail'] == 'the workspace moved during verification (%s -> %s)' % (
        REV[:12], REV2[:12])
    assert REV not in c['detail'] and REV2 not in c['detail']
    assert v.state == 'ERROR' and r.task().state == 'VERIFYING'
    assert r.missions.fired == []
