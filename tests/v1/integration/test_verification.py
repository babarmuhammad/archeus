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

import pytest

from archeus.core.application import commands, verification as V
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.verification import evidence
from archeus.infra.db import rows
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
    wt = os.path.join(os.environ['ARCHEUS_HOME'], 'worktrees', repo.project_id, mid, '_mission')
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
    wt = os.path.join(os.environ['ARCHEUS_HOME'], 'worktrees', repo.project_id, mid, '_mission')
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
