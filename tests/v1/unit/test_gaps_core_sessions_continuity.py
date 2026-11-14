"""T-314: the highest-risk uncovered branches of archeus/core/sessions/continuity.py.

Fail-closed and containment first: the dangling mission link is reported and never
filled in, a session scoped to nothing sees no change groups, a hand-off target is
never handed the source's cursor, and a context package is reused only when it is
the session's own subject's AND still fresh — otherwise P5's one recorder runs
again. Then the boundary values of the mission view (the plan in force, the latest
execution per task, task-key order, PENDING approvals only) and of the open-problems
list (terminated tasks dropped, the latest checkpoint per task, home paths projected
through the one lazily built Homes). Same real database and in-process style as
tests/v1/unit/test_hook_mailbox_origin.py and the faked-Homes seam of
test_t144_checkpoint_consumption.py: `Database.open()` on the test's own
ARCHEUS_HOME, direct `tx.insert` seeds through the writer, and P5's recorder
(`record_context_package`, tested by P5's own cards) replaced by a counting fake so
what is pinned here is continuity's *decision* to call it, never what P5 records.
No process, no network, no OS call: the only Homes is built from a tmp_path string
with `shorts` injected, exactly as the homes tests do.
"""

import hashlib
from types import SimpleNamespace

import pytest

from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes
from archeus.core.sessions import continuity
from archeus.infra.db import Database
from archeus.infra.eventlog import outbox

REC_ID = 'ctx_recording_' + '0' * 14        # the fake recorder's package id (returned as-is)


@pytest.fixture
def rdb():
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def who():
    return Ref('user_device', ids.new_id('principal'))


@pytest.fixture
def recorder(monkeypatch):
    """P5's recorder as a counter: continuity may build no package itself, so what
    matters is WHEN it decides to call the one recorder there is, with what."""
    calls = []

    def fake(tx, *, actor, subject_kind, subject_id, query=None):
        calls.append({'tx': tx, 'actor': actor, 'subject_kind': subject_kind,
                      'subject_id': subject_id, 'query': query})
        return SimpleNamespace(id=REC_ID, as_of_seq=777)
    monkeypatch.setattr(continuity, 'record_context_package', fake)
    return calls


def _seed(db, who, entities_, events=()):
    """One writer command: the rows in list order, then the events. Any mutation
    must record an event, so a rows-only seed carries one system-visibility
    `context_package.created`: invisible to the user-visible digest and to
    `context.fresh` alike, and never named by any session under test."""
    def cmd(tx, *, actor):
        for e in entities_:
            tx.insert(e, actor=actor)
        for e in events:
            tx.append(e)
        if entities_ and not events:
            tx.append(_event('context_package.created',
                             Ref('context_package', ids.new_id('context_package')), actor))
    db.writer.execute(cmd, {'actor': who})


def _mission(mid, state='APPROVED'):
    return entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                            objective='o', state=state)


def _plan(mid, pid, version=1):
    return entities.Plan(id=pid, mission_id=mid, plan_version=version, state='APPROVED')


def _task(mid, pid, tid, key, state='RUNNING'):
    return entities.Task(id=tid, plan_id=pid, mission_id=mid, key=key, title='T ' + key,
                         kind='code_change', state=state)


def _execution(mid, tid, eid, attempt=1, state='ENDED_ERROR', exit_reason='error'):
    return entities.Execution(id=eid, task_id=tid, mission_id=mid, attempt=attempt,
                              state=state, exit_reason=exit_reason, workdir='w',
                              isolated=False)


def _checkpoint(mid, tid, eid, open_problems=(), next_action='', cid=None):
    return entities.Checkpoint(id=cid or ids.new_id('checkpoint'), execution_id=eid,
                               mission_id=mid, task_id=tid, trigger='failure',
                               open_problems=tuple(open_problems), next_action=next_action)


def _approval(mid, pid, tid, aid, who_, state, kind=None):
    return entities.Approval(id=aid, subject=Ref('task', tid),
                             action_hash=hashlib.sha256(aid.encode()).hexdigest(),
                             requested_by=who_.id, kind=kind, mission_id=mid,
                             plan_id=pid, task_id=tid, state=state,
                             expires_at='2099-01-01T00:00:00Z')


