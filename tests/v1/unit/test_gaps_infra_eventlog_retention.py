"""T-763: the highest-risk uncovered branches of archeus/infra/eventlog/retention.py.

`prune` is a prefix delete plus a clamp, and both halves carry the log: what is
left must stay contiguous above `outbox.floor()` (a cursor below it is a
`410 cursor_expired`, never a silent gap), and it may never pass a consumer that
has not got there yet. tests/v1/integration/test_eventlog.py covers one shape of
each; this file sits on the branches it does not reach — the window's inclusive
edge, `min()` in both directions, the empty and the fully-pruned log, effects and
idempotency keys at their exact expiry, the clock `now=None` reads, and the
consumer a crash left with effects but no cursor row.

Fixtures and style follow the module's own tests (tests/v1/integration/
test_eventlog.py: `db`, `new_mission`, the injected `_advance` crash) and the
in-process `Database.open()` rig of tests/v1/unit/test_gaps_core_context_assemble.py.
No process, no network, no model, no sleep, no OS call: every instant is either
pinned by the test or comes from the seams the module itself uses.
"""

from datetime import datetime, timedelta, timezone

import pytest

from archeus.core.domain import ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database
from archeus.infra.eventlog import consumers, outbox, retention
from archeus.infra.eventlog.outbox import CursorExpired

NOW = datetime(2035, 6, 1, 12, 0, 0, tzinfo=timezone.utc)      # far from any machine's clock
ACTOR = Ref('user_device', ids.new_id('principal'))
DAY = timedelta(days=1)
MS = timedelta(milliseconds=1)


@pytest.fixture
def db():
    d = Database.open()               # ARCHEUS_HOME is the test's own (tests/v1/conftest.py)
    yield d
    d.close()


# ── seeding and reading, through the module's own seams ──

def _z(dt):
    """The envelope's `at` format (events.now_iso): UTC, milliseconds, `Z`."""
    return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _event(db, at):
    """Append one event whose `at` the test chooses; the writer assigns its seq."""
    def stamp(tx, **_):
        return tx.append(new_event('mission.created', Ref('mission', ids.new_id('mission')),
                                   ACTOR, at=at)).seq
    return db.writer.execute(stamp, {})


def _events(db, *ats):
    return [_event(db, at) for at in ats]


def _advance(db, name, seq):
    db.writer.execute(consumers._advance, {'name': name, 'seq': seq})


def _effect(db, name, seq):
    db.writer.execute(consumers._record_effect, {'name': name, 'seq': seq, 'result': 'ok'})


def _key(db, key, created_at):
    """A key row exactly as `_one` records it (writer.py:447-450), with the `created_at`
    the clock of that moment wrote (`ev.now_iso()`), which the test pins instead."""
    def put(tx, **_):
        tx.execute('INSERT INTO idempotency_keys (key, command, actor, request_hash, response,'
                   ' created_at) VALUES (?, ?, ?, ?, ?, ?)',
                   (key, 'test.cmd', ACTOR.id, 'hash', '"ok"', created_at))
    db.writer.execute(put, {})


def _seqs(db):
    with db.read() as r:
        return [x[0] for x in r.execute('SELECT seq FROM events ORDER BY seq')]


def _effects(db, name):
    with db.read() as r:
        return [x[0] for x in r.execute('SELECT event_seq FROM consumer_effects'
                                        ' WHERE consumer = ? ORDER BY event_seq', (name,))]


def _keys(db):
    with db.read() as r:
        return sorted(x[0] for x in r.execute('SELECT key FROM idempotency_keys'))


def _head(db):
    with db.read() as r:
        return outbox.head(r)


def _floor(db):
    with db.read() as r:
        return outbox.floor(r)


def _cursor(db, name):
    with db.read() as r:
        return consumers.cursor(r, name)


def _replay(db, cursor):
    with db.read() as r:
        return [e.seq for e in outbox.events_after(r, cursor)]


def _prune(db, **kw):
    return db.writer.execute(retention.prune, kw)


class _PinnedClock:
    """`retention.datetime` with the machine taken out of it: `now()` answers this, and
    `fromisoformat` is the real one, so a `now=` argument still parses as it would in
    the product."""

    def __init__(self, instant):
        self.instant = instant
        self.reads = 0

    def now(self, tz):
        self.reads += 1
        return self.instant

    def fromisoformat(self, text):
        return datetime.fromisoformat(text)


