"""T-712: the highest-risk uncovered branches of
`archeus/core/application/work.py` — the refusals that must write nothing, and
the one record of an end, a verification and a review that a mission is judged
on.

No test file targets this module. It is built only as scaffolding inside other
phases' rigs — `work.Work` is constructed by tests/v1/integration/test_skeleton.py,
test_automation.py, test_planning.py, test_policy.py and test_routing.py, by
tests/v1/unit/test_t150_gaps.py and by tests/v1/judge/client.py — and no test
calls `edit_plan` at all (the `edit_plan` of test_planning.py:545 is a raw
`tx.update`, used to prove a Plan row is frozen). The closest existing assertion
is test_planning.py:560, which only asks `dispatch_task` for
`pytest.raises(Exception)`. The rig below is therefore copied
from the unit tests of the sibling application modules — tests/v1/unit/
test_t150_gaps.py's Rig (the real writer on the test's own ARCHEUS_HOME, the
P9 `PolicyEngine` as the plan gate's Policy port, `ports.FixedCandidateRouter`
as the router seam) and the raw-row helpers of
tests/v1/unit/test_gaps_core_application_executions.py. Nothing here spawns a
process, opens a socket, reads the registry or touches the OS beyond SQLite
under `tmp_path` (tests/v1/conftest.py's autouse `archeus_home`); every mission
move goes through the real `commands.Missions`, so a BLOCKED or a REPLANNING
proven here is a real edge of P3's machine and answers the same on Windows and
Linux. No test depends on a path separator, a drive letter, a locale or the
clock, and none asserts on a live thread.

The ten branches this file exists for are quoted below with file:line in the
docstring of the test that now covers each, together with what its removal or
inversion would let through.
"""

import pytest

from archeus.core import ports
from archeus.core.application import commands, lifecycle, queries, work
from archeus.core.application.authorization import NotPermitted
from archeus.core.domain import entities
from archeus.core.domain.values import Ref
from archeus.core.policy.engine import PolicyEngine
from archeus.infra.db import Database, rows

AUTO = {'text': 'the result passes its automatic check', 'check': 'automatic'}
AUTO2 = {'text': 'the second result passes its automatic check', 'check': 'automatic'}
ACCEPT = [{'text': 'it is done', 'check': 'automatic'}]


def task(key, *classes, **kw):
    """A planner's task spec, in the shape `validate.problems` judges."""
    return dict({'key': key, 'title': 'Task %s' % key, 'kind': 'code_change',
                 'action_classes': list(classes), 'acceptance': ACCEPT}, **kw)