def _package(mid, cid, subject_kind='mission', subject_id=None, as_of_seq=0):
    return entities.ContextPackage(id=cid, workspace_id=ids.GLOBAL_WORKSPACE,
                                   subject_kind=subject_kind,
                                   subject_id=mid if subject_id is None else subject_id,
                                   as_of_seq=as_of_seq)


def _session(sid, mission_id=None, project_id=None, package_id=None, last_seen=0):
    return entities.Session(id=sid, harness_id='fake', workspace_id=ids.GLOBAL_WORKSPACE,
                            cwd='w', mode='manual', mission_id=mission_id,
                            project_id=project_id, context_package_id=package_id,
                            last_seen_seq=last_seen, model='m', effort='high')


def _event(type_, subject, who_, **kw):
    return new_event(type_, subject, who_, payload=kw.pop('payload', {}),
                     workspace=ids.GLOBAL_WORKSPACE, **kw)


# ── mission_state: the dangling link and the no-mission session (fail-closed) ──


def test_dangling_mission_link_is_reported_never_filled_in(rdb):
    """continuity.py:24-25 `if mrow is None: return None, [... no longer exists]`:
    removing it dereferences None (crash in the returning session); softening it
    to (None, []) lets a session whose mission was deleted continue believing
    nothing is missing — the dangling link would be silently filled in."""
    gone = ids.new_id('mission')
    with rdb.read() as conn:
        state, missing = continuity.mission_state(conn, gone)
    assert state is None
    assert missing == ['mission %s no longer exists' % gone]


def test_session_naming_no_mission_is_not_a_missing_one(rdb):
    """continuity.py:22-23 `if mission_id is None: return None, []`: inverting it
    makes every missionless session report its own mission as 'no longer exists'
    instead of the neutral no-mission answer."""
    with rdb.read() as conn:
        assert continuity.mission_state(conn, None) == (None, [])


# ── mission_state: plan in force, execution recency, task order, approvals ─────


def test_highest_plan_version_is_the_one_in_force_and_only_its_tasks_show(rdb, who):
    """continuity.py:27 (active_plan's max) + :32 `rows.where(Task, plan_id=prow.id)`:
    inverting the plan pick (lowest version) or widening the task query to the
    mission would list a superseded plan's tasks as current work and report a
    stale plan_version as the one in force."""
    mid, p1, p2 = ids.new_id('mission'), ids.new_id('plan'), ids.new_id('plan')
    t_old, t_new = ids.new_id('task'), ids.new_id('task')
    _seed(rdb, who, [_mission(mid), _plan(mid, p1, 1), _plan(mid, p2, 2),
                     _task(mid, p1, t_old, 't-old'), _task(mid, p2, t_new, 't-new')])
    with rdb.read() as conn:
        state, missing = continuity.mission_state(conn, mid)
    assert missing == [] and state['plan_version'] == 2
    assert [t['key'] for t in state['tasks']] == ['t-new']


def test_tasks_listed_in_key_order_with_no_execution_as_none(rdb, who):
    """continuity.py:32-33 `sorted(..., key=lambda r: r.entity.key)` and the
    `if e else None` of :35-36: dropping the sort shows insertion order (b before
    a here); dropping the None branch fabricates or crashes on an execution for
    the task that never ran."""
    mid, pid = ids.new_id('mission'), ids.new_id('plan')
    tb, ta, ea = ids.new_id('task'), ids.new_id('task'), ids.new_id('execution')
    _seed(rdb, who, [_mission(mid), _plan(mid, pid),
                     _task(mid, pid, tb, 'b'), _task(mid, pid, ta, 'a'),
                     _execution(mid, ta, ea)])
    with rdb.read() as conn:
        state, _ = continuity.mission_state(conn, mid)
    assert [t['key'] for t in state['tasks']] == ['a', 'b']
    by_key = {t['key']: t for t in state['tasks']}
    assert by_key['b']['execution'] is None
    assert by_key['a']['execution'] == {'id': ea, 'state': 'ENDED_ERROR',
                                        'exit_reason': 'error'}


