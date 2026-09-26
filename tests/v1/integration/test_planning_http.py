"""P8 over HTTP (p8-design-gate §19, H01–H04): the two plan reads, the mission
view's plan fields and `health.plan`, on the real Core runtime with the planning
worker — the routes are thin, so this checks what the HTTP layer adds: the
shapes, a 404 for what does not exist, and that no plan route takes a command."""

import time

from archeus.core import ports, runtime
from archeus.harnesses.fake import FakeCaller
from v1.judge.http import TempCore
from v1.integration.test_planning import ONE, answer, task


def _core(archeus_home, *plans):
    fake = FakeCaller('fake', replies={'planner': [{'parsed': p} for p in plans]})
    # the stub policy asks, so a planned mission waits in APPROVAL_REQUIRED
    return TempCore(archeus_home, ports=runtime.Ports(
        callers=[fake], policy=ports.FixedPolicy('ASK'),
        preference=ports.FixedOwnCallPreference())).start()


def _planned(tc, mid, version=1, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        m = tc.http('GET', '/v1/missions/%s' % mid).json()
        if m.get('plan_version') == version and m['state'] == 'APPROVAL_REQUIRED':
            return m
        time.sleep(0.05)
    raise AssertionError('mission %s was not planned (v%d)' % (mid, version))


def _mission(tc, key='m1'):
    return tc.http('POST', '/v1/missions', body={
        'title': 'Ship it', 'objective': 'Ship the thing.', 'idempotency_key': key}).json()['id']


def test_h01_the_mission_view_carries_the_plan_in_force_and_health_the_worker(archeus_home):
    tc = _core(archeus_home, ONE)
    try:
        mid = _mission(tc)
        m = _planned(tc, mid)
        assert m['plan_id'].startswith('pln_') and m['planning_blocked'] is None
        health = tc.http('GET', '/v1/health').json()
        assert health['plan']['state'] in ('idle', 'running')
        assert health['core']['ports'] == 'stub'
    finally:
        tc.stop()


def test_h02_a_missions_plan_and_one_exact_version(archeus_home):
    tc = _core(archeus_home, answer(task('a'), task('b', depends_on=['a'])))
    try:
        mid = _mission(tc)
        m = _planned(tc, mid)
        got = tc.http('GET', '/v1/missions/%s/plan' % mid).json()
        assert got['mission_id'] == mid and len(got['versions']) == 1
        plan = got['plan']
        assert (plan['id'], plan['state'], plan['estimated_cost']) == (
            m['plan_id'], 'PROPOSED', 'low')
        assert [t['key'] for t in plan['tasks']] == ['t1', 't2']
        assert plan['waves'] == [['t1'], ['t2']] and plan['current'] is True
        exact = tc.http('GET', '/v1/plans/%s' % plan['id']).json()
        assert exact['digest'] == plan['digest'] == got['versions'][0]['digest']
    finally:
        tc.stop()


def test_h03_what_does_not_exist_is_a_404(archeus_home):
    tc = _core(archeus_home, ONE)
    try:
        assert tc.http('GET', '/v1/plans/pln_01M3DGX0000000000000000000').status == 404
        assert tc.http('GET', '/v1/missions/msn_01M3DGX0000000000000000000/plan').status == 404
        mid = tc.http('POST', '/v1/missions', body={
            'title': 'x', 'objective': 'y', 'idempotency_key': 'k'}).json()['id']
        assert tc.http('GET', '/v1/missions/%s/plan' % mid).status == 200
    finally:
        tc.stop()


def test_h04_no_plan_route_takes_a_command(archeus_home):
    tc = _core(archeus_home, ONE)
    try:
        mid = _mission(tc)
        m = _planned(tc, mid)
        for path in ('/v1/plans/%s' % m['plan_id'], '/v1/missions/%s/plan' % mid,
                     '/v1/plans/%s/edit' % m['plan_id']):
            r = tc.http('POST', path, body={'idempotency_key': 'z'})
            assert r.status in (404, 405), (path, r.status)
        assert tc.http('GET', '/v1/plans/%s' % m['plan_id']).json()['state'] == 'PROPOSED'
    finally:
        tc.stop()
