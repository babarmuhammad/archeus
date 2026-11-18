"""T-322: the highest-risk uncovered branches of `archeus/core/metrics.py`, as tests.

Fail-closed and denial paths first: a log with no events fabricates no days, and a
worker with nothing due stops scanning the log. Then boundary values: a multi-day
backlog filled oldest-first one row per pass, `missing_days` never offering today or
re-offering a day that has its row, a COMPLETED event whose `missions` row is gone,
events that are neither an end nor a verdict, a mission ended twice in one day, the
route results that may enter the fallback-rate denominator, and the newest plan's
band with unknown costs skipped in the mean. Then the error-shaped paths: the
per-kind token guards against routes missing their rows, `record`'s once-only INSERT
under a same-day race of two writers, and a direct read through `daily`.

Same raw-row seeds and helper names as tests/v1/integration/test_p21_metrics_doctor.py,
the closest existing tests of this module; its `db` fixture is copied here because
tests/v1/unit has no conftest. No OS calls, no network, no sleeps, no real process;
the only threads are the two racers this file starts and joins itself.
"""

import datetime as dt
import json
import threading

import pytest

from archeus.core import metrics
from archeus.infra.db import Database

DAY = '2026-10-17'
T = DAY + 'T10:00:00.000Z'
META = {'version': 1, 'created_at': T, 'updated_at': T, 'created_by': 'p', 'updated_by': 'p'}


def _put(tx, *, rows):
    for table, cols in rows:
        tx.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ','.join(cols),
                                                        ','.join('?' * len(cols))),
                   list(cols.values()))


def put(db, *rows):
    db.writer.execute(_put, {'rows': list(rows)})


def mission(mid, state='RUNNING', at=T, created=None):
    return 'missions', dict(META, id=mid, workspace_id='wsp', state=state, body='{}',
                            created_at=created or at)


_SEQ = iter(range(1, 10 ** 6))


def event(etype, kind, sid, to, at=T):
    return 'events', {'id': 'evt%d' % next(_SEQ), 'type': etype, 'at': at, 'actor_kind': 'system',
                      'actor_id': 'p', 'cause_chain': '[]', 'subject_kind': kind,
                      'subject_id': sid, 'workspace_id': 'wsp', 'visibility': 'user',
                      'payload': json.dumps({'to': to})}


def plan(mid, pid, version, body):
    return 'plans', dict(META, id=pid, mission_id=mid, plan_version=version, state='APPROVED',
                         body=json.dumps(body))


def task(tid, pid, mid, body):
    return 'tasks', dict(META, id=tid, plan_id=pid, mission_id=mid, key='k-' + tid,
                         state='DONE', body=json.dumps(body))


def route(rid, body, created=T, mission_id=None, task_id=None):
    return 'route_decisions', dict(META, id=rid, mission_id=mission_id, task_id=task_id,
                                   created_at=created, body=json.dumps(body))


def pkg(cid, body):
    return 'context_packages', dict(META, id=cid, workspace_id='wsp', subject_kind='mission',
                                    subject_id='m1', body=json.dumps(body))


def usage(uid, body, route_decision_id=None):
    return 'usage_ledger', dict(META, id=uid, route_decision_id=route_decision_id,
                                execution_id=None, body=json.dumps(body))


@pytest.fixture
def db(archeus_home):                     # as in tests/v1/integration/conftest.py
    d = Database.open()
    yield d
    d.close()


def figures(db, day=DAY):
    with db.read() as conn:
        return metrics.compute(conn, day)


# ── fail-closed and denial paths ─────────────────────────────────────────────


def test_g1_no_events_fabricates_no_days_even_when_rows_exist(db):
    # metrics.py:126-127 `if first is None: return []`. With an empty events log
    # there is no finished history, whatever metrics_daily already holds; removing
    # this arm makes MIN(at)=None reach fromisoformat and crash the nightly pass.
    db.writer.execute(metrics.record, {'day': DAY, 'metrics': {'missions_completed': 1}})
    with db.read() as conn:
        assert metrics.missing_days(conn, dt.date(2026, 10, 20)) == []
    w = metrics.Metrics(db, today=lambda: dt.date(2026, 10, 20))
    assert w.pending() == 0
    assert w.pass_once() == {'changed': False}


