"""Mission confirmation under `careful` over a real Core (P19 S4;
p19-design-gate B6, §4.1): starting a mission is the action class
`mission.start`. `standard` and `autonomous` allow it, so a mission starts as
it always has; under `careful` the engine asks P9 before it fires START, an
Approval of kind `start` is created and the mission waits in CREATED.
Approving it (Attention, or the card in the conversation through B5) fires
START; rejecting it cancels the mission. No new route, card or edge."""

import time

import pytest

from archeus.core import engine, ports, runtime
from archeus.core.domain import ids
from v1.judge.http import TempCore


@pytest.fixture
def core(archeus_home):
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN))).start()
    yield tc
    tc.stop(kill=True)


def _post(tc, path, body):
    return tc.http('POST', path, body=dict(body, idempotency_key=body.get(
        'idempotency_key') or ids.new_ulid()))


def _wait(fn, what, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = fn()
        if got:
            return got
        time.sleep(0.05)
    raise AssertionError('timed out: %s' % what)


def _profile(tc, name):
    assert _post(tc, '/v1/policies/profile', {'scope': 'user', 'profile': name}).status == 200


def _mission(tc, title='Start me'):
    r = _post(tc, '/v1/missions', {'title': title, 'objective': 'o'})
    assert r.status == 200, r.body
    return r.json()['id']


def _state(tc, mid):
    return tc.http('GET', '/v1/missions/' + mid).json()['state']


def _approvals(tc, mid):
    return tc.http('GET', '/v1/approvals?mission=' + mid).json()['approvals']


def _start_approval(tc, mid):
    return _wait(lambda: next((a for a in _approvals(tc, mid) if a['kind'] == 'start'), None),
                 'a start approval for %s' % mid)


@pytest.mark.parametrize('profile', ['standard', 'autonomous'])
def test_a_profile_that_allows_the_start_starts_without_asking(core, profile):
    _profile(core, profile)
    mid = _mission(core)
    _wait(lambda: _state(core, mid) != 'CREATED', 'the mission starts')
    assert not [a for a in _approvals(core, mid) if a['kind'] == 'start']


def test_under_careful_the_mission_waits_in_created_for_its_start_approval(core):
    _profile(core, 'careful')
    mid = _mission(core)
    a = _start_approval(core, mid)
    assert (a['state'], a['eligible'], a['plan_id']) == ('PENDING', True, None)
    assert a['presented']['against']['mission']['id'] == mid
    time.sleep(1.0)                                     # the engine has ticked meanwhile
    assert _state(core, mid) == 'CREATED'
    assert len([x for x in _approvals(core, mid) if x['kind'] == 'start']) == 1   # asked once
    core.restart(kill=False)                            # a fresh engine passes over it again
    time.sleep(1.0)
    decisions = core.http('GET', '/v1/policy-decisions?mission=' + mid).json()['policy_decisions']
    assert [d['outcome'] for d in decisions if d['stage'] == 'start'] == ['asked']
    # the card is said in the conversation, linked to the mission (B5)
    msgs = core.http('GET', '/v1/conversations/primary/messages').json()['messages']
    assert any(c['ref'] == {'kind': 'approval', 'id': a['id']} for m in msgs for c in m['cards'])
    r = _post(core, '/v1/approvals/%s/decide' % a['id'],
              {'decision': 'approve', 'action_hash': a['action_hash']})
    assert r.status == 200 and r.json()['state'] in ('APPROVED', 'CONSUMED'), r.body
    # started; `careful` then asks for the plan as it always has
    _wait(lambda: _state(core, mid) == 'APPROVAL_REQUIRED', 'the plan asks next')
    kinds = sorted(x['kind'] for x in _approvals(core, mid))
    assert kinds == ['plan', 'start']
    decisions = core.http('GET', '/v1/policy-decisions?mission=' + mid).json()['policy_decisions']
    assert [d['outcome'] for d in decisions if d['stage'] == 'start'] == ['asked', 'approved']


def test_under_careful_rejecting_the_start_cancels_the_mission(core):
    _profile(core, 'careful')
    mid = _mission(core)
    a = _start_approval(core, mid)
    r = _post(core, '/v1/approvals/%s/decide' % a['id'],
              {'decision': 'reject', 'action_hash': a['action_hash']})
    assert r.status == 200, r.body
    assert _state(core, mid) == 'CANCELLED'


def test_a_start_is_approved_from_the_conversation_card(core):
    _profile(core, 'careful')
    mid = _mission(core)
    a = _start_approval(core, mid)
    r = _post(core, '/v1/conversations/%s/messages' % mid, {
        'text': 'approve', 'decision': {'approval_id': a['id'], 'action_hash': a['action_hash'],
                                        'expected_version': a['version']}})
    assert r.status == 200, r.body
    _wait(lambda: _state(core, mid) != 'CREATED', 'the chat approval starts it')


def test_a_mission_cancelled_while_it_waits_leaves_its_approval_undecidable(core):
    _profile(core, 'careful')
    mid = _mission(core)
    a = _start_approval(core, mid)
    # a bare `cancel` in the mission's thread is about the mission (B3)
    assert _post(core, '/v1/conversations/%s/messages' % mid, {'text': 'cancel'}).status == 200
    _wait(lambda: _state(core, mid) == 'CANCELLED', 'the mission is cancelled')
    got = core.http('GET', '/v1/approvals/' + a['id']).json()
    assert (got['state'], got['eligible']) == ('REJECTED', False)      # withdrawn (D15)
    r = _post(core, '/v1/approvals/%s/decide' % a['id'],
              {'decision': 'approve', 'action_hash': a['action_hash']})
    assert (r.status, r.json()['error']) == (422, 'invalid_transition'), r.body
    assert _state(core, mid) == 'CANCELLED'


def test_a_wrong_hash_does_not_start_it(core):
    _profile(core, 'careful')
    mid = _mission(core)
    a = _start_approval(core, mid)
    r = _post(core, '/v1/approvals/%s/decide' % a['id'],
              {'decision': 'approve', 'action_hash': '0' * 64})
    assert r.status == 422
    time.sleep(0.5)
    assert _state(core, mid) == 'CREATED'


def test_the_estop_does_not_hold_a_start_and_careful_still_asks(core):
    """A CREATED mission was always started while disarmed; B6 changes that
    for nobody: `standard` starts, `careful` asks, both under the e-stop."""
    assert _post(core, '/v1/estop', {}).status == 200
    try:
        mid = _mission(core, 'Under the e-stop')
        _wait(lambda: _state(core, mid) != 'CREATED', 'standard starts under the e-stop')
        _profile(core, 'careful')
        mid = _mission(core, 'Careful under the e-stop')
        assert _start_approval(core, mid)['state'] == 'PENDING'
    finally:
        _post(core, '/v1/rearm', {})


def test_a_users_deny_rule_holds_the_mission_without_asking(core):
    r = _post(core, '/v1/policies/rules', {'scope_level': 'USER', 'action_class': 'mission.start',
                                           'decision': 'DENY'})
    assert r.status == 200, r.body
    mid = _mission(core)
    time.sleep(1.0)
    assert _state(core, mid) == 'CREATED' and not _approvals(core, mid)
