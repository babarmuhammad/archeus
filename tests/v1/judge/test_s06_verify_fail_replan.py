"""S6 — a verification failure replans; the replan budget (2) ends in BLOCKED
(SP11, SP12)."""

import pytest

from .support import mission_states, wait_state


@pytest.mark.xfail(strict=True, reason="phase:P8")
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
