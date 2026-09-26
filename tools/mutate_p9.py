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
