"""T-150 round 2: chat start and plan consent, without database IO."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from archeus.core.application import authorization as A
from archeus.core.domain import entities, guards, ids


def mission(origin='conversation', profile=None):
    return entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                            title='Chat work', objective='o', origin=origin,
                            autonomy_profile=profile)


@pytest.mark.parametrize('origin, profile, user_profile, asks', [
    ('conversation', None, 'standard', True), ('idea', None, 'standard', True),
    ('api', None, 'standard', False), ('automation', None, 'standard', False),
    ('conversation', None, 'autonomous', False), ('idea', None, 'autonomous', False),
    ('conversation', 'autonomous', 'standard', False),
    ('conversation', 'standard', 'autonomous', True),
    ('conversation', None, 'careful', False)])
def test_chat_start_scope_and_profile(monkeypatch, origin, profile, user_profile, asks):
    monkeypatch.setattr(A, 'owner', lambda conn: SimpleNamespace(autonomy_profile=user_profile))
    assert A.asks_before_start(None, mission(origin, profile)) is asks


def test_chat_plan_requires_consent_even_when_policy_and_cost_allow():
    m = mission()
    f = guards.MissionFacts(plan_version=1, tasks=(guards.TaskFact('t1', 'code_change', 'PENDING'),),
                           policy=(('t1', 'read', 'ALLOW'),), cost_within_ceiling=True,
                           explicit_plan_approval=True)
    assert not guards.plan_auto_approved(m, f).passed
    assert guards.plan_needs_approval(m, f).passed
    denied = replace(f, policy=(('t1', 'deploy', 'DENY'),))
    assert not guards.plan_needs_approval(m, denied).passed
    stale = replace(m, decided_plan_version=1)
    assert not guards.plan_needs_approval(stale, f).passed
    automatic = replace(f, explicit_plan_approval=False)
    assert guards.plan_auto_approved(m, automatic).passed
    assert not guards.plan_needs_approval(m, automatic).passed


@pytest.mark.parametrize('state, idle', [
    ('REJECTED', True), ('EXPIRED', True), ('PENDING', False), ('APPROVED', False)])
def test_expired_or_declined_start_is_not_reasked(monkeypatch, state, idle):
    def stored(conn, cls, **filters):
        assert cls is entities.Approval and filters == {'action_hash': 'start-hash'}
        return [SimpleNamespace(entity=SimpleNamespace(state=state))]
    monkeypatch.setattr(A.rows, 'where', stored)
    assert A._declined(None, 'start-hash') is idle


@pytest.mark.parametrize('policy_decision, expected', [('ALLOW', 'ASK'), ('DENY', 'DENY')])
def test_judge_start_keeps_denials_and_uses_start_context(monkeypatch, policy_decision, expected):
    extra = [object()]
    m = mission()
    def context(conn, got, **kw):
        assert got == m and kw['stage'] == 'start' and kw['extra_rules'] == extra
        return {'estop': True, 'chain': {'USER': None}}
    def judge(policy, action, ctx):
        assert action == A.start_action(m)
        assert ctx['estop'] is False and ctx['chain']['USER'] == 'standin'
        return {'decision': policy_decision, 'reason': 'policy'}
    monkeypatch.setattr(A, 'context', context)
    monkeypatch.setattr(A, 'judge', judge)
    monkeypatch.setattr(A, 'asks_before_start', lambda conn, got: True)
    items, ctx = A.judge_start(None, None, m, now='now', extra_rules=extra, user_id='standin')
    assert items[0]['decision'] == expected


def test_start_simulation_uses_judge_start(monkeypatch):
    m = mission()
    monkeypatch.setattr(A.rows, 'get', lambda conn, cls, eid: SimpleNamespace(entity=m))
    calls = []
    def judge_start(policy, conn, got, **kw):
        calls.append((got.id, kw['now'], kw['extra_rules']))
        return [{'decision': 'ASK', 'reason': 'chat consent'}], {'policy_version': 'v1'}
    monkeypatch.setattr(A, 'judge_start', judge_start)
    got = A.simulate(None, None, now='now', mission_id=m.id,
                     action={'class': 'mission.start', 'target': 'mission:' + m.id})
    assert calls == [(m.id, 'now', [])]
    assert got['decision'] == 'ASK' and got['simulated'] and got['mission_id'] == m.id
