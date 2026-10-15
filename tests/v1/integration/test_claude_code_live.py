"""S1 and S5 against the REAL Claude Code adapter (p11-design-gate §24.1, §9):
the opt-in suite. It spends real quota, so it never runs in CI or by default:

    ARCHEUS_REAL_HARNESS=1 py -m pytest tests/v1/integration/test_claude_code_live.py

Everything but the adapter is the integration rig: the real P9 policy, the P10
router, the execution manager, the hook answering through the mailbox."""

import os

import pytest

from archeus.core.application import calls as C
from archeus.core.domain import entities
from archeus.harnesses.claude_code.adapter import ClaudeCodeAdapter
from archeus.infra.paths import ExecPaths

from v1.integration.test_execution import Rig, ended
from v1.integration.test_policy import task

pytestmark = pytest.mark.skipif(os.environ.get('ARCHEUS_REAL_HARNESS') != '1',
                                reason='the real Claude Code run is opt-in')

HELLO = 'Create a file named hello.txt containing the single word hello, then stop.'


@pytest.fixture
def live(db):
    adapter = ClaudeCodeAdapter()
    if not adapter.discover().installed:
        pytest.skip('claude is not installed')
    rig = Rig(db, adapters=[adapter])
    rig.do(C.decide_provider_terms, who=rig.user, harness_id='claude_code',
           headless='permitted')
    yield rig
    rig.cleanup()


def test_S1_a_real_execution_runs_under_the_hook_and_ends_as_evidence(live):
    mid = live.ready(task('t1', 'write_repo', title=HELLO))
    e = live.drive(mid, lambda: live.exe(mission_id=mid), timeout=60)
    live.drive(mid, ended(live, e.id), timeout=300)
    e = live.state(e.id)
    assert (e.state, e.exit_code) == ('ENDED_OK', 0)
    assert os.path.isfile(os.path.join(ExecPaths(e.id).dir, 'hello.txt'))
    assert 'allow' in [ev['payload']['decision'] for ev in live.events('execution.hook')]
    assert live.task_of(mid).state == 'VERIFYING'


def test_S5_an_action_approval_resumes_the_same_session_and_is_used_once(live):
    live.rule('USER', 'write_repo', 'ASK')
    mid = live.ready_approved(task('t1', 'write_repo', title=HELLO))
    e = live.drive(mid, lambda: (live.exe(mission_id=mid) is not None
                                 and live.exe(mission_id=mid).state == 'AWAITING_APPROVAL'
                                 and live.exe(mission_id=mid)), timeout=300)
    a = live.pending(mid)
    assert (a.kind, a.execution_id) == ('action', e.id)
    live.decide(a)
    live.drive(mid, ended(live, e.id), timeout=300)
    e = live.state(e.id)
    assert (e.state, e.process_seq) == ('ENDED_OK', 2)
    assert live.one(entities.Approval, id=a.id).state == 'CONSUMED'
