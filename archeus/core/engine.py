"""The walking skeleton (plan §31.1 P3.5): the smallest operating loop that
takes a mission from CREATED to a settled state over the real application
commands, the real database and the fake harness's real subprocess.

    CREATED -> start -> UNDERSTANDING -> understood (from its intent, P7)
    CONTEXT_GATHERING -> context_ready: the context package (P5) -> REASONING
    REASONING | PLANNING | REPLANNING: the planning worker's (P8, core/planning/);
    only with an injected stub `brain`: brain `plan.v1` -> Work.propose_plan
        -> PLANNING -> plan gate (Policy port)
        -> APPROVED | APPROVAL_REQUIRED on ASK (stops: a human decides)
        | DENY: nothing written, state unchanged (stops: `policy_denied`)
    REPLANNING: replan budget judged first -> BLOCKED, or a new plan as above
    APPROVED -> dispatch -> EXECUTING
    each task: deps_satisfied -> admission (P11 §16) -> dispatch_task (P9, P10,
        INTENT); the execution manager (core/execution/manager.py) spawns,
        watches and records it; ENDED_OK -> VERIFYING -> verifier
        -> record_task_verification -> SUCCEEDED | retry | FAILED
    EXECUTING advance -> VERIFYING | REPLANNING | FAILED
    verifier per automatic criterion -> verify_mission -> REVIEWING | REPLANNING | BLOCKED
    reviewer -> record_review -> COMPLETED | REPLANNING | (rejected: stops in REVIEWING)

Every state change is one writer command (archeus/core/application/work.py,
commands.Missions). Everything with a side effect or a wait — the brain, a
process, a verifier, a reviewer — happens between commands, never inside one.
`step()` does exactly one unit and says which, so the loop is deterministic and
can be stopped anywhere: that is how the restart tests kill Core at an exact
point. An execution this engine did not start (its Core died) is reconciled:
its process is killed by pid + creation time and the attempt ends LOST or
ABANDONED; the task retries with a new execution.

The stubs it runs on are the ports' (archeus/core/ports.py). Deliberately not
here: intent (the intent worker, core/missions/intent.py, P7), planning (the planning
worker, core/planning/worker.py, P8 — the engine plans only through an injected stub),
approvals bound to action hashes (P9), routing and accounts (P10), the
execution manager and node — adoption, pause, stop, timeouts, hand-off, the
process registry (P11) — and real verification, merge-back and review (the
verification worker, core/verification/worker.py, P13 — the engine verifies and
reviews only through injected stubs, and otherwise only judges what it recorded).
"""

import os
import time

from ..infra.db import rows
from .application.commands import active_plan
from .application import authorization
from .application.work import PolicyDenied
from .domain import entities, states
from .domain.values import Ref
from .execution.manager import ExecutionManager

#: at most this many live executions per mission (p11-design-gate §16)
MISSION_PARALLEL = 3

#: A mission starts as soon as it exists: whether the user must confirm it
#: first is the autonomy profile's (P9), and the P1 policy stub never asks.
START = 'start'

#: States the engine has nothing to do in: ended, or waiting for a human.
SETTLED = ('COMPLETED', 'CANCELLED', 'FAILED', 'BLOCKED', 'PAUSED', 'APPROVAL_REQUIRED')
#: Why the loop stops, by the state it stops in (anything else: 'waiting').
STOPS = dict({s: s.lower() for s in SETTLED}, REVIEWING='review_rejected',
             EXECUTING='task_blocked', VERIFYING='unverifiable')

#: The stub brain's plan: one task on the fake harness, one automatic criterion.
SKELETON_PLAN = {
    'summary': 'walking skeleton: one task on the fake harness',
    'tasks': [{'key': 'work', 'title': 'Do the work', 'kind': 'code_change',
               'action_classes': ['write_repo'],
               'acceptance': [{'text': 'the work is done', 'check': 'automatic'}]}],
    'success_criteria': [{'text': 'the result passes its automatic check',
                          'check': 'automatic'}],
}
#: What the fake agent does for a task no scenario is scripted for.
DEFAULT_SCENARIO = [{'emit': {'type': 'result', 'summary': 'done'}}]

_ENDED = states.terminal('execution')


def _conflict(t, other):
    """Two tasks of one project that may not run at once (§16): either in
    place, either without `touches`, or touches that overlap."""
    if 'in_place' in (t.workspace_mode, other.workspace_mode) or not t.touches \
            or not other.touches:
        return True
    return any(_overlap(a, b) for a in t.touches for b in other.touches)


def _overlap(a, b):
    def base(g):
        g = g.replace('\\', '/')
        cut = min([g.index(c) for c in '*?[' if c in g] or [len(g)])
        return g[:cut].rstrip('/')
    x, y = base(a), base(b)
    return not x or not y or x == y or x.startswith(y + '/') or y.startswith(x + '/')


