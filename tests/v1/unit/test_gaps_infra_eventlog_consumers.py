"""Gap tests for `archeus/infra/eventlog/consumers.py` (T-761): the outbox
consumer contract — the effect-before-cursor ordering, the failure and `Hold`
boundaries, the effects-table dedupe that makes a crash repeat nothing, the
cursor upsert, and the retention boundary a consumer must fail closed on.

Style and fixtures follow `tests/v1/integration/test_eventlog.py`, the closest
existing tests of this module (`test_cwrite.py` supplies the injected-failure and
`Hold` idioms); its `db`, `actor` and `new_mission` fixtures are copied here
because `tests/v1/unit` has no conftest of its own. Everything runs on the real
`Database` under the per-test `ARCHEUS_HOME` — no OS calls, no network, no
sleeps, no threads except the writer thread the `Database` itself starts, no
file names or paths with platform meaning, no assertion on OS error text. The
only injected failures are the module-level seams (`_record_effect`, `_advance`)
that the existing tests already monkeypatch.

Every test names in its docstring the source branch (`consumers.py` line) whose
removal or inversion it would catch; the companion list is in
`/work/QWEN-DONE-T-761.md`.
"""

import contextlib
import datetime as dt

import pytest

from archeus.core.domain import events as ev
from archeus.core.domain import ids
from archeus.core.domain.values import Ref
from archeus.infra.db import Database
from archeus.infra.eventlog import consumers, outbox, retention

OLD = '2000-01-01T00:00:00.000Z'


# ── fixtures (copied from tests/v1/integration/conftest.py) ──

@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def actor():
    return Ref('user_device', ids.new_id('principal'))


@pytest.fixture
def new_mission(db, actor):
    from archeus.core.application import commands

    def make(title='M'):
        return db.writer.execute(commands.create_mission,
                                 {'actor': actor, 'title': title, 'objective': 'o'})
    return make


# ── helpers ──

def _cursor(db, name):
    with db.read() as r:
        return consumers.cursor(r, name)


def _effects(db, name):
    """`consumer_effects` as `[(event_seq, result)]`, oldest first."""
    with db.read() as r:
        return [tuple(x) for x in r.execute(
            'SELECT event_seq, result FROM consumer_effects WHERE consumer = ? '
            'ORDER BY event_seq', (name,)).fetchall()]


def _cursors(db, name):
    with db.read() as r:
        return [tuple(x) for x in r.execute(
            'SELECT name, last_seq, updated_at FROM consumer_cursors WHERE name = ? '
            'ORDER BY last_seq', (name,)).fetchall()]


def _seed_cursor(tx, *, name, last_seq, at):
    """A cursor row as it was left by an earlier process (test-side seed only)."""
    tx.execute('INSERT INTO consumer_cursors (name, last_seq, updated_at) VALUES (?, ?, ?)',
               (name, last_seq, at))


def _later(days):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=days)).isoformat().replace(
        '+00:00', 'Z')


class _Shown:
    """Truth-y, not a `str`: only `str(result)` can put it in a TEXT column."""

    def __str__(self):
        return 'R7'


# ── fail-closed: what must never be recorded, skipped or swallowed ──

def test_an_effect_that_cannot_be_written_leaves_the_cursor_behind(db, new_mission,
                                                                   monkeypatch):
    """consumers.py:63-65 — `_record_effect` is submitted BEFORE `_advance`, and
    neither is wrapped: if the order were inverted, or an effect failure were
    swallowed, the cursor would pass an event whose effect was never recorded and
    that event would be lost (at-most-once instead of at-least-once)."""
    made = [new_mission()['seq'] for _ in range(3)]

    def refuse(tx, **kw):
        raise OSError('injected: effect write refused')

    real = consumers._record_effect
    monkeypatch.setattr(consumers, '_record_effect', refuse)
    with pytest.raises(OSError, match='effect write refused'):
        consumers.deliver(db, 'c', lambda e: 'ok')
    monkeypatch.setattr(consumers, '_record_effect', real)
    assert _cursor(db, 'c') == 0 and _effects(db, 'c') == []      # nothing moved past
    calls = []                                                    # and nothing was lost
    assert consumers.deliver(db, 'c', lambda e: calls.append(e.seq) or 'ok') == 3
    assert calls == made and _cursor(db, 'c') == made[-1]


