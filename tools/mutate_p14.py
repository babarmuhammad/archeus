"""The P14 mutation suite (p14-design-gate §19): break each safety property of
the event bus and automation, run the tests that guard it, and require them to
fail.

    py tools/mutate_p14.py            every mutation
    py tools/mutate_p14.py A04 A13    only these

Same runner as tools/mutate_p11.py: each mutation replaces exact snippets
(each must occur once), runs its tests, and restores the files whatever
happens; a mutation the tests do not catch ("survived") fails the run. It
edits sources: run it with nothing else running against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p11  # noqa: E402  (one runner)

APP = 'archeus/core/application/automations.py'
MAT = 'archeus/core/automation/matcher.py'
WRK = 'archeus/core/automation/worker.py'
CON = 'archeus/infra/eventlog/consumers.py'
I = 'tests/v1/integration/test_automation.py'
U = 'tests/v1/unit/test_automation_units.py'

MUTATIONS = [
    # ── delivery and idempotency (§5) ──
    ('A01', 'a re-delivered event claims a second run', [(APP,
     "        if tx.execute('SELECT 1 FROM automation_runs WHERE automation_id = ? AND '\n"
     "                      'triggering_event_seq = ?', (a.id, e.seq)).fetchone():",
     "        if False:")],
     [I + '::test_E02_a_duplicate_delivery_has_one_effect',
      I + '::test_E20_concurrent_deliveries_of_one_event_claim_one_run']),
    # ── loops (§10) ──
    ('A02', 'causal depth ignored', [(APP,
     "    if e.subject.kind == 'automation_run':\n"
     "        row = rows.get(conn, entities.AutomationRun, e.subject.id)",
     "    return 0\n"
     "    if e.subject.kind == 'automation_run':\n"
     "        row = rows.get(conn, entities.AutomationRun, e.subject.id)")],
     [I + '::test_E16_a_self_triggering_automation_escalates_at_depth_three_then_suspends']),
    ('A03', 'depth exceeded is dropped silently, not escalated', [(APP,
     "        end('depth_exceeded', 'depth_exceeded',",
     "        return run.id\n        end('depth_exceeded', 'depth_exceeded',")],
     [I + '::test_E16_a_self_triggering_automation_escalates_at_depth_three_then_suspends']),
    ('A13', 'the rate limit is off', [(APP,
     "    if made >= a.rate_limit:",
     "    if False:")],
     [I + '::test_the_rate_limit_skips_and_three_rate_limited_runs_suspend']),
    ('A14', 'the loop guard never suspends', [(MAT,
     "    return (sum(s == 'ESCALATED' for s, _ in recent) >= SUSPEND_AFTER",
     "    return False and (sum(s == 'ESCALATED' for s, _ in recent) >= SUSPEND_AFTER")],
     [I + '::test_E16_a_self_triggering_automation_escalates_at_depth_three_then_suspends',
      U + '::test_three_escalations_or_three_rate_limits_suspend_and_fewer_do_not']),
    ('A19', 'an automation may react to automation events', [(MAT,
     "    if t.startswith(FORBIDDEN_PREFIXES):",
     "    if False:")],
     [I + '::test_D13_only_a_user_device_with_admin_writes_or_enables_an_automation']),
    # ── what fires (§7, §9, §13) ──
    ('A04', 'a disabled or archived automation fires', [(APP,
     "            if r.entity.state == 'ENABLED']",
     "            if r.entity.state != 'DRAFT']")],
     [I + '::test_E05_a_disabled_or_archived_automation_does_not_fire']),
    ('A05', "the envelope's scope is trusted over the mission's", [(APP,
     "    m = mission_of(conn, e.subject)\n    return (m.workspace_id, m.project_id) if m else",
     "    m = None\n    return (m.workspace_id, m.project_id) if m else")],
     [I + '::test_E23_a_projects_event_never_fires_another_projects_automation']),
    ('A06', 'enabling replays what happened before', [(APP,
     "        if e.seq <= a.armed_seq:\n            continue",
     "        pass")],
     [I + '::test_X1_enabling_never_replays_what_happened_before']),
    ('A07', 'a stale state event asks for work', [(APP,
     "    old = stale(tx.conn, e)\n    if old:",
     "    old = stale(tx.conn, e)\n    if False:")],
     [I + '::test_E22_a_stale_state_event_does_not_ask_for_work']),
    ('A08', 'an event caused by an execution asks for work', [(APP,
     "    if e.actor.kind == 'execution':",
     "    if False:")],
     [I + '::test_X2_an_event_caused_by_an_execution_asks_for_nothing']),
    ('A09', 'the e-stop is ignored', [(APP,
     "    if authorization.estop_armed():",
     "    if False:")],
     [I + '::test_X4_while_disarmed_every_run_is_denied_and_the_automation_stays_enabled']),
    ('A15', 'a template may carry anything', [(MAT,
     "    extra = set(template) - set(TEMPLATE_KEYS)\n    if extra:",
     "    extra = set(template) - set(TEMPLATE_KEYS)\n    if False:")],
     [I + '::test_E11_E14_a_template_asks_for_a_mission_and_nothing_else',
      U + '::test_a_template_is_a_mission_request_and_nothing_else']),
    ('A16', 'a non-admin writes an automation', [(APP,
     "    `admin` only: an automation, a brain or an execution cannot write one.\"\"\"\n"
     "    authorization._principal(tx, actor, 'admin')",
     "    `admin` only: an automation, a brain or an execution cannot write one.\"\"\"")],
     [I + '::test_D13_only_a_user_device_with_admin_writes_or_enables_an_automation']),
    ('A20', 'a non-admin enables an automation', [(APP,
     "    re-arms it at the current head: it never fires for an earlier event (D12).\"\"\"\n"
     "    authorization._principal(tx, actor, 'admin')",
     "    re-arms it at the current head: it never fires for an earlier event (D12).\"\"\"")],
     [I + '::test_D13_only_a_user_device_with_admin_writes_or_enables_an_automation']),
    # ── outcome and provenance (§8, §15) ──
    ('A17', 'a run settles on any move of its mission', [(APP,
     "    return e.type == 'mission.state_changed' and e.payload.get('to') in SETTLES",
     "    return e.type == 'mission.state_changed'"), (APP,
     "    trigger, code = SETTLES[e.payload['to']]",
     "    trigger, code = SETTLES.get(e.payload['to'], SETTLES['COMPLETED'])")],
     [I + '::test_E07_E08_automated_work_meets_the_plan_gate_and_cannot_approve_itself']),
    ('A18', "the mission loses its cause", [(APP,
     "                                origin='automation', origin_ref=run.id, cause=chain)",
     "                                origin='automation', origin_ref=run.id, cause=())")],
     [I + '::test_E09_E10_E15_E25_automated_work_is_routed_executed_verified_and_explained']),
    # ── faults (§6, §11) ──
    ('A10', 'a failed reaction is not held: the event is passed over', [(WRK,
     "            log.warning('automation: event %d failed (attempt %d), held: %s', e.seq, attempts, x)\n"
     "            raise consumers.Hold",
     "            return 'failed'")],
     [I + '::test_E17_a_failed_reaction_is_held_and_retried',
      I + '::test_E21_a_held_event_blocks_the_ones_after_it']),
    ('A11', 'a failing reaction is retried forever', [(WRK,
     "            if attempts >= MAX_ATTEMPTS:",
     "            if False:")],
     [I + '::test_E18_a_reaction_that_keeps_failing_is_quarantined_not_retried_forever']),
    ('A12', 'a quarantine is swallowed silently', [(WRK,
     "                return 'quarantined: %s: %s' % (type(x).__name__, x)",
     "                return ''")],
     [I + '::test_E18_a_reaction_that_keeps_failing_is_quarantined_not_retried_forever']),
    ('A21', 'a held event is overtaken by the ones after it', [(CON,
     "            except Hold:\n                return n",
     "            except Hold:\n                continue")],
     [I + '::test_E21_a_held_event_blocks_the_ones_after_it']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
