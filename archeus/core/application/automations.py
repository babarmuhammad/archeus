"""Automations (P14, p14-design-gate): writing them, the one reaction command
the consumer runs per event, and the reads that explain them.

`react` is the whole of P14's effect on the world. For one committed event it
claims at most one run per matching automation, decides it, and — only when
every guard passes — inserts a Mission in CREATED with `origin: automation`.
All of it commits in ONE transaction, and `UNIQUE (automation_id,
triggering_event_seq)` makes a re-delivered event a no-op (§5). From CREATED
the mission is the normal loop's: P7 understands it, P8 plans it, P9 gates its
plan and every dispatch, P10 routes, P11 executes, P13 verifies and reviews.
Nothing here authorises, routes, executes, verifies or touches a session.

The event is read back from the events table by `seq` inside the transaction,
never taken from the caller: no caller can hand this command an event that was
not committed (§13).
"""

from datetime import datetime, timedelta, timezone

from ...infra.db import rows
from ...infra.eventlog import outbox
from ..automation import matcher
from ..domain import entities, events as ev, ids
from ..domain.events import new_event
from ..domain.values import Ref
from . import authorization, commands, lifecycle

#: entity kind -> class, for resolving an event's subject
KINDS = {cls._ID: cls for cls in rows.TABLES}
#: a mission move that settles the run that created it
SETTLES = {'COMPLETED': ('mission_completed', 'mission_completed'),
           'CANCELLED': ('mission_failed_or_cancelled', 'mission_cancelled')}
_ACTIONS = {'enable': 'ENABLED', 'disable': 'DISABLED', 'archive': 'ARCHIVED'}
_CREATED = ('MISSION_CREATED', 'SUCCEEDED', 'FAILED')


def _iso(dt):
    return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _ago(now, seconds):
    return _iso(datetime.fromisoformat(now.replace('Z', '+00:00')) - timedelta(seconds=seconds))


def _event(conn, seq):
    r = conn.execute('SELECT * FROM events WHERE seq = ?', (seq,)).fetchone()
    return None if r is None else outbox.decode(r)


# ── lineage (§9, §10) ────────────────────────────────────────────────────────

def mission_of(conn, subject):
    """The Mission an event's subject belongs to, or None."""
    kind, sid = subject.kind, subject.id
    if kind == 'mission':
        row = rows.get(conn, entities.Mission, sid)
        return row and row.entity
    cls = KINDS.get(kind)
    row = cls and rows.get(conn, cls, sid)
    if row is None:
        return None
    ent = row.entity
    if kind == 'verification':
        return mission_of(conn, ent.subject)
    mid = getattr(ent, 'mission_id', None)
    return mission_of(conn, Ref('mission', mid)) if mid else None


def scope_of(conn, e):
    """(workspace, project) of an event: its mission's when it has one (D8)."""
    m = mission_of(conn, e.subject)
    return (m.workspace_id, m.project_id) if m else (e.workspace, e.project)


def depth_of(conn, e):
    """The causal depth of an event: the depth of the automation run whose
    work it belongs to, 0 when none (D5)."""
    if e.subject.kind == 'automation_run':
        row = rows.get(conn, entities.AutomationRun, e.subject.id)
        return row.entity.depth if row else 0
    m = mission_of(conn, e.subject)
    if m is not None and m.origin == 'automation' and m.origin_ref:
        row = rows.get(conn, entities.AutomationRun, m.origin_ref)
        return row.entity.depth if row else 0
    return 0


def _current(conn, e):
    """The state a `*.state_changed` event's subject is in now, or None when
    it cannot be read."""
    cls = KINDS.get(e.subject.kind)
    row = cls and rows.get(conn, cls, e.subject.id)
    if row is None:
        return None
    try:
        field = cls.machine_field(e.type.rsplit('.', 1)[0])[0]
    except (KeyError, TypeError):
        return None
    return getattr(row.entity, field, None)


def stale(conn, e):
    """Why a state event no longer describes its subject, or None (E22)."""
    if not e.type.endswith('.state_changed'):
        return None
    now, said = _current(conn, e), e.payload.get('to')
    if now is None or now == said:
        return None
    return '%s %s is %s now, not %s as event %d said' % (e.subject.kind, e.subject.id, now,
                                                        said, e.seq)


def enabled(conn):
    return [r.entity for r in rows.where(conn, entities.Automation)
            if r.entity.state == 'ENABLED']


def candidates(conn, e):
    """[(automation, rationale)] the event fires, before any run is claimed:
    ENABLED, armed before it, of its exact scope, and its trigger matches."""
    if e.type.startswith(matcher.FORBIDDEN_PREFIXES):
        return []
    scope, out = None, []
    for a in enabled(conn):
        if e.seq <= a.armed_seq:
            continue
        hit, why = matcher.matches(a.trigger, e.type, e.payload)
        if not hit:
            continue
        scope = scope or scope_of(conn, e)
        if (a.workspace_id, a.project_id) == scope:
            out.append((a, dict(why, scope={'workspace': scope[0], 'project': scope[1]})))
    return out


