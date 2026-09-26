"""Authorisation (P9, p9-design-gate §8-§12, §17): the commands that turn the
policy engine's answers into recorded decisions and approvals, and check them.

Each public command runs inside the caller's writer transaction; nothing here
has a side effect outside the database, and nothing here routes, dispatches a
process, executes, verifies or reviews (§14). The engine is the Policy port
(core/policy/engine.py, pure); this module gathers what it reads (`context`),
records what it answered (`PolicyDecision`, immutable), asks the user
(`Approval`) and re-checks every approval at every use (§8.4):

    plan gate   record_plan_decision   (from Missions._fire, the one path)
                record_plan_denial     (the response to a plan-gate DENY)
    dispatch    check_dispatch         (from Work.dispatch_task)
    decide      decide / withdraw      (a user device; a cancelled mission)
    lifetime    supersede_for / expire_due
    action      evaluate_action        (the action stage; its caller is P11's hook)
    policy      create_rule / retire_rule / set_profile / simulate

`action_hash` is the identity of the exact thing authorised and never
contains the policy version (D7); the policy version is recorded beside it,
and every use evaluates the CURRENT policy again — an approval is never
valid merely because it exists.
"""

import hashlib
import json
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ...infra import paths
from ...infra.db import rows
from ...infra.eventlog import outbox
from ..domain import actions, entities, guards, ids
from ..domain.actions import Action
from ..domain.events import new_event
from ..domain.values import Ref
from ..policy import rules as R
from . import lifecycle

#: How long a request may wait for its decision (domain-model §9.3, D8).
TTL = {'plan': timedelta(hours=24), 'task': timedelta(hours=24),
       'action': timedelta(hours=2)}
LIVE = ('PENDING', 'APPROVED')
#: devices paired from outside this machine (P15); before P15 every device is
#: local, and a local device satisfies step-up (D16)
PAIRED_PLATFORMS = ('ios', 'android')
_DECIDED = {'approve': 'APPROVED', 'reject': 'REJECTED', 'request_changes': 'REJECTED'}


class NotPermitted(PermissionError):
    """The principal may not do this (`403 not_permitted`, D22)."""


class NotEligible(RuntimeError):
    """The approval exists and may not be decided now (`409
    approval_not_eligible`): expired, superseded, stale, digest mismatch,
    or its mission is no longer waiting on it."""

    def __init__(self, approval_id, why, detail=''):
        super().__init__('approval %s is not eligible: %s%s'
                         % (approval_id, why, (' (%s)' % detail) if detail else ''))
        self.approval_id, self.why, self.detail = approval_id, why, detail


# ── inputs ──────────────────────────────────────────────────────────────────

def _iso(dt):
    return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _parse(ts):
    return datetime.fromisoformat(ts.replace('Z', '+00:00'))


def _plus(now, delta):
    return _iso(_parse(now) + delta)


def owner(conn):
    got = rows.where(conn, entities.User)
    return got[0].entity if got else None


def user_rules(conn):
    """The active user rules as the engine's rule dicts."""
    return [R.from_entity(r.entity) for r in rows.where(conn, entities.PolicyRule)
            if r.entity.retired_at is None]


def policy_version(rules):
    """sha256 over the active user rules, the profiles and the engine (§7.2):
    recorded on every decision and approval, never part of an action_hash."""
    body = {'rules': sorted(rules, key=lambda r: r['id']), 'profiles': R.PROFILES_VERSION,
            'engine': R.ENGINE_VERSION}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode('utf-8')).hexdigest()


def estop_armed():
    return os.path.exists(paths.stop_sentinel())


def context(conn, mission, *, stage, now, task=None, actor=None, plan=None,
            task_classes=None, extra_rules=(), unclassified=False):
    """What the engine reads (§3.1), gathered from *conn* — a transaction's
    connection, so an answer is never judged on other rows than the ones the
    move changes. The P3.5 keys (mission_id, …) stay for the stub policies."""
    u = owner(conn)
    rules = user_rules(conn) + [dict(r) for r in extra_rules]
    return {
        'stage': stage, 'now': now, 'estop': estop_armed(), 'unclassified': unclassified,
        'chain': {'USER': u.id if u else None, 'WORKSPACE': mission.workspace_id,
                  'PROJECT': mission.project_id, 'MISSION': mission.id,
                  'TASK': task.id if task is not None else None},
        'profiles': {'USER': u.autonomy_profile if u else 'standard',
                     'MISSION': mission.autonomy_profile},
        'rules': rules, 'policy_version': policy_version(rules),
        'task_classes': task_classes,
        'mission_id': mission.id, 'workspace_id': mission.workspace_id,
        'project_id': mission.project_id,
        'task_id': task.id if task is not None else None,
        'plan_version': None if plan is None else plan.plan_version,
        'actor': None if actor is None else {'kind': actor.kind, 'id': actor.id}}


def task_items(key, action_classes, capabilities=(), touches=()):
    """[(class, implied_by, Action)]: the task's declared classes and the ones
    its capabilities imply, as plan-level canonical actions (§3.3, D6)."""
    p = tuple(touches or ()) or None
    return [(c, by, Action(action_class=c, target='task:%s' % key, paths=p))
            for c, by in R.implied(action_classes, capabilities)]


def items_of(task):
    return task_items(task.key, task.action_classes, task.capabilities_required, task.touches)


def judge(policy, action, ctx):
    """The port's answer as an item record. A stub port (P1/P3.5) answers
    only a decision and a reason; the engine answers everything that led to it."""
    d = policy.evaluate(action, ctx)
    got = dict(d.items[0]) if d.items else {
        'class': action.action_class, 'action': action.canonical_dict(), 'matched': [],
        'effective': [], 'deciding_rule': None, 'conflicts': [], 'boundary': None,
        'checks': None, 'step_up': False}
    got.update(decision=d.decision, reason=d.reason)
    return got


