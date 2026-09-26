"""The P10 mutation suite (p10-design-gate §19): break each invariant the
resource router keeps, run the tests that guard it, and require them to fail.

    py tools/mutate_p10.py            every mutation
    py tools/mutate_p10.py R05 R12    only these

Each mutation replaces one exact snippet (which must occur once), runs its
tests, and restores the file whatever happens. A mutation the tests do not
catch ("survived") fails the run. It edits sources: run it with nothing else
running against the tree.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RT = 'archeus/core/routing/router.py'
RES = 'archeus/core/application/resources.py'
WORK = 'archeus/core/application/work.py'
ENG = 'archeus/core/engine.py'
CALLS = 'archeus/core/calls.py'
ENT = 'archeus/core/domain/entities.py'
U = 'tests/v1/unit/test_routing_units.py'
I = 'tests/v1/integration/test_routing.py'
B = 'tests/v1/unit/test_routing_boundaries.py'
K1 = 'tests/v1/judge/test_k01_knowledge_without_claude.py'
S4 = 'tests/v1/judge/test_s04_limit_and_fallback.py'

MUTATIONS = [
    # ── eligibility (the elimination steps) ──
    ('R01', 'an incapable harness selected', RT,
     "    if missing:\n        return 'lacks %s' % ', '.join(missing)\n",
     "    if False:\n        return 'lacks %s' % ', '.join(missing)\n",
     [U + '::test_an_incapable_harness_is_never_selected_even_alone']),
    ('R02', 'a preferred resource overriding capability', RT,
     "    if missing:\n        return 'lacks %s' % ', '.join(missing)\n",
     "    if missing and c['harness'] not in _ids(req.get('preferred'), 'harnesses'):\n"
     "        return 'lacks %s' % ', '.join(missing)\n",
     [U + '::test_a_preferred_or_required_harness_lacking_a_capability_is_still_eliminated']),
    ('R03', 'native structured output required', RT,
     "    if req.get('structured_output') and h.get('structured_output') not in ('native', "
     "'prompted'):",
     "    if req.get('structured_output') and h.get('structured_output') != 'native':",
     [U + '::test_structured_output_is_met_natively_or_in_the_prompt',
      U + '::test_native_unavailable_but_prompted_available_selects_the_prompted_one']),
    ('R04', 'prompted structured output rejected at the snapshot', RES,
     "            'structured_output': caps.structured_output if caps else None,",
     "            'structured_output': (caps.structured_output if caps.structured_output\n"
     "                                  != 'prompted' else None) if caps else None,",
     [K1 + '::test_the_pass_runs_on_a_harness_that_is_not_claude_code']),
    ('R05', 'a model leaked across harnesses', RT,
     "    want = (req.get('models') or {}).get(h['id'])",
     "    want = next(iter((req.get('models') or {}).values()), None)",
     [U + '::test_switching_harness_never_carries_the_previous_harness_model']),
    ('R06', 'a model that is not an offer used anyway', RT,
     "    if want and want in offers and fits(offers[want]):",
     "    if want:",
     [U + '::test_a_model_that_is_not_an_offer_is_dropped_never_translated']),
    ('R07', 'the tier minimum ignored', RT,
     "        return (_rank(m.get('tier')) >= _rank(need)",
     "        return (True",
     [U + '::test_a_tier_minimum_picks_the_smallest_offer_that_meets_it_and_excludes_unknown',
      I + '::test_I_R5_a_task_needing_a_tier_no_account_offers_is_blocked_with_the_reason']),
    ('R08', 'enforcement ignored', RT,
     "    if mode == 'hook':\n        return None\n",
     "    if True:\n        return None\n",
     [U + '::test_enforcement_follows_the_authorised_items']),
    ('R09', 'provider terms (first check) ignored', RT,
     "    if h.get('exempt'):\n        return None\n",
     "    if True:\n        return None\n",
     [U + '::test_a_real_harness_needs_permitted_terms_and_a_scripted_one_never_does',
      I + '::test_I_T1_a_real_execution_adapter_needs_permitted_terms_to_be_routed']),
    ('R10', 'rotation across subscriptions not gated', RT,
     "        if first['id'] != a['id']:",
     "        if False:",
     [U + '::test_rotation_across_subscriptions_needs_its_own_permission']),
    ('R11', 'a disabled account routed', RT,
     "    if a['health'] not in ROUTABLE:",
     "    if False:",
     [U + '::test_a_disabled_or_unverified_account_is_never_routed_and_degraded_only_by_fallback',
      I + '::test_I_R2_the_probe_decides_health_and_only_available_accounts_are_routed']),
    # ── allocation ──
    ('R12', 'the allocation ceiling ignored', RT,
     "        if w + bump < cap:\n            return None\n",
     "        if True:\n            return None\n",
     [U + '::test_a_task_starts_only_under_the_ceiling_minus_the_projected_bump',
      S4 + '::test_no_execution_starts_on_an_account_at_its_ceiling']),
    ('R13', 'the brain reserve not kept from tasks', RT,
     "    return eff if subject == 'archeus_call' else eff - policy['brain_reserve_pct']",
     "    return eff",
     [U + '::test_an_own_call_may_use_the_brain_reserve_a_task_may_not']),
    ('R14', 'unknown usage read as 0%', RT,
     "    if not windows:\n        return None\n",
     "    if not windows:\n        return 0\n",
     [U + '::test_unknown_usage_is_never_zero']),
    ('R15', 'the stale-usage penalty dropped', RT,
     "    if penalty and (usage.get('age_s') or 0) > STALE_S:",
     "    if False:",
     [U + '::test_stale_usage_carries_the_penalty']),
    ('R16', 'the projected bump dropped (a ceiling exceeded at start)', RT,
     "        bump = PROJECTED.get(req.get('size'), 0)",
     "        bump = 0",
     [U + '::test_a_task_starts_only_under_the_ceiling_minus_the_projected_bump']),
    # ── ordering, continuity, determinism ──
    ('R17', 'fallback skipped', RT,
     "                or next((c for c in fb if c['fallback'] == 'allow'), None))",
     "                )",
     [U + '::test_fallback_follows_the_account_policy',
      U + '::test_fallback_is_never_skipped_while_one_is_allowed']),
    ('R18', 'the router answers its own `ask` (self-approval)', RT,
     "                or next((c for c in fb if c['fallback'] == 'allow'), None))",
     "                or next((c for c in fb if c['fallback'] in ('allow', 'ask')), None))",
     [U + '::test_fallback_follows_the_account_policy', S4 + '::test_fallback_follows_the_'
      'account_policy']),
    ('R19', 'nondeterministic candidate ordering (input order)', RT,
     "    for h in sorted(snap.get('harnesses') or (), key=lambda h: h['id']):",
     "    for h in (snap.get('harnesses') or ()):",
     [U + '::test_P_properties_over_generated_worlds']),
    ('R20', 'no stable tie-break', RT,
     "            _rank(tier) if c['model'] else 0, 1 if c['constrained'] else 0, c['resource'])",
     "            _rank(tier) if c['model'] else 0, 1 if c['constrained'] else 0)",
     [U + '::test_multiple_accounts_at_the_same_priority_break_ties_by_id',
      U + '::test_P_properties_over_generated_worlds']),
    ('R21', 'continuity overriding allocation', RT,
     "    p, usage = a['policy'], a.get('usage')\n",
     "    p, usage = a['policy'], a.get('usage')\n"
     "    if (snap.get('affinity') or {}).get('account') == _key(c):\n        return None\n",
     [U + '::test_continuity_never_overrides_capability_or_allocation']),
    ('R37', 'continuity overriding capability', RT,
     "    if missing:\n        return 'lacks %s' % ', '.join(missing)\n",
     "    if missing and (snap.get('affinity') or {}).get('harness') != c['harness']:\n"
     "        return 'lacks %s' % ', '.join(missing)\n",
     [U + '::test_continuity_never_overrides_capability_or_allocation']),
    ('R22', 'priority ignored', RT,
     "    return (0 if affine else 1, 0 if pref else 1, c['priority'],",
     "    return (0 if affine else 1, 0 if pref else 1, 0,",
     [U + '::test_a_preferred_account_wins_over_priority_when_valid',
      U + '::test_the_allocation_is_a_ceiling_not_a_share_that_must_be_used']),
    # ── the P9 -> P10 contract ──
    ('R23', 'a pending approval routed (dispatch skips the P9 outcome)', WORK,
     "        if auth['outcome'] != 'covered':\n",
     "        if False:\n",
     [I + '::test_I_A3_a_task_waiting_on_an_approval_is_never_routed']),
    ('R24', 'a non-covered decision accepted by the router', RES,
     "    if (d.stage, d.outcome, d.task_id) != ('dispatch', 'covered', task.id):",
     "    if (d.stage, d.task_id) != ('dispatch', task.id):",
     [I + '::test_I_A4_a_stale_superseded_or_foreign_authorisation_cannot_route']),
    ('R25', 'a superseded authorisation accepted', RES,
     "    if latest[-1].id != d.id:",
     "    if False:",
     [I + '::test_I_A4_a_stale_superseded_or_foreign_authorisation_cannot_route']),
    ('R26', 'a DENY in the record ignored (router bypassing P9)', RES,
     "    if d.decision == 'DENY' or any(i.get('decision') == 'DENY' for i in d.items):",
     "    if False:",
     [I + '::test_I_A6_a_forged_covered_decision_that_carries_a_deny_cannot_route']),
    ('R27', 'another plan version accepted', RES,
     "    if (d.plan_id, d.plan_digest) != (plan.id, plan.digest):",
     "    if False:",
     [I + '::test_I_A4_a_stale_superseded_or_foreign_authorisation_cannot_route']),
    ('R28', 'the router creates an approved approval', RES,
     "        id=ids.new_id('approval'), kind='route', subject=Ref('task', task.id), "
     "action_hash=h,",
     "        id=ids.new_id('approval'), kind='route', subject=Ref('task', task.id), "
     "action_hash=h, state='APPROVED',",
     [I + '::test_I_F2_fallback_ask_asks_through_p9_and_only_a_user_device_answers',
      B + '::test_B4_p10_never_authorises_approves_or_changes_policy']),
    # ── provider terms, history, usage ──
    ('R29', 'the own-call terms re-check removed', CALLS,
     "        if not is_fake_caller(adapter):\n            with self.db.read() as conn:",
     "        if False:\n            with self.db.read() as conn:",
     [I + '::test_I_T3_an_own_call_is_checked_again_before_its_spawn']),
    ('R30', 'the execution terms re-check removed', ENG,
     "        if not permitted:\n            return self._reconcile",
     "        if False:\n            return self._reconcile",
     [I + '::test_I_T2_terms_revoked_between_routing_and_the_adapter_block_the_start']),
    ('R31', 'a historical routing decision mutable', ENT,
     "    _FROZEN = ('subject', 'selected', 'explanation',",
     "    _FROZEN = ('subject', 'explanation',",
     [I + '::test_I_H1_a_route_decision_never_changes_and_a_later_one_is_a_new_row',
      B + '::test_B10_a_router_decision_is_frozen_but_for_an_own_calls_outcome']),
    ('R32', 'usage detached from its routing decision (entity)', ENT,
     "        if self.route_decision_id is None:\n            raise ValueError('a usage row "
     "belongs",
     "        if False:\n            raise ValueError('a usage row belongs",
     [B + '::test_B10_a_router_decision_is_frozen_but_for_an_own_calls_outcome']),
    ('R33', 'an execution\'s usage not ledgered against its decision', WORK,
     "        if usage and e.route_decision_id is not None:",
     "        if False:",
     [I + '::test_I_U1_an_executions_usage_points_at_its_route_decision_and_counts_for_budgets']),
    ('R34', 'an own call run on a different account than decided', CALLS,
     "        account = base.AccountRef(d['account_id'] or d['account_ref'], acct.get('home_ref'))",
     "        account = base.AccountRef(d['account_ref'] or d['harness_id'], acct.get('home_ref'))",
     [I + '::test_I_U2_an_own_calls_usage_points_at_its_route_decision_and_account']),
    ('R35', 'a blocked task leaves its mission running', WORK,
     "            self.missions._fire(tx, m.id, 'block', actor=actor, reason=why)\n",
     "",
     [I + '::test_I_F4_nothing_eligible_blocks_the_mission_and_a_resume_routes_again',
      S4 + '::test_fallback_follows_the_account_policy']),
    ('R36', 'affinity never cleared by the mission\'s own resources', RES,
     "           and r.created_at > since]",
     "           ]",
     [I + '::test_I_R3_a_mission_stays_where_it_runs_until_its_resources_are_set']),
]


def run(selected=()):
    survived, killed = [], []
    for mid, what, rel, old, new, tests in MUTATIONS:
        if selected and mid not in selected:
            continue
        path = os.path.join(ROOT, rel)
        with open(path, encoding='utf-8', newline='') as f:
            src = f.read()
        if src.count(old) != 1:
            raise SystemExit('%s: the snippet occurs %d times in %s' % (mid, src.count(old), rel))
        try:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(src.replace(old, new))
            r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-x', '-p',
                                'no:cacheprovider', *tests], cwd=ROOT, capture_output=True,
                               text=True)
        finally:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(src)
        (killed if r.returncode != 0 else survived).append(mid)
        print('%-5s %-8s %s' % (mid, 'killed' if r.returncode else 'SURVIVED', what))
    print('\n%d/%d killed' % (len(killed), len(killed) + len(survived)))
    return 1 if survived else 0


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))
