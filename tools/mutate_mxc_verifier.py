"""The PV20 B11 mutation suite: break each property of the confined verifier on MXC that
tests/v1/unit/test_mxc_verifier_child.py and tests/v1/integration/test_pv20_mxc_verifier.py
pin, run the test written for it, and require it to fail.

    py tools/mutate_mxc_verifier.py                 every mutation
    py tools/mutate_mxc_verifier.py MV01 MV10       only these

It edits archeus/node/mxc_verifier.py, mxc_boundary.py, isolation.py and local.py, and
restores them whatever happens: run it with nothing else against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

CHILD = 'archeus/node/mxc_verifier.py'
BOUNDARY = 'archeus/node/mxc_boundary.py'
ISO = 'archeus/node/isolation.py'
LOCAL = 'archeus/node/local.py'
U = 'tests/v1/unit/test_mxc_verifier_child.py::'
I = 'tests/v1/integration/test_pv20_mxc_verifier.py::'  # noqa: E741

DRAINED = I + 'test_the_checks_output_is_drained_into_its_own_log_and_the_exit_is_the_workloads'
SINK = U + 'test_the_sink_appends_stdout_and_stderr_and_the_reader_is_the_stdin_file'
DEADLINE = U + 'test_a_deadline_is_a_timeout_fault_with_exit_one'
FAULTS = U + 'test_a_bound_or_a_transport_fault_is_a_fault_not_an_exception'
OWN = U + 'test_a_fault_of_cores_own_is_raised_from_wait_and_is_no_fault'
CAP = I + 'test_output_past_the_cap_is_an_error_result_and_never_a_verdict'

MUTATIONS = [
    ('MV01', 'the check\'s output never reaches its log', [(CHILD,
     '        self._out.write(data)\n', '        pass\n')], [SINK, DRAINED]),
    ('MV02', 'stderr is dropped from the log', [(CHILD,
     '        self._out.write(data)\n',
     "        if name == 'stdout':\n            self._out.write(data)\n")], [SINK, DRAINED]),
    ('MV03', 'output is held back until the file closes', [(CHILD,
     '        self._out.flush()\n', '')], [SINK]),
    ('MV04', 'stdin is not the attempt\'s file', [(CHILD,
     'stdin_reader=self._stdin.read)', 'stdin_reader=None)')], [SINK]),
    ('MV05', 'a deadline is no fault', [(CHILD,
     '        except TimeoutError:\n            self.fault = self._late\n',
     '        except TimeoutError:\n            pass\n')], [DEADLINE]),
    ('MV06', 'a fault of Core\'s own is read as a launcher fault', [(CHILD,
     '        except staging.StageError as err:\n            self._raised = err\n',
     "        except staging.StageError as err:\n            self.fault = 'x: %s' % err\n")],
     [OWN, 'tests/v1/integration/test_pv20_mxc_agent_path.py::test_a_workload_outcome_that_is_not_an_exit_code_is_refused']),
    ('MV07', 'a transport fault is raised, not a result', [(CHILD,
     '        except (mxc_native.MxcUnavailable, OSError) as err:',
     '        except OSError as err:')], [FAULTS, CAP]),
    ('MV08', 'a fault answers with no exit at all', [(CHILD,
     '        return 1 if self.fault else self.code', '        return None if self.fault else self.code')],
     [DEADLINE, FAULTS]),
    ('MV09', 'wait does not give the drain the time it was given', [(CHILD,
     '        self._thread.join(timeout)', '        self._thread.join(0)')],
     [U + 'test_wait_gives_a_slow_launch_the_time_it_was_given', DRAINED]),
    ('MV10', 'the files stay open after the drain', [(CHILD,
     '        finally:\n            self._close()\n', '        finally:\n            pass\n')],
     [U + 'test_both_files_are_closed_once_the_drain_is_over']),
    ('MV11', 'a launch that cannot be attached leaks its files', [(CHILD,
     '        except BaseException:\n            self._close()\n            raise\n',
     '        except BaseException:\n            raise\n')],
     [U + 'test_a_launch_that_cannot_be_attached_leaves_no_file_open']),
    ('MV12', 'the transport is bounded by its own default, not the log\'s cap', [(BOUNDARY,
     "                              transport={'output_limit': iso.CONFINED_OUT_MAX,\n"
     "                                         'total_limit': iso.CONFINED_OUT_MAX})\n",
     '                              transport=None)\n')],
     [I + 'test_the_transport_is_bounded_by_the_cap_the_log_is_held_to', CAP]),
    ('MV13', 'the check runs under the boundary\'s deadline, not its own', [(BOUNDARY,
     'math.ceil(timeout * 1000),', 'self.timeout_ms,')],
     [I + 'test_the_deadline_is_this_checks_not_the_boundarys']),
    ('MV14', 'the isolation never asks the boundary to drain the check', [(ISO,
     "            if hasattr(api, 'launch_confined'):", '            if False:')],
     [DRAINED, I + 'test_the_log_sits_outside_every_grant_so_only_core_writes_it']),
    ('MV15', 'a drain fault is no error of the attempt', [(ISO,
     "_over_limit(out_path, roots, start) or getattr(child, 'fault', None) or (",
     '_over_limit(out_path, roots, start) or (')], [CAP]),
    ('MV16', 'the check\'s deadline is not handed to the boundary', [(ISO,
     'profile=rec.profile, job=job, timeout=timeout,', 'profile=rec.profile, job=job, timeout=30,')],
     [I + 'test_the_deadline_is_this_checks_not_the_boundarys']),
    ('MV17', 'the transport options never reach the transport', [(LOCAL,
     'schema_validator,\n                                         switches=switches, **(transport or {}))',
     'schema_validator)')],
     [I + 'test_the_transport_is_bounded_by_the_cap_the_log_is_held_to', CAP]),
    ('MV18', 'a run that stops early closes the Job under the drain', [(ISO,
     "                _end_child(child, error or 'the verifier run ended')\n", '                pass\n')],
     [I + 'test_a_run_that_stops_early_ends_the_launch_before_the_job_is_closed']),
    ('MV19', 'a run that fails closes the Job under the drain', [(ISO,
     "                    _end_child(child, 'the verifier run failed')\n", '                    pass\n')],
     [I + 'test_a_run_that_fails_ends_the_launch_before_the_job_is_closed']),
    ('MV20', 'a child that cannot be built leaves its started launch running', [(BOUNDARY,
     "            launch.cancel(reason='the confined child failed to start')\n", '            pass\n')],
     [I + 'test_a_started_launch_whose_child_cannot_be_built_is_ended']),
    ('MV21', 'a cancelled child does not stop its drain', [(CHILD,
     '        self._stop.set()\n        self._thread.join(PUMP_JOIN_S)\n',
     '        self._thread.join(0)\n')],
     [U + 'test_cancel_stops_the_drain_and_ends_the_launch_with_the_first_reason']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
