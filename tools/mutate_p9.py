"""The P9 mutation suite (p9-design-gate §22): break each rule policy and
authorisation keep, run the tests that guard it, and require them to fail.

    py tools/mutate_p9.py            every mutation
    py tools/mutate_p9.py M04 M12    only these

Each mutation replaces one exact snippet (which must occur once), runs its
tests, and restores the file whatever happens. A mutation the tests do not
catch ("survived") fails the run. It edits sources: run it with nothing else
running against the tree.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U = 'tests/v1/unit/test_policy_units.py'
ENG = 'archeus/core/policy/engine.py'
RUL = 'archeus/core/policy/rules.py'
AUTH = 'archeus/core/application/authorization.py'
I = 'tests/v1/integration/test_policy.py'
PL = 'tests/v1/integration/test_planning.py'
B = 'tests/v1/unit/test_policy_boundaries.py'
UD = 'tests/v1/unit/test_domain.py'
S5 = 'tests/v1/judge/test_s05_approvals.py'
G6 = 'tests/v1/judge/test_g06_security.py'

MUTATIONS = [
    # ── the pure engine (commit 2) ──
    ('M01', 'DENY ranked below ALLOW (deny -> allow)', RUL,
     "STRICTNESS = {'ALLOW': 0, 'ALLOW_WITHIN_BOUNDARY': 1, 'ASK': 2, 'DENY': 3}",
     "STRICTNESS = {'ALLOW': 0, 'ALLOW_WITHIN_BOUNDARY': 1, 'ASK': 2, 'DENY': -1}",
     [U + '::test_U_R2_global_deny_cannot_be_loosened_by_a_narrower_allow']),
    ('M03', 'specificity ordering removed (broadest wins)', ENG,
     "    return (-_depth(r), -R.STRICTNESS[r['decision']], r['id'])",
     "    return (_depth(r), -R.STRICTNESS[r['decision']], r['id'])",
     [U + '::test_U_R3_a_user_rule_overrides_the_users_own_profile',
      U + '::test_U_R4_a_project_restriction_tightens_and_applies_only_to_that_project']),
    ('M04', 'explicit deny ignored (locks ignored)', ENG,
     "    effective = [specific[0]] + [r for r in applicable\n"
     "                                 if r['locked'] and _depth(r) < top_depth]",
     "    effective = [specific[0]]",
     [U + '::test_U_R2_global_deny_cannot_be_loosened_by_a_narrower_allow']),
    ('M05', 'project restriction bypassed', ENG,
     "    if level == 'GLOBAL' or r['source'] == 'profile':\n        return True\n",
     "    if level == 'GLOBAL' or r['source'] == 'profile':\n        return True\n"
     "    if level == 'PROJECT':\n        return False\n",
     [U + '::test_U_R4_a_project_restriction_tightens_and_applies_only_to_that_project']),
    ('M06a', 'task rules ignored', ENG,
     "    if level == 'GLOBAL' or r['source'] == 'profile':\n        return True\n",
     "    if level == 'GLOBAL' or r['source'] == 'profile':\n        return True\n"
     "    if level == 'TASK':\n        return False\n",
     [U + '::test_U_R5_a_task_rule_restricts_that_task_only']),
    ('M06b', 'the implicit task contract removed', ENG,
     "    if stage != 'plan' and task_classes is not None and cls not in task_classes:\n",
     "    if False:\n",
     [U + '::test_U_R7_the_task_contract_asks_for_an_undeclared_class_outside_the_plan_stage']),
    ('M07', 'boundary condition removed', ENG,
     "        if checks['outside']:\n            worst",
     "        if False:\n            worst",
     [U + '::test_U_B2_a_path_that_leaves_the_workspace_is_outside']),
    ('M20', 'missing policy -> ALLOW', ENG,
     "        return _result('DENY', cls, action, [miss], [miss], miss, [], None,",
     "        return _result('ALLOW', cls, action, [miss], [miss], miss, [], None,",
     [U + '::test_U_R10_no_applicable_rule_is_a_deny']),
    ('M21', 'e-stop ignored', ENG,
     "    if ctx.get('estop'):\n", "    if False:\n",
     [U + '::test_estop_denies_everything']),
    ('M23', 'autonomy loosens a locked rule', ENG,
     "                                 if r['locked'] and _depth(r) < top_depth]",
     "                                 if r['locked'] and _depth(r) < top_depth\n"
     "                                 and specific[0]['source'] != 'profile']",
     [U + '::test_U_P3_autonomy_never_loosens_a_locked_rule_or_the_floor']),
    ('M24', 'unknown attributes match permissive rules', RUL,
     "            if r['decision'] in RESTRICTIVE:\n                continue\n            return False",
     "            continue",
     [U + '::test_U_R8_leaving_an_attribute_out_never_reaches_a_permissive_rule']),
    ('M28a', 'step-up not required', ENG,
     "            'step_up': decision == 'ASK' and cls in R.STEP_UP_CLASSES, 'reason': why}",
     "            'step_up': False, 'reason': why}",
     [U + '::test_step_up_is_required_for_deploy_and_destructive_asks']),
    ('M31', 'containment trusts a wildcard prefix', RUL,
     "        return p[:wild.start()].startswith(base + '/')",
     "        return p[:wild.start()].startswith(base)",
     [U + '::test_containment_is_conservative']),
    ('M32', 'relative-path check removed', RUL,
     "    if not _relative(path):\n        return False\n", "",
     [U + '::test_U_B2_a_path_that_leaves_the_workspace_is_outside']),
    # ── authorisation (commit 3) ──
    ('M02', 'the plan gate treats ASK as allowed', 'archeus/core/domain/guards.py',
     "AUTO_OK = ('ALLOW', 'ALLOW_WITHIN_BOUNDARY')",
     "AUTO_OK = ('ALLOW', 'ALLOW_WITHIN_BOUNDARY', 'ASK')",
     [I + '::test_I_G2_an_ask_waits_for_one_approval_of_exactly_this_plan']),
    ('M08', 'a stale plan accepted', AUTH,
     "    if approve and a.kind == 'plan':\n", "    if False:\n",
     [I + '::test_I_A10_a_stale_plan_is_never_approved_but_can_be_refused']),
    ('M09', 'an old plan approval reused (supersession removed)',
     'archeus/core/application/work.py',
     "            authorization.supersede_for(tx, actor=actor, plan_id=prev.entity.id,\n"
     "                                        replaced_by=p.plan_version)\n",
     "            pass\n",
     [I + '::test_I_A07_an_approved_plans_approval_ends_with_it']),
    ('M10', 'action_hash ignored when deciding', AUTH,
     "    if given != a.action_hash:\n", "    if False:\n",
     [I + '::test_I_A05_a_hash_mismatch_writes_nothing']),
    ('M11', 'plan.digest removed from the action identity', 'archeus/core/domain/actions.py',
     "    return {'mission_id': mission_id, 'plan_id': plan_id, 'plan_version': plan_version,\n"
     "            'plan_digest': plan_digest,",
     "    return {'mission_id': mission_id, 'plan_id': plan_id, 'plan_version': plan_version,\n"
     "            'plan_digest': 'x' if plan_digest else plan_digest,",
     [UD + '::test_an_approval_hash_binds_the_exact_identity_and_not_the_policy']),
    ('M12', 'a single-use approval replayed', AUTH,
     "            lifecycle.fire(tx, entities.Approval, a.id, 'action_executed', actor=actor,\n"
     "                           reason='used once by execution %s' % execution_id)\n", "",
     [I + '::test_I_A14_an_action_approval_is_single_use']),
    ('M13', 'approval scope widened (coverage not by exact item)', AUTH,
     "    return want in [dict(x) for x in a.items] and (a.step_up or not step_up)",
     "    return a.step_up or not step_up",
     [I + '::test_approval_coverage_is_the_exact_item_and_its_step_up']),
    ('M14', 'an expired approval accepted', AUTH,
     "    if a.expires_at <= now:\n        return 'expired'",
     "    if False:\n        return 'expired'",
     [I + '::test_I_A11_an_expired_approval_covers_nothing_and_is_swept']),
    # a task approval is found by its task's own hash AND covers only its own
    # items, so no single edit lets another task through (I-D2 proves the
    # behaviour); this mutant removes the task from the identity itself
    ('M15', 'the task dropped from the action identity', 'archeus/core/domain/actions.py',
     "            'plan_digest': plan_digest, 'task_id': task_id, 'task_key': task_key,",
     "            'plan_digest': plan_digest, 'task_id': None, 'task_key': None,",
     [UD + '::test_an_approval_hash_binds_the_exact_identity_and_not_the_policy']),
    ('M16', 'a different plan version accepted', 'archeus/core/domain/actions.py',
     "    return {'mission_id': mission_id, 'plan_id': plan_id, 'plan_version': plan_version,",
     "    return {'mission_id': mission_id, 'plan_id': 'p', 'plan_version': 1,",
     [UD + '::test_an_approval_hash_binds_the_exact_identity_and_not_the_policy',
      I + '::test_I_A04_an_approval_never_covers_another_missions_same_plan']),
    ('M17', 'a policy decision changed after recording', 'archeus/core/domain/entities.py',
     "    _REFS = {'mission_id': 'mission', 'plan_id': 'plan', 'task_id': 'task',\n"
     "             'execution_id': 'execution', 'approval_id': 'approval'}\n"
     "    _FROZEN = FROZEN_ALL\n",
     "    _REFS = {'mission_id': 'mission', 'plan_id': 'plan', 'task_id': 'task',\n"
     "             'execution_id': 'execution', 'approval_id': 'approval'}\n"
     "    _FROZEN = ()\n",
     [I + '::test_rules_are_revised_never_edited_and_the_old_decision_keeps_its_policy']),
    ('M18', 'P10 routing invoked from authorisation', AUTH,
     "def check_dispatch(tx, *, actor, policy, missions, mission, plan, task):\n",
     "def check_dispatch(tx, *, actor, policy, missions, mission, plan, task):\n"
     "    missions.router.route(None, 0) if hasattr(missions, 'router') else None\n",
     [B + '::test_E2_policy_never_routes_spawns_executes_verifies_or_reviews']),
    ('M19', 'P11 execution invoked from authorisation', AUTH,
     "def evaluate_action(tx, *, actor, policy, execution_id, action, unclassified=False):\n",
     "def evaluate_action(tx, *, actor, policy, execution_id, action, unclassified=False):\n"
     "    import archeus.harnesses.fake as _f\n"
     "    _f.FakeHarness().start if False else None\n",
     [B + '::test_E1_policy_imports_no_later_phase_resource_or_process_module']),
    ('M22', 'the principal check removed', AUTH,
     "    _principal(tx, actor, 'approve')\n", "",
     [I + '::test_I_A15_only_a_user_device_with_approve_decides',
      G6 + '::test_the_brain_principal_can_never_approve']),
    ('M25', 'at most one live approval per identity (index dropped)',
     'archeus/infra/db/migrations/0008_policy.sql',
     "CREATE UNIQUE INDEX approvals_live ON approvals (action_hash)\n",
     "CREATE INDEX approvals_live ON approvals (action_hash)\n",
     [I + '::test_I_A12b_the_database_refuses_a_second_live_approval_of_one_identity']),
    ('M26', 'the mission approve edge unguarded', 'archeus/core/domain/guards.py',
     "    ('mission', 'approve'): approve_mission,\n", "",
     [I + '::test_I_A18_the_mission_approve_edge_by_name_approves_nothing']),
    ('M27', 'a plan denial not recorded', AUTH,
     "    denied = [i for i in items if i['decision'] == 'DENY']\n    if not denied:\n"
     "        return {'recorded': False, 'why': 'the policy no longer denies this plan'}",
     "    denied = [i for i in items if i['decision'] == 'DENY']\n    if True:\n"
     "        return {'recorded': False, 'why': 'the policy no longer denies this plan'}",
     [I + '::test_I_G3_a_denied_first_plan_blocks_as_denied_and_writes_no_plan',
      PL + '::test_i27_p9_a_denied_plan_is_recorded_and_a_policy_change_plans_again']),
    ('M28b', 'step-up not checked when deciding', 'archeus/core/domain/guards.py',
     "    if approval.step_up and not f.step_up_valid:\n", "    if False:\n",
     [I + '::test_I_A19_a_paired_device_cannot_step_up_before_P15']),
    ('M29', 'dispatch stops re-evaluating', AUTH,
     "    if whole and (plan_ok or task_granted) and not uncovered:\n",
     "    if whole:\n",
     [I + '::test_I_D2_a_policy_turned_ask_after_auto_approval_asks_for_the_task']),
    ('M30', 'the recorded result differs from the judged one', AUTH,
     "    plan, items = prow.entity, list(facts.evaluated)\n",
     "    plan, items = prow.entity, [dict(i, decision='ALLOW') for i in facts.evaluated]\n",
     [I + '::test_I_G2_an_ask_waits_for_one_approval_of_exactly_this_plan']),
    ('M33', 'a DENY approvable at decide time', AUTH,
     "    denied = [i for i in items if i['decision'] == 'DENY']\n    if denied:\n"
     "        d = record(tx, actor=actor, stage=stage,",
     "    denied = [i for i in items if i['decision'] == 'DENY']\n    if False:\n"
     "        d = record(tx, actor=actor, stage=stage,",
     [I + '::test_I_A17_a_deny_is_never_approvable']),
    ('M34', 'a superseded plan still eligible', AUTH,
     "    if plan is None or plan.id != a.plan_id or plan.state not in ('PROPOSED', 'APPROVED'):\n"
     "        return 'superseded'",
     "    if plan is None:\n        return 'superseded'",
     [I + '::test_I_A08b_a_pending_approval_of_a_version_no_longer_in_force_is_ineligible']),
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
