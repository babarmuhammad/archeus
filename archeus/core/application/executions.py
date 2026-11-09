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

import contextlib
import hashlib
import hmac
import json
import re
import time

from ...infra.db import rows
from ..domain import entities, ids, instants
from ..domain.events import caused_by, new_event
from ..domain.values import Ref
from ..execution.command_allowlist import Allowed
from ..execution.canonical import needs_command_cap
from . import authorization, lifecycle
from .commands import active_plan
from .public import system_value
from .queries import _homes

#: live states: a process may exist, or the execution may still get one
LIVE = ('INTENT', 'STARTING', 'RUNNING', 'AWAITING_APPROVAL', 'PAUSING', 'PAUSED',
        'STOPPING', 'LOST', 'HANDING_OFF')
#: ends the task does not own: they spend no attempt (D9)
UNCHARGED = ('user', 'estop', 'ceiling', 'limit', 'breaker', 'pause_timeout', 'cancel',
             'binding', 'disarmed', 'pressure', 'handoff_user', 'path_too_long', 'spawn')
#: refusals every later attempt would repeat: the mission waits for the user
#: instead of re-dispatching the task (T-078)
BLOCKING = ('path_too_long',)
#: O7's spawn breaker and start wait, as the owner answered T-110 Q2-Q5 (2026-10-21):
#: 3 failed starts of a harness within 10 min open it; 5 min after its last failure
#: one task may try; a task waits 15 s after a failed start, doubling up to 5 min
SPAWN_TRIP, SPAWN_WINDOW_S, SPAWN_COOLDOWN_S = 3, 600, 300
SPAWN_WAIT_S, SPAWN_WAIT_MAX_S = 15, 300
#: how an end is reported, by the state it is observed in (§8.1)
_EXIT = {'ok': 'exited_success', 'error': 'exited_error'}
_USAGE_KEYS = ('tokens_in', 'tokens_out', 'cache_read', 'cache_write', 'cost_usd')
EVENT_LINES, EVENT_BYTES, LINE_CAP = 20, 2048, 200


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


@contextlib.contextmanager
def _after(tx, ended):
    """What the task and its mission do in reply to *ended* (`execution.ended`, or None
    when nothing ended) carries it (p21 D13 (b), owner 2026-10-21). Scoped, because one
    command (an e-stop, a mission stop) can end several executions."""
    before = tx.cause
    if ended is not None:
        tx.cause = caused_by(ended)
    try:
        yield
    finally:
        tx.cause = before


def charged_attempts(tx, task_id):
    """How many of a task's executions spent an attempt (D9)."""
    return sum(1 for r in tx.where(entities.Execution, task_id=task_id)
               if r.entity.charged is not False)


# ── O7: the spawn breaker and the start wait (T-106) ────────────────────────
# Derived from the recorded starts alone (owner, T-110 Q10), so a restart neither
# loses the breaker nor gives a harness its attempts back.

def _tripped(times):
    # an INTENT that waited (its mission paused) can fail after a later one did:
    # rowid order is not time order
    times = sorted(times)
    return any(b - a <= SPAWN_WINDOW_S for a, b in zip(times, times[SPAWN_TRIP - 1:]))


def spawn_streak(newest_first):
    """The failed starts after the last start among one harness's executions
    (*newest_first*, read only as far as that start), and whether one dispatched
    after the last of them has not started yet (the half-open breaker's trial)."""
    fails, trial = [], False
    for x in newest_first:
        if x.stop_reason == 'spawn':
            fails.append(x)
        elif x.started_at:
            break
        elif x.state == 'INTENT' and not fails:
            trial = True
    return fails, trial


def breaker_state(times, trial, now):
    """None (closed), or {'state': 'open' | 'half_open', 'until'}: open until
    the cooldown after the latest failure, then half-open for one trial; while
    the trial has not started, everything else still waits."""
    if not _tripped(times):
        return None
    until = max(times) + SPAWN_COOLDOWN_S          # the times are never after now (_newest)
    if now < until:
        return {'state': 'open', 'until': until}
    if trial:
        return {'state': 'open', 'until': now + SPAWN_WAIT_S}
    return {'state': 'half_open', 'until': None}


def _decided(x, created_at):
    """When a row's place in the streak was decided: a failed start's end, else the
    start, else (a trial not yet started) its creation. Both readers use it (T-106 r5)."""
    if x.stop_reason == 'spawn':
        return x.ended_at
    return x.started_at or created_at


def _newest(conn, harness_id, now):
    """The harness's counting executions (a failed start, a start, a trial INTENT)
    decided at or before *now*, newest first by when each was decided (a failed start's
    end, a start, a trial's creation). A row decided
    after *now* is a backward clock step's: it is not history yet, so it counts for
    nothing (T-106 r4; were it counted, the window it opens would run from the recorded
    time, not from now). A trial INTENT counts only while its mission is EXECUTING: one
    parked by a pause or a block would hold every other task back until that mission
    moves. Rowid is creation order, which an INTENT that waited does not keep, so it
    only breaks ties. The instants are compared as parsed, not as text: created_at has
    milliseconds and the others do not. SQLite 3.31 has no json_extract (test_db_schema
    pins the floor), so the body is read here. Owner sign-off, T-106 r8: "Accept
    read-all, cap 600". The cap is by creation, not by decided time, and it counts
    counting rows only (the SQL drops the others, so 600 newer binding refusals cannot
    hide a tripped breaker): the streak reads the harness's 600 newest counting rows by
    creation and orders them here by decided time. A row created before 600 newer ones
    is outside the cap even when it was decided after them
    (test_O7_the_cap_is_by_creation_order); a decided-time cap needs a column or
    json1."""
    # ponytail: decodes the newest 600 counting rows per call (the owner's ceiling,
    # T-106 r8); a decided_at column (or json1 once the floor allows it) bounds it by time
    found = []
    key = '"harness_id": ' + json.dumps(harness_id)       # the body's own encoding of the key
    for rec in conn.execute(
            "SELECT * FROM executions WHERE body LIKE ? AND (state = 'INTENT'"
            " OR body LIKE '%\"stop_reason\": \"spawn\"%' OR body LIKE '%\"started_at\": \"%')"
            " ORDER BY rowid DESC LIMIT 600", ('%' + key + '%',)):
        x = rows.decode(entities.Execution, rec).entity
        if x.harness_id != harness_id or not (
                x.stop_reason == 'spawn' or x.started_at or x.state == 'INTENT'):
            continue
        at = _epoch(_decided(x, rec['created_at']))
        if at <= now:
            found.append((at, x))
    found.sort(key=lambda p: p[0], reverse=True)          # stable: rowid order breaks ties
    for _, x in found:
        if x.state == 'INTENT' and rows.get(conn, entities.Mission,
                                            x.mission_id).entity.state != 'EXECUTING':
            continue
        yield x


