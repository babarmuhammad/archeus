"""G1 — domain state is persistent, and a mission is independent of any
session (SP9): kill Core mid-mission, restart, reconcile, continue."""

import pytest

from .support import wait_state


def test_a_mission_survives_a_core_restart(client, rig):
    m = client.create_mission(title='Durable', objective='Outlive the process')
    history = client.events(0)
    rig.restart_core(kill=True)
    again = client.get_mission(m['id'])
    assert again['id'] == m['id'] and again['title'] == 'Durable'
    assert client.events(0)[:len(history)] == history


@pytest.mark.xfail(strict=True, reason="phase:P11")
def test_a_restart_mid_execution_reconciles_and_the_mission_continues(client, rig):
    rig.script_harness('t1', [{'sleep': 3}])
    m = client.create_mission(title='Durable', objective='Kill Core while a task runs')
    wait_state(client, m['id'], 'EXECUTING')
    rig.restart_core(kill=True)
    wait_state(client, m['id'], 'COMPLETED', timeout=90)
