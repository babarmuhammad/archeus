"""The execution orchestrator's writer commands (P11, p11-design-gate §20.3).

Every function here is ONE writer transaction. State moves go through
`lifecycle.fire` (an edge of the P1 table plus the six P11 adds, audited by its
`execution.state_changed` event) and a mission moves only through
`commands.Missions`. Nothing here touches a process, a file or the network:
the execution manager (core/execution/manager.py) does that between commands
and records what happened through them.

What these commands decide, and nothing else:
- whether the execution is still bound to what was authorised (`binding`,
  p11-design-gate §7) — plan in force and intact, task running under it, the
  dispatch decision still the latest covered one;
- which edge an observed end takes, whether the task is charged an attempt
  (D9), and the task's and mission's response (§8.3);
- a hook request's answer, through P9's `evaluate_action` (§10.4).

Policy is P9's, resources are P10's: this module imports neither the policy
engine nor the router, and asks `authorization` / `resources` through their
entry points (a boundary test holds it to that).
"""

import hashlib
import hmac
import time

from ...infra.db import rows
from ..domain import entities, ids
from ..domain.events import new_event
from ..domain.values import Ref
from . import authorization, lifecycle
from .commands import active_plan

#: live states: a process may exist, or the execution may still get one
LIVE = ('INTENT', 'STARTING', 'RUNNING', 'AWAITING_APPROVAL', 'PAUSING', 'PAUSED',
        'STOPPING', 'LOST', 'HANDING_OFF')
#: ends the task does not own: they spend no attempt (D9)
UNCHARGED = ('user', 'estop', 'ceiling', 'limit', 'breaker', 'pause_timeout', 'cancel',
             'binding', 'disarmed', 'pressure', 'handoff_user')
#: how an end is reported, by the state it is observed in (§8.1)
_EXIT = {'ok': 'exited_success', 'error': 'exited_error'}
_USAGE_KEYS = ('tokens_in', 'tokens_out', 'cache_read', 'cache_write', 'cost_usd')
EVENT_LINES, EVENT_BYTES = 20, 2048


def token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _event(tx, type_, e, actor, payload, mission=None):
    m = mission or lifecycle.load(tx, entities.Mission, e.mission_id).entity
    return tx.append(new_event(type_, Ref('execution', e.id), actor, payload=payload,
                               workspace=m.workspace_id, project=m.project_id))


def _fire(tx, e_id, trigger, actor, reason, fields=None):
    row, _ev = lifecycle.fire(tx, entities.Execution, e_id, trigger, actor=actor,
                              reason=reason, fields=fields)
    return row.entity


def charged_attempts(tx, task_id):
    """How many of a task's executions spent an attempt (D9)."""
    return sum(1 for r in tx.where(entities.Execution, task_id=task_id)
               if r.entity.charged is not False)


# ── the binding (§7) ────────────────────────────────────────────────────────

def binding(conn, e):
    """Why *e* is no longer bound to what was authorised, or None when it is."""
    prow = active_plan(conn, e.mission_id)
    if prow is None or prow.entity.id != e.plan_id or prow.entity.state != 'APPROVED':
        return 'the plan it was dispatched under is no longer in force'
    plan = prow.entity
    if plan.digest != e.plan_digest or not authorization.intact(conn, plan):
        return 'plan v%d does not match its recorded digest' % plan.plan_version
    trow = rows.get(conn, entities.Task, e.task_id)
    if trow is None or trow.entity.plan_id != plan.id or trow.entity.state != 'RUNNING':
        return 'task is not running under this plan'
    latest = [r.entity for r in rows.where(conn, entities.PolicyDecision,
                                                     task_id=e.task_id)
              if r.entity.stage == 'dispatch']
    if not latest or latest[-1].id != e.policy_decision_id or latest[-1].outcome != 'covered':
        return 'its dispatch authorisation was superseded'
    return None


# ── process start and progress ──────────────────────────────────────────────

