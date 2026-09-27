"""V06 — a failed attempt is not evidence, and a later attempt is verified on
its own revision (p13-design-gate §10, §24)."""

import pytest

from .support import wait_state
from .test_v01_outcome_verification import FIX, WRONG, _write

pytestmark = pytest.mark.real_verification


def test_V06_attempt_one_fails_attempt_two_is_verified_on_its_own_revision(client, rig):
    repo = rig.fixture_repo('verify-python')
    rig.script_harness('t1', [
        dict(_write(WRONG), attempt=1), {'exit': 1, 'attempt': 1},
        dict(_write(FIX), attempt=2), {'emit': {'type': 'result', 'summary': 'done'}}])
    m = client.create_mission(title='Fix add', objective='Make add add',
                              project_id=repo.project_id)
    wait_state(client, m['id'], 'COMPLETED', timeout=120)
    task_vs = [v for v in client.verifications(m['id']) if v['subject']['kind'] == 'task']
    # attempt 1 exited 1: an execution failure, retried, never verified
    (v,) = task_vs
    assert v['state'] == 'PASSED'
    ended = [e for e in client.events(0) if e['type'] == 'execution.ended'
             and e['payload']['task_id'] == v['subject']['id']]
    assert [e['payload']['exit_reason'] for e in ended] == ['error', 'ok']
    assert v['execution_id'] == ended[-1]['subject']['id']
    # its evidence is attempt 2's workspace: the fix is what was tested
    assert {c['name']: c['result'] for c in v['checks']}['test: python -m pytest'] == 'pass'
