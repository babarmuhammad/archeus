"""The work a mission is made of (P3.5): plan, task, execution, verification,
review — as writer commands over the P3 transition.

Each method runs inside ONE writer transaction and moves entities only through
`lifecycle.fire` (so every move is an edge of the P1 table, audited by its
`<machine>.state_changed` event) or `commands.Missions` (so a mission moves
only through its P3 actions and guards). What belongs together commits
together: an execution's end and its task's response; a verification and the
move it decides; a review verdict and the mission's response to it.

Nothing here has a side effect outside the database. Calling the brain,
starting a process, waiting for it, running a verifier or a reviewer is the
engine's (archeus/core/engine.py), done between commands and recorded by them
— a process is never spawned inside a transaction (execution-architecture §1).

Policy is consulted through the Policy port, never by actor kind. ASK and DENY
are different answers and never share a path:

- DENY: the action is not permitted. `propose_plan` and `dispatch_task` refuse
  with `PolicyDenied` before writing anything — no plan, task or execution row,
  no approval request, and the mission's state is left where it was. (Only in
  EXECUTING does an existing edge stand for a denial: `advance` takes
  `unrecoverable` to FAILED.) No approval overrides a DENY.
- ASK: the plan gate (`Missions.snapshot`, P3) refuses `plan_auto_approved` and
  the mission waits in APPROVAL_REQUIRED for a human `approve`.

P9 (p9-design-gate §11, §12): a refusal still writes nothing, and the denial
is recorded by the command that responds to it (`authorization.
record_plan_denial` for the plan gate; `unrecoverable` for a dispatch).
`dispatch_task` asks `authorization.check_dispatch` whether this task of this
exact version may run under the CURRENT policy: an ASK nothing covers blocks
the mission and asks for the task, so a policy that turns to ASK after an
automatic approval is asked again.
"""

import time
from dataclasses import replace

from ..domain import entities, guards, ids
from ..domain.actions import Action
from ..domain.events import new_event
from ..domain.values import Ref
from ..planning import validate
from . import authorization, lifecycle, resources
from .commands import active_plan

#: the task fields a plan spec may carry (its dispatch contract, P8 §7.1)
_TASK_CONTRACT = frozenset(entities.Task.frozen_fields()) - {'plan_id', 'mission_id'}
#: the plan's own lists, copied as proposed (never derived by Core)
_PLAN_LISTS = ('inputs', 'coverage', 'assumptions', 'questions', 'risks', 'refs')

#: Task states after which its dependants may start.
DONE = ('SUCCEEDED', 'SKIPPED')
#: What an end of an execution means for its process record.
_EXIT = {'ok': 'exited_success', 'error': 'exited_error'}
_VERDICT = {'PASSED': 'all_checks_pass', 'FAILED': 'a_check_fails'}
_REVIEW = {'accept': 'verdict_accept', 'changes_requested': 'verdict_changes',
           'reject': 'verdict_reject'}


class PolicyDenied(PermissionError):
    """The Policy port DENIED an action class a task needs (`423 policy_denied`).
    Raised before anything is written, so the transaction commits nothing."""

    def __init__(self, decision, task_key, specs=None):
        super().__init__('policy denies %s on task %s: %s'
                         % (decision.action.action_class, task_key, decision.reason))
        # the validated task specs of a refused plan, for the command that
        # records the denial (P9 D12); None for a refused dispatch
        self.decision, self.task_key, self.specs = decision, task_key, specs


def _require(machine, row, states, verb):
    if row.entity.state not in states:
        raise lifecycle.IllegalTrigger(machine, row.entity.state, verb,
                                       '%s needs %s' % (verb, ' or '.join(states)))


