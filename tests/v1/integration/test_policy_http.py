"""P9 over HTTP (p9-design-gate §18, §21.2 H-*): the routes, their scopes,
idempotency and error codes, against the real Core runtime (the P3.5 stub
brain plans the skeleton plan; the policy is the real engine)."""

import time

import pytest

from archeus.core import engine, ports, runtime
from archeus.core.domain import ids

DEPLOY = dict(engine.SKELETON_PLAN, tasks=[dict(engine.SKELETON_PLAN['tasks'][0],
                                                 action_classes=['deploy'])])


def _post(tc, path, body, token=None):
    return tc.http('POST', path, body=dict(body, idempotency_key=body.get(
        'idempotency_key') or ids.new_ulid()), **({'token': token} if token else {}))


def _wait(fn, what, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = fn()
        if got:
            return got
        time.sleep(0.05)
    raise AssertionError('timed out: %s' % what)


def _pending(tc, mid):
    def got():
        ap = tc.http('GET', '/v1/approvals?state=PENDING&mission=%s' % mid).json()['approvals']
        return ap[0] if ap else None
    return _wait(got, 'an approval for %s' % mid)


@pytest.fixture
def deploy_core(archeus_home):
    from v1.judge.http import TempCore
    core = TempCore(archeus_home, ports=runtime.Ports(brain=ports.FixedPlanBrain(DEPLOY))).start()
    yield core
    core.stop()


def _mission(tc):
    return _post(tc, '/v1/missions', {'title': 'Ship', 'objective': 'deploy it'}).json()['id']


def test_H01_approval_round_trip_echoes_the_hash_and_is_idempotent(deploy_core):
    tc = deploy_core
    mid = _mission(tc)
    a = _pending(tc, mid)
    assert a['eligible'] and a['step_up'] and a['presented']['what'][0]['class'] == 'deploy'
    bad = _post(tc, '/v1/approvals/%s/decide' % a['id'],
                {'decision': 'approve', 'action_hash': '0' * 64})
    assert (bad.status, bad.json()['error']) == (422, 'guard_failed')
    body = {'decision': 'approve', 'action_hash': a['action_hash'], 'idempotency_key': 'k1'}
    first = _post(tc, '/v1/approvals/%s/decide' % a['id'], body)
    assert first.status == 200 and first.json()['state'] == 'APPROVED'
    assert _post(tc, '/v1/approvals/%s/decide' % a['id'], body).json() == first.json()
    other = _post(tc, '/v1/approvals/%s/decide' % a['id'],
                  dict(body, decision='reject', idempotency_key='k2'))
    assert (other.status, other.json()['error']) == (422, 'invalid_transition')
    _wait(lambda: tc.http('GET', '/v1/missions/%s' % mid).json()['state'] == 'COMPLETED',
          'the approved mission runs')
    decisions = tc.http('GET', '/v1/policy-decisions?mission=%s' % mid).json()
    outcomes = [d['outcome'] for d in decisions['policy_decisions']]
    assert 'needs_approval' in outcomes and 'approved' in outcomes and 'covered' in outcomes
    one = decisions['policy_decisions'][0]
    assert tc.http('GET', '/v1/policy-decisions/%s' % one['id']).json()['id'] == one['id']


def test_H02_a_read_only_device_and_a_brain_cannot_decide(deploy_core):
    tc = deploy_core
    mid = _mission(tc)
    a = _pending(tc, mid)
    code = tc.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    browser = tc.http('POST', '/v1/devices/launch/redeem',
                      body={'code': code, 'platform': 'web'}).json()['token']
    got = _post(tc, '/v1/approvals/%s/decide' % a['id'],
                {'decision': 'approve', 'action_hash': a['action_hash']}, token=browser)
    assert (got.status, got.json()['error']) == (403, 'scope_required')
    assert tc.http('GET', '/v1/approvals/%s' % a['id'], token=browser).status == 200


def test_H03_a_deny_found_at_approve_is_423_and_recorded(deploy_core):
    tc = deploy_core
    mid = _mission(tc)
    a = _pending(tc, mid)
    r = _post(tc, '/v1/policies/rules', {'scope_level': 'USER', 'action_class': 'deploy',
                                          'decision': 'DENY'})
    assert r.status == 200 and r.json()['revision'] == 1
    got = _post(tc, '/v1/approvals/%s/decide' % a['id'],
                {'decision': 'approve', 'action_hash': a['action_hash']})
    assert (got.status, got.json()['error']) == (423, 'policy_denied')
    pid = got.json()['detail']['policy_decision_id']
    assert tc.http('GET', '/v1/policy-decisions/%s' % pid).json()['decision'] == 'DENY'
    pol = tc.http('GET', '/v1/policies').json()
    assert [x['decision'] for x in pol['rules']] == ['DENY'] and pol['user_profile'] == 'standard'
    retired = _post(tc, '/v1/policies/rules/%s/retire' % r.json()['id'], {})
    assert retired.status == 200 and retired.json()['retired_at']


def test_H04_request_changes_replans_and_simulate_writes_nothing(deploy_core):
    tc = deploy_core
    mid = _mission(tc)
    a = _pending(tc, mid)
    rej = _post(tc, '/v1/approvals/%s/decide' % a['id'],
                {'decision': 'request_changes', 'action_hash': a['action_hash']})
    assert rej.status == 200 and rej.json()['mission']['state'] == 'PLANNING'
    b = _wait(lambda: [x for x in tc.http('GET', '/v1/approvals?state=PENDING').json()[
        'approvals'] if x['id'] != a['id']], 'the second plan asks')[0]
    assert b['plan_id'] != a['plan_id']
    head = tc.http('GET', '/v1/events').json()['events'][-1]['seq']
    sim = tc.http('POST', '/v1/policies/simulate', body={
        'action': {'class': 'git_push', 'target': 'x'}, 'mission_id': mid,
        'extra_rules': [{'scope_level': 'MISSION', 'scope_ref': mid, 'action_class': 'git_push',
                         'decision': 'ALLOW'}]})
    assert sim.status == 200 and sim.json()['decision'] == 'ALLOW' and sim.json()['simulated']
    # the locked prod floor answers a deploy whatever a mission rule says
    floor = tc.http('POST', '/v1/policies/simulate', body={
        'action': {'class': 'deploy', 'target': 'x'}, 'mission_id': mid,
        'extra_rules': [{'scope_level': 'MISSION', 'scope_ref': mid, 'action_class': 'deploy',
                         'decision': 'ALLOW'}]}).json()
    assert floor['decision'] == 'ASK' and 'builtin:floor:deploy-prod' in floor['effective']
    old = _post(tc, '/v1/approvals/%s/decide' % a['id'],
                {'decision': 'approve', 'action_hash': a['action_hash']})
    assert (old.status, old.json()['error']) == (422, 'invalid_transition')
    assert tc.http('GET', '/v1/events').json()['events'][-1]['seq'] == head


_READ = {'class': 'read', 'target': 'x'}


_WS = {'scope_level': 'WORKSPACE', 'scope_ref': 'ws_global'}
_AWB = dict(_WS, decision='ALLOW_WITHIN_BOUNDARY')
_PUSH = {'class': 'git_push', 'target': 'a', 'host': 'github.com', 'branch': 'main'}


@pytest.mark.parametrize('body,why', [
    ({'action': {}}, 'not well formed'), ({'action': {'nonsense': 1}}, 'not well formed'),
    ({'action': _READ, 'extra_rules': [{}]}, 'scope_level'),
    ({'action': _READ, 'extra_rules': [dict(_WS, action_class='read', decision='MAYBE')]},
     'decision'),
    ({'action': _READ, 'extra_rules': [dict(_WS, action_class='read', decision='ALLOW',
                                            expires_at=5)]}, 'expires_at'),
    ({'action': dict(_READ, host=['github.com'])}, 'host'),
    *[({'action': a, 'extra_rules': [dict(_AWB, action_class=a['class'], boundary={k: v})]},
       'boundary.' + k) for a, k, v in [
        ({'class': 'write_repo', 'target': 'a', 'paths': ['a']}, 'paths', 5),
        ({'class': 'write_repo', 'target': 'a', 'paths': ['a']}, 'paths', None),
        (_PUSH, 'hosts', 5), (_PUSH, 'branches', 5),
        ({'class': 'deploy', 'target': 'a', 'environment': 'dev'}, 'environments', 5),
        ({'class': 'write_repo', 'target': 'a', 'paths': ['a']}, 'max_cost_band', 'huge')]]])
def test_H04b_a_malformed_simulated_action_or_rule_is_a_400_not_a_500(tc, body, why):
    """Found by tools/fuzz_p20.py (P20 D12): the action and the rules are built
    from the request's own dicts, so a missing or unknown field is the
    request's fault. A rule is checked as create_rule would check it (the same
    PolicyRule), so a decision outside the vocabulary, an expiry that is not
    a timestamp or a boundary value check_boundary cannot read never reaches
    the engine (T-094 review, finding 1; re-review, finding 1). The rules are
    WORKSPACE-scoped so each is refused on the check it names, not on a
    missing owner."""
    r = tc.http('POST', '/v1/policies/simulate', body=body)
    assert (r.status, r.json()['error']) == (400, 'invalid_request')
    assert why in r.json()['detail']['why'], r.json()


@pytest.mark.parametrize('action', [_READ, {'class': 'mission.start', 'target': 'mission:sim'}])
def test_H04c_with_no_owner_yet_a_simulated_user_rule_answers_as_the_created_one_will(tc, action):
    """create_rule makes the owner a USER rule names when there is none yet;
    simulate writes nothing, so it judges against a stand-in owner instead of
    refusing the rule as scope-less (T-094 re-review, non-blocking 2)."""
    rule = {'scope_level': 'USER', 'action_class': action['class'], 'decision': 'DENY'}
    sim = tc.http('POST', '/v1/policies/simulate', body={'action': action, 'extra_rules': [rule]})
    assert sim.status == 200, sim.json()
    assert tc.http('GET', '/v1/policies').json()['rules'] == []
    assert _post(tc, '/v1/policies/rules', rule).status == 200
    after = tc.http('POST', '/v1/policies/simulate', body={'action': action}).json()
    assert sim.json()['decision'] == after['decision'] == 'DENY'


def test_H05_profiles_are_admin_only_and_the_health_names_the_policy_worker(deploy_core):
    tc = deploy_core
    got = _post(tc, '/v1/policies/profile', {'scope': 'user', 'profile': 'careful'})
    assert got.status == 200 and got.json()['profile'] == 'careful'
    assert tc.http('GET', '/v1/policies').json()['user_profile'] == 'careful'
    health = tc.http('GET', '/v1/health').json()
    assert health['core']['ports'] == 'real' and health['policy']['state'] in (
        'idle', 'running', 'reconciling')
    missing = _post(tc, '/v1/approvals/apr_01J00000000000000000000000/decide',
                    {'decision': 'approve', 'action_hash': '0' * 64})
    assert missing.status == 404
