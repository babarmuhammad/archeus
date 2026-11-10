"""T-305 (pv22-verification-hardening): the branches of the verification worker
(`archeus/core/verification/worker.py`) that no test in tests/v1 reached — the
fail-closed and denial paths first, then the boundary values, then the error
paths.

The rig is the one tests/v1/integration/test_verification.py built for this
worker, kept to what a unit test may hold: the real worker over a real database
of real rows, so every lineage `application/verification.py` re-derives really
is re-derived, with a fake for each call the worker makes out of the process
(git, a command, a confined run, the staged runtime, the engine's mission port).
A node call no fake was given for fails the test where it is made, so a worker
that reached git, a command or the staged runtime where it must not is caught
here rather than left to whatever the machine running the suite has installed.
Nothing here needs a real repository, a process, the network or Windows.
"""

import os
import sys

import pytest

from archeus.core.application import errors, verification as V
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.verification.worker import VerifyWorker
from archeus.infra.db import Database
from archeus.infra.db import rows
from archeus.node.local import PathTooLong

#: revisions as git would name them, and the base the mission branch was cut at
REV, REV2, IMP, BASE = 'a' * 40, 'b' * 40, 'c' * 40, 'd' * 40
#: what the plan's one task asks for, and what the mission asks of its branch
AUTO = {'text': 'the checks pass', 'check': 'automatic'}
HUMAN = {'text': 'it looks right', 'check': 'human'}
#: one criterion reading, as a passed row leaves it
OK0 = {'index': 0, 'text': 'the checks pass', 'check': 'automatic', 'result': 'satisfied'}
UNKNOWN0 = {'index': 0, 'text': 'the checks pass', 'check': 'automatic', 'result': 'unknown'}


class _Missions:
    """The engine's mission port: what the worker asked the engine to move, and
    the move made for real through the state table, so a test sees the mission
    as the worker left it. What stays fake is the engine's own judgement of the
    reason: only the worker's request is recorded here."""

    def __init__(self):
        self.fired = []

    def fire(self, tx, *, actor, mission_id, trigger, reason=None, **_kw):
        self.fired.append((mission_id, trigger, reason))
        if trigger != 'block':
            return {'state': 'EXECUTING'}
        frm = tx.get(entities.Mission, mission_id).entity.state
        row, _e = tx.transition(entities.Mission, mission_id, 'BLOCKED', actor=actor,
                                reason=reason, fields={'held_from': frm})
        return {'state': row.entity.state}


class _Node:
    """The worker's node (the integration file's `_Node`, with no real
    `LocalNode` under it): every call recorded, each answered by the fake given
    for it, and any call no fake was given for fails the test where it is made —
    that is how these tests say that *nothing* reached git or a command."""

    def __init__(self, **fake):
        self.fake, self.calls = fake, []

    def __getattr__(self, name):
        def call(*a, **k):
            self.calls.append(name)
            if name not in self.fake:
                raise AssertionError('the worker called node.%s%r' % (name, a))
            return self.fake[name](*a, **k)
        return call


def _script(*answers):
    """A fake answer handing out *answers* in turn and keeping the last one."""
    left = list(answers)

    def answer(*_a, **_k):
        return left.pop(0) if len(left) > 1 else left[0]
    return answer


def _result(exit_code=0, error=None, output=b'ok', **extra):
    """One command run, as the node reports it: the shape `evidence.check_of` reads."""
    return dict({'exit_code': exit_code, 'duration_ms': 1, 'error': error, 'output': output,
                 'output_bytes': len(output), 'truncated': False}, **extra)


class _Confined:
    """A fake `run_confined_check` (the integration file's): records each attempt
    and the inputs it was given, and answers by calling *record* before it
    returns, as the real one does."""

    def __init__(self, *results):
        self.results, self.seen, self.inputs = list(results), [], []

    def __call__(self, vid, attempt, argv, *, toolchain, timeout, record, project_id,
                 revision, workdirs):
        self.seen.append((vid, attempt, list(argv), list(toolchain)))
        self.inputs.append({'timeout': timeout, 'project_id': project_id,
                            'revision': revision, 'workdirs': list(workdirs)})
        # what the real one does: the verdict is recorded before it returns
        r = dict({'exit_code': 0, 'duration_ms': 1, 'error': None, 'output': b'ok',
                  'output_bytes': 2, 'truncated': False,
                  'confinement': {'isolated': True, 'job': 'fake'}},
                 **(self.results.pop(0) if self.results else {}))
        record(r)
        return r


@pytest.fixture
def stage():
    """The directory of one real staged program, and its name: what
    `evidence.confined_argv` will accept as confined, and nothing outside it.

    The interpreter's own directory rather than a program written under pytest's
    tmp_path, because `confined_argv` asks the platform whether a file may be run
    at all, and a temporary directory mounted noexec refuses every file written
    into it — whereupon the mount decides what the worker is supposed to decide.
    Nothing is run from here and nothing is staged: the worker's own staging call
    is replaced in every test that uses this, so the guard that no test may stage
    the installed runtime is never reached, and the confined run is faked."""
    exe = os.path.realpath(sys.executable)
    return os.path.dirname(exe), os.path.basename(exe)