def test_g2_a_worker_with_nothing_due_stops_reading_the_log(db, monkeypatch):
    # metrics.py:164-166 — the `if not days` arm sets `_filled_through` too, as
    # the filled arm does (only the after-a-change arm is covered by
    # test_a_filled_worker_reads_nothing_until_the_date_changes). Dropping that
    # line makes every poll re-scan the unindexed events log until midnight.
    w = metrics.Metrics(db, today=lambda: dt.date(2026, 10, 18))
    assert w.pass_once() == {'changed': False}
    reads = []
    real = db.read
    monkeypatch.setattr(db, 'read', lambda: reads.append(1) or real())
    assert w.pending() == 0 and w.pass_once() == {'changed': False}
    assert reads == []


# ── boundary values ──────────────────────────────────────────────────────────


def test_g3_a_backlog_is_filled_oldest_first_one_row_per_pass(db):
    # metrics.py:167-168 (`compute(conn, days[0])`, `{'day': days[0], ...}`) and
    # the oldest-first append at metrics.py:132-134: one pass publishes exactly
    # one day, always the oldest. `days[-1]` would publish yesterday first and a
    # long outage could starve the oldest finished day.
    put(db, *[event('session.observed', 'session', 's%d' % i, None, at=d + 'T12:00:00.000Z')
              for i, d in enumerate(('2026-10-15', '2026-10-16', '2026-10-17'))])
    w = metrics.Metrics(db, today=lambda: dt.date(2026, 10, 18))
    assert w.pending() == 3
    for expect in (['2026-10-15'], ['2026-10-15', '2026-10-16'],
                   ['2026-10-15', '2026-10-16', '2026-10-17']):
        assert w.pass_once() == {'changed': True}
        with db.read() as conn:
            got = [d for (d,) in conn.execute('SELECT day FROM metrics_daily ORDER BY day')]
        assert got == expect
    assert w.pass_once() == {'changed': False}


def test_g4_missing_days_never_offers_today_or_a_day_that_has_its_row(db):
    # metrics.py:130 `while d < today` (today has not ended, even with events at
    # 01:00Z) and metrics.py:131 `if d.isoformat() not in have` (a finished day
    # with its row is never re-offered, so it is never recomputed).
    put(db, event('session.observed', 'session', 's1', None, at=DAY + 'T06:00:00.000Z'),
        event('session.observed', 'session', 's2', None, at='2026-10-18T23:00:00.000Z'))
    db.writer.execute(metrics.record, {'day': DAY, 'metrics': {}})
    with db.read() as conn:
        assert metrics.missing_days(conn, dt.date(2026, 10, 19)) == ['2026-10-18']
        assert metrics.missing_days(conn, dt.date(2026, 10, 17)) == []


def test_g5_a_completed_event_whose_mission_row_is_gone_never_eats_the_median(db):
    # metrics.py:50-51 `for m in done if m in created`: the counters come from the
    # event log, but a duration exists only for missions still in `missions`.
    # Without the guard the whole nightly pass dies with KeyError('m2') and the
    # day gets no row at all. metrics.py:27 too: 0 approvals over 2 ended is 0.0,
    # not None (None is only for nothing measured).
    put(db, mission('m1', created=DAY + 'T09:00:00.000Z'),
        event('mission.state_changed', 'mission', 'm1', 'COMPLETED', at=DAY + 'T10:00:00.000Z'),
        event('mission.state_changed', 'mission', 'm2', 'COMPLETED', at=DAY + 'T11:00:00.000Z'))
    got = figures(db)
    assert (got['missions_completed'], got['missions_failed']) == (2, 0)
    assert got['median_time_to_complete_s'] == 3600.0     # m1's; m2 contributes none
    assert got['approvals_per_mission'] == 0.0
    assert got['cost_per_mission_band'] == {'unknown': {'missions': 2, 'cost_usd_mean': None}}


def test_g6_neither_an_end_nor_a_verdict_moves_a_counter(db):
    # metrics.py:42 `to in ENDS` and metrics.py:44 `to in ('PASSED', 'FAILED')`.
    # Inverting the first counts a still-RUNNING mission as failed; dropping the
    # second puts a RUNNING verification in the failure-rate denominator.
    put(db, mission('m1', created=DAY + 'T08:00:00.000Z'),
        event('mission.state_changed', 'mission', 'm0', 'RUNNING'),
        event('mission.state_changed', 'mission', 'm1', 'COMPLETED'),
        event('verification.state_changed', 'verification', 'v1', 'PASSED'),
        event('verification.state_changed', 'verification', 'v2', 'FAILED'),
        event('verification.state_changed', 'verification', 'v3', 'RUNNING'))
    got = figures(db)
    assert (got['missions_completed'], got['missions_failed']) == (1, 0)
    assert got['verification_failure_rate'] == 0.5         # not 1/3


