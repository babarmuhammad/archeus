"""T-1148 · the highest-risk uncovered branches of
`archeus/core/application/executions.py` lines **97-222 inclusive** (the O7 spawn
breaker and the task's start wait), at tip 56d53504. No source file is edited here,
and no other test file is imported: this file stands on its own.

The ten branches this file pins (ranked by risk; the report carries the evidence
for each, including the closest existing test and why its assertion misses):

1. `executions.py:182-183` — a *start* decided after `now` is not history yet: were
   it counted it would end the failure streak and hand a broken harness its tries
   back (fail-open: an endless run of failed spawns).
2. `executions.py:119-122` with `145-146` — a failed start whose own row also carries
   `started_at` (a restart that failed) is a FAILURE decided at its end, not the
   start that ends the streak (`if spawn` must be tested before `elif started_at`).
3. `executions.py:178-180` — the body's own JSON is not the entity: a row of
   another harness that only *quotes* `"harness_id": "fake"` inside a dict field
   passes the SQL prefilter and must be dropped by the Python check.
4. `executions.py:186-188` — the half-open trial is taken from an INTENT of an
   EXECUTING mission: a parked mission's INTENT never becomes the trial that makes
   every other task wait.
5. `executions.py:221` — `_spawn_failed` decides the trip from *this harness's*
   rows only; read unscoped, another harness's failures would silence this
   harness's `harness.state_changed` notice (P21 D1: the tray never says it).
6. `executions.py:208-209` — the task's wait counts its trailing failures by
   *decided* time, not by creation: a success decided between them, or creation
   order, would shorten the streak to nothing and re-dispatch on every pass.
7. `executions.py:173-176` (the `LIMIT 600`) with `186-188` — the cap is applied to
   the raw scan, before the INTENTs of a parked mission are dropped, so 600 newer
   parked INTENTs can hide a tripped breaker: the source contradicts its own
   contract at 162-164, so this case is kept as an xfail.
8. `executions.py:182-183` with `137-138` — a *trial INTENT* decided after `now` is
   not history either: kept, it would hold the whole harness open on a mission that
   never starts it.
9. `executions.py:184` — rows decided at one instant are ordered by creation
   (rowid): inverted, a start that came last would still end the streak.
10. `executions.py:200, 212-213` — the wait is capped at `SPAWN_WAIT_MAX_S` and
    expires at exactly that instant (`now < until`, not `<=`).

Platform-neutral: no OS call is made or faked beyond the writer's own clock seam
(`archeus.core.domain.events.now_iso`, the seam tests/v1/integration/
test_spawn_breaker.py already uses for T-106 r5), no process, no socket, no thread,
no sleep; every instant is an explicit `...Z` string and every write goes through
the real single writer over the `tmp_path` ARCHEUS_HOME the v1 conftest pins, so
nothing lands outside the test's temp directory. The `tc`/TempCore fixture (real
sockets) is deliberately never requested: nothing in this slice touches a transport,
a worker, a sentinel or an adapter.
"""

import itertools

import pytest

from archeus.core.application import executions as X, queries
from archeus.infra.db import rows
from archeus.core.domain import entities, events, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref

#: every recorded day of this file, spelled out so no test reads a local zone
DAY = '2026-10-21T'
HARNESS = 'fake'


def T(h, m, s=0):
    """The recorded instant `2026-10-21T<h>:<m>:<s>Z` (text, as the rows hold it)."""
    return '%s%02d:%02d:%02dZ' % (DAY, h, m, s)


def E(h, m, s=0):
    """That same instant as the epoch the breaker compares (parsed, never as text)."""
    return X._epoch(T(h, m, s))