def test_a_handler_that_raises_mid_batch_records_and_advances_nothing_after_it(db, new_mission):
    """consumers.py:57-62 — a raise that is not a `Hold` propagates out of the loop
    with no effect row for that event: recording it anyway (or advancing past it)
    turns a bug in one handler into a permanently skipped event."""
    made = [new_mission()['seq'] for _ in range(4)]
    ambient = ev.CAUSE.get()                                      # whatever the suite left set
    calls = []

    def handler(e):
        calls.append(e.seq)
        if e.seq == made[2]:
            raise ValueError('injected: handler bug')
        return 'ok'

    with pytest.raises(ValueError, match='handler bug'):
        consumers.deliver(db, 'c', handler)
    assert calls == made[:3]                                      # 1, 2 ok; 3 raised; 4 unseen
    assert _cursor(db, 'c') == made[1]
    assert [s for s, _r in _effects(db, 'c')] == made[:2]         # the raising one is absent
    assert ev.CAUSE.get() == ambient                              # consumers.py:62 (finally)
    assert consumers.deliver(db, 'c', lambda e: 'ok') == 2        # resumes AT the raised one
    assert _cursor(db, 'c') == made[-1]


def test_a_hold_stops_the_batch_and_nothing_after_it_overtakes(db, new_mission):
    """consumers.py:59-60 — `except Hold: return n`: returning `n + 1` or continuing
    the loop would let a later event overtake the held one, and recording the held
    event's effect would answer for it forever, so it would never be handled."""
    made = [new_mission()['seq'] for _ in range(4)]
    calls = []

    def handler(e):
        calls.append(e.seq)
        if e.seq == made[1]:
            raise consumers.Hold()
        return 'ok'

    assert consumers.deliver(db, 'hold', handler) == 1            # n, not n + 1
    assert calls == made[:2]                                      # 3 and 4 were never offered
    assert _cursor(db, 'hold') == made[0]                         # stays at the last delivered
    assert [s for s, _r in _effects(db, 'hold')] == [made[0]]     # the held one recorded nothing
    assert consumers.deliver(db, 'hold', lambda e: 'ok') == 3     # a later pass, same order
    assert _cursor(db, 'hold') == made[-1]


def test_another_consumers_effects_do_not_answer_for_this_one(db, new_mission):
    """consumers.py:51-53 — `WHERE consumer = ?`: drop the filter and another
    consumer's effects table silences this consumer's handler while its own cursor
    still moves past the event: the side effect never happens and nothing reports it."""
    made = [new_mission()['seq'] for _ in range(3)]
    for s in made:
        db.writer.execute(consumers._record_effect, {'name': 'other', 'seq': s, 'result': 'x'})
    mine = []
    assert consumers.deliver(db, 'mine', lambda e: mine.append(e.seq) or 'done') == 3
    assert mine == made                                           # not silenced by 'other'
    assert [s for s, r_ in _effects(db, 'mine')] == made
    assert _effects(db, 'other') == [(s, 'x') for s in made]      # and not overwritten either
    other = []                                                    # its own rows DO answer for it
    assert consumers.deliver(db, 'other', lambda e: other.append(e.seq)) == 3
    assert other == [] and _cursor(db, 'other') == made[-1]


def test_a_second_effect_for_the_same_event_keeps_the_first_result(db):
    """consumers.py:34 — `INSERT OR IGNORE`: without `OR IGNORE` a re-delivery dies
    on the `PRIMARY KEY (consumer, event_seq)`; with `REPLACE` the retry would
    overwrite the record of what actually happened with what it claims now."""
    db.writer.execute(consumers._record_effect, {'name': 'c', 'seq': 1, 'result': 'sent'})
    db.writer.execute(consumers._record_effect, {'name': 'c', 'seq': 1, 'result': 'ignored'})
    db.writer.execute(consumers._record_effect, {'name': 'c', 'seq': 2, 'result': 'sent'})
    assert _effects(db, 'c') == [(1, 'sent'), (2, 'sent')]