# ── writing an automation (§7, D13) ──────────────────────────────────────────

def create(tx, *, actor, name, trigger, template, project_id=None,
           workspace_id=ids.GLOBAL_WORKSPACE, max_depth=3, rate_limit=6):
    """A new automation in DRAFT, with its own principal. A user device with
    `admin` only: an automation, a brain or an execution cannot write one."""
    authorization._principal(tx, actor, 'admin')
    trigger = matcher.validate_trigger(trigger, ev.REGISTRY)
    template = matcher.validate_template(template)
    if project_id is not None and tx.get(entities.Project, project_id) is None:
        raise lifecycle.NotFound(project_id)
    principal = commands.register_principal(tx, kind='automation', scopes=('create_mission',))
    a = entities.Automation(id=ids.new_id('automation'), workspace_id=workspace_id, name=name,
                            project_id=project_id, trigger=trigger, template=template,
                            max_depth=max_depth, rate_limit=rate_limit,
                            principal_id=principal['id'])
    row = tx.insert(a, actor=actor)
    e = tx.append(new_event('automation.created', Ref('automation', a.id), actor,
                            payload={'name': name, 'trigger': trigger},
                            workspace=workspace_id, project=project_id))
    return {'id': a.id, 'state': a.state, 'version': row.version, 'seq': e.seq}


def set_state(tx, *, actor, automation_id, action, expected_version=None):
    """enable (from DRAFT, DISABLED or SUSPENDED), disable, archive. Enabling
    re-arms it at the current head: it never fires for an earlier event (D12)."""
    authorization._principal(tx, actor, 'admin')
    if action not in _ACTIONS:
        raise ValueError('action is enable, disable or archive')
    row = lifecycle.load(tx, entities.Automation, automation_id)
    to = _ACTIONS[action]
    if row.entity.state == to:
        return {'id': automation_id, 'state': to, 'version': row.version, 'changed': False}
    trigger = {'ENABLED': 'user_reenables' if row.entity.state == 'SUSPENDED'
               else 'enable_within_policy', 'DISABLED': 'disable', 'ARCHIVED': 'archive'}[to]
    fields = {'armed_seq': outbox.head(tx.conn)} if to == 'ENABLED' else None
    row, e = lifecycle.fire(tx, entities.Automation, automation_id, trigger, actor=actor,
                            reason='%sd on request' % action, fields=fields,
                            expected_version=expected_version)
    return {'id': automation_id, 'state': to, 'version': row.version, 'changed': True,
            'seq': e.seq}


# ── reacting to one event (§5, §8, §10) ──────────────────────────────────────

def react(tx, *, actor, seq):
    """Everything P14 does about event *seq*, in this one transaction:
    settle the run of an automation mission that ended, then claim and decide
    a run for each automation the event fires. Returns the run ids claimed."""
    e = _event(tx.conn, seq)
    if e is None:
        return {'runs': [], 'settled': None}        # pruned: nothing to react to
    settled = _settle(tx, actor, e)
    runs = []
    for a, why in candidates(tx.conn, e):
        if tx.execute('SELECT 1 FROM automation_runs WHERE automation_id = ? AND '
                      'triggering_event_seq = ?', (a.id, e.seq)).fetchone():
            continue                                 # claimed by an earlier delivery
        runs.append(_claim(tx, actor, a, e, why))
    return {'runs': runs, 'settled': settled}


def settles(e):
    """Is *e* a mission move that settles the run that asked for it?"""
    return e.type == 'mission.state_changed' and e.payload.get('to') in SETTLES


def _settle(tx, actor, e):
    if not settles(e):
        return None
    m = tx.get(entities.Mission, e.subject.id)
    if m is None or m.entity.origin != 'automation' or not m.entity.origin_ref:
        return None
    run = tx.get(entities.AutomationRun, m.entity.origin_ref)
    if run is None or run.entity.state != 'MISSION_CREATED':
        return None
    trigger, code = SETTLES[e.payload['to']]
    why = 'its mission %s was %s' % (m.entity.id, e.payload['to'].lower())
    lifecycle.fire(tx, entities.AutomationRun, run.entity.id, trigger, actor=actor,
                   reason=why, fields={'reason_code': code, 'reason': why})
    return run.entity.id


