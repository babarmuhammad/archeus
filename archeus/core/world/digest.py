"""The since-you-left digest (S14; context-and-knowledge §9; p4-design-gate §9).

User-visible events after the owner's cursor, grouped by what they are about
— a mission (the plan, task, execution, verification and review events of a
mission fold into it), a repository, a project or a knowledge item — each
group with a deterministic headline. `up_to_seq` is the head of the read, so
acknowledging it acknowledges exactly what was shown. A repository going
STALE is bookkeeping, not news, and is not reported. A message is not a row of
its own (R13-03): a mission thread's messages fold into the mission, and the
primary conversation's into one `new_messages` row counting the messages.
"""

from ...infra.db import rows
from ...infra.eventlog import outbox
from ..application.world import owner
from ..domain import entities

ORDER = ('needs_you', 'drift_found', 'failed', 'completed', 'drift_cleared', 'progressed',
         'new_messages')
NEEDS_YOU = ('APPROVAL_REQUIRED', 'REVIEWING', 'BLOCKED')
_OF_MISSION = {'plan': entities.Plan, 'task': entities.Task, 'execution': entities.Execution,
               'review': entities.Review, 'verification': entities.Verification}


def _mission_of(conn, kind, entity_id):
    cls = _OF_MISSION.get(kind)
    if cls is None:
        return None
    row = rows.get(conn, cls, entity_id)
    if row is None:
        return None
    mid = getattr(row.entity, 'mission_id', None)
    if mid is None and getattr(row.entity, 'plan_id', None):
        plan = rows.get(conn, entities.Plan, row.entity.plan_id)
        mid = plan and plan.entity.mission_id
    return mid


def _thread_of(conn, message_id):
    """(kind, id) a message folds into: its mission, or its conversation."""
    m = rows.get(conn, entities.Message, message_id)
    c = m and rows.get(conn, entities.Conversation, m.entity.conversation_id)
    if c is None:
        return 'message', message_id
    if c.entity.mission_id:
        return 'mission', c.entity.mission_id
    return 'conversation', c.entity.id


def _headline(conn, kind, entity_id, events, was_drifted=False):
    if kind == 'conversation':
        return 'new_messages'
    if kind == 'mission':
        m = rows.get(conn, entities.Mission, entity_id)
        state = m.entity.state if m else None
        if state in NEEDS_YOU:
            return 'needs_you'
        return {'COMPLETED': 'completed', 'FAILED': 'failed'}.get(state, 'progressed')
    if kind == 'repository':
        moves = [e for e in events if e.type == 'architecture.state_changed']
        if moves:
            last = moves[-1].payload
            if last['to'] == 'DRIFTED':
                return 'drift_found'
            if last['to'] == 'CONSISTENT' and (was_drifted or any(
                    'DRIFTED' in (e.payload['from'], e.payload['to']) for e in moves)):
                return 'drift_cleared'
    return 'progressed'


def digest(conn, *, since=None, project_id=None, mission_id=None):
    """The owner's digest, or (P12, p12-design-gate D14) a session's: the
    changes after *since* instead of the owner's cursor, and — when a mission or
    a project is named — only the groups about that mission or of that project."""
    if since is None:
        user = owner(conn)
        cursor = user.entity.last_ack_event_seq if user else 0
    else:
        cursor = since
    head, low = outbox.head(conn), outbox.floor(conn)
    start = max(cursor, low)
    groups, left_drift = {}, set()
    for r in conn.execute("SELECT * FROM events WHERE seq > ? AND seq <= ? AND visibility = 'user' "
                          "ORDER BY seq", (start, head)):
        e = outbox.decode(r)
        if e.type == 'architecture.state_changed' and e.payload.get('to') == 'STALE':
            if e.payload.get('from') == 'DRIFTED':
                left_drift.add(e.subject.id)       # remembered: a fix is news
            continue
        kind, eid = e.subject.kind, e.subject.id
        if kind == 'message':
            kind, eid = _thread_of(conn, eid)
        mid = _mission_of(conn, kind, eid)
        if mid is not None:
            kind, eid = 'mission', mid
        if (mission_id or project_id) and not (
                (mission_id and (kind, eid) == ('mission', mission_id))
                or (project_id and e.project == project_id)):
            continue
        groups.setdefault((kind, eid), []).append(e)
    out = []
    for (kind, eid), evs in groups.items():
        out.append({'ref': {'kind': kind, 'id': eid},
                    'headline': _headline(conn, kind, eid, evs, eid in left_drift),
                    # a conversation counts its messages, not their events
                    'count': len({e.subject.id for e in evs}) if kind == 'conversation'
                    else len(evs), 'first_seq': evs[0].seq, 'last_seq': evs[-1].seq,
                    'project_id': next((e.project for e in evs if e.project), None),
                    'types': sorted({e.type for e in evs})})
    out.sort(key=lambda g: (ORDER.index(g['headline']), -g['last_seq']))
    return {'from_seq': start, 'up_to_seq': head, 'count': len(out), 'groups': out,
            'truncated': cursor < low}
