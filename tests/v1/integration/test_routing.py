"""P10 on the real database (p10-design-gate §17, I-*): the dispatch path
through the resource router, the P9 -> P10 contract, fallback and the route
approval, provider terms at the adapter, immutable history, usage attributed
to its decision, registration, continuity, the mission's own resources. Every
command goes through the writer, one transaction each, as Core runs them."""

import dataclasses

import pytest

from archeus.core import calls as OC
from archeus.core import engine, ports
from archeus.core.application import authorization, calls as C, commands, resources, work
from archeus.core.application.authorization import NotPermitted
from archeus.core.application.work import PolicyDenied
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.policy.engine import PolicyEngine
from archeus.core.routing import router as R
from archeus.core.routing.usage import FakeUsageFeed
from archeus.harnesses import base
from archeus.harnesses.fake import FakeCaller, FakeHarness
from archeus.harnesses.registry import AdapterRegistry
from archeus.infra.db import rows
from archeus.infra.db.writer import InvalidTransition

from v1.integration.test_policy import Rig as PolicyRig, task


class Rig(PolicyRig):
    """test_policy's rig on the real router: the registry's fake harness, a
    scripted usage feed, and a user device for resource changes."""

    def __init__(self, db, adapters=None):
        super().__init__(db)
        self.feed = FakeUsageFeed()
        self.registry = AdapterRegistry(self.policy)
        for a in adapters or [FakeHarness()]:
            self.registry.register(a)
        self.router = resources.ResourceRouter(self.registry, self.feed)
        self.work = work.Work(missions=self.missions, router=self.router)

    def account(self, label, harness_id='fake', auth=True, home_ref=None, **policy):
        a = self.do(resources.register_account, who=self.user, harness_id=harness_id,
                    label=label, auth_kind='api_key', home_ref=home_ref,
                    auth=None if auth is None else {'ok': auth, 'detail': 'probe'})
        if policy:
            self.do(resources.set_resource_policy, who=self.user, account_id=a['id'], **policy)
        return a['id']

    def ready(self, *tasks_, title='M'):
        mid = self.mission(title)
        out = self.propose(mid, *(tasks_ or [task('t1', 'write_repo')]))
        assert out['mission']['state'] == 'APPROVED', out
        self.do(self.missions.fire, mission_id=mid, trigger='dispatch', reason='go')
        self.do(self.work.ready_tasks, mission_id=mid)
        return mid

    def dispatch(self, mid, key='t1'):
        (t,) = [x for x in self.all(entities.Task, mission_id=mid) if x.key == key]
        return self.do(self.work.dispatch_task, task_id=t.id)

    def finish(self, out, usage=None):
        self.do(self.work.record_spawn, execution_id=out['execution_id'], pid=1, create_time=1.0)
        self.do(self.work.record_exit, execution_id=out['execution_id'], exit_reason='ok',
                exit_code=0, usage=usage)

    def rds(self, **eq):
        return self.all(entities.RouteDecision, **eq)


@pytest.fixture
def r(db):
    return Rig(db)


@pytest.fixture
def spy(monkeypatch):
    """Every call the router engine receives."""
    calls = []
    real = R.route
    monkeypatch.setattr(R, 'route', lambda req, snap: calls.append(req) or real(req, snap))
    return calls


# ── I-A the P9 -> P10 contract ──────────────────────────────────────────────

def test_I_A1_an_authorised_task_routes_and_the_decision_names_its_authorisation(r):
    acc = r.account('Work')
    mid = r.ready()
    out = r.dispatch(mid)
    (e,) = r.all(entities.Execution, mission_id=mid)
    (rd,) = r.rds(mission_id=mid)
    (pd,) = [d for d in r.all(entities.PolicyDecision, mission_id=mid) if d.stage == 'dispatch']
    assert (e.route_decision_id, e.account_id, e.harness_id) == (rd.id, acc, 'fake')
    assert (rd.result, rd.selected, rd.policy_decision_id, rd.decided_by) == (
        'selected', acc, pd.id, 'router')
    assert pd.outcome == 'covered' and out['route_decision_id'] == rd.id
    assert [x['payload']['account_id'] for x in r.events('route.decided')] == [acc]


def test_I_A2_a_denied_task_is_never_routed(r, spy):
    r.account('Work')
    mid = r.ready()
    r.rule('MISSION', 'write_repo', 'DENY', scope_ref=mid)
    with pytest.raises(PolicyDenied):
        r.dispatch(mid)
    assert spy == [] and r.rds(mission_id=mid) == [] and r.all(entities.Execution) == []


