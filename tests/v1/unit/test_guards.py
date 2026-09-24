"""P3: the guards and the trigger resolution, as pure functions (state-machines §0, §2, §5)."""

import ast
import dataclasses
import os

import pytest

from archeus.core.application import lifecycle
from archeus.core.domain import entities as E
from archeus.core.domain import guards, ids, states
from archeus.core.domain.guards import CriterionFact, MissionFacts, TaskFact

GUARDS_PY = guards.__file__


def _mission(**kw):
    return E.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                     title='t', objective='o', **kw)


def _task(state='SUCCEEDED', kind='code_change', **kw):
    return TaskFact(key=kw.pop('key', 't1'), kind=kind, state=state, **kw)


# ── the registry is the table ──

def test_every_guarded_edge_has_exactly_one_guard_and_nothing_else_does():
    guarded = {(m, g) for m, _f, _t, _trig, g in states.TABLE if g}
    assert set(guards.GUARDS) == guarded


def test_guards_are_pure_they_import_nothing_that_does_io():
    tree = ast.parse(open(GUARDS_PY, encoding='utf-8').read())
    imported = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
                for a in n.names}
    imported |= {n.module.split('.')[0] for n in ast.walk(tree)
                 if isinstance(n, ast.ImportFrom) and n.module and n.level == 0}
    assert imported <= {'dataclasses'}, imported
    relative = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level}
    assert relative <= set(), relative              # not even the rest of the domain


def test_a_guard_gives_the_same_answer_for_the_same_inputs():
    m = _mission()
    f = MissionFacts(plan_version=1, tasks=(_task(),), criteria=(CriterionFact('automatic',
                                                                               'PASSED'),))
    for (machine, _trig), fn in guards.GUARDS.items():
        if machine != 'mission':
            continue
        assert fn(m, f) == fn(m, f) == fn(m, dataclasses.replace(f))


def test_evaluate_binds_the_result_to_the_row_and_version():
    m = _mission()
    r = guards.evaluate('mission', 'all_tasks_done', m,
                        MissionFacts(plan_version=1, tasks=(_task(),)), version=7)
    assert (r.guard, r.passed, r.entity_id, r.version) == ('all_tasks_done', True, m.id, 7)
    with pytest.raises(LookupError):
        guards.evaluate('mission', 'start', m, MissionFacts())


# ── each guard: passes on its definition, fails closed otherwise ──

def _decided(*triples):
    return MissionFacts(plan_version=1, tasks=(_task('PENDING', action_classes=('read',)),),
                        cost_within_ceiling=True, policy=triples)


@pytest.mark.parametrize('facts, ok', [
    (_decided(('t1', 'read', 'ALLOW')), True),
    (_decided(('t1', 'read', 'ALLOW_WITHIN_BOUNDARY')), True),
    (_decided(('t1', 'read', 'ASK')), False),
    (_decided(('t1', 'read', 'ALLOW'), ('t1', 'deploy', 'DENY')), False),
    (dataclasses.replace(_decided(('t1', 'read', 'ALLOW')), cost_within_ceiling=False), False),
    (dataclasses.replace(_decided(('t1', 'read', 'ALLOW')), cost_within_ceiling=None), False),
    (dataclasses.replace(_decided(), plan_version=None), False),         # no plan
    (dataclasses.replace(_decided(), tasks=()), False),                  # no tasks
])
def test_plan_auto_approved(facts, ok):
    assert guards.plan_auto_approved(_mission(), facts).passed is ok


@pytest.mark.parametrize('facts, ok, why', [
    (_decided(('t1', 'read', 'ASK')), True, 'policy says ASK'),
    (dataclasses.replace(_decided(('t1', 'read', 'ALLOW')), cost_within_ceiling=False), True,
     'not under the auto-approve ceiling'),
    (dataclasses.replace(_decided(('t1', 'read', 'ALLOW')), cost_within_ceiling=None), True,
     'no estimated cost band'),
    (_decided(('t1', 'read', 'ALLOW')), False, 'nothing to ask'),
    (_decided(('t1', 'read', 'ASK'), ('t1', 'deploy', 'DENY')), False,
     'policy denies deploy on task t1: not a question for approval'),
    (dataclasses.replace(_decided(('t1', 'read', 'ASK')), plan_version=None), False,
     'no active plan'),
    (dataclasses.replace(_decided(('t1', 'read', 'ASK')), tasks=()), False, 'no active plan'),
])
def test_plan_needs_approval_only_when_there_is_a_question(facts, ok, why):
    got = guards.plan_needs_approval(_mission(), facts)
    assert got.passed is ok and why in got.reason


