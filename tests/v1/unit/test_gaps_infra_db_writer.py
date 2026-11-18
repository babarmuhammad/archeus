"""T-711: the highest-risk uncovered branches of `archeus/infra/db/writer.py`, as tests.

Fail-closed and denial paths first: an UPDATE that matched no row is a conflict and
never a reported version bump — in `transition` (w1) and in `update` (w2); `update`
never writes an id or a state (w3); a transition's `fields` never write the id or the
state (w4) and may only START a secondary machine, never move one (w5, w6); a stateless
entity is never transitioned (w7); a machine without its `<machine>.state_changed`
event type is refused before anything is written (w8). Then the writer thread: a
command cancelled before it ran never runs (w13), a BaseException ends the thread and
closes the write connection instead of leaving it serving (w14), and a connection that
never opened fails the constructor rather than handing back a writer that accepts work
forever (w17) — the seam a failed migration or its pre-migration backup dies at. Then
boundaries and error paths: an idempotency key expires only strictly past the TTL, and
an expired row is deleted (w10); a keyed submit hashes on the caller's thread while an
unkeyed one hashes nothing (w9); a commit that wrote nothing wakes no reader (w11) and
the real `wait_commit`/`wake` release their waiter (w12a, w12b); and a ROLLBACK is
issued only when there is a transaction to roll back (w15, w16).

Same fixture and helper names as tests/v1/integration/test_writer.py and
tests/v1/integration/conftest.py, the closest existing tests of this module; they are
copied here because tests/v1/unit has no conftest. The write connection is the real
SQLite one — the only thing faked is what it answers (one statement raises, or one
UPDATE matches no row), through the same seam-swapping style those tests use
(monkeypatch on the module, a gate to hold the writer thread, a `tmp_path` file). No OS
call is faked, no network, no real process; the only threads are the ones this file
starts and joins, no sleep is over 1 second, every future wait is bounded, and nothing
asserts on the set of live threads.
"""

import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from archeus.core.application import commands
from archeus.core.domain import entities, events as ev, ids
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, connection, migrate, writer

WAIT = 10                                       # every wait on a future here is bounded
PKG = ids.new_id('context_package')            # a field that lives in the row's body


@pytest.fixture
def actor():                                   # as in tests/v1/integration/conftest.py
    return Ref('user_device', ids.new_id('principal'))


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def new_mission(db, actor):
    def make(title='M', key=None):
        return db.writer.execute(commands.create_mission,
                                 {'actor': actor, 'title': title, 'objective': 'o'},
                                 idempotency_key=key, timeout=WAIT)
    return make


# ── commands run on the writer, and the reads that check what they left ──────


def _move(tx, *, actor, mission_id, to='UNDERSTANDING', fields=None):
    """One mission edge through the primitive, as in tests/v1/integration/test_writer.py."""
    row, e = tx.transition(entities.Mission, mission_id, to, actor=actor,
                           reason='test says so', fields=fields)
    return {'state': row.entity.state, 'version': row.version, 'seq': e.seq}


def _edit(tx, *, actor, mission_id):
    """A non-lifecycle write plus the event that records it (what `update` demands)."""
    tx.update(entities.Mission, mission_id, {'context_package_id': PKG}, actor=actor)
    tx.append(ev.new_event('mission.updated', Ref('mission', mission_id), actor))
    return 'edited'


def _new_task(tx, *, actor, mid, started=None):
    """A task with the plan its key requires, at its main machine's initial state."""
    p = entities.Plan(id=ids.new_id('plan'), mission_id=mid)
    tx.insert(p, actor=actor)
    t = entities.Task(id=ids.new_id('task'), plan_id=p.id, mission_id=mid,
                      key='k', title='t', kind='code_change', integration_state=started)
    tx.insert(t, actor=actor)
    tx.append(ev.new_event('task.created', Ref('task', t.id), actor))
    return t.id