def test_I_A3_a_task_waiting_on_an_approval_is_never_routed(r, spy):
    r.account('Work')
    mid = r.ready()
    r.rule('MISSION', 'write_repo', 'ASK', scope_ref=mid)
    out = r.dispatch(mid)
    assert out['authorization']['outcome'] == 'asked' and r.pending(mid).kind == 'task'
    assert spy == [] and r.rds(mission_id=mid) == []


def test_I_A4_a_stale_superseded_or_foreign_authorisation_cannot_route(r):
    mid = r.ready(task('t1', 'write_repo'), task('t2', 'write_repo'))
    t1, t2 = sorted(r.all(entities.Task, mission_id=mid), key=lambda t: t.key)

    def auth(t, **kw):
        return r.db.writer.execute(lambda tx, actor: authorization.check_dispatch(
            tx, actor=actor, policy=r.policy, missions=r.missions, mission=r.m(mid),
            plan=commands.active_plan(tx.conn, mid).entity, task=t), {'actor': r.system})

    first, second = auth(t1)['policy_decision_id'], auth(t1)['policy_decision_id']
    other = auth(t2)['policy_decision_id']
    r.rule('TASK', 'write_repo', 'ASK', scope_ref=t2.id)
    asked = auth(t2)
    assert asked['outcome'] == 'asked'
    with r.db.read() as c:
        plan = commands.active_plan(c, mid).entity
        assert resources.current_authorization(c, t1, plan, second).id == second
        for bad, why in ((None, 'no authorisation'), (first, 'superseded'),
                         (other, 'does not authorise')):
            with pytest.raises(resources.NotAuthorised, match=why):
                resources.current_authorization(c, t1, plan, bad)
        with pytest.raises(resources.NotAuthorised, match='does not authorise'):
            resources.current_authorization(c, t2, plan, asked['policy_decision_id'])
        stale = dataclasses.replace(plan, digest='0' * 64)
        with pytest.raises(resources.NotAuthorised, match='another plan version'):
            resources.current_authorization(c, t1, stale, second)


def test_I_A6_a_forged_covered_decision_that_carries_a_deny_cannot_route(r):
    """X: a record claiming `covered` over a DENY item (no P9 path writes one)
    is refused by the router's own check, not trusted."""
    mid = r.ready()
    (t,) = r.all(entities.Task, mission_id=mid)
    with r.db.read() as c:
        plan = commands.active_plan(c, mid).entity
    forged = entities.PolicyDecision(
        id=ids.new_id('policy_decision'),
        decision='ALLOW', stage='dispatch', outcome='covered', mission_id=mid,
        plan_id=plan.id, plan_digest=plan.digest, task_id=t.id,
        items=({'class': 'write_repo', 'decision': 'DENY', 'boundary': None},))
    r.db.writer.execute(lambda tx, actor: (tx.insert(forged, actor=actor), tx.append(new_event(
        'policy_decision.created', Ref('policy_decision', forged.id), actor))),
        {'actor': r.system})
    with r.db.read() as c:
        with pytest.raises(resources.NotAuthorised, match='denies'):
            resources.current_authorization(c, t, plan, forged.id)


def test_I_A5_routing_writes_no_policy_decision_rule_or_approval(r):
    r.account('Work')
    mid = r.ready()
    before = [len(r.all(k)) for k in (entities.PolicyDecision, entities.PolicyRule,
                                      entities.Approval)]
    with r.db.read() as c:
        t = r.all(entities.Task, mission_id=mid)[0]
        plan = commands.active_plan(c, mid).entity
    r.db.writer.execute(lambda tx, actor: authorization.check_dispatch(
        tx, actor=actor, policy=r.policy, missions=r.missions, mission=r.m(mid), plan=plan,
        task=t), {'actor': r.system})
    after_auth = [len(r.all(k)) for k in (entities.PolicyDecision, entities.PolicyRule,
                                          entities.Approval)]
    out = r.dispatch(mid)
    after = [len(r.all(k)) for k in (entities.PolicyDecision, entities.PolicyRule,
                                     entities.Approval)]
    assert out['execution_id'] and after_auth[1:] == before[1:]
    # the dispatch's own P9 check is the one decision; routing added none
    assert after == [after_auth[0] + 1, before[1], before[2]]


# ── I-F fallback and the route approval (resource-router §7) ───────────────

def _limited(r, fallback):
    a = r.account('A', priority=1)
    b = r.account('B', priority=2, fallback=fallback)
    r.feed.set(a, '5h', 100)
    r.feed.set(b, '5h', 79)
    return a, b


