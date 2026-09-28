"""P14: the event bus and automation (p14-design-gate §18, E01–E25 and X1–X4).

Each test runs the real automation consumer (`core/automation/worker.py`)
over a real archeus.db, and — where the scenario is about what happens to the
work an automation asks for — the real engine on the skeleton's stubs, so the
mission it creates walks P7 → P8 → P9 → P10 → P11 → P13 like any other.
"""

import os
import threading

import pytest

from archeus.core.application import authorization, automations as A, commands, queries
from archeus.core.application import resources, work
from archeus.core.automation import matcher
from archeus.core.automation.worker import CONSUMER, MAX_ATTEMPTS, Automations
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.routing.usage import FakeUsageFeed
from archeus.harnesses.fake import FakeHarness
from archeus.harnesses.registry import AdapterRegistry
from archeus.infra import paths
from archeus.infra.db import Database, rows
from archeus.infra.eventlog import consumers

from .test_skeleton import Core, SpyPolicy

FOLLOW = {'title': 'follow up {subject.id}', 'objective': 'look at {event.type} #{event.seq}'}
SEED = {'type': 'mission.created', 'where': {'title': 'seed'}}


class Rig(Core):
    """The skeleton's Core plus an admin device and the automation consumer."""

    def __init__(self, real_router=False, **kw):
        super().__init__(**kw)
        if real_router:             # P10's router, recording its decisions
            registry = AdapterRegistry(self.policy)
            registry.register(FakeHarness())
            self.work = work.Work(missions=self.missions,
                                  router=resources.ResourceRouter(registry, FakeUsageFeed()))
            self.engine = self.build_engine()
        self.admin = Ref('user_device', self.db.writer.execute(commands.register_principal, {
            'kind': 'user_device', 'scopes': ('observe', 'control', 'approve', 'admin')})['id'])
        self.auto = Automations(self.db, actor=self.system, retry_s=0)

    def automation(self, trigger=SEED, template=FOLLOW, enable=True, **kw):
        aid = self.do(A.create, actor=self.admin, name='rule', trigger=trigger,
                      template=template, **kw)['id']
        if enable:
            self.do(A.set_state, actor=self.admin, automation_id=aid, action='enable')
        return aid

    def seed(self, title='seed', project_id=None):
        return self.do(commands.create_mission, title=title, objective='o',
                       project_id=project_id)['id']

    def pump(self, limit=50):
        """Deliver until the consumer has nothing left and holds nothing."""
        for _ in range(limit):
            if not self.auto.pass_once()['changed'] and not self.auto.pending() \
                    and not self.auto.retrying:
                return
        raise AssertionError('the automation consumer did not settle')

    def runs(self, aid=None):
        return self.all(entities.AutomationRun, **({'automation_id': aid} if aid else {}))

    def state(self, aid):
        return self.row(entities.Automation, aid).entity.state

    def made(self):
        return [m for m in self.all(entities.Mission) if m.origin == 'automation']

    def raw(self, type_, subject, payload, *, actor=None, project=None):
        """An event appended as a producer would, with whatever envelope."""
        def cmd(tx, *, actor):
            return tx.append(new_event(type_, subject, actor, payload=payload,
                                       project=project)).seq
        return self.db.writer.execute(cmd, {'actor': actor or self.user})


@pytest.fixture
def rig(archeus_home):
    r = Rig()
    yield r
    r.close()


def _project(tx, *, actor, name):
    p = entities.Project(id=ids.new_id('project'), workspace_id=ids.GLOBAL_WORKSPACE, name=name)
    tx.insert(p, actor=actor)
    tx.append(new_event('project.created', Ref('project', p.id), actor, project=p.id))
    return p.id


# ── durability and delivery (§4, §5) ─────────────────────────────────────────

def test_E01_a_committed_event_survives_a_restart_before_the_consumer_ran(archeus_home):
    rig = Rig()
    aid = rig.automation()
    mid = rig.seed()
    rig.close()                                 # Core stops: the consumer never ran
    db = Database.open()
    try:
        system = Ref('system', db.writer.execute(commands.register_principal, {
            'kind': 'system', 'scopes': ('system',)})['id'])
        w = Automations(db, actor=system)
        while w.pass_once()['changed']:
            pass
        with db.read() as r:
            (run,) = [x.entity for x in rows.where(r, entities.AutomationRun)]
        assert (run.automation_id, run.state) == (aid, 'MISSION_CREATED')
        assert run.rationale['where'] == {'title': {'test': 'seed', 'value': 'seed'}}
        assert run.triggering_event_seq > 0 and run.depth == 1
        assert mid != run.mission_id
    finally:
        db.close()


