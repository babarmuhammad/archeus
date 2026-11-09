"""T-713: the highest-risk branches of `archeus/core/engine.py` the other tests
never reached — the e-stop guard, the denials and the limits first, then the
boundaries of admission, then the loop's two give-up paths.

The engine is Core's only driver of a mission, and it was the one module of
`core/` with no unit test file of its own: it was covered only from
`tests/v1/integration/test_skeleton.py`, `test_execution.py` and
`test_planning.py`, all of which drive the HAPPY path on the real `LocalNode`
with real fake-harness subprocesses. What those tests never assert is what this
file pins: the branch that refuses, the limit that stops, and what the loop
reports when it does nothing. The style and the seeded rows are the neighbouring
gap files' — `test_gaps_core_execution_manager.py` fakes its seams,
`test_gaps_core_application_executions.py` seeds rows on a real database,
`test_t150_gaps.py` brings the real writer and its principals. The writer is
never faked, so every command that is not answered by a stub runs against the
real state machines and a refusal the domain would not allow fails here.

Nothing here spawns a process or touches the OS: the P11 execution manager is
the engine's one injected seam (`Engine.__init__(manager=…)`), and every Rig
injects a node that never spawns and a manager whose `tick` answers as the test
says. The Policy, router, brain, verifier and reviewer are the module's own
stubs (`archeus.core.ports`, extended only by recording), so the file needs no
Windows-only call, no path, no environment value and no live thread: it answers
the same way on Linux and Windows.

The ten branches (engine.py lines as written):

GAP 1  198-203  the disarmed guard over APPROVED/RESUMED/EXECUTING/VERIFYING/
                REVIEWING: an e-stop must fail nothing and start nothing
GAP 2  216-219  a recorded plan denial is never planned again; no brain means no plan
GAP 3  291-301  `_start`: a dispatch that produced no execution is route_wait,
                awaiting_approval or no_route — never `dispatch_task`
GAP 4  311-318  `_verify_mission`: only the AUTOMATIC criteria go to the verifier,
                each under its own index
GAP 5  320-329  `_review`: an existing REJECTED review stops the engine, and nothing
                is recorded
GAP 6  246-265  `_execute`'s order: verify, advance, release, and only then dispatch
GAP 7  161-174  `step`'s PolicyDenied: a plan denial is recorded once, a spec-less
                denial records nothing
GAP 8  181-195  `step`'s `wake_at` (via `_wake_at`): a parked EXECUTING mission says
                WHEN it wakes, and only a parked one
GAP 9  267-289  `_admit`: MISSION_PARALLEL, the project scope of the workspace
                conflict, the fail-closed conflict forms, the disarmed node
GAP 10 130-156  `run`'s two limits (steps, wall clock) and `_busy`'s live-execution
                state set
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

from archeus.core import engine, ports
from archeus.core.application import commands
from archeus.core.application import work as W
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.planning import validate
from archeus.infra.db import Database, rows

AUTO = {'text': 'the result passes its automatic check', 'check': 'automatic'}
HUMAN = {'text': 'the user likes it', 'check': 'human'}
ACCEPT = [{'text': 'it is done', 'check': 'automatic'}]
FUTURE = '2099-01-01T00:00:00.000Z'

#: the live execution states `_busy` waits on (engine.py:151-156)
LIVE = ('INTENT', 'STARTING', 'RUNNING', 'PAUSING', 'STOPPING')


def _iso(offset_s):
    """An ISO stamp *offset_s* seconds from now in the UTC form the domain stores —
    the same one `executions._epoch` parses, on either OS."""
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_s)
            ).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


# ── the engine's seams, faked ────────────────────────────────────────────────

class Node:
    """P11's node as the engine sees it: one question, `disarmed()`."""

    def __init__(self, disarmed=False):
        self.disarmed_flag = disarmed

    def disarmed(self):
        return self.disarmed_flag


class Manager:
    """The injected execution manager (the engine's only way to the OS): it never
    spawns, never adopts, and ticks as the test says."""

    def __init__(self, disarmed=False, ticks=()):
        self.node, self.ticks = Node(disarmed), list(ticks)
        self.tick_calls = 0

    def tick(self):
        self.tick_calls += 1
        return self.ticks.pop(0) if self.ticks else False

    def boot(self):
        return []


class Router:
    """P10's seam (`ports.FixedCandidateRouter`'s shape): every routing is answered
    with what the test says, and what was asked for is recorded. `decided_by` stays
    None as the stub's does: a stub's decision is not a row."""

    def __init__(self, **answer):
        self.answer, self.calls = answer, []

    def route(self, subject, now, **_context):
        self.calls.append(subject)
        return entities.RouteDecision(id=ids.new_id('route_decision'), subject=subject,
                                      **self.answer)


SELECTED = dict(selected='fake', harness_id='fake', result='selected',
                explanation='the only candidate')
NO_RESOURCE = dict(selected=None, result='blocked',
                   explanation='no eligible resource',
                   candidates=({'harness': 'fake', 'eliminated_at_step': 'installed'},))
BREAKER = dict(selected=None, result='blocked', unblock_at=FUTURE,
               explanation='every harness is on its breaker',
               candidates=({'harness': 'fake', 'eliminated_at_step': 'breaker'},))
ASK = dict(selected=None, result='ask', harness_id='other', account_ref='acct_x',
           explanation='the fallback account needs your approval')


class Verifier(ports.ScriptedVerifier):
    """The verifier stub of `archeus.core.ports`, extended by recording who was
    asked, in order."""

    def __init__(self, failing=()):
        super().__init__(failing=failing)
        self.subjects = []

    def verify(self, subject):
        self.subjects.append(subject)
        return super().verify(subject)


class Reviewer(ports.ScriptedReview):
    """The reviewer stub, extended by recording."""

    def __init__(self, verdicts=None):
        super().__init__(verdicts=verdicts)
        self.missions = []

    def review(self, mission):
        self.missions.append(mission.id)
        return super().review(mission)