def spawn_breaker(conn, harness_id, now):
    """The harness's breaker with the latest failure's reason, or None."""
    fails, trial = spawn_streak(_newest(conn, harness_id, now))
    b = breaker_state([_epoch(x.ended_at) for x in fails], trial, now)
    return b and dict(b, error=max(fails, key=lambda x: x.ended_at).summary)


def spawn_wait_s(n):
    return min(SPAWN_WAIT_S * 2 ** (n - 1), SPAWN_WAIT_MAX_S)


def spawn_wait(conn, task_id, now):
    """Until when (epoch) the task waits after its failed starts in a row, or None."""
    # a row decided after now is a backward clock step's, not history yet (as _newest)
    xs = [r.entity for r in rows.where(conn, entities.Execution, task_id=task_id)
          if _epoch(_decided(r.entity, r.created_at)) <= now]
    n = next((i for i, x in enumerate(reversed(xs)) if x.stop_reason != 'spawn'), len(xs))
    if not n:
        return None
    until = _epoch(xs[-1].ended_at) + spawn_wait_s(n)
    return until if now < until else None


def _spawn_failed(tx, actor, e, reason):
    """The breaker opening on this failure is said once (P21 D1: the tray says
    it); a failed half-open trial only keeps it open."""
    # the failure's own stamp, not tx.now: refuse stamps whole seconds inside the
    # command, so a second boundary between the two would drop this very failure
    fails, _ = spawn_streak(_newest(tx.conn, e.harness_id, _epoch(e.ended_at)))
    times = [_epoch(x.ended_at) for x in fails]
    if _tripped(times) and not _tripped([t for x, t in zip(fails, times) if x.id != e.id]):
        tx.append(new_event('harness.state_changed', Ref('harness', e.harness_id), actor,
                            payload={'breaker': 'open', 'reason': reason},
                            workspace=ids.GLOBAL_WORKSPACE))


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

def prepare_process(tx, *, actor, execution_id, token_digest, workdir, branch, process_seq,
                    isolated, inventory_sha256=None, inventory_size=None, seed_revision=None):
    """Before a process starts: the binding still holds (else the execution ends
    uncharged and the task is re-dispatched), and the new process's number,
    workdir, branch and hook token hash are recorded — and (P20, ADR-0049) the
    inventory of what its settings sources load, an artifact the manager has
    already stored, referenced from the execution. The isolation decision
    (T-035) is recorded at the first preparation; a later one under a different
    decision ends the execution uncharged, and a legacy row stays unknown. So is
    the commit its seed was built from (K2, T-049 §7): a resume must name the one
    recorded, None included, or it ends uncharged the same way."""
    if not isinstance(isolated, bool):
        raise ValueError('prepare_process needs the isolation decision as a bool')
    if seed_revision is not None and not (isinstance(seed_revision, str)
                                          and entities.SEED_REVISION.fullmatch(seed_revision)):
        raise ValueError('a seed revision is a commit id: %r' % (seed_revision,))
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if e.state not in ('INTENT', 'PAUSED', 'AWAITING_APPROVAL'):
        raise lifecycle.IllegalTrigger('execution', e.state, 'prepare_process',
                                       'no process may be started in this state')
    if process_seq != e.process_seq + 1:
        raise ValueError('process %d of %s cannot follow %d' % (process_seq, e.id,
                                                                e.process_seq))
    # a refusal, not IllegalTrigger: the manager's pass treats that as a lost
    # race and would re-attempt (and re-refuse) a PAUSED execution forever
    if e.process_seq >= 1 and e.isolated is not None and e.isolated != isolated:
        why = 'its isolation decision changed (recorded %s, now %s)' % (e.isolated, isolated)
        return dict(refuse(tx, actor=actor, execution_id=e.id, reason=why,
                           stop_reason='binding'), refused=why)
    if e.process_seq >= 1 and seed_revision != e.seed_revision:
        why = 'its seed changed (recorded %s, now %s)' % (e.seed_revision, seed_revision)
        return dict(refuse(tx, actor=actor, execution_id=e.id, reason=why,
                           stop_reason='binding'), refused=why)
    recorded = isolated if e.process_seq == 0 else e.isolated
    seed = seed_revision if e.process_seq == 0 else e.seed_revision
    why = binding(tx.conn, e)
    if why is not None:
        return dict(refuse(tx, actor=actor, execution_id=e.id, reason=why,
                           stop_reason='binding'), refused=why)
    if inventory_sha256 is not None and tx.get(entities.Artifact, inventory_sha256) is None:
        tx.insert(entities.Artifact(id=inventory_sha256, media_type='application/json',
                                    size=inventory_size), actor=actor)
    tx.update(entities.Execution, e.id, {'process_seq': process_seq, 'workdir': workdir,
                                         'branch': branch, 'hook_token_hash': token_digest,
                                         'hook_seq': 0 if e.process_seq == 0 else e.hook_seq,
                                         'isolated': recorded, 'seed_revision': seed,
                                         'inventory_sha256': inventory_sha256},
              actor=actor)
    _event(tx, 'execution.prepared', e, actor, {'process_seq': process_seq, 'workdir': workdir,
                                                'branch': branch,
                                                'inventory': inventory_sha256,
                                                'isolated': recorded,
                                                'seed_revision': seed})
    return {'execution_id': e.id, 'process_seq': process_seq, 'refused': None}