# ── 1. the window boundary (retention.py:22-24) ──

def test_an_event_sitting_exactly_on_the_cutoff_is_the_first_one_kept(db):
    """`WHERE at >= ?` (retention.py:23) is inclusive: the event whose `at` IS the cutoff
    is `first_kept`, so `through` stops one below it. Inverting `>=` to `>` deletes an
    event that is inside the window, and the reported `through` moves up by one."""
    cutoff = NOW - timedelta(days=180)
    first, edge, last = _events(db, _z(cutoff - MS), _z(cutoff), _z(cutoff + MS))
    got = _prune(db, now=_z(NOW), keep_days=180)
    assert (first, edge, last) == (1, 2, 3)
    assert (got['events'], got['through']) == (1, 1)
    assert _seqs(db) == [2, 3]
    assert _floor(db) == 1 and _head(db) == 3


def test_prune_removes_a_prefix_and_leaves_the_log_contiguous_above_its_floor(db):
    """`through = first_kept - 1` and `DELETE ... WHERE seq <= ?` (retention.py:24, 28):
    everything below the first kept event goes and nothing else does. Off-by-one either
    way leaves a hole under a cursor that still replays, which is the silent gap the
    module's docstring promises never to create."""
    old, new = NOW - timedelta(days=200), NOW - timedelta(days=1)
    _events(db, _z(old), _z(old), _z(old), _z(new), _z(new))
    got = _prune(db, now=_z(NOW), keep_days=180)
    assert (got['events'], got['through']) == (3, 3)
    assert _seqs(db) == [4, 5] and _floor(db) == 3
    assert _replay(db, 3) == [4, 5]                  # the floor still replays completely
    with pytest.raises(CursorExpired) as err:
        _replay(db, 2)                                # one below it is a 410, not a gap
    assert (err.value.reason, err.value.floor, err.value.head) == ('pruned', 3, 5)


def test_a_backdated_event_is_never_left_behind_as_a_gap(db):
    """The prefix is cut by `seq`, not by `at` (retention.py:28): `at` picks `first_kept`
    and `seq` picks what goes. Delete by `at` instead and the backdated seq 3 below goes
    too, leaving 1..4 with a hole the reader cannot see — `events_after(1)` would answer
    [2, 4] as if that were the whole history."""
    _events(db, _z(NOW - timedelta(days=200)), _z(NOW - MS), _z(NOW - timedelta(days=365)),
            _z(NOW - MS))
    got = _prune(db, now=_z(NOW), keep_days=180)
    assert (got['events'], got['through']) == (1, 1)
    assert _seqs(db) == list(range(got['through'] + 1, _head(db) + 1)) == [2, 3, 4]
    assert _replay(db, 1) == [2, 3, 4]
    with pytest.raises(CursorExpired):
        _replay(db, 0)


# ── 2. the log with nothing (or nothing left) inside the window (retention.py:24) ──

def test_prune_of_a_log_with_nothing_inside_the_window_goes_through_the_head(db):
    """`first_kept is None` (retention.py:24) takes `outbox.head(tx.conn)`, never 0 and
    never `MIN(seq)`: the log is emptied up to the highest seq ever assigned, so
    `floor()` says "everything below the head is gone" and a lagging cursor is refused
    rather than told the log ended where the surviving rows do."""
    old = _z(NOW - timedelta(days=200))
    _events(db, old, old, old)
    head = _head(db)
    assert _prune(db, now=_z(NOW), keep_days=180) == {'events': 3, 'through': head,
                                                      'idempotency_keys': 0}
    assert _seqs(db) == [] and _floor(db) == head == 3 and _head(db) == head
    assert _replay(db, head) == []                    # a caught-up reader is fine
    with pytest.raises(CursorExpired) as err:
        _replay(db, head - 1)
    assert (err.value.reason, err.value.floor, err.value.head) == ('pruned', 3, 3)
    assert _event(db, _z(NOW)) == head + 1            # AUTOINCREMENT: a seq is never reused


