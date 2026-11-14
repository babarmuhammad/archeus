"""T-751: the ten highest-risk uncovered branches of archeus/core/world/digest.py.

Fail-closed and denial paths first: a STALE bookkeeping move is never news and
never becomes a group, yet a drift that left the log silently is remembered so
its eventual fix still surfaces as `drift_cleared`; a mission or project scope
drops every group it cannot prove belongs; a message whose conversation was
moved out from under it is still counted instead of vanishing; a mission whose
row is gone degrades to `progressed` and is never guessed into `needs_you`.
Then the boundary values: the LAST architecture move decides a repository
headline, the window `seq > start` may not be one off, `since=0` is a session
cursor and not "no cursor", and a duplicated event may not inflate a
conversation's message count. Then the error paths: an
`architecture.state_changed` whose payload omits `to` or `from` must degrade to
`progressed`, not crash the owner's only read.

Style, fixtures and seams follow
tests/v1/unit/test_gaps_core_sessions_continuity.py: the real
`Database.open()` on the test's own ARCHEUS_HOME, one writer command per seed
(`tx.insert` rows, then `tx.append` events), and every event built through the
registry-validated `new_event` so nothing here bypasses the envelope contract.
No process, no network, no OS call, no Windows-only or POSIX-only assertion:
the same facts hold on both platforms, and every file the run leaves behind is
under pytest's `tmp_path`.
"""

import sqlite3

import pytest

from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.world import digest
from archeus.infra.db import Database


# ── the seams the existing tests use ─────────────────────────────────────────

@pytest.fixture
def rdb():
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def who():
    return Ref('user_device', ids.new_id('principal'))


def _seed(db, who, entities_=(), events=()):
    """One writer command: the rows in list order, then the events, so seqs are
    1..len(events) in the order a test lists them. A rows-only seed carries one
    system-visibility `context_package.created` (invisible to the digest) so the
    writer's record-or-refuse rule is satisfied without polluting an answer."""
    def cmd(tx, *, actor):
        for e in entities_:
            tx.insert(e, actor=actor)
        for e in events:
            tx.append(e)
        if entities_ and not events:
            tx.append(new_event('context_package.created',
                                Ref('context_package', ids.new_id('context_package')),
                                actor))
    db.writer.execute(cmd, {'actor': who})


def _read(conn, **kw):
    return digest.digest(conn, **kw)


def _moved_away(db, sql, params=()):
    """A row deleted out from under the events that still name it, exactly the
    tamper the suite already uses behind the writer's back
    (tests/v1/integration/test_execution.py rewrites a bound row the same way):
    a plain sqlite3 connection — `foreign_keys` is OFF there by default, only
    connection.py turns it on — drops a row the single writer would never drop.
    The digest must answer from whatever the rows and the log then say."""
    c = sqlite3.connect(db.path)
    try:
        c.execute(sql, params)
        c.commit()
    finally:
        c.close()


def _ev(who, type_, kind, eid, project=None, **payload):
    return new_event(type_, Ref(kind, eid), who, payload=payload, project=project)


def _arch(who, rid, frm, to):
    return _ev(who, 'architecture.state_changed', 'repository', rid,
               **{'from': frm, 'to': to})


def _mission(mid, state='APPROVED'):
    return entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                            objective='o', state=state)


def _plan(mid, pid, version=1):
    return entities.Plan(id=pid, mission_id=mid, plan_version=version)


def _task(mid, pid, tid):
    return entities.Task(id=tid, plan_id=pid, mission_id=mid, key='k', title='T',
                         kind='code_change', state='RUNNING')


def _verification(vid, tid, pid):
    return entities.Verification(id=vid, subject=Ref('task', tid), verifier='code',
                                 plan_id=pid)


def _conversation(cid, mission_id=None):
    return entities.Conversation(id=cid, kind='mission' if mission_id else 'primary',
                                 mission_id=mission_id)


def _message(msg_id, cid):
    return entities.Message(id=msg_id, conversation_id=cid, author='user', text='hi')


def _user(acked):
    return entities.User(id=ids.new_id('user'), display_name='owner',
                         last_ack_event_seq=acked)


# ── denial: bookkeeping that must not report, news that must not hide ────────

