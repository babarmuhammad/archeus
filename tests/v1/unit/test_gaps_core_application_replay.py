"""T-729: the highest-risk uncovered branches of
`archeus/core/application/replay.py` — the fail-closed and denial paths first
(a settlement a forged event must not buy, foreign rows that must never be
read, missions that do not exist), then the boundary values of `_files` and
`history`, then the error paths (a corrupt event payload, and the read-only
idempotency of `replay` itself).

Style, fixtures and the seeded-world helper follow the closest existing
tests: tests/v1/integration/test_replay.py (module fixtures and `_read`) and
tests/v1/unit/test_gaps_core_application_executions.py (unit-level seeding on
the tmp ARCHEUS_HOME every v1 test already gets; no integration fixtures are
imported). Platform-neutral: a real SQLite only — no OS calls, no clock, no
network, nothing Windows-specific. Each test names the source branch whose
removal or inversion it would catch; the companion list is in the T-729 report.
"""

import json

import pytest

from archeus.api import schemas
from archeus.core.application import replay
from archeus.core.domain import entities, ids, states
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows
from archeus.infra.db.writer import NotFound
from archeus.infra.eventlog import retention


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def _principal(kind='user_device'):
    return Ref(kind, ids.new_id('principal'))


def _seed(db, actor, *new_rows):
    """Insert entity rows as one writer command; the writer refuses a mutation
    with no event, so it carries one filler event about a mission no test
    reads (the exact `_tx` pattern of tests/v1/integration/test_ui_seams.py)."""
    def command(tx, **_):
        for row in new_rows:
            tx.insert(row, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                            actor, payload={}, workspace=ids.GLOBAL_WORKSPACE))
    return db.writer.execute(command, {})


def _edges(db, actor, *specs):
    """Append `machine.state_changed` events, one command, so their seq order
    is their commit order. spec = (subject_id, machine, from, to, trigger)."""
    def command(tx, **_):
        for subject_id, machine, frm, to, trigger in specs:
            tx.append(new_event(machine + '.state_changed',
                                Ref(ids.kind_of(subject_id), subject_id), actor,
                                payload={'from': frm, 'to': to, 'trigger': trigger},
                                workspace=ids.GLOBAL_WORKSPACE))
    return db.writer.execute(command, {})


def _read(db, mid):
    with db.read() as conn:
        result = replay.replay(conn, mid)
    schemas.validate(result, schemas.TYPES['Replay'])
    return result


def _record(result, id_, machine=None):
    return next(r for r in result['records'] if r['ref']['id'] == id_
                and (machine is None or r['machine'] == machine))


def _world(db, *, mission_state='EXECUTING', plan_state='APPROVED',
           task_state='PENDING', integration_state=None,
           exec_state='ENDED_OK', exec2=None, **exec_kw):
    """A mission with one plan, one task and one execution on a real database
    (plus a second task with its own execution when *exec2* names a state).
    Returns (user, system, ids)."""
    user, system = _principal(), _principal('system')
    k = {kind: ids.new_id(kind) for kind in ('mission', 'plan', 'task', 'execution')}
    new = [
        entities.Mission(id=k['mission'], workspace_id=ids.GLOBAL_WORKSPACE,
                         title='M', objective='o', state=mission_state),
        entities.Plan(id=k['plan'], mission_id=k['mission'], state=plan_state),
        entities.Task(id=k['task'], plan_id=k['plan'], mission_id=k['mission'],
                      key='t', title='T', kind='code_change', state=task_state,
                      integration_state=integration_state),
        entities.Execution(id=k['execution'], task_id=k['task'], mission_id=k['mission'],
                           plan_id=k['plan'], state=exec_state, **exec_kw)]
    if exec2 is not None:
        k['task2'] = ids.new_id('task')
        k['execution2'] = ids.new_id('execution')
        new += [
            entities.Task(id=k['task2'], plan_id=k['plan'], mission_id=k['mission'],
                          key='t2', title='T2', kind='code_change', state=task_state),
            entities.Execution(id=k['execution2'], task_id=k['task2'],
                               mission_id=k['mission'], plan_id=k['plan'], state=exec2)]
    _seed(db, user, *new)
    return user, system, k


def _checkpoint(k, **kw):
    base = dict(id=ids.new_id('checkpoint'), execution_id=k['execution'],
                mission_id=k['mission'], task_id=k['task'], trigger='task_boundary',
                files_changed=('M a.py',))
    base.update(kw)
    return entities.Checkpoint(**base)