def prepare_process(tx, *, actor, execution_id, token_digest, workdir, branch, process_seq):
    """Before a process starts: the binding still holds (else the execution ends
    uncharged and the task is re-dispatched), and the new process's number,
    workdir, branch and hook token hash are recorded."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if e.state not in ('INTENT', 'PAUSED', 'AWAITING_APPROVAL'):
        raise lifecycle.IllegalTrigger('execution', e.state, 'prepare_process',
                                       'no process may be started in this state')
    if process_seq != e.process_seq + 1:
        raise ValueError('process %d of %s cannot follow %d' % (process_seq, e.id,
                                                                e.process_seq))
    why = binding(tx.conn, e)
    if why is not None:
        return dict(refuse(tx, actor=actor, execution_id=e.id, reason=why,
                           stop_reason='binding'), refused=why)
    tx.update(entities.Execution, e.id, {'process_seq': process_seq, 'workdir': workdir,
                                         'branch': branch, 'hook_token_hash': token_digest,
                                         'hook_seq': 0 if e.process_seq == 0 else e.hook_seq},
              actor=actor)
    _event(tx, 'execution.prepared', e, actor, {'process_seq': process_seq, 'workdir': workdir,
                                                'branch': branch})
    return {'execution_id': e.id, 'process_seq': process_seq, 'refused': None}


def refuse(tx, *, actor, execution_id, reason, stop_reason, facts=None):
    """An execution with no process ends here: INTENT never spawned
    (ABANDONED), a paused or waiting one is discarded (ENDED_KILLED). Uncharged,
    and the task goes back to READY, unless the reason is the task's own (a
    workspace that cannot be made, §28 note 11): that one spends an attempt."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    fields = {'stop_reason': stop_reason, 'charged': stop_reason not in UNCHARGED,
              'ended_at': _now_iso(),
              'hook_token_hash': None}
    if e.state == 'INTENT':
        e = _fire(tx, e.id, 'spawn_failed', actor, reason,
                  dict(fields, exit_reason='abandoned'))
    else:
        e = _fire(tx, e.id, 'discarded', actor, reason, dict(fields, exit_reason='killed'))
        e = _finish(tx, actor, e, facts)
        _event(tx, 'execution.ended', e, actor, _end_payload(e))
    return _respond(tx, actor, e, reason)


def record_process(tx, *, actor, execution_id, pid, create_time, process_seq):
    """The process exists: INTENT -> STARTING (`spawn`), PAUSED -> STARTING
    (`resume`) or AWAITING_APPROVAL -> STARTING (`resume_approved`)."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if process_seq != e.process_seq:
        raise ValueError('process %d was not prepared for %s' % (process_seq, e.id))
    trigger = {'INTENT': 'spawn', 'PAUSED': 'resume',
               'AWAITING_APPROVAL': 'resume_approved'}.get(e.state)
    if trigger is None:
        raise lifecycle.IllegalTrigger('execution', e.state, 'record_process',
                                       'a process can only start from INTENT or a halt')
    e = _fire(tx, e.id, trigger, actor, 'process %d started (pid %d)' % (process_seq, pid),
              {'pid': pid, 'create_time': create_time,
               'started_at': e.started_at or _now_iso()})
    ev = _event(tx, 'execution.started', e, actor, {
        'pid': pid, 'create_time': create_time, 'process_seq': process_seq,
        'task_id': e.task_id, 'attempt': e.attempt, 'harness_id': e.harness_id,
        'account_id': e.account_id, 'model': e.model})
    return {'execution_id': e.id, 'state': e.state, 'seq': ev.seq}


def record_progress(tx, *, actor, execution_id, offset, events=0, lines=(), usage=None,
                    pressure=None):
    """New stream output was read up to *offset*: the offset (never backwards),
    the cumulative usage, `first_output`, and `execution.progress`."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if offset < e.stream_offset:
        raise ValueError('progress for %s went backwards (%d < %d)'
                         % (e.id, offset, e.stream_offset))
    if e.state == 'STARTING' and events:
        e = _fire(tx, e.id, 'first_output', actor, 'the process wrote output')
    got = {'stream_offset': offset}
    if usage:
        got['usage'] = _usage(usage)
    if pressure is not None:
        got['pressure'] = round(float(pressure), 4)
    if offset == e.stream_offset and got.get('usage', e.usage) == e.usage             and got.get('pressure', e.pressure) == e.pressure:
        return {'execution_id': e.id, 'offset': offset}          # nothing new
    tx.update(entities.Execution, e.id, got, actor=actor)
    last, size = [], 0
    for line in list(lines)[-EVENT_LINES:]:
        if size + len(line) > EVENT_BYTES:
            break
        last.append(line)
        size += len(line)
    _event(tx, 'execution.progress', e, actor, {'offset': offset, 'events': events,
                                                'last': last, 'usage': got.get('usage')})
    return {'execution_id': e.id, 'offset': offset}


