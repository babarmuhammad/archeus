"""S8 — meeting notes are used as context (SP2): import -> mention -> the
context package cites the meeting, with a reason."""

from .support import wait_for


def test_an_imported_meeting_is_cited_when_a_mission_mentions_it(client, tmp_path):
    notes = tmp_path / 'planning-2026-09-20.md'
    notes.write_text('# Planning\nDECISION: the dashboard ships dark-first.\n',
                     encoding='utf-8')
    meeting = client.import_meeting(str(notes))
    m = client.create_mission(title='Dashboard', objective='Build it as agreed in planning')
    pkg = wait_for(lambda: client.get_mission(m['id']).get('context_package'))
    cited = [i for i in pkg['items'] if i['ref']['id'] == meeting['id']]
    assert cited and cited[0]['reason']
