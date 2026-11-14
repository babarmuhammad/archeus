"""T-762: the highest-risk uncovered branches of archeus/infra/eventlog/outbox.py.

Fail-closed and denials first — a bool/non-integer/non-negative cursor refused, a bad
limit refused before the log is consulted, the two refusals answering 400 and 410 and
nothing else, a cursor under the retained window refused with its exact bounds, a cursor
past the head refused on an empty log too, and a consumer whose whole batch has been
pruned refused rather than handed the tail — then boundaries — the slowest consumer's
cursor as the floor retention may not pass, the DEFAULT_LIMIT page, limit=1 and
limit=MAX_LIMIT accepted, paging across a pruned log from exactly `floor`, and the bounds
and the rows coming from one snapshot — then the error and decoding paths — head before
the first event and after every event is gone, and decode rebuilding the envelope.

Same real-database style as tests/v1/integration/test_eventlog.py, the closest existing
tests of this module: its `db` fixture is the one in tests/v1/integration/conftest.py,
copied here because tests/v1/unit has no conftest (as in
tests/v1/unit/test_gaps_core_metrics.py). A test's whole seed is one writer command, so
one commit, and every `at` is a literal, so nothing reads the wall clock. The seeded ids
run deliberately OPPOSITE to `seq` (`_uid`), so a page ordered by anything but seq reads
differently. The only fake is a connection that answers the three queries `events_after`
makes, which lets the page statement itself be read (test_g15) and lets a refused
argument be proven never to have reached the log. Nothing here opens a socket or a
process and nothing sleeps or spins on time; the only thread is the writer thread
`Database.open()` starts for every test that opens a database, exactly as the existing
tests of this module do, and the only file access is SQLite under the test's own
`ARCHEUS_HOME`. Every comparison is on integers, ISO-8601 text the test itself wrote and
dict/tuple contents, so nothing here reads differently on Windows than on Linux.
"""

import itertools
import json

import pytest

from archeus.core.domain import ids
from archeus.core.domain.events import REGISTRY
from archeus.core.domain.values import Ref
from archeus.infra.db import Database
from archeus.infra.eventlog import consumers, outbox, retention
from archeus.infra.eventlog.outbox import CursorExpired

MAX = outbox.MAX_LIMIT
OLD = '2020-01-01T00:00:00.000Z'          # outside every retention window
RECENT = '2026-09-15T00:00:00.000Z'       # inside the window measured from NOW
NOW = '2026-10-01T00:00:00.000Z'          # the clock `prune` is asked to use
COLUMNS = ('id', 'type', 'at', 'actor_kind', 'actor_id', 'cause_chain', 'subject_kind',
           'subject_id', 'workspace_id', 'project_id', 'visibility', 'payload')


_ULID_MS = 1759000000000              # pinned: every seeded id carries the same time
_ULID_TOP = 2 ** 79
_ULID_STEP = 977333333333
_SEED = iter(itertools.count())       # one counter for the file: ids stay unique


def _uid(i):
    """The id of the i-th seeded event, its entropy running DOWN as its seq runs UP.
    `ids.new_ulid()` is monotonic within a millisecond, so freshly minted ids sort in
    exactly the order `seq` does and an `ORDER BY id` page would read as correct; a
    pinned descending entropy means it does not. One counter for the whole file, so a
    test that seeds twice still gives every event its own id."""
    return ids.new_ulid(at_ms=_ULID_MS, entropy=_ULID_TOP - (i + 1) * _ULID_STEP)


def _row(etype='mission.created', *, at=RECENT, payload=None, cause=(), project=None,
         actor='system', visibility=None, uid=None):
    """A complete `events` row but for `seq`, which the writer assigns. `at` is always
    given: no test in this file depends on the time the suite runs at."""
    kind = REGISTRY[etype][1]
    return {'id': uid or ids.new_ulid(), 'type': etype, 'at': at, 'actor_kind': actor,
            'actor_id': ids.new_id('principal'), 'cause_chain': json.dumps(list(cause)),
            'subject_kind': kind, 'subject_id': ids.new_id(kind),
            'workspace_id': ids.GLOBAL_WORKSPACE, 'project_id': project,
            'visibility': visibility or REGISTRY[etype][2],
            'payload': json.dumps({'n': 1} if payload is None else payload)}


