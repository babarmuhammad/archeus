"""S9 — feedback becomes durable knowledge, and supersession keeps history (SP14)."""

import pytest

from .support import events_of, wait_for


@pytest.mark.xfail(strict=True, reason="phase:P6")
def test_feedback_becomes_a_candidate_preference(client):
    client.submit_message('From now on, always write commit messages in English.')
    fb = wait_for(lambda: events_of(client, 'feedback.received'))
    assert fb[0]['payload']['promoted']['state'] == 'CANDIDATE'


@pytest.mark.xfail(strict=True, reason="phase:P6")
def test_a_superseding_preference_keeps_the_old_one_as_history(client):
    client.submit_message('Use tabs.')
    client.submit_message('Actually, use four spaces, not tabs.')
    fb = wait_for(lambda: len(events_of(client, 'feedback.received')) == 2
                  and events_of(client, 'feedback.received'))
    new = fb[-1]['payload']['promoted']
    assert new['supersedes_id'] == fb[0]['payload']['promoted']['id']
