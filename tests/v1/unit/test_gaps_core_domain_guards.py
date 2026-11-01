"""T-316: the highest-risk uncovered branches of archeus/core/domain/guards.py.

Boundary values and malformed input for the guards that gate real authority:
the chat mission's explicit-approval veto, the unknown policy decision, the
P13 merge-back gate (`all_tasks_done` integration, `task_verified`), the
human/automatic split of `awaiting_human_acceptance` and `verification_failed`,
`redispatch`, `accepted`, the architecture `_assessed` fail-closed paths.
Pure functions only: no I/O, no clock, no OS — the same style and fixtures as
tests/v1/unit/test_guards.py (a subset of those branches are covered there or
in test_planning_units.py; only the gaps are re-opened here).
"""

import dataclasses

import pytest

from archeus.core.domain import entities as E
from archeus.core.domain import guards, ids
from archeus.core.domain.guards import (ArchitectureFacts, CriterionFact, IntegrationFacts,
                                        MissionFacts, PlanFacts, TaskFact)

A, H = 'automatic', 'human'


def _mission(**kw):
    return E.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                     title='t', objective='o', **kw)


def _task(state='SUCCEEDED', kind='code_change', **kw):
    return TaskFact(key=kw.pop('key', 't1'), kind=kind, state=state, **kw)


def _allowed(**kw):
    """A plan that would pass `plan_auto_approved`: everything allowed, cost under."""
    return MissionFacts(plan_version=1, tasks=(_task('PENDING', action_classes=('read',)),),
                        cost_within_ceiling=True, policy=(('t1', 'read', 'ALLOW'),), **kw)


def _repo():
    return E.Repository(id=ids.new_id('repository'), workspace_id=ids.GLOBAL_WORKSPACE,
                        project_id=ids.new_id('project'), path='projects/app',
                        path_key='projects/app')


def _inspection(repo, state='COMPLETED'):
    return E.RepositoryInspection(id=ids.new_id('repository_inspection'),
                                  repository_id=repo.id, extractor_version=1, state=state)


# ── plan_auto_approved: the chat veto and the unknown decision ────────────────

def test_plan_auto_approved_refuses_a_mission_that_asked_for_explicit_approval():
    """Everything else is fully allowed, so ONLY the explicit veto can refuse:
    dropping guards.py:139 would let a chat mission self-approve its plan."""
    got = guards.plan_auto_approved(_mission(), _allowed(explicit_plan_approval=True))
    assert not got.passed and 'needs its plan approved' in got.reason
    # and the mirror guard treats it as exactly the question to ask a human
    assert guards.plan_needs_approval(_mission(),
                                      _allowed(explicit_plan_approval=True)).passed


@pytest.mark.parametrize('decision', ['ASK', 'MAYBE', 'allow', '', 'DENIED'])
def test_an_unrecognised_policy_decision_is_never_auto_ok(decision):
    """AUTO_OK is an allowlist (guards.py:20): a malformed or unknown decision
    must fall to the refuse side of `d not in AUTO_OK` (guards.py:135/167),
    never be treated as an allowance."""
    f = dataclasses.replace(_allowed(), policy=(('t1', 'read', decision),))
    got = guards.plan_auto_approved(_mission(), f)
    assert not got.passed and 'policy says %s for %s on task %s' % (decision, 'read', 't1') \
        in got.reason
    assert guards.plan_needs_approval(_mission(), f).passed      # it becomes a question


# ── all_tasks_done: the P13 D11 merge-back gate ───────────────────────────────

@pytest.mark.parametrize('integration, ok', [
    (None, True),                                                # in place: nothing to merge
    ('MERGED', True), ('ABANDONED', True),                        # decided outcomes
    ('PENDING', False), ('MERGING', False), ('CONFLICT', False),  # not decided yet
    ('merged', False),                                            # malformed: refused
], ids=['none', 'merged', 'abandoned', 'pending', 'merging', 'conflict', 'lowercase'])
def test_all_tasks_done_waits_for_every_worktree_merge(integration, ok):
    """guards.py:189-192: dropping the unmerged filter would complete a mission
    whose verified worktree results were never merged to the mission branch."""
    f = MissionFacts(plan_version=1, tasks=(_task('SUCCEEDED', integration=integration),))
    got = guards.all_tasks_done(_mission(), f)
    assert got.passed is ok
    if not ok:
        assert got.reason == 'results not merged yet: t1'


# ── awaiting_human_acceptance / verification_failed: the human split ──────────

