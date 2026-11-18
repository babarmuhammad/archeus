"""T-301: the highest-risk uncovered branches of
`archeus/core/application/executions.py` — refusals and ownership denials first,
then the lifecycle guards of the process commands, then the error paths. Each
test names the source branch it catches (the report quotes them); none of them
needs Windows, a process, the network or the OS beyond the real SQLite database
every execution unit test already uses (the style and the seeded-world fixture
are copied from tests/v1/unit/test_execution_units.py).
"""

import pytest

from archeus.core.application import authorization, executions as X, queries
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows


def _world(state='RUNNING', *, max_attempts=2, isolated=None, process_seq=0,
           stop_reason=None, seed_revision=None, import_revision=None, account_id=None,
           approval_state=None, approval_for_other=False):
    """One execution in *state* under a RUNNING task on a real database, plus one
    `action` approval of its task when *approval_state* names one (belonging to
    another execution when *approval_for_other*). No fixture beyond tmp_path's
    ARCHEUS_HOME, which tests/v1/conftest.py already gives every test."""
    db = Database.open()
    user = Ref('user_device', ids.new_id('principal'))
    system = Ref('system', ids.new_id('principal'))
    mid, pid, tid, eid = (ids.new_id(k) for k in ('mission', 'plan', 'task', 'execution'))

    def run(tx, **_):
        for row in (
                entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                 objective='o', state='EXECUTING'),
                entities.Plan(id=pid, mission_id=mid, state='APPROVED'),
                entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t', title='T',
                              kind='code_change', state='RUNNING',
                              max_attempts=max_attempts),
                entities.Execution(id=eid, task_id=tid, mission_id=mid, plan_id=pid,
                                   attempt=1, state=state, stop_reason=stop_reason,
                                   isolated=isolated, process_seq=process_seq,
                                   seed_revision=seed_revision,
                                   import_revision=import_revision,
                                   account_id=account_id)):
            tx.insert(row, actor=user)
        if approval_state is not None:
            tx.insert(entities.Approval(
                id=ids.new_id('approval'), kind='action',
                subject=Ref('execution', eid), action_hash='0' * 64,
                requested_by=system.id, mission_id=mid, plan_id=pid, task_id=tid,
                execution_id=ids.new_id('execution') if approval_for_other else eid,
                expires_at='2099-01-01T00:00:00Z', state=approval_state), actor=user)
        tx.append(new_event('mission.updated', Ref('mission', mid), user, payload={},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return db, user, system, {'mid': mid, 'pid': pid, 'tid': tid, 'eid': eid}


def _row(db, kind, id_):
    with db.read() as r:
        return rows.get(r, kind, id_)


def _events(db, type_, subject_id=None):
    with db.read() as r:
        return [ev for ev in queries.events(r)
                if ev['type'] == type_
                and (subject_id is None or ev['subject']['id'] == subject_id)]


def _prep(db, who, eid, seq):
    return db.writer.execute(X.prepare_process, {
        'actor': who, 'execution_id': eid, 'token_digest': '0' * 64, 'workdir': 'w',
        'branch': None, 'process_seq': seq, 'isolated': True})


# ── refusals and ownership: the e-stop and the re-arm ───────────────────────

@pytest.mark.parametrize('kind', ['agent', 'harness', 'web'], ids=['agent', 'harness', 'web'])
def test_the_estop_refuses_what_is_neither_a_user_device_nor_core(kind):
    """executions.py:752-753 — `if actor.kind not in ('user_device', 'system'):
    raise NotPermitted`. Were that gate removed, any harness's own agent could
    e-stop the whole Core (and the event below would say it did)."""
    db, user, system, k = _world('RUNNING', process_seq=1)
    try:
        with pytest.raises(authorization.NotPermitted):
            db.writer.execute(X.estop, {'actor': Ref(kind, ids.new_id('principal')),
                                        'missions': None})
        assert _row(db, entities.Execution, k['eid']).entity.state == 'RUNNING'
        assert _events(db, 'core.estopped') == []
    finally:
        db.close()


def test_core_itself_never_rearms_only_a_user_device_does():
    """executions.py:744-745 (`_user`, called first by `rearm`, executions.py:771)
    — were it inverted or dropped, Core could clear its own e-stop from a system
    pass, which is exactly what D10/V2-3 forbids."""
    db, user, system, k = _world('RUNNING', process_seq=1)
    try:
        with pytest.raises(authorization.NotPermitted):
            db.writer.execute(X.rearm, {'actor': system, 'step_up': None})
        assert _events(db, 'core.rearmed') == []
    finally:
        db.close()


# ── the action approval: fail closed on what is not a dead decision ────────

@pytest.mark.parametrize('case', ['approved', 'pending', 'foreign', 'none'],
                         ids=['approved', 'pending', 'foreign', 'none'])
def test_an_execution_awaits_until_its_own_approval_is_actually_dead(case):
    """executions.py:910-912 — `if a is None or a.state not in ('REJECTED',
    'EXPIRED', 'SUPERSEDED'): return` (with executions.py:925-928 dropping an
    approval of another execution). Inverted, an APPROVED (still to be used) or
    a foreign approval would end the execution as rejected; with the foreign
    filter dropped, another execution's expiry would end this one."""
    kw = {'approved': dict(approval_state='APPROVED'),
          'pending': dict(approval_state='PENDING'),
          'foreign': dict(approval_state='EXPIRED', approval_for_other=True),
          'none': dict()}[case]
    db, user, system, k = _world('AWAITING_APPROVAL', process_seq=1, **kw)
    try:
        out = db.writer.execute(X.approval_answered, {'actor': system,
                                                      'execution_id': k['eid']})
        assert out['state'] == 'AWAITING_APPROVAL'
        assert out['approval'] == {'approved': 'APPROVED', 'pending': 'PENDING',
                                   'foreign': None, 'none': None}[case]
        e = _row(db, entities.Execution, k['eid']).entity
        assert (e.state, e.exit_reason, e.charged) == ('AWAITING_APPROVAL', None, None)
        assert _row(db, entities.Task, k['tid']).entity.state == 'RUNNING'
        assert _events(db, 'execution.ended', k['eid']) == []
    finally:
        db.close()


@pytest.mark.parametrize('dead', ['EXPIRED', 'SUPERSEDED'], ids=['expired', 'superseded'])
def test_a_dead_approval_ends_its_execution_charged_and_fails_the_task_as_human(dead):
    """executions.py:914-921 — the `rejected` fire with `charged: True` and
    `_respond`'s `ENDED_REJECTED` arm (executions.py:672-676, failure_class
    'human'). Without the charge the task would retry forever on a rejected
    action; without the human class the retry would be judged as ours."""
    db, user, system, k = _world('AWAITING_APPROVAL', process_seq=1, max_attempts=1,
                                 approval_state=dead)
    try:
        db.writer.execute(X.approval_answered, {'actor': system, 'execution_id': k['eid']})
        e = _row(db, entities.Execution, k['eid']).entity
        assert (e.state, e.exit_reason, e.charged) == ('ENDED_REJECTED', 'rejected', True)
        assert e.session_id is not None                     # it ran, so it has its record
        t = _row(db, entities.Task, k['tid']).entity
        assert (t.state, t.failure_class) == ('FAILED', 'human')
        assert len(_events(db, 'execution.ended', k['eid'])) == 1
    finally:
        db.close()


# ── ends: a clean isolated hand-off end is never record_end's ───────────────

def test_an_isolated_hand_off_that_exited_cleanly_refuses_record_end():
    """executions.py:524-528 — `if isolated and e.state == 'HANDING_OFF' and
    clean: raise IllegalTrigger`. Without it, exit 0 would take the
    `exited_success` edge to ENDED_OK (success Core never verified) instead of
    the uncharged hand-off `record_handoff` writes."""
    db, user, system, k = _world('HANDING_OFF', isolated=True, stop_reason='pressure',
                                 process_seq=1)
    try:
        with pytest.raises(X.lifecycle.IllegalTrigger):
            db.writer.execute(X.record_end, {'actor': system, 'execution_id': k['eid'],
                                             'exit_code': 0, 'isolated': True})
        e = _row(db, entities.Execution, k['eid']).entity
        assert (e.state, e.charged, e.exit_reason) == ('HANDING_OFF', None, None)
        assert _events(db, 'execution.ended', k['eid']) == []
    finally:
        db.close()


# ── the stop vocabulary: nothing Core does not record is accepted ───────────

@pytest.mark.parametrize('bad', ['exploded', 'paused'], ids=['exploded', 'paused'])
def test_stop_refuses_a_stop_reason_Core_never_records(bad):
    """executions.py:700-701 — `if stop_reason not in entities.STOP_REASONS:
    raise ValueError`. An invented reason past this gate would land in
    `charged = stop_reason not in UNCHARGED` and silently charge (or spare) an
    attempt for a reason no reader knows."""
    db, user, system, k = _world('RUNNING', process_seq=1)
    try:
        with pytest.raises(ValueError, match='unknown stop reason'):
            db.writer.execute(X.stop, {'actor': system, 'execution_id': k['eid'],
                                       'reason': 'r', 'stop_reason': bad})
        e = _row(db, entities.Execution, k['eid']).entity
        assert (e.state, e.stop_reason) == ('RUNNING', None)
    finally:
        db.close()


@pytest.mark.parametrize('bad', ['user', 'binding', 'workspace'], ids=['user', 'binding',
                                                                       'workspace'])
def test_a_hand_off_is_only_for_the_causes_Core_decides(bad):
    """executions.py:805-808 — `if stop_reason not in HANDOFF_CAUSES: raise
    ValueError`. A 'user' hand-off past this gate would spend the uncharged
    `UNCHARGED` vocabulary wrongly: 'user' is a stop's reason, never a
    hand-off's, and no continuation's charge rule reads it."""
    db, user, system, k = _world('RUNNING', process_seq=1)
    try:
        with pytest.raises(ValueError, match='a hand-off is for'):
            db.writer.execute(X.request_handoff, {'actor': system, 'execution_id': k['eid'],
                                                  'stop_reason': bad, 'reason': 'r'})
        e = _row(db, entities.Execution, k['eid']).entity
        assert (e.state, e.stop_reason) == ('RUNNING', None)
    finally:
        db.close()


# ── the process commands: the numbers they may write, the states they may be in

@pytest.mark.parametrize('seq', [0, 2, 5], ids=['seq0', 'seq2', 'seq5'])
def test_preparation_never_skips_a_process_number(seq):
    """executions.py:273-275 — `if process_seq != e.process_seq + 1: raise
    ValueError('cannot follow')`. A skipped number would let a stale manager
    pass prepare a process the kill-by-identity registry cannot match, and a
    reused one would overwrite the row of the process that may still run."""
    db, user, system, k = _world('INTENT')
    try:
        with pytest.raises(ValueError, match='cannot follow'):
            _prep(db, system, k['eid'], seq)
        e = _row(db, entities.Execution, k['eid']).entity
        assert (e.state, e.process_seq, e.workdir) == ('INTENT', 0, None)
        assert _events(db, 'execution.prepared', k['eid']) == []
    finally:
        db.close()


@pytest.mark.parametrize('state', ['RUNNING', 'STARTING', 'STOPPING', 'LOST', 'ENDED_OK'],
                         ids=['running', 'starting', 'stopping', 'lost', 'ended'])
def test_no_process_is_prepared_in_a_state_that_cannot_have_one(state):
    """executions.py:269-272 — `if e.state not in ('INTENT', 'PAUSED',
    'AWAITING_APPROVAL'): raise IllegalTrigger`. Past it, preparing a RUNNING
    execution would reset the workdir/hook token of a live process, and a new
    preparation of an ended one would start a second process for dead work."""
    db, user, system, k = _world(state, process_seq=1)
    try:
        with pytest.raises(X.lifecycle.IllegalTrigger):
            _prep(db, system, k['eid'], 2)
        e = _row(db, entities.Execution, k['eid']).entity
        assert (e.state, e.process_seq) == (state, 1)
        assert _events(db, 'execution.prepared', k['eid']) == []
    finally:
        db.close()


@pytest.mark.parametrize('state', ['RUNNING', 'STARTING', 'STOPPING', 'HANDING_OFF',
                                   'ENDED_KILLED'],
                         ids=['running', 'starting', 'stopping', 'handing', 'killed'])
def test_a_process_is_recorded_only_where_a_start_is_legal(state):
    """executions.py:385-388 — the `trigger` table's `.get(e.state)` returning
    None (`record_process` accepts only INTENT, PAUSED, AWAITING_APPROVAL).
    Without the table, recording a process on a RUNNING row would fire an
    unknown trigger, and on STOPPING it would resurrect a kill that is owed."""
    db, user, system, k = _world(state, process_seq=1)
    try:
        with pytest.raises(X.lifecycle.IllegalTrigger):
            db.writer.execute(X.record_process, {'actor': system, 'execution_id': k['eid'],
                                                 'pid': 4242, 'create_time': 111,
                                                 'process_seq': 1})
        e = _row(db, entities.Execution, k['eid']).entity
        assert (e.state, e.pid) == (state, None)
        assert _events(db, 'execution.started', k['eid']) == []
    finally:
        db.close()


@pytest.mark.parametrize('state,seq', [('INTENT', 1), ('INTENT', 2), ('PAUSED', 2)],
                         ids=['intent1', 'intent2', 'paused2'])
def test_record_process_refuses_a_process_that_was_never_prepared(state, seq):
    """executions.py:382-383 — `if process_seq != e.process_seq: raise
    ValueError('was not prepared')`. Dropped, a stale manager could record a
    process number the preparation never wrote: the registry would watch a pid
    under an identity Core never committed to."""
    db, user, system, k = _world(state)
    try:
        with pytest.raises(ValueError, match='was not prepared'):
            db.writer.execute(X.record_process, {'actor': system, 'execution_id': k['eid'],
                                                 'pid': 4242, 'create_time': 111,
                                                 'process_seq': seq})
        e = _row(db, entities.Execution, k['eid']).entity
        assert (e.state, e.process_seq, e.pid) == (state, 0, None)
        assert _events(db, 'execution.started', k['eid']) == []
    finally:
        db.close()


# ── the breaker's gate: a limit never moves an account mid-breaker ──────────

def test_a_provider_limit_never_moves_an_account_the_breaker_owns():
    """executions.py:1118-1119 — `if a.health in ('AVAILABLE',
    'CONSTRAINED'):` around the `window_exhausted` fire. Fired from DEGRADED it
    either crashes the pass with IllegalTrigger or (with the table loosened)
    drags a breaker-degraded account to LIMITED, where the release path would
    hand back a resource the breaker just refused."""
    db = Database.open()
    system = Ref('system', ids.new_id('principal'))
    aid = ids.new_id('account')

    def run(tx, **_):
        tx.insert(entities.Account(id=aid, harness_id='fake', label='A', auth_kind='api_key',
                                   health='DEGRADED'), actor=system)
        tx.append(new_event('account.registered', Ref('account', aid), system, payload={
            'harness_id': 'fake', 'label': 'A', 'auth_kind': 'api_key'},
            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    now = 1_700_000_000
    try:
        out = db.writer.execute(X.account_limited, {'actor': system, 'account_id': aid,
                                                    'resets_at': None, 'now': now})
        assert out == {'account_id': aid, 'limited_until': X._iso(now + X.LIMIT_DEFAULT_S)}
        a = _row(db, entities.Account, aid).entity
        assert (a.health, a.limited_until) == ('DEGRADED', None)   # the fire would have moved both
    finally:
        db.close()
