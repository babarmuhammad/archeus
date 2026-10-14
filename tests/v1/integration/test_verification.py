"""P13 verification, merge-back and review at the application layer: the
scenarios that need a deterministic hold inside Core or a call the contract
cannot express (p13-design-gate §24: V04, V07-V10, V12, V13, the merge-back
conflict and abandon, the restart sweep).

They run the in-process judge binding with the real verification worker, but
pump its parts one at a time (`pump`), so a test can stop between the worker's
write and the engine's judgement of it.
"""

import dataclasses
import os
import subprocess
from types import SimpleNamespace

import pytest

from archeus.core.application import commands, verification as V
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.verification import evidence
from archeus.infra import paths
from archeus.infra.db import rows
from archeus.node.local import LocalNode
from v1.judge.client import CoreClientError, InProcessClient
from v1.judge.conftest import recorded_brain
from v1.judge import support
from v1.judge.support import Rig

FIX = 'def add(a, b):\n    return a + b\n'
WRONG = 'def add(a, b):\n    return a * b\n'


def _write(content, path='calc.py'):
    return {'emit': {'type': 'tool', 'name': 'Write',
                     'input': {'file_path': path, 'content': content}}}


@pytest.fixture
def core(archeus_home, monkeypatch):
    c = InProcessClient(archeus_home, callers=[recorded_brain()], real_verification=True)
    monkeypatch.setattr(support, 'idle', c._idle)      # the rig's waits pump this Core
    yield c
    c.close()


def pump(c, until=None, limit=400):
    """Every part of the in-process Core, one at a time; stop as soon as
    *until()* holds (checked after each part); fail if Core idles first."""
    for _ in range(limit):
        moved = False
        for part in _parts(c):
            moved = bool(part()) or moved
            if until is not None and until():
                return True
        if not moved:
            # idle with the condition unmet is a failure, never a quiet return
            assert until is None or until(), 'Core went idle before the awaited state'
            return True
    raise AssertionError('Core kept moving for %d rounds' % limit)


def _parts(c):
    def engine():
        with c._core().read() as conn:
            live = [m.entity.id for m in rows.where(conn, entities.Mission)
                    if m.entity.state not in ('COMPLETED', 'CANCELLED', 'FAILED', 'BLOCKED',
                                              'PAUSED', 'APPROVAL_REQUIRED')]
        return any([c._engine.step(mid)['changed'] for mid in live])
    return (lambda: c._engine.manager.tick() or bool(c._engine.manager._procs),
            lambda: c._world.pass_once()['changed'],
            lambda: c._knowledge.pass_once()['changed'],
            lambda: c._plans.pass_once()['changed'],
            lambda: c._verify.pass_once()['changed'],
            engine)


def _do(c, command, **kw):
    return c._core().writer.execute(command, dict(kw, actor=Ref('system', c._system)))


def _user(c, command, **kw):
    return c._core().writer.execute(command, dict(kw, actor=Ref('user_device', c._principal)))


def _get(c, cls, eid):
    with c._core().read() as conn:
        return rows.get(conn, cls, eid).entity


def _mission(c, rig, fixture='verify-python', steps=(), **kw):
    repo = rig.fixture_repo(fixture)
    rig.script_harness('t1', list(steps))
    m = c.create_mission(title='Fix add', objective='Make add add', project_id=repo.project_id,
                         **kw)
    return repo, m['id']


def _state(c, mid):
    return c.get_mission(mid)['state']


def _task(c, mid):
    with c._core().read() as conn:
        plan = commands.active_plan(conn, mid)
        if plan is None:
            return None
        (t,) = [r.entity for r in rows.where(conn, entities.Task, plan_id=plan.entity.id)]
    return t


def _t(c, mid, attr='state'):
    """An attribute of the mission's one task, None before it is planned."""
    return getattr(_task(c, mid), attr, None)


def _vs(c, mid, kind=None):
    return [v for v in c.verifications(mid) if kind is None or v['subject']['kind'] == kind]


# ── V04: stale evidence (§11) ───────────────────────────────────────────────

def test_V04_a_mission_branch_moved_after_its_criteria_were_verified_is_verified_again(
        core, monkeypatch):
    rig = Rig(core)
    repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                  'summary': 'done'}}])
    wt = paths.mission_worktree_path(repo.project_id, mid)
    real, moved = evidence.run_commands, []

    def run_then_move(node, workspace, cmds, **kw):
        checks = real(node, workspace, cmds, **kw)
        if workspace == wt and not moved:
            # someone commits to the mission branch while its criteria are checked
            with open(os.path.join(wt, 'calc.py'), 'w', encoding='utf-8', newline='\n') as f:
                f.write(WRONG)
            subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit',
                            '-qam', 'moved'], cwd=wt, check=True)
            moved.append(subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=wt,
                                        capture_output=True, text=True,
                                        check=True).stdout.strip())
        return checks
    monkeypatch.setattr(evidence, 'run_commands', run_then_move)
    pump(core, lambda: _state(core, mid) in ('REPLANNING', 'REVIEWING', 'COMPLETED'))
    (head,) = moved
    assert _get(core, entities.Mission, mid).integration_head == head
    crit = _vs(core, mid, 'mission')
    old = [v for v in crit if v['revision'] != head]
    new = [v for v in crit if v['revision'] == head]
    assert old and old[0]['state'] == 'PASSED'
    # the PASSED of the old head never moved the mission: the new head is judged
    assert new and new[-1]['state'] == 'FAILED'
    assert _state(core, mid) == 'REPLANNING'


# ── V07: one logical verdict (§10, §20) ─────────────────────────────────────

def test_V07_a_second_verdict_for_the_same_verification_is_refused(core):
    rig = Rig(core)
    _repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                   'summary': 'done'}}])
    pump(core, lambda: _state(core, mid) == 'COMPLETED')
    (v,) = _vs(core, mid, 'task')
    with pytest.raises(V.Refused):
        _do(core, V.record, missions=core._missions, verification_id=v['id'],
            checks=[{'name': 'test', 'kind': 'command', 'result': 'fail'}])
    t = _task(core, mid)
    with pytest.raises(V.Refused):          # the task left VERIFYING with its verdict
        _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
            verifier='code', execution_id=v['execution_id'])
    before = len(core.verifications(mid))
    pump(core)                              # redelivery, idle passes: nothing new
    assert len(core.verifications(mid)) == before
    assert [x['state'] for x in _vs(core, mid, 'task')] == ['PASSED']


# ── V08: restart during verification (§19) ──────────────────────────────────

def test_V08_a_verification_running_when_core_died_is_re_observed(core, archeus_home):
    rig = Rig(core)
    _repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                   'summary': 'done'}}])
    pump(core, lambda: _t(core, mid) == 'VERIFYING' and not _vs(core, mid))
    t = _task(core, mid)
    with core._core().read() as conn:
        e = V.verified_execution(conn, t)
        m = rows.get(conn, entities.Mission, mid).entity
        _root, ws, revision, base, _cmds = core._verify._workspace_of(conn, m, t, e)
    # started exactly as the worker starts it, then the process is gone
    started = _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
                  verifier='code', execution_id=e.id, revision=revision, base_revision=base,
                  workspace=ws, criteria=[dict(c, index=i, result='unknown')
                                          for i, c in enumerate(t.acceptance)])
    core.close(drain=False)                 # Core dies with the row RUNNING
    again = InProcessClient(archeus_home, callers=[recorded_brain()], real_verification=True)
    try:
        again._principal, again._system = core._principal, core._system
        row = _get(again, entities.Verification, started['verification_id'])
        assert row.state == 'ERROR' and row.error == 'core_restarted' and row.errors == 1
        pump(again, lambda: _state(again, mid) == 'COMPLETED')
        states = [x['state'] for x in _vs(again, mid, 'task')]
        assert states.count('PASSED') == 1
    finally:
        again.close()


