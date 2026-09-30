"""Continuity from current durable state (p12-design-gate §9, §11): what a
returning session, or a hand-off target, is told. Read-only but for one
thing — a stale context package is replaced through P5's one recorder.

Nothing here reads a checkpoint, a brief or a session field as the state of
anything: the mission, its plan, tasks, executions and approvals are read from
their rows at the moment of the call (D9), and a session's own fields are
cursors into them (its mission link, its last-seen event, its last package).
"""

from ...infra.db import rows
from ...infra.eventlog import outbox
from ..context import assemble as context
from ..application.commands import active_plan, record_context_package
from ..domain import entities
from ..world.digest import digest


def mission_state(conn, mission_id):
    """The mission as it is now, or None when the session names none; a
    dangling link is reported, never filled in."""
    if mission_id is None:
        return None, []
    mrow = rows.get(conn, entities.Mission, mission_id)
    if mrow is None:
        return None, ['mission %s no longer exists' % mission_id]
    m = mrow.entity
    prow = active_plan(conn, m.id)
    tasks = []
    if prow is not None:
        runs = {}
        for r in rows.where(conn, entities.Execution, mission_id=m.id):
            runs[r.entity.task_id] = r.entity           # rows come oldest first
        for r in sorted(rows.where(conn, entities.Task, plan_id=prow.entity.id),
                        key=lambda r: r.entity.key):
            t, e = r.entity, runs.get(r.entity.id)
            tasks.append({'id': t.id, 'key': t.key, 'title': t.title, 'state': t.state,
                          'execution': {'id': e.id, 'state': e.state,
                                        'exit_reason': e.exit_reason} if e else None})
    needs = [{'id': a.entity.id, 'kind': a.entity.kind or a.entity.subject.kind,
              'state': a.entity.state}
             for a in rows.where(conn, entities.Approval, mission_id=m.id)
             if a.entity.state == 'PENDING']
    return {'id': m.id, 'title': m.title, 'state': m.state,
            'plan_version': prow.entity.plan_version if prow else None,
            'tasks': tasks, 'needs_you': needs}, []


def open_problems(conn, mission_id):
    """The latest checkpoint of every task of the mission's plan in force that
    is not done: history, shown as history."""
    if mission_id is None:
        return []
    prow = active_plan(conn, mission_id)
    if prow is None:
        return []
    keys = {r.entity.id: r.entity for r in rows.where(conn, entities.Task, plan_id=prow.entity.id)}
    latest = {}
    for r in rows.where(conn, entities.Checkpoint, mission_id=mission_id):
        latest[r.entity.task_id] = r.entity
    out = []
    for tid, cp in sorted(latest.items(), key=lambda x: keys[x[0]].key if x[0] in keys else ''):
        t = keys.get(tid)
        if t is None or t.state in ('SUCCEEDED', 'SKIPPED', 'CANCELLED'):
            continue
        out.append({'task_key': t.key, 'execution_id': cp.execution_id, 'trigger': cp.trigger,
                    'open_problems': list(cp.open_problems), 'next_action': cp.next_action,
                    'checkpoint_id': cp.id})
    return out


def subject(session):
    """What a session's context is assembled for (§11.1): its mission, else its
    project, else nothing."""
    if session.mission_id is not None:
        return 'mission', session.mission_id
    if session.project_id is not None:
        return 'project', session.project_id
    return None


def package(tx, actor, session):
    """{package_id, as_of_seq, rebuilt}: the session's last package when it is
    fresh for the same subject (D13), else a new one recorded through P5 (D12).
    A package id the session names that no longer exists is stale."""
    want = subject(session)
    if want is None:
        return {'package_id': None, 'as_of_seq': None, 'rebuilt': False}
    if session.context_package_id is not None:
        prow = rows.get(tx.conn, entities.ContextPackage, session.context_package_id)
        if prow is not None and (prow.entity.subject_kind, prow.entity.subject_id) == want \
                and context.fresh(tx.conn, prow.entity):
            return {'package_id': prow.entity.id, 'as_of_seq': prow.entity.as_of_seq,
                    'rebuilt': False}
    pkg = record_context_package(tx, actor=actor, subject_kind=want[0], subject_id=want[1])
    return {'package_id': pkg.id, 'as_of_seq': pkg.as_of_seq, 'rebuilt': True}


def brief(conn, session, ctx, head=None):
    """The continuity brief for *session* now (§11.4). `ctx` is `package()`'s
    answer (or a preview's)."""
    head = outbox.head(conn) if head is None else head
    state, missing = mission_state(conn, session.mission_id)
    changes = digest(conn, since=session.last_seen_seq, project_id=session.project_id,
                     mission_id=session.mission_id)
    if session.mission_id is None and session.project_id is None:
        changes = dict(changes, groups=[], count=0)     # a session scoped to nothing
    return {'session': {'id': session.id, 'harness_id': session.harness_id,
                        'model': session.model, 'effort': session.effort,
                        'last_seen_seq': session.last_seen_seq,
                        'last_active_at': session.last_active_at},
            'as_of_seq': head, 'mission': state, 'changes': changes,
            'open_problems': open_problems(conn, session.mission_id), 'context': ctx,
            'missing': missing}


def handoff_state(conn, session, ctx, head=None):
    """What a hand-off target of a mission-linked session is given: the brief
    without the source's cursor (the target has seen nothing)."""
    head = outbox.head(conn) if head is None else head
    state, missing = mission_state(conn, session.mission_id)
    return {'mission': state, 'open_problems': open_problems(conn, session.mission_id),
            'context': ctx, 'missing': missing, 'as_of_seq': head}