class _Rig:
    """One verification worker over a Core whose rows an earlier pass left
    behind: the real database and the real sinks, and a fake per call out of the
    process. `timeout_s` is the worker's own bound, chosen to differ from
    `evidence.CHECK_TIMEOUT_S` so a check that reached the module default rather
    than the worker's value is caught.

    One of these per test: they are all the one ARCHEUS_HOME, so two would read
    one database and each other's rows."""

    def __init__(self, tmp_path, *, node=None, calls=None, timeout_s=7,
                 mission_state='EXECUTING', success=(), base=None, head=None,
                 held_from=None, task_state='VERIFYING', kind='code_change',
                 acceptance=(AUTO,), integration_state=None, isolated=False,
                 process_seq=1, attempt=1, imported=None, seed_rev=None, branch=None,
                 workdir='worktree', tests=('tool --check',), builds=(), project=True,
                 model='m-large'):
        self.db = Database.open()
        self.actor = Ref('system', ids.new_id('principal'))
        self.root = str(tmp_path / 'project')
        self.missions = _Missions()
        self.node = node if node is not None else _Node()
        self.worker = VerifyWorker(self.db, actor=self.actor, missions=self.missions,
                                   calls=calls, node=self.node, timeout_s=timeout_s)
        self.mid = ids.new_id('mission')
        self.plan_id = ids.new_id('plan')
        self.tid = ids.new_id('task')
        self.eid = ids.new_id('execution')
        self.proj = ids.new_id('project') if project else None
        t = entities.Task(id=self.tid, plan_id=self.plan_id, mission_id=self.mid, key='t1',
                          title='Do the work', kind=kind, acceptance=tuple(acceptance),
                          state=task_state, integration_state=integration_state)
        items = [entities.Mission(
            id=self.mid, workspace_id=ids.GLOBAL_WORKSPACE, title='Fix add',
            objective='Make add add', project_id=self.proj, success_criteria=tuple(success),
            integration_base=base, integration_head=head, held_from=held_from,
            state=mission_state),
            entities.Plan(id=self.plan_id, mission_id=self.mid, plan_version=1,
                          summary='one task', state='APPROVED'),
            t]
        if self.proj is not None:
            # P4's rows, so the commands the worker runs come from a real
            # inspection rather than from a fake of the read that finds them
            repo = entities.Repository(id=ids.new_id('repository'),
                                       workspace_id=ids.GLOBAL_WORKSPACE,
                                       project_id=self.proj, path=self.root,
                                       path_key=os.path.normcase(os.path.abspath(self.root)))
            items += [entities.Project(id=self.proj, workspace_id=ids.GLOBAL_WORKSPACE,
                                       name='repo', root_paths=(self.root,)), repo,
                      entities.RepositoryInspection(id=ids.new_id('repository_inspection'),
                                                    repository_id=repo.id, extractor_version=1,
                                                    state='COMPLETED',
                                                    test_commands=tuple(tests),
                                                    build_commands=tuple(builds))]
        items.append(entities.Execution(
            id=self.eid, task_id=self.tid, mission_id=self.mid, attempt=attempt,
            harness_id='h1', model=model, process_seq=process_seq, state='ENDED_OK',
            exit_reason='ok', isolated=isolated, workdir=workdir, plan_id=self.plan_id,
            branch=V.task_branch(t) if branch == 'task' else branch,
            seed_revision=seed_rev, import_revision=imported))
        self._place(*items)

    # ── placing rows ──

    def _place(self, *items):
        """One writer command placing rows as an earlier pass left them, with the
        event that records them: a mutation without an event is rolled back."""
        def put(tx, *, actor):
            for x in items:
                tx.insert(x, actor=actor)
            tx.append(new_event('mission.updated', Ref('mission', self.mid), actor,
                                payload={'fields': [], 'placed_by': 'T-305'},
                                workspace=ids.GLOBAL_WORKSPACE, project=self.proj))
        return self.db.writer.execute(put, {'actor': self.actor})

    def place_at(self, stamp, *items):
        """The same at a stated time, so a row can be placed before the plan was
        made (`_review_due` reads `created_at`)."""
        glue = new_event.__globals__
        old = glue['now_iso']
        glue['now_iso'] = lambda: stamp
        try:
            return self._place(*items)
        finally:
            glue['now_iso'] = old

    def vrow(self, subject='task', **fields):
        """A Verification row of this rig's task (or of its mission) as a crash
        or an older pass left it."""
        f = dict(id=ids.new_id('verification'),
                 subject=Ref('mission' if subject == 'mission' else 'task',
                             self.mid if subject == 'mission' else self.tid),
                 verifier='code', plan_id=self.plan_id, execution_id=self.eid,
                 verifier_version=V.VERIFIER_VERSION, state='ERROR')
        if f['subject'].kind == 'mission':
            f.pop('execution_id')
            f.update(criterion=0)
        f.update(fields)
        self._place(entities.Verification(**f))
        return f['id']

    def erow(self, **fields):
        """Another attempt of the task, as a dispatch left it."""
        f = dict(id=ids.new_id('execution'), task_id=self.tid, mission_id=self.mid,
                 attempt=2, harness_id='h1', process_seq=2, state='ENDED_ERROR',
                 exit_reason='error', isolated=False)
        f.update(fields)
        self._place(entities.Execution(**f))
        return f['id']

    def drow(self, at=None, **fields):
        """A review call's RouteDecision, as `OwnCalls` recorded how it ended."""
        f = dict(id=ids.new_id('route_decision'),
                 subject=Ref('route_decision', ids.new_id('route_decision')),
                 purpose='review', source=Ref('mission', self.mid),
                 outcome={'state': 'error'})
        f.update(fields)
        return (self.place_at(at, entities.RouteDecision(**f)) if at is not None
                else self._place(entities.RouteDecision(**f)))

    def rrow(self, **fields):
        """A Review of the plan in force."""
        f = dict(id=ids.new_id('review'), mission_id=self.mid, reviewer='model',
                 plan_id=self.plan_id, state='ACCEPTED')
        f.update(fields)
        return self._place(entities.Review(**f))

    # ── reading and running ──

    def get(self, cls, entity_id):
        with self.db.read() as conn:
            r = rows.get(conn, cls, entity_id)
        return None if r is None else r.entity

    def where(self, cls, **eq):
        with self.db.read() as conn:
            return [r.entity for r in rows.where(conn, cls, **eq)]

    def plan(self):
        with self.db.read() as conn:
            return self.worker.plan(conn)

    def task(self):
        return self.get(entities.Task, self.tid)

    def mission(self):
        return self.get(entities.Mission, self.mid)

    def verification(self, vid):
        return self.get(entities.Verification, vid)

    def rows(self, kind='task'):
        """The worker's Verification rows, of the task or of the mission."""
        return [v for v in self.where(entities.Verification) if v.subject.kind == kind]

    def one(self, kind='task'):
        (v,) = self.rows(kind)
        return v

    def spy(self):
        """Record every writer command the worker runs, as (name, kwargs)."""
        real, seen = self.worker._do, []

        def do(command, **kw):
            seen.append((getattr(command, '__name__', '?'), kw))
            return real(command, **kw)
        self.worker._do = do
        return seen

    def close(self):
        self.db.close()


