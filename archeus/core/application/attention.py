"""What waits on the user (p16-design-gate §6.3, D3): a read over rows, never
a store of its own. Each item names the row that makes it (its kind and ref),
the state that row is in, and the row's own reason; the order is fixed — kind,
then oldest first — and nothing is scored. Whether an approval can be decided
now is P9's `approval_view`, reused, not re-judged here.

Also the mission timeline (D5): the events of a mission's own rows."""

from ...infra.db import rows
from ...infra.db.writer import NotFound
from ...infra.eventlog import outbox
from ..domain import entities
from .queries import approval_view

#: The kinds, in the order they are listed.
KINDS = ('approval', 'verification', 'mission', 'knowledge', 'drift', 'automation', 'account')


def _mission_of_task(conn, task_id):
    t = rows.get(conn, entities.Task, task_id)
    return t.entity.mission_id if t else None


def _project(conn, mission_id):
    m = mission_id and rows.get(conn, entities.Mission, mission_id)
    return m.entity.project_id if m else None


def _item(kind, ref_kind, row, state, reason_code, reason=None, mission_id=None,
          project_id=None, **extra):
    return dict({'kind': kind, 'ref': {'kind': ref_kind, 'id': row.entity.id},
                 'state': state, 'reason_code': reason_code, 'reason': reason,
                 'mission_id': mission_id, 'project_id': project_id,
                 'since': row.updated_at}, **extra)


def attention(conn, now=None):
    items = []
    for r in rows.where(conn, entities.Approval, **{'state': 'PENDING'}):
        a = approval_view(conn, r, now)
        items.append(_item('approval', 'approval', r, 'PENDING', r.entity.kind,
                           a['eligible_why'], r.entity.mission_id,
                           _project(conn, r.entity.mission_id),
                           eligible=a['eligible'], expires_at=r.entity.expires_at,
                           step_up=bool(r.entity.step_up)))
    for state in ('AWAITING_HUMAN', 'ERROR'):
        for r in rows.where(conn, entities.Verification, **{'state': state}):
            v = r.entity
            if state == 'ERROR' and not v.holds_mission:
                continue                # an ERROR retried by Core waits on nobody
            mid = v.subject.id if v.subject.kind == 'mission' else _mission_of_task(conn, v.subject.id)
            items.append(_item('verification', 'verification', r, state,
                               'acceptance' if state == 'AWAITING_HUMAN' else 'verifier_error',
                               v.error if state == 'ERROR' else None, mid, _project(conn, mid)))
    for r in rows.where(conn, entities.Mission):
        pb, m = r.entity.planning_blocked, r.entity
        # a planning round that asked a question or was denied waits for the user,
        # in BLOCKED or in place in PLANNING/REPLANNING (P8 D6, P9)
        if pb and m.state not in ('COMPLETED', 'CANCELLED', 'FAILED'):
            asked = '; '.join(pb.get('questions') or ()) or None
            items.append(_item('mission', 'mission', r, m.state, pb.get('kind') or 'blocked',
                               asked, m.id, m.project_id))
    for r in rows.where(conn, entities.KnowledgeItem, **{'state': 'CANDIDATE'}):
        items.append(_item('knowledge', 'knowledge_item', r, 'CANDIDATE', r.entity.type,
                           r.entity.title, project_id=r.entity.project_id))
    for r in rows.where(conn, entities.Repository,
                        **{'architecture_state': 'DRIFTED'}):
        items.append(_item('drift', 'repository', r, 'DRIFTED', 'drifted', r.entity.path,
                           project_id=r.entity.project_id))
    for r in rows.where(conn, entities.Automation, **{'state': 'SUSPENDED'}):
        items.append(_item('automation', 'automation', r, 'SUSPENDED', 'suspended',
                           r.entity.name, project_id=r.entity.project_id))
    for r in rows.where(conn, entities.Account, health='UNAUTHENTICATED'):
        items.append(_item('account', 'account', r, 'UNAUTHENTICATED', 'reauth',
                           r.entity.label))
    order = {k: i for i, k in enumerate(KINDS)}
    items.sort(key=lambda i: (order[i['kind']], i['since'], i['ref']['id']))
    return {'items': items, 'count': len(items)}


# ── the mission timeline (D5) ──

#: The rows of a mission whose events are its history, by the column that
#: names the mission; verifications name a plan instead.
_OWN = (('plan', entities.Plan), ('task', entities.Task), ('execution', entities.Execution),
        ('approval', entities.Approval), ('review', entities.Review),
        ('session', entities.Session), ('checkpoint', entities.Checkpoint))
MAX_TIMELINE = 100


def timeline(conn, mission_id, before=None, limit=50):
    """The newest *limit* events (before seq *before*) whose subject is the
    mission or one of its own rows — never another mission's."""
    if rows.get(conn, entities.Mission, mission_id) is None:
        raise NotFound(mission_id)
    subjects = {'mission': [mission_id]}
    for kind, cls in _OWN:
        subjects[kind] = [r.entity.id for r in rows.where(conn, cls, mission_id=mission_id)]
    subjects['verification'] = [r.entity.id for p in subjects['plan']
                                for r in rows.where(conn, entities.Verification, plan_id=p)]
    seqs = []
    for kind, ids in subjects.items():
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            sql = ('SELECT seq FROM events WHERE subject_kind = ? AND subject_id IN (%s)'
                   % ','.join('?' * len(chunk)))
            args = [kind, *chunk]
            if before is not None:
                sql += ' AND seq < ?'
                args.append(before)
            sql += ' ORDER BY seq DESC LIMIT ?'
            args.append(limit)
            seqs += [r['seq'] for r in conn.execute(sql, args)]
    seqs = sorted(set(seqs), reverse=True)[:limit]
    if not seqs:
        return {'mission_id': mission_id, 'events': [], 'next_before': None}
    got = conn.execute('SELECT * FROM events WHERE seq IN (%s) ORDER BY seq DESC'
                       % ','.join('?' * len(seqs)), seqs)
    events = [outbox.decode(r).to_envelope() for r in got]
    return {'mission_id': mission_id, 'events': events,
            'next_before': events[-1]['seq'] if len(events) == limit else None}