class DispatchDeny(ports.FixedPolicy):
    """A policy that allows the plan and refuses the DISPATCH: only the stage the
    question is asked at differs (`authorization.context`'s `stage`), which is what
    keeps `unrecoverable` false while `check_dispatch` refuses — the only way a
    dispatch denial is reachable at all from an EXECUTING mission."""

    def evaluate(self, action, ctx):
        if ctx.get('stage') != 'dispatch':
            return super().evaluate(action, ctx)
        return entities.PolicyDecision(
            id=ids.new_id('policy_decision'), action=action, decision='DENY',
            reason='the dispatch stage is denied for %s' % action.action_class)


class _Spy:
    """Wraps one of the engine's ports (its `work`, its `missions`): every writer
    command the engine sends is recorded by name, and `Rig.reply` may answer it
    instead of running it. Anything else on the port is the real thing, so the
    commands that are not answered still run against the real machines."""

    def __init__(self, rig, real, names):
        self.rig, self.real, self.names = rig, real, names

    def __getattr__(self, name):
        real = getattr(self.real, name)
        if name not in self.names:
            return real

        def command(tx, **kw):
            return self.rig._call(name, tx, kw, real)
        return command


class Rig:
    """One Core on the test's own ARCHEUS_HOME: the real writer, the real commands
    and the real domain, the engine's stub ports recorded, the execution manager
    faked so nothing in this file can spawn a process."""

    def __init__(self, *, policy=None, router=None, brain='stub', verifier=None,
                 reviewer=None, disarmed=False):
        self.db = Database.open()
        reg = lambda kind, scopes: Ref(kind, self.db.writer.execute(  # noqa: E731
            commands.register_principal, {'kind': kind, 'scopes': scopes})['id'])
        self.system = reg('system', ('system',))
        self.user = reg('user_device', ('observe', 'control', 'approve', 'admin'))
        self.policy = policy or ports.FixedPolicy()
        self.missions = commands.Missions(policy=self.policy)
        self.router = router or ports.FixedCandidateRouter('fake')
        self.work = W.Work(missions=self.missions, router=self.router)
        self.brain = (ports.FixedPlanBrain(engine.SKELETON_PLAN) if brain == 'stub' else brain)
        self.verifier, self.reviewer = verifier, reviewer
        self.manager = Manager(disarmed=disarmed)
        self.calls, self.reply = [], {}
        work = _Spy(self, self.work, ('replan_budget_spent', 'propose_plan', 'ready_tasks',
                                      'dispatch_task', 'record_task_verification',
                                      'verify_mission', 'record_review'))
        work.missions = _Spy(self, self.missions, ('fire', 'understand', 'context_ready',
                                                   'advance', 'reasoned', 'approve'))
        self.engine = engine.Engine(self.db, actor=self.system, work=work, brain=self.brain,
                                    registry=None, verifier=self.verifier,
                                    reviewer=self.reviewer, manager=self.manager, poll=0.01)

    # ── the recorder ──

    def _call(self, name, tx, kw, real):
        self.calls.append((name, dict(kw)))
        return dict(self.reply[name]) if name in self.reply else real(tx, **kw)

    @property
    def commands(self):
        return [name for name, _kw in self.calls]

    def close(self):
        self.db.close()

    # ── the real path, where the test wants it ──

    def do(self, command, who=None, **kw):
        return self.db.writer.execute(command, dict(kw, actor=who or self.user))

    def created(self, *, title='M', criteria=(AUTO,), project_id=None, max_replans=2):
        """A mission in CREATED, made by the real command (so a guard that reads
        what the command recorded is reading a row a command wrote)."""
        return self.do(commands.create_mission, title=title, objective='o',
                       success_criteria=list(criteria), project_id=project_id,
                       max_replans=max_replans)['id']

    def to_reasoning(self, mid):
        """CREATED -> REASONING on the real lifecycle: what the engine's own first
        three steps do, for a test that needs the engine to start from there."""
        for trigger in ('start', 'understood', 'context_ready'):
            self.do(self.missions.fire, mission_id=mid, trigger=trigger, reason='seed')
        return mid

    def project(self, name='P'):
        pid = ids.new_id('project')
        self.insert(entities.Project(id=pid, workspace_id=ids.GLOBAL_WORKSPACE, name=name),
                    subject=Ref('project', pid))
        return pid

    # ── the seed: rows at the state the branch is judged in ──

    #: an event of the kind that names the row, as every command records one
    _EVENT = {'mission': 'mission.updated', 'plan': 'plan.created', 'task': 'task.created',
              'execution': 'execution.intent', 'route_decision': 'route.decided',
              'review': 'review.requested', 'project': 'project.created'}

    def insert(self, *entities_, subject=None):
        subject = subject or Ref('mission', entities_[0].id)
        etype = self._EVENT[subject.kind]

        def seed(tx, **_kw):
            for e in entities_:
                tx.insert(e, actor=self.system)
            tx.append(new_event(etype, subject, self.system, payload={'seeded': len(entities_)},
                                workspace=ids.GLOBAL_WORKSPACE))
        self.db.writer.execute(seed, {})

    def mission(self, *, state='EXECUTING', criteria=(AUTO,), project_id=None,
                planning_blocked=None, max_replans=2):
        mid = ids.new_id('mission')
        self.insert(entities.Mission(
            id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M', objective='o',
            success_criteria=list(criteria), project_id=project_id, state=state,
            planning_blocked=planning_blocked, max_replans=max_replans),
            subject=Ref('mission', mid))
        return mid

    def plan_with_tasks(self, mid, *keys, version=1, state='APPROVED', **task_kw):
        """The plan in force with one task per *keys*, its digest recomputed as
        `authorization.intact` will find it: a plan whose digest does not match is
        refused at dispatch for a reason no test here is about."""
        pid = ids.new_id('plan')
        plan = entities.Plan(id=pid, mission_id=mid, plan_version=version,
                             summary='the seeded plan', estimated_cost='low', state=state)
        tasks = [entities.Task(id=ids.new_id('task'), plan_id=pid, mission_id=mid, key=k,
                               title='Task %s' % k, kind='code_change', acceptance=ACCEPT,
                               action_classes=('write_repo',), workspace_mode='worktree',
                               **dict({'state': 'READY'}, **task_kw.get(k, {}))) for k in keys]
        self.insert(entities.Plan(**{**plan.to_dict(),
                                     'digest': validate.digest(plan, tasks)}),
                    *tasks, subject=Ref('mission', mid))
        return pid, {t.key: t.id for t in tasks}

    def execution(self, mid, tid, *, state='RUNNING', attempt=1, plan_id=None,
                  stop_reason=None, ended_at=None, started_at=None, exit_reason=None,
                  harness_id='fake'):
        eid = ids.new_id('execution')
        self.insert(entities.Execution(
            id=eid, task_id=tid, mission_id=mid, plan_id=plan_id, attempt=attempt,
            state=state, stop_reason=stop_reason, ended_at=ended_at,
            started_at=started_at, exit_reason=exit_reason, harness_id=harness_id),
            subject=Ref('execution', eid))
        return eid

    def review(self, mid, pid, *, state='REJECTED', verdict='reject'):
        rid = ids.new_id('review')
        self.insert(entities.Review(id=rid, mission_id=mid, plan_id=pid, state=state,
                                    reviewer='code', verdict=verdict),
                    subject=Ref('review', rid))
        return rid

    def route_decision(self, tid, *, result='blocked', unblock_at=None, candidates=(),
                       selected=None):
        rdid = ids.new_id('route_decision')
        self.insert(entities.RouteDecision(
            id=rdid, subject=Ref('task', tid), result=result, unblock_at=unblock_at,
            candidates=candidates, selected=selected, task_id=tid),
            subject=Ref('route_decision', rdid))
        return rdid

    # ── reads ──

    def row(self, cls, eid):
        with self.db.read() as r:
            got = rows.get(r, cls, eid)
        return None if got is None else got.entity

    def all(self, cls, **eq):
        with self.db.read() as r:
            return [x.entity for x in rows.where(r, cls, **eq)]

    def events(self):
        with self.db.read() as r:
            return r.execute('SELECT seq FROM events ORDER BY seq').fetchall()


