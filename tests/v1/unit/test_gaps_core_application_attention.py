"""T-736: the highest-risk uncovered branches of
`archeus/core/application/attention.py`, as tests.

The read is the whole of the user's "Needs you" strip and of a mission's
history, so the risk is a thing that waits being *missing* (fail-open: the user
is never told, and the mission sits there forever) and a thing that does not
wait being shown (a button for a decision that can no longer be made). Denial
and fail-closed branches come first, then the boundary values (the expiry
instant, `before`, a full page, the 500-subject chunk), then the error paths (a
route row that is not a route, a subject that names nothing).

Same seams and style as the module's closest tests
(tests/v1/integration/test_ui_seams.py and tests/v1/unit/test_fix_attention.py):
the real SQLite database on the test's own ARCHEUS_HOME, the rows a phase would
have written through the real writer, every instant fixed by the test so
nothing depends on the wall clock, homes faked through the `Homes` seam with
`path_flavour='windows'` (one behaviour on Linux and on Windows), no process, no
network, no sleep, and no file written outside `tmp_path`.
"""

import dataclasses
import hashlib
import json

import pytest

from archeus.core.application import attention
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes
from archeus.core.planning import validate
from archeus.infra.db import Database, rows
from archeus.infra.db.writer import NotFound

WS = ids.GLOBAL_WORKSPACE
ACTOR = Ref('user_device', ids.new_id('principal'))
#: every approval expiry, every `now` and every `since` comes from here or from
#: `_age` below: the answers are the same on any machine at any time
NOW = '2026-11-01T10:00:00.000Z'
ONE_MS_BEFORE = '2026-11-01T09:59:59.999Z'
LATER = '2999-01-01T00:00:00.000Z'
#: an account home, screened through the fixture below rather than the OS, so
#: the same string behaves the same on the Linux container and on Windows
HOME = 'C:/T736/Work-Claude'


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def homes():
    """The registered-home set the screens use, built the way the existing
    attention test builds it: one home, no probing (`shorts` finds nothing)."""
    return Homes([HOME], [('fake', 'fake:' + HOME.lower(), HOME)], shorts=lambda _: None,
                 path_flavour='windows')


# ── the rows a phase would have written ─────────────────────────────────────

def _tx(db, fn):
    """Run *fn* as one writer command. The writer refuses a mutation with no
    event, so each carries one about a row no test reads."""
    def run(tx, **_):
        fn(tx)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                            ACTOR, payload={}, workspace=WS))
    return db.writer.execute(run, {})


def _insert(db, *new):
    return _tx(db, lambda tx: [tx.insert(r, actor=ACTOR) for r in new])


def _age(db, cls, entity_id, when):
    """Move one row's `updated_at` (what `_item` shows as `since`) to a fixed
    instant, so an ordering assertion never depends on how long a test took."""
    _tx(db, lambda tx: tx.conn.execute(
        'UPDATE %s SET updated_at = ? WHERE id = ?' % rows.table(cls), (when, entity_id)))


def _project(db):
    pid = ids.new_id('project')
    _insert(db, entities.Project(id=pid, workspace_id=WS, name='P', root_paths=[]))
    return pid


def _mission(db, *, state='CREATED', project=None, **kw):
    mid = ids.new_id('mission')
    _insert(db, entities.Mission(id=mid, workspace_id=WS, title='M', objective='o',
                                 state=state, project_id=project, **kw))
    return mid


def _plan(db, mid, *, state='APPROVED', tasks=1, tamper=False, version=1):
    """A plan of *mid* with its tasks. Its `digest` is the real content digest
    (`validate.digest`, what `authorization.intact` recomputes) unless *tamper*,
    which stores a plan that does not match its own rows."""
    pid = ids.new_id('plan')
    ts = tuple(entities.Task(id=ids.new_id('task'), plan_id=pid, mission_id=mid,
                             key='t%d' % i, title='T%d' % i, kind='code_change',
                             state='RUNNING') for i in range(tasks))
    p = entities.Plan(id=pid, mission_id=mid, plan_version=version, state=state)
    _insert(db, dataclasses.replace(p, digest='0' * 64 if tamper else validate.digest(p, ts)), *ts)
    return pid, ts


def _execution(db, mid, pid, tid, *, state='RUNNING'):
    eid = ids.new_id('execution')
    _insert(db, entities.Execution(id=eid, task_id=tid, mission_id=mid, plan_id=pid,
                                   attempt=1, state=state))
    return eid


def _hash(seed):
    """A canonical-action hash for an approval row (unique per row: the column
    is), as the domain requires it — 64 hex."""
    return hashlib.sha256(seed.encode()).hexdigest()


def _approval(db, *, kind, mid, pid=None, digest=None, tid=None, eid=None, state='PENDING',
              expires_at=LATER, step_up=False):
    aid = ids.new_id('approval')
    subject = {'plan': ('plan', pid), 'task': ('task', tid), 'action': ('execution', eid),
               'start': ('mission', mid), 'route': ('task', tid)}[kind]
    _insert(db, entities.Approval(
        id=aid, kind=kind, subject=Ref(*subject), action_hash=_hash(aid),
        requested_by=ACTOR.id, step_up=step_up, mission_id=mid, plan_id=pid, plan_version=1,
        plan_digest=digest, task_id=tid, execution_id=eid, expires_at=expires_at, state=state))
    return aid