def _fire_task(tx, *, actor, task_id, fields):
    """The task's own edge, carrying `fields` for its secondary machine."""
    row, _e = tx.transition(entities.Task, task_id, 'READY', actor=actor,
                            reason='deps satisfied', fields=fields)
    return {'state': row.entity.state, 'version': row.version}


def _only_an_event(tx, *, actor):
    tx.append(ev.new_event('mission.created', Ref('mission', ids.new_id('mission')), actor))
    return 'logged'


def _edit_fields(tx, *, actor, mission_id, fields):
    """Anything `update` may be asked to do with a field it must not touch."""
    tx.update(entities.Mission, mission_id, fields, actor=actor)
    tx.append(ev.new_event('mission.updated', Ref('mission', mission_id), actor))
    return 'edited'


def _row(db, sql, params=()):
    with db.read() as r:
        rec = r.execute(sql, params).fetchone()
        return tuple(rec) if rec is not None else None


def _all(db, sql, params=()):
    with db.read() as r:
        return [tuple(rec) for rec in r.execute(sql, params)]


def _mission(db, mid):
    return _row(db, 'SELECT state, version FROM missions WHERE id = ?', (mid,))


def _types(db, subject_id):
    return [t[0] for t in _all(db, 'SELECT type FROM events WHERE subject_id = ? ORDER BY seq',
                               (subject_id,))]


# ── the writer thread's connection, with what it answers injected ────────────


class _Inject:
    """What the write connection is told to do: `fail` raises on a statement starting
    with that key, `no_rows` makes a statement match no row, `log` is every statement
    the writer thread ran, and `closed` says its connection was closed."""

    def __init__(self):
        self.fail = {}
        self.no_rows = ()
        self.log = []
        self.closed = False


class _NoRows:
    """The cursor of an UPDATE that matched nothing: the row moved under the lock."""

    rowcount = 0
    lastrowid = None

    def fetchone(self):
        return None


class _Conn:
    """The real write connection, with the statements `_Inject` names made to fail or
    to match no row. Only what SQLite answers is faked, never an OS call."""

    def __init__(self, conn, inj):
        self._conn = conn
        self._inj = inj

    def execute(self, sql, params=()):
        self._inj.log.append(sql)
        for prefix, boom in self._inj.fail.items():
            if sql.startswith(prefix):
                raise boom()
        if any(s in sql for s in self._inj.no_rows):
            return _NoRows()
        return self._conn.execute(sql, params)

    def close(self):
        self._inj.closed = True
        self._conn.close()

    def __getattr__(self, name):                  # in_transaction and friends
        return getattr(self._conn, name)


def _writer(path, inj, **kw):
    def open_conn():
        conn = connection.connect(path)
        migrate.migrate(conn)
        return _Conn(conn, inj)
    return writer.Writer(open_conn, **kw)


def _after(path, sql, params=()):
    """A read of the file once the writer that owned it has closed."""
    c = connection.connect(path, readonly=True)
    try:
        return [tuple(rec) for rec in c.execute(sql, params)]
    finally:
        c.close()


def _until(predicate, timeout=WAIT):
    """Poll a writer-thread side effect 10 ms apart, bounded by `timeout`."""
    deadline = time.time() + timeout
    while time.time() < deadline and not predicate():
        time.sleep(0.01)
    return predicate()


# ── fail-closed: a write that matched nothing is never reported as a write ───


