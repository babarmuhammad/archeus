"""T-304: the highest-risk uncovered branches of
`archeus/core/application/verification.py` — who may verify what, evidence Core
can prove, and every refusal path that must write nothing.

The module's existing tests are tests/v1/unit/test_verification_units.py (the
closest one: the pure verdict/coverage/review parts, whose check-dict shape is
copied here) and tests/v1/integration/test_provenance.py, which reaches the
module only through the runtime. Neither drives a command over a database, so
the fixtures follow the database-driven unit tests of the sibling application
modules (tests/v1/unit/test_execution_units.py): Database.open() and
db.writer.execute(command, kwargs). Nothing spawns a process, touches git
or reads the network; the only OS interface used is the content-addressed
artifact store under the test's own `ARCHEUS_HOME` (the autouse fixture of
tests/v1/conftest.py), written as bytes with explicit newlines. Mission moves go
through the real `commands.Missions` with the P1 allow-all policy and an injected
guard snapshot, so a block or a resume proven here is a real edge of P3's machine
and answers the same on Windows and Linux.

The ten branches that needed it most are listed in /work/QWEN-DONE-T-304.md,
file:line first, with the test that now covers each.
"""

import hashlib
import json

import pytest

from archeus.core import ports
from archeus.core.application import commands, lifecycle
from archeus.core.application import verification as V
from archeus.core.application.world import Conflict
from archeus.core.domain import entities, guards, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.execution import manager
from archeus.infra.artifacts import store
from archeus.infra.db import Database, rows

HEAD = 'c' * 40            # the mission branch head, as recorded
IMP = 'd' * 40             # an execution's recorded import revision
RECV = 'e' * 40            # the revision a merge may take


def who(kind='user_device'):
    """A principal of *kind*: the only thing a caller may claim to be."""
    return Ref(kind, ids.new_id('principal'))


class Missions:
    """The runtime's `Missions`, under test: every call is recorded and handed to
    the real object, whose guard snapshot is fixed here. A mission move a test
    asserts is therefore a real edge of P3's machine, not a stub's answer."""

    def __init__(self, facts=None):
        self.calls = []
        fixed = facts or guards.MissionFacts(review='ACCEPTED')
        self._ms = commands.Missions(policy=ports.AllowAllPolicy(),
                                   facts=lambda tx, row: fixed)

    def fire(self, tx, *, actor, mission_id, trigger, reason, expected_version=None):
        self.calls.append((trigger, mission_id))
        return self._ms.fire(tx, actor=actor, mission_id=mission_id, trigger=trigger,
                             reason=reason, expected_version=expected_version)

    def resume(self, tx, *, actor, mission_id, reason):
        self.calls.append(('resume', mission_id))
        return self._ms.resume(tx, actor=actor, mission_id=mission_id, reason=reason)

    def accept(self, tx, *, actor, mission_id, reason):
        self.calls.append(('accept', mission_id))
        return self._ms.accept(tx, actor=actor, mission_id=mission_id, reason=reason)

    def request_changes(self, tx, *, actor, mission_id, reason, expected_version=None):
        self.calls.append(('changes_requested', mission_id))
        return self._ms.request_changes(tx, actor=actor, mission_id=mission_id, reason=reason,
                                        expected_version=expected_version)


# ── seeding: one transaction each, no command and no process ────────────────

def _seed(db, actor, *, mission=None, plan=None, task=None, execution=None, worktree=False,
         extra=()):
    """One mission, its plan in force, one VERIFYING task and the execution whose
    end moved it there. Each argument overrides a default field of that row,
    `worktree` gives the execution the branch P11 gives a worktree task, and
    `extra` adds executions."""
    mid, pid, tid, eid = (ids.new_id(k) for k in ('mission', 'plan', 'task', 'execution'))
    m = dict(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M', objective='o',
             state='EXECUTING', integration_head=HEAD,
             success_criteria=({'text': 'it works', 'check': 'automatic'},))
    p = dict(id=pid, mission_id=mid, state='APPROVED', plan_version=1)
    t = dict(id=tid, plan_id=pid, mission_id=mid, key='t1', title='T', kind='code_change',
             state='VERIFYING', acceptance=({'text': 'it works', 'check': 'automatic'},))
    e = dict(id=eid, task_id=tid, mission_id=mid, plan_id=pid, attempt=1, state='ENDED_OK',
             isolated=False, process_seq=1, harness_id='fake', model='m-large',
             import_revision=IMP, branch=None)
    m.update(mission or {})
    p.update(plan or {})
    t.update(task or {})
    e.update(execution or {})
    if worktree:
        e['branch'] = '%s.%s' % (manager.mission_branch(mid), t['key'])
    execs = [dict(e)] + [dict(x) for x in (extra or ())]

    def run(tx, **_):
        for row in (entities.Mission(**m), entities.Plan(**p), entities.Task(**t)):
            tx.insert(row, actor=actor)
        for x in execs:
            x.setdefault('id', ids.new_id('execution'))
            x.setdefault('task_id', tid)
            x.setdefault('mission_id', mid)
            x.setdefault('plan_id', pid)
            tx.insert(entities.Execution(**x), actor=actor)
        tx.append(new_event('mission.created', Ref('mission', mid), actor,
                           payload={'fields': []}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return {'mid': mid, 'pid': pid, 'tid': tid, 'eid': eid}


def _insert(db, actor, entity, subject=None, type_='mission.updated'):
    """One more row, with the event its insert owes. A state field may be given
    here (an insert is not a move); only `transition` may set one on an update."""
    sub = subject if subject is not None else Ref('mission', entity.mission_id)

    def run(tx, **_):
        tx.insert(entity, actor=actor)
        tx.append(new_event(type_, sub, actor, payload={'fields': []},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})
    return entity.id


def _set(db, w, cls, entity_id, fields):
    """What the runtime would have recorded between two commands: an execution
    learned to be isolated, a mission's head moved by something else. Never a
    state field (an edge does those) and never a frozen one."""
    actor = who('system')

    def run(tx, **_):
        tx.update(cls, entity_id, fields, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', w['mid']), actor,
                            payload={'fields': sorted(fields)},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})


def _verification(db, actor, w, **over):
    """A Verification row already in the database in the shape the test needs —
    for a state, or a frozen field, no command of this module can put there."""
    row = dict(id=ids.new_id('verification'), subject=Ref('task', w['tid']), verifier='code',
               plan_id=w['pid'], execution_id=w['eid'], state='RUNNING', criteria=_criteria(0))
    row.update(over)
    return _insert(db, actor, entities.Verification(**row), subject=Ref('verification', row['id']),
                   type_='verification.created')


def _criterion_row(db, actor, w, state, *, holds=False):
    """A mission success criterion's verification row, as one started earlier
    would already stand: AWAITING_HUMAN waits on a person, PASSED does not."""
    return _insert(db, actor, entities.Verification(
        id=ids.new_id('verification'), subject=Ref('mission', w['mid']),
        verifier='generic_human', plan_id=w['pid'], criterion=0, revision=HEAD,
        state=state, holds_mission=holds), subject=Ref('verification', w['mid']),
        type_='verification.created')


def _running(db, actor, w, **kw):
    """A RUNNING code verification of the seeded task, covering criterion 0."""
    kw.setdefault('criteria', _criteria(0))
    return _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('task', w['tid']),
               verifier='code', execution_id=w['eid'], **kw)['verification_id']