def _ready_rig(**kw):
    """An EXECUTING mission with one admissible READY task of its own, and nothing
    live: the seed every dispatch branch is judged on."""
    r = Rig(**kw)
    mid = r.mission(state='EXECUTING')
    _pid, tid = r.plan_with_tasks(mid, 'work')
    return r, mid, tid['work']


# ── GAP 1 (engine.py:198-203): the e-stop guard ─────────────────────────────

@pytest.mark.parametrize('state', ['APPROVED', 'RESUMED', 'EXECUTING', 'VERIFYING',
                                   'REVIEWING'])
def test_a_disarmed_node_moves_no_work_state_at_all(state):
    """`if m.state in ('APPROVED', 'RESUMED', 'EXECUTING', 'VERIFYING', 'REVIEWING')
    and self.manager.node.disarmed(): return None` (engine.py:198-203). Deleted, or
    with one of these five states dropped, an e-stopped Core would go on dispatching,
    advancing, verifying and reviewing until the policy denied each step — which the
    same branch says must never read as a mission's failure."""
    rig = Rig(disarmed=True, verifier=Verifier(), reviewer=Reviewer())
    try:
        mid = rig.mission(state=state)
        rig.plan_with_tasks(mid, 'work')
        head = len(rig.events())
        out = rig.engine.step(mid)
        assert (out['did'], out['changed'], out['state']) == (None, False, state)
        assert out['stop'] == engine.STOPS.get(state, 'waiting')
        assert rig.commands == []                       # no command reached the writer
        assert rig.verifier.subjects == [] and rig.reviewer.missions == []
        assert len(rig.events()) == head                # and nothing was recorded
        assert rig.row(entities.Mission, mid).state == state
        assert rig.row(entities.Plan, rig.all(entities.Plan, mission_id=mid)[0].id).state \
            == 'APPROVED'
    finally:
        rig.close()


def test_the_same_seed_moves_on_when_the_node_is_armed():
    """The control GAP 1 needs: the seed above really is work the engine would do,
    so its silence is the guard's and not the seed's (engine.py:198-203 read against
    engine.py:233-241)."""
    rig = Rig(reviewer=Reviewer())
    try:
        mid = rig.mission(state='REVIEWING')
        rig.plan_with_tasks(mid, 'work')
        assert rig.engine.step(mid)['did'] == 'review'
        assert rig.commands == ['record_review']
        assert rig.reviewer.missions == [mid]
    finally:
        rig.close()


@pytest.mark.parametrize('state', ['CREATED', 'UNDERSTANDING', 'CONTEXT_GATHERING',
                                   'REASONING', 'PLANNING'])
def test_disarming_does_not_stop_the_engine_before_work_exists(state):
    """engine.py:198 — the guard's membership is exactly the five states that drive
    work: a mission still being understood, gathered or planned moves on while the
    node is disarmed. Widening the tuple would stall P7 and P8 behind an e-stop, and
    a mission could never be planned at all."""
    rig = Rig(disarmed=True, brain=ports.FixedPlanBrain(engine.SKELETON_PLAN))
    try:
        mid = rig.created() if state == 'CREATED' else rig.mission(state=state)
        out = rig.engine.step(mid)
        assert out['did'] is not None and out['changed'] is True
        assert out['stop'] is None
    finally:
        rig.close()


# ── GAP 2 (engine.py:216-219): the denial the plan gate already recorded ────

def test_a_recorded_plan_denial_is_never_asked_of_the_brain_again():
    """`if (m.planning_blocked or {}).get('kind') == 'policy': return None`
    (engine.py:218-219), reported by engine.py:177-178 as `policy_denied`. Dropped,
    the engine would send a denied mission straight back to the brain and to
    `propose_plan`, re-opening past a denial P9 had recorded: the plan gate would be
    moved by the loop instead of by a human or a policy change."""
    rig = Rig(brain=ports.FixedPlanBrain(engine.SKELETON_PLAN))
    try:
        mid = rig.mission(state='PLANNING', planning_blocked={'kind': 'policy',
                                                              'policy_decision_id': 'pdc_x'})
        pid, _ = rig.plan_with_tasks(mid, 'work', state='REJECTED')
        out = rig.engine.step(mid)
        assert (out['did'], out['changed'], out['stop']) == (None, False, 'policy_denied')
        assert rig.brain.calls == []                    # the brain was never asked
        assert rig.commands == []                       # nothing was sent to the writer
        assert len(rig.all(entities.Plan, mission_id=mid)) == 1        # no new version
        assert rig.row(entities.Plan, pid).state == 'REJECTED'
        assert rig.row(entities.Mission, mid).state == 'PLANNING'      # waits in place
    finally:
        rig.close()


