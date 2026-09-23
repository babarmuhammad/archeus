"""S3 — several accounts registered; the router respects priority (SP7, SP8, IP-C)."""

import pytest

from .support import events_of, wait_state


@pytest.mark.xfail(strict=True, reason="phase:P10")
def test_the_priority_one_account_gets_the_work(client):
    a = client.register_account(harness_id='fake', label='A', auth_kind='api_key')
    b = client.register_account(harness_id='fake', label='B', auth_kind='api_key')
    client.set_resource_policy(a['id'], priority=1, allocation_pct=100)
    client.set_resource_policy(b['id'], priority=2, allocation_pct=80)
    m = client.create_mission(title='Route me', objective='One task')
    wait_state(client, m['id'], 'COMPLETED')
    started = events_of(client, 'execution.started')
    assert {e['payload']['account_id'] for e in started} == {a['id']}


@pytest.mark.xfail(strict=True, reason="phase:P10")
def test_routing_is_deterministic_for_the_same_inputs(client):
    a = client.register_account(harness_id='fake', label='A', auth_kind='api_key')
    client.register_account(harness_id='fake', label='B', auth_kind='api_key')
    client.set_resource_policy(a['id'], priority=1)
    picks = set()
    for i in range(3):
        m = client.create_mission(title='Route %d' % i, objective='Same inputs')
        wait_state(client, m['id'], 'COMPLETED')
        picks.add(client.route_why(m['id'])['selected'])
    assert picks == {a['id']}
