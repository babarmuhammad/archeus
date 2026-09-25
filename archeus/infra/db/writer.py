"""The single writer (ADR-0002): one thread, one write connection, one
transaction per command.

A *command* is a function `command(tx, **kwargs) -> JSON-able result`. It is
queued, run on the writer thread inside `BEGIN IMMEDIATE`, and either every row
it wrote — entity rows, the events recording them, its idempotency key — is
committed together, or none is. `submit()` returns a Future resolved only after
COMMIT, so an acknowledged command is durable.

Invariants this module enforces rather than documents:
- the write connection never leaves the writer thread (`check_same_thread`);
  every other connection is `query_only`;
- a command that changed entity state must append at least one event, or its
  transaction is rolled back (`UnrecordedMutation`);
- `events.seq` is assigned here, by SQLite, inside the transaction. One writer
  means commit order IS seq order, so a reader can never see seq N+1 committed
  while N is still in flight — which is what makes "everything after cursor N"
  a complete answer;
- only `Tx.transition()` assigns an entity's state, and only along an edge of
  the P1 state table (state-machines §0). It is the PERSISTENCE primitive —
  version check, edge check, state, version bump, event, reason, one
  transaction. Guards, action semantics, policy and lifecycle orchestration are
  the application layer's (core/application/lifecycle.py), never added here; a
  guarded edge is taken only with that layer's `states.TransitionProof` for the
  exact edge, row and version being changed.
"""

import dataclasses
import hashlib
import json
import queue
import threading
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone

from ...core.domain import events as ev
from ...core.domain import ids, states
from ...core.domain.values import Ref
from . import rows

IDEMPOTENCY_TTL = timedelta(hours=24)       # api-and-realtime §2
MAX_PENDING = 1024


class WriterClosed(RuntimeError):
    pass


class WriterBusy(RuntimeError):
    """The queue is full: back-pressure, never an unbounded backlog."""


class NotFound(LookupError):
    pass


class VersionConflict(RuntimeError):
    def __init__(self, entity_id, expected, current):
        super().__init__('%s is at version %s, not %s' % (entity_id, current, expected))
        self.entity_id, self.expected, self.current = entity_id, expected, current


class InvalidTransition(ValueError):
    def __init__(self, machine, frm, to, why='no such edge'):
        super().__init__('%s: %s -> %s: %s' % (machine, frm, to, why))
        self.machine, self.frm, self.to = machine, frm, to


class IdempotencyConflict(ValueError):
    """A key was reused for a different command, arguments or actor."""


class UnrecordedMutation(RuntimeError):
    """A command changed state without appending the event that records it."""


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _jsonable(o):
    if dataclasses.is_dataclass(o):
        return dataclasses.asdict(o)
    raise TypeError('%r is not JSON-serialisable' % (o,))


def command_name(command):
    return '%s.%s' % (command.__module__, command.__qualname__)


def request_hash(name, kwargs):
    blob = json.dumps({'command': name, 'args': kwargs}, sort_keys=True, default=_jsonable)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def _commit(conn):
    conn.execute('COMMIT')


