# ruff: noqa: F811  (the imported fixtures are taken as arguments)
"""P20 slice A: the e-stop with Core down or not answering, and its drills
(p20-design-gate §4.1 item 83, D13; execution-architecture §10 path 2;
p11-design-gate §13.4, D26).

`archeus estop` with no Core to answer writes `run/STOP` first and then kills
every process in `run/processes.jsonl` that has no end line and is still the
process recorded (pid and create_time). A Core that answers and refuses is not
bypassed. A Core starting afterwards comes up disarmed and starts nothing until
a user device re-arms it. Mutation-verified by tools/mutate_p20.py (Q01-Q08)."""

import dataclasses
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from archeus.cli import main as cli
from archeus.cli.tui import client as tui_client
from archeus.core import engine, ports, runtime
from archeus.harnesses.fake import FakeHarness
from archeus.infra import discovery, paths
from archeus.node import isolation as iso
from archeus.node import local, mxc_ledger
from archeus.node.local import LocalNode
from claude_sessions import proc

from v1.integration.test_execution_http import SLOW, _post, _wait
from v1.integration.test_pv20_mxc_agent_path import agent_case, registry_lines
from v1.unit.test_mxc_boundary import gate, outcome, sdk  # noqa: F401  (fixtures)


@pytest.fixture
def children():
    """Real processes standing in for executions' harness processes."""
    made = []

    def spawn():
        p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],
                             creationflags=proc.no_window_flags)
        made.append(p)
        _wait(lambda: proc.process_create_time(p.pid) is not None, 'the child')
        return p
    yield spawn
    for p in made:
        if p.poll() is None:
            p.kill()
        p.wait(10)


def _register(*lines):
    node = LocalNode()
    for x in lines:
        node._registry(x)


def _spawn_line(eid, p, *, create_time=None, seq=1):
    return {'op': 'spawn', 'execution_id': eid, 'process_seq': seq, 'pid': p.pid,
            'create_time': proc.process_create_time(p.pid) if create_time is None else create_time}


def _gone(p, timeout=20):
    _wait(lambda: p.poll() is not None, 'process %d to exit' % p.pid, timeout)
    return True


def test_A01_core_down_kills_exactly_the_live_registry_processes(archeus_home, children, capsys):
    live, ended, recycled = children(), children(), children()
    _register(_spawn_line('exe_live', live),
              _spawn_line('exe_ended', ended),
              {'op': 'end', 'execution_id': 'exe_ended', 'process_seq': 1},
              # the recorded process is gone and its pid now names a stranger
              _spawn_line('exe_recycled', recycled, create_time=12345))
    assert discovery.discover()[0] == 'not_running'
    assert cli.main(['estop']) == 0
    out = capsys.readouterr().out
    assert 'without Core: 1 process(es) killed' in out and 'disarmed' in out
    assert os.path.exists(paths.stop_sentinel())
    assert _gone(live)
    time.sleep(0.5)
    assert ended.poll() is None and recycled.poll() is None      # never touched
    assert discovery.discover()[0] == 'not_running'               # Core was not started
    # a second press is harmless: nothing left to kill, the sentinel stays
    assert cli.main(['estop']) == 0
    assert 'without Core: 0 process(es) killed' in capsys.readouterr().out
    assert os.path.exists(paths.stop_sentinel())


def test_A02_the_sentinel_is_written_before_any_kill(archeus_home, children, monkeypatch):
    p = children()
    _register(_spawn_line('exe_1', p))
    seen = []
    real = proc.kill_pid_tree

    def kill(pid, create_time):
        seen.append(os.path.exists(paths.stop_sentinel()))
        return real(pid, create_time)
    monkeypatch.setattr(proc, 'kill_pid_tree', kill)
    assert cli.main(['estop']) == 0
    assert seen == [True]
    assert _gone(p)


@pytest.mark.parametrize('state', ['unreadable', 'running'])
def test_A03_a_core_that_does_not_answer_is_stopped_without_it(archeus_home, children,
                                                                monkeypatch, capsys, state):
    p = children()
    _register(_spawn_line('exe_1', p))
    monkeypatch.setattr(discovery, 'discover', lambda: (state, {'port': 1}))
    monkeypatch.setattr(discovery, 'read_local_token', lambda: 'tok')

    def no_answer(self, path, body):
        raise tui_client.CoreError(0, 'network', {'why': 'ConnectionRefusedError'})
    monkeypatch.setattr(tui_client.Core, 'post', no_answer)
    assert cli.main(['estop']) == 0
    assert 'without Core: 1 process(es) killed' in capsys.readouterr().out
    assert os.path.exists(paths.stop_sentinel())
    assert _gone(p)