class Rig:
    """One Core on the test's ARCHEUS_HOME: the real writer, the real P3 mission
    machine over the P9 engine, and the router seam a dispatch asks. Every call
    is a writer command, one transaction each, exactly as Core runs them."""

    def __init__(self, db, policy=None, router=None):
        reg = lambda kind, scopes: Ref(kind, db.writer.execute(  # noqa: E731
            commands.register_principal, {'kind': kind, 'scopes': scopes})['id'])
        self.db = db
        self.system = reg('system', ('system',))
        self.user = reg('user_device', ('observe', 'control', 'approve', 'admin'))
        self.control = reg('user_device', ('observe', 'control'))
        self.brain = reg('brain', ('propose',))
        self.policy = policy or PolicyEngine()
        self.missions = commands.Missions(policy=self.policy)
        self.router = router or ports.FixedCandidateRouter('fake')
        self.work = work.Work(missions=self.missions, router=self.router)

    # ── the writer ──

    def do(self, command, who=None, key=None, **kw):
        return self.db.writer.execute(command, dict(kw, actor=who or self.system),
                                      idempotency_key=key)

    def move(self, cls, entity_id, trigger, fields=None):
        """*trigger* of *entity_id*'s machine, with the *fields* Core itself would
        write with it (for what no command of this module offers: a SKIPPED task)."""
        def run(tx, **_):
            return lifecycle.fire(tx, cls, entity_id, trigger, actor=self.system,
                                  reason='the world moved it', fields=fields)[0].entity
        return self.db.writer.execute(run, {})

    # ── reads ──

    def all(self, cls, **eq):
        with self.db.read() as r:
            return [x.entity for x in rows.where(r, cls, **eq)]

    def one(self, cls, **eq):
        got = self.all(cls, **eq)
        assert len(got) == 1, got
        return got[0]

    def row(self, cls, entity_id):
        with self.db.read() as r:
            return rows.get(r, cls, entity_id)

    def m(self, mid):
        return self.row(entities.Mission, mid).entity

    def plans(self, mid):
        return sorted(self.all(entities.Plan, mission_id=mid), key=lambda p: p.plan_version)

    def events(self, type_):
        with self.db.read() as r:
            return [e for e in queries.events(r) if e['type'] == type_]

    def head(self):
        with self.db.read() as r:
            return r.execute('SELECT MAX(seq) FROM events').fetchone()[0]

    # ── walking a mission, one command each ──

    def mission(self, title='M', **kw):
        mid = self.do(commands.create_mission, who=self.user, title=title, objective='o',
                      success_criteria=kw.pop('success_criteria', [AUTO]), **kw)['id']
        for trig in ('start', 'understood'):
            self.do(self.missions.fire, mission_id=mid, trigger=trig, reason='test')
        self.do(self.missions.context_ready, mission_id=mid)
        return mid

    def propose(self, mid, *tasks_, who=None, key=None, plan=None, **kw):
        """`propose_plan` as the planner's caller sends it; *plan* replaces the
        whole plan dict when a test needs the shape the validator refuses."""
        body = plan if plan is not None else {
            'summary': 'test plan', 'tasks': list(tasks_), 'success_criteria': [AUTO]}
        return self.do(self.work.propose_plan, who=who, key=key, mission_id=mid,
                       context_package_id=self.m(mid).context_package_id,
                       plan=body, **kw)

    def edit(self, mid, *tasks_, who=None, key=None, expected_version=None, plan_id=None):
        """The person's edit of the version awaiting them (P19 S2)."""
        pid = self.plans(mid)[-1].id if plan_id is None else plan_id
        return self.do(self.work.edit_plan, who=who or self.user, key=key,
                       plan_id=pid, tasks=list(tasks_), expected_version=expected_version)

    def executing(self, mid):
        """APPROVED -> EXECUTING with every ready task READY (the engine's two
        steps, taken as commands)."""
        self.do(self.missions.fire, mission_id=mid, trigger='dispatch', reason='go')
        return self.do(self.work.ready_tasks, mission_id=mid)

    def task(self, mid, key='t1'):
        return self.one(entities.Task, mission_id=mid, key=key)

    def spawn_and_end(self, mid, key='t1', ok=True, exit_code=None):
        """Dispatch the READY task *key*, report its process and its end."""
        out = self.do(self.work.dispatch_task, task_id=self.task(mid, key).id)
        if out['execution_id'] is None:
            return out
        self.do(self.work.record_spawn, execution_id=out['execution_id'], pid=4242,
                create_time=1.0)
        self.do(self.work.record_exit, execution_id=out['execution_id'],
                exit_reason='ok' if ok else 'error',
                exit_code=(0 if ok else 1) if exit_code is None else exit_code)
        return out

    def replanning(self, mid, key='t1'):
        """The mission in REPLANNING: the task failed with everything charged,
        and the mission's own `task_failed_retryable` took it there."""
        self.executing(mid)
        self.spawn_and_end(mid, key, ok=False)
        assert self.task(mid, key).state == 'FAILED', self.task(mid, key)
        self.do(self.missions.advance, mission_id=mid)
        assert self.m(mid).state == 'REPLANNING', self.m(mid)
        return mid

    def verifying_task(self, mid, key='t1'):
        """The task in VERIFYING: dispatched, its process ended clean."""
        self.executing(mid)
        self.spawn_and_end(mid, key, ok=True)
        assert self.task(mid, key).state == 'VERIFYING', self.task(mid, key)
        return mid

    def verifying_mission(self, mid, key='t1'):
        """The mission in VERIFYING: its one task SUCCEEDED and `advance` took
        `all_tasks_done`."""
        self.verifying_task(mid, key)
        self.do(self.work.record_task_verification, task_id=self.task(mid, key).id,
                verdict='PASSED', verifier='code')
        self.do(self.missions.advance, mission_id=mid)
        assert self.m(mid).state == 'VERIFYING', self.m(mid)
        return mid

    def reviewing(self, mid, key='t1'):
        """The mission in REVIEWING: every automatic criterion passed."""
        self.verifying_mission(mid, key)
        self.do(self.work.verify_mission, mission_id=mid, verdicts=[
            {'criterion': i, 'verdict': 'PASSED', 'verifier': 'code'}
            for i in range(len(self.m(mid).success_criteria))])
        assert self.m(mid).state == 'REVIEWING', self.m(mid)
        return mid