def test_w1_a_transition_whose_update_matched_no_row_is_a_conflict(tmp_path, actor):
    # writer.py:297-298 `if cur.rowcount != 1: raise VersionConflict(entity_id,
    # row.version, None)`. Without it the state, the version+1 the caller is handed
    # and the state_changed event are committed over a row that says something else:
    # the log and the table disagree, and the caller believes its edge was taken.
    inj = _Inject()
    path = str(tmp_path / 'w1.db')
    w = _writer(path, inj)
    try:
        mid = w.execute(commands.create_mission,
                        {'actor': actor, 'title': 't', 'objective': 'o'}, timeout=WAIT)['id']
        inj.no_rows = ('version = version + 1',)          # the row moved under the lock
        with pytest.raises(writer.VersionConflict) as err:
            w.execute(_move, {'actor': actor, 'mission_id': mid}, timeout=WAIT)
        assert (err.value.entity_id, err.value.expected, err.value.current) == (mid, 1, None)
        assert 'ROLLBACK' in inj.log                       # writer.py:453-454, the tx is undone
    finally:
        w.close()
    assert _after(path, 'SELECT state, version FROM missions WHERE id = ?', (mid,)) == [
        ('CREATED', 1)]
    assert _after(path, "SELECT COUNT(*) FROM events WHERE type = 'mission.state_changed'") == [
        (0,)]


def test_w2_an_update_whose_update_matched_no_row_is_a_conflict(tmp_path, actor):
    # writer.py:200-201, the same guard on the other write path. Removing it hands the
    # caller a Row at version+1 with the new field, and commits the event that was
    # supposed to record that change, for a row SQLite never touched.
    inj = _Inject()
    path = str(tmp_path / 'w2.db')
    w = _writer(path, inj)
    try:
        mid = w.execute(commands.create_mission,
                        {'actor': actor, 'title': 't', 'objective': 'o'}, timeout=WAIT)['id']
        before = _after(path, 'SELECT version, body FROM missions WHERE id = ?', (mid,))
        inj.no_rows = ('version = version + ?',)           # bump=True is the caller's
        with pytest.raises(writer.VersionConflict) as err:
            w.execute(_edit, {'actor': actor, 'mission_id': mid}, timeout=WAIT)
        assert (err.value.expected, err.value.current) == (1, None)
    finally:
        w.close()
    assert _after(path, 'SELECT version, body FROM missions WHERE id = ?', (mid,)) == before
    assert _after(path, "SELECT COUNT(*) FROM events WHERE type = 'mission.updated'") == [(0,)]


# ── denial: only an edge writes a state, and only its own ───────────────────


@pytest.mark.parametrize('fields', [{'state': 'COMPLETED'}, {'id': ids.new_id('mission')}],
                         ids=['state', 'id'])
def test_w3_update_never_writes_the_id_or_a_state(db, actor, new_mission, fields):
    # writer.py:186-188 `forbidden = {'id'} | cls.state_fields(); if set(fields) &
    # forbidden: raise ValueError`. Drop it and `update` writes a state straight
    # through (the command appends its own event, so nothing else refuses it): a
    # lifecycle jump with no edge, no guard, no proof and no trigger in the payload.
    mid = new_mission()['id']
    with pytest.raises(ValueError, match='may not set the id or the state'):
        db.writer.execute(_edit_fields, {'actor': actor, 'mission_id': mid, 'fields': fields},
                          timeout=WAIT)
    assert _mission(db, mid) == ('CREATED', 1)
    assert _types(db, mid) == ['mission.created']


@pytest.mark.parametrize('fields', [{'state': 'UNDERSTANDING'}, {'id': ids.new_id('mission')}],
                         ids=['state', 'id'])
def test_w4_a_transitions_fields_never_write_the_id_or_the_state(db, actor, new_mission, fields):
    # writer.py:279-280 `if set(extra) & {field, 'id'}: raise ValueError`. Without it
    # `fields` writes the same column the edge writes (or the identity) after the
    # edge check, so `to` is a decoy: the row lands wherever the caller typed.
    mid = new_mission()['id']
    before = _mission(db, mid)
    with pytest.raises(ValueError, match='may not set the id or the state; the edge does'):
        db.writer.execute(_move, {'actor': actor, 'mission_id': mid, 'fields': fields},
                          timeout=WAIT)
    assert _mission(db, mid) == before
    assert _types(db, mid) == ['mission.created']          # the row write and its event


