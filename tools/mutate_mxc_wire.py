"""The T-245 mutation suite: break each invariant of the MXC wire (the ledger, the
suspended transport, Core's Job and the single resume), run the test written for that
invariant, and require it to fail.

    py tools/mutate_mxc_wire.py              every mutation
    py tools/mutate_mxc_wire.py W01 W04      only these

Each mutant says what it breaks in one edit to one source file; the guarding test is
named, and the suite fails if any mutant survives. Run it with nothing else against the
tree: it edits archeus/node/local.py, archeus/node/mxc.py and archeus/node/mxc_native.py
and restores them whatever happens.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

LOCAL = 'archeus/node/local.py'
SPAWN = 'archeus/node/mxc.py'
NATIVE = 'archeus/node/mxc_native.py'
W = 'tests/v1/unit/test_mxc_wire.py::'
N = 'tests/v1/unit/test_mxc_native.py::'
L = 'tests/v1/integration/test_pv20_mxc_local.py::'
O = 'tests/v1/unit/test_mxc_wire_outcome.py::'
R = 'tests/v1/unit/test_mxc_wire_resources.py::'
C = 'tests/v1/unit/test_mxc_wire_cancel.py::'
D = 'tests/v1/unit/test_mxc_wire_watchdog.py::'
U = 'tests/v1/unit/test_mxc_wire_dupstart.py::'
V = 'tests/v1/unit/test_mxc_wire_review.py::'

MUTATIONS = [
    ('W01', 'the thread is resumed before the ownership facts are written', [(NATIVE,
     "            if before_resume is not None:\n                before_resume(child)\n"
     "            self.resume(child)",
     "            self.resume(child)\n            if before_resume is not None:\n"
     "                before_resume(child)")],
     [N + 'test_the_ownership_seam_runs_between_membership_and_the_resume',
      W + 'test_ownership_is_durable_before_the_resume']),
    ('W02', 'the transport never calls the ownership seam the launch handed it', [(SPAWN,
     "            if before_resume is not None:\n                before_resume(child)\n"
     "            if self.transport.resume(child) != 1:",
     "            if self.transport.resume(child) != 1:")],
     [W + 'test_ownership_is_durable_before_the_resume',
      W + 'test_the_seven_steps_happen_in_that_order']),
    ('W03', 'membership is never verified before the seam', [(NATIVE,
     "            self.assign_job(job, child)\n            if self.in_job(job, child) is not "
     "True:\n                raise MxcUnavailable('launcher Job membership unverified')",
     "            self.assign_job(job, child)\n            if False:\n"
     "                raise MxcUnavailable('launcher Job membership unverified')")],
     [N + 'test_start_orders_assignment_membership_and_single_resume']),
    ('W21', 'membership is never verified on the path the launch takes', [(SPAWN,
     "            if self.transport.in_job(job, child) is not True:\n"
     "                raise MxcUnavailable('launcher Job membership unverified')",
     "            if False:\n"
     "                raise MxcUnavailable('launcher Job membership unverified')")],
     [W + 'test_the_seven_steps_happen_in_that_order']),
    ('W04', 'the create intent is journalled after the create', [(LOCAL,
     "            self._record_intent()                     # (1) durable before anything is "
     "created\n            self.process = self.backend.spawn(self.policy, exe=exe, job=job, "
     "**self._seam())",
     "            self.process = self.backend.spawn(self.policy, exe=exe, job=job, "
     "**self._seam())\n            self._record_intent()")],
     [W + 'test_the_create_intent_is_durable_before_the_create']),
    ('W05', 'an execution id that already has a journal starts again', [(LOCAL,
     "        if self.ledger is not None and self.execution_id in self.ledger.journals():",
     "        if False:")],
     [W + 'test_a_second_launch_of_the_same_execution_id_is_refused',
      W + 'test_a_launch_that_failed_to_journal_is_not_started_again']),
    ('W06', 'the broker keeps admitting for an execution that has ended', [(LOCAL,
     "            self.broker.revoke(self.execution_id)", "            pass")],
     [W + 'test_ending_follows_the_audited_order',
      W + 'test_a_verified_end_records_the_workload_outcome']),
    ('W07', 'the Job is closed before its count is read', [(LOCAL,
     "        limit = self._now() + self.quiescence_wait",
     "        self.boundary.close_job(self.job)\n"
     "        limit = self._now() + self.quiescence_wait")],
     [W + 'test_the_count_is_read_through_an_open_handle_and_a_clean_end_is_reachable',
      W + 'test_ending_follows_the_audited_order']),
    ('W08', 'a second cancel ends the execution twice', [(LOCAL,
     "            if self._ended:\n                return self.end_state",
     "            if False:\n                return self.end_state")],
     [W + 'test_cancel_reports_the_first_ending_and_ends_nothing_twice']),
    ('W09', 'a Job count that cannot be read is taken for an empty Job', [(LOCAL,
     "                self._quiet_why = 'the Job count failed: %s' % type(err).__name__\n"
     "                raise",
     "                self._quiet_why = 'the Job count failed: %s' % type(err).__name__\n"
     "                return True")],
     [W + 'test_a_boundary_that_cannot_answer_leaves_the_end_unverified']),
    ('W10', 'whatever the Job answers is read as no members', [(LOCAL,
     "            if type(n) is int and n == 0:\n                return True",
     "            if True:\n                return True")],
     [W + 'test_the_quiescence_wait_is_bounded_and_honest']),
    ('W11', 'the owned-resource read-back is not required to be verified', [(LOCAL,
     "        if answer is True or (isinstance(answer, (list, tuple)) and answer):\n"
     "            return answer",
     "        if True:\n            return True")],
     [W + 'test_readback_that_is_not_verification_quarantines']),
    ('W12', 'a tree that never quiesced is completed anyway', [(LOCAL,
     "                self._quiet_why = 'the Job answered %r, not zero members' % (n,)\n"
     "                return False",
     "                self._quiet_why = 'the Job answered %r, not zero members' % (n,)\n"
     "                return True")],
     [W + 'test_the_quiescence_wait_is_bounded_and_honest']),
    ('W13', 'an unobserved workload outcome is completed anyway', [(LOCAL,
     "        if outcome is None:\n            self._quarantine('no workload outcome was "
     "observed (%s)' % reason)",
     "        if False:\n            self._quarantine('no workload outcome was observed (%s)' "
     "% reason)")],
     [W + 'test_a_verified_readback_still_needs_an_observed_outcome',
      W + 'test_launcher_zero_is_never_the_workload_outcome']),
    ('W14', 'a launcher that never exited is treated as exited', [(LOCAL,
     "        if type(self.launcher_exit) is not int:", "        if False:")],
     [L + 'test_unfinished_launcher_cannot_supply_result']),
    ('W15', "a reader's non-answer inherits the launcher's success", [(LOCAL,
     "        if type(code) is not int:", "        if False:")],
     [L + 'test_missing_or_forged_result_never_inherits_launcher_success',
      W + 'test_a_forged_outcome_reader_is_still_a_reader_that_is_called']),
    ('W16', "the grants Core already scanned are not scanned again at launch", [(LOCAL,
     "        linkscan.check_grants(grants, staging.StageError)\n"
     "        staging.scan_grants(grants)", "        pass")],
     [W + 'test_the_hardlink_gate_still_runs_at_launch']),
    ('W17', 'a fault in the spawn sequence leaves the child running', [(SPAWN,
     "            try:\n                child.terminate()\n                child.wait(5)",
     "            try:\n                pass")],
     [W + 'test_a_fault_at_any_step_never_leaves_a_running_child']),
    ('W18', "Transport.start's fault path leaves the suspended child running", [(NATIVE,
     "        except BaseException:\n            child.terminate()\n            raise",
     "        except BaseException:\n            raise")],
     [N + 'test_an_ownership_seam_that_fails_never_resumes',
      N + 'test_start_fault_terminates_and_closes']),
    ('W19', 'a launch with no ledger promises an ownership record it cannot make', [(LOCAL,
     "        return {} if self.ledger is None else {'before_resume': self._record_ownership}",
     "        return {'before_resume': self._record_ownership}")],
     [L + 'test_a_backend_without_a_ledger_is_asked_for_no_ownership_hook']),
    ('W20', 'an unverified ending goes unrecorded', [(LOCAL,
     "            self.ledger.append(self.execution_id, 'quarantine',\n"
     "                               reason=str(why)[:200] or 'end unverified')",
     "            pass")],
     [W + 'test_no_reader_at_all_is_never_a_clean_end',
      W + 'test_a_fault_at_any_step_never_leaves_a_running_child']),
    ('W22', 'a quarantined verdict is read as a clean end', [(LOCAL,
     "            clean = self.verdict == mxc_cancel.DISPOSED_VERIFIED",
     "            clean = self.verdict in (mxc_cancel.DISPOSED_VERIFIED,\n"
     "                                     mxc_cancel.QUARANTINE_UNVERIFIED)")],
     [W + 'test_a_failing_ending_step_never_skips_the_next_and_is_never_clean']),
    ('W23', "the ending never closes the launch's own handles", [(LOCAL,
     "self._revoke, self._end_job_step, self._wait_step,",
     "self._revoke, lambda execution: None, self._wait_step,")],
     [W + 'test_a_failing_ending_step_never_skips_the_next_and_is_never_clean']),
    ('W24', "the launch closes the caller's Job, which the caller closes again", [(LOCAL,
     "            clean = self.verdict == mxc_cancel.DISPOSED_VERIFIED",
     "            self.boundary.close_job(self.job)\n"
     "            clean = self.verdict == mxc_cancel.DISPOSED_VERIFIED")],
     [W + 'test_the_owner_closes_the_job_exactly_once_after_the_end']),
    ('W25', 'a torn or corrupt journal is taken as already quarantined', [(LOCAL,
     "        rows, _ = mxc_ledger.read_records(",
     "        rows, invalid = mxc_ledger.read_records("),
     (LOCAL,
      "        return any(row['op'] == 'quarantine' for row in rows)",
      "        return invalid or any(row['op'] == 'quarantine' for row in rows)")],
     [W + 'test_a_torn_journal_still_gets_its_quarantine_line']),
    ('W26', "the launcher's exit code is reported as the bound workload outcome", [(LOCAL,
     "        return self.bound.workload_exit if self.bound.succeeded else None",
     "        return self.launcher_exit")],
     [O + 'test_a_launcher_zero_with_any_other_binding_is_never_success']),
    ('W27', 'an interrupted outcome reader leaves the launch never ended', [(LOCAL,
     "        except BaseException:\n            self._end(reason='the outcome "
     "reader failed', outcome=None)",
     "        except ZeroDivisionError:\n            self._end(reason='the outcome "
     "reader failed', outcome=None)")],
     [O + 'test_a_reader_that_is_interrupted_still_ends_the_launch']),
    ('W28', 'a read-back that differs from the request still resumes the launcher', [(LOCAL,
     "            if differences:\n                raise staging.StageError('the resources read "
     "back differ",
     "            if False:\n                raise staging.StageError('the resources read "
     "back differ")],
     [R + 'test_a_read_back_that_differs_never_resumes',
      R + 'test_a_read_back_that_answers_nothing_usable_never_resumes']),
    ('W29', 'two live launches may share an execution id or a process', [(LOCAL,
     "                if (other is not self and other._ledger_key() == self._ledger_key()",
     "                if (False and other._ledger_key() == self._ledger_key()")],
     [R + 'test_two_live_launches_never_share_a_process']),
    ('W30', "the caller's callback is never asked to end the Job", [(LOCAL,
     "                self._end_job(self.job)", "                pass")],
     [C + 'test_the_steps_run_in_the_cancel_modules_order_on_an_open_job']),
    ('W31', 'an empty list of owned resources is read as a verified read-back', [(LOCAL,
     "        if answer is True or (isinstance(answer, (list, tuple)) and answer):",
     "        if answer is True or isinstance(answer, (list, tuple)):")],
     [C + 'test_only_true_or_a_list_of_owned_ids_answers_the_read_back']),
    ('W32', 'a watchdog that fired or lost its reading is still a clean end', [(LOCAL,
     "        if report['state'] != mxc_watchdog.ARMED:", "        if False:")],
     [D + 'test_a_watchdog_that_fired_ends_the_launch_not_clean',
      D + 'test_a_shared_watchdog_that_fired_is_never_a_clean_end']),
    ('W33', 'the Job is never recorded with the watchdog before the resume', [(LOCAL,
     "        if self.watchdog is not None:                 # last: a refusal here still ends "
     "the child",
     "        if False:")],
     [D + 'test_the_job_is_recorded_before_the_resume_and_after_the_ownership']),
    ('W34', "one launch's clean end disarms a watchdog shared with other jobs", [(LOCAL,
     "        if report['recorded'] == [self.execution_id]:", "        if True:")],
     [D + 'test_a_watchdog_shared_with_another_job_stays_armed']),
    ('W35', 'a start never claims its execution id before the journal check', [(LOCAL,
     "            _MXC_CLAIMS.add(claim)", "            pass")],
     [U + 'test_two_threads_starting_one_id_let_exactly_one_proceed',
      U + 'test_a_start_is_refused_while_another_is_still_writing_its_intent']),
    ('W36', 'a claimed execution id is never released after a failed start', [(LOCAL,
     "                    _MXC_CLAIMS.discard(claim)", "                    pass")],
     [U + 'test_a_failing_intent_write_leaves_no_journal_and_frees_the_id',
      U + 'test_a_start_that_cannot_read_the_ledger_frees_the_id']),
    ('W37', 'a clock reading that is not finite is believed', [(LOCAL,
     "        if type(now) not in (int, float) or not math.isfinite(now):", "        if False:")],
     [V + 'test_a_clock_with_no_usable_reading_never_proves_quiescence']),
    ('W38', 'a cancelled launch is still resumed', [(LOCAL,
     "        if self._ended:\n            raise staging.StageError('MXC launch was ended before "
     "it resumed')",
     "        if False:\n            raise staging.StageError('MXC launch was ended before "
     "it resumed')")],
     [V + 'test_a_cancel_that_lands_before_the_resume_stops_the_resume']),
    ('W39', 'a child that outlived a cancel during its start keeps running', [(LOCAL,
     "            if self._ended:                           # cancel() ran while the child "
     "was made",
     "            if False:")],
     [V + 'test_a_cancel_that_lands_after_the_resume_terminates_the_child']),
    ('W40', 'a callback that cancels again deadlocks the ending', [(LOCAL,
     "self._end_lock = threading.RLock()", "self._end_lock = threading.Lock()")],
     [V + 'test_a_callback_that_cancels_again_does_not_deadlock_the_ending']),
    ('W41', 'a ledger that cannot be read at the end leaves the launch never ended', [(LOCAL,
     "        except Exception:\n            pass                                       # the "
     "ledger keeps what it could",
     "        except ZeroDivisionError:\n            pass                                       "
     "# the ledger keeps what it could")],
     [V + 'test_a_ledger_that_cannot_be_read_at_the_end_still_ends_the_launch']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
