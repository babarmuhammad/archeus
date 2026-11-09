"""The fix batch 15 mutation suite (the review of pv20-int8): break each rule the batch
added, run the test that guards it, and require it to fail.

    py tools/mutate_fx15.py            every mutation
    py tools/mutate_fx15.py G01 G05    only these

Same runner as tools/mutate_p11.py. It edits sources: run it with nothing else running
against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (its runner)

RED = 'archeus/core/redact.py'
BASE = 'archeus/harnesses/base.py'
R = 'tests/v1/unit/test_redact_red_team.py::'
S = 'tests/v1/integration/test_stream_redaction_red_team.py::'
ROUTER = 'archeus/core/routing/router.py'
E = 'tests/v1/unit/test_effort_selection.py::'
OUT = 'archeus/core/application/outcomes.py'
W = 'tests/v1/unit/test_outcomes_rework.py::'
RUN = 'archeus/core/runtime.py'
PV = 'archeus/core/pv20.py'
BRK = 'archeus/node/broker.py'
A = 'tests/v1/unit/test_pv20_activate.py::'
N = 'tests/v1/unit/test_fix_node_broker.py::'

MUTATIONS = [
    ('G01', 'a field name does not carry the key state to the fields after it', [(RED,
     r"""            dst[k], state = _name(v, state)""",
     r"""            dst[k] = _name(v, state)[0]""")],
     [R + 'test_a_marker_used_as_a_json_field_name_opens_the_key_for_later_fields',
      R + 'test_a_key_line_used_as_a_json_field_name_is_held']),
    ('G02', 'a field name is read after the value that follows it', [(RED,
     r"""                entries += [(key, slot, 0, _KEY, depth + 1), (x, slot, 1, key, depth + 1)]""",
     r"""                entries += [(x, slot, 1, key, depth + 1), (key, slot, 0, _KEY, depth + 1)]""")],
     [R + 'test_a_field_name_is_read_before_its_own_value']),
    ('G03', 'a short fragment of an open key is shown', [(RED,
     r""" or not name and _short(text):""",
     r""":""")],
     [R + 'test_a_short_key_fragment_in_an_open_key_is_held',
      R + 'test_a_short_fragment_is_held_in_the_stderr_channel_too']),
    ('G04', 'a plain field name is masked as a short fragment', [(RED,
     r""" or not name and _short(text):""",
     r""" or _short(text):""")],
     [R + 'test_a_plain_field_name_stays_while_a_key_is_open']),
    ('G05', 'a string with one base64 line is a short fragment', [(RED,
     r"""    return bool(lines) and all(_LINE.fullmatch(x) for x in lines)""",
     r"""    return bool(lines) and any(_LINE.fullmatch(x) for x in lines)""")],
     [R + 'test_a_string_of_a_base64_line_and_prose_is_not_a_short_fragment']),
    ('G06', 'an empty string is a short fragment', [(RED,
     r"""    return bool(lines) and all(""",
     r"""    return all(""")],
     [R + 'test_an_empty_string_is_not_masked_while_a_key_is_open']),
    ('G07', 'an escaped character of a marker in an oversized line is not read', [(BASE,
     r"""        flat = _BLANKS.sub(' ', _ASCII.sub(lambda m: chr(int(m[1], 16)),
                                           seam + rest.decode('utf-8', errors='replace')))""",
     r"""        flat = _BLANKS.sub(' ', seam + rest.decode('utf-8', errors='replace'))""")],
     [S + 'test_an_oversized_json_line_with_an_escaped_marker_opens_the_key',
      S + 'test_an_escape_cut_by_the_read_boundary_still_opens_the_key']),
    ('G08', 'blanks of an oversized line are not folded', [(BASE,
     r"""        flat = _BLANKS.sub(' ', _ASCII.sub(lambda m: chr(int(m[1], 16)),
                                           seam + rest.decode('utf-8', errors='replace')))""",
     r"""        flat = _ASCII.sub(lambda m: chr(int(m[1], 16)), seam + rest.decode('utf-8', errors='replace'))""")],
     [S + 'test_a_marker_whose_blanks_span_a_read_boundary_opens_the_key',
      S + 'test_a_marker_whose_blanks_end_at_the_first_read_boundary']),
    ('G09', 'a model whose efforts its harness lacks keeps the requested effort', [(ROUTER,
     r"""            c['effort'] = None""",
     r"""            pass""")],
     [E + 'test_a_model_that_states_efforts_its_harness_lacks_takes_no_effort']),
    ('G10', 'a required effort no common level can take is not refused', [(ROUTER,
     r"""            if req.get('effort_required'):
                return 'model %s accepts none""",
     r"""            if False:
                return 'model %s accepts none""")],
     [E + 'test_a_required_effort_a_model_with_no_common_level_cannot_take_eliminates_it']),
    ('G11', 'a model that states no efforts is held to none', [(ROUTER,
     r"""        if stated and not allowed:""",
     r"""        if not allowed:""")],
     [E + 'test_the_router_clamps_effort_to_the_chosen_model_and_records_it']),
    ('G12', 'an execution not yet spawned is counted as a run', [(OUT,
     r""" and e.state != 'INTENT')""",
     r""")""")],
     [W + 'test_an_execution_still_pending_is_not_a_second_run']),
    ('G13', 'only a pending execution is not a run: a started one that is not finished is not either', [(OUT,
     r""" and e.state != 'INTENT')""",
     r""" and e.state in ('ENDED_OK', 'ENDED_ERROR'))""")],
     [W + 'test_a_started_execution_still_running_is_a_second_run']),
    ('G14', 'a stop does not wait for the workers that admit work', [(RUN,
     r"""                    worker.join(QUIESCE_S)""",
     r"""                    pass""")],
     [A + 'test_stop_joins_the_dispatch_workers_before_the_activation_closes']),
    ('G15', 'a core with no activation waits for its workers', [(RUN,
     r"""        if self.pv20 is not None:
            # a dispatch in flight""",
     r"""        if True:
            # a dispatch in flight""")],
     [A + 'test_a_core_without_an_activation_does_not_wait_for_its_workers']),
    ('G16', 'a worker that was never started cannot be joined', [(RUN,
     r"""        self._stop.set()

    def join(self, timeout):
        if self._thread.is_alive():
            self._thread.join(timeout)""",
     r"""        self._stop.set()

    def join(self, timeout):
        self._thread.join(timeout)""")],
     [A + 'test_production_core_binds_every_switch']),
    ('G17', 'a closed broker still issues', [(BRK,
     r"""        with self._lock:
            self._closed = True
        return self.revoke_all()""",
     r"""        return self.revoke_all()""")],
     [N + 'test_a_closed_broker_revokes_its_grants_and_issues_no_more_listeners',
      A + 'test_no_listener_is_bound_after_the_activation_closed']),
    ('G18', 'an issue in flight when the broker closes keeps its listener', [(BRK,
     r"""            closed = self._closed
""",
     r"""            closed = False
""")],
     [N + 'test_an_issue_in_flight_when_the_broker_closes_leaves_no_listener']),
    ('G19', 'revoke_all closes the broker', [(BRK,
     r"""    def revoke_all(self):
        with self._lock:""",
     r"""    def revoke_all(self):
        self._closed = True
        with self._lock:""")],
     [N + 'test_revoke_all_alone_leaves_the_broker_open']),
    ('G20', 'held workloads are not disposed', [(PV,
     r"""            resources.callback(lambda: _dispose(node))
""",
     r"""""")],
     [A + 'test_a_held_workload_is_disposed_after_the_grants_and_before_the_watchdog']),
    ('G21', 'the watchdog closes before the broker and the workloads', [(PV,
     r"""            resources.callback(running.close)
            resources.callback(lambda: _dispose(node))
            resources.callback(broker.close)
""",
     r"""            resources.callback(lambda: _dispose(node))
            resources.callback(broker.close)
            resources.callback(running.close)
""")],
     [A + 'test_a_held_workload_is_disposed_after_the_grants_and_before_the_watchdog',
      A + 'test_production_core_binds_every_switch']),
    ('G22', 'a workload that will not go keeps the rest', [(PV,
     r"""            first = first or error""",
     r"""            raise""")],
     [A + 'test_a_workload_that_will_not_go_does_not_keep_the_rest_or_the_watchdog_open']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
