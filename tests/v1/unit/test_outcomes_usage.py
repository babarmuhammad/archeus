"""`outcomes.usage` sums the usage ledger by account or mission (and, for a pass, as
`by_pass` does): an unreported figure stays None, never 0, `complete` holds only while every
row is the harness's total, and a row that names no account or mission is kept, not dropped."""

import pytest

from archeus.core.application import outcomes
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.infra.db import Database
from v1.unit.test_outcomes_cache import put, task


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def row(db, *, mission=None, task_id=None, source=None, basis='reported_total', **fields):
    """One ledger row: of an execution of *task_id* (a mission's), or of an own call about
    *source* (a mission id), or of neither."""
    rd = ids.new_id('route_decision')
    made = [entities.RouteDecision(
        id=rd, subject=Ref('task' if task_id else 'archeus_call', task_id or 'x'),
        purpose='planner', source=Ref('mission', source) if source else None)]
    x = None
    if task_id:
        x = ids.new_id('execution')
        made.append(entities.Execution(id=x, task_id=task_id, mission_id=mission, attempt=1,
                                       state='ENDED_OK', route_decision_id=rd, model='m',
                                       effort='high'))
    made.append(entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=x,
                                     route_decision_id=rd, basis=basis, **fields))
    put(db, *made)


def read(db, by):
    with db.read() as conn:
        return outcomes.usage(conn, by)


def test_an_account_sums_its_rows_and_an_unreported_figure_stays_none(db):
    row(db, account_ref='A', tokens_in=100, tokens_out=10, cost_usd=0.5)
    row(db, account_ref='A', tokens_in=50, cache_read=7)
    row(db, account_ref='B')
    a, b = read(db, 'account')
    assert a == {'account': 'A', 'calls': 2, 'tokens_in': 150, 'tokens_out': 10,
                 'cache_read': 7, 'cache_write': None, 'cost_usd': 0.5, 'complete': True}
    assert (b['account'], b['tokens_in'], b['cost_usd'], b['calls']) == ('B', None, None, 1)


def test_the_registered_account_wins_over_the_harness_account_and_none_sorts_last(db):
    acc = ids.new_id('account')
    put(db, entities.Account(id=acc, harness_id='fake', label='A', auth_kind='api_key'))
    row(db, account_id=acc, account_ref='home', tokens_in=1)
    row(db, tokens_in=2)
    assert [(r['account'], r['tokens_in']) for r in read(db, 'account')] == [(acc, 1), (None, 2)]


def test_one_partial_row_makes_the_group_incomplete(db):
    row(db, account_ref='A', tokens_in=1)
    row(db, account_ref='A', tokens_in=1, basis='partial')
    row(db, account_ref='B', tokens_in=1)
    a, b = read(db, 'account')
    assert (a['complete'], b['complete']) == (False, True)


def test_a_mission_sums_its_executions_and_the_own_calls_about_it(db):
    m1, t1 = task(db)
    m2, t2 = task(db)
    row(db, mission=m1, task_id=t1, tokens_in=10)
    row(db, mission=m2, task_id=t2, tokens_in=1)
    row(db, source=m1, tokens_in=5)
    got = {r['mission']: r for r in read(db, 'mission')}
    assert (got[m1]['tokens_in'], got[m1]['calls']) == (15, 2)
    assert got[m2]['tokens_in'] == 1


def test_an_own_call_about_no_mission_is_kept_under_none_not_dropped(db):
    m, t = task(db)
    row(db, mission=m, task_id=t, tokens_in=10)
    row(db, tokens_in=3)
    mission, other = read(db, 'mission')
    assert (mission['mission'], other['mission'], other['tokens_in']) == (m, None, 3)


@pytest.mark.parametrize('by', ['account', 'mission'])
def test_the_groups_sum_to_the_whole_ledger(db, by):
    m, t = task(db)
    row(db, mission=m, task_id=t, account_ref='A', tokens_in=10)
    row(db, source=m, account_ref='B', tokens_in=5)
    row(db, tokens_in=3)
    assert sum(r['tokens_in'] for r in read(db, by)) == 18
    assert sum(r['calls'] for r in read(db, by)) == 3


def test_a_pass_is_by_pass_and_anything_else_is_refused(db):
    with db.read() as conn:
        assert outcomes.usage(conn, 'pass') == outcomes.by_pass(conn) == []
        with pytest.raises(ValueError):
            outcomes.usage(conn, 'model')


def test_accounts_shown_alike_are_one_row(db):
    row(db, account_ref='C:/home/a', tokens_in=1)
    row(db, tokens_in=2)
    row(db, account_ref='B', tokens_in=4)
    with db.read() as conn:
        got = outcomes.usage(conn, 'account', lambda k: None if k and k.startswith('C:') else k)
    assert [(r['account'], r['calls'], r['tokens_in']) for r in got] == [('B', 1, 4), (None, 2, 3)]