def test_a_stale_bookkeeping_move_is_not_news_not_even_a_group(rdb, who):
    """digest.py:86-89 — the STALE branch and its `continue`: a repository going
    STALE is bookkeeping, and removing the `continue` would hand the owner a
    group for a move the module doc promises is not reported (and would let
    `_headline` file it under the drift headlines a STALE move never earned)."""
    rid = ids.new_id('repository')
    _seed(rdb, who, events=[_arch(who, rid, 'CONSISTENT', 'STALE')])
    with rdb.read() as conn:
        d = _read(conn)
    assert d == {'from_seq': 0, 'up_to_seq': 1, 'count': 0, 'groups': [],
                 'truncated': False}


def test_a_drift_that_left_silently_still_gets_its_fix_reported(rdb, who):
    """digest.py:87-88 and 65-67 — DRIFTED->STALE is skipped but remembered
    (`left_drift.add`), so the later STALE->CONSISTENT — whose own payload names
    no DRIFTED — is still `drift_cleared`. Drop the `add` and the fix of a real
    drift disappears from the digest, because the move that made it drift was
    the one move the loop refused to report."""
    rid = ids.new_id('repository')
    _seed(rdb, who, events=[_arch(who, rid, 'DRIFTED', 'STALE'),
                            _arch(who, rid, 'STALE', 'CONSISTENT')])
    with rdb.read() as conn:
        (g,) = _read(conn)['groups']
    assert g['ref'] == {'kind': 'repository', 'id': rid}
    assert (g['headline'], g['count'], g['first_seq'], g['last_seq']) == \
        ('drift_cleared', 1, 2, 2)


@pytest.mark.parametrize('moves,want,count', [
    ([('CONSISTENT', 'DRIFTED'), ('DRIFTED', 'CONSISTENT')], 'drift_cleared', 2),
    ([('DRIFTED', 'CONSISTENT'), ('CONSISTENT', 'DRIFTED')], 'drift_found', 2),
    ([('CONSISTENT', 'STALE'), ('STALE', 'CONSISTENT')], 'progressed', 1),
], ids=['fix-after-drift', 'newest-move-drifted', 'consistent-never-drifted'])
def test_the_last_architecture_move_decides_a_repository_headline(rdb, who, moves, want,
                                                                   count):
    """digest.py:60-67 — `moves[-1]` decides, the `to == 'DRIFTED'` answer comes
    first, and CONSISTENT is only `drift_cleared` when DRIFTED actually figures
    (this run or `left_drift`): reading `moves[0]` flips case 2, dropping the
    `was_drifted or any(...)` guard files a never-drifted repository as a fix
    the owner never had to wait for."""
    rid = ids.new_id('repository')
    _seed(rdb, who, events=[_arch(who, rid, frm, to) for frm, to in moves])
    with rdb.read() as conn:
        (g,) = _read(conn)['groups']
    assert (g['ref']['kind'], g['headline'], g['count']) == ('repository', want, count)


def test_an_added_file_alone_is_progress_and_a_silent_drift_move_adds_nothing(rdb, who):
    """digest.py:61 (`if moves:`) and 68 — with the only architecture move a
    skipped DRIFTED->STALE, the file_added group has no moves at all and falls
    through to `progressed`; without the falsy guard `moves[-1]` raises
    IndexError on an empty list, and the event list of the group proves the
    skipped move was never grouped."""
    rid = ids.new_id('repository')
    _seed(rdb, who, events=[_ev(who, 'repository.file_added', 'repository', rid,
                                path='app/a.py'),
                            _arch(who, rid, 'DRIFTED', 'STALE')])
    with rdb.read() as conn:
        (g,) = _read(conn)['groups']
    assert (g['headline'], g['count'], g['types']) == \
        ('progressed', 1, ['repository.file_added'])


# ── fail-closed: missing rows never guess a grouping, scoping never leaks ─────

