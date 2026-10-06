"""Checkpoints (p12-design-gate §8; execution-architecture §6): what an ended
execution did, derived by Core from the rows and from facts the manager
measured, never asked of the agent and never a transcript.

One per ended execution that ran (D5), written in the transaction of the end:
ENDED_OK, ENDED_ERROR, ENDED_KILLED and ENDED_HANDOFF with a process; none for
ABANDONED (nothing ran) or ENDED_REJECTED (P9's decision is the record). A
checkpoint is history: nothing reads it to decide a state, and the only thing
Core reads from it is its rendering (the next execution's prompt suffix, a
hand-off artifact).

`facts` come from outside the transaction (the node reads the workdir, the
manager reads the stream) as plain data:
    files_changed  `git diff --stat` lines of the workdir
    decisions      stream lines beginning `DECISION:` (the task contract's convention)
    last_error     the stream's last error line
"""

from ...infra.artifacts import store as artifacts
from ...infra.db import rows
from ...infra.eventlog import outbox
from ..domain import entities, ids
from ..domain.events import new_event
from ..domain.values import Ref
from ..redact import redact
from ..sessions import render

#: at most this many of each list: a checkpoint is a summary, not a log
MAX_ITEMS = 30
_TRIGGER = {'pressure': 'pressure', 'limit': 'account_change', 'ceiling': 'account_change',
            'handoff_user': 'user', 'pause_timeout': 'pause'}


def trigger_of(e):
    """Why *e* ended, in the checkpoint's vocabulary (§8.1)."""
    if e.state == 'ENDED_OK':
        return 'task_boundary'
    if e.state == 'ENDED_HANDOFF':
        return _TRIGGER.get(e.stop_reason, 'pressure')
    if e.state == 'ENDED_KILLED' and e.stop_reason == 'pause_timeout':
        return 'pause'
    return 'failure'


def ran(e):
    """Whether *e* had a process, which is what earns it a checkpoint."""
    return e.process_seq >= 1 and e.state not in ('ABANDONED', 'ENDED_REJECTED')


def _text(x):
    return str(x.get('text') if isinstance(x, dict) else x)


def _clip(items):
    return tuple(redact(str(i))[:300] for i in list(items)[:MAX_ITEMS])


def derive(tx, *, actor, execution, facts=None, context_package_id=None):
    """Write the checkpoint of *execution* (already in its terminal state) and
    its rendering; returns the Checkpoint."""
    e, facts = execution, facts or {}
    m = rows.get(tx.conn, entities.Mission, e.mission_id).entity
    t = rows.get(tx.conn, entities.Task, e.task_id).entity
    plan = rows.get(tx.conn, entities.Plan, e.plan_id).entity if e.plan_id else None
    steps = []
    if plan is not None:
        for r in sorted(rows.where(tx.conn, entities.Task, plan_id=plan.id),
                        key=lambda r: r.entity.key):
            steps.append('%s %s: %s' % (r.entity.key, r.entity.title, r.entity.state))
    problems = ['%s: %s' % (ev.payload.get('decision'), ev.payload.get('reason'))
                for ev in _hooks(tx.conn, e.id)
                if ev.payload.get('decision') in ('deny', 'halt')]
    if e.failure:
        problems.append('the harness reported a %s failure' % e.failure)
    if e.exit_code not in (None, 0):
        problems.append('the process exited with code %s' % e.exit_code)
    if facts.get('last_error'):
        problems.append('last error: %s' % facts['last_error'])
    decisions = list(facts.get('decisions') or ())
    decisions += ['%s (knowledge %s)' % (k.entity.title, k.entity.id)
                  for k in rows.where(tx.conn, entities.KnowledgeItem)
                  if k.entity.type == 'DECISION' and k.entity.state == 'CONFIRMED'
                  and k.entity.project_id == m.project_id][:MAX_ITEMS]
    checks = ['%s: %s' % (v.entity.verifier, v.entity.state)
              for v in rows.where(tx.conn, entities.Verification)
              if v.entity.subject.kind == 'task' and v.entity.subject.id == t.id]
    cp = entities.Checkpoint(
        id=ids.new_id('checkpoint'), execution_id=e.id, mission_id=m.id,
        trigger=trigger_of(e), task_id=t.id, session_id=e.session_id,
        plan_id=plan.id if plan else None, plan_version=plan.plan_version if plan else None,
        as_of_seq=outbox.head(tx.conn), objective=redact(t.objective or t.title),
        constraints=_clip(_text(c) for c in list(m.constraints) + list(t.boundaries)),
        success_criteria=_clip([_text(c) for c in m.success_criteria]
                               + [_text(a) for a in t.acceptance]),
        completed_steps=_clip(steps), files_changed=_clip(facts.get('files_changed') or ()),
        decisions=_clip(decisions), open_problems=_clip(problems), verification=_clip(checks),
        next_action='', context_package_id=context_package_id or m.context_package_id,
        usage=dict(e.usage) if e.usage else None)
    sha = artifacts.put(render.checkpoint(cp).encode('utf-8'))
    cp = entities.Checkpoint(**dict(cp.to_dict(), artifact_sha=sha))
    tx.insert(cp, actor=actor)
    tx.append(new_event('checkpoint.created', Ref('checkpoint', cp.id), actor,
                        payload={'execution': e.id, 'trigger': cp.trigger, 'task_id': t.id},
                        workspace=m.workspace_id, project=m.project_id))
    return cp


def _hooks(conn, execution_id):
    return [outbox.decode(r) for r in conn.execute(
        "SELECT * FROM events WHERE subject_kind = 'execution' AND subject_id = ? "
        "AND type = 'execution.hook' ORDER BY seq", (execution_id,))]


def of_execution(conn, execution_id):
    got = rows.where(conn, entities.Checkpoint, execution_id=execution_id)
    return got[0].entity if got else None


def text_of(cp):
    """The rendering of a checkpoint, or a statement that it is unavailable —
    never an invented one (§18)."""
    try:
        return artifacts.get(cp.artifact_sha).decode('utf-8')
    except (OSError, ValueError, TypeError):
        return ('[checkpoint %s of execution %s is unavailable: its rendering could not be '
                'read. Continue from the task and the workdir.]' % (cp.id, cp.execution_id))