def evaluate_task(policy, conn, mission, task_key, action_classes, *, now, task=None,
                  capabilities=(), touches=(), actor=None, plan=None, stage='plan'):
    """Every item of one task, judged (plan and dispatch stages)."""
    items = task_items(task_key, action_classes, capabilities, touches)
    classes = [c for c, _b, _a in items]
    ctx = context(conn, mission, stage=stage, now=now, task=task, actor=actor, plan=plan,
                  task_classes=None if stage == 'plan' else classes)
    out = []
    for c, by, a in items:
        r = judge(policy, a, ctx)
        r.update(task=task_key, task_id=task.id if task is not None else None, implied_by=by)
        out.append(r)
    return out, ctx


# ── identity (§7) ───────────────────────────────────────────────────────────

def _tasks(conn, plan):
    return [r.entity for r in rows.where(conn, entities.Task, plan_id=plan.id)]


def intact(conn, plan):
    """The plan's content recomputed from its rows matches its digest (§10.2)."""
    from ..planning import validate
    return bool(plan.digest) and validate.digest(plan, _tasks(conn, plan)) == plan.digest


def bind(plan, task=None, execution_id=None):
    return actions.binding(mission_id=plan.mission_id, plan_id=plan.id,
                           plan_version=plan.plan_version, plan_digest=plan.digest,
                           task_id=None if task is None else task.id,
                           task_key=None if task is None else task.key,
                           execution_id=execution_id)


def plan_items(conn, plan):
    return [actions.item(t.key, a) for t in sorted(_tasks(conn, plan), key=lambda t: t.key)
            for _c, _b, a in items_of(t)]


def plan_hash(conn, plan):
    return actions.action_hash('plan', bind(plan), plan_items(conn, plan))


def task_hash(plan, task):
    return actions.action_hash('task', bind(plan, task),
                               [actions.item(task.key, a) for _c, _b, a in items_of(task)])


def live_approval(conn, h):
    got = [r for r in rows.where(conn, entities.Approval, action_hash=h)
           if r.entity.state in LIVE]
    return got[-1] if got else None


def plan_approval_state(conn, plan):
    """The state of the approval of exactly *plan* (hash recomputed from its
    rows), or None: what the mission's `approve` guard reads (D10)."""
    if plan is None or not plan.digest or not intact(conn, plan):
        return None
    got = rows.where(conn, entities.Approval, action_hash=plan_hash(conn, plan))
    return got[-1].entity.state if got else None


def current(conn, mission, plan):
    """(current, why): P8's context currency, and the log still reaching back
    to the package — a pruned log is unknown, so stale (§10.2, X24)."""
    from ..planning import planner
    if plan.context_package_id is None:
        return True, 'planned without a recorded context package'
    pkg = rows.get(conn, entities.ContextPackage, plan.context_package_id)
    if pkg is not None and outbox.floor(conn) > pkg.entity.as_of_seq:
        return False, 'the event log no longer reaches back to its context package'
    return planner.currency(conn, mission, plan.context_package_id)


# ── records ─────────────────────────────────────────────────────────────────

def _slim(item):
    """An item as recorded: its rules by id (their contents are in
    `matched_rules`), everything else as judged."""
    out = {k: v for k, v in item.items() if k != 'matched'}
    out['matched'] = [r['id'] for r in item.get('matched') or ()]
    return out


def record(tx, *, actor, stage, mission, decision, outcome, items, reason, plan=None,
           task=None, execution_id=None, action=None, h=None, ctx=None, cost=None,
           approval_id=None, subject=None):
    """Insert one immutable PolicyDecision and its event (§9)."""
    matched, seen = [], set()
    for it in items:
        for r in it.get('matched') or ():
            if r['id'] not in seen:
                seen.add(r['id'])
                matched.append(r)
    ctx = ctx or {}
    d = entities.PolicyDecision(
        id=ids.new_id('policy_decision'), decision=decision, action=action, reason=reason,
        stage=stage, subject=subject or (Ref('task', task.id) if task is not None else
                                         Ref('plan', plan.id) if plan is not None else
                                         Ref('mission', mission.id)),
        mission_id=mission.id, plan_id=None if plan is None else plan.id,
        plan_version=None if plan is None else plan.plan_version,
        plan_digest=None if plan is None else plan.digest,
        task_id=None if task is None else task.id, execution_id=execution_id,
        action_hash=h, outcome=outcome, items=tuple(_slim(i) for i in items),
        matched_rules=tuple(matched), cost=cost, profiles=ctx.get('profiles'),
        estop=bool(ctx.get('estop')), principal={'kind': actor.kind, 'id': actor.id},
        policy_version=ctx.get('policy_version'), engine_version=str(R.ENGINE_VERSION),
        approval_id=approval_id)
    tx.insert(d, actor=actor)
    tx.append(new_event(
        'policy_decision.created', Ref('policy_decision', d.id), actor,
        payload={'stage': stage, 'decision': decision, 'outcome': outcome,
                 'mission_id': mission.id, 'plan_id': d.plan_id, 'task_id': d.task_id},
        visibility='user' if decision in ('ASK', 'DENY') else 'system',
        workspace=mission.workspace_id, project=mission.project_id))
    return d


def _overall(items):
    return max((i['decision'] for i in items), key=R.STRICTNESS.get, default='ALLOW')


