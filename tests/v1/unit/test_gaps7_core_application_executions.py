"""T-1309: the highest-risk uncovered branches of
`archeus/core/application/executions.py` lines **106-195 inclusive** (the O7 spawn
breaker: `_tripped`, `spawn_streak`, `breaker_state`, `_decided`, `_newest` and
`spawn_breaker`), at the current branch tip. No source file is edited and no other
test file is imported; the Ledger and the clock seam are copied from
tests/v1/integration/test_gaps3_core_application_executions_breaker.py.

Ten candidates, ranked by risk, each with the source branch it catches:

1. executions.py:178 (`LIMIT 600`) — the cap admits exactly 600 counting rows by
   creation: 597 newer INTENTs leave three failures visible (tripped), 598 hide one.
   Catches: a cap of 599 or 601.
2. executions.py:173-176 (SQL prefilter) — 600 newer binding refusals consume no cap
   and cannot hide three failures. Catches: a prefilter that stops dropping non-counting rows.
3. executions.py:184 (`if at <= now`) — a failure decided exactly at `now` counts; one
   second earlier it does not. Catches: `<=` changed to `<`.
4. executions.py:195 (`max(fails, key=ended_at)`) — the reported error is the latest
   failure by its end time, not by rowid, with a parked row mixed in.
5. executions.py:123-124 (`not fails`) — an INTENT dispatched before the latest failure
   is not the half-open trial, read from the database rather than a stub.
6. executions.py:176-177 (the parked-INTENT NOT clause) — failures of a PAUSED mission
   still count; only that mission's INTENTs are dropped. Catches: the NOT clause
   applied to every row.
7. executions.py:135 (`if now < until`) — at the cooldown's exact end the breaker is
   half-open, not open, when no trial is pending.
8. executions.py:119-121 (`elif x.started_at: break`) — binding refusals between
   failures neither end the streak nor add to it.
9. executions.py:178 with 176-177 — 599/600/601 parked INTENTs leave three failures
   visible: parked rows never reach the cap.
10. executions.py:184 with 119-121 — a start decided exactly at `now` ends the streak;
   one second earlier, the start is not yet history and the failures still trip.

Closest existing tests: tests/v1/integration/test_gaps3_core_application_executions_breaker.py
(items 1-10 there cover the parked, ahead-of-clock and tie cases, not these boundaries)
and tests/v1/unit/test_gaps_core_application_executions.py (no breaker probes).
"""

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import entities, events, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows

DAY = '2026-10-21T'
HARNESS = 'fake'


def T(h, m, s=0):
    return '%s%02d:%02d:%02dZ' % (DAY, h, m, s)


def E(h, m, s=0):
    return X._epoch(T(h, m, s))


@pytest.fixture
def db():
    return Database.open()


class Ledger:
    """The harness's execution rows, each written by the real writer at the instant the
    test names (the only seam faked is `events.now_iso`, which `writer.Tx.now` reads)."""

    def __init__(self, db, monkeypatch):
        self.db = db
        self.actor = Ref('user_device', ids.new_id('principal'))
        self._stamp = {'now': None}
        real = events.now_iso
        monkeypatch.setattr(events, 'now_iso', lambda: self._stamp['now'] or real())
        self._attempts = {}
        self._keys = iter(range(1, 10 ** 6))

    def mission(self, state='EXECUTING'):
        m = {'mid': ids.new_id('mission'), 'pid': ids.new_id('plan'), 'tid': ids.new_id('task')}
        a = self.actor

        def run(tx, **_):
            tx.insert(entities.Mission(id=m['mid'], workspace_id=ids.GLOBAL_WORKSPACE,
                                       title='M', objective='o', state=state), actor=a)
            tx.insert(entities.Plan(id=m['pid'], mission_id=m['mid'], state='APPROVED'), actor=a)
            tx.insert(entities.Task(id=m['tid'], plan_id=m['pid'], mission_id=m['mid'],
                                    key='t%d' % next(self._keys), title='T',
                                    kind='code_change', state='RUNNING'), actor=a)
            tx.append(new_event('mission.updated', Ref('mission', m['mid']), a, payload={},
                                workspace=ids.GLOBAL_WORKSPACE))
        self._stamp['now'] = T(9, 0)
        self.db.writer.execute(run, {})
        return m

    def executions(self, n, m, harness=HARNESS, created=None, state='ABANDONED', stop='spawn',
                   started_at=None, ended_at=None, summary='no process', charged=False):
        """*n* rows of one shape in one command: they share `created_at` and take the
        cap's newest slots in creation (rowid) order."""
        def run(tx, **_):
            for _ in range(n):
                tid = m['tid']
                self._attempts[tid] = k = self._attempts.get(tid, 0) + 1
                tx.insert(entities.Execution(
                    id=ids.new_id('execution'), task_id=tid, mission_id=m['mid'],
                    plan_id=m['pid'], attempt=k, harness_id=harness, state=state,
                    stop_reason=stop, started_at=started_at, ended_at=ended_at,
                    summary=summary, charged=charged), actor=self.actor)
            tx.append(new_event('mission.updated', Ref('mission', m['mid']), self.actor,
                                payload={}, workspace=ids.GLOBAL_WORKSPACE))
        self._stamp['now'] = created or T(10, 3)
        self.db.writer.execute(run, {})

    def one(self, m, **kw):
        self.executions(1, m, **kw)


