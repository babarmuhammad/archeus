"""S11 — mobile control: observe, pause, resume and approve from a paired
device (SP16, SP17, IP-E). Pause is cooperative."""

import pytest

from .client import CoreClientError
from .support import wait_state


@pytest.mark.xfail(strict=True, reason="phase:P15")
def test_a_paired_phone_can_pause_and_resume_a_mission(client, rig):
    phone = rig.device('phone', scopes=('observe', 'control', 'approve'))
    rig.script_harness('t1', [{'sleep': 5}])
    m = client.create_mission(title='Remote', objective='Long enough to pause')
    wait_state(client, m['id'], 'EXECUTING')
    phone.pause(m['id'])
    wait_state(phone, m['id'], 'PAUSED')
    phone.resume(m['id'])
    wait_state(phone, m['id'], 'COMPLETED', timeout=60)


@pytest.mark.xfail(strict=True, reason="phase:P15")
def test_a_device_without_the_control_scope_cannot_pause(client, rig):
    viewer = rig.device('tablet', scopes=('observe',))
    m = client.create_mission(title='Remote', objective='Observe only')
    with pytest.raises(CoreClientError) as err:
        viewer.pause(m['id'])
    assert err.value.status == 403