def _presented(tx, kind, mission, plan, task, items, why, step_up):
    """What the user is asked (§8.6): built from rows, model text labelled."""
    titles = {t.key: t.title for t in _tasks(tx.conn, plan)}
    return {
        'what': [{'task': i['task'], 'title': titles.get(i['task']), 'class': i['class'],
                  'target': i['action']['target'], 'paths': i['action'].get('paths'),
                  'implied_by': i.get('implied_by'), 'decision': i['decision'],
                  'why': i['reason']} for i in items],
        'why': why,
        'against': {'mission': {'id': mission.id, 'title': mission.title,
                                'objective': mission.objective},
                    'plan': {'id': plan.id, 'version': plan.plan_version,
                             'digest': plan.digest, 'summary': plan.summary,
                             'summary_by': 'the planner (model-written)'},
                    'task': None if task is None else {'id': task.id, 'key': task.key,
                                                       'title': task.title}},
        'scope': {'plan': 'this plan version', 'task': 'this task of this plan version',
                  'action': 'this one action, once'}[kind],
        'resources': sorted({i['class'] for i in items}),
        'consequences': {
            'approve': {'plan': 'the plan runs; its tasks dispatch under it',
                        'task': 'the mission resumes and this task dispatches',
                        'action': 'the action runs once'}[kind],
            'reject': {'plan': 'the mission is cancelled',
                       'task': 'the mission stays blocked for you to cancel',
                       'action': 'the action is refused'}[kind],
            'request_changes': 'the mission is planned again' if kind == 'plan' else None,
            'step_up': step_up},
        'reusable': {'plan': 'plan-lifetime', 'task': 'task-lifetime',
                     'action': 'single-use'}[kind]}


def request(tx, *, actor, kind, mission, plan, items, h, decision_id, why, ctx, task=None,
            execution_id=None):
    """The live approval of identity *h*, or a new PENDING one (§19: the
    same thing asked twice finds the same row)."""
    got = live_approval(tx.conn, h)
    if got is not None:
        return got.entity, False
    step_up = any(i.get('step_up') for i in items)
    a = entities.Approval(
        id=ids.new_id('approval'), kind=kind,
        subject=Ref(kind if kind != 'action' else 'execution',
                    {'plan': plan.id, 'task': task.id if task else None,
                     'action': execution_id}[kind]),
        action_hash=h, requested_by=actor.id, step_up=step_up, mission_id=mission.id,
        plan_id=plan.id, plan_version=plan.plan_version, plan_digest=plan.digest,
        task_id=None if task is None else task.id, execution_id=execution_id,
        presented=_presented(tx, kind, mission, plan, task, items, why, step_up),
        items=tuple({'task': i['task'], 'action': i['action']} for i in items),
        expires_at=_plus(tx.now, TTL[kind]), policy_decision_id=decision_id,
        policy_version=ctx.get('policy_version'))
    tx.insert(a, actor=actor)
    tx.append(new_event('approval.requested', Ref('approval', a.id), actor, payload={
        'kind': kind, 'mission_id': mission.id, 'plan_id': plan.id, 'task_id': a.task_id,
        'action_hash': h, 'step_up': step_up, 'expires_at': a.expires_at},
        workspace=mission.workspace_id, project=mission.project_id))
    return a, True


# ── the plan gate (§12.1) ───────────────────────────────────────────────────

def record_plan_decision(tx, *, actor, mission, trigger, facts):
    """Called by `Missions._fire` right after a plan decision: record the
    evaluation the guard JUDGED (`facts.evaluated`) and act on it — the plan
    APPROVED within policy, or an Approval requested. A decision on scripted
    facts with no such plan in the database (the P3 lifecycle tests) has
    nothing real to authorise and records nothing."""
    from .commands import active_plan, auto_approve_ceiling
    ceiling = auto_approve_ceiling(mission)
    prow = active_plan(tx.conn, mission.id)
    if prow is None or prow.entity.plan_version != facts.plan_version or not prow.entity.digest:
        return None
    plan, items = prow.entity, list(facts.evaluated)
    h = plan_hash(tx.conn, plan)
    ctx = context(tx.conn, mission, stage='plan', now=tx.now, actor=actor, plan=plan)
    cost = {'band': plan.estimated_cost, 'ceiling': ceiling,
            'within': facts.cost_within_ceiling}
    auto = trigger == 'plan_auto_approved'
    d = record(tx, actor=actor, stage='plan', mission=mission, plan=plan,
               decision=_overall(items), outcome='auto_approved' if auto else 'needs_approval',
               items=items, h=h, ctx=ctx, cost=cost,
               reason=('plan v%d is within policy' % plan.plan_version) if auto else
               '; '.join([i['reason'] for i in items if i['decision'] == 'ASK'] or
                         ['the cost band %s is not known to be under the ceiling %s'
                          % (plan.estimated_cost, ceiling)]))
    if auto:
        lifecycle.fire(tx, entities.Plan, plan.id, 'approved', actor=actor,
                       reason='plan v%d approved within policy (decision %s)'
                       % (plan.plan_version, d.id))
        return {'decision_id': d.id, 'approval_id': None}
    asked = [i for i in items if i['decision'] == 'ASK']
    a, _new = request(tx, actor=actor, kind='plan', mission=mission, plan=plan, items=items,
                      h=h, decision_id=d.id, ctx=ctx,
                      why=[i['reason'] for i in asked] or [
                          'the cost band %s is not under the auto-approve ceiling %s'
                          % (plan.estimated_cost, ceiling)])
    return {'decision_id': d.id, 'approval_id': a.id}


def first_denial(policy, conn, mission, specs, *, now, actor=None):
    """The items of a would-be plan, judged, and whether any is a DENY."""
    items = []
    for s in specs:
        got, ctx = evaluate_task(policy, conn, mission, s['key'], s.get('action_classes', ()),
                                 capabilities=s.get('capabilities_required', ()),
                                 touches=s.get('touches', ()), now=now, actor=actor)
        items += got
    return items, ctx