# ── fail-closed: a settlement must be proven, never claimed ──────────────────

def test_a_forged_settlement_event_is_never_reconciled(db):
    """replay.py:113-114 (`matches = ... and any(edge == ... for ... in
    states.edges(machine))`) and replay.py:126-127 (`elif answer ==
    'RECONCILED': answer, reason = 'UNKNOWN', settlement_reason`). The real
    execution table has exactly one `reconciled_kill` edge — LOST →
    ENDED_KILLED (states.py:200) — so this RUNNING → ENDED_KILLED claim is
    not an edge. Were the `any(...)` check dropped (or the edge table skipped),
    any device that could append one row would certify a kill as reconciled;
    fail-closed, the answer is UNKNOWN and every settlement field is empty."""
    assert ('RUNNING', 'ENDED_KILLED', 'reconciled_kill') not in [
        (f, t, tr) for f, t, tr, _g in states.edges('execution')]
    user, system, k = _world(db, exec_state='ENDED_KILLED')
    _edges(db, system, (k['execution'], 'execution', 'RUNNING', 'ENDED_KILLED',
                        'reconciled_kill'))
    rec = _record(_read(db, k['mission']), k['execution'])
    assert (rec['answer'], rec['reason']) == ('UNKNOWN', 'no_retained_transition')
    assert (rec['settled_by'], rec['settlement_seq']) == ('unknown', None)
    assert rec['settlement_reason'] == 'no_retained_transition'


def test_a_settlement_must_describe_where_the_row_actually_stopped(db):
    """replay.py:113 (`payload.get('to') == state`). LOST → RUNNING 'adopted'
    is a real, settling edge (states.py:199), but the row stands at
    ENDED_KILLED. Drop the to == state clause and this stale adoption alone
    would reconcile the kill (answer RECONCILED, settled_by core); the row,
    not the event, holds the state — so the answer falls back to UNKNOWN."""
    assert ('LOST', 'RUNNING', 'adopted') in [
        (f, t, tr) for f, t, tr, _g in states.edges('execution')]
    user, system, k = _world(db, exec_state='ENDED_KILLED')
    _edges(db, system, (k['execution'], 'execution', 'LOST', 'RUNNING', 'adopted'))
    rec = _record(_read(db, k['mission']), k['execution'])
    assert (rec['answer'], rec['settled_by'], rec['settlement_seq']) == (
        'UNKNOWN', 'unknown', None)


@pytest.mark.parametrize('genuine_last', [True, False], ids=['genuine-last', 'forged-last'])
def test_the_highest_seq_state_change_is_the_one_judged(db, genuine_last):
    """replay.py:108-110 (`ORDER BY seq DESC LIMIT 1`). Two claims for one
    execution: the genuine LOST → ENDED_KILLED 'reconciled_kill' edge and a
    forged RUNNING one. Only the newest (highest seq) may decide: with the
    genuine one last the answer is RECONCILED/core at exactly that seq — were
    the ORDER BY dropped (a plain scan takes the first row) the stale forged
    claim would answer UNKNOWN and the honest settlement would be lost; with
    the forged one last it must NOT answer RECONCILED."""
    user, system, k = _world(db, exec_state='ENDED_KILLED')
    forged = (k['execution'], 'execution', 'RUNNING', 'ENDED_KILLED', 'reconciled_kill')
    genuine = (k['execution'], 'execution', 'LOST', 'ENDED_KILLED', 'reconciled_kill')
    _edges(db, system, *((forged, genuine) if genuine_last else (genuine, forged)))
    rec = _record(_read(db, k['mission']), k['execution'])
    if genuine_last:
        assert (rec['answer'], rec['settled_by'], rec['settlement_reason']) == (
            'RECONCILED', 'core', 'event_actor')
        with db.read() as conn:
            newest = conn.execute('SELECT MAX(seq) FROM events WHERE subject_id = ?',
                                  (k['execution'],)).fetchone()[0]
        assert rec['settlement_seq'] == newest
    else:
        assert (rec['answer'], rec['settled_by'], rec['settlement_seq']) == (
            'UNKNOWN', 'unknown', None)


