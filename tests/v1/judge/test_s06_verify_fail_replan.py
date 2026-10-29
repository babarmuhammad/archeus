"""S6 — a verification failure replans; the replan budget (2) ends in BLOCKED
(SP11, SP12).

p8-design-gate D13: the first function's failure comes from a verifier judging
the work, which only P13's verifiers do — the P3.5 stub verifier passes
everything — so it was tagged P13. P8's own part is the third function: a
replan, driven by what the fake harness can do (a task that fails its
attempts), records a new plan version that supersedes the one in force.

P13 (p13-design-gate D20): both P13 functions pass, on a fixture repository
whose test fails until `add` adds, with the verification worker judging the
workspace. Their bodies changed in two ways, each recorded in the gate: the
frozen first body asked a verifier to judge "what the agent reported", which
the evidence model forbids (the agent's report is untrusted; the workspace is
judged), so the agent now writes a wrong change and says "done"; and the second
body's `count('REPLANNING') == 2` is the machine's three entries — two replans,
then the refused third, REPLANNING -> BLOCKED — the fact P8 recorded (§23.2)
and this docstring carried since.
"""

import pytest

from .support import events_of, mission_states, wait_for, wait_state


WRONG = [{'emit': {'type': 'tool', 'name': 'Write',
                   'input': {'file_path': 'calc.py', 'content': 'def add(a, b):\n    return a * b\n'}}},
         {'emit': {'type': 'result', 'summary': 'done (it is not)'}}]


@pytest.mark.real_verification
def test_a_failed_verification_produces_a_new_plan_version(client, rig):
    repo = rig.fixture_repo('verify-python')
    rig.script_harness('t1', WRONG)
    m = client.create_mission(title='Fix it', objective='A change whose tests fail once',
                              project_id=repo.project_id)
    wait_for(lambda: 'REPLANNING' in mission_states(client, m['id']), timeout=120)
    wait_for(lambda: client.get_mission(m['id'])['plan_version'] == 2, timeout=120)
    failed = [v for v in client.verifications(m['id']) if v['state'] == 'FAILED']
    assert failed and all(v['subject']['kind'] == 'task' for v in failed)


@pytest.mark.real_verification
def test_the_replan_budget_ends_in_blocked_not_a_fourth_plan(client, rig):
    repo = rig.fixture_repo('verify-python')
    rig.script_harness('t1', WRONG)
    m = client.create_mission(title='Never passes', objective='Tests always fail',
                              project_id=repo.project_id)
    blocked = wait_state(client, m['id'], 'BLOCKED', timeout=180)
    assert blocked['plan_version'] == 3
    assert mission_states(client, m['id']).count('REPLANNING') == 3


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