def _task_row(db, tid):
    """(its own state, the secondary machine's state, its version) — only the first
    two are columns of `tasks`; the second lives in the body (T-42)."""
    state, version, body = _row(db, 'SELECT state, version, body FROM tasks WHERE id = ?',
                                (tid,))
    return (state, json.loads(body).get('integration_state'), version)


def test_w5_a_transition_may_start_a_secondary_machine_at_its_initial_state(db, actor,
                                                                             new_mission):
    # writer.py:282-286, the one exception it allows (P13 D22): from None to the
    # machine's initial state. Inverting it refuses the only legal secondary start,
    # so a task could never enter its integration lifecycle at all.
    mid = new_mission()['id']
    tid = db.writer.execute(_new_task, {'actor': actor, 'mid': mid}, timeout=WAIT)
    assert _task_row(db, tid) == ('PENDING', None, 1)
    got = db.writer.execute(_fire_task, {'actor': actor, 'task_id': tid,
                                         'fields': {'integration_state': 'PENDING'}},
                            timeout=WAIT)
    assert got == {'state': 'READY', 'version': 2}
    assert _task_row(db, tid) == ('READY', 'PENDING', 2)
    assert _types(db, tid) == ['task.created', 'task.state_changed']


@pytest.mark.parametrize('started, fields', [
    (None, {'integration_state': 'MERGED'}),               # a move, not a start
    (None, {'integration_state': 'ABANDONED'}),
    ('PENDING', {'integration_state': 'PENDING'}),         # already started
], ids=['moved', 'abandoned', 'again'])
def test_w6_a_transition_never_moves_a_secondary_machine_through_fields(
        db, actor, new_mission, started, fields):
    # writer.py:282-286 `if f not in of_field or getattr(row.entity, f) is not None
    # or extra[f] != states.initial(of_field[f])`. Delete the check and `fields` is a
    # back door into the second lifecycle: integration_state jumps to MERGED with no
    # edge, no guard and a payload describing only the task's own edge.
    mid = new_mission()['id']
    tid = db.writer.execute(_new_task, {'actor': actor, 'mid': mid, 'started': started},
                            timeout=WAIT)
    before = _task_row(db, tid)
    with pytest.raises(ValueError, match='never move one'):
        db.writer.execute(_fire_task, {'actor': actor, 'task_id': tid, 'fields': fields},
                          timeout=WAIT)
    assert _task_row(db, tid) == before
    assert _types(db, tid) == ['task.created']             # nothing of it is recorded


def test_w7_an_entity_without_a_state_machine_is_never_transitioned(db, actor):
    # writer.py:243-244 `if not cls._STATE: raise TypeError`. The refusal is the
    # point: without it the unpack below raises an opaque "cannot unpack None" from
    # deep inside the primitive instead of naming the entity that has no machine.
    with pytest.raises(TypeError, match='has no state machine'):
        db.writer.execute(_stateless, {'actor': actor}, timeout=WAIT)
    assert _all(db, 'SELECT COUNT(*) FROM events') == [(0,)]
    assert _all(db, 'SELECT COUNT(*) FROM route_decisions') == [(0,)]


def _stateless(tx, *, actor):
    return tx.transition(entities.RouteDecision, ids.new_id('route_decision'), 'ANY',
                         actor=actor, reason='no machine here')


def test_w8_a_machine_without_its_registered_event_type_is_refused(db, actor, new_mission,
                                                                   monkeypatch):
    # writer.py:249-250 `if etype not in ev.REGISTRY: raise LookupError`. The audit
    # rule is that a state move and its `<machine>.state_changed` event are one
    # write; skipping the check commits a state change whose event no reader of the
    # registry can decode, and the row has moved with an unregistered type logged.
    mid = new_mission()['id']
    before = _mission(db, mid)
    monkeypatch.delitem(ev.REGISTRY, 'mission.state_changed')
    with pytest.raises(LookupError, match='registered for mission transitions'):
        db.writer.execute(_move, {'actor': actor, 'mission_id': mid}, timeout=WAIT)
    assert _mission(db, mid) == before
    assert _types(db, mid) == ['mission.created']