@pytest.mark.parametrize('criteria, awaiting', [
    ((CriterionFact(A, 'AWAITING_HUMAN'),), True),                       # §6: verifier stuck
    ((CriterionFact(A, 'PASSED'), CriterionFact(H, 'PENDING')), True),
    ((CriterionFact(A, 'PASSED'), CriterionFact(H, 'REJECTED')), False),  # decided once
    ((CriterionFact(A, 'PASSED'), CriterionFact(H, 'WEIRD')), False),     # malformed: no wait
    ((CriterionFact(A, 'PASSED'), CriterionFact(H, 'PASSED')), False),
], ids=['auto-awaiting', 'human-pending', 'human-rejected', 'human-weird', 'all-passed'])
def test_awaiting_human_acceptance_only_on_a_criterion_that_really_waits(criteria, awaiting):
    """guards.py:214-216: the `or c.verification == 'AWAITING_HUMAN'` disjunct
    (an automatic criterion the verifier could not decide) and the exclusion of
    a decided human verdict (`REJECTED` must NOT wait, it goes to rejection)."""
    got = guards.awaiting_human_acceptance(_mission(), MissionFacts(criteria=criteria))
    assert got.passed is awaiting


@pytest.mark.parametrize('criteria, kind', [
    ((CriterionFact(A, 'FAILED'),), 'an automatic'),
    ((CriterionFact(A, 'PASSED'), CriterionFact(H, 'FAILED')), 'a human'),
], ids=['automatic', 'human'])
def test_verification_failed_names_the_kind_that_failed(criteria, kind):
    """guards.py:242-244: inverting the `any(c.check == 'automatic' ...)` would
    mislabel a human rejection as automatic (or vice versa) in the event trail."""
    got = guards.verification_failed(_mission(), MissionFacts(criteria=criteria))
    assert got.passed and got.reason == '%s criterion failed' % kind


@pytest.mark.parametrize('criteria', [
    (),                                                    # nothing to fail
    (CriterionFact(A, 'PASSED'),),
    (CriterionFact(A, 'AWAITING_HUMAN'), CriterionFact(H, 'PENDING')),   # waiting, not failed
], ids=['empty', 'passed', 'waiting'])
def test_verification_failed_never_fires_without_a_failed_criterion(criteria):
    """guards.py:245: the refuse branch must not fire on pending or waiting rows."""
    got = guards.verification_failed(_mission(), MissionFacts(criteria=criteria))
    assert not got.passed and got.reason == 'no criterion failed'


# ── redispatch: PLAN_IN_FORCE is the whole boundary ───────────────────────────

@pytest.mark.parametrize('held_from, ok', [
    ('EXECUTING', True), ('VERIFYING', True),               # an approved plan is in force
    ('RESUMED', False), ('PAUSED', False), ('BLOCKED', False),   # not in PLAN_IN_FORCE
    ('REVIEWING', False),                                    # verified, not yet accepted
    (None, False),                                           # never held: nothing in force
])
def test_redispatch_only_returns_to_executing_from_a_plan_in_force(held_from, ok):
    """guards.py:249-253: widening PLAN_IN_FORCE (or dropping the check) would
    send a mission straight back to EXECUTING from a hold that had no plan."""
    got = guards.redispatch(_mission(held_from=held_from), MissionFacts())
    assert got.passed is ok
    if ok:
        assert got.reason == 'held from %s with an approved plan in force' % held_from
    else:
        assert 'redispatch_before_plan' in got.reason


# ── accepted: three states of the latest review ───────────────────────────────

@pytest.mark.parametrize('review, suffix', [
    ('ACCEPTED', None),                       # passes; no suffix branch taken
    (None, ''),                               # no review at all: no suffix
    ('REJECTED', '(the latest is REJECTED)'),  # another review: names it
])
def test_accepted_only_the_latest_review_accepts(review, suffix):
    """guards.py:257-261: `accepted` is exactly review == 'ACCEPTED', and the
    reason must say what the latest review really was (never None's suffix)."""
    got = guards.accepted(_mission(), MissionFacts(review=review))
    assert got.passed is (review == 'ACCEPTED')
    if suffix is None:
        assert '(the latest is' not in got.reason
    elif suffix == '':
        assert '(the latest is' not in got.reason
    else:
        assert got.reason.endswith(suffix)


# ── architecture: _assessed fails closed on every missing piece ───────────────

ARCHI = ('first_inspection', 'first_inspection_drift',
         'reinspected_no_drift', 'reinspected_drift')