@pytest.fixture
def rig(tmp_path):
    """Make the test's one rig, and close it afterwards. Exactly one: a second
    would be a second Core over the one ARCHEUS_HOME, reading the first's rows."""
    made = []

    def make(**kw):
        assert not made, 'one rig per test: two share the one database'
        made.append(_Rig(tmp_path, **kw))
        return made[0]
    yield make
    for r in made:
        r.close()


# ── the loop itself: what it refuses to swallow, and what it leaves alone ──

def test_a_closed_writer_is_raised_and_never_recorded_as_a_lost_race(rig, monkeypatch):
    # worker.py:90-91 `except errors.WriterClosed: raise` — the one error this
    # loop may not turn into a lost race: swallowing it would report a Core whose
    # writer has gone as though another writer had simply been first
    r = rig(workdir=None)
    assert r.plan() == [('verify_task', r.tid, r.eid)]

    def closed(command, **kw):
        raise errors.WriterClosed('the writer closed')
    monkeypatch.setattr(r.worker, '_do', closed)
    with pytest.raises(errors.WriterClosed):
        r.worker.pass_once()

    def lost(command, **kw):
        raise V.Refused('the task moved on')
    monkeypatch.setattr(r.worker, '_do', lost)
    assert r.worker.pass_once() == {'changed': True, 'did': 'lost_race'}
    assert r.rows() == []                       # contention starts nothing either


def test_stopping_between_the_plan_and_the_item_starts_no_verification(rig, monkeypatch):
    # worker.py:85-86 `if self.stopping(): break` — a worker asked to stop leaves
    # the item it had already been told is due untouched rather than starting a
    # row nobody will record; the scan is a continuation, so the work only waits
    r = rig()
    assert r.plan() == [('verify_task', r.tid, r.eid)]
    monkeypatch.setattr(r.worker, 'stopping', lambda: True)
    assert r.worker.pass_once() == {'changed': False}
    assert r.rows() == [] and r.missions.fired == [] and r.node.calls == []


# ── what is due: the boundary between retried, held and left alone ──

@pytest.mark.parametrize('state,errors_,holds,want', [
    ('EXECUTING', 1, False, 'retry'),        # worker.py:145-146 a retry is left
    ('EXECUTING', 2, False, 'hold'),         # worker.py:147-148 none: the user decides
    ('EXECUTING', 2, True, 'retry'),         # held once and resumed: run it again
    ('EXECUTING', 3, False, 'hold'),         # past the cap it stays a person's
    ('VERIFYING', 2, False, None),           # not executing: nobody to ask to unblock
    ('PAUSED', 1, False, None),              # worker.py:102-103 a settled mission waits
], ids=['retry-once', 'hold-twice', 'retry-resumed', 'hold-past', 'not-executing',
        'paused-settled'])
