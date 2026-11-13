"""T-1167 · gap tests for archeus/core/application/outcomes.py lines 1-143 (tip 56d53504).

Closes the ten highest-risk uncovered branches of the slice (`_add`, `_count`,
`by_model`, `PASSES`, `_sum`, `by_pass`, `USAGE_BY`), ranked fail-closed and
denial first, then boundaries, then error paths:

 1. by_pass ignores a TASK-subject route decision even when its (purpose, source
    kind) is pass-shaped (outcomes.py:134-137) - cross-accounting denial.
 2. by_model keeps own-call ledger rows (execution_id None) out of every group
    (outcomes.py:56-58) - a row that belongs to no execution bills no one.
 3. a verifier retry event that binds to no execution (deleted verification, or a
    verification bound to nothing) attributes to no group (outcomes.py:43-49, 74-75).
 4. a `partial` basis ledger row makes by_model `complete` False yet still sums its
    figures (outcomes.py:78-79) - fail-closed on trust, not on data.
 5. only the latest terminal verification of an execution decides passed/failed
    (outcomes.py:41-42, 72); a non-terminal row never decides and never counts.
 6. `changes_requested` sums over every mission a group spans; an unreviewed
    mission contributes 0 and a group with no reviewed mission stays None
    (outcomes.py:50-51, 98-99).
 7. a task escalated to another model is `reworked` in each group it touches
    (outcomes.py:52-53, 64, 73).
 8. ledger rows sharing one route decision merge into one by_route bucket, and a
    None account_ref sorts with '' not by crash (outcomes.py:86-97).
 9. a reported zero token/cost figure in by_model stays 0, never None, and never
    drags `complete` down (outcomes.py:80-83).
10. by_pass skips an archeus_call route decision with no source instead of
    crashing on it (outcomes.py:134-137).

Probes replaced as already covered: uncharged excluded
(test_outcomes_rework.test_a_stop_that_spent_no_attempt_is_not_a_second_run),
INTENT-not-a-run (test_an_execution_still_pending_is_not_a_second_run), missing
ledger -> incomplete (test_outcomes_cache.test_nothing_reported_stays_none_never_zero),
by_pass non-pass exclusion and consolidate (test_outcomes_by_pass), bound retries
and zero cache figures (test_outcomes_rework, test_outcomes_cache).

All fakes stay under tmp_path via the archeus_home fixture; no real OS, network or
adapter is touched.
"""

import pytest

from archeus.core.application import outcomes
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database

from .test_outcomes_cache import ACTOR, plan_of, put, read, run, task


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def passes(db):
    with db.read() as conn:
        return outcomes.by_pass(conn)


def own_call(db, *, purpose, source_kind, source_id=None, **figures):
    """An archeus_call route decision with a ledger row (no execution: ADR-0022);
    source_kind None: the decision carries no source at all."""
    rd = ids.new_id('route_decision')
    source = Ref(source_kind, ids.new_id(source_kind)) if source_kind else None
    put(db, entities.RouteDecision(id=rd, subject=Ref('archeus_call', purpose),
                                   purpose=purpose, source=source),
        entities.UsageLedger(id=ids.new_id('usage_ledger'), route_decision_id=rd,
                             basis='reported_total', **figures))


