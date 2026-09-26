"""P3.5: the walking skeleton as one real in-process vertical slice.

intent -> Mission -> Plan -> Task -> Policy -> resource seam -> fake harness
subprocess -> Execution -> result -> Verification -> Review -> mission state,
every step a writer command over the P3 lifecycle, every mutation an event in
the P2 outbox, all of it on a real archeus.db that is reopened to prove it.
The ports are the deterministic P3.5 stubs; the process is real.
"""

import json
import os
import subprocess
import sys
import threading
import time

import pytest

from archeus.core import engine, ports
from archeus.core.application import commands, lifecycle, queries, work
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.harnesses.fake import FakeHarness
from archeus.harnesses.registry import AdapterRegistry
from archeus.infra.db import Database, rows, writer
from archeus.infra.paths import ExecPaths

from .conftest import ROOT

AUTO = {'text': 'the result passes its automatic check', 'check': 'automatic'}
HUMAN = {'text': 'the user likes it', 'check': 'human'}
ACCEPT = [{'text': 'it is done', 'check': 'automatic'}]


class SpyPolicy(ports.FixedPolicy):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.asked = []

    def evaluate(self, action, ctx):
        self.asked.append((action.action_class, action.target, ctx.get('task_id')))
        return super().evaluate(action, ctx)


class Core:
    """One Core on the test's ARCHEUS_HOME: a database, a system principal
    for the engine, a user device, and the engine on scriptable stubs."""

    def __init__(self, policy=None, router='fake', scenarios=None):
        self.db = Database.open()
        self.system = Ref('system', self.db.writer.execute(
            commands.register_principal, {'kind': 'system', 'scopes': ('system',)})['id'])
        self.user = Ref('user_device', self.db.writer.execute(
            commands.register_principal, {'kind': 'user_device',
                                          'scopes': ('observe', 'control', 'approve')})['id'])
        self.policy = policy or SpyPolicy()
        self.missions = commands.Missions(policy=self.policy)
        self.work = work.Work(missions=self.missions,
                              router=ports.FixedCandidateRouter(router))
        self.brain = ports.FixedPlanBrain(engine.SKELETON_PLAN)
        self.verifier, self.reviewer = ports.ScriptedVerifier(), ports.ScriptedReview()
        self.scenarios = dict(scenarios or {})
        self.engine = self.build_engine()

    def build_engine(self):
        registry = AdapterRegistry(self.policy)
        registry.register(FakeHarness())
        return engine.Engine(self.db, actor=self.system, work=self.work, brain=self.brain,
                             registry=registry, verifier=self.verifier,
                             reviewer=self.reviewer, scenarios=self.scenarios, poll=0.01)

    def mission(self, criteria=(AUTO,), key=None, max_replans=2):
        return self.db.writer.execute(commands.create_mission, {
            'actor': self.user, 'title': 'Skeleton', 'objective': 'prove the slice',
            'success_criteria': list(criteria), 'max_replans': max_replans},
            idempotency_key=key)['id']

    def do(self, command, key=None, **kw):
        return self.db.writer.execute(command, dict(kw, actor=kw.pop('actor', self.user)),
                                      idempotency_key=key)

    def until(self, mid, pred, limit=100):
        """Step the engine until pred(mission row) holds (or fail)."""
        for _ in range(limit):
            if pred(self.row(entities.Mission, mid).entity):
                return
            if not self.engine.step(mid)['changed']:
                break
        assert pred(self.row(entities.Mission, mid).entity), self.row(entities.Mission, mid)

    def row(self, cls, eid):
        with self.db.read() as r:
            return rows.get(r, cls, eid)

    def all(self, cls, **eq):
        with self.db.read() as r:
            return [x.entity for x in rows.where(r, cls, **eq)]

    def events(self):
        with self.db.read() as r:
            return queries.events(r)

    def close(self):
        self.db.close()


@pytest.fixture
def core(archeus_home):
    c = Core()
    yield c
    c.close()


def mission_path(events, mid):
    return [e['payload']['to'] for e in events
            if e['type'] == 'mission.state_changed' and e['subject']['id'] == mid]


def of(events, type_):
    return [e for e in events if e['type'] == type_]


# ── happy path ──

def test_a_mission_travels_the_whole_slice_to_completed(core, archeus_home):
    mid = core.mission()
    out = core.engine.run(mid)
    assert (out['state'], out['stop']) == ('COMPLETED', 'completed')

    (plan,) = core.all(entities.Plan, mission_id=mid)
    (task,) = core.all(entities.Task, plan_id=plan.id)
    (exe,) = core.all(entities.Execution, task_id=task.id)
    assert (plan.plan_version, plan.estimated_cost) == (1, 'low')
    assert task.state == 'SUCCEEDED'
    assert (exe.state, exe.attempt, exe.harness_id, exe.exit_reason, exe.exit_code) == (
        'ENDED_OK', 1, 'fake', 'ok', 0)
    assert exe.pid and exe.create_time is not None and exe.summary == 'done'
    verifications = core.all(entities.Verification, plan_id=plan.id)
    assert [(v.subject.kind, v.criterion, v.state) for v in verifications] == [
        ('task', None, 'PASSED'), ('mission', 0, 'PASSED')]
    (review,) = core.all(entities.Review, plan_id=plan.id)
    assert (review.state, review.verdict) == ('ACCEPTED', 'accept')

    # the fake agent really ran: it read the prompt as stdin, saw its execution id
    paths = ExecPaths(exe.id)
    stream = [json.loads(ln) for ln in open(paths.stream, encoding='utf-8')]
    assert stream[0]['type'] == 'started' and stream[0]['execution_id'] == exe.id
    assert stream[0]['stdin_bytes'] > 0 and os.path.exists(paths.ended)

    # policy was asked through its port, for the plan gate and for the dispatch
    assert ('write_repo', 'task:work', None) in core.policy.asked
    assert ('write_repo', 'task:work', task.id) in core.policy.asked
    assert core.brain.calls == [('plan.v1', 'prove the slice')]

    events = core.events()
    assert mission_path(events, mid) == [
        'UNDERSTANDING', 'CONTEXT_GATHERING', 'REASONING', 'PLANNING', 'APPROVED',
        'EXECUTING', 'VERIFYING', 'REVIEWING', 'COMPLETED']
    types = [e['type'] for e in events]
    for t in ('mission.created', 'plan.created', 'task.created', 'task.state_changed',
              'execution.intent', 'execution.started', 'execution.state_changed',
              'execution.ended', 'verification.created', 'verification.state_changed',
              'review.requested', 'review.state_changed'):
        assert t in types, t
    started = of(events, 'execution.started')[0]['payload']
    assert (started['pid'], started['create_time']) == (exe.pid, exe.create_time)


