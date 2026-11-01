# ruff: noqa: F811  (the imported fixtures are taken as arguments)
"""PV20 B7: the MXC child object and the lifecycle routed to it, over fakes.

`agent_case` is the T-457 wiring: `LocalNode.spawn` -> `base.spawn` -> `MxcIsolationContext`
-> the production `MxcBoundary` over the scripted launcher. The pump thread is the real one;
what stands in for Windows are the injected fakes, and nothing here starts a process.
A launcher that never exits on its own (`launcher_exit=None`) is the long agent: it ends
only when Core stops it.
"""

import dataclasses
import json
import os
import threading
import time

import pytest

from claude_sessions import proc

from archeus.harnesses import base
from archeus.infra.paths import ExecPaths
from archeus.node import isolation as iso
from archeus.node import local, mxc_ledger
from archeus.node import mxc_context, mxc_native
from archeus.node.mxc_context import STREAM_BYTES

from v1.integration.test_pv20_mxc_agent_path import (agent_case, child_of, no_process,  # noqa: F401
                                                     registry_lines)
from v1.unit.test_mxc_boundary import gate, outcome, sdk, seed_journal  # noqa: F401
from v1.unit.test_pv20_isolation import os_tripwire  # noqa: F401

RUNNING = outcome(launcher_exit=None)


@pytest.fixture
def long_agent(tmp_path, sdk, gate, monkeypatch):
    """A case whose launcher runs until Core ends it; the pump is stopped at teardown."""
    case = agent_case(tmp_path, sdk, outcomes=[RUNNING])
    killed = []
    monkeypatch.setattr(mxc_context, 'PUMP_JOIN_S', 2.0)
    monkeypatch.setattr(proc, 'kill_pid_tree', lambda pid, created: killed.append(pid))
    case.pid_kills = killed
    yield case
    for child in list(case.authority.children.values()):
        child.cancel('test teardown')


def spawn(case, **over):
    handle = case.node.spawn(case.agent, dataclasses.replace(case.spec, **over),
                             isolated=True)
    return handle, case.authority.children[(case.spec.execution_id, over.get('process_seq', 1))]


def stream_of(case):
    with open(ExecPaths(case.spec.execution_id).stream, 'rb') as f:
        return f.read()


def limits_of(case):
    call = case.boundary.launch_calls[0]
    return {k: call[k] for k in ('transport', 'timeout_ms') if k in call}


def journal(case, seq=1):
    name = mxc_ledger.journal_name(case.spec.execution_id, seq)
    records, invalid = mxc_ledger.read_records(case.ledger.journals()[name], name)
    assert not invalid
    return [r['op'] for r in records], records


# ── the pump: the prompt in, the stream out ──────────────────────────────────

def test_the_prompt_goes_in_and_both_outputs_are_appended_to_the_stream(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk, outcomes=[outcome(stdout=b'{"type":"a"}\n',
                                                       stderr=b'warning\n')])
    fed = []
    case.api.write = lambda handle, data: fed.append(bytes(data)) or len(data)
    case.node.spawn(case.agent, case.spec, isolated=True)
    child = child_of(case)
    assert b''.join(fed) == b'go'                          # the prompt file, read once
    assert stream_of(case) == b'{"type":"a"}\nwarning\n'
    assert child.poll() == 3 and child.fault is None
    assert os.path.getsize(ExecPaths(case.spec.execution_id).prompt) == 2


def test_the_stream_of_a_resume_is_appended_to_the_one_before_it(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk, outcomes=[outcome(stdout=b'one\n'),
                                               outcome(stdout=b'two\n')])
    first = case.node.spawn(case.agent, case.spec, isolated=True)
    child_of(case)
    case.node.ended(first, 3, 1)
    case.node.spawn(case.agent, dataclasses.replace(case.spec, process_seq=2),
                    isolated=True, resume_state={'session': 'one'})
    child_of(case, 2)
    assert stream_of(case) == b'one\ntwo\n'


def test_a_stream_past_the_transports_default_bound_is_not_cut_off(tmp_path, sdk, gate):
    big = b'x' * (300 * 1024)                  # the 256 KiB default would end this launch
    case = agent_case(tmp_path, sdk, outcomes=[outcome(stdout=big)])
    case.node.spawn(case.agent, case.spec, isolated=True)
    assert child_of(case).poll() == 3
    assert stream_of(case) == big
    assert limits_of(case) == {'transport': {'output_limit': STREAM_BYTES}}


