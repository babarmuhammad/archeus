"""The walking skeleton (plan §31.1 P3.5): the smallest operating loop that
takes a mission from CREATED to a settled state over the real application
commands, the real database and the fake harness's real subprocess.

    CREATED -> start -> UNDERSTANDING -> understood (from its intent, P7)
    CONTEXT_GATHERING -> context_ready: the context package (P5) -> REASONING
    brain `plan.v1` -> Work.propose_plan -> PLANNING -> plan gate (Policy port)
        -> APPROVED | APPROVAL_REQUIRED on ASK (stops: a human decides)
        | DENY: nothing written, state unchanged (stops: `policy_denied`)
    REPLANNING: replan budget judged first -> BLOCKED, or a new plan as above
    APPROVED -> dispatch -> EXECUTING
    each task: deps_satisfied -> dispatch_task (Policy port, Router port, INTENT)
        -> adapter.start -> record_spawn -> wait -> record_exit -> verifier
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
here: intent (the intent worker, core/missions/intent.py, P7), the real planner (P8),
approvals bound to action hashes (P9), routing and accounts (P10), the
execution manager and node — adoption, pause, stop, timeouts, hand-off, the
process registry (P11) — and real verifiers and review (P13).
"""

import os
import time

from ..harnesses import base
from ..infra.db import rows
from ..infra.paths import ExecPaths
from .application.commands import active_plan
from .application.work import PolicyDenied
from .domain import entities, states
from .domain.values import Ref

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
    'estimated_cost': 'low',
    'tasks': [{'key': 'work', 'title': 'Do the work', 'kind': 'code_change',
               'action_classes': ['write_repo']}],
    'success_criteria': [{'text': 'the result passes its automatic check',
                          'check': 'automatic'}],
}
#: What the fake agent does for a task no scenario is scripted for.
DEFAULT_SCENARIO = [{'emit': {'type': 'result', 'summary': 'done'}}]

_ENDED = states.terminal('execution')


