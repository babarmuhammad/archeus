"""S2 — a long mission across several sessions (also SP9, SP10, IP-D).

The fake harness reports context pressure at tasks 3 and 6; each hand-off ends
one execution and starts the next from a Core-derived checkpoint, and neither
the task nor the mission changes state because of it.
"""

import pytest

from .support import events_of, mission_states, wait_state


@pytest.mark.xfail(strict=True, reason="phase:P12")
def test_a_mission_survives_two_session_handoffs(client, rig):
    pressure = [{'emit': {'type': 'usage', 'usage': {'input_tokens': 190000}}}]
    rig.script_harness('t3', pressure)
    rig.script_harness('t6', pressure)
    m = client.create_mission(title='Long', objective='Eight small tasks')
    wait_state(client, m['id'], 'COMPLETED', timeout=180)
    ended = events_of(client, 'execution.ended')
    assert sum(1 for e in ended if e['payload'].get('exit_reason') == 'handoff') == 2


@pytest.mark.xfail(strict=True, reason="phase:P12")
def test_a_handoff_never_moves_the_mission_out_of_executing(client, rig):
    rig.script_harness('t3', [{'emit': {'type': 'usage', 'usage': {'input_tokens': 190000}}}])
    m = client.create_mission(title='Long', objective='Hand off once')
    wait_state(client, m['id'], 'COMPLETED', timeout=180)
    seen = mission_states(client, m['id'])
    assert seen.count('EXECUTING') == 1, seen