def test_E02_a_duplicate_delivery_has_one_effect(rig):
    rig.automation()
    rig.seed()
    (seq,) = [e['seq'] for e in rig.events() if e['type'] == 'mission.created']
    first = rig.do(A.react, actor=rig.system, seq=seq)
    again = rig.do(A.react, actor=rig.system, seq=seq)
    rig.pump()
    assert len(first['runs']) == 1 and again['runs'] == []
    assert len(rig.runs()) == 1 and len(rig.made()) == 1


def test_E03_a_crash_after_the_effect_before_the_ack_repeats_nothing(rig):
    rig.automation()
    rig.seed()
    (seq,) = [e['seq'] for e in rig.events() if e['type'] == 'mission.created']
    rig.do(A.react, actor=rig.system, seq=seq)          # the effect committed, then "crash"
    with rig.db.read() as r:
        assert consumers.cursor(r, CONSUMER) == 0       # no effect row, no cursor move
    rig.pump()                                          # redelivered from the cursor
    assert len(rig.runs()) == 1 and len(rig.made()) == 1


# ── what fires (§7, E04–E06) ─────────────────────────────────────────────────

def test_E05_a_disabled_or_archived_automation_does_not_fire(rig):
    off = rig.automation()
    gone = rig.automation()
    rig.do(A.set_state, actor=rig.admin, automation_id=off, action='disable')
    rig.do(A.set_state, actor=rig.admin, automation_id=gone, action='disable')
    rig.do(A.set_state, actor=rig.admin, automation_id=gone, action='archive')
    rig.seed()
    rig.pump()
    assert rig.runs() == [] and rig.made() == []
    draft = rig.automation(enable=False)
    rig.seed()
    rig.pump()
    assert rig.runs(draft) == []


def test_E06_an_event_outside_the_trigger_or_its_scope_does_not_fire(rig):
    rig.automation()
    p = rig.do(_project, actor=rig.user, name='elsewhere')
    rig.seed(title='not seed')                          # the predicate fails
    rig.seed(project_id=p)                              # another scope
    rig.seed()
    rig.pump()
    assert len(rig.runs()) == 1                         # only the in-scope, matching one


def test_X1_enabling_never_replays_what_happened_before(rig):
    aid = rig.automation(enable=False)
    rig.seed()
    rig.do(A.set_state, actor=rig.admin, automation_id=aid, action='enable')
    rig.pump()
    assert rig.runs() == []
    rig.seed()
    rig.pump()
    assert len(rig.runs()) == 1


# ── the chain after the request stays P7–P13's (E07–E14) ────────────────────

def test_E07_E08_automated_work_meets_the_plan_gate_and_cannot_approve_itself(archeus_home):
    rig = Rig(policy=SpyPolicy('ASK'))
    try:
        aid = rig.automation()
        rig.seed()
        rig.pump()
        (m,) = rig.made()
        out = rig.engine.run(m.id)
        assert (out['state'], out['stop']) == ('APPROVAL_REQUIRED', 'approval_required')
        assert rig.all(entities.Execution) == []
        a = rig.pending(m.id)
        me = Ref('automation', rig.row(entities.Automation, aid).entity.principal_id)
        with pytest.raises(authorization.NotPermitted):
            rig.do(authorization.decide, actor=me, policy=rig.policy, missions=rig.missions,
                   approval_id=a.id, decision='approve', action_hash=a.action_hash)
        assert rig.pending(m.id).state == 'PENDING'
        rig.pump()          # the mission moved but did not settle: neither does its run
        assert [r.state for r in rig.runs(aid)] == ['MISSION_CREATED']
    finally:
        rig.close()


def test_E09_E10_E15_E25_automated_work_is_routed_executed_verified_and_explained(
        archeus_home):
    rig = Rig(real_router=True)
    try:
        _explained(rig)
    finally:
        rig.close()


