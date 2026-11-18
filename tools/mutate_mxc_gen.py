"""The PV20 B2/B3 mutation suite: break each rule of the per-generation journal names and
of the Job end (terminate, never close), run the test written for it, and require it to
fail.

    py tools/mutate_mxc_gen.py               every mutation
    py tools/mutate_mxc_gen.py G01 G05       only these

It edits archeus/node/mxc_ledger.py, local.py and isolation.py and restores them
whatever happens: run it with nothing else against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

LEDGER = 'archeus/node/mxc_ledger.py'
LOCAL = 'archeus/node/local.py'
ISO = 'archeus/node/isolation.py'
T = 'tests/v1/unit/test_mxc_wire_generation.py::'

MUTATIONS = [
    ('G01', 'the process generation dropped from the journal name', [(LEDGER,
     "    return '%s-p%d' % (base, process_seq)",
     "    return base")],
     [T + 'test_an_execution_key_takes_its_process_generation',
      T + 'test_a_resume_of_the_same_execution_launches_under_its_own_journal']),
    ('G02', 'a verifier key used as its own name', [(LEDGER,
     "        base = 'verify_%s_%d' % (vid, attempt)",
     "        base = key")],
     [T + 'test_a_verifier_key_maps_to_a_name_without_slash_or_dot',
      T + 'test_a_verifier_launches_under_the_mapped_name_and_the_broker_gets_its_key']),
    ('G03', 'a process generation of any kind accepted', [(LEDGER,
     "    if type(process_seq) is not int or process_seq < 1:",
     "    if False:")],
     [T + 'test_a_process_generation_that_is_not_a_positive_integer_is_refused']),
    ('G04', 'an execution key that reads as a verifier name accepted', [(LEDGER,
     " and not key.startswith('verify_'):",
     ":")],
     [T + 'test_a_key_the_ledger_cannot_name_is_refused']),
    ('G05', 'the broker revoked by journal name, not the execution key', [(LOCAL,
     "            self.broker.revoke(self.execution_id)",
     "            self.broker.revoke(self.journal)")],
     [T + 'test_a_verifier_launches_under_the_mapped_name_and_the_broker_gets_its_key',
      T + 'test_the_readers_and_the_restart_see_the_journal_name']),
    ('G06', 'the duplicate-journal check made on the bare execution id', [(LOCAL,
     "self.journal in self.ledger.journals():",
     "self.execution_id in self.ledger.journals():")],
     [T + 'test_the_same_generation_twice_is_still_refused']),
    ('G07', 'the resource reader told the execution id, not the journal name', [(LOCAL,
     "        answer = self.resource_reader(self.journal, owner)",
     "        answer = self.resource_reader(self.execution_id, owner)")],
     [T + 'test_the_readers_and_the_restart_see_the_journal_name']),
    ('G08', 'no default Job end from the boundary', [(LOCAL,
     "end_job if end_job is not None else getattr(boundary, 'terminate_job',\n"
     "                                                                    None)",
     "end_job")],
     [T + 'test_an_end_terminates_the_job_through_the_boundary_and_keeps_it_open',
      T + 'test_the_default_is_the_boundarys_terminate_job_method']),
    ('G09', 'the boundary end replacing the one the caller gave', [(LOCAL,
     "end_job if end_job is not None else getattr(boundary, 'terminate_job',\n"
     "                                                                    None)",
     "getattr(boundary, 'terminate_job', end_job)")],
     [T + 'test_an_end_job_the_caller_gives_replaces_the_boundarys']),
    ('G10', 'the watchdog told the execution id, not the journal name', [(LOCAL,
     "self.watchdog.record({'execution_id': self.journal,",
     "self.watchdog.record({'execution_id': self.execution_id,")],
     ['tests/v1/unit/test_mxc_wire_watchdog.py::'
      'test_the_job_is_recorded_before_the_resume_and_after_the_ownership']),
    ('G11', 'the Job closed as it is terminated', [(ISO,
     "            _win(_TerminateJobObject(job, 1), 'TerminateJobObject')",
     "            _win(_TerminateJobObject(job, 1), 'TerminateJobObject')\n"
     "            _CloseHandle(job)")],
     [T + 'TestWindowsTerminateJob::test_it_calls_terminate_with_the_job_and_never_closes_it']),
    ('G12', 'a missing Job passed to the terminate call', [(ISO,
     "                raise IsolationUnavailable('job_missing', 'no Job to terminate')",
     "                pass")],
     [T + 'TestWindowsTerminateJob::test_no_job_raises']),
    ('G13', 'a refused terminate call not reported', [(ISO,
     "            _win(_TerminateJobObject(job, 1), 'TerminateJobObject')",
     "            _TerminateJobObject(job, 1)")],
     [T + 'TestWindowsTerminateJob::test_a_refused_terminate_raises']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