def _waiting(db, actor, w, missions=None, **kw):
    """The task's generic_human row awaiting a decision, as the sink starts it: it
    is bound to the execution whose end moved the task, like any other verdict."""
    kw.setdefault('execution_id', w['eid'])
    return _do(db, V.start, actor=actor, missions=missions or Missions(),
               subject=Ref('task', w['tid']), verifier='generic_human', **kw)['verification_id']


def _errored(db, actor, w, **kw):
    """A RUNNING row recorded into ERROR (the verifier could not run)."""
    vid = _running(db, actor, w, **kw)
    _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
        checks=[{'name': 'suite', 'kind': 'command', 'result': 'error',
                 'detail': 'the runner is not installed'}])
    assert _row(db, entities.Verification, vid).state == 'ERROR'
    return vid


def _succeeded(db, actor, *, revision, mission=None):
    """A task whose verified worktree execution has one PASSED verification of
    *revision* and whose merge-back is PENDING: where P13 leaves finished work."""
    w = _seed(db, actor, worktree=True, mission=mission)
    out = _do(db, V.record, actor=actor, missions=Missions(),
              verification_id=_running(db, actor, w, revision=revision), checks=[_passing()])
    assert (out['state'], out['task_state']) == ('PASSED', 'SUCCEEDED')
    return w


def _do(db, command, missions=None, **kw):
    """One P13 command on the writer, exactly as the runtime submits it."""
    args = dict(kw)
    if missions is not None:
        args['missions'] = missions
    return db.writer.execute(command, args)


def _row(db, cls, entity_id):
    with db.read() as c:
        r = rows.get(c, cls, entity_id)
    return None if r is None else r.entity


def _all(db, cls, **eq):
    with db.read() as c:
        return [r.entity for r in rows.where(c, cls, **eq)]


def _events(db, type_):
    """The payloads of the events of *type_*, oldest first."""
    with db.read() as c:
        return [json.loads(p) for (p,) in c.execute(
            'SELECT payload FROM events WHERE type = ? ORDER BY seq', (type_,))]


def _n_events(db):
    with db.read() as c:
        return c.execute('SELECT COUNT(*) FROM events').fetchone()[0]


def _passing(name='suite'):
    return {'name': name, 'kind': 'command', 'result': 'pass'}


def _errored_check(name='suite'):
    return {'name': name, 'kind': 'command', 'result': 'error',
            'detail': 'the runner is not installed'}


def _failing(name='suite'):
    return {'name': name, 'kind': 'command', 'result': 'fail'}


def _criteria(*indexes):
    """The criterion readings the sink hands `start`: what the acceptance says,
    each still `unknown` until a check or a decision settles it (§8.4)."""
    return tuple({'index': i, 'text': 'it works', 'check': 'automatic', 'result': 'unknown'}
                 for i in indexes)


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    try:
        yield d
    finally:
        d.close()


# ── who may decide what waits on a human (§17) ──────────────────────────────

def test_a_system_principal_never_decides_what_waits_on_a_human(db):
    """verification.py:407-408 (`if actor.kind != 'user_device'`): without it a
    worker could accept its own verdict, which is the whole of §17. The row and
    the mission stay exactly as they were: a refusal writes nothing."""
    actor = who()
    w = _seed(db, actor)
    vid = _waiting(db, actor, w)
    assert _row(db, entities.Verification, vid).state == 'AWAITING_HUMAN'
    before = _n_events(db)
    with pytest.raises(V.Refused, match='only a user device'):
        _do(db, V.decide, actor=who('system'), missions=Missions(), verification_id=vid,
            decision='accept')
    v = _row(db, entities.Verification, vid)
    assert (v.state, v.holds_mission, v.decided_by, v.note) == ('AWAITING_HUMAN', True, None, None)
    assert _row(db, entities.Mission, w['mid']).state == 'BLOCKED'
    assert _n_events(db) == before


def test_a_decision_that_is_neither_accept_nor_reject_is_answered_with_a_value_error(db):
    """verification.py:409-410 (`if decision not in ('accept', 'reject')`):
    widened, this lets `maybe`, `ACCEPT` or a number decide a mission."""
    actor = who()
    w = _seed(db, actor)
    vid = _waiting(db, actor, w)
    for bad in ('ACCEPT', 'maybe', '', None, 1):
        with pytest.raises(ValueError, match='accept or reject'):
            _do(db, V.decide, actor=actor, missions=Missions(), verification_id=vid,
                decision=bad)
    v = _row(db, entities.Verification, vid)
    assert (v.state, v.decided_by) == ('AWAITING_HUMAN', None)
    assert _row(db, entities.Mission, w['mid']).state == 'BLOCKED'


def test_nothing_is_decided_on_a_row_that_does_not_wait_on_a_human(db):
    """verification.py:413-416 (`if v.state != 'AWAITING_HUMAN'` -> 409 Conflict):
    a RUNNING row decided from here records a verdict no check ever produced."""
    actor = who()
    w = _seed(db, actor)
    vid = _running(db, actor, w)
    with pytest.raises(Conflict, match='nothing waits on a decision') as err:
        _do(db, V.decide, actor=actor, missions=Missions(), verification_id=vid,
            decision='accept')
    assert err.value.detail == {'verification_id': vid, 'state': 'RUNNING'}
    assert _row(db, entities.Verification, vid).state == 'RUNNING'


def test_a_decision_rewrites_only_the_criteria_and_records_the_who(db):
    """verification.py:417-424 (the criteria rewrite, `decided_by`, `note`,
    `holds_mission` cleared): an accept that left a criterion unsatisfied, or a
    decision that did not say who made it, is an unauditable verdict (§17)."""
    actor = who()
    w = _seed(db, actor, mission={'state': 'VERIFYING'})
    vid = _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('mission', w['mid']),
              verifier='generic_human', criterion=0, revision=HEAD,
              criteria=({'index': 0, 'text': 'it works', 'check': 'human',
                         'result': 'unknown'},))['verification_id']
    out = _do(db, V.decide, actor=actor, missions=Missions(), verification_id=vid,
              decision='reject', note='not yet')
    assert (out['state'], out['resumed']) == ('FAILED', False)
    v = _row(db, entities.Verification, vid)
    assert [c['result'] for c in v.criteria] == ['failed']
    assert (v.state, v.decided_by, v.note, v.holds_mission) == ('FAILED', actor.id, 'not yet',
                                                                False)


