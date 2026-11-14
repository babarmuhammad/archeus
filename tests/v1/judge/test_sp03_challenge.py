"""SP3 — Archeus challenges or clarifies when necessary: a request conflicting
with a CONFIRMED decision yields a Challenge, and no mission runs until the
user chooses."""


def test_a_request_against_a_confirmed_decision_is_challenged(client, tmp_path):
    notes = tmp_path / 'arch-review.md'
    notes.write_text('DECISION: the core never talks to the database directly.\n',
                     encoding='utf-8')
    client.import_meeting(str(notes))
    reply = client.submit_message('Have the core query SQLite directly for speed.')
    assert any(c['type'] == 'challenge' for c in reply['cards'])
    assert all(m['state'] in ('CREATED', 'BLOCKED') for m in client.list_missions())
