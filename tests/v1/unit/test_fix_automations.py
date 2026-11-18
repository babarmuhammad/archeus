"""T-613: asking for no runs returns no runs (a -0 slice returned every one)."""

import pytest

from archeus.core.application import automations as A
from v1.integration.test_automation import Rig


@pytest.fixture
def rig(archeus_home):
    r = Rig()
    yield r
    r.close()


def test_get_automation_with_runs_zero_returns_no_runs(rig):
    aid = rig.automation()
    rig.seed()
    rig.seed()
    rig.pump()
    assert len(rig.runs(aid)) == 2
    with rig.db.read() as conn:
        assert A.get_automation(conn, aid, runs=0)['runs'] == []
        assert len(A.get_automation(conn, aid, runs=1)['runs']) == 1
