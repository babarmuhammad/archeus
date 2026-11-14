"""T-1262: the uncovered branches of archeus/core/application/world.py lines 40-171
(project ownership, constraint binding and inspection start), denial first.

Selected branches, with the source line each test is built to catch:
- 81  discovery finds two repositories, both owned: Conflict before any insert or event, every taken detail kept
- 78  the ownership lookup is per workspace and per path key, not per project label
- 74  a discovery failure propagates before any insert or event; project roots stay the requested ones
- 110 a spec without a kind is refused before any KnowledgeItem write; a missing project wins over it
- 114 an invalid constraint kind or spec is rejected by the real check_constraint before any write
- 119 an equivalent structured constraint returns changed False; prose duplicates need the exact title
- 135 only CONSISTENT and DRIFTED repositories of the project go STALE
- 149 an existing completed inspection of the same revision and extractor refuses; revision=None bypasses it
- 159 a retry of another repository or revision refuses before any retry or start
- 166 a matching revision never stales; a moved revision stales only assessed states, after start

Rig: a fake transaction over synthetic rows that records every write and
transition in order; real entities and real constraint validation; the real
lifecycle.load; lifecycle.fire replaced by a recorder that applies only the
target state; discovery and path keys replaced by in-memory values. No git,
no filesystem, no subprocess, no network, no Windows-specific call.
"""

import dataclasses

import pytest

from archeus.core.application import lifecycle
from archeus.core.application import world as W
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref

_LETTERS = 'ABCDEFGHJKMNPQRSTVWXYZ'


def _id(kind, letter):
    return ids.PREFIXES[kind] + '_01ARZ3NDEKTSV4RRFFQ69G5F' + letter + 'A'


PRJ = _id('project', 'A')
OTHER_PRJ = _id('project', 'B')
WS = _id('workspace', 'A')
OTHER_WS = _id('workspace', 'B')
REPO_A = _id('repository', 'A')
REPO_B = _id('repository', 'B')
REPO_C = _id('repository', 'C')
REPO_D = _id('repository', 'D')
REPO_E = _id('repository', 'E')
INS_A = _id('repository_inspection', 'A')
INS_B = _id('repository_inspection', 'B')
SYS = Ref('system', _id('principal', 'A'))
EXTRACTOR = W.inspection.EXTRACTOR_VERSION


class Row:
    def __init__(self, entity, version=1):
        self.entity = entity
        self.version = version
        self.created_at = None
        self.updated_at = None


class FakeTx:
    def __init__(self, *rows):
        self.store = {}
        self.log = []
        self.conn = self
        for r in rows:
            self.store[(type(r.entity), r.entity.id)] = r

    def get(self, cls, entity_id):
        return self.store.get((cls, entity_id))

    def where(self, cls, **eq):
        return [r for (c, _), r in self.store.items()
                if c is cls and all(getattr(r.entity, k) == v for k, v in eq.items())]

    def insert(self, entity, *, actor):
        self.log.append(('insert', type(entity).__name__))
        row = Row(entity)
        self.store[(type(entity), entity.id)] = row
        return row

    def append(self, event):
        self.log.append(('append', event.type))

    def ops(self):
        return [entry[0] for entry in self.log]

    def fires(self):
        return [(e[1], e[2], e[3]) for e in self.log if e[0] == 'fire']

    def inserts(self):
        return [e[1] for e in self.log if e[0] == 'insert']


_TARGET = {
    (entities.KnowledgeItem, 'confirm'): 'CONFIRMED',
    (entities.RepositoryInspection, 'start'): 'RUNNING',
    (entities.RepositoryInspection, 'retry'): 'SCHEDULED',
}


def _fake_fire(tx, cls, entity_id, trigger, *, actor, reason, facts=None, expected_version=None,
               cause=(), fields=None, machine=None):
    tx.log.append(('fire', cls.__name__, entity_id, trigger))
    row = lifecycle.load(tx, cls, entity_id)
    target = _TARGET.get((cls, trigger))
    entity = row.entity if target is None else dataclasses.replace(row.entity, state=target)
    new = Row(entity, row.version + 1)
    tx.store[(cls, entity_id)] = new
    return new, None