def test_an_error_row_is_retried_once_and_the_second_time_holds_the_mission(
        rig, state, errors_, holds, want):
    # V.ERROR_ATTEMPTS is a cap on errors, not on tries after a hold: a row the
    # user resumed runs again, and one that could not run twice becomes exactly
    # one request to block the mission, asked once
    r = rig(mission_state=state)
    vid = r.vrow(state='ERROR', errors=errors_, holds_mission=holds)
    assert r.plan() == ([(('retry' if want == 'retry' else 'hold'), vid)] if want else [])
    if want != 'hold':
        assert r.missions.fired == []
        return
    assert r.worker.pass_once() == {'changed': True, 'did': 'hold'}
    (mid, trigger, why), = r.missions.fired
    assert (mid, trigger) == (r.mid, 'block') and 'could not run' in why
    assert r.verification(vid).holds_mission is True
    assert r.mission().state == 'BLOCKED'           # the engine moved it, once
    assert r.plan() == []                           # held: never asked for again
    assert r.node.calls == []                       # holding runs nothing


@pytest.mark.parametrize('version', ['ordinary', 'confined'], ids=['unconfined-row',
                                                                   'confined-row'])
def test_a_guarded_error_row_is_held_once_and_only_a_confined_one_is_re_run(rig, version):
    # worker.py:141-144 (A6, T-041 C2): an ERROR row of a guarded mission the
    # confined sink did not stamp is held, never re-run — re-running it would run
    # its commands unconfined over a mission that may not be verified that way.
    # The same row stamped confined keeps its retries: the guard is the version
    # the sink gave it, not the isolation itself
    r = rig(isolated=True, process_seq=1, imported=IMP)
    vid = r.vrow(state='ERROR', errors=1, holds_mission=False, revision=IMP,
                 verifier_version=getattr(V, 'VERIFIER_VERSION' if version == 'ordinary'
                                          else 'CONFINED_VERIFIER'))
    if version == 'confined':
        assert r.plan() == [('retry', vid)]
        return
    assert r.plan() == [('hold', vid)]
    assert r.worker.pass_once() == {'changed': True, 'did': 'hold'}
    assert r.verification(vid).holds_mission is True
    assert 'withheld' in r.missions.fired[0][2]     # the sink's own reason
    assert r.plan() == [] and r.node.calls == []


@pytest.mark.parametrize('state', ['RUNNING', 'AWAITING_HUMAN'], ids=['running', 'awaiting'])
def test_a_row_still_running_or_waiting_for_a_human_starts_no_second_one(rig, state):
    # worker.py:150-151: an attempt in flight, or one a person has not answered,
    # is not a reason to start another — and nothing at all is observed for it
    r = rig()
    r.vrow(state=state, criteria=(UNKNOWN0,))
    assert r.plan() == []
    assert r.worker.pass_once() == {'changed': False}
    assert len(r.rows()) == 1 and r.one().state == state and r.node.calls == []


def test_only_the_criteria_no_passed_row_satisfied_are_asked_of_a_person(rig):
    # worker.py:152-153 with 306-311 (§13): the human row carries the criteria no
    # PASSED row of the execution satisfied — not all of them again, which would
    # let a person decide again what the automatic checks had already decided
    r = rig(acceptance=(AUTO, AUTO, HUMAN))
    r.vrow(state='PASSED', criteria=(OK0, dict(OK0, index=1, text='b')))
    assert r.plan() == [('verify_human', r.tid, r.eid)]
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_human'}
    v = r.rows()[-1]
    assert (v.verifier, v.state) == ('generic_human', 'AWAITING_HUMAN')
    assert [c['index'] for c in v.criteria] == [2]          # the one left over
    assert v.revision == r.rows()[0].revision               # what the code row observed
    assert r.missions.fired[0][1] == 'block'                # ... and the task now waits


@pytest.mark.parametrize('case,want', [
    ('none', True), ('one', True), ('two', False), ('three', False), ('ok', True),
    ('other', True), ('nosrc', True), ('old', True), ('reviewed', False)],
    ids=['never-tried', 'one-bad', 'two-bad', 'three-bad', 'ended-ok', 'another-mission',
         'no-source', 'before-plan', 'reviewed'])
def test_a_review_is_asked_of_the_model_twice_and_then_never_again(rig, case, want):
    # worker.py:168-175: a review call counts against the mission only when it is
    # this mission's (`source`), was made for this plan version (`created_at`) and
    # ended badly (`outcome`); at V.REVIEW_CALL_ATTEMPTS the mission stops being
    # offered a call of its own, and a plan already reviewed is never offered one
    bad = {'state': 'error'}
    r = rig(mission_state='REVIEWING', task_state='SUCCEEDED', calls=object())
    n = {'none': 0, 'one': 1, 'two': 2, 'three': 3, 'reviewed': 0}.get(case, 2)
    for _ in range(n):
        r.drow(outcome=({'state': 'ok'} if case == 'ok' else bad),
               source=(Ref('mission', ids.new_id('mission')) if case == 'other'
                       else None if case == 'nosrc' else Ref('mission', r.mid)),
               at='2020-01-01T00:00:00.000000Z' if case == 'old' else None)
    if case == 'reviewed':
        r.rrow()
    assert (('review', r.mid) in r.plan()) is want