def test_latest_execution_of_a_task_wins_over_earlier_attempts(rdb, who):
    """continuity.py:30-31 (`runs[task_id] = r.entity` over rows.where's oldest-
    first order): inverting that order, or first-wins (`setdefault`), would tell a
    returning session that a task's FIRST crashed attempt is its current
    execution."""
    mid, pid = ids.new_id('mission'), ids.new_id('plan')
    tid = ids.new_id('task')
    e1, e2 = ids.new_id('execution'), ids.new_id('execution')
    _seed(rdb, who, [_mission(mid), _plan(mid, pid), _task(mid, pid, tid, 't1'),
                     _execution(mid, tid, e1, attempt=1),
                     _execution(mid, tid, e2, attempt=2, state='RUNNING',
                                exit_reason=None)])
    with rdb.read() as conn:
        state, _ = continuity.mission_state(conn, mid)
    assert state['tasks'][0]['execution']['id'] == e2
    assert state['tasks'][0]['execution']['state'] == 'RUNNING'


def test_needs_you_holds_only_pending_approvals(rdb, who):
    """continuity.py:38-40 `if a.entity.state == 'PENDING'`: dropping that filter
    tells the session an approval its user ALREADY decided is still waiting on it
    — a fail-open lie about a human gate. The kept entries carry the stored kind
    (explicit 'action', or the subject's kind through the `kind or subject.kind`
    chain for the row that stores none)."""
    mid, pid = ids.new_id('mission'), ids.new_id('plan')
    t1, t2, t3 = ids.new_id('task'), ids.new_id('task'), ids.new_id('task')
    a1, a2, a3 = (ids.new_id('approval') for _ in range(3))
    _seed(rdb, who, [_mission(mid), _plan(mid, pid), _task(mid, pid, t1, 'a'),
                     _task(mid, pid, t2, 'b'), _task(mid, pid, t3, 'c'),
                     _approval(mid, pid, t1, a1, who, 'PENDING', kind=None),
                     _approval(mid, pid, t2, a2, who, 'PENDING', kind='action'),
                     _approval(mid, pid, t3, a3, who, 'APPROVED', kind='task')])
    with rdb.read() as conn:
        state, _ = continuity.mission_state(conn, mid)
    assert sorted((n['id'], n['kind'], n['state']) for n in state['needs_you']) == \
        sorted([(a1, 'task', 'PENDING'), (a2, 'action', 'PENDING')])


# ── open_problems: empty by refusal; terminations and orphans dropped ──────────


def test_open_problems_empty_for_no_mission_and_for_a_planless_mission(rdb, who):
    """continuity.py:52-53 (`if prow is None: return []`): without the plan guard
    the code dereferences the missing plan (AttributeError) instead of answering
    empty; the `mission_id is None` early return at :49-50 pins the contract
    itself (it is defensive: a `mission_id = NULL` row query returns nothing, so
    its removal alone changes no DB-observable behaviour — the assertion here is
    that callers get [] rather than an exception)."""
    mid = ids.new_id('mission')
    _seed(rdb, who, [_mission(mid, state='CREATED')])
    with rdb.read() as conn:
        assert continuity.open_problems(conn, None) == []
        assert continuity.open_problems(conn, mid) == []