def record_plan_denial(tx, *, actor, policy, missions, mission_id, specs, round_seq=None):
    """The response to a plan-gate DENY (§11, D11, D12). `propose_plan`
    refused before writing any plan, task or approval; this records the
    denial itself — an auditable fact — re-judged in THIS transaction, and
    blocks the mission for it: REASONING -> BLOCKED (`plan_denied`), while
    PLANNING / REPLANNING wait in place (P8 D6). If the policy no longer
    denies (it changed in between), nothing is recorded and the next round plans."""
    m = lifecycle.load(tx, entities.Mission, mission_id).entity
    items, ctx = first_denial(policy, tx.conn, m, specs, now=tx.now, actor=actor)
    denied = [i for i in items if i['decision'] == 'DENY']
    if not denied:
        return {'recorded': False, 'why': 'the policy no longer denies this plan'}
    d = record(tx, actor=actor, stage='plan', mission=m, decision='DENY', outcome='denied',
               items=items, ctx=ctx, reason='; '.join(i['reason'] for i in denied))
    blocked = {'kind': 'policy', 'policy_decision_id': d.id, 'round_seq': round_seq,
               'denied': [{'task': i['task'], 'class': i['class'],
                           'rule': i['deciding_rule']} for i in denied]}
    if m.state == 'REASONING':
        f = replace(missions.facts(tx, lifecycle.load(tx, entities.Mission, m.id)), denial=d.id)
        missions._fire(tx, m.id, 'plan_denied', actor=actor, facts=f,
                       reason='policy denies the plan: %s' % denied[0]['reason'],
                       extra={'planning_blocked': blocked})
    else:
        tx.update(entities.Mission, m.id, {'planning_blocked': blocked}, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', m.id), actor, payload={
            'fields': ['planning_blocked'], 'planning_blocked': blocked},
            workspace=m.workspace_id, project=m.project_id))
    return {'recorded': True, 'policy_decision_id': d.id, 'state':
            lifecycle.load(tx, entities.Mission, m.id).entity.state}


def supersede_for(tx, *, actor, plan_id, replaced_by):
    """Every live approval of a superseded version ends with it, in the
    transaction that supersedes it (D14): nothing carries to the next one."""
    for r in rows.where(tx.conn, entities.Approval, plan_id=plan_id):
        if r.entity.state in LIVE:
            lifecycle.fire(tx, entities.Approval, r.entity.id, 'plan_replaced', actor=actor,
                           reason='plan %s was replaced by v%d' % (plan_id, replaced_by))


# ── dispatch (§12.2) ────────────────────────────────────────────────────────

def _covers(a, item, step_up):
    """Does APPROVED approval *a* cover *item* (§8.4)? Exactly the item, and
    a step-up the current policy needs must have been given with it."""
    want = {'task': item['task'], 'action': item['action']}
    return want in [dict(x) for x in a.items] and (a.step_up or not step_up)


def _usable(conn, h, now):
    got = live_approval(conn, h)
    if got is None or got.entity.state != 'APPROVED':
        return None
    a = got.entity
    if a.kind == 'action' and a.expires_at <= now:
        return None
    return a


def check_dispatch(tx, *, actor, policy, missions, mission, plan, task):
    """May this task of this exact version dispatch now, under the current
    policy? Returns {'outcome': covered | asked, ...}; raises PolicyDenied on
    a DENY, having written nothing (P3.5) — the `unrecoverable` move that
    answers it records the DENY it judged."""
    from .work import PolicyDenied
    items, ctx = evaluate_task(policy, tx.conn, mission, task.key, task.action_classes,
                               capabilities=task.capabilities_required, touches=task.touches,
                               now=tx.now, task=task, actor=actor, plan=plan, stage='dispatch')
    for i in items:
        if i['decision'] == 'DENY':
            raise PolicyDenied(entities.PolicyDecision(
                id=ids.new_id('policy_decision'), decision='DENY', reason=i['reason'],
                action=Action(**_action_kwargs(i['action']))), task.key)
    th = task_hash(plan, task)
    whole = intact(tx.conn, plan)
    plan_ok = whole and plan.state == 'APPROVED'
    grants = [a for a in (_usable(tx.conn, plan_hash(tx.conn, plan), tx.now) if whole else None,
                          _usable(tx.conn, th, tx.now) if whole else None) if a is not None]
    uncovered = []
    for i in items:
        if i['decision'] == 'ASK':
            by = next((a.id for a in grants if _covers(a, i, i.get('step_up'))), None)
            i['covered_by'] = by
            if by is None:
                uncovered.append(i)
    task_granted = any(a.kind == 'task' for a in grants)
    if whole and (plan_ok or task_granted) and not uncovered:
        d = record(tx, actor=actor, stage='dispatch', mission=mission, plan=plan, task=task,
                   decision=_overall(items), outcome='covered', items=items, h=th, ctx=ctx,
                   reason='task %s may dispatch under plan v%d%s' % (
                       task.key, plan.plan_version,
                       '' if not any(i.get('covered_by') for i in items) else
                       ' (asked items covered by an approval)'))
        return {'outcome': 'covered', 'policy_decision_id': d.id}
    if not whole:
        why = 'plan v%d does not match its recorded digest' % plan.plan_version
        d = record(tx, actor=actor, stage='dispatch', mission=mission, plan=plan, task=task,
                   decision='DENY', outcome='denied', items=items, h=th, ctx=ctx, reason=why)
        missions._fire(tx, mission.id, 'block', actor=actor, reason=why)
        return {'outcome': 'denied', 'policy_decision_id': d.id, 'why': 'digest_mismatch'}
    why = ([i['reason'] for i in uncovered] or
           ['plan v%d has no authorisation (it was never approved under a real policy)'
            % plan.plan_version])
    d = record(tx, actor=actor, stage='dispatch', mission=mission, plan=plan, task=task,
               decision='ASK', outcome='asked', items=items, h=th, ctx=ctx,
               reason='; '.join(why))
    a, _new = request(tx, actor=actor, kind='task', mission=mission, plan=plan, task=task,
                      items=items, h=th, decision_id=d.id, why=why, ctx=ctx)
    missions._fire(tx, mission.id, 'block', actor=actor,
                   reason='waiting for your approval of task %s (approval %s)' % (task.key,
                                                                                a.id))
    return {'outcome': 'asked', 'policy_decision_id': d.id, 'approval_id': a.id}