def test_a_mission_that_is_not_a_mission_is_not_found(db):
    """replay.py:152-153 (`if mission is None: raise NotFound`). The existing
    coverage only passes a well-formed but absent mission id; an execution id
    or a shapeless string must meet the same denial, not a KeyError, an
    AttributeError or a fabricated empty replay — NotFound is a LookupError,
    which is what makes the route answer 404 rather than 500."""
    assert issubclass(NotFound, LookupError)
    user, system, k = _world(db)
    with db.read() as conn:
        for bad in (k['execution'], 'clearly-not-an-id', ids.new_id('mission')):
            with pytest.raises(NotFound):
                replay.replay(conn, bad)


def test_checkpoints_that_do_not_belong_to_the_pair_are_dropped(db):
    """replay.py:171-173 (the three filter clauses of the checkpoint
    comprehension: `task_id in tasks and execution_id in executions and
    executions[...].task_id == r.entity.task_id`, plus the rows.where
    mission_id equality). A checkpoint naming a foreign task, a nonexistent
    execution, an execution of another task, or another mission must not be
    rendered as this mission's history; dropping any one clause leaks it."""
    user, system, k = _world(db, exec2='ENDED_OK')
    # FKs force every id a stray names to exist, so each stray can violate its
    # own clause and nothing else: a real task of another mission, a real
    # execution of another mission, a real owned execution of another task.
    other = ids.new_id('mission')
    other_task = ids.new_id('task')
    e_foreign_task = ids.new_id('execution')     # owned, but of the foreign task
    e_foreign_mission = ids.new_id('execution')  # real, owned by the other mission
    e_extra = ids.new_id('execution')            # owned, of our task (attempt 2)
    keep = _checkpoint(k)
    stray = [
        _checkpoint(k, id=ids.new_id('checkpoint'), task_id=other_task,
                    execution_id=e_foreign_task),
        _checkpoint(k, id=ids.new_id('checkpoint'), execution_id=e_foreign_mission),
        _checkpoint(k, id=ids.new_id('checkpoint'), execution_id=k['execution2']),
        _checkpoint(k, id=ids.new_id('checkpoint'), mission_id=other,
                    execution_id=e_extra)]
    _seed(db, user,
          entities.Mission(id=other, workspace_id=ids.GLOBAL_WORKSPACE,
                           title='O', objective='o', state='EXECUTING'),
          entities.Task(id=other_task, plan_id=k['plan'], mission_id=other,
                        key='tx', title='X', kind='code_change', state='PENDING'),
          entities.Execution(id=e_foreign_task, task_id=other_task,
                             mission_id=k['mission'], state='ENDED_OK'),
          entities.Execution(id=e_foreign_mission, task_id=other_task,
                             mission_id=other, attempt=2, state='ENDED_OK'),
          entities.Execution(id=e_extra, task_id=k['task'], mission_id=k['mission'],
                             attempt=2, state='ENDED_OK'),
          keep, *stray)
    result = _read(db, k['mission'])
    assert [c['id'] for c in result['checkpoints']] == [keep.id]
    assert result['checkpoints'][0]['files_are'] == 'unknown'   # no isolation decision


def test_an_artifact_record_naming_another_mission_is_dropped(db):
    """replay.py:174-176 (`if r.entity.mission_id in (None, mission_id)`).
    The record under OUR task that names ANOTHER mission is the case the
    existing task-binding test never plants: loosen the filter (or drop the
    membership test) and another mission's production shows in this replay.
    A NULL mission is trusted (it was always this task's), a foreign one is not."""
    user, system, k = _world(db)
    other = ids.new_id('mission')
    ours, loose, foreign = (ids.new_id('artifact_record') for _ in range(3))
    _seed(db, user,
          entities.Mission(id=other, workspace_id=ids.GLOBAL_WORKSPACE,
                           title='O', objective='o', state='EXECUTING'),
          entities.Artifact(id='d' * 64, media_type='text/x-diff', size=1),
          entities.ArtifactRecord(id=ours, artifact_id='d' * 64,
                                  produced_by=Ref('execution', k['execution']),
                                  kind='patch', task_id=k['task'], mission_id=k['mission']),
          entities.ArtifactRecord(id=loose, artifact_id='d' * 64,
                                  produced_by=Ref('execution', k['execution']),
                                  kind='patch', task_id=k['task'], mission_id=None),
          entities.ArtifactRecord(id=foreign, artifact_id='d' * 64,
                                  produced_by=Ref('execution', k['execution']),
                                  kind='patch', task_id=k['task'], mission_id=other))
    result = _read(db, k['mission'])
    assert [a['id'] for a in result['artifacts']] == [ours, loose]
    assert foreign not in json.dumps(result)