def _insert(tx, *, rows):
    sql = 'INSERT INTO events (%s) VALUES (%s)' % (
        ','.join(COLUMNS), ','.join('?' * len(COLUMNS)))
    for r in rows:
        tx.execute(sql, [r[c] for c in COLUMNS])


def _clear(tx):
    """Every event gone with `seq` still spent — where `prune` ends when the whole log
    is outside the window and no consumer holds it back (retention.py:26-28)."""
    tx.execute('DELETE FROM events')


class _NoConn:
    """A connection for the argument guards: any query at all means a refused cursor or
    limit got as far as the log (outbox.py:59-65), which is the bug being tested for."""

    def __init__(self):
        self.used = []

    def execute(self, sql, params=()):
        self.used.append((sql, tuple(params)))
        raise AssertionError('a refused argument reached the database: %s' % sql)


class _Int(int):
    """What an HTTP layer's `int(x)` hands back: an integer that is not `int` itself."""


class _Row(dict):
    """A `sqlite3.Row` stand-in: indexable by column name (what `decode` does) and by
    position (what `floor` and `head` do)."""

    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else dict.__getitem__(self, key)


class _Rows:
    """What `conn.execute` answers: iterable for the page, `fetchone` for a bound."""

    def __init__(self, items):
        self.items = list(items)

    def __iter__(self):
        return iter(self.items)

    def fetchone(self):
        return self.items[0] if self.items else None


class _Sql:
    """A read connection that answers the three queries `events_after` makes and keeps
    their text, so the page statement can be read as well as its rows. It is a spy on
    the SQL, not a second implementation of the log: it hands back what it is given."""

    def __init__(self, rows, head=0):
        self.rows, self.head_value, self.calls = rows, head, []

    def execute(self, sql, params=()):
        self.calls.append((' '.join(sql.split()), tuple(params)))
        if 'sqlite_sequence' in sql:
            return _Rows([_Row(seq=self.head_value)])
        if 'MIN(seq)' in sql:
            return _Rows([_Row(seq=min([r['seq'] for r in self.rows], default=None))])
        later = sorted((r for r in self.rows if r['seq'] > params[0]), key=lambda r: r['seq'])
        return _Rows(later[:params[1]])


def _stored(n=3, **kw):
    """*n* rows as the database holds them: `seq` assigned, the JSON columns as text."""
    return [_Row(dict(_row(uid=_uid(next(_SEED)), **kw), seq=i + 1)) for i in range(n)]


@pytest.fixture
def db(archeus_home):                     # as in tests/v1/integration/conftest.py
    d = Database.open()
    yield d
    d.close()


def put(db, rows):
    """Append rows in one command; returns the seqs SQLite assigned, ascending."""
    db.writer.execute(_insert, {'rows': list(rows)})
    with db.read() as conn:
        return [r[0] for r in conn.execute('SELECT seq FROM events ORDER BY seq')]


def seed(db, n=1, **kw):
    return put(db, [_row(uid=_uid(next(_SEED)), **kw) for _ in range(n)])


def after(db, cursor, **kw):
    with db.read() as conn:
        return outbox.events_after(conn, cursor, **kw)


def head(db):
    with db.read() as conn:
        return outbox.head(conn)


def floor(db):
    with db.read() as conn:
        return outbox.floor(conn)


def prune(db, **kw):
    return db.writer.execute(retention.prune, dict({'now': NOW}, **kw))


def lag(db, name, seq):
    """Register *name* as a consumer that has taken *seq* (consumers.py:_advance)."""
    db.writer.execute(consumers._advance, {'name': name, 'seq': seq})


def _prefix_and_tail(db):
    """Events 1..2 outside the window, 3..5 inside it: `prune` may remove the prefix."""
    put(db, [_row(at=OLD, uid=_uid(next(_SEED))) for _ in (0, 1)]
          + [_row(uid=_uid(next(_SEED))) for _ in (0, 1, 2)])


# ── fail-closed and denials ────────────────────────────────────────────────────────


