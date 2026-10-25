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
CH = 'clients/app/src/state/chips.ts'
ACT = 'tests/v1/integration/test_p21_activity.py::'
CHT = 'node:test/chips.test.ts'
CN = 'archeus/core/execution/canonical.py'

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
    # ── P21 slice E: the activity chip's record (D6) and the chip (A-17) ──
    ('Z90', "a foreign request becomes the execution's current action", [(EX,
     "        return _hook_answer(tx, actor, e, seq, 'halt', 'the request is not this execution\\'s')",
     "        return _hook_answer(tx, actor, e, seq, 'halt', 'the request is not this execution\\'s',\n"
     "                            _current(first))")],
     [ACT + 'test_E01_every_answer_is_unchanged_and_each_authentic_request_becomes_the_current_action']),
    ('Z91', 'the record keeps the argv', [(EX,
     "    return {'action_class': a.action_class, 'label': _label(a)}",
     "    return {'action_class': a.action_class, 'label': _label(a),\n"
     "            'argv': list(a.argv or ())}")],
     [ACT + 'test_E03_the_record_never_holds_raw_input']),
    ('Z92', 'a URL is named by its target, not its host', [(EX,
     "    if a.chip_host:\n        return a.chip_host",
     "    if a.chip_host:\n        return a.target")],
     [ACT + 'test_E03_the_record_never_holds_raw_input']),
    ('Z93', 'a program outside the list names its first argument', [(EX,
     "    if name not in _TOOLS:\n        return 'a program'",
     "    if name not in _TOOLS:\n        return a.argv[-1]")],
     [ACT + 'test_E08_no_hostile_input_reaches_a_label']),
    ('Z94', 'every recorded call says Core allowed it', [(EX,
     "        fields['current_action'] = dict(action, decision=decision, seq=seq)",
     "        fields['current_action'] = dict(action, decision='allow', seq=seq)")],
     [ACT + 'test_E01_every_answer_is_unchanged_and_each_authentic_request_becomes_the_current_action']),
    ('Z95', 'a denied call is never the current action', [(EX,
     "'; '.join(reasons), _current(denier))",
     "'; '.join(reasons))")],
     [ACT + 'test_E01_every_answer_is_unchanged_and_each_authentic_request_becomes_the_current_action']),
    ('Z96', 'a refused call leaves as soon as an allowed one', [(CH,
     "    const ttl = a.decision === 'allow' ? CHIP_TTL_MS : CHIP_TTL_ERROR_MS;",
     "    const ttl = CHIP_TTL_MS;")],
     [CHT]),
    ('Z97', 'the same action read again is chipped again', [(CH,
     "    if (!e || !a || a.seq <= (this.chipped.get(x) ?? -Infinity)) return;",
     "    if (!e || !a) return;")],
     [CHT]),
    ('Z98', 'a row takes any number of chips', [(CH,
     "    if (row.length < CHIPS_PER_ROW && !w.length) {",
     "    if (row.length < Infinity && !w.length) {")],
     [CHT]),
    ('Z99', 'any execution frame chips a row', [(CH,
     "f.id !== undefined && f.event === 'execution.hook' && s?.kind",
     "f.id !== undefined && f.event.startsWith('execution.') && s?.kind")],
     [CHT]),
    # ── P21 slice E, rework: the deciding action, NAME=value, the live check, the queue ──
    ('Z113', 'a denied call is labelled with the first action, not the one that denied it', [(EX,
     "'; '.join(reasons), _current(denier))",
     "'; '.join(reasons), _current(first))")],
     [ACT + 'test_E06_the_chip_names_the_action_that_decided_the_answer']),
    ('Z114', 'a request for a stopped execution records its first action', [(EX,
     "        return _hook_answer(tx, actor, e, seq, 'halt', 'the execution is %s' % e.state)",
     "        return _hook_answer(tx, actor, e, seq, 'halt', 'the execution is %s' % e.state,\n"
     "                            _current(first))")],
     [ACT + 'test_E05_a_request_for_an_execution_that_is_not_live_records_nothing']),
    ('Z115', 'a path outside the workspace is named as a file in it', [(EX,
     "re.match(r'(/|[A-Za-z]:)', a.target or '')",
     "False")],
     [ACT + 'test_E03_the_record_never_holds_raw_input']),
    ('Z116', 'a fetch with no clear host names its target', [(EX,
     "            return 'search' if a.target == 'search' else ''",
     "            return a.target")],
     [ACT + 'test_E08_no_hostile_input_reaches_a_label']),
    ('Z117', 'the queue shows the newest waiting chip first', [(CH,
     "    w.push(chip);",
     "    w.unshift(chip);")],
     [CHT]),
    ('Z118', 'the queue is unbounded', [(CH,
     "    if (w.length >= QUEUE_MAX) w.shift();",
     "    if (false) w.shift();")],
     [CHT]),
    ('Z119', 'a queued chip shows though its execution has ended', [(CH,
     "      if (!e || !LIVE.includes(e.state ?? '')) return;",
     "      if (!e) return;")],
     [CHT]),
    ('Z120', 'a read Core never answers stalls every chip after it', [(CH,
     "      t = setTimeout(() => r(null), this.host.readMs ?? READ_MS);",
     "      t = setTimeout(() => (false && r(null)), this.host.readMs ?? READ_MS);")],
     [CHT]),
    ('Z121', 'an allowed chip is announced through the polite region', [(CH,
     "    if (chip.announce) this.host.announce?.(chip.text);",
     "    if (chip) this.host.announce?.(chip.text);")],
     [CHT]),
    ('Z122', 'a chip leaving does not bring the queue up', [(CH,
     "    if (this.waiting.has(mission)) {",
     "    if (false) {")],
     [CHT]),
    ('Z156', 'the queue is promoted one read at a time', [(CH,
     "    const got = await Promise.all(w.map((c) => this.read(c.execution)));",
     "    const got: Array<{ mission_id: string; state?: string } | null> = []; for (const c of w) got.push(await this.read(c.execution));")],
     [CHT]),
    ('Z157', 'a frame takes the room ahead of a queued chip', [(CH,
     "    if (row.length < CHIPS_PER_ROW && !w.length) {",
     "    if (row.length < CHIPS_PER_ROW) {")],
     [CHT]),
    ('Z158', 'a late hook from a run that has ended chips its action', [(CH,
     "    if (!LIVE.includes(e.state ?? '')) return;",
     "    if (false) return;")],
     [CHT]),
    ('Z159', 'a refused or held chip is not announced', [(CH,
     "    if (chip.announce) this.host.announce?.(chip.text);",
     "    void chip.announce;")],
     [CHT]),
    ('Z183', 'the chip names the policy host (argument text)', [(EX,
     "    if a.chip_host:\n        return a.chip_host",
     "    if a.host:\n        return a.host")],
     [ACT + 'test_E03_the_record_never_holds_raw_input']),
    ('Z184', 'a verb outside the list is not named', [(EX,
     "    return name + ' ' + verb if verb in _VERBS.get(name, ()) else name",
     "    return name")],
     [ACT + 'test_E03_the_record_never_holds_raw_input']),
    ('Z185', 'a path outside the workspace is not told apart', [(EX,
     "re.match(r'(/|[A-Za-z]:)', a.target or '')",
     "False")],
     [ACT + 'test_E03_the_record_never_holds_raw_input']),
    ('Z186', 'a path inside the workspace is named', [(EX,
     "                else 'a file in the workspace'",
     "                else a.target")],
     [ACT + 'test_E03_the_record_never_holds_raw_input']),
    ('Z187', 'a chip is announced only when it is shown', [(CH,
     "    if (chip.announce) this.host.announce?.(chip.text);",
     "    void chip.announce;"),
     (CH,
     "    this.rows.set(mission, [...(this.rows.get(mission) ?? NONE), { ...c, still: !fade }]);",
     "    this.rows.set(mission, [...(this.rows.get(mission) ?? NONE), { ...c, still: !fade }]);\n"
     "    if (c.announce) this.host.announce?.(c.text);")],
     [CHT]),
]


