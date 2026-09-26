"""S1 — a simple coding mission end to end (also SP1–7, SP11–13, IP-B part).

The second function passes since P7 on the P3.5 stub verifier and reviewer,
which is all it asks, so its marker came off (p7-design-gate D3). What only P13
gives — a review independent of the work it reviews — is the third function,
which keeps the row pending until P13.
"""

import pytest

from .support import events_of, mission_states, wait_for, wait_state


def test_a_request_becomes_a_mission_with_a_proposed_plan(client):
    msg = client.submit_message('Add a --version flag to the CLI')
    mission = wait_for(lambda: client.list_missions())[0]
    assert msg['id'] and mission['objective']
    assert 'PLANNING' in mission_states(client, mission['id']) or mission['state'] in (
        'PLANNING', 'APPROVAL_REQUIRED', 'APPROVED')


def test_the_mission_completes_only_after_verification_and_review(client):
    client.submit_message('Add a --version flag to the CLI')
    mission = wait_for(lambda: client.list_missions())[0]
    wait_state(client, mission['id'], 'COMPLETED', timeout=120)
    seen = mission_states(client, mission['id'])
    assert seen.index('VERIFYING') < seen.index('REVIEWING') < seen.index('COMPLETED')
    assert events_of(client, 'review.requested')


@pytest.mark.xfail(strict=True, reason="phase:P13")
def test_the_review_is_independent_of_the_work_it_reviews(client):
    """The P3.5 stub reviewer is `stub` and never independent; P13's reviewer is
    the brain on another model or account, or the user, and says so on the
    review it requests."""
    client.submit_message('Add a --version flag to the CLI')
    mission = wait_for(lambda: client.list_missions())[0]
    wait_state(client, mission['id'], 'COMPLETED', timeout=120)
    reviews = [e for e in events_of(client, 'review.requested')
               if e['payload']['mission_id'] == mission['id']]
    assert reviews and all(r['payload'].get('independent') is True for r in reviews)
