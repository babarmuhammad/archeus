"""P21 slice H: schedule triggers and `next_run_at` (p21-design-gate D9, ADR-0020,
ADR-0030 §4, state-machines §8 claim-and-advance).

The real automation worker over a real archeus.db, on a frozen clock: Core's
one clock is `events.now_iso`, which every transaction's `now` reads (the
fixture is not called `clock`: conftest's `clock` is the launch clock `tc` takes).
"""

import threading
from datetime import datetime, timedelta, timezone

import pytest

from archeus.core.application import automations as A, commands
from archeus.core.automation.worker import Automations
from archeus.core.domain import entities, events
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows

from .test_automation import SEED, Rig
from .test_automation_http import _post

T0 = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
EVERY = {'kind': 'schedule', 'every': '15m'}


def iso(minutes):
    return (T0 + timedelta(minutes=minutes)).isoformat(timespec='milliseconds').replace(
        '+00:00', 'Z')


@pytest.fixture
def frozen(monkeypatch):
    now = [iso(0)]
    monkeypatch.setattr(events, 'now_iso', lambda: now[0])

    def at(minutes):
        now[0] = iso(minutes)
    return at


@pytest.fixture
def rig(archeus_home, frozen):
    r = Rig()
    yield r
    r.close()


def _due_events(conn, aid):
    return [r for r in conn.execute("SELECT seq, payload FROM events WHERE type = "
                                    "'automation.schedule_due' AND subject_id = ?", (aid,))]


def test_H01_a_schedule_fires_at_its_time_not_before_and_moves_on(rig, frozen):
    aid = rig.automation(trigger=EVERY)
    assert rig.row(entities.Automation, aid).entity.next_run_at == iso(15)
    frozen(14.99)
    rig.pump()
    assert rig.runs(aid) == []
    frozen(15)
    rig.pump()
    (run,) = rig.runs(aid)
    assert run.state == 'MISSION_CREATED' and run.depth == 1
    assert run.rationale['schedule'] == {'every': '15m', 'due_at': iso(15)}
    assert rig.row(entities.Automation, aid).entity.next_run_at == iso(30)
    (m,) = rig.made()
    assert m.origin_ref == run.id and m.title == 'follow up ' + aid
    rig.pump()                                                  # the same time, again
    assert len(rig.runs(aid)) == 1


def test_H02_a_restart_fires_the_times_it_missed_once_then_keeps_the_grid(archeus_home, frozen):
    rig = Rig()
    aid = rig.automation(trigger=EVERY)
    rig.close()                                     # Core stops at 09:00 for 70 minutes
    frozen(70)
    db = Database.open()
    try:
        system = Ref('system', db.writer.execute(commands.register_principal, {
            'kind': 'system', 'scopes': ('system',)})['id'])
        w = Automations(db, actor=system)
        for _ in range(3):
            w.pass_once()

        def state():
            with db.read() as conn:
                runs = [r.entity for r in rows.where(conn, entities.AutomationRun,
                                                     automation_id=aid)]
                return runs, rows.get(conn, entities.Automation, aid).entity.next_run_at
        runs, nxt = state()
        assert len(runs) == 1 and nxt == iso(75)    # four missed times: one run, not four
        assert runs[0].rationale['schedule']['due_at'] == iso(15)
        frozen(74.9)
        w.pass_once()
        assert len(state()[0]) == 1
        frozen(75)
        w.pass_once()
        runs, nxt = state()
        assert len(runs) == 2 and nxt == iso(90)
    finally:
        db.close()


def test_H03_two_workers_on_one_time_claim_it_once(rig, frozen):
    aid = rig.automation(trigger=EVERY)
    frozen(15)
    other = Automations(rig.db, actor=rig.system)
    gate = threading.Barrier(2)

    def go(w):
        gate.wait()
        w.pass_once()
    ts = [threading.Thread(target=go, args=(w,)) for w in (rig.auto, other)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    rig.pump()
    assert len(rig.runs(aid)) == 1
    with rig.db.read() as conn:
        assert len(_due_events(conn, aid)) == 1


def test_H04_the_loop_guard_still_suspends_a_schedule(rig, frozen):
    aid = rig.automation(trigger={'kind': 'schedule', 'every': '1m'}, rate_limit=1)
    for minute in (1, 2, 3, 4):
        frozen(minute)
        rig.pump()
    assert [r.reason_code for r in rig.runs(aid)] == ['allowed'] + ['rate_limited'] * 3
    assert rig.state(aid) == 'SUSPENDED'
    frozen(10)
    rig.pump()
    assert len(rig.runs(aid)) == 4                  # suspended: its times pass unclaimed


def test_H05_a_disabled_schedule_does_not_fire_and_re_enabling_restarts_its_clock(rig, frozen):
    aid = rig.automation(trigger=EVERY)
    rig.do(A.set_state, actor=rig.admin, automation_id=aid, action='disable')
    frozen(60)
    rig.pump()
    assert rig.runs(aid) == []
    rig.do(A.set_state, actor=rig.admin, automation_id=aid, action='enable')
    assert rig.row(entities.Automation, aid).entity.next_run_at == iso(75)
    rig.pump()
    assert rig.runs(aid) == []                      # no catch-up for the disabled hour


def test_H06_an_event_never_fires_a_schedule_and_its_due_event_fires_no_event_rule(rig, frozen):
    sched = rig.automation(trigger=EVERY)
    rule = rig.automation(trigger=SEED)
    rig.seed()
    rig.pump()
    assert rig.runs(sched) == [] and len(rig.runs(rule)) == 1
    frozen(15)
    rig.pump()
    assert len(rig.runs(sched)) == 1 and len(rig.runs(rule)) == 1


def test_H07_next_run_is_read_and_simulated_over_http(tc):
    made = _post(tc, '/v1/automations', {'name': 'every quarter hour', 'trigger': EVERY,
                                         'template': {'title': 't', 'objective': 'o'}})
    aid = made.json()['id']
    assert made.status == 200
    assert tc.http('GET', '/v1/automations/%s' % aid).json().get('next_run_at') is None
    _post(tc, '/v1/automations/%s/state' % aid, {'action': 'enable'})
    got = tc.http('GET', '/v1/automations/%s' % aid).json()['next_run_at']
    left = datetime.fromisoformat(got.replace('Z', '+00:00')) - datetime.now(timezone.utc)
    assert timedelta(minutes=14) < left <= timedelta(minutes=15)
    sim = tc.http('GET', '/v1/automations/%s/simulate?days=1' % aid).json()
    assert sim['scheduled'] == 96 and sim['matched'] == []
    bad = _post(tc, '/v1/automations', {'name': 'x', 'trigger': {'kind': 'schedule',
                                                                 'every': '30s'},
                                        'template': {'title': 't', 'objective': 'o'}})
    assert bad.status == 400