def _verification(db, pid, subject, *, state, holds=False, error=None, when=None):
    vid = ids.new_id('verification')
    _insert(db, entities.Verification(
        id=vid, subject=subject, verifier='generic_human', plan_id=pid, state=state,
        holds_mission=holds, error=error,
        criterion=0 if subject.kind == 'mission' else None))
    if when is not None:
        _age(db, entities.Verification, vid, when)
    return vid


def _blocked_mission(db, *, held='EXECUTING'):
    """A BLOCKED mission with one BLOCKED task (the P10 shape: routing blocks
    the task and its mission)."""
    mid, pid, tid = ids.new_id('mission'), ids.new_id('plan'), ids.new_id('task')
    _insert(db, entities.Mission(id=mid, workspace_id=WS, title='M', objective='o',
                                 state='BLOCKED', held_from=held),
            entities.Plan(id=pid, mission_id=mid, plan_version=1, state='APPROVED'),
            entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t1', title='T',
                          kind='code_change', state='BLOCKED'))
    return mid, pid, tid


def _blocked_task(db, mid, pid, key):
    """A second BLOCKED task of the same mission (so the mission has more than
    one reason to be stopped)."""
    tid = ids.new_id('task')
    _insert(db, entities.Task(id=tid, plan_id=pid, mission_id=mid, key=key, title='T',
                              kind='code_change', state='BLOCKED'))
    return tid


def _route(db, mid, tid, result, *, explanation='x', unblock_at=None):
    _insert(db, entities.RouteDecision(
        id=ids.new_id('route_decision'), subject=Ref('task', tid), result=result,
        task_id=tid, mission_id=mid, explanation=explanation, unblock_at=unblock_at,
        selected='fake' if result != 'blocked' else None))


def _items(db, *, now=NOW, homes=None, **only):
    with db.read() as conn:
        out = attention.attention(conn, now=now, homes=homes)
    assert out['count'] == len(out['items'])
    return [i for i in out['items'] if all(i[k] == v for k, v in only.items())]


def _one(db, kind, **kw):
    got = _items(db, kind=kind, **kw)
    assert len(got) == 1, 'expected exactly one %r item, got %r' % (kind, got)
    return got[0]


def _digest(db, pid):
    with db.read() as conn:
        return rows.get(conn, entities.Plan, pid).entity.digest


def _since(db, cls, entity_id):
    """The `updated_at` the writer stamped on a row: what `_item` must show as
    `since`, and nothing else."""
    with db.read() as conn:
        return rows.get(conn, cls, entity_id).updated_at


def _append(db, *events):
    return _tx(db, lambda tx: [tx.append(e) for e in events])


def _event(type_, subject, payload=None):
    return new_event(type_, Ref(*subject), ACTOR, payload=payload or {}, workspace=WS)


#: one event type per own-row kind: what `timeline` selects its history by
_OWN_EVENT = {'plan': 'plan.state_changed', 'task': 'task.state_changed',
              'execution': 'execution.state_changed', 'approval': 'approval.state_changed',
              'review': 'review.state_changed', 'session': 'session.state_changed',
              'checkpoint': 'checkpoint.created'}


def _own_rows(db, mid, *, plan):
    """Give *mid* one of every row `_OWN` names — plan, task, execution,
    approval, review, session, checkpoint — and one event about each, hung on
    the existing plan *plan*. Returns {kind: id}, the plan included."""
    made = {}

    def build(tx):
        made['plan'] = pid = plan
        made['task'] = tid = ids.new_id('task')
        made['execution'] = eid = ids.new_id('execution')
        made['approval'] = aid = ids.new_id('approval')
        made['review'] = revid = ids.new_id('review')
        made['session'] = sid = ids.new_id('session')
        made['checkpoint'] = ckid = ids.new_id('checkpoint')
        for e in (entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t', title='T',
                                kind='code_change'),
                  entities.Execution(id=eid, task_id=tid, mission_id=mid, plan_id=pid,
                                     attempt=1),
                  entities.Approval(id=aid, kind='action', subject=Ref('execution', eid),
                                    action_hash=_hash(aid), requested_by=ACTOR.id,
                                    mission_id=mid, plan_id=pid, task_id=tid, execution_id=eid,
                                    expires_at=LATER),
                  entities.Review(id=revid, mission_id=mid, reviewer='model', plan_id=pid),
                  entities.Session(id=sid, harness_id='fake', workspace_id=WS, cwd='C:/w',
                                   mode='headless', mission_id=mid, execution_id=eid),
                  entities.Checkpoint(id=ckid, execution_id=eid, mission_id=mid,
                                      trigger='task_boundary', task_id=tid, plan_id=pid)):
            tx.insert(e, actor=ACTOR)
        for kind, type_ in _OWN_EVENT.items():
            tx.append(new_event(type_, Ref(kind, made[kind]), ACTOR, payload={'seen': kind},
                                workspace=WS))
    _tx(db, build)
    return made


def _emit_events(db, specs):
    """Append one event per (type, subject) pair; return their seqs, oldest
    first."""
    seqs = []

    def fn(tx):
        for type_, subject in specs:
            seqs.append(tx.append(new_event(type_, Ref(*subject), ACTOR, payload={},
                                            workspace=WS)).seq)
    _tx(db, fn)
    return seqs