@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


@pytest.fixture
def r(db):
    return Rig(db)


# ── proposing a plan: what is refused before a row exists ─────────────────

def test_a_plan_never_states_its_own_cost_band(r):
    """work.py:165-166 `if 'estimated_cost' in plan: raise ValueError` (D9). With
    it gone, work.py:182 would still compute Core's band but the caller's claim
    would win the `to_dict` round trip, and the plan gate's cost-ceiling guard
    (commands.py:243) would be judged on what the planner wrote about itself."""
    mid = r.mission()
    with pytest.raises(ValueError, match='cost band'):
        r.propose(mid, plan={'summary': 's', 'tasks': [task('t1', 'read')],
                             'success_criteria': [AUTO], 'estimated_cost': 'low'})
    assert r.all(entities.Plan) == [] and r.all(entities.Task) == []
    assert r.m(mid).state == 'REASONING'


@pytest.mark.parametrize('bad', ['no-tasks', 'cycle'], ids=['none', 'cycle'])
def test_a_plan_the_validator_refuses_leaves_nothing_behind(r, bad):
    """work.py:169-171 `found = validate.problems(...)` / `if found: raise
    ValueError`. The P8 rule is that a plan Core cannot validate is refused with
    nothing written; past this gate work.py:176-199 would insert the version and
    its tasks and the `ready` guard would then refuse a DRAFT row already in the
    database."""
    mid = r.mission()
    bad_plan = {'no-tasks': [], 'cycle': [task('t1', 'read', depends_on=['t2']),
                                          task('t2', 'read', depends_on=['t1'])]}[bad]
    with pytest.raises(ValueError, match='not valid'):
        r.propose(mid, plan={'summary': 's', 'tasks': bad_plan, 'success_criteria': [AUTO]})
    assert r.all(entities.Plan) == [] and r.all(entities.Task) == []
    assert r.m(mid).state == 'REASONING'
    assert r.events('plan.created') == []


def test_a_denied_replan_writes_nothing_and_keeps_the_plan_in_force(r):
    """work.py:173 `self._refuse_denied(...)` (work.py:121-131) sits between the
    validator and the first `tx.insert`, and work.py:210-216 supersedes the old
    version only after that. Move the DENY check later and a refused replan
    would still retire the approved plan and drop the approvals P9 D14 superseded
    with it, leaving the mission with no plan in force at all."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read', max_attempts=1))
    r.replanning(mid)
    (v1,) = r.plans(mid)
    assert v1.state == 'APPROVED'
    head = r.head()
    with pytest.raises(work.PolicyDenied) as got:
        r.propose(mid, task('t2', 'destructive'))
    assert got.value.task_key == 't2' and got.value.specs
    assert [(p.id, p.state, p.plan_version) for p in r.plans(mid)] == [(v1.id, 'APPROVED', 1)]
    assert r.m(mid).state == 'REPLANNING' and r.all(entities.Approval) == []
    assert r.head() == head                                    # nothing committed
    # and the same call with a plan the policy allows does record the version,
    # so the assertion above is not the assertion that a replan never works
    out = r.propose(mid, task('t2', 'read'))
    assert out['plan_version'] == 2
    assert [(p.state, p.plan_version) for p in r.plans(mid)] == [('SUPERSEDED', 1),
                                                                 ('APPROVED', 2)]


@pytest.mark.parametrize('left', [0, 1], ids=['no-replans-left', 'one-replan-left'])
def test_the_replan_budget_is_judged_before_anything_is_recorded(r, left):
    """work.py:161-164 (`if m.entity.state == 'REPLANNING': spent = ...; if spent
    is not None: return`) and work.py:288-296 (`replan_budget_spent`: the one
    `replan_budget_exhausted` fire, `None` on GuardFailed). Delete the early
    return and an over-budget mission gets a recorded, approved version and its
    `plan_auto_approved` edge — the budget guard (guards.py:220-225, judged on
    the version it replaces) is `max_replans`'s only enforcement."""
    mid = r.mission(max_replans=left)
    r.propose(mid, task('t1', 'read', max_attempts=1))
    r.replanning(mid)
    out = r.propose(mid, task('t2', 'read'))
    if left == 0:
        assert out['plan_id'] is None and out['plan_version'] is None
        assert out['mission']['state'] == 'BLOCKED'
        assert [(p.plan_version, p.state) for p in r.plans(mid)] == [(1, 'APPROVED')]
        assert r.m(mid).held_from == 'REPLANNING'
        assert [e['payload']['trigger'] for e in r.events('mission.state_changed')][-1] == \
            'replan_budget_exhausted'
    else:
        assert out['plan_version'] == 2 and out['mission']['state'] == 'APPROVED'
        assert [(p.plan_version, p.state) for p in r.plans(mid)] == [(1, 'SUPERSEDED'),
                                                                     (2, 'APPROVED')]


