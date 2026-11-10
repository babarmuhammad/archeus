"""The P13 mutation suite (p13-design-gate §27): break each safety property of
verification, merge-back and review, run the tests that guard it, and require
them to fail.

    py tools/mutate_p13.py            every mutation
    py tools/mutate_p13.py Z04 Z13    only these

Same runner as tools/mutate_p11.py: each mutation replaces exact snippets
(each must occur once), runs its tests, and restores the files whatever
happens; a mutation the tests do not catch ("survived") fails the run. It
edits sources: run it with nothing else running against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (one runner)

VER = 'archeus/core/application/verification.py'
WRK = 'archeus/core/verification/worker.py'
REV = 'archeus/core/verification/reviewer.py'
EVD = 'archeus/core/verification/evidence.py'
LOC = 'archeus/node/local.py'
CMD = 'archeus/core/application/commands.py'
GRD = 'archeus/core/domain/guards.py'
J = 'tests/v1/judge/test_v01_outcome_verification.py'
I = 'tests/v1/integration/test_verification.py'
U = 'tests/v1/unit/test_verification_units.py'
P = 'tests/v1/integration/test_provenance.py'
W = 'tests/v1/unit/test_verification_weakening.py'
R = 'tests/v1/unit/test_gaps_core_verification_reviewer.py'
MC = 'tests/v1/unit/test_verification_memory_check.py'
B = 'tests/v1/unit/test_verification_baseline.py'
RR = 'tests/v1/unit/test_review_rules.py'
RMD = 'tests/v1/integration/test_review_md.py'
IP = '[inprocess]'

MUTATIONS = [
    # ── evidence decides, never the exit code (§8.4) ──
    ('Z01', 'an execution exit 0 is taken as success: PASSED without checks', [(WRK,
     "        self._do(V.record, missions=self.missions, verification_id=vid, checks=checks)\n"
     "\n    def _verify_human(",
     "        self._do(V.record, missions=self.missions, verification_id=vid,\n"
     "                 checks=[{'name': 'exit', 'kind': 'command', 'result': 'pass'}])\n"
     "\n    def _verify_human(")],
     [J + '::test_V01_V14_exit_0_with_a_wrong_change_is_a_verification_failure' + IP]),
    ('Z02', 'a failing check does not fail the verdict', [(VER,
     "    if 'fail' in results:\n        return 'FAILED'",
     "    if False:\n        return 'FAILED'")],
     [U + '::test_a_failing_check_fails_whatever_else_passed_or_errored',
      J + '::test_V11_passing_tests_and_no_change_is_contradictory_and_fails' + IP]),
    ('Z03', 'no outcome check is PASSED instead of AWAITING_HUMAN', [(VER,
     "    if not any(c['kind'] == 'command' for c in checks):\n        return 'ERROR'\n",
     ""), (WRK,
     "        if not (auto and revision is not None and t.kind in evidence.CODE_KINDS and cmds):",
     "        if not (auto and revision is not None and t.kind in evidence.CODE_KINDS):")],
     [J + '::test_V03_nothing_to_run_waits_for_your_acceptance' + IP]),
    # ── bound to its lineage (§11, §20) ──
    ('Z04', 'stale mission verifications count', [(CMD,
     "            if (v.entity.subject == Ref('mission', m.id)\n"
     "                    and v.entity.revision == m.integration_head):",
     "            if (v.entity.subject == Ref('mission', m.id)):")],
     [I + '::test_V04_a_mission_branch_moved_after_its_criteria_were_verified_is_verified_again']),
    ('Z05', 'the record accepts an execution of another task', [(VER,
     "    if e is None or e.id != execution_id:",
     "    if e is None:")],
     [I + '::test_V10_evidence_of_another_task_or_execution_is_refused']),
    ('Z06', "the record accepts a superseded plan's task", [(VER,
     "    if not _in_force(tx, t):\n        raise Refused(",
     "    if False:\n        raise Refused(")],
     [I + '::test_a_verification_whose_plan_is_superseded_while_it_runs_cannot_be_recorded']),
    ('Z07', 'one automatic criterion skipped by the mission verification', [(GRD,
     "    pending = [c for c in auto if c.verification != 'PASSED']",
     "    pending = [c for c in auto[:1] if c.verification != 'PASSED']")],
     [U + '::test_every_automatic_criterion_must_pass_not_only_the_first']),
    # ── a verifier fault is not a verdict (§6, §16) ──
    ('Z08', 'ERROR treated as PASSED', [(VER,
     "    if 'error' in results:\n        return 'ERROR'",
     "    if 'error' in results:\n        return 'PASSED'")],
     [U + '::test_an_error_is_never_a_pass',
      I + '::test_V12_a_runner_that_cannot_run_is_an_error_retried_once_then_yours']),
    # a decided row cannot take a second verdict (PASSED/FAILED are terminal in
    # the machine, and `record`'s RUNNING check is a second layer); the way to a
    # second logical result is a new row for a task that already has its verdict
    ('Z09', 'a task that left VERIFYING with its verdict is verified again', [(VER,
     "    if t.state != 'VERIFYING':\n        raise Refused('task %s is %s, not VERIFYING'",
     "    if False:\n        raise Refused('task %s is %s, not VERIFYING'")],
     [I + '::test_V07_a_second_verdict_for_the_same_verification_is_refused']),
    ('Z10', 'verifier failure becomes task failure', [(VER,
     "    if v.subject.kind == 'task' and state != 'ERROR':",
     "    if v.subject.kind == 'task':"), (VER,
     "    if 'FAILED' in states_:\n        bad = next(x for x in mine if x.state == 'FAILED')",
     "    if 'FAILED' in states_ or 'ERROR' in states_:\n"
     "        bad = next(x for x in mine if x.state in ('FAILED', 'ERROR'))")],
     [I + '::test_V12_a_runner_that_cannot_run_is_an_error_retried_once_then_yours']),
    # ── review (§14) ──
    ('Z11', 'a REJECTED review completes the mission', [(VER,
     "    if verdict == 'accept':\n        out = missions.accept(",
     "    if verdict in ('accept', 'reject'):\n        out = missions.accept("), (GRD,
     "    if f.review == 'ACCEPTED':",
     "    if f.review in ('ACCEPTED', 'REJECTED'):")],
     [I + '::test_a_rejecting_review_does_not_complete_the_mission']),
    ('Z15', 'the review is marked independent without comparing resources', [(REV,
     "        if same_resource and not (model and em and model != em):",
     "        if False:")],
     [U + '::test_a_review_is_independent_only_of_another_resource_or_model']),
    # ── restart (§19) ──
    ('Z12', 'the boot sweep leaves RUNNING rows alone', [(VER,
     "        if r.entity.state != 'RUNNING':\n            continue\n"
     "        _fire(tx, entities.Verification, r.entity.id, 'verifier_crashed'",
     "        if True:\n            continue\n"
     "        _fire(tx, entities.Verification, r.entity.id, 'verifier_crashed'")],
     [I + '::test_V08_a_verification_running_when_core_died_is_re_observed']),
    # ── merge-back (§12) ──
    ('Z13', 'the merge uses the branch name instead of the verified SHA', [(WRK,
     "            outcome, got = self.node.git_merge(wt, revision, ",
     "            outcome, got = self.node.git_merge(wt, e.branch, ")],
     [I + '::test_a_commit_on_the_task_branch_after_verification_is_not_merged']),
    ('Z14', '`all_tasks_done` ignores integration', [(GRD,
     "    if unmerged:\n        return _r('all_tasks_done', False,",
     "    if False:\n        return _r('all_tasks_done', False,")],
     [I + '::test_a_commit_on_the_task_branch_after_verification_is_not_merged']),
    # ── provenance (§22) ──
    ('Z16', "`performed_by` taken from the stream's claim", [(VER,
     "        m, plan_id, who = _mission(tx, t.mission_id), t.plan_id, performed_by(tx.conn, e)",
     "        m, plan_id, who = _mission(tx, t.mission_id), t.plan_id, dict(\n"
     "            performed_by(tx.conn, e),\n"
     "            model=(provenance or {}).get('reported_model') or e.model)")],
     [P + '::test_M06_a_reported_model_other_than_the_routed_one_is_recorded_not_failed']),
    # ── the advisory test-weakening check (T-1067) ──
    ('Z17', 'a test moved to another file is reported as removed', [(EVD,
     "            if m and m.group('name') not in added_names:",
     "            if m:")],
     [W + '::test_a_removed_test_function_is_named_and_a_moved_one_is_not']),
    ('Z18', 'a file with as many assertions as before is reported', [(EVD,
     "        if net > 0:", "        if net >= 0:")],
     [W + '::test_assertions_removed_are_counted_net_per_file']),
    ('Z19', 'a skip marker that was already there is reported as added', [(EVD,
     "            if s['marker'].search(a) and a.strip() not in gone:",
     "            if s['marker'].search(a):")],
     [W + '::test_a_marker_that_was_already_there_is_not_added']),
    ('Z20', 'a lowered timeout is reported as raised', [(EVD,
     "if k in old and new[k] > old[k]]", "if k in old and new[k] != old[k]]")],
     [W + '::test_a_raised_timeout_or_threshold_is_a_finding_and_a_lowered_one_is_not']),
    ('Z21', 'the advisory check fails the verification', [(EVD,
     "    return {'name': WEAKENING, 'kind': 'git', 'result': 'pass',\n"
     "            'detail': '%d finding(s), advisory'",
     "    return {'name': WEAKENING, 'kind': 'git', 'result': 'fail',\n"
     "            'detail': '%d finding(s), advisory'")],
     [W + '::test_a_finding_is_a_passing_git_check_with_its_findings']),
    ('Z22', 'a deleted test file is also reported test by test', [(EVD,
     "            found.append('test file deleted: %s' % f['path'])\n            continue\n",
     "            found.append('test file deleted: %s' % f['path'])\n")],
     [W + '::test_a_deleted_test_file_is_one_finding_not_one_per_test']),
    ('Z23', 'the worker never records the advisory check', [(WRK,
     "            if advisory:\n                checks.append(advisory)\n", "")],
     [W + '::test_the_worker_records_the_check_after_changes_and_only_for_a_code_change']),
    ('Z24', 'a file that is not a test is read as one', [(EVD,
     "        if s is None:\n            continue\n        if f['deleted']:",
     "        s = s or _SHAPES['py']\n        if f['deleted']:"),
     (EVD, "in_hunk, keep = True, _shape_of(cur['path']) is not None",
      "in_hunk, keep = True, True")],
     [W + '::test_a_file_that_is_not_a_test_is_never_read']),
    ('Z25', 'the diff may run a configured diff program', [(LOC,
     "'--text', '--no-ext-diff', '--no-textconv', '--no-renames',",
     "'--text', '--no-renames',")],
     [W + '::test_git_diff_runs_no_configured_diff_or_textconv_program']),
    ('Z26', 'the review prompt lists every finding, uncapped', [(REV,
     "c.get('findings', ())[:20]]", "c.get('findings', ())]")],
     [R + '::test_the_weakening_findings_of_a_verification_are_listed_for_the_reviewer']),
    # ── memory: advisory, never a verdict (T-1096) ──
    ('Z27', 'the memory check recorded for a mission that changed nothing', [(WRK,
     "self.node.git_numstat(\n                root, m.integration_base, m.integration_head):",
     "not self.node.git_numstat(\n                root, m.integration_base, m.integration_head):")],
     [MC + '::test_no_changed_files_or_no_branch_records_no_memory_check',
      MC + '::test_a_mission_that_changed_files_and_cites_a_lesson_passes_the_memory_check']),
    ('Z50', 'a retried mission verification drops the memory check', [(WRK,
     "                                     v.verifier_version) + self._memory(m, root)",
     "                                     v.verifier_version)")],
     [MC + '::test_a_retried_mission_verification_records_the_memory_check_too']),
    ('Z51', 'an expired or unrelated relation counts as a lesson', [(EVD,
     "    n = sum(r.entity.valid_until is None for r in rows.where(\n"
     "        conn, entities.Relation, src_kind='knowledge_item', rel='learned_from',\n",
     "    n = sum(True for r in rows.where(\n        conn, entities.Relation,\n")],
     [MC + '::test_only_a_live_lesson_learned_from_the_mission_counts']),
    ('Z28', 'a missing memory row is a fail', [(EVD,
     "    return {'name': 'memory', 'kind': 'state', 'result': 'skip',",
     "    return {'name': 'memory', 'kind': 'state', 'result': 'fail',")],
     [MC + '::test_without_a_row_it_is_a_skip_with_a_detail_and_the_verdict_stays_passed']),
    ('Z29', 'the memory check passes with nothing cited', [(EVD,
     "    if n:\n        return {'name': 'memory'",
     "    if True:\n        return {'name': 'memory'")],
     [MC + '::test_memory_check_is_a_read_of_relations_to_the_mission']),
    ('Z30', "another mission's lesson counted for this one", [(EVD,
     "dst_kind='mission', dst_id=mission_id))",
     "dst_kind='mission'))")],
     [MC + '::test_without_a_row_it_is_a_skip_with_a_detail_and_the_verdict_stays_passed']),
    ('Z31', 'a skipped check weighed as an error', [(VER,
     "    results = [c['result'] for c in checks]\n    if 'fail' in results:",
     "    results = [c['result'] if c['result'] != 'skip' else 'error' for c in checks]\n"
     "    if 'fail' in results:")],
     [MC + '::test_a_memory_check_never_flips_the_verdict[skip]']),
    ('Z32', 'the review prompt leaves the memory check out', [(REV,
     "        if memory:\n",
     "        if False:\n")],
     [MC + '::test_the_review_prompt_says_the_memory_check_is_advisory']),
    ('Z33', 'a skipped check stops a replayed verification reading as passed', [(
     'archeus/core/application/replay.py',
     "c.get('result') in ('pass', 'skip')", "c.get('result') == 'pass'")],
     ['tests/v1/unit/test_gaps_core_application_replay.py'
      '::test_a_failed_check_or_an_unmet_criterion_never_reads_as_passed']),
    # ── the base-revision regression check: opt-in, advisory, bounded (T-1068) ──
    ('Z34', 'every failed test runs at the base without the opt-in', [(WRK,
     "        if base is None or root is None or not self.baseline & {m.id, m.project_id}:",
     "        if base is None or root is None:")],
     [B + '::test_without_the_opt_in_nothing_runs_at_the_base']),
    ('Z35', 'a test failing at the base too is taken as passed', [(EVD,
     "    out = dict(check, baseline=base)\n",
     "    out = dict(check, baseline=base, result='pass' if base['result'] == 'fail'\n"
     "               else check['result'])\n")],
     [B + '::test_a_test_failing_at_the_base_too_is_failing_at_base']),
    ('Z36', 'the labels are swapped', [(EVD,
     "BASE_LABELS = {'pass': 'regressed', 'fail': 'also fails in a clean base checkout'}",
     "BASE_LABELS = {'pass': 'also fails in a clean base checkout', 'fail': 'regressed'}")],
     [B + '::test_a_failed_check_names_what_its_command_did_at_the_base']),
    ('Z37', 'a kept base run of another base revision is reused', [(WRK,
     "                     for c in v.checks if (c.get('baseline') or {}).get('revision') == base\n",
     "                     for c in v.checks if c.get('baseline')\n")],
     [B + '::test_one_base_run_per_plan_base_and_command']),
    ('Z46', 'an errored base run is kept and never tried again', [(WRK,
     "                     and c['baseline'].get('result') != 'error'}",
     "                     }")],
     [B + '::test_an_errored_base_run_is_tried_again_and_a_failed_removal_is_logged']),
    ('Z47', 'a line separator in an added line read as a line break', [(EVD,
     "    for line in diff.split('\\n'):", "    for line in diff.splitlines():")],
     [W + '::test_a_line_separator_in_an_added_line_cannot_fake_a_header']),
    ('Z48', 'a minified line is read whatever its length', [(EVD,
     "                if len(line) <= _LINE_MAX:", "                if True:")],
     [W + '::test_a_very_long_line_is_not_read_and_a_non_test_file_keeps_no_hunks']),
    ('Z49', 'the diff follows the repository config: no prefix, renames', [(LOC,
     "'--no-renames',\n                                '--src-prefix=a/', '--dst-prefix=b/',",
     "\n                               ")],
     [W + '::test_repository_config_renames_and_unicode_paths_hide_nothing']),
    ('Z38', 'the base runs again for every row of the plan', [(WRK,
     "        todo = [x for x in mine if '%s: %s' % x not in known]",
     "        todo = mine")],
     [B + '::test_one_base_run_per_plan_base_and_command']),
    ('Z39', 'a passing test also runs at the base', [(WRK,
     "        failed = {c['name'] for c in checks if c['kind'] == 'command' and c['result'] == 'fail'}",
     "        failed = {c['name'] for c in checks if c['kind'] == 'command'}")],
     [B + '::test_a_passing_test_or_a_failing_build_costs_no_base_run']),
    ('Z40', 'a failing build also runs at the base', [(WRK,
     "        mine = [(k, c) for k, c in cmds if k == 'test' and '%s: %s' % (k, c) in failed]",
     "        mine = [(k, c) for k, c in cmds if '%s: %s' % (k, c) in failed]")],
     [B + '::test_a_passing_test_or_a_failing_build_costs_no_base_run']),
    ('Z41', 'the base checkout is left behind', [(WRK,
     "            finally:\n                if not self.node.drop_checkout(root, tree):",
     "            finally:\n                if False:")],
     [B + '::test_a_test_that_passed_at_the_base_and_fails_now_is_regressed_and_still_failed',
      B + '::test_a_base_that_cannot_be_checked_out_is_said_and_changes_nothing']),
    ('Z42', 'the base checkout launches git by its bare name', [(LOC,
     "        argv = [exe, '--no-replace-objects']",
     "        argv = ['git', '--no-replace-objects']")],
     [B + '::test_the_base_checkout_is_a_detached_tree_of_the_base_from_an_absolute_git']),
    ('Z44', "the base checkout runs the repository's hooks", [(LOC,
     "        for c in ('core.hooksPath=' + empty, 'core.fsmonitor=false', 'core.attributesFile=' + none,",
     "        for c in ('core.fsmonitor=false', 'core.attributesFile=' + none,")],
     [B + '::test_the_base_checkout_runs_no_hook_or_filter_of_the_repository']),
    ('Z45', "the base checkout runs a filter the repository's attributes select", [(LOC,
     "                   GIT_ATTR_SOURCE=EMPTY_TREE, GIT_TERMINAL_PROMPT='0',",
     "                   GIT_TERMINAL_PROMPT='0',")],
     [B + '::test_the_base_checkout_runs_no_hook_or_filter_of_the_repository']),
    ('Z43', "a mission criterion is not compared with the branch's base", [(WRK,
     "                                     m.integration_base, cmds, checks,",
     "                                     None, cmds, checks,")],
     [B + '::test_a_mission_criterion_is_compared_with_the_integration_base']),
    # ── T-1106: REVIEW.md and review lessons, for an opted-in project only ──
    ('Z52', 'REVIEW.md read at the mission head', [(WRK,
     "        review_md = (self.node.git_file(root, m.integration_base, reviewer.RULES_FILE)",
     "        review_md = (self.node.git_file(root, m.integration_head, reviewer.RULES_FILE)")],
     [RMD + '::test_an_opted_in_project_reviews_against_review_md_at_the_base']),
    ('Z53', 'the rules reach every review, opted in or not', [(WRK,
     "            ruled = reviewer.RULES_OPT_IN in optins.effective(conn, account_id=None,\n"
     "                                                               project_id=m.project_id)",
     "            ruled = True")],
     [RMD + '::test_without_the_opt_in_the_review_prompt_is_todays']),
    ('Z54', 'REVIEW.md uncapped', [(REV,
     "                data[:RULES_BYTES].decode('utf-8', 'ignore')]",
     "                data.decode('utf-8', 'ignore')]")],
     [RR + '::test_the_rules_section_is_capped_marked_and_redacted_and_empty_without_rules']),
    ('Z55', 'REVIEW.md not redacted', [(REV,
     "        data = scrub_text(redact(review_md), homes).encode('utf-8')",
     "        data = scrub_text(review_md, homes).encode('utf-8')")],
     [RR + '::test_the_rules_section_is_capped_marked_and_redacted_and_empty_without_rules']),
    ('Z56', 'a work lesson read as a review rule', [(REV,
     "               if r.entity.state == 'CONFIRMED' and r.entity.source_kind == 'review']",
     "               if r.entity.state == 'CONFIRMED']")],
     [RR + '::test_the_rules_section_carries_the_last_ten_review_lessons_cut']),
    ('Z57', 'every review lesson listed', [(REV,
     "            for k in lessons[-RULES_LESSONS:]]",
     "            for k in lessons]")],
     [RR + '::test_the_rules_section_carries_the_last_ten_review_lessons_cut']),
    ('Z58', 'git_file reads the worktree instead of the commit', [(LOC,
     "        return proc.git(['cat-file', 'blob', '%s:%s' % (rev, path)], root)",
     "        try:\n"
     "            with open(os.path.join(root, path), encoding='utf-8') as f:\n"
     "                return f.read()\n"
     "        except OSError:\n"
     "            return None")],
     [RR + '::test_review_md_is_read_from_the_commit_named_never_the_worktree']),
    # codex review of fx17/fx18 (fx19)
    ('Z70', 'a Git below the floor is run in the project', [(LOC,
     "                if not _at_floor(out):\n                    return None\n", "")],
     [B + '::test_a_git_below_the_floor_is_asked_its_version_and_nothing_else']),
    ('Z71', 'a file the repository calls binary is shown as a summary', [(LOC,
     "'--text', ", "")],
     [W + '::test_repository_config_that_calls_a_test_binary_hides_nothing']),
    ('Z72', 'a path is read only from the --- and +++ lines', [(EVD,
     "{'path': _path('--- ' + names[:len(names) // 2]), 'deleted': False,",
     "{'path': None, 'deleted': False,")],
     [W + '::test_a_deletion_git_shows_as_binary_is_still_a_deleted_test_file']),
    ('Z73', 'a changed test line too long to inspect is dropped in silence', [(EVD,
     "        if f['skipped']:\n", "        if False:\n")],
     [W + '::test_a_changed_test_line_too_long_to_read_is_said_never_dropped']),
    ('Z74', 'a checkout is dropped once its directory is gone, whatever Git still lists', [(LOC,
     "                       for line in r.stdout.splitlines() if line.startswith('worktree '))",
     "                       for line in ())")],
     [B + '::test_a_checkout_whose_registration_outlives_its_directory_is_not_dropped']),
    ('Z75', 'a list Git could not give counts as a dropped checkout', [(LOC,
     "        if r is None or r.returncode:\n            return False\n        at = ",
     "        if r is None or r.returncode:\n            return True\n        at = ")],
     [B + '::test_a_git_below_the_floor_is_asked_its_version_and_nothing_else']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