@pytest.mark.parametrize('recorded,state,offered', [
    ('EXECUTING', 'EXECUTING', False), ('EXECUTING', 'BLOCKED', True),
    (None, 'EXECUTING', True)], ids=['waiting', 'moved-on', 'never-refused'])
def test_a_task_whose_mission_waits_on_a_too_long_worktree_is_offered_once(
        rig, recorded, state, offered):    # worker.py:114-118: a merge refused because its worktree path is too long is
    # tried once per mission rather than every pass — and the record is dropped,
    # and the merge offered again, the moment the mission moves on without it
    r = rig(mission_state=state, task_state='SUCCEEDED', integration_state='PENDING')
    r.vrow(state='PASSED', revision=REV)
    if recorded is not None:
        r.worker._too_long[r.mid] = recorded
    assert (('merge', r.tid) in r.plan()) is offered
    assert r.worker._too_long == ({r.mid: state} if recorded == state else {})


# ── confined: what refuses to run, and what a run is given ──

@pytest.mark.parametrize('staged', ['oserror', 'staged'], ids=['unstaged', 'staged'])
def test_a_check_the_staged_runtime_cannot_run_goes_to_a_person_not_to_the_machine(
        rig, monkeypatch, stage, staged):
    # worker.py:256-260: the Core-staged runtime is the only place a confined
    # check may come from, and a staging that fails (an OSError out of
    # `toolchain`) is answered by a person deciding — by no run, and no git read
    # either. The same rows with a staged runtime do run confined, so it is the
    # refusal that decided this and not something else about the seed
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    fake = _Confined()
    r = rig(isolated=True, process_seq=1, imported=IMP, tests=(stage[1] + ' --check',),
            node=_Node(run_confined_check=fake))
    if staged == 'oserror':
        def boom():
            raise OSError('the staged runtime is missing')
        r.worker.toolchain = boom
    else:
        r.worker.toolchain = lambda: [stage[0]]
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    v = r.one()
    if staged == 'oserror':
        assert (v.verifier, v.verifier_version, v.state) == (
            'generic_human', V.VERIFIER_VERSION, 'AWAITING_HUMAN')
        assert r.node.calls == []               # no git, no command, no confined run
    else:
        assert v.verifier_version == V.CONFINED_VERIFIER
        assert v.revision == IMP                # the import Core made, nothing else
        assert r.node.calls == ['run_confined_check']


def test_a_confined_run_is_given_the_workers_bound_and_only_recorded_workdirs(
        rig, monkeypatch, stage):
    # worker.py:277-283 (K1, T-054 C-1013 §4): the bound on a confined check is
    # the worker's own timeout, the project and revision are the import's, and
    # the tree is fenced by the recorded workdirs of the Core's executions — none
    # of it decided by a caller, and an execution with no workdir adds nothing
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    fake = _Confined()
    r = rig(isolated=True, process_seq=1, imported=IMP, timeout_s=7, workdir='ws-one',
            tests=(stage[1] + ' --check',), node=_Node(run_confined_check=fake))
    r.worker.toolchain = lambda: [stage[0]]
    r.erow(state='ENDED_ERROR', isolated=True, workdir=None, process_seq=3)
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    assert fake.inputs == [{'timeout': 7, 'project_id': r.proj, 'revision': IMP,
                            'workdirs': ['ws-one']}]
    assert fake.seen[0][1] == 0                         # the first attempt's number
    assert r.one().checks[0]['confinement'] == {'isolated': True, 'job': 'fake'}


def test_a_confined_check_that_never_finished_is_an_error_and_never_a_pass(rig, monkeypatch,
                                                                           stage):
    # worker.py:266-274 with `evidence.check_of`: a confined run that names no
    # exit code but an error (it timed out, quiescence stayed unknown) is
    # recorded as this row's error, its attempt counted, and the task left
    # waiting — a missing exit code is never read as a pass
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    fake = _Confined({'exit_code': None, 'error': 'timed out after 7s'})
    r = rig(isolated=True, process_seq=1, imported=IMP, timeout_s=7,
            tests=(stage[1] + ' --check',), node=_Node(run_confined_check=fake))
    r.worker.toolchain = lambda: [stage[0]]
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    v = r.one()
    assert (v.state, v.errors, v.verifier_version) == ('ERROR', 1, V.CONFINED_VERIFIER)
    assert v.checks[0]['result'] == 'error' and v.checks[0]['detail'] == 'timed out after 7s'
    assert r.task().state == 'VERIFYING' and r.missions.fired == []


@pytest.mark.parametrize('case', ['one', 'two', 'absent', 'outside'],
                         ids=['one', 'two', 'not-in-stage', 'named-by-path'])