# ── A6: a guarded mission runs no command, and is never re-run ──────────────

@pytest.mark.parametrize('isolated, seq', [(True, 1), (None, 1), (False, 1), (None, 0)],
                         ids=['isolated', 'unknown', 'ordinary', 'never-prepared'])
def test_only_a_prepared_execution_guards_its_mission(db, isolated, seq):
    """verification.py:114-116 (`unconfined`, with its `process_seq >= 1`
    filter): dropping the filter reads a never-prepared execution's unknown as a
    verdict, and `is False` -> `is not False` lets an isolated one run commands."""
    actor = who()
    w = _seed(db, actor, execution={'isolated': isolated, 'process_seq': seq})
    if isolated is not False and seq >= 1:
        with pytest.raises(V.Refused, match='verification withheld'):
            _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('task', w['tid']),
                verifier='code', execution_id=w['eid'], revision=IMP)
        assert _all(db, entities.Verification) == []
    else:
        out = _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('task', w['tid']),
                  verifier='code', execution_id=w['eid'])
        assert out['state'] == 'RUNNING' and out['verifier_version'] == V.VERIFIER_VERSION


def test_a_guarded_mission_keeps_its_command_checks_while_activation_is_off(db):
    """verification.py:123 (`CONFINED_VERIFICATION_ENABLED`, False in the module):
    with A6-4's switch off even a perfectly confined code row is withheld, and the
    human row that stands in for it says why in the reason it holds with (§6)."""
    actor = who()
    w = _seed(db, actor, execution={'isolated': True, 'import_revision': IMP})
    with pytest.raises(V.Refused, match='verification withheld'):
        _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('task', w['tid']),
            verifier='code', execution_id=w['eid'], revision=IMP)
    assert _all(db, entities.Verification) == []
    out = _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('task', w['tid']),
              verifier='generic_human', execution_id=w['eid'])
    assert out['state'] == 'AWAITING_HUMAN'
    v = _row(db, entities.Verification, out['verification_id'])
    assert v.holds_mission is True and v.verifier_version == V.VERIFIER_VERSION
    assert [e for e in _events(db, 'verification.state_changed')
            if V.WITHHELD in e['reason']]
    assert _row(db, entities.Mission, w['mid']).state == 'BLOCKED'


@pytest.mark.parametrize('bad', [{'workspace': 'w'}, {'revision': HEAD},
                                 {'import_revision': None}, {'verifier': 'research'}],
                         ids=['workdir', 'wrong-revision', 'no-import', 'not-a-code-row'])
def test_a_confined_row_runs_only_over_its_own_import_and_no_workdir(db, monkeypatch, bad):
    """verification.py:123-124 (`confined`) and 208-211 (`verifier == 'code'`):
    each argument below switches off one conjunct of the guard. Any of them
    dropping runs a guarded mission's commands over content that was never
    imported, or outside the sandbox — the exact thing A6 exists to stop."""
    actor = who('system')
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    w = _seed(db, actor, execution={'isolated': True, 'import_revision': IMP})
    bad = dict(bad)
    if 'import_revision' in bad:
        _set(db, w, entities.Execution, w['eid'],
             {'import_revision': bad.pop('import_revision')})      # nothing was imported
    kw = dict(subject=Ref('task', w['tid']), verifier='code', execution_id=w['eid'],
              revision=IMP, workspace=None)
    kw.update(bad)
    with pytest.raises(V.Refused, match='verification withheld'):
        _do(db, V.start, actor=actor, missions=Missions(), **kw)
    assert _all(db, entities.Verification) == []


def test_a_row_may_run_confined_only_with_the_switch_on_and_is_stamped_as_confined(
        db, monkeypatch):
    """verification.py:208-212 (`version = CONFINED_VERIFIER`): the stamp
    is what `retry` may later trust; an unguarded stamp on a guarded row would
    have it re-run free, and the default must be closed when the switch is off."""
    actor = who('system')
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    w = _seed(db, actor, execution={'isolated': True, 'import_revision': IMP})
    out = _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('task', w['tid']),
              verifier='code', execution_id=w['eid'], revision=IMP)
    assert (out['state'], out['verifier_version']) == ('RUNNING', V.CONFINED_VERIFIER)
    v = _row(db, entities.Verification, out['verification_id'])
    assert (v.workspace, v.revision, v.performed_by['harness_id']) == (None, IMP, 'fake')
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', False)
    with pytest.raises(V.Refused, match='verification withheld'):
        _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('task', w['tid']),
            verifier='code', execution_id=w['eid'], revision=IMP)
    assert len(_all(db, entities.Verification)) == 1


@pytest.mark.parametrize('version, workspace',
                         [(V.CONFINED_VERIFIER, 'w'), (None, None), (V.VERIFIER_VERSION, None)],
                         ids=['confined-but-a-workdir', 'no-version', 'unguarded-version'])
def test_a_guarded_rows_error_is_retried_only_while_it_still_may_run_confined(
        db, monkeypatch, version, workspace):
    """verification.py:348-351 (the `not unconfined(...) and not (verifier_version
    == CONFINED_VERIFIER and e ... and confined(...))` refusal): dropping the
    second half re-runs a guarded row free; dropping the first retries one that
    may not run at all."""
    actor = who('system')
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    w = _seed(db, actor, execution={'isolated': True, 'import_revision': IMP})
    vid = _verification(db, actor, w, state='ERROR', verifier_version=version,
                        workspace=workspace, revision=IMP, errors=1, error='no runner')
    with pytest.raises(V.Refused, match='is not retried'):
        _do(db, V.retry, actor=actor, verification_id=vid)
    assert _row(db, entities.Verification, vid).state == 'ERROR'


def test_a_confined_error_is_retried_on_the_same_row_with_its_lineage(db, monkeypatch):
    """verification.py:352-355 (the allowed side of the same guard): the retry is
    on the same row, its execution, plan and confined stamp unchanged and its
    hold cleared. A new row, a kept hold or a lost stamp is what §6 and A6-4
    forbid."""
    actor = who('system')
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    w = _seed(db, actor, execution={'isolated': True, 'import_revision': IMP})
    vid = _errored(db, actor, w, revision=IMP)
    _set(db, w, entities.Verification, vid, {'holds_mission': True})       # as §6 leaves it
    assert _do(db, V.hold, actor=actor, missions=Missions(),
               verification_id=vid)['held'] is True
    assert _do(db, V.retry, actor=actor, verification_id=vid) == \
        {'verification_id': vid, 'state': 'RUNNING'}
    v = _row(db, entities.Verification, vid)
    assert (v.state, v.errors, v.execution_id, v.plan_id, v.verifier_version) == (
        'RUNNING', 1, w['eid'], w['pid'], V.CONFINED_VERIFIER)
    assert v.holds_mission is False
    assert len(_all(db, entities.Verification)) == 1                        # never a new row