def test_the_whole_slice_survives_reopening_the_database(core):
    mid = core.mission()
    core.engine.run(mid)
    before = core.events()
    state = {cls.__name__: [(e.id, e.state) for e in core.all(cls)]
             for cls in (entities.Mission, entities.Plan, entities.Task, entities.Execution,
                         entities.Verification, entities.Review)}
    core.close()
    core.db = Database.open()
    assert core.events() == before
    assert state == {cls.__name__: [(e.id, e.state) for e in core.all(cls)]
                     for cls in (entities.Mission, entities.Plan, entities.Task,
                                 entities.Execution, entities.Verification, entities.Review)}


def test_events_follow_the_outbox_order_and_every_move_chains(core):
    """Seqs strictly increase, and each subject's state_changed events form one
    chain: every `from` is the previous `to` (nothing moved behind the log)."""
    core.engine.run(core.mission())
    events = core.events()
    seqs = [e['seq'] for e in events]
    assert seqs == sorted(set(seqs))
    last = {}
    for e in events:
        if e['type'].endswith('.state_changed'):
            sid = e['subject']['id']
            if sid in last:
                assert e['payload']['from'] == last[sid], e
            last[sid] = e['payload']['to']
            assert e['actor']['kind'] in ('system', 'user_device') and e['payload']['reason']


def test_completed_is_reached_only_from_reviewing_after_verified(core):
    core.engine.run(core.mission())
    events = core.events()
    done = [e for e in of(events, 'mission.state_changed') if e['payload']['to'] == 'COMPLETED']
    assert [(e['payload']['from'], e['payload']['trigger']) for e in done] == [
        ('REVIEWING', 'accepted')]
    verified = [e for e in of(events, 'mission.state_changed')
                if e['payload']['trigger'] == 'verified']
    assert verified and verified[0]['payload']['guard']['name'] == 'verified'
    assert verified[0]['seq'] < done[0]['seq']


def test_every_mission_move_goes_through_missions_fire():
    """Structural: outside `commands.Missions._fire` nothing moves a Mission —
    no `lifecycle.fire(..., entities.Mission, ...)` and no raw `Tx.transition` of
    one — so every mission transition is legality -> guard -> proof -> P2 AND
    records `held_from` / `decided_plan_version` on the way."""
    import ast
    found = []
    for d, _s, files in os.walk(os.path.join(ROOT, 'archeus')):
        for f in files:
            if not f.endswith('.py'):
                continue
            path = os.path.join(d, f)
            for node in ast.walk(ast.parse(open(path, encoding='utf-8').read())):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ('fire', '_fire', 'transition')
                        and any((isinstance(a, ast.Attribute) and a.attr == 'Mission')
                                or (isinstance(a, ast.Name) and a.id == 'Mission')
                                for a in node.args)):
                    found.append(os.path.relpath(path, ROOT).replace(os.sep, '/'))
    assert found == ['archeus/core/application/commands.py'], found


def test_review_and_verification_cannot_bypass_the_lifecycle(core):
    mid = core.mission()
    core.until(mid, lambda m: m.state == 'EXECUTING')
    head = core.events()[-1]['seq']
    for verdict in ('accept', 'reject'):
        with pytest.raises(lifecycle.IllegalTrigger):
            core.do(core.work.record_review, mission_id=mid, verdict=verdict, reviewer='me')
    with pytest.raises(lifecycle.IllegalTrigger):
        core.do(core.work.verify_mission, mission_id=mid,
                verdicts=[{'criterion': 0, 'verdict': 'PASSED', 'verifier': 'code'}])
    with pytest.raises(lifecycle.IllegalTrigger):
        core.do(core.missions.accept, mission_id=mid)
    assert core.row(entities.Mission, mid).entity.state == 'EXECUTING'
    assert core.events()[-1]['seq'] == head
    assert core.all(entities.Review) == [] and core.all(entities.Verification) == []


def test_a_paused_mission_dispatches_nothing(core):
    mid = core.mission()
    core.until(mid, lambda m: [t for t in core.all(entities.Task) if t.state == 'READY'])
    core.do(core.missions.pause, mission_id=mid)
    (task,) = core.all(entities.Task)
    with pytest.raises(lifecycle.IllegalTrigger, match='not EXECUTING'):
        core.do(core.work.dispatch_task, actor=core.system, task_id=task.id)
    out = core.engine.run(mid)
    assert (out['state'], out['stop']) == ('PAUSED', 'paused')
    assert core.all(entities.Execution) == []
    core.do(core.missions.resume, mission_id=mid)          # held from EXECUTING
    assert core.engine.run(mid)['state'] == 'COMPLETED'


# ── policy ──