@pytest.mark.parametrize('guard', [guards.plan_auto_approved, guards.plan_needs_approval])
def test_a_plan_already_decided_is_never_decided_again(guard):
    """REPLANNING (or PLANNING after request_changes) with the old plan still in
    force: both decisions refuse until a newer plan is proposed."""
    facts = {guards.plan_auto_approved: _decided(('t1', 'read', 'ALLOW')),
             guards.plan_needs_approval: _decided(('t1', 'read', 'ASK'))}[guard]
    for decided, ok in ((None, True), (1, False), (3, False)):
        got = guard(_mission(decided_plan_version=decided),
                    dataclasses.replace(facts, plan_version=1 if decided != 3 else 3))
        assert got.passed is ok, (decided, got.reason)
        if not ok:
            assert 'already decided' in got.reason
    assert guard(_mission(decided_plan_version=1), dataclasses.replace(facts, plan_version=2)).passed


@pytest.mark.parametrize('tasks, ok', [
    ((_task('SUCCEEDED'), _task('SKIPPED', key='t2')), True),
    ((_task('SUCCEEDED'), _task('PENDING', kind='human', key='h')), True),   # human excluded
    ((_task('SUCCEEDED'), _task('RUNNING', key='t2')), False),
    ((_task('FAILED'),), False),
    ((), False),                                                            # vacuous: refused
])
def test_all_tasks_done(tasks, ok):
    assert guards.all_tasks_done(_mission(), MissionFacts(plan_version=1, tasks=tasks)).passed is ok


def test_all_tasks_done_needs_a_plan():
    assert not guards.all_tasks_done(_mission(), MissionFacts(tasks=(_task(),))).passed


A, H = 'automatic', 'human'


@pytest.mark.parametrize('criteria, verified, awaiting', [
    ((CriterionFact(A, 'PASSED'),), True, False),
    ((CriterionFact(A, 'PASSED'), CriterionFact(A, None)), False, False),
    ((CriterionFact(A, 'FAILED'),), False, False),
    ((CriterionFact(A, 'PASSED'), CriterionFact(H, None)), False, True),
    ((CriterionFact(A, 'PASSED'), CriterionFact(H, 'AWAITING_HUMAN')), False, True),
    ((CriterionFact(A, 'PASSED'), CriterionFact(H, 'PASSED')), True, False),
    ((CriterionFact(H, 'PASSED'),), False, False),           # nothing automatic to verify
    ((), False, False),                                      # no criteria: refused
])
def test_verified_and_awaiting_human_acceptance(criteria, verified, awaiting):
    f = MissionFacts(criteria=criteria)
    assert guards.verified(_mission(), f).passed is verified
    got = guards.awaiting_human_acceptance(_mission(), f)
    assert got.passed is awaiting
    if awaiting:
        assert got.reason == 'waiting for your acceptance'      # state-machines §2
    if not criteria:
        assert guards.verified(_mission(), f).reason == 'no success criteria to verify'


@pytest.mark.parametrize('plan_version, max_replans, ok', [
    (1, 2, False), (2, 2, False), (3, 2, True), (4, 2, True), (1, 0, True), (None, 2, False)])
def test_replan_budget_exhausted(plan_version, max_replans, ok):
    got = guards.replan_budget_exhausted(_mission(max_replans=max_replans),
                                         MissionFacts(plan_version=plan_version))
    assert got.passed is ok


@pytest.mark.parametrize('task, ok', [
    (_task('FAILED', attempts=2, max_attempts=2, failure_class='test_failure'), True),
    (_task('FAILED', attempts=2, max_attempts=2), True),                  # unclassified
    (_task('FAILED', attempts=1, max_attempts=2, failure_class='x'), False),  # attempts left
    (_task('FAILED', attempts=2, max_attempts=2, failure_class='policy'), False),
    (_task('FAILED', attempts=2, max_attempts=2, failure_class='credential'), False),
    (_task('FAILED', attempts=2, max_attempts=2, failure_class='human'), False),
    (_task('RUNNING', attempts=2, max_attempts=2), False),
])
def test_task_failed_retryable(task, ok):
    assert guards.task_failed_retryable(_mission(), MissionFacts(tasks=(task,))).passed is ok