# ── V09, V10, V13: evidence bound to its lineage (§20) ─────────────────────

def test_V09_forged_evidence_is_refused(core):
    rig = Rig(core)
    _repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                   'summary': 'done'}}])
    pump(core, lambda: _t(core, mid) == 'VERIFYING' and not _vs(core, mid))
    t = _task(core, mid)
    with core._core().read() as conn:
        e = V.verified_execution(conn, t)
    vid = _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
              verifier='code', execution_id=e.id)['verification_id']
    # a check naming evidence the store does not hold
    with pytest.raises(V.Refused, match='does not hold'):
        _do(core, V.record, missions=core._missions, verification_id=vid,
            checks=[{'name': 'test', 'kind': 'command', 'result': 'pass',
                     'output_sha256': 'a' * 64}])
    # only a user device decides, and only what waits on a human
    with pytest.raises(V.Refused):
        _do(core, V.decide, missions=core._missions, verification_id=vid, decision='accept')
    with pytest.raises(CoreClientError) as err:
        core.decide_verification(vid, 'accept')             # RUNNING: nothing to decide
    assert err.value.status == 409
    assert _get(core, entities.Verification, vid).state == 'RUNNING'


def test_V10_evidence_of_another_task_or_execution_is_refused(core):
    rig = Rig(core)
    _r1, m1 = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                'summary': 'done'}}])
    pump(core, lambda: _state(core, m1) == 'COMPLETED')
    other = _vs(core, m1, 'task')[0]['execution_id']
    _r2, m2 = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                'summary': 'done'}}])
    pump(core, lambda: _t(core, m2) == 'VERIFYING' and not _vs(core, m2))
    t2 = _task(core, m2)
    with pytest.raises(V.Refused, match='not the one whose end'):
        _do(core, V.start, missions=core._missions, subject=Ref('task', t2.id),
            verifier='code', execution_id=other)
    m2row = _get(core, entities.Mission, m2)
    with pytest.raises(V.Refused):          # a mission criterion of a mission not verifying
        _do(core, V.start, missions=core._missions, subject=Ref('mission', m2),
            verifier='code', criterion=0, revision=m2row.integration_head)


def test_V13_a_superseded_plan_cannot_be_verified_or_counted(core):
    rig = Rig(core)
    _repo, mid = _mission(core, rig, steps=[_write(WRONG), {'emit': {'type': 'result',
                                                                     'summary': 'done'}}])
    pump(core, lambda: (c := core.get_mission(mid))['plan_version'] == 2)
    with core._core().read() as conn:
        plans = sorted((r.entity for r in rows.where(conn, entities.Plan, mission_id=mid)),
                       key=lambda p: p.plan_version)
        old = [r.entity for r in rows.where(conn, entities.Task, plan_id=plans[0].id)][0]
        e = max((r.entity for r in rows.where(conn, entities.Execution, task_id=old.id)),
                key=lambda x: x.attempt)
    assert plans[0].state == 'SUPERSEDED'
    with pytest.raises(V.Refused):
        _do(core, V.start, missions=core._missions, subject=Ref('task', old.id),
            verifier='code', execution_id=e.id)
    # the old plan's verifications never reach the guard snapshot of the new one
    with core._core().read() as conn:
        facts = commands.persisted_facts(core._core().writer and _Tx(conn),
                                         rows.get(conn, entities.Mission, mid))
    assert all(c.verification is None for c in facts.criteria)


class _Tx:
    """A read-only stand-in for a transaction: `persisted_facts` only reads."""

    def __init__(self, conn):
        self.conn = conn

    def where(self, cls, **eq):
        return rows.where(self.conn, cls, **eq)


# ── V12: a verifier fault is not a task failure (§6, §16) ──────────────────

def test_V12_a_runner_that_cannot_run_is_an_error_retried_once_then_yours(core, monkeypatch):
    rig = Rig(core)
    _repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                   'summary': 'done'}}])
    monkeypatch.setattr(evidence, 'argv_of', lambda cmd: ['archeus-no-such-runner-xyz'])
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    (v,) = _vs(core, mid, 'task')
    assert v['state'] == 'ERROR' and v['errors'] == 2          # tried, retried once
    assert v['checks'][-1]['result'] == 'error'
    assert _task(core, mid).state == 'VERIFYING'                # the task did not fail
    held = [e for e in core.events(0) if e['type'] == 'mission.state_changed'
            and e['subject']['id'] == mid and e['payload']['to'] == 'BLOCKED']
    assert 'verification could not run' in held[-1]['payload']['reason']
    # the runner is back; you resume; the same verification is tried again and passes
    monkeypatch.undo()
    core.resume(mid)
    pump(core, lambda: _state(core, mid) == 'COMPLETED')
    (v,) = _vs(core, mid, 'task')
    assert v['state'] == 'PASSED' and v['errors'] == 2


# ── merge-back conflict and abandon (§12.5) ─────────────────────────────────

def test_a_conflicting_merge_blocks_the_mission_and_can_be_abandoned(core):
    rig = Rig(core)
    repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                  'summary': 'done'}}])
    pump(core, lambda: _t(core, mid) in ('VERIFYING', 'SUCCEEDED'))
    # the mission branch gains a conflicting change before the task's result lands
    subprocess.run(['git', 'branch', 'archeus/%s' % mid, 'HEAD'], cwd=repo.path, check=True)
    wt = paths.mission_worktree_path(repo.project_id, mid)
    subprocess.run(['git', 'worktree', 'add', '-q', '--', wt, 'archeus/%s' % mid],
                   cwd=repo.path, check=True)
    with open(os.path.join(wt, 'calc.py'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('def add(a, b):\n    return b + a  # theirs\n')
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qam',
                    'theirs'], cwd=wt, check=True)
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    t = _task(core, mid)
    assert t.state == 'SUCCEEDED' and t.integration_state == 'CONFLICT'
    assert t.conflicts == ('calc.py',)
    reason = [e for e in core.events(0) if e['type'] == 'mission.state_changed'
              and e['subject']['id'] == mid][-1]['payload']['reason']
    assert 'conflicts with archeus/%s in calc.py' % mid in reason
    # the mission branch was left as it was
    head = subprocess.run(['git', 'log', '-1', '--format=%s'], cwd=wt, capture_output=True,
                          text=True, check=True).stdout.strip()
    assert head == 'theirs'
    out = core.abandon_integration(t.id, reason='I will redo it')
    assert out['integration_state'] == 'ABANDONED'
    with pytest.raises(CoreClientError):
        core.abandon_integration(t.id)                      # decided once


def test_only_the_verified_revision_is_merged(core):
    """`task_verified` is guarded: a revision no passing verification checked
    cannot be merged (D10)."""
    rig = Rig(core)
    _repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                   'summary': 'done'}}])
    pump(core, lambda: _t(core, mid, 'integration_state') == 'PENDING')
    t = _task(core, mid)
    from archeus.core.application.lifecycle import GuardFailed
    with pytest.raises(GuardFailed, match='not the verified'):
        _do(core, V.begin_merge, task_id=t.id, revision='f' * 40)
    pump(core, lambda: _t(core, mid, 'integration_state') == 'MERGED')


def test_a_worktree_task_result_is_committed_before_it_is_verified(core):
    """The snapshot commit (§12.2): the agent left its change uncommitted, and
    the verified revision is a commit holding it."""
    rig = Rig(core)
    repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                  'summary': 'done'}}])
    pump(core, lambda: _state(core, mid) == 'COMPLETED')
    (v,) = _vs(core, mid, 'task')
    msg = subprocess.run(['git', 'log', '-1', '--format=%an|%s', v['revision']], cwd=repo.path,
                         capture_output=True, text=True, check=True).stdout.strip()
    assert msg.startswith('Archeus|archeus: result of task t1')
    # merged, and the task's worktree removed; its branch kept
    t = _task(core, mid)
    with core._core().read() as conn:
        e = V.verified_execution(conn, t)
    assert not os.path.exists(e.workdir)
    assert subprocess.run(['git', 'rev-parse', '--verify', '-q', e.branch],
                          cwd=repo.path, capture_output=True).returncode == 0