def test_ask_stops_at_approval_required_and_nothing_runs(archeus_home):
    core = Core(policy=SpyPolicy('ASK'))
    try:
        mid = core.mission()
        out = core.engine.run(mid)
        assert (out['state'], out['stop']) == ('APPROVAL_REQUIRED', 'approval_required')
        assert core.all(entities.Execution) == []
        assert [t.state for t in core.all(entities.Task)] == ['PENDING']
        assert not [e for e in core.events() if e['type'].startswith('execution.')]
        # a human approves the plan: ASK was the plan gate's question, now answered
        core.do(core.missions.fire, mission_id=mid, trigger='approve', reason='looks fine')
        assert core.engine.run(mid)['state'] == 'COMPLETED'
    finally:
        core.close()


def test_deny_is_refused_without_an_approval_request_or_any_write(archeus_home):
    """DENY is not ASK: no APPROVAL_REQUIRED, no plan, task or execution row, no
    event, and the mission is exactly where it was (same state, same version)."""
    core = Core(policy=SpyPolicy(by_class={'write_repo': 'DENY'}))
    try:
        mid = core.mission()
        core.until(mid, lambda m: m.state == 'REASONING')
        before, head = core.row(entities.Mission, mid), core.events()[-1]['seq']
        out = core.engine.run(mid)
        assert (out['state'], out['stop'], out['changed']) == ('REASONING', 'policy_denied',
                                                               False)
        assert 'policy denies write_repo on task work' in out['denied']
        after = core.row(entities.Mission, mid)
        assert (after.entity.state, after.version) == (before.entity.state, before.version)
        assert core.events()[-1]['seq'] == head
        for cls in (entities.Plan, entities.Task, entities.Execution):
            assert core.all(cls) == []
        assert 'APPROVAL_REQUIRED' not in mission_path(core.events(), mid)
        assert not of(core.events(), 'approval.requested')
        with pytest.raises(lifecycle.IllegalTrigger):          # nothing to approve
            core.do(core.missions.fire, mission_id=mid, trigger='approve', reason='override')
        with pytest.raises(work.PolicyDenied):                 # the command itself refuses
            core.do(core.work.propose_plan, actor=core.system, mission_id=mid,
                    plan=engine.SKELETON_PLAN)
        assert core.events()[-1]['seq'] == head
    finally:
        core.close()


def test_a_human_approval_does_not_override_a_later_deny(archeus_home):
    """ASK -> a human approves -> the policy now DENIES: nothing runs. Dispatch
    refuses and writes nothing; in EXECUTING the existing `unrecoverable` edge
    (policy DENY on a required action) is what ends the mission."""
    core = Core(policy=SpyPolicy('ASK'))
    try:
        mid = core.mission()
        assert core.engine.run(mid)['state'] == 'APPROVAL_REQUIRED'
        core.do(core.missions.fire, mission_id=mid, trigger='approve', reason='ship it')
        core.policy.decision = 'DENY'
        core.do(core.missions.fire, mission_id=mid, trigger='dispatch', reason='go')
        core.do(core.work.ready_tasks, mission_id=mid)
        (task,) = core.all(entities.Task)
        head = core.events()[-1]['seq']
        with pytest.raises(work.PolicyDenied) as denied:        # the protected action
            core.do(core.work.dispatch_task, task_id=task.id)
        assert denied.value.decision.decision == 'DENY'
        assert core.events()[-1]['seq'] == head                 # wrote nothing
        assert core.row(entities.Task, task.id).entity.state == 'READY'
        out = core.engine.run(mid)
        assert (out['state'], out['stop']) == ('FAILED', 'failed')
        failed = of(core.events(), 'mission.state_changed')[-1]['payload']
        assert failed['trigger'] == 'unrecoverable'
        assert failed['guard']['reason'] == 'policy denies write_repo on task work'
        assert core.all(entities.Execution) == []
    finally:
        core.close()


def test_a_plan_over_the_cost_ceiling_needs_approval(core):
    big = dict(engine.SKELETON_PLAN['tasks'][0], min_model_tier='large', estimate=5)
    core.brain.plan = dict(engine.SKELETON_PLAN, tasks=[      # Core's band: 40 -> high (D9)
        big, dict(big, key='more', title='Do more', depends_on=['work'])])
    out = core.engine.run(core.mission())
    assert out['state'] == 'APPROVAL_REQUIRED' and core.all(entities.Execution) == []


def test_no_eligible_resource_blocks_the_task_without_an_execution(archeus_home):
    core = Core(router=None)
    try:
        out = core.engine.run(core.mission())
        assert (out['state'], out['stop']) == ('EXECUTING', 'task_blocked')
        assert [t.state for t in core.all(entities.Task)] == ['BLOCKED']
        assert core.all(entities.Execution) == []
    finally:
        core.close()


# ── failure paths ──

@pytest.mark.parametrize('max_replans', [0, 1, 2])
def test_max_replans_counts_replans_after_the_initial_plan(archeus_home, max_replans):
    """Every plan fails its task twice (exit 3). The initial plan plus exactly
    `max_replans` replans run; the next replan is refused -> BLOCKED, before the
    brain is asked and without recording a plan."""
    core = Core(scenarios={'work': [{'exit': 3}]})
    try:
        mid = core.mission(max_replans=max_replans)
        out = core.engine.run(mid)
        assert (out['state'], out['stop']) == ('BLOCKED', 'blocked')
        plans = max_replans + 1
        assert [p.plan_version for p in core.all(entities.Plan)] == list(range(1, plans + 1))
        assert len(core.brain.calls) == plans
        assert [(e.attempt, e.state, e.exit_code) for e in core.all(entities.Execution)] == [
            (1, 'ENDED_ERROR', 3), (2, 'ENDED_ERROR', 3)] * plans
        assert [(t.state, t.failure_class) for t in core.all(entities.Task)] == [
            ('FAILED', 'execution')] * plans
        moves = of(core.events(), 'mission.state_changed')
        assert [e['payload']['trigger'] for e in moves].count('task_failed_retryable') == plans
        last = moves[-1]['payload']
        assert (last['from'], last['trigger']) == ('REPLANNING', 'replan_budget_exhausted')
        assert last['guard']['reason'] == '%d of %d replans used' % (max_replans, max_replans)
        path = mission_path(core.events(), mid)
        assert 'VERIFYING' not in path and 'COMPLETED' not in path
        assert core.all(entities.Verification) == []
    finally:
        core.close()


