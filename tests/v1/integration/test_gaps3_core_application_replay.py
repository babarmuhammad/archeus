"""T-1147: the highest-risk uncovered branches of
`archeus/core/application/replay.py` lines 1-204 inclusive (the whole module at
tip 56d53504 — ANSWER/CATEGORIES 1-95, `_binding` 97-100, `_record` 103-134,
`_files` 137-147, `replay` 150-204). Definitions and imports outside the slice
are read-only context; every branch claimed here is owned inside it.

Fail-closed and denial first, then boundaries, then error paths. The ten
probes the card named were each checked against the existing coverage
(tests/v1/integration/test_replay.py, tests/v1/unit/test_gaps_core_application_replay.py);
the ones already covered were replaced, and the replacement is named here with
the branch it owns:

 1. `_record` 119-123 — a settlement actor whose `actor_kind` claims `system`
    but whose `actor_id` is not a principal id: the `ids.is_id(...)` False arm
    (probe 7 "unreadable settlement actor", existing form varies actor_kind only).
 2. `_record` 108-114 — the `AND type = ?` clause of the state-changed lookup:
    an event of another machine's type must not decide this record (replaces
    probe 2 "foreign checkpoint excluded", covered by
    test_checkpoints_that_do_not_belong_to_the_pair_are_dropped).
 3. `_record` 115-130 — execution LOST whose newest event IS a genuine
    transition: still unsettled (probe 8, existing form plants no event at all).
 4. `_record` 117 + 128 — the `_SETTLEMENT.get(machine, ())` default and the
    `machine == 'execution'` False arm: a LOST *session* has no core sweep
    (replaces probe 3 "unknown machine state", covered by
    test_unknown_is_never_none).
 5. `replay` 183, 197-200 — the `retained is None` with `floor == 0` arm: a log
    that never recorded an event says `no_retained_events`, not RECORDED and
    not `retained_event_prefix_pruned` (replaces probe 4 "pruned history
    remains unknown", covered by test_retention_pruning_loses_attribution_but_keeps_rows
    and test_empty_event_range_is_unknown, which both leave floor > 0).
 6. `_files` 140 — the `seed_revision`/`import_revision` conjunction arms: a
    run that seeded but never imported owns no A/M/D paths (replaces probe 9
    "unmeasured files unknown" half 1, covered by
    test_paths_are_only_claimed_for_files_that_exist).
 7. `_files` 140-141 — the `execution is not None` arms: a checkpoint whose
    execution row is gone is unknown, never a summary (probe 9 half 2).
 8. `_record` 111-114 — a state-changed payload that is valid JSON but not an
    object: it must blow up, never be read as `{}` (replaces probe 5 "missing
    transition event"/probe 6 "event state differs from durable state", both
    covered by test_a_forged_settlement_event_is_never_reconciled and
    test_a_settlement_must_describe_where_the_row_actually_stopped; the corrupt
    non-JSON payload of test_a_corrupt_state_changed_payload_raises_instead_of_inventing
    is the neighbouring case).
 9. `replay` 187-188 + 204 — the homes projection over the task scope (probe
    10, existing form covers only checkpoints.files_changed and a policy
    decision reason).
10. `replay` 151-154 — the missing-mission denial happens BEFORE `queries._homes`
    builds anything (replaces probe 1 "missing mission" as an exception-type
    check, covered by test_a_mission_that_is_not_a_mission_is_not_found).

Platform: Linux here, review on Windows. Everything OS-shaped is faked through
an existing seam — `Homes(shorts=..., path_flavour='windows')`, an invented
account key, an invented `public_account_secret`, and a spy callable for
`homes=` — so no test reads a real home, a real credential, the environment or
a socket. The `tc` fixture (real sockets) is never requested. DB and runtime
files are the `archeus_home`/`tmp_path` area every v1 test already owns. No
sleeps, no threads, no subprocesses, no skips, no source edit.
"""

import json

import pytest

from archeus.api import schemas
from archeus.core.application import replay
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes, public_account_id
from archeus.infra.db import Database
from archeus.infra.db.writer import NotFound
from archeus.infra.eventlog import retention

#: One fixed timestamp for every planted event: this module never reads a clock,
#: and a stored `at` is data here, not an input.
AT = '2026-01-01T00:00:00.000Z'


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def _principal(kind='user_device'):
    return Ref(kind, ids.new_id('principal'))