def test_a_handlers_result_is_recorded_as_text_never_as_null(db, new_mission):
    """consumers.py:64 — `str(result or '')`: without `or ''` a `None` result is
    stored as `'None'` (an audit row that lies), and without `str()` a non-`str`
    result dies on the `NOT NULL` TEXT column — a handler that returns an object
    would break delivery for every event behind it."""
    made = [new_mission()['seq'] for _ in range(6)]
    results = iter([None, 0, False, '', 7, _Shown()])
    assert consumers.deliver(db, 'c', lambda e: next(results)) == 6
    got = _effects(db, 'c')
    assert [s for s, _r in got] == made
    assert [r_ for _s, r_ in got] == ['', '', '', '', '7', 'R7']
    assert all(isinstance(r_, str) for _s, r_ in got)


# ── boundary values ──

def test_a_consumer_that_never_ran_is_read_from_zero_and_replays_the_log(db, new_mission):
    """consumers.py:30 — `r[0] if r else 0`: a missing cursor row must read as 0 so
    a new consumer sees history; read it as `head` instead and a freshly added
    consumer starts at the end of the log and never sees a back-log."""
    made = [new_mission()['seq'] for _ in range(3)]
    with db.read() as r:
        assert consumers.cursor(r, 'fresh') == 0
        assert consumers.cursor(r, 'also unknown') == 0
    calls = []
    assert consumers.deliver(db, 'fresh', lambda e: calls.append(e.seq) or 'done') == 3
    assert calls == made and _cursor(db, 'fresh') == made[-1]


def test_an_event_whose_effect_is_recorded_is_not_re_run_but_still_moves_the_cursor(
        db, new_mission):
    """consumers.py:55 + 65 — the crash-after-the-effect stand-in, twice: the effect
    of the MIDDLE event exists and of the LAST event exists, the cursor is still 0
    both times. Remove `if event.seq not in done` and the side effect runs twice;
    move `_advance` inside that branch and a pass that ENDS on an already-recorded
    event leaves the cursor below an event it can never record again — it re-reads
    that page forever."""
    made = [new_mission()['seq'] for _ in range(3)]
    db.writer.execute(consumers._record_effect, {'name': 'mid', 'seq': made[1], 'result': 'first'})
    calls = []
    assert consumers.deliver(db, 'mid', lambda e: calls.append(e.seq) or 'again') == 3
    assert calls == [made[0], made[2]]                            # 2 answered for itself
    assert _cursor(db, 'mid') == made[-1]                         # and the cursor caught up
    assert _effects(db, 'mid') == [(made[0], 'again'), (made[1], 'first'), (made[2], 'again')]
    db.writer.execute(consumers._record_effect,
                      {'name': 'last', 'seq': made[2], 'result': 'first'})
    late = []                                                     # the pass ENDS on the skip
    assert consumers.deliver(db, 'last', lambda e: late.append(e.seq) or 'again') == 3
    assert late == made[:2] and _cursor(db, 'last') == made[2]    # nothing stranded behind
    assert consumers.deliver(db, 'last', lambda e: 'never') == 0


def test_a_batch_that_was_already_delivered_moves_the_cursor_and_runs_no_handler(db, new_mission):
    """consumers.py:54-66 — every event skipped and nothing run: the pass must still
    return `len(batch)` (consumers.py:66) and still advance every one of them. Return
    `n`/`0` for an all-skipped batch, or advance only the run events, and the consumer
    re-reads the same page forever."""
    made = [new_mission()['seq'] for _ in range(3)]
    for s in made:
        db.writer.execute(consumers._record_effect, {'name': 'c', 'seq': s, 'result': 'earlier'})
    calls = []
    assert consumers.deliver(db, 'c', lambda e: calls.append(e.seq)) == 3
    assert calls == [] and _cursor(db, 'c') == made[-1]
    assert consumers.deliver(db, 'c', lambda e: 'never') == 0     # caught up: an empty batch