@pytest.mark.parametrize('state,want', [
    ('APPROVAL_REQUIRED', 'needs_you'), ('REVIEWING', 'needs_you'),
    ('BLOCKED', 'needs_you'), ('COMPLETED', 'completed'), ('FAILED', 'failed'),
    ('APPROVED', 'progressed'), (None, 'progressed'),
], ids=['approval', 'reviewing', 'blocked', 'completed', 'failed', 'alive', 'gone'])
def test_a_mission_headline_comes_from_the_row_and_a_gone_row_says_nothing(
        rdb, who, state, want):
    """digest.py:54-58 — the three `needs_you` states, the completed/failed map
    and the `m.entity.state if m else None` guard: a task event whose mission
    row was deleted must degrade to `progressed`, not crash on `m.entity` and
    not keep a stale headline; widening `NEEDS_YOU` or answering from the event
    instead of the row makes news nag about a mission that finished."""
    mid, pid, tid = (ids.new_id('mission'), ids.new_id('plan'), ids.new_id('task'))
    _seed(rdb, who, entities_=[_mission(mid, state or 'APPROVED'), _plan(mid, pid),
                               _task(mid, pid, tid)],
          events=[_ev(who, 'task.state_changed', 'task', tid, to='DONE')])
    if state is None:                                  # the row moves away after
        _moved_away(rdb, 'DELETE FROM missions WHERE id = ?', (mid,))
    with rdb.read() as conn:
        (g,) = _read(conn)['groups']
    assert g['ref'] == {'kind': 'mission', 'id': mid}      # folded, gone or not
    assert g['headline'] == want


def test_an_event_about_a_moved_away_row_keeps_its_own_group(rdb, who):
    """digest.py:27-31 — `_OF_MISSION.get` returning None (a knowledge_item is
    nobody's foldable child) and `rows.get` returning None (the task was deleted
    from under its event): both answer "no mission", and the event stays under
    its own subject. Removing the missing-row guard dereferences None; guessing
    a mission from the payload would file news about a row that is gone."""
    tid = ids.new_id('task')                                 # no Task row
    kid = ids.new_id('knowledge_item')
    _seed(rdb, who, events=[_ev(who, 'task.created', 'task', tid),
                            _ev(who, 'knowledge_item.created', 'knowledge_item', kid)])
    with rdb.read() as conn:
        d = _read(conn)
    assert sorted((g['ref']['kind'], g['headline'], g['count']) for g in d['groups']) == \
        sorted([('task', 'progressed', 1), ('knowledge_item', 'progressed', 1)])


def test_a_verification_folds_through_its_plan_and_stops_when_the_plan_is_gone(
        rdb, who):
    """digest.py:33-35 — a Verification has no mission_id of its own, so the
    only road to its mission runs through `plan_id`: the row that exists folds
    into ('mission', mid), the one whose Plan was deleted stays under its own id
    rather than guessing a mission from a plan it can no longer read (the
    `plan and ...` half: without it the deleted plan raises AttributeError)."""
    mid, pid, tid = (ids.new_id('mission'), ids.new_id('plan'), ids.new_id('task'))
    pid_gone = ids.new_id('plan')
    v_here, v_gone = ids.new_id('verification'), ids.new_id('verification')
    _seed(rdb, who, entities_=[_mission(mid), _plan(mid, pid), _plan(mid, pid_gone, 2),
                               _task(mid, pid, tid),
                               _verification(v_here, tid, pid),
                               _verification(v_gone, tid, pid_gone)],
          events=[_ev(who, 'verification.created', 'verification', v_here),
                  _ev(who, 'verification.created', 'verification', v_gone)])
    _moved_away(rdb, 'DELETE FROM plans WHERE id = ?', (pid_gone,))
    with rdb.read() as conn:
        d = _read(conn)
    refs = sorted((g['ref']['kind'], g['ref']['id']) for g in d['groups'])
    assert refs == sorted([('mission', mid), ('verification', v_gone)])


def test_a_message_whose_conversation_was_moved_out_is_still_counted(rdb, who):
    """digest.py:41-44 — the `c is None` fallback of `_thread_of`: the message
    row is there and its conversation is not (and the message itself is gone
    too, so `m` is None as well): both must fold under the message's OWN id,
    never disappear. Dropping the fallback dereferences None; dropping the
    message instead would silently swallow news the owner never saw."""
    cid_a, msg_a = ids.new_id('conversation'), ids.new_id('message')
    msg_b = ids.new_id('message')                             # no Message row either
    _seed(rdb, who, entities_=[_conversation(cid_a), _message(msg_a, cid_a)],
          events=[_ev(who, 'message.created', 'message', msg_a),
                  _ev(who, 'message.created', 'message', msg_b)])
    _moved_away(rdb, 'DELETE FROM conversations WHERE id = ?', (cid_a,))
    with rdb.read() as conn:
        d = _read(conn)
    assert sorted((g['ref']['kind'], g['ref']['id']) for g in d['groups']) == \
        sorted([('message', msg_a), ('message', msg_b)])
    assert [g['headline'] for g in d['groups']] == ['progressed', 'progressed']


