"""The P11 mutation suite (p11-design-gate §24.3): break each invariant the
execution orchestrator keeps, run the tests that guard it, and require them to
fail.

    py tools/mutate_p11.py            every mutation
    py tools/mutate_p11.py X05 X12    only these

Each mutation replaces exact snippets (each must occur once in its file; a
mutation of a guard that is checked twice breaks both, so what is measured is
the invariant and not one copy of it), runs its tests, and restores the files
whatever happens. A mutation the tests do not catch ("survived") fails the run.
It edits sources: run it with nothing else running against the tree.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = 'archeus/core/application/executions.py'
MGR = 'archeus/core/execution/manager.py'
CAN = 'archeus/core/execution/canonical.py'
NODE = 'archeus/node/local.py'
HOOK = 'archeus/harnesses/hook.py'
I = 'tests/v1/integration/test_execution.py'
S = 'tests/v1/integration/test_execution_security.py'
U = 'tests/v1/unit/test_execution_units.py'
TIMEOUT_S = 900

MUTATIONS = [
    # ── authorisation and the binding (§7, §10.4) ──
    ('X01', 'P9 authorisation skipped at the hook', [(EX,
     "    for a in actions:\n        got = authorization.evaluate_action(",
     "    for a in ():\n        got = authorization.evaluate_action(")],
     [I + '::test_E40_an_allowed_tool_call_runs_and_its_decision_is_recorded']),
    ('X02', 'a stale (superseded) dispatch authorisation accepted', [(EX,
     "    if not latest or latest[-1].id != e.policy_decision_id or latest[-1].outcome != "
     "'covered':",
     "    if not latest or latest[-1].outcome != 'covered':")],
     [I + '::test_E04_a_superseded_authorisation_never_starts']),
    ('X03', 'a superseded plan accepted', [(EX,
     "    if prow is None or prow.entity.id != e.plan_id or prow.entity.state != 'APPROVED':",
     "    if prow is None:")],
     [I + '::test_E05_a_superseded_plan_never_starts']),
    ('X04', 'the plan digest ignored', [(EX,
     "    if plan.digest != e.plan_digest or not authorization.intact(conn, plan):",
     "    if False:")],
     [I + '::test_E06_a_plan_whose_rows_no_longer_match_its_digest_never_starts']),
    ('X05', 'the task binding ignored', [(EX,
     "    if trow is None or trow.entity.plan_id != plan.id or trow.entity.state != 'RUNNING':",
     "    if False:")],
     [I + '::test_E07_the_binding_names_its_exact_task']),
    # ── process identity (§15.1) ──
    ('X06', 'a process identified by its pid alone', [(NODE,
     "                and proc.process_create_time(handle.pid) == handle.create_time)",
     "                and proc.process_create_time(handle.pid) is not None)")],
     [I + '::test_E10_a_pid_now_held_by_another_process_is_never_killed']),
    ('X07', 'a reused pid killed', [(NODE,
     "        if handle is None or not self.alive(handle):\n            return 'gone'",
     "        if handle is None:\n            return 'gone'")],
     [I + '::test_E10_a_pid_now_held_by_another_process_is_never_killed']),
    # ── the hook's guards (§10) ──
    ('X08', 'the hook token not checked', [(EX,
     "    if not (e.hook_token_hash and isinstance(tok, str) and hmac.compare_digest(",
     "    if False and not (e.hook_token_hash and isinstance(tok, str) and hmac.compare_digest(")],
     [I + '::test_E44_a_request_with_another_executions_token_is_refused']),
    ('X09', 'the hook sequence not checked', [(EX,
     "    if seq <= e.hook_seq:",
     "    if False:")],
     [I + '::test_E45_a_replayed_or_reordered_request_is_refused']),
    ('X10', 'the hook directory not checked', [(HOOK,
     "    if not (home and token and _ID.match(eid)):",
     "    if not (home and token):")],
     [I + '::test_E48_the_hook_refuses_to_run_inside_itself_or_without_an_identity']),
    # ── concrete boundaries (§11) ──
    ('X11', 'the branch check skipped', [(EX,
     "    if not branch_ok:",
     "    if False:")],
     [I + '::test_E46_a_workdir_escape_or_a_branch_mismatch_halts']),
    ('X12', 'the host dropped from the action', [(CAN,
     "        return [Action(action_class='web', target=url or 'web', host=host_of(url))], False",
     "        return [Action(action_class='web', target=url or 'web')], False")],
     [I + '::test_E43_a_host_rule_reaches_the_action']),
    ('X13', 'the workdir check skipped', [(EX,
     "    if not cwd_ok:",
     "    if False:")],
     [I + '::test_E46_a_workdir_escape_or_a_branch_mismatch_halts']),
    ('X14', 'an unclassified command classified permissive', [(CAN,
     "    if '$' in cmd or '`' in cmd or _OPERATOR.search(_outside_quotes(cmd)):\n"
     "        return [_unclassified('shell', (cmd,))], True",
     "    if '$' in cmd or '`' in cmd or _OPERATOR.search(_outside_quotes(cmd)):\n"
     "        return [_unclassified('shell', (cmd,))], False")],
     [I + '::test_E42_an_unclassified_command_is_judged_as_the_strictest_class']),
    # ── runtime (§12) ──
    ('X15', 'the ceiling not enforced', [(MGR,
     "            if worst is not None and worst >= pol.entity.allocation_pct:",
     "            if False:")],
     [I + '::test_E30_crossing_the_allocation_stops_the_execution_uncharged_and_drops_affinity']),
    ('X16', 'the breaker disabled', [(EX,
     "        if a.health in ('AVAILABLE', 'CONSTRAINED') and len(recent) >= STORM:",
     "        if False:")],
     [I + '::test_E32_the_breaker_is_per_account_and_counts_only_resource_failures']),
    # ── the e-stop (§13) ──
    ('X17', 'the e-stop ignored at spawn', [
        (MGR, "        if disarmed:\n            self._do(X.refuse, execution_id=e.id, "
              "reason='emergency stop: nothing starts',",
              "        if False:\n            self._do(X.refuse, execution_id=e.id, "
              "reason='emergency stop: nothing starts',"),
        (MGR, "        if self.node.disarmed():\n            self._do(X.refuse, execution_id=e.id, "
              "reason='emergency stop: nothing starts',",
              "        if False:\n            self._do(X.refuse, execution_id=e.id, "
              "reason='emergency stop: nothing starts',")],
     [I + '::test_E14_nothing_starts_while_disarmed']),
    ('X18', 'an e-stop racing the spawn ignored', [(MGR,
     "        if self.node.disarmed():            # the e-stop raced the spawn: it loses",
     "        if False:")],
     [I + '::test_E25_an_estop_racing_a_spawn_kills_what_started']),
    # ── ends and duplicates (§8) ──
    ('X19', 'a duplicate completion accepted', [(EX,
     "        raise lifecycle.IllegalTrigger('execution', e.state, 'record_end',\n"
     "                                       'the execution has already ended')",
     "        return {'execution_id': e.id, 'state': e.state}")],
     [I + '::test_E27_a_second_report_of_one_end_changes_nothing']),
    ('X20', 'a duplicate stop accepted', [(EX,
     "    e = _fire(tx, e.id, 'stop', actor, reason, {'stop_reason': stop_reason})",
     "    if e.state not in LIVE:\n        return {'execution_id': e.id, 'state': e.state}\n"
     "    e = _fire(tx, e.id, 'stop', actor, reason, {'stop_reason': stop_reason})")],
     [I + '::test_E22_a_user_stop_kills_by_identity_charges_nothing_and_blocks_the_mission']),
    ('X21', 'usage detached from its execution', [(EX,
     "        tx.insert(entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=e.id,",
     "        tx.insert(entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=None,")],
     [I + '::test_E33_usage_is_the_providers_cumulative_figure_ledgered_once_at_the_end']),
    ('X22', 'ENDED_OK straight to SUCCEEDED', [(EX,
     "                           reason='%s; verifying' % why)[0].entity\n",
     "                           reason='%s; verifying' % why)[0].entity\n"
     "        t = lifecycle.fire(tx, entities.Task, t.id, 'checks_passed', actor=actor,\n"
     "                           reason=why)[0].entity\n")],
     [I + '::test_E01_an_authorised_task_runs_and_a_clean_exit_is_evidence_not_success']),
    ('X23', 'a vanished process recorded as success', [(EX,
     "    ok = exit_code == 0 and not killed and not halted",
     "    ok = not halted")],
     [I + '::test_E13_a_vanished_process_is_never_success']),
    ('X24', 'uncharged ends charged', [(EX,
     "                       charged=e.stop_reason not in UNCHARGED, ended_at=_now_iso(),",
     "                       charged=True, ended_at=_now_iso(),")],
     [I + '::test_E22_a_user_stop_kills_by_identity_charges_nothing_and_blocks_the_mission']),
    ('X25', 'charged ends uncharged', [(EX,
     "                   charged=not (uncharged or stop), stop_reason=stop, ended_at=_now_iso(),",
     "                   charged=False, stop_reason=stop, ended_at=_now_iso(),")],
     [I + '::test_E26_a_failing_task_retries_with_new_executions_until_its_budget']),
    ('X26', 'progress offset allowed to go backwards', [(EX,
     "    if offset < e.stream_offset:\n        raise ValueError(",
     "    if False:\n        raise ValueError(")],
     [I + '::test_E71_progress_never_goes_backwards']),
    # ── recovery (§15.3) ──
    ('X27', 'an orphan left running on a disarmed boot', [(MGR,
     "        if alive and disarmed:\n            self.node.kill(adapter, handle)",
     "        if False:\n            self.node.kill(adapter, handle)")],
     [I + '::test_E62_a_disarmed_core_kills_live_orphans_at_boot']),
    ('X28', 'restart reconciliation skipped', [(MGR,
     "            try:\n                self._reconcile_one(e, disarmed)\n",
     "            try:\n")],
     [I + '::test_E60_a_new_core_adopts_a_live_process_and_records_its_end']),
    # ── resume (§14) ──
    ('X29', 'a resume without re-routing', [(EX,
     "            if (rd.result not in ('selected', 'fallback')\n"
     "                    or (rd.harness_id, rd.account_id) != (e.harness_id, e.account_id)):",
     "            if False:")],
     [S + '::test_S05_a_resume_never_routes_around_p10']),
    ('X30', 'a resume without P9', [(EX,
     "            auth = authorization.check_dispatch(tx, actor=actor, policy=policy,\n"
     "                                                missions=missions, mission=m, plan=plan, "
     "task=t)",
     "            auth = {'outcome': 'covered', 'policy_decision_id': e.policy_decision_id}")],
     [S + '::test_S07_a_resume_is_judged_by_p9_again']),
]


def _apply(edits):
    """{path: (original, mutated)} for *edits*; raises if a snippet is not unique."""
    out = {}
    for rel, old, new in edits:
        path = os.path.join(ROOT, rel)
        if path not in out:
            with open(path, encoding='utf-8', newline='') as f:
                src = f.read()
            out[path] = (src, src)
        src, cur = out[path]
        if cur.count(old) != 1:
            raise SystemExit('the snippet occurs %d times in %s:\n%s' % (cur.count(old), rel,
                                                                        old))
        out[path] = (src, cur.replace(old, new))
    return out


def run(selected=()):
    chosen = [m for m in MUTATIONS if not selected or m[0] in selected]
    for _mid, _what, edits, _tests in chosen:          # every snippet checked before any run
        _apply(edits)
    survived, killed = [], []
    for mid, what, edits, tests in chosen:
        files = _apply(edits)
        try:
            for path, (_src, mutated) in files.items():
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(mutated)
            try:
                r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-x', '-p',
                                    'no:cacheprovider', *tests], cwd=ROOT, capture_output=True,
                                   text=True, timeout=TIMEOUT_S)
                caught, how = r.returncode != 0, ''
            except subprocess.TimeoutExpired:
                caught, how = True, ' (timed out)'
        finally:
            for path, (src, _mutated) in files.items():
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(src)
        (killed if caught else survived).append(mid)
        print('%-5s %-8s %s%s' % (mid, 'killed' if caught else 'SURVIVED', what, how),
              flush=True)
    print('\n%d/%d killed' % (len(killed), len(killed) + len(survived)))
    return 1 if survived else 0


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))