def _seed(db, actor, *new_rows):
    """Entity rows in one writer command. The writer refuses a mutation with no
    event, so the command carries one filler event about a mission no test
    reads (the `_tx` pattern of tests/v1/integration/test_ui_seams.py)."""
    def command(tx, **_):
        for row in new_rows:
            tx.insert(row, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                            actor, payload={}, workspace=ids.GLOBAL_WORKSPACE))
    return db.writer.execute(command, {})


def _edges(db, actor, *specs):
    """`machine.state_changed` events, one command, so seq order is commit order.
    spec = (subject_id, machine, from, to, trigger)."""
    def command(tx, **_):
        for subject_id, machine, frm, to, trigger in specs:
            tx.append(new_event(machine + '.state_changed',
                                Ref(ids.kind_of(subject_id), subject_id), actor,
                                payload={'from': frm, 'to': to, 'trigger': trigger},
                                workspace=ids.GLOBAL_WORKSPACE))
    return db.writer.execute(command, {})


def _raw_event(db, *, etype, subject_id, actor_kind, actor_id, payload,
               visibility='system'):
    """One event row written as raw SQL, bypassing `new_event`: what a hostile or
    corrupted log holds. Returns its seq (the events rowid)."""
    def command(tx, **_):
        return tx.execute(
            'INSERT INTO events (id, type, at, actor_kind, actor_id, cause_chain, '
            'subject_kind, subject_id, workspace_id, project_id, visibility, payload) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (ids.new_ulid(), etype, AT, actor_kind, actor_id, '[]',
             ids.kind_of(subject_id), subject_id, ids.GLOBAL_WORKSPACE, None,
             visibility, payload if isinstance(payload, str) else json.dumps(payload))).lastrowid
    return db.writer.execute(command, {})


def _wipe_log(db):
    """An event log that never recorded anything: every row gone AND the
    AUTOINCREMENT counter gone, which is what makes `outbox.floor` 0."""
    def command(tx, **_):
        tx.execute('DELETE FROM events')
        tx.execute("DELETE FROM sqlite_sequence WHERE name = 'events'")
    return db.writer.execute(command, {})


def _read(db, mid, **kwargs):
    with db.read() as conn:
        result = replay.replay(conn, mid, **kwargs)
    schemas.validate(result, schemas.TYPES['Replay'])
    return result


def _record(result, id_, machine=None):
    return next(r for r in result['records'] if r['ref']['id'] == id_
                and (machine is None or r['machine'] == machine))


def _world(db, *, mission_state='EXECUTING', plan_state='APPROVED', task_state='PENDING',
           integration_state=None, exec_state='ENDED_OK', task_kw=None, **exec_kw):
    """A mission with one plan, one task, one execution on a real database.
    Returns (user, system, ids)."""
    user, system = _principal(), _principal('system')
    k = {kind: ids.new_id(kind) for kind in ('mission', 'plan', 'task', 'execution')}
    task = dict(id=k['task'], plan_id=k['plan'], mission_id=k['mission'], key='t',
                title='T', kind='code_change', state=task_state,
                integration_state=integration_state)
    task.update(task_kw or {})
    _seed(db, user,
          entities.Mission(id=k['mission'], workspace_id=ids.GLOBAL_WORKSPACE,
                           title='M', objective='o', state=mission_state),
          entities.Plan(id=k['plan'], mission_id=k['mission'], state=plan_state),
          entities.Task(**task),
          entities.Execution(id=k['execution'], task_id=k['task'],
                             mission_id=k['mission'], plan_id=k['plan'],
                             state=exec_state, **exec_kw))
    return user, system, k


# ── fail-closed and denial ───────────────────────────────────────────────────

