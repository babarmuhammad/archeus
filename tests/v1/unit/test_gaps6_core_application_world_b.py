"""T-1263: the ten highest-risk uncovered branches of archeus/core/application/world.py,
source lines 174-301 (complete_inspection, fail_inspection, record_assessment,
sweep_inspections, owner, ack_digest) at worktree d429bf96.

Selected branches and the test that catches each one:
- 228-229 record_assessment: a changed constraint token refuses before the inspection is
  loaded, transitioned or written.
- 184-185 complete_inspection: a second COMPLETED inspection of the revision is refused
  before the Artifact insert and any event.
- 181-182 complete_inspection: a repeated completion returns the first row unchanged.
- 234-239 record_assessment: the same inspection and token is a no-op; a different
  inspection of the same revision refuses until the repository is STALE.
- 242-245 record_assessment: an assessment after a rollback fires revision_moved, then the
  STALE trigger, with facts of the inspection it rests on.
- 186-193 complete_inspection: an existing artifact is not inserted twice, and supplied
  fields override hostile observation keys.
- 209-210 fail_inspection: an UNCOUNTED prefix before the colon keeps the attempt count;
  near-matches and ordinary errors count exactly once.
- 264-268 sweep_inspections: only RUNNING inspections fail, with core_restarted, without
  charging the attempt cap.
- 284-288 ack_digest: bool, negative, float, string and ahead-of-head cursors refuse
  before any write.
- 294-301 ack_digest: equal or older acks change nothing; the first ack creates the owner
  row; forward acks persist with one scoped event.

Seams: lifecycle.load and lifecycle.fire, the transaction, rows.where, drift.token and
drift.violated, outbox.head and queries.view are replaced by one recorder. The domain
entities that the code constructs (Artifact, User) and guards.ArchitectureFacts are real.
Nothing touches a database, git or the filesystem.
"""

import dataclasses
from types import SimpleNamespace

import pytest

from archeus.core.application import lifecycle, world
from archeus.core.domain import guards, ids
from archeus.core.domain.values import Ref
from archeus.core.world import inspection


class Row:
    def __init__(self, entity):
        self.entity = entity


class Env:
    def __init__(self):
        self.data = {}
        self.log = []
        self.head = 5
        self.facts = None

    def put(self, cls_name, entity):
        self.data[(cls_name, entity.id)] = entity
        return entity

    def events(self):
        return [x for x in self.log if x[0] == 'event']

    def writes(self):
        return [x for x in self.log if x[0] in ('insert', 'update', 'fire', 'event')]


class Tx:
    now = 1000

    def __init__(self, env):
        self.env = env
        self.conn = object()

    def get(self, cls, id):
        ent = self.env.data.get((cls.__name__, id))
        return None if ent is None else Row(ent)

    def insert(self, ent, actor=None):
        self.env.data[(type(ent).__name__, ent.id)] = ent
        self.env.log.append(('insert', type(ent).__name__, ent.id))
        return Row(ent)

    def update(self, cls, id, fields, actor=None):
        ent = dataclasses.replace(self.env.data[(cls.__name__, id)], **fields)
        self.env.data[(cls.__name__, id)] = ent
        self.env.log.append(('update', cls.__name__, id, dict(fields)))
        return Row(ent)

    def append(self, event):
        self.env.log.append(('event', event.type, event.payload))

    def where(self, cls):
        return [Row(e) for (n, _), e in list(self.env.data.items()) if n == cls.__name__]


ACTOR = Ref('system', ids.new_id('principal'))

STATE_AFTER = {'start': 'RUNNING', 'retry': 'RUNNING', 'inspected': 'COMPLETED',
               'error': 'FAILED', 'revision_moved': 'STALE', 'first_inspection': 'CONSISTENT',
               'first_inspection_drift': 'DRIFTED', 'reinspected_no_drift': 'CONSISTENT',
               'reinspected_drift': 'DRIFTED'}


@pytest.fixture
def env(monkeypatch):
    e = Env()

    def load(tx, cls, id):
        e.log.append(('load', cls.__name__, id))
        ent = e.data.get((cls.__name__, id))
        if ent is None:
            raise lifecycle.NotFound(id)
        return Row(ent)

    def fire(tx, cls, id, trigger, actor=None, reason='', fields=None, facts=None):
        ent = e.data[(cls.__name__, id)]
        e.log.append(('fire', cls.__name__, id, trigger, dict(fields or {}), facts))
        for k, v in (fields or {}).items():
            setattr(ent, k, v)
        if cls.__name__ == 'Repository':
            ent.architecture_state = STATE_AFTER[trigger]
        else:
            ent.state = STATE_AFTER[trigger]
        if facts is not None:
            e.facts = facts
        return Row(ent), None

    def where(conn, cls, **kw):
        return [Row(ent) for (n, _), ent in list(e.data.items())
                if n == cls.__name__ and all(getattr(ent, k, None) == v for k, v in kw.items())]

    def head(conn):
        e.log.append(('head',))
        return e.head

    monkeypatch.setattr(lifecycle, 'load', load)
    monkeypatch.setattr(lifecycle, 'fire', fire)
    monkeypatch.setattr(world.rows, 'where', where)
    monkeypatch.setattr(world.outbox, 'head', head)
    monkeypatch.setattr(world, 'view', lambda row: {'id': row.entity.id})
    monkeypatch.setattr(world.drift, 'token', lambda current: 'tok-now')
    monkeypatch.setattr(world.drift, 'violated',
                        lambda findings: any(f['status'] == 'violated' for f in findings))
    return e


