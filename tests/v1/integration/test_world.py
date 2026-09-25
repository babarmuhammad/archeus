"""P4 acceptance, in process (p4-design-gate §13.2, W01–W25): the real world
worker over a real database and real git repositories. No model anywhere.
The HTTP-level scenarios (W18, W26–W30) are test_world_http.py."""

import os
import shutil
import time

import pytest

from archeus.core.application import commands, queries, world
from archeus.core.application.lifecycle import NotFound, VersionConflict
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.world import digest as world_digest
from archeus.core.world import drift, inspection
from archeus.core.world import status as world_status
from archeus.core.world.worker import World, backoff
from archeus.infra.db import rows
from archeus.infra.eventlog import outbox, retention
from claude_sessions import connections
from v1.judge.support import FixtureRepo

NO_CORE_API = {'statement': 'core must not import api', 'kind': 'forbid_dependency',
               'spec': {'from': 'app/core/**', 'to': 'app/api/**'}}


class Clock:
    """Wall time that a test moves forward: `failed_at` is the writer's clock."""

    def __init__(self):
        self.now = time.time()

    def __call__(self):
        return self.now


class Harness:
    def __init__(self, db, parent):
        self.db, self.parent, self.clock = db, parent, Clock()
        reg = lambda kind, scopes: db.writer.execute(commands.register_principal, {
            'kind': kind, 'scopes': scopes})['id']
        self.system = Ref('system', reg('system', ['system']))
        self.user = Ref('user_device', reg('user_device', ['observe', 'control', 'admin']))
        self.world = World(db, actor=self.system, clock=self.clock)

    def run(self, command, key=None, **kw):
        return self.db.writer.execute(command, dict(kw, actor=self.user), idempotency_key=key)

    def pump(self, limit=10):
        for _ in range(limit):
            if not self.world.pass_once()['changed']:
                return
        raise AssertionError('the world did not settle in %d passes' % limit)

    def read(self, fn, *a):
        with self.db.read() as conn:
            return fn(conn, *a)

    def repo(self, rid):
        return self.read(lambda c: rows.get(c, entities.Repository, rid).entity)

    def inspections(self, rid):
        return self.read(lambda c: [r.entity for r in rows.where(
            c, entities.RepositoryInspection, repository_id=rid)])

    def head(self):
        return self.read(outbox.head)

    def events(self, etype, after=0):
        return [e for e in self.read(queries.events, after) if e['type'] == etype]

    def register(self, name, constraints=(), repo=None):
        repo = repo or FixtureRepo.create(name, self.parent)
        p = self.run(world.create_project, name=name, root_paths=[repo.path])
        repo.project_id = p['project']['id']
        repo.repository_id = p['repositories'][0]['id']
        for c in constraints:
            self.run(world.declare_constraint, project_id=repo.project_id, **c)
        return repo


@pytest.fixture
def h(db, tmp_path):
    parent = tmp_path / 'repos'
    parent.mkdir()
    return Harness(db, str(parent))


# ── W01–W03 registration ──

def test_w01_a_project_registers_its_repo_submodule_and_named_worktree(h):
    main = FixtureRepo.create('layered-python', h.parent)
    lib = FixtureRepo.create('layered-ts', h.parent)
    main.git('-c', 'protocol.file.allow=always', 'submodule', 'add', '-q', lib.path, 'vendor/lib')
    main.commit('submodule', {})
    wt = os.path.join(h.parent, 'wt')
    main.git('worktree', 'add', '-q', '-b', 'feature', wt)
    out = h.run(world.create_project, name='p', root_paths=[main.path, wt])
    assert sorted(r['kind'] for r in out['repositories']) == ['repo', 'submodule', 'worktree']
    assert all(r['architecture_state'] == 'UNKNOWN' for r in out['repositories'])
    assert len(h.events('project.created')) == 1 and len(h.events('repository.registered')) == 3


