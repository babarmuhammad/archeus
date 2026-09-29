"""G3 — GUI, TUI, web and mobile use one backend model (SP17): the same mission
observed from every client reads the same."""

import pytest


def test_the_gui_shows_the_mission_the_api_reports(client, rig):
    """P16: the SPA's Work row, and the state badge inside it, say what the API
    says — read from the page a user sees, not from the API."""
    gui = rig.gui()
    m = client.create_mission(title='One model', objective='Seen everywhere')
    card = gui.mission_card(m['id'])
    now = client.get_mission(m['id'])['state']
    if card['state'] != now:                    # it moved between the two reads: read again
        card, now = gui.mission_card(m['id']), client.get_mission(m['id'])['state']
    assert card['state'] == card['badge_state'] == now
    assert card['label'].strip()                # a label, never a glyph alone


@pytest.mark.xfail(strict=True, reason="phase:P17")
def test_the_tui_shows_the_mission_the_api_reports(client, rig):
    m = client.create_mission(title='One model', objective='Seen everywhere')
    assert rig.tui().mission_row(m['id'])['state'] == client.get_mission(m['id'])['state']


@pytest.mark.xfail(strict=True, reason="phase:P19")
def test_every_client_agrees(client, rig):
    m = client.create_mission(title='One model', objective='Seen everywhere')
    views = {rig.gui().mission_card(m['id'])['state'],
             rig.tui().mission_row(m['id'])['state'],
             rig.cli('status', m['id'])['state']}
    assert views == {client.get_mission(m['id'])['state']}
