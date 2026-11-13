"""T-1151: close the remaining high-risk test gaps in
`archeus/infra/eventlog/consumers.py` lines 1-66 (the whole module; tip
56d53504 content, verified against this checkout's single baseline commit).

Coverage already held by `tests/v1/integration/test_eventlog.py`,
`tests/v1/integration/test_cwrite.py` and
`tests/v1/unit/test_gaps_infra_eventlog_consumers.py` (T-761) is NOT repeated.
The ten branches/compositions selected here, ranked by risk (evidence and the
closest existing test for each are in /work/QWEN-DONE-T-1151.md):

1. Hold on the FIRST undelivered event writes nothing at all — no effect row,
   no cursor row, zero writer submissions                 (consumers.py:57-60)
2. an EMPTY batch submits zero writes and creates no cursor row (loop runs
   zero times)                                             (consumers.py:48-54, 63-66)
3. an effect row committed DURING the pass (after the snapshot) must not
   silence that event's handler; done is the snapshot, and INSERT OR IGNORE
   keeps the first result                        (consumers.py:48-55, 63, 34)
4. a subclass of `Hold` stops the batch exactly like `Hold` (the `except Hold`
   class match)                                            (consumers.py:59-60)
5. crash at the SECOND event's `_advance`: the first event's advance stands,
   the failed event's effect answers for it on retry       (consumers.py:63-65)
6. crash at the SECOND event's `_record_effect`: cursor stays at the last
   fully delivered event, the handler runs again on retry  (consumers.py:63-64)
7. a recorded-skip followed by a Hold in ONE batch: the recorded event still
   advances, the held one stops the batch at its index     (consumers.py:55, 60, 65)
8. Hold on the LAST event of a batch returns `len(batch) - 1`, boundary of
   the two return sites                                    (consumers.py:54, 60, 66)
9. the handler's CAUSE is `ev.caused_by(event)` for an event with a NON-EMPTY
   cause chain, not just `(event.id,)`                     (consumers.py:56)
10. the effect/cursor commands are SUBMITTED after the `finally` reset, so
    they carry the caller's cause, never the event's       (consumers.py:62-65)

Fixtures follow T-761 (`db`, `actor`, `new_mission` copied here because
`tests/v1/unit` has no conftest of its own); everything runs on the real
`Database` under the per-test `ARCHEUS_HOME` — no OS seams beyond the
module-level functions (`_record_effect`, `_advance`) the existing tests
already monkeypatch, no network, no sleeps, no threads but the writer thread
`Database` itself starts. Each docstring names the source branch whose removal
or inversion it catches.
"""

import contextlib

import pytest

from archeus.core.application import commands
from archeus.core.domain import events as ev
from archeus.core.domain import ids
from archeus.core.domain.values import Ref
from archeus.infra.db import Database
from archeus.infra.eventlog import consumers


# ── fixtures (copied from tests/v1/unit/test_gaps_infra_eventlog_consumers.py) ──

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


def _cursor_rows(db, name):
    with db.read() as r:
        return [tuple(x) for x in r.execute(
            'SELECT name, last_seq, updated_at FROM consumer_cursors WHERE name = ? '
            'ORDER BY last_seq', (name,)).fetchall()]


class SpyWriter:
    """Counts submissions to the real writer, delegating everything."""

    def __init__(self, real):
        self._real = real
        self.submits = []

    def execute(self, command, kwargs=None, **kw):
        self.submits.append(command.__qualname__)
        return self._real.execute(command, kwargs, **kw)


class Spy:
    """The two attributes `deliver` touches on the database, nothing else."""

    def __init__(self, real):
        self._real = real
        self.writer = SpyWriter(real.writer)

    @contextlib.contextmanager
    def read(self):
        with self._real.read() as conn:
            yield conn


# ── fail-closed and denial first ──