# ── the person's edit of the plan awaiting them: who may, what, and nothing ──

@pytest.mark.parametrize('who', ['control', 'system', 'brain'],
                         ids=['control-scope', 'system', 'brain'])
def test_only_a_device_holding_the_approve_scope_may_edit_the_plan(r, who):
    """work.py:243 `who = authorization._principal(tx, actor, 'approve')` — the
    FIRST statement of `edit_plan` (authorization.py:574-575 raises). Drop it, or
    widen the scope it asks for, and a control-only client, a system pass or the
    brain could rewrite the plan in force and have Core propose it as the next
    version with a person's authorship."""
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    assert r.m(mid).state == 'APPROVAL_REQUIRED'
    before, head = r.plans(mid), r.head()
    with pytest.raises(NotPermitted):
        r.edit(mid, task('t1', 'deploy'), who=getattr(r, who))
    assert r.m(mid).state == 'APPROVAL_REQUIRED'
    assert [p.id for p in r.plans(mid)] == [p.id for p in before]
    assert r.plans(mid)[-1].state == 'PROPOSED'
    assert r.head() == head


def test_a_stale_expected_version_is_refused_before_anything_is_read(r):
    """work.py:245-246 `if expected_version is not None and expected_version !=
    row.version: raise VersionConflict`. Without it two clients editing the same
    awaiting-approval plan would both be proposed, the second silently replacing
    the first (the lost update the version check exists for)."""
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    pid = r.plans(mid)[-1].id
    stale = r.row(entities.Plan, pid).version + 3
    with pytest.raises(lifecycle.VersionConflict):
        r.edit(mid, task('t1', 'deploy'), expected_version=stale)
    assert len(r.plans(mid)) == 1
    assert r.m(mid).state == 'APPROVAL_REQUIRED'
    assert r.events('plan.created') and not [e for e in r.events('plan.state_changed')
                                             if e['payload']['to'] == 'SUPERSEDED']


def test_a_mission_that_is_not_awaiting_the_person_is_never_edited_back(r):
    """work.py:257 `_require('mission', m, ('APPROVAL_REQUIRED',), 'edit_plan')`.
    Inverted or widened, an edit would answer a mission that has already moved on
    — here EXECUTING with its plan approved — by sending it back to PLANNING and
    recording a version no one asked for."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read'))
    assert r.m(mid).state == 'APPROVED'
    r.executing(mid)
    assert r.m(mid).state == 'EXECUTING'
    with pytest.raises(lifecycle.IllegalTrigger, match='edit_plan'):
        r.edit(mid, task('t1', 'read'))
    assert r.m(mid).state == 'EXECUTING'
    assert len(r.plans(mid)) == 1


def test_only_the_plan_in_force_is_edited(r):
    """work.py:258-260 `if prev.state != 'PROPOSED' or active_plan(...) != prev:
    raise IllegalTrigger('only the plan in force is edited')`. With it removed,
    editing the SUPERSEDED version would propose a third version descended from
    the retired one, and P9 D14's supersession of its approvals would never run."""
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    r.do(r.missions.request_changes, mission_id=mid, reason='try again')
    r.propose(mid, task('t1', 'deploy'), task('t2', 'deploy'))
    assert [p.state for p in r.plans(mid)] == ['SUPERSEDED', 'PROPOSED']
    assert r.m(mid).state == 'APPROVAL_REQUIRED'
    with pytest.raises(lifecycle.IllegalTrigger, match='only the plan in force'):
        r.edit(mid, task('t1', 'deploy'), plan_id=r.plans(mid)[0].id)
    assert [p.state for p in r.plans(mid)] == ['SUPERSEDED', 'PROPOSED']
    assert r.m(mid).state == 'APPROVAL_REQUIRED'