def repo(**kw):
    base = dict(id='repo-1', project_id='proj-1', workspace_id='ws-1', architecture_state='CONSISTENT',
                last_inspection_id='ins-old', last_revision='rev-A', evaluated_against='tok-now')
    base.update(kw)
    return SimpleNamespace(**base)


def insp(id, state='RUNNING', rev='rev-A', attempts=0, **kw):
    base = dict(id=id, repository_id='repo-1', revision=rev, state=state, attempts=attempts,
                failure=None, extractor_version=inspection.EXTRACTOR_VERSION)
    base.update(kw)
    return SimpleNamespace(**base)


def test_a_changed_constraint_token_refuses_before_the_inspection_is_read(env):
    env.put('Repository', repo())
    env.put('RepositoryInspection', insp('ins-1', state='COMPLETED'))
    with pytest.raises(lifecycle.VersionConflict):
        world.record_assessment(Tx(env), actor=ACTOR, repository_id='repo-1', inspection_id='ins-1',
                                findings=[], evaluated_against='tok-stale')
    assert ('load', 'RepositoryInspection', 'ins-1') not in env.log
    assert env.writes() == []


def test_a_second_completed_inspection_of_the_revision_is_refused_before_any_write(env):
    env.put('Repository', repo())
    env.put('RepositoryInspection', insp('ins-0', state='COMPLETED'))
    env.put('RepositoryInspection', insp('ins-1'))
    with pytest.raises(world.Conflict) as caught:
        world.complete_inspection(Tx(env), actor=ACTOR, inspection_id='ins-1', observation={},
                                  payload_sha256='h1', payload_size=3)
    assert caught.value.detail == {'inspection_id': 'ins-0'}
    assert ('Artifact', 'h1') not in env.data
    assert env.writes() == []


def test_a_repeated_completion_returns_the_first_row_and_ignores_the_new_observation(env):
    env.put('Repository', repo())
    env.put('RepositoryInspection', insp('ins-1', state='COMPLETED', observed='first',
                                         payload_sha256='h-first'))
    out = world.complete_inspection(Tx(env), actor=ACTOR, inspection_id='ins-1',
                                    observation={'observed': 'second'}, payload_sha256='h-second',
                                    payload_size=9, models_added=('m.py',))
    assert out == {'inspection': {'id': 'ins-1'}, 'changed': False}
    stored = env.data[('RepositoryInspection', 'ins-1')]
    assert stored.observed == 'first' and stored.payload_sha256 == 'h-first'
    assert env.writes() == []


def test_the_same_inspection_and_token_is_a_noop_and_another_inspection_of_the_revision_refuses(env):
    env.put('Repository', repo(architecture_state='CONSISTENT', last_inspection_id='ins-1'))
    env.put('RepositoryInspection', insp('ins-1', state='COMPLETED'))
    env.put('RepositoryInspection', insp('ins-2', state='COMPLETED'))
    tx = Tx(env)
    out = world.record_assessment(tx, actor=ACTOR, repository_id='repo-1', inspection_id='ins-1',
                                  findings=[], evaluated_against='tok-now')
    assert out['changed'] is False
    assert env.writes() == []

    with pytest.raises(lifecycle.IllegalTrigger):
        world.record_assessment(tx, actor=ACTOR, repository_id='repo-1', inspection_id='ins-2',
                                findings=[], evaluated_against='tok-now')
    assert env.writes() == []


def test_an_assessment_after_a_rollback_marks_the_repository_stale_and_then_replaces_it(env):
    env.put('Repository', repo(last_inspection_id='ins-2', last_revision='rev-B'))
    env.put('RepositoryInspection', insp('ins-1', state='COMPLETED', rev='rev-A'))
    out = world.record_assessment(Tx(env), actor=ACTOR, repository_id='repo-1', inspection_id='ins-1',
                                  findings=[{'status': 'ok'}], evaluated_against='tok-now')
    fires = [x[:4] for x in env.log if x[0] == 'fire']
    assert fires == [('fire', 'Repository', 'repo-1', 'revision_moved'),
                     ('fire', 'Repository', 'repo-1', 'reinspected_no_drift')]
    assert env.facts == guards.ArchitectureFacts('repo-1', 'COMPLETED', False)
    assert out['changed'] is True
    assert env.data[('Repository', 'repo-1')].last_revision == 'rev-A'