def _explained(rig):
    aid = rig.automation()
    rig.seed()
    rig.pump()
    (m,) = rig.made()
    assert rig.engine.run(m.id)['state'] == 'COMPLETED'
    rig.pump()
    (run,) = rig.runs(aid)
    assert (run.state, run.reason_code, run.mission_id) == ('SUCCEEDED', 'mission_completed',
                                                            m.id)
    with rig.db.read() as r:
        why = A.explain(r, run.id)
    trigger = why['event']
    assert trigger['type'] == 'mission.created' and trigger['seq'] == run.triggering_event_seq
    assert why['automation']['id'] == aid and why['why']['rationale']['type'] == 'mission.created'
    mission = why['mission']
    assert mission['origin'] == 'automation' and mission['origin_ref'] == run.id
    (ex,) = mission['executions']
    (route,) = [d for d in mission['routes'] if d['subject']['id'] == ex['task_id']]
    assert ex['route_decision_id'] == route['id']               # P10 chose, P11 ran it
    assert ex['state'] == 'ENDED_OK'
    assert 'plan' in {d['stage'] for d in mission['policy_decisions']}       # P9 judged
    assert any(v['state'] == 'PASSED' for v in mission['verifications'])     # P13 verified
    assert [r['state'] for r in mission['reviews']] == ['ACCEPTED']
    # the mission's creation names its cause: the triggering event, by id
    (created,) = [e for e in rig.events() if e['type'] == 'mission.created'
                  and e['subject']['id'] == m.id]
    assert created['cause_chain'][-1] == trigger['id']
    assert created['actor'] == {'kind': 'automation', 'id': why['automation']['principal_id']}


def test_E11_E14_a_template_asks_for_a_mission_and_nothing_else(rig):
    for extra in ('verification', 'verdict', 'model', 'harness', 'account', 'autonomy_profile',
                  'plan', 'approval', 'resource_preferences'):
        with pytest.raises(ValueError, match='cannot carry'):
            rig.do(A.create, actor=rig.admin, name='x', trigger=SEED,
                   template=dict(FOLLOW, **{extra: 'anything'}))
    rig.automation()
    rig.seed()
    before = len(rig.events())
    rig.pump()
    written = {e['type'] for e in rig.events()[before:]}
    assert written == {'automation_run.created', 'automation_run.state_changed',
                       'mission.created'}
    assert rig.all(entities.Verification) == [] and rig.all(entities.Review) == []


def test_E12_a_verification_failure_asks_for_a_follow_up_mission(archeus_home):
    rig = Rig()
    try:
        aid = rig.automation(trigger={'type': 'verification.state_changed',
                                      'where': {'to': 'FAILED'}})
        mid = rig.do(commands.create_mission, title='work', objective='o', max_replans=0,
                     success_criteria=[{'text': 'it passes', 'check': 'automatic'}])['id']
        rig.verifier.failing.add(mid)
        rig.engine.run(mid)
        rig.pump()
        (run,) = rig.runs(aid)
        assert run.state == 'MISSION_CREATED'
        (v,) = [x for x in rig.all(entities.Verification) if x.state == 'FAILED']
        assert rig.row(entities.Mission, run.mission_id).entity.title == 'follow up ' + v.id
        assert rig.row(entities.Verification, v.id).entity.state == 'FAILED'    # untouched
    finally:
        rig.close()


def test_E13_the_mission_an_automation_asks_for_starts_with_no_session(rig):
    rig.automation()
    rig.seed()
    rig.pump()
    (m,) = rig.made()
    assert rig.all(entities.Session) == []
    assert m.state == 'CREATED'


# ── loops, rates, suspension (§10, E16, S10b) ────────────────────────────────

def test_E16_a_self_triggering_automation_escalates_at_depth_three_then_suspends(rig):
    aid = rig.automation(trigger={'type': 'mission.created'}, rate_limit=50)
    rig.seed()
    rig.pump()
    runs = rig.runs(aid)
    assert [(r.depth, r.state) for r in runs] == [
        (1, 'MISSION_CREATED'), (2, 'MISSION_CREATED'), (3, 'MISSION_CREATED'),
        (4, 'ESCALATED')]
    assert 'escalated to you, not dropped' in runs[-1].reason
    assert len(rig.made()) == 3 and rig.state(aid) == 'ENABLED'
    rig.seed()
    rig.seed()
    rig.pump()
    assert sum(r.state == 'ESCALATED' for r in rig.runs(aid)) == 3
    assert rig.state(aid) == 'SUSPENDED'
    rig.seed()
    rig.pump()
    assert sum(r.state == 'ESCALATED' for r in rig.runs(aid)) == 3        # fires nothing now
    # X3: re-enabling re-arms it; the backlog it missed is not replayed
    rig.do(A.set_state, actor=rig.admin, automation_id=aid, action='enable')
    count = len(rig.runs(aid))
    rig.pump()
    assert len(rig.runs(aid)) == count and rig.state(aid) == 'ENABLED'