def test_an_ordinary_error_is_retried_once_and_a_guarded_one_never(db):
    """verification.py:348 (the unconfined side) and 343-345 (whose lineage the
    check is made from): the retry is ERROR -> PENDING -> RUNNING on the same row,
    so `errors` counts the runs of one verdict; an execution later learned to be
    isolated closes the door again."""
    actor = who()
    w = _seed(db, actor)
    vid = _errored(db, actor, w)
    assert _do(db, V.retry, actor=actor, verification_id=vid)['state'] == 'RUNNING'
    assert _row(db, entities.Verification, vid).errors == 1
    _set(db, w, entities.Execution, w['eid'], {'isolated': True})           # learned late
    _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
        checks=[_errored_check()])
    assert _row(db, entities.Verification, vid).errors == 2                 # one row, two runs
    with pytest.raises(V.Refused, match='is not retried'):
        _do(db, V.retry, actor=actor, verification_id=vid)
    assert _row(db, entities.Verification, vid).state == 'ERROR'


# ── forged and missing evidence (§20) ───────────────────────────────────────

@pytest.mark.parametrize('stage', ['awaiting', 'judged'], ids=['awaiting', 'judged'])
def test_no_checks_are_recorded_on_a_row_that_is_not_running(db, stage):
    """verification.py:242-245 (`if v.state != 'RUNNING': raise Refused(... is %s,
    not RUNNING)`): checks belong to the row the verifier started and to no other.
    Recording onto a row that waits on a person, or onto one already judged, is a
    verdict no check ever produced; the refusal writes no check, no criteria and
    no task move (§20)."""
    actor = who()
    w = _seed(db, actor)
    if stage == 'awaiting':
        vid = _waiting(db, actor, w)
    else:
        vid = _running(db, actor, w)
        assert _do(db, V.record, actor=actor, missions=Missions(),
                   verification_id=vid, checks=[_passing()])['state'] == 'PASSED'
    was = _row(db, entities.Verification, vid)
    task_was = _row(db, entities.Task, w['tid']).state
    before = _n_events(db)
    with pytest.raises(V.Refused, match='not RUNNING'):
        _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
            checks=[_failing()])
    v = _row(db, entities.Verification, vid)
    assert (v.state, v.checks, v.criteria, v.holds_mission) == (
        was.state, was.checks, was.criteria, was.holds_mission)
    assert _row(db, entities.Task, w['tid']).state == task_was
    assert _n_events(db) == before

@pytest.mark.parametrize('corrupt', [False, True], ids=['absent', 'tampered'])
def test_evidence_the_store_cannot_prove_is_refused_and_nothing_is_recorded(db, corrupt):
    """verification.py:247-255: a check whose `output_sha256` the store does not
    hold intact (absent -> OSError, tampered -> ValueError) refuses the whole
    recording. Reading it anyway, or trusting the caller's word for it, is the
    forgery §20 exists to stop."""
    actor = who()
    w = _seed(db, actor)
    vid = _running(db, actor, w)
    sha = hashlib.sha256(b'evidence\n').hexdigest()
    if corrupt:
        store.put(b'evidence\n')                          # the address exists...
        with open(store.path_for(sha), 'wb') as f:        # ...but not its bytes
            f.write(b'tampered\n')
    with pytest.raises(V.Refused, match='does not hold intact'):
        _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
            checks=[_passing(), {'name': 'diff', 'kind': 'git', 'result': 'pass',
                                 'output_sha256': sha}])
    v = _row(db, entities.Verification, vid)
    assert (v.state, v.checks, v.criteria) == ('RUNNING', (), _criteria(0))
    assert _all(db, entities.Artifact) == []


def test_intact_evidence_is_recorded_from_the_store_and_described_once(db):
    """verification.py:256-258 (`if tx.get(entities.Artifact, sha) is None`): the
    describing row is made from the bytes actually read (its size is theirs, not
    the caller's) and a blob already described is not re-described."""
    actor = who()
    w = _seed(db, actor)
    sha1 = store.put(b'first\nsecond\n')
    sha2 = store.put(b'other\n')
    _insert(db, actor, entities.Artifact(id=sha1, media_type='text/plain', size=0),
            subject=Ref('artifact_record', sha1), type_='artifact.recorded')
    vid = _running(db, actor, w)
    out = _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
              checks=[_passing(), {'name': 'diff', 'kind': 'git', 'result': 'pass',
                                   'output_sha256': sha1},
                      {'name': 'log', 'kind': 'git', 'result': 'pass',
                       'output_sha256': sha2}])
    assert out['state'] == 'PASSED'
    arts = {a.id: a for a in _all(db, entities.Artifact)}
    assert (arts[sha2].size, arts[sha2].media_type) == (len(b'other\n'), 'text/plain')
    assert arts[sha1].size == 0                           # left as seeded, not rewritten


def test_a_check_that_carries_no_evidence_of_its_own_is_still_a_check(db):
    """verification.py:248-249 (`if sha is None: continue`): inverted, this
    refuses every command check — that is, every verdict Core ever records."""
    actor = who()
    w = _seed(db, actor)
    vid = _running(db, actor, w)
    assert _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
               checks=[_passing()])['state'] == 'PASSED'


# ── lineage: nothing the caller passes decides it (§9, §20) ─────────────────

@pytest.mark.parametrize('crit, head', [
    (None, HEAD), (-1, HEAD), (1, HEAD), ('0', HEAD), (True, HEAD), (0, 'f' * 40)],
    ids=['missing', 'negative', 'past-the-end', 'string', 'bool', 'wrong-head'])
def test_a_mission_criterion_row_is_bound_to_one_criterion_that_exists_at_the_head(
        db, crit, head):
    """verification.py:198-202 (`isinstance(criterion, int) and 0 <= criterion
    < len(m.success_criteria)`, and `revision != m.integration_head`): a criterion
    Core does not have, or a verdict of another revision, is what would let a
    stale or invented criterion complete a mission. `True` is the int that is not
    one, `'0'` the number that is not a number (§20)."""
    actor = who()
    w = _seed(db, actor, mission={'state': 'VERIFYING'})
    with pytest.raises(V.Refused, match='success criterion|not the mission branch head'):
        _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('mission', w['mid']),
            verifier='generic_human', criterion=crit, revision=head)
    assert _all(db, entities.Verification) == []