def test_the_page_limit_reaches_the_outbox_unchanged(db, new_mission):
    """consumers.py:48-50 + 66 — paging: a pass delivers exactly `limit` events and
    the remainder on the next pass. Ignore the limit (or return `len(batch)` for a
    page that was cut) and the return value stops meaning "the cursor moved past
    these", so a caller's backlog bookkeeping is wrong in both directions."""
    made = [new_mission()['seq'] for _ in range(5)]
    calls = []

    def page(n):
        return consumers.deliver(db, 'paged', lambda e: calls.append(e.seq) or 'ok', limit=n)

    assert page(2) == 2 and calls == made[:2] and _cursor(db, 'paged') == made[1]
    assert page(2) == 2 and calls == made[:4] and _cursor(db, 'paged') == made[3]
    assert page(2) == 1 and calls == made and _cursor(db, 'paged') == made[-1]
    assert page(2) == 0


def test_the_default_page_is_a_hundred_and_the_hundred_first_are_delivered(db, new_mission):
    """consumers.py:45 (`limit=100`) — the default boundary: 101 events must yield
    100 then 1. A default of 0 or `None` here is a consumer that reports "delivered"
    without reading anything, and a default above `outbox.MAX_LIMIT` is a
    `ValueError` out of `events_after` on every pass."""
    made = [new_mission()['seq'] for _ in range(101)]
    calls = []
    assert consumers.deliver(db, 'big', lambda e: calls.append(e.seq) or 'ok') == 100
    assert calls == made[:100] and _cursor(db, 'big') == made[99]
    assert consumers.deliver(db, 'big', lambda e: calls.append(e.seq) or 'ok') == 1
    assert calls == made and _cursor(db, 'big') == made[-1]


@pytest.mark.parametrize('limit', [0, True, outbox.MAX_LIMIT + 1])
def test_a_malformed_limit_is_still_a_value_error_out_of_deliver(db, new_mission, limit):
    """consumers.py:50 — `deliver` catches nothing: swallowing the `limit` guard
    from `outbox.events_after` (outbox.py:59) as "nothing to deliver" is a caller
    bug turned into a consumer that reports success and never advances."""
    new_mission()
    with pytest.raises(ValueError, match='limit'):
        consumers.deliver(db, 'c', lambda e: pytest.fail('nothing may be delivered'),
                          limit=limit)


def test_an_advance_inserts_once_never_rewinds_and_refreshes_updated_at(db):
    """consumers.py:38-42 — the cursor upsert: `ON CONFLICT` must take
    `MAX(last_seq, excluded.last_seq)` so an out-of-date advance from a stale pass
    cannot rewind a live cursor (a rewind re-delivered history), must keep exactly
    ONE row for the name, and must set `updated_at = excluded.updated_at` or a live
    consumer keeps reporting the time it first started."""
    db.writer.execute(_seed_cursor, {'name': 'c', 'last_seq': 9, 'at': OLD})
    db.writer.execute(consumers._advance, {'name': 'c', 'seq': 4})       # stale: must not rewind
    assert _cursor(db, 'c') == 9
    db.writer.execute(consumers._advance, {'name': 'c', 'seq': 12})      # forward: it does
    assert _cursor(db, 'c') == 12
    rows = _cursors(db, 'c')
    assert len(rows) == 1 and rows[0][:2] == ('c', 12)                   # exactly one row
    assert rows[0][2] != OLD and rows[0][2].endswith('Z')                # refreshed, not seeded


# ── error paths that must reach the caller ──

def test_a_cursor_the_log_cannot_honour_raises_out_of_deliver(db, new_mission):
    """consumers.py:49 — `events_after` raises `CursorExpired` and `deliver` does
    not catch it. Return `0` instead of raising and a consumer sitting behind a
    cursor this database never assigned reads as "caught up" and waits forever."""
    made = [new_mission()['seq'] for _ in range(2)]
    ahead = made[-1] + 5
    db.writer.execute(consumers._advance, {'name': 'c', 'seq': ahead})
    with pytest.raises(outbox.CursorExpired) as err:
        consumers.deliver(db, 'c', lambda e: pytest.fail('nothing may be delivered'))
    assert (err.value.reason, err.value.cursor) == ('ahead', ahead)
    assert _cursor(db, 'c') == ahead                                  # the failed pass changed