def _three(L, m, ended=(0, 1, 2)):
    """Three failed starts created and ended at the given minutes past 10:00."""
    for i in ended:
        L.one(m, created=T(10, i), ended_at=T(10, i))


def _newest(db, now):
    with db.read() as r:
        return list(X._newest(r, HARNESS, now))


def _breaker(db, now):
    with db.read() as r:
        return X.spawn_breaker(r, HARNESS, now)


# ── 1 · the cap is 600 counting rows, by creation (executions.py:178) ───────

@pytest.mark.parametrize('newer,tripped', [(597, True), (598, False)],
                         ids=['597_newer_fit', '598_newer_hide_one'])
def test_the_cap_admits_exactly_600_counting_rows_by_creation(db, monkeypatch, newer, tripped):
    """executions.py:178 — `ORDER BY rowid DESC LIMIT 600`. Trial INTENTs are counting
    rows, so 597 of them plus the three failures fill the cap exactly and the breaker
    sees all three; one more INTENT pushes the oldest failure out of the read."""
    L = Ledger(db, monkeypatch)
    live = L.mission()
    _three(L, live)
    L.executions(newer, live, state='INTENT', stop=None, created=T(10, 3), summary='',
                 charged=None)
    seen = _newest(db, E(10, 4))
    assert len(seen) == min(600, newer + 3)
    b = _breaker(db, E(10, 4))
    assert (b is not None) == tripped
    if tripped:
        assert b == {'state': 'open', 'until': E(10, 2) + X.SPAWN_COOLDOWN_S,
                     'error': 'no process'}


# ── 2 · binding refusals consume no cap (executions.py:173-176) ─────────────

def test_six_hundred_newer_binding_refusals_consume_no_cap(db, monkeypatch):
    """executions.py:173-176 — the SQL prefilter drops a row with no `spawn`, no
    `started_at` and not an INTENT, so a refusal that binds nothing never takes one of
    the 600 slots. Without the filter, 600 refusals would push the three failures out
    of the read and the breaker would never open."""
    L = Ledger(db, monkeypatch)
    live = L.mission()
    _three(L, live)
    L.executions(600, live, stop='binding', summary='refused', created=T(10, 3))
    assert len(_newest(db, E(10, 4))) == 3
    b = _breaker(db, E(10, 4))
    assert b and b['state'] == 'open' and b['until'] == E(10, 2) + X.SPAWN_COOLDOWN_S


# ── 3 · a failure decided exactly at now counts (executions.py:184) ─────────

def test_a_failure_decided_exactly_at_now_counts_and_a_second_earlier_does_not(db, monkeypatch):
    """executions.py:184 — `if at <= now`. The third failure ended at 10:04:00. At
    10:03:59 it is not history yet and two failures do not trip; at 10:04:00 it is, and
    the breaker opens for the cooldown after it."""
    L = Ledger(db, monkeypatch)
    live = L.mission()
    _three(L, live, ended=(0, 1, 4))
    assert _breaker(db, E(10, 3, 59)) is None
    assert _breaker(db, E(10, 4)) == {'state': 'open', 'until': E(10, 4) + X.SPAWN_COOLDOWN_S,
                                      'error': 'no process'}


# ── 4 · the error is the latest failure by end time (executions.py:195) ─────

def test_the_reported_error_is_the_latest_failure_by_end_not_by_creation(db, monkeypatch):
    """executions.py:195 — `max(fails, key=ended_at)`. The newest row by creation ended
    earliest ('early'); the one created first ended last ('late'). A parked INTENT of a
    PAUSED mission sits newest of all and must change nothing."""
    L = Ledger(db, monkeypatch)
    live, parked = L.mission(), L.mission('PAUSED')
    L.one(live, created=T(10, 0), ended_at=T(10, 2, 30), summary='late')
    L.one(live, created=T(10, 1), ended_at=T(10, 0, 30), summary='early')
    L.one(live, created=T(10, 2), ended_at=T(10, 1), summary='mid')
    L.one(parked, state='INTENT', stop=None, charged=None, created=T(10, 5), summary='')
    b = _breaker(db, E(10, 3))
    assert b == {'state': 'open', 'until': E(10, 2, 30) + X.SPAWN_COOLDOWN_S, 'error': 'late'}


# ── 5 · an INTENT behind the failures is not the trial (executions.py:123-124) ──