@pytest.mark.parametrize('kind', ['clarification', 'challenge', 'call'])
def test_a_block_that_is_not_a_policy_denial_still_plans(kind):
    """engine.py:218 — the test is `== 'policy'`, not truthiness: only a recorded
    policy denial stops the planning. Replaced by `if m.planning_blocked:`, every
    clarification or challenge would freeze a mission the planning worker can still
    answer, and the stub path would never plan again."""
    rig = Rig(brain=ports.FixedPlanBrain(engine.SKELETON_PLAN))
    try:
        mid = rig.to_reasoning(rig.created())

        def block(tx, **_kw):
            tx.update(entities.Mission, mid, {'planning_blocked': {'kind': kind}},
                      actor=rig.system)
            tx.append(new_event('mission.updated', Ref('mission', mid), rig.system,
                                payload={'fields': ['planning_blocked']},
                                workspace=ids.GLOBAL_WORKSPACE))
        rig.db.writer.execute(block, {})
        assert rig.engine.step(mid)['did'] == 'propose_plan'
        assert len(rig.brain.calls) == 1
        assert rig.commands[:1] == ['propose_plan']
        assert rig.all(entities.Plan, mission_id=mid)   # a plan was recorded
        assert rig.row(entities.Mission, mid).planning_blocked is None
    finally:
        rig.close()


def test_no_brain_means_no_plan_and_no_invention():
    """`if self.brain is None: return None` (engine.py:216-217): with the P8 planning
    worker owning the plan, the engine must write no plan of its own. Removed, the
    stub call is an AttributeError on None — and no plan could be proposed by
    anything else either."""
    rig = Rig(brain=None)
    try:
        mid = rig.to_reasoning(rig.created())
        out = rig.engine.step(mid)
        assert (out['did'], out['changed'], out['stop']) == (None, False, 'waiting')
        assert rig.commands == [] and rig.all(entities.Plan, mission_id=mid) == []
        assert rig.row(entities.Mission, mid).state == 'REASONING'
    finally:
        rig.close()


# ── GAP 3 (engine.py:291-301): a dispatch that started nothing ──────────────

def test_a_route_that_cannot_start_now_waits_and_starts_nothing():
    """`if out['execution_id'] is None: if out.get('unblock_at'): return
    'route_wait'` (engine.py:294-298). Without it the engine would answer
    `dispatch_task` for a task P10 refused to start (the harness is on its breaker,
    O7/T-106), and `EngineLoop` would wait for a process that does not exist."""
    rig, mid, tid = _ready_rig(router=Router(**BREAKER))
    try:
        assert rig.engine.step(mid)['did'] == 'route_wait'
        assert rig.router.calls == [Ref('task', tid)]
        assert rig.all(entities.Execution, task_id=tid) == []   # nothing was begun
        assert rig.row(entities.Task, tid).state == 'READY'     # it waits, unblocked
        assert rig.row(entities.Mission, mid).state == 'EXECUTING'
    finally:
        rig.close()


def test_a_fallback_that_asks_leaves_the_task_awaiting_approval():
    """engine.py:299-300 — `'awaiting_approval' if out.get('authorization') or
    out.get('approval_id') else 'no_route'`: the router's `ask` is a human's decision,
    recorded as one approval and no execution."""
    rig, mid, tid = _ready_rig(router=Router(**ASK))
    try:
        assert rig.engine.step(mid)['did'] == 'awaiting_approval'
        assert rig.all(entities.Execution, task_id=tid) == []
        assert rig.row(entities.Task, tid).state == 'AWAITING_APPROVAL'
        (a,) = rig.all(entities.Approval, mission_id=mid)
        assert (a.state, a.kind) == ('PENDING', 'route')
        assert rig.row(entities.Mission, mid).state == 'BLOCKED'
    finally:
        rig.close()


def test_a_task_with_no_eligible_resource_is_reported_as_no_route():
    """engine.py:299-300, the last arm: a blocked route with nothing to wait for is
    `no_route` — not `dispatch_task`, and not a silent None the loop would settle on."""
    rig, mid, tid = _ready_rig(router=Router(**NO_RESOURCE))
    try:
        out = rig.engine.step(mid)
        assert out['did'] == 'no_route'
        assert out['stop'] is None                      # it is a unit of progress
        assert rig.all(entities.Execution, task_id=tid) == []
        assert rig.row(entities.Task, tid).state == 'BLOCKED'
        assert rig.row(entities.Mission, mid).state == 'BLOCKED'
    finally:
        rig.close()


def test_a_routed_dispatch_is_reported_once_with_its_execution():
    """engine.py:301 — the positive arm GAP 3's three refusals are read against: an
    execution that exists is all that makes `dispatch_task` a true answer."""
    rig, mid, tid = _ready_rig(router=Router(**SELECTED))
    try:
        assert rig.engine.step(mid)['did'] == 'dispatch_task'
        (e,) = rig.all(entities.Execution, task_id=tid)
        assert (e.state, e.attempt, e.harness_id) == ('INTENT', 1, 'fake')
        assert rig.row(entities.Task, tid).state == 'RUNNING'
    finally:
        rig.close()


# ── GAP 4 (engine.py:311-318): who is put to the verifier ───────────────────

def test_a_human_criterion_is_never_verified_and_never_passes_on_its_own():
    """`for i, c in enumerate(m.success_criteria): if c['check'] == 'automatic'`
    (engine.py:313-316). Without the filter, a human criterion would be handed to the
    code verifier and recorded PASSED, and a mission nobody accepted would complete;
    and enumerating the filtered list instead of the criteria would file verdict 1
    under criterion 1. Both mistakes are a hard failure: `verify_mission` refuses a
    verdict set that is not exactly the automatic criteria."""
    rig = Rig(verifier=Verifier())
    try:
        mid = rig.mission(state='VERIFYING', criteria=(AUTO, HUMAN, AUTO))
        pid, _ = rig.plan_with_tasks(mid, 'work', work={'state': 'SUCCEEDED'})
        out = rig.engine.step(mid)
        assert out['did'] == 'verify_mission'
        assert rig.verifier.subjects == [Ref('mission', mid)] * 2      # never a third
        assert [(v.criterion, v.state) for v in rig.all(entities.Verification,
                                                        plan_id=pid)] == [(0, 'PASSED'),
                                                                          (2, 'PASSED')]
        # the open human criterion holds the mission: it is not accepted by silence
        assert out['state'] == 'BLOCKED'
        assert rig.row(entities.Mission, mid).state == 'BLOCKED'
    finally:
        rig.close()