def test_the_two_edges_of_the_criterion_index_are_verifiable_and_nothing_else_is_a_subject(db):
    """verification.py:198 (the last criterion is verifiable, `criterion < len`)
    and 204-205 (a subject that is neither a task nor a mission): widened by one
    the bounds take an index with no criterion behind it, and any other subject
    leaves a verdict bound to nothing at all."""
    actor = who()
    w = _seed(db, actor, mission={'state': 'VERIFYING',
                                  'success_criteria': ({'text': 'a', 'check': 'automatic'},
                                                        {'text': 'b', 'check': 'human'})})
    for crit in (0, 1):
        out = _do(db, V.start, actor=actor, missions=Missions(),
                  subject=Ref('mission', w['mid']), verifier='generic_human',
                  criterion=crit, revision=HEAD)
        assert out['state'] == 'AWAITING_HUMAN'
    assert [v.criterion for v in _all(db, entities.Verification)] == [0, 1]
    # a bool is an int that names no criterion, and any other subject is none
    with pytest.raises((V.Refused, ValueError), match='criterion'):
        _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('mission', w['mid']),
            verifier='generic_human', criterion=True, revision=HEAD)
    with pytest.raises(V.Refused, match='a task or a mission'):
        _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('plan', w['pid']),
            verifier='code')
    assert len(_all(db, entities.Verification)) == 2


def test_a_mission_that_is_not_verifying_verifies_nothing(db):
    """verification.py:170 + 196-197 (`mission_open`, and its refusal): a mission
    BLOCKED from somewhere other than VERIFYING has no criteria to decide, and a
    row started there could never be recorded or cleared."""
    actor = who()
    w = _seed(db, actor, mission={'state': 'BLOCKED', 'held_from': 'EXECUTING'})
    with pytest.raises(V.Refused, match='not verifying'):
        _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('mission', w['mid']),
            verifier='generic_human', criterion=0, revision=HEAD)
    assert _all(db, entities.Verification) == []
    _set(db, w, entities.Mission, w['mid'], {'held_from': 'VERIFYING'})  # §17's one hold
    assert _do(db, V.start, actor=actor, missions=Missions(), subject=Ref('mission', w['mid']),
               verifier='generic_human', criterion=0, revision=HEAD)['state'] == 'AWAITING_HUMAN'


@pytest.mark.parametrize('what', ['not-verifying', 'superseded-plan', 'wrong-execution',
                                  'never-ended'],
                         ids=['task-state', 'plan-version', 'other-execution', 'no-end'])
def test_a_verdict_is_bound_to_the_task_the_execution_end_moved_and_the_plan_in_force(
        db, what):
    """verification.py:148-158 (`_task_lineage`): a task not VERIFYING, a plan
    that is not in force, a verification of an execution other than the one whose
    end moved the task, and a latest end that never ended: the four ways a verdict
    can be about something other than what actually ran."""
    actor = who()
    if what == 'not-verifying':
        w = _seed(db, actor, task={'state': 'RUNNING'})
    elif what == 'never-ended':
        w = _seed(db, actor, execution={'state': 'RUNNING'})
    elif what == 'wrong-execution':                      # a later end superseded the row's own
        w = _seed(db, actor, extra=[{'attempt': 2, 'state': 'ENDED_OK', 'isolated': False,
                                      'process_seq': 1}])
    else:
        w = _seed(db, actor)
    kw = {'subject': Ref('task', w['tid']), 'verifier': 'code', 'execution_id': w['eid']}
    if what == 'superseded-plan':
        _insert(db, actor, entities.Plan(id=ids.new_id('plan'), mission_id=w['mid'],
                                         state='APPROVED', plan_version=2))
    with pytest.raises(V.Refused, match='not VERIFYING|not in force|not the one whose end'):
        _do(db, V.start, actor=actor, missions=Missions(), **kw)
    assert _all(db, entities.Verification) == []


def test_a_verdict_is_never_recorded_over_a_moved_branch_or_a_superseded_plan(db):
    """verification.py:264-267: a mission whose head moved, or whose plan was
    replaced while the checks ran, may not have the verdict recorded at all
    (§11, §20): a judgement would read a verdict about a dead revision."""
    actor = who()
    w = _seed(db, actor, mission={'state': 'VERIFYING'})
    vid = _verification(db, actor, w, subject=Ref('mission', w['mid']),
                        verifier='generic_human', criterion=0, revision=HEAD,
                        execution_id=None)
    _set(db, w, entities.Mission, w['mid'], {'integration_head': 'f' * 40})
    with pytest.raises(V.Refused, match='moved since'):
        _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
            checks=[_passing()])
    _set(db, w, entities.Mission, w['mid'], {'integration_head': HEAD})
    _insert(db, actor, entities.Plan(id=ids.new_id('plan'), mission_id=w['mid'],
                                     state='APPROVED', plan_version=2))
    with pytest.raises(V.Refused, match='not in force'):
        _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
            checks=[_passing()])
    v = _row(db, entities.Verification, vid)
    assert (v.state, v.checks) == ('RUNNING', ())


def test_a_head_that_moved_while_the_checks_ran_is_recorded_with_the_verdict(db):
    """verification.py:280-281 (`if v.subject.kind == 'mission' and head and head
    != m.integration_head`): without it a verdict is recorded as though nothing
    had moved, and everything §11 decides afterwards reads a stale head."""
    actor = who()
    w = _seed(db, actor, mission={'state': 'VERIFYING'})
    vid = _verification(db, actor, w, subject=Ref('mission', w['mid']),
                        verifier='generic_human', criterion=0, revision=HEAD,
                        execution_id=None)
    out = _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
              checks=[{'name': 'review', 'kind': 'git', 'result': 'pass'}], head='a' * 40)
    assert out['state'] == 'ERROR'                        # no outcome check: never PASSED
    assert _row(db, entities.Mission, w['mid']).integration_head == 'a' * 40


# ── verdicts, coverage, and what a task may become (§6, §8.4, §13) ──────────

def test_a_task_succeeds_only_when_every_criterion_is_covered(db):
    """verification.py:306 (`if not mine or any(s != 'PASSED' ...) or uncovered(t,
    mine)`) and 308-312 (a worktree task's `integration_state = PENDING`): a task
    whose second criterion no verification satisfied would SUCCEED with a
    criterion untested (§13), and a worktree result would never be merged back."""
    actor = who()
    w = _seed(db, actor, worktree=True,
              task={'acceptance': ({'text': 'a', 'check': 'automatic'},
                                    {'text': 'b', 'check': 'automatic'})})
    out = _do(db, V.record, actor=actor, missions=Missions(),
              verification_id=_running(db, actor, w, criteria=_criteria(0)),
              checks=[_passing()])
    assert (out['state'], out['task_state']) == ('PASSED', 'VERIFYING')
    t = _row(db, entities.Task, w['tid'])
    assert (t.state, t.integration_state) == ('VERIFYING', None)
    out = _do(db, V.record, actor=actor, missions=Missions(),
              verification_id=_running(db, actor, w, criteria=_criteria(1)),
              checks=[_passing()])
    assert out['task_state'] == 'SUCCEEDED'
    t = _row(db, entities.Task, w['tid'])
    assert (t.state, t.integration_state) == ('SUCCEEDED', 'PENDING')


