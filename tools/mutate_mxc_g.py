"""The PV20 slice G (step G1) mutation suite: break each security property that
tests/v1/unit/test_pv20_g_regressions.py pins, run the test written for it, and require
it to fail.

    py tools/mutate_mxc_g.py                 every mutation
    py tools/mutate_mxc_g.py MG01 MG10       only these

It edits archeus/node/mxc_native.py, mxc_ledger.py, local.py, mxc_cancel.py,
isolation.py, attest.py, origin_native.py, origin_windows.py, archeus/api/origin.py and
server.py, and restores them whatever happens: run it with nothing else against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

NATIVE = 'archeus/node/mxc_native.py'
LEDGER = 'archeus/node/mxc_ledger.py'
LOCAL = 'archeus/node/local.py'
CANCEL = 'archeus/node/mxc_cancel.py'
ISO = 'archeus/node/isolation.py'
ATTEST = 'archeus/node/attest.py'
OWNER = 'archeus/node/origin_native.py'
BACKEND = 'archeus/node/origin_windows.py'
ORIGIN = 'archeus/api/origin.py'
SERVER = 'archeus/api/server.py'
T = 'tests/v1/unit/test_pv20_g_regressions.py::'

FLOOD = [T + 'test_a_child_flooding_one_stream_puts_no_more_than_its_bound_in_core_memory',
         T + 'test_the_in_memory_streams_are_bounded_too_when_no_sink_is_attached']
TOTAL = T + 'test_two_streams_each_inside_their_own_bound_cannot_exceed_the_total'
NAMES = [T + 'test_no_two_keys_or_generations_ever_get_one_journal_name',
         T + 'test_an_execution_can_never_be_given_a_verifiers_journal_name']
ONE_COMPONENT = T + 'test_a_journal_name_is_one_path_component_whatever_the_key'
TREE = T + 'test_an_end_that_terminates_the_job_is_clean_only_because_the_tree_is_gone'
SURVIVES = T + 'test_a_tree_that_survives_the_end_is_never_recorded_clean'
REFUSED = T + 'test_every_way_the_origin_is_unproven_is_refused'
LATER = T + 'test_a_user_binding_is_refused_the_moment_the_peer_stops_being_that_user'
REGISTRY = (T + 'test_the_registry_approves_only_a_user_on_the_direct_local_path_to_a_'
            'registered_port')
NO_READERS = (T + 'test_a_backend_with_no_readers_validates_nothing_even_a_genuine_looking_'
              'binding')
KERNEL = T + 'TestTheKernelEnd::'

MUTATIONS = [
    # B1: output bounds
    ('MG01', 'a stream may reach twice its bound', [(NATIVE,
     'if (self._seen[name] > self.transport.output_limit',
     'if (self._seen[name] > 2 * self.transport.output_limit')], FLOOD),
    ('MG02', 'the total bound is never applied', [(NATIVE,
     'or sum(self._seen.values()) > self.transport.total_limit):', 'or False):')], [TOTAL]),
    ('MG03', 'received bytes are never counted', [(NATIVE,
     'self._seen[name] += len(data)', 'self._seen[name] += 0')], FLOOD + [TOTAL]),
    ('MG04', 'one read may ask the OS for a gigabyte', [(NATIVE,
     'data = self.api.read(self._pipes[index], 65536)',
     'data = self.api.read(self._pipes[index], 1 << 30)')],
     [T + 'test_core_never_asks_the_os_for_more_than_one_bounded_chunk_at_a_time']),
    ('MG05', 'the drain has no deadline', [(NATIVE,
     'if self.transport.clock() >= deadline:', 'if False:')],
     [T + 'test_a_child_that_dribbles_forever_is_stopped_at_the_deadline_not_held_open',
      T + 'test_a_child_that_never_reads_its_input_cannot_make_core_buffer_without_end']),
    ('MG06', 'stdin is read ahead of a child that takes nothing', [(NATIVE,
     'if offset >= len(pending):', 'if True:')],
     [T + 'test_a_child_that_never_reads_its_input_cannot_make_core_buffer_without_end']),
    ('MG07', 'the drain returns before the output pipes are at end', [(NATIVE,
     'if self.launcher_exit is not None and len(eof) == 2:',
     'if self.launcher_exit is not None and len(eof) >= 1:')],
     [T + 'test_output_that_arrives_after_the_launcher_exited_is_not_dropped']),
    ('MG08', 'a faulted drain leaves the launcher running', [(NATIVE,
     '            self._draining = False\n            self.terminate()\n            self.close()\n',
     '            self._draining = False\n            self.close()\n')],
     [T + 'test_whatever_ends_the_drain_the_launcher_is_killed_and_no_handle_is_left']),
    # B2: journal names
    ('MG10', 'the process generation dropped from the name', [(LEDGER,
     "    return '%s-p%d' % (base, process_seq)", "    return base")], NAMES),
    ('MG11', 'the generation glued on with no separator', [(LEDGER,
     "    return '%s-p%d' % (base, process_seq)", "    return '%s%d' % (base, process_seq)")],
     NAMES),
    ('MG12', 'an execution key that reads as a verifier name accepted', [(LEDGER,
     " and not key.startswith('verify_'):", ":")], NAMES),
    ('MG13', 'any key at all accepted as an execution key', [(LEDGER,
     "re.fullmatch('[A-Za-z0-9_]+', key)", "re.fullmatch('.+', key)")], [ONE_COMPONENT]),
    ('MG14', 'a key only has to start like an execution key', [(LEDGER,
     "re.fullmatch('[A-Za-z0-9_]+', key)", "re.match('[A-Za-z0-9_]+', key)")],
     [ONE_COMPONENT]),
    ('MG15', 'every attempt of one verification shares a name', [(LEDGER,
     "base = 'verify_%s_%d' % (vid, attempt)", "base = 'verify_%s_%d' % (vid, 0)")], NAMES),
    ('MG16', 'every verification shares a name per attempt', [(LEDGER,
     "base = 'verify_%s_%d' % (vid, attempt)", "base = 'verify_%d' % attempt")], NAMES),
    ('MG17', 'any process generation accepted', [(LEDGER,
     "    if type(process_seq) is not int or process_seq < 1:", "    if False:")],
     [T + 'test_a_process_generation_that_could_read_as_another_is_refused']),
    # B3: the end
    ('MG20', 'the Job is never ended', [(LOCAL,
     "                self._end_job(self.job)", "                pass")], [TREE]),
    ('MG21', 'a loose member count proves the tree gone', [(LOCAL,
     "            if type(n) is int and n == 0:", "            if n == 0:")],
     [T + 'test_only_an_integer_zero_member_count_proves_the_tree_gone']),
    ('MG22', 'a tree still running is disposed verified', [(CANCEL,
     "    elif quiescent is False:", "    elif False:")], [SURVIVES]),
    ('MG23', 'the admission is not revoked at the end', [(LOCAL,
     "            self.broker.revoke(self.execution_id)", "            pass")],
     [T + 'test_the_admission_is_revoked_before_the_tree_is_ended_and_the_count_is_read_after',
      T + 'test_a_terminate_that_fails_on_a_living_tree_is_quarantined_and_still_revokes']),
    ('MG24', 'a workload with no exit code returns as a result', [(LOCAL,
     "        if type(code) is not int:", "        if False:")],
     [T + 'test_a_workload_that_reports_no_exit_code_is_an_error_never_a_result']),
    ('MG25', 'a second end ends again', [(LOCAL,
     "            if self._ended:\n                return self.end_state",
     "            if False:\n                return self.end_state")],
     [T + 'test_ending_twice_ends_nothing_twice']),
    ('MG26', 'the Job closed as it is terminated', [(ISO,
     "            _win(_TerminateJobObject(job, 1), 'TerminateJobObject')",
     "            _win(_TerminateJobObject(job, 1), 'TerminateJobObject')\n"
     "            _CloseHandle(job)")],
     [KERNEL + 'test_ending_a_job_never_closes_the_handle_the_count_is_read_through']),
    ('MG27', 'a refused kernel end not reported', [(ISO,
     "            _win(_TerminateJobObject(job, 1), 'TerminateJobObject')",
     "            _TerminateJobObject(job, 1)")],
     [KERNEL + 'test_a_kernel_that_refuses_the_end_is_an_error_never_a_silent_pass']),
    # B9: an origin that is not proven is refused
    ('MG30', 'a reused pid is the same peer', [(ATTEST,
     "    if CREATION_TIME_UNREADABLE not in failures and info.creation_time != "
     "binding.creation_time:", "    if False:")], [LATER]),
    ('MG31', 'a binding never expires', [(ATTEST,
     "    if not _finite(now) or not (now - binding.accepted_at <= max_age_s):",
     "    if not _finite(now):")],
     [T + 'test_a_binding_older_than_its_age_is_refused_without_a_reattest']),
    ('MG32', 'a dead owner passes the liveness check', [(ATTEST,
     'def _alive_failures(info: ProcessInfo) -> "list[str]":\n    failures: list[str] = []\n'
     '    if info.alive is not True:',
     'def _alive_failures(info: ProcessInfo) -> "list[str]":\n    failures: list[str] = []\n'
     '    if False:')], [REFUSED, LATER]),
    ('MG33', 'a peer in a Core Job may be the user', [(ATTEST,
     "    if info.in_core_job is not False:\n        failures.append(INSIDE_CORE_JOB)",
     "    if False:\n        failures.append(INSIDE_CORE_JOB)")], [REFUSED, LATER]),
    ('MG34', 'a peer under the launcher may be the user', [(ATTEST,
     '    if reason is None:\n        failures.append(LAUNCHER_PRESENT)',
     '    if False:\n        failures.append(LAUNCHER_PRESENT)')], [REFUSED]),
    ('MG35', 'a peer in another session may be the user', [(ATTEST,
     "    if info.same_session is not True:", "    if False:")], [REFUSED, LATER]),
    ('MG36', 'a user is attested off the direct loopback path', [(BACKEND,
     'if not origin.direct_loopback(context):', 'if False:')],
     [T + 'test_the_backend_itself_never_attests_a_user_off_the_loopback_path']),
    ('MG37', 'the registry approves an unregistered port', [(ORIGIN,
     '                and direct_loopback(context)\n'
     '                and context.local_endpoint[1] in self._ports)',
     '                and direct_loopback(context))')], [REFUSED, REGISTRY]),
    ('MG38', 'the registry approves any origin', [(ORIGIN,
     '                and evidence.origin == OriginClass.USER\n'
     '                and evidence.path == PathClass.DIRECT_LOCAL',
     '                and evidence.path == PathClass.DIRECT_LOCAL')], [REGISTRY]),
    ('MG39', 'two owners of one port resolve to one', [(OWNER,
     'if len(pids) == 1 else None', 'if pids else None')], [REFUSED]),
    ('MG40', 'every owner reads alive', [(OWNER,
     'return ProcessInfo(alive=process.alive,', 'return ProcessInfo(alive=True,')],
     [REFUSED, LATER]),
    ('MG41', "Core's Job table is never read for membership", [(OWNER,
     '                           in_core_job=process.in_jobs,',
     '                           in_core_job=False,')], [REFUSED, LATER]),
    ('MG42', "every process is in Core's session", [(OWNER,
     'same_session=process.session_id == api.core_session())', 'same_session=True)')],
     [REFUSED, LATER]),
    ('MG43', 'a hung call is not a timeout', [(ORIGIN,
     'if not done.wait(BACKEND_DEADLINE_S):',
     'if not done.wait(BACKEND_DEADLINE_S) and False:')],
     [T + 'test_a_call_that_hangs_is_a_timeout_and_not_a_missing_answer']),
    ('MG44', 'the per-request re-check is skipped', [(SERVER,
     'and origin.bounded(backend.valid, self.context, self.evidence) is True',
     'and True')], [LATER]),
    ('MG45', "Core's registry is not consulted", [(SERVER,
     'and self.origin_registry.approved(self.context, self.evidence) is True):',
     'and True):')], [REFUSED]),
    ('MG46', 'a backend with no readers validates', [(BACKEND,
     '    def valid(self, context, evidence):\n        if self.readers is None:\n'
     '            return False',
     '    def valid(self, context, evidence):\n        if False:\n            return False')],
     [NO_READERS]),
    ('MG47', 'a backend with no readers attests', [(BACKEND,
     '    def attest(self, context):\n        if self.readers is None:',
     '    def attest(self, context):\n        if False:')], [NO_READERS, REFUSED]),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