def _usage(usage):
    """The adapter's usage in the ledger's vocabulary (provider figures only)."""
    alias = {'input_tokens': 'tokens_in', 'output_tokens': 'tokens_out',
             'cache_read_input_tokens': 'cache_read',
             'cache_creation_input_tokens': 'cache_write', 'total_cost_usd': 'cost_usd'}
    out = {}
    for k, v in (usage or {}).items():
        k = alias.get(k, k)
        if k in _USAGE_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
    return out


# ── ends (§8.1, §8.3) ───────────────────────────────────────────────────────

def _end_payload(e):
    return {'exit_reason': e.exit_reason, 'exit_code': e.exit_code, 'task_id': e.task_id,
            'attempt': e.attempt, 'stop_reason': e.stop_reason, 'charged': e.charged,
            'final_offset': e.stream_offset}


def record_end(tx, *, actor, execution_id, exit_code, killed=False, halted=False, failure=None,
               usage=None, summary='', adapter_state=None, final_offset=None, output=True,
               facts=None):
    """A process of *execution_id* is gone. Which edge that is depends on the
    state it was observed in; a second report of the same end is an invalid
    transition (nothing changes). A vanished process is never success: without
    an observed exit code 0 there is no ENDED_OK."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if final_offset is not None and final_offset > e.stream_offset:
        tx.update(entities.Execution, e.id, {'stream_offset': final_offset}, actor=actor)
    fields = {'adapter_state': dict(adapter_state) if adapter_state else e.adapter_state,
              'failure': failure, 'summary': summary or e.summary}
    if e.state == 'AWAITING_APPROVAL':
        # the hook halted it for an approval: the execution waits, the process is gone
        tx.update(entities.Execution, e.id, {'adapter_state': fields['adapter_state'],
                                             'pid': None, 'create_time': None,
                                             'hook_token_hash': None}, actor=actor)
        _event(tx, 'execution.halted', e, actor, {'exit_code': exit_code,
                                                  'process_seq': e.process_seq})
        return {'execution_id': e.id, 'state': e.state, 'waiting': True}
    if e.state == 'PAUSING' and halted:
        e = _fire(tx, e.id, 'halted_at_boundary', actor, 'halted at a tool boundary',
                  dict(fields, pid=None, create_time=None, hook_token_hash=None))
        return {'execution_id': e.id, 'state': e.state}
    if e.state == 'STOPPING':
        e = _fire(tx, e.id, 'process_gone', actor, 'the process is gone',
                  dict(fields, exit_reason='killed', exit_code=exit_code,
                       charged=e.stop_reason not in UNCHARGED, ended_at=_now_iso(),
                       hook_token_hash=None))
        return _ended(tx, actor, e, usage, facts)
    if e.state == 'STARTING':
        if not output:
            return lost(tx, actor=actor, execution_id=e.id,
                        reason='the process exited without output')
        e = _fire(tx, e.id, 'first_output', actor, 'the process wrote output')
    if e.state not in ('RUNNING', 'PAUSING', 'HANDING_OFF'):
        raise lifecycle.IllegalTrigger('execution', e.state, 'record_end',
                                       'the execution has already ended')
    ok = exit_code == 0 and not killed and not halted
    # a resource's failure spends no attempt only where the breaker can see it: a
    # registered account (§12.4); on a harness's own account it is charged, so it
    # cannot retry forever. A halt Core did not ask for (the hook failed closed) is
    # charged for the same reason.
    uncharged = failure in ('resource', 'auth') and e.account_id is not None
    stop = 'limit' if failure == 'limit' and e.account_id is not None else None
    e = _fire(tx, e.id, _EXIT['ok' if ok else 'error'], actor,
              'exit code %s%s' % (exit_code, ' (halted without being asked)' if halted else ''),
              dict(fields, exit_reason='ok' if ok else 'error', exit_code=exit_code,
                   charged=not (uncharged or stop), stop_reason=stop or e.stop_reason,
                   ended_at=_now_iso(), hook_token_hash=None))
    return _ended(tx, actor, e, usage, facts)


def _finish(tx, actor, e, facts):
    """What every end of an execution that ran leaves behind (p12-design-gate
    §6, D5): the headless session it ran in, and its checkpoint."""
    from ..execution import checkpoint
    from . import sessions
    if e.process_seq >= 1 and e.session_id is None:
        ref = (e.adapter_state or {}).get('session')
        sessions.headless_session(tx, actor=actor, execution=e,
                                  provider_session_ref=ref if isinstance(ref, str) else None)
        e = lifecycle.load(tx, entities.Execution, e.id).entity
    if checkpoint.ran(e):
        checkpoint.derive(tx, actor=actor, execution=e, facts=facts)
    return e


def _ledger(tx, actor, e, usage):
    u = _usage(usage) or _usage(e.usage)
    if u and e.route_decision_id is not None:
        # attributable truth (P10): once per execution, against where it was routed
        tx.insert(entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=e.id,
                                       route_decision_id=e.route_decision_id,
                                       account_id=e.account_id, **u), actor=actor)


def _ended(tx, actor, e, usage, facts=None):
    _ledger(tx, actor, e, usage)
    e = _finish(tx, actor, e, facts)
    _event(tx, 'execution.ended', e, actor, _end_payload(e))
    return _respond(tx, actor, e, 'execution %s ended (%s)' % (e.id, e.exit_reason))


def lost(tx, *, actor, execution_id, reason, facts=None):
    """Nothing is watching and nothing is collectable: LOST -> ENDED_KILLED,
    charged (a process may have run and done anything)."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    to_lost = {'INTENT': 'spawn_unconfirmed', 'STARTING': 'start_timeout',
               'RUNNING': 'heartbeat_missing'}
    if e.state in to_lost:
        e = _fire(tx, e.id, to_lost[e.state], actor, reason)
    if e.state != 'LOST':
        raise lifecycle.IllegalTrigger('execution', e.state, 'lost', 'not a live process')
    e = _fire(tx, e.id, 'reconciled_kill', actor, reason,
              {'exit_reason': 'lost', 'charged': True, 'ended_at': _now_iso(),
               'hook_token_hash': None})
    return _ended(tx, actor, e, None, facts)