# ── the writer thread: what it refuses to run, and what ends it ─────────────


def test_w13_a_command_cancelled_before_it_ran_never_runs(tmp_path, actor):
    # writer.py:414-415 `if not fut.set_running_or_notify_cancel(): continue`. A caller
    # that gave up (a disconnected API request) is not re-run for its effects: without
    # the check the command runs, its rows commit, and `fut.set_result` on a cancelled
    # future then raises InvalidStateError on the writer thread.
    inj = _Inject()
    path = str(tmp_path / 'w13.db')
    w = _writer(path, inj)
    gate = threading.Event()
    ran = []
    try:
        w.submit(lambda tx, *, g: g.wait(5), {'g': gate})          # holds the thread
        assert _until(lambda: w.pending() == 0)
        fut = w.submit(_note, {'actor': actor, 'ran': ran})
        assert fut.cancel()                                         # the caller gave up
        gate.set()
        assert w.execute(lambda tx: 'drained', timeout=WAIT) == 'drained'   # ran after it
        assert ran == [] and fut.cancelled()
    finally:
        gate.set()
        w.close()
    assert _after(path, 'SELECT COUNT(*) FROM missions') == [(0,)]
    assert _after(path, 'SELECT COUNT(*) FROM events') == [(0,)]


def _note(tx, *, actor, ran):
    ran.append(1)
    return commands.create_mission(tx, actor=actor, title='t', objective='o')


def test_w14_a_base_exception_ends_the_writer_and_closes_the_connection(tmp_path, actor,
                                                                        monkeypatch):
    # `_run`: `except BaseException ... if not isinstance(e, Exception): raise` and the
    # `finally` that closes the connection and refuses new work. A shutdown signal is not
    # a failed command: catching it as if it were leaves a writer thread that has just
    # watched its own transaction half-run serving the next commit on a connection
    # that may no longer be sound. It stops, the write connection closes with it, and
    # submit says so instead of queueing work nobody will answer.
    escapes = []
    monkeypatch.setattr(threading, 'excepthook', lambda args: escapes.append(args))
    inj = _Inject()
    path = str(tmp_path / 'w14.db')
    w = _writer(path, inj)
    try:
        with pytest.raises(KeyboardInterrupt, match='shutdown'):
            w.execute(_boom, timeout=WAIT)
        assert w.failed == 1 and w.committed == 0
        assert _until(lambda: w._closed)                           # the thread is gone: no new work
        with pytest.raises(writer.WriterClosed):
            w.submit(lambda tx: 'still here')
        assert _until(lambda: inj.closed)                        
        assert _until(lambda: escapes)                             # the thread itself ended
        assert escapes[0].exc_type is KeyboardInterrupt            # for good: out of the loop
        assert escapes[0].thread is not threading.current_thread()
    finally:
        w.close(timeout=2)
    assert _after(path, 'SELECT COUNT(*) FROM missions') == [(0,)]


def _boom(tx):
    raise KeyboardInterrupt('simulated shutdown signal on the writer thread')


def test_w15_a_busy_begin_reaches_the_caller_and_the_writer_survives(tmp_path, actor):
    # writer.py:433 (`conn.execute('BEGIN IMMEDIATE')`, outside the try) with the
    # counted re-raise at 421-423. A writer that cannot even start a transaction
    # fails THAT command and keeps the queue: the error the caller sees is SQLite's,
    # and nothing is rolled back because nothing was ever begun.
    inj = _Inject()
    path = str(tmp_path / 'w15.db')
    w = _writer(path, inj)
    try:
        inj.fail = {'BEGIN IMMEDIATE': lambda: sqlite3.OperationalError('database is locked')}
        with pytest.raises(sqlite3.OperationalError, match='database is locked'):
            w.execute(commands.create_mission, {'actor': actor, 'title': 't', 'objective': 'o'},
                       idempotency_key='busy', timeout=WAIT)
        assert w.failed == 1 and w.committed == 0
        assert 'ROLLBACK' not in inj.log                           # nothing was begun
        inj.fail = {}                                              # the lock cleared
        assert w.execute(commands.create_mission,
                         {'actor': actor, 'title': 't', 'objective': 'o'},
                         idempotency_key='busy', timeout=WAIT)['id']    # the key is still free
    finally:
        w.close()
    assert _after(path, 'SELECT COUNT(*) FROM missions') == [(1,)]