def test_a_system_actor_that_is_not_a_principal_never_settles_as_core(db):
    """Branch 1 — replay.py:119-123, the `ids.is_id(event['actor_id'],
    'principal')` False arm of `settled_by`. The closest existing test,
    tests/v1/integration/test_replay.py::test_unreadable_actor_never_means_device,
    plants `Ref('execution', ids.new_id('principal'))`: its actor_id IS a
    principal, so `is_id` is True and only the `{'system': 'core',
    'user_device': 'device'}.get(actor, 'unknown')` default runs. The other
    arm — actor_kind claims `system` (which maps to 'core') while the actor_id
    is not a principal id at all — is planted by no test, and it is the
    forgery that matters: events.actor_id is documented as the causing
    PRINCIPAL (0001_init.sql:80-83), so a row that breaks that rule may not
    buy the core sweep's settlement. Delete the `is_id` guard, or make the
    actor_kind map fall through to a credit, and this record reads as a core
    settlement (settled_by 'core') instead of an unreadable claim."""
    user, system, k = _world(db, exec_state='ENDED_KILLED')
    seq = _raw_event(db, etype='execution.state_changed', subject_id=k['execution'],
                     actor_kind='system', actor_id=ids.new_id('mission'),
                     payload={'from': 'LOST', 'to': 'ENDED_KILLED',
                              'trigger': 'reconciled_kill'})
    rec = _record(_read(db, k['mission']), k['execution'])
    assert (rec['answer'], rec['reason']) == ('RECONCILED', 'recorded_settlement_edge')
    assert (rec['settled_by'], rec['settlement_reason']) == ('unknown', 'unreadable_event_actor')
    assert rec['settlement_seq'] == seq            # the claim is shown, not credited


def test_an_event_of_another_machines_type_never_decides_a_record(db):
    """Branch 2 — replay.py:108-110, the `AND type = ?` clause of the lookup
    (with 113-114 and 126-127 behind it). No existing test plants a
    `state_changed` of the WRONG type for a subject: every existing planter
    (`_edge` of tests/v1/integration/test_replay.py, `_edges` of
    tests/v1/unit/test_gaps_core_application_replay.py) names
    `machine + '.state_changed'` for the machine being read, so dropping the
    type predicate entirely would be caught by nothing. A task carries two
    machines (Task._MACHINES, entities.py:897), and both records are keyed by
    the SAME subject id (`ids.kind_of` of a task id is 'task' for both), so
    type is the only thing separating them. Here a `task.state_changed` row
    honestly spells the integration machine's settling edge (CONFLICT ->
    ABANDONED 'user_abandons', states.py:362); the integration record must not
    see it, while the identical claim under the right type does settle."""
    user, system, k = _world(db, task_state='PENDING', integration_state='ABANDONED')
    wrong = ids.new_id('task')
    right = ids.new_id('task')
    _seed(db, user,
          entities.Task(id=wrong, plan_id=k['plan'], mission_id=k['mission'], key='w',
                        title='W', kind='code_change', state='PENDING',
                        integration_state='ABANDONED'),
          entities.Task(id=right, plan_id=k['plan'], mission_id=k['mission'], key='r',
                        title='R', kind='code_change', state='PENDING',
                        integration_state='ABANDONED'))
    claim = {'from': 'CONFLICT', 'to': 'ABANDONED', 'trigger': 'user_abandons'}
    _raw_event(db, etype='task.state_changed', subject_id=wrong, actor_kind='user_device',
               actor_id=user.id, payload=claim, visibility='user')
    _raw_event(db, etype='integration.state_changed', subject_id=right,
               actor_kind='user_device', actor_id=user.id, payload=claim,
               visibility='user')
    result = _read(db, k['mission'])
    denial = _record(result, wrong, 'integration')
    assert (denial['answer'], denial['reason']) == ('UNKNOWN', 'no_retained_transition')
    assert (denial['settled_by'], denial['settlement_seq']) == ('unknown', None)
    assert denial['settlement_reason'] == 'no_retained_transition'
    # and the task's OWN record is untouched by the claim about its other machine
    assert (_record(result, wrong, 'task')['answer'],
            _record(result, wrong, 'task')['reason']) == ('INTENDED', 'durable_row')
    # the same row under the right type is credited — the claim itself is valid
    credited = _record(result, right, 'integration')
    assert (credited['answer'], credited['settled_by'], credited['settlement_reason']) == (
        'RECONCILED', 'device', 'event_actor')