class Engine:
    """Drives missions on one open Database as the principal `actor`.

    `work` is `work.Work` (its `missions` carries the Policy port), `brain`
    (a stub `plan.v1` port, or None when the planning worker plans), `verifier`
    and `reviewer` stub ports, or None when the verification worker verifies
    and reviews (P13 D15), `registry` the adapter registry,
    `scenarios` maps a task key to the fake agent's steps."""

    def __init__(self, db, *, actor, work, brain, registry, verifier, reviewer,
                 scenarios=None, poll=0.02, usage=None, manager=None):
        self.db, self.actor, self.work = db, actor, work
        self.missions = work.missions
        self.brain, self.registry = brain, registry
        self.verifier, self.reviewer = verifier, reviewer
        self.scenarios = {} if scenarios is None else scenarios
        self.poll = poll
        # every process is the execution manager's (P11): this engine dispatches
        self.manager = manager or ExecutionManager(db, actor=actor, registry=registry,
                                                   work=work, usage=usage,
                                                   scenarios=self.scenarios)

    def _do(self, command, **kwargs):
        return self.db.writer.execute(command, dict(kwargs, actor=self.actor))

    def _mission(self, mission_id):
        with self.db.read() as r:
            row = rows.get(r, entities.Mission, mission_id)
        if row is None:
            raise LookupError(mission_id)
        return row.entity

    def run(self, mission_id, *, max_steps=200, timeout=60.0):
        """Step until nothing changes; the last step's report says why. The
        synchronous driver (tests, tools): it also runs the execution manager's
        pass and waits while one of the mission's processes is running, which
        the Core runtime does on its own thread (P11)."""
        deadline, steps = time.monotonic() + timeout, 0
        while steps < max_steps:
            out = self.step(mission_id)
            if out['changed']:
                steps += 1
                continue
            if self.manager.tick():
                continue
            if not self._busy(mission_id):
                return out
            if time.monotonic() > deadline:
                raise RuntimeError('mission %s: its executions ran past %.0fs'
                                   % (mission_id, timeout))
            time.sleep(self.poll)
        raise RuntimeError('mission %s did not settle in %d steps' % (mission_id, max_steps))

    def _busy(self, mission_id):
        """Does the mission have a process running, or an execution about to?"""
        with self.db.read() as r:
            return any(x.entity.state in ('INTENT', 'STARTING', 'RUNNING', 'PAUSING',
                                          'STOPPING')
                       for x in rows.where(r, entities.Execution, mission_id=mission_id))

    def step(self, mission_id):
        """One unit of progress: {'changed', 'did', 'state', 'stop'}. `stop`
        (when nothing changed) says why, by the state the mission waits in."""
        try:
            did = self._step(self._mission(mission_id))
        except PolicyDenied as e:           # refused before any write (P3.5)
            recorded = None
            if e.specs is not None:         # a plan: the denial itself is recorded (P9 D12)
                recorded = self._do(authorization.record_plan_denial,
                                    policy=self.work.policy, missions=self.missions,
                                    mission_id=mission_id, specs=e.specs)
            state, changed = self._mission(mission_id).state, bool(recorded and
                                                                   recorded['recorded'])
            return {'mission_id': mission_id, 'changed': changed,
                    'did': 'plan_denied' if changed else None, 'state': state,
                    'stop': None if changed else 'policy_denied', 'denied': str(e),
                    'recorded': recorded}
        m = self._mission(mission_id)
        stop = STOPS.get(m.state, 'waiting')
        if (m.planning_blocked or {}).get('kind') == 'policy':
            stop = 'policy_denied'          # waits in place on a recorded denial (P9)
        return {'mission_id': mission_id, 'changed': did is not None, 'did': did,
                'state': m.state, 'stop': None if did else stop}

    def _step(self, m):
        if m.state in ('APPROVED', 'RESUMED', 'EXECUTING', 'VERIFYING', 'REVIEWING') \
                and self.manager.node.disarmed():
            # disarmed (P11 §13): nothing dispatches, resumes or advances until a
            # user device re-arms — P9 would deny every action, and a denial read
            # as a mission's failure is exactly what an e-stop must not cause
            return None
        if m.state == 'CREATED':
            self._do(self.missions.fire, mission_id=m.id, trigger=START,
                     reason='Archeus starts on the mission')
            return START
        if m.state == 'UNDERSTANDING':
            self._do(self.missions.understand, mission_id=m.id)     # from its intent (P7)
            return 'understood'
        if m.state == 'CONTEXT_GATHERING':
            self._do(self.missions.context_ready, mission_id=m.id)
            return 'context_ready'
        if m.state in ('REASONING', 'PLANNING', 'REPLANNING'):
            if self.brain is None:
                return None     # the planning worker's (P8): nothing for the engine to do
            if (m.planning_blocked or {}).get('kind') == 'policy':
                return None     # denied (P9): a policy change or the user moves it on
            if m.state == 'REPLANNING' and self._do(self.work.replan_budget_spent,
                                                    mission_id=m.id):
                return 'replan_budget_exhausted'        # judged before asking the brain
            plan = self.brain.call('plan.v1', m.objective,
                                   context={'mission_id': m.id, 'title': m.title})
            self._do(self.work.propose_plan, mission_id=m.id, plan=plan)
            return 'propose_plan'
        if m.state == 'APPROVED':
            self._do(self.missions.fire, mission_id=m.id, trigger='dispatch',
                     reason='the approved plan is dispatched')
            return 'dispatch'
        if m.state == 'EXECUTING':
            return self._execute(m)
        if m.state == 'VERIFYING':
            if self.verifier is None:
                # the verification worker records the criteria (P13 D15); the
                # engine only judges them
                return 'advance' if self._do(self.missions.advance,
                                             mission_id=m.id)['changed'] else None
            return self._verify_mission(m)
        if m.state == 'REVIEWING':
            return None if self.reviewer is None else self._review(m)
        return None

    # ── executing ──

    def _execute(self, m):
        """Verify, advance, release tasks, and dispatch what admission allows.
        Processes are the execution manager's; this never waits for one."""
        with self.db.read() as r:
            plan = active_plan(r, m.id)
            tasks = [t.entity for t in rows.where(r, entities.Task, plan_id=plan.entity.id)]
        for t in tasks:
            if t.state == 'VERIFYING' and self.verifier is not None:
                v = self.verifier.verify(Ref('task', t.id))
                self._do(self.work.record_task_verification, task_id=t.id, verdict=v.state,
                         verifier=v.verifier, independent=v.independent)
                return 'verify_task'
        if self._do(self.missions.advance, mission_id=m.id)['changed']:
            return 'advance'
        if self._do(self.work.ready_tasks, mission_id=m.id)['ready']:
            return 'ready_tasks'
        for t in tasks:
            if t.state == 'READY' and self._admit(m, t):
                return self._start(m, t)
        return None

    def _admit(self, m, t):
        """Admission (p11-design-gate §16): not disarmed, under the mission's
        parallelism, and no workspace conflict with live work of the project."""
        if self.manager.node.disarmed():
            return False
        with self.db.read() as r:
            live = [x.entity for x in rows.where(r, entities.Execution)
                    if x.entity.state not in _ENDED]
            mine = [x for x in live if x.mission_id == m.id]
            if len(mine) >= MISSION_PARALLEL:
                return False
            if m.project_id is None:
                return True
            others = []
            for x in live:
                xm = rows.get(r, entities.Mission, x.mission_id).entity
                if xm.project_id == m.project_id:
                    others.append(rows.get(r, entities.Task, x.task_id).entity)
        return not any(_conflict(t, o) for o in others)

    def _start(self, m, t):
        """Commit the dispatch (P9, P10, INTENT); the manager spawns it."""
        out = self._do(self.work.dispatch_task, task_id=t.id)
        if out['execution_id'] is None:
            # P9: not covered, or P10: a fallback asks -> the mission was blocked
            # on an approval; P10: nothing could run -> blocked
            return ('awaiting_approval' if out.get('authorization') or out.get('approval_id')
                    else 'no_route')
        return 'dispatch_task'

    def reconcile_orphans(self):
        """The boot sweep (p3.5b §18.1), P11's adopt-or-reconcile: every
        non-terminal execution a previous Core left, whatever its mission's
        state. Returns the execution ids it examined."""
        return self.manager.boot()

    # ── verifying, reviewing ──

    def _verify_mission(self, m):
        verdicts = []
        for i, c in enumerate(m.success_criteria):
            if c['check'] == 'automatic':
                v = self.verifier.verify(Ref('mission', m.id))
                verdicts.append({'criterion': i, 'verdict': v.state, 'verifier': v.verifier})
        out = self._do(self.work.verify_mission, mission_id=m.id, verdicts=verdicts)
        return 'verify_mission' if out['mission']['changed'] else None

    def _review(self, m):
        with self.db.read() as r:
            plan = active_plan(r, m.id)
            done = rows.where(r, entities.Review, plan_id=plan.entity.id)
        if any(x.entity.state == 'REJECTED' for x in done):
            return None             # a human decides (accept or request changes)
        rv = self.reviewer.review(m)
        self._do(self.work.record_review, mission_id=m.id, verdict=rv.verdict,
                 reviewer=rv.reviewer, independent=rv.independent)
        return 'review'

