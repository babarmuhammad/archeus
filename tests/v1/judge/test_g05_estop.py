"""G5 — the emergency stop exists, with and without Core (execution-architecture §10)."""

import pytest

from .support import events_of, wait_for, wait_state


def test_stop_everything_halts_running_fake_executions(client, rig):
    rig.script_harness('t1', [{'sleep': 30}])
    client.create_mission(title='Runaway', objective='Needs stopping')
    # P11 (p11-design-gate §28): EXECUTING precedes the first dispatch, so wait for
    # the process itself, as G1's adoption function does
    wait_for(lambda: events_of(client, 'execution.started'))
    client.stop('all')
    ended = wait_for(lambda: events_of(client, 'execution.ended'))
    assert ended[0]['payload']['exit_reason'] == 'killed'


@pytest.mark.xfail(strict=True, reason="phase:P20")
def test_the_estop_works_with_core_down_and_core_comes_back_disarmed(client, rig):
    rig.script_harness('t1', [{'sleep': 30}])
    m = client.create_mission(title='Runaway', objective='Core dies first')
    wait_state(client, m['id'], 'EXECUTING')
    rig.estop_without_core()
    rig.restart_core(kill=False)
    assert client.status()['armed'] is False