def test_w02_registration_is_idempotent_and_a_repository_has_one_project(h):
    repo = FixtureRepo.create('layered-python', h.parent)
    first = h.run(world.create_project, key='k1', name='p', root_paths=[repo.path])
    head = h.head()
    assert h.run(world.create_project, key='k1', name='p', root_paths=[repo.path]) == first
    assert h.head() == head
    spelled = repo.path.upper() if os.name == 'nt' else repo.path + os.sep
    with pytest.raises(world.Conflict) as e:
        h.run(world.create_project, name='other', root_paths=[spelled])
    assert e.value.detail['repositories'][0]['project_id'] == first['project']['id']
    assert h.head() == head


@pytest.mark.parametrize('roots', [['relative'], [], ['{missing}'], ['{empty}'], ['{file}']])
def test_w03_a_bad_root_is_refused_and_writes_nothing(h, tmp_path, roots):
    (tmp_path / 'empty').mkdir()
    (tmp_path / 'file.txt').write_text('x')
    subst = {'{missing}': str(tmp_path / 'nope'), '{empty}': str(tmp_path / 'empty'),
             '{file}': str(tmp_path / 'file.txt')}
    head = h.head()
    with pytest.raises(ValueError):
        h.run(world.create_project, name='p', root_paths=[subst.get(r, r) for r in roots])
    assert h.head() == head and h.read(world_status.projects) == []


# ── W04–W06 inspection ──

def test_w04_a_first_inspection_observes_and_assesses(h, archeus_home):
    py = h.register('layered-python')
    ts = h.register('layered-ts')
    h.pump()
    for repo in (py, ts):
        (i,) = h.inspections(repo.repository_id)
        r = h.repo(repo.repository_id)
        assert (i.state, i.revision, i.extractor_version) == (
            'COMPLETED', repo.head(), inspection.EXTRACTOR_VERSION)
        assert (r.architecture_state, r.last_revision, r.last_inspection_id) == (
            'CONSISTENT', repo.head(), i.id)
        assert h.read(rows.get, entities.Artifact, i.payload_sha256) is not None
    assert h.inspections(py.repository_id)[0].frameworks == ('fastapi',)
    assert h.inspections(ts.repository_id)[0].test_commands == ('npm test',)
    moves = [e['payload']['trigger'] for e in h.events('architecture.state_changed')]
    assert moves == ['first_inspection', 'first_inspection']
    assert py.git('status', '--porcelain') == ''


def test_w05_an_unchanged_head_costs_nothing(h, monkeypatch):
    h.register('layered-python')
    h.pump()
    head = h.head()
    walked = []
    real = inspection.inspect
    monkeypatch.setattr(inspection, 'inspect', lambda p: walked.append(p) or real(p))
    for _ in range(3):
        assert h.world.pass_once() == {'changed': False, 'done': 0}
    assert h.head() == head and walked == [] and h.world.pending() == 0


def test_w06_a_clean_commit_is_reinspected_and_stays_consistent(h):
    repo = h.register('layered-python', [NO_CORE_API])
    h.pump()
    new = repo.commit('core helper', {'app/core/y.py': 'x = 1\n'})
    assert h.world.pending() == 1
    h.pump()
    r = h.repo(repo.repository_id)
    assert (r.architecture_state, r.last_revision) == ('CONSISTENT', new)
    assert [e['payload']['to'] for e in h.events('architecture.state_changed')] == [
        'CONSISTENT', 'STALE', 'CONSISTENT']
    assert h.read(world_status.status)['drift'] == []


# ── W07–W11 drift per kind, through the worker ──

def test_w07_a_forbidden_import_is_drift(h):
    repo = h.register('layered-python', [NO_CORE_API])
    h.pump()
    repo.commit('core imports api', {'app/core/x.py': 'import app.api\n'})
    h.pump()
    (d,) = h.read(world_status.status)['drift']
    assert (d['constraint'], d['violations'], d['stale']) == (
        'core must not import api', [['app/core/x.py', 'app/api/__init__.py']], False)
    assert h.repo(repo.repository_id).architecture_state == 'DRIFTED'
    # a new constraint makes the assessment stale: its old findings say so
    h.run(world.declare_constraint, project_id=repo.project_id, statement='models exist',
          kind='module_exists', spec={'path': 'app/core/models.py'})
    assert [x['stale'] for x in h.read(world_status.status)['drift']] == [True]
    h.pump()
    assert [x['stale'] for x in h.read(world_status.status)['drift']] == [False]