# ── fail-closed and denial: what the read must never show, and never hide ───

def test_an_approval_the_user_can_decide_now_is_listed_decidable(db):
    """attention.py:64-70 + 48-50 — the PENDING loop with `approval_view` answering
    *decidable*. Its `reason_code` is the kind, its `reason` P9's why (nothing
    here), its `ref` the approval itself, `step_up` a bool, and the project
    comes from the mission through `_project`."""
    prj = _project(db)
    mid = _mission(db, state='APPROVAL_REQUIRED', project=prj)
    pid, ts = _plan(db, mid)
    eid = _execution(db, mid, pid, ts[0].id)
    aid = _approval(db, kind='action', mid=mid, pid=pid, digest=_digest(db, pid),
                    tid=ts[0].id, eid=eid, step_up=True)
    i = _one(db, 'approval')
    assert i['ref'] == {'kind': 'approval', 'id': aid}
    assert (i['state'], i['reason_code'], i['reason']) == ('PENDING', 'action', None)
    assert i['eligible'] is True and i['expires_at'] == LATER and i['step_up'] is True
    assert (i['mission_id'], i['project_id'], i['since']) \
        == (mid, prj, _since(db, entities.Approval, aid))


def test_a_decided_approval_never_waits_on_the_user_again(db):
    """attention.py:64 — the loop is `rows.where(Approval, state='PENDING')`.
    Widen it and the strip offers a button for an approval that has already
    been answered, expired, or superseded."""
    mid = _mission(db, state='APPROVAL_REQUIRED')
    pid, _ = _plan(db, mid)
    for state in ('APPROVED', 'REJECTED', 'EXPIRED', 'SUPERSEDED', 'CONSUMED'):
        _approval(db, kind='plan', mid=mid, pid=pid, digest=_digest(db, pid), state=state)
    assert _items(db) == []


@pytest.mark.parametrize('why,setup', [
    ('expired', None),
    ('superseded', 'replan'),
    ('digest_mismatch', 'tamper'),
    ('not_awaiting', 'ended'),
], ids=['expired', 'superseded', 'digest', 'ended'])
def test_an_approval_that_cannot_be_decided_still_waits_and_names_why(db, why, setup):
    """attention.py:66-70 — whatever P9 answers, the item is listed with
    `eligible_why` as its `reason`. Hide the ineligible ones instead of showing
    them and the expired approval disappears too: the user waits for a
    decision that no longer exists, and nothing tells them."""
    mid = _mission(db, state='APPROVAL_REQUIRED')
    pid, ts = _plan(db, mid, tamper=(setup == 'tamper'))
    eid = _execution(db, mid, pid, ts[0].id, state='ENDED_OK' if setup == 'ended' else 'RUNNING')
    aid = _approval(db, kind='action', mid=mid, pid=pid, digest=_digest(db, pid),
                    tid=ts[0].id, eid=eid, expires_at=(NOW if setup is None else LATER))
    if setup == 'replan':
        _plan(db, mid, version=2)
    i = _one(db, 'approval')
    assert (i['eligible'], i['reason'], i['reason_code'], i['ref']['id']) \
        == (False, why, 'action', aid)


def test_an_approval_expires_at_its_instant_not_a_moment_later(db):
    """queries.py:446-452 → authorization.py:625-626, reached from attention.py:65: the
    guard is `expires_at <= now`. Loosen the comparison and a decision that has
    expired is offered as still decidable for as long as the row says so."""
    mid = _mission(db, state='APPROVAL_REQUIRED')
    pid, ts = _plan(db, mid)
    eid = _execution(db, mid, pid, ts[0].id)
    _approval(db, kind='action', mid=mid, pid=pid, digest=_digest(db, pid), tid=ts[0].id,
              eid=eid, expires_at=NOW)
    assert _one(db, 'approval', now=ONE_MS_BEFORE)['eligible'] is True
    assert _one(db, 'approval', now=NOW)['eligible'] is False
    assert _one(db, 'approval', now='2026-11-01T10:00:00.001Z')['reason'] == 'expired'


def test_a_stopped_verifier_waits_only_when_it_holds_the_mission(db):
    """attention.py:71-80 — of the six verification states only
    AWAITING_HUMAN, and of the ERROR rows only the ones that `holds_mission`,
    are listed; an ERROR Core retried by itself waits on nobody, and the reason
    of an AWAITING_HUMAN is always `acceptance` with no error text."""
    mid = _mission(db)
    pid, ts = _plan(db, mid)
    for state in ('PENDING', 'RUNNING', 'PASSED', 'FAILED', 'ERROR'):
        _verification(db, pid, Ref('task', ts[0].id), state=state, error='runner gone')
    _verification(db, pid, Ref('task', ts[0].id), state='ERROR', holds=True, error='runner gone')
    assert [(i['state'], i['reason_code'], i['reason']) for i in _items(db, kind='verification')] \
        == [('ERROR', 'verifier_error', 'runner gone')]
    _verification(db, pid, Ref('mission', mid), state='AWAITING_HUMAN')
    (human,) = [i for i in _items(db, kind='verification') if i['state'] == 'AWAITING_HUMAN']
    assert (human['reason_code'], human['reason'], human['mission_id']) \
        == ('acceptance', None, mid)