@pytest.mark.parametrize('bad', ['no-tasks', 'unknown-kind', 'dangling-dep',
                                'same-task', 'dangling-input'],
                         ids=['none', 'kind', 'dep', 'dupe', 'input'])
def test_an_invalid_edit_never_sends_the_mission_back(r, bad):
    """work.py:266-267 (the `inputs` `from_task` labels no earlier check knows,
    appended to `found`) and work.py:271-274 (`if found: raise GuardFailed`, the
    answer the version's own `ready` guard would have given). Both sit BEFORE
    `self.missions.request_changes` (work.py:280): were the validator dropped,
    or the order swapped, a person's typo would leave the mission in PLANNING
    waiting for a plan that was never recorded."""
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    before = r.plans(mid)[-1]
    bad_tasks = {
        'no-tasks': [],
        'unknown-kind': [task('t1', 'deploy', kind='not_a_kind')],
        'dangling-dep': [task('t1', 'deploy'), task('t2', 'deploy', depends_on=['ghost'])],
        'same-task': [task('t1', 'deploy'), task('t2', 'deploy', title='Task t1')],
        'dangling-input': [task('t1', 'deploy', inputs=({'from_task': 'ghost',
                                                         'what': 'its result'},))],
    }[bad]
    with pytest.raises(lifecycle.GuardFailed):
        r.edit(mid, *bad_tasks)
    assert r.m(mid).state == 'APPROVAL_REQUIRED'
    after = r.plans(mid)
    assert [p.id for p in after] == [before.id]
    assert after[-1].state == 'PROPOSED'


def test_a_valid_edit_is_proposed_as_the_next_version_by_the_person(r):
    """The control for the five refusals above: with the checks in place a good
    edit does reach work.py:280-285 (`request_changes`, then `propose_plan` with
    `edited_by=who.id`) — so their `nothing changed` assertions are not the
    assertion that `edit_plan` never works."""
    mid = r.mission()
    r.propose(mid, task('t1', 'deploy'))
    out = r.edit(mid, task('t1', 'deploy'), task('t2', 'deploy', depends_on=['t1']))
    assert out['changed'] is True and out['plan_version'] == 2
    old, new = r.plans(mid)
    assert (old.state, new.state, new.supersedes_plan_id, new.edited_by) == (
        'SUPERSEDED', 'PROPOSED', old.id, r.user.id)
    assert r.m(mid).state == 'APPROVAL_REQUIRED'          # the gate asks again
    assert {t.key for t in r.all(entities.Task, plan_id=new.id)} == {'t1', 't2'}


# ── dispatch and the two reports of an execution ─────────────────────────

