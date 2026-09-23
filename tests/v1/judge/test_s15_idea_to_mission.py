"""S15 — an idea becomes a mission (IP-A)."""

import pytest

from .support import wait_for


@pytest.mark.xfail(strict=True, reason="phase:P7")
def test_an_idea_is_captured_and_can_be_promoted_to_a_mission(client):
    reply = client.submit_message('Idea: a weekly digest email of what Archeus did.')
    idea = [c for c in reply['cards'] if c['type'] == 'idea'][0]
    client.submit_message('Make the weekly digest idea a mission.')
    missions = wait_for(lambda: client.list_missions())
    assert missions[0]['origin'] == 'idea' and missions[0]['origin_ref'] == idea['ref']['id']
