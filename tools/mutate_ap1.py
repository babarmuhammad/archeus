"""The AP-1 mutation suite (ADR-0041 §1, §3; ADR-0048; testing-strategy §8:
AP-1, G9, G10, AP-UK, AP-CC, AP-ID, AP-RT, CX-7): break each safety rule of
account protection, run the tests that guard it, and require them to fail.

    py tools/mutate_ap1.py            every mutation
    py tools/mutate_ap1.py A05 A08    only these

Same runner as tools/mutate_p11.py: each mutation replaces exact snippets
(each must occur once), runs its tests, and restores the files whatever
happens; a mutation the tests do not catch ("survived") fails the run. It
edits sources: run it with nothing else running against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402

RT = 'archeus/core/routing/router.py'
RS = 'archeus/core/application/resources.py'
CA = 'archeus/core/application/calls.py'
EX = 'archeus/core/application/executions.py'
WK = 'archeus/core/application/work.py'
HO = 'archeus/core/execution/handoff.py'
HC = 'archeus/harnesses/calls.py'
EN = 'archeus/core/domain/entities.py'
U = 'tests/v1/unit/test_ap1_units.py'
I = 'tests/v1/integration/test_account_protection.py'
KU = 'tests/v1/unit/test_knowledge_units.py'
E = 'tests/v1/integration/test_execution.py'

MUTATIONS = [
    # ── the partition, before ordering (AP-1) ──
    ('A01', 'a protected (last_resort) account allowed like a normal one', [(RT,
     "    return ((c['_a'].get('policy') or {}).get('consumption') == 'last_resort'\n"
     "            and not _named(c, req))",
     "    return False")],
     [U + '::test_a_last_resort_account_is_never_elected_while_a_normal_one_survives',
      I + '::test_a_last_resort_account_waits_while_a_normal_one_can_run']),
    ('A02', 'protection applied after ordering', [(RT,
     "    ordered = sorted(normal, key=lambda c: order_key(c, req, snap))",
     "    ordered = sorted(live, key=lambda c: order_key(c, req, snap))")],
     [U + '::test_affinity_to_a_now_protected_account_does_not_keep_the_work_there',
      U + '::test_a_last_resort_account_is_never_elected_while_a_normal_one_survives']),
    ('A03', 'a lone last_resort account elected directly, not as a fallback', [(RT,
     "    ordered = sorted(normal, key=lambda c: order_key(c, req, snap))",
     "    ordered = sorted(normal or live, key=lambda c: order_key(c, req, snap))")],
     [U + '::test_with_only_last_resort_left_it_is_a_fallback_under_its_own_mode',
      U + '::test_all_protected_is_never_a_silent_fallback']),
    ('A04', 'a protected fallback preferred over a normal one', [(RT,
     "                    key=lambda c: (_last_resort(c, req), order_key(c, req, snap)))",
     "                    key=lambda c: order_key(c, req, snap))")],
     [U + '::test_a_normal_account_in_fallback_comes_before_a_last_resort_one']),
    ('A05', 'explicit_only selected automatically', [(RT,
     "    if p.get('consumption') == 'explicit_only' and not _named(c, req):",
     "    if False:")],
     [U + '::test_explicit_only_is_never_automatic_and_a_user_named_account_lifts_it',
      I + '::test_explicit_only_is_used_only_when_a_user_device_names_it_for_that_mission']),
    ('A06', 'the lift granted by any preference, not by naming the account', [(RT,
     "        | _ids(req.get('required'), 'accounts'))",
     "        | _ids(req.get('required'), 'accounts')) or bool(req.get('preferred'))")],
     [U + '::test_explicit_only_is_never_automatic_and_a_user_named_account_lifts_it']),
    ('A07', 'an exclusion reason dropped', [(RT,
     "                c['reason'] = 'a last-resort account, not used while a normal one can run'",
     "                c['reason'] = None")],
     [U + '::test_every_candidate_that_is_not_elected_has_a_step_and_a_reason',
      I + '::test_a_last_resort_account_waits_while_a_normal_one_can_run']),
    # ── budgets, and unknown never 0 (G10, AP-UK) ──
    ('A08', 'budgets skipped on an account with a readable window', [(RT,
     "    why = _budgets(budgets, a)",
     "    why = _budgets(budgets, a) if w is None else None")],
     [U + '::test_a_budget_on_a_windowed_account_is_enforced']),
    ('A09', 'unknown usage read as complete (zero for the rest)', [(RT,
     "        if m is not None and (not done.get(m, True)",
     "        if m is not None and (False")],
     [U + '::test_partly_unreported_usage_makes_a_budget_unevaluable_never_zero',
      I + '::test_a_call_that_ended_with_no_outcome_makes_the_day_unknown_never_zero']),
    ('A10', 'partial usage counted as a total in the ledger', [(RS,
     "        complete['tokens'] &= whole and None not in (e.tokens_in, e.tokens_out)",
     "        complete['tokens'] &= True")],
     [I + '::test_an_execution_that_ran_always_leaves_a_row_with_its_basis']),
    ('A11', 'an absent figure reported as 0 by the adapter', [(HC,
     "    return {ours: u[theirs] for theirs, ours in names.items()\n"
     "            if isinstance(u.get(theirs), int) and not isinstance(u.get(theirs), bool)}",
     "    return {ours: u.get(theirs) or 0 for theirs, ours in names.items()}")],
     [KU + '::test_l13_claude_code_calls_read_only_ephemeral_and_native']),
    ('A12', 'an execution that reported nothing leaves no row', [(EX,
     "    if e.route_decision_id is None or e.process_seq < 1:\n        return",
     "    if e.route_decision_id is None or e.process_seq < 1 or not (usage or e.usage):\n"
     "        return")],
     [E + '::test_E34_unknown_usage_writes_a_row_that_says_so_never_zero',
      I + '::test_an_execution_that_ran_always_leaves_a_row_with_its_basis']),
    ('A13', 'a lower bound labelled the harness total', [(EX,
     "    basis = 'none' if not u else 'reported_total' if total and e.process_seq == 1 else 'partial'",
     "    basis = 'none' if not u else 'reported_total'")],
     [I + '::test_an_execution_that_ran_always_leaves_a_row_with_its_basis']),
    ('A14', 'an own call that reported nothing leaves no row', [(CA,
     "    ran = usage is not None or outcome['state'] not in NOT_RUN",
     "    ran = bool(usage)")],
     [I + '::test_an_own_call_leaves_a_row_unless_it_never_ran']),
    ('A15', 'a budget accepted on a measure nobody reports', [(RS,
     "        if m is not None and m not in (usage_measures or ()):",
     "        if False:")],
     [I + '::test_the_class_is_set_by_a_user_device_and_a_budget_only_on_a_reported_measure']),
    # ── concurrency over live work (AP-CC) ──
    ('A16', 'the concurrency budget bypassed', [(RT,
     "        if led[_LEDGER[k]] >= budgets[k]:",
     "        if k != 'concurrency' and led[_LEDGER[k]] >= budgets[k]:")],
     [U + '::test_a_full_concurrency_budget_refuses_tasks_and_own_calls_alike',
      I + '::test_a_live_task_holds_the_last_slot_against_an_own_call']),
    ('A17', 'own calls in flight not counted', [(RS,
     "        if own_call_live(r, now):\n            mine(rd.account_id)['running'] += 1",
     "        if False:\n            mine(rd.account_id)['running'] += 1")],
     [I + '::test_an_own_call_in_flight_holds_the_last_slot_against_a_task']),
    ('A18', 'a slot not released by the call\'s outcome', [(RS,
     "    if rd.outcome is not None or rd.result not in ('selected', 'fallback'):",
     "    if rd.result not in ('selected', 'fallback'):")],
     [I + '::test_an_own_call_in_flight_holds_the_last_slot_against_a_task',
      I + '::test_a_failed_or_abandoned_call_releases_its_slot']),
    ('A19', 'an abandoned call holds its slot for ever', [(RS,
     "    return bound is None or now - _epoch(row.created_at) <= bound",
     "    return True")],
     [I + '::test_a_failed_or_abandoned_call_releases_its_slot']),
    ('A20', 'a slot released twice (the outcome rewritten)', [(CA,
     "    if row.entity.outcome is not None:\n        raise ValueError",
     "    if False:\n        raise ValueError")],
     [I + '::test_an_own_call_in_flight_holds_the_last_slot_against_a_task']),
    ('A21', 'an own call decided over a stale snapshot, outside its transaction', [(RS,
     "    snapshot = refresh_ledgers(tx.conn, snapshot, time.time() if now is None else now)",
     "    snapshot = snapshot")],
     [I + '::test_two_own_calls_cannot_both_take_the_last_slot']),
    # ── retries and continuations (CX-7) ──
    ('A22', 'a continuation reuses the ended decision instead of routing', [(HO,
     "        route = router.route(Ref('task', t.id), now, tx=tx, actor=actor, authorization=auth,\n"
     "                             mission=m, plan=plan, task=t)",
     "        route = tx.get(entities.RouteDecision, e.route_decision_id).entity")],
     [I + '::test_a_continuation_never_goes_back_to_an_account_protected_since']),
    ('A23', 'a retry reuses the task\'s last decision instead of routing', [(WK,
     "        route = self.router.route(Ref('task', task_id), time.time() if now is None else now,",
     "        prev = [r.entity for r in tx.where(entities.RouteDecision, task_id=task_id)]\n"
     "        route = prev[-1] if prev else self.router.route(\n"
     "            Ref('task', task_id), time.time() if now is None else now,")],
     [I + '::test_a_retry_never_goes_to_an_account_made_explicit_only_since']),
    # ── one election, one key (AP-RT, AP-ID) ──
    ('A24', 'an account chosen outside the router (legacy rotation)', [(HC,
     "        return base.default_ref(self.id, config.resolve_config_dir(None))\n\n"
     "    def why_not(self, account):\n"
     "        \"\"\"`quota.reason()`",
     "        from claude_sessions import rotate\n"
     "        return base.default_ref(self.id, rotate.elect())\n\n"
     "    def why_not(self, account):\n"
     "        \"\"\"`quota.reason()`")],
     [I + '::test_no_v1_module_chooses_an_account_outside_the_router',
      I + '::test_ap1_writes_nothing_outside_archeus_home']),
    ('A25', 'the default account survives a registration', [(RS,
     "        if h['installed'] and 'headless' in h['capabilities'] and a.id not in have:",
     "        if h['installed'] and 'headless' in h['capabilities']:")],
     [I + '::test_the_default_account_exists_only_until_the_harness_has_a_registered_one']),
    ('A26', 'a task names the default account ":default", apart from own calls', [(RS,
     "            accounts.append({'id': None, 'ref': ref and ref.account_id,\n"
     "                             'home_ref': ref and ref.home_ref,\n"
     "                             'harness': h['id'],",
     "            accounts.append({'id': None, 'ref': '%s:default' % h['id'],\n"
     "                             'home_ref': None,\n"
     "                             'harness': h['id'],")],
     [I + '::test_a_task_and_an_own_call_name_the_unregistered_default_alike']),
    ('A27', 'one home registered twice', [(RS,
     "                                      ) == key:",
     "                                      ) == key and False:")],
     [I + '::test_one_home_is_one_account_and_its_home_never_changes']),
    ('A28', 'an account\'s home changed after registration', [(EN,
     "    _FROZEN = ('harness_id', 'auth_kind', 'node_id', 'home_ref', 'home_key')",
     "    _FROZEN = ('harness_id', 'auth_kind', 'node_id')")],
     [I + '::test_one_home_is_one_account_and_its_home_never_changes']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