def test_propose_plan_itself_refuses_a_replan_over_budget(archeus_home):
    """The command enforces the budget, not only the engine: over budget it
    records no plan and the mission goes BLOCKED."""
    core = Core(scenarios={'work': [{'exit': 3}]})
    try:
        mid = core.mission(max_replans=0)
        core.until(mid, lambda m: m.state == 'REPLANNING')
        out = core.do(core.work.propose_plan, actor=core.system, mission_id=mid,
                      plan=engine.SKELETON_PLAN)
        assert out['plan_id'] is None and out['mission']['state'] == 'BLOCKED'
        assert [p.plan_version for p in core.all(entities.Plan)] == [1]
    finally:
        core.close()


def test_a_failed_task_check_retries_with_a_new_execution_then_fails(core):
    mid = core.mission()
    core.until(mid, lambda m: [t for t in core.all(entities.Task) if t.state == 'VERIFYING'])
    (task,) = core.all(entities.Task)
    core.verifier.failing.add(task.id)
    core.until(mid, lambda m: m.state != 'EXECUTING')
    assert core.row(entities.Task, task.id).entity.failure_class == 'verification'
    assert [(v.subject.id, v.state) for v in core.all(entities.Verification)] == [
        (task.id, 'FAILED')] * 2
    assert [e.attempt for e in core.all(entities.Execution, task_id=task.id)] == [1, 2]
    assert core.row(entities.Mission, mid).entity.state == 'REPLANNING'


def test_a_failed_mission_verification_prevents_completion(core):
    mid = core.mission()
    core.verifier.failing.add(mid)
    out = core.engine.run(mid)
    assert (out['state'], out['stop']) == ('BLOCKED', 'blocked')
    path = mission_path(core.events(), mid)
    assert 'REVIEWING' not in path and 'COMPLETED' not in path
    assert path.count('VERIFYING') == 3          # the initial plan and two replans
    mine = [v for v in core.all(entities.Verification) if v.subject.kind == 'mission']
    assert [v.state for v in mine] == ['FAILED'] * 3
    assert len({v.plan_id for v in mine}) == 3


def test_an_open_human_criterion_blocks_instead_of_completing(core):
    mid = core.mission(criteria=(AUTO, HUMAN))
    out = core.engine.run(mid)
    assert (out['state'], out['stop']) == ('BLOCKED', 'blocked')
    last = of(core.events(), 'mission.state_changed')[-1]['payload']
    assert last['trigger'] == 'awaiting_human_acceptance'


def test_a_mission_without_criteria_cannot_be_verified(core):
    """No criterion from the caller and none from the plan: `verified` refuses
    and the engine stops in VERIFYING instead of passing vacuously."""
    core.brain.plan = dict(engine.SKELETON_PLAN, success_criteria=[])
    mid = core.mission(criteria=())
    out = core.engine.run(mid)
    assert (out['state'], out['stop']) == ('VERIFYING', 'unverifiable')


def test_a_plan_without_criteria_gets_the_brains_marked_inferred(core):
    mid = core.mission(criteria=())
    assert core.engine.run(mid)['state'] == 'COMPLETED'
    assert core.row(entities.Mission, mid).entity.success_criteria == (
        dict(AUTO, origin='inferred'),)


def test_a_verification_counts_only_for_the_plan_it_ran_under(core):
    """Plan 1 is verified and then sent back by review; under plan 2 its
    PASSED verification must not let the mission through `verified`."""
    mid = core.mission()
    core.reviewer.verdicts[mid] = 'changes_requested'
    core.until(mid, lambda m: m.state == 'REPLANNING')
    core.until(mid, lambda m: m.state == 'VERIFYING')
    assert len(core.all(entities.Plan)) == 2
    out = core.do(core.missions.advance, mission_id=mid)
    assert not out['changed'] and 'have not passed' in out['considered'][-1]['reason']


def test_replanning_cannot_redecide_the_plan_it_is_replacing(core):
    """REPLANNING with the old plan still in force: neither `advance` nor a plan
    decision fired by name can approve it or send it for approval. Only a
    proposed replacement moves the mission on — which the engine does."""
    mid = core.mission()
    core.reviewer.verdicts[mid] = 'changes_requested'
    core.until(mid, lambda m: m.state == 'REPLANNING')
    before, head = core.row(entities.Mission, mid), core.events()[-1]['seq']
    assert before.entity.decided_plan_version == 1
    out = core.do(core.missions.advance, mission_id=mid)
    assert not out['changed']
    assert [(c['trigger'], c['taken']) for c in out['considered']] == [
        ('replan_budget_exhausted', False), ('plan_auto_approved', False),
        ('plan_needs_approval', False)]
    assert all('already decided' in c['reason'] for c in out['considered'][1:])
    for trigger in ('plan_auto_approved', 'plan_needs_approval'):
        with pytest.raises(lifecycle.GuardFailed, match='already decided'):
            core.do(core.missions.fire, mission_id=mid, trigger=trigger, reason='re-approve')
    after = core.row(entities.Mission, mid)
    assert (after.entity.state, after.version) == ('REPLANNING', before.version)
    assert core.events()[-1]['seq'] == head and len(core.all(entities.Plan)) == 1

    core.reviewer.verdicts[mid] = 'accept'
    assert core.engine.run(mid)['state'] == 'COMPLETED'
    assert [p.plan_version for p in core.all(entities.Plan)] == [1, 2]
    assert core.row(entities.Mission, mid).entity.decided_plan_version == 2