def test_hold_first_event_writes_nothing_at_all(db, new_mission):
    """consumers.py:57-60 — `except Hold: return n` at n == 0 is BEFORE both
    `db.writer.execute` calls (63-65): a held FIRST event must leave no effect row,
    no cursor row at all and zero writer submissions, and nothing behind it may be
    offered. Closest existing test: `test_a_held_event_leaves_no_cause_behind`
    (test_cwrite.py) asserts only the `0` return and CAUSE; T-761's
    `test_a_hold_stops_the_batch_and_nothing_after_it_overtakes` holds at the SECOND
    event, where the first event's advance has already created the cursor row, so
    neither can see a Hold creating one. If the held event were recorded or advanced
    (or a cursor row were seeded), retention would treat this consumer as protected
    at a seq whose side effect never ran, and the event would never be delivered
    again. Catches: recording or advancing before the Hold check."""
    made = [new_mission()['seq'] for _ in range(2)]
    calls = []

    def handler(e):
        calls.append(e.seq)
        raise consumers.Hold()

    spy = Spy(db)
    assert consumers.deliver(spy, 'held1', handler) == 0
    assert calls == [made[0]]                                     # the second was never offered
    assert _effects(db, 'held1') == []
    assert _cursor_rows(db, 'held1') == []                        # not even a row at 0
    assert spy.writer.submits == []                               # nothing submitted at all
    assert consumers.deliver(db, 'held1', lambda e: 'ok') == 2    # a later pass still gets it
    assert _cursor(db, 'held1') == made[-1]


def test_empty_batch_submits_no_writes_no_cursor_row(db, new_mission):
    """consumers.py:48-54 (loop zero times) + 63-66 — an empty batch submits ZERO
    writer commands: the caught-up consumer does not even refresh `updated_at`, and
    a consumer that has never seen an event gets no cursor row. Closest existing:
    `test_a_batch_that_was_already_delivered_moves_the_cursor_and_runs_no_handler`
    (T-761) asserts only the return value and handler silence, never the absence of
    writes; the T-761 spy test observes the writer only for a non-empty batch. A
    stray `_advance` on an empty pass would create a cursor row for a consumer that
    delivered nothing: retention's `MIN(last_seq) FROM consumer_cursors` would pin
    the prune floor to it forever, and the effects/cursor audit would claim a pass
    that never touched an event. Catches: any write executed outside the batch loop
    or unconditionally per pass."""
    spy = Spy(db)
    assert consumers.deliver(spy, 'never', lambda e: pytest.fail('empty log delivers nothing')
                             ) == 0                                # empty log, cursor unknown
    assert spy.writer.submits == []
    assert _cursor_rows(db, 'never') == []                        # no row seeded for an empty pass
    assert _effects(db, 'never') == []

    made = [new_mission()['seq'] for _ in range(2)]
    assert consumers.deliver(db, 'caught', lambda e: 'ok') == 2
    before = _cursor_rows(db, 'caught')
    spy2 = Spy(db)
    assert consumers.deliver(spy2, 'caught', lambda e: pytest.fail('caught-up consumer')
                             ) == 0
    assert spy2.writer.submits == []                               # not even an advance
    assert _cursor_rows(db, 'caught') == before                    # cursor and updated_at untouched
    assert _effects(db, 'caught') == [(s, 'ok') for s in made]     # audit unchanged too


def test_effect_recorded_mid_batch_does_not_silence_its_event(db, new_mission):
    """consumers.py:48-55 + 63 — `done` is read ONCE inside the read snapshot (51-53);
    an effect row committed after that snapshot, before the loop reaches its event,
    must not silence the handler: at-least-once is judged against the snapshot the
    batch was planned from, and `INSERT OR IGNORE` (34) then keeps the earlier row
    instead of letting the second record overwrite the first. Closest existing:
    `test_the_batch_is_read_in_one_snapshot_and_written_after_it_closes` (T-761)
    never has a handler write an effect mid-pass, and
    `test_an_event_whose_effect_is_recorded_is_not_re_run_but_still_moves_the_cursor`
    seeds its rows BEFORE `deliver`. Re-querying `done` per event (or per write)
    turns a concurrent commit into a permanently skipped side effect that the log
    nonetheless reports delivered."""
    made = [new_mission()['seq'] for _ in range(3)]
    calls = []

    def handler(e):
        calls.append(e.seq)
        if e.seq == made[0]:                    # a parallel writer records event 2 mid-pass
            db.writer.execute(consumers._record_effect,
                              {'name': 'racer', 'seq': made[1], 'result': 'first-wins'})
        return 'late'

    assert consumers.deliver(db, 'racer', handler) == 3
    assert calls == made                                          # event 2 still ran its handler
    assert _effects(db, 'racer') == [(made[0], 'late'), (made[1], 'first-wins'),
                                     (made[2], 'late')]           # OR IGNORE kept the earlier row
    assert _cursor(db, 'racer') == made[-1]