class Work:
    """Commands for the work under a mission. `missions` is the P3 `Missions`
    (its Policy port is the plan gate's); `router` picks the harness."""

    def __init__(self, *, missions, router):
        self.missions, self.policy, self.router = missions, missions.policy, router

    def _event(self, tx, type_, subject, actor, mission, payload):
        return tx.append(new_event(type_, subject, actor, payload=payload,
                                   workspace=mission.workspace_id, project=mission.project_id))

    def _fire(self, tx, cls, entity_id, trigger, actor, reason, fields=None):
        return lifecycle.fire(tx, cls, entity_id, trigger, actor=actor, reason=reason,
                              fields=fields)[0]

    def _refuse_denied(self, tx, mission, actor, specs):
        """Raise PolicyDenied if the policy DENIES any item (declared or
        implied, P9 §3.3) of any task of a proposed plan."""
        items, _ctx = authorization.first_denial(self.policy, tx.conn, mission, specs,
                                                 now=tx.now, actor=actor)
        for r in items:
            if r['decision'] == 'DENY':
                raise PolicyDenied(entities.PolicyDecision(
                    id=ids.new_id('policy_decision'), decision='DENY', reason=r['reason'],
                    action=Action(action_class=r['class'], target='task:%s' % r['task'])),
                    r['task'], specs=[dict(s) for s in specs])

    # ── plan ──

    def propose_plan(self, tx, *, actor, mission_id, plan, round_seq=None,
                     route_decision_id=None, context_package_id=None, explicit=(), asked=()):
        """Record a proposed plan as the next PlanVersion with its tasks, then
        take the mission's decision on it — all in one transaction, so a plan is
        never left undecided. From REASONING the mission first moves to PLANNING
        (`reasoned`); a mission that has no success criteria takes the plan's,
        marked `inferred`.

        From REPLANNING the replan budget is judged FIRST, on the plan still in
        force (the one being replaced): `max_replans` counts replans after the
        initial plan, so the guard's `plan_version - 1` is the replans already
        used. Over budget, the mission goes BLOCKED and no plan is recorded.
        A plan the policy DENIES is refused before anything is written.

        P8 (p8-design-gate §5-§7, §11): Core's validator judges the tasks first
        (a plan that fails it is refused, nothing written); Core computes the
        cost band and adds the serialisation edges (recorded in `serialised`);
        the version is inserted DRAFT and takes the guarded `ready` edge to
        PROPOSED — ready for the POLICY stage, never approved here — and the
        version it replaces is SUPERSEDED in the same transaction. The decision
        that follows is the P3 plan gate's, over the Policy port, unchanged.
        `explicit`/`asked` are the requirement handles the planner's coverage
        is judged on (D16); the planner's provenance comes with it."""
        m = lifecycle.load(tx, entities.Mission, mission_id)
        _require('mission', m, ('REASONING', 'PLANNING', 'REPLANNING'), 'propose_plan')
        if m.entity.state == 'REPLANNING':
            spent = self.replan_budget_spent(tx, actor=actor, mission_id=mission_id)
            if spent is not None:
                return {'plan_id': None, 'plan_version': None, 'mission': spent}
        if 'estimated_cost' in plan:
            raise ValueError('a plan does not state its cost band: Core computes it (D9)')
        specs = [dict(s, depends_on=tuple(s.get('depends_on', ()))) for s in plan.get('tasks') or ()]
        criteria = m.entity.success_criteria or tuple(plan.get('success_criteria') or ())
        found = validate.problems(specs, criteria=criteria, explicit=explicit, asked=asked)
        if found:
            raise ValueError('the plan is not valid: %s' % '; '.join(found))
        specs, serialised = validate.serialise(validate.order(specs))
        self._refuse_denied(tx, m.entity, actor, specs)
        prev = active_plan(tx.conn, mission_id)
        pid = ids.new_id('plan')
        tasks = [entities.Task(
            id=ids.new_id('task'), plan_id=pid, mission_id=mission_id,
            **{k: v for k, v in spec.items() if k in _TASK_CONTRACT}) for spec in specs]
        p = entities.Plan(
            id=pid, mission_id=mission_id,
            plan_version=1 if prev is None else prev.entity.plan_version + 1,
            summary=plan.get('summary', ''), estimated_cost=validate.cost_band(specs),
            supersedes_plan_id=None if prev is None else prev.entity.id, round_seq=round_seq,
            route_decision_id=route_decision_id, context_package_id=context_package_id,
            serialised=tuple(serialised),
            **{k: tuple(plan.get(k) or ()) for k in _PLAN_LISTS},
            rollback=plan.get('rollback'))
        p = replace(p, digest=validate.digest(p, tasks))
        tx.insert(p, actor=actor)
        self._event(tx, 'plan.created', Ref('plan', p.id), actor, m.entity, {
            'mission_id': mission_id, 'plan_version': p.plan_version,
            'supersedes_plan_id': p.supersedes_plan_id, 'round_seq': round_seq,
            'digest': p.digest, 'route_decision_id': route_decision_id,
            'context_package_id': context_package_id, 'tasks': len(tasks),
            'serialised': len(serialised)})
        for t in tasks:
            tx.insert(t, actor=actor)
            self._event(tx, 'task.created', Ref('task', t.id), actor, m.entity,
                        {'plan_id': p.id, 'key': t.key})

        def judged(row):            # re-read and re-judged from the rows just written
            stored = [r.entity for r in tx.where(entities.Task, plan_id=row.entity.id)]
            again = validate.problems([t.to_dict() for t in stored], criteria=criteria,
                                      explicit=explicit, asked=asked)
            return guards.PlanFacts(problems=tuple(again),
                                    digest=validate.digest(row.entity, stored))
        lifecycle.fire(tx, entities.Plan, p.id, 'ready', actor=actor, facts=judged,
                       reason='plan v%d validated by Core: ready for the policy stage'
                       % p.plan_version)
        if prev is not None and prev.entity.state in ('PROPOSED', 'APPROVED'):
            lifecycle.fire(tx, entities.Plan, prev.entity.id, 'superseded', actor=actor,
                           reason='replaced by plan v%d' % p.plan_version)
        if prev is not None:
            # P9 D14: nothing an approval covers carries to the next version
            authorization.supersede_for(tx, actor=actor, plan_id=prev.entity.id,
                                        replaced_by=p.plan_version)
        if m.entity.planning_blocked is not None:
            tx.update(entities.Mission, mission_id, {'planning_blocked': None}, actor=actor)
            self._event(tx, 'mission.updated', Ref('mission', mission_id), actor, m.entity,
                        {'fields': ['planning_blocked'], 'cleared': True, 'plan_id': p.id})
        if m.entity.state == 'REASONING':
            inferred = None
            if not m.entity.success_criteria and plan.get('success_criteria'):
                inferred = tuple(dict(c, origin='inferred') for c in plan['success_criteria'])
            self.missions.reasoned(tx, actor=actor, mission_id=mission_id,
                                   reason='plan v%d proposed' % p.plan_version,
                                   success_criteria=inferred)
        # the decision on THIS plan: auto-approved, or asked (the budget was
        # judged above, on the plan it replaces — never again on this one)
        try:
            decided = self.missions.fire(tx, actor=actor, mission_id=mission_id,
                                         trigger='plan_auto_approved',
                                         reason='plan v%d approved within policy' % p.plan_version)
        except lifecycle.GuardFailed as e:
            decided = self.missions.fire(tx, actor=actor, mission_id=mission_id,
                                         trigger='plan_needs_approval', reason=e.result.reason)
        return {'plan_id': p.id, 'plan_version': p.plan_version, 'digest': p.digest,
                'mission': decided}

    def replan_budget_spent(self, tx, *, actor, mission_id):
        """REPLANNING -> BLOCKED if the replan budget is spent (judged on the plan
        in force); None, writing nothing, while replans remain."""
        try:
            return self.missions.fire(tx, actor=actor, mission_id=mission_id,
                                      trigger='replan_budget_exhausted',
                                      reason='no replan left for this mission')
        except lifecycle.GuardFailed:
            return None

    # ── tasks ──

    def ready_tasks(self, tx, *, actor, mission_id):
        """PENDING tasks of the plan in force whose dependencies are done -> READY."""
        m = lifecycle.load(tx, entities.Mission, mission_id)
        _require('mission', m, ('EXECUTING',), 'ready_tasks')
        tasks = tx.where(entities.Task, plan_id=active_plan(tx.conn, mission_id).entity.id)
        done = {r.entity.key for r in tasks if r.entity.state in DONE}
        ready = [r.entity.id for r in tasks if r.entity.state == 'PENDING'
                 and set(r.entity.depends_on) <= done]
        for tid in ready:
            self._fire(tx, entities.Task, tid, 'deps_satisfied', actor, 'dependencies done')
        # a task routing blocked blocked its mission too (P10): the mission is
        # EXECUTING again only because it was resumed, so the task routes again
        blocked = [r.entity.id for r in tasks if r.entity.state == 'BLOCKED']
        for tid in blocked:
            self._fire(tx, entities.Task, tid, 'unblock', actor,
                       'the mission was resumed: routing again')
        return {'ready': ready + blocked}

    def dispatch_task(self, tx, *, actor, task_id, now=None):
        """READY -> ROUTING -> RUNNING and a new Execution in INTENT, committed
        before any process exists (state-machines §4). Refused with
        PolicyDenied, writing nothing, when the policy DENIES an action class
        of the task. No eligible resource -> the task is BLOCKED."""
        t = lifecycle.load(tx, entities.Task, task_id).entity
        m = lifecycle.load(tx, entities.Mission, t.mission_id).entity
        if m.state != 'EXECUTING':
            raise lifecycle.IllegalTrigger('task', t.state, 'dispatch',
                                           'the mission is %s, not EXECUTING' % m.state)
        plan = active_plan(tx.conn, m.id).entity
        if t.plan_id != plan.id:
            raise lifecycle.IllegalTrigger('task', t.state, 'dispatch',
                                           'the task belongs to a superseded plan')
        auth = authorization.check_dispatch(tx, actor=actor, policy=self.policy,
                                            missions=self.missions, mission=m, plan=plan, task=t)
        if auth['outcome'] != 'covered':
            return {'task_id': task_id, 'execution_id': None, 'state': t.state,
                    'authorization': auth}
        self._fire(tx, entities.Task, task_id, 'dispatch', actor, 'dispatched')
        # P10: only an authorised task reaches the router, which checks that
        # authorisation again and records its decision in this transaction
        route = self.router.route(Ref('task', task_id), time.time() if now is None else now,
                                  tx=tx, actor=actor, authorization=auth, mission=m,
                                  plan=plan, task=t)
        result = route.result or ('selected' if route.selected else 'blocked')
        rd = route.id if route.decided_by == 'router' else None
        if result == 'ask':
            self._fire(tx, entities.Task, task_id, 'route_needs_approval', actor,
                       route.explanation)
            a, _new = resources.request_route(tx, actor=actor, mission=m, plan=plan,
                                              task=t, route=route)
            self.missions._fire(tx, m.id, 'block', actor=actor,
                                reason='waiting for your approval to run task %s on %s '
                                '(approval %s)' % (t.key, route.account_id or route.account_ref,
                                                   a.id))
            return {'task_id': task_id, 'execution_id': None, 'state': 'AWAITING_APPROVAL',
                    'route_decision_id': rd, 'approval_id': a.id}
        if result == 'blocked':
            why = route.explanation or 'no eligible resource'
            self._fire(tx, entities.Task, task_id, 'no_eligible_resource', actor, why)
            self.missions._fire(tx, m.id, 'block', actor=actor, reason=why)
            return {'task_id': task_id, 'execution_id': None, 'state': 'BLOCKED',
                    'route_decision_id': rd}
        self._fire(tx, entities.Task, task_id, 'routed', actor,
                   route.explanation or 'routed to %s' % route.selected)
        e = entities.Execution(id=ids.new_id('execution'), task_id=task_id, mission_id=m.id,
                               attempt=len(tx.where(entities.Execution, task_id=task_id)) + 1,
                               harness_id=route.harness_id or route.selected,
                               route_decision_id=rd, account_id=route.account_id,
                               model=route.model, effort=route.effort)
        tx.insert(e, actor=actor)
        ev = self._event(tx, 'execution.intent', Ref('execution', e.id), actor, m,
                         {'task_id': task_id, 'attempt': e.attempt, 'harness_id': e.harness_id,
                          'account_id': e.account_id, 'route_decision_id': rd})
        return {'task_id': task_id, 'execution_id': e.id, 'attempt': e.attempt,
                'harness_id': e.harness_id, 'account_id': e.account_id, 'model': e.model,
                'effort': e.effort, 'route_decision_id': rd, 'seq': ev.seq}

    def _task_after(self, tx, actor, execution, ok, failure_class='execution'):
        """The task's response to its execution ending (one transaction with it)."""
        t = lifecycle.load(tx, entities.Task, execution.task_id).entity
        if ok:
            return self._fire(tx, entities.Task, t.id, 'execution_succeeded', actor,
                              'execution %s ended ok; verifying' % execution.id)
        return self._failed(tx, actor, t, 'execution_failed_retry', 'execution_failed_final',
                            failure_class, 'execution %s did not succeed' % execution.id)

    def _failed(self, tx, actor, t, retry, final, failure_class, why):
        """Retry while attempts remain (a retry is a new Execution), else FAILED."""
        if len(tx.where(entities.Execution, task_id=t.id)) < t.max_attempts:
            return self._fire(tx, entities.Task, t.id, retry, actor, why + '; retrying')
        return self._fire(tx, entities.Task, t.id, final, actor,
                          why + '; %d attempts used' % t.max_attempts,
                          {'failure_class': failure_class})

    # ── executions ──

    def record_spawn(self, tx, *, actor, execution_id, pid, create_time):
        """INTENT -> STARTING: the process exists (pid + creation time)."""
        e = self._fire(tx, entities.Execution, execution_id, 'spawn', actor,
                       'process %d started' % pid,
                       {'pid': pid, 'create_time': create_time}).entity
        m = lifecycle.load(tx, entities.Mission, e.mission_id).entity
        ev = self._event(tx, 'execution.started', Ref('execution', e.id), actor, m,
                         {'pid': pid, 'create_time': create_time, 'task_id': e.task_id,
                          'attempt': e.attempt, 'harness_id': e.harness_id,
                          'account_id': e.account_id, 'model': e.model})
        return {'execution_id': e.id, 'state': e.state, 'seq': ev.seq}

    def record_exit(self, tx, *, actor, execution_id, exit_reason, exit_code, summary='',
                    output=True, usage=None):
        """The process exited: STARTING -> RUNNING (it wrote output) -> ENDED_OK |
        ENDED_ERROR, `execution.ended`, and the task's response, in one
        transaction. ENDED_OK sends the task to VERIFYING — never to SUCCEEDED.
        A second report of the same end is an invalid transition: nothing changes."""
        if exit_reason not in _EXIT:
            raise ValueError('exit_reason is ok or error, not %r' % (exit_reason,))
        row = lifecycle.load(tx, entities.Execution, execution_id)
        if row.entity.state == 'STARTING':
            if not output:
                return self._lost(tx, actor, row.entity, 'the process exited without output')
            self._fire(tx, entities.Execution, execution_id, 'first_output', actor,
                       'the process wrote output')
        e = self._fire(tx, entities.Execution, execution_id, _EXIT[exit_reason], actor,
                       'exit code %s' % exit_code,
                       {'exit_reason': exit_reason, 'exit_code': exit_code,
                        'summary': summary}).entity
        if usage and e.route_decision_id is not None:
            # attributable truth (P10): what it consumed, against where it was routed
            u = {k: usage[k] for k in ('tokens_in', 'tokens_out', 'cache_read', 'cache_write',
                                       'cost_usd') if isinstance(usage.get(k), (int, float))
                 and not isinstance(usage.get(k), bool)}
            tx.insert(entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=e.id,
                                           route_decision_id=e.route_decision_id,
                                           account_id=e.account_id, **u), actor=actor)
        return self._ended(tx, actor, e, exit_reason == 'ok')

    def _ended(self, tx, actor, e, ok):
        m = lifecycle.load(tx, entities.Mission, e.mission_id).entity
        ev = self._event(tx, 'execution.ended', Ref('execution', e.id), actor, m,
                         {'exit_reason': e.exit_reason, 'exit_code': e.exit_code,
                          'task_id': e.task_id, 'attempt': e.attempt})
        t = self._task_after(tx, actor, e, ok).entity
        return {'execution_id': e.id, 'state': e.state, 'task_state': t.state, 'seq': ev.seq}

    #: How reconciliation reaches LOST from each live state (state-machines §4).
    _TO_LOST = {'INTENT': 'spawn_unconfirmed', 'STARTING': 'start_timeout',
                'RUNNING': 'heartbeat_missing'}

    def _lost(self, tx, actor, e, why):
        if e.state != 'LOST':
            self._fire(tx, entities.Execution, e.id, self._TO_LOST[e.state], actor, why)
        e = self._fire(tx, entities.Execution, e.id, 'reconciled_kill', actor, why,
                       {'exit_reason': 'lost'}).entity
        return self._ended(tx, actor, e, False)

    def reconcile(self, tx, *, actor, execution_id, spawned):
        """An execution no running Core is watching (it was started by a Core
        that died). The caller has already killed its process, if any, by pid +
        creation time. INTENT that never spawned -> ABANDONED; anything else ->
        LOST -> ENDED_KILLED. Either way the attempt is over and the task
        retries with a NEW execution or fails; a process is never re-attached or
        re-spawned under the same attempt (adoption is the execution manager's,
        P11)."""
        row = lifecycle.load(tx, entities.Execution, execution_id)
        e = row.entity
        if e.state == 'INTENT' and not spawned:
            e = self._fire(tx, entities.Execution, execution_id, 'spawn_failed', actor,
                           'no process was started', {'exit_reason': 'abandoned'}).entity
            t = self._task_after(tx, actor, e, False)
            return {'execution_id': e.id, 'state': e.state, 'task_state': t.entity.state}
        if e.state not in self._TO_LOST and e.state != 'LOST':
            raise lifecycle.IllegalTrigger('execution', e.state, 'reconcile',
                                           'the execution has already ended')
        return self._lost(tx, actor, e, 'Core restarted; nothing was watching this process')

    # ── verification and review ──

    def _verify(self, tx, actor, mission, v, verdict):
        if verdict not in _VERDICT:
            raise ValueError('a verdict is PASSED or FAILED, not %r' % (verdict,))
        tx.insert(v, actor=actor)
        self._event(tx, 'verification.created', Ref('verification', v.id), actor, mission,
                    {'subject': {'kind': v.subject.kind, 'id': v.subject.id},
                     'criterion': v.criterion, 'plan_id': v.plan_id})
        self._fire(tx, entities.Verification, v.id, 'start', actor, 'verifier %s' % v.verifier)
        return self._fire(tx, entities.Verification, v.id, _VERDICT[verdict], actor,
                          'verifier %s: %s' % (v.verifier, verdict)).entity

    def record_task_verification(self, tx, *, actor, task_id, verdict, verifier,
                                 independent=False):
        """A VERIFYING task's checks, recorded with its move: SUCCEEDED when they
        pass; otherwise a retry (a new execution) or FAILED."""
        t = lifecycle.load(tx, entities.Task, task_id)
        _require('task', t, ('VERIFYING',), 'record_task_verification')
        t = t.entity
        m = lifecycle.load(tx, entities.Mission, t.mission_id).entity
        v = self._verify(tx, actor, m, entities.Verification(
            id=ids.new_id('verification'), subject=Ref('task', task_id), verifier=verifier,
            independent=independent, plan_id=t.plan_id), verdict)
        if v.state == 'PASSED':
            t = self._fire(tx, entities.Task, task_id, 'checks_passed', actor,
                           'verification %s passed' % v.id).entity
        else:
            t = self._failed(tx, actor, t, 'checks_failed_retry', 'checks_failed_final',
                             'verification', 'verification %s failed' % v.id).entity
        return {'task_id': task_id, 'state': t.state, 'verification_id': v.id}

    def verify_mission(self, tx, *, actor, mission_id, verdicts):
        """A VERIFYING mission's automatic criteria — `verdicts` is
        `[{criterion, verdict, verifier}]`, one per automatic criterion — each
        recorded as a Verification of the plan in force, then the mission's P3
        `advance` in the same transaction: `verification_failed`,
        `awaiting_human_acceptance` or `verified`, judged on exactly these rows."""
        m = lifecycle.load(tx, entities.Mission, mission_id)
        _require('mission', m, ('VERIFYING',), 'verify_mission')
        m = m.entity
        auto = {i for i, c in enumerate(m.success_criteria) if c['check'] == 'automatic'}
        if sorted(v['criterion'] for v in verdicts) != sorted(auto):
            raise ValueError('verdicts must cover each automatic criterion once: %s'
                             % sorted(auto))
        plan_id = active_plan(tx.conn, mission_id).entity.id
        made = [self._verify(tx, actor, m, entities.Verification(
            id=ids.new_id('verification'), subject=Ref('mission', mission_id),
            verifier=v['verifier'], plan_id=plan_id, criterion=v['criterion']),
            v['verdict']).id for v in verdicts]
        return {'verifications': made,
                'mission': self.missions.advance(tx, actor=actor, mission_id=mission_id)}

    def record_review(self, tx, *, actor, mission_id, verdict, reviewer, independent=False):
        """A REVIEWING mission's review, recorded with the mission's response:
        `accept` -> COMPLETED through the P3 `accept`; `changes_requested` ->
        REPLANNING; `reject` leaves the mission in REVIEWING (the mission
        machine has no edge for it) for a human to decide. Review is not
        verification: REVIEWING is reachable only through `verified`."""
        m = lifecycle.load(tx, entities.Mission, mission_id)
        _require('mission', m, ('REVIEWING',), 'record_review')
        if verdict not in _REVIEW:
            raise ValueError('a review verdict is accept, changes_requested or reject')
        r = entities.Review(id=ids.new_id('review'), mission_id=mission_id, reviewer=reviewer,
                            independent=independent,
                            plan_id=active_plan(tx.conn, mission_id).entity.id)
        tx.insert(r, actor=actor)
        self._event(tx, 'review.requested', Ref('review', r.id), actor, m.entity,
                    {'mission_id': mission_id, 'plan_id': r.plan_id})
        self._fire(tx, entities.Review, r.id, 'start', actor, 'reviewer %s' % reviewer)
        self._fire(tx, entities.Review, r.id, _REVIEW[verdict], actor,
                   'reviewer %s: %s' % (reviewer, verdict), {'verdict': verdict})
        reason = 'review %s: %s' % (r.id, verdict)
        out = None
        if verdict == 'accept':
            out = self.missions.accept(tx, actor=actor, mission_id=mission_id, reason=reason)
        elif verdict == 'changes_requested':
            out = self.missions.request_changes(tx, actor=actor, mission_id=mission_id,
                                                reason=reason)
        return {'review_id': r.id, 'verdict': verdict, 'mission': out}