def test_a_deny_cannot_be_sent_for_approval_by_firing_the_edge(archeus_home):
    """PLANNING with a plan (sent back after ASK), then the policy DENIES:
    `plan_needs_approval` fired by name is refused by its guard."""
    core = Core(policy=SpyPolicy('ASK'))
    try:
        mid = core.mission()
        assert core.engine.run(mid)['state'] == 'APPROVAL_REQUIRED'
        core.do(core.missions.request_changes, mission_id=mid, reason='rethink it')
        core.policy.decision = 'DENY'
        before, head = core.row(entities.Mission, mid), core.events()[-1]['seq']
        with pytest.raises(lifecycle.GuardFailed, match='not a question for approval'):
            core.do(core.missions.fire, mission_id=mid, trigger='plan_needs_approval',
                    reason='ask anyway')
        after = core.row(entities.Mission, mid)
        assert (after.entity.state, after.version) == ('PLANNING', before.version)
        assert core.events()[-1]['seq'] == head
        out = core.engine.run(mid)                  # a new plan is denied before it exists
        assert (out['state'], out['stop']) == ('PLANNING', 'policy_denied')
        assert len(core.all(entities.Plan)) == 1 and core.all(entities.Execution) == []
    finally:
        core.close()


def test_review_changes_requested_replans_and_reject_waits_for_a_human(core):
    mid = core.mission()
    core.reviewer.verdicts[mid] = 'reject'
    out = core.engine.run(mid)
    assert (out['state'], out['stop']) == ('REVIEWING', 'review_rejected')
    assert [r.state for r in core.all(entities.Review)] == ['REJECTED']
    assert 'COMPLETED' not in mission_path(core.events(), mid)
    assert core.engine.run(mid)['stop'] == 'review_rejected'         # driving it again
    assert len(core.all(entities.Review)) == 1                       # neither re-reviews
    assert core.row(entities.Mission, mid).entity.state == 'REVIEWING'  # nor completes
    core.do(core.missions.request_changes, mission_id=mid, reason='try again')
    assert core.row(entities.Mission, mid).entity.state == 'REPLANNING'

    other = core.mission()
    core.reviewer.verdicts[other] = 'changes_requested'
    core.until(other, lambda m: m.state == 'REPLANNING')
    (r,) = core.all(entities.Review, mission_id=other)
    assert (r.state, r.verdict) == ('CHANGES_REQUESTED', 'changes_requested')


# ── transaction boundaries, idempotency, concurrency ──

def test_a_rejected_plan_writes_nothing(core):
    mid = core.mission()
    core.until(mid, lambda m: m.state == 'REASONING')
    head = core.events()[-1]['seq']
    bad = dict(engine.SKELETON_PLAN, tasks=[engine.SKELETON_PLAN['tasks'][0]] * 2)
    with pytest.raises(ValueError, match='labels repeat'):
        core.do(core.work.propose_plan, mission_id=mid, plan=bad)
    assert core.events()[-1]['seq'] == head
    assert core.all(entities.Plan) == [] and core.all(entities.Task) == []
    assert core.row(entities.Mission, mid).entity.state == 'REASONING'


def test_the_same_command_twice_changes_nothing_twice(core):
    a = core.mission(key='create-1')
    assert core.mission(key='create-1') == a
    assert len(core.all(entities.Mission)) == 1
    assert len(of(core.events(), 'mission.created')) == 1

    core.until(a, lambda m: [e for e in core.all(entities.Execution) if e.state == 'STARTING'])
    (exe,) = core.all(entities.Execution)
    core.engine._running.clear()                          # we report the end ourselves
    end = dict(execution_id=exe.id, exit_reason='ok', exit_code=0, output=True)
    first = core.do(core.work.record_exit, key='exit-1', actor=core.system, **end)
    head = core.events()[-1]['seq']
    assert core.do(core.work.record_exit, key='exit-1', actor=core.system, **end) == first
    with pytest.raises(lifecycle.IllegalTrigger):                   # no key: refused
        core.do(core.work.record_exit, actor=core.system, **end)
    assert core.events()[-1]['seq'] == head
    assert len(of(core.events(), 'execution.ended')) == 1


def test_two_writers_on_the_same_version_one_wins_one_conflicts(core):
    mid = core.mission()
    core.until(mid, lambda m: m.state == 'APPROVED')
    v = core.row(entities.Mission, mid).version
    futs = [core.db.writer.submit(core.missions.fire, {
        'actor': core.system, 'mission_id': mid, 'trigger': 'dispatch', 'reason': 'go',
        'expected_version': v}) for _ in range(2)]
    results = []
    for f in futs:
        try:
            results.append(f.result())
        except writer.VersionConflict as e:
            results.append(e)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, writer.VersionConflict) for r in results) == 1
    assert mission_path(core.events(), mid).count('EXECUTING') == 1


