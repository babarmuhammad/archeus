"""S10 — an event triggers an automation: a new model file -> a documentation
mission (SP15, IP-F). The loop guard is test_s10b_loop_guard.py."""

import pytest

from .support import wait_for


@pytest.mark.xfail(strict=True, reason="phase:P14")
def test_a_new_model_file_creates_a_documentation_mission(client, rig):
    repo = rig.fixture_repo('django-app')
    repo.commit('add Invoice model', {'billing/models/invoice.py': 'class Invoice: ...\n'})
    missions = wait_for(lambda: client.list_missions())
    assert any(m['origin'] == 'automation' and 'Invoice' in m['title'] for m in missions)
