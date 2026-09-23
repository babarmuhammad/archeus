"""G6 — approval boundaries and destructive-action controls."""

import pytest

from .client import CoreClientError
from .support import events_of, wait_for


@pytest.mark.xfail(strict=True, reason="phase:P9")
def test_a_locked_deny_cannot_be_loosened_by_a_narrower_scope(client, rig):
    rig.script_harness('t1', [{'emit': {'type': 'tool', 'name': 'Bash',
                                        'input': 'terraform destroy -auto-approve'}}])
    m = client.create_mission(title='Prod', objective='Destructive on prod')
    blocked = wait_for(lambda: client.get_mission(m['id'])['state'] in ('BLOCKED', 'FAILED'))
    assert blocked


@pytest.mark.xfail(strict=True, reason="phase:P9")
def test_the_brain_principal_can_never_approve(client, rig):
    client.create_mission(title='Deploy', objective='Ship to prod')
    apr = wait_for(lambda: events_of(client, 'approval.requested'))[0]['subject']['id']
    brain = rig.principal_client('brain')
    with pytest.raises(CoreClientError) as err:
        brain.decide_approval(apr, 'approve', idempotency_key='b')
    assert err.value.status == 403


@pytest.mark.xfail(strict=True, reason="phase:P15")
def test_revoking_a_device_closes_its_live_stream(client, rig):
    phone = rig.device('phone', scopes=('observe',))
    stream = phone.open_stream()
    rig.revoke(phone)
    assert stream.closed()


@pytest.mark.xfail(strict=True, reason="phase:P20")
def test_a_token_in_the_query_string_is_rejected(client, rig):
    assert rig.http_get('/v1/now?token=' + rig.device_token()).status == 401