def test_a_commit_on_the_task_branch_after_verification_is_not_merged(core):
    """Merge-back takes the verified SHA, never the branch name (§12.4), and
    the mission is not done with its tasks until the result is merged (D11)."""
    rig = Rig(core)
    repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                  'summary': 'done'}}])
    pump(core, lambda: _t(core, mid, 'integration_state') == 'PENDING')
    assert not any(p() for p in _parts(core)[-1:])      # the engine: nothing to do yet
    assert _state(core, mid) == 'EXECUTING'             # verified, not merged: not done
    with core._core().read() as conn:
        e = V.verified_execution(conn, _task(core, mid))
    with open(os.path.join(e.workdir, 'late.txt'), 'w', encoding='utf-8') as f:
        f.write('never verified\n')
    subprocess.run(['git', 'add', 'late.txt'], cwd=e.workdir, check=True)
    subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm',
                    'late'], cwd=e.workdir, check=True)
    pump(core, lambda: _state(core, mid) == 'COMPLETED')
    (v,) = _vs(core, mid, 'task')
    files = subprocess.run(['git', 'ls-tree', '-r', '--name-only', 'archeus/%s' % mid],
                           cwd=repo.path, capture_output=True, text=True,
                           check=True).stdout.split()
    assert 'late.txt' not in files and 'calc.py' in files
    assert subprocess.run(['git', 'merge-base', '--is-ancestor', v['revision'],
                           'archeus/%s' % mid], cwd=repo.path).returncode == 0


def test_a_rejecting_review_does_not_complete_the_mission(core):
    rig = Rig(core)
    _repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                   'summary': 'done'}}])
    pump(core, lambda: _state(core, mid) == 'REVIEWING')
    out = core.review(mid, 'reject', note='not like this')
    assert out['verdict'] == 'reject' and out['mission'] is None
    assert _state(core, mid) == 'REVIEWING'
    assert [r['state'] for r in core.reviews(mid)] == ['REJECTED']
    core.review(mid, 'accept')
    assert _state(core, mid) == 'COMPLETED'


def test_a_verification_whose_plan_is_superseded_while_it_runs_cannot_be_recorded(core):
    rig = Rig(core)
    _repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                   'summary': 'done'}}])
    pump(core, lambda: _t(core, mid) == 'VERIFYING' and not _vs(core, mid))
    t = _task(core, mid)
    with core._core().read() as conn:
        e = V.verified_execution(conn, t)
        plan = commands.active_plan(conn, mid).entity
    vid = _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
              verifier='code', execution_id=e.id)['verification_id']

    def supersede(tx, *, actor):        # a newer plan version lands meanwhile
        tx.insert(dataclasses.replace(plan, id=ids.new_id('plan'),
                                      plan_version=plan.plan_version + 1,
                                      round_seq=plan.round_seq + 1), actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', mid), actor,
                            payload={'fields': ['plan'], 'forged_by': 'test'}))
    _do(core, supersede)
    with pytest.raises(V.Refused, match='not in force'):
        _do(core, V.record, missions=core._missions, verification_id=vid,
            checks=[{'name': 'test', 'kind': 'command', 'result': 'pass'}])
    assert _get(core, entities.Verification, vid).state == 'RUNNING'


# ── a task's workspace (P11 as built, §28 note 11) ──────────────────────────

def _git(root, *args):
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout.strip()


def test_a_branch_left_by_a_failed_worktree_add_does_not_stop_the_task(core):
    """`git worktree add -b` can create the branch and then fail; every later
    attempt used to fail on the branch itself, uncharged, forever."""
    rig = Rig(core)
    repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                  'summary': 'done'}}])
    _git(repo.path, 'branch', 'archeus/%s.t1' % mid)       # what the failed add left
    pump(core, lambda: _state(core, mid) == 'COMPLETED')
    t = _task(core, mid)
    with core._core().read() as conn:
        es = [r.entity for r in rows.where(conn, entities.Execution, task_id=t.id)]
    assert [(e.state, e.stop_reason) for e in es] == [('ENDED_OK', None)]


def test_a_workspace_that_cannot_be_made_spends_the_tasks_attempts(core, monkeypatch):
    from archeus.node.local import LocalNode

    def refuse(root, path, branch, base='HEAD'):
        raise OSError('git worktree add failed: fatal: simulated')
    monkeypatch.setattr(LocalNode, 'add_worktree', staticmethod(refuse))
    rig = Rig(core)
    _repo, mid = _mission(core, rig, steps=[_write(FIX)])
    pump(core, lambda: _task(core, mid) is not None)
    tid = _task(core, mid).id
    pump(core, lambda: _get(core, entities.Task, tid).state == 'FAILED')
    t = _get(core, entities.Task, tid)
    with core._core().read() as conn:
        es = [r.entity for r in rows.where(conn, entities.Execution, task_id=tid)]
    assert len(es) == t.max_attempts
    assert {(e.state, e.stop_reason, e.charged) for e in es} == {('ABANDONED', 'workspace', True)}


def _repo_with_commit(tmp_path):
    root = str(tmp_path / 'r')
    os.makedirs(root)
    _git(root, 'init', '-q', '-b', 'main')
    _git(root, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty',
         '-m', 'base')
    return root


def test_a_task_branch_that_holds_nothing_new_is_moved_to_its_base(tmp_path):
    """Kept after its merge (P13 §12.1), then a later plan version reuses the
    task key: the worktree starts from the base it asks for, not the old tip."""
    from archeus.node.local import LocalNode
    root = _repo_with_commit(tmp_path)
    _git(root, 'branch', 'archeus/m.t1')
    _git(root, 'checkout', '-q', '-b', 'archeus/m')
    _git(root, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty',
         '-m', 'merged later')
    _git(root, 'checkout', '-q', 'main')
    path = str(tmp_path / 'wt')
    assert LocalNode.add_worktree(root, path, 'archeus/m.t1', base='archeus/m') == path
    assert _git(path, 'rev-parse', 'HEAD') == _git(root, 'rev-parse', 'archeus/m')
    assert _git(path, 'rev-parse', '--abbrev-ref', 'HEAD') == 'archeus/m.t1'


def test_a_task_branch_holding_commits_its_base_lacks_is_never_moved(tmp_path):
    from archeus.node.local import LocalNode
    root = _repo_with_commit(tmp_path)
    _git(root, 'checkout', '-q', '-b', 'archeus/m.t1')
    _git(root, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '--allow-empty',
         '-m', 'work nobody merged')
    tip = _git(root, 'rev-parse', 'HEAD')
    _git(root, 'checkout', '-q', 'main')
    with pytest.raises(OSError, match='holds commits'):
        LocalNode.add_worktree(root, str(tmp_path / 'wt'), 'archeus/m.t1', base='main')
    assert _git(root, 'rev-parse', 'archeus/m.t1') == tip
    assert not os.path.exists(str(tmp_path / 'wt'))


# ── A6: the interim command guard (T-041, T-042) ────────────────────────────

#: the Git a legacy unknown or ordinary execution keeps under G1 (never a command)
_GIT = ('git_head', 'git_dirty', 'git_snapshot', 'branch_exists', 'git_merge_base',
        'mission_worktree', 'git_is_ancestor', 'git_merge', 'remove_worktree')


class _Node:
    """The worker's node with every call recorded: a method in *allow* reaches
    the real node, one in *fake* is answered by it, and any other call fails
    the test where it is made."""

    def __init__(self, real, allow=(), fake=None):
        self.real, self.allow, self.fake, self.calls = real, set(allow), dict(fake or {}), []

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append(name)
            if name in self.fake:
                return self.fake[name](*a, **k)
            if name in self.allow:
                return getattr(self.real, name)(*a, **k)
            raise AssertionError('the worker called node.%s%r' % (name, a))
        return call


