"""T-825: pins on the authority-bearing conditions of archeus/core/domain/guards.py
that no existing test in tests/v1 pins — each one fails when the condition it
names is inverted, removed or loosened, and the mutant that proves it is named in
the docstring (applied to a scratch copy of the source, never to the repo).

The conditions the suite already pins are left alone, each by a named test:
guards.py:126 (the `<=` of a plan already decided, test_guards.py:104), 139 (the
chat veto, test_gaps_core_domain_guards.py:53), 145/171 (the cost band fed False
and None, test_guards.py:76-77), 159 (the DENY refusal, test_guards.py:98), 184
(the open-task filter, test_guards.py:125), 190 (the merge-back filter,
test_gaps_core_domain_guards.py:83), 224 (`used >= max_replans`,
test_guards.py:159), 230 (the retryable conjunct, test_guards.py:174), 249
(`held_from in PLAN_IN_FORCE`, test_gaps_core_domain_guards.py:140), 257 (the
three review states, test_gaps_core_domain_guards.py:158), 279 and 288
(test_guards.py:310, 319), 311 (the step-up conjunct, test_guards.py:206),
334/336/339 (the architecture identity, inspection state and None-verdict
refuses, test_gaps_core_domain_guards.py:191, 202, 177), 365-373 (the four
task_verified refuses, test_gaps_core_domain_guards.py:247) and the `evaluate`
binding (test_guards.py:55). See the card report for the twenty verdicts and
their tests.

Pure functions only: no I/O, no clock, no OS, no process. The fixtures are the
same fact dataclasses the guards read, with explicit values everywhere except
where a default is exactly what is being pinned.
"""

import pytest

from archeus.core.domain import entities as E
from archeus.core.domain import guards, ids
from archeus.core.domain.guards import (ArchitectureFacts, ApprovalFacts, IntegrationFacts,
                                        MissionFacts, PlanFacts, TaskFact)

ARCHI = ('first_inspection', 'first_inspection_drift',
         'reinspected_no_drift', 'reinspected_drift')

HASH = 'a' * 64
TASK = TaskFact('t1', 'code_change', 'PENDING', action_classes=('read',))


def _mission(**kw):
    return E.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                     title='t', objective='o', **kw)


def _plan(digest=HASH):
    return E.Plan(id=ids.new_id('plan'), mission_id=ids.new_id('mission'), digest=digest)


def _approval(action_hash=HASH, step_up=False):
    return E.Approval(id=ids.new_id('approval'), subject=E.Ref('task', ids.new_id('task')),
                      action_hash=action_hash, requested_by=ids.new_id('principal'),
                      step_up=step_up)


def _repo():
    return E.Repository(id=ids.new_id('repository'), workspace_id=ids.GLOBAL_WORKSPACE,
                        project_id=ids.new_id('project'), path='projects/app',
                        path_key='projects/app')


def _allowed(**over):
    """A plan that would pass `plan_auto_approved`, with `over` on the facts."""
    base = dict(plan_version=1, tasks=(TASK,), cost_within_ceiling=True,
                policy=(('t1', 'read', 'ALLOW'),))
    return MissionFacts(**dict(base, **over))


def _failed(**kw):
    return TaskFact(key='t1', kind='code_change', state='FAILED', **kw)


# ── AUTO_OK is an allowlist of exactly two decisions (guards.py:21) ──────────

def test_the_auto_approve_allowlist_names_exactly_two_decisions():
    """Mutant: `AUTO_OK = ('ALLOW', 'ALLOW_WITHIN_BOUNDARY', 'PASSED')`. No
    existing test feeds any other decision word, so a widening survives."""
    assert set(guards.AUTO_OK) == {'ALLOW', 'ALLOW_WITHIN_BOUNDARY'}


@pytest.mark.parametrize('decision', ['PASSED', 'OK', 'YES', 'AUTO', 'UNDECIDED'],
                         ids=['passed', 'ok', 'yes', 'auto', 'undecided'])
