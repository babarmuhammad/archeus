"""G3 — GUI, TUI, web and mobile use one backend model (SP17): the same mission
observed from every client reads the same."""

import pytest


@pytest.mark.xfail(strict=True, reason="phase:P16")
def test_the_gui_shows_the_mission_the_api_reports(client, rig):
    m = client.create_mission(title='One model', objective='Seen everywhere')
    assert rig.gui().mission_card(m['id'])['state'] == client.get_mission(m['id'])['state']


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