def test_a_verification_of_a_task_that_is_gone_still_waits_with_no_mission(db):
    """attention.py:43-45 + 76-80 — `_mission_of_task` answers None for a
    subject this database no longer holds. The item must still be listed (it
    waits) with no mission and no project, rather than hide the fact or raise."""
    mid = _mission(db)
    pid, _ = _plan(db, mid)
    vid = _verification(db, pid, Ref('task', ids.new_id('task')), state='AWAITING_HUMAN')
    (lost,) = [i for i in _items(db, kind='verification') if i['ref']['id'] == vid]
    assert (lost['mission_id'], lost['project_id'], lost['state']) == (None, None,
                                                                       'AWAITING_HUMAN')
    _verification(db, pid, Ref('mission', 'msn_' + '0' * 26), state='ERROR', holds=True)
    assert [i['project_id'] for i in _items(db, kind='verification')
            if i['mission_id'] == 'msn_' + '0' * 26] == [None]


def test_a_mission_that_finished_waits_on_nobody_even_with_a_stalled_planning(db):
    """attention.py:85 — `m.state not in ('COMPLETED', 'CANCELLED', 'FAILED')`.
    Unguarded, a mission whose result is in still asks a question nobody can
    answer; inverted, a live REPLANNING round goes quiet and the mission stops."""
    for state in ('COMPLETED', 'CANCELLED', 'FAILED'):
        _mission(db, state=state, planning_blocked={'kind': 'policy'})
    assert _items(db, kind='mission') == []
    for state in ('PLANNING', 'REPLANNING', 'BLOCKED', 'CREATED'):
        _mission(db, state=state, planning_blocked={'kind': 'clarification',
                                                    'questions': ['Which one?']})
    assert [(i['state'], i['reason_code'], i['reason']) for i in _items(db, kind='mission')] \
        == [(s, 'clarification', 'Which one?')
            for s in ('PLANNING', 'REPLANNING', 'BLOCKED', 'CREATED')]


def test_a_planning_block_with_no_question_has_no_reason_and_two_make_one(db):
    """attention.py:86 — `'; '.join(pb.get('questions') or ()) or None`: two
    questions are one reason, and a block that asks nothing (`questions` absent
    or empty) is shown with no reason at all rather than with an empty string
    or the string '[]'. Note `pb.get('kind') or 'blocked'` on the same line is
    unreachable: `Mission._check` refuses a block that names no kind, so no row
    this database holds can ever ask for the default (see the report)."""
    _mission(db, state='PLANNING', planning_blocked={'kind': 'call'})
    _mission(db, state='REPLANNING', planning_blocked={'kind': 'challenge',
                                                       'questions': ['a', 'b']})
    _mission(db, state='BLOCKED', planning_blocked={'kind': 'policy', 'questions': []})
    quiet = _mission(db, state='CREATED', planning_blocked={'kind': 'clarification',
                                                            'questions': ['stale']})
    _rebody(db, entities.Mission, quiet, planning_blocked={'kind': 'clarification',
                                                           'questions': None})
    assert [(i['state'], i['reason_code'], i['reason']) for i in _items(db, kind='mission')] \
        == [('PLANNING', 'call', None), ('REPLANNING', 'challenge', 'a; b'),
            ('BLOCKED', 'policy', None), ('CREATED', 'clarification', None)]


def test_a_blocked_mission_waits_on_a_resource_only_if_a_route_said_so(db, homes):
    """attention.py:31-40 — `_no_resource` answers None, and nothing is shown,
    when a BLOCKED task has no route row, when the row's body is not a route,
    when a resource is not the whole reason it stopped (it is held from
    PLANNING), and when no task of the mission is BLOCKED at all. All five are
    fail-closed: a mission is only ever presented as waiting on a resource
    because a route said so, and only while routing is what holds it.

    *homes* is given, as every real read gives it (`routes.py:619` passes the
    registered set): with None the read builds the set out of every route row,
    which is a different branch and not this one."""
    a, _, at = _blocked_mission(db)                    # no route row at all
    b, _, bt = _blocked_mission(db)                    # a body that is not a route
    _route(db, b, bt, 'blocked')
    _tx(db, lambda tx: tx.conn.execute("UPDATE route_decisions SET body = 'null' "
                                        'WHERE task_id = ?', (bt,)))
    c, _, ct = _blocked_mission(db)                    # its last route fell back
    _route(db, c, ct, 'blocked')
    _route(db, c, ct, 'fallback')
    d, _, dt = _blocked_mission(db)                    # its only task runs again
    _route(db, d, dt, 'blocked')
    _tx(db, lambda tx: tx.conn.execute("UPDATE tasks SET state = 'RUNNING' WHERE id = ?",
                                       (dt,)))
    e, _, et = _blocked_mission(db, held='PLANNING')   # planning held it, not routing
    _route(db, e, et, 'blocked')
    assert _items(db, homes=homes, kind='mission') == []
    _route(db, a, at, 'blocked', explanation='no eligible resource: acct LIMITED',
           unblock_at='2999-01-01T15:00:00.000Z')
    assert [(i['ref']['id'], i['reason_code'], i['reason'], i['unblock_at'])
            for i in _items(db, homes=homes, kind='mission')] \
        == [(a, 'no_resource', 'no eligible resource: acct LIMITED',
             '2999-01-01T15:00:00.000Z')]