def test_the_task_limits_are_the_launchs_bounds(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk, outcomes=[outcome(stdout=b'y' * 100)])
    limits = {'output_bytes': 40, 'total_bytes': 60, 'timeout_s': 7}
    case.node.spawn(case.agent, dataclasses.replace(case.spec, limits=limits),
                    isolated=True)
    child = child_of(case)
    assert limits_of(case) == {'transport': {'output_limit': 40, 'total_limit': 60},
                               'timeout_ms': 7000}
    assert case.boundary.launches[0].policy.raw['process']['timeout'] == 7000
    # the chunk that crosses the bound never reaches the stream: no exit is clean
    assert child.poll() == 1 and stream_of(case) == b''
    assert 'output bound' in str(child.fault)
    assert journal(case)[0][-1] == 'quarantine'


def test_a_launch_that_cannot_read_its_prompt_is_ended_and_exits_nonzero(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk, outcomes=[RUNNING])
    first = case.boundary.launch

    def launch(*args, **kw):
        launched = first(*args, **kw)
        os.remove(ExecPaths(case.spec.execution_id).prompt)
        return launched

    case.boundary.launch = launch
    case.node.spawn(case.agent, case.spec, isolated=True)
    child = child_of(case)
    assert child.poll() == 1 and isinstance(child.fault, OSError)
    assert case.boundary.launches[0].end_state['state'] == mxc_ledger.DEAD_UNVERIFIED
    assert 'the pump failed' in case.boundary.launches[0].end_state['reason']
    assert case.jobs.terminated == [case.boundary.launch_calls[0]['job']]


def test_the_child_answers_poll_none_while_the_launcher_runs(long_agent):
    handle, child = spawn(long_agent)
    assert child.poll() is None and child.wait(0.05) is None
    assert child.pid == handle.pid == 1000
    assert long_agent.authority.launched(long_agent.spec.execution_id) is child
    child.cancel('test')
    assert child.poll() == 1


def test_a_normal_exit_is_the_workload_outcome_and_was_not_cancelled(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk)
    handle = case.node.spawn(case.agent, case.spec, isolated=True)
    child = child_of(case)
    assert child.poll() == 3 and child.reason is None
    child.cancel('late')                                  # too late to be why it ended
    assert child.reason is None
    assert journal(case)[0] == ['intent', 'ownership', 'disposal', 'completion']
    assert case.node.cancelled(handle, 1) is False
    case.node.ended(handle, 3, 1)
    assert case.authority.children == {}


# ── every stop of Core's ends through the launch, with its reason ─────────────

@pytest.mark.parametrize('reason', ['disarmed', 'estop', 'limit', 'handoff', 'stopped'])
def test_a_stop_ends_through_the_launch_and_never_through_the_pid_kill(long_agent, reason):
    handle, child = spawn(long_agent)
    job = long_agent.boundary.launch_calls[0]['job']
    assert long_agent.node.kill(long_agent.agent, handle, reason=reason) == 'killed'
    assert child.poll() == 1 and child.reason == reason
    assert 'cancelled during drain' in str(child.fault)       # the pump stopped itself
    assert long_agent.agent.stops == [] and long_agent.pid_kills == []
    assert long_agent.jobs.terminated == [job]                  # the Job ended, never closed
    assert long_agent.jobs.closed == []
    ended = long_agent.boundary.launches[0].end_state
    assert ended['reason'] == reason and ended['state'] == mxc_ledger.DEAD_UNVERIFIED
    ops, records = journal(long_agent)
    assert ops[-1] == 'quarantine' and reason in records[-1]['reason']   # a cancel completes nothing
    assert long_agent.node.cancelled(handle, 1) is True


def test_kill_defaults_to_the_stopped_reason(long_agent):
    handle, child = spawn(long_agent)
    long_agent.node.kill(long_agent.agent, handle)
    assert child.reason == 'stopped'


def test_kill_identity_routes_to_the_live_launch_too(long_agent):
    handle, child = spawn(long_agent)
    assert long_agent.node.kill_identity(handle, 'estop') is True
    assert child.reason == 'estop' and long_agent.pid_kills == []


def test_a_second_stop_ends_nothing_twice(long_agent):
    handle, child = spawn(long_agent)
    first = child.cancel('estop')
    assert child.cancel('limit') is first
    assert child.reason == 'estop' and len(long_agent.jobs.terminated) == 1
    long_agent.node.kill(long_agent.agent, handle, reason='limit')
    assert child.reason == 'estop' and len(long_agent.jobs.terminated) == 1