def _respond(tx, actor, e, why):
    """The task's (and for a stop, the mission's) response to *e* ending."""
    t = lifecycle.load(tx, entities.Task, e.task_id).entity
    out = {'execution_id': e.id, 'state': e.state, 'charged': e.charged}
    if t.state != 'RUNNING':
        return {**out, 'task_state': t.state}
    if e.state == 'ENDED_OK':
        t = lifecycle.fire(tx, entities.Task, t.id, 'execution_succeeded', actor=actor,
                           reason='%s; verifying' % why)[0].entity
    elif e.state == 'ENDED_REJECTED':
        t = lifecycle.fire(tx, entities.Task, t.id, 'execution_failed_final', actor=actor,
                           reason='%s: the action it needed was rejected' % why,
                           fields={'failure_class': 'human'})[0].entity
    elif e.charged is False:
        t = lifecycle.fire(tx, entities.Task, t.id, 'execution_failed_retry', actor=actor,
                           reason='%s; not charged (%s)' % (why, e.stop_reason or 'resource')
                           )[0].entity
    else:
        t = charged_failure(tx, actor, t, 'execution_failed_retry', 'execution_failed_final',
                            'execution', why).entity
    return {**out, 'task_state': t.state}


def charged_failure(tx, actor, t, retry, final, failure_class, why):
    """P3.5's rule with P11's count (D9): retry while charged attempts remain,
    else FAILED."""
    used = charged_attempts(tx, t.id)
    if used < t.max_attempts:
        return lifecycle.fire(tx, entities.Task, t.id, retry, actor=actor,
                              reason=why + '; retrying')[0]
    return lifecycle.fire(tx, entities.Task, t.id, final, actor=actor,
                          reason=why + '; %d attempts used' % used,
                          fields={'failure_class': failure_class})[0]


# ── control: stop, pause, e-stop (§13) ──────────────────────────────────────

def stop(tx, *, actor, execution_id, reason, stop_reason='user'):
    """Stop one execution: a live process -> STOPPING (the manager halts it at a
    boundary, then kills it by identity); none -> ended here. Stopping what is
    already stopping or ended is an invalid transition: nothing changes."""
    if stop_reason not in entities.STOP_REASONS:
        raise ValueError('unknown stop reason %r' % (stop_reason,))
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if e.state in ('INTENT', 'PAUSED', 'AWAITING_APPROVAL'):
        return refuse(tx, actor=actor, execution_id=e.id, reason=reason,
                      stop_reason=stop_reason)
    e = _fire(tx, e.id, 'stop', actor, reason, {'stop_reason': stop_reason})
    return {'execution_id': e.id, 'state': e.state}


def _live(tx, **eq):
    return [r.entity for r in tx.where(entities.Execution, **eq) if r.entity.state in LIVE
            and r.entity.state not in ('STOPPING', 'LOST')]


