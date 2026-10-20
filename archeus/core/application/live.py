"""Live work (ADR-0043 §2) and the context of an execution (ADR-0047 §9).

`live_work(conn)` is the one derivation of the work in flight: every execution
in a live state, with its mission, task, workspace, resources, states, what it
has produced, what it waits on, its hand-off lineage and its context. The
`status` verb and `/v1/status.live` read it; nothing else derives it.

`explain(conn, e)` answers "why" for an execution from its records only — the
route decision's explanation, the reasons its transitions recorded, its
checkpoint and its context basis — never from a model's account of itself.

Not here yet: own calls in flight (ADR-0043 §2's second kind) and recorded
artifacts (the producer record, V1-3); both are P21's, outside the D-26 slice.
"""

from ...infra.db import rows
from ...infra.eventlog import outbox
from ..domain import entities
from ..execution import checkpoint, pressure
from .executions import LIVE


def transitions(conn, execution_id):
    """[(from, to, reason)] of one execution, oldest first."""
    return [(ev.payload.get('from'), ev.payload.get('to'), ev.payload.get('reason'))
            for ev in (outbox.decode(r) for r in conn.execute(
                "SELECT * FROM events WHERE subject_kind = 'execution' AND subject_id = ? "
                "AND type = 'execution.state_changed' ORDER BY seq", (execution_id,)))]


def _asked(conn, execution_id):
    """The reason the execution was asked to hand off, or None."""
    got = [why for _f, to, why in transitions(conn, execution_id) if to == 'HANDING_OFF']
    return got[-1] if got else None


def chain(conn, e):
    """The executions *e* continues, nearest first (its `handoff_from` ancestry)."""
    out, cur = [], e.handoff_from
    while cur is not None:
        prev = rows.get(conn, entities.Execution, cur).entity
        out.append(prev)
        cur = prev.handoff_from
    return out


def handoff_of(conn, e):
    """{from, count, reason}: what *e* continues and why that one handed off."""
    before = chain(conn, e)
    return {'from': e.handoff_from, 'count': len(before),
            'reason': _asked(conn, e.handoff_from) if e.handoff_from else None}


def live_work(conn, project_id=None):
    """Every execution in a live state (ADR-0043 §2), oldest first."""
    out = []
    for r in rows.where(conn, entities.Execution):
        e = r.entity
        if e.state not in LIVE:
            continue
        m = rows.get(conn, entities.Mission, e.mission_id).entity
        if project_id is not None and m.project_id != project_id:
            continue
        t = rows.get(conn, entities.Task, e.task_id).entity
        waits = None
        if e.state == 'AWAITING_APPROVAL':
            waits = 'approval'
        elif e.state == 'PAUSED':
            waits = 'resume'
        out.append({
            'kind': 'execution', 'id': e.id, 'mission_id': m.id, 'mission_title': m.title,
            'project_id': m.project_id, 'task_id': t.id, 'task_key': t.key,
            'task_title': t.title, 'task_state': t.state, 'state': e.state,
            'attempt': e.attempt, 'workdir': e.workdir, 'branch': e.branch,
            'harness_id': e.harness_id, 'account_id': e.account_id, 'model': e.model,
            'effort': e.effort, 'route_decision_id': e.route_decision_id,
            'checkpoints': len(rows.where(conn, entities.Checkpoint, task_id=t.id)),
            'waits_on': waits, 'handoff': handoff_of(conn, e),
            'handing_off': _asked(conn, e.id) if e.state == 'HANDING_OFF' else None,
            'context': pressure.view(e)})
    return out


def explain(conn, e):
    """Why *e* runs where it runs, and why it stopped or continued, in words."""
    parts = []
    if e.route_decision_id is not None:
        rd = rows.get(conn, entities.RouteDecision, e.route_decision_id)
        if rd is not None and rd.entity.explanation:
            parts.append('Routing: %s' % rd.entity.explanation)
    ctx = pressure.view(e)
    parts.append('Context (%s): %s.' % (ctx['quality'], ctx['summary']))
    if e.handoff_from is not None:
        h = handoff_of(conn, e)
        parts.append('It continues execution %s in a fresh session (hand-off %d of its chain)'
                     '%s.' % (e.handoff_from, h['count'],
                              ': %s' % h['reason'] if h['reason'] else ''))
    asked = _asked(conn, e.id)
    if asked:
        parts.append('It was asked to hand off: %s.' % asked)
    ended = [why for _f, to, why in transitions(conn, e.id) if to == e.state]
    if e.state == 'ENDED_HANDOFF' and ended:
        parts.append('It ended: %s%s.' % (ended[-1], ' (charged)' if e.charged else ''))
        nxt = [x.entity.id for x in rows.where(conn, entities.Execution, task_id=e.task_id)
               if x.entity.handoff_from == e.id]
        parts.append('Continued by execution %s.' % nxt[0] if nxt else
                     'No continuation was created.')
    cp = checkpoint.of_execution(conn, e.id)
    if cp is not None:
        parts.append('What was preserved: checkpoint %s (%s), %d completed step(s), %d '
                     'file change(s), %d open problem(s).'
                     % (cp.id, cp.trigger, len(cp.completed_steps), len(cp.files_changed),
                        len(cp.open_problems)))
    return ' '.join(parts)