def test_a_decision_word_outside_the_two_allowed_names_never_passes(decision):
    """Mutant: a decision added to AUTO_OK (guards.py:21) makes this guard pass
    on a policy that never allowed the action class."""
    f = _allowed(policy=(('t1', 'read', decision),))
    got = guards.plan_auto_approved(_mission(), f)
    assert not got.passed and 'policy says %s for read on task t1' % decision in got.reason
    assert guards.plan_needs_approval(_mission(), f).passed     # it is a question instead


# ── the plan digest is compared whole (guards.py:299) ────────────────────────

@pytest.mark.parametrize('recorded', ['a' * 32 + 'b' * 32, 'a' * 63 + 'b', 'b' + 'a' * 63],
                         ids=['half', 'last-char', 'first-char'])
def test_ready_compares_the_whole_digest_not_a_prefix_of_it(recorded):
    """Mutant: `plan.digest[:16] != f.digest[:16]`. Every existing digest pair
    differs in its first character, so a prefix comparison keeps them green."""
    got = guards.ready(_plan(digest=HASH), PlanFacts(digest=recorded))
    assert not got.passed
    assert got.reason == 'the plan content does not match its recorded digest'


# ── no cost band recorded is never under the ceiling (guards.py:71, 145) ─────

def test_the_default_cost_band_is_no_band_and_refuses_auto_approval():
    """Mutant: `cost_within_ceiling: bool = True`. The existing plan-fact
    fixtures always set the band, so the fail-closed default goes untested."""
    f = MissionFacts(plan_version=1, tasks=(TASK,), policy=(('t1', 'read', 'ALLOW'),))
    got = guards.plan_auto_approved(_mission(), f)
    assert not got.passed and got.reason == 'no estimated cost band'
    asked = guards.plan_needs_approval(_mission(), f)
    assert asked.passed and asked.reason == 'no estimated cost band'


# ── TaskFact's own attempt counters (guards.py:47-48, 230) ───────────────────

def test_a_failed_task_that_never_ran_an_attempt_has_not_exhausted_anything():
    """Mutants: `attempts: int = 2` or `max_attempts: int = 0`. Every existing
    task fixture passes both counters, so the defaults are free."""
    got = guards.task_failed_retryable(_mission(), MissionFacts(tasks=(_failed(),)))
    assert not got.passed and got.reason == 'no task failed retryably'


def test_the_default_attempt_ceiling_is_two_attempts():
    """Mutant: `max_attempts: int = 0` (or 1): the retryable verdict arrives
    before the second attempt was ever spent."""
    t = TaskFact(key='t1', kind='code_change', state='FAILED', attempts=2,
                 failure_class='test_failure')
    got = guards.task_failed_retryable(_mission(), MissionFacts(tasks=(t,)))
    assert got.passed and got.reason == 'task t1 failed after 2 attempts (test_failure)'


def test_a_failed_task_with_no_class_records_that_it_is_unclassified():
    """Mutant: `t.failure_class` alone in the reason (guards.py:233) writes
    'None' into the state event instead of saying nothing was classified."""
    t = TaskFact(key='t1', kind='code_change', state='FAILED', attempts=2)
    got = guards.task_failed_retryable(_mission(), MissionFacts(tasks=(t,)))
    assert got.passed and got.reason == 'task t1 failed after 2 attempts (unclassified)'


# ── NOT_RETRYABLE is a blocklist of exactly three classes (guards.py:23) ─────

def test_the_replan_blocklist_names_exactly_three_failure_classes():
    """Mutant: `NOT_RETRYABLE = ('policy', 'credential', 'human', 'tool')` —
    'tool' appears in no existing task fixture, so it survives."""
    assert set(guards.NOT_RETRYABLE) == {'policy', 'credential', 'human'}


@pytest.mark.parametrize('failure_class', ['tool', 'other', 'context_insufficient', 'POLICY'],
                         ids=['tool', 'other', 'context', 'uppercase'])
def test_a_class_the_blocklist_does_not_name_stays_retryable(failure_class):
    """Mutant: the class added to NOT_RETRYABLE (guards.py:23) strands a task a
    replan could fix, because the retryable edge never fires for it."""
    t = _failed(attempts=2, max_attempts=2, failure_class=failure_class)
    got = guards.task_failed_retryable(_mission(), MissionFacts(tasks=(t,)))
    assert got.passed and got.reason == 'task t1 failed after 2 attempts (%s)' % failure_class


