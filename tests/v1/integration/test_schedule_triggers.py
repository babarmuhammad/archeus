"""P21 slice H: schedule triggers and `next_run_at` (p21-design-gate D9, ADR-0020,
ADR-0030 §4, state-machines §8 claim-and-advance).

The real automation worker over a real archeus.db, on a frozen clock: Core's
one clock is `events.now_iso`, which every transaction's `now` reads (the
fixture is not called `clock`: conftest's `clock` is the launch clock `tc` takes).
"""

import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

from archeus.core.application import automations as A, commands
from archeus.core.automation.worker import MAX_ATTEMPTS, Automations
from archeus.core.domain import entities, events
from archeus.core.domain.values import Ref
from archeus.infra import paths
from archeus.infra.db import Database, rows

from .test_automation import FOLLOW, SEED, Rig, _project
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


def _api_next(rig, aid):
    with rig.db.read() as conn:
        return A.get_automation(conn, aid, runs=0)['next_run_at']


def _api_waiting(rig, aid):
    with rig.db.read() as conn:
        return A.get_automation(conn, aid, runs=0,
                                schedule_faults=rig.auto.quarantined_schedules())['waiting']


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
    assert run.rationale['schedule'] == {'every': '15m', 'due_at': iso(15), 'missed': 0}
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
        assert runs[0].rationale['schedule'] == {'every': '15m', 'due_at': iso(15), 'missed': 3}
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
    # a second worker that read the time as due before the first commit reaches the
    # writer after it, every run: its claim must find the time already moved on
    late = rig.db.writer.execute(A.fire_due, {'actor': rig.system, 'automation_id': aid})
    assert late == {'runs': []}
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
    assert _api_next(rig, aid) is None
    frozen(10)
    rig.pump()
    assert len(rig.runs(aid)) == 4                  # suspended: its times pass unclaimed


def test_H05_a_disabled_schedule_does_not_fire_and_re_enabling_restarts_its_clock(rig, frozen):
    aid = rig.automation(trigger=EVERY)
    rig.do(A.set_state, actor=rig.admin, automation_id=aid, action='disable')
    frozen(60)
    rig.pump()
    assert rig.runs(aid) == []
    assert _api_next(rig, aid) is None              # the API does not report a time it will not keep
    rig.do(A.set_state, actor=rig.admin, automation_id=aid, action='enable')
    assert rig.row(entities.Automation, aid).entity.next_run_at == iso(75)
    assert _api_next(rig, aid) == iso(75)
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


def test_H08_a_mission_a_schedule_asked_for_starts_a_rule_one_level_deeper(rig, frozen):
    sched = rig.automation(trigger=EVERY)
    rule = rig.automation(trigger={'kind': 'event', 'type': 'mission.created',
                                   'where': {'title': {'glob': 'follow up*'}}},
                          template={'title': 'chained', 'objective': 'o'})
    frozen(15)
    rig.pump()
    (srun,) = rig.runs(sched)
    (rrun,) = rig.runs(rule)
    assert srun.depth == 1 and rrun.depth == 2 and rrun.state == 'MISSION_CREATED'
    assert rrun.triggering_event_seq > srun.triggering_event_seq


def test_H09_a_fire_does_not_stale_a_persons_version(rig, frozen):
    aid = rig.automation(trigger=EVERY)
    before = rig.row(entities.Automation, aid).version
    frozen(15)
    rig.pump()
    assert rig.row(entities.Automation, aid).version == before     # the time moved, not the row's version
    rig.do(A.set_state, actor=rig.admin, automation_id=aid, action='disable',
           expected_version=before)                                  # a read before the fire still works
    assert rig.state(aid) == 'DISABLED'


def _archive(tx, *, actor, project_id, state):
    tx.update(entities.Project, project_id, {'state': state}, actor=actor)
    tx.append(events.new_event('project.changed', Ref('project', project_id), actor,
                               payload={'state': state}, project=project_id))


def test_H10_a_schedule_of_an_archived_project_or_while_disarmed_waits_and_fires_once(rig, frozen):
    pid = rig.do(_project, actor=rig.user, name='A')
    aid = rig.automation(trigger={'kind': 'schedule', 'every': '1m'}, project_id=pid)
    rig.do(_archive, actor=rig.admin, project_id=pid, state='ARCHIVED')
    for minute in (1, 2):
        frozen(minute)
        rig.pump()
    assert rig.runs(aid) == []                       # no condition_false run per period
    assert rig.row(entities.Automation, aid).entity.next_run_at == iso(1)
    assert _api_waiting(rig, aid) == 'project gone or archived'
    rig.do(_archive, actor=rig.admin, project_id=pid, state='ACTIVE')
    frozen(3)
    rig.pump()
    (run,) = rig.runs(aid)
    assert run.rationale['schedule'] == {'every': '1m', 'due_at': iso(1), 'missed': 2}
    assert _api_waiting(rig, aid) is None
    os.makedirs(os.path.dirname(paths.stop_sentinel()), exist_ok=True)
    open(paths.stop_sentinel(), 'w').close()         # disarmed (e-stop)
    try:
        frozen(4)
        rig.pump()
        assert len(rig.runs(aid)) == 1
        assert _api_waiting(rig, aid) == 'Core disarmed'
    finally:
        os.remove(paths.stop_sentinel())
    frozen(4)
    rig.pump()
    assert [r.state for r in rig.runs(aid)] == ['MISSION_CREATED', 'MISSION_CREATED']


def test_H11_a_schedule_whose_claim_raises_holds_only_itself(rig, frozen, monkeypatch):
    bad = rig.automation(trigger=EVERY)
    good = rig.automation(trigger=EVERY)
    frozen(15)
    real, calls = A._claim, []

    def claim(tx, actor, a, e, why):
        if a.id == bad:
            calls.append(a.id)
            raise RuntimeError('a claim that always faults')
        return real(tx, actor, a, e, why)
    monkeypatch.setattr(A, '_claim', claim)
    for _ in range(5):
        rig.auto.pass_once()
    assert len(rig.runs(good)) == 1                  # not held behind the faulty schedule
    assert rig.runs(bad) == []
    assert len(calls) == MAX_ATTEMPTS                # then quarantined, not retried every pass
    assert rig.row(entities.Automation, bad).entity.next_run_at == iso(15)   # rolled back
    assert _api_waiting(rig, bad) == ('quarantined after %d failures: RuntimeError: '
                                      'a claim that always faults' % MAX_ATTEMPTS)
    assert _api_waiting(rig, good) is None