def stop_execution(tx, *, actor, missions, execution_id):
    """The user stops one execution; its mission waits for them (`block`)."""
    _user(actor)
    out = stop(tx, actor=actor, execution_id=execution_id, reason='stopped by the user')
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    _block(tx, actor, missions, e.mission_id, 'execution %s stopped by the user' % e.id)
    return out


def stop_mission(tx, *, actor, missions, mission_id):
    """The user stops every live execution of a mission, which then waits."""
    _user(actor)
    lifecycle.load(tx, entities.Mission, mission_id)
    done = [stop(tx, actor=actor, execution_id=e.id, reason='mission stopped by the user')
            for e in _live(tx, mission_id=mission_id)]
    _block(tx, actor, missions, mission_id, 'stopped by the user')
    return {'mission_id': mission_id, 'stopped': [d['execution_id'] for d in done]}


def _block(tx, actor, missions, mission_id, why):
    m = lifecycle.load(tx, entities.Mission, mission_id).entity
    if m.state == 'EXECUTING':
        missions._fire(tx, m.id, 'block', actor=actor, reason=why)


def _user(actor):
    if actor.kind != 'user_device':
        raise authorization.NotPermitted('only a user device stops executions')


def estop(tx, *, actor, missions):
    """The e-stop, recorded (the sentinel was written before this command, by
    the caller): every live execution stops now, every mission with live work
    waits, and `core.estopped` says who and what."""
    if actor.kind not in ('user_device', 'system'):
        raise authorization.NotPermitted('only a user device or Core engages the e-stop')
    killed, missions_hit = [], set()
    for e in _live(tx):
        stop(tx, actor=actor, execution_id=e.id, reason='emergency stop', stop_reason='estop')
        killed.append(e.id)
        missions_hit.add(e.mission_id)
    for mid in sorted(missions_hit):
        _block(tx, actor, missions, mid, 'emergency stop')
    tx.append(new_event('core.estopped', Ref('principal', actor.id), actor,
                        payload={'killed': killed}))
    return {'stopped': killed}


def rearm(tx, *, actor):
    """Record the e-stop being cleared (the caller removes the sentinel after
    this commits). Only a user device."""
    _user(actor)
    tx.append(new_event('core.rearmed', Ref('principal', actor.id), actor, payload={}))
    return {'armed': True}


def pause_work(tx, *, actor, mission_id):
    """A paused mission's running executions are asked to halt at their next
    tool boundary (RUNNING -> PAUSING)."""
    done = []
    for r in tx.where(entities.Execution, mission_id=mission_id):
        if r.entity.state == 'RUNNING':
            _fire(tx, r.entity.id, 'pause_requested', actor, 'the mission was paused')
            done.append(r.entity.id)
    return {'pausing': done}


def pause_timed_out(tx, *, actor, execution_id):
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    e = _fire(tx, e.id, 'pause_timeout', actor, 'no tool boundary before the pause timeout',
              {'stop_reason': 'pause_timeout'})
    return {'execution_id': e.id, 'state': e.state}


# ── hand-off (p12-design-gate §10.1) ────────────────────────────────────────

#: why Core hands an execution off -> the stop reason it records
HANDOFF_CAUSES = ('pressure', 'limit', 'ceiling')


def request_handoff(tx, *, actor, execution_id, stop_reason, reason):
    """Core decided a running execution should continue in a fresh one:
    RUNNING -> HANDING_OFF; the manager halts it at the next tool call."""
    if stop_reason not in HANDOFF_CAUSES:
        raise ValueError('a hand-off is for %s, not %r' % (', '.join(HANDOFF_CAUSES),
                                                           stop_reason))
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    e = _fire(tx, e.id, 'pressure_or_account_change', actor, reason,
              {'stop_reason': stop_reason})
    return {'execution_id': e.id, 'state': e.state}


def handoff_execution(tx, *, actor, execution_id):
    """The user asks for a running execution to continue in a fresh session."""
    _user(actor)
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    e = _fire(tx, e.id, 'user_handoff', actor, 'the user asked for a fresh session',
              {'stop_reason': 'handoff_user'})
    return {'execution_id': e.id, 'state': e.state}