class Engine:
    """Drives missions on one open Database as the principal `actor`.

    `work` is `work.Work` (its `missions` carries the Policy port), `brain`,
    `verifier` and `reviewer` are ports, `registry` the adapter registry,
    `scenarios` maps a task key to the fake agent's steps."""

    def __init__(self, db, *, actor, work, brain, registry, verifier, reviewer,
                 scenarios=None, poll=0.02):
        self.db, self.actor, self.work = db, actor, work
        self.missions = work.missions
        self.brain, self.registry = brain, registry
        self.verifier, self.reviewer = verifier, reviewer
        self.scenarios = {} if scenarios is None else scenarios
        self.poll = poll
        self._running = {}      # execution id -> (adapter, handle): processes WE started

    def _do(self, command, **kwargs):
        return self.db.writer.execute(command, dict(kwargs, actor=self.actor))

    def _mission(self, mission_id):
        with self.db.read() as r:
            row = rows.get(r, entities.Mission, mission_id)
        if row is None:
            raise LookupError(mission_id)
        return row.entity

    def run(self, mission_id, *, max_steps=200):
        """Step until nothing changes; the last step's report says why."""
        for _ in range(max_steps):
            out = self.step(mission_id)
            if not out['changed']:
                return out
        raise RuntimeError('mission %s did not settle in %d steps' % (mission_id, max_steps))

    def step(self, mission_id):
        """One unit of progress: {'changed', 'did', 'state', 'stop'}. `stop`
        (when nothing changed) says why, by the state the mission waits in."""
        try:
            did = self._step(self._mission(mission_id))
        except PolicyDenied as e:           # refused before any write: nothing moved
            return {'mission_id': mission_id, 'changed': False, 'did': None,
                    'state': self._mission(mission_id).state, 'stop': 'policy_denied',
                    'denied': str(e)}
        state = self._mission(mission_id).state
        return {'mission_id': mission_id, 'changed': did is not None, 'did': did,
                'state': state, 'stop': None if did else STOPS.get(state, 'waiting')}

    def _step(self, m):
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
            return self._verify_mission(m)
        if m.state == 'REVIEWING':
            return self._review(m)
        return None

    # ── executing ──

    def _execute(self, m):
        with self.db.read() as r:
            executions = rows.where(r, entities.Execution, mission_id=m.id)
            plan = active_plan(r, m.id)
            tasks = [t.entity for t in rows.where(r, entities.Task, plan_id=plan.entity.id)]
        for e in (x.entity for x in executions):
            if e.state not in _ENDED:
                return self._finish(e) if e.id in self._running else self._reconcile(e)
        for t in tasks:
            if t.state == 'VERIFYING':
                v = self.verifier.verify(Ref('task', t.id))
                self._do(self.work.record_task_verification, task_id=t.id, verdict=v.state,
                         verifier=v.verifier, independent=v.independent)
                return 'verify_task'
        if self._do(self.missions.advance, mission_id=m.id)['changed']:
            return 'advance'
        if self._do(self.work.ready_tasks, mission_id=m.id)['ready']:
            return 'ready_tasks'
        for t in tasks:
            if t.state == 'READY':
                return self._start(m, t)
        return None

    def _start(self, m, t):
        """Commit INTENT, then spawn (outside any transaction), then record it."""
        out = self._do(self.work.dispatch_task, task_id=t.id)
        eid = out['execution_id']
        if eid is None:
            return 'no_route'
        adapter = self.registry.get(out['harness_id'])
        spec = base.ExecutionSpec(
            execution_id=eid, prompt='%s\n\n%s\n' % (m.objective, t.title),
            workdir=ExecPaths(eid).dir, attempt=out['attempt'],
            task_contract={'key': t.key, 'kind': t.kind,
                           'action_classes': list(t.action_classes),
                           'fake_scenario': self.scenarios.get(t.key, DEFAULT_SCENARIO)})
        try:
            handle = adapter.start(spec)
        except base.SpawnFailed:
            return self._reconcile(self._execution(eid))
        self._running[eid] = (adapter, handle)
        self._do(self.work.record_spawn, execution_id=eid, pid=handle.pid,
                 create_time=handle.create_time)
        return 'start_execution'

    def _finish(self, e):
        """Wait for a process this engine started, then record how it ended.
        ponytail: blocks until the process exits — pause, stop and timeouts are
        the execution manager's (P11)."""
        adapter, handle = self._running[e.id]
        while adapter.status(handle).state == 'running':
            time.sleep(self.poll)
        result = adapter.collect_result(handle)
        base.mark_ended(ExecPaths(e.id), result.exit_code)
        self._do(self.work.record_exit, execution_id=e.id, exit_reason=result.exit_reason,
                 exit_code=result.exit_code, summary=result.reported_summary,
                 output=bool(adapter.inspect(handle).events))
        del self._running[e.id]
        return 'finish_execution'

    def reconcile_orphans(self):
        """Reconcile every non-terminal execution this engine did not start,
        whatever state its mission is in — the boot sweep (p3.5b §18.1): at
        boot that is all of them, so an orphan under a PAUSED or otherwise
        settled mission is not left running until someone steps it. Each goes
        through the one `_reconcile`. One that fails does not stop the others
        from being reconciled; the first failure is raised after the sweep, so
        the caller still fails stop. Returns the reconciled execution ids."""
        with self.db.read() as r:
            orphans = [x.entity for x in rows.where(r, entities.Execution)
                       if x.entity.state not in _ENDED and x.entity.id not in self._running]
        done, failed = [], None
        for e in orphans:
            try:
                self._reconcile(e)
            except Exception as err:
                failed = failed or err
            else:
                done.append(e.id)
        if failed is not None:
            raise failed
        return done

    def _reconcile(self, e):
        """An execution nobody is watching: kill its process if one exists (pid
        + creation time, so a recycled pid is refused), tombstone it, record."""
        paths = ExecPaths(e.id)
        marker = os.path.exists(paths.spawning)
        pid = base.read_json(paths.pid)
        ended = os.path.exists(paths.ended)
        if pid is not None:
            try:
                self.registry.get(e.harness_id).stop(
                    base.ProcessHandle(e.id, pid['pid'], pid['create_time'], paths.dir),
                    grace_s=0.0)
            except base.StopRefused:
                pass    # the pid was recycled: our process has exited, the live one is not ours
        if marker and not ended:
            base.mark_ended(paths, None, reconciled=True)
        # a marker with a tombstone and no pid.json is a spawn that failed
        # before any process existed (base.spawn)
        self._do(self.work.reconcile, execution_id=e.id,
                 spawned=marker and (pid is not None or not ended))
        self._running.pop(e.id, None)
        return 'reconcile_execution'

    def _execution(self, eid):
        with self.db.read() as r:
            return rows.get(r, entities.Execution, eid).entity

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