def test_prune_of_an_already_empty_log_reports_the_head_and_deletes_nothing(db):
    """Two faces of the same branch: a database that never held an event (`outbox.head`
    answers 0, outbox.py:35) and one retention already drained (`head` > 0 while
    `MIN(seq)` is NULL). Both must report `through == head` and delete no rows; a second
    prune must be a no-op, not a negative count and not a re-delete."""
    assert _prune(db, now=_z(NOW)) == {'events': 0, 'through': 0, 'idempotency_keys': 0}
    _events(db, _z(NOW - timedelta(days=200)), _z(NOW - timedelta(days=200)))
    first = _prune(db, now=_z(NOW), keep_days=180)
    assert (first['events'], first['through']) == (2, 2)
    again = _prune(db, now=_z(NOW), keep_days=180)
    assert again == {'events': 0, 'through': _head(db), 'idempotency_keys': 0}
    assert _seqs(db) == [] and _head(db) == 2


# ── 3. the consumer clamp, in both directions (retention.py:25-27) ──

def test_a_consumer_that_has_read_nothing_at_all_stops_the_prune(db):
    """`if slowest is not None` (retention.py:26) tests for NULL, not for truthiness: a
    registered consumer parked at 0 is the fail-closed case and nothing may be deleted.
    Rewrite it as `if slowest:` and `0` is read as "no consumer", so the whole log of a
    consumer that has seen nothing is pruned away."""
    old = _z(NOW - timedelta(days=200))
    _events(db, old, old, old)
    _advance(db, 'slow', 0)
    assert _prune(db, now=_z(NOW), keep_days=180) == {'events': 0, 'through': 0,
                                                      'idempotency_keys': 0}
    assert _seqs(db) == [1, 2, 3] and _cursor(db, 'slow') == 0
    assert _replay(db, 0) == [1, 2, 3]                # it still owes all three, and sees them


def test_the_slowest_of_several_consumers_holds_the_line(db):
    """`MIN(last_seq)` (retention.py:25) is the slowest consumer of the whole registry:
    with cursors at 4, 2 and 6 the line is 2. `MAX` instead of `MIN` honours the fastest
    consumer and silently starves the one at 2 out of the events it never read."""
    old = _z(NOW - timedelta(days=200))
    _events(db, old, old, old, old, old, old)
    _advance(db, 'fast', 4)
    _advance(db, 'slow', 2)
    _advance(db, 'other', 6)
    got = _prune(db, now=_z(NOW), keep_days=180)
    assert (got['events'], got['through']) == (2, 2)
    assert _seqs(db) == [3, 4, 5, 6]            # nothing the slow one owes is gone
    assert _cursor(db, 'slow') == 2


def test_a_consumer_ahead_of_the_cut_does_not_hold_the_prune_back(db):
    """The other half of `min(through, slowest)` (retention.py:27): a consumer past the
    cut must not lift `through` above the window. Take `min` out and `through` becomes
    the consumer's cursor, so a caught-up reader deletes the events the window says to
    keep — the inverse of the case test_eventlog.py pins."""
    old, new = _z(NOW - timedelta(days=200)), _z(NOW - MS)
    _events(db, old, old, new, new)
    _advance(db, 'caught-up', 4)
    got = _prune(db, now=_z(NOW), keep_days=180)
    assert (got['events'], got['through']) == (2, 2)
    assert _seqs(db) == [3, 4] and _floor(db) == 2 and _cursor(db, 'caught-up') == 4
    assert _replay(db, 2) == [3, 4]


def test_prune_clears_effects_only_up_to_its_own_cursor(db):
    """`DELETE FROM consumer_effects WHERE event_seq <= ?` (retention.py:29) uses the same
    cut as the events: an effect recorded above the cursor is the proof that keeps a
    side effect from running twice, so it must outlive every row that cannot be
    re-delivered anyway. `<` instead of `<=` keeps effects for events nobody can replay;
    a wider cut deletes the evidence for events a consumer still owes."""
    old = _z(NOW - timedelta(days=200))
    _events(db, old, old, old, old, old)
    _advance(db, 'crashy', 3)
    for seq in (1, 2, 3, 4, 5):                      # 4 and 5: done, cursor never moved
        _effect(db, 'crashy', seq)
    got = _prune(db, now=_z(NOW), keep_days=180)
    assert (got['events'], got['through']) == (3, 3)
    assert _effects(db, 'crashy') == [4, 5]
    assert _effects(db, 'untouched') == []