def test_A04_a_core_that_answers_and_refuses_is_not_bypassed(archeus_home, children,
                                                              monkeypatch, capsys):
    p = children()
    _register(_spawn_line('exe_1', p))
    monkeypatch.setattr(discovery, 'discover', lambda: ('running', {'port': 1}))
    monkeypatch.setattr(discovery, 'read_local_token', lambda: 'tok')

    def refuse(self, path, body):
        raise tui_client.CoreError(403, 'insufficient_scope', {})
    monkeypatch.setattr(tui_client.Core, 'post', refuse)
    assert cli.main(['estop']) == 2
    assert 'Core did not accept the e-stop' in capsys.readouterr().err
    assert not os.path.exists(paths.stop_sentinel())
    time.sleep(0.5)
    assert p.poll() is None


def test_A05_a_sentinel_that_cannot_be_written_is_a_failure_not_a_stop(archeus_home, monkeypatch,
                                                                        capsys):
    def denied():
        raise PermissionError('denied')
    monkeypatch.setattr(LocalNode, 'engage_estop', staticmethod(denied))
    assert cli.main(['estop']) == 2
    assert 'emergency stop failed' in capsys.readouterr().err


def _core(home):
    from v1.judge.http import TempCore
    return TempCore(home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), scenarios=dict(SLOW),
        executors=[FakeHarness()])).start()


def _started(tc, mission_id=None):
    evs = [e for e in tc.client().events(0) if e['type'] == 'execution.started']
    if mission_id is None:
        return evs
    return [e for e in evs if tc.http('GET', '/v1/executions/%s' % e['subject']['id'])
            .json()['mission_id'] == mission_id]


def test_A06_core_down_estop_then_disarmed_core_starts_nothing_until_rearmed(archeus_home,
                                                                              capsys):
    tc = _core(archeus_home)
    try:
        _post(tc, '/v1/missions', {'title': 'Runaway', 'objective': 'Core dies first'})
        (ev,) = _wait(lambda: _started(tc), 'a running execution')
        pid, eid = ev['payload']['pid'], ev['subject']['id']
        tc.stop(kill=True)                                   # Core is gone; its process is not
        assert proc.process_create_time(pid) is not None
        assert cli.main(['estop']) == 0
        assert 'without Core: 1 process(es) killed' in capsys.readouterr().out
        _wait(lambda: proc.process_create_time(pid) is None, 'the registry kill')

        tc.start()                                           # comes back disarmed
        assert tc.http('GET', '/v1/health').json()['armed'] is False
        state = _wait(lambda: (lambda s: s.startswith('ENDED') and s)(
            tc.http('GET', '/v1/executions/%s' % eid).json()['state']), 'the reconciliation')
        assert state != 'ENDED_OK'                           # a killed process is never success
        new = _post(tc, '/v1/missions', {'title': 'After', 'objective': 'o'}).json()['id']
        time.sleep(3)
        assert _started(tc, new) == []                       # no new work while disarmed

        assert _post(tc, '/v1/rearm').json() == {'armed': True}
        # re-arming restores starting work (a mission refused while disarmed stays
        # BLOCKED by builtin:estop: P9's existing rule, p20-design-gate §12)
        after = _post(tc, '/v1/missions', {'title': 'Re-armed', 'objective': 'o'}).json()['id']
        _wait(lambda: _started(tc, after), 'work after the re-arm', 60)
    finally:
        if tc.core is not None:
            for p in list(tc.core.manager._procs.values()):
                proc.kill_pid_tree(p['handle'].pid, p['handle'].create_time)
            tc.stop()
        LocalNode.clear_estop()


# ── the isolated variant (p20-design-gate §12 item 99; PV-20 B7) ───────────────
#
# For an isolated execution the first step of A06 inverts: Core's death closes the Job
# only Core held, so no process lives on for the e-stop to kill. The launcher is a fake
# one behind the production MxcBoundary (nothing native runs), and a process is "gone" when
# its fake pid reads no creation time.

@pytest.fixture
def isolated(tmp_path, sdk, gate, monkeypatch):
    alive = {'now': True}

    def reads(pid):
        return 17.0 if alive['now'] else None

    monkeypatch.setattr(proc, 'process_create_time', reads)
    monkeypatch.setattr(iso, 'base_create_time', reads)
    kills = []
    monkeypatch.setattr(proc, 'kill_pid_tree', lambda pid, created: kills.append(
        (pid, created, os.path.exists(paths.stop_sentinel()))) or False)

    def start(**kw):
        case = agent_case(tmp_path, sdk, outcomes=[outcome(launcher_exit=None)], **kw)
        handle = case.node.spawn(case.agent, case.spec, isolated=True)
        child = case.authority.children[(case.spec.execution_id, 1)]
        case.handle, case.child = handle, child
        return case

    cases = []
    yield SimpleNamespace(alive=alive, kills=kills, cases=cases,
                          start=lambda **kw: cases.append(start(**kw)) or cases[-1])
    for case in cases:
        case.child.cancel('test teardown')
    LocalNode.clear_estop()


