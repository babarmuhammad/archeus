import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

NATIVE = 'archeus/node/mxc_native.py'
MXC = 'archeus/node/mxc.py'
TEST = 'tests/v1/unit/test_mxc_native.py::'
S = 'tests/v1/unit/test_mxc_native_stream.py::'

MUTATIONS = [
    ('N01', 'suspended creation removed', [(NATIVE,
     'flags=CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,',
     'flags=EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,')],
     [TEST + 'test_suspended_allowlist_and_resume_once']),
    ('N02', 'resume once check removed', [(NATIVE,
     '        if child.resumed:\n', '        if False:\n')],
     [TEST + 'test_suspended_allowlist_and_resume_once']),
    ('N03', 'fault handle cleanup removed', [(NATIVE,
     '            for handle in reversed(handles):\n                self.api.close_handle(handle)',
     '            for handle in reversed(handles):\n                pass')],
     [TEST + 'test_allocation_fault_closes_every_handle']),
    ('N04', 'inheritance allowlist removed', [(NATIVE,
     'attributes = self.api.attribute_list(inherited)',
     'attributes = self.api.attribute_list(())')],
     [TEST + 'test_suspended_allowlist_and_resume_once']),
    ('N05', 'assignment fault kill removed', [(MXC,
     '                child.terminate()\n', '                pass\n')],
     [TEST + 'test_job_fault_kills_and_closes']),
    ('N06', 'output bound removed', [(NATIVE,
     'if (self._seen[name] > self.transport.output_limit\n'
     '                                or sum(self._seen.values()) > self.transport.total_limit):',
     'if False:')],
     [TEST + 'test_output_bound']),
    # B1: the streaming drain, its bounds and the one-drain-thread contract
    ('N07', 'the per-stream output bound is never checked', [(NATIVE,
     'if (self._seen[name] > self.transport.output_limit\n                                or sum(',
     'if (False\n                                or sum(')],
     [S + 'test_the_per_stream_bound_stops_the_launch_and_withholds_the_chunk']),
    ('N08', 'the total output bound is never checked', [(NATIVE,
     'or sum(self._seen.values()) > self.transport.total_limit):',
     'or False):')],
     [S + 'test_the_total_bound_stops_two_streams_each_within_their_own']),
    ('N09', 'the default total bound is one stream, not two', [(NATIVE,
     'total_limit = 2 * output_limit', 'total_limit = output_limit')],
     [S + 'test_the_total_bound_defaults_to_two_full_streams_and_counts_across_reads']),
    ('N10', 'output bypasses the Core-supplied sink', [(NATIVE,
     'self._sink(name, data)', 'self._buffer(name, data)')],
     [S + 'test_partial_reads_reach_the_sink_in_arrival_order_and_not_the_memory_stream']),
    ('N11', 'stdin EOF from the reader never closes the pipe', [(NATIVE,
     "if chunk == b'':", "if chunk == b'~':")],
     [S + 'test_the_stdin_reader_is_fed_until_eof_then_the_pipe_closes_once']),
    ('N12', 'a stop asked for from another thread is ignored by the drain', [(NATIVE,
     'if self._stop or cancelled():', 'if cancelled():')],
     [S + 'test_another_thread_can_only_ask_the_drain_to_stop']),
    ('N13', 'terminate closes handles under a running drain', [(NATIVE,
     '        if self._draining:\n            self._stop = True',
     '        if False:\n            self._stop = True')],
     [S + 'test_another_thread_can_only_ask_the_drain_to_stop',
      S + 'test_a_sink_that_terminates_on_the_drain_thread_does_not_pull_handles_from_under_it']),
    ('N14', 'a second concurrent wait is allowed into the drain', [(NATIVE,
     "        if self._draining:\n            raise AlreadyDraining('launcher already draining')",
     "        if False:\n            raise AlreadyDraining('launcher already draining')")],
     [S + 'test_a_wait_from_inside_the_drain_is_refused_not_nested',
      S + 'test_a_wait_from_another_thread_is_refused_while_the_drain_runs']),
    ('N15', 'poll reports the exit while the drain still holds handles', [(NATIVE,
     'return None if self._handles else self.launcher_exit', 'return self.launcher_exit')],
     [S + 'test_poll_is_none_until_the_drain_has_returned_whatever_the_kernel_says']),
    ('N16', 'a terminated launcher never gets an exit code', [(NATIVE,
     '                self.launcher_exit = 1\n            finally:', '                pass\n            finally:')],
     [S + 'test_a_sink_that_raises_ends_the_launch_with_its_own_error',
      S + 'test_deadline_expiry_keeps_the_output_so_far_and_kills_the_running_launcher']),
    ('N17', 'the Core can re-route output while the drain runs', [(NATIVE,
     'if self._draining or not self._handles:', 'if not self._handles:')],
     [S + 'test_attach_is_refused_during_the_drain_and_after_close']),
    ('N18', 'the drain never checks its deadline', [(NATIVE,
     'if self.transport.clock() >= deadline:', 'if False:')],
     [S + 'test_deadline_expiry_keeps_the_output_so_far_and_kills_the_running_launcher',
      S + 'test_a_caller_timeout_overrides_the_policy_deadline']),
    ('N19', 'a stdin reader with nothing yet is read as EOF', [(NATIVE,
     "pending, offset = chunk or b'', 0",
     "pending, offset = chunk or b'', 0\n                            if chunk is None:\n"
     "                                self._close(self._pipes[0])")],
     [S + 'test_the_stdin_reader_is_fed_until_eof_then_the_pipe_closes_once',
      S + 'test_a_stdin_reader_with_nothing_yet_keeps_the_pipe_open_until_the_deadline']),
    ('N20', 'a deadline from the task limit never reaches the drain', [(NATIVE,
     "policy.raw['process']['timeout'] / 1000)", "policy.raw['process']['timeout'])")],
     [S + 'test_the_deadline_is_the_task_limit_the_policy_was_compiled_from']),
    ('N21', 'a NaN or infinite output bound is accepted and never trips', [(NATIVE,
     '        if not all(type(limit) is int and limit > 0 for limit in (output_limit, total_limit)):',
     '        if output_limit <= 0 or total_limit <= 0:')],
     ['tests/v1/unit/test_mxc_native_gaps.py::test_a_bound_that_is_not_a_positive_int_is_refused',
      S + 'test_a_total_bound_that_is_not_a_positive_int_is_refused']),
    ('N22', 'a handle that fails to close stays on the list to be retried', [(NATIVE,
     "                self._handles.remove(handle)    # a handle that fails to close is not retried"
     "\n                self.api.close_handle(handle)",
     "                self.api.close_handle(handle)\n                self._handles.remove(handle)")],
     [TEST + 'test_one_handle_that_will_not_close_does_not_keep_the_others_open']),
    ('N23', 'the first handle that fails to close stops the close', [(NATIVE,
     "            except Exception as err:\n                failed = failed or err",
     "            except ZeroDivisionError as err:\n                failed = failed or err")],
     [TEST + 'test_one_handle_that_will_not_close_does_not_keep_the_others_open']),
    ('N24', 'a released drain uses a handle that was closed under it', [(NATIVE,
     "            if handle not in self._handles:\n"
     "                raise MxcUnavailable('launcher closed during drain')",
     "            if False:\n"
     "                raise MxcUnavailable('launcher closed during drain')")],
     [TEST + 'test_a_drain_released_after_its_launch_was_closed_touches_no_closed_handle']),
    # review fixes 1-6 (fix batch 10)
    ('N25', 'two closers each release the policy lease', [(NATIVE,
     "        with self._lock:                # two closers must not release one lease twice\n"
     "            lease, self._policy_lease = self._policy_lease, None\n"
     "        try:\n"
     "            if lease is not None:\n"
     "                self.api.remove_policy(*lease)\n",
     "        lease = self._policy_lease\n"
     "        try:\n"
     "            if lease is not None:\n"
     "                self.api.remove_policy(*lease)\n"
     "                self._policy_lease = None\n")],
     [TEST + 'test_two_closers_release_the_policy_lease_once']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
