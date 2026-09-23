"""G4 — the audit trail exists: every state change has an event naming its
actor, written with the change."""

import pytest


@pytest.mark.xfail(strict=True, reason="phase:P2")
def test_creating_a_mission_records_an_event_with_its_actor(client):
    m = client.create_mission(title='Audited', objective='Leave a trail')
    created = [e for e in client.events(0)
               if e['type'] == 'mission.created' and e['subject']['id'] == m['id']]
    assert len(created) == 1
    assert created[0]['actor']['kind'] == 'user_device'
    assert created[0]['seq'] > 0


@pytest.mark.xfail(strict=True, reason="phase:P2")
def test_the_event_log_is_append_only(client):
    client.create_mission(title='A', objective='first')
    first = client.events(0)
    client.create_mission(title='B', objective='second')
    assert client.events(0)[:len(first)] == first