@pytest.mark.parametrize('bad', [False, True, -1, '0', 1.0, None, []],
                         ids=['false', 'true', 'minus-1', 'str', 'float', 'none', 'list'])
def test_g1_a_cursor_that_is_not_an_integer_is_refused_without_reading_the_log(bad):
    # outbox.py:55-56. The bool arm has to hold for False as well as True (and only
    # True is covered by test_eventlog.py:70): drop `isinstance(cursor, bool)` and
    # `False` IS the integer 0, so a caller that has no cursor to give gets the whole
    # log back instead of a refusal. The HTTP route screens its own text cursor
    # (routes.py:96 `_cursor`), so this guard is what stands between every IN-PROCESS
    # caller (consumers.py:50, api/sse.py:149) and its own bug. `'0'`/`1.0`/`None`/`[]`
    # are the `not isinstance(cursor, int)` arm, `-1` the `cursor < 0` arm. The guard
    # answers before outbox.py:59, so the log is never queried.
    conn = _NoConn()
    with pytest.raises(ValueError, match='cursor'):
        outbox.events_after(conn, bad)
    assert conn.used == []


@pytest.mark.parametrize('bad', [False, True, 0, -1, None, '10', 1.5, MAX + 1],
                         ids=['false', 'true', '0', 'minus-1', 'none', 'str', 'float',
                              'max+1'])
def test_g2_a_bad_limit_is_a_client_error_before_the_cursor_is_consulted(bad):
    # outbox.py:57-58. cursor 10**9 would be `ahead` (outbox.py:62-63) if the bounds
    # were read first, so a ValueError naming the limit proves the order; inverting
    # `not 1 <= limit <= MAX_LIMIT` either refuses a legal page or — with the upper
    # bound gone — lets one caller pull the whole log into memory on one read command,
    # which is the writer thread blocking (db/writer.py). The 400 it earns is
    # api/server.py:172-173; it must not be the 410 of outbox.py:61/63, because the
    # client is wrong and the log is fine.
    conn = _NoConn()
    with pytest.raises(ValueError, match='limit') as err:
        outbox.events_after(conn, 10 ** 9, limit=bad)
    assert conn.used == [] and not isinstance(err.value, LookupError)
    with pytest.raises(ValueError, match='cursor') as both:
        outbox.events_after(conn, -1, limit=0)      # line 55 is checked before line 57
    assert 'limit' not in str(both.value)


def test_g3_expired_and_malformed_are_different_kinds_of_answer(db):
    # outbox.py:26 `class CursorExpired(LookupError)` against the ValueError at
    # outbox.py:56: api/server.py:162-163 turns the first into `410 cursor_expired`
    # (the resync every cursor-bearing reader needs, and the one api/sse.py:204-208
    # writes as an SSE frame) and api/server.py:172-173 the second into
    # `400 invalid_request`. Nothing in tests/v1 asserts either relationship — rebase
    # CursorExpired on ValueError, or on object, and every existing test still passes
    # while the API answers a needed resync with a client error.
    seed(db, 1)
    assert issubclass(outbox.CursorExpired, LookupError)
    assert not issubclass(outbox.CursorExpired, ValueError)
    with pytest.raises(CursorExpired) as err:
        after(db, 2)                                # one past the head
    assert isinstance(err.value, LookupError) and not isinstance(err.value, ValueError)
    with pytest.raises(ValueError) as err:
        after(db, -1)
    assert not isinstance(err.value, LookupError)


def test_g4_a_cursor_below_the_retained_window_is_pruned_with_its_exact_bounds(db):
    # outbox.py:60-61 plus the four arguments of outbox.py:28-29. test_eventlog.py:93
    # prunes the WHOLE log, where floor == head, so swapping `floor` and `head` in the
    # CursorExpired call is invisible there; here they differ (2 and 5) and both are
    # asserted, as is the message the 410 body (api/server.py:163) is built from.
    _prefix_and_tail(db)
    assert prune(db)['through'] == 2
    with pytest.raises(CursorExpired) as err:
        after(db, 1)
    e = err.value
    assert (e.cursor, e.reason, e.floor, e.head) == (1, 'pruned', 2, 5)
    assert str(e) == 'cursor 1 is pruned (retained: 2..5)'      # outbox.py:28