def test_hold_subclass_stops_the_batch_like_hold(db, new_mission):
    """consumers.py:59 — `except Hold` matches subclasses: real consumers define
    their own `Hold` derivatives, and a handler raising one must STOP the batch
    (return n, nothing recorded or advanced for it) instead of killing the pass.
    Closest existing: T-761's `test_a_hold_stops_the_batch_and_nothing_after_it_overtakes`
    and test_cwrite's Hold tests all raise the bare class, so an exact-type match
    (`type(err) is Hold`) or a broader `except Exception: return n` passes them all.
    The subclass leaking out as a crash would lose the batch; any exception being
    treated as a Hold would silently stop delivery for a broken handler."""
    class Gate(consumers.Hold):
        """A domain consumer's own held-later exception."""

    made = [new_mission()['seq'] for _ in range(3)]
    calls = []

    def handler(e):
        calls.append(e.seq)
        if e.seq == made[1]:
            raise Gate('gate: not yet')
        return 'ok'

    assert consumers.deliver(db, 'gate', handler) == 1             # return n, not a crash
    assert calls == made[:2]                                       # event 3 never offered
    assert _cursor(db, 'gate') == made[0]
    assert _effects(db, 'gate') == [(made[0], 'ok')]               # the held event wrote nothing
    assert consumers.deliver(db, 'gate', lambda e: 'ok') == 2      # and it is delivered later
    assert _cursor(db, 'gate') == made[-1]


def test_advance_crash_at_second_event_keeps_first_and_reuses_effect(db, new_mission,
                                                                     monkeypatch):
    """consumers.py:63-65 — an `_advance` that dies at the SECOND event of a batch:
    each event's commit is its own, so the first event's advance must STAND (cursor
    at made[0], not 0), the failed event's effect row must stand, and the retry
    enters with start > 0 and that event already in `done`: its handler must NOT run
    again, yet line 65 must still advance it. Closest existing: the integration
    `test_a_crash_after_the_effect_and_before_the_cursor_repeats_nothing` crashes
    EVERY advance, so the pass dies at the first event and the retry starts from 0 —
    neither the standing first advance nor the start>0 re-entry is ever executed.
    Catches: one big transaction for the pass, or `_advance` inside the not-in-done
    branch under these exact crash coordinates."""
    made = [new_mission()['seq'] for _ in range(3)]
    calls = []
    real = consumers._advance

    def crash(tx, *, name, seq):
        if seq == made[1]:
            raise OSError('injected: advance died at the second event')
        return real(tx, name=name, seq=seq)

    monkeypatch.setattr(consumers, '_advance', crash)
    with pytest.raises(OSError, match='advance died'):
        consumers.deliver(db, 'c', lambda e: calls.append(e.seq) or 'ok')
    assert calls == made[:2]                                       # event 3 never offered
    assert _cursor(db, 'c') == made[0]                             # event 1's advance stands
    assert _effects(db, 'c') == [(made[0], 'ok'), (made[1], 'ok')]
    monkeypatch.setattr(consumers, '_advance', real)
    retry = []
    assert consumers.deliver(db, 'c', lambda e: retry.append(e.seq) or 'again') == 2
    assert retry == [made[2]]                                      # event 2's effect answered for it
    assert _effects(db, 'c') == [(made[0], 'ok'), (made[1], 'ok'), (made[2], 'again')]
    assert _cursor(db, 'c') == made[-1]


# ── boundaries ──