def record_handoff(tx, *, actor, policy, missions, router, execution_id, now, exit_code=None,
                   usage=None, adapter_state=None, final_offset=None, facts=None):
    """The process of a HANDING_OFF execution is gone: in one transaction its
    checkpoint, HANDING_OFF -> ENDED_HANDOFF (uncharged), and the continuation
    (P9, P10, a new INTENT with `handoff_from`). The task and the mission do
    not move unless there is no continuation (then the task is READY again,
    uncharged)."""
    from ..execution.handoff import continue_task
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if e.state != 'HANDING_OFF':
        raise lifecycle.IllegalTrigger('execution', e.state, 'checkpoint_written',
                                       'the execution is not handing off')
    if final_offset is not None and final_offset > e.stream_offset:
        tx.update(entities.Execution, e.id, {'stream_offset': final_offset}, actor=actor)
    e = _fire(tx, e.id, 'checkpoint_written', actor,
              'handed off (%s): the checkpoint is written' % e.stop_reason,
              {'exit_reason': 'handoff', 'exit_code': exit_code, 'charged': False,
               'ended_at': _now_iso(), 'hook_token_hash': None,
               'adapter_state': dict(adapter_state) if adapter_state else e.adapter_state})
    _ledger(tx, actor, e, usage)
    e = _finish(tx, actor, e, facts)
    _event(tx, 'execution.ended', e, actor, _end_payload(e))
    nxt = continue_task(tx, actor=actor, policy=policy, missions=missions, router=router,
                        execution=e, now=now)
    return {'execution_id': e.id, 'state': e.state, 'continuation': nxt['execution_id'],
            'refused': nxt['refused']}


def approval_answered(tx, *, actor, execution_id):
    """An execution waiting on an action approval: REJECTED or EXPIRED ends it
    (ENDED_REJECTED); anything else leaves it waiting (the manager resumes it
    once APPROVED)."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if e.state != 'AWAITING_APPROVAL':
        return {'execution_id': e.id, 'state': e.state}
    a = _approval(tx.conn, e)
    if a is None or a.state not in ('REJECTED', 'EXPIRED', 'SUPERSEDED'):
        return {'execution_id': e.id, 'state': e.state, 'approval': a and a.state}
    e = _fire(tx, e.id, 'rejected', actor, 'approval %s %s' % (a.id, a.state.lower()),
              {'exit_reason': 'rejected', 'charged': True, 'ended_at': _now_iso(),
               'hook_token_hash': None})
    e = _finish(tx, actor, e, None)         # its session; no checkpoint (P9's decision is it)
    _event(tx, 'execution.ended', e, actor, _end_payload(e))
    return _respond(tx, actor, e, 'execution %s: approval %s' % (e.id, a.state.lower()))


def _approval(conn, e):
    got = [r.entity for r in rows.where(conn, entities.Approval, task_id=e.task_id)
           if r.entity.kind == 'action' and r.entity.execution_id == e.id]
    return got[-1] if got else None


def waiting_approval(conn, e):
    """The action approval an AWAITING_APPROVAL execution waits on, or None."""
    return _approval(conn, e)


# ── the hook (§10.4) ────────────────────────────────────────────────────────

def serve_hook(tx, *, actor, policy, execution_id, seq, request, canon, cwd_ok, branch_ok,
               disarmed):
    """Answer one hook request: (decision, reason) with decision allow | deny |
    halt. `canon` is (actions, unclassified) from the canonicaliser; `cwd_ok`
    and `branch_ok` are the manager's reads of the world (outside this
    transaction). Records every P9 decision; moves the execution on an ASK."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if e.state not in ('STARTING', 'RUNNING'):
        return _hook_answer(tx, actor, e, seq, 'halt', 'the execution is %s' % e.state)
    if seq <= e.hook_seq:
        return _hook_answer(tx, actor, e, None, 'halt', 'request %d was already answered' % seq)
    tok = (request or {}).get('token')
    if not (e.hook_token_hash and isinstance(tok, str) and hmac.compare_digest(
            token_hash(tok).encode(), e.hook_token_hash.encode())):
        return _hook_answer(tx, actor, e, seq, 'halt', 'the request is not this execution\'s')
    if disarmed:
        return _hook_answer(tx, actor, e, seq, 'halt', 'emergency stop')
    if e.state == 'STARTING':
        e = _fire(tx, e.id, 'first_output', actor, 'the process asked its first question')
    why = binding(tx.conn, e)
    if why is not None:
        stop(tx, actor=actor, execution_id=e.id, reason=why, stop_reason='binding')
        return _hook_answer(tx, actor, e, seq, 'halt', why)
    if not cwd_ok:
        return _hook_answer(tx, actor, e, seq, 'halt', 'the working directory is outside %s'
                            % e.workdir)
    if not branch_ok:
        return _hook_answer(tx, actor, e, seq, 'halt', 'HEAD is not branch %s' % e.branch)
    actions, unclassified = canon
    worst, reasons, asked = 'allow', [], None
    for a in actions:
        got = authorization.evaluate_action(tx, actor=actor, policy=policy,
                                            execution_id=e.id, action=a,
                                            unclassified=unclassified)
        if got['decision'] == 'DENY':
            worst = 'deny'
            reasons.append(_reason(tx, got))
        elif got['decision'] == 'ASK':
            asked = asked or got
            reasons.append(_reason(tx, got))
    if worst == 'deny':
        return _hook_answer(tx, actor, e, seq, 'deny', '; '.join(reasons))
    if asked is not None:
        _fire(tx, e.id, 'hook_asked', actor, 'waiting for approval %s' % asked['approval_id'])
        return _hook_answer(tx, actor, e, seq, 'halt', 'waiting for your approval (%s)'
                            % asked['approval_id'])
    return _hook_answer(tx, actor, e, seq, 'allow', '')


