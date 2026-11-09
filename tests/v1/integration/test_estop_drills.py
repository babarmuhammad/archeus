"""P20 slice A: the e-stop with Core down or not answering, and its drills
(p20-design-gate §4.1 item 83, D13; execution-architecture §10 path 2;
p11-design-gate §13.4, D26).

`archeus estop` with no Core to answer writes `run/STOP` first and then kills
every process in `run/processes.jsonl` that has no end line and is still the
process recorded (pid and create_time). A Core that answers and refuses is not
bypassed. A Core starting afterwards comes up disarmed and starts nothing until
a user device re-arms it. Mutation-verified by tools/mutate_p20.py (Q01-Q08)."""

import os
import subprocess
import sys
import time

import pytest

from archeus.cli import main as cli
from archeus.cli.tui import client as tui_client
from archeus.core import engine, ports, runtime
from archeus.harnesses.fake import FakeHarness
from archeus.infra import discovery, paths
from archeus.node.local import LocalNode
from claude_sessions import proc

from v1.integration.test_execution_http import SLOW, _post, _wait


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
