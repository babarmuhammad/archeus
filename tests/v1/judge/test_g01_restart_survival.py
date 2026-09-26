"""G1 — domain state is persistent, and a mission is independent of any
session (SP9): kill Core mid-mission, restart, reconcile, continue.

The second function passes since P8, when the rig could script the fake
harness (p8-design-gate D13): what it asserts — the orphan is reconciled and
the task retried to completion — is P3.5's reconciliation, so its marker came
off. What only P11 gives, adopting the live process instead of killing and
retrying it, is the third function, which keeps the row pending until P11.
"""

import pytest

from .support import events_of, wait_for, wait_state


def test_a_mission_survives_a_core_restart(client, rig):
    m = client.create_mission(title='Durable', objective='Outlive the process')
    history = client.events(0)
    rig.restart_core(kill=True)
    again = client.get_mission(m['id'])
    assert again['id'] == m['id'] and again['title'] == 'Durable'
    assert client.events(0)[:len(history)] == history


def test_a_restart_mid_execution_reconciles_and_the_mission_continues(client, rig):
    rig.script_harness('t1', [{'sleep': 3}])
    m = client.create_mission(title='Durable', objective='Kill Core while a task runs')
    wait_state(client, m['id'], 'EXECUTING')
    rig.restart_core(kill=True)
    wait_state(client, m['id'], 'COMPLETED', timeout=90)


@pytest.mark.xfail(strict=True, reason="phase:P11")
def test_a_restart_mid_execution_adopts_the_live_process(client, rig):
    """P3.5 kills an orphan and retries its task; P11's execution manager adopts
    a process that is still alive, so the task runs exactly once."""
    rig.script_harness('t1', [{'sleep': 3}])
    m = client.create_mission(title='Durable', objective='Adopt the running task')
    wait_for(lambda: events_of(client, 'execution.started'))    # its process is running
    rig.restart_core(kill=True)
    wait_state(client, m['id'], 'COMPLETED', timeout=90)
    assert len(events_of(client, 'execution.started')) == 1     # the only mission here