def test_A01_isolated_core_death_ends_the_tree_and_the_registry_kill_finds_nothing(
        archeus_home, isolated):
    case = isolated.start()
    job = case.boundary.launch_calls[0]['job']
    case.jobs.on_close.append(lambda closed: case.child.cancel('core death'))
    case.authority._close_job(case.spec.execution_id)           # what Core's death does
    assert case.child.wait(10) is not None and case.jobs.closed == [job]
    isolated.alive['now'] = False
    unended = [x for x in LocalNode.unended() if x['execution_id'] == case.spec.execution_id]
    assert len(unended) == 1 and unended[0]['isolated'] is True      # the line is still there
    killed, gone = LocalNode.estop_without_core()
    assert killed == [] and unended[0] in gone
    assert os.path.exists(paths.stop_sentinel())


def test_A02_the_sentinel_is_written_before_any_isolated_process_is_ended(archeus_home,
                                                                          isolated):
    case = isolated.start()
    seen = []
    real = case.child.cancel
    case.child.cancel = lambda reason='cancelled': (
        seen.append(os.path.exists(paths.stop_sentinel())), real(reason))[1]
    LocalNode.engage_estop()
    assert case.node.kill(case.agent, case.handle, reason='disarmed') == 'killed'
    assert seen == [True] and case.child.reason == 'disarmed'
    isolated.kills.clear()
    LocalNode.estop_without_core()                       # the belt writes it first too
    assert [k[2] for k in isolated.kills] == [True]


def test_A03_a_core_that_does_not_answer_is_stopped_by_identity_while_the_job_stays_the_authority(
        archeus_home, isolated):
    case = isolated.start()
    killed, gone = LocalNode.estop_without_core()
    assert [k[:2] for k in isolated.kills] == [(case.handle.pid, case.handle.create_time)]
    assert killed == [] and len(gone) == 1               # the (faked) kill was refused
    assert case.child.poll() is None                     # only the Job or cancel ends the launch
    assert case.node.kill(case.agent, case.handle, reason='estop') == 'killed'
    assert case.child.poll() == 1 and case.jobs.terminated == [
        case.boundary.launch_calls[0]['job']]


def test_A04_a_recycled_pid_is_never_touched_and_never_ends_the_launch(archeus_home,
                                                                       isolated):
    case = isolated.start()
    stale = dataclasses.replace(case.handle, pid=case.handle.pid + 1000)
    assert case.node.kill_identity(stale, 'estop') is False
    assert case.child.poll() is None and case.jobs.terminated == []
    assert [k[:2] for k in isolated.kills] == [(stale.pid, stale.create_time)]


def test_A05_an_estop_that_cannot_verify_the_end_is_quarantined_and_never_a_clean_end(
        archeus_home, isolated):
    case = isolated.start(resource_reader=lambda journal, owner: [{'resource': 'left'}])
    assert case.node.kill(case.agent, case.handle, reason='estop') == 'killed'
    assert case.child.poll() == 1 and case.node.cancelled(case.handle, 1) is True
    state = case.boundary.launches[0].end_state
    assert state['state'] == 'DEAD_UNVERIFIED' and state['reason'] == 'estop'
    records, _ = mxc_ledger.read_records(
        case.ledger.journals()['%s-p1' % case.spec.execution_id],
        '%s-p1' % case.spec.execution_id)
    assert [r['op'] for r in records][-1] == 'quarantine'


def test_A06_isolated_estop_then_a_restarted_core_adopts_nothing_and_resumes_nothing(
        archeus_home, isolated):
    case = isolated.start()
    LocalNode.engage_estop()
    case.node.kill(case.agent, case.handle, reason='disarmed')
    isolated.alive['now'] = False
    # a Core that starts afterwards: a fresh authority over the same ledger, disarmed
    node = local.LocalNode()
    node.isolation = iso.Isolation(node, boundary=case.boundary)
    assert node.disarmed() and node.isolation.children == {}
    assert node.kill(case.agent, case.handle) == 'gone'
    node.reclaim_isolation(())
    journal = '%s-p1' % case.spec.execution_id
    assert [x['state'] for x in registry_lines() if x.get('journal') == journal] == [
        'DEAD_UNVERIFIED']
    with pytest.raises(iso.IsolationUnavailable, match='generation_unresolved'):
        case.boundary.create_profile(case.spec.execution_id)
    assert case.child.poll() == 1
