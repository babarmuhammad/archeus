"""P9 authorisation on the real database (p9-design-gate §21.2, I-*): the
plan gate's records, approvals and their lifetime, dispatch re-checks, the
action stage, principals, idempotency. Every command goes through the writer,
one transaction each, exactly as Core runs them; the router is the P1 stub and
nothing here starts a process (E5/E6 are asserted by `no_later_phase_called`)."""

import dataclasses
import json
import os
import sqlite3
from datetime import timedelta

import pytest

from archeus.core import ports
from archeus.core.application import authorization, commands, lifecycle, queries, work
from archeus.core.application.authorization import NotEligible, NotPermitted
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.policy.engine import PolicyEngine
from archeus.infra import paths
from archeus.infra.db import rows
from archeus.infra.db.writer import IdempotencyConflict
from archeus.infra.eventlog import retention

AUTO = {'text': 'the result passes its automatic check', 'check': 'automatic'}
ACCEPT = [{'text': 'it is done', 'check': 'automatic'}]


def task(key, *classes, **kw):
    return dict({'key': key, 'title': 'Task %s' % key, 'kind': 'code_change',
                 'action_classes': list(classes), 'acceptance': ACCEPT}, **kw)


class Rig:
    def __init__(self, db, policy=None):
        self.db = db
        reg = lambda kind, scopes: Ref(kind, db.writer.execute(  # noqa: E731
            commands.register_principal, {'kind': kind, 'scopes': scopes})['id'])
        self.system = reg('system', ('system',))
        self.user = reg('user_device', ('observe', 'control', 'approve', 'admin'))
        self.control = reg('user_device', ('observe', 'control'))
        self.brain = reg('brain', ('propose',))
        self.execution = reg('execution', ('report', 'checkpoint', 'request_approval'))
        self.policy = policy or PolicyEngine()
        self.missions = commands.Missions(policy=self.policy)
        self.work = work.Work(missions=self.missions,
                              router=ports.FixedCandidateRouter('fake'))
        self.authz = authorization.Authorization(missions=self.missions)

    def do(self, command, who=None, key=None, **kw):
        return self.db.writer.execute(command, dict(kw, actor=who or self.system),
                                      idempotency_key=key)

    def mission(self, title='M'):
        mid = self.do(commands.create_mission, who=self.user, title=title, objective='o',
                      success_criteria=[AUTO])['id']
        for trig in ('start', 'understood'):
            self.do(self.missions.fire, mission_id=mid, trigger=trig, reason='test')
        self.do(self.missions.context_ready, mission_id=mid)
        return mid

    def propose(self, mid, *tasks):
        return self.do(self.work.propose_plan, mission_id=mid,
                       context_package_id=self.m(mid).context_package_id, plan={
            'summary': 'test plan', 'tasks': list(tasks), 'success_criteria': [AUTO]})

    def one(self, cls, **eq):
        with self.db.read() as r:
            got = rows.where(r, cls, **eq)
        assert len(got) == 1, got
        return got[0].entity

    def all(self, cls, **eq):
        with self.db.read() as r:
            return [x.entity for x in rows.where(r, cls, **eq)]

    def m(self, mid):
        with self.db.read() as r:
            return rows.get(r, entities.Mission, mid).entity

    def pending(self, mid):
        (a,) = [a for a in self.all(entities.Approval, mission_id=mid) if a.state == 'PENDING']
        return a

    def decide(self, a, decision='approve', who=None, key=None, h=None, **kw):
        return self.do(self.authz.decide, who=who or self.user, key=key, approval_id=a.id,
                       decision=decision, action_hash=h or a.action_hash, **kw)

    def head(self):
        with self.db.read() as r:
            return r.execute('SELECT MAX(seq) FROM events').fetchone()[0]

    def events(self, type_):
        with self.db.read() as r:
            return [e for e in queries.events(r) if e['type'] == type_]

    def rule(self, level, cls, decision, who=None, **kw):
        return self.do(self.authz.create_rule, who=who or self.user, scope_level=level,
                       action_class=cls, decision=decision, **kw)

    def run_task(self, mid, ok=True, attempts=1):
        """Dispatch the mission's READY task and end its executions."""
        (t,) = [t for t in self.all(entities.Task, mission_id=mid) if t.state == 'READY']
        for _ in range(attempts):
            out = self.do(self.work.dispatch_task, task_id=t.id)
            if out['execution_id'] is None:
                return out
            self.do(self.work.record_spawn, execution_id=out['execution_id'], pid=1,
                    create_time=1.0)
            self.do(self.work.record_exit, execution_id=out['execution_id'],
                    exit_reason='ok' if ok else 'error', exit_code=0 if ok else 1)
        return out