def test_one_blocked_task_stopped_for_another_reason_and_nothing_is_claimed(db, homes):
    """attention.py:37-39 — `return None`, not "carry on and keep the route I
    already had": the docstring's rule is that EVERY blocked task of the
    mission must have a last route that blocked, because a mission waiting on a
    resource is not waiting on a resource *alone*. The order the tasks come in
    must not decide it: the fail-open version shows the mission whenever the
    good route happens to come first."""
    good_first, pid, first = _blocked_mission(db)         # the second task has no route
    _route(db, good_first, first, 'blocked')
    _blocked_task(db, good_first, pid, 't2')
    bad_first, pid2, _ = _blocked_mission(db)              # the first task has no route
    _route(db, bad_first, _blocked_task(db, bad_first, pid2, 't2'), 'blocked')
    assert _items(db, homes=homes, kind='mission') == []


def test_a_no_resource_mission_is_listed_even_with_nothing_to_say(db):
    """attention.py:89-96 — `system_value(said, homes) if said else None` and
    `unblock_at=route.get('unblock_at')`: a route that explains nothing, or
    that names no time, is still a mission waiting on a resource. Invert the
    `if said` and the item vanishes along with its reason."""
    mid, _, tid = _blocked_mission(db)
    _route(db, mid, tid, 'blocked', explanation=None, unblock_at=None)
    i = _one(db, 'mission')
    assert (i['reason_code'], i['reason'], i['unblock_at']) == ('no_resource', None, None)
    assert (i['mission_id'], i['project_id']) == (mid, None)


def test_the_needs_you_strip_shows_one_item_per_kind_and_counts_them(db):
    """attention.py:64-114 + 19-23 — one row of each of the seven kinds: every
    loop must contribute its item, in the declared `KINDS` order, with the
    `ref.kind` the screen links on and its own reason code. The fail-open bug
    this exists for is a loop that stops answering: the user is never told."""
    proj = _project(db)
    mid = _mission(db, state='PLANNING', project=proj)
    pid, ts = _plan(db, mid)
    made = {k: _seed_one(db, k, mid, pid, ts[0].id, proj) for k in attention.KINDS}
    with db.read() as conn:
        out = attention.attention(conn, now=NOW)
    assert out['count'] == len(out['items']) == len(attention.KINDS)
    assert [i['kind'] for i in out['items']] == list(attention.KINDS)
    assert [i['ref']['kind'] for i in out['items']] == [
        'approval', 'verification', 'mission', 'knowledge_item', 'repository', 'automation',
        'account']
    assert [i['reason_code'] for i in out['items']] == [
        'action', 'acceptance', 'clarification', 'PREFERENCE', 'drifted', 'suspended', 'reauth']
    assert [i['ref']['id'] for i in out['items']] == list(made.values())
    # the state the row is in, the reason the screen shows, and the project it
    # links on, for every one of the seven loops
    assert [i['state'] for i in out['items']] == [
        'PENDING', 'AWAITING_HUMAN', 'PLANNING', 'CANDIDATE', 'DRIFTED', 'SUSPENDED',
        'UNAUTHENTICATED']
    assert [i['reason'] for i in out['items']] == [
        None, None, 'Which one?', 'use tabs', 'C:/r', 'docs', 'A']
    assert [i['project_id'] for i in out['items']] == [
        proj, proj, proj, None, proj, None, None]


def test_a_candidate_shows_its_own_type_and_title_and_only_a_candidate_does(db):
    """attention.py:97-99 — the knowledge loop's reason code is `r.entity.type`
    and its reason the title, and the query is `state='CANDIDATE'`: the strip is
    where the user decides which of Core's guesses to keep, so a FACT presented
    as a PREFERENCE asks a different question, and a confirmed or retracted item
    shown again asks one that was already answered."""
    for type_, title in (('FACT', 'the build is ninja'), ('LESSON', 'retry once'),
                         ('PREFERENCE', 'use tabs')):
        _insert(db, entities.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=WS,
                                          type=type_, title=title, state='CANDIDATE'))
    for state in ('CONFIRMED', 'RETRACTED', 'SUPERSEDED', 'EXPIRED'):
        _insert(db, entities.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=WS,
                                          type='FACT', title=state, state=state))
    assert [(i['reason_code'], i['reason'], i['state']) for i in _items(db, kind='knowledge')] \
        == [('FACT', 'the build is ninja', 'CANDIDATE'), ('LESSON', 'retry once', 'CANDIDATE'),
            ('PREFERENCE', 'use tabs', 'CANDIDATE')]


