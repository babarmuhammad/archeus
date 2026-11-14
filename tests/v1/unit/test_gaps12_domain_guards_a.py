"""T-1428: the approval and plan gates of archeus/core/domain/guards.py, lines 274-313
at tip 026ea58e: approve_mission (274-282), plan_denied (285-290), ready (295-301),
approve (306-313). Ranked, denial and fail-closed first:

1. 277-278 approve_mission: no plan in force refuses with 'no active plan' even when APPROVED.
2. 279-281 approve_mission: no approval supplied reads 'none requested'.
3. 279-281 approve_mission: a non-APPROVED state (DENIED) is named in the refusal.
4. 277 before 279: the missing plan is reported before the missing approval.
5. 282 approve_mission: APPROVED passes and the reason names the plan version.
6. 290 plan_denied: a recorded denial id passes and the reason carries that id.
7. 290 plan_denied: no other mission fact passes it (only a denial id does).
8. 299 ready: a missing recorded digest refuses even when the facts digest is also None or ''.
9. 299-301 ready: equal digests with no problems pass, with the exact reason.
10. 307 before 309 approve: the actor check runs before the action-hash check.
11. 313 approve: a matching decision passes and the reason names the exact action.

Pure functions only: plain entities, no database, no clock, no OS.
"""

import types

import pytest

from archeus.core.domain import entities as E
from archeus.core.domain import guards, ids
from archeus.core.domain.guards import ApprovalFacts, MissionFacts, PlanFacts

HASH = 'a' * 64


def _mission():
    return E.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                     title='t', objective='o')


def _plan(digest=HASH):
    return E.Plan(id=ids.new_id('plan'), mission_id=ids.new_id('mission'), digest=digest)


def _approval():
    return E.Approval(id=ids.new_id('approval'), subject=E.Ref('task', ids.new_id('task')),
                      action_hash=HASH, requested_by=ids.new_id('principal'))


def test_approve_mission_refuses_with_no_active_plan_even_when_approved():
    got = guards.approve_mission(_mission(), MissionFacts(plan_version=None,
                                                          plan_approval='APPROVED'))
    assert not got.passed
    assert got.reason == 'no active plan'


@pytest.mark.parametrize('plan_approval, named', [(None, 'none requested'),
                                                  ('DENIED', 'DENIED')],
                         ids=['none-requested', 'denied'])
def test_approve_mission_names_the_state_it_refuses_on(plan_approval, named):
    got = guards.approve_mission(_mission(), MissionFacts(plan_version=3,
                                                          plan_approval=plan_approval))
    assert not got.passed
    assert got.reason == 'no approval of plan v3 is APPROVED (%s)' % named


def test_approve_mission_reports_the_missing_plan_before_the_missing_approval():
    got = guards.approve_mission(_mission(), MissionFacts(plan_version=None,
                                                          plan_approval=None))
    assert got.reason == 'no active plan'


def test_approve_mission_passes_and_names_the_plan_version():
    got = guards.approve_mission(_mission(), MissionFacts(plan_version=3,
                                                          plan_approval='APPROVED'))
    assert got.passed
    assert got.reason == 'plan v3 approved by a user device'


def test_plan_denied_passes_and_carries_the_decision_id():
    got = guards.plan_denied(_mission(), MissionFacts(denial='pdc_x'))
    assert got.passed
    assert got.reason == 'policy denies the plan (decision pdc_x)'


def test_plan_denied_is_not_passed_by_any_other_mission_fact():
    f = MissionFacts(plan_version=1, plan_approval='APPROVED', tasks=(), denial=None)
    got = guards.plan_denied(_mission(), f)
    assert not got.passed
    assert got.reason == 'no policy denial is recorded for this plan'


@pytest.mark.parametrize('plan_digest', [None, ''], ids=['none', 'empty'])
def test_ready_refuses_a_plan_with_no_recorded_digest_even_when_facts_have_none(plan_digest):
    got = guards.ready(types.SimpleNamespace(digest=plan_digest), PlanFacts(digest=None))
    assert not got.passed
    assert got.reason == 'the plan content does not match its recorded digest'


def test_ready_passes_on_equal_digests_and_no_problems():
    got = guards.ready(_plan(digest=HASH), PlanFacts(digest=HASH))
    assert got.passed
    assert got.reason == 'Core validated the plan; it is ready for the policy stage'


def test_approve_checks_the_actor_before_the_action_hash():
    got = guards.approve(_approval(), ApprovalFacts('brain', ('approve',), 'b' * 64))
    assert not got.passed
    assert got.reason == 'only a user device with the approve scope decides'


def test_approve_passes_for_this_exact_action_and_names_it():
    got = guards.approve(_approval(), ApprovalFacts('user_device', ('approve',), HASH))
    assert got.passed
    assert got.reason == 'approved by a user device for this exact action'
