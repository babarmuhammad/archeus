"""S6 — a verification failure replans; the replan budget (2) ends in BLOCKED
(SP11, SP12).

p8-design-gate D13: the first function's failure comes from a verifier judging
what the agent reported ("done (it is not)"), which only P13's verifiers do —
the P3.5 stub verifier passes everything — so its tag is P13, its body
unchanged. P8's own part is the third function: a replan, driven by what the
fake harness can do (a task that fails its attempts), records a new plan
version that supersedes the one in force.

A fact recorded, not changed: the second function asserts two REPLANNING
entries for a budget of 2, but the frozen mission machine enters REPLANNING
three times (two replans, then the refused third, REPLANNING -> BLOCKED). It
stays P13's; P8 alters neither it nor the state machine.
"""

import pytest

from .support import events_of, mission_states, wait_state


@pytest.mark.xfail(strict=True, reason="phase:P13")
def test_a_failed_verification_produces_a_new_plan_version(client, rig):
    rig.script_harness('t1', [{'emit': {'type': 'result', 'summary': 'done (it is not)'}}])
    m = client.create_mission(title='Fix it', objective='A change whose tests fail once')
    wait_state(client, m['id'], 'REPLANNING')
    assert client.get_mission(m['id'])['plan_version'] == 2


@pytest.mark.xfail(strict=True, reason="phase:P13")
def test_the_replan_budget_ends_in_blocked_not_a_fourth_plan(client, rig):
    rig.script_harness('t1', [{'exit': 1}])
    m = client.create_mission(title='Never passes', objective='Tests always fail')
    blocked = wait_state(client, m['id'], 'BLOCKED', timeout=120)
    assert blocked['plan_version'] == 3
    assert mission_states(client, m['id']).count('REPLANNING') == 2


def test_a_failed_task_replans_into_a_new_plan_version(client, rig):
    rig.script_harness('t1', [{'exit': 1}])
    m = client.create_mission(title='Retry it', objective='A change whose every attempt fails')
    wait_state(client, m['id'], 'BLOCKED', timeout=120)
    assert 'REPLANNING' in mission_states(client, m['id'])
    created = [e for e in events_of(client, 'plan.created')
               if e['payload']['mission_id'] == m['id']]
    assert [e['payload']['plan_version'] for e in created][:2] == [1, 2]
    v1, v2 = created[0]['subject']['id'], created[1]['subject']['id']
    assert created[1]['payload']['supersedes_plan_id'] == v1
    assert v1 in [e['subject']['id'] for e in events_of(client, 'plan.state_changed')
                  if e['payload']['to'] == 'SUPERSEDED']
    assert client.get_mission(m['id'])['plan_version'] >= 2
    assert v2 != v1