def test_g7_a_mission_ended_twice_in_one_day_counts_once_at_its_last_end(db):
    # metrics.py:43 `ended[sid] = (to, at)` overwrites, so the day's last word is
    # the one that counts and the duration is measured to it; metrics.py:46/89-90
    # make `missions_failed` the exact complement of the completed list, never a
    # per-event tally (which would count m1 twice here).
    put(db, mission('m1', created=DAY + 'T09:00:00.000Z'),
        event('mission.state_changed', 'mission', 'm1', 'FAILED', at=DAY + 'T10:00:00.000Z'),
        event('mission.state_changed', 'mission', 'm1', 'COMPLETED', at=DAY + 'T11:00:00.000Z'),
        mission('m2', created=DAY + 'T09:00:00.000Z'),
        event('mission.state_changed', 'mission', 'm2', 'FAILED', at=DAY + 'T10:00:00.000Z'))
    got = figures(db)
    assert (got['missions_completed'], got['missions_failed']) == (1, 1)
    # m1's is measured to its LAST end (11:00 - 09:00): first-wins at
    # metrics.py:43 would make it 3600.0. m2 failed, and failed missions never
    # enter the median (metrics.py:50 `for m in done`).
    assert got['median_time_to_complete_s'] == 7200.0


def test_g8_fallback_rate_admits_only_routes_that_chose_a_resource(db):
    # metrics.py:59 `r in ('selected', 'fallback')` and metrics.py:27 `if whole
    # else None`: a day whose only routes were 'blocked' measured nothing, so its
    # rate is None, not 0.0 ("no fallbacks" would be a claim the day never made);
    # and blocked routes never enter the denominator beside the two that did.
    put(db, route('r1', {'result': 'blocked'}), route('r2', {'result': 'ask'}))
    assert figures(db)['fallback_rate'] is None
    put(db, route('r3', {'result': 'selected'}), route('r4', {'result': 'fallback'}))
    assert figures(db)['fallback_rate'] == 0.5
    put(db, route('r5', {'result': 'blocked'}))
    assert figures(db)['fallback_rate'] == 0.5             # denominator still 2


def test_g9_the_latest_plan_bands_a_mission_and_unknown_costs_skip_the_mean(db):
    # metrics.py:63-65 (the newest `plan_version` wins, and a plan without
    # `estimated_cost`, or no plan at all, is the 'unknown' label), metrics.py:70-71
    # and the mean at metrics.py:96-98: a mission with no usage row is counted in
    # `missions` but skipped in the mean (summing the None would raise), an all-
    # unknown band has mean None, and a usage row attached to no execution and no
    # route belongs to no mission.
    put(db,
        mission('m1', created=DAY + 'T08:00:00.000Z'), mission('m2'), mission('m3'),
        plan('m1', 'p1a', 1, {}), plan('m1', 'p1b', 2, {'estimated_cost': 'low'}),
        plan('m2', 'p2', 1, {'estimated_cost': 'low'}),
        plan('m3', 'p3', 1, {'notes': 'no estimated_cost here'}),
        route('r1', {'result': 'selected'}, mission_id='m1'),
        usage('u1', {'cost_usd': 0.5}, route_decision_id='r1'),
        usage('u2', {'cost_usd': 0.25}),                   # attached to nothing
        event('mission.state_changed', 'mission', 'm1', 'COMPLETED'),
        event('mission.state_changed', 'mission', 'm2', 'COMPLETED'),
        event('mission.state_changed', 'mission', 'm3', 'COMPLETED'))
    assert figures(db)['cost_per_mission_band'] == {
        'low': {'missions': 2, 'cost_usd_mean': 0.5},      # mean of m1's 0.5 only
        'unknown': {'missions': 1, 'cost_usd_mean': None}}


# ── error-shaped paths ───────────────────────────────────────────────────────