def test_a_mission_with_only_human_criteria_asks_the_verifier_nothing():
    """engine.py:313-316, the empty case: with no automatic criterion nothing is
    put to the verifier and no Verification row is made; the mission goes to a human
    (`awaiting_human_acceptance`), never to review on a vacuous pass (`verified`
    refuses 'no automatic success criterion')."""
    rig = Rig(verifier=Verifier())
    try:
        mid = rig.mission(state='VERIFYING', criteria=(HUMAN,))
        pid, _ = rig.plan_with_tasks(mid, 'work', work={'state': 'SUCCEEDED'})
        out = rig.engine.step(mid)
        assert rig.verifier.subjects == []
        assert rig.all(entities.Verification, plan_id=pid) == []
        assert (out['did'], out['state']) == ('verify_mission', 'BLOCKED')
    finally:
        rig.close()


# ── GAP 5 (engine.py:320-329): a rejected review is a human's to answer ─────

def test_a_rejected_review_stops_the_engine_without_a_second_review():
    """`if any(x.entity.state == 'REJECTED' for x in done): return None`
    (engine.py:324-325). Removed, the reviewer would be asked again on every pass and
    its next `accept` would complete a mission a reviewer had rejected."""
    rig = Rig(reviewer=Reviewer())
    try:
        mid = rig.mission(state='REVIEWING')
        pid, _ = rig.plan_with_tasks(mid, 'work')
        rig.review(mid, pid, state='REJECTED', verdict='reject')
        out = rig.engine.step(mid)
        assert (out['did'], out['changed'], out['stop']) == (None, False, 'review_rejected')
        assert rig.reviewer.missions == [] and rig.commands == []
        assert [r.state for r in rig.all(entities.Review, plan_id=pid)] == ['REJECTED']
        assert rig.row(entities.Mission, mid).state == 'REVIEWING'
    finally:
        rig.close()


def test_the_reviewer_is_asked_once_when_nothing_has_been_reviewed():
    """engine.py:326-329 — the arm GAP 5 is read against: with no review of the plan
    in force the engine records exactly one, and the mission's own `accepted` guard
    answers it."""
    rig = Rig(reviewer=Reviewer())
    try:
        mid = rig.mission(state='REVIEWING')
        pid, _ = rig.plan_with_tasks(mid, 'work')
        assert rig.engine.step(mid)['did'] == 'review'
        assert rig.commands == ['record_review'] and rig.reviewer.missions == [mid]
        assert [r.state for r in rig.all(entities.Review, plan_id=pid)] == ['ACCEPTED']
    finally:
        rig.close()


# ── GAP 6 (engine.py:246-265): one unit of progress, in the planned order ───

def test_an_advance_is_the_whole_pass():
    """`if self._do(self.missions.advance, ...)['changed']: return 'advance'`
    (engine.py:258-259), before `ready_tasks` and before any dispatch. Take the
    return away, or move it after the dispatch loop, and the engine starts a task of
    a mission that has already moved on to VERIFYING."""
    rig, mid, tid = _ready_rig()
    try:
        rig.reply['advance'] = {'changed': True}
        assert rig.engine.step(mid)['did'] == 'advance'
        assert rig.commands == ['advance']
        assert rig.all(entities.Execution, task_id=tid) == []
    finally:
        rig.close()


def test_releasing_ready_tasks_is_the_whole_pass():
    """engine.py:260-261 — the second `return`: tasks whose dependencies are done are
    released, and nothing is dispatched in the same pass. Without it a task would be
    dispatched on the pass its dependency finished, on the same snapshot of tasks
    `_execute` read before either move."""
    rig = Rig()
    try:
        mid = rig.mission(state='EXECUTING')
        _pid, tid = rig.plan_with_tasks(mid, 'work', work={'state': 'PENDING'})
        rig.reply['ready_tasks'] = {'ready': [tid['work']]}
        assert rig.engine.step(mid)['did'] == 'ready_tasks'
        assert rig.commands == ['advance', 'ready_tasks']
        assert rig.all(entities.Execution, task_id=tid['work']) == []
        assert rig.row(entities.Task, tid['work']).state == 'PENDING'   # the answer
    finally:
        rig.close()


def test_a_verifying_task_is_judged_before_the_mission_advances():
    """engine.py:252-257 — the VERIFYING loop comes FIRST, and returns: a task whose
    checks are not recorded yet is judged before `advance` is asked whether the
    mission is done, so `all_tasks_done` is never answered on an undecided task."""
    rig = Rig(verifier=Verifier())
    try:
        mid = rig.mission(state='EXECUTING')
        pid, tid = rig.plan_with_tasks(mid, 'work', work={'state': 'VERIFYING'})
        assert rig.engine.step(mid)['did'] == 'verify_task'
        assert rig.commands == ['record_task_verification']
        assert rig.row(entities.Task, tid['work']).state == 'SUCCEEDED'
        assert [(v.subject.kind, v.state) for v in rig.all(entities.Verification,
                                                           plan_id=pid)] == [('task',
                                                                              'PASSED')]
    finally:
        rig.close()


def test_the_engine_judges_no_task_when_the_verification_worker_verifies():
    """engine.py:253 — `and self.verifier is not None`: with no verifier injected
    (P13 D15) the engine verifies nothing itself, and asks only the mission's
    `advance` — which does not move on an undecided task."""
    rig = Rig(verifier=None)
    try:
        mid = rig.mission(state='EXECUTING')
        rig.plan_with_tasks(mid, 'work', work={'state': 'VERIFYING'})
        out = rig.engine.step(mid)
        assert rig.commands == ['advance', 'ready_tasks']
        assert rig.all(entities.Verification) == []
        assert (out['did'], out['stop']) == (None, 'task_blocked')
    finally:
        rig.close()