def test_the_rate_limit_skips_and_three_rate_limited_runs_suspend(rig):
    aid = rig.automation(rate_limit=2)
    for _ in range(3):
        rig.seed()
    rig.pump()
    assert [r.state for r in rig.runs(aid)] == ['MISSION_CREATED', 'MISSION_CREATED',
                                                'SKIPPED']
    assert rig.runs(aid)[-1].reason_code == 'rate_limited'
    for _ in range(2):
        rig.seed()
    rig.pump()
    assert rig.state(aid) == 'SUSPENDED'


# ── faults: retry, quarantine, replay, concurrency, order (§6, §11) ──────────

def _failing(monkeypatch, times, only=None):
    real, seen = A.react, []

    def react(tx, *, actor, seq):
        if (only is None or seq in only) and seen.count(seq) < times:
            seen.append(seq)
            raise RuntimeError('boom at %d' % seq)
        return real(tx, actor=actor, seq=seq)
    monkeypatch.setattr(A, 'react', react)
    return seen


def test_E17_a_failed_reaction_is_held_and_retried(rig, monkeypatch):
    rig.automation()
    rig.seed()
    seen = _failing(monkeypatch, 1)
    rig.auto.pass_once()
    assert [a for a, _ in rig.auto.retrying.values()] == [1] and rig.runs() == []
    rig.pump()
    assert len(seen) == 1 and len(rig.runs()) == 1 and rig.auto.retrying == {}


def test_E18_a_reaction_that_keeps_failing_is_quarantined_not_retried_forever(rig, monkeypatch):
    rig.automation()
    rig.seed()
    (seq,) = [e['seq'] for e in rig.events() if e['type'] == 'mission.created']
    seen = _failing(monkeypatch, 99, only={seq})
    rig.pump()
    assert seen == [seq] * MAX_ATTEMPTS and rig.runs() == []
    with rig.db.read() as r:
        listed = A.list_automations(r)['quarantined']
        assert consumers.cursor(r, CONSUMER) >= seq          # the log moved past it
    assert [q['seq'] for q in listed] == [seq] and 'boom' in listed[0]['error']
    assert rig.auto.detail()['quarantined'] == 1
    rig.seed()                                               # later events still work
    rig.pump()
    assert len(rig.runs()) == 1


def test_E19_replaying_the_log_repeats_nothing(rig):
    rig.automation()
    rig.seed()
    rig.pump()
    before = (len(rig.runs()), len(rig.made()))

    def rewind(tx, *, actor):
        tx.execute('DELETE FROM consumer_effects WHERE consumer = ?', (CONSUMER,))
        tx.execute('UPDATE consumer_cursors SET last_seq = 0 WHERE name = ?', (CONSUMER,))
    rig.db.writer.execute(rewind, {'actor': rig.system})
    rig.pump()
    assert (len(rig.runs()), len(rig.made())) == before