# ── `accepted` is the exact word ACCEPTED (guards.py:257) ────────────────────

@pytest.mark.parametrize('review', ['accepted', ' ACCEPTED', 'ACCEPTED ', 'NOT_ACCEPTED',
                                    'ACCEPTED_OR_SO'],
                         ids=['lowercase', 'leading-space', 'trailing-space', 'prefixed',
                              'suffixed'])
def test_accepted_takes_exactly_the_word_accepted_and_no_other(review):
    """Mutants: `'ACCEPTED' in f.review` (the prefixed case) and
    `f.review.upper() == 'ACCEPTED'` (the lowercase case) both keep the existing
    three-value table green and accept a review that never accepted."""
    got = guards.accepted(_mission(), MissionFacts(review=review))
    assert not got.passed
    assert got.reason == 'no accepting review of the plan in force (the latest is %s)' % review


# ── only the exact word APPROVED authorises the mission (guards.py:279) ──────

@pytest.mark.parametrize('plan_approval', ['approved', 'Accepted', 'APPROVED ', 'ACCEPTED',
                                           'APPROVING'],
                         ids=['lowercase', 'titlecase', 'trailing-space', 'accepted',
                              'in-progress'])
def test_the_mission_is_approved_only_by_the_exact_word_approved(plan_approval):
    """Mutants: `str(f.plan_approval).upper() != 'APPROVED'` (lowercase) and
    `f.plan_approval not in ('APPROVED', 'ACCEPTED')` (accepted): the existing
    table only holds PENDING, SUPERSEDED and None, so both survive."""
    got = guards.approve_mission(_mission(), MissionFacts(plan_version=1,
                                                          plan_approval=plan_approval))
    assert not got.passed
    assert got.reason == 'no approval of plan v1 is APPROVED (%s)' % plan_approval


# ── a recorded denial is a real decision id (guards.py:288) ──────────────────

@pytest.mark.parametrize('denial', [None, ''], ids=['none', 'empty'])
def test_plan_denied_only_moves_the_mission_on_a_real_denial_id(denial):
    """Mutant: `if f.denial is None:` — an empty string passes that test, so a
    mission is BLOCKED on a denial id that was never recorded."""
    got = guards.plan_denied(_mission(), MissionFacts(denial=denial))
    assert not got.passed
    assert got.reason == 'no policy denial is recorded for this plan'


# ── the approval guard's actor, scope and hash (guards.py:307, 309) ──────────

@pytest.mark.parametrize('actor_kind', ['user_device_admin', 'USER_DEVICE', 'user-devices'],
                         ids=['suffix', 'uppercase', 'hyphen'])
def test_only_exactly_a_user_device_decides_the_approval(actor_kind):
    """Mutant: `'user_device' in f.actor_kind` — a brain-side principal whose
    kind merely contains the word decides an approval."""
    got = guards.approve(_approval(), ApprovalFacts(actor_kind, ('approve',), HASH))
    assert not got.passed
    assert got.reason == 'only a user device with the approve scope decides'


@pytest.mark.parametrize('scopes', [('approve_all',), ('read', 'can_approve'), ('approve ',)],
                         ids=['suffix', 'near-miss', 'trailing-space'])
def test_the_approve_scope_is_a_whole_token_of_its_own(scopes):
    """Mutant: `'approve' not in ' '.join(f.actor_scopes)` — a principal whose
    scope merely contains the word decides an approval."""
    got = guards.approve(_approval(), ApprovalFacts('user_device', scopes, HASH))
    assert not got.passed
    assert got.reason == 'only a user device with the approve scope decides'


@pytest.mark.parametrize('decided', ['a' * 32 + 'b' * 32, 'a' * 63 + 'b', 'b' + 'a' * 63],
                         ids=['half', 'last-char', 'first-char'])
def test_the_approval_is_for_the_whole_action_hash(decided):
    """Mutant: `f.action_hash[:16] != approval.action_hash[:16]` — the existing
    pair ('a'*64, 'b'*64) differs in its first character, so a prefix
    comparison survives it and approves a different action."""
    got = guards.approve(_approval(), ApprovalFacts('user_device', ('approve',), decided))
    assert not got.passed
    assert got.reason == 'the decision is for a different action'