class SeedRefused(Exception):
    """No base an execution's seed may be built from: it is refused, charged, and on
    its task's last attempt the task fails with `failure_class`."""

    def __init__(self, why, failure_class):
        super().__init__(why)
        self.failure_class = failure_class


def seed_base(conn, e):
    """T-049 §2: the commit *e*'s seed is built from, read from Core's write-once
    records only (a retry: the latest earlier attempt's), or None for a first
    attempt, whose base the node reads once from the user's repository. A hand-off
    continuation continues its predecessor's import (K3); without one there is
    nothing to continue, and under T-030 §3.3 Q2 (owner, A) that is a charged
    failure of class `import`, never a seed of something else. A retry takes the
    latest earlier seeded attempt's import, else that attempt's own seed."""
    if e.handoff_from is not None:
        prev = rows.get(conn, entities.Execution, e.handoff_from).entity
        if prev.import_revision is None:
            raise SeedRefused('%s continues %s, which has no import' % (e.id, prev.id),
                              'import')
        return prev.import_revision
    earlier = [r.entity for r in rows.where(conn, entities.Execution, task_id=e.task_id)
               if r.entity.attempt < e.attempt and r.entity.seed_revision is not None]
    if not earlier:
        return None
    last = max(earlier, key=lambda x: x.attempt)
    return last.import_revision or last.seed_revision


def refuse(tx, *, actor, execution_id, reason, stop_reason, facts=None,
           failure_class='execution', missions=None):
    """An execution with no process ends here: INTENT never spawned
    (ABANDONED), a paused or waiting one is discarded (ENDED_KILLED). Uncharged,
    and the task goes back to READY, unless the reason is the task's own (a
    workspace that cannot be made, §28 note 11): that one spends an attempt. A
    BLOCKING reason also blocks the mission on *reason* (needs *missions*), so
    the READY task is not dispatched again until the user resumes it."""
    from . import queries
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    fields = {'stop_reason': stop_reason, 'charged': stop_reason not in UNCHARGED,
              'ended_at': _now_iso(),
              'hook_token_hash': None}
    if stop_reason == 'spawn':
        fields['summary'] = reason          # what the harness's status shows (T-106)
    ended = None
    if e.state == 'INTENT':
        e = _fire(tx, e.id, 'spawn_failed', actor, reason,
                  dict(fields, exit_reason='abandoned'))
    else:
        e = _fire(tx, e.id, 'discarded', actor, reason, dict(fields, exit_reason='killed'))
        # the session is Core's record of what ran, whoever ends the execution: a user's
        # stop or e-stop of a halted one ends it from their own command (T-101). Only
        # here: every other end is Core recording what it observed, and keeps its guard
        e = _finish(tx, actor, e, facts, session_actor=(
            actor if actor.kind == 'system'
            else Ref('system', queries.system_principal(tx.conn))))
        ended = _event(tx, 'execution.ended', e, actor, _end_payload(e))
    with _after(tx, ended):
        out = _respond(tx, actor, e, reason, failure_class)
        if stop_reason in BLOCKING:
            _block(tx, actor, missions, e.mission_id, reason)
        if stop_reason == 'spawn':
            _spawn_failed(tx, actor, e, reason)
    return out


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
                    pressure=None, context=None, served=None):
    """New stream output was read up to *offset*: the offset (never backwards),
    the cumulative usage, the pressure with its basis (ADR-0047 §2), the served
    model at its provenance level (ADR-0031 §6), `first_output`, and
    `execution.progress`."""
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
    if context is not None:
        got['context'] = dict(context)
    got.update(_served(e, served))
    if 'served_level' not in got and offset == e.stream_offset \
            and got.get('usage', e.usage) == e.usage \
            and got.get('pressure', e.pressure) == e.pressure \
            and got.get('context', e.context) == e.context:
        return {'execution_id': e.id, 'offset': offset}          # nothing new
    tx.update(entities.Execution, e.id, got, actor=actor)
    from ..homes import cut_safe
    from . import resources
    last, size, homes = [], 0, None
    for line in list(lines)[-EVENT_LINES:]:
        if len(line) > LINE_CAP:
            homes = homes or resources.bound_homes(tx.conn, tx.live)
            line = cut_safe(line, homes, LINE_CAP)
        if size + len(line) > EVENT_BYTES:
            break
        last.append(line)
        size += len(line)
    _event(tx, 'execution.progress', e, actor, {'offset': offset, 'events': events,
                                                'last': last, 'usage': got.get('usage')})
    return {'execution_id': e.id, 'offset': offset}


