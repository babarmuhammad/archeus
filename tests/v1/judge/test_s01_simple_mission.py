"""S1 — a simple coding mission end to end (also SP1–7, SP11–13, IP-B part)."""

import pytest

from .support import events_of, mission_states, wait_for, wait_state


@pytest.mark.xfail(strict=True, reason="phase:P7")
def test_a_request_becomes_a_mission_with_a_proposed_plan(client):
    msg = client.submit_message('Add a --version flag to the CLI')
    mission = wait_for(lambda: client.list_missions())[0]
    assert msg['id'] and mission['objective']
    assert 'PLANNING' in mission_states(client, mission['id']) or mission['state'] in (
        'PLANNING', 'APPROVAL_REQUIRED', 'APPROVED')


@pytest.mark.xfail(strict=True, reason="phase:P13")
def test_the_mission_completes_only_after_verification_and_review(client):
    client.submit_message('Add a --version flag to the CLI')
    mission = wait_for(lambda: client.list_missions())[0]
    wait_state(client, mission['id'], 'COMPLETED', timeout=120)
    seen = mission_states(client, mission['id'])
    assert seen.index('VERIFYING') < seen.index('REVIEWING') < seen.index('COMPLETED')
    assert events_of(client, 'review.requested')