def _reason(tx, got):
    d = rows.get(tx.conn, entities.PolicyDecision, got['policy_decision_id'])
    return d.entity.reason if d is not None else got['decision']


def _hook_answer(tx, actor, e, seq, decision, reason):
    if seq is not None and seq > e.hook_seq:
        tx.update(entities.Execution, e.id, {'hook_seq': seq}, actor=actor)
    _event(tx, 'execution.hook', e, actor, {'seq': seq, 'decision': decision,
                                            'reason': reason[:500]})
    return {'decision': decision, 'reason': reason, 'execution_id': e.id}


# ── accounts at run time (§12.3, §12.4) ─────────────────────────────────────

LIMIT_DEFAULT_S = 3600
BEAT_S = 60
STORM, STORM_WINDOW_S, PERSIST, COOLDOWN_S = 5, 600, 2, 300


def _iso(epoch):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(epoch))


def _epoch(iso):
    from datetime import datetime
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp()


def account_limited(tx, *, actor, account_id, resets_at=None, now=None):
    """A provider refused for a limit: the account is LIMITED until it resets."""
    a = lifecycle.load(tx, entities.Account, account_id).entity
    now = time.time() if now is None else now
    until = resets_at or _iso(now + LIMIT_DEFAULT_S)
    if a.health in ('AVAILABLE', 'CONSTRAINED'):
        lifecycle.fire(tx, entities.Account, a.id, 'window_exhausted', actor=actor,
                       reason='the provider refused for a limit; resets %s' % until,
                       fields={'limited_until': until})
    return {'account_id': a.id, 'limited_until': until}


def accounts_tick(tx, *, actor, now=None):
    """Time-driven account moves: LIMITED past its reset -> AVAILABLE; the
    breaker (per registered account, resource/auth failures only)."""
    now = time.time() if now is None else now
    moved = []
    for r in tx.where(entities.Account):
        a, since = r.entity, _epoch(r.updated_at)
        if a.health == 'LIMITED' and a.limited_until and _epoch(a.limited_until) <= now:
            lifecycle.fire(tx, entities.Account, a.id, 'reset_time_passed', actor=actor,
                           reason='the limit reset at %s' % a.limited_until,
                           fields={'limited_until': None})
            moved.append((a.id, 'AVAILABLE'))
            continue
        errs = [_epoch(x.entity.ended_at) for x in tx.where(entities.Execution)
                if x.entity.account_id == a.id and x.entity.state == 'ENDED_ERROR'
                and x.entity.failure in ('resource', 'auth') and x.entity.ended_at]
        oks = [_epoch(x.entity.ended_at) for x in tx.where(entities.Execution)
               if x.entity.account_id == a.id and x.entity.state == 'ENDED_OK'
               and x.entity.ended_at]
        recent = [t for t in errs if t > now - STORM_WINDOW_S]
        beat = now - since >= BEAT_S
        if a.health in ('AVAILABLE', 'CONSTRAINED') and len(recent) >= STORM:
            trig, to = 'error_storm', 'DEGRADED'
        elif a.health == 'DEGRADED' and beat and len([t for t in errs if t > since]) >= PERSIST:
            trig, to = 'errors_persist', 'OPEN'
        elif a.health == 'DEGRADED' and beat and any(t > since for t in oks):
            trig, to = 'probe_ok', 'AVAILABLE'
        elif a.health == 'OPEN' and now - since >= COOLDOWN_S:
            trig, to = 'cooldown_elapsed', 'DEGRADED'
        else:
            continue
        lifecycle.fire(tx, entities.Account, a.id, trig, actor=actor,
                       reason='breaker: %d resource errors in %d s' % (len(recent),
                                                                        STORM_WINDOW_S))
        moved.append((a.id, to))
    return {'moved': moved}


