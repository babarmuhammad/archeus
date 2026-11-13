"""T-1150: the highest-risk still-uncovered branches of archeus/infra/eventlog/outbox.py
lines 1-65 (tip 56d53504). Fail-closed and denials first, then boundaries, then error
paths. The card's ten starter probes were walked first; those already covered by
tests/v1/unit/test_gaps_infra_eventlog_outbox.py (g1-g15), tests/v1/integration/
test_eventlog.py or tests/v1/unit/test_gaps_infra_eventlog_retention.py were replaced,
and the replacement list is (source line -> test):

  1. outbox.py:60-61 vs :64-65  a pruned refusal must precede any page read ....... t1
  2. outbox.py:62-63 vs :64-65  an ahead refusal precedes the page, and a cursor
     beyond the driver's integer range never reaches a bind ....................... t2
  3. outbox.py:34-35            `head` counts only the sqlite_sequence row of
                                'events', whatever else that table holds ........... t3
  4. outbox.py:38-41, :60       `floor` is MIN(seq) - 1 even across a hole, so a
                                 retained history is never silently refused ........ t4
  5. outbox.py:57               the int-subclass accept arm of the limit guard ..... t5
  6. outbox.py:50, :64          truncated payload JSON aborts the whole page; the
                                 reader is never handed an invented event .......... t6
  7. outbox.py:49               malformed / foreign cause_chain JSON refused ....... t7
  8. outbox.py:44-50            an unregistered event type cannot be read back ..... t8
  9. outbox.py:44-50            a NULL or missing column fails the read instead of
                                decode substituting a default (fake conn: the real
                                schema is NOT NULL, so NULL is corruption only a
                                seam can present) ................................. t9
 10. outbox.py:50 + events.py:201-202  a stored payload of `null` must be refused,
     not fabricated into `{}` - kept as xfail(strict=True) per the card ........... t10

Same real-database style as tests/v1/integration/test_eventlog.py and the existing
tests/v1/unit/test_gaps_infra_eventlog_outbox.py; its `db` fixture is the one from
tests/v1/integration/conftest.py copied here (tests/v1/unit has no conftest; the
`archeus_home` it needs is the autouse fixture of tests/v1/conftest.py). Every seed
is one writer command, every `at` is a literal, seeded ids run OPPOSITE to `seq` so
an `ORDER BY` fault reads differently, and the only fakes are connections answering
the three queries `events_after` makes - there is no OS seam to fake here (this slice
reads no clock, no file, no socket), so none is touched. Nothing sleeps, nothing
spawns, nothing reads the host environment; all files are SQLite under the test's own
ARCHEUS_HOME (tmp_path). Portable on purpose: no path separators, no case
sensitivity, no OS error text.
"""

import itertools
import json

import pytest

from archeus.core.domain import ids
from archeus.core.domain.events import REGISTRY
from archeus.infra.db import Database
from archeus.infra.eventlog import outbox
from archeus.infra.eventlog.outbox import CursorExpired

MAX = outbox.MAX_LIMIT
AT = '2026-09-15T00:00:00.000Z'                      # a literal: nothing reads the clock
COLUMNS = ('id', 'type', 'at', 'actor_kind', 'actor_id', 'cause_chain', 'subject_kind',
           'subject_id', 'workspace_id', 'project_id', 'visibility', 'payload')

_ULID_MS = 1759000000000                              # pinned: every seeded id is the same ms
_ULID_TOP = 2 ** 79
_ULID_STEP = 977333333333
_SEED = iter(itertools.count())                       # one counter for the file: ids stay unique


def _uid(i):
    """The id of the i-th seeded event, entropy running DOWN as its seq runs UP, so a
    page ordered by anything but seq reads differently (as in the existing gaps file)."""
    return ids.new_ulid(at_ms=_ULID_MS, entropy=_ULID_TOP - (i + 1) * _ULID_STEP)


def _row(etype='mission.created', *, over=None):
    """A complete `events` row but for `seq`; `over` writes raw column text so a test
    can store exactly the damaged value it is about (`payload='{"n": 1'`, `type=`...)."""
    kind = REGISTRY[etype][1]
    r = {'id': _uid(next(_SEED)),
         'type': etype, 'at': AT, 'actor_kind': 'system', 'actor_id': ids.new_id('principal'),
         'cause_chain': '[]', 'subject_kind': kind, 'subject_id': ids.new_id(kind),
         'workspace_id': ids.GLOBAL_WORKSPACE, 'project_id': None,
         'visibility': REGISTRY[etype][2], 'payload': '{"n": 1}'}
    r.update(over or {})
    return r