def test_only_one_command_whose_program_the_stage_holds_may_run_confined(
        rig, tmp_path, monkeypatch, stage, case):
    # worker.py:243-262 (owner T-054 Q1 A): one command per attempt, and its
    # program found inside the staged runtime and nowhere else — a command PATH
    # could resolve but the stage does not hold is a person's, and so is a task
    # with more than one command, since an attempt is one principal. `named-by-path`
    # is the hazard the stage is the answer to: a program named with a directory
    # resolves (on Windows, from the current directory first) while the stage holds
    # something else entirely, and such a command is never confined
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    fake = _Confined()
    tests = {'one': (stage[1] + ' --check',),
             'two': (stage[1] + ' --check', stage[1] + ' --lint'),
             'absent': ('nothing-here --check',),
             'outside': (os.path.join(*stage) + ' --check',)}[case]
    r = rig(isolated=True, process_seq=1, imported=IMP, tests=tests,
            node=_Node(run_confined_check=fake))
    r.worker.toolchain = lambda: [str(tmp_path / 'elsewhere')] if case == 'outside' \
        else [stage[0]]
    route = r.worker._confined_route(r.mission(), r.task(), r.get(entities.Execution, r.eid))
    if case == 'one':
        (cmd, got, dirs, project_id, revision) = route
        assert cmd == ('test', tests[0]) and dirs == [stage[0]]
        assert os.path.normcase(got[0]) == os.path.normcase(os.path.join(*stage))
        assert (project_id, revision) == (r.proj, IMP)
    else:
        assert route is None
    assert fake.seen == []                              # no attempt was made either


# ── unconfined runs: the observed workspace and the bound on a command ──

@pytest.mark.parametrize('case', ['moved', 'untouched', 'dirty', 'scratch'],
                        ids=['moved', 'untouched', 'dirty', 'scratch'])
def test_a_workspace_that_moved_or_dirtied_while_the_checks_ran_is_no_verdict(rig, case):
    # worker.py:288-295 (§8.3): the head is read again once the commands ended, and
    # a workspace that moved (or gained a tracked change) while they ran adds an
    # `error` check, so the row can only be an error — evidence gathered from a
    # revision that is gone is not evidence about this one. The same rows left
    # alone pass, and a scratch file nobody tracks is no reason it should not
    seen = []
    tree = {'moved': {}, 'untouched': {}, 'dirty': {'tracked': True},
            'scratch': {'untracked': True}}[case]

    def run_check(ws, argv, **kw):
        seen.append(('run_check', argv, kw))
        return _result()

    def git_dirty(ws, **kw):
        seen.append(('git_dirty', ws, kw))
        # the node's own answer: tracked changes always, untracked ones only when
        # the caller did not ask for tracked files alone
        return bool(tree.get('tracked')
                    or (not kw.get('tracked_only') and tree.get('untracked')))
    r = rig(workdir='ws', timeout_s=7,
            node=_Node(git_head=_script(REV, REV if case != 'moved' else REV2),
                       git_dirty=git_dirty, branch_exists=_script(False),
                       run_check=run_check))
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    v = r.one()
    assert [k for (n, _a, k) in seen if n == 'run_check'][0]['timeout'] == 7
    assert [k for (n, _a, k) in seen if n == 'run_check'][0]['out_path'].endswith('0.log')
    assert v.checks[0]['result'] == 'pass'
    if case in ('untouched', 'scratch'):
        # the head held, so the dirtiness of the tree is what is asked next, of the
        # tracked files only: an untracked scratch file cannot fail a verification
        assert [k for (n, _a, k) in seen if n == 'git_dirty'] == [{'tracked_only': True}]
        assert [a for (n, a, _k) in seen if n == 'git_dirty'] == ['ws']
        assert v.state == 'PASSED' and r.task().state == 'SUCCEEDED'
    elif case == 'dirty':
        assert v.state == 'ERROR' and v.checks[-1]['result'] == 'error'
        assert 'moved during verification' in v.checks[-1]['detail']
        assert r.task().state == 'VERIFYING' and r.missions.fired == []
    else:
        # the head moved: the row is refused on that alone, and the tree of a
        # revision that is gone is not worth reading
        assert [n for (n, _a, _k) in seen if n == 'git_dirty'] == []
        assert v.state == 'ERROR' and v.checks[-1]['result'] == 'error'
        assert 'moved during verification' in v.checks[-1]['detail']
        assert REV2[:12] in v.checks[-1]['detail']
        assert r.task().state == 'VERIFYING' and r.missions.fired == []


@pytest.mark.parametrize('case', ['timeout', 'failing', 'unparsable'],
                        ids=['timed-out', 'nonzero-exit', 'unparsable-command'])
def test_a_command_that_never_finished_or_failed_is_never_a_pass(rig, case):
    # worker.py:285-295 hands each command's result to `evidence.check_of`
    # (evidence.py:104-107: an error is an error, exit 0 is a pass, anything else a
    # failure) and records exactly what it got: a command that timed out without an
    # exit code is an ERROR row and a non-zero one a FAILED row, and the task
    # succeeds neither way. Its output is stored even so — a log of a run that
    # never finished is what a person has to read. `unparsable-command` is the same
    # refusal one step earlier (evidence.py:112-116): a command line that cannot be
    # split is never handed to a process at all, and is an error rather than a pass
    def run_check(ws, argv, **kw):
        if case == 'timeout':
            return _result(exit_code=None, error='timed out after 7s', output=b'half a log')
        return _result(exit_code=1, output=b'nope')
    r = rig(workdir='ws', timeout_s=7,
            tests=("this is not 'splittable",) if case == 'unparsable' else ('tool --check',),
            node=_Node(git_head=_script(REV), git_dirty=_script(False),
                       branch_exists=_script(False), run_check=run_check))
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    v = r.one()
    assert v.checks[0]['name'].startswith('test: ')
    if case == 'unparsable':
        assert 'run_check' not in r.node.calls          # no process was ever started
        assert v.checks[0]['detail'] == 'the command line cannot be parsed'
    if case == 'failing':
        assert (v.state, v.checks[0]['result'], v.checks[0]['exit_code']) == (
            'FAILED', 'fail', 1)
        assert r.task().state in ('READY', 'FAILED')    # a failure was charged to it
    else:
        assert (v.state, v.errors, v.checks[0]['result']) == ('ERROR', 1, 'error')
        assert r.task().state == 'VERIFYING'
        if case == 'timeout':
            assert v.checks[0]['detail'] == 'timed out after 7s'
            assert v.checks[0]['exit_code'] is None     # no exit code is no verdict
            assert (v.checks[0]['output_bytes'], v.checks[0]['truncated']) == (10, False)
            assert v.checks[0]['output_sha256']         # the half-written log is stored


