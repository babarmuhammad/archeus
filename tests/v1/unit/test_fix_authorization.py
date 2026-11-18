"""Regression tests for the T-612 audit findings of authorization.py that were
real: an expired approval is never handed back as the live ask, a start
decision records the true e-stop state, a rule's expiry and scope_ref must be
readable, and a denial is not written onto a mission that stopped planning."""

import os
import time
from datetime import timedelta

import pytest

from archeus.core.application import authorization, commands
from archeus.core.domain import entities
from archeus.infra import paths
from archeus.infra.db import Database
from v1.integration.test_policy import AUTO, Rig, _dispatchable, task

PUSH = {'action_class': 'git_push', 'target': 'origin/main',
        'argv': ['git', 'push', 'origin', 'main']}


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def r(db):
    return Rig(db)


def test_an_approved_action_approval_that_expired_is_not_handed_back_as_the_live_ask(
        r, monkeypatch):
    monkeypatch.setitem(authorization.TTL, 'action', timedelta(seconds=1.5))
    mid = r.mission()
    r.propose(mid, task('t1', 'write_repo'))
    _dispatchable(r, mid)
    (t,) = r.all(entities.Task)
    eid = r.do(r.work.dispatch_task, task_id=t.id)['execution_id']
    first = r.do(r.authz.evaluate_action, execution_id=eid, action=PUSH)
    a = r.one(entities.Approval, id=first['approval_id'])
    r.decide(a)
    time.sleep(1.7)
    again = r.do(r.authz.evaluate_action, execution_id=eid, action=PUSH)
    assert again['decision'] == 'ASK'
    assert again['approval_id'] != a.id
    assert r.one(entities.Approval, id=again['approval_id']).state == 'PENDING'
    assert r.one(entities.Approval, id=a.id).state == 'EXPIRED'


def test_a_start_decision_records_the_e_stop_that_was_armed(r):
    mid = r.do(commands.create_mission, who=r.user, title='M', objective='o',
               success_criteria=[AUTO])['id']
    os.makedirs(paths.run_dir(), exist_ok=True)
    open(paths.stop_sentinel(), 'w').close()
    try:
        r.do(r.authz.gate_start, mission_id=mid)
    finally:
        os.remove(paths.stop_sentinel())
    d = r.one(entities.PolicyDecision, mission_id=mid, stage='start')
    assert d.estop is True


@pytest.mark.parametrize('bad', ['tomorrow', '2099-1', '2099-01-01', 'soon'])
def test_a_rule_expiry_that_is_not_a_timestamp_is_refused(r, bad):
    with pytest.raises(ValueError, match='expires_at'):
        r.rule('USER', 'deploy', 'DENY', expires_at=bad)
    assert r.all(entities.PolicyRule) == []


def test_a_rule_expiry_is_stored_in_the_form_the_engine_compares(r):
    r.rule('USER', 'deploy', 'DENY', expires_at='2099-01-01T00:00:00Z')
    (rule,) = r.all(entities.PolicyRule)
    assert rule.expires_at == '2099-01-01T00:00:00.000Z'


@pytest.mark.parametrize('level,ref', [('MISSION', 'mission:typo'), ('TASK', 'tsk_nope'),
                                       ('PROJECT', 'prj_nope'), ('WORKSPACE', 'ws_nope'),
                                       ('USER', 'usr_nope')])
def test_a_rule_scoped_to_something_that_does_not_exist_is_refused(r, level, ref):
    with pytest.raises(ValueError, match='scope_ref'):
        r.rule(level, 'deploy', 'DENY', scope_ref=ref)
    assert r.all(entities.PolicyRule) == []


def test_a_rule_scoped_to_a_real_mission_and_the_global_workspace_is_made(r):
    mid = r.mission()
    r.rule('MISSION', 'deploy', 'DENY', scope_ref=mid)
    r.rule('WORKSPACE', 'deploy', 'ASK', scope_ref='ws_global')
    assert len(r.all(entities.PolicyRule)) == 2


def test_a_denial_is_not_written_onto_a_mission_that_has_been_cancelled(r):
    mid = r.do(commands.create_mission, who=r.user, title='M', objective='o',
               success_criteria=[AUTO])['id']
    r.rule('MISSION', 'deploy', 'DENY', scope_ref=mid)
    r.do(r.missions.cancel, who=r.user, mission_id=mid, reason='no longer wanted')
    out = r.do(r.authz.record_plan_denial, mission_id=mid, specs=[task('t1', 'deploy')])
    assert out['recorded'] is False
    assert r.m(mid).planning_blocked is None
    assert r.all(entities.PolicyDecision, mission_id=mid) == []