def _put(tx, *, rows):
    sql = 'INSERT INTO events (%s) VALUES (%s)' % (
        ','.join(COLUMNS), ','.join('?' * len(COLUMNS)))
    for r in rows:
        tx.execute(sql, [r[c] for c in COLUMNS])


def _drop(tx, *, seq):
    """A damaging middle delete (not `prune`, which only ever removes a prefix): the
    fault `floor` has to survive."""
    tx.execute('DELETE FROM events WHERE seq = ?', (seq,))


def _decoy(tx, *, name, seq):
    """A foreign sqlite_sequence row, as a restored backup or a schema bug could leave."""
    tx.execute('INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)', (name, seq))


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


class _Spy:
    """A read connection answering the three queries `events_after` makes and keeping
    the text of every call, so a refusal can be proven to have issued the two bound
    reads and NOTHING else - no page, no write, no pragma."""

    def __init__(self, rows, head):
        self.rows, self.head_value, self.calls = rows, head, []

    def execute(self, sql, params=()):
        self.calls.append((' '.join(sql.split()), tuple(params)))
        if 'sqlite_sequence' in sql:
            return _Rows([_Row(seq=self.head_value)])
        if 'MIN(seq)' in sql:
            return _Rows([_Row(seq=min([r['seq'] for r in self.rows], default=None))])
        later = sorted((r for r in self.rows if r['seq'] > params[0]), key=lambda r: r['seq'])
        return _Rows(later[:params[1]])


def _stored(n=3, *, start=1):
    """*n* rows as the database holds them, seqs `start..start+n-1`, JSON columns text."""
    return [_Row(dict(_row(), seq=start + i)) for i in range(n)]


@pytest.fixture
def db(archeus_home):                                 # as in tests/v1/integration/conftest.py
    d = Database.open()
    yield d
    d.close()


def put(db, rows):
    db.writer.execute(_put, {'rows': list(rows)})


def seed(db, n=1):
    put(db, [_row() for _ in range(n)])


def after(db, cursor, **kw):
    with db.read() as conn:
        return outbox.events_after(conn, cursor, **kw)


def head(db):
    with db.read() as conn:
        return outbox.head(conn)


def floor(db):
    with db.read() as conn:
        return outbox.floor(conn)


# ── denials first: a refusal must not read, and must not bind ──────────────────────


def test_t1_a_pruned_cursor_is_refused_before_any_page_is_read():
    # outbox.py:60-61 checked against outbox.py:64-65, and the order of the two bound
    # reads at :59. The closest existing test, gaps g4, proves the refusal's CONTENT on
    # a real database; on a real database it cannot prove the refusal came FIRST,
    # because a page query that ran and was thrown away looks identical from outside.
    # Reorder `events_after` to read the page before checking `cursor < low` (the shape
    # that turns a 410 into "the caller forgot to raise") and this spy sees the page.
    # Handing the pruned reader the surviving tail while raising is exactly the silent
    # history loss the module docstring forbids.
    conn = _Spy(_stored(3, start=3), head=5)          # retained 3..5: floor 2, head 5
    with pytest.raises(CursorExpired) as err:
        outbox.events_after(conn, 1)
    e = err.value
    assert (e.cursor, e.reason, e.floor, e.head) == (1, 'pruned', 2, 5)   # outbox.py:28-29
    assert len(conn.calls) == 2, conn.calls                                # nothing extra
    assert 'MIN(seq)' in conn.calls[0][0]                      # :59 evaluates floor first
    assert 'sqlite_sequence' in conn.calls[1][0]               # ...then head
    assert not [s for s, _ in conn.calls if 'seq > ?' in s]    # :64 never ran
    assert all(s.lstrip().upper().startswith('SELECT') for s, _ in conn.calls)


@pytest.mark.parametrize('bad', [6, 2 ** 63, 10 ** 400],
                         ids=['head-plus-1', 'int64-overflow', 'absurd'])
def test_t2_an_ahead_cursor_is_refused_before_any_page_is_read(bad):
    # outbox.py:62-63. gaps g5 tries `head + 1` on a real database only: a small cursor
    # passes whether the comparison happens in Python (as it must) or in SQL. `2 ** 63`
    # and `10 ** 400` do not fit a SQLite bind at all - move the bound check into the
    # page statement and a reader holding a cursor from a restored backup gets the
    # driver's integer-range error (a 500) instead of its 410 resync, and waits forever.
    # The spy also proves the refused cursor was never handed to the log.
    conn = _Spy(_stored(3, start=3), head=5)
    with pytest.raises(CursorExpired) as err:
        outbox.events_after(conn, bad)
    e = err.value
    assert (e.cursor, e.reason, e.floor, e.head) == (bad, 'ahead', 2, 5)
    assert len(conn.calls) == 2, conn.calls
    assert not [s for s, _ in conn.calls if 'seq > ?' in s]                # :64 never ran
    assert all(p != bad for _, params in conn.calls for p in params)       # never bound


