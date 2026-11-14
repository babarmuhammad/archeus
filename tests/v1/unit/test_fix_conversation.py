import pytest

from archeus.core.domain import entities
from archeus.infra.db import Database

from v1.integration.test_intent import MS, WORK, _decision, brain, make  # noqa: F401


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def test_a_challenge_proceed_does_not_grow_a_mission_that_ended_meanwhile(make):  # noqa: F811
    more = {'kind': 'continue_work', 'target': 'm1',
            'requirements': [{'text': 'print the git hash', 'origin': 'explicit'}],
            'conflicts': [{'ref': 'k1', 'why': 'the decision forbids it'}]}
    r = make([brain(('Add a --version flag to the CLI', WORK), ('Also print the git hash.', more))])
    _decision(r, 'The core never talks to the database directly')
    r.say('Add a --version flag to the CLI')
    _reply, it = r.say('Also print the git hash.')
    assert it.resolution == 'clarification_requested'
    (m,) = r.all(entities.Mission)
    r.run(MS.cancel, mission_id=m.id)
    r.run(r.conv.choose, intent_id=it.id, choice='proceed')
    (m,) = r.all(entities.Mission)
    assert [c['text'] for c in m.requirements] == [c['text'] for c in WORK['requirements']]


def test_an_impossible_date_never_becomes_a_meetings_held_at(make, tmp_path):  # noqa: F811
    from archeus.core.application import queries
    from archeus.core.knowledge import ingest
    notes = tmp_path / 'review.md'
    notes.write_text('# Review\nnothing dated\n', encoding='utf-8')
    r = make([brain()])
    ingest.import_file(r.db, r.user, str(notes), allow_undated=True)
    (ask,) = [m for m in r.read(queries.messages, 'primary') if m['author'] == 'archeus']
    _reply, it = r.say('It was 2026-13-45, I think.', in_reply_to=ask['id'])
    assert r.all(entities.Meeting)[0].held_at is None
    assert it.resolution == 'declined'