# ── GAP 7 (engine.py:161-174): what a denial leaves behind ─────────────────

def test_a_plan_denial_is_recorded_once_by_the_step_that_refused_it():
    """`if e.specs is not None: recorded = self._do(authorization.record_plan_denial,
    …)` (engine.py:165-168). Without it a denied plan is an audited nothing: the
    mission blocks with no decision row to point at, while `stop` says `policy_denied`
    for a denial no record names."""
    rig = Rig(policy=ports.FixedPolicy(by_class={'write_repo': 'DENY'}),
              brain=ports.FixedPlanBrain(engine.SKELETON_PLAN))
    try:
        mid = rig.to_reasoning(rig.created())
        out = rig.engine.step(mid)
        assert (out['did'], out['changed'], out['state']) == ('plan_denied', True, 'BLOCKED')
        assert out['recorded']['recorded'] is True and 'write_repo' in out['denied']
        (d,) = [x for x in rig.all(entities.PolicyDecision) if x.stage == 'plan']
        assert (d.decision, d.outcome, d.mission_id) == ('DENY', 'denied', mid)
        assert rig.all(entities.Plan, mission_id=mid) == []        # nothing was written
        assert rig.engine.step(mid)['did'] is None                 # recorded once
        assert [x for x in rig.all(entities.PolicyDecision) if x.stage == 'plan'] == [d]
    finally:
        rig.close()


def test_a_denial_that_carries_no_plan_records_nothing():
    """engine.py:161-174, the same arm's other side: a `PolicyDenied` from a command
    with no `specs` (P9's dispatch check) answers `policy_denied` with `changed False`
    and records NOTHING. Invert the test on `e.specs` and a dispatch denial is
    answered with a plan denial whose `changed True` would have `run` loop on a
    mission that never moved. The policy denies only the `dispatch` stage, which is
    what lets the pass reach `check_dispatch` at all: judged at the plan stage,
    `unrecoverable` would have failed the mission on the `advance` before it."""
    rig = Rig(policy=DispatchDeny())
    try:
        mid = rig.mission(state='EXECUTING')
        _pid, tid = rig.plan_with_tasks(mid, 'work')
        head = len(rig.events())
        out = rig.engine.step(mid)
        assert (out['did'], out['changed'], out['state']) == (None, False, 'EXECUTING')
        assert out['stop'] == 'policy_denied' and out['recorded'] is None
        assert 'write_repo' in out['denied']
        assert len(rig.events()) == head                           # wrote nothing
        assert rig.all(entities.Execution, task_id=tid['work']) == []
        assert rig.row(entities.Task, tid['work']).state == 'READY'
    finally:
        rig.close()


# ── GAP 8 (engine.py:181-195): a parked mission says when it wakes ──────────

def test_a_parked_mission_reports_the_hour_it_wakes_after_a_failed_start():
    """`wake = None if did or m.state != 'EXECUTING' else self._wake_at(m)`
    (engine.py:176) and `_wake_at`'s min over `spawn_wait` (engine.py:193-195).
    A mission that changed nothing while a READY task waits out a failed start must
    say WHEN, or `EngineLoop` never steps it again and the task is lost (O7, T-106)."""
    rig = Rig()
    try:
        mid = rig.mission(state='EXECUTING')
        _pid, tid = rig.plan_with_tasks(mid, 'work')
        now = time.time()
        rig.execution(mid, tid['work'], state='ABANDONED', stop_reason='spawn',
                      ended_at=_iso(-1), exit_reason='abandoned')
        out = rig.engine.step(mid)
        assert (out['did'], out['stop']) == (None, 'task_blocked')
        assert out['wake_at'] is not None
        assert now + 10 <= out['wake_at'] <= now + 20
        assert len(rig.all(entities.Execution, task_id=tid['work'])) == 1  # nothing new
    finally:
        rig.close()


def test_a_parked_mission_reports_the_earlier_of_its_two_waits():
    """engine.py:193-195 — `min((w for t in tids for w in (spawn_wait(…),
    route_wait(…)) if w)`: the answer is the earlier wait. Taking only the first, or
    dropping the route half, parks the mission until the later one or forever."""
    rig = Rig()
    try:
        mid = rig.mission(state='EXECUTING')
        _pid, tid = rig.plan_with_tasks(mid, 'work')
        rig.route_decision(tid['work'], result='blocked', unblock_at=_iso(60),
                           candidates=({'harness': 'fake',
                                         'eliminated_at_step': 'breaker'},))
        rig.execution(mid, tid['work'], state='ABANDONED', stop_reason='spawn',
                      ended_at=_iso(-1), exit_reason='abandoned')
        out = rig.engine.step(mid)
        assert out['did'] is None
        assert out['wake_at'] is not None and out['wake_at'] <= time.time() + 20
    finally:
        rig.close()


def test_a_mission_purely_on_a_breaker_reports_the_breakers_hour():
    """engine.py:193-195 with no failed start at all: the `route_wait` half of the
    min is the only answer, and it is the routing decision's own `unblock_at` —
    dropping it would re-route a harness that cannot start on every pass (T-106)."""
    rig = Rig()
    try:
        mid = rig.mission(state='EXECUTING')
        _pid, tid = rig.plan_with_tasks(mid, 'work')
        rig.route_decision(tid['work'], result='blocked', unblock_at=_iso(60),
                           candidates=({'harness': 'fake',
                                         'eliminated_at_step': 'breaker'},))
        out = rig.engine.step(mid)
        assert (out['did'], out['stop']) == (None, 'task_blocked')
        assert out['wake_at'] is not None and out['wake_at'] >= time.time() + 30
    finally:
        rig.close()