@pytest.fixture(autouse=True)
def _rig(monkeypatch):
    seq = iter(range(10_000))
    monkeypatch.setattr(W.ids, 'new_id', lambda kind: _id(kind, _LETTERS[next(seq) % 22]))
    monkeypatch.setattr(W.rows, 'get', lambda conn, cls, eid: conn.get(cls, eid))
    monkeypatch.setattr(W.rows, 'where', lambda conn, cls, **eq: conn.where(cls, **eq))
    monkeypatch.setattr(W.inspection, 'path_key', lambda path: 'key:' + path)
    monkeypatch.setattr(lifecycle, 'fire', _fake_fire)


def _project(**kw):
    fields = dict(id=PRJ, workspace_id=WS, name='app', root_paths=('/src',))
    fields.update(kw)
    return Row(entities.Project(**fields))


def _repo(repo_id, *, project=PRJ, workspace=WS, path='/src/a', state=None, revision=None):
    return Row(entities.Repository(id=repo_id, workspace_id=workspace, project_id=project,
                                   path=path, path_key='key:' + path,
                                   architecture_state=state, last_revision=revision))


def _inspection(ins_id, *, repo=REPO_A, revision='abc', state='FAILED', version=EXTRACTOR):
    return Row(entities.RepositoryInspection(id=ins_id, repository_id=repo, revision=revision,
                                             extractor_version=version, state=state))


def _item(item_id, *, constraint=None, title='Layers are clean', state='CONFIRMED',
          type_='ARCHITECTURE'):
    return Row(entities.KnowledgeItem(id=item_id, workspace_id=WS, type=type_, title=title,
                                      project_id=PRJ, origin='explicit', state=state,
                                      constraint=constraint))


def _discover(monkeypatch, found):
    monkeypatch.setattr(W.inspection, 'discover', lambda roots: list(found))


# ── create_project: ownership and discovery ───────────────────────────────

def test_two_discovered_repositories_both_owned_refuse_with_every_detail_and_no_write(monkeypatch):
    _discover(monkeypatch, [('/src/a', 'repo'), ('/src/b', 'repo')])
    tx = FakeTx(_repo(REPO_A, project=OTHER_PRJ, path='/src/a'),
                _repo(REPO_B, project=_id('project', 'C'), path='/src/b'))
    with pytest.raises(W.Conflict, match='repository already registered') as exc:
        W.create_project(tx, actor=SYS, name='new', root_paths=['/src'], workspace_id=WS)
    assert exc.value.detail == {'repositories': [
        {'path': '/src/a', 'repository_id': REPO_A, 'project_id': OTHER_PRJ},
        {'path': '/src/b', 'repository_id': REPO_B, 'project_id': _id('project', 'C')},
    ]}
    assert tx.log == []


def test_a_repository_owned_in_another_workspace_is_not_a_conflict(monkeypatch):
    _discover(monkeypatch, [('/src/a', 'repo')])
    tx = FakeTx(_repo(REPO_A, workspace=OTHER_WS, project=OTHER_PRJ, path='/src/a'))
    out = W.create_project(tx, actor=SYS, name='new', root_paths=['/src'], workspace_id=WS)
    assert out['project']['name'] == 'new'
    assert [r['path'] for r in out['repositories']] == ['/src/a']
    assert tx.inserts() == ['Project', 'Repository']


def test_a_repository_owned_in_the_same_workspace_conflicts_whatever_the_project_label(monkeypatch):
    _discover(monkeypatch, [('/src/a', 'repo')])
    tx = FakeTx(_project(id=OTHER_PRJ, name='a totally different label'),
                _repo(REPO_A, project=OTHER_PRJ, path='/src/a'))
    with pytest.raises(W.Conflict):
        W.create_project(tx, actor=SYS, name='app', root_paths=['/src'], workspace_id=WS)
    assert tx.inserts() == []


def test_a_discovery_failure_propagates_before_any_write(monkeypatch):
    def broken(roots):
        raise RuntimeError('walk failed')
    monkeypatch.setattr(W.inspection, 'discover', broken)
    tx = FakeTx()
    with pytest.raises(RuntimeError, match='walk failed'):
        W.create_project(tx, actor=SYS, name='app', root_paths=['/src'])
    assert tx.log == []