def test_a_lost_execution_with_a_genuine_transition_is_still_unsettled(db):
    """Branch 3 — replay.py:128-130 reached through `matches` True (113-116).
    tests/v1/integration/test_replay.py::test_lost_is_unsettled_and_names_sweep
    plants no event at all, so line 107 already holds the sweep reason and the
    override is never exercised: delete lines 128-130 and that test still
    passes. With the execution's real RUNNING -> LOST 'heartbeat_missing' edge
    in the log (states.py:198), line 116 would otherwise report
    'transition_does_not_reconcile' — a transition that explains the loss
    would read as a settled one. LOST never proves disposal: no seq, nobody
    settled it, whatever the newest honest event says."""
    user, system, k = _world(db, exec_state='LOST')
    _edges(db, system, (k['execution'], 'execution', 'RUNNING', 'LOST', 'heartbeat_missing'))
    rec = _record(_read(db, k['mission']), k['execution'])
    assert (rec['answer'], rec['reason']) == ('UNCERTAIN', 'durable_row')
    assert (rec['settled_by'], rec['settlement_seq']) == ('unknown', None)
    assert rec['settlement_reason'] == 'unsettled_lost_awaiting_core_sweep'


def test_a_lost_session_is_not_an_execution_and_has_no_sweep_to_wait_for(db):
    """Branch 4 — replay.py:117 `_SETTLEMENT.get(machine, ())` taking its
    default AND replay.py:128 `machine == 'execution'` being False while
    `state == 'LOST'` is True. No existing test reaches either: every settling
    test names a machine listed in _SETTLEMENT (execution, integration,
    execution_node, knowledge_item), and the only LOST test names an execution.
    A session row stands LOST on its own machine (states.py:214 OPEN -> LOST
    'vanished', replay.py:41 maps session LOST to UNCERTAIN); its honest
    transition is recorded but settles nothing, and borrowing the execution
    sweep's reason would promise a core sweep that never visits the session
    table. Drop the machine check from line 128 and this answer changes."""
    user, system, k = _world(db, exec_state='LOST')
    sid = ids.new_id('session')
    _seed(db, user, entities.Session(
        id=sid, mission_id=k['mission'], harness_id='fake',
        workspace_id=ids.GLOBAL_WORKSPACE, cwd='work/project', mode='manual',
        state='LOST'))
    _edges(db, system, (k['execution'], 'execution', 'RUNNING', 'LOST', 'heartbeat_missing'),
                        (sid, 'session', 'OPEN', 'LOST', 'vanished'))
    result = _read(db, k['mission'])
    rec = _record(result, sid, 'session')
    assert (rec['answer'], rec['reason']) == ('UNCERTAIN', 'durable_row')
    assert (rec['settled_by'], rec['settlement_seq']) == ('unknown', None)
    assert rec['settlement_reason'] == 'transition_does_not_reconcile'
    # the machine list is what decides, not the word LOST: the LOST execution of
    # this same world, with its own honest edge, keeps the sweep reason
    execution = _record(result, k['execution'], 'execution')
    assert (execution['answer'], execution['reason']) == ('UNCERTAIN', 'durable_row')
    assert execution['settlement_reason'] == 'unsettled_lost_awaiting_core_sweep'
    assert (execution['settled_by'], execution['settlement_seq']) == ('unknown', None)


def test_a_mission_that_is_not_there_is_denied_before_any_home_is_built(db):
    """Branch 10 — replay.py:151-154: the `if mission is None: raise NotFound`
    guard runs BEFORE `queries._homes(conn, homes)` on line 154. The existing
    denial tests (test_a_mission_that_is_not_a_mission_is_not_found,
    test_route_is_observe_read_only_and_unknown_mission_is_404) assert only the
    exception type or the status code, so
    moving the guard below the homes build — or building homes eagerly and
    denying after — is caught by nothing. `homes=` accepts a callable that
    builds them lazily (queries.py:15-20) and that build is the OS/account
    surface (resources.py:813-828 reads every account row); a 404 read may not
    touch it. The spy is called for the mission that exists, so an uncalled spy
    here is a fact and not a vacuity."""
    user, system, k = _world(db)
    calls = []

    def build_homes():
        calls.append(1)
        return Homes((), (), shorts=lambda _: None, path_flavour='windows')

    with db.read() as conn:
        for missing in (ids.new_id('mission'), k['execution'], 'clearly-not-an-id'):
            with pytest.raises(NotFound):
                replay.replay(conn, missing, homes=build_homes)
    assert calls == []
    result = _read(db, k['mission'], homes=build_homes)
    assert result['mission_id'] == k['mission'] and calls == [1]


# ── boundaries ───────────────────────────────────────────────────────────────

