"""Effort per task end to end (resource-router §6): a task's effort reaches its
route decision and its execution beside the model, is clamped to what the
chosen model accepts, and the finished executions group by (kind, model,
effort) with their verdicts and usage. A task with none routes as it always did."""

from archeus.core.application import outcomes, verification as V
from archeus.core.domain import entities
from archeus.harnesses.base import ModelInfo
from archeus.harnesses.fake import FakeHarness

from v1.integration import test_routing
from v1.integration.test_policy import task
from v1.integration.test_provenance import _verify
from v1.integration.test_routing import Rig

r = test_routing.r
EFFORTS = ('low', 'medium', 'high')


def _rig(db, *models):
    rig = Rig(db, adapters=[FakeHarness(models=models or (ModelInfo('m-mid', 'mid'),),
                                        efforts=EFFORTS)])
    rig.account('A')
    return rig


def _run(rig, mid, key):
    out = rig.dispatch(mid, key)
    (e,) = rig.all(entities.Execution, id=out['execution_id'])
    return out, e


def test_a_tasks_effort_is_requested_routed_and_recorded_beside_the_model(db):
    rig = _rig(db)
    mid = rig.ready(task('t1', 'write_repo', min_model_tier='mid', effort='high'))
    out, e = _run(rig, mid, 't1')
    (rd,) = rig.rds()
    assert (e.model, e.effort, rd.model, rd.effort) == ('m-mid', 'high', 'm-mid', 'high')
    assert rd.requirements['effort'] == 'high'
    assert rd.requirements['_source']['effort'] == 'plan_contract'
    assert out['route_decision_id'] == rd.id


def test_a_task_without_an_effort_routes_with_none(db):
    rig = _rig(db)
    _, e = _run(rig, rig.ready(task('t1', 'write_repo', min_model_tier='mid')), 't1')
    (rd,) = rig.rds()
    assert (e.effort, rd.effort, rd.requirements['effort']) == (None, None, None)


def test_the_effort_is_clamped_to_what_the_chosen_model_accepts(db):
    rig = _rig(db, ModelInfo('m-mid', 'mid', efforts=('low', 'medium')))
    _, e = _run(rig, rig.ready(task('t1', 'write_repo', min_model_tier='mid', effort='high')), 't1')
    assert (e.model, e.effort) == ('m-mid', 'medium')


def test_the_plan_refuses_an_effort_off_the_scale(db):
    rig = _rig(db)
    mid = rig.mission('M')
    try:
        rig.propose(mid, task('t1', 'write_repo', effort='turbo'))
    except ValueError as err:
        assert 'unknown effort' in str(err)
    else:
        raise AssertionError('a plan with effort turbo was accepted')


def _finish(rig, effort, verdict, usage=None):
    mid = rig.ready(task('t1', 'write_repo', min_model_tier='mid', effort=effort))
    out, _ = _run(rig, mid, 't1')
    if verdict:
        rig.finish = lambda o: Rig.finish(rig, o, usage=usage)     # _verify ends it
        v, _ = _verify(rig, out)
        rig.do(V.record, missions=rig.missions, verification_id=v.id,
               checks=[{'name': 'tests', 'kind': 'command', 'result': verdict}])
    else:
        Rig.finish(rig, out, usage=usage)


def test_finished_executions_group_by_kind_model_and_effort_with_verdict_and_usage(db):
    rig = _rig(db)
    _finish(rig, 'low', 'pass', {'input_tokens': 10, 'output_tokens': 5, 'total_cost_usd': 0.25})
    _finish(rig, 'low', 'fail')
    _finish(rig, 'high', None)
    mid = rig.ready(task('t1', 'write_repo', min_model_tier='mid', effort='high'))
    rig.dispatch(mid)                                   # still running: not an outcome
    with rig.db.read() as conn:
        got = outcomes.by_model(conn)
    assert got == [
        {'kind': 'code_change', 'model': 'm-mid', 'effort': 'high', 'executions': 1,
         'passed': 0, 'failed': 0, 'unverified': 1, 'tokens': None, 'cost_usd': None,
         'complete': False},
        {'kind': 'code_change', 'model': 'm-mid', 'effort': 'low', 'executions': 2,
         'passed': 1, 'failed': 1, 'unverified': 0, 'tokens': 15, 'cost_usd': 0.25,
         'complete': False}]