def test_the_project_keeps_the_requested_roots_and_the_repositories_are_the_discovered_ones(monkeypatch):
    _discover(monkeypatch, [('/src/a', 'repo')])
    tx = FakeTx()
    out = W.create_project(tx, actor=SYS, name='app', root_paths=['/src'], workspace_id=WS)
    assert out['project']['root_paths'] == ('/src',)
    assert [r['path'] for r in out['repositories']] == ['/src/a']


# ── declare_constraint: spec, kind, duplicates ────────────────────────────

def test_a_spec_without_a_kind_is_refused_before_any_knowledge_write():
    tx = FakeTx(_project())
    with pytest.raises(ValueError, match='a spec needs a kind'):
        W.declare_constraint(tx, actor=SYS, project_id=PRJ, statement='x', spec={'path': 'a.py'})
    assert tx.log == []


def test_a_missing_project_wins_over_a_spec_without_a_kind():
    tx = FakeTx()
    with pytest.raises(lifecycle.NotFound):
        W.declare_constraint(tx, actor=SYS, project_id=PRJ, statement='x', spec={'path': 'a.py'})
    assert tx.log == []


@pytest.mark.parametrize('kind, spec', [
    ('unknown_kind', {'path': 'a.py'}),
    ('module_exists', {'path': 'a.py', 'extra': 1}),
    ('forbid_dependency', {'from': 'app/a'}),
    ('module_exists', {'path': '../escape.py'}),
])
def test_an_invalid_constraint_is_rejected_by_the_real_check_before_any_write(kind, spec):
    tx = FakeTx(_project())
    with pytest.raises(ValueError):
        W.declare_constraint(tx, actor=SYS, project_id=PRJ, statement='x', kind=kind, spec=spec)
    assert tx.log == []


def test_an_equivalent_structured_constraint_returns_unchanged_whatever_the_key_order():
    existing = _item(_id('knowledge_item', 'A'), title='no cross layer import',
                     constraint={'kind': 'forbid_dependency',
                                 'spec': {'from': 'app/a', 'to': 'app/b'}})
    tx = FakeTx(_project(), existing)
    out = W.declare_constraint(tx, actor=SYS, project_id=PRJ, statement='other words',
                               kind='forbid_dependency', spec={'to': 'app/b', 'from': 'app/a'})
    assert out['changed'] is False
    assert out['stale'] == []
    assert out['knowledge_item']['id'] == existing.entity.id
    assert tx.log == []


def test_a_prose_duplicate_needs_the_exact_title_to_be_unchanged():
    existing = _item(_id('knowledge_item', 'A'), title='Layers are clean')
    tx = FakeTx(_project(), existing)
    same = W.declare_constraint(tx, actor=SYS, project_id=PRJ, statement='Layers are clean')
    assert same['changed'] is False
    other = W.declare_constraint(tx, actor=SYS, project_id=PRJ, statement='Layers are clean!')
    assert other['changed'] is True
    assert tx.inserts() == ['KnowledgeItem']


def test_only_consistent_and_drifted_repositories_of_the_project_go_stale():
    tx = FakeTx(
        _project(),
        _repo(REPO_A, path='/src/a', state='UNKNOWN'),
        _repo(REPO_B, path='/src/b', state='STALE'),
        _repo(REPO_C, path='/src/c', state='CONSISTENT', revision='r1'),
        _repo(REPO_D, path='/src/d', state='DRIFTED', revision='r1'),
        _repo(REPO_E, project=OTHER_PRJ, path='/src/e', state='CONSISTENT', revision='r1'),
    )
    out = W.declare_constraint(tx, actor=SYS, project_id=PRJ, statement='new rule')
    assert out['changed'] is True
    assert out['stale'] == [REPO_C, REPO_D]
    stale_fires = [f for f in tx.fires() if f[1] != out['knowledge_item']['id']]
    assert stale_fires == [('Repository', REPO_C, 'constraints_changed'),
                           ('Repository', REPO_D, 'constraints_changed')]


# ── begin_inspection: completed revisions, retries, revision moves ────────