def _action_kwargs(canonical):
    k = dict(canonical)
    k['action_class'] = k.pop('class')
    return k


# ── deciding (§8.5, D15) ────────────────────────────────────────────────────

def _principal(tx, actor, scope):
    p = rows.get(tx.conn, entities.Principal, actor.id)
    if p is None or p.entity.kind != 'user_device' or scope not in p.entity.scopes:
        raise NotPermitted('only a user device holding the %s scope may do this' % scope)
    return p.entity


def _step_up_valid(tx, actor, proof):
    """Before P15 every device is local, and a local device satisfies step-up;
    a paired device needs a proof, which P15 defines (D16)."""
    devices = rows.where(tx.conn, entities.Device, principal_id=actor.id)
    return proof is None and not any(d.entity.platform in PAIRED_PLATFORMS for d in devices)


def _awaiting(conn, a, mission):
    if a.kind == 'plan':
        return mission.state == 'APPROVAL_REQUIRED'
    if a.kind == 'task':
        return mission.state == 'BLOCKED' and mission.held_from == 'EXECUTING'
    if a.kind == 'route':
        t = rows.get(conn, entities.Task, a.task_id)
        return (mission.state == 'BLOCKED' and mission.held_from == 'EXECUTING'
                and t is not None and t.entity.state == 'AWAITING_APPROVAL')
    e = rows.get(conn, entities.Execution, a.execution_id)
    return e is not None and e.entity.state not in ('ENDED_OK', 'ENDED_ERROR', 'ENDED_KILLED',
                                                    'ENDED_HANDOFF', 'ENDED_REJECTED',
                                                    'ABANDONED')


def _refuse_hash(a, given, trigger):
    if given != a.action_hash:
        raise lifecycle.GuardFailed('approval', a.state, _DECIDED.get(trigger), trigger,
                                    guards.GuardResult('approve', False,
                                                       'the decision is for a different action'))


def ineligible(conn, a, *, now, approve=True):
    """Why approval *a* may not be decided now, as (why, detail), or None
    (§8.5 checks 3 and 6-8; the principal, the state and the hash are the
    deciding command's). Read-only: the approval views compute it too."""
    from .commands import active_plan
    if a.expires_at <= now:
        return 'expired', 'expired at %s' % a.expires_at
    mission = rows.get(conn, entities.Mission, a.mission_id).entity
    prow = active_plan(conn, mission.id)
    plan = None if prow is None else prow.entity
    if plan is None or plan.id != a.plan_id or plan.state not in ('PROPOSED', 'APPROVED'):
        return 'superseded', 'plan %s is not in force' % a.plan_id
    if not intact(conn, plan) or plan.digest != a.plan_digest:
        return 'digest_mismatch', 'plan %s does not match its recorded digest' % plan.id
    if a.task_id is not None:
        t = rows.get(conn, entities.Task, a.task_id)
        if t is None or t.entity.plan_id != plan.id:
            return 'superseded', 'task %s is not in the plan in force' % a.task_id
    if not _awaiting(conn, a, mission):
        return 'not_awaiting', 'mission %s is %s' % (mission.id, mission.state)
    if approve and a.kind == 'plan':
        ok, why = current(conn, mission, plan)
        if not ok:
            return 'stale', why
    return None


def decide(tx, *, actor, policy, missions, approval_id, decision, action_hash, note=None,
           step_up=None, expected_version=None):
    """A user device decides an approval (§8.5): `approve`, `reject`, or
    (a plan) `request_changes`. Everything is re-judged in this transaction;
    a refusal writes nothing, except a DENY found at approve time, which is
    recorded and answered as `denied`."""
    from .commands import active_plan
    if decision not in _DECIDED:
        raise ValueError('a decision is approve, reject or request_changes')
    _principal(tx, actor, 'approve')
    row = lifecycle.load(tx, entities.Approval, approval_id)
    if expected_version is not None and expected_version != row.version:
        raise lifecycle.VersionConflict(approval_id, expected_version, row.version)
    a = row.entity
    trigger = 'reject' if decision == 'request_changes' else decision
    if a.state != 'PENDING':
        if a.state == _DECIDED[decision] and a.decision == decision:   # the same again: one
            return _answer(tx, row, changed=False)
        raise lifecycle.IllegalTrigger('approval', a.state, trigger,
                                       'already %s' % a.state.lower())
    if decision == 'request_changes' and a.kind != 'plan':
        raise ValueError('only a plan approval can send its plan back for changes')
    _refuse_hash(a, action_hash, trigger)
    bad = ineligible(tx.conn, a, now=tx.now, approve=decision == 'approve')
    if bad is not None:
        raise NotEligible(a.id, *bad)
    mission = lifecycle.load(tx, entities.Mission, a.mission_id).entity
    plan = active_plan(tx.conn, mission.id).entity
    task = None if a.task_id is None else lifecycle.load(tx, entities.Task, a.task_id).entity
    if decision == 'approve':
        return _approve(tx, actor, policy, missions, row, mission, plan, task, step_up, note,
                        action_hash)
    kind = a.kind
    row, _e = lifecycle.fire(tx, entities.Approval, a.id, 'reject', actor=actor,
                             reason=note or ('changes requested' if decision == 'request_changes'
                                             else 'rejected by a user device'),
                             fields=_decided(tx, actor, decision, note))
    out = None
    if kind == 'route':
        lifecycle.fire(tx, entities.Task, task.id, 'rejected', actor=actor,
                       reason='approval %s: running on the fallback account was rejected' % a.id)
    if kind == 'plan':
        lifecycle.fire(tx, entities.Plan, plan.id, 'rejected', actor=actor,
                       reason='approval %s: %s' % (a.id, decision))
        if decision == 'request_changes':
            out = missions.request_changes(tx, actor=actor, mission_id=mission.id,
                                           reason=note or 'changes requested on approval %s'
                                           % a.id)
        else:
            out = missions._by_state(tx, mission.id, 'reject', actor=actor,
                                     reason=note or 'plan v%d rejected' % plan.plan_version,
                                     expected_version=None,
                                     pick=lambda to, t: t == 'reject')
    return _answer(tx, row, mission=out)


