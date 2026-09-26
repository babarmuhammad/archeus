"""S9 — feedback becomes durable knowledge, and supersession keeps history (SP14).

Driven through `submit_message`: deciding that a message is feedback, and which
earlier preference it supersedes, is intent (P7). P6 built what it lands on —
feedback promoted to a CANDIDATE, explicit supersession keeping the old item as
history (tests/v1/integration/test_knowledge.py).
"""

from .support import events_of, wait_for


def test_feedback_becomes_a_candidate_preference(client):
    client.submit_message('From now on, always write commit messages in English.')
    fb = wait_for(lambda: events_of(client, 'feedback.received'))
    assert fb[0]['payload']['promoted']['state'] == 'CANDIDATE'


def test_a_superseding_preference_keeps_the_old_one_as_history(client):
    client.submit_message('Use tabs.')
    client.submit_message('Actually, use four spaces, not tabs.')
    fb = wait_for(lambda: len(events_of(client, 'feedback.received')) == 2
                  and events_of(client, 'feedback.received'))
    new = fb[-1]['payload']['promoted']
    assert new['supersedes_id'] == fb[0]['payload']['promoted']['id']