KINDS = [
    ({'statement': 'api above core', 'kind': 'require_layering',
      'spec': {'layers': ['app/api/**', 'app/core/**']}},
     {'app/core/x.py': 'from app.api import route\n'}),
    ({'statement': 'models exist', 'kind': 'module_exists', 'spec': {'path': 'app/core/models.py'}},
     {'app/core/models.py': None, 'app/api/__init__.py': 'x = 1\n'}),
    ({'statement': 'pydantic 2.7', 'kind': 'framework_pinned',
      'spec': {'package': 'pydantic', 'version': '2.7'}},
     {'pyproject.toml': '[project]\nname = "x"\ndependencies = ["pydantic==1.10.2"]\n'}),
]


@pytest.mark.parametrize('constraint,breaking', KINDS, ids=['layering', 'exists', 'pinned'])
def test_w08_w10_each_kind_is_satisfied_then_violated(h, constraint, breaking):
    repo = h.register('layered-python', [constraint])
    h.pump()
    assert h.repo(repo.repository_id).findings[0]['status'] == 'satisfied'
    repo.commit('break it', breaking)
    h.pump()
    r = h.repo(repo.repository_id)
    assert (r.architecture_state, r.findings[0]['status']) == ('DRIFTED', 'violated')


def test_w11_what_cannot_be_checked_is_said_so_and_is_not_drift(h):
    repo = h.register('layered-python', [
        {'statement': 'docs describe the api', 'kind': 'doc_matches_code',
         'spec': {'doc': 'README.md', 'code': 'app/api/**'}},
        {'statement': 'keep it simple'}])
    h.pump()
    st = h.read(world_status.status)
    assert sorted(u['constraint'] for u in st['unchecked']) == ['docs describe the api',
                                                                 'keep it simple']
    assert all(u['reason'] for u in st['unchecked'])
    assert st['drift'] == [] and h.repo(repo.repository_id).architecture_state == 'CONSISTENT'


# ── W12–W16 constraint and revision changes ──

def test_w12_a_new_constraint_is_evaluated_without_a_new_walk(h, monkeypatch):
    repo = h.register('layered-python')
    repo.commit('api knows core', {})
    h.pump()
    assert h.repo(repo.repository_id).architecture_state == 'CONSISTENT'
    out = h.run(world.declare_constraint, project_id=repo.project_id,
                statement='api must not import core', kind='forbid_dependency',
                spec={'from': 'app/api/**', 'to': 'app/core/**'})
    assert out['stale'] == [repo.repository_id]
    assert h.repo(repo.repository_id).architecture_state == 'STALE'
    monkeypatch.setattr(inspection, 'inspect', lambda p: pytest.fail('walked again'))
    h.pump()
    r = h.repo(repo.repository_id)
    assert r.architecture_state == 'DRIFTED' and len(h.inspections(repo.repository_id)) == 1
    assert [c[0] for c in r.evaluated_constraints] == [out['knowledge_item']['id']]


def test_w13_a_repository_that_violates_from_the_start_starts_drifted(h):
    repo = FixtureRepo.create('layered-python', h.parent)
    repo.commit('core imports api', {'app/core/x.py': 'import app.api\n'})
    h.register('layered-python', [NO_CORE_API], repo=repo)
    h.pump()
    assert [e['payload']['trigger'] for e in h.events('architecture.state_changed')] == [
        'first_inspection_drift']


def test_w14_a_fix_clears_drift_and_the_digest_says_so(h):
    repo = h.register('layered-python', [NO_CORE_API])
    repo.commit('core imports api', {'app/core/x.py': 'import app.api\n'})
    h.pump()
    assert h.repo(repo.repository_id).architecture_state == 'DRIFTED'
    h.run(world.ack_digest, up_to_seq=h.head())
    repo.commit('fix', {'app/core/x.py': 'x = 1\n'})
    h.pump()
    assert h.repo(repo.repository_id).architecture_state == 'CONSISTENT'
    (g,) = h.read(world_digest.digest)['groups']
    assert (g['ref']['id'], g['headline']) == (repo.repository_id, 'drift_cleared')