@pytest.fixture
def r(db):
    return Rig(db)


@pytest.fixture(autouse=True)
def no_later_phase_called(monkeypatch):
    """E6: nothing a P9 test does reaches a later phase's port from authorisation."""
    calls = []
    real = ports.FixedCandidateRouter.route
    monkeypatch.setattr(ports.FixedCandidateRouter, 'route',
                        lambda self, *a, **k: calls.append('route') or real(self, *a, **k))
    import archeus.core.calls as C
    monkeypatch.setattr(C.OwnCalls, 'run', lambda *a, **k: calls.append('archeus_call'))
    yield calls
    assert 'archeus_call' not in calls


def _dispatchable(r, mid):
    """APPROVED -> EXECUTING with its first task READY."""
    r.do(r.missions.fire, mission_id=mid, trigger='dispatch', reason='go')
    r.do(r.work.ready_tasks, mission_id=mid)


# ── the plan gate (§12.1) ───────────────────────────────────────────────────

def test_I_G1_auto_approval_records_the_decision_and_approves_the_plan(r):
    mid = r.mission()
    out = r.propose(mid, task('t1', 'read', 'write_repo', touches=['src/**']))
    assert out['mission']['state'] == 'APPROVED'
    p = r.one(entities.Plan, mission_id=mid)
    d = r.one(entities.PolicyDecision, mission_id=mid)
    assert p.state == 'APPROVED' and (d.stage, d.outcome, d.plan_id) == ('plan', 'auto_approved',
                                                                        p.id)
    with r.db.read() as conn:
        assert d.action_hash == authorization.plan_hash(conn, p)
    assert d.plan_digest == p.digest and d.policy_version and d.engine_version
    by = {(i['task'], i['class']): i for i in d.items}
    assert by[('t1', 'write_repo')]['decision'] == 'ALLOW_WITHIN_BOUNDARY'
    assert by[('t1', 'write_repo')]['checks']['checked'] == ['paths']
    assert {x['id'] for x in d.matched_rules} >= set(by[('t1', 'write_repo')]['matched'])
    assert r.all(entities.Approval) == []


