"""The PV-20 B9 mutation suite: break each invariant of the native origin readers, the
USER-by-exclusion attestor, the Core path registry and the backend deadline, run the
test written for that invariant, and require it to fail.

    py tools/mutate_origin_native.py              every mutation
    py tools/mutate_origin_native.py B01 B04      only these

Run it with nothing else against the tree: it edits archeus/node/origin_native.py,
attest.py, origin_windows.py, archeus/api/origin.py and server.py, and restores them
whatever happens.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

NATIVE = 'archeus/node/origin_native.py'
ATTEST = 'archeus/node/attest.py'
BACKEND = 'archeus/node/origin_windows.py'
ORIGIN = 'archeus/api/origin.py'
SERVER = 'archeus/api/server.py'
T = 'tests/v1/unit/test_origin_native.py::'
H = 'tests/v1/integration/test_api_origin_transport.py::'

MUTATIONS = [
    ('B01', 'a row that is not established names the owner', [(NATIVE,
     'if row.state == ESTABLISHED and row.pid > 0', 'if row.pid > 0')],
     [T + 'test_a_row_that_is_not_the_direct_loopback_peer_names_no_owner']),
    ('B02', 'a pid 0 row names the owner', [(NATIVE,
     'if row.state == ESTABLISHED and row.pid > 0', 'if row.state == ESTABLISHED')],
     [T + 'test_a_row_that_is_not_the_direct_loopback_peer_names_no_owner']),
    ('B03', 'a connection to another listener names the owner', [(NATIVE,
     'and row.remote_addr == LOOPBACK and row.remote_port == core_port}',
     'and row.remote_addr == LOOPBACK}')],
     [T + 'test_a_row_that_is_not_the_direct_loopback_peer_names_no_owner']),
    ('B04', 'two different owners resolve to one', [(NATIVE,
     'if len(pids) == 1 else None', 'if pids else None')],
     [T + 'test_two_different_owners_of_one_port_are_ambiguous_and_name_no_owner']),
    ('B05', 'any port finds the owner', [(NATIVE,
     'and row.local_addr == LOOPBACK and row.local_port == peer_port',
     'and row.local_addr == LOOPBACK')],
     [T + 'test_another_port_has_no_owner']),
    ('B06', 'a process the job lists is alive whatever the wait says', [(NATIVE,
     'return ProcessInfo(alive=process.alive,', 'return ProcessInfo(alive=True,')],
     [T + 'test_a_dead_process_the_job_still_lists_is_not_alive_f9c']),
    ('B07', 'a process that cannot be opened reads alive', [(NATIVE,
     'return ProcessInfo(alive=False, creation_time=None,',
     'return ProcessInfo(alive=True, creation_time=None,')],
     [T + 'test_no_process_is_dead_with_no_creation_time']),
    ('B08', 'a parent created after its child extends the chain', [(NATIVE,
     'or child.creation_time is None or parent.creation_time >= child.creation_time):',
     'or child.creation_time is None):')],
     [T + 'test_a_parent_created_after_its_child_is_a_recycled_pid_and_ends_the_chain']),
    ('B09', 'a dead parent extends the chain', [(NATIVE,
     'if (parent is None or not parent.alive or parent.creation_time is None',
     'if (parent is None or parent.creation_time is None')],
     [T + 'test_a_dead_parent_ends_the_chain']),
    ('B10', 'the ancestor walk is unbounded', [(NATIVE,
     'while parent_pid and len(names) < MAX_ANCESTORS:', 'while parent_pid:')],
     [T + 'test_the_ancestor_walk_is_bounded']),
    ('B11', "every process is in Core's session", [(NATIVE,
     'same_session=process.session_id == api.core_session())', 'same_session=True)')],
     [T + 'test_another_session_is_not_the_same_session']),
    ('B12', 'a user may sit in a Core Job', [(ATTEST,
     'if info.in_core_job is not False:', 'if False:')],
     [T + 'test_a_peer_that_is_not_positively_the_user_is_undetermined']),
    ('B13', 'a user may sit under the launcher', [(ATTEST,
     '    if reason is None:\n        failures.append(LAUNCHER_PRESENT)',
     '    if False:\n        failures.append(LAUNCHER_PRESENT)')],
     [T + 'test_a_peer_that_is_not_positively_the_user_is_undetermined']),
    ('B14', 'a user may be in another session', [(ATTEST,
     'if info.same_session is not True:', 'if False:')],
     [T + 'test_a_reader_that_does_not_report_the_session_cannot_make_a_user']),
    ('B15', 'a user binding is not re-checked for the Job or the launcher', [(ATTEST,
     '    else:\n        failures += _user_failures(info, launcher)', '    else:\n        pass')],
     [T + 'test_a_user_binding_loses_validity_when_the_peer_enters_a_core_job']),
    ('B16', 'a user is attested off the direct loopback path', [(BACKEND,
     'if not origin.direct_loopback(context):', 'if False:')],
     [T + 'test_no_user_without_the_direct_loopback_path']),
    ('B17', 'a re-attest accepts the other kind of process', [(BACKEND,
     '                bound.pid, bound.creation_time, bound.core_job_at_accept) != (\n'
     '                first.pid, first.creation_time, first.core_job_at_accept):',
     '                bound.pid, bound.creation_time) != (\n'
     '                first.pid, first.creation_time):')],
     [T + 'test_a_reattest_that_finds_another_kind_of_process_is_refused']),
    ('B18', 'the registry approves any origin', [(ORIGIN,
     '                and evidence.origin == OriginClass.USER\n'
     '                and evidence.path == PathClass.DIRECT_LOCAL',
     '                and evidence.path == PathClass.DIRECT_LOCAL')],
     [T + 'test_the_registry_never_approves_a_non_user_origin']),
    ('B19', 'the registry approves an unregistered port', [(ORIGIN,
     '                and direct_loopback(context)\n'
     '                and context.local_endpoint[1] in self._ports)',
     '                and direct_loopback(context))')],
     [T + 'test_the_registry_refuses_an_unregistered_port_and_a_non_loopback_end']),
    ('B20', 'a hung call is not a timeout', [(ORIGIN,
     'if not done.wait(BACKEND_DEADLINE_S):',
     'if not done.wait(BACKEND_DEADLINE_S) and False:')],
     [T + 'test_a_hung_call_times_out_at_the_deadline']),
    ('B21', 'hung calls are not capped', [(ORIGIN,
     'if not _slots.acquire(blocking=False):', 'if False:')],
     [T + 'test_hung_calls_hold_their_slots_and_the_next_one_fails_at_once']),
    ('B22', 'the server waits on attest unbounded', [(SERVER,
     'self.evidence = origin.bounded(backend.attest, self.context)',
     'self.evidence = backend.attest(self.context)')],
     [H + 'test_backend_calls_are_time_bounded']),
    ('B23', 'the server waits on valid unbounded', [(SERVER,
     'and origin.bounded(backend.valid, self.context, self.evidence) is True',
     'and backend.valid(self.context, self.evidence) is True')],
     [H + 'test_a_hung_valid_or_release_cannot_hold_the_request']),
    ('B24', 'a failed Job probe reads as outside the Job', [(NATIVE,
     'if not job or not self.kernel.IsProcessInJob(handle, job, c.byref(inside)):',
     'if not job:')],
     [T + 'test_a_job_probe_that_fails_is_a_reader_error_not_outside_the_job',
      T + 'test_an_orphan_whose_job_probe_fails_is_not_attested_as_the_user']),
    ('B25', 'a NULL Job handle is probed', [(NATIVE,
     'if not job or not self.kernel.IsProcessInJob(handle, job, c.byref(inside)):',
     'if not self.kernel.IsProcessInJob(handle, job, c.byref(inside)):')],
     [T + 'test_a_null_job_handle_is_refused_because_the_kernel_reads_it_as_any_job']),
    ('B26', 'a worker thread that cannot start keeps its slot', [(ORIGIN,
     '    except BaseException:\n        _slots.release()\n        raise',
     '    except BaseException:\n        raise')],
     [T + 'test_a_worker_thread_that_cannot_start_gives_its_slot_back']),
    ('B27', 'a process Core spawned may be the user', [(ATTEST,
     'if info.outside_core is not True:', 'if False:')],
     [T + 'test_a_reader_that_does_not_say_the_peer_is_outside_core_cannot_make_a_user']),
    ('B28', 'every peer reads as outside Core', [(NATIVE,
     'outside_core=pid != core_pid and not under_core,', 'outside_core=True,')],
     [T + 'test_a_process_core_spawned_outside_every_job_is_not_the_user_t17']),
    ('B29', 'Core among the ancestors is not noticed', [(NATIVE,
     'if parent_pid == core_pid:', 'if False:')],
     [T + 'test_a_process_core_spawned_outside_every_job_is_not_the_user_t17']),
    ('B30', 'Core itself reads as outside Core', [(NATIVE,
     'outside_core=pid != core_pid and not under_core,', 'outside_core=not under_core,')],
     [T + 'test_core_itself_is_not_the_user']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