def test_an_in_place_task_is_never_left_a_merge_to_do(db):
    """verification.py:309-311 (`if e.branch == task_branch(t)`): setting
    `integration_state` for a task that ran in place would hand the engine a merge
    of nothing — and, inverted, a worktree result is silently lost."""
    actor = who()
    w = _seed(db, actor)                                   # the execution has no branch
    out = _do(db, V.record, actor=actor, missions=Missions(),
              verification_id=_running(db, actor, w), checks=[_passing()])
    assert out['task_state'] == 'SUCCEEDED'
    t = _row(db, entities.Task, w['tid'])
    assert (t.state, t.integration_state) == ('SUCCEEDED', None)


def test_an_error_verdict_costs_the_row_an_attempt_and_never_the_task(db):
    """verification.py:274-279 (the ERROR fields) and 283 (`and state != 'ERROR'`):
    an error is the verifier's fault, so it spends the row's retry budget (§6) and
    must not move the task at all — which is exactly what a runner that cannot
    start looks like to a user."""
    actor = who()
    w = _seed(db, actor)
    vid = _running(db, actor, w)
    out = _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
              checks=[_passing(), dict(_errored_check(), name='runner')])
    assert out == {'verification_id': vid, 'state': 'ERROR'}               # no task_state
    v = _row(db, entities.Verification, vid)
    assert (v.state, v.errors, v.error) == ('ERROR', 1, 'the runner is not installed')
    assert [c['result'] for c in v.criteria] == ['unknown']                # §8.4
    assert _row(db, entities.Task, w['tid']).state == 'VERIFYING'


def test_an_error_with_no_errored_check_says_so_and_a_failure_spends_the_attempts(db):
    """verification.py:65-66 (`if not any(c['kind'] == 'command')` -> ERROR) with
    276 (the `'no outcome check could run'` default), and 301-305
    (`charged_failure`): checks that observed nothing are not a pass, and a FAILED
    verdict retries while charged attempts remain and fails the task, with its
    failure class, when they are spent — P11's D9 rule seen from P13."""
    actor = who()
    w = _seed(db, actor)
    vid = _running(db, actor, w)
    _do(db, V.record, actor=actor, missions=Missions(), verification_id=vid,
        checks=[{'name': 'diff', 'kind': 'git', 'result': 'pass'}])
    v = _row(db, entities.Verification, vid)
    assert (v.state, v.errors, v.error) == ('ERROR', 1, 'no outcome check could run')

    w2 = _seed(db, actor)
    out = _do(db, V.record, actor=actor, missions=Missions(),
              verification_id=_running(db, actor, w2), checks=[_failing()])
    assert out['task_state'] == 'READY'                     # 1 charged attempt of 2
    assert _row(db, entities.Task, w2['tid']).state == 'READY'

    w3 = _seed(db, actor, task={'max_attempts': 1})
    out = _do(db, V.record, actor=actor, missions=Missions(),
              verification_id=_running(db, actor, w3), checks=[_failing()])
    assert out['task_state'] == 'FAILED'
    t = _row(db, entities.Task, w3['tid'])
    assert (t.state, t.failure_class) == ('FAILED', 'verification')


def test_a_running_row_is_crashed_by_a_restart_and_no_other_row_is_touched(db):
    """verification.py:459-471 (`sweep`): only a RUNNING row ran under a Core that
    died. Crashing an AWAITING_HUMAN one erases what waits for a person; a sweep
    that did not count the error would hide a row that crashes forever (§19)."""
    actor = who()
    w = _seed(db, actor)
    running = _running(db, actor, w)
    held = _waiting(db, actor, w)
    other = _seed(db, actor)
    passed = _running(db, actor, other)
    _do(db, V.record, actor=actor, missions=Missions(), verification_id=passed,
        checks=[_passing()])
    before = _n_events(db)
    assert _do(db, V.sweep, actor=actor) == [running]
    v = _row(db, entities.Verification, running)
    assert (v.state, v.errors, v.error) == ('ERROR', 1, 'core_restarted')
    assert _row(db, entities.Verification, held).state == 'AWAITING_HUMAN'
    assert _row(db, entities.Verification, held).holds_mission is True
    assert _row(db, entities.Verification, passed).state == 'PASSED'
    assert _n_events(db) == before + 1                      # one move, one event


def test_a_held_row_blocks_only_a_mission_that_is_executing(db):
    """verification.py:358-379 (`hold`, `_hold` and its `if m.state ==
    'EXECUTING'`): the reason is the verifier's error for an ordinary mission and
    WITHHELD for a guarded one, and a mission already out of EXECUTING is left
    where it is — hijacking it to BLOCKED would rewrite where it really was."""
    actor = who()
    w = _seed(db, actor)
    vid = _errored(db, actor, w)
    assert _do(db, V.hold, actor=actor, missions=Missions(), verification_id=vid) == \
        {'verification_id': vid, 'held': True}
    m = _row(db, entities.Mission, w['mid'])
    assert (m.state, m.held_from) == ('BLOCKED', 'EXECUTING')
    assert _row(db, entities.Verification, vid).holds_mission is True
    blocks = [e for e in _events(db, 'mission.state_changed') if e['to'] == 'BLOCKED']
    assert len(blocks) == 1 and 'verification could not run' in blocks[0]['reason']

    w2 = _seed(db, actor, mission={'state': 'VERIFYING'})
    vid2 = _errored(db, actor, w2)
    assert _do(db, V.hold, actor=actor, missions=Missions(),
               verification_id=vid2)['held'] is True
    assert _row(db, entities.Mission, w2['mid']).state == 'VERIFYING'
    assert _row(db, entities.Verification, vid2).holds_mission is True


# ── what still holds a mission, and its release (§17) ───────────────────────

def test_the_mission_resumes_only_when_the_last_row_waiting_on_you_is_decided(db):
    """verification.py:431-435 (`if m.state == 'BLOCKED' and not _still_held(...)`,
    the resume and its `resumed` answer): resuming while a second row still waits
    puts an unfinished mission back in the engine's hands."""
    actor = who()
    w = _seed(db, actor)
    ms = Missions()
    first = _waiting(db, actor, w, missions=ms)
    second = _waiting(db, actor, w, missions=ms)
    out = _do(db, V.decide, actor=actor, missions=ms, verification_id=first,
              decision='accept')
    assert out['resumed'] is False
    assert _row(db, entities.Mission, w['mid']).state == 'BLOCKED'
    assert _do(db, V.decide, actor=actor, missions=ms, verification_id=second,
               decision='accept')['resumed'] is True
    assert _row(db, entities.Mission, w['mid']).state == 'EXECUTING'
    assert [c for c, _m in ms.calls].count('resume') == 1