def _claim(tx, actor, a, e, why):
    depth = depth_of(tx.conn, e)
    chain = (tuple(e.cause_chain) + (e.id,))[-ev.MAX_CAUSE_CHAIN:]
    me = Ref('automation', a.principal_id)
    run = entities.AutomationRun(id=ids.new_id('automation_run'), automation_id=a.id,
                                 triggering_event_seq=e.seq, triggering_event_id=e.id,
                                 depth=depth + 1, cause_chain=chain, rationale=why)
    tx.insert(run, actor=me)
    tx.append(new_event('automation_run.created', Ref('automation_run', run.id), me,
                        payload={'automation': a.id, 'event_seq': e.seq, 'depth': run.depth},
                        workspace=a.workspace_id, project=a.project_id, cause_chain=chain))

    def end(trigger, code, reason, **fields):
        lifecycle.fire(tx, entities.AutomationRun, run.id, trigger, actor=me, reason=reason,
                       cause=chain, fields=dict(fields, reason_code=code, reason=reason))
        return run.id

    old = stale(tx.conn, e)
    if old:
        return end('condition_false', 'condition_false', 'stale: ' + old)
    p = a.project_id and tx.get(entities.Project, a.project_id)
    if a.project_id is not None and (p is None or p.entity.state != 'ACTIVE'):
        return end('condition_false', 'condition_false', 'its project is gone or archived')
    if depth >= a.max_depth:
        end('depth_exceeded', 'depth_exceeded',
            'event %d is at causal depth %d, the cap is %d: escalated to you, not dropped'
            % (e.seq, depth, a.max_depth))
        return _guard(tx, actor, a, run.id)
    since = _ago(tx.now, matcher.WINDOW_S)
    made = sum(1 for r in tx.where(entities.AutomationRun, automation_id=a.id)
               if r.entity.state in _CREATED and r.created_at >= since)
    if made >= a.rate_limit:
        end('rate_limited', 'rate_limited', '%d missions in the last hour, the limit is %d'
            % (made, a.rate_limit))
        return _guard(tx, actor, a, run.id)
    lifecycle.fire(tx, entities.AutomationRun, run.id, 'conditions_met', actor=me, cause=chain,
                   reason='matched %s' % e.type)
    if authorization.estop_armed():
        return end('denied', 'denied', 'Core is disarmed (e-stop): no work is requested')
    if e.actor.kind == 'execution':
        return end('denied', 'denied', 'caused by an execution, which may not create missions '
                   '(domain-model §3.3)')
    want = matcher.render(a.template, e.type, e.seq, (e.subject.kind, e.subject.id), e.payload)
    m = commands.create_mission(tx, actor=me, title=want['title'], objective=want['objective'],
                                project_id=a.project_id, workspace_id=a.workspace_id,
                                success_criteria=want['success_criteria'],
                                origin='automation', origin_ref=run.id, cause=chain)
    return end('allowed', 'allowed', 'asked for mission %s' % m['id'], mission_id=m['id'])


def _guard(tx, actor, a, run_id):
    """Suspend *a* when the loop guard trips (§10), in the same transaction."""
    since = _ago(tx.now, matcher.WINDOW_S)
    recent = [(r.entity.state, r.entity.reason_code)
              for r in tx.where(entities.AutomationRun, automation_id=a.id)
              if r.created_at >= since]
    if matcher.should_suspend(recent):
        lifecycle.fire(tx, entities.Automation, a.id, 'loop_guard_tripped', actor=actor,
                       reason='%d escalated or rate-limited runs in the last hour: suspended '
                       'until you re-enable it' % matcher.SUSPEND_AFTER)
    return run_id


# ── reads (§15) ──────────────────────────────────────────────────────────────

def _view(row):
    a = row.entity
    return dict(a.to_dict(), version=row.version, created_at=row.created_at,
                updated_at=row.updated_at)


def _run_view(row):
    return dict(row.entity.to_dict(), version=row.version, created_at=row.created_at,
                updated_at=row.updated_at)


def quarantined(conn):
    return [{'seq': r[0], 'error': r[1][len('quarantined: '):], 'at': r[2]}
            for r in conn.execute("SELECT event_seq, result, at FROM consumer_effects WHERE "
                                  "consumer = 'automation' AND result LIKE 'quarantined:%' "
                                  "ORDER BY event_seq")]


def list_automations(conn):
    return {'automations': [_view(r) for r in rows.where(conn, entities.Automation)],
            'quarantined': quarantined(conn)}


def get_automation(conn, automation_id, *, runs=50):
    row = rows.get(conn, entities.Automation, automation_id)
    if row is None:
        raise lifecycle.NotFound(automation_id)
    rs = rows.where(conn, entities.AutomationRun, automation_id=automation_id)
    return dict(_view(row), runs=[_run_view(r) for r in rs[-runs:]])


def _mine(conn, cls, mission_id):
    if 'mission_id' in rows.columns(conn, rows.table(cls)):
        return [r.entity for r in rows.where(conn, cls, mission_id=mission_id)]
    return [r.entity for r in rows.where(conn, cls) if r.entity.mission_id == mission_id]