@pytest.mark.parametrize('isolated', [True, None], ids=['isolated', 'unknown'])
def test_an_isolated_execution_reaches_no_git_and_an_unknown_one_is_still_read(
        rig, isolated):
    # worker.py:201-207 (A5, owner G1): a workdir known to be isolated is never
    # read by Core's git at all, while a legacy unknown (None) is read as before
    # — and neither runs a command, and neither invents a revision for its row
    r = rig(isolated=isolated, imported=IMP, workdir='ws',
            node=_Node(git_head=_script(REV), git_dirty=_script(False),
                       branch_exists=_script(False), git_merge_base=_script(BASE)))
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_task'}
    v = r.one()
    assert (v.verifier, v.state) == ('generic_human', 'AWAITING_HUMAN')
    if isolated is True:
        assert r.node.calls == [] and v.revision is None
    else:
        assert r.node.calls[0] == 'git_head' and 'run_check' not in r.node.calls
        assert v.revision == REV                # read as before, from git itself


# ── merge-back ──

def test_a_merge_with_nothing_to_take_refuses_before_any_call_to_the_node(rig):
    # worker.py:369-372 (A5, D10): a task whose only PASSED row is of an isolated
    # execution has no mergeable revision at all, so the merge refuses before a
    # worktree is made, a branch read or anything recorded — the alternative is
    # merging a revision no verification ever observed
    r = rig(task_state='SUCCEEDED', integration_state='PENDING', isolated=True,
            process_seq=1, imported=IMP)
    r.vrow(state='PASSED', revision=REV)
    assert r.plan() == []                       # nothing mergeable: never offered
    with pytest.raises(V.Refused, match='no revision a merge may take'):
        r.worker._merge(r.tid)
    assert r.node.calls == []
    assert r.task().integration_state == 'PENDING'


def test_a_merge_a_restart_left_running_records_the_head_without_merging_again(rig):
    # worker.py:388-390 (§12.4): the branch already holds the revision — a merge
    # that died after the commit but before the record — so it is recorded as
    # merged with the head git reads, and no second merge is ever asked for; the
    # worktree P11 deferred is removed with it
    gone = []
    r = rig(task_state='SUCCEEDED', integration_state='MERGING', base=BASE, head=BASE,
            branch='task', workdir='ws',
            node=_Node(mission_worktree=_script('wt'), git_head=_script(REV),
                       git_is_ancestor=_script(True), remove_worktree=lambda *_a: gone.append(1)))
    r.vrow(state='PASSED', revision=REV)
    assert r.worker._merge(r.tid) is True
    assert r.task().integration_state == 'MERGED'
    assert r.task().merged_revision == REV and r.mission().integration_head == REV
    assert 'git_merge' not in r.node.calls and gone == [1]


@pytest.mark.parametrize('state', ['EXECUTING', 'VERIFYING'], ids=['executing', 'waiting'])
def test_a_worktree_git_refuses_for_its_length_blocks_the_mission_once(rig, state):
    # worker.py:378-387 (T-078): a path too long for a worktree is not retried in
    # a hot loop — the state the mission was left in is kept per mission, one
    # block is asked for and only while it was EXECUTING, and the merge is
    # offered again only when the mission moves on (tested above)
    def too_long(*_a):
        raise PathTooLong('the worktree path is over the limit')
    r = rig(mission_state=state, task_state='SUCCEEDED', integration_state='PENDING',
            base=BASE, node=_Node(mission_worktree=too_long))
    r.vrow(state='PASSED', revision=REV)
    assert r.worker._merge(r.tid) is True
    left = 'BLOCKED' if state == 'EXECUTING' else state
    assert r.worker._too_long == {r.mid: left}          # what the mission was left as
    assert [(m, t, 'over the limit' in why) for (m, t, why) in r.missions.fired] == (
        [(r.mid, 'block', True)] if state == 'EXECUTING' else [])
    assert r.task().integration_state == 'MERGING'      # begun before the worktree failed
    assert 'mission_worktree' in r.node.calls and 'git_merge' not in r.node.calls
    assert r.plan() == []                               # and now it waits, not loops


# ── the mission's own criteria ──