CA = 'archeus/core/execution/command_allowlist.py'
CU = 'tests/v1/unit/test_command_allowlist.py::'
PU = 'tests/v1/unit/test_p21_proof_tools.py::'
AH = 'tests/v1/integration/test_p21_allowlist_hook.py::'


def _guard_mutant(id, description, before, after, test):
    return (id, description, [(CA, before, after)], [CU + test])


def _row_mutant(id, program, prefix):
    before = "    Row('A16', 'node', (), (('--version',),), 'none', 'exec'),"
    extra = f"    Row('B01', {program!r}, {prefix!r}, ((),), 'none', 'exec'),\n"
    return _guard_mutant(id, 'missing-row denial admits ' + program + ' ' + ' '.join(prefix),
                         before, extra + before, 'test_new_guard_mutation_witnesses')


REDEFINED = [
    _guard_mutant('Z112', 'assignment prefix silently removed',
                  '    if not tokens or tokens[0].quoted:',
                  "    if tokens and '=' in tokens[0].text:\n        tokens = tokens[1:]\n    if not tokens or tokens[0].quoted:",
                  'test_grammar_and_exact_options'),
    ('Z196', 'generated gate table drifts from row data', [(CA,
     "Row('A01', 'pwd', (), ((),), 'none')", "Row('A01', 'cwd', (), ((),), 'none')")],
     [PU + 'test_gate_allowlist_block_matches_data']),
    _row_mutant('Z219', 'git', ('-C', '.', 'reset', '--hard')),
    _row_mutant('Z225', 'python3.11', ('-c', 'x')),
    _row_mutant('Z226', 'python.bat', ('-c', 'x')),
    _row_mutant('Z288', 'rm.cmd', ('-R', 'x')),
]