def _decided(tx, actor, decision, note, decision_id=None):
    return {'decision': decision, 'decided_by': actor.id, 'decided_at': tx.now,
            'decision_note': note, 'decided_policy_decision_id': decision_id}


def _approve(tx, actor, policy, missions, row, mission, plan, task, proof, note, given):
    a = row.entity
    if a.kind == 'route':
        return _approve_route(tx, actor, missions, row, mission, task, proof, note, given)
    items = []
    if a.kind == 'action':                  # the one action it is for, judged again
        ctx = context(tx.conn, mission, stage='action', now=tx.now, task=task, actor=actor,
                      plan=plan, task_classes=[c for c, _b, _x in items_of(task)])
        for it in a.items:
            r = judge(policy, Action(**_action_kwargs(it['action'])), ctx)
            r.update(task=task.key, task_id=task.id)
            items.append(r)
    for t in (() if a.kind == 'action' else [task] if task is not None
              else _tasks(tx.conn, plan)):
        got, ctx = evaluate_task(policy, tx.conn, mission, t.key, t.action_classes,
                                 capabilities=t.capabilities_required, touches=t.touches,
                                 now=tx.now, task=t, actor=actor, plan=plan,
                                 stage='plan' if a.kind == 'plan' else 'dispatch')
        items += got
    stage = {'plan': 'plan', 'task': 'dispatch', 'action': 'action'}[a.kind]
    subject = Ref('approval', a.id)
    denied = [i for i in items if i['decision'] == 'DENY']
    if denied:
        d = record(tx, actor=actor, stage=stage, mission=mission, plan=plan, task=task,
                   decision='DENY', outcome='denied', items=items, h=a.action_hash, ctx=ctx,
                   approval_id=a.id, subject=subject,
                   reason='a DENY is never approvable: %s' % denied[0]['reason'])
        return dict(_answer(tx, row, changed=False), denied={
            'policy_decision_id': d.id, 'reason': d.reason})
    f = guards.ApprovalFacts(actor.kind, tuple(rows.get(tx.conn, entities.Principal,
                                                        actor.id).entity.scopes),
                             given, step_up_valid=_step_up_valid(tx, actor, proof))
    d = record(tx, actor=actor, stage=stage, mission=mission, plan=plan, task=task,
               decision=_overall(items), outcome='approved', items=items, h=a.action_hash,
               ctx=ctx, approval_id=a.id, subject=subject,
               reason='approved by a user device (approval %s)' % a.id)
    row, _e = lifecycle.fire(tx, entities.Approval, a.id, 'approve', actor=actor, facts=f,
                             reason=note or 'approved by a user device',
                             fields=_decided(tx, actor, 'approve', note, d.id))
    out = None
    if a.kind == 'plan':
        lifecycle.fire(tx, entities.Plan, plan.id, 'approved', actor=actor,
                       reason='plan v%d approved by a user device (approval %s)'
                       % (plan.plan_version, a.id))
        out = missions.fire(tx, actor=actor, mission_id=mission.id, trigger='approve',
                            reason='plan v%d approved (approval %s)' % (plan.plan_version, a.id))
    elif a.kind == 'task':
        out = missions.resume(tx, actor=actor, mission_id=mission.id,
                              reason='task %s approved (approval %s)' % (task.key, a.id))
    return _answer(tx, row, mission=out)


def _approve_route(tx, actor, missions, row, mission, task, proof, note, given):
    """A route approval covers no action, so there is nothing to judge now: the
    task returns to READY and its next dispatch is judged by P9 and routed
    again, where this approval lets the router use the fallback account."""
    a = row.entity
    f = guards.ApprovalFacts(actor.kind, tuple(rows.get(tx.conn, entities.Principal,
                                                        actor.id).entity.scopes),
                             given, step_up_valid=_step_up_valid(tx, actor, proof))
    row, _e = lifecycle.fire(tx, entities.Approval, a.id, 'approve', actor=actor, facts=f,
                             reason=note or 'approved by a user device',
                             fields=_decided(tx, actor, 'approve', note))
    lifecycle.fire(tx, entities.Task, task.id, 'approved', actor=actor,
                   reason='running on the fallback account approved (approval %s)' % a.id)
    out = missions.resume(tx, actor=actor, mission_id=mission.id,
                          reason='task %s may run on the fallback account (approval %s)'
                          % (task.key, a.id))
    return _answer(tx, row, mission=out)


def _answer(tx, row, *, changed=True, mission=None):
    a = row.entity
    return {'approval_id': a.id, 'kind': a.kind, 'state': a.state, 'decision': a.decision,
            'version': row.version, 'changed': changed, 'mission': mission}


def withdraw(tx, *, actor, mission_id, reason):
    """The pending approvals of a mission that stopped waiting (it was
    cancelled) are rejected by the system — never left decidable (D15)."""
    for r in rows.where(tx.conn, entities.Approval, mission_id=mission_id):
        if r.entity.state == 'PENDING':
            lifecycle.fire(tx, entities.Approval, r.entity.id, 'reject', actor=actor,
                           reason=reason, fields=_decided(tx, actor, 'reject', reason))