# ── boundary values: what may and may not be reported as known ───────────────

@pytest.mark.parametrize('files, expected', [
    (('M a.py',), 'paths'),
    ((), 'unknown'),
    (('M a.py', '(not measured: 41 files)'), 'unknown'),
    (('M a.py', 7), 'unknown'),
], ids=['seeded-paths', 'empty', 'not-measured', 'non-string'])
def test_paths_are_only_claimed_for_files_that_exist(files, expected):
    """replay.py:142-143 (`if not files or any(not isinstance(f, str) or
    f.startswith('(not measured:') ...: shape = 'unknown'`). On a fully
    seeded execution (both revisions set, the 'paths' candidate) an empty,
    sentinel-carrying or non-string list must downgrade to 'unknown'; deleting
    that override would advertise a clipped or broken summary as durable A/M/D
    paths — the exact honesty contract of the checkpoint."""
    k = {kind: ids.new_id(kind) for kind in ('mission', 'plan', 'task', 'execution')}
    execution = entities.Execution(id=k['execution'], task_id=k['task'],
                                   mission_id=k['mission'], state='ENDED_OK',
                                   seed_revision='a' * 40, import_revision='b' * 40)
    checkpoint = entities.Checkpoint(id=ids.new_id('checkpoint'),
                                     execution_id=k['execution'], mission_id=k['mission'],
                                     task_id=k['task'], trigger='task_boundary',
                                     files_changed=files)
    out = replay._files(checkpoint, execution)
    assert out['files_are'] == expected
    assert out['complete'] is False and out['item_limit'] == 30
    assert out['reason'] == 'checkpoint_is_a_clipped_summary'
    assert out['files_changed'] == list(files)


@pytest.mark.parametrize('isolated, expected', [
    (False, 'summary'), (True, 'unknown'), (None, 'unknown'),
], ids=['not-isolated', 'isolated', 'decision-unknown'])
def test_the_isolation_shape_never_guesses_a_summary(isolated, expected):
    """replay.py:140-141 (`execution.isolated is False`, a strict identity
    check) on an UNSEEDED execution (a seeded one is 'paths' by line 140 and
    is covered above): a plain non-isolated run gives 'summary'; an isolation
    decision (True) or the absence of one (None) proves nothing about files.
    Weaken `is False` to a falsy test and None (never prepared) would be
    reported as a summary."""
    k = {kind: ids.new_id(kind) for kind in ('mission', 'plan', 'task', 'execution')}
    execution = entities.Execution(id=k['execution'], task_id=k['task'],
                                   mission_id=k['mission'], state='ENDED_OK',
                                   isolated=isolated)
    checkpoint = entities.Checkpoint(id=ids.new_id('checkpoint'),
                                     execution_id=k['execution'], mission_id=k['mission'],
                                     task_id=k['task'], trigger='task_boundary',
                                     files_changed=('M a.py',))
    assert replay._files(checkpoint, execution)['files_are'] == expected


def test_a_seeded_checkpoint_with_no_files_is_unknown_through_the_read(db):
    """replay.py:142 end to end: on the real path (rows + events + schema) a
    seeded execution whose checkpoint names no files reports 'unknown', while
    the Replay schema still validates — the empty list may never ride the
    'paths' answer just because the execution was seeded."""
    user, system, k = _world(db, isolated=False, seed_revision='a' * 40,
                             import_revision='b' * 40)
    _seed(db, user, _checkpoint(k, files_changed=()))
    result = _read(db, k['mission'])
    assert [c['files_are'] for c in result['checkpoints']] == ['unknown']


