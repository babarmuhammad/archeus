"""S14 — "what changed while I was away?": a per-user cursor, cleared on any device."""

from . import support


def test_the_digest_lists_what_happened_since_the_last_ack(client):
    before = client.digest()
    client.ack(before['up_to_seq'])
    client.create_mission(title='While away', objective='Something new')
    after = client.digest()
    assert after['count'] >= 1 and after['up_to_seq'] > before['up_to_seq']


def test_acknowledging_on_one_device_clears_it_on_the_others(client, rig):
    phone = rig.device('phone', scopes=('observe', 'control'))
    client.create_mission(title='While away', objective='Something new')
    # the engine moves the mission on by itself: let it finish, so nothing
    # happens between the phone's ack and the desktop's read (P15)
    support.wait_for(lambda: support.idle())
    phone.ack(phone.digest()['up_to_seq'])
    assert client.digest()['count'] == 0