def test_two_stops_in_flight_agree_on_the_first_reason(long_agent):
    handle, child = spawn(long_agent)
    api, held, entered = long_agent.api, threading.Event(), threading.Event()
    real = api.poll

    def poll_when_released(process):
        entered.set()
        held.wait(5)                # the pump cannot see the stop until both have been made
        return real(process)
    api.poll = poll_when_released
    assert entered.wait(5)
    first = threading.Thread(target=child.cancel, args=('estop',))
    first.start()
    while child.reason is None:
        time.sleep(0.01)
    second = threading.Thread(target=child.cancel, args=('limit',))
    second.start()
    held.set()
    first.join(10)
    second.join(10)
    assert child.reason == 'estop'
    ops, records = journal(long_agent)
    assert ops[-1] == 'quarantine' and 'estop' in records[-1]['reason']
    assert 'limit' not in records[-1]['reason']


def test_a_second_wait_on_a_draining_launch_ends_nothing(long_agent):
    handle, child = spawn(long_agent)
    launch = child.launch
    with pytest.raises(mxc_native.AlreadyDraining, match='already draining'):
        launch.wait()
    assert launch.end_state is None and long_agent.jobs.terminated == []
    assert child.poll() is None and child.fault is None
    child.cancel('estop')
    assert child.reason == 'estop' and launch.end_state['reason'] == 'estop'


def test_a_handle_naming_another_pid_never_cancels_the_launch(long_agent):
    handle, child = spawn(long_agent)
    stale = base.ProcessHandle(handle.execution_id, handle.pid + 99, handle.create_time,
                               handle.exec_dir)
    long_agent.node.kill(long_agent.agent, stale)
    assert child.poll() is None and child.reason is None
    assert long_agent.agent.stops == [stale]                    # only the pid fallback ran


def test_a_launch_that_already_ended_is_not_killed_again_through_the_pid(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk)
    handle = case.node.spawn(case.agent, case.spec, isolated=True)
    child_of(case)
    assert case.node.kill(case.agent, handle, reason='estop') == 'killed'
    assert case.agent.stops == [handle]                  # the pid fallback: no launch to end
    assert case.boundary.launches[0].end_state['reason'] == 'launcher exited'


def test_the_children_are_keyed_by_execution_and_process_seq(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk)
    eid = case.spec.execution_id
    first = case.node.spawn(case.agent, case.spec, isolated=True)
    child_of(case)
    assert list(case.authority.children) == [(eid, 1)]
    case.node.ended(first, 3, 1)
    assert case.authority.children == {}
    case.node.spawn(case.agent, dataclasses.replace(case.spec, process_seq=2),
                    isolated=True, resume_state={'session': 'one'})
    child_of(case, 2)
    assert list(case.authority.children) == [(eid, 2)]


def test_ending_the_isolation_cancels_a_running_child_and_forgets_it(long_agent):
    handle, child = spawn(long_agent)
    eid = long_agent.spec.execution_id
    long_agent.node.end_isolation(eid, reason='the mission ended')
    assert child.reason == 'the mission ended' and child.poll() == 1
    assert long_agent.authority.children == {}
    assert long_agent.jobs.closed == [long_agent.boundary.launch_calls[0]['job']]
    assert 'the mission ended' in journal(long_agent)[1][-1]['reason']


def test_the_fence_ends_a_child_that_is_still_running_before_it_closes_the_job(long_agent):
    handle, child = spawn(long_agent)
    assert long_agent.node.fence_isolation(long_agent.spec.execution_id) is None
    assert child.reason == 'fenced' and child.poll() == 1
    assert long_agent.jobs.terminated and long_agent.jobs.closed


def test_the_fence_of_an_ended_child_ends_nothing_again(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk)
    case.node.spawn(case.agent, case.spec, isolated=True)
    child = child_of(case)
    assert case.node.fence_isolation(case.spec.execution_id) is None
    assert child.reason is None and len(case.jobs.terminated) == 1


def test_an_isolated_launch_that_fails_after_the_launch_ends_it(long_agent, monkeypatch):
    spec = long_agent.spec
    real = long_agent.authority._save

    def refuse(rec):
        if rec.pid is not None:     # the write that names the launched process
            raise OSError('the isolation record cannot be written')
        return real(rec)

    monkeypatch.setattr(long_agent.authority, '_save', refuse)
    with pytest.raises(base.SpawnFailed, match='launch_failed'):
        long_agent.node.spawn(long_agent.agent, spec, isolated=True)
    assert long_agent.authority.children == {}
    assert long_agent.boundary.launches[0].end_state['reason'] == 'launch failed'
    assert long_agent.jobs.terminated == [long_agent.boundary.launch_calls[0]['job']]