def test_a_log_that_never_recorded_an_event_says_so_and_blames_nobody(db):
    """Branch 5 — replay.py:183 with 197-200: the `'no_retained_events' if
    retained is None` arm, reached only when `floor` is falsy AND no event row
    exists. Both existing history tests leave floor > 0
    (test_empty_event_range_is_unknown deletes rows but not the AUTOINCREMENT
    counter, so outbox.floor returns head and the row asserts
    'retained_event_prefix_pruned'; so does
    test_retention_pruning_loses_attribution_but_keeps_rows) and the one
    RECORDED test has rows. So no test pins the third answer. An empty
    log is neither a complete range nor a pruned one: it never held anything.
    Drop `retained is None` from line 197 and this read certifies a RECORDED
    history out of nothing; reorder lines 198-199 and it blames a retention
    that ran no prune."""
    user, system, k = _world(db, exec_state='ENDED_OK')
    _wipe_log(db)
    result = _read(db, k['mission'])
    assert result['history'] == {'answer': 'UNKNOWN', 'reason': 'no_retained_events',
                                 'floor': 0, 'head': 0, 'oldest_retained_at': None,
                                 'event_days': retention.EVENT_DAYS,
                                 'open_mission_extension': False,
                                 'gap': 'open_mission_retention_extension_not_built'}
    # the rows are still read: what is gone is the history, not the state
    assert _record(result, k['mission'], 'mission')['answer'] == 'MAY-HAVE-TAKEN-EFFECT'
    assert _record(result, k['execution'], 'execution')['answer'] == 'RECORDED'
    assert _record(result, k['execution'], 'execution')['settlement_reason'] == \
        'no_retained_transition'


@pytest.mark.parametrize('seed, imported, isolated, expected', [
    ('a' * 40, 'b' * 40, True, 'paths'),
    ('a' * 40, None, True, 'unknown'),
    (None, 'b' * 40, True, 'unknown'),
    ('a' * 40, None, False, 'summary'),
    (None, 'b' * 40, False, 'summary'),
    (None, None, False, 'summary'),
], ids=['seeded-and-imported', 'seeded-only-isolated', 'imported-only-isolated',
        'seeded-only-in-place', 'imported-only-in-place', 'plain-in-place'])
def test_paths_are_claimed_only_for_a_run_that_seeded_AND_imported(seed, imported,
                                                                   isolated, expected):
    """Branch 6 — replay.py:140-141, the individual conjuncts of
    `execution.seed_revision is not None and execution.import_revision is not
    None`. The existing parametrizations
    (test_paths_are_only_claimed_for_files_that_exist,
    test_the_isolation_shape_never_guesses_a_summary) only ever set BOTH
    revisions or NEITHER, so dropping either conjunct is caught by nothing:
    a run that was seeded but whose import was refused (entities.py:1038-1039,
    "None: no import (never seeded, or refused)") would advertise its clipped
    checkpoint as durable A/M/D paths, and — the worse half, rows 4-6 — an
    in-place run would lose its honest 'summary' to a 'paths' claim it never
    earned."""
    checkpoint = entities.Checkpoint(id=ids.new_id('checkpoint'),
                                     execution_id=ids.new_id('execution'),
                                     mission_id=ids.new_id('mission'),
                                     task_id=ids.new_id('task'), trigger='task_boundary',
                                     files_changed=('M a.py', 'D b.py'))
    execution = entities.Execution(id=checkpoint.execution_id, task_id=checkpoint.task_id,
                                   mission_id=checkpoint.mission_id, state='ENDED_OK',
                                   seed_revision=seed, import_revision=imported,
                                   isolated=isolated)
    out = replay._files(checkpoint, execution)
    assert out['files_are'] == expected
    assert out['files_changed'] == ['M a.py', 'D b.py']
    assert (out['complete'], out['item_limit'], out['reason']) == (
        False, 30, 'checkpoint_is_a_clipped_summary')
    assert (out['id'], out['execution_id'], out['task_id']) == (
        checkpoint.id, checkpoint.execution_id, checkpoint.task_id)


