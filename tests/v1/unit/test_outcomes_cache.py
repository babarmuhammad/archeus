"""`outcomes.by_model` also sums cache reads and writes per group and splits them by
the route each ledger row names; an unreported figure stays None, never 0."""

import itertools

import pytest

from archeus.core.application import outcomes
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import Database, rows

ATTEMPTS = itertools.count(1)
ACTOR = Ref('user_device', ids.new_id('principal'))


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def put(db, *rows):
    def run(tx, **_):
        for r in rows:
            tx.insert(r, actor=ACTOR)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')), ACTOR,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    db.writer.execute(run, {})


def run(db, mid, tid, state='ENDED_OK', attempt=None, harness='fake', account='A', model='m',
        charged=None, **usage):
    """A finished execution of task *tid* routed to (harness, account, model), with a ledger
    row carrying *usage* (none: no row)."""
    rd, x = ids.new_id('route_decision'), ids.new_id('execution')
    row = [entities.RouteDecision(id=rd, subject=Ref('task', tid), task_id=tid, mission_id=mid,
                                  harness_id=harness, account_ref=account, model=model),
           entities.Execution(id=x, task_id=tid, mission_id=mid, attempt=attempt or next(ATTEMPTS), state=state,
                              route_decision_id=rd, model=model, effort='high', charged=charged)]
    if usage:
        row.append(entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=x,
                                        route_decision_id=rd, basis='reported_total', **usage))
    put(db, *row)
    return x


def plan_of(db, mid):
    with db.read() as conn:
        (r,) = rows.where(conn, entities.Plan, mission_id=mid)
    return r.entity.id


def task(db, mid=None):
    """A task of *mid* (a new mission, with its plan, when none is given): (mission id, task id)."""
    tid = ids.new_id('task')
    if mid is None:
        mid, pid = ids.new_id('mission'), ids.new_id('plan')
        put(db, entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                 objective='o', state='EXECUTING'),
            entities.Plan(id=pid, mission_id=mid, plan_version=1, state='APPROVED'))
    put(db, entities.Task(id=tid, plan_id=plan_of(db, mid), mission_id=mid, key=tid, title='T',
                          kind='code_change'))
    return mid, tid


def read(db):
    with db.read() as conn:
        return outcomes.by_model(conn)


def test_cache_totals_sum_what_was_reported_and_split_by_route(db):
    mid, tid = task(db)
    run(db, mid, tid, account='A', cache_read=100, cache_write=10, tokens_in=1)
    run(db, mid, tid, account='A', cache_read=50)
    run(db, mid, tid, account='B', cache_write=5)
    (g,) = read(db)
    assert (g['cache_read'], g['cache_write']) == (150, 15)
    assert g['by_route'] == [
        {'harness': 'fake', 'account_ref': 'A', 'model': 'm', 'cache_read': 150, 'cache_write': 10},
        {'harness': 'fake', 'account_ref': 'B', 'model': 'm', 'cache_read': None,
         'cache_write': 5}]


def test_nothing_reported_stays_none_never_zero(db):
    mid, tid = task(db)
    run(db, mid, tid, tokens_in=7)
    run(db, mid, tid)
    (g,) = read(db)
    assert (g['cache_read'], g['cache_write'], g['complete']) == (None, None, False)
    assert g['by_route'] == [{'harness': 'fake', 'account_ref': 'A', 'model': 'm',
                              'cache_read': None, 'cache_write': None}]


def test_a_reported_zero_is_kept(db):
    mid, tid = task(db)
    run(db, mid, tid, cache_read=0)
    assert read(db)[0]['cache_read'] == 0