def explain(conn, run_id):
    """Why an automated action happened, from rows (§15, E15, E25)."""
    row = rows.get(conn, entities.AutomationRun, run_id)
    if row is None:
        raise lifecycle.NotFound(run_id)
    run = row.entity
    a = rows.get(conn, entities.Automation, run.automation_id).entity
    e = _event(conn, run.triggering_event_seq)
    out = {'run': _run_view(row),
           'automation': {'id': a.id, 'name': a.name, 'trigger': a.trigger,
                          'project_id': a.project_id, 'principal_id': a.principal_id,
                          'state': a.state},
           'event': None if e is None else {
               'seq': e.seq, 'id': e.id, 'type': e.type, 'at': e.at,
               'actor': {'kind': e.actor.kind, 'id': e.actor.id},
               'subject': {'kind': e.subject.kind, 'id': e.subject.id},
               'scope': {'workspace': e.workspace, 'project': e.project},
               'cause_chain': list(e.cause_chain)},
           'why': {'rationale': run.rationale, 'depth': run.depth, 'max_depth': a.max_depth,
                   'outcome': run.state, 'reason_code': run.reason_code, 'reason': run.reason},
           'mission': None}
    if run.mission_id is None:
        return out
    mid = run.mission_id
    m = rows.get(conn, entities.Mission, mid).entity
    plans = _mine(conn, entities.Plan, mid)
    plan_ids = {p.id for p in plans}
    task_ids = {t.id for t in _mine(conn, entities.Task, mid)}
    execs = _mine(conn, entities.Execution, mid)
    # a route is the mission's by its column, or by the execution it placed
    routed = {d.id: d for d in _mine(conn, entities.RouteDecision, mid)}
    for x in execs:
        if x.route_decision_id and x.route_decision_id not in routed:
            d = rows.get(conn, entities.RouteDecision, x.route_decision_id)
            if d is not None:
                routed[d.entity.id] = d.entity
    out['mission'] = {
        'id': m.id, 'state': m.state, 'origin': m.origin, 'origin_ref': m.origin_ref,
        'plans': [{'id': p.id, 'version': p.plan_version, 'state': p.state} for p in plans],
        'policy_decisions': [{'id': d.id, 'stage': d.stage, 'decision': d.decision,
                              'outcome': d.outcome}
                             for d in _mine(conn, entities.PolicyDecision, mid)],
        'approvals': [{'id': x.id, 'kind': x.kind, 'state': x.state}
                      for x in _mine(conn, entities.Approval, mid)],
        'routes': [{'id': d.id, 'subject': {'kind': d.subject.kind, 'id': d.subject.id},
                    'selected': d.selected, 'harness_id': d.harness_id,
                    'account_id': d.account_id, 'model': d.model, 'result': d.result}
                   for d in routed.values()],
        'executions': [{'id': x.id, 'task_id': x.task_id, 'state': x.state,
                        'harness_id': x.harness_id, 'account_id': x.account_id,
                        'model': x.model, 'route_decision_id': x.route_decision_id}
                       for x in execs],
        'verifications': [{'id': v.id, 'subject': {'kind': v.subject.kind, 'id': v.subject.id},
                           'state': v.state, 'verifier': v.verifier}
                          for v in (r.entity for r in rows.where(conn, entities.Verification))
                          if v.plan_id in plan_ids or v.subject.id in task_ids | {mid}],
        'reviews': [{'id': r.id, 'state': r.state, 'verdict': r.verdict,
                     'reviewer': r.reviewer, 'independent': r.independent}
                    for r in _mine(conn, entities.Review, mid)],
    }
    return out


def simulate(conn, automation_id, *, now, days=30, limit=outbox.MAX_LIMIT):
    """The events of the last *days* the automation's trigger and scope would
    have fired on, and why (ADR-0020). Writes nothing; depth, rate and state
    are not simulated — they depend on what the runs would have done."""
    a = get_automation(conn, automation_id, runs=0)
    since = _ago(now, days * 86400)
    hits, examined = [], 0
    for r in conn.execute('SELECT * FROM events WHERE at >= ? AND type = ? ORDER BY seq',
                          (since, a['trigger']['type'])):
        e = outbox.decode(r)
        examined += 1
        hit, why = matcher.matches(a['trigger'], e.type, e.payload)
        if hit and scope_of(conn, e) == (a['workspace_id'], a['project_id']):
            hits.append({'seq': e.seq, 'at': e.at, 'subject': {'kind': e.subject.kind,
                                                               'id': e.subject.id},
                         'rationale': why,
                         'denied': e.actor.kind == 'execution'})
            if len(hits) >= limit:
                break
    return {'automation_id': automation_id, 'days': days, 'examined': examined,
            'matched': hits}