@pytest.mark.parametrize('facts, ok', [
    (MissionFacts(policy=(('t1', 'deploy', 'DENY'),)), True),
    (MissionFacts(policy=(('t1', 'deploy', 'ASK'),)), False),
    (MissionFacts(missing_capability=True), True),
    (MissionFacts(declared_by='user_device'), True),
    (MissionFacts(declared_by='brain'), False),              # only a user declares failure
    (MissionFacts(declared_by='execution'), False),
    (MissionFacts(), False),
])
def test_unrecoverable(facts, ok):
    assert guards.unrecoverable(_mission(), facts).passed is ok


def _approval(step_up=False):
    return E.Approval(id=ids.new_id('approval'), subject=E.Ref('task', ids.new_id('task')),
                      action_hash='a' * 64, requested_by=ids.new_id('principal'),
                      step_up=step_up)


@pytest.mark.parametrize('facts, step_up, ok', [
    (guards.ApprovalFacts('user_device', ('approve',), 'a' * 64), False, True),
    (guards.ApprovalFacts('user_device', ('observe',), 'a' * 64), False, False),
    (guards.ApprovalFacts('brain', ('approve',), 'a' * 64), False, False),  # brains never
    (guards.ApprovalFacts('user_device', ('approve',), 'b' * 64), False, False),
    (guards.ApprovalFacts('user_device', ('approve',), 'a' * 64), True, False),
    (guards.ApprovalFacts('user_device', ('approve',), 'a' * 64, step_up_valid=True), True,
     True),
])
def test_approve(facts, step_up, ok):
    assert guards.approve(_approval(step_up), facts).passed is ok


# ── trigger resolution, generated over every machine ──

MACHINES = states.MACHINES


@pytest.mark.parametrize('machine', MACHINES)
def test_every_edge_resolves_and_every_non_edge_is_refused(machine):
    triggers = {t for _f, _to, t, _g in states.edges(machine) if t}
    real = [s for s in states.states(machine)]
    checked = 0
    for frm in real:
        for trig in sorted(triggers):
            edge = [(to, g) for f, to, t, g in states.edges(machine) if f == frm and t == trig]
            if edge and edge[0][0] != states.END:
                assert lifecycle.resolve(machine, frm, trig) == edge[0]
            else:
                with pytest.raises(lifecycle.IllegalTrigger) as err:
                    lifecycle.resolve(machine, frm, trig)
                assert (err.value.machine, err.value.frm, err.value.trigger) == (machine, frm,
                                                                                trig)
            checked += 1
    assert checked == len(real) * len(triggers)


@pytest.mark.parametrize('machine', MACHINES)
def test_terminal_states_have_no_way_out(machine):
    triggers = {t for _f, _to, t, _g in states.edges(machine) if t}
    for s in states.terminal(machine):
        for trig in triggers:
            with pytest.raises(lifecycle.IllegalTrigger):
                lifecycle.resolve(machine, s, trig)


def test_a_trigger_that_ends_the_machine_is_not_a_state_change():
    with pytest.raises(lifecycle.IllegalTrigger, match='removes the row'):
        lifecycle.resolve('device', 'PAIRING', 'code_expired')


def test_an_illegal_trigger_names_where_it_would_lead():
    with pytest.raises(lifecycle.IllegalTrigger) as err:
        lifecycle.resolve('mission', 'CREATED', 'pause')
    assert (err.value.machine, err.value.frm, err.value.to) == ('mission', 'CREATED', 'PAUSED')
    with pytest.raises(lifecycle.IllegalTrigger) as err:          # from two states, one place
        lifecycle.resolve('mission', 'CREATED', 'plan_auto_approved')
    assert err.value.to == 'APPROVED'
    with pytest.raises(lifecycle.IllegalTrigger) as err:
        lifecycle.resolve('mission', 'CREATED', 'teleport')
    assert err.value.to is None


def test_no_state_is_set_outside_the_p2_primitive():
    """The application layer names triggers; only Tx.transition writes state."""
    app = os.path.dirname(lifecycle.__file__)
    for name in os.listdir(app):
        if name.endswith('.py'):
            src = open(os.path.join(app, name), encoding='utf-8').read()
            assert 'UPDATE ' not in src and 'INSERT ' not in src, name
            assert "replace(row.entity" not in src and 'state=' not in src.replace(
                'state=None', ''), name