def test_I_F1_fallback_allow_runs_there_and_says_so(r):
    a, b = _limited(r, 'allow')
    out = r.dispatch(r.ready())
    (rd,) = r.rds()
    assert (out['account_id'], rd.result, rd.selected) == (b, 'fallback', b)
    assert list(rd.fallback_from) == [a]          # A was exhausted; B is the fallback
    assert 'fell back' in rd.explanation


def test_I_F2_fallback_ask_asks_through_p9_and_only_a_user_device_answers(r):
    a, b = _limited(r, 'ask')
    mid = r.ready()
    out = r.dispatch(mid)
    ap = r.pending(mid)
    t = r.all(entities.Task, mission_id=mid)[0]
    assert (out['execution_id'], out['state']) == (None, 'AWAITING_APPROVAL')
    assert (ap.kind, ap.task_id, ap.state, ap.items[0]['resource']['account']) == (
        'route', t.id, 'PENDING', b)
    assert r.m(mid).state == 'BLOCKED' and r.all(entities.Execution) == []
    with pytest.raises(NotPermitted):
        r.decide(ap, who=r.system)
    with pytest.raises(NotPermitted):
        r.decide(ap, who=r.brain)
    assert r.decide(ap)['mission']['state'] == 'EXECUTING'
    assert r.all(entities.Task, mission_id=mid)[0].state == 'READY'
    out = r.dispatch(mid)
    assert out['account_id'] == b and r.rds()[-1].result == 'fallback'
    assert 'approved' in r.rds()[-1].explanation


def test_I_F3_a_rejected_fallback_leaves_the_task_blocked_and_runs_nothing(r):
    _limited(r, 'ask')
    mid = r.ready()
    r.dispatch(mid)
    r.decide(r.pending(mid), 'reject')
    assert r.all(entities.Task, mission_id=mid)[0].state == 'BLOCKED'
    assert r.m(mid).state == 'BLOCKED' and r.all(entities.Execution) == []


def test_I_F4_nothing_eligible_blocks_the_mission_and_a_resume_routes_again(r):
    a, b = _limited(r, 'deny')
    mid = r.ready()
    out = r.dispatch(mid)
    assert out['state'] == 'BLOCKED' and r.m(mid).state == 'BLOCKED'
    r.feed.set(b, '5h', 10)
    r.do(r.missions.resume, who=r.user, mission_id=mid)
    assert r.do(r.work.ready_tasks, mission_id=mid)['ready']
    assert r.dispatch(mid)['account_id'] == b


# ── I-T provider terms at the adapter (ADR-0021) ───────────────────────────

class GatedHarness(FakeHarness):
    """A real-looking execution adapter (not FakeHarness itself): gated."""


def test_I_T1_a_real_execution_adapter_needs_permitted_terms_to_be_routed(db):
    r = Rig(db, adapters=[GatedHarness('gated')])
    mid = r.ready()
    assert r.dispatch(mid)['state'] == 'BLOCKED'
    (rd,) = r.rds()
    assert rd.candidates[0]['eliminated_at_step'] == 'provider_terms'


def test_I_T2_terms_revoked_between_routing_and_the_adapter_block_the_start(db, monkeypatch):
    r = Rig(db, adapters=[GatedHarness('gated')])
    r.do(C.decide_provider_terms, who=r.user, harness_id='gated', headless='permitted')
    mid = r.ready()
    started = []
    monkeypatch.setattr(GatedHarness, 'start', lambda self, spec: started.append(spec))
    real = r.work.dispatch_task

    def dispatch_then_revoke(tx, **kw):
        out = real(tx, **kw)
        C.decide_provider_terms(tx, actor=r.user, harness_id='gated', headless='refused')
        return out
    r.work.dispatch_task = dispatch_then_revoke
    eng = engine.Engine(db, actor=r.system, work=r.work, brain=None, registry=r.registry,
                        verifier=ports.ScriptedVerifier(), reviewer=ports.ScriptedReview())
    assert eng.step(mid)['did'] == 'reconcile_execution'
    assert started == []                                   # the second check held
    (e,) = r.all(entities.Execution)
    assert e.state not in ('STARTING', 'RUNNING') and r.rds()[0].result == 'selected'