def test_the_same_dispatch_replayed_starts_one_execution(r):
    """`new_execution` (work.py:78-103) is the one place an Execution is born and
    `dispatch_task` (work.py:318-371) runs it once per call with no idempotency of
    its own: what makes a redelivered dispatch safe is the writer's key, and this
    is the test that the command Core exposes for it stays safe — the second call
    replays the first result instead of taking the task `READY -> ROUTING -> RUNNING`
    again and recording a second Execution for the same work."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read'))
    r.executing(mid)
    t = r.task(mid)
    out = r.do(r.work.dispatch_task, task_id=t.id, key='dispatch-t1')
    moved = r.row(entities.Task, t.id).version
    again = r.do(r.work.dispatch_task, task_id=t.id, key='dispatch-t1')
    assert again == out and out['execution_id'] is not None
    assert len(r.all(entities.Execution, task_id=t.id)) == 1
    assert len(r.events('execution.intent')) == 1
    assert r.row(entities.Task, t.id).version == moved          # one move, not two


def test_a_task_of_a_superseded_plan_is_never_dispatched(r):
    """work.py:332-334 `if t.plan_id != plan.id: raise IllegalTrigger('the task
    belongs to a superseded plan')`, the check `dispatch_task` does after its
    mission-state check (work.py:328-330) and *before* `check_dispatch`
    (work.py:335). Dropped, a READY task the replan abandoned would be routed and
    run under the approvals and the digest of the plan that is no longer in
    force; `Task` has no state for "abandoned by a replan", so this is the only
    thing that refuses it."""
    mid = r.mission(max_replans=1)
    r.propose(mid, task('t1', 'read', max_attempts=1), task('t2', 'read'))
    r.executing(mid)
    abandoned = r.task(mid, 't2')
    assert abandoned.state == 'READY'
    r.spawn_and_end(mid, 't1', ok=False)                 # t1 FAILED, t2 untouched
    r.do(r.missions.advance, mission_id=mid)
    assert (r.task(mid, 't2').state, r.m(mid).state) == ('READY', 'REPLANNING')
    r.propose(mid, task('t1', 'read'))                   # v2 supersedes v1
    assert r.m(mid).state == 'APPROVED'
    r.do(r.missions.fire, mission_id=mid, trigger='dispatch', reason='the next version')
    assert r.m(mid).state == 'EXECUTING'
    with pytest.raises(lifecycle.IllegalTrigger, match='superseded plan'):
        r.do(r.work.dispatch_task, task_id=abandoned.id)
    assert r.all(entities.Execution, task_id=abandoned.id) == []
    assert r.row(entities.Task, abandoned.id).entity.state == 'READY'


@pytest.mark.parametrize('code', [0, None], ids=['code0', 'codeNone'])
def test_an_error_end_is_never_recorded_as_a_clean_exit(r, code):
    """work.py:400 `code = 0 if exit_reason == 'ok' else (exit_code if exit_code
    not in (0, None) else 1)`. Drop the `not in (0, None)` and a process that
    reported `error` with no code would be recorded exit 0, which
    `executions.record_end` reads as `clean` (executions.py:524): ENDED_OK, and
    its `execution_succeeded` (executions.py:676-678) would send the task to
    VERIFYING on work that failed."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read'))
    r.executing(mid)
    eid = r.do(r.work.dispatch_task, task_id=r.task(mid).id)['execution_id']
    r.do(r.work.record_spawn, execution_id=eid, pid=4242, create_time=1.0)
    r.do(r.work.record_exit, execution_id=eid, exit_reason='error', exit_code=code)
    e = r.row(entities.Execution, eid).entity
    assert (e.state, e.exit_reason, e.exit_code) == ('ENDED_ERROR', 'error', 1)
    assert e.charged is True
    assert r.task(mid).state == 'READY'                    # the retry, never VERIFYING
    assert r.all(entities.Verification) == []


@pytest.mark.parametrize('bad', ['crashed', 'OK', ''], ids=['invented', 'uppercase', 'empty'])
def test_an_end_that_is_neither_ok_nor_error_is_refused(r, bad):
    """work.py:398-399 `if exit_reason not in ('ok', 'error'): raise ValueError`.
    Anything past it reaches `executions.record_end` with an exit code chosen by
    `exit_reason == 'ok'`, so an invented reason silently means a FAILED end."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read'))
    r.executing(mid)
    eid = r.do(r.work.dispatch_task, task_id=r.task(mid).id)['execution_id']
    r.do(r.work.record_spawn, execution_id=eid, pid=4242, create_time=1.0)
    with pytest.raises(ValueError, match='exit_reason is ok or error'):
        r.do(r.work.record_exit, execution_id=eid, exit_reason=bad, exit_code=1)
    e = r.row(entities.Execution, eid).entity
    assert (e.state, e.exit_code, e.exit_reason, e.pid) == ('STARTING', None, None, 4242)
    assert r.task(mid).state == 'RUNNING'


def test_the_same_end_reported_twice_changes_nothing(r):
    """The replay rule of work.py:392-403: `record_exit` is `executions.record_end`,
    whose own guard is "a second report of the same end is an invalid transition:
    nothing changes" (executions.py:572-574). Accepted, the task would take
    `execution_succeeded` a second time (executions.py:676-678) and could be
    verified twice under one execution."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read'))
    r.executing(mid)
    eid = r.do(r.work.dispatch_task, task_id=r.task(mid).id)['execution_id']
    r.do(r.work.record_spawn, execution_id=eid, pid=4242, create_time=1.0)
    first = r.do(r.work.record_exit, execution_id=eid, exit_reason='ok', exit_code=0)
    assert first['state'] == 'ENDED_OK' and r.task(mid).state == 'VERIFYING'
    ended = r.row(entities.Execution, eid).entity.ended_at
    with pytest.raises(lifecycle.InvalidTransition):
        r.do(r.work.record_exit, execution_id=eid, exit_reason='ok', exit_code=0)
    e = r.row(entities.Execution, eid).entity
    assert (e.state, e.exit_code, e.ended_at) == ('ENDED_OK', 0, ended)
    assert r.task(mid).state == 'VERIFYING'
    assert r.all(entities.Verification) == []