def test_terminated_tasks_drop_their_problems_and_open_ones_sort_by_key(rdb, who):
    """continuity.py:60-61 `if t.state in ('SUCCEEDED','SKIPPED','CANCELLED'):
    continue`: inverting it hides the open task's problems AND shows the finished
    tasks' — the agent is told closed history is its live to-do (a SUCCEEDED and
    a CANCELLED task here). The sorted() of :59 orders the two open entries by
    task key, not insert order."""
    mid, pid = ids.new_id('mission'), ids.new_id('plan')
    tk, tz, ty, tw = (ids.new_id('task') for _ in range(4))
    ek, ez, ey, ew = (ids.new_id('execution') for _ in range(4))
    _seed(rdb, who, [_mission(mid), _plan(mid, pid),
                     _task(mid, pid, tk, 'k', state='SUCCEEDED'),
                     _task(mid, pid, tw, 'w', state='CANCELLED'),
                     _task(mid, pid, tz, 'z'), _task(mid, pid, ty, 'y'),
                     _execution(mid, tk, ek), _execution(mid, tz, ez),
                     _execution(mid, ty, ey), _execution(mid, tw, ew),
                     _checkpoint(mid, tk, ek, open_problems=('closed task problem',)),
                     _checkpoint(mid, tw, ew, open_problems=('cancelled task problem',)),
                     _checkpoint(mid, tz, ez, open_problems=('z open',)),
                     _checkpoint(mid, ty, ey, open_problems=('y open',))])
    with rdb.read() as conn:
        got = continuity.open_problems(conn, mid, homes=Homes())
    assert [g['task_key'] for g in got] == ['y', 'z']
    assert [g['open_problems'] for g in got] == [['y open'], ['z open']]


def test_checkpoint_of_a_task_outside_the_plan_in_force_is_dropped(rdb, who):
    """continuity.py:59 (`else ''` sorts it FIRST) and :61-62 `if t is None:
    continue`: deleting that continue crashes on t.key; widening the task lookup
    to any plan would replay a superseded plan's checkpoint as a live open
    problem — here the orphan task is RUNNING, so only the plan filter drops it."""
    mid, p1, p2 = ids.new_id('mission'), ids.new_id('plan'), ids.new_id('plan')
    t_old, t_now, e_old = ids.new_id('task'), ids.new_id('task'), ids.new_id('execution')
    _seed(rdb, who, [_mission(mid), _plan(mid, p1, 1), _plan(mid, p2, 2),
                     _task(mid, p1, t_old, 't1'), _task(mid, p2, t_now, 't1'),
                     _execution(mid, t_old, e_old),
                     _checkpoint(mid, t_old, e_old, open_problems=('orphan problem',))])
    with rdb.read() as conn:
        assert continuity.open_problems(conn, mid, homes=Homes()) == []


def test_latest_checkpoint_of_a_task_is_the_one_shown(rdb, who):
    """continuity.py:55-56 (`latest[task_id] = r.entity` over rows.where's oldest-
    first order): a first-wins variant (or inverted ORDER BY rowid) replays the
    EARLIEST checkpoint of a retried task, hiding what its last attempt hit."""
    mid, pid = ids.new_id('mission'), ids.new_id('plan')
    tid = ids.new_id('task')
    e1, e2 = ids.new_id('execution'), ids.new_id('execution')
    cp1 = _checkpoint(mid, tid, e1, open_problems=('first attempt hurt',), next_action='old')
    cp2 = _checkpoint(mid, tid, e2, open_problems=('last attempt hurts',),
                      next_action='new', cid=ids.new_id('checkpoint'))
    _seed(rdb, who, [_mission(mid), _plan(mid, pid), _task(mid, pid, tid, 't1'),
                     _execution(mid, tid, e1, attempt=1),
                     _execution(mid, tid, e2, attempt=2), cp1, cp2])
    with rdb.read() as conn:
        (got,) = continuity.open_problems(conn, mid, homes=Homes())
    assert got['checkpoint_id'] == cp2.id and got['next_action'] == 'new'
    assert got['open_problems'] == ['last attempt hurts']


def test_open_problem_text_is_projected_and_homes_built_exactly_once(rdb, who, tmp_path):
    """continuity.py:62-66: `if cp.open_problems and not shown` builds the
    projection source ONCE (drop `not shown` and every problem re-runs the lazy
    build the homes tests treat as expensive), and the projection itself is
    system_value(...): drop it and a raw account home reaches the session's brief
    — the exact leak class T-144 closed."""
    home = str(tmp_path / 'T314-Home')
    mid, pid = ids.new_id('mission'), ids.new_id('plan')
    t1, t2, e1, e2 = (ids.new_id(k) for k in ('task', 'task', 'execution', 'execution'))
    _seed(rdb, who, [_mission(mid), _plan(mid, pid), _task(mid, pid, t1, 'a'),
                     _task(mid, pid, t2, 'b'),
                     _execution(mid, t1, e1), _execution(mid, t2, e2),
                     _checkpoint(mid, t1, e1, open_problems=('cannot read %s/x' % home,)),
                     _checkpoint(mid, t2, e2, open_problems=('denied %s/y' % home,))])
    builds = []

    def lazy():
        builds.append(1)
        return Homes([home], shorts=lambda _: None)
    with rdb.read() as conn:
        got = continuity.open_problems(conn, mid, homes=lazy)
    assert [g['open_problems'] for g in got] == [['cannot read its home/x'],
                                                 ['denied its home/y']]
    assert len(builds) == 1