def test_w15_a_truncated_graph_is_incomplete_and_never_consistent_by_default(h, monkeypatch):
    monkeypatch.setattr(connections, 'MAX_DEP_EDGES', 0)
    repo = h.register('layered-python', [NO_CORE_API])
    h.pump()
    (i,) = h.inspections(repo.repository_id)
    assert i.complete is False
    (u,) = h.read(world_status.status)['unchecked']
    assert u['reason'] == 'graph_truncated'


def test_w16_a_commit_during_the_walk_discards_the_result(h, monkeypatch):
    repo = h.register('layered-python')
    old = repo.head()
    real, moved = inspection.inspect, []

    def racing(path):
        out = real(path)
        if not moved:
            moved.append(repo.commit('during the walk', {'app/core/z.py': 'z = 1\n'}))
        return out
    monkeypatch.setattr(inspection, 'inspect', racing)
    h.pump()
    got = [(i.revision, i.state, i.failure, i.attempts) for i in h.inspections(repo.repository_id)]
    assert got == [(old, 'FAILED', 'revision_moved_during', 0), (moved[0], 'COMPLETED', None, 0)]
    assert h.repo(repo.repository_id).last_revision == moved[0]


# ── W17–W20 failure, restart, duplicates, races ──

def test_w17_a_missing_repository_fails_with_capped_backoff_and_blocks_no_one(h):
    gone = h.register('layered-python')
    other = h.register('layered-ts')
    h.pump()
    shutil.rmtree(gone.path, onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    other.commit('other moves on', {'src/core/more.ts': 'export const m = 1;\n'})
    h.pump()
    fails = [i for i in h.inspections(gone.repository_id) if i.state == 'FAILED']
    assert [(i.failure, i.attempts, i.revision) for i in fails] == [('repository_missing', 1, None)]
    assert h.repo(other.repository_id).last_revision == other.head()
    assert h.repo(gone.repository_id).architecture_state == 'CONSISTENT'   # unchanged
    h.pump()
    assert h.inspections(gone.repository_id)[-1].attempts == 1           # not due yet
    for n in (2, 3):
        h.clock.now += backoff(n - 1) + 1
        h.pump()
        assert h.inspections(gone.repository_id)[-1].attempts == n
    h.clock.now += 10 ** 6
    assert h.world.pending() == 0
    h.pump()
    assert h.inspections(gone.repository_id)[-1].attempts == 3
    st = h.read(world_status.status)
    last = [r for p in st['projects'] for r in p['repositories']
            if r['id'] == gone.repository_id][0]['last_inspection']
    assert (last['state'], last['failure']) == ('FAILED', 'repository_missing')


def test_w19_a_duplicate_completion_is_a_no_op(h):
    repo = h.register('layered-python')
    h.pump()
    (i,) = h.inspections(repo.repository_id)
    head = h.head()
    again = h.db.writer.execute(world.complete_inspection, {
        'actor': h.system, 'inspection_id': i.id, 'observation': {}, 'payload_sha256': i.payload_sha256,
        'payload_size': 1})
    assert again['changed'] is False and h.head() == head
    with pytest.raises(world.Conflict):
        h.db.writer.execute(world.begin_inspection, {'actor': h.system,
                                                     'repository_id': repo.repository_id,
                                                     'revision': repo.head()})


def test_w20_a_constraint_declared_mid_evaluation_is_never_missed(h, monkeypatch):
    repo = h.register('layered-python')
    repo.commit('api knows core', {})
    real, raced = drift.evaluate, []

    def racing(payload, cs):
        out = real(payload, cs)
        if not raced:
            raced.append(h.run(world.declare_constraint, project_id=repo.project_id,
                               statement='api must not import core', kind='forbid_dependency',
                               spec={'from': 'app/api/**', 'to': 'app/core/**'}))
        return out
    monkeypatch.setattr(drift, 'evaluate', racing)
    assert h.world.pass_once()['changed']
    assert h.repo(repo.repository_id).architecture_state == 'UNKNOWN'   # nothing recorded
    with pytest.raises(VersionConflict):
        h.db.writer.execute(world.record_assessment, {
            'actor': h.system, 'repository_id': repo.repository_id,
            'inspection_id': h.inspections(repo.repository_id)[0].id, 'findings': [],
            'evaluated_against': drift.token([])})
    h.pump()
    r = h.repo(repo.repository_id)
    assert r.architecture_state == 'DRIFTED'
    assert [c[0] for c in r.evaluated_constraints] == [raced[0]['knowledge_item']['id']]


def test_w20_the_guard_refuses_an_assessment_its_findings_contradict(h):
    """The edge is bound to the findings: a caller cannot record 'no drift'
    with a violation in hand (or drift without one)."""
    from archeus.core.application import lifecycle
    from archeus.core.domain import guards
    repo = h.register('layered-python')
    h.pump()
    repo.commit('moved', {})
    h.pump()
    (i1, i2) = h.inspections(repo.repository_id)

    def forced(tx, actor):
        lifecycle.fire(tx, entities.Repository, repo.repository_id, 'revision_moved',
                       actor=actor, reason='test')
        lifecycle.fire(tx, entities.Repository, repo.repository_id, 'reinspected_drift',
                       actor=actor, reason='test', facts=guards.ArchitectureFacts.of(i1, False))
    with pytest.raises(lifecycle.GuardFailed):
        h.db.writer.execute(forced, {'actor': h.system})
    other = h.register('layered-ts')
    h.pump()
    (foreign,) = h.inspections(other.repository_id)

    def borrowed(tx, actor):            # another repository's clean inspection
        lifecycle.fire(tx, entities.Repository, repo.repository_id, 'revision_moved',
                       actor=actor, reason='test')
        lifecycle.fire(tx, entities.Repository, repo.repository_id, 'reinspected_no_drift',
                       actor=actor, reason='test', facts=guards.ArchitectureFacts.of(foreign, False))
    with pytest.raises(lifecycle.GuardFailed, match='not of an inspection of this repository'):
        h.db.writer.execute(borrowed, {'actor': h.system})

    def unfinished(tx, actor):          # this repository's, but not COMPLETED
        lifecycle.fire(tx, entities.Repository, repo.repository_id, 'revision_moved',
                       actor=actor, reason='test')
        lifecycle.fire(tx, entities.Repository, repo.repository_id, 'reinspected_no_drift',
                       actor=actor, reason='test', facts=guards.ArchitectureFacts(
                           repo.repository_id, 'RUNNING', False))
    with pytest.raises(lifecycle.GuardFailed, match='not COMPLETED'):
        h.db.writer.execute(unfinished, {'actor': h.system})
    assert i2.state == 'COMPLETED'


def test_a_duplicate_constraint_is_the_same_constraint(h):
    repo = h.register('layered-python', [NO_CORE_API])
    h.pump()
    again = h.run(world.declare_constraint, project_id=repo.project_id, **NO_CORE_API)
    assert again['changed'] is False and again['stale'] == []
    prose = dict(statement='keep it simple')
    first = h.run(world.declare_constraint, project_id=repo.project_id, **prose)
    assert h.run(world.declare_constraint, project_id=repo.project_id, **prose)['changed'] is False
    assert first['changed'] is True
    assert len(h.read(world.constraints, repo.project_id)) == 2


def test_an_extractor_upgrade_is_used_by_the_next_assessment_never_an_old_observation(
        h, monkeypatch):
    """A current assessment stays current across an upgrade (the machine has
    no edge for it); the next thing that makes it stale walks again with the
    new extractor instead of re-evaluating the old one's observation."""
    repo = h.register('layered-python')
    h.pump()
    monkeypatch.setattr(inspection, 'EXTRACTOR_VERSION', inspection.EXTRACTOR_VERSION + 1)
    assert h.world.pending() == 0
    h.run(world.declare_constraint, project_id=repo.project_id, **NO_CORE_API)
    h.pump()
    got = [(i.revision, i.extractor_version, i.state) for i in h.inspections(repo.repository_id)]
    assert got == [(repo.head(), 1, 'COMPLETED'), (repo.head(), 2, 'COMPLETED')]
    r = h.repo(repo.repository_id)
    assert (r.architecture_state, r.last_inspection_id) == (
        'CONSISTENT', h.inspections(repo.repository_id)[1].id)


# ── W21–W22 status and project scoping ──

def test_w21_status_is_deterministic_and_scoped(h):
    a = h.register('layered-python', [NO_CORE_API])
    b = h.register('layered-ts')
    a.commit('core imports api', {'app/core/x.py': 'import app.api\n'})
    m = h.run(commands.create_mission, title='t', objective='o', project_id=b.project_id)

    def legacy(tx, actor):          # a pre-P4 row whose project_id names nothing
        x = entities.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                             project_id=ids.new_id('project'), title='old', objective='o')
        tx.insert(x, actor=actor)
        tx.append(new_event('mission.created', Ref('mission', x.id), actor, payload={}))
        return x.id
    old = h.db.writer.execute(legacy, {'actor': h.user})
    h.pump()
    st = h.read(world_status.status)
    assert st['source'] == 'deterministic' and st == h.read(world_status.status)
    assert [d['repository_id'] for d in st['drift']] == [a.repository_id]
    assert st['unknown_project'] == [old]
    only_b = h.read(world_status.status, b.project_id)
    assert [p['id'] for p in only_b['projects']] == [b.project_id]
    assert [x['id'] for x in only_b['missions']] == [m['id']] and only_b['drift'] == []
    with pytest.raises(NotFound):
        h.read(world_status.status, ids.new_id('project'))


