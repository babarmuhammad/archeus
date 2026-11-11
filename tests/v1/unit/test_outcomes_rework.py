"""`outcomes.by_model` counts rework next to pass and fail: verifier retries of an
execution's verifications, reviews that asked for changes, and executions whose task
ran again. An absent source is None, never 0."""

import pytest

from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref

from archeus.infra.db import Database

from .test_outcomes_cache import ACTOR, plan_of, put, read, run, task


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def verify(db, mid, x, tid, rows=1, retries=0):
    """*rows* verifications of execution *x*; the first crashed and was retried *retries* times."""
    ids_ = [ids.new_id('verification') for _ in range(rows)]
    put(db, *(entities.Verification(id=v, subject=Ref('task', tid), verifier='code',
                                    execution_id=x, plan_id=plan_of(db, mid),
                                    state='ERROR' if retries and v == ids_[0] else 'PASSED')
              for v in ids_))

    def move(tx, **_):
        for i in range(retries):
            for to in ('PENDING', 'RUNNING', 'ERROR' if i < retries - 1 else 'PASSED'):
                tx.transition(entities.Verification, ids_[0], to, actor=ACTOR, reason='test')
    db.writer.execute(move, {})


def review(db, mid, verdict):
    put(db, entities.Review(id=ids.new_id('review'), mission_id=mid, reviewer='r',
                            verdict=verdict, plan_id=plan_of(db, mid)))


def test_nothing_to_count_is_none_but_for_the_executions_themselves(db):
    mid, tid = task(db)
    run(db, mid, tid)
    (g,) = read(db)
    assert (g['verification_attempts'], g['changes_requested'], g['reworked']) == (None, None, 0)


def test_verification_attempts_are_the_verifier_retries_of_each_execution(db):
    mid, tid = task(db)
    verify(db, mid, run(db, mid, tid), tid, retries=3)
    verify(db, mid, run(db, mid, tid), tid, retries=1)
    verify(db, mid, run(db, mid, tid), tid)
    run(db, mid, tid)
    (g,) = read(db)
    assert g['verification_attempts'] == 4
    assert g['reworked'] == 4


def test_a_verified_once_execution_made_no_extra_attempt_but_is_not_absent(db):
    mid, tid = task(db)
    verify(db, mid, run(db, mid, tid), tid)
    assert read(db)[0]['verification_attempts'] == 0


def test_a_human_row_beside_the_automatic_one_is_not_a_retry(db):
    mid, tid = task(db)
    verify(db, mid, run(db, mid, tid), tid, rows=2)
    assert read(db)[0]['verification_attempts'] == 0


def test_a_crashed_verifier_retried_on_its_one_row_counts_each_retry(db):
    mid, tid = task(db)
    verify(db, mid, run(db, mid, tid), tid, retries=3)
    assert read(db)[0]['verification_attempts'] == 3


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


def test_a_stop_that_spent_no_attempt_is_not_a_second_run(db):
    mid, tid = task(db)
    run(db, mid, tid)
    run(db, mid, tid, charged=False)
    (g,) = read(db)
    assert (g['executions'], g['reworked']) == (1, 0)


def test_an_execution_still_pending_is_not_a_second_run(db):
    mid, tid = task(db)
    run(db, mid, tid)
    run(db, mid, tid, state='INTENT')
    (g,) = read(db)
    assert (g['executions'], g['reworked']) == (1, 0)


def test_a_started_execution_still_running_is_a_second_run(db):
    mid, tid = task(db)
    run(db, mid, tid)
    run(db, mid, tid, state='RUNNING')
    assert read(db)[0]['reworked'] == 1


def test_a_stored_payload_that_is_not_an_object_is_no_retry(db):
    """A history row whose payload decodes to a list, null or a scalar is skipped;
    the valid retries beside it still count."""
    mid, tid = task(db)
    verify(db, mid, run(db, mid, tid), tid, retries=2)
    assert read(db)[0]['verification_attempts'] == 2

    def junk(tx, **_):
        for i, payload in enumerate(('[]', 'null', '"x"')):
            tx.execute("INSERT INTO events (id, type, at, actor_kind, actor_id, cause_chain, "
                       "subject_kind, subject_id, workspace_id, project_id, visibility, payload) "
                       "SELECT ?, type, at, actor_kind, actor_id, cause_chain, subject_kind, "
                       "subject_id, workspace_id, project_id, visibility, ? FROM events "
                       "WHERE json_extract(payload, '$.trigger') = 'retry' LIMIT 1",
                       ('junk-%d' % i, payload))
    db.writer.execute(junk, {})
    assert read(db)[0]['verification_attempts'] == 2