def test_a_spawn_reported_twice_keeps_one_process_record(r):
    """The spawn half of the pair this module hands P3.5: work.py:386-390 hands
    the report to `executions.record_process` (executions.py:385-391), which is
    the check that a process may only *start* an execution. A second `record_spawn`
    for the same execution is therefore refused: one `execution.started`, one pid,
    one process number — which is what `record_process` later matches a live pid
    against."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read'))
    r.executing(mid)
    eid = r.do(r.work.dispatch_task, task_id=r.task(mid).id)['execution_id']
    out = r.do(r.work.record_spawn, execution_id=eid, pid=4242, create_time=1.0)
    assert (out['state'], r.row(entities.Execution, eid).entity.process_seq) == ('STARTING', 1)
    with pytest.raises(lifecycle.IllegalTrigger):
        r.do(r.work.record_spawn, execution_id=eid, pid=9999, create_time=2.0)
    e = r.row(entities.Execution, eid).entity
    assert (e.state, e.process_seq, e.pid, e.create_time) == ('STARTING', 1, 4242, 1.0)
    assert len(r.events('execution.started')) == 1


@pytest.mark.parametrize('finished', ['failed', 'skipped'], ids=['failed', 'skipped'])
def test_a_task_starts_only_when_its_dependencies_have_actually_finished(r, finished):
    """work.py:53 `DONE = ('SUCCEEDED', 'SKIPPED')` with its use at work.py:306-307
    (`set(r.entity.depends_on) <= done`). Widen DONE and a task blocked behind a
    FAILED one would be dispatched on work that never happened; narrow it and a
    dependency someone skipped would hold its dependants forever."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read', max_attempts=1), task('t2', 'read', depends_on=['t1']))
    r.do(r.missions.fire, mission_id=mid, trigger='dispatch', reason='go')
    assert r.m(mid).state == 'EXECUTING'
    assert r.task(mid, 't2').state == 'PENDING'
    if finished == 'failed':
        r.do(r.work.ready_tasks, mission_id=mid)                 # only t1 becomes READY
        assert r.task(mid, 't2').state == 'PENDING'
        eid = r.do(r.work.dispatch_task, task_id=r.task(mid, 't1').id)['execution_id']
        r.do(r.work.record_spawn, execution_id=eid, pid=1, create_time=1.0)
        r.do(r.work.record_exit, execution_id=eid, exit_reason='error', exit_code=3)
        assert r.task(mid, 't1').state == 'FAILED'
    else:
        r.move(entities.Task, r.task(mid, 't1').id, 'skip')      # PENDING -> SKIPPED
        assert r.task(mid, 't1').state == 'SKIPPED'
    out = r.do(r.work.ready_tasks, mission_id=mid)
    assert out['ready'] == ([] if finished == 'failed' else [r.task(mid, 't2').id])
    assert r.task(mid, 't2').state == ('PENDING' if finished == 'failed' else 'READY')


# ── verification and review: the records a mission is judged on ───────────

