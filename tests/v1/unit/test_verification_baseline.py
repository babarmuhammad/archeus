"""T-1068: the base-revision regression check (coarse pass-to-pass). A failed
test command is run again at the base the task (or the mission branch) started
from, for a project opted in (`verify baseline`, off by default: owner decision
113), and its check then says `regressed` or `also fails in a clean base checkout`.
Advisory: no result and no verdict moves. Per-test granularity is out of scope: the
label is of the whole command."""

import os
import subprocess
import sys

import pytest

from archeus.core.application import optins
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.core.verification import evidence
from archeus.node import local
from archeus.node.local import LocalNode

from . import test_gaps_core_verification_worker as W
from .test_gaps_core_verification_worker import AUTO, BASE, REV, _Node, _result, _script

rig = W.rig

OTHER = 'e' * 40
ALSO = 'also fails in a clean base checkout'


def _fail(**extra):
    return dict({'name': 'test: t', 'kind': 'command', 'result': 'fail', 'exit_code': 1,
                 'detail': 'exit 1'}, **extra)


@pytest.mark.parametrize('at_base,label', [('pass', 'regressed'), ('fail', ALSO),
                                           ('error', None)])
def test_a_failed_check_names_what_its_command_did_at_the_base(at_base, label):
    base = evidence.base_of(dict(_fail(), result=at_base), BASE)
    out = evidence.with_base(_fail(), base)
    assert out['result'] == 'fail' and out['baseline'] == base
    assert base['label'] == label and base['revision'] == BASE
    if label is None:
        assert out['detail'] == 'exit 1'
    else:
        assert out['detail'] == 'exit 1; %s (%s)' % (label, BASE[:12])


def test_a_check_that_did_not_fail_or_has_no_base_run_is_left_as_it_is():
    base = evidence.base_of(dict(_fail(), result='pass'), BASE)
    ok = dict(_fail(), result='pass', detail='exit 0')
    assert evidence.with_base(ok, base) is ok
    assert evidence.with_base(_fail(), None) == _fail()


class _Base:
    """The node's calls for a task in its own worktree `ws` whose test fails there;
    *at_base* is the same command's exit code in the base checkout."""

    def __init__(self, at_base=0, checkout=None):
        self.runs, self.made, self.dropped = [], [], []
        self.at_base, self.checkout = at_base, checkout

    def run_check(self, ws, argv, **kw):
        self.runs.append((ws, kw['out_path']))
        return _result(exit_code=1 if ws == 'ws' else self.at_base)

    def base_checkout(self, root, path, rev):
        self.made.append((root, path, rev))
        if self.checkout is not None:
            raise self.checkout
        return path

    def node(self, **more):
        return _Node(**dict(git_head=_script(REV), git_dirty=_script(False),
                            branch_exists=_script(False), git_merge_base=_script(BASE),
                            git_numstat=_script([('1', '0', 'a.py')]), git_diff=_script(''),
                            run_check=self.run_check, base_checkout=self.base_checkout,
                            drop_checkout=lambda root, path: self.dropped.append(path) or True)
                     | more)


def _opt(r, opted_in=True):
    """The user's own command, as the opt-in route runs it."""
    return r.db.writer.execute(optins.set_opt_in, dict(
        actor=Ref('user_device', ids.new_id('principal')), owner_id=r.proj, kind='verify',
        name='baseline', opted_in=opted_in))


def _task(rig, fake, opt=True, **kw):
    r = rig(workdir='ws', branch='task', node=fake.node(), **kw)
    if opt:
        _opt(r)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    return r


def test_a_test_that_passed_at_the_base_and_fails_now_is_regressed_and_still_failed(rig):
    fake = _Base(at_base=0)
    r = _task(rig, fake)
    v = r.one()
    test = next(c for c in v.checks if c['name'] == 'test: tool --check')
    assert v.state == 'FAILED' and test['result'] == 'fail'
    assert test['baseline']['label'] == 'regressed'
    assert test['detail'] == 'exit 1; regressed (%s)' % BASE[:12]
    (root, tree, rev), = fake.made
    assert (root, rev) == (r.root, BASE) and fake.dropped == [tree]
    assert [ws for ws, _p in fake.runs] == ['ws', tree]
    assert os.path.join(v.id, 'base') in fake.runs[1][1]    # its own log, not the candidate's