@pytest.mark.parametrize('decided', [None, ''], ids=['none', 'empty'])
def test_a_decision_with_no_action_hash_is_not_a_decision(decided):
    """Mutant: `if f.action_hash and f.action_hash != approval.action_hash` —
    an empty hash matches nothing and approves everything."""
    got = guards.approve(_approval(), ApprovalFacts('user_device', ('approve',), decided))
    assert not got.passed
    assert got.reason == 'the decision is for a different action'


# ── the architecture assessment takes only its exact values (guards.py:333-344) ──

@pytest.mark.parametrize('violated', ['no', 'yes', '0', 'PASSED'],
                         ids=['no-string', 'yes-string', 'zero-string', 'word'])
def test_the_architecture_guards_take_only_a_real_boolean_verdict(violated):
    """Mutant: `bool(f.violated) != drift` (guards.py:341) — a malformed verdict
    string is truthy, so the drift guard moves the repository on it."""
    repo = _repo()
    f = ArchitectureFacts(inspection_repository_id=repo.id, inspection_state='COMPLETED',
                          violated=violated)
    for name in ARCHI:
        got = getattr(guards, name)(repo, f)
        assert not got.passed, (name, got.reason)


@pytest.mark.parametrize('state', ['completed', 'COMPLETED ', 'COMPLETEDx'],
                         ids=['lowercase', 'trailing-space', 'suffix'])
def test_the_assessment_rests_on_the_exact_word_completed(state):
    """Mutant: `(f.inspection_state or '').upper() != 'COMPLETED'` (guards.py:336)
    — an inspection still RUNNING in a lowercase spelling moves the repository."""
    repo = _repo()
    f = ArchitectureFacts(inspection_repository_id=repo.id, inspection_state=state,
                          violated=False)
    for name in ARCHI:
        got = getattr(guards, name)(repo, f)
        assert not got.passed, (name, got.reason)
        assert 'not COMPLETED' in got.reason


# ── task_verified: the merge gate compares whole values (guards.py:92-94, 372) ──

GOOD = dict(task_state='SUCCEEDED', plan_in_force=True,
            verified_revision='rev_a', revision='rev_a')


@pytest.mark.parametrize('revision', ['rev_a_2', 'rev_ax', 'rev_a '],
                         ids=['suffix', 'appended', 'trailing-space'])
def test_task_verified_merges_the_whole_verified_revision(revision):
    """Mutant: `not str(f.revision).startswith(str(f.verified_revision))` — the
    existing pairs (rev_a/rev_b, rev_a/None) never share a prefix, so a
    prefix match lets a different revision merge into the mission branch."""
    got = guards.task_verified(None, IntegrationFacts(**dict(GOOD, revision=revision)))
    assert not got.passed and 'is not the verified' in got.reason


def test_task_verified_refuses_the_default_facts_row():
    """Mutant: `task_state: str = 'SUCCEEDED'` (guards.py:92) — no existing
    IntegrationFacts omits the field, so a default state merges unverified work."""
    got = guards.task_verified(None, IntegrationFacts())
    assert not got.passed and got.reason == 'the task is None, not SUCCEEDED'


def test_task_verified_refuses_until_the_plan_is_in_force_by_default():
    """Mutant: `plan_in_force: bool = True` (guards.py:93) — a verification of a
    superseded plan would merge (P13 D11)."""
    f = IntegrationFacts(task_state='SUCCEEDED', verified_revision='rev_a', revision='rev_a')
    got = guards.task_verified(None, f)
    assert not got.passed and got.reason == "the task's plan is not in force"


def test_task_verified_refuses_without_a_verified_revision_of_its_own():
    """Mutant: `verified_revision: str = 'rev_a'` (guards.py:94) — the merge
    would name a revision no PASSED verification ever checked."""
    f = IntegrationFacts(task_state='SUCCEEDED', plan_in_force=True, revision='rev_a')
    got = guards.task_verified(None, f)
    assert not got.passed and got.reason == 'no passing verification of the plan in force'