def test_the_order_is_kind_first_and_only_then_the_row_age_and_the_id(db):
    """attention.py:58 + 112-113 — the key is `(order[kind], since, ref id)`. The
    approval is the oldest row and the account the newest, and they still come
    first and last: `since` never outranks the kind, is read oldest-first, and
    two rows of one instant fall back to the id."""
    mid = _mission(db)
    pid, ts = _plan(db, mid)
    eid = _execution(db, mid, pid, ts[0].id)
    aid = _approval(db, kind='action', mid=mid, pid=pid, digest=_digest(db, pid),
                    tid=ts[0].id, eid=eid)
    _age(db, entities.Approval, aid, '2030-01-01T00:00:00.000Z')
    acc = ids.new_id('account')
    _insert(db, entities.Account(id=acc, harness_id='fake', label='A', auth_kind='api_key',
                                 health='UNAUTHENTICATED'))
    _age(db, entities.Account, acc, '2020-01-01T00:00:00.000Z')
    old = _verification(db, pid, Ref('task', ts[0].id), state='AWAITING_HUMAN',
                        when='2021-01-01T00:00:00.000Z')
    twin_a, twin_b = (_verification(db, pid, Ref('task', ts[0].id), state='AWAITING_HUMAN')
                      for _ in range(2))
    for v in (twin_a, twin_b):
        _age(db, entities.Verification, v, '2022-01-01T00:00:00.000Z')
    assert twin_a < twin_b                                     # the tie-break is the id
    got = _items(db)
    assert [(i['kind'], i['ref']['id']) for i in got] \
        == [('approval', aid), ('verification', old), ('verification', twin_a),
            ('verification', twin_b), ('account', acc)]
    # `since` is the age of the ROW, not the moment it was created
    assert [i['since'] for i in got] == ['2030-01-01T00:00:00.000Z', '2021-01-01T00:00:00.000Z',
                                         '2022-01-01T00:00:00.000Z', '2022-01-01T00:00:00.000Z',
                                         '2020-01-01T00:00:00.000Z']


@pytest.mark.parametrize('health,code', [
    ('UNAUTHENTICATED', 'reauth'), ('LIMITED', 'limited'), ('DEGRADED', 'degraded'),
    ('OPEN', 'open'),
    ('UNVERIFIED', None), ('AVAILABLE', None), ('CONSTRAINED', None), ('DISABLED', None),
], ids=['reauth', 'limited', 'degraded', 'open', 'unverified', 'available', 'constrained',
        'disabled'])
def test_only_the_account_healths_that_wait_on_the_user_are_listed(db, health, code):
    """attention.py:22 + 107-111 — the `ACCOUNT` tuple is the whole allow-list: the
    four healths that wait on the user come with their reason code, and a
    health outside it (an account that is merely near its ceiling, or one the
    user switched off) is silent. Drop a health from the tuple and the user is
    never told to sign in again."""
    acc = ids.new_id('account')
    control = ids.new_id('account')
    _insert(db, entities.Account(id=acc, harness_id='fake', label='L', auth_kind='api_key',
                                 health=health, limited_until='2026-11-01T15:00:00.000Z'))
    _insert(db, entities.Account(id=control, harness_id='fake', label='C', auth_kind='api_key',
                                 health='AVAILABLE',
                                 limited_until='2026-11-01T15:00:00.000Z'))
    got = _items(db, kind='account')
    assert [(i['ref']['id'], i['reason_code'], i['reason']) for i in got] \
        == ([(acc, code, 'L')] if code else [])
    # `until` is the LIMITED row's own window, and no other health grows one
    assert [('until' in i) for i in got] == ([health == 'LIMITED'] if code else [])
    assert [i.get('until') for i in got] \
        == (['2026-11-01T15:00:00.000Z'] if health == 'LIMITED' else [None] if code else [])


def test_a_limited_account_carries_the_hour_it_lifts_and_no_other_kind_does(db):
    """attention.py:109-111 — `{'until': r.entity.limited_until}` is added for
    the LIMITED health alone, and its value is the row's own, None included: an
    account whose window was never recorded must not borrow another's."""
    plain, timed = ids.new_id('account'), ids.new_id('account')
    _insert(db, entities.Account(id=plain, harness_id='fake', label='A', auth_kind='api_key',
                                 health='LIMITED', limited_until=None))
    _insert(db, entities.Account(id=timed, harness_id='fake', label='B', auth_kind='api_key',
                                 health='LIMITED', limited_until='2026-11-01T15:00:00.000Z'))
    got = {i['ref']['id']: i for i in _items(db, kind='account')}
    assert set(got) == {plain, timed}
    assert [got[i]['until'] for i in (plain, timed)] == [None, '2026-11-01T15:00:00.000Z']
    assert [got[i]['reason_code'] for i in (plain, timed)] == ['limited', 'limited']


def test_the_same_read_replayed_answers_identically_and_writes_nothing(db):
    """attention.py:61-114 and 127-158 replayed: the same read twice on one
    snapshot is the same answer, and a read is a read — no second event, no
    row moved. A read that mutated (or that rejudged against a moving clock)
    would make the UI flicker and the cursor skip."""
    mid = _world(db)
    with db.read() as conn:
        first, first_tl = attention.attention(conn, now=NOW), attention.timeline(conn, mid,
                                                                                  limit=7)
        second, second_tl = attention.attention(conn, now=NOW), attention.timeline(conn, mid,
                                                                                   limit=7)
        head = conn.execute('SELECT MAX(seq) FROM events').fetchone()[0]
    assert (first, first_tl) == (second, second_tl)
    with db.read() as conn:
        assert attention.attention(conn, now=NOW) == first
        assert conn.execute('SELECT MAX(seq) FROM events').fetchone()[0] == head


# ── the mission timeline (D5) ───────────────────────────────────────────────