def _served(e, served):
    """The provenance fields to write for a reported {level, model} (ADR-0031 §6):
    a level is never lowered; at the same level a later report of another model
    wins (the harness changed model mid-run). SERVED and BILLED name the exact
    revision; REQUESTED and ROUTED never claim one."""
    if not served or not served.get('model'):
        return {}
    levels = entities.PROVENANCE_LEVELS
    level, model = served['level'], str(served['model'])[:200]
    old = levels.index(e.served_level) if e.served_level else -1
    if levels.index(level) < old or (levels.index(level) == old and model == e.served_model):
        return {}
    out = {'served_level': level, 'served_model': model}
    if level in ('SERVED', 'BILLED'):
        out['model_revision'] = model
    return out


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

def _end_payload(e, facts=None):
    out = {'exit_reason': e.exit_reason, 'exit_code': e.exit_code, 'task_id': e.task_id,
           'attempt': e.attempt, 'stop_reason': e.stop_reason, 'charged': e.charged,
           'final_offset': e.stream_offset, 'import_revision': e.import_revision}
    if (facts or {}).get('import_counts'):
        # what the import left out of its commit (T-051 §3): deleted seed paths and
        # dropped empty directories, recorded with the end that imported
        out['import_counts'] = dict(facts['import_counts'])
    return out


def imports(state, exit_code, killed, halted, output):
    """The route on which a seeded execution's end imports its workspace (K3,
    C-1012-T030-2 §2): a clean exit of a running execution, or of a starting one
    that wrote output. One classification for the manager, which captures it
    before the import, and for `record_end`, which checks it still holds."""
    return (exit_code == 0 and not killed and not halted
            and (state == 'RUNNING' or state == 'STARTING' and output))


def record_end(tx, *, actor, execution_id, exit_code, killed=False, halted=False, failure=None,
               usage=None, summary='', adapter_state=None, final_offset=None, output=True,
               facts=None, usage_total=False, isolated=False, core_halt=False,
               import_revision=None, no_import=None):
    """A process of *execution_id* is gone. Which edge that is depends on the
    state it was observed in; a second report of the same end is an invalid
    transition (nothing changes). A vanished process is never success: without
    an observed exit code 0 there is no ENDED_OK.

    For an *isolated* execution a PAUSING or HANDING_OFF end is decided by Core's
    own state and observed exit, never by the execution's halt report (PV-20 §3.3
    H2, A7): an exit 0 pauses (a hand-off goes through `record_handoff`), anything
    else is ENDED_ERROR. *core_halt* is Core's own halt decision, never a report.

    A seeded execution's ENDED_OK is written with its *import_revision* in the same
    transaction (K3, T-051 §5); without one the end stands and the task takes the
    charged failure of class `import` (§7, owner A), *no_import* saying why."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    _import_once(e, import_revision)
    clean = exit_code == 0 and not killed
    if import_revision is not None or no_import is not None:
        # an import was attempted on the route the manager captured: either outcome
        # stands only if that route still holds (C-1012-T030-2 §2 step 5)
        if not (clean and not halted):
            raise ValueError('only a clean end imports its workspace')
        if not imports(e.state, exit_code, killed, halted, output):
            # the row moved after the route was captured: a lost race, and the
            # import, kept in the store, is never recorded
            raise lifecycle.IllegalTrigger('execution', e.state, 'record_end',
                                           'an import is recorded only by a running end')
    if isolated and e.state == 'HANDING_OFF' and clean:
        raise lifecycle.IllegalTrigger('execution', e.state, 'record_end',
                                       'an isolated hand-off that exited 0 ends through '
                                       'record_handoff')
    # T-025 C1: an isolated end during a hand-off Core asked for is not the execution
    # failing, so it spends no attempt; A7 still makes the end ENDED_ERROR
    core_handoff = isolated and e.state == 'HANDING_OFF' and e.stop_reason in UNCHARGED
    if final_offset is not None and final_offset > e.stream_offset:
        tx.update(entities.Execution, e.id, {'stream_offset': final_offset}, actor=actor)
    fields = {'adapter_state': dict(adapter_state) if adapter_state else e.adapter_state,
              'failure': failure, 'summary': summary or e.summary}
    end = {'end_state_digest': (facts or {}).get('end_state')}
    if e.state == 'AWAITING_APPROVAL':
        # the hook halted it for an approval: the execution waits, the process is gone
        tx.update(entities.Execution, e.id, {'adapter_state': fields['adapter_state'],
                                             'pid': None, 'create_time': None,
                                             'hook_token_hash': None}, actor=actor)
        _event(tx, 'execution.halted', e, actor, {'exit_code': exit_code,
                                                  'process_seq': e.process_seq})
        return {'execution_id': e.id, 'state': e.state, 'waiting': True}
    if e.state == 'PAUSING' and (core_halt or (clean if isolated else halted)):
        e = _fire(tx, e.id, 'halted_at_boundary', actor, 'halted at a tool boundary',
                  dict(fields, pid=None, create_time=None, hook_token_hash=None))
        return {'execution_id': e.id, 'state': e.state}
    if e.state == 'STOPPING':
        e = _fire(tx, e.id, 'process_gone', actor, 'the process is gone',
                  dict(fields, exit_reason='killed', exit_code=exit_code,
                       charged=e.stop_reason not in UNCHARGED, ended_at=_now_iso(),
                       hook_token_hash=None, **end))
        return _ended(tx, actor, e, usage, facts, usage_total)
    if e.state == 'STARTING':
        if not output:
            return lost(tx, actor=actor, execution_id=e.id,
                        reason='the process exited without output')
        e = _fire(tx, e.id, 'first_output', actor, 'the process wrote output')
    if e.state not in ('RUNNING', 'PAUSING', 'HANDING_OFF'):
        raise lifecycle.IllegalTrigger('execution', e.state, 'record_end',
                                       'the execution has already ended')
    ok = exit_code == 0 and not killed and not halted
    missing = _missing_import(e, import_revision, no_import) if ok else None
    # a resource's failure spends no attempt only where the breaker can see it: a
    # registered account (§12.4); on a harness's own account it is charged, so it
    # cannot retry forever. A halt Core did not ask for (the hook failed closed) is
    # charged for the same reason.
    uncharged = core_handoff or (failure in ('resource', 'auth') and e.account_id is not None)
    stop = 'limit' if failure == 'limit' and e.account_id is not None else None
    e = _fire(tx, e.id, _EXIT['ok' if ok else 'error'], actor,
              'exit code %s%s' % (exit_code, ' (halted without being asked)' if halted else ''),
              dict(fields, exit_reason='ok' if ok else 'error', exit_code=exit_code,
                   charged=missing is not None or not (uncharged or stop),
                   stop_reason=stop or e.stop_reason, ended_at=_now_iso(),
                   hook_token_hash=None, import_revision=import_revision, **end))
    return _ended(tx, actor, e, usage, facts, usage_total, missing)


def _finish(tx, actor, e, facts, session_actor=None):
    """What every end of an execution that ran leaves behind (p12-design-gate
    §6, D5): the headless session it ran in, and its checkpoint."""
    from ..execution import checkpoint
    from . import sessions
    if e.process_seq >= 1 and e.session_id is None:
        ref = (e.adapter_state or {}).get('session')
        sessions.headless_session(tx, actor=session_actor or actor, execution=e,
                                  provider_session_ref=ref if isinstance(ref, str) else None)
        e = lifecycle.load(tx, entities.Execution, e.id).entity
    if checkpoint.ran(e):
        checkpoint.derive(tx, actor=actor, execution=e, facts=facts)
    return e


def _ledger(tx, actor, e, usage, total=False):
    """Attributable truth (P10): one row per execution that ran, against where
    it was routed — also when it reported nothing (`basis: none`), so no
    consumption hides behind a missing row (ADR-0048 D-25.3). `total` is the
    adapter saying the figures are the harness's own total for the process; a
    second process (a resume) or the last progress report is a lower bound."""
    if e.route_decision_id is None or e.process_seq < 1:
        return                      # never spawned: nothing was consumed
    u = _usage(usage)
    if not u:
        u, total = _usage(e.usage), False
    # ponytail: one row per execution, so a resumed one is only a lower bound;
    # per-process rows would make it a total
    basis = 'none' if not u else 'reported_total' if total and e.process_seq == 1 else 'partial'
    tx.insert(entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=e.id,
                                   route_decision_id=e.route_decision_id,
                                   account_id=e.account_id, basis=basis, **u), actor=actor)


def _ended(tx, actor, e, usage, facts=None, usage_total=False, missing=None):
    _ledger(tx, actor, e, usage, usage_total)
    e = _finish(tx, actor, e, facts)
    ended = _event(tx, 'execution.ended', e, actor, _end_payload(e, facts))
    with _after(tx, ended):
        if missing is not None:
            return _respond(tx, actor, e, 'execution %s ended (%s), %s' % (
                e.id, e.exit_reason, missing), 'import', no_import=True)
        return _respond(tx, actor, e, 'execution %s ended (%s)' % (e.id, e.exit_reason))


def _import_once(e, import_revision):
    """`import_revision` is written once, by the end that imported (T-051 §5)."""
    if e.import_revision is not None:
        raise ValueError('%s already recorded its import %s' % (e.id, e.import_revision))
    if import_revision is not None and e.seed_revision is None:
        raise ValueError('%s was never seeded: it has nothing to import' % e.id)


def _missing_import(e, import_revision, no_import):
    """Why a seeded execution's clean end has no import (T-051 §7), or None."""
    if e.seed_revision is None or import_revision is not None:
        return None
    return 'no import: %s' % (no_import or 'none was made')


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