def test_a_checkpoint_whose_execution_row_is_gone_is_unknown_and_not_a_crash():
    """Branch 7 — replay.py:140-141, both `execution is not None` arms (the
    `paths` conjunction and the `summary` one). No existing call of `_files`
    passes None, and `replay` itself never does (its comprehension keeps only
    checkpoints whose execution_id is in `executions`, replay.py:170-173) — so
    the None branch is either dead code or the last honest answer, and only a
    direct test tells them apart. A checkpoint whose execution row cannot be
    read has NO isolation decision and NO revisions: the answer is 'unknown'
    about the files, and it must not be guessed as 'summary', and reading it
    must not raise out of an observe route. Remove the `paths` guard and this
    is an AttributeError instead of an answer; remove the `summary` guard and
    it silently claims an in-place run that nobody decided."""
    checkpoint = entities.Checkpoint(id=ids.new_id('checkpoint'),
                                     execution_id=ids.new_id('execution'),
                                     mission_id=ids.new_id('mission'),
                                     task_id=ids.new_id('task'), trigger='task_boundary',
                                     files_changed=('M a.py', 'D b.py'))
    assert replay._files(checkpoint, None) == {
        'id': checkpoint.id, 'execution_id': checkpoint.execution_id,
        'task_id': checkpoint.task_id, 'files_changed': ['M a.py', 'D b.py'],
        'files_are': 'unknown', 'complete': False, 'item_limit': 30,
        'reason': 'checkpoint_is_a_clipped_summary'}


def test_a_private_home_inside_the_task_scope_never_reaches_the_answer(db, monkeypatch):
    """Branch 9 — replay.py:187-188 feeding the single `system_value(result,
    homes)` of line 204: the task scope (objective, expected_output, boundaries,
    acceptance) is a projection surface no leak test plants. The closest,
    test_all_replay_strings_use_trace_public_projection, puts the home and the
    account key into checkpoint files_changed and a policy decision reason only
    (both built outside the task dict), so a scope field rendered without the
    projection — `'scope': {...}` raw, or the lists copied by reference — would
    be caught by nothing. The DB keeps the raw text; the answer may not."""
    home = 'C:/T1147/Private-Home'
    key = 'fake:' + home.lower()
    monkeypatch.setattr('archeus.infra.discovery.public_account_secret', lambda: b't1147-secret')
    homes = Homes([home], [('fake', key, home)], shorts=lambda _: None, path_flavour='windows')
    user, system, k = _world(db, task_kw={
        'objective': 'work in ' + home + ' only',
        'expected_output': 'a patch under ' + home + '/src',
        'boundaries': ['no writes outside ' + home + ' at all'],
        'acceptance': [{'text': 'runs in ' + home + ' as ' + key, 'check': 'automatic'}]})
    with db.read() as conn:
        stored = conn.execute('SELECT body FROM tasks WHERE id = ?', (k['task'],)).fetchone()[0]
    assert home in stored and key in stored            # the raw text really is there
    result = _read(db, k['mission'], homes=homes)
    encoded = json.dumps(result)
    assert home.lower() not in encoded.lower() and key not in encoded
    assert result['tasks'] == [{'id': k['task'], 'scope': {
        'objective': 'work in its home only',
        'expected_output': 'a patch under its home/src',
        'boundaries': ['no writes outside its home at all'],
        'acceptance': [{'text': 'runs in its home as ' + public_account_id(key),
                        'check': 'automatic'}]}}]


# ── error paths ──────────────────────────────────────────────────────────────

def test_a_state_changed_payload_that_is_not_an_object_is_never_read_as_absent(db):
    """Branch 8 — replay.py:111-114 with a payload that IS valid JSON and is not
    an object. The neighbouring case
    (test_a_corrupt_state_changed_payload_raises_instead_of_inventing) plants
    `'{not json'` and pins the ValueError; `'[]'`/`'null'` parse, so `if event
    else {}` hands line 112 something with no `.get`. The tempting "fix" is a
    try/except that falls back to `{}` — and that is the fabrication this test
    exists to forbid, because `{}` on an ENDED_KILLED row answers
    UNKNOWN/'no_retained_transition' and the caller cannot tell a corrupt claim
    from no claim. The read must blow up on the caller's face and return
    nothing at all, not one record."""
    user, system, k = _world(db, exec_state='ENDED_KILLED')
    _raw_event(db, etype='execution.state_changed', subject_id=k['execution'],
               actor_kind='system', actor_id=system.id, payload='[]')
    with db.read() as conn:
        stored = conn.execute('SELECT payload FROM events WHERE subject_id = ?',
                              (k['execution'],)).fetchone()[0]
        assert stored == '[]'
        with pytest.raises((AttributeError, TypeError)):
            replay.replay(conn, k['mission'])