def test_a_mission_branch_that_moved_on_disk_is_noted_and_nothing_is_verified(rig):
    # worker.py:419-425 (§11): what Core recorded as the branch head no longer
    # matches the disk, so every verification of the old head is stale — the head
    # is noted and the pass ends there: no criterion started, no command run
    r = rig(mission_state='VERIFYING', base=BASE, head=REV, success=(AUTO,),
            task_state='SUCCEEDED', node=_Node(git_head=_script(REV2)))
    assert r.plan() == [('verify_mission', r.mid)]
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_mission'}
    assert r.mission().integration_head == REV2
    assert r.rows('mission') == [] and r.node.calls == ['git_head']


def test_only_the_last_record_of_a_mission_criterion_carries_the_head(rig):
    # worker.py:459-463 (§11): the head read after the commands ran goes to the
    # LAST record of the pass only — given to every one, it would move the branch
    # head between them, and each later record would then be refused for a
    # mission that had "moved" while its own checks ran
    r = rig(mission_state='VERIFYING', base=BASE, head=REV, task_state='SUCCEEDED',
            success=(AUTO, AUTO),
            node=_Node(git_head=_script(REV, REV2), run_check=_script(_result())))
    seen = r.spy()
    assert r.worker._verify_mission(r.mid) is True
    assert [kw['head'] for (name, kw) in seen if name == 'record'] == [None, REV2]
    assert [v.state for v in r.rows('mission')] == ['PASSED', 'PASSED']
    assert r.mission().integration_head == REV2         # noted once, by the last one


@pytest.mark.parametrize('errors_,verifier', [(1, 'code'), (2, 'generic_human')],
                         ids=['one-error', 'twice-failed'])
def test_a_mission_criterion_that_could_not_run_twice_becomes_a_persons(
        rig, errors_, verifier):
    # worker.py:438-444: an ERROR criterion of the current head is retried while
    # attempts are left, and once they are not a fresh row for a person
    # supersedes it — the row that failed is left as the record it is
    r = rig(mission_state='VERIFYING', success=(AUTO,), task_state='SUCCEEDED',
            node=_Node(git_head=_script(REV), run_check=_script(_result())))
    vid = r.vrow(subject='mission', criterion=0, state='ERROR', errors=errors_,
                 holds_mission=False, revision=None)
    assert r.plan() == [('verify_mission', r.mid)]
    assert r.worker.pass_once() == {'changed': True, 'did': 'verify_mission'}
    if errors_ == 1:
        assert r.verification(vid).state == 'PASSED'    # the same row ran again
        assert len(r.rows('mission')) == 1
        assert r.node.calls.count('run_check') == 1
    else:
        assert r.verification(vid).state == 'ERROR'     # it stays as it was
        v = r.rows('mission')[-1]
        assert (v.verifier, v.state, v.criterion) == (verifier, 'AWAITING_HUMAN', 0)
        assert r.node.calls.count('run_check') == 0     # nothing of it is re-run


@pytest.mark.parametrize('base', [None, BASE], ids=['no-branch', 'branch'])
def test_a_mission_row_names_the_head_only_where_its_branch_is_the_base(rig, base):
    # worker.py:338: a mission with no integration base has no branch to name, so
    # nothing is read after its commands and no head reaches its record; with one
    # the head of *its own* worktree is what the record is given
    r = rig(mission_state='VERIFYING', base=base, head=REV if base else None,
            success=(AUTO,), task_state='SUCCEEDED',
            node=_Node(git_head=_script(REV), run_check=_script(_result())))
    vid = r.vrow(subject='mission', criterion=0, state='ERROR', errors=1,
                 holds_mission=False, revision=REV if base else None,
                 workspace='wt' if base else r.root)
    seen = r.spy()
    assert r.worker._retry(vid) is True
    (name, kw), = [(n, k) for (n, k) in seen if n == 'record']
    assert kw['head'] == (REV if base else None)
    assert r.verification(vid).state == 'PASSED'


def test_a_confined_row_that_can_no_longer_run_confined_is_held_not_run(rig,
                                                                     monkeypatch):
    # worker.py:350-352: a confined row's next attempt needs the same contract it
    # started under; once the confined route is gone (the staged runtime is), the
    # row is held for a person. Re-running it would run its commands unconfined,
    # which the sink itself refuses — so a worker that tried would lose the row
    # to a lost race instead of holding the mission
    monkeypatch.setattr(V, 'CONFINED_VERIFICATION_ENABLED', True)
    r = rig(isolated=True, process_seq=1, imported=IMP)
    vid = r.vrow(state='ERROR', errors=1, holds_mission=False, revision=IMP,
                 verifier_version=V.CONFINED_VERIFIER)

    def boom():
        raise OSError('nothing staged')
    r.worker.toolchain = boom
    seen = r.spy()
    assert r.plan() == [('retry', vid)]
    assert r.worker.pass_once() == {'changed': True, 'did': 'retry'}
    assert [n for (n, _k) in seen] == ['hold']          # retried: never even asked
    assert (r.verification(vid).state, r.verification(vid).holds_mission) == (
        'ERROR', True)
    assert r.node.calls == [] and 'withheld' in r.missions.fired[0][2]