def _respond(tx, actor, e, why, failure_class='execution', no_import=False):
    """The task's (and for a stop, the mission's) response to *e* ending. A clean
    end with no import (*no_import*) cannot be verified or merged: charged (§7)."""
    t = lifecycle.load(tx, entities.Task, e.task_id).entity
    out = {'execution_id': e.id, 'state': e.state, 'charged': e.charged}
    if t.state != 'RUNNING':
        return {**out, 'task_state': t.state}
    if e.state == 'ENDED_OK' and not no_import:
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
                            failure_class, why).entity
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
    if stop_reason in BLOCKING:
        # a blocking reason is a refusal's, made where the mission is in hand (refuse)
        raise ValueError('%r is not a stop reason' % (stop_reason,))
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


def rearm(tx, *, actor, step_up=None):
    """Record the e-stop being cleared (the caller removes the sentinel after
    this commits). Only a user device; from a paired one, only with its PIN
    (D10, V2-3 resolved 2026-10-15: a local client re-arms by being local)."""
    _user(actor)
    if not authorization._step_up_valid(tx, actor, step_up):
        from ..domain.guards import GuardResult
        raise lifecycle.GuardFailed('core', 'disarmed', 'armed', 'rearm', GuardResult(
            'step_up', False, 're-arming from a paired device needs a valid step-up proof'))
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