class Ledger:
    """The harness's execution rows, written by the real writer at the times the
    test names.

    Each row goes through its own writer command, because a command stamps
    `created_at` once (`Tx.now`) and the breaker reads two different clocks: what
    the row was *created* at (`created_at`, the cap's and the trial's time) and
    what it was *decided* at (a failed start's `ended_at`, a start's `started_at`).
    The only seam faked is the writer's clock: `events.now_iso`, which
    `writer.Tx.now` reads.
    """

    def __init__(self, db, monkeypatch):
        self.db = db
        self.actor = Ref('user_device', ids.new_id('principal'))
        self._stamp = {'now': None}
        real = events.now_iso
        monkeypatch.setattr(events, 'now_iso', lambda: self._stamp['now'] or real())
        self._keys = itertools.count(1)
        self._attempts = {}

    def stamp(self, iso):
        """What the next command's `Tx.now` says (a command's stamp is taken before
        it runs, which is the whole of the T-106 r5 hazard)."""
        self._stamp['now'] = iso

    def mission(self, state='EXECUTING'):
        """A mission in *state*, an approved plan and one RUNNING task under it."""
        m = {'mid': ids.new_id('mission'), 'pid': ids.new_id('plan'),
             'tid': ids.new_id('task')}
        a = self.actor

        def run(tx, **_):
            tx.insert(entities.Mission(id=m['mid'], workspace_id=ids.GLOBAL_WORKSPACE,
                                       title='M', objective='o', state=state), actor=a)
            tx.insert(entities.Plan(id=m['pid'], mission_id=m['mid'], state='APPROVED'),
                      actor=a)
            tx.insert(entities.Task(id=m['tid'], plan_id=m['pid'], mission_id=m['mid'],
                                    key='t%d' % next(self._keys), title='T',
                                    kind='code_change', state='RUNNING'), actor=a)
            tx.append(new_event('mission.updated', Ref('mission', m['mid']), a, payload={},
                                workspace=ids.GLOBAL_WORKSPACE))
        self.stamp(T(9, 0))
        self.db.writer.execute(run, {})
        return m

    def _entity(self, m, harness, state, stop, started_at, ended_at, summary,
                charged, kw):
        tid = m['tid']
        self._attempts[tid] = n = self._attempts.get(tid, 0) + 1
        return entities.Execution(id=ids.new_id('execution'), task_id=tid,
                                  mission_id=m['mid'], plan_id=m['pid'], attempt=n,
                                  harness_id=harness, state=state, stop_reason=stop,
                                  started_at=started_at, ended_at=ended_at,
                                  summary=summary, charged=charged, **kw)

    def execution(self, m, **kw):
        """One execution row, by its own command. `created` is the row's
        `created_at`; the recorded instants are the entity's own and may disagree
        with it (a clock step, which is what these tests are about)."""
        return self._insert(1, m, **kw)[0]

    def executions(self, n, m, **kw):
        """*n* rows of one shape, in one command: they share `created_at` and take
        the cap's newest slots in rowid (creation) order."""
        return self._insert(n, m, **kw)

    def _insert(self, n, m, harness=HARNESS, created=None, state='ABANDONED',
                stop='spawn', started_at=None, ended_at=None, summary='no process',
                charged=False, **kw):
        made = []

        def run(tx, **_):
            for _ in range(n):
                e = self._entity(m, harness, state, stop, started_at, ended_at,
                                 summary, charged, kw)
                tx.insert(e, actor=self.actor)
                made.append(e.id)
            tx.append(new_event('mission.updated', Ref('mission', m['mid']), self.actor,
                                payload={}, workspace=ids.GLOBAL_WORKSPACE))
        self.stamp(created or T(10, 3))
        self.db.writer.execute(run, {})
        return made