# ── boundaries: the bounds themselves must not omit or invent history ──────────────


def test_t3_head_counts_only_the_events_sqlite_sequence_row(db):
    # outbox.py:34 `WHERE name = 'events'`. The closest existing test, gaps g12, runs on
    # a database whose sqlite_sequence holds at most that one row, so deleting the
    # predicate changes nothing there. With a foreign row FIRST in the table (a restored
    # backup or a stray writer command), an unscoped `fetchone` answers the foreign seq:
    # `head` jumps to 999, the cursor of a reader this database never assigned is
    # silently accepted as if it were caught up (it would wait forever for an event
    # that never comes: no 410, no resync), and a real caught-up reader at 2 must still
    # read the empty page while 3 is refused `ahead` with the TRUE bounds.
    db.writer.execute(_decoy, {'name': 'zzz_other_table', 'seq': 999})      # before events'
    seed(db, 2)
    assert (head(db), floor(db)) == (2, 0)             # the decoy is not the log's head
    assert [e.seq for e in after(db, 0)] == [1, 2]
    assert after(db, 2) == []                          # exactly head: caught up, fine
    with pytest.raises(CursorExpired) as err:
        after(db, 3)
    assert (err.value.reason, err.value.floor, err.value.head) == ('ahead', 0, 2)


def test_t4_floor_is_min_seq_minus_one_across_a_hole(db):
    # outbox.py:40 `low - 1` and outbox.py:60, across a hole. gaps g12 and the retention
    # file's contiguity tests only ever see the whole log or a PRUNED PREFIX, where
    # `MIN(seq) - 1` and a formula like `head - retained_count` answer the same every
    # time. Delete one middle event (a damaging `_drop`, which `prune` never does) and
    # they split: with the wrong formula `floor` becomes 1 or 2 and a reader at 0,
    # whose history from 0 is fully retained, is refused `pruned` - exactly the
    # history the bounds promise never to silently omit. The page must also still walk
    # the hole once each, in seq order (ids run opposite, so `ORDER BY seq` is the only
    # thing it can be).
    seed(db, 3)
    db.writer.execute(_drop, {'seq': 2})
    assert (floor(db), head(db)) == (0, 3)
    assert [e.seq for e in after(db, 0)] == [1, 3]     # retained history, nothing refused
    assert [e.seq for e in after(db, 2)] == [3]
    assert after(db, 3) == []
    seen, cursor, pages = [], 0, 0
    while True:
        pages += 1
        assert pages <= 5, 'the walk never ended, stuck at cursor %d' % cursor
        page = after(db, cursor, limit=1)
        if not page:
            break
        seen += [e.seq for e in page]
        cursor = page[-1].seq
    assert seen == [1, 3] and cursor == 3


def test_t5_an_int_subclass_page_size_is_accepted(db):
    # outbox.py:57 `not isinstance(limit, int)`: the ACCEPT arm with an int subclass.
    # gaps g13 walks that arm for the cursor only, and gaps g9's accepted limits are
    # plain ints. Written as `type(limit) is not int` (the "stricter" edit this guard
    # invites next to the cursor guard g13 already protects), every page size that came
    # through an HTTP layer's `int(x)` becomes a 400 for a request that is fine.
    seed(db, 3)
    assert [e.seq for e in after(db, 0, limit=_Int(1))] == [1]
    assert [e.seq for e in after(db, 0, limit=_Int(3))] == [1, 2, 3]
    assert [e.seq for e in after(db, 0, limit=_Int(MAX))] == [1, 2, 3]


# ── error paths: damaged data in the log must fail the read, never invent an event ─