def test_checkpoint_without_problems_never_builds_homes(rdb, who, tmp_path):
    """continuity.py:62 `if cp.open_problems and not shown` (the first conjunct)
    and the ternary's `if cp.open_problems else []` at :65-66: with the conjunct
    dropped an empty checkpoint still forces the lazy Homes build; without the
    ternary an empty list would be projected through a shown[0] that was never
    built (IndexError) instead of staying the empty list it must be."""
    mid, pid, tid, eid = (ids.new_id(k) for k in ('mission', 'plan', 'task', 'execution'))
    _seed(rdb, who, [_mission(mid), _plan(mid, pid), _task(mid, pid, tid, 't'),
                     _execution(mid, tid, eid),
                     _checkpoint(mid, tid, eid, open_problems=(), next_action='go')])
    builds = []

    def lazy():
        builds.append(1)
        return Homes([str(tmp_path / 'Unused')], shorts=lambda _: None)
    with rdb.read() as conn:
        (got,) = continuity.open_problems(conn, mid, homes=lazy)
    assert got['open_problems'] == [] and got['next_action'] == 'go'
    assert builds == []


# ── package / subject: fresh-or-rebuild, never a foreign or dangling package ───


def test_session_with_no_subject_is_never_handed_a_package(rdb, who, recorder):
    """continuity.py:subject() :72-76 returning None + package() :79-81
    `if want is None:`: inverting it records a package for a subject that does
    not exist (the entity's own id check raises); fail-closed says no package,
    nothing rebuilt, and P5's recorder is NEVER reached."""
    tx = SimpleNamespace(conn=None)
    out = continuity.package(tx, actor=who, session=_session(ids.new_id('session')))
    assert out == {'package_id': None, 'as_of_seq': None, 'rebuilt': False}
    assert recorder == []


def test_mission_wins_over_project_as_the_package_subject(rdb, who, recorder):
    """continuity.py:subject() :72-76 (`if session.mission_id is not None:` before
    the project): dropping that order assembles a mission session's context from
    the whole project — the §11.1 containment this module is named for; and the
    recorder is called with THE tx and actor package() was given."""
    mid, pid = ids.new_id('mission'), ids.new_id('project')
    tx = SimpleNamespace(conn=None)
    continuity.package(tx, actor=who, session=_session(ids.new_id('session'),
                                                       mission_id=mid, project_id=pid))
    continuity.package(tx, actor=who, session=_session(ids.new_id('session'),
                                                       project_id=pid))
    assert [(c['subject_kind'], c['subject_id'], c['tx'] is tx, c['actor'] is who)
            for c in recorder] == [('mission', mid, True, True), ('project', pid, True, True)]


def test_fresh_package_of_same_subject_is_reused_and_nothing_recorded(rdb, who, recorder):
    """continuity.py:82-88 (the reuse return): drop the reuse and every resume
    re-records a package through P5 (the recorder count and the returned id pin
    it); as_of_seq must come from the package row, and bookkeeping events (a
    session's own creation, the package's own creation) must not stale it."""
    mid, cid = ids.new_id('mission'), ids.new_id('context_package')
    sid = ids.new_id('session')
    _seed(rdb, who, [_mission(mid), _package(mid, cid, as_of_seq=0)],
          events=[_event('session.created', Ref('session', sid), who),
                  _event('context_package.created', Ref('context_package', cid), who)])
    with rdb.read() as conn:
        out = continuity.package(SimpleNamespace(conn=conn), actor=who,
                                 session=_session(sid, mission_id=mid, package_id=cid))
    assert out == {'package_id': cid, 'as_of_seq': 0, 'rebuilt': False}
    assert recorder == []


