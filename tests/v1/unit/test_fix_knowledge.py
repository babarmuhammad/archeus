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


def test_a_forget_selector_without_a_project_never_reaches_every_project(db):
    actor = Ref('system', ids.new_id('principal'))
    pid = ids.new_id('project')
    other = ids.new_id('project')

    def seed(tx, **_):
        for p in (pid, other):
            tx.insert(entities.Project(id=p, workspace_id=ids.GLOBAL_WORKSPACE, name=p,
                                       root_paths=[]), actor=actor)
            K.new_item(tx, actor=actor, workspace_id=ids.GLOBAL_WORKSPACE, project_id=p,
                       type='LESSON', title='keep ' + p, origin='explicit', source_kind='user')
    db.writer.execute(seed, {})
    with pytest.raises(ValueError, match='project_id'):
        db.writer.execute(K.forget, {'actor': actor, 'selector': {'type': 'LESSON'},
                                     'mode': 'purge', 'dry_run': False})
    with db.read() as r:
        assert all(not x.entity.purged for x in rows.where(r, entities.KnowledgeItem))
