"""The PV20 B7 mutation suite: break each property of the MXC child, the pump and the
lifecycle routed to it that tests/v1/integration/test_pv20_mxc_lifecycle.py, the isolated
A-series drills and the manager pins hold, run the test written for it, and require it to fail.

    py tools/mutate_mxc_lifecycle.py                 every mutation
    py tools/mutate_mxc_lifecycle.py ML01 ML10       only these

It edits archeus/node/mxc_context.py, mxc_boundary.py, mxc_ledger.py, local.py, isolation.py
and core/execution/manager.py, and restores them whatever happens: run it with nothing else
against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

CTX = 'archeus/node/mxc_context.py'
BOUNDARY = 'archeus/node/mxc_boundary.py'
LEDGER = 'archeus/node/mxc_ledger.py'
LOCAL = 'archeus/node/local.py'
ISO = 'archeus/node/isolation.py'
MGR = 'archeus/core/execution/manager.py'
L = 'tests/v1/integration/test_pv20_mxc_lifecycle.py::'
E = 'tests/v1/integration/test_estop_drills.py::'
P = 'tests/v1/unit/test_pins_core_execution_manager.py::'
G = 'tests/v1/unit/test_gaps_core_execution_manager.py::'
B = 'tests/v1/unit/test_mxc_boundary.py::'
W = 'tests/v1/unit/test_mxc_wire_sweep.py::'

PUMP = L + 'test_the_prompt_goes_in_and_both_outputs_are_appended_to_the_stream'
LIMITS = L + 'test_the_task_limits_are_the_launchs_bounds'
STOP = L + 'test_a_stop_ends_through_the_launch_and_never_through_the_pid_kill'
STALE = L + 'test_a_handle_naming_another_pid_never_cancels_the_launch'
KEYED = L + 'test_the_children_are_keyed_by_execution_and_process_seq'
NEVER = L + 'test_boot_never_quarantines_a_launch_this_core_is_running'
REASONS = P + 'test_every_kill_carries_the_reason_the_stop_was_for'

MUTATIONS = [
    ('ML01', 'the pump never attaches its sink and reader to the launch', [(CTX,
     '        launch.process.attach(self._write, self._read)', '        pass')], [PUMP]),
    ('ML02', 'what the launcher writes to stderr never reaches the stream', [(CTX,
     '        self._out.write(data)       # unbuffered',
     "        name == 'stdout' and self._out.write(data)       # unbuffered")], [PUMP]),
    ('ML03', 'a resume truncates the stream of the process before it', [(CTX,
     "open(self.paths.stream, 'ab', buffering=0)", "open(self.paths.stream, 'wb', buffering=0)")],
     [L + 'test_the_stream_of_a_resume_is_appended_to_the_one_before_it']),
    ('ML04', 'an end with no workload outcome exits zero', [(CTX,
     '        code = 1                    # an end', '        code = 0                    # an end')],
     [LIMITS]),
    ('ML05', 'the task output bound is ignored', [(CTX,
     "        transport = {'output_limit': limits.get('output_bytes', STREAM_BYTES)}",
     "        transport = {'output_limit': STREAM_BYTES}")], [LIMITS]),
    ('ML06', 'the task deadline is ignored', [(CTX,
     "        if 'timeout_s' in limits:", '        if False:')], [LIMITS]),
    ('ML07', 'a stop does not tell the drain why it was stopped', [(CTX,
     '                self.reason = self.launch.stop_reason = reason',
     '                self.reason = reason')], [STOP]),
    ('ML08', 'a stop never tells the pump to stop', [(CTX,
     '        self._stop.set()', '        pass')], [STOP]),
    ('ML09', 'a cancel after the end overwrites why it ended', [(CTX,
     '            if self.reason is None and not self._done.is_set():',
     '            if self.reason is None:')],
     [L + 'test_a_normal_exit_is_the_workload_outcome_and_was_not_cancelled']),
    ('ML10', 'a launch that fails after it started is left running', [(CTX,
     "                launch.cancel(reason='launch failed')", '                pass')],
     [L + 'test_an_isolated_launch_that_fails_after_the_launch_ends_it']),
    ('ML11', 'the child is not the process the isolation holds', [(CTX,
     '            authority._live[rec.execution_id] = child', '            pass')],
     [L + 'test_the_child_answers_poll_none_while_the_launcher_runs']),
    ('ML12', 'the child is registered under the first process seq whatever it is', [(CTX,
     '            authority.children[(rec.execution_id, request.process_seq)] = child',
     '            authority.children[(rec.execution_id, 1)] = child')], [KEYED]),
    ('ML13', 'a process of the node that already ended is cancelled again', [(LOCAL,
     '                if eid == execution_id and child.poll() is None',
     '                if eid == execution_id')],
     [L + 'test_a_launch_that_already_ended_is_not_killed_again_through_the_pid']),
    ('ML14', 'a stale pid ends the launch of the execution', [(LOCAL,
     '                and (pid is None or child.pid == pid)]', '                and True]')],
     [STALE, E + 'test_A04_a_recycled_pid_is_never_touched_and_never_ends_the_launch']),
    ('ML15', 'kill drops the reason it was given', [(LOCAL,
     '            child.cancel(reason)\n        if running:',
     "            child.cancel('stopped')\n        if running:")], [STOP]),
    ('ML16', 'kill goes on to the pid kill after ending the launch', [(LOCAL,
     "        if running:\n            return 'killed'", "        if False:\n            return 'killed'")],
     [STOP]),
    ('ML17', 'ended keeps the child it has seen end', [(LOCAL,
     '        child = self.isolation.children.pop((handle.execution_id, process_seq), None)',
     '        child = self.isolation.children.get((handle.execution_id, process_seq))')],
     [KEYED]),
    ('ML18', 'a cancelled launch is not reported as cancelled', [(LOCAL,
     '        return child is not None and child.reason is not None', '        return False')],
     [STOP, E + 'test_A05_an_estop_that_cannot_verify_the_end_is_quarantined_and_never_a_clean_end']),
    ('ML19', 'ending the isolation leaves a running child running', [(LOCAL,
     "            child.cancel(reason or 'ended')", '            pass')],
     [L + 'test_ending_the_isolation_cancels_a_running_child_and_forgets_it']),
    ('ML20', 'the fence closes the Job under a running child', [(LOCAL,
     "            child.cancel('fenced')", '            pass')],
     [L + 'test_the_fence_ends_a_child_that_is_still_running_before_it_closes_the_job']),
    ('ML21', 'boot reads the journals of the launches this Core is running', [(LOCAL,
     'resource_reader, skip=mxc_busy(ledger))', 'resource_reader, skip=())')], [NEVER]),
    ('ML22', 'a journal already noted is noted again on every sweep', [(ISO,
     '                   if self._reconciled.get(journal) != state}', '                   if True}')],
     [L + 'test_boot_quarantines_a_journal_no_core_ended_and_notes_it_once']),
    ('ML23', 'the ledger ignores the journals it is told to skip', [(LEDGER,
     '.items() if name not in skip}', '.items() if True}')],
     [L + 'test_the_ledger_reads_every_journal_but_the_ones_it_is_told_to_skip']),
    ('ML24', 'the boundary is not the one that names the launch context', [(BOUNDARY,
     '    context = MxcIsolationContext', '    context = None')], [PUMP]),
    ('ML25', 'a boundary with no process reader is available', [(BOUNDARY,
     '                                                 self.pins, self.process_reader))):',
     '                                                 self.pins))):')],
     [B + 'test_every_part_is_needed_for_it_to_be_available']),
    ('ML26', 'the request forgets which process of the execution it is', [(ISO,
     '                            broker=r.broker, process_seq=spec.process_seq,',
     '                            broker=r.broker, process_seq=1,')], [KEYED]),
    ('ML27', 'the request drops the limits of the task', [(ISO,
     '                            limits=spec.limits)', '                            limits=None)')],
     [LIMITS]),
    ('ML28', 'a collected kill of Core is recorded as an ordinary end', [(MGR,
     "        killed = result.exit_reason == 'killed' or cancelled",
     "        killed = result.exit_reason == 'killed'")],
     [G + 'test_a_stop_of_cores_that_ended_an_isolated_launch_is_a_kill_whatever_the_adapter_says']),
    ('ML31', 'a sweep lets a launch claim its id while it reads the journals', [(LOCAL,
     '    with _MXC_CLAIMS_LOCK:\n        return ledger.reconcile(',
     '    if True:\n        return ledger.reconcile(')],
     [W + 'test_a_start_that_begins_during_a_sweep_waits_for_it_and_is_not_quarantined']),
    ('ML32', 'a later stop overwrites the reason of the first', [(CTX,
     '            if self.reason is None and not self._done.is_set():',
     '            if not self._done.is_set():')],
     [L + 'test_two_stops_in_flight_agree_on_the_first_reason']),
    ('ML29', 'the e-stop reason is lost on the way to the node', [(MGR,
     "                           reason='disarmed' if disarmed else e.stop_reason or 'stopped')",
     "                           reason='stopped')")], [REASONS]),
    ('ML30', 'a hand-off kill carries no reason', [(MGR,
     "reason=e.stop_reason or 'handoff')", "reason='handoff')")], [REASONS]),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