def test_scoped_to_a_mission_nothing_else_shows_even_drift(rdb, who):
    """digest.py:96-99 — the mission branch of the scope filter, applied AFTER
    folding: a message of the mission's own thread is in (it folded to the
    mission), and a repository that just went DRIFTED — the loudest news there
    is — is out, because scoping to a mission is a promise, not a suggestion.
    Widening the tuple test to `kind == 'mission'` leaks every mission's news."""
    mid_a, mid_b = ids.new_id('mission'), ids.new_id('mission')
    pid_a, pid_b = ids.new_id('plan'), ids.new_id('plan')
    tid_a, tid_b = ids.new_id('task'), ids.new_id('task')
    cid_a, msg_a = ids.new_id('conversation'), ids.new_id('message')
    rid = ids.new_id('repository')
    _seed(rdb, who, entities_=[_mission(mid_a), _mission(mid_b), _plan(mid_a, pid_a),
                               _plan(mid_b, pid_b), _task(mid_a, pid_a, tid_a),
                               _task(mid_b, pid_b, tid_b), _conversation(cid_a, mid_a),
                               _message(msg_a, cid_a)],
          events=[_ev(who, 'task.state_changed', 'task', tid_a, to='DONE'),
                  _ev(who, 'message.created', 'message', msg_a),
                  _ev(who, 'task.state_changed', 'task', tid_b, to='DONE'),
                  _arch(who, rid, 'CONSISTENT', 'DRIFTED')])
    with rdb.read() as conn:
        scoped = _read(conn, mission_id=mid_a)
        unknown = _read(conn, mission_id=ids.new_id('mission'))
    assert [(g['ref']['kind'], g['ref']['id'], g['count']) for g in scoped['groups']] == \
        [('mission', mid_a, 2)]                              # task event + folded message
    assert unknown['count'] == 0 and unknown['up_to_seq'] == scoped['up_to_seq']


def test_scoped_to_a_project_an_event_without_one_is_not_in_it(rdb, who):
    """digest.py:96-99 — the project branch (`e.project == project_id`): the
    task event and the drift event that name the project group as usual, an
    event that names no project never joins it, and a scope naming a project
    nobody has answers empty instead of falling back to unscoped."""
    pid, tid = ids.new_id('plan'), ids.new_id('task')
    mid = ids.new_id('mission')
    prj, other = ids.new_id('project'), ids.new_id('project')        # scope names one
    rid = ids.new_id('repository')
    kid = ids.new_id('knowledge_item')
    _seed(rdb, who, entities_=[_mission(mid), _plan(mid, pid), _task(mid, pid, tid)],
          events=[_ev(who, 'task.state_changed', 'task', tid, project=prj, to='DONE'),
                  _ev(who, 'mission.created', 'mission', mid),      # no project
                  _arch(who, rid, 'CONSISTENT', 'DRIFTED'),         # no project
                  _ev(who, 'knowledge_item.created', 'knowledge_item', kid,
                      project=prj)])
    with rdb.read() as conn:
        scoped = _read(conn, project_id=prj)
        unknown = _read(conn, project_id=other)
    assert sorted((g['ref']['kind'], g['headline']) for g in scoped['groups']) == \
        sorted([('mission', 'progressed'), ('knowledge_item', 'progressed')])
    assert unknown['count'] == 0


# ── boundary values: the cursor, the fold, the count ─────────────────────────