def test_the_timeline_of_an_unknown_mission_is_not_found(db):
    """attention.py:130-131 — a mission that is not there raises `NotFound`;
    it does not answer an empty history, which the thread would show as a
    mission with nothing to report."""
    _world(db)
    with db.read() as conn, pytest.raises(NotFound):
        attention.timeline(conn, 'msn_' + '0' * 26)


def test_a_mission_with_no_events_of_its_own_answers_empty_and_no_cursor(db):
    """attention.py:150-155 — `if not seqs`: nothing is asked of the event log
    and the home registry is never built (the callable is never called), and no
    cursor is handed back (a reader would page forever). The events of the other
    mission in the same database stay out of it."""
    mine, other = _mission(db), _mission(db)
    _append(db, _event('mission.updated', ('mission', other), {'note': 'not mine'}))
    calls = []

    def lazy():
        calls.append(1)
        return Homes([], path_flavour='windows')

    with db.read() as conn:
        assert attention.timeline(conn, mine, homes=lazy) \
            == {'mission_id': mine, 'events': [], 'next_before': None}
    assert calls == []


def test_the_timeline_holds_the_missions_own_rows_and_no_one_elses(db):
    """attention.py:132-136 — the own rows found by their `mission_id` column,
    and the verifications of *its own plans only*. The verification half is the
    leak that matters: a verification names a plan, never a mission, so another
    mission's verifier output — its checks, its evidence, its failures — joins
    this thread the moment that plan-to-mission step is widened."""
    mine, other = _mission(db), _mission(db)
    pid, ts = _plan(db, mine)
    opid, ots = _plan(db, other)
    made = _own_rows(db, mine, plan=pid)
    mine_v = _verification(db, made['plan'], Ref('task', ts[0].id), state='PASSED')
    other_v = _verification(db, opid, Ref('task', ots[0].id), state='PASSED')
    _append(db,
            _event('mission.state_changed', ('mission', mine), {'from': 'CREATED',
                                                                'to': 'PLANNING'}),
            _event('verification.state_changed', ('verification', mine_v), {'to': 'PASSED'}),
            _event('verification.state_changed', ('verification', other_v), {'to': 'PASSED'}),
            _event('plan.state_changed', ('plan', opid), {'to': 'APPROVED'}),
            _event('task.state_changed', ('task', ots[0].id), {'to': 'VERIFYING'}),
            _event('mission.updated', ('mission', other), {'note': 'not mine'}))
    with db.read() as conn:
        got = attention.timeline(conn, mine)
    subjects = [(e['subject']['kind'], e['subject']['id']) for e in got['events']]
    for leaked in (('verification', other_v), ('plan', opid), ('task', ots[0].id),
                   ('mission', other)):
        assert leaked not in subjects, 'another mission\'s row leaked into the timeline: %r' \
            % (leaked,)
    assert {k for k, _ in subjects} >= set(_OWN_EVENT) | {'verification', 'mission'}
    assert ('mission', mine) in subjects
    assert {i for k, i in subjects if k in _OWN_EVENT} == set(made.values())
    assert [e['seq'] for e in got['events']] == sorted([e['seq'] for e in got['events']],
                                                       reverse=True)


def test_before_is_strict_and_a_page_hands_a_cursor_only_when_it_is_full(db):
    """attention.py:144-149 and 157-158 — `seq < ?`, and `next_before` only
    when the page is exactly `limit` long. A `<=` repeats one event on every
    page; a cursor on a short page makes a reader stop early or ask again for
    nothing."""
    mid = _mission(db)
    _, ts = _plan(db, mid)
    seqs = _emit_events(db, [('task.state_changed', ('task', ts[0].id))] * 6)
    with db.read() as conn:
        page = attention.timeline(conn, mid, limit=3)
        assert [e['seq'] for e in page['events']] == seqs[5:2:-1]
        assert page['next_before'] == seqs[3]
        older = attention.timeline(conn, mid, before=page['next_before'], limit=3)
        assert [e['seq'] for e in older['events']] == seqs[2::-1]
        assert older['next_before'] == seqs[0]
        tail = attention.timeline(conn, mid, before=older['next_before'], limit=3)
        assert tail == {'mission_id': mid, 'events': [], 'next_before': None}
        whole = attention.timeline(conn, mid, limit=50)
        assert len(whole['events']) == 6 and whole['next_before'] is None
        assert attention.timeline(conn, mid, before=seqs[0])['events'] == []