def test_new_mission_event_stales_package_and_p5_records_a_new_one(rdb, who, recorder):
    """continuity.py:86-87 (`and context.fresh(tx.conn, prow.entity)`) and the
    rebuild fall-through: drop the fresh check and a session is handed a package
    that predates user-visible news about its own mission; the rebuilt answer
    carries the NEW package's id and as_of_seq, and the recorder got this tx."""
    mid, cid = ids.new_id('mission'), ids.new_id('context_package')
    _seed(rdb, who, [_mission(mid), _package(mid, cid)],
          events=[_event('mission.updated', Ref('mission', mid), who)])
    sess = _session(ids.new_id('session'), mission_id=mid, package_id=cid)
    with rdb.read() as conn:
        tx = SimpleNamespace(conn=conn)
        out = continuity.package(tx, actor=who, session=sess)
    assert out == {'package_id': REC_ID, 'as_of_seq': 777, 'rebuilt': True}
    assert [(c['subject_kind'], c['subject_id']) for c in recorder] == [('mission', mid)]
    assert recorder[0]['tx'] is tx and recorder[0]['actor'] == who


def test_package_of_another_subject_is_never_reused(rdb, who, recorder):
    """continuity.py:84-86 (the `(subject_kind, subject_id) == want` guard):
    without it a session whose stale field points at its PROJECT's package is
    handed that package as its MISSION's context — a foreign subject's curated
    context presented as the session's own."""
    mid, pid = ids.new_id('mission'), ids.new_id('project')
    cid = ids.new_id('context_package')
    _seed(rdb, who, [_mission(mid), _package(mid, cid, subject_kind='project',
                                             subject_id=pid)])
    with rdb.read() as conn:
        out = continuity.package(SimpleNamespace(conn=conn), actor=who,
                                 session=_session(ids.new_id('session'), mission_id=mid,
                                                  project_id=pid, package_id=cid))
    assert out == {'package_id': REC_ID, 'as_of_seq': 777, 'rebuilt': True}
    assert recorder[0]['subject_kind'] == 'mission' and recorder[0]['subject_id'] == mid


def test_package_id_that_no_longer_exists_is_stale(rdb, who, recorder):
    """continuity.py:83-89 (`rows.get(...ContextPackage...)`; `prow is not None`):
    the session's field is a cursor, not a fact — remove the read (trusting the
    field) and a package retention pruned is still 'reused' as a live id; remove
    the None check and the deleted package crashes the resume."""
    mid = ids.new_id('mission')
    _seed(rdb, who, [_mission(mid)])
    with rdb.read() as conn:
        out = continuity.package(SimpleNamespace(conn=conn), actor=who,
                                 session=_session(ids.new_id('session'), mission_id=mid,
                                                  package_id=ids.new_id('context_package')))
    assert out == {'package_id': REC_ID, 'as_of_seq': 777, 'rebuilt': True}


# ── brief / handoff_state: digest containment, the head, no source cursor ──────


def test_session_scoped_to_nothing_sees_no_change_groups(rdb, who):
    """continuity.py:100-101 `if mission_id is None and project_id is None:
    changes = dict(changes, groups=[], count=0)`: digest() with no scope answers
    with the WHOLE log's user news; with that line removed an unrelated mission's
    events are handed to a session scoped to nothing — the control below proves
    the news is really there, so this fails only on the containment."""
    mid = ids.new_id('mission')
    _seed(rdb, who, [_mission(mid)],
          events=[_event('mission.updated', Ref('mission', mid), who)])
    from archeus.core.world.digest import digest
    with rdb.read() as conn:
        assert digest(conn, since=0)['count'] == 1        # the news exists unscoped
        out = continuity.brief(conn, _session(ids.new_id('session')), {'package_id': None})
    assert out['changes']['groups'] == [] and out['changes']['count'] == 0
    assert out['mission'] is None and out['missing'] == []