def test_an_intent_dispatched_before_the_latest_failure_is_not_the_trial(db, monkeypatch):
    """executions.py:123 — `elif x.state == 'INTENT' and not fails`. The INTENT was
    dispatched at 10:00:30, before the failure that ended at 10:02. After the cooldown
    the harness is half-open with no trial pending; were the INTENT taken as the trial
    the wait would run again for 15 s."""
    L = Ledger(db, monkeypatch)
    live = L.mission()
    _three(L, live)
    L.one(live, state='INTENT', stop=None, charged=None, created=T(10, 0, 30), summary='')
    assert _breaker(db, E(10, 8)) == {'state': 'half_open', 'until': None, 'error': 'no process'}


# ── 6 · failures of a paused mission still count (executions.py:176-177) ────

def test_the_failures_of_a_paused_mission_count_only_its_intents_are_parked(db, monkeypatch):
    """executions.py:176-177 — the NOT clause drops INTENTs of a non-EXECUTING mission
    and nothing else. The three failed starts belong to a PAUSED mission; they still trip
    the breaker, and its parked INTENT is not read."""
    L = Ledger(db, monkeypatch)
    paused = L.mission('PAUSED')
    _three(L, paused)
    L.one(paused, state='INTENT', stop=None, charged=None, created=T(10, 5), summary='')
    seen = _newest(db, E(10, 6))
    assert [x.state for x in seen] == ['ABANDONED'] * 3
    assert _breaker(db, E(10, 6)) == {'state': 'open', 'until': E(10, 2) + X.SPAWN_COOLDOWN_S,
                                      'error': 'no process'}


# ── 7 · the cooldown's exact end is half-open (executions.py:135) ───────────

def test_at_the_cooldown_end_with_no_trial_the_breaker_is_half_open(db, monkeypatch):
    """executions.py:135 — `if now < until`. The latest failure ended at 10:02, so the
    cooldown ends at 10:07:00. At that very instant nothing is pending: half-open, with
    no until. One second earlier it is still open."""
    L = Ledger(db, monkeypatch)
    live = L.mission()
    _three(L, live)
    assert _breaker(db, E(10, 6, 59))['state'] == 'open'
    assert _breaker(db, E(10, 7)) == {'state': 'half_open', 'until': None,
                                      'error': 'no process'}


# ── 8 · binding refusals between failures do not end the streak (119-121) ──

def test_binding_refusals_between_failures_neither_end_nor_add_to_the_streak(db, monkeypatch):
    """executions.py:119-121 — a refusal has no `spawn` and no `started_at`, so the
    streak passes over it. Two refusals sit between the failures in creation order and
    the breaker opens on exactly the three failures."""
    L = Ledger(db, monkeypatch)
    live = L.mission()
    L.one(live, created=T(10, 0), ended_at=T(10, 0))
    L.one(live, stop='binding', summary='refused', created=T(10, 0, 10))
    L.one(live, created=T(10, 1), ended_at=T(10, 1))
    L.one(live, stop='binding', summary='refused', created=T(10, 1, 10))
    L.one(live, created=T(10, 2), ended_at=T(10, 2))
    b = _breaker(db, E(10, 3))
    assert b == {'state': 'open', 'until': E(10, 2) + X.SPAWN_COOLDOWN_S, 'error': 'no process'}


# ── 9 · parked INTENTs never reach the cap (executions.py:176-178) ──────────

@pytest.mark.parametrize('parked', [599, 600, 601], ids=['599', '600', '601'])
def test_parked_intents_at_the_cap_boundary_leave_three_failures_visible(db, monkeypatch, parked):
    """executions.py:176-178 — parked INTENTs are excluded by the SQL before the LIMIT, so
    599, 600 or 601 of them, all newer, cannot push the failures out of the read. The
    integration file pins 600 only."""
    L = Ledger(db, monkeypatch)
    live, paused = L.mission(), L.mission('PAUSED')
    _three(L, live)
    L.executions(parked, paused, state='INTENT', stop=None, created=T(10, 3), summary='',
                 charged=None)
    assert len(_newest(db, E(10, 4))) == 3
    assert _breaker(db, E(10, 4))['state'] == 'open'


# ── 10 · a start decided exactly at now ends the streak (119-121, 184) ──────

def test_a_start_decided_exactly_at_now_ends_the_streak_and_one_second_earlier_it_does_not(
        db, monkeypatch):
    """executions.py:184 with 119-121 — the start's decided time is its `started_at`.
    At 10:03:00 it is history and cuts the streak, so no breaker. At 10:02:59 it is not
    history yet, the three failures stand and the breaker is open."""
    L = Ledger(db, monkeypatch)
    live = L.mission()
    _three(L, live)
    L.one(live, state='ENDED_OK', stop=None, charged=False, created=T(10, 3),
          started_at=T(10, 3), ended_at=T(10, 3, 30), summary='')
    assert _breaker(db, E(10, 2, 59))['state'] == 'open'
    assert _breaker(db, E(10, 3)) is None