def no_progress(tx, e, end_state):
    """Why the pressure hand-off of *e* must not continue (ADR-0047 §5), or None.

    Only a continuation handing off for pressure is judged. It made progress
    when its measured end state is one no earlier link of its chain (the whole
    `handoff_from` ancestry, so A -> B -> A is caught) ended in. Read from the
    Execution rows, never from a checkpoint (p12-design-gate §8.3). An end
    state that could not be measured is no progress: guards fail closed."""
    from ..execution import pressure
    if e.stop_reason != 'pressure' or e.handoff_from is None:
        return None
    chain, cur = [], e.handoff_from
    while cur is not None:
        prev = lifecycle.load(tx, entities.Execution, cur).entity
        chain.append(prev)
        cur = prev.handoff_from
    earlier = [x.end_state_digest for x in chain if x.end_state_digest is not None]
    # the artifacts it recorded count too (clause 5 (ii)); its own checkpoint is
    # derived after this guard, so it is never among them
    if pressure.progressed(end_state, artifacts_of(tx.conn, e), earlier):
        return None
    why = ('its end state could not be measured' if end_state is None else
           'it ended in a state an earlier link of its chain already ended in')
    return ('context insufficient: a pressure continuation with no progress over the %d '
            'earlier link(s) of its chain (%s); now: %s; before: %s; charged'
            % (len(chain), why, pressure.describe(e.context),
               pressure.describe(chain[0].context)))


def record_handoff(tx, *, actor, policy, missions, router, execution_id, now, exit_code=None,
                   usage=None, adapter_state=None, final_offset=None, facts=None,
                   usage_total=False, import_revision=None, no_import=None):
    """The process of a HANDING_OFF execution is gone: in one transaction its
    checkpoint, HANDING_OFF -> ENDED_HANDOFF (uncharged), and the continuation
    (P9, P10, a new INTENT with `handoff_from`). The task and the mission do
    not move unless there is no continuation (then the task is READY again,
    uncharged). A seeded execution hands off its *import_revision*, which its
    continuation is seeded from; without one there is no continuation, and the
    hand-off is the charged failure of class `import` (K3, T-051 §7, owner A)."""
    from ..execution.handoff import continue_task
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    if e.state != 'HANDING_OFF':
        raise lifecycle.IllegalTrigger('execution', e.state, 'checkpoint_written',
                                       'the execution is not handing off')
    _import_once(e, import_revision)
    missing = _missing_import(e, import_revision, no_import)
    if final_offset is not None and final_offset > e.stream_offset:
        tx.update(entities.Execution, e.id, {'stream_offset': final_offset}, actor=actor)
    end_state = (facts or {}).get('end_state')
    guarded = None if missing else no_progress(tx, e, end_state)
    refused = missing or guarded
    e = _fire(tx, e.id, 'checkpoint_written', actor,
              refused or 'handed off (%s): the checkpoint is written' % e.stop_reason,
              {'exit_reason': 'handoff', 'exit_code': exit_code, 'charged': refused is not None,
               'ended_at': _now_iso(), 'hook_token_hash': None, 'end_state_digest': end_state,
               'import_revision': import_revision,
               'adapter_state': dict(adapter_state) if adapter_state else e.adapter_state})
    _ledger(tx, actor, e, usage, usage_total)
    e = _finish(tx, actor, e, dict(facts or {}, context_insufficient=guarded) if guarded
                else facts)
    ended = _event(tx, 'execution.ended', e, actor, _end_payload(e, facts))
    with _after(tx, ended):
        if refused is not None:
            # ADR-0047 §5 and T-051 §7: no continuation; the attempt is spent and the
            # ordinary retry (a fresh execution) or FAILED -> replan takes over
            t = lifecycle.load(tx, entities.Task, e.task_id).entity
            if t.state == 'RUNNING':
                t = charged_failure(tx, actor, t, 'execution_failed_retry',
                                    'execution_failed_final',
                                    'import' if missing else 'context_insufficient',
                                    'execution %s: %s' % (e.id, refused)).entity
            return {'execution_id': e.id, 'state': e.state, 'continuation': None,
                    'refused': refused, 'task_state': t.state}
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
    ended = _event(tx, 'execution.ended', e, actor, _end_payload(e))
    with _after(tx, ended):
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
               disarmed, command_eligibility=None):
    """Answer one hook request: (decision, reason) with decision allow | deny |
    halt. `canon` is (actions, unclassified) from the canonicaliser; `cwd_ok`
    and `branch_ok` are the manager's reads of the world (outside this
    transaction). Records every P9 decision; moves the execution on an ASK."""
    e = lifecycle.load(tx, entities.Execution, execution_id).entity
    actions, unclassified = canon
    first = actions[0] if actions else None
    if e.state not in ('STARTING', 'RUNNING'):
        return _hook_answer(tx, actor, e, seq, 'halt', 'the execution is %s' % e.state)
    if seq <= e.hook_seq:
        return _hook_answer(tx, actor, e, None, 'halt', 'request %d was already answered' % seq)
    tok = (request or {}).get('token')
    if not (e.hook_token_hash and isinstance(tok, str) and hmac.compare_digest(
            token_hash(tok).encode(), e.hook_token_hash.encode())):
        return _hook_answer(tx, actor, e, seq, 'halt', 'the request is not this execution\'s')
    act = _current(first)
    if disarmed:
        return _hook_answer(tx, actor, e, seq, 'halt', 'emergency stop', act)
    if e.state == 'STARTING':
        e = _fire(tx, e.id, 'first_output', actor, 'the process asked its first question')
    why = binding(tx.conn, e)
    if why is not None:
        stop(tx, actor=actor, execution_id=e.id, reason=why, stop_reason='binding')
        return _hook_answer(tx, actor, e, seq, 'halt', why, act)
    if not cwd_ok:
        return _hook_answer(tx, actor, e, seq, 'halt', 'the working directory is outside %s'
                            % e.workdir, act)
    if not branch_ok:
        return _hook_answer(tx, actor, e, seq, 'halt', 'HEAD is not branch %s' % e.branch, act)
    worst, reasons, asked = 'allow', [], None
    approved = bool(actions)
    denier = asker = None          # the action that decided the answer; the chip names it
    for a in actions:
        got = authorization.evaluate_action(tx, actor=actor, policy=policy,
                                            execution_id=e.id, action=a,
                                            unclassified=unclassified)
        approved = approved and got['decision'] == 'ALLOW' and bool(got.get('approval_id'))
        if got['decision'] == 'DENY':
            worst = 'deny'
            denier = a if denier is None else denier
            reasons.append(_reason(tx, got))
        elif got['decision'] == 'ASK':
            if asked is None:
                asked, asker = got, a
            reasons.append(_reason(tx, got))
    if worst == 'deny':
        return _hook_answer(tx, actor, e, seq, 'deny', '; '.join(reasons), _current(denier))
    if asked is not None:
        _fire(tx, e.id, 'hook_asked', actor, 'waiting for approval %s' % asked['approval_id'])
        return _hook_answer(tx, actor, e, seq, 'halt', 'waiting for your approval (%s)'
                            % asked['approval_id'], _current(asker))
    if needs_command_cap(request.get('tool'), request.get('input'), unclassified) and not (
            isinstance(command_eligibility, Allowed) and command_eligibility.row_id
            or approved):
        return _hook_answer(tx, actor, e, seq, 'halt', 'command form needs review',
                            {'action_class': 'exec', 'label': 'command'})
    return _hook_answer(tx, actor, e, seq, 'allow', '', act)