def test_a_mission_that_moved_or_waits_in_no_executing_state_reports_no_hour():
    """engine.py:176,181 — `wake` is reported for a parked EXECUTING mission and for
    nothing else: not for a pass that changed something, not for a state the loop is
    not waiting in. Always reporting it would let `EngineLoop` sleep on a stale hour
    instead of stepping the mission."""
    rig = Rig(reviewer=Reviewer())
    try:
        mid = rig.mission(state='REVIEWING')
        pid, _ = rig.plan_with_tasks(mid, 'work')
        assert 'wake_at' not in rig.engine.step(mid)          # a pass that did something
        rig2 = Rig()
        try:
            mid2 = rig2.mission(state='REVIEWING')                # a pass that did nothing
            pid2, _ = rig2.plan_with_tasks(mid2, 'work')
            rig2.review(mid2, pid2, state='REJECTED', verdict='reject')
            out = rig2.engine.step(mid2)
            assert 'wake_at' not in out and out['stop'] == 'review_rejected'
        finally:
            rig2.close()
    finally:
        rig.close()


# ── GAP 9 (engine.py:267-289): admission ────────────────────────────────────

def test_a_mission_never_runs_more_than_mission_parallel_executions():
    """engine.py:279-281 — `mine = [x for x in live if x.mission_id == m.id]`, `if
    len(mine) >= MISSION_PARALLEL: return False`: at the cap the next READY task
    waits, one under it it starts. Read `> MISSION_PARALLEL`, or count every
    mission's work, and the gate P11 §16 set on parallel work is gone."""
    assert engine.MISSION_PARALLEL == 3
    for live, expected in ((engine.MISSION_PARALLEL, []), (engine.MISSION_PARALLEL - 1,
                                                           ['INTENT'])):
        rig = Rig()
        try:
            mid = rig.mission(state='EXECUTING')
            keys = ['w%d' % i for i in range(live + 1)]
            _pid, tid = rig.plan_with_tasks(mid, *keys, **{
                k: {'touches': ('src/%s/**' % k,)} for k in keys})
            for k in keys[:live]:
                rig.execution(mid, tid[k], state='RUNNING', started_at=_iso(-30))
            out = rig.engine.step(mid)
            assert [e.state for e in rig.all(entities.Execution,
                                             mission_id=mid) if e.state == 'INTENT'] \
                == expected
            assert (out['did'] == 'dispatch_task') == bool(expected)
        finally:
            rig.close()


def test_another_missions_live_work_does_not_spend_this_missions_capacity():
    """engine.py:279 — the `x.mission_id == m.id` of `mine`: the cap is the mission's
    own. Counting every live execution instead would starve a second mission
    completely once three tasks anywhere were running."""
    rig = Rig()
    try:
        other = rig.mission(state='EXECUTING')
        _op, otid = rig.plan_with_tasks(other, 'a0', 'a1', 'a2')
        for k in otid:
            rig.execution(other, otid[k], state='RUNNING', started_at=_iso(-30))
        mid = rig.mission(state='EXECUTING')
        _pid, tid = rig.plan_with_tasks(mid, 'work')
        assert rig.engine.step(mid)['did'] == 'dispatch_task'
        assert [e.state for e in rig.all(entities.Execution, mission_id=mid)] == ['INTENT']
    finally:
        rig.close()


@pytest.mark.parametrize('label,dispatched', [('docs-only', True), ('src-overlap', False)])
def test_two_missions_of_one_project_share_only_the_workspace_they_touch(label,
                                                                        dispatched):
    """engine.py:282-289 — live work of the same PROJECT whose `touches` overlap
    holds the candidate back (`if xm.project_id == m.project_id`, then
    `_conflict(t, o)`); work that touches something else does not. Dropping the
    overlap test would serialise a whole project behind one task at a time; dropping
    the project scoping would serialise every mission of every project."""
    touches = {'docs-only': 'docs/api/**', 'src-overlap': 'src/**'}[label]
    rig = Rig(router=Router(**SELECTED))
    try:
        project = rig.project()
        live_mission = rig.mission(state='EXECUTING', project_id=project)
        _lp, ltid = rig.plan_with_tasks(live_mission, 'live', live={'touches':
                                                                    ('src/a/**',)})
        rig.execution(live_mission, ltid['live'], state='RUNNING', started_at=_iso(-30))
        mid = rig.mission(state='EXECUTING', project_id=project)
        _pid, tid = rig.plan_with_tasks(mid, 'work', work={'touches': (touches,)})
        out = rig.engine.step(mid)
        assert (out['did'] == 'dispatch_task') is dispatched
        assert (out['stop'] == 'task_blocked') is not dispatched
        assert [e.state for e in rig.all(entities.Execution, mission_id=mid)] == (
            ['INTENT'] if dispatched else [])
    finally:
        rig.close()


def test_work_of_another_project_never_blocks_a_dispatch():
    """engine.py:287 — `if xm.project_id == m.project_id`: the conflict set is
    the project's, and a mission with no project of another's live work is no reason
    to wait."""
    rig = Rig(router=Router(**SELECTED))
    try:
        pa, pb = rig.project('P'), rig.project('Q')
        live_mission = rig.mission(state='EXECUTING', project_id=pa)
        _lp, ltid = rig.plan_with_tasks(live_mission, 'live', live={'touches':
                                                                    ('src/a/**',)})
        rig.execution(live_mission, ltid['live'], state='RUNNING', started_at=_iso(-30))
        mid = rig.mission(state='EXECUTING', project_id=pb)
        _pid, tid = rig.plan_with_tasks(mid, 'work', work={'touches': ('src/a/**',)})
        assert rig.engine.step(mid)['did'] == 'dispatch_task'
    finally:
        rig.close()