def resume_checked(tx, *, actor, policy, missions, router, execution_id, now):
    """Everything a resume needs (§14) in one transaction: the binding, P9's
    dispatch coverage for this task NOW, P10 choosing the same harness and
    account again. Any failure discards the execution (uncharged) so the task is
    dispatched and judged from scratch. Returns {'ok'} or {'refused': why}."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    m = lifecycle.load(tx, entities.Mission, e.mission_id).entity
    why = binding(tx.conn, e)
    if why is None:
        plan = lifecycle.load(tx, entities.Plan, e.plan_id).entity
        t = lifecycle.load(tx, entities.Task, e.task_id).entity
        from .work import PolicyDenied
        try:
            auth = authorization.check_dispatch(tx, actor=actor, policy=policy,
                                                missions=missions, mission=m, plan=plan, task=t)
        except PolicyDenied as denied:
            auth = {'outcome': 'denied (%s)' % denied}
        if auth['outcome'] != 'covered':
            why = 'its authorisation no longer covers it (%s)' % auth['outcome']
        else:
            tx.update(entities.Execution, e.id,
                      {'policy_decision_id': auth['policy_decision_id']}, actor=actor)
            rd = router.route(Ref('task', t.id), now, tx=tx, actor=actor, authorization=auth,
                              mission=m, plan=plan, task=t)
            if (rd.result not in ('selected', 'fallback')
                    or (rd.harness_id, rd.account_id) != (e.harness_id, e.account_id)):
                why = 'the resource router no longer chooses %s' % (e.account_id or e.harness_id)
    if why is not None:
        return dict(refuse(tx, actor=actor, execution_id=e.id, reason='cannot resume: ' + why,
                           stop_reason='binding'), refused=why)
    return {'ok': True, 'refused': None}


def adopted(tx, *, actor, execution_id, pid, offset):
    """A restarted Core took over a live process (§15.3)."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if e.state == 'LOST':
        e = _fire(tx, e.id, 'adopted', actor, 'the process is alive (pid %d)' % pid)
    _event(tx, 'execution.adopted', e, actor, {'pid': pid, 'process_seq': e.process_seq,
                                               'offset': offset})
    return {'execution_id': e.id, 'state': e.state}


class Executions:
    """The execution commands a transport calls, bound to the Missions they
    move (as P9's `Authorization` is): a keyed command's arguments are hashed,
    so no service object travels in them."""

    def __init__(self, *, missions):
        self.missions = missions

    def stop_execution(self, tx, **kw):
        return stop_execution(tx, missions=self.missions, **kw)

    def stop_mission(self, tx, **kw):
        return stop_mission(tx, missions=self.missions, **kw)

    def estop(self, tx, **kw):
        return estop(tx, missions=self.missions, **kw)

    rearm = staticmethod(rearm)


# ── reads ───────────────────────────────────────────────────────────────────

def view(conn, execution_id):
    row = rows.get(conn, entities.Execution, execution_id)
    if row is None:
        raise lifecycle.NotFound(execution_id)
    from .queries import view as v
    out = v(row)
    out.pop('hook_token_hash', None)
    return out


def entity(conn, execution_id):
    """The Execution entity itself (what a read of its output needs)."""
    row = rows.get(conn, entities.Execution, execution_id)
    if row is None:
        raise lifecycle.NotFound(execution_id)
    return row.entity


def checkpoints(conn, execution_id):
    """The checkpoints of an execution (p12-design-gate §19): at most one."""
    if rows.get(conn, entities.Execution, execution_id) is None:
        raise lifecycle.NotFound(execution_id)
    return [r.entity.to_dict() for r in rows.where(conn, entities.Checkpoint,
                                                   execution_id=execution_id)]


def of_task(conn, task_id):
    from .queries import view as v
    if rows.get(conn, entities.Task, task_id) is None:
        raise lifecycle.NotFound(task_id)
    out = []
    for r in rows.where(conn, entities.Execution, task_id=task_id):
        d = v(r)
        d.pop('hook_token_hash', None)
        out.append(d)
    return out