def test_t6_truncated_payload_json_aborts_the_page_and_invents_nothing(db):
    # outbox.py:50 `json.loads(r['payload'])` and the comprehension at :64. The closest
    # existing tests, gaps g14 and test_eventlog.py's replay test, only ever read a
    # payload the writer itself wrote. Wrap the loads in `try: ... except: payload={}`
    # (the "resilient" edit that keeps a page flowing past one corrupt row) and the
    # reader gets a well-formed Event whose payload was invented: the row said
    # `{"n": 2` and the answer says `{}` or `{'n': 1}` - data the log never held. The
    # whole page must fail instead (fail-closed: no partial list escapes), while a page
    # that ends before the damaged row must still read, so the refusal stays data-bound.
    seed(db, 3)                                                # rows 1..3, payloads fine
    put(db, [_row(over={'payload': '{"n": 2'})])              # row 4: truncated JSON
    with pytest.raises(json.JSONDecodeError):                  # subclass of ValueError
        after(db, 0)                          # the page that CONTAINS the damage
    assert [e.payload for e in after(db, 0, limit=3)] == [{'n': 1}] * 3   # stops before it
    with pytest.raises(json.JSONDecodeError):
        after(db, 3)                          # reached from any cursor that exposes row 4


def test_t7_a_foreign_cause_chain_is_refused_not_defaulted(db):
    # outbox.py:49 `json.loads(r['cause_chain'])`, both damage arms: text that is not
    # JSON at all, and JSON that decodes but is not event ids - the domain's check
    # (events.py:221-222) must be what refuses the second, reached through this line.
    # gaps g14 only ever stores real ULIDs. Replace the loads with `[]` (a defaulted
    # chain is silently rewritten provenance: the audit trail says "caused by nothing")
    # and both assertions below fail, because an Event comes back where a read raises.
    put(db, [_row(over={'cause_chain': 'not json {'})])                # seq 1: not JSON
    with pytest.raises(json.JSONDecodeError):
        after(db, 0)
    put(db, [_row(over={'cause_chain': '["nope"]'})])                  # seq 2: foreign ids
    with pytest.raises(ValueError, match='cause_chain holds event ids'):
        after(db, 1)                          # only the second row is in this page


def test_t8_an_unregistered_event_type_cannot_be_read_as_an_event(db):
    # outbox.py:44-50 handing the row to Event: a log restored from a newer build can
    # hold a type this REGISTRY never declared, and events.py:204-205 must refuse it on
    # the read. The closest existing test, gaps g14, only decodes registered types; make
    # `decode` paper over the type (default it, or swallow the domain's ValueError) and
    # the reader gets an invented event - same seq, wrong facts - where it must get a
    # hard failure, and this test's raise becomes a returned list.
    seed(db, 1)
    put(db, [_row(over={'type': 'quantum.tunneled'})])
    assert [e.type for e in after(db, 0, limit=1)] == ['mission.created']
    with pytest.raises(ValueError, match='unregistered event type'):
        after(db, 1)


@pytest.mark.parametrize('damage, exc', [
    (lambda r: r.update(payload=None), TypeError),             # column present, value NULL
    (lambda r: r.pop('cause_chain'), (KeyError, IndexError)),  # column absent (corrupt dump)
], ids=['null-payload', 'missing-cause-chain'])
def test_t9_a_null_or_missing_column_fails_the_read_rather_than_fabricates(damage, exc):
    # outbox.py:44-50, the two ways a row can be missing data the envelope needs. The
    # real schema is NOT NULL (0001_init.sql:77-90), so only a seam can present a NULL
    # - which is the point: `decode` is called with whatever a connection hands it and
    # must neither invent `{}` for a NULL payload (json.loads(None) raising TypeError
    # is the fail-closed answer; `r['payload'] or 'null'` would fabricate an empty
    # object) nor shrug at an absent column (`r.get(col, '[]')` would invent a chain of
    # nothing). The page query ran (the row was offered); nothing else did.
    row = _stored(1)[0]
    damage(row)
    conn = _Spy([row], head=1)
    with pytest.raises(exc):
        outbox.events_after(conn, 0)
    assert [s for s, _ in conn.calls if 'seq > ?' in s]          # the row WAS offered
    assert len(conn.calls) == 3, conn.calls                      # bounds + page, nothing more
    assert all(s.lstrip().upper().startswith('SELECT') for s, _ in conn.calls)


def test_t10_a_stored_null_payload_is_refused_not_fabricated_as_an_empty_object(db):
    # The probe "malformed event JSON cannot invent data", pushed to the one case the
    # current source lets through: payload text `null` is valid JSON, decodes to None,
    # and is silently laundered into a plausible empty payload - the reader cannot tell
    # this event from one that genuinely had no payload. Fail-closed says refuse; see
    # the reason for the exact defect and lines. The assertion is NOT weakened: this
    # must start passing (and then XPASS against the strict marker) when the source
    # refuses.
    put(db, [_row(over={'payload': 'null'})])
    with pytest.raises(ValueError):
        after(db, 0)
