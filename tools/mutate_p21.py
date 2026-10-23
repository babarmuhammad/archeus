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
AT = 'archeus/core/application/attention.py'
HL = 'tests/v1/integration/test_p21_health.py::'
JH = 'tests/v1/judge/http.py'
ENV = 'tools/v1_env.py'
DL = 'tests/v1/integration/test_dev_launcher.py::'
SCR = 'archeus/cli/tui/screens.py'
TUIA = 'tests/v1/tui/test_acceptance.py::'

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
    # ── slice D Health: Attention items (D12, K7) and the metrics read (D2) ──
    ('Z80', 'a LIMITED account waits on nobody', [(AT,
     "('LIMITED', 'limited'), ",
     "")],
     [HL + 'test_H01_accounts_a_provider_or_the_breaker_stopped_wait_on_the_user']),
    ('Z81', "an account the breaker OPENed waits on nobody", [(AT,
     "('DEGRADED', 'degraded'),\n           ('OPEN', 'open'))",
     "('DEGRADED', 'degraded'))")],
     [HL + 'test_H01_accounts_a_provider_or_the_breaker_stopped_wait_on_the_user']),
    ('Z82', 'a limited account does not say when it resets', [(AT,
     "**({'until': r.entity.limited_until} if health == 'LIMITED'",
     "**({} if health == 'LIMITED'")],
     [HL + 'test_H01_accounts_a_provider_or_the_breaker_stopped_wait_on_the_user']),
    ('Z83', "the task's first route decides, not its last", [(AT,
     "'ORDER BY created_at DESC, rowid DESC LIMIT 1'",
     "'ORDER BY created_at, rowid LIMIT 1'")],
     [HL + 'test_H02_a_mission_no_resource_can_run_waits_with_the_routes_reason',
      HL + 'test_H03_only_a_route_that_found_no_resource_makes_the_item']),
    ('Z84', 'a route that asked is taken for no resource', [(AT,
     "if not route or route.get('result') != 'blocked':",
     "if not route or route.get('result') not in ('blocked', 'ask'):")],
     [HL + 'test_H03_only_a_route_that_found_no_resource_makes_the_item']),
    ('Z85', 'a mission held from verification is said to want a resource', [(AT,
     "elif m.state == 'BLOCKED' and m.held_from == 'EXECUTING':",
     "elif m.state == 'BLOCKED':")],
     [HL + 'test_H03_only_a_route_that_found_no_resource_makes_the_item']),
    ('Z86', "the route's own reason is dropped", [(AT,
     "route.get('explanation') or None, m.id, m.project_id,",
     "None, m.id, m.project_id,")],
     [HL + 'test_H02_a_mission_no_resource_can_run_waits_with_the_routes_reason']),
    ('Z87', 'the Health days come oldest first', [(MT,
     "'ORDER BY day DESC LIMIT ?'",
     "'ORDER BY day LIMIT ?'")],
     [HL + 'test_H04_metrics_newest_first_bounded_and_unknown_kept_unknown']),
    ('Z88', 'the metrics read takes any number of days', [(ROUTES,
     "    if not 1 <= days <= metrics.MAX_DAYS:",
     "    if False:")],
     [HL + 'test_H04_metrics_newest_first_bounded_and_unknown_kept_unknown']),
    ('Z89', 'the TUI names only the kind', [(SCR,
     "    title = (ATTENTION_REASON.get('%s.%s' % (item['kind'], item.get('reason_code')))",
     "    title = (None")],
     [TUIA + 'test_attention_names_a_limited_account_and_a_mission_no_resource_can_run']),
    ('Z120', 'a mission is a resource wait when one of its blocked tasks was', [(AT,
     "        if not route or route.get('result') != 'blocked':\n            return None\n        found = found or route",
     "        if route and route.get('result') == 'blocked':\n            return route")],
     [HL + 'test_H07_every_blocked_task_must_be_blocked_on_a_resource']),
    ('Z121', 'a metrics worker never started reads as idle', [(RTM,
     "                else {'state': 'stopped', 'pending': 0}}",
     "                else {'state': 'idle', 'pending': 0}}")],
     [HL + 'test_H08_a_metrics_worker_never_started_is_stopped_not_idle']),
    ('Z122', 'a no-resource item drops its unblock_at', [(AT,
     "route.get('explanation') or None, m.id, m.project_id,\n                                   unblock_at=route.get('unblock_at')))",
     "route.get('explanation') or None, m.id, m.project_id))")],
     [HL + 'test_H02_a_mission_no_resource_can_run_waits_with_the_routes_reason']),
    ('Z160', 'an application module sets a state through a dict key outside a read', [(AT,
     "    found = None\n",
     "    found = None\n    _ = entities.Task(**{'state': 'BLOCKED'})\n")],
     ['tests/v1/unit/test_guards.py::test_no_state_is_set_outside_the_p2_primitive']),
    ('Z161', 'a never-started planner reads idle', [(RTM,
     "'plan': self.plan.status() if self.plan is not None\n                else {'state': 'stopped', 'pending': 0},",
     "'plan': self.plan.status() if self.plan is not None\n                else {'state': 'idle', 'pending': 0},")],
     [HL + 'test_H10_a_never_started_worker_reads_stopped_not_idle[plan]']),
    ('Z162', 'a never-started policy worker reads idle', [(RTM,
     "'policy': self.policy.status() if self.policy is not None\n                else {'state': 'stopped', 'pending': 0},",
     "'policy': self.policy.status() if self.policy is not None\n                else {'state': 'idle', 'pending': 0},")],
     [HL + 'test_H10_a_never_started_worker_reads_stopped_not_idle[policy]']),
    ('Z163', 'a never-started verify worker reads idle', [(RTM,
     "'verify': self.verify.status() if self.verify is not None\n                else {'state': 'stopped', 'pending': 0},",
     "'verify': self.verify.status() if self.verify is not None\n                else {'state': 'idle', 'pending': 0},")],
     [HL + 'test_H10_a_never_started_worker_reads_stopped_not_idle[verify]']),
    ('Z164', 'a never-started automation worker reads idle', [(RTM,
     "'automation': self.automation.status() if self.automation is not None\n                else {'state': 'stopped', 'pending': 0},",
     "'automation': self.automation.status() if self.automation is not None\n                else {'state': 'idle', 'pending': 0},")],
     [HL + 'test_H10_a_never_started_worker_reads_stopped_not_idle[automation]']),
    ('Z165', 'a past limited reset reads resets, not reset due (TUI)', [('archeus/cli/tui/present.py',
     "    if then is not None and then <= now_ms:",
     "    if False:")],
     [TUIA + 'test_attention_names_a_limited_account_and_a_mission_no_resource_can_run']),
    # ── T-127 fix round: the settle check, the launcher's ready states, the guard's exemption ──
    ('Z166', "the judge settles on a crashed worker", [(JH,
     "if ((state != 'idle' and not unwired) or health[worker]['pending']",
     "if ((state not in ('idle', 'failed') and not unwired) or health[worker]['pending']")],
     [HL + 'test_H11_settle_takes_a_never_started_worker_and_never_a_crashed_one']),
    ('Z167', "the judge never settles on an unwired plan or verify worker", [(JH,
     "unwired = state == 'stopped' and worker in ('plan', 'verify')",
     "unwired = False")],
     [HL + 'test_H11_settle_takes_a_never_started_worker_and_never_a_crashed_one']),
    ('Z168', "a started metrics worker reads stopped", [(RTM,
     "'metrics': self.metrics.status() if self.metrics is not None",
     "'metrics': dict(self.metrics.status(), state='stopped') if self.metrics is not None")],
     [HL + 'test_H05_health_names_the_metrics_worker']),
    ('Z169', "the launcher does not accept a stopped unwired worker", [(ENV,
     "if s not in READY_STATES and not (s == 'stopped' and k in UNWIRED))",
     "if s not in READY_STATES)")],
     [DL + 'test_ready_means_every_component_running_idle_or_stopped']),
    ('Z171', "an engine whose writer closed reads stopped, not failed", [(RTM,
     "        except errors.WriterClosed:\n            self.state = 'stopped'\n            if not self._stop.is_set():\n                self._failed()\n        except Exception:\n            if self._stop.is_set():\n                self.state = 'stopped'\n            else:\n                self._failed()\n\n    def _failed(self):\n        self.state = 'failed'\n        log.exception('the engine",
     "        except errors.WriterClosed:\n            if not self._stop.is_set():\n                self._failed()\n            self.state = 'stopped'\n        except Exception:\n            if self._stop.is_set():\n                self.state = 'stopped'\n            else:\n                self._failed()\n\n    def _failed(self):\n        self.state = 'failed'\n        log.exception('the engine")],
     [HL + 'test_H12_an_engine_whose_writer_closed_reads_failed_not_stopped']),
    ('Z170', "a rows.where read on a line exempts a state write on that line", [(AT,
     "    found = None\n",
     "    found = None\n    _ = rows.where(None, entities.Task), entities.Task(**{'state': 'BLOCKED'})\n")],
     ['tests/v1/unit/test_guards.py::test_no_state_is_set_outside_the_p2_primitive']),
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