def test_effect_crash_at_second_event_reruns_only_that_handler(db, new_mission, monkeypatch):
    """consumers.py:63-64 — `_record_effect` dies at the SECOND event after the
    first was fully delivered: the cursor must stay at the last fully delivered
    event, the crashed event must leave NO half row, and its handler — whose
    outside-the-database side effect already ran — must run AGAIN on retry
    (at-least-once) with exactly one effect row afterwards. Closest existing:
    `test_an_effect_that_cannot_be_written_leaves_the_cursor_behind` (T-761) fails
    EVERY write so nothing at all advances, and the integration
    `test_a_crash_before_the_effect_is_recorded_redelivers` crashes the HANDLER,
    not the effect write: neither exercises a pass that had already delivered one
    event, and neither pins that the crashed event's row is absent, not partial.
    Catches: swallowing the effect-write error (cursor would pass an unrecorded
    event) or recording before the handler ran."""
    made = [new_mission()['seq'] for _ in range(3)]
    calls = []
    real = consumers._record_effect

    def crash(tx, *, name, seq, result):
        if seq == made[1]:
            raise OSError('injected: effect write died at the second event')
        return real(tx, name=name, seq=seq, result=result)

    monkeypatch.setattr(consumers, '_record_effect', crash)
    with pytest.raises(OSError, match='effect write died'):
        consumers.deliver(db, 'c', lambda e: calls.append(e.seq) or 'ok')
    assert calls == made[:2]                                       # event 2's side effect ran
    assert _cursor(db, 'c') == made[0]                             # but nothing past event 1 moved
    assert _effects(db, 'c') == [(made[0], 'ok')]                  # no row, not even a partial
    monkeypatch.setattr(consumers, '_record_effect', real)
    retry = []
    assert consumers.deliver(db, 'c', lambda e: retry.append(e.seq) or 'again') == 2
    assert retry == [made[1], made[2]]                             # at-least-once, once more each
    assert _effects(db, 'c') == [(made[0], 'ok'), (made[1], 'again'), (made[2], 'again')]
    assert _cursor(db, 'c') == made[-1]


def test_recorded_skip_then_hold_in_one_batch_stops_at_the_hold(db, new_mission):
    """consumers.py:55 + 60 + 65 in ONE batch — event 1 is already recorded (skipped,
    but STILL advanced by 65) and event 2 raises Hold: the skip's advance must stand,
    the batch must stop at the held event's INDEX (`return n` = 1, the number the
    cursor moved past), and events 3-4 must not overtake it; a later pass delivers
    them in order. Closest existing: the T-761 skip tests have no Hold and the T-761
    Hold test has no skip, so `return n` mixing up batch index with recorded-event
    counts, or an advance lost on the skipped event (advance inside the not-in-done
    branch), passes every current test. Catches: Hold returning `len(batch)`-style
    counts, or not advancing a skipped event when the pass ends early."""
    made = [new_mission()['seq'] for _ in range(4)]
    db.writer.execute(consumers._record_effect,
                      {'name': 'mix', 'seq': made[0], 'result': 'earlier'})
    calls = []

    def handler(e):
        calls.append(e.seq)
        if e.seq == made[1]:
            raise consumers.Hold()
        return 'ok'

    assert consumers.deliver(db, 'mix', handler) == 1              # n: one cursor move, the skip
    assert calls == [made[1]]                                      # events 3-4 never offered
    assert _cursor(db, 'mix') == made[0]                           # the skipped event did advance
    assert _effects(db, 'mix') == [(made[0], 'earlier')]           # the held one recorded nothing
    later = []
    assert consumers.deliver(db, 'mix', lambda e: later.append(e.seq) or 'ok') == 3
    assert later == made[1:]                                       # and order survives the hold
    assert _cursor(db, 'mix') == made[-1]


def test_hold_on_last_event_returns_the_count_before_it(db, new_mission):
    """consumers.py:54 + 60 + 66 — the boundary where the two return sites sit one
    apart: the LAST event of the batch holds, so `return n` must give `len(batch)-1`
    while a completed batch gives `len(batch)` (66). Closest existing: T-761's Hold
    test holds mid-batch (n = 1 of 4) and test_cwrite holds on the first event
    (n = 0); no current test holds at the final index, where a Hold that fell
    through to the loop-end return, or a `return n - 1` that only survives at other
    indices, misreports a backlog: a caller that keeps pulling while the return is
    non-zero would stop pulling while the held event is still pending, or pull
    forever over a recorded-but-not-held pass. Catches: Hold returning
    `len(batch)`, or recording and advancing the held final event."""
    made = [new_mission()['seq'] for _ in range(4)]
    calls = []

    def handler(e):
        calls.append(e.seq)
        if e.seq == made[-1]:
            raise consumers.Hold()
        return 'ok'

    assert consumers.deliver(db, 'last', handler) == 3             # len(batch)-1, not len(batch)
    assert calls == made                                           # the held one WAS offered
    assert _cursor(db, 'last') == made[2]                          # it is not passed
    assert _effects(db, 'last') == [(s, 'ok') for s in made[:3]]   # it recorded nothing
    assert consumers.deliver(db, 'last', lambda e: 'ok') == 1      # the retry COMPLETES: len(batch)
    assert _cursor(db, 'last') == made[-1]