class Tx:
    """One command's transaction. Made only by the writer thread."""

    def __init__(self, conn):
        self.conn = conn
        self.now = ev.now_iso()
        self.events = []
        self.mutated = False

    def execute(self, sql, params=()):
        """Raw SQL for infrastructure rows (cursors, effects, retention).
        Entity state goes through insert()/transition(), never through here."""
        return self.conn.execute(sql, params)

    def insert_token(self, *, token_hash, kind, principal_id, scopes, actor, expires_at=None):
        """A credential row (api-and-realtime §5.3). Only the token's sha256
        ever reaches the database; the token itself is never an argument here."""
        self.conn.execute(
            'INSERT INTO tokens (token_hash, kind, principal_id, scopes, created_at, '
            'created_by, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (token_hash, kind, principal_id, json.dumps(list(scopes)), self.now, actor.id,
             expires_at))

    def revoke_tokens(self, principal_id):
        """Revoke every live credential of a principal; returns how many."""
        return self.conn.execute(
            'UPDATE tokens SET revoked_at = ? WHERE principal_id = ? AND revoked_at IS NULL',
            (self.now, principal_id)).rowcount

    def get(self, cls, entity_id):
        return rows.get(self.conn, cls, entity_id)

    def where(self, cls, **eq):
        return rows.where(self.conn, cls, **eq)

    def insert(self, entity, *, actor):
        """A new entity row at version 1. `actor` is the causing principal."""
        if not ids.is_id(actor.id, 'principal'):
            raise ValueError('created_by must be a principal id, not %r' % actor.id)
        name = rows.table(type(entity))
        promoted, body = rows.encode(entity, rows.columns(self.conn, name))
        values = dict(promoted, version=1, created_at=self.now, updated_at=self.now,
                      created_by=actor.id, updated_by=actor.id, body=body)
        self.conn.execute('INSERT INTO %s (%s) VALUES (%s)' % (
            name, ', '.join(values), ', '.join('?' * len(values))), tuple(values.values()))
        self.mutated = True
        return rows.Row(entity, 1, self.now, self.now, actor.id, actor.id)

    def update(self, cls, entity_id, fields, *, actor, expected_version=None):
        """Change fields of an entity row other than its id and its state
        (version + 1). State moves only along an edge (`transition`); this is
        for what is not a lifecycle — a stateless entity's cursor. The caller
        appends the event that records it, as for every mutation."""
        row = self.get(cls, entity_id)
        if row is None:
            raise NotFound(entity_id)
        if expected_version is not None and expected_version != row.version:
            raise VersionConflict(entity_id, expected_version, row.version)
        forbidden = {'id'} | ({cls._STATE[0]} if cls._STATE else set())
        if set(fields) & forbidden:
            raise ValueError('update may not set the id or the state; an edge does')
        entity = dataclasses.replace(row.entity, **fields)
        name = rows.table(cls)
        promoted, body = rows.encode(entity, rows.columns(self.conn, name))
        promoted.pop('id')
        sets = dict(promoted, body=body, updated_at=self.now, updated_by=actor.id)
        cur = self.conn.execute(
            'UPDATE %s SET %s, version = version + 1 WHERE id = ? AND version = ?' % (
                name, ', '.join('%s = ?' % c for c in sets)),
            (*sets.values(), entity_id, row.version))
        if cur.rowcount != 1:                    # unreachable with one writer
            raise VersionConflict(entity_id, row.version, None)
        self.mutated = True
        return rows.Row(entity, row.version + 1, row.created_at, self.now, row.created_by,
                        actor.id)

    def append(self, event):
        """Record an event; SQLite assigns its seq. Returns the event with it."""
        if event.seq is not None:
            raise ValueError('seq is assigned by the writer, not the caller')
        cur = self.conn.execute(
            'INSERT INTO events (id, type, at, actor_kind, actor_id, cause_chain, '
            'subject_kind, subject_id, workspace_id, project_id, visibility, payload) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (event.id, event.type, event.at, event.actor.kind, event.actor.id,
             json.dumps(list(event.cause_chain)), event.subject.kind, event.subject.id,
             event.workspace, event.project, event.visibility, json.dumps(event.payload)))
        stored = dataclasses.replace(event, seq=cur.lastrowid)
        self.events.append(stored)
        return stored

    def transition(self, cls, entity_id, to, *, actor, reason, cause=(),
                   expected_version=None, proof=None, fields=None):
        """Move an entity along one edge of its state machine: validate the
        edge, bump `version`, write the row and append `<machine>.state_changed`
        — all in this transaction. Returns (Row, Event). `actor` is the causing
        principal. The persistence half only: the application layer
        (core/application/lifecycle.py) evaluates guards and calls this.

        `proof` (a `states.TransitionProof`) names the edge and binds it to this
        row: its entity, version, from, to and trigger must match, and its
        guard must be the table's guard for that trigger. A guarded edge is
        taken only with a matching proof, so a guard can neither be skipped
        nor reused on a row that changed after it was judged. This module never
        evaluates a guard and knows no machine's meaning — only the table.

        `fields` sets other fields of the entity in the same row write (never
        its state), validated by the entity like any other value."""
        if not cls._STATE:
            raise TypeError('%s has no state machine' % cls.__name__)
        if not (isinstance(reason, str) and reason.strip()):
            raise ValueError('a transition needs a reason (the audit trail)')
        field, machine = cls._STATE
        etype = '%s.state_changed' % machine
        if etype not in ev.REGISTRY:
            raise LookupError('no event type registered for %s transitions' % machine)
        row = self.get(cls, entity_id)
        if row is None:
            raise NotFound(entity_id)
        if expected_version is not None and expected_version != row.version:
            raise VersionConflict(entity_id, expected_version, row.version)
        frm = getattr(row.entity, field)
        edges = [(t, g) for f, dest, t, g in states.edges(machine)
                 if f == frm and dest == to and t is not None]
        if not edges:
            raise InvalidTransition(machine, frm, to)
        if proof is not None:
            if not isinstance(proof, states.TransitionProof):
                raise InvalidTransition(machine, frm, to, 'proof is not a TransitionProof')
            match = [(t, g) for t, g in edges if t == proof.trigger and g == proof.guard]
            if not match or (proof.entity_id, proof.version, proof.frm, proof.to) != (
                    entity_id, row.version, frm, to):
                raise InvalidTransition(machine, frm, to,
                                        'the proof is for another edge, row or version '
                                        '(this row is at version %d)' % row.version)
            taken, g = match[0]
        else:
            free = [(t, g) for t, g in edges if g is None]
            taken, g = (free or edges)[0]
            if g is not None:
                raise InvalidTransition(machine, frm, to,
                                        'guarded by %s: needs a transition proof for this '
                                        'row at version %d' % (g, row.version))
        extra = dict(fields or {})
        if set(extra) & {field, 'id'}:
            raise ValueError('fields may not set the id or the state; the edge does')
        entity = dataclasses.replace(row.entity, **dict(extra, **{field: to}))
        name = rows.table(cls)
        promoted, body = rows.encode(entity, rows.columns(self.conn, name))
        promoted.pop('id')
        sets = dict(promoted, body=body, updated_at=self.now, updated_by=actor.id)
        cur = self.conn.execute(
            'UPDATE %s SET %s, version = version + 1 WHERE id = ? AND version = ?' % (
                name, ', '.join('%s = ?' % c for c in sets)),
            (*sets.values(), entity_id, row.version))
        if cur.rowcount != 1:                    # unreachable with one writer
            raise VersionConflict(entity_id, row.version, None)
        self.mutated = True
        payload = {'from': frm, 'to': to, 'trigger': taken, 'reason': reason}
        if g is not None:
            payload['guard'] = {'name': g, 'reason': proof.guard_reason}
        event = self.append(ev.new_event(
            etype, Ref(ids.kind_of(entity_id), entity_id), actor,
            payload=payload,
            workspace=getattr(entity, 'workspace_id', ids.GLOBAL_WORKSPACE),
            project=getattr(entity, 'project_id', None), cause_chain=cause))
        return (rows.Row(entity, row.version + 1, row.created_at, self.now,
                         row.created_by, actor.id), event)