def _node(c, monkeypatch, allow=(), fake=None):
    node = _Node(c._verify.node, allow, fake)
    monkeypatch.setattr(c._verify, 'node', node)
    return node


def _forge(c, mid, change):
    """A row changed or added directly, as an older Core or another path left it."""
    def put(tx, *, actor):
        change(tx, actor)
        tx.append(new_event('mission.updated', Ref('mission', mid), actor,
                            payload={'fields': [], 'forged_by': 'test'}))
    _do(c, put)


def _isolate(c, mid, execution_id, value=True):
    _forge(c, mid, lambda tx, actor: tx.update(entities.Execution, execution_id,
                                               {'isolated': value}, actor=actor))


def _another_execution(c, t, **kw):
    """Another attempt of task *t*, recorded as it ended (ENDED_OK makes it the
    one verified)."""
    def put(tx, actor):
        attempt = 1 + max(r.entity.attempt for r in tx.where(entities.Execution, task_id=t.id))
        tx.insert(entities.Execution(id=ids.new_id('execution'), task_id=t.id,
                                     mission_id=t.mission_id, plan_id=t.plan_id,
                                     attempt=attempt, **kw), actor=actor)
    _forge(c, t.mission_id, put)


def _verifying(c):
    """A mission whose one task waits for its verification, nothing recorded yet."""
    repo, mid = _mission(c, Rig(c), steps=[_write(FIX), {'emit': {'type': 'result',
                                                                  'summary': 'done'}}])
    pump(c, lambda: _t(c, mid) == 'VERIFYING' and not _vs(c, mid))
    t = _task(c, mid)
    with c._core().read() as conn:
        e = V.verified_execution(conn, t)
    return repo, mid, t, e


def _unconfined(c, mid):
    with c._core().read() as conn:
        return V.unconfined(conn, mid)


def _held(c, mid):
    return [x for x in c.events(0) if x['type'] == 'mission.state_changed'
            and x['subject']['id'] == mid and x['payload']['to'] == 'BLOCKED'][-1]['payload']


def _errored(c):
    """A task's code verification that errored once, as Core recorded it before
    the guard: revision and workspace are what the execution's workdir held."""
    _repo, mid, t, e = _verifying(c)
    vid = _do(c, V.start, missions=c._missions, subject=Ref('task', t.id), verifier='code',
              execution_id=e.id, revision='r1', base_revision='b1', workspace=e.workdir,
              criteria=[dict(x, index=i, result='unknown')
                        for i, x in enumerate(t.acceptance)])['verification_id']
    _do(c, V.record, missions=c._missions, verification_id=vid,
        checks=[{'name': 'test', 'kind': 'command', 'result': 'error', 'detail': 'no runner'}])
    return mid, t, e, vid


def _frozen(v):
    return {f: getattr(v, f) for f in entities.Verification._FROZEN}


def test_A6_the_guard_reads_every_prepared_execution_of_the_mission_and_never_clears(core):
    _repo, mid, t, e = _verifying(core)
    assert e.isolated is False and _unconfined(core, mid)
    # never prepared: no decision recorded, so it guards nothing
    _another_execution(core, t, isolated=True, process_seq=0, state='ABANDONED')
    assert _unconfined(core, mid)
    # an isolated attempt that failed
    _another_execution(core, t, isolated=True, process_seq=1, state='ENDED_ERROR')
    assert not _unconfined(core, mid)
    # and no later exactly-ordinary attempt lifts it
    _another_execution(core, t, isolated=False, process_seq=2, state='ENDED_ERROR')
    assert not _unconfined(core, mid)
    _repo2, other, _t2, _e2 = _verifying(core)
    assert _unconfined(core, other)                 # another mission is its own


def test_A6_an_execution_of_a_superseded_plan_still_guards_its_mission(core):
    _repo, mid = _mission(core, Rig(core), steps=[_write(WRONG), {'emit': {'type': 'result',
                                                                           'summary': 'done'}}])
    pump(core, lambda: core.get_mission(mid)['plan_version'] == 2)
    with core._core().read() as conn:
        first = min((r.entity for r in rows.where(conn, entities.Plan, mission_id=mid)),
                    key=lambda p: p.plan_version)
        old = [r.entity for task in rows.where(conn, entities.Task, plan_id=first.id)
               for r in rows.where(conn, entities.Execution, task_id=task.entity.id)]
    assert first.state == 'SUPERSEDED' and old and _unconfined(core, mid)
    _isolate(core, mid, old[0].id)
    assert not _unconfined(core, mid)


@pytest.mark.parametrize('isolated', [True, None])
def test_A6_one_execution_not_exactly_ordinary_guards_its_whole_mission(core, isolated):
    _repo, mid, t, _e = _verifying(core)
    _another_execution(core, t, isolated=isolated, process_seq=1, state='ABANDONED')
    assert not _unconfined(core, mid)


def test_A6_an_isolated_execution_goes_to_you_with_no_git_and_no_revision(core, monkeypatch):
    _repo, mid, t, e = _verifying(core)
    _isolate(core, mid, e.id)
    node = _node(core, monkeypatch)                 # any node call fails the test
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    (v,) = _vs(core, mid, 'task')
    assert (v['verifier'], v['state']) == ('generic_human', 'AWAITING_HUMAN')
    assert v['revision'] is None and v['base_revision'] is None and v['workspace'] is None
    assert V.WITHHELD in _held(core, mid)['reason']
    (why,) = [x['payload']['reason'] for x in core.events(0) if x['subject']['id'] == v['id']
              and x['type'] == 'verification.state_changed'
              and x['payload'].get('trigger') == 'generic_verifier']
    assert why.startswith(V.WITHHELD) and 'nothing deterministic' not in why
    assert node.calls == []
    # you accept it: the task succeeds, and nothing its workdir claimed is mergeable
    core.decide_verification(v['id'], 'accept')
    t = _task(core, mid)
    assert (t.state, t.integration_state) == ('SUCCEEDED', 'PENDING')
    for _ in range(3):
        assert core._verify.pass_once() == {'changed': False}     # waits, never a hot loop
    assert node.calls == [] and _t(core, mid, 'integration_state') == 'PENDING'


def test_A6_an_unknown_execution_keeps_its_git_and_loses_its_commands(core, monkeypatch):
    """G1: a legacy None execution's workdir is read as today; nothing of the
    mission is run, its criteria are yours, and its review gets no diff."""
    _repo, mid, t, e = _verifying(core)
    _isolate(core, mid, e.id, None)
    node = _node(core, monkeypatch, allow=_GIT)     # run_check and git_numstat fail the test
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    (v,) = _vs(core, mid, 'task')
    assert (v['verifier'], v['state']) == ('generic_human', 'AWAITING_HUMAN')
    assert v['revision'] and v['workspace'] == e.workdir and 'git_head' in node.calls
    core.decide_verification(v['id'], 'accept')
    pump(core, lambda: _vs(core, mid, 'mission'))
    assert _t(core, mid, 'integration_state') == 'MERGED'      # G1: its revision merges
    crit = _vs(core, mid, 'mission')
    assert crit and {(x['verifier'], x['state'], x['workspace']) for x in crit} == {
        ('generic_human', 'AWAITING_HUMAN', None)}
    seen = []
    monkeypatch.setattr(core._verify, 'calls', SimpleNamespace(
        run=lambda **ask: seen.append(ask) or SimpleNamespace(state='error')))
    core._verify._review(mid)
    assert 'withheld, not empty' in seen[0]['prompt']
    assert (seen[0]['no_tools'], seen[0]['workdir']) == (True, paths.fresh_call_dir)
    assert 'run_check' not in node.calls and 'git_numstat' not in node.calls


