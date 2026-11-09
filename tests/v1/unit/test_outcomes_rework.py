"""`outcomes.by_model` counts rework next to pass and fail: verification rows beyond an
execution's first, reviews that asked for changes, and executions whose task ran again.
An absent source is None, never 0."""

import pytest

from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref

from archeus.infra.db import Database

from .test_outcomes_cache import plan_of, put, read, run, task


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def verify(db, mid, x, tid, n=1):
    put(db, *(entities.Verification(id=ids.new_id('verification'), subject=Ref('task', tid),
                                    verifier='code', execution_id=x, state='PASSED',
                                    plan_id=plan_of(db, mid))
              for _ in range(n)))


def review(db, mid, verdict):
    put(db, entities.Review(id=ids.new_id('review'), mission_id=mid, reviewer='r',
                            verdict=verdict, plan_id=plan_of(db, mid)))


def test_nothing_to_count_is_none_but_for_the_executions_themselves(db):
    mid, tid = task(db)
    run(db, mid, tid)
    (g,) = read(db)
    assert (g['verification_attempts'], g['changes_requested'], g['reworked']) == (None, None, 0)


def test_verification_attempts_are_the_rows_beyond_the_first_per_execution(db):
    mid, tid = task(db)
    verify(db, mid, run(db, mid, tid), tid, 3)
    verify(db, mid, run(db, mid, tid), tid, 1)
    run(db, mid, tid)
    (g,) = read(db)
    assert g['verification_attempts'] == 2
    assert g['reworked'] == 3


def test_a_verified_once_execution_made_no_extra_attempt_but_is_not_absent(db):
    mid, tid = task(db)
    verify(db, mid, run(db, mid, tid), tid)
    assert read(db)[0]['verification_attempts'] == 0


def test_changes_requested_counts_that_verdict_on_the_groups_missions(db):
    mid, tid = task(db)
    run(db, mid, tid)
    review(db, mid, 'changes_requested')
    review(db, mid, 'changes_requested')
    review(db, mid, 'accept')
    other, otid = task(db)
    run(db, other, otid)
    review(db, other, 'accept')
    assert read(db)[0]['changes_requested'] == 2


def test_a_mission_reviewed_without_changes_requested_counts_zero_not_none(db):
    mid, tid = task(db)
    run(db, mid, tid)
    review(db, mid, 'accept')
    assert read(db)[0]['changes_requested'] == 0


def test_reworked_counts_executions_of_a_task_that_ran_more_than_once(db):
    mid, tid = task(db)
    _, once = task(db, mid)
    run(db, mid, tid, state='ENDED_ERROR')
    run(db, mid, tid)
    run(db, mid, once)
    (g,) = read(db)
    assert (g['executions'], g['reworked']) == (3, 2)


def test_an_execution_that_never_started_is_not_a_second_run(db):
    mid, tid = task(db)
    run(db, mid, tid)
    run(db, mid, tid, charged=False)
    (g,) = read(db)
    assert (g['executions'], g['reworked']) == (1, 0)
