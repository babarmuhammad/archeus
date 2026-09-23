"""S13 — ask the current state across projects (SP13): a deterministic status
with no brain, and a brain summary whose every claim links to an object."""

import pytest


@pytest.mark.xfail(strict=True, reason="phase:P4")
def test_status_is_answered_without_the_brain(client):
    client.create_mission(title='One', objective='Something')
    st = client.status()
    assert st['missions'] and st['source'] == 'deterministic'


@pytest.mark.xfail(strict=True, reason="phase:P7")
def test_the_brain_summary_links_every_claim(client):
    client.create_mission(title='One', objective='Something')
    reply = client.submit_message('What is going on across my projects?')
    assert reply['links'] and all(link['ref']['id'] for link in reply['links'])