def test_the_owner_cursor_opens_the_window_and_since_is_a_literal_number(rdb, who):
    """digest.py:75-81 and the window at 83-84 — with the user row acked at 2
    the unscoped digest starts AT 2 and its first event is seq 3 (`seq > ?`,
    never `>=`); `since=0` is a cursor of zero, not "no cursor": it shows seq 1
    that the owner's row would hide (`since or None` would); `since` past the
    head is empty and honest, and a negative one reads from the floor with
    `truncated` telling the truth about the cursor that could not be honoured."""
    mid, pid, tid = (ids.new_id('mission'), ids.new_id('plan'), ids.new_id('task'))
    _seed(rdb, who, entities_=[_mission(mid), _plan(mid, pid), _task(mid, pid, tid),
                               _user(2)],
          events=[_ev(who, 'task.state_changed', 'task', tid, to='A'),
                  _ev(who, 'task.state_changed', 'task', tid, to='B'),
                  _ev(who, 'task.state_changed', 'task', tid, to='C')])
    with rdb.read() as conn:
        (acked,) = _read(conn)['groups']
        session = _read(conn, since=0)['groups'][0]
        ahead = _read(conn, since=99)
        negative = _read(conn, since=-5)
    assert (acked['count'], acked['first_seq'], acked['last_seq']) == (1, 3, 3)
    assert (session['count'], session['first_seq']) == (3, 1)
    assert ahead == {'from_seq': 99, 'up_to_seq': 3, 'count': 0, 'groups': [],
                     'truncated': False}
    assert (negative['from_seq'], negative['truncated']) == (0, True)
    assert sum(g['count'] for g in negative['groups']) == 3


def test_a_system_event_is_not_news_even_about_a_mission_row(rdb, who):
    """digest.py:83 — the `visibility = 'user'` predicate: an `execution.progress`
    (system in the registry) about an execution of the mission must not create a
    group, must not inflate the mission group's count, and must not appear in
    its `types`, while `up_to_seq` still counts it as read."""
    mid, pid, tid = (ids.new_id('mission'), ids.new_id('plan'), ids.new_id('task'))
    exe = ids.new_id('execution')
    _seed(rdb, who, entities_=[_mission(mid), _plan(mid, pid), _task(mid, pid, tid)],
          events=[_ev(who, 'task.state_changed', 'task', tid, to='DONE'),
                  new_event('execution.progress', Ref('execution', exe), who,
                            visibility='system')])
    with rdb.read() as conn:
        d = _read(conn)
    assert d['up_to_seq'] == 2 and d['count'] == 1
    (g,) = d['groups']
    assert (g['count'], g['types']) == (1, ['task.state_changed'])


def test_a_primary_conversation_counts_messages_and_not_their_events(rdb, who):
    """digest.py:51-52 and 106-107 — the primary conversation folds to one
    `new_messages` row (R13-03) whose count is the number of DISTINCT message
    subjects: the duplicated `message.created` for m1 may not inflate it to 3
    (`count=len(evs)` would), and `types` stays a sorted set, not a list of
    every event."""
    cid = ids.new_id('conversation')
    m1, m2 = ids.new_id('message'), ids.new_id('message')
    _seed(rdb, who, entities_=[_conversation(cid), _message(m1, cid), _message(m2, cid)],
          events=[_ev(who, 'message.created', 'message', m1),
                  _ev(who, 'message.created', 'message', m2),
                  _ev(who, 'message.created', 'message', m1)])
    with rdb.read() as conn:
        (g,) = _read(conn)['groups']
    assert g['ref'] == {'kind': 'conversation', 'id': cid}
    assert (g['headline'], g['count'], g['first_seq'], g['last_seq']) == \
        ('new_messages', 2, 1, 3)
    assert g['types'] == ['message.created']


def test_a_mission_thread_message_folds_into_the_mission_not_a_row_of_its_own(
        rdb, who):
    """digest.py:45-46 and 91-92 — a message of a mission conversation folds to
    ('mission', mid) via `_thread_of`, so the mission gets one group whose
    count is EVENTS (mission kind, line 106's else) and the conversation never
    surfaces. Falling through to ('conversation', cid) leaves the thread's news
    beside, instead of inside, the mission it belongs to."""
    mid, cid = ids.new_id('mission'), ids.new_id('conversation')
    msg = ids.new_id('message')
    _seed(rdb, who, entities_=[_mission(mid, 'EXECUTING'), _conversation(cid, mid),
                               _message(msg, cid)],
          events=[_ev(who, 'message.created', 'message', msg)])
    with rdb.read() as conn:
        d = _read(conn)
    assert [(g['ref']['kind'], g['ref']['id'], g['headline'], g['count'])
            for g in d['groups']] == [('mission', mid, 'progressed', 1)]


