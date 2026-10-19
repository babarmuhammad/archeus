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
QRY = 'archeus/core/application/queries.py'
ROUTES = 'archeus/api/routes.py'
CMDBAR = 'clients/app/src/surfaces/CommandBar.tsx'
GUI = 'archeus/cli/gui.py'
SRCH = 'tests/v1/integration/test_p21_search.py::'
PAL_E2E = 'tests/v1/e2e/test_spa_palette.py::test_the_palette_moves_by_arrows_and_acts_by_cores_verbs'
SHL = 'tests/v1/integration/test_gui_shell.py::'

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
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
