"""`outcomes.by_context` splits the outcome counts by the size band of the context package a
mission points at. The band is what was assembled, not what the agent saw; an unreported
figure is None, never 0."""

import pytest

from archeus.core.application import outcomes
from archeus.core.domain import entities, ids
from archeus.infra.db import Database

from .test_outcomes_cache import put, run


@pytest.fixture
def db(archeus_home):
    d = Database.open()
    yield d
    d.close()


def mission(db, used=None, package=True, budget=True):
    """(mission id, task id) of a mission whose package reports *used* tokens (package: False,
    budget: False: no package, a package with no budget)."""
    mid, pid, tid = (ids.new_id(k) for k in ('mission', 'plan', 'task'))
    pkg = ids.new_id('context_package')
    extra = []
    if package:
        extra.append(entities.ContextPackage(
            id=pkg, workspace_id=ids.GLOBAL_WORKSPACE, subject_kind='mission', subject_id=mid,
            budget={'limit_tokens': 9999, 'used_tokens': used} if budget else None))
    put(db, *extra, entities.Mission(id=mid, workspace_id=ids.GLOBAL_WORKSPACE, title='M',
                                     objective='o', state='EXECUTING',
                                     context_package_id=pkg if package else None),
        entities.Plan(id=pid, mission_id=mid, plan_version=1, state='APPROVED'),
        entities.Task(id=tid, plan_id=pid, mission_id=mid, key=tid, title='T', kind='code_change'))
    return mid, tid


def read(db):
    with db.read() as conn:
        return outcomes.by_context(conn)


def bands(db):
    return {g['context']: g for g in read(db)}


@pytest.mark.parametrize('used,band', [(0, 'none'), (1, 'under 1k'), (999, 'under 1k'),
                                       (1000, '1k to 4k'), (4000, '1k to 4k'),
                                       (4001, 'over 4k')])
def test_a_package_size_lands_in_its_band_at_the_edges(db, used, band):
    run(db, *mission(db, used))
    assert [g['context'] for g in read(db)] == [band]


def test_a_mission_without_a_package_or_a_figure_has_band_none_not_the_none_band(db):
    run(db, *mission(db, package=False))
    run(db, *mission(db, budget=False))
    run(db, *mission(db, 0))
    (a, b) = read(db)
    assert (a['context'], a['executions']) == (None, 2)
    assert (b['context'], b['executions']) == ('none', 1)


def test_counts_and_sample_size_per_band(db):
    small, st = mission(db, 500)
    big, bt = mission(db, 6000)
    for _ in range(2):
        run(db, small, st)
    run(db, big, bt, state='ENDED_ERROR')
    run(db, big, bt, charged=False)
    g = bands(db)
    assert (g['under 1k']['executions'], g['over 4k']['executions']) == (2, 1)
    assert g['over 4k']['unverified'] == 1


def test_tokens_and_cost_sum_what_was_reported_and_stay_none_otherwise(db):
    mid, tid = mission(db, 10)
    other, otid = mission(db, 2000)
    run(db, mid, tid, tokens_in=5, tokens_out=7, cost_usd=0.5)
    run(db, mid, tid, tokens_in=1, cost_usd=0.25)
    run(db, other, otid, tokens_in=3)
    run(db, *mission(db, 5000))
    g = bands(db)
    assert (g['under 1k']['tokens'], g['under 1k']['cost_usd']) == (13, 0.75)
    assert (g['1k to 4k']['tokens'], g['1k to 4k']['cost_usd']) == (3, None)
    assert (g['over 4k']['tokens'], g['over 4k']['cost_usd']) == (None, None)


def test_a_group_is_per_kind_model_and_effort_as_well(db):
    mid, tid = mission(db, 10)
    run(db, mid, tid, model='a')
    run(db, mid, tid, model='b')
    assert [g['model'] for g in read(db)] == ['a', 'b']


def test_passed_and_failed_are_split_per_band(db):
    from archeus.core.domain.values import Ref
    from .test_outcomes_cache import plan_of
    small, st = mission(db, 500)
    big, bt = mission(db, 6000)
    for mid, tid, state in ((small, st, 'PASSED'), (big, bt, 'FAILED')):
        x = run(db, mid, tid, tokens_in=1)
        put(db, entities.Verification(id=ids.new_id('verification'), subject=Ref('task', tid),
                                      verifier='code', execution_id=x, plan_id=plan_of(db, mid),
                                      state=state))
    run(db, small, st, tokens_in=1)
    g = bands(db)
    assert [g['under 1k'][k] for k in ('passed', 'failed', 'unverified')] == [1, 0, 1]
    assert [g['over 4k'][k] for k in ('passed', 'failed', 'unverified')] == [0, 1, 0]


def test_a_band_is_complete_only_while_every_execution_reported_its_total(db):
    small, st = mission(db, 500)
    big, bt = mission(db, 6000)
    run(db, small, st, tokens_in=1)
    run(db, big, bt, tokens_in=1)
    run(db, big, bt)
    g = bands(db)
    assert (g['under 1k']['complete'], g['over 4k']['complete']) == (True, False)