@pytest.mark.parametrize('bad', ['MAYBE', 'passed', ''], ids=['invented', 'lowercase', 'empty'])
def test_a_task_verdict_Core_does_not_know_is_refused_before_the_row(r, bad):
    """work.py:408-409 (`_verify`: `if verdict not in _VERDICT: raise ValueError`)
    sits before the `tx.insert` of work.py:410 and before the edge lookup
    `_VERDICT[verdict]` of work.py:415. Drop it and a caller's typo is no longer a
    refusal: `_VERDICT['MAYBE']` raises KeyError from the middle of the
    transaction — and work.py:55 `_VERDICT` is the only thing mapping a verdict to
    the `all_checks_pass` / `a_check_fails` edges, so whatever did get written
    would move a task to SUCCEEDED or to a retry on a word no reader knows."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read'))
    r.verifying_task(mid)
    with pytest.raises(ValueError, match='a verdict is PASSED or FAILED'):
        r.do(r.work.record_task_verification, task_id=r.task(mid).id, verdict=bad,
             verifier='code')
    assert r.all(entities.Verification) == []
    assert r.task(mid).state == 'VERIFYING'
    assert r.events('verification.created') == []


@pytest.mark.parametrize('case', ['only-one', 'twice', 'unknown'],
                         ids=['one-criterion-judged', 'criterion-judged-twice',
                              'unknown-criterion'])
def test_the_mission_is_verified_only_over_every_automatic_criterion(r, case):
    """work.py:447-449 `if sorted(v['criterion'] for v in verdicts) !=
    sorted(auto): raise ValueError`, before the rows of work.py:451-454 and before
    the `advance` of work.py:456. Relaxed, the extra verdict below commits a
    Verification of a criterion this mission does not have and the `advance` still
    takes `verified` — guards.py:196-207 reads the *mission's* criteria, not the
    rows handed to it — and the incomplete one leaves the mission in VERIFYING with
    a half-set of rows no one asked for. Either way the caller asked for a refusal
    and got a written mission."""
    mid = r.mission(success_criteria=[AUTO, AUTO2])
    r.propose(mid, task('t1', 'read'))
    r.verifying_mission(mid)
    verdicts = {'only-one': [{'criterion': 0, 'verdict': 'PASSED',
                             'verifier': 'code'}],
                'twice': [{'criterion': 0, 'verdict': 'PASSED',
                           'verifier': 'code'},
                          {'criterion': 0, 'verdict': 'PASSED',
                           'verifier': 'code'}],
                'unknown': [{'criterion': 0, 'verdict': 'PASSED', 'verifier': 'code'},
                            {'criterion': 1, 'verdict': 'PASSED', 'verifier': 'code'},
                            {'criterion': 2, 'verdict': 'PASSED', 'verifier': 'code'}],
                }[case]
    with pytest.raises(ValueError, match='each automatic criterion once'):
        r.do(r.work.verify_mission, mission_id=mid, verdicts=verdicts)
    before = len(r.all(entities.Verification))          # the task's own, from the walk here
    assert before == 1 and r.m(mid).state == 'VERIFYING'
    out = r.do(r.work.verify_mission, mission_id=mid, verdicts=[
        {'criterion': i, 'verdict': 'PASSED', 'verifier': 'code'} for i in (0, 1)])
    assert len(out['verifications']) == 2 and out['mission']['state'] == 'REVIEWING'
    assert sorted(v.criterion for v in r.all(entities.Verification)
                  if v.subject.kind == 'mission') == [0, 1]


@pytest.mark.parametrize('bad', ['maybe', 'ACCEPT', ''], ids=['invented', 'uppercase', 'empty'])
def test_a_review_verdict_Core_does_not_know_is_refused_before_the_row(r, bad):
    """work.py:466-467 `if verdict not in _REVIEW: raise ValueError` (with
    work.py:56-57 `_REVIEW` naming the three edges). The check sits before
    `tx.insert(r)` at work.py:471: after it, a Review row no reader knows would
    become the latest review of the plan in force, which is exactly what
    `guards.accepted` (guards.py:256-260) reads to let a mission COMPLETED."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read'))
    r.reviewing(mid)
    head = r.head()
    with pytest.raises(ValueError, match='a review verdict is'):
        r.do(r.work.record_review, mission_id=mid, verdict=bad, reviewer='me')
    assert r.all(entities.Review) == []
    assert r.m(mid).state == 'REVIEWING'
    assert r.head() == head


def test_a_rejected_review_completes_nothing_and_moves_nothing(r):
    """work.py:478-484: `out` stays None unless the verdict is `accept` or
    `changes_requested`, so a `reject` records the review and leaves the mission in
    REVIEWING for a human (the mission machine has no edge for it). Give `reject`
    a mission move anyway and a rejected mission reports itself COMPLETED on the
    strength of the review that refused it — so the `accept` that follows has to be
    the one that completes it, refused until then by `guards.accepted`
    (guards.py:256-260)."""
    mid = r.mission()
    r.propose(mid, task('t1', 'read'))
    r.reviewing(mid)
    out = r.do(r.work.record_review, mission_id=mid, verdict='reject', reviewer='me')
    assert out['verdict'] == 'reject' and out['mission'] is None
    assert r.m(mid).state == 'REVIEWING'
    (review,) = r.all(entities.Review, mission_id=mid)
    assert (review.state, review.plan_id) == ('REJECTED', r.plans(mid)[-1].id)
    # the mission cannot be accepted over it: `guards.accepted` reads the latest
    # review of the plan in force, and this one refused the mission
    with pytest.raises(lifecycle.GuardFailed, match='accepted'):
        r.do(r.missions.accept, mission_id=mid)
    # what completes it is a human recording their own accepting review (P3)
    assert r.do(r.work.record_review, mission_id=mid, verdict='accept',
                reviewer='you')['mission']['state'] == 'COMPLETED'