def test_w16_a_command_that_already_committed_is_not_rolled_back_again(tmp_path, actor):
    # writer.py:452-455 `except BaseException: if conn.in_transaction:
    # conn.execute('ROLLBACK')`. A raw-SQL command that committed its own work and
    # then failed is exactly the false arm: rolling back unconditionally here raises
    # "cannot rollback - no transaction is active" inside the handler and replaces
    # the caller's real error with a sqlite3 one.
    inj = _Inject()
    path = str(tmp_path / 'w16.db')
    w = _writer(path, inj)
    try:
        with pytest.raises(ValueError, match='after the commit'):
            w.execute(_commit_then_fail, timeout=WAIT)
        assert w.failed == 1
        assert 'ROLLBACK' not in inj.log
    finally:
        w.close()


def _commit_then_fail(tx):
    tx.execute('COMMIT')                                # a retention command's own commit
    raise ValueError('after the commit')


def test_w17_a_writer_whose_connection_never_opened_raises_from_the_constructor(tmp_path):
    # writer.py:403-406 (the writer thread reports the open_conn failure) with
    # writer.py:336-337 (`if self._error is not None: raise self._error`). This is
    # where a failed migration — or the pre-migration backup `Database.open` takes
    # before it — surfaces. Swallow it and the constructor hands back a Writer whose
    # thread is already dead: every submit() is accepted and never answered.
    attempts = []

    def open_conn():
        attempts.append(1)
        raise migrate.MigrationError('0002_broken.sql failed: simulated')

    w = None
    with pytest.raises(migrate.MigrationError, match='0002_broken'):
        w = writer.Writer(open_conn)
    assert w is None                                    # never assigned: it never opened
    assert attempts == [1]                              # and it tried exactly once


# ── boundaries ──────────────────────────────────────────────────────────────


class _Fixed:
    """The clock `_recall` reads (writer.py:472), pinned so the TTL boundary is exact."""

    def __init__(self, when):
        self.when = when

    def now(self, tz=None):
        return self.when


def _set_key_time(tx, *, key, created_at):
    tx.execute('UPDATE idempotency_keys SET created_at = ? WHERE key = ?', (created_at, key))
    return 'stamped'


def test_w10_an_idempotency_key_expires_only_strictly_past_the_ttl(db, actor, monkeypatch):
    # writer.py:472-474 `if hit['created_at'] < iso(now - IDEMPOTENCY_TTL): DELETE`.
    # A day-old key is the boundary: `<=` retires a key a request is still retrying
    # (the command runs twice, twice the effects), and dropping the DELETE leaves the
    # old row to collide with the new one, so the retry dies on a UNIQUE error.
    fixed = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(writer, 'datetime', _Fixed(fixed))

    def retry():                                  # the SAME request, keyed and retried
        return db.writer.submit(commands.create_mission,
                               {'actor': actor, 'title': 'once', 'objective': 'o'},
                               idempotency_key='k')

    first = retry().result(WAIT)
    assert _all(db, 'SELECT COUNT(*) FROM missions') == [(1,)]

    at_the_ttl = writer.iso(fixed - writer.IDEMPOTENCY_TTL)          # not a day yet
    db.writer.execute(_set_key_time, {'key': 'k', 'created_at': at_the_ttl})
    again = retry()
    assert again.result(WAIT) == first and again.replayed is True
    assert _all(db, 'SELECT COUNT(*) FROM missions') == [(1,)]       # nothing ran

    expired = writer.iso(fixed - writer.IDEMPOTENCY_TTL - timedelta(milliseconds=1))
    db.writer.execute(_set_key_time, {'key': 'k', 'created_at': expired})
    fresh = retry()
    assert fresh.result(WAIT)['id'] != first['id'] and fresh.replayed is False
    assert _all(db, 'SELECT COUNT(*) FROM missions') == [(2,)]
    assert _all(db, 'SELECT created_at FROM idempotency_keys WHERE key = ?',
                ('k',)) != [(expired,)]             # the dead row went, it was not reused