def test_a_task_that_declares_no_workspace_conflicts_with_everything():
    """engine.py:83-86 (`_conflict`) and engine.py:89-95 (`_overlap`), the
    fail-closed forms: either side with no `touches` conflicts, and two patterns with
    an empty `base` (a glob in their first component) overlap whatever the other
    names. Drop `not t.touches or not other.touches` and an unbounded task runs
    beside anything; drop `not x or not y` from `_overlap` and a `*/*.py` task and a
    `docs/x.md` task write the same files at once, because no prefix survives to
    compare."""
    T, base = entities.Task, dict(id=ids.new_id('task'), plan_id=ids.new_id('plan'),
                                  mission_id=ids.new_id('mission'),
                                  key='k', title='t', kind='code_change')
    assert engine._conflict(T(**dict(base, touches=('src/a/**',))),
                            T(**dict(base, touches=()))) is True
    assert engine._conflict(T(**dict(base, touches=('src/a/**',))),
                            T(**dict(base, touches=('docs/x/**',), workspace_mode='in_place')
                              )) is True
    assert engine._overlap('*/*.py', 'docs/x.md') is True
    assert engine._overlap('src/a/**', 'src/a/x.py') is True
    assert engine._overlap('src/a/**', 'docs/x.md') is False
    rig = Rig(router=Router(**SELECTED))
    try:
        project = rig.project()
        live_mission = rig.mission(state='EXECUTING', project_id=project)
        _lp, ltid = rig.plan_with_tasks(live_mission, 'live', live={'touches': ('*/*.py',)})
        rig.execution(live_mission, ltid['live'], state='RUNNING', started_at=_iso(-30))
        mid = rig.mission(state='EXECUTING', project_id=project)
        _pid, tid = rig.plan_with_tasks(mid, 'work', work={'touches': ()})
        out = rig.engine.step(mid)
        assert (out['did'], out['stop']) == (None, 'task_blocked')
        assert rig.all(entities.Execution, mission_id=mid, state='INTENT') == []
        assert rig.row(entities.Task, tid['work']).state == 'READY'
    finally:
        rig.close()


def test_admission_refuses_a_disarmed_node_before_capacity_is_counted():
    """engine.py:271-272 — `_admit` asks `self.manager.node.disarmed()` first and
    says False: even with the whole capacity free and no conflict, nothing is admitted
    while the node is disarmed. `step`'s own guard (engine.py:198) means this is
    reached only by a caller that gets the engine's answer directly, which is why it
    is called here rather than through a step."""
    rig, mid, tid = _ready_rig(disarmed=True, router=Router(**SELECTED))
    try:
        m, t = rig.row(entities.Mission, mid), rig.row(entities.Task, tid)
        assert rig.engine._admit(m, t) is False
        assert rig.all(entities.Execution, mission_id=mid) == []
        rig.manager.node.disarmed_flag = False
        assert rig.engine._admit(m, t) is True      # the same seed, once armed
    finally:
        rig.close()


def test_a_task_still_waiting_on_a_harness_is_neither_dispatched_nor_routed_again():
    """engine.py:275-276 — `if X.spawn_wait(r, t.id, now) or resources.route_wait(
    r, t.id, now): return False`: the O7 back-off is honoured by admission, not only
    by `wake_at` (the spawn half of the same line is pinned by GAP 8's failed-start
    test, which is seeded with an abandoned spawn and asserts no execution is begun).
    Removed, a harness whose spawns keep failing is retried on every pass of the
    loop, and the breaker never means anything."""
    rig = Rig(router=Router(**SELECTED))
    try:
        mid = rig.mission(state='EXECUTING')
        _pid, tid = rig.plan_with_tasks(mid, 'work')
        rig.route_decision(tid['work'], result='blocked', unblock_at=_iso(60),
                           candidates=({'harness': 'fake',
                                         'eliminated_at_step': 'breaker'},))
        out = rig.engine.step(mid)
        assert (out['did'], out['stop']) == (None, 'task_blocked')
        assert rig.router.calls == []                       # not even routed again
        assert rig.all(entities.Execution, mission_id=mid) == []
    finally:
        rig.close()


# ── GAP 10 (engine.py:130-156): the loop's limits, and what it waits for ────

def test_run_gives_up_after_the_step_budget():
    """engine.py:149 — `raise RuntimeError('mission %s did not settle in %d steps')`:
    a mission that never settles is an error, never a hang. Delete it and the
    synchronous driver spins past its budget; the assertion on the commands counts
    that what the budget spends is the steps that changed something."""
    rig = Rig()
    try:
        mid = rig.mission(state='UNDERSTANDING')
        rig.reply['understand'] = {}                        # a step that always "does"
        with pytest.raises(RuntimeError, match='did not settle in 3 steps'):
            rig.engine.run(mid, max_steps=3)
        assert rig.commands == ['understand'] * 3     # the budget counts CHANGED steps
    finally:
        rig.close()


def test_run_gives_up_when_an_execution_outlives_the_deadline():
    """engine.py:145-147 — `if time.monotonic() > deadline: raise RuntimeError(
    '… ran past %.0fs')`: the loop is waiting on a process that will never end, and
    must say so. Without it `run` waits forever on a wedged execution."""
    rig = Rig()
    try:
        mid = rig.mission(state='EXECUTING')
        _pid, tid = rig.plan_with_tasks(mid, 'work', work={'state': 'RUNNING'})
        rig.execution(mid, tid['work'], state='RUNNING', started_at=_iso(-1))
        with pytest.raises(RuntimeError, match='ran past'):
            rig.engine.run(mid, max_steps=50, timeout=-1.0)
    finally:
        rig.close()


@pytest.mark.parametrize('state', LIVE)
def test_the_loop_waits_while_an_execution_is_live(state):
    """engine.py:151-156 — `_busy` is the exact live set ('INTENT', 'STARTING',
    'RUNNING', 'PAUSING', 'STOPPING'): an execution in one of them means the mission
    is not settled yet. Drop one state and `run` answers while a process is still
    starting or stopping, reporting the mission's mid-flight state as its result."""
    rig = Rig()
    try:
        mid = rig.mission(state='EXECUTING')
        _pid, tid = rig.plan_with_tasks(mid, 'work', work={'state': 'RUNNING'})
        rig.execution(mid, tid['work'], state=state, started_at=_iso(-1))
        assert rig.engine._busy(mid) is True
    finally:
        rig.close()


@pytest.mark.parametrize('state,exit_reason', [('ENDED_OK', 'ok'), ('ENDED_KILLED', 'killed'),
                                               ('ABANDONED', 'abandoned')])
def test_the_loop_stops_waiting_when_no_execution_is_live(state, exit_reason):
    """engine.py:154-156, the same tuple's other side: an ended execution is history,
    and waiting on it would keep `run` from answering at all."""
    rig = Rig()
    try:
        mid = rig.mission(state='EXECUTING')
        _pid, tid = rig.plan_with_tasks(mid, 'work', work={'state': 'SUCCEEDED'})
        rig.execution(mid, tid['work'], state=state, exit_reason=exit_reason,
                      ended_at=_iso(-5))
        assert rig.engine._busy(mid) is False
    finally:
        rig.close()
