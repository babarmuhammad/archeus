import pytest

from archeus.core.application import knowledge as K
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows

SHA = 'a' * 64


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def _import(db, held_at):
    actor = Ref('system', ids.new_id('principal'))
    return db.writer.execute(K.import_meeting, {
        'actor': actor, 'name': 'kickoff', 'held_at': held_at, 'notes_sha256': SHA,
        'notes_size': 3, 'imported_from': 'n.md'})


@pytest.mark.parametrize('held_at', ['2026-31-12', '2026-13-45', 'soon', '2026-09-20T99:00'])
def test_a_meeting_is_never_dated_with_a_moment_the_context_cannot_read(db, held_at):
    with pytest.raises(ValueError):
        _import(db, held_at)
    with db.read() as r:
        assert rows.where(r, entities.Meeting) == []


def test_a_real_date_is_still_imported(db):
    assert _import(db, '2026-09-20')['meeting']['held_at'] == '2026-09-20'