def test_a_project_id_is_the_first_event_that_names_one(rdb, who):
    """digest.py:108 — `next((e.project for e in evs if e.project), None)`: the
    group's project comes from the first event that carries one — dropping the
    `if e.project` filter would take the None of the first event and hide the
    project the second one names, unfiling the group from the project view."""
    mid, pid, tid = (ids.new_id('mission'), ids.new_id('plan'), ids.new_id('task'))
    prj = ids.new_id('project')
    _seed(rdb, who, entities_=[_mission(mid), _plan(mid, pid), _task(mid, pid, tid)],
          events=[_ev(who, 'task.created', 'task', tid),                  # no project
                  _ev(who, 'task.state_changed', 'task', tid, project=prj, to='DONE')])
    with rdb.read() as conn:
        (g,) = _read(conn)['groups']
    assert g['project_id'] == prj


def test_needs_you_reads_first_and_within_a_headline_the_latest_reads_first(rdb, who):
    """digest.py:110 — the sort key `(ORDER.index(headline), -last_seq)`: the
    oldest event's needs_you outranks everything and the newest event's
    new_messages still reads last, while two `progressed` groups come back
    newest-first. Dropping the minus is a digest that buries the freshest news
    of a headline under its stalest."""
    a = ids.new_id('mission')
    b = ids.new_id('mission')
    rid = ids.new_id('repository')
    cid, msg = ids.new_id('conversation'), ids.new_id('message')
    k1, k2 = ids.new_id('knowledge_item'), ids.new_id('knowledge_item')
    _seed(rdb, who, entities_=[_mission(a, 'APPROVAL_REQUIRED')],
          events=[_ev(who, 'mission.created', 'mission', a)])                     # 1
    _seed(rdb, who, entities_=[_mission(b, 'COMPLETED')],
          events=[_ev(who, 'mission.created', 'mission', b)])                      # 2
    _seed(rdb, who, events=[_arch(who, rid, 'CONSISTENT', 'DRIFTED')])             # 3
    _seed(rdb, who, entities_=[_conversation(cid), _message(msg, cid)],
          events=[_ev(who, 'message.created', 'message', msg)])                    # 4
    _seed(rdb, who, events=[_ev(who, 'knowledge_item.created', 'knowledge_item', k1)])   # 5
    _seed(rdb, who, events=[_ev(who, 'knowledge_item.created', 'knowledge_item', k2)])   # 6
    with rdb.read() as conn:
        d = _read(conn)
    assert [(g['ref']['kind'], g['ref']['id'], g['headline']) for g in d['groups']] == \
        [('mission', a, 'needs_you'), ('repository', rid, 'drift_found'),
         ('mission', b, 'completed'), ('knowledge_item', k2, 'progressed'),
         ('knowledge_item', k1, 'progressed'), ('conversation', cid, 'new_messages')]
    assert d['count'] == 6


# ── error paths: a payload that omits what the headline reads ─────────────────

@pytest.mark.parametrize('payloads', [
    [{}],                                                        # no `to` at all
    [{'to': 'CONSISTENT'}, {'from': 'DRIFTED', 'to': 'CONSISTENT'}],   # no `from`
], ids=['no-to', 'no-from'])
def test_an_architecture_move_without_the_ends_it_claims_to_move_degrades(
        rdb, who, payloads):
    """digest.py:62-66 — the owner's only read must not be killable by one
    malformed event: whatever the digest decides about a move whose payload
    names no end, it must answer (the repository group degrades to
    `progressed` at worst) instead of raising KeyError out of `_headline`."""
    rid = ids.new_id('repository')
    _seed(rdb, who, events=[
        new_event('architecture.state_changed', Ref('repository', rid), who,
                  payload=p) for p in payloads])
    with rdb.read() as conn:
        (g,) = _read(conn)['groups']
    assert g['ref'] == {'kind': 'repository', 'id': rid}
    assert g['headline'] in digest.ORDER