def test_I_G2_an_ask_waits_for_one_approval_of_exactly_this_plan(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    assert r.m(mid).state == 'APPROVAL_REQUIRED'
    a = r.pending(mid)
    p = r.one(entities.Plan, mission_id=mid)
    assert (a.kind, a.plan_id, a.plan_digest, a.step_up) == ('plan', p.id, p.digest, True)
    assert p.state == 'PROPOSED'                        # asked, not approved
    assert a.presented['scope'] == 'this plan version'
    assert a.presented['what'][0]['class'] == 'deploy'
    assert a.presented['against']['plan']['summary_by'].startswith('the planner')
    assert a.presented['consequences']['reject'] == 'the mission is cancelled'
    d = r.one(entities.PolicyDecision)          # recorded as judged: the ASK, not an ALLOW
    assert (d.outcome, [i['decision'] for i in d.items]) == ('needs_approval', ['ASK'])
    (ev,) = r.events('approval.requested')
    assert ev['subject']['id'] == a.id and ev['payload']['action_hash'] == a.action_hash


def test_I_G3_a_denied_first_plan_blocks_as_denied_and_writes_no_plan(r):
    mid = r.mission()
    with pytest.raises(work.PolicyDenied) as e:
        r.propose(mid, task('t1', 'destructive'))
    assert e.value.specs and r.all(entities.Plan) == []
    out = r.do(r.authz.record_plan_denial, mission_id=mid, specs=e.value.specs)
    assert out['recorded'] and out['state'] == 'BLOCKED'
    m = r.m(mid)
    assert m.planning_blocked['kind'] == 'policy'
    assert m.planning_blocked['denied'][0]['rule'] == 'builtin:floor:destructive-prod'
    d = r.one(entities.PolicyDecision)
    assert (d.decision, d.outcome) == ('DENY', 'denied')
    assert r.events('mission.state_changed')[-1]['payload']['trigger'] == 'plan_denied'
    for cls in (entities.Plan, entities.Task, entities.Execution, entities.Approval):
        assert r.all(cls) == []


def test_I_G3b_a_denial_in_planning_waits_in_place(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    r.decide(r.pending(mid), 'request_changes')
    assert r.m(mid).state == 'PLANNING'
    with pytest.raises(work.PolicyDenied) as e:
        r.propose(mid, task('t1', 'destructive'))
    r.do(r.authz.record_plan_denial, mission_id=mid, specs=e.value.specs)
    m = r.m(mid)
    assert m.state == 'PLANNING' and m.planning_blocked['kind'] == 'policy'
    assert len(r.all(entities.Plan)) == 1


def test_I_G3c_a_denial_the_policy_no_longer_makes_records_nothing(r):
    mid = r.mission()
    with pytest.raises(work.PolicyDenied) as e:
        r.propose(mid, task('t1', 'destructive'))
    specs = [dict(s, action_classes=['read']) for s in e.value.specs]
    assert not r.do(r.authz.record_plan_denial, mission_id=mid, specs=specs)['recorded']
    assert r.all(entities.PolicyDecision) == [] and r.m(mid).state == 'REASONING'


def test_I_G5_what_is_recorded_is_what_the_guard_judged(db):
    """A policy that answers differently on a later call: the plan gate
    records the evaluation its guard judged, not a fresh one (M30)."""
    class Drifting(ports.FixedPolicy):
        calls = 0

        def evaluate(self, action, ctx):
            Drifting.calls += 1
            return entities.PolicyDecision(
                id=ids.new_id('policy_decision'), action=action, reason='drift',
                decision='ALLOW' if Drifting.calls <= 2 else 'ASK')
    r = Rig(db, Drifting())
    mid = r.mission()
    assert r.propose(mid, task('t1', 'read'))['mission']['state'] == 'APPROVED'
    d = r.one(entities.PolicyDecision)
    assert [i['decision'] for i in d.items] == ['ALLOW'] and d.outcome == 'auto_approved'


def test_I_G6_estop_denies_the_plan(r):
    os.makedirs(paths.run_dir(), exist_ok=True)
    open(paths.stop_sentinel(), 'w').close()
    try:
        mid = r.mission()
        with pytest.raises(work.PolicyDenied) as e:
            r.propose(mid, task('t1', 'read'))
        r.do(r.authz.record_plan_denial, mission_id=mid, specs=e.value.specs)
        d = r.one(entities.PolicyDecision)
        assert d.estop is True and d.items[0]['deciding_rule'] == 'builtin:estop'
    finally:
        os.remove(paths.stop_sentinel())


# ── deciding (§8.5) ─────────────────────────────────────────────────────────

def test_I_A01_approve_moves_the_approval_the_plan_and_the_mission_together(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    out = r.decide(a, note='ship it')
    assert out['changed'] and out['state'] == 'APPROVED'
    assert out['mission']['state'] == 'APPROVED'
    a2 = r.one(entities.Approval)
    assert (a2.decision, a2.decided_by, a2.decision_note) == ('approve', r.user.id, 'ship it')
    assert r.one(entities.Plan).state == 'APPROVED'
    (d,) = [d for d in r.all(entities.PolicyDecision) if d.outcome == 'approved']
    assert a2.decided_policy_decision_id == d.id and d.approval_id == a.id


def test_I_A02_reject_cancels_the_mission(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    out = r.decide(r.pending(mid), 'reject')
    assert out['state'] == 'REJECTED' and out['mission']['state'] == 'CANCELLED'
    assert r.one(entities.Plan).state == 'REJECTED'


def test_I_A03_request_changes_plans_again_and_nothing_carries(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    first = r.pending(mid)
    assert r.decide(first, 'request_changes')['mission']['state'] == 'PLANNING'
    r.propose(mid, task('t1', 'deploy'))
    v1, v2 = sorted(r.all(entities.Plan), key=lambda p: p.plan_version)
    assert (v1.state, v2.state) == ('REJECTED', 'PROPOSED')
    second = r.pending(mid)
    assert second.id != first.id and second.action_hash != first.action_hash
    with pytest.raises(lifecycle.IllegalTrigger):          # a decided approval stays decided
        r.decide(first, 'approve', key='again')


def test_I_A04_an_approval_never_covers_another_missions_same_plan(r):
    a_mid, b_mid = r.mission('A'), r.mission('B')
    for mid in (a_mid, b_mid):
        r.propose(mid, task('t1', 'deploy'))
    a, b = r.pending(a_mid), r.pending(b_mid)
    assert a.plan_version == b.plan_version == 1 and a.action_hash != b.action_hash
    with pytest.raises(lifecycle.GuardFailed, match='different action'):
        r.decide(b, h=a.action_hash)


def test_I_A05_a_hash_mismatch_writes_nothing(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a, head = r.pending(mid), r.head()
    for decision in ('approve', 'reject', 'request_changes'):
        with pytest.raises(lifecycle.GuardFailed, match='different action'):
            r.decide(a, decision, h='0' * 64)
    assert r.head() == head and r.pending(mid).id == a.id


def _tamper(db, plan_id):
    """Write a plan's body around the writer, as corruption or tampering would."""
    path = db.path if hasattr(db, 'path') else None
    from archeus.infra.db import connection
    c = sqlite3.connect(path or connection.db_path(paths.archeus_home()))
    body = json.loads(c.execute('SELECT body FROM plans WHERE id = ?', (plan_id,)).fetchone()[0])
    body['summary'] = 'something else entirely'
    c.execute('UPDATE plans SET body = ? WHERE id = ?', (json.dumps(body), plan_id))
    c.commit()
    c.close()


def test_I_A06_a_plan_that_does_not_match_its_digest_is_never_approved_or_dispatched(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    _tamper(r.db, a.plan_id)
    with pytest.raises(NotEligible) as e:
        r.decide(a)
    assert e.value.why == 'digest_mismatch'
    mid2 = r.mission('auto')
    r.propose(mid2, task('t1', 'write_repo'))
    _dispatchable(r, mid2)
    _tamper(r.db, r.one(entities.Plan, mission_id=mid2).id)
    out = r.run_task(mid2)
    assert out['authorization']['why'] == 'digest_mismatch' and r.m(mid2).state == 'BLOCKED'
    assert r.all(entities.Execution) == []


def test_I_A07_an_approved_plans_approval_ends_with_it(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    r.decide(a)
    _dispatchable(r, mid)
    r.run_task(mid, ok=False, attempts=2)
    assert r.do(r.missions.advance, mission_id=mid)['state'] == 'REPLANNING'
    r.propose(mid, task('t1', 'deploy'))
    assert r.one(entities.Approval, id=a.id).state == 'SUPERSEDED'
    (moved,) = [e for e in r.events('approval.state_changed')
                if e['subject']['id'] == a.id and e['payload']['to'] == 'SUPERSEDED']
    assert moved['payload']['trigger'] == 'plan_replaced'
    assert r.m(mid).state == 'APPROVAL_REQUIRED'           # v2 is decided afresh
    with pytest.raises(lifecycle.IllegalTrigger):
        r.decide(a, key='replay')


def test_I_A08_supersession_ends_every_live_approval_of_the_version(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    r.do(authorization.supersede_for, plan_id=a.plan_id, replaced_by=2)
    assert r.one(entities.Approval).state == 'SUPERSEDED'


def test_I_A08b_a_pending_approval_of_a_version_no_longer_in_force_is_ineligible(r):
    """Supersession ends a version's approvals in its own transaction; the
    eligibility check is the second layer, for a version that left force by any
    other path (here: moved directly, as a bug or a race would)."""
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    r.do(lambda tx, actor: lifecycle.fire(tx, entities.Plan, a.plan_id, 'superseded',
                                          actor=actor, reason='test'))
    with r.db.read() as conn:
        assert queries.get_approval(conn, a.id)['eligible_why'] == 'superseded'
    with pytest.raises(NotEligible) as e:
        r.decide(a)
    assert e.value.why == 'superseded'


def test_I_A09_a_task_approval_covers_its_task_only(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'install'), task('t2', 'install', depends_on=['t1']))
    r.decide(r.pending(mid))
    _dispatchable(r, mid)
    # the policy turns: install is now asked at a narrower level than the plan saw
    r.rule('MISSION', 'install', 'ASK', scope_ref=mid, locked=True, note='re-ask')
    r.run_task(mid)                         # t1 is covered: its item was presented
    assert r.m(mid).state == 'EXECUTING'


def test_I_A10_a_stale_plan_is_never_approved_but_can_be_refused(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)

    def change(tx, *, actor):
        m = lifecycle.load(tx, entities.Mission, mid).entity
        req = m.requirements + ({'text': 'also this', 'origin': 'explicit'},)
        tx.update(entities.Mission, mid, {'requirements': req}, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', mid), actor,
                            payload={'fields': ['requirements']}))
    r.do(change)
    with pytest.raises(NotEligible) as e:
        r.decide(a)
    assert e.value.why == 'stale'
    with r.db.read() as conn:
        v = queries.get_approval(conn, a.id)
        assert (v['eligible'], v['eligible_why']) == (False, 'stale')
    assert r.decide(a, 'reject')['mission']['state'] == 'CANCELLED'


def test_I_A10b_a_pruned_log_cannot_prove_currency(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    r.do(lambda tx, actor: retention.prune(tx, now='2099-01-01T00:00:00Z', keep_days=0))
    with pytest.raises(NotEligible) as e:
        r.decide(a)
    assert e.value.why == 'stale'


def test_I_A11_an_expired_approval_covers_nothing_and_is_swept(r, monkeypatch):
    monkeypatch.setitem(authorization.TTL, 'plan', timedelta(seconds=-1))
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    with pytest.raises(NotEligible) as e:
        r.decide(a)
    assert e.value.why == 'expired'
    assert r.do(authorization.expire_due)['expired'] == [a.id]
    assert r.one(entities.Approval).state == 'EXPIRED'
    assert r.do(authorization.expire_due)['expired'] == []


def test_I_A12b_the_database_refuses_a_second_live_approval_of_one_identity(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    with pytest.raises(sqlite3.IntegrityError):
        r.do(lambda tx, actor: tx.insert(dataclasses.replace(
            a, id=ids.new_id('approval')), actor=actor))


def test_approval_coverage_is_the_exact_item_and_its_step_up():
    a = entities.Approval(id=ids.new_id('approval'), subject=Ref('plan', ids.new_id('plan')),
                          action_hash='a' * 64, requested_by=ids.new_id('principal'),
                          items=({'task': 't1', 'action': {'class': 'deploy',
                                                           'target': 'task:t1'}},))
    item = {'task': 't1', 'class': 'deploy', 'action': {'class': 'deploy', 'target': 'task:t1'}}
    assert authorization._covers(a, item, step_up=False)
    assert not authorization._covers(a, dict(item, task='t2'), step_up=False)
    assert not authorization._covers(a, dict(item, action={'class': 'deploy',
                                                           'target': 'task:t2'}), False)
    assert not authorization._covers(a, item, step_up=True)      # given without step-up


def test_I_A12_the_same_identity_asked_twice_is_one_approval(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)

    def again(tx, *, actor):
        m = lifecycle.load(tx, entities.Mission, mid).entity
        p = lifecycle.load(tx, entities.Plan, a.plan_id).entity
        got, new = authorization.request(
            tx, actor=actor, kind='plan', mission=m, plan=p, items=[], h=a.action_hash,
            decision_id=a.policy_decision_id, why=[], ctx={})
        return {'id': got.id, 'new': new}
    assert r.do(again) == {'id': a.id, 'new': False}
    assert len(r.all(entities.Approval)) == 1


def test_I_A13_deciding_again_is_one_decision(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    first = r.decide(a, key='k1')
    assert r.decide(a, key='k1') == first                         # same key: same answer
    again = r.decide(a, key='k2')                                 # another device, same answer
    assert (again['changed'], again['state']) == (False, 'APPROVED')
    with pytest.raises(IdempotencyConflict):
        r.decide(a, 'reject', key='k1')
    with pytest.raises(lifecycle.IllegalTrigger):
        r.decide(a, 'reject', key='k3')
    assert len([d for d in r.all(entities.PolicyDecision) if d.outcome == 'approved']) == 1


def test_I_A14_an_action_approval_is_single_use(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'))
    _dispatchable(r, mid)
    (t,) = r.all(entities.Task)
    eid = r.do(r.work.dispatch_task, task_id=t.id)['execution_id']
    push = {'action_class': 'git_push', 'target': 'origin/main',
            'argv': ['git', 'push', 'origin', 'main']}
    first = r.do(r.authz.evaluate_action, execution_id=eid, action=push)
    assert first['decision'] == 'ASK' and first['approval_id']
    a = r.one(entities.Approval, id=first['approval_id'])
    assert a.kind == 'action' and a.execution_id == eid
    r.decide(a)
    used = r.do(r.authz.evaluate_action, execution_id=eid, action=push)
    assert (used['decision'], used['approval_id']) == ('ALLOW', a.id)
    assert r.one(entities.Approval, id=a.id).state == 'CONSUMED'
    again = r.do(r.authz.evaluate_action, execution_id=eid, action=push)
    assert again['decision'] == 'ASK' and again['approval_id'] != a.id


def test_I_A15_only_a_user_device_with_approve_decides(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    for who in (r.brain, r.control, r.execution, r.system):
        with pytest.raises(NotPermitted):
            r.decide(a, who=who)
    assert r.pending(mid).id == a.id


def test_I_A16_a_cancelled_mission_leaves_no_decidable_approval(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    r.do(r.missions.cancel, who=r.user, mission_id=mid)
    got = r.one(entities.Approval)
    assert (got.state, got.decided_by) == ('REJECTED', r.user.id)
    with pytest.raises(lifecycle.IllegalTrigger):
        r.decide(a)


def test_I_A17_a_deny_is_never_approvable(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    r.rule('USER', 'deploy', 'DENY')
    out = r.decide(a)
    assert out['denied'] and out['changed'] is False and out['state'] == 'PENDING'
    d = r.one(entities.PolicyDecision, id=out['denied']['policy_decision_id'])
    assert (d.decision, d.outcome, d.approval_id) == ('DENY', 'denied', a.id)
    assert r.m(mid).state == 'APPROVAL_REQUIRED'


def test_I_A18_the_mission_approve_edge_by_name_approves_nothing(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    with pytest.raises(lifecycle.GuardFailed, match='no approval of plan v1 is APPROVED'):
        r.do(r.missions.fire, who=r.user, mission_id=mid, trigger='approve', reason='x')


def test_I_A19_a_paired_device_cannot_step_up_before_P15(r, db):
    phone = db.writer.execute(commands.register_device, {
        'actor': r.system, 'name': 'phone', 'platform': 'android', 'token_hash': 'a' * 64,
        'scopes': ('observe', 'approve')})
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    assert a.step_up
    with pytest.raises(lifecycle.GuardFailed, match='step-up'):
        r.decide(a, who=Ref('user_device', phone['principal_id']))


# ── dispatch (§12.2) ────────────────────────────────────────────────────────

def test_I_D1_an_unchanged_policy_covers_the_dispatch_and_records_it(r, no_later_phase_called):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'))
    _dispatchable(r, mid)
    r.run_task(mid)
    (d,) = [d for d in r.all(entities.PolicyDecision) if d.stage == 'dispatch']
    assert d.outcome == 'covered' and d.task_id == r.one(entities.Task).id


def test_I_D2_a_policy_turned_ask_after_auto_approval_asks_for_the_task(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'), task('t2', 'write_repo', depends_on=['t1']))
    _dispatchable(r, mid)
    r.rule('MISSION', 'write_repo', 'ASK', scope_ref=mid)
    out = r.run_task(mid)
    assert out['authorization']['outcome'] == 'asked' and r.m(mid).state == 'BLOCKED'
    a = r.pending(mid)
    t1 = r.one(entities.Task, key='t1')
    assert (a.kind, a.task_id) == ('task', t1.id)
    assert r.decide(a)['mission']['state'] == 'EXECUTING'
    r.run_task(mid)                                         # covered by the task approval
    assert r.one(entities.Task, key='t1').state == 'VERIFYING'
    r.do(r.work.record_task_verification, task_id=t1.id, verdict='PASSED', verifier='code')
    r.do(r.work.ready_tasks, mission_id=mid)
    out = r.run_task(mid)                                   # t2: the approval was t1's only
    assert out['authorization']['outcome'] == 'asked'


def test_I_D3_a_deny_at_dispatch_writes_nothing_and_unrecoverable_records_it(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'))
    _dispatchable(r, mid)
    r.rule('USER', 'write_repo', 'DENY')
    (t,) = r.all(entities.Task)
    head = r.head()
    with pytest.raises(work.PolicyDenied):
        r.do(r.work.dispatch_task, task_id=t.id)
    assert r.head() == head
    assert r.do(r.missions.advance, mission_id=mid)['state'] == 'FAILED'
    (d,) = [d for d in r.all(entities.PolicyDecision) if d.outcome == 'denied']
    assert d.stage == 'dispatch' and d.decision == 'DENY'


def test_I_D4_a_stub_approved_plan_without_authorisation_asks_at_dispatch(r):
    """Missing authorisation (§11): a version no real policy approved is never
    dispatched on its word; it blocks and asks — never denied, never run."""
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'))
    p = r.one(entities.Plan)

    def unapprove(tx, *, actor):            # what a P1-stub era plan looks like
        tx.conn.execute("UPDATE plans SET state = 'PROPOSED' WHERE id = ?", (p.id,))
    r.do(unapprove)
    _dispatchable(r, mid)
    out = r.run_task(mid)
    assert out['authorization']['outcome'] == 'asked' and r.all(entities.Execution) == []


# ── autonomy and rules (§5, §4.3) ───────────────────────────────────────────

def test_I_P4_raising_a_missions_autonomy_is_admin_only_and_changes_only_unlocked_answers(r):
    mid = r.mission()
    with pytest.raises(NotPermitted):
        r.do(r.authz.set_profile, who=r.control, scope='mission', mission_id=mid,
             profile='autonomous')
    r.do(r.authz.set_profile, who=r.user, scope='mission', mission_id=mid,
         profile='autonomous')
    assert r.m(mid).autonomy_profile == 'autonomous'
    assert r.propose(mid, task('t1', 'git_push'))['mission']['state'] == 'APPROVED'
    mid2 = r.mission('floor')
    r.do(r.authz.set_profile, who=r.user, scope='mission', mission_id=mid2,
         profile='autonomous')
    with pytest.raises(work.PolicyDenied):                  # the floor stands (I-P5)
        r.propose(mid2, task('t1', 'destructive'))


def test_I_P6_the_users_profile_is_the_default_every_mission_inherits(r):
    r.do(r.authz.set_profile, who=r.user, scope='user', profile='careful')
    mid = r.mission()
    assert r.propose(mid, task('t1', 'write_repo'))['mission']['state'] == 'APPROVAL_REQUIRED'
    assert r.events('user.updated')[-1]['payload']['autonomy_profile'] == 'careful'


def test_rules_are_revised_never_edited_and_the_old_decision_keeps_its_policy(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'install'))                   # asked under the old policy
    before = r.one(entities.PolicyDecision)
    first = r.rule('USER', 'install', 'ASK')
    second = r.do(r.authz.create_rule, who=r.user, scope_level='USER', action_class='install',
                  decision='ALLOW', supersedes_rule_id=first['id'])
    assert second['revision'] == 2
    old = r.one(entities.PolicyRule, id=first['id'])
    assert old.retired_at is not None and old.decision == 'ASK'
    retired = r.events('policy_rule.retired')[-1]['payload']
    assert retired['replaced_by'] == second['id'] and retired['before']['decision'] == 'ASK'
    after = r.one(entities.PolicyDecision, id=before.id)
    assert after == before                          # history is never rewritten
    with pytest.raises(ValueError):
        r.do(lambda tx, actor: tx.update(entities.PolicyDecision, before.id,
                                         {'decision': 'ALLOW'}, actor=actor))
    with pytest.raises(NotPermitted):
        r.rule('USER', 'install', 'ALLOW', who=r.control)


def test_I_S1_simulate_answers_and_writes_nothing(r):
    mid = r.mission()
    head = r.head()
    with r.db.read() as conn:
        got = r.authz.simulate(conn, now='2026-09-26T00:00:00Z',
                               action={'class': 'git_push', 'target': 'origin/x'},
                               mission_id=mid,
                               extra_rules=[{'scope_level': 'MISSION', 'scope_ref': mid,
                                             'action_class': 'git_push',
                                             'decision': 'ALLOW'}])
    assert got['decision'] == 'ALLOW' and got['simulated']
    assert r.head() == head and r.all(entities.PolicyDecision) == []


def test_the_views_say_whether_an_approval_and_a_plan_can_be_authorised(r):
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    a = r.pending(mid)
    with r.db.read() as conn:
        v = queries.get_approval(conn, a.id)
        p = queries.get_plan(conn, a.plan_id)
        m = queries.get_mission(conn, mid)
    assert v['eligible'] and v['eligible_why'] is None
    assert (p['in_force'], p['eligible']) == (True, True)
    assert m['pending_approval_id'] == a.id
    assert dataclasses.asdict(r.one(entities.Approval))['action_hash'] == v['action_hash']