# ── boot: the ledger is read for ends nobody verified ─────────────────────────

def noted(state=None):
    return [(x['journal'], x['state']) for x in registry_lines()
            if x.get('op') == 'mxc_reconcile' and (state is None or x['state'] == state)]


def reclaim(case, live=()):
    return case.node.reclaim_isolation(live)


def test_boot_quarantines_a_journal_no_core_ended_and_notes_it_once(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk, resource_reader=None)      # nothing proves disposal
    seed_journal(case, 'old_one-p1', 'intent', 'ownership')
    reclaim(case)
    assert journal_ops(case, 'old_one-p1')[-1] == 'quarantine'
    assert noted() == [('old_one-p1', mxc_ledger.DEAD_UNVERIFIED)]
    reclaim(case)                                       # every sweep reads it again
    assert noted() == [('old_one-p1', mxc_ledger.DEAD_UNVERIFIED)]


def journal_ops(case, name):
    records, _ = mxc_ledger.read_records(case.ledger.journals()[name], name)
    return [r['op'] for r in records]


def test_boot_notes_a_dead_launcher_whose_resources_are_proven_absent_as_clean(
        tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk)
    seed_journal(case, 'gone-p1', 'intent', 'ownership')
    reclaim(case)
    assert noted() == [('gone-p1', mxc_ledger.DEAD_CLEAN)]
    assert journal_ops(case, 'gone-p1') == ['intent', 'ownership']      # nothing appended


def test_boot_leaves_a_completed_journal_alone(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk)
    seed_journal(case, 'done-p1', 'intent', 'ownership', 'disposal', 'completion')
    reclaim(case)
    assert noted() == [] and journal_ops(case, 'done-p1')[-1] == 'completion'


@pytest.mark.parametrize('seen,state', [(1, mxc_ledger.STILL_RUNNING),
                                        (2, mxc_ledger.UNKNOWN_OWNER)])
def test_boot_reads_a_live_launcher_by_pid_and_creation_time(tmp_path, sdk, gate, seen, state):
    case = agent_case(tmp_path, sdk)
    case.boundary.process_reader = lambda pid: seen    # the journal says pid 1, created at 1
    seed_journal(case, 'live-p1', 'intent', 'ownership')
    reclaim(case)
    assert noted() == [('live-p1', state)]


def test_boot_never_quarantines_a_launch_this_core_is_running(long_agent):
    handle, child = spawn(long_agent)
    name = long_agent.boundary.launches[0].journal
    reclaim(long_agent, {long_agent.spec.execution_id})
    reclaim(long_agent, {long_agent.spec.execution_id})
    assert journal(long_agent)[0] == ['intent', 'ownership']        # still in flight
    assert [x for x in noted() if x[0] == name] == []
    assert child.poll() is None


def test_a_restart_after_a_cancelled_run_finds_it_already_quarantined_and_refuses_a_resume(
        long_agent):
    handle, child = spawn(long_agent)
    long_agent.node.kill(long_agent.agent, handle, reason='estop')
    long_agent.node.ended(handle, 1, 1)
    reclaim(long_agent)                                  # the next Core's first sweep
    assert journal(long_agent)[0][-1] == 'quarantine'
    assert 'estop' in json.dumps(journal(long_agent)[1][-1])        # not overwritten
    with pytest.raises(base.SpawnFailed, match='generation_unresolved'):
        long_agent.node.spawn(long_agent.agent,
                              dataclasses.replace(long_agent.spec, process_seq=2),
                              isolated=True, resume_state={'session': 'one'})


def test_a_boundary_with_no_ledger_reconciles_nothing(tmp_path):
    authority = iso.Isolation(local.LocalNode(), boundary=iso.UnavailableBoundary())
    assert authority.reconcile_ledger() == {}


def test_the_ledger_reads_every_journal_but_the_ones_it_is_told_to_skip(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk)
    seed_journal(case, 'a-p1', 'intent', 'ownership')
    seed_journal(case, 'b-p1', 'intent', 'ownership')
    read = case.ledger.reconcile(lambda pid: None, lambda eid, owner: None, skip={'a-p1'})
    assert read == {'b-p1': mxc_ledger.DEAD_UNVERIFIED}
    assert journal_ops(case, 'a-p1') == ['intent', 'ownership']       # not even quarantined
