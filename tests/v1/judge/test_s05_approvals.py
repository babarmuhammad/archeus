"""S5 — human approval of a plan and of a mid-execution action (SP6).

P9 (p9-design-gate D21): the plan's approval is P9's, driven by a recorded
plan whose one task deploys (Standard asks for it, and the locked prod floor
asks whatever a narrower rule says). *An approval is single-use* needs the
fake agent's emitted `git push` to reach Core mid-execution — the action stage
through the policy hook — so it is P11's: the row's phases are P9, P11. The
body is unchanged. The fourth P9 function is new: an approval never carries
to the plan version that replaces the one it approved.
"""

import pytest

from .client import CoreClientError
from .support import events_of, wait_for, wait_state


def _first_approval(client):
    return wait_for(lambda: events_of(client, 'approval.requested'))[0]['subject']['id']


def test_a_plan_that_asks_waits_for_the_user_and_then_runs(client):
    m = client.create_mission(title='Deploy', objective='Ship to prod')
    wait_state(client, m['id'], 'APPROVAL_REQUIRED')
    client.decide_approval(_first_approval(client), 'approve', idempotency_key='k1')
    wait_state(client, m['id'], 'EXECUTING')


@pytest.mark.xfail(strict=True, reason="phase:P11")
def test_an_approval_is_single_use(client, rig):
    rig.script_harness('t1', [{'emit': {'type': 'tool', 'name': 'Bash',
                                        'input': 'git push origin main'}}] * 2)
    m = client.create_mission(title='Push twice', objective='Same action twice')
    client.decide_approval(_first_approval(client), 'approve', idempotency_key='k1')
    wait_for(lambda: len(events_of(client, 'approval.requested')) == 2)
    assert client.get_mission(m['id'])['state'] != 'COMPLETED'


def test_deciding_twice_with_one_key_is_one_decision(client):
    client.create_mission(title='Deploy', objective='Ship to prod')
    apr = _first_approval(client)
    first = client.decide_approval(apr, 'approve', idempotency_key='same')
    again = client.decide_approval(apr, 'approve', idempotency_key='same')
    assert first == again


def test_a_decided_approval_cannot_be_decided_again(client):
    client.create_mission(title='Deploy', objective='Ship to prod')
    apr = _first_approval(client)
    client.decide_approval(apr, 'reject', idempotency_key='a')
    with pytest.raises(CoreClientError) as err:
        client.decide_approval(apr, 'approve', idempotency_key='b')
    assert err.value.status == 422


def test_an_approval_does_not_carry_to_the_next_plan_version(client, rig):
    """Approve v1; its task fails every attempt, the mission replans; v2 asks
    again, and v1's approval — superseded with its plan — can never be used or
    decided again (p9-design-gate §10.3, X01)."""
    rig.script_harness('t1', [{'exit': 1}])
    m = client.create_mission(title='Deploy', objective='Ship to prod')
    first = _first_approval(client)
    client.decide_approval(first, 'approve', idempotency_key='v1')
    wait_for(lambda: len(events_of(client, 'approval.requested')) == 2, timeout=60)
    assert first in [e['subject']['id'] for e in events_of(client, 'approval.state_changed')
                     if e['payload']['to'] == 'SUPERSEDED']
    second = events_of(client, 'approval.requested')[1]['subject']['id']
    assert second != first
    with pytest.raises(CoreClientError) as err:
        client.decide_approval(first, 'approve', idempotency_key='replay')
    assert err.value.status == 422
    assert client.get_mission(m['id'])['plan_version'] == 2