# ── the cause contract at the two seams ──

def test_handler_cause_carries_the_events_whole_chain(db, new_mission):
    """consumers.py:56 — `ev.CAUSE.set(ev.caused_by(event))` for an event with a
    NON-EMPTY cause chain: the handler must see chain + the event's id, not just
    `(event.id,)`, or everything the gated handler writes is attributed as if the
    event had caused itself. Closest existing: T-761's
    `test_the_handler_sees_its_event_as_the_cause_and_the_callers_cause_survives`
    asserts `seen == [(event.id,)]` for a root mission event whose chain is empty —
    `CAUSE.set((event.id,))` passes it; test_cwrite checks what writes carry, not
    what the handler sees. Catches: dropping `caused_by`, or truncating to the id."""
    a, b = ids.new_ulid(), ids.new_ulid()
    token = ev.CAUSE.set((a, b))                                    # the trigger is itself caused
    try:
        m = new_mission('caused')
    finally:
        ev.CAUSE.reset(token)
    seen = []

    def handler(e):
        seen.append((list(e.cause_chain), ev.CAUSE.get(), e.id))
        return 'ok'

    assert consumers.deliver(db, 'chain', handler) == 1
    assert seen == [([a, b], (a, b, seen[0][2]), seen[0][2])]      # chain first, then the event
    assert ev.CAUSE.get() == ()                                    # and nothing leaked out


def test_writes_submit_under_the_callers_cause_not_the_events(db, new_mission, monkeypatch):
    """consumers.py:62-65 — the `finally: ev.CAUSE.reset(cause)` runs BEFORE the
    effect and cursor commands are submitted, so what the writer captures at submit
    time (`tx.cause`, writer.py submit) is the CALLER's ambient cause, never the
    event's. Closest existing: test_cwrite's `test_a_consumer_writes_under_its_event_and_leaves_no_cause_behind`
    observes the handler's writes and the ambient value only AFTER deliver returned;
    it cannot see what the two infrastructure submissions carried. Moving the reset
    after the executes (or recording inside the try) would stamp the effect/cursor
    commands with the event cause — misattributing infrastructure audit rows."""
    made = [new_mission()['seq'] for _ in range(2)]
    captured, seen = [], []
    real_rec, real_adv = consumers._record_effect, consumers._advance

    def spy_record(tx, *, name, seq, result):
        captured.append(('record', tx.cause))
        return real_rec(tx, name=name, seq=seq, result=result)

    def spy_advance(tx, *, name, seq):
        captured.append(('advance', tx.cause))
        return real_adv(tx, name=name, seq=seq)

    monkeypatch.setattr(consumers, '_record_effect', spy_record)
    monkeypatch.setattr(consumers, '_advance', spy_advance)

    def handler(e):
        seen.append((ev.CAUSE.get(), e.id))                        # inside: the event's cause
        return 'ok'

    outer = (ids.new_ulid(),)                                      # the caller is itself a consumer
    token = ev.CAUSE.set(outer)
    try:
        assert consumers.deliver(db, 'sub', handler) == 2
    finally:
        ev.CAUSE.reset(token)
    assert [obs for obs, _x in seen] == [(eid,) for _o, eid in seen]
    # inside the handler: the event's own cause, never the caller's
    assert captured == [('record', outer), ('advance', outer),
                        ('record', outer), ('advance', outer)]     # submitted AFTER the reset
    assert ev.CAUSE.get() == ()
    assert _effects(db, 'sub') == [(s, 'ok') for s in made]