def test_g5_a_cursor_the_log_never_assigned_is_ahead_even_with_nothing_in_it(db):
    # outbox.py:62-63. test_eventlog.py:82 only tries head+1 on a log with rows; on an
    # EMPTY log head is 0, so deleting this raise (or its `cursor > high` test) turns a
    # cursor from a restored backup into a silent empty page — the reader waits forever
    # for an event this database will never assign, and never gets its resync.
    assert (head(db), floor(db)) == (0, 0)
    with pytest.raises(CursorExpired) as err:
        after(db, 1)
    assert (err.value.cursor, err.value.reason, err.value.floor, err.value.head) == \
        (1, 'ahead', 0, 0)
    _prefix_and_tail(db)
    prune(db)
    with pytest.raises(CursorExpired) as err:
        after(db, 6)
    assert err.value.reason == 'ahead' and str(err.value) == 'cursor 6 is ahead (retained: 2..5)'


def test_g6_a_consumer_whole_batch_was_pruned_is_refused_not_handed_the_tail(db):
    # outbox.py:60-61 through consumers.py:49-50, and the `if slowest is not None`
    # False arm at retention.py:26-27. Nobody has ever registered as a consumer, so
    # nothing holds `prune` back and the whole log goes. `deliver` must refuse that
    # reader exactly as the stream does (api/sse.py:204-208 writes `cursor_expired`
    # and stops) rather than starting it at what happens to be left and returning a
    # count as if the batch had been delivered. The handler must not run at all.
    seqs = seed(db, 3, at=OLD)
    assert prune(db) == {'events': 3, 'through': seqs[-1], 'idempotency_keys': 0}
    assert floor(db) == seqs[-1]
    seen = []
    with pytest.raises(CursorExpired) as err:
        consumers.deliver(db, 'late', seen.append)
    assert (err.value.reason, err.value.cursor) == ('pruned', 0)
    assert seen == []
    with db.read() as conn:
        assert consumers.cursor(conn, 'late') == 0     # refused, so it has not moved


def test_g7_retention_may_not_pass_the_slowest_consumer_cursor(db):
    # retention.py:25 `through = min(through, slowest)`, which is what keeps
    # outbox.py:60 from ever refusing a consumer that is merely behind. With the clamp
    # removed (or `min` made `max`) seq 3 — never delivered to `slow` — is deleted with
    # the rest of the prefix, `floor` moves to 3 and the consumer below it is 410'd:
    # a skipped event nobody can account for again.
    seed(db, 3, at=OLD)
    seed(db, 2)
    lag(db, 'slow', 2)
    assert prune(db) == {'events': 2, 'through': 2, 'idempotency_keys': 0}
    assert floor(db) == 2                              # the retained window starts at 3
    assert [e.seq for e in after(db, 2)] == [3, 4, 5]  # its own next event is still there
    seen = []
    assert consumers.deliver(db, 'slow', seen.append) == 3
    assert [e.seq for e in seen] == [3, 4, 5]
    with db.read() as conn:
        assert consumers.cursor(conn, 'slow') == 5


# ── boundaries ─────────────────────────────────────────────────────────────────────


def test_g8_the_default_page_is_default_limit_events_and_oldest_first(db):
    # outbox.py:53 `limit=DEFAULT_LIMIT` and outbox.py:64's `LIMIT ?`. Every existing
    # test of this module holds 7 events or fewer, so the default page size has never
    # been observed: consumers.deliver brings its own 100 (consumers.py:45) and
    # api/sse.py:149 its own MAX_LIMIT, so nothing in the tree pins this number.
    # Widen it to MAX_LIMIT and one read command holds a thousand events in memory
    # while the writer thread is busy; narrow it and a caller that omits a limit
    # silently gets half a page. 501 events, one commit.
    seed(db, outbox.DEFAULT_LIMIT + 1)
    page = after(db, 0)
    assert len(page) == outbox.DEFAULT_LIMIT == 500
    assert [e.seq for e in page] == list(range(1, outbox.DEFAULT_LIMIT + 1))
    assert [e.seq for e in after(db, page[-1].seq)] == [outbox.DEFAULT_LIMIT + 1]