def test_project_scoped_session_gets_its_projects_news_only(rdb, who):
    """the control for the containment above: continuity.py:99 passes the session's
    project_id into digest and :100-101 does NOT zero a SCOPED session — zeroing
    unconditionally, or dropping project_id from the digest call, breaks exactly
    this test while the containment test still passes."""
    pid, mid = ids.new_id('project'), ids.new_id('mission')
    _seed(rdb, who, [_mission(mid)],
          events=[_event('mission.updated', Ref('mission', mid), who, project=pid)])
    with rdb.read() as conn:
        out = continuity.brief(conn, _session(ids.new_id('session'), project_id=pid), {})
    assert out['changes']['count'] == 1
    assert out['changes']['groups'][0]['ref'] == {'kind': 'mission', 'id': mid}


def test_brief_names_the_head_it_was_given_else_the_outbox_head(rdb, who):
    """continuity.py:97 `head = outbox.head(conn) if head is None else head`:
    inverting the fallback re-reads the log behind a preview's back (its as_of
    would not match what it previews); ignoring the caller's head makes any
    caller's number authoritative-wrong. The session block pins :103-108 —
    it must show THIS session's cursor, not an assumed-zero one."""
    mid = ids.new_id('mission')
    _seed(rdb, who, [_mission(mid)],
          events=[_event('mission.updated', Ref('mission', mid), who),
                  _event('mission.updated', Ref('mission', mid), who)])
    sess = _session(ids.new_id('session'), mission_id=mid, last_seen=1)
    with rdb.read() as conn:
        assert continuity.brief(conn, sess, {})['as_of_seq'] == outbox.head(conn)
        assert continuity.brief(conn, sess, {}, head=99)['as_of_seq'] == 99
        got = continuity.brief(conn, sess, {'package_id': 'ctx_x'})
    assert got['session'] == {'id': sess.id, 'harness_id': 'fake', 'model': 'm',
                              'effort': 'high', 'last_seen_seq': 1,
                              'last_active_at': sess.last_active_at}
    assert got['context'] == {'package_id': 'ctx_x'}


def test_handoff_target_is_given_nothing_the_source_has_seen(rdb, who):
    """continuity.py:118-127: the hand-off dict is built fresh — it has no
    'session' key: adding one (or leaking the source's last_seen_seq or model
    into it) lets the target claim as seen what only the SOURCE saw. `missing`
    still travels: a dangling mission link is reported to the target too."""
    mid, pid, tid = ids.new_id('mission'), ids.new_id('plan'), ids.new_id('task')
    eid = ids.new_id('execution')
    _seed(rdb, who, [_mission(mid), _plan(mid, pid), _task(mid, pid, tid, 't1'),
                     _execution(mid, tid, eid),
                     _checkpoint(mid, tid, eid, open_problems=('still broken',))])
    sess = _session(ids.new_id('session'), mission_id=mid, last_seen=42)
    with rdb.read() as conn:
        out = continuity.handoff_state(conn, sess, {'package_id': 'ctx_y'})
    assert set(out) == {'mission', 'open_problems', 'context', 'missing', 'as_of_seq'}
    assert out['context'] == {'package_id': 'ctx_y'} and out['missing'] == []
    assert out['as_of_seq'] == outbox.head(conn)
    assert [g['task_key'] for g in out['open_problems']] == ['t1']
    assert sess.id not in repr(out) and 'fake' not in repr(out)
    with rdb.read() as conn2:
        gone = ids.new_id('mission')
        dangling = continuity.handoff_state(
            conn2, _session(ids.new_id('session'), mission_id=gone), {})
    assert dangling['mission'] is None
    assert dangling['missing'] == ['mission %s no longer exists' % gone]


def test_brief_reports_dangling_mission_as_missing(rdb):
    """continuity.py:98-99 + 24-25 through brief: a session cannot be silenced
    about its missing mission by the rest of the brief succeeding — softening
    mission_state's report to [] here shows the session 'no mission, no problem'
    when its own cursor points at a deleted mission."""
    mid = ids.new_id('mission')
    sess = _session(ids.new_id('session'), mission_id=mid)
    with rdb.read() as conn:
        out = continuity.brief(conn, sess, {})
    assert out['mission'] is None
    assert out['missing'] == ['mission %s no longer exists' % mid]