def test_a_mission_criterion_that_waits_on_you_holds_the_mission_by_itself(db):
    """verification.py:450-452 (the second clause of `_still_held`: a criterion of
    the plan in force at the current head counts by state alone, `holds_mission`
    or not): dropping it resumes a mission whose criterion no one has accepted."""
    actor = who()
    w = _seed(db, actor)
    _criterion_row(db, actor, w, 'AWAITING_HUMAN')            # not holding by its own flag
    vid = _waiting(db, actor, w)
    assert _do(db, V.decide, actor=actor, missions=Missions(), verification_id=vid,
               decision='accept')['resumed'] is False
    # the task's row is decided and no longer holds: the criterion alone still does
    assert _row(db, entities.Verification, vid).holds_mission is False
    vid2 = _waiting(db, actor, w)
    assert _do(db, V.decide, actor=actor, missions=Missions(), verification_id=vid2,
               decision='reject')['resumed'] is False
    assert _row(db, entities.Mission, w['mid']).state == 'BLOCKED'


def test_a_conflicting_merge_holds_the_mission_until_the_merge_is_settled(db):
    """verification.py:453-454 (the third clause of `_still_held`: a task of the
    plan in force still in merge CONFLICT): resuming over it puts the mission back
    in the engine while its result is still unresolved (§12.5); `retry_merge`
    settles it and the next decision resumes."""
    actor = who()
    w = _seed(db, actor)
    _criterion_row(db, actor, w, 'PASSED')                    # a criterion already accepted
    other = ids.new_id('task')                                # another task's unresolved result
    _insert(db, actor, entities.Task(id=other, plan_id=w['pid'], mission_id=w['mid'],
                                     key='t2', title='T2', kind='code_change',
                                     state='BLOCKED', integration_state='CONFLICT',
                                     acceptance=({'text': 'it works', 'check': 'automatic'},)))
    ms = Missions()
    vid = _waiting(db, actor, w, missions=ms)
    assert _do(db, V.decide, actor=actor, missions=ms, verification_id=vid,
               decision='accept')['resumed'] is False
    assert _row(db, entities.Mission, w['mid']).state == 'BLOCKED'
    assert _do(db, V.retry_merge, actor=actor,
               task_id=other)['integration_state'] == 'PENDING'
    vid2 = _waiting(db, actor, w, missions=ms)
    assert _do(db, V.decide, actor=actor, missions=ms, verification_id=vid2,
               decision='accept')['resumed'] is True
    assert _row(db, entities.Mission, w['mid']).state == 'EXECUTING'


# ── merge-back (§12) ────────────────────────────────────────────────────────

def test_only_the_verified_revision_of_the_plan_in_force_may_begin_merging(db):
    """verification.py:127-140 + 143-145 + 483-490 (`mergeable_revision`,
    `_in_force`, the `task_verified` guard): the three refusals that make D10
    true — another revision, and a superseded plan — each write nothing."""
    actor = who()
    w = _succeeded(db, actor, revision=RECV)
    with pytest.raises(lifecycle.GuardFailed, match='not the verified'):
        _do(db, V.begin_merge, actor=actor, task_id=w['tid'], revision='deadbeef')
    assert _row(db, entities.Task, w['tid']).integration_state == 'PENDING'
    w2 = _succeeded(db, actor, revision=RECV)
    _insert(db, actor, entities.Plan(id=ids.new_id('plan'), mission_id=w2['mid'],
                                     state='APPROVED', plan_version=2))
    with pytest.raises(lifecycle.GuardFailed, match='not in force'):
        _do(db, V.begin_merge, actor=actor, task_id=w2['tid'], revision=RECV)
    assert _row(db, entities.Task, w2['tid']).integration_state == 'PENDING'
    assert _do(db, V.begin_merge, actor=actor, task_id=w['tid'],
               revision=RECV)['integration_state'] == 'MERGING'


def test_a_merge_never_takes_a_revision_no_intact_row_of_the_plan_in_force_gives(db):
    """verification.py:132-140 (`mergeable_revision`: no PASSED row of that plan,
    or one whose execution is known-isolated, means no revision at all) and
    498-501 (`is not MERGING`, then `mergeable_revision is None`): A5, seen from
    the merge — never an older row instead."""
    actor = who()
    w = _seed(db, actor)                                    # nothing verified at all
    with pytest.raises(V.Refused, match='not merging'):
        _do(db, V.record_merge, actor=actor, missions=Missions(), task_id=w['tid'],
            outcome='merged', head='a' * 40)
    w = _succeeded(db, actor, revision=RECV)
    _do(db, V.begin_merge, actor=actor, task_id=w['tid'], revision=RECV)
    _set(db, w, entities.Execution, w['eid'], {'isolated': True})           # learned late
    with pytest.raises(V.Refused, match='no revision a merge may take'):
        _do(db, V.record_merge, actor=actor, missions=Missions(), task_id=w['tid'],
            outcome='merged', head='b' * 40)
    t = _row(db, entities.Task, w['tid'])
    assert (t.integration_state, t.merged_revision) == ('MERGING', None)
    assert _row(db, entities.Mission, w['mid']).integration_head == HEAD


def test_a_merge_records_the_head_it_moved_or_blocks_the_mission(db):
    """verification.py:502-518: `merged` moves the mission head in the same
    transaction and keeps the base the mission already had; `conflict` keeps
    the paths and blocks an EXECUTING mission; anything else is a ValueError that
    writes neither half."""
    actor = who()
    w = _succeeded(db, actor, revision=RECV, mission={'integration_base': '7' * 40})
    _do(db, V.begin_merge, actor=actor, task_id=w['tid'], revision=RECV)
    out = _do(db, V.record_merge, actor=actor, missions=Missions(), task_id=w['tid'],
              outcome='merged', head='b' * 40, base='9' * 40)
    assert out == {'task_id': w['tid'], 'integration_state': 'MERGED', 'head': 'b' * 40}
    t = _row(db, entities.Task, w['tid'])
    m = _row(db, entities.Mission, w['mid'])
    assert (t.integration_state, t.merged_revision, t.conflicts) == ('MERGED', 'b' * 40, ())
    # the base of the mission branch was known before this merge: it stays what it was
    assert (m.integration_head, m.integration_base) == ('b' * 40, '7' * 40)

    w2 = _succeeded(db, actor, revision=RECV)
    _do(db, V.begin_merge, actor=actor, task_id=w2['tid'], revision=RECV)
    with pytest.raises(ValueError, match='merged or conflict'):
        _do(db, V.record_merge, actor=actor, missions=Missions(), task_id=w2['tid'],
            outcome='squashed', head='b' * 40)
    t2 = _row(db, entities.Task, w2['tid'])
    assert (t2.integration_state, t2.merged_revision) == ('MERGING', None)
    assert _row(db, entities.Mission, w2['mid']).integration_head == HEAD
    out = _do(db, V.record_merge, actor=actor, missions=Missions(), task_id=w2['tid'],
              outcome='conflict', conflicts=['calc.py', 'other.py'])
    assert out == {'task_id': w2['tid'], 'integration_state': 'CONFLICT',
                   'conflicts': ['calc.py', 'other.py']}
    t2 = _row(db, entities.Task, w2['tid'])
    assert (t2.integration_state, t2.conflicts, t2.merged_revision) == (
        'CONFLICT', ('calc.py', 'other.py'), None)
    m2 = _row(db, entities.Mission, w2['mid'])
    assert (m2.state, m2.held_from) == ('BLOCKED', 'EXECUTING')
    assert _do(db, V.retry_merge, actor=actor,
               task_id=w2['tid'])['integration_state'] == 'PENDING'