def test_A6_an_ordinary_review_still_reads_the_mission_diff(core, monkeypatch):
    _repo, mid = _mission(core, Rig(core), steps=[_write(FIX), {'emit': {'type': 'result',
                                                                         'summary': 'done'}}])
    pump(core, lambda: _state(core, mid) == 'REVIEWING')
    node = _node(core, monkeypatch, allow=_GIT + ('git_numstat',))
    seen = []
    monkeypatch.setattr(core._verify, 'calls', SimpleNamespace(
        run=lambda **ask: seen.append(ask) or SimpleNamespace(
            state='unavailable' if len(seen) == 1 else 'error')))
    core._verify._review(mid)
    assert node.calls == ['git_numstat'] and 'withheld' not in seen[0]['prompt']
    # T-081: the retry without `forbidden` (no independent resource) is the same
    # call, with no tools in a fresh directory of its own, never ARCHEUS_HOME
    first, retry = seen
    assert 'forbidden' in first and 'forbidden' not in retry
    for ask in seen:
        assert (ask['no_tools'], ask['workdir']) == (True, paths.fresh_call_dir)


def test_A6_an_ordinary_task_of_a_guarded_mission_keeps_its_git_and_loses_its_commands(
        core, monkeypatch):
    _repo, mid, t, e = _verifying(core)
    _another_execution(core, t, isolated=True, process_seq=1, state='ENDED_ERROR')
    node = _node(core, monkeypatch, allow=_GIT)
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    (v,) = _vs(core, mid, 'task')
    assert (v['verifier'], v['state']) == ('generic_human', 'AWAITING_HUMAN') and v['revision']
    assert 'git_head' in node.calls and 'run_check' not in node.calls


def test_A6_the_sink_refuses_a_code_verification_of_a_guarded_mission(core):
    _repo, mid, t, e = _verifying(core)
    _isolate(core, mid, e.id)
    n = len(core.events(0))
    with pytest.raises(V.Refused, match='withheld'):
        _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
            verifier='code', execution_id=e.id)
    assert not _vs(core, mid) and len(core.events(0)) == n


def test_A6_a_mission_guarded_between_the_read_and_the_start_runs_nothing(core, monkeypatch):
    _repo, mid, t, _e = _verifying(core)
    real_do, real_start = core._verify._do, V.start

    def racing(command, **kw):
        if command is real_start and kw['verifier'] == 'code':
            _another_execution(core, t, isolated=True, process_seq=1, state='ENDED_ERROR')
        return real_do(command, **kw)
    monkeypatch.setattr(core._verify, '_do', racing)
    node = _node(core, monkeypatch, allow=_GIT)
    assert core._verify.pass_once()['did'] == 'lost_race'
    assert not _vs(core, mid) and 'run_check' not in node.calls
    assert core._verify.pass_once()['did'] == 'verify_task'
    (v,) = _vs(core, mid, 'task')
    assert v['verifier'] == 'generic_human' and 'run_check' not in node.calls


def test_A6_a_guarded_rows_error_is_held_once_and_never_re_run(core, monkeypatch):
    mid, _t1, e, vid = _errored(core)
    _isolate(core, mid, e.id)
    before, seq = _get(core, entities.Verification, vid), core.events(0)[-1]['seq']
    node = _node(core, monkeypatch)
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    pump(core)                                      # quiescent: held once, nothing else
    after = _get(core, entities.Verification, vid)
    assert (after.state, after.errors, after.holds_mission) == ('ERROR', 1, True)
    assert _frozen(after) == _frozen(before) and after.revision == 'r1'
    assert _held(core, mid)['reason'] == V.WITHHELD
    changes = [x['payload'] for x in core.events(seq) if x['subject']['id'] == vid
               and x['type'] == 'verification.state_changed']
    assert not [p for p in changes if p['to'] in ('PENDING', 'RUNNING', 'AWAITING_HUMAN')]
    assert len([p for p in changes if p.get('holds_mission')]) == 1
    assert node.calls == []


def test_A6_the_retry_sink_refuses_a_guarded_row_before_writing(core):
    mid, _t1, e, vid = _errored(core)
    _isolate(core, mid, e.id)
    before, n = _get(core, entities.Verification, vid), len(core.events(0))
    with pytest.raises(V.Refused, match='withheld'):
        _do(core, V.retry, verification_id=vid)
    assert _get(core, entities.Verification, vid) == before and len(core.events(0)) == n
    assert _state(core, mid) == 'EXECUTING'


def test_A6_a_retry_runs_nothing_unless_the_sink_says_it_runs(core, monkeypatch):
    mid, _t1, _e, vid = _errored(core)               # ordinary: the planner retries it
    monkeypatch.setattr(V, 'retry', lambda tx, *, actor, verification_id: {
        'verification_id': verification_id, 'state': 'AWAITING_HUMAN'})

    def never(*a, **k):
        raise AssertionError('read the commands of a retry that does not run')
    monkeypatch.setattr(evidence, 'project_root', never)
    monkeypatch.setattr(evidence, 'commands', never)
    node = _node(core, monkeypatch)
    assert core._verify.pass_once()['did'] == 'retry'
    assert node.calls == []


def test_A6_a_mission_guarded_between_the_plan_and_the_retry_runs_nothing(core, monkeypatch):
    mid, _t1, e, vid = _errored(core)
    real_do, real_retry = core._verify._do, V.retry

    def racing(command, **kw):
        if command is real_retry:
            _isolate(core, mid, e.id)               # committed before the retry's transaction
        return real_do(command, **kw)
    monkeypatch.setattr(core._verify, '_do', racing)
    node = _node(core, monkeypatch)
    assert core._verify.pass_once()['did'] == 'lost_race'
    assert _get(core, entities.Verification, vid).state == 'ERROR' and node.calls == []
    assert core._verify.pass_once()['did'] == 'hold'
    assert node.calls == []


def test_A6_a_held_rows_lineage_can_never_be_accepted_or_merged(core, monkeypatch):
    mid, _t1, e, vid = _errored(core)
    _isolate(core, mid, e.id)
    node = _node(core, monkeypatch)
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    with pytest.raises(CoreClientError) as err:
        core.decide_verification(vid, 'accept')
    assert err.value.status == 409
    t = _task(core, mid)
    assert (t.state, t.integration_state) == ('VERIFYING', None)
    from archeus.core.application import errors
    with pytest.raises(errors.LOST_RACE):
        _do(core, V.begin_merge, task_id=t.id, revision='r1')
    assert node.calls == []
    _user(core, core._missions.cancel, mission_id=mid)     # H: the supported way out
    assert _state(core, mid) == 'CANCELLED'


@pytest.mark.parametrize('isolated', [True, False])
def test_A6_an_old_human_rows_revision_merges_only_if_its_execution_may_supply_it(
        core, monkeypatch, isolated):
    """A human row the pre-K5a path recorded with the workdir's HEAD: accepting
    it never makes a known-isolated execution's claim mergeable (A5)."""
    _repo, mid, t, e = _verifying(core)
    vid = _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
              verifier='generic_human', execution_id=e.id, revision='r1', workspace=e.workdir,
              criteria=[dict(x, index=i, result='unknown')
                        for i, x in enumerate(t.acceptance)])['verification_id']
    _isolate(core, mid, e.id, isolated)
    core.decide_verification(vid, 'accept')
    assert (_t(core, mid), _t(core, mid, 'integration_state')) == ('SUCCEEDED', 'PENDING')
    node = _node(core, monkeypatch, fake={
        'git_merge_base': lambda *a: 'b' * 40, 'mission_worktree': lambda *a: 'wt',
        'git_head': lambda *a: None, 'git_merge': lambda *a: ('merged', 'a' * 40),
        'remove_worktree': lambda *a: None})
    out = core._verify.pass_once()
    if isolated:
        assert out == {'changed': False} and node.calls == []
        assert _t(core, mid, 'integration_state') == 'PENDING'
    else:
        assert out['did'] == 'merge' and 'git_merge' in node.calls
        assert _t(core, mid, 'integration_state') == 'MERGED'