def test_duplicate_execution_ends_racing_leave_one_end(core):
    mid = core.mission()
    core.until(mid, lambda m: [e for e in core.all(entities.Execution) if e.state == 'STARTING'])
    (exe,) = core.all(entities.Execution)
    core.engine._running.clear()
    barrier, out = threading.Barrier(2), []

    def end():
        barrier.wait()
        try:
            out.append(core.do(core.work.record_exit, actor=core.system, execution_id=exe.id,
                               exit_reason='ok', exit_code=0))
        except lifecycle.IllegalTrigger as e:
            out.append(e)
    ts = [threading.Thread(target=end) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(type(x).__name__ for x in out) == ['IllegalTrigger', 'dict']
    assert len(of(core.events(), 'execution.ended')) == 1


# ── adversarial: direct calls the engine never makes ──

def test_completed_needs_an_accepting_review_of_the_plan_in_force(core):
    """REVIEWING is not a licence to complete: `accepted` needs the latest review
    of the plan in force to accept it. A human overrides a verdict by recording
    their own review, never by firing the edge."""
    mid = core.mission()
    core.reviewer.verdicts[mid] = 'reject'
    core.until(mid, lambda m: m.state == 'REVIEWING')          # no review recorded yet
    head = core.events()[-1]['seq']
    with pytest.raises(lifecycle.GuardFailed, match='no accepting review'):
        core.do(core.missions.accept, mission_id=mid)
    assert core.events()[-1]['seq'] == head
    assert core.engine.run(mid)['stop'] == 'review_rejected'
    head = core.events()[-1]['seq']
    for verb in ('accept', 'fire'):
        with pytest.raises(lifecycle.GuardFailed, match='the latest is REJECTED'):
            kw = {'trigger': 'accepted', 'reason': 'x'} if verb == 'fire' else {}
            core.do(getattr(core.missions, verb), mission_id=mid, **kw)
    assert core.row(entities.Mission, mid).entity.state == 'REVIEWING'
    assert core.events()[-1]['seq'] == head
    out =core.do(core.work.record_review, mission_id=mid, verdict='accept', reviewer='user')
    assert out['mission']['state'] == 'COMPLETED'
    assert [(r.reviewer, r.state) for r in core.all(entities.Review)] == [
        ('stub', 'REJECTED'), ('user', 'ACCEPTED')]


def test_verification_failed_needs_a_failed_criterion(core):
    mid = core.mission()
    core.until(mid, lambda m: m.state == 'VERIFYING')
    before, head = core.row(entities.Mission, mid), core.events()[-1]['seq']
    with pytest.raises(lifecycle.GuardFailed, match='no automatic criterion failed'):
        core.do(core.missions.fire, mission_id=mid, trigger='verification_failed', reason='x')
    after = core.row(entities.Mission, mid)
    assert (after.entity.state, after.version) == ('VERIFYING', before.version)
    assert core.events()[-1]['seq'] == head


def test_redispatch_needs_a_plan_in_force(core):
    """Held before any plan: `unblock` then `redispatch` by name cannot reach
    EXECUTING; `resume` takes the mission back to UNDERSTANDING instead."""
    mid = core.mission()
    for t in ('start', 'needs_clarification', 'unblock'):
        core.do(core.missions.fire, mission_id=mid, trigger=t, reason='x')
    with pytest.raises(lifecycle.GuardFailed, match='no approved plan is in force'):
        core.do(core.missions.fire, mission_id=mid, trigger='redispatch', reason='x')
    core.do(core.missions.fire, mission_id=mid, trigger='redispatch_before_plan', reason='x')
    assert core.row(entities.Mission, mid).entity.state == 'UNDERSTANDING'
    other = core.mission()
    for t in ('start', 'needs_clarification'):
        core.do(core.missions.fire, mission_id=other, trigger=t, reason='x')
    assert core.do(core.missions.resume, mission_id=other)['state'] == 'UNDERSTANDING'
    assert core.engine.run(other)['state'] == 'COMPLETED'      # through a plan, like any other


def test_a_superseded_plans_task_cannot_run(archeus_home):
    core = Core(policy=SpyPolicy())
    try:
        mid = core.mission()
        core.until(mid, lambda m: [t for t in core.all(entities.Task) if t.state == 'READY'])
        (old,) = core.all(entities.Task)
        core.policy.decision = 'DENY'
        assert core.engine.step(mid)['state'] == 'FAILED'     # unrecoverable
        core.policy.decision = 'ALLOW'
        core.do(core.missions.fire, mission_id=mid, trigger='replan', reason='again')
        core.until(mid, lambda m: m.state == 'EXECUTING')      # plan v2 in force
        assert core.row(entities.Task, old.id).entity.state == 'READY'
        with pytest.raises(lifecycle.IllegalTrigger, match='superseded plan'):
            core.do(core.work.dispatch_task, actor=core.system, task_id=old.id)
        assert core.engine.run(mid)['state'] == 'COMPLETED'
        assert [e.task_id for e in core.all(entities.Execution)] != [] and old.id not in {
            e.task_id for e in core.all(entities.Execution)}
    finally:
        core.close()


def test_ready_tasks_reads_only_the_plan_in_force(core):
    """Plan v1 ran to the end and failed verification; plan v2 has the same keys.
    v1's SUCCEEDED `a` must not satisfy v2's `b`: only v2's `a` becomes READY."""
    core.brain = ports.FixedPlanBrain({
        'summary': 'two steps',
        'tasks': [{'key': 'a', 'title': 'A', 'kind': 'code_change', 'acceptance': ACCEPT},
                  {'key': 'b', 'title': 'B', 'kind': 'code_change', 'depends_on': ['a'],
                   'acceptance': ACCEPT}]})
    core.engine = core.build_engine()
    mid = core.mission()
    core.verifier.failing.add(mid)
    core.until(mid, lambda m: m.state == 'REPLANNING')
    core.verifier.failing.discard(mid)
    core.until(mid, lambda m: m.state == 'EXECUTING')
    v2 = max(core.all(entities.Plan), key=lambda p: p.plan_version)
    (a2,) = [t.id for t in core.all(entities.Task, plan_id=v2.id) if t.key == 'a']
    assert core.do(core.work.ready_tasks, mission_id=mid)['ready'] == [a2]


def test_an_old_plans_accepting_review_cannot_complete_a_newer_plan(core):
    """`record_review` rolls back an accept that does not complete, so a stale
    ACCEPTED review needs another writer; the guard still reads only the plan in
    force (defence in depth)."""
    mid = core.mission()
    core.reviewer.verdicts[mid] = 'changes_requested'
    core.until(mid, lambda m: m.state == 'REPLANNING')
    core.until(mid, lambda m: m.state == 'REVIEWING' and len(core.all(entities.Plan)) == 2)
    v1 = min(core.all(entities.Plan), key=lambda p: p.plan_version)

    def stale_accept(tx, *, actor):
        r = entities.Review(id=ids.new_id('review'), mission_id=mid, reviewer='x',
                            plan_id=v1.id)
        tx.insert(r, actor=actor)
        lifecycle.fire(tx, entities.Review, r.id, 'start', actor=actor, reason='x')
        lifecycle.fire(tx, entities.Review, r.id, 'verdict_accept', actor=actor, reason='x',
                       fields={'verdict': 'accept'})
        return {}
    core.do(stale_accept)
    with pytest.raises(lifecycle.GuardFailed, match='no accepting review'):
        core.do(core.missions.accept, mission_id=mid)
    assert core.row(entities.Mission, mid).entity.state == 'REVIEWING'


def test_a_failed_command_leaves_state_fields_version_and_events_unchanged(core):
    """Atomicity of a mission move: state, version, `decided_plan_version`,
    `held_from` and the state_changed event commit together or not at all."""
    mid = core.mission()
    core.until(mid, lambda m: m.state == 'REASONING')

    def decide_then_fail(tx, *, actor, mission_id):
        core.work.propose_plan(tx, actor=actor, mission_id=mission_id,
                               plan=engine.SKELETON_PLAN)          # reasoned + decided
        raise RuntimeError('dies after the decision')

    def pause_then_fail(tx, *, actor, mission_id):
        core.missions.pause(tx, actor=actor, mission_id=mission_id)
        raise RuntimeError('dies after the hold')

    for command, state in ((decide_then_fail, 'REASONING'), (pause_then_fail, 'EXECUTING')):
        if state == 'EXECUTING':
            core.until(mid, lambda m: m.state == 'EXECUTING')
        before, head = core.row(entities.Mission, mid), core.events()[-1]['seq']
        with pytest.raises(RuntimeError, match='dies after'):
            core.do(command, actor=core.system, mission_id=mid)
        after = core.row(entities.Mission, mid)
        assert after == before and after.entity.state == state
        assert (after.entity.decided_plan_version, after.entity.held_from) == (
            before.entity.decided_plan_version, None)
        assert core.events()[-1]['seq'] == head
    assert len(core.all(entities.Plan)) == 1                    # only the engine's


# ── restart: a real process dies at a deterministic point ──

CHILD = r'''
import json, os, sys
sys.path.insert(0, %(root)r)
sys.path.insert(0, %(tests)r)
from v1.integration.test_skeleton import Core
from archeus.core.domain import entities

mode = sys.argv[1]
core = Core(scenarios={'work': [{'sleep': 60}]})
mid = core.mission()
core.until(mid, lambda m: m.state == 'EXECUTING')
core.until(mid, lambda m: [t for t in core.all(entities.Task) if t.state == 'READY'])
(task,) = core.all(entities.Task)
if mode == 'intent':
    core.do(core.work.dispatch_task, actor=core.system, task_id=task.id)
else:
    assert core.engine.step(mid)['did'] == 'start_execution'
(exe,) = core.all(entities.Execution)
print(json.dumps({'mission': mid, 'execution': exe.id, 'state': exe.state, 'pid': exe.pid}),
      flush=True)
os._exit(9)
'''


def _die(archeus_home, mode):
    r = subprocess.run([sys.executable, '-c', CHILD % {
        'root': ROOT, 'tests': os.path.join(ROOT, 'tests')}, mode],
        capture_output=True, text=True, timeout=120,
        env=dict(os.environ, ARCHEUS_HOME=str(archeus_home)))
    assert r.returncode == 9, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _alive(pid, create_time):
    from claude_sessions import proc
    return proc.process_create_time(pid) == create_time


def test_core_killed_mid_execution_reconciles_and_the_mission_completes(archeus_home):
    died = _die(archeus_home, 'spawned')
    assert died['state'] == 'STARTING' and died['pid']
    paths = ExecPaths(died['execution'])
    pid = json.load(open(paths.pid))
    assert os.path.exists(paths.spawning) and not os.path.exists(paths.ended)
    assert _alive(pid['pid'], pid['create_time'])          # the orphan still runs

    core = Core()                                          # a new Core, same home
    try:
        m = core.row(entities.Mission, died['mission']).entity
        assert m.state == 'EXECUTING'
        assert [t.state for t in core.all(entities.Task)] == ['RUNNING']
        (exe,) = core.all(entities.Execution)
        assert (exe.state, exe.pid) == ('STARTING', pid['pid'])

        out = core.engine.run(m.id)
        assert (out['state'], out['stop']) == ('COMPLETED', 'completed')
        deadline = time.monotonic() + 10
        while _alive(pid['pid'], pid['create_time']) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _alive(pid['pid'], pid['create_time']), 'the orphan was not killed'
        first, second = core.all(entities.Execution)
        assert (first.state, first.exit_reason) == ('ENDED_KILLED', 'lost')
        assert (second.attempt, second.state) == (2, 'ENDED_OK')
        moves = [(e['payload']['from'], e['payload']['trigger'])
                 for e in of(core.events(), 'execution.state_changed')
                 if e['subject']['id'] == first.id]
        assert moves == [('INTENT', 'spawn'), ('STARTING', 'start_timeout'),
                         ('LOST', 'reconciled_kill')]
        assert os.path.exists(paths.ended)
    finally:
        core.close()


@pytest.mark.parametrize('pid_now', ['dead', 'recycled'])
def test_an_orphan_whose_process_is_gone_ends_lost_and_nothing_is_killed(archeus_home, pid_now):
    """The recorded process has exited by the time a new Core reconciles. Its
    pid is either free, or recycled by a stranger: the adapter refuses to stop
    a stranger (StopRefused), which reconciliation reads as 'ours is gone'."""
    from claude_sessions import proc
    died = _die(archeus_home, 'spawned')
    paths = ExecPaths(died['execution'])
    pid = json.load(open(paths.pid))
    assert proc.kill_pid_tree(pid['pid'], pid['create_time'])
    deadline = time.monotonic() + 10
    while _alive(pid['pid'], pid['create_time']) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(pid['pid'], pid['create_time'])

    stranger = None
    if pid_now == 'recycled':
        stranger = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        with open(paths.pid, 'w') as f:        # the orphan's pid, now someone else's
            json.dump({'pid': stranger.pid, 'create_time': pid['create_time']}, f)
        seen = 'recorded %r, the stranger\'s own %r' % (
            pid['create_time'], proc.process_create_time(stranger.pid))
    core = Core()
    try:
        out = core.engine.run(died['mission'])
        assert (out['state'], out['stop']) == ('COMPLETED', 'completed')
        if stranger is not None:
            assert stranger.poll() is None, 'reconciliation killed a recycled pid: ' + seen
        first, second = core.all(entities.Execution)
        assert (first.state, first.exit_reason) == ('ENDED_KILLED', 'lost')
        assert (second.attempt, second.state) == (2, 'ENDED_OK')
        moves = [(e['payload']['from'], e['payload']['trigger'])
                 for e in of(core.events(), 'execution.state_changed')
                 if e['subject']['id'] == first.id]
        assert moves == [('INTENT', 'spawn'), ('STARTING', 'start_timeout'),
                         ('LOST', 'reconciled_kill')]
        assert os.path.exists(paths.ended)
    finally:
        core.close()
        if stranger is not None:
            stranger.kill()
            stranger.wait()


def test_the_boot_sweep_reconciles_every_orphan_whatever_its_mission_is_doing(core):
    """Engine.reconcile_orphans (p3.5b §18.1): every non-terminal execution a
    NEW engine did not start, through the one `_reconcile` — including one
    under a PAUSED mission, which no engine step would ever reach. A failure
    on one orphan does not leave the others running; it is raised after."""
    from claude_sessions import proc
    core.scenarios['work'] = [{'sleep': 60}]
    first, second = core.mission(), core.mission()
    for mid in (first, second):
        core.until(mid, lambda m: m.state == 'EXECUTING')
        core.until(mid, lambda m, mid=mid: [e for e in core.all(entities.Execution,
                                                                 mission_id=mid)
                                   if e.state == 'STARTING'])
    core.do(core.missions.pause, mission_id=first)
    live = {e.id: (e.pid, e.create_time) for e in core.all(entities.Execution)}
    assert len(live) == 2 and all(proc.process_create_time(p) == c for p, c in live.values())

    fresh = core.build_engine()             # a restarted Core: none of these are its own
    real, calls = fresh._reconcile, []

    def flaky(e):
        calls.append(e.id)
        if len(calls) == 1:
            raise RuntimeError('the first orphan fails')
        return real(e)
    fresh._reconcile = flaky
    with pytest.raises(RuntimeError, match='the first orphan fails'):
        fresh.reconcile_orphans()
    assert len(calls) == 2, 'a failing orphan stopped the sweep'
    failed_id, done_id = calls
    assert core.row(entities.Execution, done_id).entity.state == 'ENDED_KILLED'
    assert core.row(entities.Execution, failed_id).entity.state == 'STARTING'

    fresh._reconcile = real
    assert fresh.reconcile_orphans() == [failed_id]         # the rest, on the next sweep
    assert fresh.reconcile_orphans() == []
    for pid, ctime in live.values():
        deadline = time.monotonic() + 10
        while proc.process_create_time(pid) == ctime and time.monotonic() < deadline:
            time.sleep(0.05)
        assert proc.process_create_time(pid) != ctime
    assert core.row(entities.Mission, first).entity.state == 'PAUSED'      # never moved
    assert {e.exit_reason for e in core.all(entities.Execution)} == {'lost'}


def test_the_boot_sweep_leaves_the_executions_its_own_engine_started(core):
    core.scenarios['work'] = [{'sleep': 60}]
    mid = core.mission()
    core.until(mid, lambda m: [e for e in core.all(entities.Execution) if e.state == 'STARTING'])
    try:
        assert core.engine.reconcile_orphans() == []
        (e,) = core.all(entities.Execution)
        assert e.state == 'STARTING'
    finally:
        adapter, handle = core.engine._running[e.id]
        adapter.stop(handle, grace_s=0)


def test_core_killed_between_intent_and_spawn_abandons_the_attempt(archeus_home):
    died = _die(archeus_home, 'intent')
    assert died['state'] == 'INTENT' and died['pid'] is None
    assert not os.path.exists(ExecPaths(died['execution']).spawning)
    core = Core()
    try:
        assert core.engine.run(died['mission'])['state'] == 'COMPLETED'
        first, second = core.all(entities.Execution)
        assert (first.state, first.exit_reason) == ('ABANDONED', 'abandoned')
        assert (second.attempt, second.state) == (2, 'ENDED_OK')
    finally:
        core.close()


def test_the_stubs_satisfy_their_ports():
    for stub, port in ((ports.FixedPolicy(), ports.Policy),
                       (ports.FixedPlanBrain({}), ports.Brain),
                       (ports.ScriptedVerifier(), ports.Verifier),
                       (ports.ScriptedReview(), ports.Review)):
        assert isinstance(stub, port)
    assert ports.FixedPolicy().is_stub is True
    with pytest.raises(LookupError):
        ports.FixedPlanBrain({}).call('intent.v1', 'x')
    subject = Ref('mission', ids.new_id('mission'))
    assert ports.ScriptedVerifier(failing={subject.id}).verify(subject).state == 'FAILED'
