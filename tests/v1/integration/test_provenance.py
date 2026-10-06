"""P13 model/harness provenance (p13-design-gate §22, §26, M01-M06): what ran
is chosen by the router from rows, recorded on the execution, and copied onto
the verification from those rows, never from what the stream claims.

M01, M03-M05 run on test_routing's rig (the real router and writer, fake
harnesses as instances); M02 and M06 run the in-process Core with the real
verification worker, so the copy is the one the worker makes."""

from archeus.core.application import verification as V
from archeus.core.domain import entities
from archeus.core.domain.values import Ref
from archeus.harnesses.base import ModelInfo
from archeus.harnesses.fake import FakeHarness

from v1.integration import test_routing, test_verification
from v1.integration.test_policy import task
from v1.integration.test_routing import Rig, _limited
from v1.integration.test_verification import FIX, _mission, _t, _task, _vs, _write, pump
from v1.judge.support import Rig as JudgeRig

r, core = test_routing.r, test_verification.core       # the two rigs' fixtures

SMALL, LARGE = ModelInfo('m-small', 'small'), ModelInfo('m-large', 'large')


def _execution(r, out):
    return r.all(entities.Execution, id=out['execution_id'])[0]


def _verify(r, out):
    """The execution ends; a verification of it starts as the worker starts one."""
    r.finish(out)
    e = _execution(r, out)
    return r.all(entities.Verification, id=r.do(
        V.start, missions=r.missions, subject=Ref('task', e.task_id), verifier='code',
        execution_id=e.id)['verification_id'])[0], e


def test_M01_two_tasks_with_different_tiers_run_on_different_models(db):
    r = Rig(db, adapters=[FakeHarness('fake-s', models=(SMALL,)),
                          FakeHarness('fake-l', models=(LARGE,))])
    mid = r.ready(task('t1', 'write_repo', min_model_tier='small'),
                  task('t2', 'write_repo', min_model_tier='large'))
    e1, e2 = (_execution(r, r.dispatch(mid, k)) for k in ('t1', 't2'))
    assert (e1.harness_id, e1.model) == ('fake-s', 'm-small')    # the smallest that fits
    assert (e2.harness_id, e2.model) == ('fake-l', 'm-large')


def test_M03_one_model_id_on_two_harnesses_stays_two_harnesses(db):
    same = ModelInfo('m-shared', 'large')
    r = Rig(db, adapters=[FakeHarness('fake-a', models=(same,)),
                          FakeHarness('fake-b', models=(same,))])
    out = r.dispatch(r.ready(task('t1', 'write_repo', min_model_tier='large')))
    (rd,) = r.rds()
    seen = {(c['harness'], c['model']) for c in rd.candidates}
    assert seen == {('fake-a', 'm-shared'), ('fake-b', 'm-shared')}
    v, e = _verify(r, out)
    assert e.harness_id in ('fake-a', 'fake-b')
    assert (v.performed_by['harness_id'], v.performed_by['model']) == (e.harness_id, 'm-shared')


def test_M04_two_models_on_one_harness_stay_two_models(db):
    r = Rig(db, adapters=[FakeHarness(models=(SMALL, LARGE))])
    mid = r.ready(task('t1', 'write_repo', min_model_tier='small'),
                  task('t2', 'write_repo', min_model_tier='large'))
    e1, e2 = (_execution(r, r.dispatch(mid, k)) for k in ('t1', 't2'))
    assert e1.harness_id == e2.harness_id == 'fake'
    assert (e1.model, e2.model) == ('m-small', 'm-large')


def test_M05_a_fallback_is_its_own_route_decision_and_the_verification_names_it(r):
    a, b = _limited(r, 'allow')
    out = r.dispatch(r.ready())
    (rd,) = r.rds()
    assert (rd.result, list(rd.fallback_from), rd.selected) == ('fallback', [a], b)
    v, e = _verify(r, out)
    assert e.route_decision_id == rd.id and e.account_id == b
    assert (v.performed_by['route_decision_id'], v.performed_by['account_id']) == (rd.id, b)
    # `ask` and `deny` never run silently elsewhere: test_routing I-F2..I-F4


def test_M02_the_executions_identity_is_copied_onto_its_verification(core):
    rig = JudgeRig(core)
    _repo, mid = _mission(core, rig, steps=[_write(FIX), {'emit': {'type': 'result',
                                                                   'summary': 'done'}}])
    pump(core, lambda: _t(core, mid) == 'SUCCEEDED')
    (v,) = _vs(core, mid, 'task')
    with core._core().read() as conn:
        e = V.verified_execution(conn, _task(core, mid))
    assert v['execution_id'] == e.id
    assert {k: v['performed_by'][k] for k in ('harness_id', 'account_id', 'model', 'effort',
                                              'route_decision_id', 'session_id')} == {
        'harness_id': e.harness_id, 'account_id': e.account_id, 'model': e.model,
        'effort': e.effort, 'route_decision_id': e.route_decision_id,
        'session_id': e.session_id}
    assert e.harness_id == 'fake' and e.model and e.route_decision_id


def test_M06_a_reported_model_other_than_the_routed_one_is_recorded_not_failed(core):
    rig = JudgeRig(core)
    _repo, mid = _mission(core, rig, steps=[
        {'emit': {'type': 'system', 'model': 'someone-else'}},    # the stream's claim
        _write(FIX), {'emit': {'type': 'result', 'summary': 'done'}}])
    pump(core, lambda: _t(core, mid) == 'SUCCEEDED')
    (v,) = _vs(core, mid, 'task')
    assert v['state'] == 'PASSED'                          # provenance, not correctness
    routed = v['performed_by']['model']
    assert routed and routed != 'someone-else'             # never taken from the claim
    assert v['provenance'] == {'routed_model': routed, 'reported_model': 'someone-else',
                               'match': False}
