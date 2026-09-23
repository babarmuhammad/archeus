"""S4 — quota exhaustion -> policy-controlled fallback; allocation ceilings are
never exceeded at start; crossing one halts at the next boundary (IP-C)."""

import pytest

from .support import events_of, wait_for, wait_state


def _two_accounts(client, fallback):
    a = client.register_account(harness_id='fake', label='A', auth_kind='api_key')
    b = client.register_account(harness_id='fake', label='B', auth_kind='api_key')
    client.set_resource_policy(a['id'], priority=1, allocation_pct=80, reserve_pct=10)
    client.set_resource_policy(b['id'], priority=2, allocation_pct=80, fallback=fallback)
    return a, b


@pytest.mark.xfail(strict=True, reason="phase:P10")
def test_no_execution_starts_on_an_account_at_its_ceiling(client, rig):
    a, b = _two_accounts(client, 'allow')
    rig.usage(a['id'], '5h', 71)            # ceiling = 80 - 10 = 70
    m = client.create_mission(title='Ceiling', objective='One task')
    wait_state(client, m['id'], 'COMPLETED')
    assert all(e['payload']['account_id'] != a['id']
               for e in events_of(client, 'execution.started'))


@pytest.mark.xfail(strict=True, reason="phase:P10")
@pytest.mark.parametrize('fallback,expect', [('allow', 'COMPLETED'),
                                             ('ask', 'approval'),
                                             ('deny', 'BLOCKED')])
def test_fallback_follows_the_account_policy(client, rig, fallback, expect):
    a, b = _two_accounts(client, fallback)
    rig.usage(a['id'], '5h', 100)
    rig.usage(b['id'], '5h', 79)            # over B's task ceiling: fallback decides
    m = client.create_mission(title='Fallback', objective='One task')
    if expect == 'approval':
        assert wait_for(lambda: events_of(client, 'approval.requested'))
    else:
        wait_state(client, m['id'], expect)


@pytest.mark.xfail(strict=True, reason="phase:P12")
def test_crossing_the_ceiling_mid_run_halts_at_the_boundary_and_hands_off(client, rig):
    a, b = _two_accounts(client, 'allow')
    rig.script_harness('t1', [{'emit': {'type': 'error', 'error': 'rate_limit'}}, {'exit': 1}])
    m = client.create_mission(title='Cross', objective='Two tasks')
    wait_state(client, m['id'], 'COMPLETED', timeout=120)
    accounts = [e['payload']['account_id'] for e in events_of(client, 'execution.started')]
    assert accounts[0] == a['id'] and b['id'] in accounts[1:]