def _reason(tx, got):
    d = rows.get(tx.conn, entities.PolicyDecision, got['policy_decision_id'])
    return d.entity.reason if d is not None else got['decision']


#: what a chip may name of a command, besides a host it took from a clear URL (P21 D6, I-F4):
#: a tool's name, and a verb from a short list per tool. Nothing else of an argument is ever
#: named: a value, a path, a header, a flag or a credential has no word here.
_TOOLS = frozenset((
    'git', 'npm', 'npx', 'yarn', 'pnpm', 'pip', 'pip3', 'python', 'python3', 'py', 'node',
    'perl', 'ruby', 'php', 'bash', 'sh', 'zsh', 'dash', 'fish', 'cmd', 'powershell', 'pwsh',
    'rm', 'mv', 'cp', 'mkdir', 'touch', 'rmdir', 'chmod', 'ln', 'ls', 'cat', 'head', 'tail',
    'wc', 'grep', 'rg', 'find', 'pwd', 'echo', 'which', 'curl', 'wget', 'ssh', 'scp', 'rsync',
    'sftp', 'terraform', 'kubectl', 'helm', 'docker', 'vercel', 'make', 'cargo', 'go', 'mvn',
    'gradle', 'dotnet', 'pytest', 'ruff', 'tsc', 'vite', 'base64', 'ps', 'kill', 'tar', 'unzip',
    'zip', 'gh', 'aws', 'gcloud', 'az', 'brew', 'apt', 'apt-get', 'choco', 'winget', 'make',
    'env', 'timeout', 'sudo', 'xargs', 'nohup', 'base64', 'busybox', 'stdbuf'))
_VERBS = {
    'git': frozenset(('status', 'log', 'diff', 'show', 'rev-parse', 'ls-files', 'branch',
                      'remote', 'fetch', 'pull', 'clone', 'ls-remote', 'push', 'commit', 'add',
                      'checkout', 'switch', 'restore', 'stash', 'merge', 'rebase',
                      'cherry-pick', 'reset', 'clean', 'tag')),
    'npm': frozenset(('install', 'i', 'add', 'publish', 'run', 'test', 'ci', 'exec')),
    'yarn': frozenset(('install', 'add', 'publish')),
    'pip': frozenset(('install',)), 'pip3': frozenset(('install',)),
    'terraform': frozenset(('apply', 'destroy')),
    'kubectl': frozenset(('apply', 'delete')),
    'helm': frozenset(('install', 'uninstall', 'upgrade')),
    'docker': frozenset(('build', 'run', 'push', 'rm')),
    'vercel': frozenset(('deploy',)),
    'gh': frozenset(('pr', 'release', 'issue')),
    'cargo': frozenset(('build', 'test', 'publish', 'install')),
}
def _current(a):
    """What the activity chip shows (P21 D6): the class of the action that decided the
    answer, and a label. Never raw input (slice I)."""
    if a is None:
        return None
    return {'action_class': a.action_class, 'label': _label(a)}


def _label(a):
    """The chip's word for an action: a host from a clear URL, else a tool and a verb from
    the lists above, else a fixed phrase. An argument is never named (I-F4)."""
    if a.chip_host:
        return a.chip_host
    if a.argv is None:                       # a harness tool (Read, Write, WebSearch ...)
        if a.action_class in ('read', 'write_repo'):
            return 'a file outside the workspace' if re.match(r'(/|[A-Za-z]:)', a.target or '') \
                else 'a file in the workspace'
        if a.action_class == 'web':
            return 'search' if a.target == 'search' else ''
        return 'a tool'
    if a.target in ('shell', 'command'):      # the canonicaliser's fixed words
        return a.target
    name = re.split(r'[\\/]', a.argv[0])[-1].lower()
    name = name[:-4] if name.endswith('.exe') else name
    if name not in _TOOLS:
        return 'a program'
    verb = a.argv[1].lower() if len(a.argv) > 1 else ''
    return name + ' ' + verb if verb in _VERBS.get(name, ()) else name