def test_an_existing_artifact_is_not_inserted_twice_and_supplied_fields_win(env):
    env.put('Repository', repo())
    env.put('RepositoryInspection', insp('ins-1'))
    env.put('Artifact', SimpleNamespace(id='h1'))
    hostile = {'payload_sha256': 'evil', 'inspected_at': 0, 'failure': 'hostile', 'files': 4}
    world.complete_inspection(Tx(env), actor=ACTOR, inspection_id='ins-1', observation=hostile,
                              payload_sha256='h1', payload_size=10, diff_from_previous={'added': 1})
    assert not [x for x in env.log if x[0] == 'insert']
    fields = [x for x in env.log if x[0] == 'fire'][0][4]
    assert fields['payload_sha256'] == 'h1'
    assert fields['inspected_at'] == Tx.now
    assert fields['failure'] is None
    assert fields['diff_from_previous'] == {'added': 1}
    assert fields['files'] == 4
    assert hostile['payload_sha256'] == 'evil'


@pytest.mark.parametrize('failure, attempts', [
    ('revision_moved_during: HEAD moved', 1),
    ('core_restarted: Core died', 1),
    ('revision_moved_during_cleanup: x', 2),
    ('core_restarted_now', 2),
    ('git status failed: exit 128', 2),
])
def test_only_the_exact_uncounted_prefix_keeps_the_attempt_count(env, failure, attempts):
    env.put('RepositoryInspection', insp('ins-1', attempts=1))
    world.fail_inspection(Tx(env), actor=ACTOR, inspection_id='ins-1', failure=failure)
    stored = env.data[('RepositoryInspection', 'ins-1')]
    assert stored.attempts == attempts
    assert stored.failure == failure


def test_the_boot_sweep_fails_only_running_inspections_without_charging_the_cap(env):
    env.put('RepositoryInspection', insp('ins-run-1', state='RUNNING', attempts=1))
    env.put('RepositoryInspection', insp('ins-done', state='COMPLETED', attempts=0))
    env.put('RepositoryInspection', insp('ins-run-2', state='RUNNING', attempts=2))
    env.put('RepositoryInspection', insp('ins-failed', state='FAILED', attempts=3))
    out = world.sweep_inspections(Tx(env), actor=ACTOR)
    assert out == {'failed': ['ins-run-1', 'ins-run-2']}
    assert env.data[('RepositoryInspection', 'ins-run-1')].attempts == 1
    assert env.data[('RepositoryInspection', 'ins-run-2')].attempts == 2
    assert env.data[('RepositoryInspection', 'ins-run-2')].failure == 'core_restarted'
    assert env.data[('RepositoryInspection', 'ins-done')].state == 'COMPLETED'
    assert ('fire', 'RepositoryInspection', 'ins-done') not in [x[:3] for x in env.log]


@pytest.mark.parametrize('cursor', [True, False, -1, 1.0, '3'])
def test_a_malformed_cursor_refuses_before_the_head_is_read(env, cursor):
    with pytest.raises(ValueError):
        world.ack_digest(Tx(env), actor=ACTOR, up_to_seq=cursor)
    assert env.log == []


def test_a_cursor_ahead_of_the_head_refuses_before_an_owner_row_is_written(env):
    with pytest.raises(ValueError):
        world.ack_digest(Tx(env), actor=ACTOR, up_to_seq=6)
    assert env.writes() == []


def test_equal_and_older_acks_change_nothing(env):
    env.put('User', SimpleNamespace(id='user-1', last_ack_event_seq=5))
    for cursor in (5, 2):
        out = world.ack_digest(Tx(env), actor=ACTOR, up_to_seq=cursor)
        assert out == {'up_to_seq': 5, 'changed': False}
    assert env.events() == []
    assert not [x for x in env.log if x[0] in ('insert', 'update')]
    assert env.data[('User', 'user-1')].last_ack_event_seq == 5


def test_the_first_ack_creates_the_owner_row_and_a_forward_ack_persists_with_one_event(env):
    out = world.ack_digest(Tx(env), actor=ACTOR, up_to_seq=0)
    assert out == {'up_to_seq': 0, 'changed': True}
    created = [e for (n, _), e in env.data.items() if n == 'User']
    assert len(created) == 1 and created[0].last_ack_event_seq == 0
    assert env.events() == [('event', 'user.digest_acked', {'up_to_seq': 0})]

    env.log.clear()
    out = world.ack_digest(Tx(env), actor=ACTOR, up_to_seq=4)
    assert out == {'up_to_seq': 4, 'changed': True}
    assert [x for x in env.log if x[0] == 'update'] == [
        ('update', 'User', created[0].id, {'last_ack_event_seq': 4})]
    assert env.data[('User', created[0].id)].last_ack_event_seq == 4
    assert env.events() == [('event', 'user.digest_acked', {'up_to_seq': 4})]