@pytest.mark.parametrize('limit', [1, MAX], ids=['1', 'max'])
def test_g9_the_smallest_and_the_largest_page_are_both_accepted(db, limit):
    # outbox.py:57 `not 1 <= limit <= MAX_LIMIT`: the two accept sides of the same
    # comparison, untested on either end (test_eventlog.py:76 only tries rejections).
    # Tighten it to `1 < limit` and the pre-200 probe api/sse.py:163 makes with
    # limit=1 becomes a 400; tighten the upper end and the MAX_LIMIT page
    # api/sse.py:149 reads for its backlog dies.
    seed(db, 5)
    page = after(db, 0, limit=limit)
    assert [e.seq for e in page] == list(range(1, min(limit, 5) + 1))


def test_g10_pages_from_the_floor_cover_every_retained_event_exactly_once(db):
    # outbox.py:64 `WHERE seq > ? ORDER BY seq LIMIT ?` against the floor of
    # outbox.py:41. `floor` is the smallest cursor a reader may hold, so paging must
    # start AT it and still see the first retained event: turn `cursor < low` at
    # outbox.py:60 into `cursor <= low`, or `seq > ?` at outbox.py:64 into `seq >= ?`,
    # and this page either loses seq 3 or repeats seq 2. `ORDER BY` inverted to DESC
    # hands back the newest events first and the walk never reaches the tail; pointing
    # it at `id` fails here too, because the seeded ids run opposite to seq.
    _prefix_and_tail(db)
    prune(db)
    low, seen = floor(db), []
    assert low == 2
    cursor, pages = low, 0
    while True:
        pages += 1
        # a page that does not move the cursor would walk forever; bounded, so a bug
        # here fails the test instead of hanging the suite
        assert pages <= 4, 'the walk never ended, stuck at cursor %d' % cursor
        page = after(db, cursor, limit=2)
        if not page:
            break
        assert [e.seq for e in page] == sorted(e.seq for e in page)
        seen += [e.seq for e in page]
        cursor = page[-1].seq
    assert seen == [3, 4, 5] and cursor == head(db)


def test_g11_the_bounds_and_the_rows_come_from_the_one_snapshot(db):
    # outbox.py:59 `low, high = floor(conn), head(conn)`, read on the CALLER's
    # connection: if either bound were read on a connection of its own (a second
    # `db.read()`, as an "extracted helper" refactor would do) the commit that lands
    # below would move `head` past the rows, and the caught-up cursor in the last
    # assertion would be refused as `ahead` for no reason the client can act on.
    seed(db, 3)
    with db.read() as conn:
        first = [e.seq for e in outbox.events_after(conn, 0)]
        high = outbox.head(conn)
        assert (high, first) == (3, [1, 2, 3])
        db.writer.execute(_insert, {'rows': [_row(), _row()]})   # commits while open
        assert outbox.head(conn) == high                     # same snapshot: no new head
        assert outbox.floor(conn) == 0                         # ...and no new floor
        assert [e.seq for e in outbox.events_after(conn, 0)] == first
        assert outbox.events_after(conn, high) == []           # caught up, not `ahead`
    assert [e.seq for e in after(db, 0)] == [1, 2, 3, 4, 5]


def test_g12_head_survives_deleting_every_event_and_floor_follows_it(db):
    # outbox.py:35 `return r[0] if r else 0` (no sqlite_sequence row at all: a fresh
    # database) and outbox.py:41 `return head(conn) if low is None` (an empty log with
    # the seq space spent). Read `head` as `MAX(seq) FROM events`, or `floor` as
    # `low — 1` unconditionally, and after the last event goes a caught-up reader is
    # told `ahead` forever while a reader of a fresh log gets `floor` of -1 and no
    # refusal it needs. `seq` is never reused, which is what makes `ahead` mean
    # "this database never assigned that".
    assert (head(db), floor(db)) == (0, 0) and after(db, 0) == []
    assert seed(db, 4) == [1, 2, 3, 4]
    assert (head(db), floor(db)) == (4, 0)      # floor is MIN(seq) - 1, and MIN is 1
    db.writer.execute(_clear)
    assert (head(db), floor(db)) == (4, 4)
    assert after(db, 4) == []
    with pytest.raises(CursorExpired) as err:
        after(db, 3)
    assert (err.value.reason, err.value.floor, err.value.head) == ('pruned', 4, 4)
    assert seed(db, 1) == [5]                                  # AUTOINCREMENT, no reuse