def test_a_test_failing_at_the_base_too_is_failing_at_base(rig):
    r = _task(rig, _Base(at_base=1))
    test = r.one().checks[-1]
    assert test['baseline']['label'] == ALSO and test['result'] == 'fail'


def test_without_the_opt_in_nothing_runs_at_the_base(rig):
    fake = _Base()
    r = _task(rig, fake, opt=False)
    assert fake.made == [] and 'baseline' not in r.one().checks[-1]
    assert r.one().state == 'FAILED'


def test_an_opt_out_or_another_projects_opt_in_runs_nothing_at_the_base(rig):
    fake = _Base()
    r = rig(workdir='ws', branch='task', node=fake.node())
    _opt(r)
    _opt(r, opted_in=False)
    other = entities.Project(id=ids.new_id('project'), workspace_id=ids.GLOBAL_WORKSPACE,
                             name='other')
    r._place(other, entities.OptIn(id=ids.new_id('opt_in'), kind='verify', name='baseline',
                                   project_id=other.id),
             entities.OptIn(id=ids.new_id('opt_in'), kind='source', name='project',
                            project_id=r.proj))
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    assert fake.made == [] and r.one().state == 'FAILED'


@pytest.mark.parametrize('owner,name', [('account', 'baseline'), ('project', 'anything')])
def test_a_verify_opt_in_is_only_a_projects_and_only_a_named_one(owner, name):
    with pytest.raises(ValueError, match='verify opt-in'):
        entities.OptIn(id=ids.new_id('opt_in'), kind='verify', name=name,
                       **{owner + '_id': ids.new_id(owner)})


def test_a_passing_test_or_a_failing_build_costs_no_base_run(rig):
    fake = _Base()
    fake.run_check = lambda ws, argv, **kw: _result(exit_code=0 if argv[-1] == '--check' else 2)
    r = _task(rig, fake, builds=('tool --build',))
    assert fake.made == [] and r.one().state == 'FAILED'
    assert all('baseline' not in c for c in r.one().checks)


def test_a_base_that_cannot_be_checked_out_is_said_and_changes_nothing(rig):
    fake = _Base(checkout=OSError('path too long'))
    r = _task(rig, fake)
    test = r.one().checks[-1]
    assert r.one().state == 'FAILED' and test['result'] == 'fail'
    assert test['baseline']['result'] == 'error' and test['baseline']['label'] is None
    assert 'path too long' in test['baseline']['detail'] and test['detail'] == 'exit 1'
    assert fake.dropped == [fake.made[0][1]]       # what a failed add left is removed too


def test_an_errored_base_run_is_tried_again_and_a_failed_removal_is_logged(rig, caplog):
    fake = _Base(at_base=1)
    r = rig(workdir='ws', branch='task', node=fake.node(drop_checkout=lambda root, path: False))
    kept = evidence.base_of(dict(_fail(), result='error'), BASE)
    r.vrow(state='FAILED', execution_id=r.erow(),
           checks=(_fail(name='test: tool --check', baseline=kept),))
    _opt(r)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    assert len(fake.made) == 1 and 'was not removed' in caplog.text


@pytest.mark.parametrize('kept_at,runs', [(BASE, 0), (OTHER, 1)])
def test_one_base_run_per_plan_base_and_command(rig, kept_at, runs):
    fake = _Base(at_base=1)
    r = rig(workdir='ws', branch='task', node=fake.node())
    kept = evidence.base_of(dict(_fail(), result='pass'), kept_at)
    # an earlier attempt's row of the same plan, its command already run at *kept_at*
    r.vrow(state='FAILED', execution_id=r.erow(),
           checks=(_fail(name='test: tool --check', baseline=kept),))
    _opt(r)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    assert len(fake.made) == runs
    v = next(v for v in r.rows() if v.execution_id == r.eid)
    assert v.state == 'FAILED' and v.checks[-1]['baseline']['revision'] == BASE
    assert v.checks[-1]['baseline']['label'] == ('regressed' if runs == 0 else ALSO)