_STOP = object()


class Writer:
    """The writer thread. `submit()` from any thread; `close()` once."""

    def __init__(self, open_conn, *, max_pending=MAX_PENDING):
        self._q = queue.Queue(max_pending)
        self._lock = threading.Lock()
        self._closed = False
        self._ready = threading.Event()
        self._error = None
        self.committed = self.failed = 0
        # commit notification (api-and-realtime §4): readers — SSE streams, the
        # engine loop — wait here instead of polling the head
        self._commits = threading.Condition()
        self.commit_count = 0
        self._thread = threading.Thread(target=self._run, args=(open_conn,),
                                        name='archeus-writer', daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error is not None:
            raise self._error

    def pending(self):
        return self._q.qsize()

    def submit(self, command, kwargs=None, *, idempotency_key=None):
        kwargs = dict(kwargs or {})
        name = command_name(command)
        # a keyed command's arguments must be JSON (they are what a retry is
        # compared by), and that is checked here, on the caller's thread
        rhash = None if idempotency_key is None else request_hash(name, kwargs)
        fut = Future()
        with self._lock:
            if self._closed:
                raise WriterClosed('the writer is closed')
            try:
                self._q.put_nowait((fut, command, kwargs, idempotency_key, name, rhash))
            except queue.Full:
                raise WriterBusy('%d commands already queued' % self._q.maxsize) from None
        return fut

    def execute(self, command, kwargs=None, *, idempotency_key=None, timeout=None):
        return self.submit(command, kwargs, idempotency_key=idempotency_key).result(timeout)

    def wait_commit(self, seen, timeout, until=None):
        """Block until a command that wrote something commits after *seen* (a
        `commit_count` read earlier), *until()* is true, or *timeout* passes.
        Returns `commit_count` now. Read the count BEFORE reading the rows it
        guards, so a commit landing in between is never slept through; *until*
        is re-checked under the lock `wake()` takes, so a flag set before a
        `wake()` is never slept through either."""
        with self._commits:
            self._commits.wait_for(lambda: self.commit_count != seen or (until and until()),
                                   timeout)
            return self.commit_count

    def wake(self):
        """Wake every waiter so it re-checks its `until` (a stream being closed,
        a stop). Set the flag first, then wake."""
        with self._commits:
            self._commits.notify_all()

    def close(self, *, drain=True, timeout=30):
        """Stop accepting commands. drain=True runs what is queued first;
        drain=False fails it with WriterClosed (nothing queued is committed)."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if not drain:
                while True:
                    try:
                        item = self._q.get_nowait()
                    except queue.Empty:
                        break
                    item[0].set_exception(WriterClosed('the writer closed before this ran'))
        self._q.put(_STOP)
        self._thread.join(timeout)

    # ── the writer thread ──

    def _run(self, open_conn):
        try:
            conn = open_conn()
        except BaseException as e:       # reported to the constructor
            self._error = e
            self._ready.set()
            return
        self._ready.set()
        try:
            while True:
                item = self._q.get()
                if item is _STOP:
                    break
                fut, command, kwargs, key, name, rhash = item
                if not fut.set_running_or_notify_cancel():
                    continue
                try:
                    result = self._one(conn, command, kwargs, key, name, rhash)
                except BaseException as e:
                    self.failed += 1
                    fut.set_exception(e)
                    if not isinstance(e, Exception):
                        raise
                else:
                    self.committed += 1
                    fut.set_result(result)
        finally:
            conn.close()

    def _one(self, conn, command, kwargs, key, name, rhash):
        conn.execute('BEGIN IMMEDIATE')
        try:
            if key is not None:
                replay = self._recall(conn, key, name, rhash)
                if replay is not None:
                    conn.execute('ROLLBACK')
                    return json.loads(replay)
            tx = Tx(conn)
            result = command(tx, **kwargs)
            if tx.mutated and not tx.events:
                raise UnrecordedMutation('%s changed state and recorded no event' % name)
            response = json.dumps(result, default=_jsonable)
            if key is not None:
                actor = kwargs.get('actor')
                conn.execute(
                    'INSERT INTO idempotency_keys (key, command, actor, request_hash, '
                    'response, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                    (key, name, getattr(actor, 'id', '') or '', rhash, response, tx.now))
            _commit(conn)
        except BaseException:
            if conn.in_transaction:
                conn.execute('ROLLBACK')
            raise
        # after COMMIT, so a woken reader sees the rows; never on a rollback or
        # a replay; and not for a command that wrote nothing, or an engine
        # pass of no-op commands would wake the engine that ran them
        if tx.mutated or tx.events:
            with self._commits:
                self.commit_count += 1
                self._commits.notify_all()
        return json.loads(response)

    @staticmethod
    def _recall(conn, key, name, rhash):
        """The stored response for a repeated key; None for a new (or expired) one."""
        hit = conn.execute('SELECT command, request_hash, response, created_at '
                           'FROM idempotency_keys WHERE key = ?', (key,)).fetchone()
        if hit is None:
            return None
        if hit['created_at'] < iso(datetime.now(timezone.utc) - IDEMPOTENCY_TTL):
            conn.execute('DELETE FROM idempotency_keys WHERE key = ?', (key,))
            return None
        if (hit['command'], hit['request_hash']) != (name, rhash):
            raise IdempotencyConflict('idempotency key %r was already used for a different '
                                      'request (%s)' % (key, hit['command']))
        return hit['response']
