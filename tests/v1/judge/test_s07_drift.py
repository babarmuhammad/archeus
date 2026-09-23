"""S7 — repository re-inspection and architecture drift (IP-G)."""

import pytest

from .support import wait_for


@pytest.mark.xfail(strict=True, reason="phase:P4")
def test_a_commit_that_violates_a_constraint_is_reported_as_drift(client, rig):
    repo = rig.fixture_repo('layered-python')
    repo.commit('core imports api', {'app/core/x.py': 'import app.api\n'})
    st = wait_for(lambda: client.status()['drift'])
    assert any(d['constraint'] == 'core must not import api' for d in st)


@pytest.mark.xfail(strict=True, reason="phase:P4")
def test_a_clean_commit_is_not_drift(client, rig):
    repo = rig.fixture_repo('layered-python')
    repo.commit('core helper', {'app/core/y.py': 'x = 1\n'})
    assert client.status()['drift'] == []
