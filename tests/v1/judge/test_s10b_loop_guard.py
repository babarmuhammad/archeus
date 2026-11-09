"""S10b — a self-triggering automation escalates at depth 3 and is suspended
after three escalations; it never silently drops (state-machines §8,
p14-design-gate §10)."""

from .support import wait_for


def _loop(client):
    """Every mission it asks for is itself a `mission.created`: a loop."""
    a = client.create_automation(name='loop', trigger={'type': 'mission.created'},
                                 template={'title': 'again', 'objective': 'go round again'},
                                 rate_limit=50)
    client.set_automation_state(a['id'], 'enable')
    return a['id']


def _escalated(client, aid):
    return [r for r in client.automation(aid)['runs'] if r['state'] == 'ESCALATED']


def test_a_self_triggering_automation_escalates_at_depth_three(client, rig):
    aid = _loop(client)
    client.create_mission(title='seed', objective='start the loop')
    (run,) = wait_for(lambda: _escalated(client, aid))
    assert run['depth'] == 4 and 'not dropped' in run['reason']
    assert run['mission_id'] is None
    made = [r for r in client.automation(aid)['runs'] if r['mission_id']]
    assert sorted(r['depth'] for r in made) == [1, 2, 3]


def test_three_escalations_suspend_the_automation(client, rig):
    aid = _loop(client)
    for i in range(3):
        client.create_mission(title='seed', objective='start the loop %d' % i)
    wait_for(lambda: client.automation(aid)['state'] == 'SUSPENDED')
    assert len(_escalated(client, aid)) == 3
    assert [a['state'] for a in client.automations()] == ['SUSPENDED']