def retry_event(db, verification_id):
    """The event a verifier retry leaves (writer.transition's payload), written raw:
    the read joins on this event row, so a raw append is the row the code sees."""
    def add(tx, **_):
        tx.append(new_event('verification.state_changed',
                            Ref('verification', verification_id), ACTOR,
                            payload={'from': 'ERROR', 'to': 'PENDING',
                                     'trigger': 'retry', 'reason': 'test'},
                            workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(add, {})


def verified_once_with_a_retry(db, x, tid, mid):
    """One verification of execution *x* that crashed once and was retried: the
    ERROR -> PENDING edge has trigger 'retry' (states.py verification machine)."""
    v = ids.new_id('verification')
    put(db, entities.Verification(id=v, subject=Ref('task', tid), verifier='code',
                                  execution_id=x, plan_id=plan_of(db, mid), state='ERROR'))

    def move(tx, **_):
        for to in ('PENDING', 'RUNNING', 'PASSED'):
            tx.transition(entities.Verification, v, to, actor=ACTOR, reason='test')
    db.writer.execute(move, {})
    return v


def review(db, mid, verdict):
    put(db, entities.Review(id=ids.new_id('review'), mission_id=mid, reviewer='r',
                            verdict=verdict, plan_id=plan_of(db, mid)))


def ledger_row(db, *, execution_id, rd, basis='reported_total', **figures):
    put(db, entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=execution_id,
                                 route_decision_id=rd, basis=basis, **figures))


# 1 · denial: a task's route decision is never a learning pass
def test_by_pass_never_counts_a_task_route_decision_even_with_a_pass_purpose(db):
    """Catch: dropping `r.entity.subject.kind == 'archeus_call'` at outcomes.py:136
    bills an execution's lesson-shaped call to the 'lessons' pass."""
    mid, tid = task(db)
    rd = ids.new_id('route_decision')
    put(db, entities.RouteDecision(id=rd, subject=Ref('task', tid), task_id=tid,
                                   mission_id=mid, purpose='lesson',
                                   source=Ref('mission', mid)),
        entities.Execution(id=ids.new_id('execution'), task_id=tid, mission_id=mid,
                           attempt=1, state='ENDED_OK', route_decision_id=rd,
                           model='m', effort='high'))
    ledger_row(db, execution_id=None, rd=rd, tokens_in=9)
    own_call(db, purpose='lesson', source_kind='mission', tokens_in=1)
    assert [(g['pass'], g['calls'], g['tokens_in']) for g in passes(db)] == [('lessons', 1, 1)]


# 2 · denial: an own-call ledger row (no execution) bills no outcome group
def test_by_model_leaves_own_call_usage_out_of_every_group(db):
    """Catch: inverting `if r.entity.execution_id:` at outcomes.py:57 drops the
    execution's own rows (tokens None, by_route gone) and the read-only promise
    (events written) fails here too."""
    mid, tid = task(db)
    run(db, mid, tid, tokens_in=1, cache_read=1)
    own_call(db, purpose='planner', source_kind='mission',
             tokens_in=999, cost_usd=9, cache_read=500)
    with db.read() as conn:
        first = outcomes.by_model(conn)
        events = conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        again = outcomes.by_model(conn)
    assert first == again                      # reading invents nothing, mutates nothing
    (g,) = first
    assert (g['tokens'], g['cost_usd'], g['cache_read']) == (1, None, 1)
    assert g['by_route'] == [{'harness': 'fake', 'account_ref': 'A', 'model': 'm',
                              'cache_read': 1, 'cache_write': None}]
    with db.read() as conn:
        assert conn.execute('SELECT COUNT(*) FROM events').fetchone()[0] == events


# 3 · denial: a retry that binds to no execution counts nowhere
def test_by_model_counts_no_retry_that_binds_to_no_execution(db):
    """Catch: losing the `of_check.get(v)` join at outcomes.py:48 (or attributing
    retries globally) would read verification_attempts 3 instead of 1, and losing
    `if e.id in checked` at :74 would hide the unverified second execution."""
    mid, tid = task(db)
    x1 = run(db, mid, tid)
    run(db, mid, tid)
    verified_once_with_a_retry(db, x1, tid, mid)
    retry_event(db, ids.new_id('verification'))               # deleted verification
    v = ids.new_id('verification')
    put(db, entities.Verification(id=v, subject=Ref('task', tid), verifier='code',
                                  execution_id=None, plan_id=plan_of(db, mid),
                                  state='PENDING'))
    retry_event(db, v)                                         # retry of an unbound check
    (g,) = read(db)
    assert (g['executions'], g['reworked']) == (2, 2)
    assert (g['passed'], g['unverified'], g['verification_attempts']) == (1, 1, 1)


# 4 · fail-closed: a partial basis is trusted for figures, never for completeness
def test_by_model_a_partial_basis_row_keeps_figures_but_not_complete(db):
    """Catch: inverting `u.basis == 'reported_total'` at outcomes.py:78 leaves
    complete True on a lower-bound row, or dropping the loop (:79) loses the figures."""
    mid, tid = task(db)
    rd = ids.new_id('route_decision')
    x = ids.new_id('execution')
    put(db, entities.RouteDecision(id=rd, subject=Ref('task', tid), task_id=tid,
                                  mission_id=mid, harness_id='fake', account_ref='A',
                                  model='m'),
        entities.Execution(id=x, task_id=tid, mission_id=mid, attempt=1,
                           state='ENDED_OK', route_decision_id=rd, model='m',
                           effort='high'))
    ledger_row(db, execution_id=x, rd=rd, basis='partial', tokens_in=5,
               cost_usd=0.1, cache_read=2)
    (g,) = read(db)
    assert g['complete'] is False
    assert (g['tokens'], g['cost_usd'], g['cache_read']) == (5, 0.1, 2)
    assert g['by_route'] == [{'harness': 'fake', 'account_ref': 'A', 'model': 'm',
                              'cache_read': 2, 'cache_write': None}]


# 5 · boundary: the latest terminal verification is the verdict, one per execution
def test_by_model_only_the_latest_terminal_verification_decides(db):
    """Catch: keeping the FIRST terminal row (setdefault instead of assignment at
    outcomes.py:41) or counting each terminal row (no dict, :72) reads passed 1 /
    failed 1 or failed+passed == 2; a non-terminal row deciding would flip failed."""
    mid, tid = task(db)
    x = run(db, mid, tid)
    for state in ('PASSED', 'FAILED'):
        put(db, entities.Verification(id=ids.new_id('verification'),
                                      subject=Ref('task', tid), verifier='code',
                                      execution_id=x, plan_id=plan_of(db, mid),
                                      state=state))
    put(db, entities.Verification(id=ids.new_id('verification'),
                                  subject=Ref('task', tid), verifier='code',
                                  execution_id=x, plan_id=plan_of(db, mid),
                                  state='ERROR'))               # never decides, never counts
    (g,) = read(db)
    assert (g['executions'], g['passed'], g['failed'], g['unverified']) == (1, 0, 1, 0)
    assert g['verification_attempts'] == 0


# 6 · boundary: reviews sum over the whole group, None while no mission was reviewed
def test_by_model_changes_requested_sums_over_both_missions_of_a_group(db):
    """Catch: a per-mission instead of per-group sum, or losing `reviews.get(m, 0)`
    at outcomes.py:99, miscounts the two-mission group; losing `if any(m in reviews)`
    (:98) turns the never-reviewed group's None into 0."""
    m1, t1 = task(db)
    m2, t2 = task(db)                                          # same kind/model/effort group
    run(db, m1, t1)
    run(db, m2, t2)
    review(db, m1, 'changes_requested')
    review(db, m1, 'changes_requested')
    review(db, m1, 'accept')                                   # only the verdict counts
    m3, t3 = task(db)
    run(db, m3, t3, model='other')                             # second group, no reviews
    got = {g['model']: g for g in read(db)}
    assert got['m']['changes_requested'] == 2
    assert got['other']['changes_requested'] is None


# 7 · boundary: an escalation is a rework in every group it lands in
def test_by_model_an_escalated_task_is_reworked_in_each_group_it_touches(db):
    """Catch: counting runs per group instead of per task (`key=lambda e: e.task_id`
    at outcomes.py:52) makes each single-execution group read reworked 0."""
    mid, tid = task(db)
    run(db, mid, tid, model='small')
    run(db, mid, tid, model='big')
    got = {g['model']: g for g in read(db)}
    assert [(g['executions'], g['reworked']) for g in got.values()] == [(1, 1), (1, 1)]


# 8 · boundary: rows sharing a route merge; a None account sorts with ''
def test_by_model_rows_sharing_a_route_decision_merge_and_none_account_sorts_first(db):
    """Catch: keying the by_route bucket per ledger row instead of per route tuple
    (outcomes.py:90-92) splits the None-account bucket in two; dropping the `x or ''`
    sort key (:97) raises TypeError on the None account_ref."""
    mid, tid = task(db)
    rd1, rd2, x = (ids.new_id(k) for k in ('route_decision',) * 2 + ('execution',))
    put(db, entities.RouteDecision(id=rd1, subject=Ref('task', tid), task_id=tid,
                                   mission_id=mid, harness_id='fake',
                                   account_ref=None, model='m'),
        entities.RouteDecision(id=rd2, subject=Ref('task', tid), task_id=tid,
                               mission_id=mid, harness_id='fake', account_ref='A',
                               model='m'),
        entities.Execution(id=x, task_id=tid, mission_id=mid, attempt=1,
                           state='ENDED_OK', route_decision_id=rd1, model='m',
                           effort='high'))
    ledger_row(db, execution_id=x, rd=rd1, cache_read=10)      # same route, second lookup
    ledger_row(db, execution_id=x, rd=rd1, cache_read=5, cache_write=2)
    ledger_row(db, execution_id=x, rd=rd2, cache_read=7)
    (g,) = read(db)
    assert (g['cache_read'], g['cache_write']) == (22, 2)
    assert [(b['account_ref'], b['cache_read'], b['cache_write'])
            for b in g['by_route']] == [(None, 15, 2), ('A', 7, None)]


# 9 · boundary: a reported zero is a figure, not an absence
def test_by_model_a_reported_zero_token_or_cost_is_kept_not_none(db):
    """Catch: inverting `is not None` at outcomes.py:80/82 reads a reported zero as
    missing (tokens None), and losing the bool algebra at :78 reads it as incomplete."""
    mid, tid = task(db)
    run(db, mid, tid, tokens_in=0, cost_usd=0)
    run(db, mid, tid, model='other')                           # nothing reported at all
    got = {g['model']: g for g in read(db)}
    assert (got['m']['tokens'], got['m']['cost_usd'], got['m']['complete']) == (0, 0, True)
    assert (got['other']['tokens'], got['other']['cost_usd']) == (None, None)


# 10 · error path: a source-less archeus_call decision is skipped, not crashed on
def test_by_pass_a_route_decision_without_a_source_is_not_a_pass(db):
    """Catch: dropping the `r.entity.source` guard at outcomes.py:136 raises
    AttributeError on None.kind; a truthiness inversion hides the real pass too."""
    own_call(db, purpose='knowledge_extraction', source_kind='repository_inspection',
             tokens_in=1)
    rd = ids.new_id('route_decision')
    put(db, entities.RouteDecision(id=rd, subject=Ref('archeus_call', 'knowledge_extraction'),
                                   purpose='knowledge_extraction', source=None))
    ledger_row(db, execution_id=None, rd=rd, tokens_in=9)      # would be a 'knowledge' row
    assert [(g['pass'], g['calls'], g['tokens_in']) for g in passes(db)] == [('knowledge', 1, 1)]