def test_g13_an_integer_that_is_not_int_is_still_a_cursor(db):
    # outbox.py:55 `not isinstance(cursor, int)`: the accept side, which no existing
    # test walks (test_eventlog.py:70 only checks refusals). Written as
    # `type(cursor) is not int` — the "stricter" edit this guard invites — every
    # cursor the HTTP layer parses through an int subclass is refused as malformed,
    # a 400 for a request that is fine.
    seed(db, 2)
    assert [e.seq for e in after(db, _Int(0))] == [1, 2]
    assert after(db, _Int(2)) == []


# ── decoding the rows the cursor selected ──────────────────────────────────────────


def test_g14_decode_rebuilds_the_envelope_the_row_describes(db):
    # outbox.py:44-50, for the three columns no existing test of this module puts a
    # value into: `cause_chain`, `project_id` and a payload with anything in it
    # (test_eventlog.py:62-67 replays a mission.created with `[]`, NULL and `{}`, where
    # dropping a `json.loads` at outbox.py:49-50 is invisible). Drop either one and
    # `Event.__post_init__` rejects the row — a cause_chain of the STRING '["A","B"]'
    # is not a sequence of ULIDs, a payload of text is not a dict — and the reader
    # gets a 500 where it should get its events. Swap the actor and subject columns
    # and the envelope says the wrong principal caused it.
    cause = [ids.new_ulid(), ids.new_ulid()]
    project = ids.new_id('project')
    payload = {'from': 'CREATED', 'to': 'RUNNING', 'nested': {'a': [1, 2]}}
    rows = [_row('mission.state_changed', payload=payload, cause=cause, project=project,
                 visibility='system')]
    (seq,) = put(db, rows)
    (e,) = after(db, 0)
    assert e.seq == seq and e.id == rows[0]['id'] and e.type == 'mission.state_changed'
    assert e.at == RECENT and e.visibility == 'system'
    assert e.actor == Ref('system', rows[0]['actor_id'])          # :46, not :47
    assert e.subject == Ref('mission', rows[0]['subject_id'])     # :47, not :46
    assert e.workspace == ids.GLOBAL_WORKSPACE and e.project == project   # :48
    assert isinstance(e.cause_chain, tuple) and e.cause_chain == tuple(cause)   # :49
    assert isinstance(e.payload, dict) and e.payload == payload               # :50
    env = e.to_envelope()
    assert env['seq'] == seq and env['cause_chain'] == cause and env['payload'] == payload
    assert env['actor'] == {'kind': 'system', 'id': rows[0]['actor_id']}


def test_g15_the_page_statement_is_a_seq_cursor_page_and_nothing_else():
    # outbox.py:64-65, the statement itself. `seq` is the rowid (0001_init.sql:76
    # `seq INTEGER PRIMARY KEY AUTOINCREMENT`), so a bare table scan comes back in seq
    # order whatever the query says: test_g10 catches an `ORDER BY` aimed at the wrong
    # column or at DESC (the seeded ids run opposite to seq) but cannot see it DELETED
    # — this is the one test that can. The assertion is on the statement, kept loose on
    # purpose: any `seq > ?` page bound by a placeholder and ordered by seq passes,
    # `seq >= ?`, an unbounded page, a DESC page and the two bindings swapped do not.
    conn = _Sql(_stored(3), head=3)
    page = outbox.events_after(conn, 1, limit=2)
    assert [e.seq for e in page] == [2, 3]
    emitted = [c for c in conn.calls if c[1] == (1, 2)]
    assert len(emitted) == 1, conn.calls
    sql, params = emitted[0]
    assert params == (1, 2)                            # the cursor is the first binding
    assert 'seq > ?' in sql and 'seq >= ?' not in sql   # outbox.py:64's cursor predicate
    assert 'ORDER BY' in sql.upper() and 'DESC' not in sql.upper()
    assert 'LIMIT' in sql.upper()                       # a page, not the whole log