def test_I_T3_an_own_call_is_checked_again_before_its_spawn(db, monkeypatch):
    """P6's n03 on the router: permitted when routed, refused at the call."""
    class Real(FakeCaller):
        pass
    r = Rig(db)
    real = Real('pi', replies={'brain': [{'parsed': {'ok': True}}]})
    r.do(C.decide_provider_terms, who=r.user, harness_id='pi', headless='permitted')
    reads = []
    real_terms = C.terms

    def flip(conn):
        reads.append(1)
        got = real_terms(conn)
        if len(reads) > 1:
            got['pi'] = entities.ProviderTerms(id='pi', headless='refused')
        return got
    monkeypatch.setattr(C, 'terms', flip)
    own = OC.OwnCalls(db, actor=r.system, callers=[real],
                      preference=ports.FixedOwnCallPreference())
    got = own.run(purpose='brain', source={'kind': 'mission', 'id': 'msn_x'},
                  workspace_id='ws_global', project_id=None, prompt='p', schema=None,
                  check=lambda p: [], workdir='.')
    assert got.state == 'gated' and real.sent == []
    assert r.rds()[0].result == 'selected'           # it was routed; the call was stopped


# ── I-H history ─────────────────────────────────────────────────────────────

def test_I_H1_a_route_decision_never_changes_and_a_later_one_is_a_new_row(r):
    a = r.account('A', priority=1)
    b = r.account('B', priority=2)
    mid = r.ready(task('t1', 'write_repo'), task('t2', 'write_repo'))
    r.dispatch(mid, 't1')
    with r.db.read() as c:
        (first,) = rows.where(c, entities.RouteDecision)
    with pytest.raises(ValueError, match='frozen|fixed'):
        r.db.writer.execute(lambda tx, actor: tx.update(
            entities.RouteDecision, first.entity.id, {'selected': b}, actor=actor),
            {'actor': r.system})
    r.do(resources.set_account_enabled, who=r.user, account_id=a, enabled=False)
    r.dispatch(mid, 't2')
    with r.db.read() as c:
        again, second = rows.where(c, entities.RouteDecision)
    assert again == first                              # the same row, byte for byte
    assert (first.entity.selected, second.entity.selected) == (a, b)


def test_I_H2_a_persisted_decision_replays_to_itself(r):
    r.account('A', priority=2)
    r.account('B', priority=1)
    r.dispatch(r.ready())
    (rd,) = r.rds()
    again = resources.replay(rd)
    assert (again['selected'], again['result'], again['candidates']) == (
        rd.selected, rd.result, list(rd.candidates))
    assert R.explain(again, rd.requirements) == rd.explanation


# ── I-U usage attributed to its decision ───────────────────────────────────

def test_I_U1_an_executions_usage_points_at_its_route_decision_and_counts_for_budgets(r):
    acc = r.account('A')
    mid = r.ready()
    out = r.dispatch(mid)
    r.finish(out, usage={'tokens_in': 40, 'tokens_out': 2})
    (u,) = r.all(entities.UsageLedger)
    assert (u.execution_id, u.route_decision_id, u.account_id) == (
        out['execution_id'], out['route_decision_id'], acc)
    with r.db.read() as c:
        assert resources.ledger_totals(c, acc, '2000-01-01')['tokens_today'] == 42


def test_I_U2_an_own_calls_usage_points_at_its_route_decision_and_account(r):
    # a home of its own, so the account's id and its ref differ
    acc = r.account('Brain', harness_id='fb', home_ref='C:/homes/brain')
    fake = FakeCaller('fb', replies={'brain': [{'parsed': {'ok': True}}]})
    own = OC.OwnCalls(r.db, actor=r.system, callers=[fake], usage=r.feed,
                      preference=ports.FixedOwnCallPreference())
    got = own.run(purpose='brain', source={'kind': 'mission', 'id': 'msn_x'},
                  workspace_id='ws_global', project_id=None, prompt='p', schema=None,
                  check=lambda p: [], workdir='.')
    r.do(C.end_call, route_decision_id=got.route_decision_id, outcome={'state': 'ok'},
         usage=got.usage)
    (u,) = r.all(entities.UsageLedger)
    assert (u.route_decision_id, u.account_id, u.execution_id) == (
        got.route_decision_id, acc, None)
    # the adapter ran on that account, in its home
    assert fake.sent[0][0].account == base.AccountRef(acc, 'C:/homes/brain')


def test_I_U3_observed_usage_is_recorded_once_per_reading(r):
    acc = r.account('A')
    r.feed.set(acc, '5h', 12)
    mid = r.ready(task('t1', 'write_repo'), task('t2', 'write_repo'))
    r.dispatch(mid, 't1')
    r.dispatch(mid, 't2')
    snaps = r.all(entities.UsageSnapshot, account_id=acc)
    assert [(s.window, s.utilisation_pct, s.source) for s in snaps] == [('5h', 12.0,
                                                                         'scripted')]