_FAKE_MERGE = {'git_merge_base': lambda *a: 'b' * 40, 'mission_worktree': lambda *a: 'wt',
               'git_head': lambda *a: None, 'git_merge': lambda *a: ('merged', 'a' * 40),
               'remove_worktree': lambda *a: None}


def _accepted(c, *, revision='r1'):
    """A task you accepted on a human row that recorded *revision*, waiting to merge."""
    _repo, mid, t, e = _verifying(c)
    vid = _do(c, V.start, missions=c._missions, subject=Ref('task', t.id),
              verifier='generic_human', execution_id=e.id, revision=revision,
              workspace=e.workdir, criteria=[dict(x, index=i, result='unknown')
                                             for i, x in enumerate(t.acceptance)])['verification_id']
    c.decide_verification(vid, 'accept')
    assert (_t(c, mid), _t(c, mid, 'integration_state')) == ('SUCCEEDED', 'PENDING')
    return mid, _task(c, mid), e, vid


def _mergeable(c, t):
    with c._core().read() as conn:
        return V.mergeable_revision(conn, t)


@pytest.mark.parametrize('isolated', [True, None, False])
def test_A6_a_merge_a_restart_left_running_never_takes_an_isolated_claim(
        core, monkeypatch, isolated):
    """A task that reached MERGING before K5a, its execution known-isolated
    since: the worker, the planner and the completion sink each refuse it before
    any node call. Legacy None and ordinary False merge as today (G1)."""
    mid, t, e, vid = _accepted(core)
    _do(core, V.begin_merge, task_id=t.id, revision='r1')
    _isolate(core, mid, e.id, isolated)
    assert _t(core, mid, 'integration_state') == 'MERGING'
    before, seen = _frozen(_get(core, entities.Verification, vid)), len(core.events(0))
    node = _node(core, monkeypatch, fake=_FAKE_MERGE)
    if isolated:
        assert _mergeable(core, t) is None
        assert core._verify.pass_once() == {'changed': False}
        with pytest.raises(V.Refused):
            core._verify._merge(t.id)
        with pytest.raises(V.Refused):
            _do(core, V.record_merge, missions=core._missions, task_id=t.id,
                outcome='merged', head='a' * 40)
        assert node.calls == [] and len(core.events(0)) == seen
        assert _t(core, mid, 'integration_state') == 'MERGING'
    else:
        assert _mergeable(core, t) == 'r1'
        assert core._verify.pass_once()['did'] == 'merge' and 'git_merge' in node.calls
        assert _t(core, mid, 'integration_state') == 'MERGED'
    assert _frozen(_get(core, entities.Verification, vid)) == before


def test_A6_an_isolated_latest_row_never_falls_back_to_an_older_revision(core, monkeypatch):
    """The latest PASSED row speaks for the task: when its execution is
    known-isolated nothing merges, not the revision an older ordinary row named,
    even once a later ordinary end is the verified execution."""
    _repo, mid, t, e = _verifying(core)

    def older(tx, actor):
        attempt = 1 + max(r.entity.attempt for r in tx.where(entities.Execution, task_id=t.id))
        x = tx.insert(entities.Execution(id=ids.new_id('execution'), task_id=t.id,
                                         mission_id=mid, plan_id=t.plan_id, attempt=attempt,
                                         isolated=False, process_seq=1, state='ENDED_ERROR'),
                      actor=actor).entity
        tx.insert(entities.Verification(id=ids.new_id('verification'), subject=Ref('task', t.id),
                                        verifier='code', plan_id=t.plan_id, execution_id=x.id,
                                        revision='r0', state='PASSED'), actor=actor)
    _forge(core, mid, older)
    vid = _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
              verifier='generic_human', execution_id=e.id, revision='r1', workspace=e.workdir,
              criteria=[dict(x, index=i, result='unknown')
                        for i, x in enumerate(t.acceptance)])['verification_id']
    _isolate(core, mid, e.id)
    core.decide_verification(vid, 'accept')
    t = _task(core, mid)
    _another_execution(core, t, isolated=False, process_seq=1, state='ENDED_OK')
    with core._core().read() as conn:
        assert V.verified_execution(conn, t).isolated is False
    assert t.integration_state == 'PENDING' and _mergeable(core, t) is None
    node = _node(core, monkeypatch, fake=_FAKE_MERGE)
    assert core._verify.pass_once() == {'changed': False}
    from archeus.core.application import errors
    for revision in ('r0', 'r1'):
        with pytest.raises(errors.LOST_RACE):
            _do(core, V.begin_merge, task_id=t.id, revision=revision)
    assert node.calls == [] and _t(core, mid, 'integration_state') == 'PENDING'


def test_A6_a_later_isolated_end_withdraws_an_accepted_revision(core, monkeypatch):
    """The row's own execution was ordinary, but the task's verified execution
    - its latest ENDED_OK - is known-isolated: that lineage merges nothing."""
    mid, t, _e, _vid = _accepted(core)
    _another_execution(core, t, isolated=True, process_seq=1, state='ENDED_OK')
    assert _mergeable(core, t) is None
    node = _node(core, monkeypatch, fake=_FAKE_MERGE)
    assert core._verify.pass_once() == {'changed': False} and node.calls == []
    assert _t(core, mid, 'integration_state') == 'PENDING'


def test_A6_a_guarded_criterion_in_error_is_superseded_by_a_fresh_row_for_you(core, monkeypatch):
    repo, mid = _mission(core, Rig(core), steps=[_write(FIX), {'emit': {'type': 'result',
                                                                        'summary': 'done'}}])
    pump(core, lambda: _state(core, mid) == 'VERIFYING')
    m = _get(core, entities.Mission, mid)
    wt = paths.mission_worktree_path(repo.project_id, mid)
    old = _do(core, V.start, missions=core._missions, subject=Ref('mission', mid),
              verifier='code', criterion=0, revision=m.integration_head,
              base_revision=m.integration_base, workspace=wt,
              criteria=[dict(m.success_criteria[0], index=0, result='unknown')])['verification_id']
    _do(core, V.record, missions=core._missions, verification_id=old,
        checks=[{'name': 'test', 'kind': 'command', 'result': 'error', 'detail': 'no runner'}])
    before = _get(core, entities.Verification, old)
    with core._core().read() as conn:
        e = V.verified_execution(conn, _task(core, mid))
    _isolate(core, mid, e.id)

    def never(*a, **k):
        raise AssertionError('a guarded criterion was retried')
    monkeypatch.setattr(core._verify, '_retry', never)
    node = _node(core, monkeypatch, allow=('git_head',))   # Core's own mission worktree head
    pump(core, lambda: len(_vs(core, mid, 'mission')) > 1)
    assert _get(core, entities.Verification, old) == before
    fresh = [x for x in _vs(core, mid, 'mission') if x['id'] != old]
    assert [x['criterion'] for x in fresh] == list(range(len(m.success_criteria)))
    assert {(x['verifier'], x['state'], x['revision'], x['workspace']) for x in fresh} == {
        ('generic_human', 'AWAITING_HUMAN', m.integration_head, None)}
    assert set(node.calls) <= {'git_head'}
    with pytest.raises(V.Refused, match='withheld'):
        _do(core, V.start, missions=core._missions, subject=Ref('mission', mid),
            verifier='code', criterion=0, revision=m.integration_head)


