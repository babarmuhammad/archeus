"""A session's cwd is validated before a session is registered or launched: it
must be an existing absolute directory, inside the project's roots when the
session names a project."""

import pytest

from archeus.core.domain import entities, ids
from archeus.core.sessions import service as SV

from .test_gaps_core_sessions_service import USER, Rig


@pytest.fixture
def rig(tmp_path, monkeypatch):
    work = tmp_path / 'work'
    work.mkdir()
    r = Rig(work)
    monkeypatch.setattr(SV, 'rows', r.rows)
    return r


def _project(rig, *roots):
    rig.rows.table[entities.Project] = {}
    return rig.rows.put(entities.Project(id=ids.new_id('project'),
                                         workspace_id=ids.GLOBAL_WORKSPACE, name='p',
                                         root_paths=tuple(str(r) for r in roots))).id


@pytest.mark.parametrize('operation', ['register', 'launch'])
@pytest.mark.parametrize('bad', ['work', '.', '', 'missing-dir'])
def test_a_relative_cwd_is_refused_and_nothing_is_written(rig, operation, bad):
    with pytest.raises(ValueError, match='not absolute'):
        getattr(rig.service, operation)(USER, harness_id='fake_a', cwd=bad)
    assert rig.names() == [] and rig.term.opened == []


@pytest.mark.parametrize('operation', ['register', 'launch'])
def test_a_cwd_that_does_not_exist_or_is_a_file_is_refused(rig, tmp_path, operation):
    (tmp_path / 'a-file').write_text('x')
    for bad in (tmp_path / 'gone', tmp_path / 'a-file'):
        with pytest.raises(ValueError, match='not a directory'):
            getattr(rig.service, operation)(USER, harness_id='fake_a', cwd=str(bad))
    assert rig.names() == [] and rig.term.opened == []


def test_a_cwd_outside_the_projects_roots_is_refused(rig, tmp_path):
    root = tmp_path / 'root'
    (root / 'sub').mkdir(parents=True)
    (tmp_path / 'rootless').mkdir()
    pid = _project(rig, root)
    for ok in (root, root / 'sub'):
        rig.service.register(USER, harness_id='fake_a', cwd=str(ok), project_id=pid)
    for bad in (tmp_path, tmp_path / 'rootless', root / 'sub' / '..' / '..' / 'rootless'):
        with pytest.raises(ValueError, match='outside the project'):
            rig.service.register(USER, harness_id='fake_a', cwd=str(bad), project_id=pid)
    assert rig.names() == ['open_session'] * 2