def test_a_failed_check_or_an_unmet_criterion_never_reads_as_passed(db):
    """replay.py:177-180 (`passed` also needs every check `result == 'pass'`
    and every criterion `result == 'satisfied'`, under `state == 'PASSED'`).
    A PASSED row carrying a failing check, or a FAILED row whose checks all
    passed, is recorded but must not be reported as passed; drop either
    `all(...)` and a green row alone becomes a pass."""
    user, system, k = _world(db)
    made = {}
    for name, state, check, criterion, is_pass in (
            ('check-fails', 'PASSED', 'fail', 'satisfied', False),
            ('criterion-unknown', 'PASSED', 'pass', 'unknown', False),
            ('failed-green', 'FAILED', 'pass', 'satisfied', False),
            ('all-green', 'PASSED', 'pass', 'satisfied', True)):
        vid = ids.new_id('verification')
        made[name] = vid
        _seed(db, user, entities.Verification(
            id=vid, subject=Ref('task', k['task']), verifier='code', plan_id=k['plan'],
            state=state, base_revision='e' * 40,
            checks=({'name': 'tests', 'kind': 'command', 'result': check},),
            criteria=({'index': 0, 'text': 'works', 'check': 'automatic',
                       'result': criterion},)))
    result = {v['id']: v for v in _read(db, k['mission'])['verifications']}
    assert [result[made[n]]['validation_recorded'] for n in made] == [True] * 4
    assert [result[made[n]]['passed'] for n in made] == [False, False, False, True]


def test_history_is_recorded_when_the_whole_range_is_retained(db):
    """replay.py:197-199 (`'answer': 'UNKNOWN' if floor or retained is None
    else 'RECORDED'` and reason `'retained_range_only'`). No existing test
    ever asserts the positive answer: with nothing pruned (floor 0, events
    retained) the history must say RECORDED, carry floor/head/oldest_retained_at
    from the real tables and keep the declared gap fields. Invert the
    condition and an honest full range would answer UNKNOWN (or, worse, a
    pruned range would answer RECORDED — that side stays covered by the
    integration prune test)."""
    user, system, k = _world(db)
    _edges(db, system, (k['execution'], 'execution', 'RUNNING', 'ENDED_OK', 'exited_ok'))
    with db.read() as conn:
        first, last = conn.execute('SELECT MIN(seq), MAX(seq) FROM events').fetchone()
        oldest = conn.execute('SELECT MIN(at) FROM events').fetchone()[0]
    history = _read(db, k['mission'])['history']
    assert (history['answer'], history['reason']) == ('RECORDED', 'retained_range_only')
    assert history['floor'] == first - 1 == 0 and history['head'] == last
    assert history['oldest_retained_at'] == oldest
    assert history['event_days'] == retention.EVENT_DAYS
    assert history['open_mission_extension'] is False
    assert history['gap'] == 'open_mission_retention_extension_not_built'


# ── error paths and the read-only replay itself ──────────────────────────────

def test_a_corrupt_state_changed_payload_raises_instead_of_inventing(db):
    """replay.py:111 (`payload = json.loads(event['payload']) if event else
    {}`) on hostile input: the only `execution.state_changed` of an
    ENDED_KILLED row holds a non-JSON payload. The read must blow up with the
    JSON error (a ValueError subclass), on the caller's face — silently
    treating a corrupt claim as `{}` would quietly return UNKNOWN/durable
    answers, which is the fabrication this pins out."""
    user, system, k = _world(db, exec_state='ENDED_KILLED')

    def corrupt(tx, **_):
        tx.execute('INSERT INTO events (id, type, at, actor_kind, actor_id, '
                   'cause_chain, subject_kind, subject_id, workspace_id, project_id, '
                   "visibility, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (ids.new_ulid(), 'execution.state_changed',
                    '2026-01-01T00:00:00.000Z', 'system', system.id, '[]',
                    'execution', k['execution'], ids.GLOBAL_WORKSPACE, None,
                    'system', '{not json'))
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                            user, payload={}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(corrupt, {})
    with db.read() as conn, pytest.raises(ValueError):
        replay.replay(conn, k['mission'])


