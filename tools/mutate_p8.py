"""The P8 mutation suite (p8-design-gate §21.3): break each rule the plan engine
keeps, run the tests that guard it, and require them to fail.

    py tools/mutate_p8.py            every mutation
    py tools/mutate_p8.py M04 M12    only these

Each mutation replaces one exact snippet (which must occur once), runs its
tests, and restores the file whatever happens. A mutation the tests do not
catch ("survived") fails the run. It edits sources: run it with nothing else
running against the tree.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = 'tests/v1/integration/test_planning.py'
U = 'tests/v1/unit/test_planning_units.py'
SK = 'tests/v1/integration/test_skeleton.py'

MUTATIONS = [
    ('M01', 'execution started during P8', 'archeus/core/application/planning.py',
     "        _end(tx, actor, called, 'ok', plan_id=out['plan_id'])\n",
     "        for t in tx.where(entities.Task, plan_id=out['plan_id'] or ''):\n"
     "            lifecycle.fire(tx, entities.Task, t.entity.id, 'deps_satisfied', actor=actor,\n"
     "                           reason='x')\n"
     "        _end(tx, actor, called, 'ok', plan_id=out['plan_id'])\n",
     [I + '::test_i25_a_planning_round_starts_nothing', U]),
    ('M02', 'policy approval performed in P8', 'archeus/core/application/planning.py',
     "        _end(tx, actor, called, 'ok', plan_id=out['plan_id'])\n",
     "        if out['plan_id']:\n"
     "            lifecycle.fire(tx, entities.Plan, out['plan_id'], 'approved', actor=actor,\n"
     "                           reason='x')\n"
     "        _end(tx, actor, called, 'ok', plan_id=out['plan_id'])\n",
     [I + '::test_i01_a_simple_mission_becomes_one_proposed_plan_version', U]),
    ('M03', 'router invoked directly', 'archeus/core/planning/worker.py',
     "        c = self.calls.run(purpose='planner',",
     "        from .. import ports\n"
     "        ports.FixedCandidateRouter('fake').route(None, 0)\n"
     "        c = self.calls.run(purpose='planner',",
     [U + '::test_u06_e1_the_plan_engine_imports_no_later_phase_provider_or_process',
      U + '::test_u06_e2_e3_it_never_authorises_routes_executes_verifies_or_reviews']),
    ('M04', 'task graph cycle accepted', 'archeus/core/planning/validate.py',
     "        cycle = find_cycle(tasks)\n", "        cycle = None\n",
     [I + '::test_i04_a_cycle_is_rejected_retried_and_never_recorded', U]),
    ('M05', 'unknown world reference accepted', 'archeus/core/planning/planner.py',
     "    return f is not None and f['kind'] in WORLD\n", "    return True\n",
     [I + '::test_i08_an_unknown_handle_is_invalid_and_nothing_is_created_from_it', U]),
    ('M06a', 'inferred requirement recorded as explicit', 'archeus/core/planning/planner.py',
     "        'inputs': [{'handle': h, 'kind': f['kind'], 'origin': f['origin'], 'text': f['text']}",
     "        'inputs': [{'handle': h, 'kind': f['kind'], 'origin': 'explicit', 'text': f['text']}",
     [I + '::test_i11_explicit_and_inferred_stay_apart_and_the_mission_is_never_written']),
    ('M06b', 'planner writes the mission requirements', 'archeus/core/application/planning.py',
     "        _end(tx, actor, called, 'ok', plan_id=out['plan_id'])\n",
     "        extra = tuple({'text': a['text'], 'origin': 'explicit'}\n"
     "                      for a in proposal['spec'].get('assumptions') or ())\n"
     "        tx.update(entities.Mission, mission_id, {'requirements': m.requirements + extra},\n"
     "                  actor=actor)\n"
     "        _end(tx, actor, called, 'ok', plan_id=out['plan_id'])\n",
     [I + '::test_i11_explicit_and_inferred_stay_apart_and_the_mission_is_never_written']),
    ('M07a', 'stale package reused for the call', 'archeus/core/planning/worker.py',
     "            if pid is not None and planner.currency(conn, m, pid)[0]:\n",
     "            if pid is not None:\n",
     [I + '::test_i09_a_package_older_than_the_mission_is_replaced_before_the_call']),
    ('M07b', 'stale result recorded', 'archeus/core/application/planning.py',
     "    current, why = planner.currency(tx.conn, mission, package_id)\n"
     "    return '' if current else why\n",
     "    return ''\n",
     [I + '::test_i10_a_result_made_stale_during_the_call_is_discarded']),
    ('M08', 'duplicate version for one round', 'archeus/infra/db/migrations/0007_planning.sql',
     "CREATE UNIQUE INDEX plans_by_round ON plans (mission_id, round_seq);\n", "",
     [I + '::test_i18_a_round_is_planned_once_whatever_is_replayed']),
    ('M09', 'invalid model output accepted', 'archeus/core/planning/worker.py',
     "                           check=lambda p: planner.check(p, facts, criteria=m.success_criteria),",
     "                           check=lambda p: [],",
     [I + '::test_i04_a_cycle_is_rejected_retried_and_never_recorded',
      I + '::test_i08_an_unknown_handle_is_invalid_and_nothing_is_created_from_it']),
    ('M10', 'malformed dependency accepted', 'archeus/core/planning/validate.py',
     "            elif d not in known:\n", "            elif False:\n", [U]),
    ('M11', 'task without acceptance criteria accepted', 'archeus/core/planning/validate.py',
     "        elif not checks:\n", "        elif False:\n", [U]),
    ('M12', 'plan mutated after version creation', 'archeus/infra/db/writer.py',
     "    frozen = set(fields) & cls.frozen_fields()\n", "    frozen = set()\n",
     [I + '::test_i26_a_recorded_version_is_preserved_exactly']),
    ('M13', 'previous version not superseded', 'archeus/core/application/work.py',
     "        if prev is not None and prev.entity.state in ('PROPOSED', 'APPROVED'):\n",
     "        if False:\n",
     [I + '::test_i15_request_changes_revises_the_plan_into_a_new_version']),
    ('M14', 'replan budget judged after the call', 'archeus/core/planning/worker.py',
     "        if state == 'REPLANNING' and self._do(self.planning.work.replan_budget_spent,\n"
     "                                              mission_id=mission_id):\n",
     "        if False:\n",
     [I + '::test_i16_i17_a_failing_task_replans_until_the_budget_blocks_before_any_call']),
    ('M15', 'provider-terms gate bypassed', 'archeus/harnesses/fake.py',
     "    return type(adapter) is FakeCaller\n", "    return True\n",
     [I + '::test_i24_the_provider_terms_gate_holds_planning_until_the_user_answers']),
    ('M16', 'blocking question ignored', 'archeus/core/planning/planner.py',
     "    qs = [q for q in parsed.get('questions') or () if q['blocking']]\n",
     "    qs = []\n",
     [I + '::test_i06_an_ambiguous_requirement_is_asked_and_the_first_plan_waits_blocked']),
    ('M17', 'conflict not challenged', 'archeus/core/planning/planner.py',
     "    conflicts = list(parsed.get('conflicts') or ())\n", "    conflicts = []\n",
     [I + '::test_i13_a_plan_against_confirmed_knowledge_is_challenged']),
    ('M18', 'touches serialisation removed', 'archeus/core/planning/validate.py',
     "            if clash:\n", "            if False:\n",
     [I + '::test_i03_parallel_tasks_share_a_wave_and_overlapping_touches_are_serialised', U]),
    ('M19', 'cost band not computed by Core', 'archeus/core/application/work.py',
     "            summary=plan.get('summary', ''), estimated_cost=validate.cost_band(specs),\n",
     "            summary=plan.get('summary', ''), estimated_cost='low',\n",
     [I + '::test_i03_parallel_tasks_share_a_wave_and_overlapping_touches_are_serialised',
      SK + '::test_a_plan_over_the_cost_ceiling_needs_approval']),
    ('M20', 'digest not re-checked by the ready guard', 'archeus/core/domain/guards.py',
     "    if not plan.digest or plan.digest != f.digest:\n", "    if False:\n",
     [U + '::test_u05_ready_needs_no_problem_and_a_matching_digest']),
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