def test_a_mission_criterion_is_compared_with_the_integration_base(rig):
    fake = _Base(at_base=0)
    fake.run_check = lambda ws, argv, **kw: _result(exit_code=0 if ws.endswith('tree') else 1)
    r = rig(mission_state='VERIFYING', base=BASE, head=REV, task_state='SUCCEEDED',
            success=(AUTO,), node=fake.node())
    _opt(r)
    assert r.worker._verify_mission(r.mid) is True
    v = r.one('mission')
    test = next(c for c in v.checks if 'baseline' in c)
    assert v.state == 'FAILED' and test['baseline']['label'] == 'regressed'
    assert fake.made[0][2] == BASE and fake.dropped


def _git(cwd, *args):
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *args], cwd=cwd,
                   check=True, capture_output=True)


def test_the_base_checkout_is_a_detached_tree_of_the_base_from_an_absolute_git(
        tmp_path, monkeypatch):
    root = str(tmp_path / 'repo')
    os.makedirs(root)
    _git(root, 'init', '-q')
    for text in ('old', 'new'):
        with open(os.path.join(root, 'f.txt'), 'w') as f:
            f.write(text)
        _git(root, 'add', 'f.txt')
        _git(root, 'commit', '-q', '-m', text)
    base = subprocess.run(['git', 'rev-parse', 'HEAD~1'], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()
    seen, real = [], local.subprocess.run
    monkeypatch.setattr(local.subprocess, 'run', lambda argv, **kw: seen.append(argv[0])
                        or real(argv, **kw))
    tree = str(tmp_path / 'b' / 'tree')
    os.makedirs(tree)                       # what a crash left: replaced, not refused
    assert LocalNode.base_checkout(root, tree, base) == tree
    with open(os.path.join(tree, 'f.txt')) as f:
        assert f.read() == 'old'
    assert LocalNode.drop_checkout(root, tree) is True and not os.path.exists(tree)
    assert len(seen) == 3 and all(os.path.isabs(a) and a == local._git_exe() for a in seen)


def test_the_base_checkout_runs_no_hook_or_filter_of_the_repository(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    root.mkdir()
    _git(str(root), 'init', '-q')
    marker = tmp_path / 'ran'
    script = tmp_path / 'mark.py'
    script.write_text('import sys\nopen(%r, "a").write(sys.argv[1] + "\\n")\n'
                      'sys.stdout.write(sys.stdin.read())\n' % str(marker))
    run = '"%s" "%s"' % (sys.executable.replace('\\', '/'), str(script).replace('\\', '/'))
    hook = root / '.git' / 'hooks' / 'post-checkout'
    hook.write_text('#!/bin/sh\n%s hook </dev/null\n' % run)
    hook.chmod(0o755)
    _git(str(root), 'config', 'filter.mark.smudge', run + ' smudge')
    (root / '.gitattributes').write_text('*.txt filter=mark\n')
    (root / 'f.txt').write_text('old')
    _git(str(root), 'add', '.')
    _git(str(root), 'commit', '-q', '-m', 'base')
    base = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True,
                          text=True, check=True).stdout.strip()
    _git(str(root), 'worktree', 'add', '-q', '--detach', str(tmp_path / 'probe'), base)
    assert marker.exists()                  # the rig is live: plain git runs both
    marker.unlink()
    tree = str(tmp_path / 'b' / 'tree')
    assert LocalNode.base_checkout(str(root), tree, base) == tree
    assert (tmp_path / 'b' / 'tree' / 'f.txt').read_text() == 'old'
    assert LocalNode.drop_checkout(str(root), tree) is True
    assert not marker.exists()
