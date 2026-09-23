"""S5 — human approval of a plan and of a mid-execution action (SP6)."""

import pytest

from .client import CoreClientError
from .support import events_of, wait_for, wait_state


def _first_approval(client):
    return wait_for(lambda: events_of(client, 'approval.requested'))[0]['subject']['id']


@pytest.mark.xfail(strict=True, reason="phase:P9")
def test_a_plan_that_asks_waits_for_the_user_and_then_runs(client):
    m = client.create_mission(title='Deploy', objective='Ship to prod')
    wait_state(client, m['id'], 'APPROVAL_REQUIRED')
    client.decide_approval(_first_approval(client), 'approve', idempotency_key='k1')
    wait_state(client, m['id'], 'EXECUTING')


@pytest.mark.xfail(strict=True, reason="phase:P9")
def test_an_approval_is_single_use(client, rig):
    rig.script_harness('t1', [{'emit': {'type': 'tool', 'name': 'Bash',
                                        'input': 'git push origin main'}}] * 2)
    m = client.create_mission(title='Push twice', objective='Same action twice')
    client.decide_approval(_first_approval(client), 'approve', idempotency_key='k1')
    wait_for(lambda: len(events_of(client, 'approval.requested')) == 2)
    assert client.get_mission(m['id'])['state'] != 'COMPLETED'


@pytest.mark.xfail(strict=True, reason="phase:P9")
def test_deciding_twice_with_one_key_is_one_decision(client):
    client.create_mission(title='Deploy', objective='Ship to prod')
    apr = _first_approval(client)
    first = client.decide_approval(apr, 'approve', idempotency_key='same')
    again = client.decide_approval(apr, 'approve', idempotency_key='same')
    assert first == again


@pytest.mark.xfail(strict=True, reason="phase:P9")
def test_a_decided_approval_cannot_be_decided_again(client):
    client.create_mission(title='Deploy', objective='Ship to prod')
    apr = _first_approval(client)
    client.decide_approval(apr, 'reject', idempotency_key='a')
    with pytest.raises(CoreClientError) as err:
        client.decide_approval(apr, 'approve', idempotency_key='b')
    assert err.value.status == 422
