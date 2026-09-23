"""S14 — "what changed while I was away?": a per-user cursor, cleared on any device."""

import pytest


@pytest.mark.xfail(strict=True, reason="phase:P4")
def test_the_digest_lists_what_happened_since_the_last_ack(client):
    before = client.digest()
    client.ack(before['up_to_seq'])
    client.create_mission(title='While away', objective='Something new')
    after = client.digest()
    assert after['count'] >= 1 and after['up_to_seq'] > before['up_to_seq']


@pytest.mark.xfail(strict=True, reason="phase:P15")
def test_acknowledging_on_one_device_clears_it_on_the_others(client, rig):
    phone = rig.device('phone', scopes=('observe', 'control'))
    client.create_mission(title='While away', objective='Something new')
    phone.ack(phone.digest()['up_to_seq'])
    assert client.digest()['count'] == 0