# ── I-R registration, health, continuity, the mission's resources ──────────

def test_I_R1_only_a_user_device_registers_or_changes_resources(r):
    for who in (r.system, r.brain, r.execution):
        with pytest.raises(NotPermitted):
            r.do(resources.register_account, who=who, harness_id='fake', label='x',
                 auth_kind='api_key')
    acc = r.account('A')
    with pytest.raises(NotPermitted):
        r.do(resources.set_resource_policy, who=r.brain, account_id=acc, priority=9)
    with pytest.raises(ValueError):
        r.do(resources.set_resource_policy, who=r.user, account_id=acc, allocation_pct=101)


def test_I_R2_the_probe_decides_health_and_only_available_accounts_are_routed(r):
    ok, bad, unknown = r.account('ok'), r.account('bad', auth=False), r.account('u', auth=None)
    health = {a.id: a.health for a in r.all(entities.Account)}
    assert health == {ok: 'AVAILABLE', bad: 'UNAUTHENTICATED', unknown: 'UNVERIFIED'}
    assert [p.priority for p in r.all(entities.ResourcePolicy)] == [1, 2, 3]
    r.do(resources.set_account_enabled, who=r.user, account_id=ok, enabled=False)
    assert r.dispatch(r.ready())['state'] == 'BLOCKED'


def test_I_R3_a_mission_stays_where_it_runs_until_its_resources_are_set(r):
    a = r.account('A', priority=1)
    b = r.account('B', priority=2)
    r.do(resources.set_account_enabled, who=r.user, account_id=a, enabled=False)
    mid = r.ready(task('t1', 'write_repo'), task('t2', 'write_repo'), task('t3', 'write_repo'))
    assert r.dispatch(mid, 't1')['account_id'] == b
    r.do(resources.set_account_enabled, who=r.user, account_id=a, enabled=True,
         auth={'ok': True})
    assert r.dispatch(mid, 't2')['account_id'] == b                  # affinity
    r.do(resources.set_mission_resources, who=r.user, mission_id=mid,
         preferences={'preferred_accounts': [a]})
    assert r.dispatch(mid, 't3')['account_id'] == a                  # cleared, preferred


def test_I_R4_the_missions_cost_ceiling_is_the_users_to_raise(r):
    big = task('t1', 'write_repo', min_model_tier='large', estimate=5)
    mid = r.mission()
    with pytest.raises(NotPermitted):
        r.do(resources.set_mission_resources, who=r.system, mission_id=mid,
             preferences={'max_cost_band': 'high'})
    r.do(resources.set_mission_resources, who=r.user, mission_id=mid,
         preferences={'max_cost_band': 'high'})
    out = r.propose(mid, big, dict(big, key='t2', title='More', depends_on=['t1']))
    assert out['mission']['state'] == 'APPROVED'
    (d,) = [d for d in r.all(entities.PolicyDecision, mission_id=mid) if d.stage == 'plan']
    assert d.cost['ceiling'] == 'high'


def test_I_R5_a_task_needing_a_tier_no_account_offers_is_blocked_with_the_reason(db):
    r = Rig(db, adapters=[FakeHarness(models=('untiered',))])
    mid = r.ready(task('t1', 'write_repo', min_model_tier='mid'))
    assert r.dispatch(mid)['state'] == 'BLOCKED'
    (rd,) = r.rds()
    assert rd.candidates[0]['eliminated_at_step'] == 'model'
    assert 'tier mid' in rd.explanation


def test_I_R6_an_invalid_transition_of_an_account_is_refused(r):
    acc = r.account('A')
    with pytest.raises(InvalidTransition):
        r.do(resources.set_account_enabled, who=r.user, account_id=acc, enabled=True)


# ── B7 (p10-design-gate §18): the run-time spy ─────────────────────────────

def test_B7_routing_a_task_asks_an_adapter_nothing_but_what_it_declares(db, monkeypatch):
    """Run-time spy: through the whole dispatch-and-route command no adapter
    starts, is called, authenticates or reports status."""
    def boom(name):
        def f(*a, **k):
            raise AssertionError('routing reached %s' % name)
        return f
    for name in ('start', 'authenticate', 'status', 'stop', 'inspect', 'collect_result'):
        monkeypatch.setattr(FakeHarness, name, boom(name))
    monkeypatch.setattr(FakeCaller, 'call', boom('call'))
    r = Rig(db)
    mid = r.ready(task('t1', 'write_repo'))
    assert r.dispatch(mid)['execution_id']
