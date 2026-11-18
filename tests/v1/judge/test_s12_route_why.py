"""S12 — explain why a resource was selected (SP18): the answer is generated
from the persisted RouteDecision, with no model call, and replays equal."""

from .support import wait_state


def test_route_why_names_the_selected_account_and_the_reason(client):
    a = client.register_account(harness_id='fake', label='Work', auth_kind='api_key')
    client.set_resource_policy(a['id'], priority=1)
    m = client.create_mission(title='Why', objective='One task')
    wait_state(client, m['id'], 'COMPLETED')
    why = client.route_why(m['id'])
    assert why['selected'] == a['id']
    assert 'priority' in why['explanation'] and 'Work' in why['explanation']


def test_asking_twice_gives_the_same_answer(client):
    a = client.register_account(harness_id='fake', label='Work', auth_kind='api_key')
    client.set_resource_policy(a['id'], priority=1)
    m = client.create_mission(title='Why', objective='One task')
    wait_state(client, m['id'], 'COMPLETED')
    assert client.route_why(m['id']) == client.route_why(m['id'])