def test_architecture_guards_fail_closed_when_nothing_was_evaluated():
    """guards.py:339-340: violated None means the findings were never evaluated;
    dropping this branch (e.g. `if f.violated != drift` alone) would let
    `violated=None` compare unequal to False and refuse, but equal-to-truthy
    inversions pass — and a None verdict must never authorise a move."""
    repo = _repo()
    f = ArchitectureFacts(inspection_repository_id=repo.id, inspection_state='COMPLETED',
                          violated=None)
    for name in ARCHI:
        got = getattr(guards, name)(repo, f)
        assert not got.passed, name
        assert got.reason == 'no findings were evaluated', name


def test_architecture_guards_refuse_an_inspection_of_another_repository():
    """guards.py:334-335: without the identity check one repository's clean
    assessment could move a different repository's architecture state."""
    repo, other = _repo(), _repo()
    f = ArchitectureFacts.of(_inspection(other), False)
    for name in ('first_inspection', 'reinspected_no_drift'):
        got = getattr(guards, name)(repo, f)
        assert not got.passed and 'not of an inspection of this repository' in got.reason


@pytest.mark.parametrize('state', [None, 'RUNNING', 'FAILED'], ids=['none', 'running', 'failed'])
def test_architecture_guards_refuse_an_incomplete_inspection(state):
    """guards.py:336-337: the assessment must rest on a COMPLETED inspection."""
    repo = _repo()
    f = ArchitectureFacts.of(_inspection(repo, state=state), False)
    for name in ARCHI:
        got = getattr(guards, name)(repo, f)
        assert not got.passed and 'not COMPLETED' in got.reason


@pytest.mark.parametrize('name, violated, ok', [
    ('first_inspection', False, True), ('first_inspection', True, False),
    ('first_inspection_drift', True, True), ('first_inspection_drift', False, False),
    ('reinspected_no_drift', False, True), ('reinspected_no_drift', True, False),
    ('reinspected_drift', True, True), ('reinspected_drift', False, False),
], ids=['fi-clean', 'fi-drift', 'fid-drift', 'fid-clean',
        'rnd-clean', 'rnd-drift', 'rd-drift', 'rd-clean'])
def test_the_four_architecture_guards_split_exactly_on_the_finding(name, violated, ok):
    """guards.py:341-343: `f.violated != drift` is the whole difference between
    the drift and no-drift guards; any inversion moves the wrong repository."""
    repo = _repo()
    f = ArchitectureFacts.of(_inspection(repo), violated)
    got = getattr(guards, name)(repo, f)
    assert got.passed is ok
    if ok:
        assert got.reason == ('constraints violated' if violated else 'no constraint violated')
    else:
        assert got.reason == ('a constraint is violated' if violated
                              else 'no constraint is violated')


# ── task_verified: the P13 D10 merge gate, link by link ───────────────────────

GOOD = dict(task_state='SUCCEEDED', plan_in_force=True,
            verified_revision='rev_a', revision='rev_a')


@pytest.mark.parametrize('over, why', [
    ({}, None),
    ({'task_state': 'RUNNING'}, 'the task is RUNNING, not SUCCEEDED'),
    ({'task_state': None}, 'the task is None, not SUCCEEDED'),        # malformed: refused
    ({'plan_in_force': False}, "the task's plan is not in force"),
    ({'verified_revision': None}, 'no passing verification of the plan in force'),
    ({'revision': None}, 'is not the verified'),                      # nothing to merge
    ({'revision': 'rev_b'}, 'is not the verified'),                   # an unverified commit
], ids=['good', 'running', 'none-state', 'not-in-force', 'unverified', 'no-revision', 'other'])
def test_task_verified_only_merges_the_verified_revision(over, why):
    """guards.py:365-373: dropping any one of the four refuses lets an
    unverified (or no) revision merge into the mission branch."""
    f = IntegrationFacts(**dict(GOOD, **over))
    got = guards.task_verified(None, f)          # the guard reads only the facts
    assert got.passed is (why is None)
    if why is not None:
        assert why in got.reason


# ── ready: the truncation sub-branch (digest cases are in test_planning_units) ─

def test_ready_reports_only_the_first_five_problems():
    """guards.py:297: `problems[:5]` keeps the reason bounded; without the
    slice a validator flood reaches the state event whole."""
    plan = E.Plan(id=ids.new_id('plan'), mission_id=ids.new_id('mission'))
    problems = tuple('p%d' % i for i in range(7))
    got = guards.ready(plan, PlanFacts(problems=problems))
    assert not got.passed
    assert got.reason == 'the plan is not valid: p0; p1; p2; p3; p4'
