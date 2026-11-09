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
CMD = 'archeus/core/application/commands.py'
GRD = 'archeus/core/domain/guards.py'
J = 'tests/v1/judge/test_v01_outcome_verification.py'
I = 'tests/v1/integration/test_verification.py'
U = 'tests/v1/unit/test_verification_units.py'
P = 'tests/v1/integration/test_provenance.py'
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
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