def test_replay_is_a_pure_read_that_replays_identically(db):
    """replay.py:150-204 as a whole: `replay` is THE observe read of a mission
    (routes CLASS 'observe'; the route test in tests/v1/integration/test_replay.py
    pins that classification). Two reads over an unchanged database — a full
    owned world of plans, tasks, executions, sessions, approvals, reviews,
    checkpoints, artifacts, verifications and settling events — must return
    equal results and must not move a single row, version, event seq or head:
    any accidental write inside the read path shows up here as the digest
    change (and a mutating read is exactly the fail-open this module forbids)."""
    user, system, k = _world(db, integration_state='CONFLICT', isolated=False,
                             exec2='ENDED_KILLED')
    _seed(db, user,
          entities.Session(id=ids.new_id('session'), mission_id=k['mission'],
                           harness_id='fake', workspace_id=ids.GLOBAL_WORKSPACE,
                           cwd='work/project', mode='manual', state='OPEN'),
          entities.Review(id=ids.new_id('review'), mission_id=k['mission'],
                          plan_id=k['plan'], reviewer='critic', state='ACCEPTED'),
          entities.Approval(id=ids.new_id('approval'), subject=Ref('plan', k['plan']),
                            action_hash='a' * 64, requested_by=user.id, kind='plan',
                            mission_id=k['mission'], plan_id=k['plan'], plan_version=1,
                            state='PENDING', expires_at='2999-01-01T00:00:00.000Z'),
          entities.PolicyDecision(id=ids.new_id('policy_decision'), mission_id=k['mission'],
                                  stage='plan', decision='ALLOW', outcome='auto_approved',
                                  reason='policy'),
          entities.Artifact(id='d' * 64, media_type='text/x-diff', size=1),
          entities.ArtifactRecord(id=ids.new_id('artifact_record'), artifact_id='d' * 64,
                                  produced_by=Ref('execution', k['execution']),
                                  kind='patch', task_id=k['task'], mission_id=k['mission']),
          entities.Verification(id=ids.new_id('verification'),
                                subject=Ref('task', k['task']), verifier='code',
                                plan_id=k['plan'], state='PASSED', base_revision='e' * 40,
                                checks=({'name': 'tests', 'kind': 'command',
                                         'result': 'pass'},),
                                criteria=({'index': 0, 'text': 'works',
                                           'check': 'automatic',
                                           'result': 'satisfied'},)),
          _checkpoint(k))
    _edges(db, system,
           (k['execution'], 'execution', 'INTENT', 'STARTING', 'prepared'),
           (k['execution2'], 'execution', 'LOST', 'ENDED_KILLED', 'reconciled_kill'))

    classes = (entities.Mission, entities.Plan, entities.Task, entities.Execution,
               entities.Session, entities.Checkpoint, entities.Verification,
               entities.Review, entities.ArtifactRecord, entities.Approval,
               entities.PolicyDecision)
    tables = tuple(rows.table(cls) for cls in classes) + ('events',)

    def digest():
        with db.read() as conn:
            return {t: [tuple(r) for r in conn.execute('SELECT * FROM %s ORDER BY rowid'
                                                       % t)] for t in tables}

    before = digest()
    first, second = _read(db, k['mission']), _read(db, k['mission'])
    assert first == second
    assert json.dumps(first)                          # a read's result is data
    assert digest() == before                          # nothing was written
    machines = {(r['machine'], r['ref']['kind']) for r in first['records']}
    assert ('integration', 'task') in machines and ('review', 'review') in machines


def test_a_mission_alone_replays_honestly(db):
    """The empty-mission path of replay.py:150-204: rows.get finds the mission
    (line 151, no NotFound), every owned collection is empty (156-182), and
    the answer can only come from the rows — `_binding` with `revision is
    None` answers UNKNOWN / 'starting_state_not_recorded' (97-100), a task
    without an integration_state gets NO integration record (165-166), and
    with no events at all the records stay plain durable_row answers (104-114).
    Fabricating a RECORDED binding, an extra machine or a settlement here is
    reading futures into an empty mission."""
    user, system, k = _world(db, exec_state='ENDED_OK')
    result = _read(db, k['mission'])
    assert result['mission_id'] == k['mission']
    assert result['starting_state'] == {'source': 'Mission.integration_head',
                                        'revision': None, 'answer': 'UNKNOWN',
                                        'reason': 'starting_state_not_recorded'}
    assert [(r['machine'], r['answer']) for r in result['records']] == [
        ('mission', 'MAY-HAVE-TAKEN-EFFECT'), ('plan', 'AUTHORIZED'),
        ('task', 'INTENDED'), ('execution', 'RECORDED')]
    assert all(r['reason'] == 'durable_row' for r in result['records'])
    assert all(r['machine'] != 'integration' for r in result['records'])
    assert [t['id'] for t in result['tasks']] == [k['task']]
    assert [e['id'] for e in result['executions']] == [k['execution']]
    assert result['executions'][0]['starting_state']['answer'] == 'UNKNOWN'
    assert result['checkpoints'] == [] and result['artifacts'] == []
    assert result['verifications'] == [] and result['approvals'] == []
    assert result['policy_decisions'] == []
    assert result['external_effects'] == {'answer': 'UNKNOWN',
                                          'reason': 'external_effects_not_recorded'}
