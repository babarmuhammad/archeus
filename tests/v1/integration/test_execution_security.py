"""P11 security (p11-design-gate §22): each threat's control, proven. Rows the
main suite already proves are named here by test, so the table stays complete:

    forged / reused pid, wrong start identity   test_execution E10, E62
    wrong task, stale / superseded plan, digest  E04–E07
    stale approval, another action's approval    E28, E29 (single-use), P9 I-A*
    unauthorised command, ambiguity              E41, E42, units (unclassified)
    branch / host / workdir                      E43, E46, units (D16)
    hook recursion / impersonation / replay      E44, E45, E48
    duplicate completion / stop                  E22, E27
    e-stop race                                  E25
    forged output                                E72
"""

import os

import pytest

from archeus.core.application import executions as X
from archeus.core.domain import entities, ids
from archeus.infra.paths import ExecPaths

from v1.integration import test_execution as _E
from v1.integration.test_execution import Rig, _running, ended  # noqa: F401
from v1.integration.test_policy import task

x = _E.x        # the rig fixture, shared with the main suite


def test_S01_an_execution_id_is_a_path_only_when_it_is_an_id():
    for forged in ('../x', 'exe_../../etc', 'exe_' + 'A' * 25 + '/', ''):
        with pytest.raises(ValueError):
            ExecPaths(forged)


def test_S02_usage_cannot_name_its_own_account_or_decision(x):
    acc = x.account('Work')
    x.scenarios['t1'] = [{'emit': {'type': 'result', 'summary': 'done', 'usage': {
        'input_tokens': 3, 'account_id': ids.new_id('account'),
        'route_decision_id': ids.new_id('route_decision')}}}]
    mid = x.ready(task('t1', 'write_repo'))
    e = x.drive(mid, lambda: x.exe(mission_id=mid))
    x.drive(mid, ended(x, e.id))
    (u,) = x.all(entities.UsageLedger, execution_id=e.id)
    assert (u.account_id, u.route_decision_id, u.tokens_in) == (
        acc, x.state(e.id).route_decision_id, 3)


def test_S03_a_hook_request_is_judged_on_the_state_inside_its_transaction(x):
    """Check-then-use: the manager read RUNNING, the user stopped it before the
    command ran — the command re-reads and halts."""
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': 30}]
    mid = x.ready(task('t1', 'write_repo', 'read'))
    e = _running(x, mid)
    stale = x.state(e.id)
    x.do(X.stop, execution_id=e.id, reason='user')
    from archeus.core.execution import canonical
    out = x.do(X.serve_hook, policy=x.policy, execution_id=stale.id, seq=1,
               request={'token': 'hook_any'}, canon=canonical.canonicalise(
                   'Read', {'file_path': 'a'}, {'workdir': stale.workdir}),
               cwd_ok=True, branch_ok=True, disarmed=False)
    assert out['decision'] == 'halt' and 'STOPPING' in out['reason']


def test_S04_a_policy_that_turns_to_deny_mid_run_is_met_at_the_next_action(x):
    """P11 never judges an action itself: a rule added after dispatch is what
    the very next hook request meets (P9 re-evaluates every use)."""
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': 0.8},
                         {'emit': {'type': 'tool', 'name': 'Write',
                                   'input': {'file_path': 'a.py'}}}, {'sleep': 5}]
    mid = x.ready(task('t1', 'write_repo'))
    e = _running(x, mid)
    x.rule('USER', 'write_repo', 'DENY')
    # only the execution thread runs here: the engine's next `advance` would also
    # meet the rule (the mission fails), which is not what this test is about
    import time
    deadline = time.monotonic() + 20
    while not x.events('execution.hook') and time.monotonic() < deadline:
        x.manager.tick()
        time.sleep(0.02)
    assert [ev['payload']['decision'] for ev in x.events('execution.hook')] == ['deny']


def test_S05_a_resume_never_routes_around_p10(x):
    """A paused execution resumes only where P10 chooses again; if the router
    now picks another account, the provider session is gone and the task
    starts over through normal dispatch."""
    a = x.account('A', priority=1)
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': 0.6},
                         {'emit': {'type': 'tool', 'name': 'Read',
                                   'input': {'file_path': 'a'}}}, {'sleep': 5}]
    mid = x.ready(task('t1', 'write_repo', 'read'))
    e = _running(x, mid)
    assert e.account_id == a
    x.do(x.missions.pause, who=x.user, mission_id=mid)
    x.drive(mid, lambda: x.state(e.id).state == 'PAUSED')
    from archeus.core.application import resources
    x.do(resources.set_account_enabled, who=x.user, account_id=a, enabled=False)
    x.account('B', priority=2)
    x.do(x.missions.resume, who=x.user, mission_id=mid)
    x.drive(mid, lambda: x.state(e.id).state == 'ENDED_KILLED')
    assert (x.state(e.id).stop_reason, x.state(e.id).charged) == ('binding', False)
    runs = x.all(entities.Execution, task_id=e.task_id)
    x.drive(mid, lambda: len(x.all(entities.Execution, task_id=e.task_id)) == 2)
    assert runs[0].account_id == a and x.exe(task_id=e.task_id).account_id != a


def test_S07_a_resume_is_judged_by_p9_again(x):
    """A pause is no authorisation of its own: a resume asks P9 again, and if
    the task now needs an approval the halted execution is discarded, uncharged."""
    x.scenarios['t1'] = [{'emit': {'type': 'working'}}, {'sleep': 0.6},
                         {'emit': {'type': 'tool', 'name': 'Read',
                                   'input': {'file_path': 'a'}}}, {'sleep': 5}]
    mid = x.ready(task('t1', 'write_repo'))
    e = _running(x, mid)
    x.do(x.missions.pause, who=x.user, mission_id=mid)
    x.drive(mid, lambda: x.state(e.id).state == 'PAUSED')
    x.do(x.authz.set_profile, who=x.user, scope='user', profile='careful')
    x.do(x.missions.resume, who=x.user, mission_id=mid)
    x.drive(mid, lambda: x.state(e.id).state == 'ENDED_KILLED')
    assert (x.state(e.id).stop_reason, x.state(e.id).charged) == ('binding', False)
    assert x.state(e.id).process_seq == 1                    # never spawned again


def test_S06_a_terminal_execution_has_no_hook_credential(x):
    x.scenarios['t1'] = [{'emit': {'type': 'result', 'summary': 'done'}}]
    mid = x.ready(task('t1', 'write_repo'))
    e = x.drive(mid, lambda: x.exe(mission_id=mid))
    assert x.drive(mid, lambda: x.state(e.id).hook_token_hash is not None
                   or x.state(e.id).state == 'ENDED_OK')
    x.drive(mid, ended(x, e.id))
    assert x.state(e.id).hook_token_hash is None


_ = os