NEW_MUTATIONS = [
    _guard_mutant('Z295', 'control character discarded before scan',
                  '    for char in command:', "    for char in command.replace('\\x01', ''):",
                  'test_new_guard_mutation_witnesses'),
    _guard_mutant('Z296', 'newline discarded before scan',
                  '    for char in command:', "    for char in command.replace('\\n', ''):",
                  'test_new_guard_mutation_witnesses'),
    _guard_mutant('Z297', 'substitution marker discarded before scan',
                  '    for char in command:', "    for char in command.replace('$', ''):",
                  'test_unquoted_metacharacter_property'),
    _guard_mutant('Z298', 'braces discarded before scan',
                  '    for char in command:', "    for char in command.replace('{', '').replace('}', ''):",
                  'test_unquoted_metacharacter_property'),
    _guard_mutant('Z299', 'glob marker discarded before scan',
                  '    for char in command:', "    for char in command.replace('*', ''):",
                  'test_unquoted_metacharacter_property'),
    _guard_mutant('Z300', 'operator discarded before scan',
                  '    for char in command:', "    for char in command.replace(';', ''):",
                  'test_unquoted_metacharacter_property'),
    _guard_mutant('Z301', 'concatenated quotes collapsed',
                  '    tokens = _scan(command)', '    tokens = _scan(command.replace(\'""\', \'\'))',
                  'test_new_guard_mutation_witnesses'),
    _guard_mutant('Z302', 'env wrapper silently removed',
                  '    tokens = _scan(command)', "    tokens = _scan(command.removeprefix('env '))",
                  'test_new_guard_mutation_witnesses'),
    _guard_mutant('Z303', 'executable suffix normalized',
                  '        if tokens[0].text != row.program:',
                  "        if tokens[0].text.removesuffix('.exe') != row.program:",
                  'test_per_row_near_misses'),
    _guard_mutant('Z304', 'executable path normalized',
                  '        if tokens[0].text != row.program:',
                  "        if tokens[0].text.removeprefix('/bin/') != row.program:",
                  'test_per_row_near_misses'),
    _guard_mutant('Z305', 'executable case normalized',
                  '        if tokens[0].text != row.program:',
                  '        if tokens[0].text.lower() != row.program:',
                  'test_grammar_and_exact_options'),
    _row_mutant('Z306', 'mytool', ()),
    _guard_mutant('Z307', 'option abbreviation accepted',
                  '    return not token.quoted and token.text == word',
                  '    return not token.quoted and word.startswith(token.text)',
                  'test_grammar_and_exact_options'),
    _guard_mutant('Z308', 'short option cluster expanded',
                  '    tokens = _scan(command)', "    tokens = _scan(command.replace('-la', '-a -l'))",
                  'test_grammar_and_exact_options'),
    _guard_mutant('Z309', 'old-style option bundle expanded',
                  '    tokens = _scan(command)', "    tokens = _scan(command.replace('ls la ', 'ls -a -l '))",
                  'test_new_guard_mutation_witnesses'),
    _guard_mutant('Z310', 'extra operand ignored',
                  "        return () if not tokens else Held(Reason.OPERAND)", '        return ()',
                  'test_new_guard_mutation_witnesses'),
    _guard_mutant('Z311', 'missing file operand admitted',
                  "    if mode == 'F+' and not tokens:", '    if False:',
                  'test_new_guard_mutation_witnesses'),
    _guard_mutant('Z312', 'missing numeric option value filled in',
                  '    tokens = _scan(command)', "    tokens = _scan(command.replace('head -n file.txt', 'head -n 20 file.txt'))",
                  'test_new_guard_mutation_witnesses'),
    _guard_mutant('Z313', 'duplicate option discarded',
                  '    tokens = _scan(command)', "    tokens = _scan(command.replace('-a -a', '-a'))",
                  'test_grammar_and_exact_options'),
    _guard_mutant('Z314', 'mandatory literal separator inserted',
                  '    tokens = _scan(command)',
                  "    tokens = _scan(command.replace('git --no-pager ls-files file.txt', 'git --no-pager ls-files -- file.txt'))",
                  'test_grammar_and_exact_options'),
    _guard_mutant('Z315', 'search pattern reported as path',
                  '        tokens = tokens[2:]', '        tokens = tokens[1:]',
                  'test_pattern_is_never_path_with_matching_evidence'),
    _guard_mutant('Z316', 'containment ignored',
                  'if (evidence is None or not evidence.contained',
                  'if (evidence is None', 'test_unknown_or_unsafe_path_evidence'),
    _guard_mutant('Z317', 'POSIX profile ignored',
                  'context is None or not context.posix_shell or row.program not in context.programs',
                  'context is None or row.program not in context.programs',
                  'test_context_is_required_and_bound_to_program'),
    _guard_mutant('Z318', 'pytest mislabeled read',
                  "Row('A14', 'pytest', (), ((), ('-q',)), 'P*', 'exec')",
                  "Row('A14', 'pytest', (), ((), ('-q',)), 'P*', 'read')", 'test_each_row'),
    ('Z319', 'HELD automatic allow cap omitted', [(EX,
     "    if request.get('tool') == 'Bash' and not (", '    if False and not (')],
     [AH + 'test_each_near_miss_holds_with_allow_all_classes_policy']),
    ('Z320', 'raw held command serialized as label', [(EX,
     "{'action_class': 'exec', 'label': 'command'})",
     "{'action_class': 'exec', 'label': str(request.get('input'))})")],
     [AH + 'test_each_near_miss_holds_with_allow_all_classes_policy']),
    ('Z321', 'gate table action class drifts', [(CA,
     "Row('A16', 'node', (), (('--version',),), 'none', 'exec')",
     "Row('A16', 'node', (), (('--version',),), 'none', 'read')")],
     [PU + 'test_gate_allowlist_block_matches_data']),
]

