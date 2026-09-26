"""S10b — a self-triggering automation escalates at depth 3 and is suspended
after three escalations; it never silently drops (state-machines §8)."""

import pytest

from .support import wait_for


@pytest.mark.xfail(strict=True, reason="phase:P14")
def test_a_self_triggering_automation_escalates_at_depth_three(client, rig):
    repo = rig.fixture_repo('self-triggering-automation')
    repo.commit('trigger', {'docs/models.md': 'x\n'})
    st = wait_for(lambda: client.status()['attention'])
    assert any(a['kind'] == 'automation_escalated' for a in st)


@pytest.mark.xfail(strict=True, reason="phase:P14")
def test_three_escalations_suspend_the_automation(client, rig):
    repo = rig.fixture_repo('self-triggering-automation')
    for i in range(3):
        repo.commit('trigger %d' % i, {'docs/models.md': '%d\n' % i})
    st = wait_for(lambda: client.status()['automations'])
    assert st[0]['state'] == 'SUSPENDED'
