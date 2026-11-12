"""The fix batch 16 mutation suite (the review of pv20-fx15): break each rule the batch
added, run the test that guards it, and require it to fail.

    py tools/mutate_fx16.py            every mutation
    py tools/mutate_fx16.py H01 H05    only these

Same runner as tools/mutate_p11.py. It edits sources: run it with nothing else running
against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (its runner)

RED = 'archeus/core/redact.py'
BASE = 'archeus/harnesses/base.py'
BRK = 'archeus/node/broker.py'
ISO = 'archeus/node/isolation.py'
PV = 'archeus/core/pv20.py'
RUN = 'archeus/core/runtime.py'
MGR = 'archeus/core/execution/manager.py'
R = 'tests/v1/unit/test_redact_red_team.py::'
S = 'tests/v1/integration/test_stream_redaction_red_team.py::'
N = 'tests/v1/unit/test_fix_node_broker.py::'
F = 'tests/v1/unit/test_fx32_isolation_stop.py::'
A = 'tests/v1/unit/test_pv20_activate.py::'
C = 'tests/v1/unit/test_confined_run.py::'
X = 'tests/v1/unit/test_broker_execution.py::'

MUTATIONS = [
    ('H01', 'a lowercase word of an event is masked as a short fragment', [(RED,
     r"""_LINE.fullmatch(x) and not (x.isalpha() and x.islower())""",
     r"""_LINE.fullmatch(x)""")],
     [R + 'test_the_structural_words_of_an_event_stay_while_a_key_is_open',
      S + 'test_a_result_after_an_open_key_keeps_its_usage_summary_and_error']),
    ('H02', 'any alphabetic word is let through an open key', [(RED,
     r"""not (x.isalpha() and x.islower())""",
     r"""not x.isalpha()""")],
     [R + 'test_a_short_fragment_that_is_not_a_lowercase_word_is_still_held']),
    ('H03', 'a field name that reads as prose ends the key', [(RED,
     r"""last_mark(text), None if name else text)""",
     r"""last_mark(text), text)""")],
     [R + 'test_a_field_name_that_reads_as_prose_does_not_end_the_key']),
    ('H04', 'a body line followed by a few characters is not key material', [(RED,
     r"""{16}(?:\\[nrt]|[^A-Za-z0-9+/=\n]){0,4}[ \t\r]*$'""",
     r"""{16}[ \t\r]*$'""")],
     [R + 'test_a_body_line_with_a_few_trailing_characters_is_held',
      R + 'test_a_body_line_used_as_a_field_name_with_a_colon_is_held']),
    ('H05', 'a body line followed by a literal backslash-n is not key material', [(RED,
     r"""(?:\\[nrt]|[^A-Za-z0-9+/=\n]){0,4}""",
     r"""(?:[^A-Za-z0-9+/=\n]){0,4}""")],
     [R + 'test_a_body_line_with_a_few_trailing_characters_is_held']),
    ('H06', 'an oversized line caught mid-write is cut where the read ended', [(BASE,
     r"""        if not rest:
            return None
        if rest.endswith(b'\n'):""",
     r"""        if not rest or rest.endswith(b'\n'):""")],
     [S + 'test_an_oversized_line_caught_mid_write_is_read_whole_once_it_ends']),
    ('H07', 'the head of an oversized line inside a key is shown', [(BASE,
     r"""'[redacted]' if state is not None or mark is not None else""",
     r"""'[redacted]' if mark is not None else""")],
     [S + 'test_the_head_of_an_oversized_line_inside_or_opening_a_key_is_masked']),
    ('H08', 'the head of an oversized line with its own marker is shown', [(BASE,
     r"""'[redacted]' if state is not None or mark is not None else""",
     r"""'[redacted]' if state is not None else""")],
     [S + 'test_the_head_of_an_oversized_line_inside_or_opening_a_key_is_masked']),
    ('H09', 'a blank escape is not read in an oversized line', [(BASE,
     r"""_ASCII = re.compile(r'\\u00([0-7][0-9a-fA-F])|\\[nrtbf]')""",
     r"""_ASCII = re.compile(r'\\u00([0-7][0-9a-fA-F])')""")],
     [S + 'test_an_oversized_line_whose_marker_has_escaped_blanks_opens_the_key']),
    ('H10', 'the head of a dropped line keeps the token cut at its end', [(BASE,
     r"""                _CUT.sub('', raw[:200].decode('utf-8', errors='replace')).strip())""",
     r"""                raw[:200].decode('utf-8', errors='replace').strip())""")],
     [S + 'test_the_head_cut_of_an_oversized_line_keeps_no_token_prefix']),
    ('H11', 'a marker in an oversized JSON line opens a stderr key', [(BASE,
     r"""        channel = 'json' if raw.lstrip""",
     r"""        channel = 'stderr' if raw.lstrip""")],
     [S + 'test_an_oversized_json_line_opens_a_key_that_json_prose_ends']),
    ('H12', 'a repeated field name drops a marker before redaction reads it', [(BASE,
     r"""    if len(obj) != len(pairs):""",
     r"""    if False:""")],
     [S + 'test_a_marker_in_a_json_line_of_an_odd_shape_opens_the_key']),
    ('H13', 'a byte order mark makes a JSON line a stderr line', [(BASE,
     r"""    line = raw.decode('utf-8', errors='replace').strip().lstrip('﻿')""",
     r"""    line = raw.decode('utf-8', errors='replace').strip()""")],
     [S + 'test_a_marker_in_a_json_line_of_an_odd_shape_opens_the_key',
      S + 'test_a_bom_before_an_event_does_not_make_it_a_stderr_line']),
    ('H14', 'a JSON array line is not decoded', [(BASE,
     r"""    if line[0] in '{[':""",
     r"""    if line[0] == '{':""")],
     [S + 'test_a_marker_in_a_json_line_of_an_odd_shape_opens_the_key']),
    ('H15', 'close returns while an issue is still in flight', [(BRK,
     r"""            drained = self._drained.wait_for(
                lambda: all(t == me for t in self._issuing),
                timeout=None if deadline is None else max(0.0, deadline - time.monotonic()))""",
     r"""            drained = True""")],
     [N + 'test_close_waits_for_an_issue_in_flight_and_leaves_no_listener']),
    ('H16', 'an issue in flight is not counted', [(BRK,
     r"""            self._issuing.append(me)
        try:""",
     r"""            self._issuing.append(me)
            self._issuing.remove(me)
        try:""")],
     [N + 'test_close_waits_for_an_issue_in_flight_and_leaves_no_listener']),
    ('H17', 'a Job is created after Core began to stop', [(ISO,
     r"""            with self._state:
                if self.closed:
                    raise IsolationClosed()
                job = self._jobs.get(execution_id)""",
     r"""            with self._state:
                job = self._jobs.get(execution_id)""")],
     [A + 'test_a_late_worker_can_create_no_job_once_core_is_stopping',
      F + 'test_a_closed_authority_never_creates_a_job_for_an_unseen_execution']),
    ('H18', 'an identity is established after Core began to stop', [(ISO,
     r"""            self._check_establishment()
            for _ in range(RECORD_RETRIES):""",
     r"""            for _ in range(RECORD_RETRIES):""")],
     [A + 'test_a_late_worker_can_create_no_job_once_core_is_stopping']),
    ('H19', 'a confined check runs on after Core began to stop', [(ISO,
     r"""                if self.closed:
                    raise IsolationClosed()
                exited = child.wait(""",
     r"""                exited = child.wait(""")],
     [C + 'test_a_confined_check_running_when_core_stops_ends_at_its_next_poll']),
    ('H20', 'the workers are joined before admission closes', [(RUN,
     r"""                self.pv20.quiesce(deadline=end)""",
     r"""                pass""")],
     [A + 'test_stop_closes_admission_before_it_joins_and_the_workloads_after']),
    ('H21', 'the isolation authority stays open while the workers finish', [(PV,
     r"""        try:
            self.node.isolation.close_admission(deadline=deadline)""",
     r"""        try:
            pass""")],
     [A + 'test_stop_closes_admission_before_it_joins_and_the_workloads_after',
      A + 'test_a_late_worker_can_create_no_job_once_core_is_stopping']),
    ('H22', 'the workloads end before the workers are joined', [(PV,
     r"""            self.node.isolation.close_admission(deadline=deadline)""",
     r"""            self.node.isolation.close_admission()
            _dispose(self.node)""")],
     [A + 'test_stop_closes_admission_before_it_joins_and_the_workloads_after']),
    ('H23', 'each worker gets the whole quiesce time', [(RUN,
     r"""worker.join(max(0.0, end - time.monotonic()))""",
     r"""worker.join(QUIESCE_S)""")],
     [A + 'test_the_workers_share_one_quiesce_deadline_and_a_late_one_is_reported']),
    ('H24', 'a worker still alive after the deadline is not reported', [(RUN,
     r"""                    log.warning('%s did not stop within %gs; it can admit nothing new',
                                type(worker).__name__, QUIESCE_S)""",
     r"""                    pass""")],
     [A + 'test_the_workers_share_one_quiesce_deadline_and_a_late_one_is_reported']),
    ('H25', 'a grant refused by a closing broker refuses the binding', [(MGR,
     r"""stop_reason='spawn' if isinstance(err, broker_mod.BrokerClosed)""",
     r"""stop_reason='binding' if isinstance(err, broker_mod.BrokerClosed)""")],
     [X + 'test_a_grant_refused_by_a_closing_broker_is_an_uncharged_failed_start']),
    ('H26', 'broker drains before isolation admission closes', [(PV,
     r"""        try:
            self.node.isolation.close_admission(deadline=deadline)
        finally:
            self.broker.close(deadline=deadline)""",
     r"""        try:
            self.broker.close(deadline=deadline)
        finally:
            self.node.isolation.close_admission(deadline=deadline)""")],
     [A + 'test_broker_drain_uses_worker_deadline_after_isolation_closes']),
    ('H27', 'an admission that will not close stops stop() short', [(RUN,
     r"""            try:
                self.pv20.quiesce(deadline=end)
            except Exception as error:
                closing = error
""",
     r"""            self.pv20.quiesce(deadline=end)
""")],
     [A + 'test_a_broker_that_will_not_close_does_not_stop_the_stop_short']),
    ('H28', 'an admission error is swallowed by stop()', [(RUN,
     r"""                closing = error
            for worker in (self.exec, self.verify, self.loop):""",
     r"""                pass
            for worker in (self.exec, self.verify, self.loop):""")],
     [A + 'test_a_broker_that_will_not_close_does_not_stop_the_stop_short']),
    ('H29', 'a stop deletes the identity and the record of an execution it holds', [(PV,
     r"""            node.isolation.fence(execution_id, wait=0)""",
     r"""            node.isolation.teardown(execution_id, reason='core stopping')""")],
     [A + 'test_a_stop_closes_the_job_of_a_live_execution_and_keeps_the_record_it_resumes_from']),
    ('H30', 'a stop waits for each Job to empty before it closes it', [(PV,
     r"""            node.isolation.fence(execution_id, wait=0)""",
     r"""            node.isolation.fence(execution_id)""")],
     [A + 'test_a_held_workload_is_disposed_after_the_grants_and_before_the_watchdog']),
    ('H40', 'broker drain ignores stop deadline', [(BRK,
     "timeout=None if deadline is None else max(0.0, deadline - time.monotonic()))",
     "timeout=None)")], [N + 'test_close_deadline_revokes_even_a_stalled_issue']),
    ('H41', 'broker drain timeout is silent', [(BRK,
     "        if not drained:", "        if False:")],
     [N + 'test_close_deadline_revokes_even_a_stalled_issue']),
    ('H42', 'pending listeners survive drain timeout', [(BRK,
     "            pending = list(self._pending.values())", "            pending = []")],
     [N + 'test_close_deadline_revokes_even_a_stalled_issue']),
    ('H43', 'isolation cancellation waits until after drain', [(ISO,
     "        self.closed = True\n        acquired =", "        self.closed = False\n        acquired =")],
     [A + 'test_establishment_cannot_resume_writes_after_admission_drain_timeout']),
    ('H44', 'record writes resume after admission timeout', [(ISO,
     "    def _save_establishment(self, rec):\n        self._check_establishment()",
     "    def _save_establishment(self, rec):\n        pass")],
     [A + 'test_establishment_cannot_resume_writes_after_admission_drain_timeout']),
    ('H45', 'isolation drain ignores stop deadline', [(ISO,
     "        acquired = self._lock.acquire(timeout=-1 if deadline is None else\n"
     "                                      max(0.0, deadline - time.monotonic()))",
     "        acquired = self._lock.acquire()")],
     [A + 'test_establishment_cannot_resume_writes_after_admission_drain_timeout']),
    ('H46', 'a profile starts after admission drain timed out', [(ISO,
     "        try:\n            self._check_establishment()\n            identity =",
     "        try:\n            identity =")],
     [A + 'test_establishment_cannot_resume_writes_after_admission_drain_timeout']),
    ('H47', 'a Job returning after admission timeout is retained', [(ISO,
     "                if not held:\n                    self.boundary.close_job(job)\n"
     "                    raise IsolationClosed()\n", "")],
     [A + 'test_establishment_cannot_resume_writes_after_admission_drain_timeout']),
    ('H48', 'failure cleanup is aborted by the admission close', [(ISO,
     "            try:\n                step(*args, **kw)",
     "            try:\n                self._check_establishment()\n                step(*args, **kw)")],
     [A + 'test_establishment_cannot_resume_writes_after_admission_drain_timeout']),
    ('H49', 'a late resolver starts a listener after stop returned', [(BRK,
     "        with self._lock:\n            if self._closed:\n"
     "                raise BrokerClosed('the broker is closed')\n        endpoint =",
     "        endpoint =")], [N + 'test_close_deadline_revokes_even_a_stalled_issue']),
    ('H50', 'a late launch leaves its listener alive', [(BRK,
     "            # A launch already in flight may finish after close drained its endpoint.\n"
     "            self.transport.close(endpoint)", "            pass")],
     [N + 'test_close_deadline_revokes_even_a_stalled_issue']),
    ('H52', 'an endpoint returned after close starts serving', [(BRK,
     "        if closed:\n            self.transport.close(endpoint)\n"
     "            raise BrokerClosed('the broker is closed')\n        try:",
     "        try:")], [N + 'test_close_deadline_revokes_even_a_stalled_issue']),
    ('H53', 'an endpoint returned after close stays pending', [(BRK,
     "            if not closed:\n                self._pending[id(endpoint)] = endpoint",
     "            self._pending[id(endpoint)] = endpoint")],
     [N + 'test_close_deadline_revokes_even_a_stalled_issue']),
    ('H54', 'the ownership save of a created profile is refused after close', [(ISO,
     "            try:\n                return self._save(rec)",
     "            try:\n                return self._save_establishment(rec)")],
     [A + 'test_establishment_cannot_resume_writes_after_admission_drain_timeout']),
    ('H55', 'a Job created after the stop began is published anyway', [(ISO,
     "                    held = not self.closed",
     "                    held = True")],
     [F + 'test_a_job_created_after_the_stop_began_is_closed_and_never_held']),
    ('H56', 'the held-Job snapshot is taken outside the state lock', [(ISO,
     "    def held_jobs(self):\n        with self._state:\n            return dict(self._jobs)",
     "    def held_jobs(self):\n        return dict(self._jobs)")],
     [F + 'test_the_held_jobs_snapshot_is_taken_under_the_state_lock']),
    ('H57', 'a record write from an older read may overwrite an owned record', [(ISO,
     "            if stored.get('gen', 0) != rec.gen:",
     "            if stored.get('gen', 0) != rec.gen and not stored.get('owned'):")],
     [F + 'test_ownership_is_never_turned_back_to_unowned_by_a_write_from_an_older_read',
      F + 'test_a_late_ownership_write_is_not_undone_by_a_stale_reclaim']),
    ('H58', 'a record write is not checked against the stored record', [(ISO,
     "            if stored.get('gen', 0) != rec.gen:",
     "            if False:")],
     [F + 'test_a_record_saved_on_a_stale_read_is_refused_and_the_stored_one_stays',
      F + 'test_a_late_ownership_write_is_not_undone_by_a_stale_reclaim']),
    ('H59', 'a stop is recorded as an isolation failure', [(ISO,
     "            if isinstance(err, IsolationClosed):\n                return",
     "            if False:\n                return")],
     [F + 'test_a_stop_is_not_recorded_as_an_isolation_failure']),
    ('H60', 'a failure after close escapes as a plain refusal, not BrokerClosed', [(BRK,
     "            if closed and not isinstance(err, BrokerClosed):",
     "            if False:")],
     [N + 'test_a_resolver_failure_after_close_is_reported_as_closed',
      N + 'test_a_creation_failure_after_close_is_reported_as_closed']),
    ('H61', 'the broker does not cancel its transport when it closes', [(BRK,
     "        self.transport.cancel()\n",
     "")],
     [N + 'test_a_socket_bound_inside_a_stalled_creation_is_closed_by_a_deadline_close']),
    ('H62', 'a stopped Core consumes a verifier attempt before refusing it', [(ISO,
     r"""            self._check_establishment()
            _admit(key)""",
     r"""            _admit(key)""")],
     [F + 'test_a_stopped_core_consumes_no_verifier_attempt_through_run_confined']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
