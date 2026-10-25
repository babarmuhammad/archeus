"""The ADR-0047 / D-26 mutation suite (P21; testing-strategy §10, CX-1…CX-18):
break each invariant of context capacity, run the tests that guard it, and
require them to fail.

    py tools/mutate_p21.py            every mutation
    py tools/mutate_p21.py Z05 Z08    only these

The runner is tools/mutate_p18.py's (tools/mutate_p11.py's snippet engine; a
mutant guarded by a browser test rebuilds the SPA): each mutation replaces exact
snippets (each must occur once), runs its tests, and restores the files whatever
happens; a mutation the tests do not catch ("survived") fails the run. It edits
sources: run it with nothing else running against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402  (its runner)

PR = 'archeus/core/execution/pressure.py'
EX = 'archeus/core/application/executions.py'
HO = 'archeus/core/execution/handoff.py'
MGR = 'archeus/core/execution/manager.py'
RT = 'archeus/core/routing/router.py'
GD = 'archeus/core/domain/guards.py'
ND = 'archeus/node/local.py'
U = 'tests/v1/unit/test_pressure_units.py'
I = 'tests/v1/integration/test_context_capacity.py'
E = 'tests/v1/integration/test_execution.py'
RS = 'archeus/core/application/resources.py'
CP = 'archeus/core/execution/checkpoint.py'
XU = 'tests/v1/unit/test_execution_units.py'
RI = 'tests/v1/integration/test_routing.py'
MT = 'archeus/core/metrics.py'
DR = 'archeus/core/doctor.py'
RTM = 'archeus/core/runtime.py'
D = 'tests/v1/integration/test_p21_metrics_doctor.py'
QRY = 'archeus/core/application/queries.py'
ROUTES = 'archeus/api/routes.py'
CMDBAR = 'clients/app/src/surfaces/CommandBar.tsx'
GUI = 'archeus/cli/gui.py'
SRCH = 'tests/v1/integration/test_p21_search.py::'
PAL_E2E = 'tests/v1/e2e/test_spa_palette.py::test_the_palette_moves_by_arrows_and_acts_by_cores_verbs'
SHL = 'tests/v1/integration/test_gui_shell.py::'
TR = 'archeus/core/application/trace.py'
CC = 'archeus/harnesses/claude_code/adapter.py'
GR = 'archeus/core/application/grammar.py'
CV = 'archeus/core/application/conversation.py'
DG = 'archeus/core/world/digest.py'
TT = 'tests/v1/integration/test_trace.py'
LV = 'archeus/core/application/live.py'
TPR = 'archeus/cli/tui/present.py'
ORB = 'clients/app/src/state/orbit.ts'
PL = 'tests/v1/integration/test_p21_live.py::'
PAL = 'clients/app/src/state/palette.ts'
PTS = 'clients/app/src/state/present.ts'

MUTATIONS = [
    # ── unknown is never 0 (CX-8) ──
    ('Z01', 'an unknown window read as pressure 0', [(PR,
     "    return ctx, (used / float(window) if window else None)",
     "    return ctx, (used / float(window) if window else 0.0)")],
     [U + '::test_no_window_or_no_report_is_unavailable_never_zero']),
    ('Z02', 'remaining computed from unknown figures as 0', [(PR,
     "    if q not in ('signalled', 'unavailable'):\n        left = ctx['window'] - ctx['used_tokens']",
     "    if True:\n        left = (ctx['window'] or 0) - (ctx['used_tokens'] or 0)")],
     [U + '::test_no_window_or_no_report_is_unavailable_never_zero',
      U + '::test_precompact_is_signalled_and_never_a_usage_report']),
    # ── PreCompact is a signal, not a report (CX-9) ──
    ('Z03', 'a PreCompact reading derived as reported', [(PR,
     "    if ctx.get('signal') == 'precompact':",
     "    if False:")],
     [U + '::test_precompact_is_signalled_and_never_a_usage_report',
      I + '::test_precompact_is_the_signalled_quality_with_the_policy_stand_in']),
    ('Z04', 'a PreCompact recorded as a usage report of 0.9', [(MGR,
     "            p['context'] = P.signalled(p['context'], p['offset'])",
     "            p['context'] = P.reported({'input_tokens': 180000}, 200000, 'offer',\n"
     "                                      p['offset'], p['context'])[0]")],
     [I + '::test_precompact_is_the_signalled_quality_with_the_policy_stand_in']),
    ('Z05', 'staleness ignored', [(PR,
     "    if ctx.get('at_seq') is not None and (stream_offset or 0) > ctx['at_seq']:",
     "    if False:")],
     [U + '::test_output_after_the_report_makes_it_stale_by_offsets_alone']),
    # ── the frozen thresholds (p12 D20; CX-1, CX-2) ──
    ('Z06', 'the hand-off threshold raised', [(PR,
     "PRESSURE_HANDOFF, PRESSURE_PRECOMPACT = 0.75, 0.9",
     "PRESSURE_HANDOFF, PRESSURE_PRECOMPACT = 0.77, 0.9")],
     [I + '::test_cx2_at_the_threshold_the_report_hands_off_with_its_basis']),
    ('Z07', 'the hand-off threshold lowered', [(PR,
     "PRESSURE_HANDOFF, PRESSURE_PRECOMPACT = 0.75, 0.9",
     "PRESSURE_HANDOFF, PRESSURE_PRECOMPACT = 0.73, 0.9")],
     [I + '::test_cx1_below_the_threshold_never_hands_off']),
    ('Z08', 'the PreCompact stand-in changed', [(PR,
     "PRESSURE_HANDOFF, PRESSURE_PRECOMPACT = 0.75, 0.9",
     "PRESSURE_HANDOFF, PRESSURE_PRECOMPACT = 0.75, 0.95")],
     [I + '::test_precompact_is_the_signalled_quality_with_the_policy_stand_in']),
    # ── the guard (CX-3) ──
    ('Z09', 'only the immediate predecessor compared', [(EX,
     "    earlier = [x.end_state_digest for x in chain if x.end_state_digest is not None]",
     "    earlier = [x.end_state_digest for x in chain[:1] if x.end_state_digest is not None]")],
     [I + '::test_cx3_a_chain_that_returns_to_an_earlier_state_ends_charged']),
    ('Z10', 'checkpoints compared instead of the recorded end states', [(EX,
     "    earlier = [x.end_state_digest for x in chain if x.end_state_digest is not None]",
     "    earlier = [str(rows.where(tx.conn, entities.Checkpoint, execution_id=x.id)[0]\n"
     "                   .entity.files_changed) for x in chain]")],
     [U + '::test_the_guard_never_reads_a_checkpoint',
      I + '::test_cx3_a_chain_that_returns_to_an_earlier_state_ends_charged']),
    ('Z11', 'A -> B -> A read as progress', [(PR,
     "    return end_state not in set(earlier)",
     "    return end_state != (earlier[0] if earlier else None)")],
     [U + '::test_progress_is_a_new_end_state_against_every_earlier_link',
      I + '::test_cx3_a_chain_that_returns_to_an_earlier_state_ends_charged']),
    ('Z12', 'an unmeasurable end state let through', [(PR,
     "    if end_state is None:\n        return False",
     "    if end_state is None:\n        return True")],
     [U + '::test_an_unmeasurable_end_state_is_no_progress',
      I + '::test_no_git_workdir_gets_one_pressure_continuation_per_attempt']),
    ('Z13', 'the guarded end left uncharged', [(EX,
     "              {'exit_reason': 'handoff', 'exit_code': exit_code, 'charged': refused is not None,",
     "              {'exit_reason': 'handoff', 'exit_code': exit_code, 'charged': False,")],
     [I + '::test_cx3_a_chain_that_returns_to_an_earlier_state_ends_charged',
      I + '::test_cx18_the_retry_is_bounded_and_the_task_fails_context_insufficient']),
    ('Z14', 'a continuation created after context_insufficient', [(EX,
     "    if refused is not None:\n        # ADR-0047 §5 and T-051 §7: no continuation",
     "    if False:\n        # ADR-0047 §5 and T-051 §7: no continuation")],
     [I + '::test_cx3_a_chain_that_returns_to_an_earlier_state_ends_charged']),
    ('Z15', 'context_insufficient made unreplannable', [(GD,
     "NOT_RETRYABLE = ('policy', 'credential', 'human')",
     "NOT_RETRYABLE = ('policy', 'credential', 'human', 'context_insufficient')")],
     [U + '::test_context_insufficient_stays_retryable_and_replannable']),
    # ── a continuation is authorised and routed again (CX-7 boundary) ──
    ('Z16', 'the continuation skips P9', [(HO,
     "            auth = authorization.check_dispatch(tx, actor=actor, policy=policy,\n"
     "                                                missions=missions, mission=m, plan=plan, task=t)",
     "            auth = {'outcome': 'covered', 'policy_decision_id': e.policy_decision_id}")],
     [E + '::test_E80_a_continuation_meets_the_policy_as_it_is_now']),
    ('Z17', 'the continuation skips the router and reuses the ended decision', [(HO,
     "        route = router.route(Ref('task', t.id), now, tx=tx, actor=actor, authorization=auth,\n"
     "                             mission=m, plan=plan, task=t)",
     "        route = tx.get(entities.RouteDecision, e.route_decision_id).entity")],
     [I + '::test_cx3_a_chain_that_returns_to_an_earlier_state_ends_charged']),
    # ── the window is the execution's own account's (C-22) ──
    ('Z18', 'the harness default offers read instead of the account\'s', [(MGR,
     "            models = adapter.capabilities(base.AccountRef(e.account_id or e.harness_id,\n"
     "                                                          home)).models",
     "            models = adapter.capabilities(None).models")],
     [I + '::test_the_window_is_the_offer_of_the_executions_own_account']),
    # ── capacity eliminates, never ranks (ADR-0047 §7) ──
    ('Z19', 'the model step prefers the largest window', [(RT,
     "        ok = sorted((m for m in offers.values() if fits(m)), key=lambda m: _rank(m.get('tier')))",
     "        ok = sorted((m for m in offers.values() if fits(m)),\n"
     "                    key=lambda m: -(m.get('context_window') or 0))")],
     [U + '::test_a_larger_window_is_never_preferred']),
    ('Z20', 'the ordering prefers the account with the largest window', [(RT,
     "    return (0 if affine else 1, 0 if pref else 1, c['priority'],",
     "    return (-max([m.get('context_window') or 0 for m in _offers(c)] or [0]),\n"
     "            0 if affine else 1, 0 if pref else 1, c['priority'],")],
     [U + '::test_a_larger_window_is_never_preferred']),
    # ── the measurement writes nothing (ADR-0046, MG-6) ──
    ('Z21', 'git may refresh the index while measuring', [(ND,
     "            r = proc.run(['git', '--no-optional-locks', *args], cwd=workdir, stdin=stdin)",
     "            r = proc.run(['git', *args], cwd=workdir, stdin=stdin)")],
     [U + '::test_the_end_state_digest_measures_head_diff_and_untracked_and_writes_nothing']),
    ('Z22', 'untracked files written into the object store while measuring', [(ND,
     "        hashes = git('hash-object', '--stdin-paths',",
     "        hashes = git('hash-object', '-w', '--stdin-paths',")],
     [U + '::test_the_end_state_digest_measures_head_diff_and_untracked_and_writes_nothing']),
    # ── slice A: requirement provenance (D11) ──
    ('Z23', "a task's P9 requirement recorded as Core's own rule", [(RS,
     "                          policy='policy')",
     "                          )")],
     [RI + '::test_I_H3_every_recorded_requirement_names_its_source']),
    # ── slice A: the served model's provenance (D4, ADR-0031 §6) ──
    ('Z24', 'a lower provenance report replaces a higher one', [(EX,
     "    if levels.index(level) < old or (levels.index(level) == old and model == e.served_model):",
     "    if levels.index(level) == old and model == e.served_model:")],
     [XU + '::test_a_provenance_level_is_never_lowered_and_names_a_revision_only_from_its_source']),
    ('Z25', 'a requested or routed model claims an exact revision', [(EX,
     "    if level in ('SERVED', 'BILLED'):",
     "    if True:")],
     [XU + '::test_a_provenance_level_is_never_lowered_and_names_a_revision_only_from_its_source']),
    ('Z26', 'BILLED claimed when the usage bills other models', [(MGR,
     "    if len(billed) == 1:",
     "    if billed:")],
     [XU + '::test_a_provenance_level_is_never_lowered_and_names_a_revision_only_from_its_source']),
    ('Z27', "the transcript's model is ignored", [(MGR,
     "                p['served'] = {'level': 'SERVED', 'model': ev['model']}",
     "                pass")],
     [E + '::test_E33b_the_served_model_is_recorded_at_the_level_its_source_supports']),
    # ── slice A: the producer record (D5) and ADR-0047 clause 5 (ii) ──
    ('Z28', 'the guard ignores the artifacts a continuation recorded', [(EX,
     "    if pressure.progressed(end_state, artifacts_of(tx.conn, e), earlier):",
     "    if pressure.progressed(end_state, (), earlier):")],
     [I + '::test_an_artifact_the_continuation_produced_is_progress_and_a_checkpoint_never_is']),
    ('Z29', 'a checkpoint is derived without its producer record', [(CP,
     "    record_artifact(tx, actor=actor, execution=e, sha=sha, media_type='text/markdown',\n"
     "                    size=len(data), kind='checkpoint', label=cp.id)",
     "    pass")],
     [I + '::test_an_artifact_the_continuation_produced_is_progress_and_a_checkpoint_never_is']),
    # ── slice D: metrics_daily, doctor, core.log rotation (p21-design-gate D2, D8) ──
    ('Z40', 'a day is computed before it has ended', [(MT,
     "    while d < today:",
     "    while d <= today:")],
     [D + '::test_a_finished_day_gets_its_figures_once']),
    ('Z41', 'a figure with nothing to measure written as 0', [(MT,
     "    return round(part / whole, 4) if whole else None",
     "    return round(part / whole, 4) if whole else 0")],
     [D + '::test_a_day_with_nothing_to_measure_says_none_not_zero']),
    ('Z42', 'a finished day rewritten', [(MT,
     "               'ON CONFLICT (day) DO NOTHING',",
     "               'ON CONFLICT (day) DO UPDATE SET metrics = excluded.metrics',")],
     [D + '::test_a_finished_day_gets_its_figures_once']),
    ('Z43', 'doctor opens the database with a connection that can checkpoint it', [(DR,
     "        conn = connection.inspect(path)",
     "        conn = connection.connect(path, readonly=True)")],
     [D + '::test_doctor_leaves_a_wal_core_crashed_out_of_to_core']),
    ('Z44', 'doctor creates the database it was asked to look at', [(DR,
     "    if not os.path.isfile(path):",
     "    if not os.path.isfile(path) and connection.connect(path).close():")],
     [D + '::test_doctor_without_a_database_creates_nothing']),
    ('Z45', 'every unfinished execution reported stuck', [(DR,
     "            cutoff = (now - dt.timedelta(seconds=STUCK_S)).isoformat(",
     "            cutoff = (now).isoformat(")],
     [D + '::test_doctor_reports_stuck_executions_and_lagging_consumers']),
    ('Z46', 'consumer lag never reported', [(DR,
     "                if head - last > LAG_WARN:",
     "                if False:")],
     [D + '::test_doctor_reports_stuck_executions_and_lagging_consumers']),
    ('Z47', 'core.log grows without rotation', [(RTM,
     "        self._log_handler = logging.handlers.RotatingFileHandler(\n"
     "            os.path.join(logs, 'core.log'), maxBytes=LOG_BYTES, backupCount=LOG_BACKUPS,\n"
     "            encoding='utf-8')",
     "        self._log_handler = logging.FileHandler(os.path.join(logs, 'core.log'),\n"
     "                                                encoding='utf-8')")],
     [D + '::test_core_log_rotates']),
    ('Z48', 'the worker scans the log after every commit once each day is filled', [(MT,
     "        if self._filled_through == today:\n            return {'changed': False}",
     "        if False:\n            return {'changed': False}")],
     [D + '::test_a_filled_worker_reads_nothing_until_the_date_changes']),
    ('Z49', 'a broken execution hook never reported', [(DR,
     "        finding(DOCTOR_HOOK, 'the execution hook %s: %s' % (manager.HOOK, e))",
     "        print('the execution hook %s: %s' % (manager.HOOK, e))")],
     [D + '::test_doctor_reports_a_broken_hook_and_a_newer_schema']),
    # ── slice F: Core search (p21-design-gate D7) ──
    ('Z50', 'search minds the case', [(QRY,
     "    n = needle.casefold()", "    n = needle")],
     [SRCH + 'test_F01_titles_holding_the_needle_case_ignored']),
    ('Z51', 'search answers whole rows, bodies included', [(QRY,
     "        return [{k: v[k] for k in keys} for v in got][:limit]",
     "        return list(got)[:limit]")],
     [SRCH + 'test_F01_titles_holding_the_needle_case_ignored']),
    ('Z52', 'search needs no scope', [(ROUTES,
     "    Route('GET', '/v1/search', search_titles, 'observe',",
     "    Route('GET', '/v1/search', search_titles, None,")],
     [SRCH + 'test_F03_a_client_without_observe_reads_nothing']),
    ('Z53', 'a blank needle answers everything', [(ROUTES,
     "    if not 1 <= len(needle) <= 200:", "    if len(needle) > 200:")],
     [SRCH + 'test_F02_a_blank_or_long_needle_is_400']),
    ('Z54', 'the command bar never asks Core', [(CMDBAR,
     "live && needle ? paths.searchTitles({ q: needle }) : null",
     "live && needle && !live ? paths.searchTitles({ q: needle }) : null")],
     [PAL_E2E]),
    ('Z55', "the command bar shows its own lists, not Core's answer", [(CMDBAR,
     "      projects: found?.projects ?? read",
     "      projects: read")],
     [PAL_E2E]),
    ('Z56', 'offline, the command bar still asks Core', [(CMDBAR,
     "live && needle ? paths.searchTitles({ q: needle }) : null",
     "needle ? paths.searchTitles({ q: needle }) : null")],
     [PAL_E2E]),
    # ── slice G: the tray's notifications (p21-design-gate D1) ──
    ('Z57', "a notice repeats the approval's own words", [(GUI,
     "        return 'A %s waits for your decision' % APPROVAL_WORDS.get(kind, 'request')",
     "        return 'A %s waits for your decision' % kind")],
     [SHL + 'test_G02_a_notice_names_the_kind_never_the_content']),
    ('Z58', 'what happened before the window hid is said', [(GUI,
     "                return self._own.get(endpoints.events(limit=1))[1], []",
     "                return 0, []")],
     [SHL + 'test_G01_the_tray_says_an_approval_request_and_an_estop_only_after_it_started']),
    ('Z59', 'each event is said again at every read', [(GUI,
     "        return (events[-1]['seq'] if events else after), said",
     "        return after, said")],
     [SHL + 'test_G01_the_tray_says_an_approval_request_and_an_estop_only_after_it_started']),
    # ── P21 slice B: own calls in live work, consumption, `status` in words ──
    ('Z60', 'an own call in flight is left out of live work', [(LV,
     "    for r in own_calls(conn, now):\n        rd = r.entity\n        if not own_call_live",
     "    for r in ():\n        rd = r.entity\n        if not own_call_live")],
     [PL + 'test_g6_live_work_is_the_live_executions_then_the_own_calls_without_an_outcome']),
    ('Z61', 'an own call that has ended is still live work', [(LV,
     "        if not own_call_live(r, now) or (project_id is not None",
     "        if (project_id is not None")],
     [PL + 'test_g6_live_work_is_the_live_executions_then_the_own_calls_without_an_outcome']),
    ('Z62', "an own call ignores the project filter", [(LV,
     "        if not own_call_live(r, now) or (project_id is not None and rd.project_id != project_id):",
     "        if not own_call_live(r, now):")],
     [PL + 'test_g6_live_work_is_the_live_executions_then_the_own_calls_without_an_outcome']),
    ('Z63', 'an own call is given a running state', [(LV,
     "            'task_id': None, 'state': None,",
     "            'task_id': None, 'state': 'RUNNING',")],
     [PL + 'test_g6_live_work_is_the_live_executions_then_the_own_calls_without_an_outcome']),
    ('Z64', 'the halo counts an own call as a running attempt (G8)', [(ORB,
     "live.filter((x) => x.kind !== 'own_call' && present(",
     "live.filter((x) => present(")],
     ['node:test/orbit.test.ts']),
    ('Z65', "an account lists every account's consumers", [(RS,
     "                           for w in work if w['account_id'] == a.id])",
     "                           for w in work])")],
     [PL + 'test_g8_an_own_call_in_flight_is_listed_and_counted_on_its_account']),
    ('Z66', "the effective policy read is the stored row, not the router's input", [(RS,
     "                policy=effective_policy(p.entity),",
     "                policy=view(p),")],
     [PL + 'test_g13_the_effective_policy_read_is_what_the_router_decided_from']),
    ('Z67', 'nothing reported is said as 0', [(TPR,
     "        if done and not busy:",
     "        if done or not n:")],
     [PL + 'test_g12_a_reading_that_is_missing_is_said_unknown_never_a_number']),
    ('Z68', 'a lower bound is said as the exact figure', [(TPR,
     "            return 'at least ' + say(n)",
     "            return say(n)")],
     ['tests/v1/tui/test_parity.py']),
    ('Z69', '`status` says the raw state enum (R13-06)', [(CV,
     "    return LABELS.get(machine, {}).get(state, state)",
     "    return state")],
     [PL + 'test_r13_06_status_says_each_state_in_the_words_the_clients_show']),
    # ── P21 slice B rework (T-125 review): the in-flight zero, the counts, the words ──
    ('Z130', 'an own call in flight is not counted as running on its account', [(RS,
     "            mine(rd.account_id)['running'] += 1",
     "            mine(rd.account_id)")],
     [PL + 'test_g8_an_own_call_in_flight_is_listed_and_counted_on_its_account']),
    ('Z131', 'an own call in flight is booked to no account', [(RS,
     "            mine(rd.account_id)['running'] += 1",
     "            mine(None)['running'] += 1")],
     [PL + 'test_g8_an_own_call_in_flight_is_listed_and_counted_on_its_account']),
    ('Z132', 'an own call that ended with no outcome leaves the ledger complete', [(RS,
     "    if live['lapsed']:",
     "    if False:")],
     [PL + 'test_g12_a_reading_that_is_missing_is_said_unknown_never_a_number']),
    ('Z133', 'work in flight is said as a complete zero on its account (R1)', [(RS,
     "    if led['running']:",
     "    if False:")],
     [PL + 'test_g12_work_in_flight_is_unknown_not_a_zero_and_accounts_lists_the_same']),
    ('Z134', 'an own call counts as running in the palette', [(PAL,
     "live.filter((x) => x.kind !== 'own_call' && x.mission_id === m.id).length",
     "live.filter((x) => x.mission_id === m.id).length")],
     ['node:test/palette.test.ts']),
    ('Z135', 'in-flight work is said complete in the SPA', [(PTS,
     "done && !busy ? say(n) :",
     "done ? say(n) :")],
     ['node:test/parity.test.ts']),
    ('Z136', 'in-flight work is said complete in the TUI', [(TPR,
     "        if done and not busy:",
     "        if done:")],
     ['tests/v1/tui/test_parity.py']),
    ('Z137', 'an own call counts as a running attempt in the header', [(PTS,
     "  const attempts = live.filter((x) => x.kind !== 'own_call').length;",
     "  const attempts = live.length;")],
     ['node:test/present.test.ts']),
    ('Z138', 'a window with no reading is dropped from the TUI usage line', [(TPR,
     "    if isinstance(observed, (int, float)) and not isinstance(observed, bool):",
     "    if False:")],
     ['tests/v1/tui/test_parity.py']),
    ('Z139', 'an own call is linked as an execution in status', [(CV,
     "                  if w['kind'] == 'execution']",
     "                  ]")],
     [PL + 'test_g6_the_status_verb_names_exactly_what_status_live_lists']),
    ('Z140', 'an account carries whole live items as consumers, not the summary', [(RS,
     "                consumers=[{k: w.get(k) for k in CONSUMER_FIELDS}\n"
     "                           for w in work if w['account_id'] == a.id])",
     "                consumers=[w for w in work if w['account_id'] == a.id])")],
     [PL + 'test_g8_an_own_call_in_flight_is_listed_and_counted_on_its_account']),
    ('Z141', 'status drops the count of the work it does not name', [(CV,
     "' (+%d more)' % more if more > 0 else ''",
     "''")],
     [PL + 'test_r13_06_the_status_says_how_many_more_run_past_the_ten_it_names']),
    ('Z142', 'the own-call scan reads every decision, not only own calls', [(RS,
     "        if (json.loads(rec['body']).get('subject') or {}).get('kind') == 'archeus_call':",
     "        if True:")],
     [PL + 'test_g6_live_work_is_the_live_executions_then_the_own_calls_without_an_outcome']),
    # ── P21 slice B review rework: the home is never in the accounts view (owner 2026-10-21) ──
    ('Z143', 'the accounts view shows the home_ref path', [(RS,
     "HOME_FIELDS = ('home_ref', 'home_key')",
     "HOME_FIELDS = ('home_key',)")],
     [PL + 'test_owner_2026_10_21_the_accounts_view_never_shows_an_account_home']),
    ('Z144', 'the accounts view shows the canonical home_key path', [(RS,
     "HOME_FIELDS = ('home_ref', 'home_key')",
     "HOME_FIELDS = ('home_ref',)")],
     [PL + 'test_owner_2026_10_21_the_accounts_view_never_shows_an_account_home']),
    # ── P21 slice B review round 3 (F1-F4) ──
    ('Z147', 'a live execution in its first state is left out of live work', [(LV,
     "% ','.join('?' * len(LIVE)), LIVE):",
     "% ','.join('?' * len(LIVE[1:])), LIVE[1:]):")],
     [PL + 'test_g6_live_work_is_the_live_executions_then_the_own_calls_without_an_outcome']),
    ('Z148', 'the live map lights an own call (G8)', [(ORB,
     "filter((x) => x.kind !== 'own_call').map((x) => x.id)",
     "filter(() => true).map((x) => x.id)")],
     ['node:test/orbit.test.ts']),
    ('Z150', 'the offline header counts own calls as running (R13-06)', [(PTS,
     "  return `${liveCountText(s.live)}${s.armed ? '' : ' · Emergency stop engaged'}`;",
     "  return `${liveCountText(s.live.map((x) => ({ ...x, kind: 'execution' })))}${s.armed ? '' : ' · Emergency stop engaged'}`;")],
     ['node:test/present.test.ts']),
    # ── P21 slice B round 4 (owner, 2026-10-21: field projection only) ──
    ('Z151', 'an own call in flight names its account_ref (a home for a registered account)',
     [(LV,
     "            'account_id': rd.account_id, 'model': rd.model,",
     "            'account_id': rd.account_id, 'account_ref': rd.account_ref, 'model': rd.model,")],
     [PL + 'test_owner_2026_10_21_live_work_names_no_home_field',
      'tests/v1/integration/test_routing_http.py::test_H09_the_status_read_with_a_live_own_call_names_no_home_field']),
    ('Z153', 'a route decision read keeps the snapshot ref of an account', [(QRY,
     "_drop(a, 'home_ref', 'home_key', 'ref')",
     "_drop(a, 'home_ref', 'home_key')")],
     [PL + 'test_owner_2026_10_21_route_decision_reads_name_no_home_field',
      'tests/v1/integration/test_routing_http.py::test_H09_the_three_projected_reads_name_no_home_field']),
    ('Z154', 'a route decision read keeps account_ref on its candidates', [(QRY,
     "    cands = [_drop(c, 'account_ref') for c in decision.get('candidates') or ()]",
     "    cands = list(decision.get('candidates') or ())")],
     [PL + 'test_owner_2026_10_21_the_default_account_fields_are_left_out']),
    ('Z155', 'a route decision read keeps account_ref on its usage rows', [(QRY,
     "    usage = [_drop(view(r), 'account_ref') for r in rows.where(",
     "    usage = [view(r) for r in rows.where(")],
     [PL + 'test_owner_2026_10_21_route_decision_reads_name_no_home_field']),
    ('Z156', 'the accounts view shows the home fields', [(RS,
     "HOME_FIELDS = ('home_ref', 'home_key')",
     "HOME_FIELDS = ()")],
     [PL + 'test_owner_2026_10_21_the_accounts_view_never_shows_an_account_home',
      'tests/v1/integration/test_routing_http.py::test_H09_the_three_projected_reads_name_no_home_field']),
    ('Z157', 'a route decision read keeps account_ref on the decision', [(QRY,
     "    return _drop(dict(decision, input_snapshot=snap, candidates=cands), 'account_ref')",
     "    return dict(decision, input_snapshot=snap, candidates=cands)")],
     [PL + 'test_owner_2026_10_21_route_decision_reads_name_no_home_field',
      'tests/v1/integration/test_routing_http.py::test_H09_the_three_projected_reads_name_no_home_field']),
    # ── P21 slice B round 6 (T-125 review N-1, N-2): the trace and the status read ──
    ('Z202', "the mission trace's route decisions are read raw (N-1)", [(TR,
     "'route_decisions': route_decisions(conn, mission_id),",
     "'route_decisions': [dict(r.entity.to_dict(), version=r.version) for r in rows.where(conn, entities.RouteDecision) if r.entity.source is not None and r.entity.source.id == mission_id],")],
     [PL + 'test_owner_2026_10_21_the_mission_trace_reads_no_home_field']),
    ('Z203', 'the status read names account_ref on each live item (N-2)', [(ROUTES,
     "live=live.live_work(conn, project), armed=not LocalNode.disarmed(),",
     "live=[dict(x, account_ref=x['account_id']) for x in live.live_work(conn, project)], armed=not LocalNode.disarmed(),")],
     ['tests/v1/integration/test_routing_http.py::test_H09_the_status_read_with_a_live_own_call_names_no_home_field']),
    # ── P21 slice C: the trace (D3, D14), `why` (R13-05), the digest (R13-03) ──
    ('Z30', 'a result is paired with whichever call came first', [(TR,
     "            call = calls.get(e.get('tool_use_id'))",
     "            call = next(iter(calls.values()), None)")],
     [TT + '::test_a_call_is_paired_with_its_result_inside_its_sidechain_lane']),
    ('Z31', 'every step is put in the main lane', [(TR,
     "        out.setdefault(e.get('lane') or MAIN, []).append(step)",
     "        out.setdefault(MAIN, []).append(step)")],
     [TT + '::test_a_call_is_paired_with_its_result_inside_its_sidechain_lane']),
    ('Z32', "a call's input is carried into the trace", [(TR,
     "            step['name'] = e.get('name')",
     "            step['name'], step['input'] = e.get('name'), e.get('input')")],
     [TT + '::test_a_call_is_paired_with_its_result_inside_its_sidechain_lane']),
    ('Z33', "the Claude stream's sidechain is dropped", [(CC,
     "    lane = raw.get('parent_tool_use_id')",
     "    lane = None")],
     [TT + '::test_the_claude_stream_carries_the_call_ids_and_the_sidechain']),
    ('Z34', 'the trace lists events newest first', [(TR,
     "    return {'mission_id': mission_id, 'events': t['events'][::-1],",
     "    return {'mission_id': mission_id, 'events': t['events'],")],
     [TT + '::test_the_trace_reads_the_missions_events_decisions_and_lanes']),
    ('Z35', 'a bare why in a thread is left to the brain', [(GR,
     "            return Control('why', {'kind': 'mission', 'id': mission}, '') if mission else None",
     "            return None")],
     [TT + '::test_a_bare_why_in_a_thread_says_why_its_mission_exists']),
    ('Z36', 'an explicit why <mission> answers why the mission exists', [(CV,
     "            text, rd = _why(tx, target, bare=not arg)",
     "            text, rd = _why(tx, target, bare=True)")],
     ['tests/v1/integration/test_intent.py::test_i18_control_verbs_never_call_the_model']),
    ('Z37', 'a declined reading cites an ADR to the user', [(CV,
     "        why = {'gated': 'no harness is permitted to make the call yet (provider terms: '",
     "        why = {'gated': 'no harness is permitted to make the call yet (provider terms, ADR-0021: '")],
     [TT + '::test_a_declined_reading_names_no_adr']),
    ('Z38', 'each message is a digest row of its own again', [(DG,
     "        if kind == 'message':\n            kind, eid = _thread_of(conn, eid)",
     "        if False:\n            kind, eid = _thread_of(conn, eid)")],
     [TT + '::test_the_digest_folds_messages_into_their_mission_or_one_new_messages_row']),
    ('Z39', 'the primary conversation folds into the mission rows', [(DG,
     "    return 'conversation', c.entity.id",
     "    return 'mission', c.entity.id")],
     [TT + '::test_the_digest_folds_messages_into_their_mission_or_one_new_messages_row']),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