def _hook_answer(tx, actor, e, seq, decision, reason, action=None):
    """Only a request past the token check passes *action*: a foreign one is not
    this execution's, so it never becomes its current action."""
    from . import resources
    fields = {'hook_seq': seq} if seq is not None and seq > e.hook_seq else {}
    if action is not None:
        fields['current_action'] = dict(action, decision=decision, seq=seq)
    if fields:
        tx.update(entities.Execution, e.id, fields, actor=actor)
    _event(tx, 'execution.hook', e, actor, {'seq': seq, 'decision': decision,
                                            'reason': resources.cut_bound(tx, reason, 500)})
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


def limit_until(resets_at, now):
    """The text a limit is stored with: the provider's reset as the router reads it
    (`instants.instant`: a naive value is UTC), written with its offset. A reset that is not
    a time, or already past, holds the default window: released on the next tick it
    would be refused again, uncharged, on every pass (T-106 r6)."""
    at = instants.instant(resets_at)
    if at is None or at.timestamp() <= now:
        return _iso(now + LIMIT_DEFAULT_S)
    return at.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def limit_passed(limited_until, now):
    """Whether a stored limit's reset has come. A row written since r5 carries its
    offset. A row with no offset was written before r5 and is read in local time, as
    it was released before, so r5 releases none of those early (T-106 r6). A value
    that is not a time counts as come: no account is held forever on a value nobody
    can read (T-106 r5)."""
    from datetime import datetime
    try:
        return datetime.fromisoformat(limited_until.replace('Z', '+00:00')).timestamp() <= now
    except (AttributeError, TypeError, ValueError, OverflowError, OSError):
        return True


def account_limited(tx, *, actor, account_id, resets_at=None, now=None):
    """A provider refused for a limit: the account is LIMITED until it resets."""
    a = lifecycle.load(tx, entities.Account, account_id).entity
    now = time.time() if now is None else now
    until = limit_until(resets_at, now)
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
        if a.health == 'LIMITED' and a.limited_until and limit_passed(a.limited_until, now):
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

def view(conn, execution_id, homes=None):
    row = rows.get(conn, entities.Execution, execution_id)
    if row is None:
        raise lifecycle.NotFound(execution_id)
    from ..execution import pressure
    from .queries import view as v
    out = v(row)
    out.pop('hook_token_hash', None)
    out['context'] = pressure.view(row.entity)
    from .live import explain, handoff_of
    out['handoff'] = handoff_of(conn, row.entity, homes)
    out['why'] = explain(conn, row.entity, homes)
    out['inventory'] = inventory(row.entity.inventory_sha256)
    out['artifacts'] = artifacts_of(conn, row.entity)
    return out


def record_artifact(tx, *, actor, execution, sha, media_type, size, kind, label=''):
    """*execution* produced the artifact *sha* (ADR-0034 §1, P21 D5): its Artifact
    row when the bytes are new, its producer record, and `artifact.recorded`."""
    if tx.get(entities.Artifact, sha) is None:
        tx.insert(entities.Artifact(id=sha, media_type=media_type, size=size), actor=actor)
    rec = entities.ArtifactRecord(id=ids.new_id('artifact_record'), artifact_id=sha,
                                  produced_by=Ref('execution', execution.id), kind=kind,
                                  task_id=execution.task_id, mission_id=execution.mission_id,
                                  label=label)
    tx.insert(rec, actor=actor)
    m = lifecycle.load(tx, entities.Mission, execution.mission_id).entity
    tx.append(new_event('artifact.recorded', Ref('artifact_record', rec.id), actor, payload={
        'artifact_id': sha, 'kind': kind, 'execution': execution.id,
        'task_id': execution.task_id}, workspace=m.workspace_id, project=m.project_id))
    return rec


def artifacts_of(conn, e):
    """What *e* produced, oldest first: {artifact_id, kind, label}."""
    return [{'artifact_id': r.entity.artifact_id, 'kind': r.entity.kind,
             'label': r.entity.label}
            for r in rows.where(conn, entities.ArtifactRecord, task_id=e.task_id)
            if r.entity.produced_by.id == e.id]


def inventory(sha):
    """The recorded inventory of what an execution's settings sources load
    (ADR-0049), read from its artifact; None when none was recorded, and an
    `unavailable` note — never a guess — when the artifact cannot be read."""
    if sha is None:
        return None
    import json
    from ...infra.artifacts import store
    try:
        got = json.loads(store.get(sha).decode('utf-8'))
    except (OSError, ValueError) as e:
        return {'unavailable': 'the inventory %s cannot be read: %s' % (sha, type(e).__name__)}
    return got if isinstance(got, dict) else {'unavailable': 'the inventory is not an object'}


def entity(conn, execution_id):
    """The Execution entity itself (what a read of its output needs)."""
    row = rows.get(conn, entities.Execution, execution_id)
    if row is None:
        raise lifecycle.NotFound(execution_id)
    return row.entity


def checkpoints(conn, execution_id, homes=None):
    """The checkpoints of an execution (p12-design-gate §19): at most one. What the
    task and mission authored is as written; the rest (hook reasons, the agent's
    last error) is system text and is projected."""
    if rows.get(conn, entities.Execution, execution_id) is None:
        raise lifecycle.NotFound(execution_id)
    got = rows.where(conn, entities.Checkpoint, execution_id=execution_id)
    if not got:
        return []
    homes = _homes(conn, homes)
    return [system_value(r.entity.to_dict(), homes,
                         authored=(('objective',), ('constraints',), ('success_criteria',)))
            for r in got]


def of_task(conn, task_id):
    from .queries import view as v
    if rows.get(conn, entities.Task, task_id) is None:
        raise lifecycle.NotFound(task_id)
    out = []
    from ..execution import pressure
    for r in rows.where(conn, entities.Execution, task_id=task_id):
        d = v(r)
        d.pop('hook_token_hash', None)
        d['context'] = pressure.view(r.entity)
        out.append(d)
    return out