def test_an_existing_completed_inspection_of_the_revision_refuses_before_insert_or_start():
    tx = FakeTx(_repo(REPO_A, state='UNKNOWN'),
                _inspection(INS_A, state='COMPLETED', revision='abc'))
    with pytest.raises(W.Conflict, match='revision already inspected') as exc:
        W.begin_inspection(tx, actor=SYS, repository_id=REPO_A, revision='abc')
    assert exc.value.detail == {'revision': 'abc'}
    assert tx.log == []


def test_a_revision_of_none_bypasses_the_completed_lookup():
    tx = FakeTx(_repo(REPO_A, state='UNKNOWN'),
                _inspection(INS_A, state='COMPLETED', revision=None))
    out = W.begin_inspection(tx, actor=SYS, repository_id=REPO_A, revision=None)
    assert out['state'] == 'RUNNING'
    assert tx.inserts() == ['RepositoryInspection']


def test_a_completion_by_another_extractor_version_does_not_block_the_revision():
    tx = FakeTx(_repo(REPO_A, state='UNKNOWN'),
                _inspection(INS_A, state='COMPLETED', revision='abc', version=EXTRACTOR + 1))
    out = W.begin_inspection(tx, actor=SYS, repository_id=REPO_A, revision='abc')
    assert out['state'] == 'RUNNING'


@pytest.mark.parametrize('other_repo, other_revision', [
    (REPO_B, 'abc'),
    (REPO_A, 'def'),
])
def test_a_retry_of_another_repository_or_revision_refuses_before_any_transition(
        other_repo, other_revision):
    tx = FakeTx(_repo(REPO_A, state='UNKNOWN'),
                _inspection(INS_A, repo=other_repo, revision=other_revision, state='FAILED'))
    with pytest.raises(ValueError, match='a retry is of the same repository and revision'):
        W.begin_inspection(tx, actor=SYS, repository_id=REPO_A, revision='abc', retry_of=INS_A)
    assert tx.fires() == []
    assert tx.inserts() == []


def test_a_retry_of_the_same_repository_and_revision_reuses_the_inspection_id():
    tx = FakeTx(_repo(REPO_A, state='UNKNOWN'),
                _inspection(INS_A, state='FAILED', revision='abc'))
    out = W.begin_inspection(tx, actor=SYS, repository_id=REPO_A, revision='abc', retry_of=INS_A)
    assert out['inspection_id'] == INS_A
    assert tx.inserts() == []
    assert [f[1:] for f in tx.fires()] == [(INS_A, 'retry'), (INS_A, 'start')]


def test_a_matching_revision_never_stales_the_repository():
    tx = FakeTx(_repo(REPO_A, state='CONSISTENT', revision='abc'))
    out = W.begin_inspection(tx, actor=SYS, repository_id=REPO_A, revision='abc')
    assert out['stale'] is False
    assert all(f[2] != 'revision_moved' for f in tx.fires())


@pytest.mark.parametrize('state', [None, 'UNKNOWN', 'STALE'])
def test_a_moved_revision_does_not_stale_a_repository_that_was_never_assessed(state):
    tx = FakeTx(_repo(REPO_A, state=state, revision='aaa'))
    out = W.begin_inspection(tx, actor=SYS, repository_id=REPO_A, revision='bbb')
    assert out['stale'] is False
    assert all(f[2] != 'revision_moved' for f in tx.fires())


def test_a_moved_revision_stales_an_assessed_repository_after_the_inspection_starts():
    tx = FakeTx(_repo(REPO_A, state='DRIFTED', revision='aaa'))
    out = W.begin_inspection(tx, actor=SYS, repository_id=REPO_A, revision='bbb')
    assert out['stale'] is True
    assert [f[2] for f in tx.fires()] == ['start', 'revision_moved']
    assert tx.fires()[1][0] == 'Repository'


def test_a_none_revision_never_stales_even_an_assessed_repository():
    tx = FakeTx(_repo(REPO_A, state='CONSISTENT', revision='aaa'))
    out = W.begin_inspection(tx, actor=SYS, repository_id=REPO_A, revision=None)
    assert out['stale'] is False
    assert all(f[2] != 'revision_moved' for f in tx.fires())
