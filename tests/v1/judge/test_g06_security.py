"""G6 — approval boundaries and destructive-action controls.

P9 (p9-design-gate D21): *a locked deny cannot be loosened by a narrower scope*
scripts a mid-execution `terraform destroy`, which only the action stage sees
(the P11 hook), so it is P11's, its body unchanged — and its objective is left
without a planner recording on purpose, so no plan-level denial can make it
pass early. The P9 function beside it asks the same of the plan gate.
"""

import pytest

from .client import CoreClientError
from .support import events_of, wait_for


@pytest.mark.xfail(strict=True, reason="phase:P11")
def test_a_locked_deny_cannot_be_loosened_by_a_narrower_scope(client, rig):
    rig.script_harness('t1', [{'emit': {'type': 'tool', 'name': 'Bash',
                                        'input': 'terraform destroy -auto-approve'}}])
    m = client.create_mission(title='Prod', objective='Destructive on prod')
    blocked = wait_for(lambda: client.get_mission(m['id'])['state'] in ('BLOCKED', 'FAILED'))
    assert blocked


def test_the_brain_principal_can_never_approve(client, rig):
    client.create_mission(title='Deploy', objective='Ship to prod')
    apr = wait_for(lambda: events_of(client, 'approval.requested'))[0]['subject']['id']
    brain = rig.principal_client('brain')
    with pytest.raises(CoreClientError) as err:
        brain.decide_approval(apr, 'approve', idempotency_key='b')
    assert err.value.status == 403


def test_a_locked_deny_cannot_be_loosened_at_the_plan_gate(client):
    """A user-level ALLOW for destructive actions does not reach under the
    locked GLOBAL floor: the plan is denied, nothing is approved, and the
    denial names the floor rule (p9-design-gate §4.2, X05)."""
    client.set_policy_rule(scope_level='USER', action_class='destructive', decision='ALLOW',
                           idempotency_key='loosen')
    m = client.create_mission(title='Staging', objective='Destroy the staging database')
    blocked = wait_for(lambda: (client.get_mission(m['id']).get('planning_blocked') or {})
                       .get('kind') == 'policy')
    assert blocked
    got = client.get_mission(m['id'])
    assert got['state'] == 'BLOCKED' and got['plan_id'] is None
    assert got['planning_blocked']['denied'][0]['rule'] == 'builtin:floor:destructive-prod'
    assert not events_of(client, 'approval.requested')
    assert [e['payload']['trigger'] for e in events_of(client, 'mission.state_changed')
            if e['subject']['id'] == m['id']][-1] == 'plan_denied'


@pytest.mark.xfail(strict=True, reason="phase:P15")
def test_revoking_a_device_closes_its_live_stream(client, rig):
    phone = rig.device('phone', scopes=('observe',))
    stream = phone.open_stream()
    rig.revoke(phone)
    assert stream.closed()


def test_a_token_in_the_query_string_is_rejected(client, rig):
    assert rig.http_get('/v1/now?token=' + rig.device_token()).status == 401