def test_a_lagging_consumer_is_delivered_exactly_the_surviving_tail_in_order(db):
    """The contract of the clamp from the reader's side (retention.py:26-27 with
    consumers.deliver): after a prune that stopped at its cursor, the consumer is handed
    every surviving event once, in `seq` order — it cannot be skipped by retention and it
    cannot be re-handed what it already passed."""
    old = _z(NOW - timedelta(days=200))
    made = [_event(db, old) for _ in range(6)]
    seen = []
    assert consumers.deliver(db, 'lag', lambda e: seen.append(e.seq) or 'ok', limit=2) == 2
    assert seen == made[:2] and _cursor(db, 'lag') == 2
    assert _prune(db, now=_z(NOW), keep_days=0)['through'] == 2
    assert consumers.deliver(db, 'lag', lambda e: seen.append(e.seq) or 'ok') == 4
    assert seen == made and _cursor(db, 'lag') == made[-1]
    assert _effects(db, 'lag') == [3, 4, 5, 6]        # what it passed is gone, what it owes is not


def test_prune_never_deletes_an_event_an_effects_only_consumer_still_owes(db, monkeypatch):
    """consumers.py promises that a crash between the effect and the cursor advance
    re-delivers the event without re-running the handler — which needs the event to still
    be there. The clamp reads `MIN(last_seq) FROM consumer_cursors` (retention.py:25) and
    knows nothing about `consumer_effects`, so this consumer (effects, cursor 0 because no
    row was ever written) is not counted and retention drains what it has not seen: the
    event is never delivered and never re-delivered, which is a skipped event."""
    made = [_event(db, _z(NOW - timedelta(days=3) + timedelta(seconds=i))) for i in range(3)]
    calls = []
    real = consumers._advance

    def crash(tx, **kw):
        raise OSError('injected: died after the effect, before the cursor')
    monkeypatch.setattr(consumers, '_advance', crash)
    with pytest.raises(OSError, match='before the cursor'):
        consumers.deliver(db, 'owed', lambda e: calls.append(e.seq) or 'ok')
    monkeypatch.setattr(consumers, '_advance', real)
    with db.read() as r:
        assert consumers.cursor(r, 'owed') == 0       # exactly what a real crash leaves
        owed = [x[0] for x in r.execute('SELECT event_seq FROM consumer_effects'
                                        " WHERE consumer = 'owed' ORDER BY event_seq")]
    assert owed == made[:1]
    assert _prune(db, now=_z(NOW), keep_days=0)['through'] < min(owed)
    assert _seqs(db) == made
    assert consumers.deliver(db, 'owed', lambda e: calls.append(e.seq) or 'ok') == 3
    assert calls == made                              # at-least-once, never skipped


# ── 4. idempotency keys (retention.py:30-31) ──

def test_a_key_is_kept_until_the_ttl_has_actually_run_out(db):
    """`WHERE created_at < iso(now - IDEMPOTENCY_TTL)` (retention.py:30-31) is strict,
    matching `Writer._recall` (writer.py:472): a key at exactly the boundary is still
    replayable, so deleting it lets the same command run twice. `<=` here expires a live
    key and turns a retry into a second effect."""
    keep = _z(NOW - retention.IDEMPOTENCY_TTL)
    gone = _z(NOW - retention.IDEMPOTENCY_TTL - MS)
    _key(db, 'edge', keep)
    _key(db, 'expired', gone)
    _key(db, 'fresh', _z(NOW))
    got = _prune(db, now=_z(NOW), keep_days=retention.EVENT_DAYS)
    assert got['idempotency_keys'] == 1
    assert _keys(db) == ['edge', 'fresh']


def test_the_key_cutoff_follows_the_now_argument_not_the_machine(db):
    """The expiry instant is derived from the same `now` as the event window
    (retention.py:21, 30-31), never from a second reading of the clock: one prune sees one
    instant. Read `datetime.now()` separately here and a `now=` from the past (a replayed
    prune, a clock step back) would expire keys the caller has not aged at all."""
    _key(db, 'old', _z(NOW - timedelta(hours=25)))
    _key(db, 'young', _z(NOW - timedelta(hours=23)))
    _key(db, 'newest', _z(NOW))
    assert _prune(db, now=_z(NOW))['idempotency_keys'] == 1
    assert _keys(db) == ['newest', 'young']
    assert _prune(db, now=_z(NOW - timedelta(hours=2)))['idempotency_keys'] == 0
    assert _keys(db) == ['newest', 'young']           # nothing was aged past 24 h by this call