def test_more_subjects_than_one_chunk_answer_without_repeating_or_raising(db):
    """attention.py:137-149 + 150 — the 500-at-a-time chunking of the subject list.
    With 501 tasks the subject list is two chunks: the answer must still be the
    newest `limit` events, newest first, and a walk over the pages must return
    every event of the second chunk too — a loop that only ever asks the first
    chunk, or that drops the newest events of all but one, silently loses them
    and the thread simply looks quiet."""
    mid = _mission(db)
    seqs = []

    def build(tx):
        pid = ids.new_id('plan')
        tx.insert(entities.Plan(id=pid, mission_id=mid, plan_version=1,
                                state='APPROVED'), actor=ACTOR)
        for n in range(501):
            tid = ids.new_id('task')
            tx.insert(entities.Task(id=tid, plan_id=pid, mission_id=mid, key='k%03d' % n,
                                    title='T', kind='code_change'), actor=ACTOR)
            seqs.append(tx.append(new_event('task.state_changed', Ref('task', tid), ACTOR,
                                            payload={'to': 'RUNNING'}, workspace=WS)).seq)
    db.writer.execute(build, {})
    assert len(seqs) == 501 and seqs == sorted(seqs)
    with db.read() as conn:
        got = attention.timeline(conn, mid, limit=100)
        assert seqs[-1] in [e['seq'] for e in got['events']], 'the newest chunk of subjects is lost'
        assert seqs[0] not in [e['seq'] for e in got['events']]
        walk, cursor, pages = [], None, 0
        while True:
            page = attention.timeline(conn, mid, before=cursor, limit=100)
            walk += [e['seq'] for e in page['events']]
            pages += 1
            assert pages < 12, 'the cursor never ended the walk: %r' % (cursor,)
            if page['next_before'] is None:
                break
            cursor = page['next_before']
    assert sorted(walk) == seqs, '%d of the 501 events came back' % len(walk)
    newest = [e['seq'] for e in got['events']]
    assert newest == sorted(newest, reverse=True)
    assert got['next_before'] == got['events'][-1]['seq']


def test_the_timeline_screens_an_account_home_and_keeps_what_the_user_typed(db, homes):
    """attention.py:155-156 + 62 — `public_event(..., _homes(conn, homes))`,
    where `_homes` accepts a callable so a read that finds nothing never builds
    the registry. An unscreened system string hands a private home to anyone
    who can read the thread; over-scrubbing destroys the constraints the user
    typed."""
    mid = _mission(db)
    calls = []

    def build(tx):
        tx.append(new_event('mission.state_changed', Ref('mission', mid), ACTOR,
                            payload={'from': 'A', 'to': 'B', 'reason': 'gave up at ' + HOME},
                            workspace=WS))
        tx.append(new_event('mission.updated', Ref('mission', mid), ACTOR,
                            payload={'added': {'constraints': ['nothing at ' + HOME]}},
                            workspace=WS))
    _tx(db, build)

    def lazy():
        calls.append(1)
        return homes

    with db.read() as conn:
        out = attention.timeline(conn, mid, homes=lazy)
    assert calls == [1]
    by_type = {e['type']: e['payload'] for e in out['events']}
    assert HOME not in by_type['mission.state_changed']['reason']
    assert 'its home' in by_type['mission.state_changed']['reason']
    assert by_type['mission.updated']['added']['constraints'] == ['nothing at ' + HOME]


# ── the seeds, in one place so each test reads as its own assertion ─────────

def _rebody(db, cls, entity_id, **fields):
    """Rewrite named fields of a row's JSON body, past the entity: the seam for
    a row this build did not write (an imported home, an older schema)."""
    def run(tx):
        one = tx.conn.execute('SELECT body FROM %s WHERE id = ?' % rows.table(cls),
                              (entity_id,)).fetchone()
        body = json.loads(one[0])
        body.update(fields)
        tx.conn.execute('UPDATE %s SET body = ? WHERE id = ?' % rows.table(cls),
                        (json.dumps(body), entity_id))
    return _tx(db, run)


def _seed_one(db, kind, mid, pid, tid, proj=None):
    """One row of one kind, waiting on the user, under mission *mid*."""
    if kind == 'approval':
        return _approval(db, kind='action', mid=mid, pid=pid, digest=_digest(db, pid), tid=tid,
                         eid=_execution(db, mid, pid, tid))
    if kind == 'verification':
        return _verification(db, pid, Ref('task', tid), state='AWAITING_HUMAN')
    if kind == 'mission':
        _tx(db, lambda tx: tx.update(entities.Mission, mid, {'planning_blocked': {
            'kind': 'clarification', 'questions': ['Which one?']}}, actor=ACTOR))
        return mid
    if kind == 'knowledge':
        kid = ids.new_id('knowledge_item')
        _insert(db, entities.KnowledgeItem(id=kid, workspace_id=WS, type='PREFERENCE',
                                           title='use tabs', state='CANDIDATE'))
        return kid
    if kind == 'drift':
        rid = ids.new_id('repository')
        _insert(db, entities.Repository(id=rid, workspace_id=WS, project_id=proj or _project(db),
                                        path='C:/r', path_key='c:/r',
                                        architecture_state='DRIFTED'))
        return rid
    if kind == 'automation':
        aid = ids.new_id('automation')
        _insert(db, entities.Automation(id=aid, workspace_id=WS, name='docs',
                                        state='SUSPENDED'))
        return aid
    if kind == 'account':
        acc = ids.new_id('account')
        _insert(db, entities.Account(id=acc, harness_id='fake', label='A', auth_kind='api_key',
                                     health='UNAUTHENTICATED'))
        return acc
    raise AssertionError('no seed for %r' % kind)


def _world(db):
    """A mission with its own rows, a waiting approval, verification, knowledge
    and account, and six events: what the two replay tests read twice."""
    mid = _mission(db, state='PLANNING', project=_project(db))
    pid, ts = _plan(db, mid)
    for kind in ('approval', 'verification', 'knowledge', 'account'):
        _seed_one(db, kind, mid, pid, ts[0].id)
    _own_rows(db, mid, plan=pid)
    _emit_events(db, [('task.state_changed', ('task', ts[0].id))] * 6)
    return mid