def test_A6_a_guarded_mission_with_nothing_integrated_never_falls_back_to_your_root(
        core, monkeypatch):
    _repo, mid = _mission(core, Rig(core), steps=[_write(FIX), {'emit': {'type': 'result',
                                                                         'summary': 'done'}}])
    pump(core, lambda: _state(core, mid) == 'VERIFYING')
    with core._core().read() as conn:
        e = V.verified_execution(conn, _task(core, mid))
    _isolate(core, mid, e.id)
    # nothing integrated: before the guard, the criteria ran in your project root
    _forge(core, mid, lambda tx, actor: tx.update(
        entities.Mission, mid, {'integration_base': None, 'integration_head': None},
        actor=actor))
    node = _node(core, monkeypatch)
    pump(core, lambda: _vs(core, mid, 'mission'))
    crit = _vs(core, mid, 'mission')
    assert {(x['verifier'], x['revision'], x['workspace']) for x in crit} == {
        ('generic_human', None, None)}
    assert node.calls == []


def test_A6_an_isolated_execution_without_a_project_never_reaches_git_or_a_command(
        core, monkeypatch):
    rig = Rig(core)
    rig.script_harness('t1', [_write(FIX), {'emit': {'type': 'result', 'summary': 'done'}}])
    mid = core.create_mission(title='Fix add', objective='Make add add')['id']
    pump(core, lambda: _t(core, mid) == 'VERIFYING' and not _vs(core, mid))
    with core._core().read() as conn:
        e = V.verified_execution(conn, _task(core, mid))
    assert e.branch is None
    _isolate(core, mid, e.id)
    node = _node(core, monkeypatch)
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    (v,) = _vs(core, mid, 'task')
    assert (v['verifier'], v['revision'], v['workspace']) == ('generic_human', None, None)
    core.decide_verification(v['id'], 'accept')
    assert (_t(core, mid), _t(core, mid, 'integration_state')) == ('SUCCEEDED', None)
    pump(core, lambda: _vs(core, mid, 'mission'))
    assert {(x['verifier'], x['workspace']) for x in _vs(core, mid, 'mission')} == {
        ('generic_human', None)}
    assert node.calls == []


# ── A6-4: confined routing and sinks (T-054 C-1013 §4), with a fake confined runner ──

SEED_REV, IMP = 'a' * 40, 'c' * 40


class _Confined:
    """A fake `run_confined_check`: records each attempt and answers with
    *results* in turn, calling *record* before it returns, as the real one does."""

    def __init__(self, *results):
        self.results, self.seen, self.recorded = list(results), [], []

    def __call__(self, vid, attempt, argv, *, toolchain, timeout, record, project_id,
                 revision, workdirs):
        self.seen.append((vid, attempt, list(argv), list(toolchain)))
        self.inputs = getattr(self, 'inputs', []) + [(project_id, revision, list(workdirs))]
        r = dict({'exit_code': 0, 'duration_ms': 1, 'error': None, 'output': b'ok',
                  'output_bytes': 2, 'truncated': False,
                  'confinement': {'isolated': True, 'job': 'fake'}}, **self.results.pop(0))
        record(r)
        self.recorded.append(vid)
        return r


@pytest.fixture
def toolchain(tmp_path):
    d = tmp_path / 'stage'
    d.mkdir()
    prog = d / ('tool.exe' if os.name == 'nt' else 'tool')
    prog.write_bytes(b'')
    prog.chmod(0o755)
    return str(d), str(prog)


def _imported(c, monkeypatch, toolchain, cmds=('tool --check',), enabled=True):
    """A verifying task whose execution was isolated, seeded and imported."""
    _repo, mid, t, e = _verifying(c)
    _forge(c, mid, lambda tx, actor: tx.update(entities.Execution, e.id, {
        'isolated': True, 'seed_revision': SEED_REV, 'import_revision': IMP}, actor=actor))
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', enabled)
    monkeypatch.setattr(evidence, 'commands', lambda conn, project_id, root: (tuple(cmds), ()))
    monkeypatch.setattr(c._verify, 'toolchain', lambda: [toolchain[0]])
    return mid, t, _get(c, entities.Execution, e.id)


def _row(c, mid):
    (v,) = _vs(c, mid, 'task')
    return _get(c, entities.Verification, v['id'])


def test_A6_4_a_guarded_task_with_its_import_runs_confined_and_its_pass_is_marked(
        core, monkeypatch, toolchain):
    mid, t, e = _imported(core, monkeypatch, toolchain)
    fake = _Confined({})
    node = _node(core, monkeypatch, fake={'run_confined_check': fake})
    pump(core, lambda: _vs(core, mid, 'task') and _row(core, mid).state == 'PASSED')
    v = _row(core, mid)
    assert (v.verifier, v.verifier_version, v.revision) == ('code', V.CONFINED_VERIFIER, IMP)
    assert (v.workspace, v.base_revision) == (None, None)
    (check,) = v.checks
    assert check['result'] == 'pass' and check['confinement'] == {'isolated': True,
                                                                  'job': 'fake'}
    prog = os.path.normcase(toolchain[1])
    assert [os.path.normcase(check['argv'][0])] + check['argv'][1:] == [prog, '--check']
    ((vid, n, argv, chain),) = fake.seen
    assert (vid, n, os.path.normcase(argv[0]), argv[1:], chain) == (
        v.id, 0, prog, ['--check'], [toolchain[0]])
    assert node.calls == ['run_confined_check']        # no Git, no unconfined run
    ((project_id, revision, workdirs),) = fake.inputs
    with core._core().read() as r:
        m = rows.get(r, entities.Mission, mid).entity
        recorded = [x.entity.workdir for x in rows.where(r, entities.Execution)
                    if x.entity.workdir]
    assert (project_id, revision, workdirs) == (m.project_id, IMP, recorded)


def test_A6_4_with_the_switch_off_a_guarded_task_still_goes_to_you(core, monkeypatch,
                                                                   toolchain):
    mid, t, e = _imported(core, monkeypatch, toolchain, enabled=False)
    node = _node(core, monkeypatch)
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    v = _row(core, mid)
    assert (v.verifier, v.verifier_version) == ('generic_human', V.VERIFIER_VERSION)
    assert node.calls == []
    with pytest.raises(V.Refused, match='withheld'):
        _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
            verifier='code', execution_id=e.id, revision=IMP)


@pytest.mark.parametrize('kw', [{'revision': 'd' * 40}, {'revision': None},
                                {'revision': IMP, 'workspace': 'w'}])
def test_A6_4_the_sink_refuses_a_guarded_code_row_not_over_its_recorded_import(
        core, monkeypatch, toolchain, kw):
    mid, t, e = _imported(core, monkeypatch, toolchain)
    n = len(core.events(0))
    with pytest.raises(V.Refused, match='withheld'):
        _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
            verifier='code', execution_id=e.id, **kw)
    assert not _vs(core, mid) and len(core.events(0)) == n


def test_A6_4_a_caller_cannot_name_the_verifier_version(core, monkeypatch, toolchain):
    mid, t, e = _imported(core, monkeypatch, toolchain)
    n = len(core.events(0))
    for version in (V.CONFINED_VERIFIER, V.VERIFIER_VERSION):
        with pytest.raises(TypeError, match='verifier_version'):
            _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
                verifier='code', execution_id=e.id, revision=IMP, verifier_version=version)
    assert not _vs(core, mid) and len(core.events(0)) == n


def test_A6_4_an_unguarded_code_row_is_never_marked_confined(core, monkeypatch):
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    _repo, mid, t, e = _verifying(core)
    out = _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
              verifier='code', execution_id=e.id, revision='r1', workspace=e.workdir)
    assert out['verifier_version'] == V.VERIFIER_VERSION
    assert _get(core, entities.Verification, out['verification_id']).verifier_version == \
        V.VERIFIER_VERSION


def test_A6_4_run_commands_refuses_a_confined_row_before_any_node_call(core, monkeypatch):
    node = _Node(None)
    with pytest.raises(ValueError, match='only confined'):
        evidence.run_commands(node, 'w', [('test', 'tool')], verification_id='v',
                              timeout_s=1, verifier_version=V.CONFINED_VERIFIER)
    assert node.calls == []