class Prefilter:
    """Wraps a read connection and keeps the rows the SQL prefilter admitted, so a
    test can tell `executions.py:173-176` (the `body LIKE` scan) from the Python check
    at `executions.py:178-180` that runs after it."""

    def __init__(self, conn):
        self.conn, self.admitted = conn, []

    def execute(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        if 'FROM executions' not in sql:
            return cur
        self.admitted = list(cur)
        return iter(self.admitted)

    def __getattr__(self, name):
        return getattr(self.conn, name)


def _newest(db, harness, now):
    with db.read() as r:
        return list(X._newest(r, harness, now))


def _seen(db, harness, now):
    """(_newest's rows, the rows the SQL admitted) for one harness at *now*."""
    with db.read() as r:
        p = Prefilter(r)
        rows_ = list(X._newest(p, harness, now))
        return rows_, p.admitted


def _streak(db, harness, now):
    with db.read() as r:
        return X.spawn_streak(X._newest(r, harness, now))


def _breaker(db, harness, now):
    with db.read() as r:
        return X.spawn_breaker(r, harness, now)


def _wait(db, task_id, now):
    with db.read() as r:
        return X.spawn_wait(r, task_id, now)


def _notices(db):
    with db.read() as r:
        return [ev for ev in queries.events(r) if ev['type'] == 'harness.state_changed']


def _three_failures(L, m, at=(10, 0)):
    """Three failed starts a minute apart, the smallest set that trips O7."""
    for i in range(3):
        L.execution(m, created=T(at[0], at[1] + i), ended_at=T(at[0], at[1] + i))


# ── 1 · a start ahead of the clock is not history (executions.py:182-183) ───

def test_a_start_recorded_ahead_of_the_clock_never_ends_the_failure_streak(db, monkeypatch):
    """executions.py:182-183 — `if at <= now: found.append((at, x))` inside
    `_newest`, on a row whose decided time is its `started_at`. Dropped (or read
    from `created_at`, which is well inside history here), the start sorts above
    every failure, `spawn_streak`'s `elif x.started_at: break` fires and the
    harness keeps its tries back: the breaker that O7 opens for 3 failed starts
    would never open, and Core would spawn for ever.

    The control is the second read: once the clock really does pass that start
    (now = 10:41), the same rows cut the streak and answer None."""
    L = Ledger(db, monkeypatch)
    m = L.mission()
    _three_failures(L, m)
    L.execution(m, state='ENDED_OK', stop=None, created=T(10, 3), charged=False,
                started_at=T(10, 40), ended_at=T(10, 40, 30), summary='')
    b = _breaker(db, HARNESS, E(10, 4))
    assert b == {'state': 'open', 'until': E(10, 2) + X.SPAWN_COOLDOWN_S,
                 'error': 'no process'}
    assert _breaker(db, HARNESS, E(10, 41)) is None           # the start is history now


# ── 2 · a failed restart is a failure (executions.py:119-122) ───────────────

def test_a_failed_restart_of_a_started_row_counts_as_a_failed_start(db, monkeypatch):
    """executions.py:119-122 with 145-146 — a row that satisfies BOTH
    `x.stop_reason == 'spawn'` and `x.started_at` (a process that ran and whose
    *restart* was refused) is a FAILURE decided at its `ended_at`: the `if` must be
    taken before the `elif x.started_at: break` of 121-122, and `_decided` must
    answer a failed start's end rather than its start.

    The row that ran from 10:00 to 10:30 and then failed to restart is the newest
    by its own end, so the walk reaches the genuine start of 10:15 only after the
    three failures. Either mutation puts that start above the restart: the streak
    is cut at two failures, `_tripped` says no, and a harness that cannot start a
    process is tried again on the next pass."""
    L = Ledger(db, monkeypatch)
    m = L.mission()
    L.execution(m, state='ENDED_OK', stop=None, charged=False, created=T(10, 15),
                started_at=T(10, 15), ended_at=T(10, 15, 30), summary='')
    L.execution(m, created=T(10, 29), ended_at=T(10, 29), summary='first')
    L.execution(m, created=T(10, 29, 30), ended_at=T(10, 29, 30), summary='second')
    L.execution(m, created=T(10, 30), ended_at=T(10, 30), started_at=T(10, 0),
                summary='restart refused')
    fails, trial = _streak(db, HARNESS, E(10, 31))
    assert [x.summary for x in fails] == ['restart refused', 'second', 'first']
    assert [x.ended_at for x in fails] == [T(10, 30), T(10, 29, 30), T(10, 29)]
    assert trial is False
    assert _breaker(db, HARNESS, E(10, 31)) == {
        'state': 'open', 'until': E(10, 30) + X.SPAWN_COOLDOWN_S,
        'error': 'restart refused'}                       # the newest failure's reason


# ── 3 · the body quoting this harness is not this harness (178-180) ────────

def test_a_foreign_row_that_only_quotes_this_harness_in_its_body_counts_nothing(
        db, monkeypatch):
    """executions.py:178-179 — `if x.harness_id != harness_id ... continue`. The
    prefilter at 173-176 matches the body's own encoding of the key, and a nested dict
    field (`usage`) encodes `"harness_id": "fake"` exactly like the entity's own
    field does, so this row of harness `other` is admitted by the SQL and only the
    Python check can drop it. Removed, another harness's failure would be charged
    to this one: `other`'s summary would become `fake`'s breaker reason, and one
    `other` failure would count towards `fake`'s trip."""
    L = Ledger(db, monkeypatch)
    m = L.mission()
    _three_failures(L, m)
    L.execution(m, harness='other', created=T(10, 3), ended_at=T(10, 3),
                summary='the other harness is down', usage={'harness_id': HARNESS,
                                                            'account': 'acc-1'})
    seen, admitted = _seen(db, HARNESS, E(10, 4))
    assert len(admitted) == 4 and len(seen) == 3           # the SQL let the foreign row in
    assert {x.harness_id for x in seen} == {HARNESS}
    b = _breaker(db, HARNESS, E(10, 4))
    assert (b['state'], b['error']) == ('open', 'no process')
    assert _breaker(db, 'other', E(10, 4)) is None         # its own row is one failure only


# ── 4 · the trial comes from a running mission (executions.py:186-188) ──────

@pytest.mark.parametrize('parked', [True, False], ids=['parked', 'running'])
def test_the_half_open_trial_is_taken_from_a_mission_that_can_start_it(db, monkeypatch,
                                                                       parked):
    """executions.py:186-188 — `if x.state == 'INTENT' and rows.get(conn, Mission,
    ...).entity.state != 'EXECUTING': continue`, seen against `spawn_streak`'s
    `elif x.state == 'INTENT' and not fails: trial = True` at 123-124.

    Two missions: one EXECUTING whose INTENT was dispatched *before* the last
    failure (so it is not a trial), one PAUSED with the newest INTENT of all. The
    filter is what keeps that parked row from becoming the trial; drop it and the
    harness sits `open` for `SPAWN_WAIT_S` after `now` on the strength of a mission
    that will never start it, which is a wait no one can release."""
    L = Ledger(db, monkeypatch)
    live = L.mission('EXECUTING')
    other = L.mission('PAUSED' if parked else 'EXECUTING')
    _three_failures(L, live)
    L.execution(live, state='INTENT', stop=None, charged=None, created=T(9, 55),
                summary='')
    L.execution(other, state='INTENT', stop=None, charged=None, created=T(10, 5),
                summary='')
    seen = _newest(db, HARNESS, E(10, 10))
    intents = [x.mission_id for x in seen if x.state == 'INTENT']
    assert intents == ([live['mid']] if parked else [other['mid'], live['mid']])
    assert len([x for x in seen if x.state != 'INTENT']) == 3        # the three failed starts
    b = _breaker(db, HARNESS, E(10, 10))
    assert b['state'] == ('half_open' if parked else 'open')
    assert b['until'] == (None if parked else E(10, 10) + X.SPAWN_WAIT_S)


# ── 5 · the trip is said once, for the harness that tripped (221) ───────────

def test_the_breaker_notice_is_said_for_the_harness_whose_own_rows_tripped_it(
        db, monkeypatch):
    """executions.py:221 — `spawn_streak(_newest(tx.conn, e.harness_id,
    _epoch(e.ended_at)))`, both of its arguments.

    `fake` fails its third start while another harness, `other`, already has
    three failures of its own inside the window. Read unscoped, the union is
    already tripped without this row, so the `not _tripped(without this one)`
    test says "nothing new opened" and the operator is never told (P21 D1: the
    tray says it once). Read from `tx.now` rather than the failure's own stamp —
    a whole second behind, as it is here — this very failure is missing from the
    read and the notice is lost the same way."""
    L = Ledger(db, monkeypatch)
    m = L.mission()
    L.execution(m, created=T(10, 0), ended_at=T(10, 0))
    L.execution(m, created=T(10, 1), ended_at=T(10, 1))
    eid = L.execution(m, created=T(10, 2), ended_at=T(10, 2), summary='no process')
    for i in range(3):
        L.execution(m, harness='other', created=T(10, 0, 30 + i),
                    ended_at=T(10, 0, 30 + i), summary='other cannot start')
    with db.read() as r:
        e = rows.get(r, entities.Execution, eid).entity
    assert e.harness_id == HARNESS and e.ended_at == T(10, 2)

    def trip(tx, **_):
        X._spawn_failed(tx, L.actor, e, 'no process')
    L.stamp(T(10, 1, 59))                    # the command's stamp is one second behind the end
    db.writer.execute(trip, {})
    got = _notices(db)
    assert len(got) == 1, got
    assert (got[0]['subject'], got[0]['payload']) == (
        {'kind': 'harness', 'id': HARNESS}, {'breaker': 'open', 'reason': 'no process'})


# ── 6 · the task's wait counts failures in time order (executions.py:208-209)

def test_a_task_waits_for_the_failures_that_came_last_in_time_not_in_creation(
        db, monkeypatch):
    """executions.py:208-209 — the `sorted(decided, key=lambda p: p[0])` and the
    `next(... if x.stop_reason != 'spawn')` walk that follows it.

    The three rows were created in an order that contradicts the times they were
    decided at (a clock step): read by creation the success is the newest row and
    the streak is empty, so `spawn_wait` answers None and the engine re-dispatches
    the task on the very next pass — the hot loop of failed spawns the 15 s doubling
    wait exists to stop. Read by decided time the success is the *oldest*, the two
    failures are trailing, and the wait is `spawn_wait_s(2)` from the newer end.

    The fourth row is the same line's other half, the `if at <= now` of 208: a
    failure the clock has not reached yet (ended 10:40, a rewind mid-run) is not
    history, so it is neither counted in the streak nor used for `until`; were it
    kept, the task would sit until 45 s after an instant that has not happened."""
    L = Ledger(db, monkeypatch)
    m = L.mission()
    L.execution(m, created=T(10, 0), ended_at=T(10, 9))
    L.execution(m, created=T(10, 1), ended_at=T(10, 10))
    L.execution(m, state='ENDED_OK', stop=None, created=T(10, 2), charged=False,
                started_at=T(10, 5), ended_at=T(10, 5, 30), summary='')
    L.execution(m, created=T(10, 3), ended_at=T(10, 40))
    assert _wait(db, m['tid'], E(10, 10, 10)) == E(10, 10) + X.spawn_wait_s(2)
    # and it is the trailing streak: the same rows one second later, before the
    # wait ends, still say 30 s (spawn_wait_s(1) would be 15 s)
    assert _wait(db, m['tid'], E(10, 10, 29)) == E(10, 10) + X.spawn_wait_s(2)


# ── 7 · the cap counts counting rows (executions.py:173-176 with 186-188) ───

def test_six_hundred_parked_intents_do_not_hide_a_tripped_breaker(db, monkeypatch):
    """executions.py:173-176 (the `LIMIT 600`) held to the contract written at 162-164:
    the cap "counts counting rows only", and a trial INTENT counts only while its
    mission is EXECUTING (186-188). Here the 600 newest rows by creation are all
    INTENTs of a PAUSED mission, and the three failures that do trip the breaker
    sit just below them: they are never read, so the harness that cannot start a
    process is off the hook and is tried again on the next pass.

    The premise is justified, so the assertion stays: a counting row is a failed
    start, a start or a trial INTENT (the source's own words at 151 and 162-164),
    and the INTENTs of a parked mission are dropped only at 186-188, after the cap."""
    L = Ledger(db, monkeypatch)
    live, parked = L.mission('EXECUTING'), L.mission('PAUSED')
    _three_failures(L, live)
    L.executions(600, parked, state='INTENT', stop=None, charged=None, created=T(10, 3),
                 summary='')
    assert len(_newest(db, HARNESS, E(10, 4))) == 3          # the cap holds the failures
    b = _breaker(db, HARNESS, E(10, 4))
    assert b and b['state'] == 'open' and b['until'] == E(10, 2) + X.SPAWN_COOLDOWN_S


# ── 8 · a trial ahead of the clock holds nothing (executions.py:182-183) ────

@pytest.mark.parametrize('ahead', [True, False], ids=['ahead_of_clock', 'in_history'])
def test_an_intent_recorded_ahead_of_the_clock_is_not_the_harnesss_trial(
        db, monkeypatch, ahead):
    """executions.py:182-183 again, this time on the arm of `_decided` at 147 that
    answers a not-yet-started INTENT's `created_at`, and on the trial branch of
    `breaker_state` at 137-138 (`if trial: return {open, now + SPAWN_WAIT_S}`).

    The cooldown has run out, so the harness is half-open and one task may try. A
    row whose creation stamp is ahead of the clock is not history yet: kept, it
    would be the half-open trial, and every other task would wait 15 s on an
    INTENT that was never dispatched at that time. Dropped (the row's real
    creation, in history, is the control) the trial is real and the wait is said."""
    L = Ledger(db, monkeypatch)
    m = L.mission()
    _three_failures(L, m)
    L.execution(m, state='INTENT', stop=None, charged=None,
                created=T(10, 40) if ahead else T(10, 5), summary='')
    seen, _ = _seen(db, HARNESS, E(10, 10))
    assert [x.state for x in seen].count('INTENT') == (0 if ahead else 1)
    b = _breaker(db, HARNESS, E(10, 10))
    assert b['state'] == ('half_open' if ahead else 'open')
    assert b['until'] == (None if ahead else E(10, 10) + X.SPAWN_WAIT_S)


# ── 9 · one instant, decided by creation (executions.py:184) ────────────────

@pytest.mark.parametrize('start_last', [True, False], ids=['start_created_last',
                                                           'start_created_first'])
def test_rows_decided_at_the_same_instant_are_ordered_by_their_creation(
        db, monkeypatch, start_last):
    """executions.py:184 — `found.sort(key=lambda p: p[0], reverse=True)` is stable,
    so the `ORDER BY rowid DESC` of the scan at 176 breaks a tie; the comment at
    184 says so ("rowid order breaks ties").

    Three failed starts and one start all decided at the same second: whichever
    was created last is the newer by 184, and only the tie-break decides whether
    the streak ends before the failures or after them — i.e. whether the harness
    is blocked for a cooldown at all."""
    L = Ledger(db, monkeypatch)
    m = L.mission()
    rows_ = [dict(created=T(10, 0), ended_at=T(10, 0)),
             dict(created=T(10, 0), ended_at=T(10, 0)),
             dict(created=T(10, 0), ended_at=T(10, 0))]
    if start_last:
        rows_.append(dict(state='ENDED_OK', stop=None, charged=False, created=T(10, 0),
                          started_at=T(10, 0), ended_at=T(10, 0, 30), summary=''))
    for kw in rows_:
        L.execution(m, **kw)
    fails, _trial = _streak(db, HARNESS, E(10, 1))
    assert len(fails) == (0 if start_last else 3)
    assert _breaker(db, HARNESS, E(10, 1)) == (
        None if start_last else {'state': 'open', 'until': E(10, 0) + X.SPAWN_COOLDOWN_S,
                                 'error': 'no process'})


# ── 10 · the wait is capped and expires exactly (200, 212-213) ──────────────

def test_the_start_wait_is_capped_at_five_minutes_and_is_over_at_that_very_moment(
        db, monkeypatch):
    """executions.py:200 (`min(SPAWN_WAIT_S * 2 ** (n - 1), SPAWN_WAIT_MAX_S)`) and
    212-213 (`until = _epoch(xs[-1].ended_at) + spawn_wait_s(n)` /
    `return until if now < until else None`).

    Six failed starts in a row would double the wait to 480 s; the cap is what
    keeps a broken harness out of the way for exactly one ceiling. And the wait is
    over *at* `until`, not one pass after it: loosened to `now <= until` the call
    keeps answering `until` — a deadline equal to now, which the engine parks on
    again — instead of saying None and letting the task be routed."""
    L = Ledger(db, monkeypatch)
    m = L.mission()
    for i in range(6):
        L.execution(m, created=T(10, i), ended_at=T(10, i))
    assert X.spawn_wait_s(6) == X.SPAWN_WAIT_MAX_S == 300         # 15 * 2 ** 5 would be 480
    until = E(10, 5) + X.SPAWN_WAIT_MAX_S
    assert _wait(db, m['tid'], E(10, 5)) == until                 # from the newest failure
    assert _wait(db, m['tid'], until - 1) == until                # one second left
    assert _wait(db, m['tid'], until) is None                     # the exact expiry