def test_w9_a_keyed_submit_hashes_on_the_callers_thread(db):
    # writer.py:347 `rhash = None if idempotency_key is None else request_hash(...)`,
    # whose comment promises the check runs on the caller's thread. Move it into the
    # command loop and a caller with an unhashable argument is queued first and only
    # then fails, behind everything already waiting; hash an unkeyed command too and
    # the plain path starts refusing arguments it never compared to anything.
    class NotJSON:
        pass

    with pytest.raises(TypeError, match='not JSON-serialisable'):
        db.writer.submit(lambda tx: None, {'o': NotJSON()}, idempotency_key='k')
    assert db.writer.pending() == 0                       # nothing was queued
    assert db.writer.failed == 0
    # the same arguments with no key are nobody's to compare: accepted, and run
    assert db.writer.execute(lambda tx, *, o: 'ok', {'o': NotJSON()}, timeout=WAIT) == 'ok'


# ── the commit notification a reader waits on ───────────────────────────────


def test_w11_a_commit_that_wrote_nothing_wakes_no_reader(db, actor, new_mission):
    # writer.py:459 `if tx.mutated or tx.events:`. Waking the engine for an empty
    # commit is a busy loop of an engine pass against itself; never waking it for a
    # commit that appended an event leaves a stream (or the engine) sitting on a
    # reader that already has something to show.
    seen = db.writer.commit_count
    assert db.writer.execute(lambda tx: None, timeout=WAIT) is None
    assert db.writer.commit_count == seen                 # an empty commit wakes nobody
    new_mission()
    assert db.writer.commit_count == seen + 1
    db.writer.execute(_only_an_event, {'actor': actor}, timeout=WAIT)
    assert db.writer.commit_count == seen + 2             # an event alone is a commit


def test_w12a_the_real_wait_commit_returns_when_a_command_commits(db, actor, new_mission):
    # writer.py:363-373 with the notify at 460-462: the count read BEFORE the rows is
    # what a waiter passes, and the writer's own condition — not a poll — releases it.
    seen = db.writer.commit_count
    got = []
    t = threading.Thread(target=lambda: got.append(db.writer.wait_commit(seen, 5)))
    t.start()
    started = time.perf_counter()
    new_mission()                                         # the commit it is waiting for
    t.join(5)
    assert got == [seen + 1]
    assert time.perf_counter() - started < 2.0        # woken by the commit, not its deadline


def test_w12b_wake_releases_a_waiter_whose_flag_was_set_first(db):
    # writer.py:375-379 (`wake`: notify under the lock) with the `until` half of the
    # predicate at 371. A flag set before the notify is still seen, because both are
    # taken under the same lock; drop the notify and the waiter sits out its whole
    # timeout — a closed stream holds its handler for five more seconds.
    seen = db.writer.commit_count
    flag, got = threading.Event(), []
    t = threading.Thread(target=lambda: got.append(db.writer.wait_commit(seen, 5,
                                                                          until=flag.is_set)))
    t.start()
    flag.set()                                            # set first, then wake, as the
    db.writer.wake()                                      # docstring on `wake` requires
    started = time.perf_counter()
    t.join(5)
    assert got == [seen]                                  # no commit was needed
    assert time.perf_counter() - started < 2.0            # woken, not timed out (of 5)
