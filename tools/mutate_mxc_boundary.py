"""The PV20 B6 mutation suite: break each property of the production MXC boundary that
tests/v1/unit/test_mxc_boundary.py and the T-457 agent path pin, run the test written for
it, and require it to fail.

    py tools/mutate_mxc_boundary.py                 every mutation
    py tools/mutate_mxc_boundary.py MB01 MB10       only these

It edits archeus/node/mxc_boundary.py, local.py and isolation.py, and restores them
whatever happens: run it with nothing else against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

BOUNDARY = 'archeus/node/mxc_boundary.py'
LOCAL = 'archeus/node/local.py'
ISO = 'archeus/node/isolation.py'
T = 'tests/v1/unit/test_mxc_boundary.py::'
A = 'tests/v1/integration/test_pv20_mxc_agent_path.py::'

CLOSED = T + 'test_a_complete_boundary_is_unavailable_while_native_admission_is_closed'
PART = T + 'test_every_part_is_needed_for_it_to_be_available'
DRIFT = T + 'test_pins_that_the_staged_sdk_does_not_match_make_it_unavailable'
MARKER = T + 'test_the_identity_is_a_marker_that_is_not_a_sid'
OPEN = T + 'test_a_generation_that_never_ended_with_a_completion_refuses_the_next_identity'
RESIDUE = T + 'test_deleting_a_profile_releases_the_name_and_records_the_residue'
LAUNCH = T + 'test_a_launch_is_one_policy_over_exactly_the_verified_grants'
EXTRA = T + 'test_extra_writable_grants_join_the_workspace_in_the_policy'

MUTATIONS = [
    ('MB01', 'open native admission is no condition of availability', [(BOUNDARY,
     '        if (mxc.NATIVE_RUN_ENABLED is not True or not callable(self.schema_validator)',
     '        if (not callable(self.schema_validator)')],
     [CLOSED, T + 'test_the_isolated_path_condition_is_the_boundarys_availability']),
    ('MB02', 'the pins are never checked against the staged SDK', [(BOUNDARY,
     '            staging.verify_mxc(self.sdk_root, pins=self.pins)\n'
     '        except staging.StageError:',
     '            pass\n        except staging.StageError:')], [DRIFT]),
    ('MB03', 'a boundary without a ledger is available', [(BOUNDARY,
     '(self.win32, self.ledger, self.sdk_root,', '(self.win32, self.sdk_root,')], [PART]),
    ('MB04', 'the identity marker is spelled like an AppContainer SID', [(BOUNDARY,
     "MARKER = 'psec:'", "MARKER = 'S-1-15-2-'")], [MARKER]),
    ('MB05', 'a generation that never completed does not stop the next identity', [(BOUNDARY,
     "if ops[-1:] != ['completion']]", 'if not ops]')],
     [OPEN, A + 'test_a_resume_is_refused_while_the_process_before_it_never_ended_with_a_'
      'completion']),
    ('MB06', 'the registration residue is never written', [(BOUNDARY,
     "                f.write(json.dumps(line, sort_keys=True) + '\\n')",
     "                f.write('')")], [RESIDUE]),
    ('MB07', 'a deleted profile still holds its name', [(BOUNDARY,
     '        self._reserved.pop(key, None)', '        pass')],
     [RESIDUE, A + 'test_two_fresh_verifiers_get_two_executions_of_their_own']),
    ('MB08', 'a second create never says the name existed', [(BOUNDARY,
     '        existed = key in self._reserved', '        existed = False')],
     [T + 'test_creating_a_profile_reserves_the_name_and_a_second_create_says_it_existed']),
    ('MB09', 'a grant is not scanned for a second name', [(BOUNDARY,
     '            mxc.scan_grant(path)', '            pass')],
     [T + 'test_a_second_name_for_one_file_in_a_granted_tree_fails_the_grants_condition',
      A + 'test_a_grant_with_a_second_name_for_one_file_is_refused_at_every_scan']),
    ('MB10', 'a verified grant is not kept for the launch', [(BOUNDARY,
     '        self._reserved[key].append((os.path.normpath(path), access))',
     '        pass')], [LAUNCH]),
    ('MB11', 'an access the policy cannot list is an established grant', [(BOUNDARY,
     "        if key is None or access not in ('rw', 'rx'):", '        if key is None:')],
     [T + 'test_a_row_the_policy_cannot_list_is_not_an_established_grant']),
    ('MB12', 'a Core path under a granted one is not reachable', [(BOUNDARY,
     '        return key is None or any(iso._within(path, granted) for granted, _ in '
     'self._reserved[key])', '        return key is None')],
     [T + 'test_core_state_inside_a_granted_path_is_reachable_and_fails_two_conditions',
      T + 'test_a_granted_path_inside_core_state_reaches_nothing_of_it']),
    ('MB13', 'a broad principal that can write a grant is never looked for', [(BOUNDARY,
     '        return self.jobs.broad_writer(path)', '        return None')],
     [T + 'test_a_broad_principal_that_can_write_a_grant_fails_the_broad_grants_condition']),
    ('MB14', 'a launch from a directory that is not a writable grant goes ahead', [(BOUNDARY,
     '        if workspace is None:', '        if False:')],
     [T + 'test_a_working_directory_that_is_not_a_writable_grant_is_refused']),
    ('MB15', 'the mailbox and state rows are dropped from the writable grants', [(BOUNDARY,
     '            writable=[p for p in writable if p != workspace],', '            writable=[],')],
     [LAUNCH, A + 'test_an_isolated_agent_launch_compiles_one_policy_and_spawns_once']),
    ('MB16', 'every launch is the first process generation', [(BOUNDARY,
     '            process_seq=len(self._generations(key)) + 1,', '            process_seq=1,')],
     [T + 'test_a_resume_is_the_next_process_generation',
      A + 'test_a_stopped_execution_resumes_as_the_same_identity_with_a_new_process']),
    ('MB17', 'a profile nobody reserved is launched', [(BOUNDARY,
     "        if key is None:\n            raise IsolationUnavailable('profile_unknown',",
     "        if False:\n            raise IsolationUnavailable('profile_unknown',")],
     [T + 'test_a_profile_that_was_never_reserved_is_refused']),
    ('MB18', 'a launch without a deadline goes ahead', [(BOUNDARY,
     '        if self.timeout_ms is None:', '        if False:')],
     [T + 'test_a_launch_without_a_deadline_is_refused']),
    ('MB19', 'ending the Job closes it', [(BOUNDARY,
     '        return self.jobs.terminate_job(job)', '        return self.jobs.close_job(job)')],
     [T + 'test_the_job_and_handle_calls_go_to_the_win32_code_untouched']),
    ('MB20', 'the environment gets a second spelling of a name it holds', [(BOUNDARY,
     'if k.upper() not in have}}', 'if k not in env}}')],
     [T + 'test_the_environment_gains_the_boundarys_rows_without_a_second_spelling']),
    ('MB21', 'the registry claims the marker as a SID', [(ISO,
     "    return sid if str(sid).startswith('S-1-') else ''", '    return sid')],
     [T + 'test_the_registry_names_an_identity_a_sid_only_when_it_is_one',
      A + 'test_an_isolated_agent_launch_compiles_one_policy_and_spawns_once']),
    ('MB22', 'an extra writable grant is never scanned for a second name', [(LOCAL,
     '        linkscan.check_grants(writable, staging.StageError)\n', '')],
     [T + 'test_a_second_name_in_an_extra_writable_grant_is_refused_at_construction']),
    ('MB23', 'the extra writable grants never reach the policy', [(LOCAL,
     '            workspace=(workspace,) + writable if writable else workspace,',
     '            workspace=workspace,')], [EXTRA]),
    ('MB24', 'a verified grant is kept for a launch of another principal', [(BOUNDARY,
     '        self._reserved[key] = []\n', '        self._reserved.setdefault(key, [])\n')],
     [T + 'test_a_verified_grant_is_registered_once_per_path_for_the_launch']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