def expire_due(tx, *, actor):
    """Every approval past its expiry ends EXPIRED (the policy worker's sweep).
    An APPROVED plan or task approval does not expire (D8)."""
    done = []
    for r in rows.where(tx.conn, entities.Approval):
        a = r.entity
        if a.expires_at <= tx.now and (a.state == 'PENDING'
                                       or (a.state == 'APPROVED' and a.kind == 'action')):
            lifecycle.fire(tx, entities.Approval, a.id, 'ttl_elapsed', actor=actor,
                           reason='expired at %s' % a.expires_at)
            done.append(a.id)
    return {'expired': done}


def next_expiry(conn):
    due = [r.entity.expires_at for r in rows.where(conn, entities.Approval)
           if r.entity.state == 'PENDING' or (r.entity.state == 'APPROVED'
                                              and r.entity.kind == 'action')]
    return min(due, default=None)


# ── the action stage (its caller is P11's hook) ─────────────────────────────

def evaluate_action(tx, *, actor, policy, execution_id, action, unclassified=False):
    """May this execution perform this exact action now? ALLOW / DENY, or ASK
    with the approval to wait for; an APPROVED action approval of exactly
    this identity allows it ONCE and is CONSUMED (single-use, X09). Records
    the decision; moves no execution or task — halting and resuming is P11's."""
    from .commands import active_plan
    if not isinstance(action, Action):
        action = Action(**action)
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    task = lifecycle.load(tx, entities.Task, e.task_id).entity
    mission = lifecycle.load(tx, entities.Mission, e.mission_id).entity
    plan = lifecycle.load(tx, entities.Plan, task.plan_id).entity
    prow = active_plan(tx.conn, mission.id)
    classes = [c for c, _b, _a in items_of(task)]
    ctx = context(tx.conn, mission, stage='action', now=tx.now, task=task, actor=actor,
                  plan=plan, task_classes=classes, unclassified=unclassified)
    item = judge(policy, action, ctx)
    item.update(task=task.key, task_id=task.id)
    h = actions.action_hash('action', bind(plan, task, execution_id),
                            [actions.item(task.key, action)])
    in_force = prow is not None and prow.entity.id == plan.id and intact(tx.conn, plan)
    kw = dict(actor=actor, stage='action', mission=mission, plan=plan, task=task,
              execution_id=execution_id, action=action, h=h, ctx=ctx)
    if not in_force:
        d = record(tx, decision='DENY', outcome='deny', items=[item],
                   reason='plan v%d is not in force or not intact' % plan.plan_version, **kw)
        return {'decision': 'DENY', 'policy_decision_id': d.id}
    if item['decision'] == 'ASK':
        a = _usable(tx.conn, h, tx.now)
        if a is not None and (a.step_up or not item.get('step_up')):
            lifecycle.fire(tx, entities.Approval, a.id, 'action_executed', actor=actor,
                           reason='used once by execution %s' % execution_id)
            item['covered_by'] = a.id
            d = record(tx, decision='ALLOW', outcome='allow', items=[item], approval_id=a.id,
                       reason='allowed once by approval %s' % a.id, **kw)
            return {'decision': 'ALLOW', 'policy_decision_id': d.id, 'approval_id': a.id}
        d = record(tx, decision='ASK', outcome='ask', items=[item], reason=item['reason'], **kw)
        a, _new = request(tx, actor=actor, kind='action', mission=mission, plan=plan,
                          task=task, execution_id=execution_id, items=[item], h=h,
                          decision_id=d.id, why=[item['reason']], ctx=ctx)
        return {'decision': 'ASK', 'policy_decision_id': d.id, 'approval_id': a.id}
    allowed = item['decision'] != 'DENY'
    d = record(tx, decision=item['decision'], outcome='allow' if allowed else 'deny',
               items=[item], reason=item['reason'], **kw)
    return {'decision': item['decision'], 'policy_decision_id': d.id}


# ── policy administration (§18) ─────────────────────────────────────────────

def _rule_event(tx, type_, actor, rule_entity, payload):
    tx.append(new_event(type_, Ref('policy_rule', rule_entity.id), actor, payload=payload))


def create_rule(tx, *, actor, scope_level, action_class, decision, scope_ref=None,
                locked=None, match=None, boundary=None, outside='ASK', expires_at=None,
                note='', supersedes_rule_id=None):
    """A user rule, or the next revision of one (the old one retired in the
    same transaction). Rules are never edited (D17)."""
    _principal(tx, actor, 'admin')
    if scope_level == 'USER' and scope_ref is None:
        scope_ref = _owner_id(tx, actor)            # V1 is single-user (domain-model §3.1)
    revision, before = 1, None
    if supersedes_rule_id is not None:
        old = lifecycle.load(tx, entities.PolicyRule, supersedes_rule_id).entity
        if old.retired_at is not None:
            raise lifecycle.IllegalTrigger('policy_rule', 'RETIRED', 'revise',
                                           'rule %s is already retired' % old.id)
        revision, before = old.revision + 1, old.to_dict()
    r = entities.PolicyRule(
        id=ids.new_id('policy_rule'), scope_level=scope_level, scope_ref=scope_ref,
        action_class=action_class, decision=decision, locked=locked, match=match,
        boundary=boundary, outside=outside, expires_at=expires_at, source='user', note=note,
        revision=revision, supersedes_rule_id=supersedes_rule_id)
    if supersedes_rule_id is not None:
        _retire(tx, actor, supersedes_rule_id, replaced_by=r.id)
    row = tx.insert(r, actor=actor)
    _rule_event(tx, 'policy_rule.created', actor, r, {'before': before, 'after': r.to_dict()})
    return {'id': r.id, 'version': row.version, 'revision': revision}