NOT_DONE_REDEFINE = ('Z150', 'Z151', 'Z152', 'Z153', 'Z154', 'Z155', 'Z170', 'Z171', 'Z172', 'Z173', 'Z174', 'Z175', 'Z176', 'Z178', 'Z179', 'Z180', 'Z181', 'Z182', 'Z188', 'Z189', 'Z190', 'Z191', 'Z192', 'Z197', 'Z198', 'Z199', 'Z200', 'Z201', 'Z202', 'Z203', 'Z204', 'Z205', 'Z207', 'Z208', 'Z209', 'Z210', 'Z211', 'Z212', 'Z213', 'Z215', 'Z216', 'Z217', 'Z218', 'Z220', 'Z221', 'Z223', 'Z224', 'Z227', 'Z228', 'Z229', 'Z230', 'Z231', 'Z232', 'Z233', 'Z234', 'Z235', 'Z236', 'Z237', 'Z238', 'Z239', 'Z240', 'Z241', 'Z242', 'Z243', 'Z244', 'Z245', 'Z246', 'Z247', 'Z248', 'Z249', 'Z250', 'Z251', 'Z252', 'Z253', 'Z254', 'Z255', 'Z256', 'Z257', 'Z258', 'Z259', 'Z260', 'Z261', 'Z262', 'Z263', 'Z264', 'Z265', 'Z266', 'Z267', 'Z269', 'Z270', 'Z271', 'Z272', 'Z273', 'Z274', 'Z275', 'Z276', 'Z277', 'Z278', 'Z279', 'Z280', 'Z281', 'Z282', 'Z283', 'Z284', 'Z285', 'Z286', 'Z287', 'Z289', 'Z290', 'Z291', 'Z293', 'Z294',)
MUTATIONS += REDEFINED + NEW_MUTATIONS

if __name__ == '__main__':
    if not sys.argv[1:] or set(sys.argv[1:]) & set(NOT_DONE_REDEFINE):
        raise SystemExit('Incomplete allow-list ledger; NOT DONE: ' + ', '.join(NOT_DONE_REDEFINE))
    unknown = set(sys.argv[1:]) - {entry[0] for entry in MUTATIONS}
    if unknown:
        raise SystemExit('Unknown or retired mutant IDs: ' + ', '.join(sorted(unknown)))
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