def test_E20_concurrent_deliveries_of_one_event_claim_one_run(rig):
    rig.automation()
    rig.seed()
    (seq,) = [e['seq'] for e in rig.events() if e['type'] == 'mission.created']
    go = threading.Barrier(4)

    def hit():
        go.wait()
        rig.db.writer.execute(A.react, {'actor': rig.system, 'seq': seq})
    ts = [threading.Thread(target=hit) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    other = Automations(rig.db, actor=rig.system)
    ts = [threading.Thread(target=w.pass_once) for w in (rig.auto, other)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    rig.pump()
    assert len(rig.runs()) == 1 and len(rig.made()) == 1


def test_E21_a_held_event_blocks_the_ones_after_it(rig, monkeypatch):
    aid = rig.automation()
    rig.seed()
    rig.seed()
    first, second = [e['seq'] for e in rig.events() if e['type'] == 'mission.created']
    rig.auto.retry_s = 3600                                   # hold it for the hour
    _failing(monkeypatch, 1, only={first})
    rig.auto.pass_once()
    assert first in rig.auto.retrying and rig.runs() == []    # the second did not overtake
    rig.auto.retrying[first] = (1, 0)                         # the hour passes
    rig.pump()
    assert [r.triggering_event_seq for r in rig.runs(aid)] == [first, second]


def test_E22_a_stale_state_event_does_not_ask_for_work(rig):
    aid = rig.automation(trigger={'type': 'mission.state_changed',
                                  'where': {'to': 'UNDERSTANDING'}})
    mid = rig.seed()
    rig.engine.step(mid)                                      # CREATED -> UNDERSTANDING
    rig.engine.step(mid)                                      # -> CONTEXT_GATHERING
    rig.pump()
    (run,) = rig.runs(aid)
    assert (run.state, run.reason_code) == ('SKIPPED', 'condition_false')
    assert run.reason.startswith('stale: mission %s is CONTEXT_GATHERING' % mid)
    fresh = rig.seed()
    rig.engine.step(fresh)
    rig.pump()
    assert rig.runs(aid)[-1].state == 'MISSION_CREATED'


def test_E23_a_projects_event_never_fires_another_projects_automation(rig):
    a = rig.do(_project, actor=rig.user, name='A')
    b = rig.do(_project, actor=rig.user, name='B')
    aid = rig.automation(project_id=b)
    ma = rig.seed(project_id=a)
    # a producer that writes the wrong scope on the envelope changes nothing:
    # the scope is the mission's
    rig.raw('mission.created', Ref('mission', ma), {'title': 'seed'}, project=b)
    rig.pump()
    assert rig.runs(aid) == []
    rig.seed(project_id=b)
    rig.pump()
    (run,) = rig.runs(aid)
    assert rig.row(entities.Mission, run.mission_id).entity.project_id == b


def test_E24_restart_during_the_automated_work_settles_the_run_once(rig):
    aid = rig.automation()
    rig.seed()
    rig.pump()
    (m,) = rig.made()
    rig.until(m.id, lambda x: x.state == 'EXECUTING')
    rig.engine = rig.build_engine()                           # a new Core's engine
    rig.engine.reconcile_orphans()
    assert rig.engine.run(m.id)['state'] == 'COMPLETED'
    rig.pump()
    rig.auto = Automations(rig.db, actor=rig.system)          # and a new consumer
    rig.pump()
    (run,) = rig.runs(aid)
    assert run.state == 'SUCCEEDED'
    settles = [e for e in rig.events() if e['type'] == 'automation_run.state_changed'
               and e['payload']['to'] == 'SUCCEEDED']
    assert len(settles) == 1


# ── who may cause work (§13, D9, D13, D17) ───────────────────────────────────

def test_X2_an_event_caused_by_an_execution_asks_for_nothing(rig):
    aid = rig.automation()
    mid = rig.seed(title='other')
    agent = Ref('execution', ids.new_id('principal'))
    rig.raw('mission.created', Ref('mission', mid), {'title': 'seed'}, actor=agent)
    rig.pump()
    (run,) = rig.runs(aid)
    assert (run.state, run.reason_code) == ('SKIPPED', 'denied') and rig.made() == []


def test_X4_while_disarmed_every_run_is_denied_and_the_automation_stays_enabled(rig):
    aid = rig.automation()
    os.makedirs(os.path.dirname(paths.stop_sentinel()), exist_ok=True)
    open(paths.stop_sentinel(), 'w').close()
    try:
        rig.seed()
        rig.pump()
    finally:
        os.remove(paths.stop_sentinel())
    (run,) = rig.runs(aid)
    assert (run.state, run.reason) == ('SKIPPED', 'Core is disarmed (e-stop): no work is '
                                                  'requested')
    assert rig.state(aid) == 'ENABLED' and rig.made() == []


def test_D13_only_a_user_device_with_admin_writes_or_enables_an_automation(rig):
    with pytest.raises(authorization.NotPermitted):
        rig.do(A.create, name='x', trigger=SEED, template=FOLLOW)       # control, no admin
    aid = rig.automation(enable=False)
    me = Ref('automation', rig.row(entities.Automation, aid).entity.principal_id)
    for actor in (me, rig.system):
        with pytest.raises(authorization.NotPermitted):
            rig.do(A.set_state, actor=actor, automation_id=aid, action='enable')
        with pytest.raises(authorization.NotPermitted):
            rig.do(A.create, actor=actor, name='x', trigger=SEED, template=FOLLOW)
    assert rig.state(aid) == 'DRAFT'
    with pytest.raises(matcher.Invalid, match='loop by construction'):
        rig.do(A.create, actor=rig.admin, name='x', template=FOLLOW,
               trigger={'type': 'automation_run.state_changed'})


def test_the_simulation_reads_the_log_and_writes_nothing(rig):
    aid = rig.automation(enable=False)
    rig.seed()
    rig.seed(title='other')
    before = len(rig.events())
    with rig.db.read() as r:
        sim = A.simulate(r, aid, now=queries._now())
    assert [h['rationale']['where'] for h in sim['matched']] == [
        {'title': {'test': 'seed', 'value': 'seed'}}]
    assert sim['examined'] == 2 and len(rig.events()) == before