def _owner_id(tx, actor):
    u = owner(tx.conn)
    if u is None:
        u = entities.User(id=ids.new_id('user'), display_name='owner')
        tx.insert(u, actor=actor)
    return u.id


def _retire(tx, actor, rule_id, replaced_by=None):
    old = lifecycle.load(tx, entities.PolicyRule, rule_id).entity
    if old.retired_at is not None:
        raise lifecycle.IllegalTrigger('policy_rule', 'RETIRED', 'retire',
                                       'rule %s is already retired' % rule_id)
    row = tx.update(entities.PolicyRule, rule_id, {'retired_at': tx.now}, actor=actor)
    _rule_event(tx, 'policy_rule.retired', actor, old,
                {'before': old.to_dict(), 'replaced_by': replaced_by})
    return row


def retire_rule(tx, *, actor, rule_id):
    _principal(tx, actor, 'admin')
    row = _retire(tx, actor, rule_id)
    return {'id': rule_id, 'version': row.version, 'retired_at': row.entity.retired_at}


def set_profile(tx, *, actor, scope, profile, mission_id=None):
    """The user's default autonomy, or a mission's (§5): admin only — the
    brain and a `control` device never raise autonomy (D5)."""
    _principal(tx, actor, 'admin')
    if profile not in entities.AUTONOMY_PROFILES and not (scope == 'mission' and profile is None):
        raise ValueError('a profile is one of %s' % (entities.AUTONOMY_PROFILES,))
    if scope == 'user':
        u = rows.where(tx.conn, entities.User)
        if u:
            row = tx.update(entities.User, u[0].entity.id, {'autonomy_profile': profile},
                            actor=actor)
        else:
            row = tx.insert(entities.User(id=ids.new_id('user'), display_name='owner',
                                          autonomy_profile=profile), actor=actor)
        tx.append(new_event('user.updated', Ref('user', row.entity.id), actor,
                            payload={'fields': ['autonomy_profile'],
                                     'autonomy_profile': profile}))
        return {'scope': 'user', 'profile': profile}
    if scope != 'mission':
        raise ValueError('a profile is set for the user or a mission')
    m = lifecycle.load(tx, entities.Mission, mission_id).entity
    tx.update(entities.Mission, mission_id, {'autonomy_profile': profile}, actor=actor)
    tx.append(new_event('mission.updated', Ref('mission', mission_id), actor, payload={
        'fields': ['autonomy_profile'], 'autonomy_profile': profile},
        workspace=m.workspace_id, project=m.project_id))
    return {'scope': 'mission', 'mission_id': mission_id, 'profile': profile}


def record_unrecoverable(tx, *, actor, mission, facts):
    """`unrecoverable` taken on a policy DENY (EXECUTING): the DENY it judged is
    recorded with the move (P9 §11, D12) — a refused dispatch wrote nothing."""
    denied = [i for i in facts.evaluated if i['decision'] == 'DENY']
    if not denied:
        return None
    from .commands import active_plan
    prow = active_plan(tx.conn, mission.id)
    ctx = context(tx.conn, mission, stage='dispatch', now=tx.now, actor=actor,
                  plan=None if prow is None else prow.entity)
    return record(tx, actor=actor, stage='dispatch', mission=mission,
                  plan=None if prow is None else prow.entity, decision='DENY',
                  outcome='denied', items=list(facts.evaluated), ctx=ctx,
                  reason='; '.join(i['reason'] for i in denied))


class Authorization:
    """The commands above bound to one Core's Policy port and Missions, so the
    writer runs `command(tx, **json)` like every other command."""

    def __init__(self, *, missions):
        self.missions, self.policy = missions, missions.policy

    def decide(self, tx, **kw):
        return decide(tx, policy=self.policy, missions=self.missions, **kw)

    def record_plan_denial(self, tx, **kw):
        return record_plan_denial(tx, policy=self.policy, missions=self.missions, **kw)

    def evaluate_action(self, tx, **kw):
        return evaluate_action(tx, policy=self.policy, **kw)

    def simulate(self, conn, *, now, action, mission_id=None, task_id=None, stage='plan',
                 extra_rules=()):
        return simulate(conn, self.policy, now=now, action=action, mission_id=mission_id,
                        task_id=task_id, stage=stage, extra_rules=extra_rules)

    create_rule = staticmethod(create_rule)
    retire_rule = staticmethod(retire_rule)
    set_profile = staticmethod(set_profile)
    expire_due = staticmethod(expire_due)


def simulate(conn, policy, *, now, action, mission_id=None, task_id=None, stage='plan',
             extra_rules=()):
    """What would the policy answer for *action* (a canonical dict), in this
    mission's or task's context, with *extra_rules* added? Writes nothing."""
    a = action if isinstance(action, Action) else Action(**_action_kwargs(action)
                                                         if 'class' in action else action)
    task = None
    if task_id is not None:
        got = rows.get(conn, entities.Task, task_id)
        if got is None:
            raise lifecycle.NotFound(task_id)
        task = got.entity
    mid = mission_id or (task.mission_id if task is not None else None)
    if mid is not None:
        m = rows.get(conn, entities.Mission, mid)
        if m is None:
            raise lifecycle.NotFound(mid)
        mission = m.entity
    else:
        mission = entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                                   title='simulation', objective='simulation')
    extra = [R.rule(**dict(r, id=r.get('id') or 'simulated:%d' % i, source='user'))
             for i, r in enumerate(extra_rules)]
    classes = None if task is None else [c for c, _b, _x in items_of(task)]
    ctx = context(conn, mission, stage=stage, now=now, task=task, extra_rules=extra,
                  task_classes=None if stage == 'plan' else classes)
    r = judge(policy, a, ctx)
    return dict(_slim(r), matched_rules=r.get('matched') or [], simulated=True,
                policy_version=ctx['policy_version'], mission_id=mid)