def test_g10_the_token_loop_skips_routes_missing_their_rows_and_adds_up_per_kind(db):
    # metrics.py:74-75 (`task_id IS NOT NULL` and the day window), metrics.py:77-78
    # (`if not rd.get('context_package_id'): continue`), metrics.py:80-82 (a
    # context_packages row that is gone -> `if pkg else None`), metrics.py:83 (a
    # tasks row that is gone -> `if task`), the `(budget or {})` at metrics.py:82,
    # the `kind or 'unknown'` label at metrics.py:84, the accumulate at
    # metrics.py:85, and `used is not None` at metrics.py:83: 0 is a reading.
    put(db,
        mission('m1'), plan('m1', 'p1', 1, {}),
        task('t1', 'p1', 'm1', {'kind': 'code'}), task('t5', 'p1', 'm1', {}),
        task('t6', 'p1', 'm1', {'kind': 'docs'}), task('t7', 'p1', 'm1', {'kind': 'x'}),
        pkg('c1', {'budget': {'used_tokens': 1200}}),
        pkg('c3', {'budget': {'used_tokens': 50}}),
        pkg('c4', {'budget': {'used_tokens': 0}}),
        pkg('c5', {}),                                     # a package with no budget
        # the candidate gate is the promoted task_id COLUMN (metrics.py:75), while
        # the rows are looked up by the body's task_id (metrics.py:80) — r4 has a
        # real column value and a body id whose tasks row is gone; r6 has the
        # whole candidate body but a NULL column, so the WHERE alone excludes it
        route('r1', {'task_id': 't1', 'context_package_id': 'c1'}, task_id='t1'),
        route('r2', {'task_id': 't1', 'context_package_id': 'c1'}, task_id='t1'),
        route('r3', {'task_id': 't1', 'context_package_id': 'gone'}, task_id='t1'),
        route('r4', {'task_id': 'gone', 'context_package_id': 'c1'}, task_id='t1'),
        route('r5', {'task_id': 't5', 'context_package_id': 'c3'}, task_id='t5'),
        route('r6', {'task_id': 't1', 'context_package_id': 'c1'}),
        route('r7', {'task_id': 't1'}, task_id='t1'),                # no package id: continue
        route('r8', {'task_id': 't1', 'context_package_id': 'c1'}, task_id='t1',
              created='2026-10-18T10:00:00.000Z'),                    # out of window
        route('r9', {'task_id': 't6', 'context_package_id': 'c4'}, task_id='t6'),
        route('r10', {'task_id': 't7', 'context_package_id': 'c5'}, task_id='t7'))
    assert figures(db)['context_tokens_per_task_kind'] == {'code': 2400, 'docs': 0,
                                                           'unknown': 50}


def test_g11_two_workers_recording_the_same_day_write_exactly_one_row(db):
    # metrics.py:105-108 `ON CONFLICT (day) DO NOTHING`: two workers that compute
    # the same finished day concurrently neither raise nor overwrite. Drop the
    # conflict clause and the second INSERT raises IntegrityError (day is the
    # PRIMARY KEY); turn it into DO UPDATE and the final row is the rival's.
    first = {'missions_completed': 1, 'median_time_to_complete_s': None}
    db.writer.execute(metrics.record, {'day': DAY, 'metrics': first})
    errors = []

    def race(n):
        try:
            db.writer.execute(metrics.record, {'day': DAY, 'metrics': {'missions_completed': n}},
                              timeout=30)
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=race, args=(n,), name='racer-%d' % n) for n in (2, 3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive()
    assert errors == []
    with db.read() as conn:
        rows = [tuple(r) for r in conn.execute('SELECT day, metrics FROM metrics_daily')]
    assert rows == [(DAY, json.dumps(first, sort_keys=True))]


def test_g12_daily_reads_back_newest_first_and_keeps_unknown_unknown(db):
    # metrics.py:113-119: `ORDER BY day DESC LIMIT ?` (ASC or a dropped LIMIT
    # changes what Health would show first or how much) and the `json.loads` that
    # hands back the recorded figures verbatim: a None stays None, it is never 0.
    # No existing test calls daily() directly.
    for day, done in ((DAY, 3), ('2026-10-16', 1)):
        db.writer.execute(metrics.record, {'day': day, 'metrics': {
            'missions_completed': done, 'median_time_to_complete_s': None}})
    with db.read() as conn:
        one = metrics.daily(conn, 1)
        both = metrics.daily(conn, 2)
        raw = conn.execute('SELECT computed_at FROM metrics_daily WHERE day = ?',
                           (DAY,)).fetchone()[0]
    assert [d['day'] for d in one['days']] == [DAY]                  # LIMIT 1, newest
    assert [d['day'] for d in both['days']] == [DAY, '2026-10-16']
    assert both['days'][0]['metrics'] == {'missions_completed': 3,
                                          'median_time_to_complete_s': None}
    assert both['days'][0]['computed_at'] == raw