def test_prune_appends_no_event_and_is_never_an_unrecorded_mutation(db):
    """Retention deletes through `tx.execute`, the raw-SQL door (writer.py:135-137), so it
    never sets `tx.mutated` and the writer's `UnrecordedMutation` gate (writer.py:442-443)
    must not fire; and it must not append an event of its own, which would move the head
    a reader is entitled to walk back over. Have either happen and prune either fails
    closed forever or rewrites the history it is supposed to only shorten."""
    old = _z(NOW - timedelta(days=200))
    _events(db, old, old)
    head = _head(db)
    with db.read() as r:
        before = r.execute('SELECT COUNT(*) FROM events').fetchone()[0]
    got = _prune(db, now=_z(NOW), keep_days=180)
    assert got['events'] == before == 2 and got['through'] == head
    assert _head(db) == head                          # no event was appended by the prune
    assert set(got) == {'events', 'through', 'idempotency_keys'}
    assert all(isinstance(v, int) and v >= 0 for v in got.values())
    assert _prune(db, now=_z(NOW), keep_days=180)['events'] == 0


# ── 5. the clock and the window it is measured against (retention.py:21-22) ──

def test_prune_without_a_now_reads_the_module_clock_and_the_default_window(db, monkeypatch):
    """`now=None` falls back to `datetime.now(timezone.utc)` and `keep_days` to
    `EVENT_DAYS` (retention.py:20-22) — the only path in the module that touches a clock,
    and the one no caller in the suite pins. The clock is read exactly once, and 180 days
    is the window: one millisecond older than it goes, exactly that age stays."""
    clock = _PinnedClock(NOW)
    monkeypatch.setattr(retention, 'datetime', clock)
    edge = NOW - timedelta(days=retention.EVENT_DAYS)
    gone, kept = _events(db, _z(edge - MS), _z(edge))
    got = _prune(db)
    assert (gone, kept) == (1, 2)
    assert got['events'] == 1 and got['through'] == gone
    assert _seqs(db) == [2]
    assert clock.reads == 1                           # the machine clock is never reached


def test_a_now_that_carries_an_offset_is_the_same_instant_as_the_same_utc_moment(db):
    """`now.replace('Z', '+00:00')` then `fromisoformat` (retention.py:21) must keep the
    offset it was handed, and `iso()` (writer.py:77-78) must render the cutoff back in
    UTC: a `+02:00` caller and a `Z` caller naming the same instant must prune the same
    prefix. Drop the offset and the window slides by hours, deleting events that are
    inside it (or keeping ones that are outside)."""
    cutoff = NOW - timedelta(days=180)
    gone, kept = _events(db, _z(cutoff - MS), _z(cutoff))
    got = _prune(db, now='2035-06-01T14:00:00+02:00', keep_days=180)     # == _z(NOW)
    assert (gone, kept) == (1, 2)
    assert (got['events'], got['through']) == (1, 1) and _seqs(db) == [2]


def test_a_now_without_a_zone_is_refused_rather_than_read_as_local_time(db):
    """Every `at` in the log is UTC with a `Z` (events.now_iso), and the cutoff is
    compared to it as text. A `now` without a zone has no meaning until something picks a
    timezone, and `iso()` picks the machine's; on a UTC+8 host `now='...12:00:00'` means
    `04:00Z`, i.e. eight hours of events past the window deleted on a caller that asked
    for none. A bare timestamp is a client error (the same shape as a malformed cursor,
    outbox.events_after:56) and must be refused, here on every platform."""
    _events(db, _z(NOW - timedelta(days=1)))
    with pytest.raises(ValueError):
        _prune(db, now='2035-06-01T12:00:00')


def test_a_negative_window_never_removes_events(db):
    """`keep_days` is subtracted unchecked (retention.py:22). A negative window asks for
    events newer than `now`, which is nothing, and the NULL `first_kept` is the branch
    that means "the window left nothing" — so the head is pruned and a whole log of
    current events is deleted by an argument that can only be a bug in the caller.
    Nothing is removed, or the call is refused; it may not silently empty the log."""
    _events(db, _z(NOW), _z(NOW - MS), _z(NOW - timedelta(days=1)))
    got = _prune(db, now=_z(NOW), keep_days=-1)
    assert got['events'] == 0 and got['through'] == 0
    assert _seqs(db) == [1, 2, 3]