@pytest.mark.parametrize('cmds', [(), ('tool --check', 'tool --other'), ('python -c 1',),
                                  (os.path.abspath(__file__).replace(os.sep, '/'),)])
def test_A6_4_a_check_that_cannot_run_confined_goes_to_you_before_any_row_starts(
        core, monkeypatch, toolchain, cmds):
    mid, t, e = _imported(core, monkeypatch, toolchain, cmds=cmds)
    node = _node(core, monkeypatch)
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    v = _row(core, mid)
    assert (v.verifier, v.state) == ('generic_human', 'AWAITING_HUMAN') and node.calls == []


def test_A6_4_a_guarded_task_without_an_import_goes_to_you(core, monkeypatch, toolchain):
    mid, t, e = _imported(core, monkeypatch, toolchain)
    _forge(core, mid, lambda tx, actor: tx.update(entities.Execution, e.id,
                                                  {'import_revision': None}, actor=actor))
    node = _node(core, monkeypatch)
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    assert _row(core, mid).verifier == 'generic_human' and node.calls == []


def test_A6_4_a_legacy_frozen_row_is_still_held_with_the_switch_on(core, monkeypatch,
                                                                   toolchain):
    # as an older Core recorded it, and over exactly what the import now says
    _repo, mid, t, e = _verifying(core)
    vid = _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
              verifier='code', execution_id=e.id, revision=IMP,
              criteria=[dict(x, index=i, result='unknown')
                        for i, x in enumerate(t.acceptance)])['verification_id']
    _do(core, V.record, missions=core._missions, verification_id=vid,
        checks=[{'name': 'test', 'kind': 'command', 'result': 'error', 'detail': 'no runner'}])
    _forge(core, mid, lambda tx, actor: tx.update(entities.Execution, e.id, {
        'isolated': True, 'seed_revision': SEED_REV, 'import_revision': IMP}, actor=actor))
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    monkeypatch.setattr(core._verify, 'toolchain', lambda: [toolchain[0]])
    before = _get(core, entities.Verification, vid)
    node = _node(core, monkeypatch)
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    pump(core)
    after = _get(core, entities.Verification, vid)
    assert (after.state, after.holds_mission, after.verifier_version) == (
        'ERROR', True, V.VERIFIER_VERSION)
    assert _frozen(after) == _frozen(before) and node.calls == []
    with pytest.raises(V.Refused, match='withheld'):
        _do(core, V.retry, verification_id=vid)


def test_A6_4_a_retry_is_a_new_attempt_under_a_new_principal(core, monkeypatch, toolchain):
    mid, t, e = _imported(core, monkeypatch, toolchain)
    fake = _Confined({'exit_code': None, 'error': 'quiescence_unknown'}, {})
    _node(core, monkeypatch, fake={'run_confined_check': fake})
    pump(core, lambda: _vs(core, mid, 'task') and _row(core, mid).state == 'PASSED')
    v = _row(core, mid)
    assert [(vid, n) for vid, n, _a, _t in fake.seen] == [(v.id, 0), (v.id, 1)]
    assert (v.errors, v.verifier_version, v.revision) == (1, V.CONFINED_VERIFIER, IMP)


def test_A6_4_a_confined_row_that_can_no_longer_run_confined_is_held_not_run(
        core, monkeypatch, toolchain):
    mid, t, e = _imported(core, monkeypatch, toolchain)
    fake = _Confined({'exit_code': None, 'error': 'timed out after 1s'})
    node = _node(core, monkeypatch, fake={'run_confined_check': fake})
    pump(core, lambda: _vs(core, mid, 'task') and _row(core, mid).state == 'ERROR')
    vid = _row(core, mid).id
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', False)
    with pytest.raises(V.Refused, match='withheld'):
        _do(core, V.retry, verification_id=vid)
    pump(core, lambda: _state(core, mid) == 'BLOCKED')
    v = _row(core, mid)
    assert (v.state, v.holds_mission, v.errors) == ('ERROR', True, 1)
    assert node.calls == ['run_confined_check'] and len(fake.seen) == 1


def test_A6_4_a_verdict_the_row_no_longer_awaits_lets_the_principal_go(core, monkeypatch,
                                                                       toolchain):
    mid, t, e = _imported(core, monkeypatch, toolchain)
    fake = _Confined({})
    _node(core, monkeypatch, fake={'run_confined_check': fake})

    def gone(tx, **kw):
        raise V.Refused('verification is CANCELLED, not RUNNING')
    monkeypatch.setattr(V, 'record', gone)
    assert core._verify.pass_once()['did'] == 'verify_task'
    assert fake.recorded == [_row(core, mid).id]        # record returned: teardown proceeds
    assert _row(core, mid).state == 'RUNNING'


# ── worktree layout (target-architecture §5.1, amendment 2026-10-14) ────────

@pytest.mark.parametrize('before', [(), ('t1',), ('t1', '_mission')],
                         ids=['new', 'task-old', 'both-old'])
def test_worktrees_of_the_earlier_layout_are_used_where_they_are(core, before):
    """A mission begun before the short layout: the task's branch is checked out
    at its old path (a new attempt, or a restart, finds it there) and maybe the
    mission branch too; it verifies, merges through whichever `_mission` exists
    and reads that worktree's head when it verifies the mission."""
    repo, mid = _mission(core, Rig(core), steps=[_write(FIX), {'emit': {
        'type': 'result', 'summary': 'done'}}])
    home = os.environ['ARCHEUS_HOME']
    old = {k: os.path.join(home, 'worktrees', repo.project_id, mid, k) for k in ('t1', '_mission')}
    new = {k: os.path.join(home, 'worktrees', mid[len('msn_'):], k) for k in old}
    if 't1' in before:
        LocalNode.add_worktree(repo.path, old['t1'], 'archeus/%s.t1' % mid, base='HEAD')
    if '_mission' in before:
        LocalNode.mission_worktree(repo.path, old['_mission'], 'archeus/%s' % mid, 'HEAD')
    pump(core, lambda: _state(core, mid) == 'COMPLETED')
    used = {k: (old if k in before else new)[k] for k in old}
    with core._core().read() as conn:
        (e,) = [r.entity for r in rows.where(conn, entities.Execution)]
    assert e.workdir == used['t1']
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=used['_mission'],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert _get(core, entities.Mission, mid).integration_head == head
    assert not os.path.exists((new if '_mission' in before else old)['_mission'])
    assert _t(core, mid, 'integration_state') == 'MERGED'


def test_A6_4_a_tree_core_could_not_export_is_an_error_never_a_pass(core, monkeypatch,
                                                                    toolchain):
    mid, t, e = _imported(core, monkeypatch, toolchain)
    fake = _Confined({'error': 'prepare_failed: synthetic export failure', 'exit_code': None,
                      'output': b'', 'output_bytes': 0})
    _node(core, monkeypatch, fake={'run_confined_check': fake})
    pump(core, lambda: _vs(core, mid, 'task') and _row(core, mid).state != 'RUNNING')
    v = _row(core, mid)
    assert v.state != 'PASSED' and v.verifier_version == V.CONFINED_VERIFIER
    (check,) = v.checks
    assert check['result'] == 'error' and 'synthetic export failure' in check['detail']


@pytest.mark.parametrize('verifier', ['ci', 'lint', 'review'])
def test_A6_4_only_the_code_verifier_runs_confined(core, monkeypatch, toolchain, verifier):
    mid, t, e = _imported(core, monkeypatch, toolchain)
    with core._core().read() as r:
        before = len(list(rows.where(r, entities.Verification)))
    with pytest.raises(V.Refused, match='withheld'):
        _do(core, V.start, missions=core._missions, subject=Ref('task', t.id),
            verifier=verifier, execution_id=e.id, revision=IMP)
    with core._core().read() as r:
        assert len(list(rows.where(r, entities.Verification))) == before