def test_a_consumer_the_log_was_pruned_under_fails_closed(db, new_mission):
    """retention.py:31-33 + consumers.py:49 — `MIN(last_seq) FROM consumer_cursors`
    protects only consumers that already HAVE a row: one that never advanced is left
    behind by the prune, so its first pass must be the fail-closed `pruned` error, not
    a batch that silently skips the deleted prefix."""
    made = [new_mission()['seq'] for _ in range(3)]
    assert consumers.deliver(db, 'keeper', lambda e: 'ok') == 3       # the row retention sees
    got = db.writer.execute(retention.prune, {'now': _later(365)})
    assert (got['events'], got['through']) == (3, made[-1])
    assert consumers.deliver(db, 'keeper', lambda e: 'ok') == 0       # at the floor: caught up
    with pytest.raises(outbox.CursorExpired) as err:
        consumers.deliver(db, 'late', lambda e: pytest.fail('a gap must never be delivered past'))
    assert (err.value.reason, err.value.cursor, err.value.floor) == ('pruned', 0, made[-1])
    assert _cursor(db, 'late') == 0                                   # and it stays at 0


# ── one snapshot for the reads, the writes outside it, in the right order ──

def test_the_batch_is_read_in_one_snapshot_and_written_after_it_closes(db, new_mission):
    """consumers.py:48-65 — the three reads (cursor, `events_after`, effects) come
    from ONE `db.read()` snapshot and every writer command is submitted after it
    closes. Split the reads and the batch, the cursor and the effects table can come
    from different commits; write inside the read transaction and the handler's side
    effect is inside a transaction, which is exactly what the module promises it is
    not (docstring lines 3-4)."""
    made = [new_mission()['seq'] for _ in range(3)]
    reads, writes, state = [], [], {'open': False}

    class SpyWriter:
        def __init__(self, real):
            self._real = real

        def execute(self, command, kwargs=None, **kw):
            writes.append((command.__qualname__, state['open']))
            return self._real.execute(command, kwargs, **kw)

    class Spy:
        """The two attributes `deliver` touches on the database, nothing else."""

        def __init__(self, real):
            self._real = real
            self.writer = SpyWriter(real.writer)

        @contextlib.contextmanager
        def read(self):
            with self._real.read() as conn:
                reads.append(conn)
                state['open'] = True
                try:
                    yield conn
                finally:
                    state['open'] = False

    assert consumers.deliver(Spy(db), 'snap', lambda e: 'ok') == 3
    assert len(reads) == 1                                        # one snapshot for all 3 reads
    assert [w[1] for w in writes] == [False] * len(writes)         # nothing written inside it
    assert [w[0] for w in writes] == [                              # effect, then cursor, per event
        '_record_effect', '_advance',
        '_record_effect', '_advance',
        '_record_effect', '_advance']
    assert _cursor(db, 'snap') == made[-1] and len(_effects(db, 'snap')) == 3


def test_the_handler_sees_its_event_as_the_cause_and_the_callers_cause_survives(db, new_mission):
    """consumers.py:56 + 62 — `CAUSE.set(ev.caused_by(event))` and the reset in
    `finally`: without the set, everything the handler writes is attributed to
    nothing; without the `finally` the consumer's cause leaks into the caller's
    context — and a ContextVar leaked in a test thread outlives the test."""
    ambient = ev.CAUSE.get()
    m = new_mission()
    with db.read() as r:
        (event,) = outbox.events_after(r, 0)
    assert event.seq == m['seq'] and event.cause_chain == ()

    seen = []

    def held(e):
        seen.append(ev.CAUSE.get())
        raise consumers.Hold()

    def boom(e):
        raise RuntimeError('injected: bug after the set')

    outer = (ids.new_ulid(),)
    token = ev.CAUSE.set(outer)                             # the caller is itself a consumer
    try:
        assert consumers.deliver(db, 'cause', held) == 0
        assert seen == [(event.id,)]                         # consumers.py:56 — the event is the
        assert ev.CAUSE.get() == outer                       # cause; consumers.py:62 restores
        with pytest.raises(RuntimeError, match='bug after the set'):
            consumers.deliver(db, 'cause-raise', boom)
        assert ev.CAUSE.get() == outer                       # the raise path restores it too
    finally:
        ev.CAUSE.reset(token)
    assert ev.CAUSE.get() == ambient                              # nothing left for the next test