def test_w22_missions_are_scoped_to_registered_projects(h):
    a = h.register('layered-python')
    m = h.run(commands.create_mission, title='t', objective='o', project_id=a.project_id)
    h.run(commands.create_mission, title='u', objective='o')
    assert [x['id'] for x in h.read(queries.list_missions, None, a.project_id)] == [m['id']]
    with pytest.raises(NotFound):
        h.read(queries.list_missions, None, ids.new_id('project'))
    with pytest.raises(NotFound):
        h.run(commands.create_mission, title='t', objective='o', project_id=ids.new_id('project'))


# ── W23–W25 the digest ──

def test_w23_the_cursor_only_moves_forward_and_never_past_the_head(h):
    first = h.read(world_digest.digest)
    assert first['from_seq'] == 0 and first['up_to_seq'] == h.head()
    h.run(commands.create_mission, title='t', objective='o')
    d = h.read(world_digest.digest)
    assert d['count'] == 1 and d['groups'][0]['ref']['kind'] == 'mission'
    up = d['up_to_seq']
    assert h.run(world.ack_digest, up_to_seq=up) == {'up_to_seq': up, 'changed': True}
    assert h.run(world.ack_digest, up_to_seq=up)['changed'] is False
    assert h.run(world.ack_digest, up_to_seq=0) == {'up_to_seq': up, 'changed': False}
    for bad in (h.head() + 1, -1):
        with pytest.raises(ValueError):
            h.run(world.ack_digest, up_to_seq=bad)
    assert h.read(world_digest.digest)['count'] == 0


def test_w24_a_cursor_behind_retention_is_reported_truncated(h):
    h.run(commands.create_mission, title='t', objective='o')
    h.db.writer.execute(retention.prune, {'now': '2999-01-01T00:00:00.000Z', 'keep_days': 0})
    h.run(commands.create_mission, title='u', objective='o')
    d = h.read(world_digest.digest)
    assert d['truncated'] is True and d['from_seq'] == h.read(outbox.floor)
    assert d['count'] == 1


def test_w25_system_events_and_the_ack_itself_are_not_news(h):
    h.run(world.ack_digest, up_to_seq=h.head())
    h.db.writer.execute(commands.register_principal, {'kind': 'system', 'scopes': ['system']})
    h.run(world.ack_digest, up_to_seq=h.head() - 0)
    assert h.read(world_digest.digest)['count'] == 0
