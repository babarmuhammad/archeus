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


def test_the_tui_shows_the_mission_the_api_reports(client, rig):
    """P17: the TUI's Work row says what the API says — read from the frame a
    user sees, the label mapped back through the presentation table."""
    tui = rig.tui()
    m = client.create_mission(title='One model', objective='Seen everywhere')
    for _ in range(50):
        # the TUI's read bracketed by two API reads that agree: the mission did
        # not move while the TUI looked (it reads fast enough to catch it moving)
        before = client.get_mission(m['id'])['state']
        row = tui.mission_row(m['id'])
        if client.get_mission(m['id'])['state'] == before:
            break
    assert row['state'] == before
    assert row['label'].strip()                 # a label, never a glyph alone


@pytest.mark.xfail(strict=True, reason="phase:P19")
def test_every_client_agrees(client, rig):
    m = client.create_mission(title='One model', objective='Seen everywhere')
    views = {rig.gui().mission_card(m['id'])['state'],
             rig.tui().mission_row(m['id'])['state'],
             rig.cli('status', m['id'])['state']}
    assert views == {client.get_mission(m['id'])['state']}