def test_only_a_user_device_abandons_a_merge(db):
    """verification.py:530-538: giving up a task's result is the user's decision
    alone, and it is the `user_abandons` edge to ABANDONED; a worker that could
    abandon a conflict would erase the evidence of it (§12.5)."""
    actor = who()
    w = _succeeded(db, actor, revision=RECV)
    _do(db, V.begin_merge, actor=actor, task_id=w['tid'], revision=RECV)
    _do(db, V.record_merge, actor=actor, missions=Missions(), task_id=w['tid'],
        outcome='conflict', conflicts=['calc.py'])
    with pytest.raises(V.Refused, match='only a user device'):
        _do(db, V.abandon_integration, actor=who('system'), task_id=w['tid'], reason='no')
    assert _row(db, entities.Task, w['tid']).integration_state == 'CONFLICT'
    assert _do(db, V.abandon_integration, actor=actor, task_id=w['tid'],
               reason='not worth it') == {'task_id': w['tid'],
                                          'integration_state': 'ABANDONED'}
    assert _row(db, entities.Task, w['tid']).integration_state == 'ABANDONED'


def test_the_mission_head_is_recorded_once_and_the_base_only_when_it_is_new(db):
    """verification.py:541-554 (`note_integration_head`): a note that wrote the
    same head again would stale the mission's version and bury the real move in
    events (§11); `integration_base` is recorded once and never overwritten."""
    actor = who()
    w = _seed(db, actor)
    before = _n_events(db)
    assert _do(db, V.note_integration_head, actor=actor, mission_id=w['mid'],
               head=HEAD) == {'changed': False}
    assert _n_events(db) == before
    assert _do(db, V.note_integration_head, actor=actor, mission_id=w['mid'], head=HEAD,
               base='9' * 40) == {'changed': True}
    m = _row(db, entities.Mission, w['mid'])
    assert (m.integration_head, m.integration_base) == (HEAD, '9' * 40)
    assert _do(db, V.note_integration_head, actor=actor, mission_id=w['mid'], head=HEAD,
               base='1' * 40) == {'changed': True}          # the head had not moved
    assert _row(db, entities.Mission, w['mid']).integration_base == '9' * 40
    assert _do(db, V.note_integration_head, actor=actor, mission_id=w['mid'],
               head='2' * 40)['changed'] is True


# ── review (§7, §14) ────────────────────────────────────────────────────────

def test_a_review_needs_a_reviewing_mission_and_a_verdict_that_exists(db):
    """verification.py:565-575: the four refusals — a mission that is not
    REVIEWING, a verdict outside the three, a `user` review not recorded by a user
    device, and findings Core has no column for. Each is what keeps a review from
    completing, replanning or annotating a mission that is not a review's."""
    actor = who()
    w = _seed(db, actor, mission={'state': 'EXECUTING'})
    with pytest.raises(lifecycle.IllegalTrigger, match='a review needs REVIEWING'):
        _do(db, V.record_review, actor=actor, missions=Missions(), mission_id=w['mid'],
            verdict='accept', reviewer='judge')
    w2 = _seed(db, actor, mission={'state': 'REVIEWING'})
    with pytest.raises(ValueError, match='accept, changes_requested or reject'):
        _do(db, V.record_review, actor=actor, missions=Missions(), mission_id=w2['mid'],
            verdict='maybe', reviewer='judge')
    with pytest.raises(V.Refused, match='recorded by a user device'):
        _do(db, V.record_review, actor=who('system'), missions=Missions(), mission_id=w2['mid'],
            verdict='accept', reviewer='user', user=True)
    with pytest.raises(ValueError, match='unknown review fields'):
        _do(db, V.record_review, actor=actor, missions=Missions(), mission_id=w2['mid'],
            verdict='accept', reviewer='judge', opinions='everything')
    assert _all(db, entities.Review) == []
    assert _row(db, entities.Mission, w2['mid']).state == 'REVIEWING'


def test_a_users_review_is_always_independent_and_a_reject_completes_nothing(db):
    """verification.py:576-597 (`'user' if user else reviewer`, `True if user`,
    the principal, the plan in force, and the two mission moves with the absence
    of one for `reject`): a user's review that was not marked independent, or a
    reject that completed the mission, is the §14 gate failing open."""
    actor = who()
    w = _seed(db, actor, mission={'state': 'REVIEWING'})
    ms = Missions()
    out = _do(db, V.record_review, actor=actor, missions=ms, mission_id=w['mid'],
              verdict='accept', reviewer='judge', independent=False, user=True,
              summary='ship it', requirements_met=['r1'], risks=['none'])
    assert (out['verdict'], out['independent'], out['mission']['state']) == ('accept', True,
                                                                             'COMPLETED')
    r = _row(db, entities.Review, out['review_id'])
    assert (r.reviewer, r.independent, r.principal_id, r.plan_id) == ('user', True, actor.id,
                                                                      w['pid'])
    assert (r.requirements_met, r.risks, r.summary, r.state) == (('r1',), ('none',), 'ship it',
                                                                 'ACCEPTED')
    assert ms.calls == [('accept', w['mid'])]

    w2 = _seed(db, actor, mission={'state': 'REVIEWING'})
    ms2 = Missions()
    out = _do(db, V.record_review, actor=actor, missions=ms2, mission_id=w2['mid'],
              verdict='reject', reviewer='judge', independent=True)
    assert (out['mission'], out['independent']) == (None, True)
    assert _row(db, entities.Mission, w2['mid']).state == 'REVIEWING'
    assert _row(db, entities.Review, out['review_id']).state == 'REJECTED'
    assert ms2.calls == []

    w3 = _seed(db, actor, mission={'state': 'REVIEWING'})
    ms3 = Missions()
    out = _do(db, V.record_review, actor=actor, missions=ms3, mission_id=w3['mid'],
              verdict='changes_requested', reviewer='judge', independent=False)
    assert out['independent'] is False                      # a model's own word kept
    assert _row(db, entities.Mission, w3['mid']).state == 'REPLANNING'
    assert ms3.calls == [('changes_requested', w3['mid'])]
