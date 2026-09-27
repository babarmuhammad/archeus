"""The P12 mutation suite (p12-design-gate §22): break each invariant session
and context continuity keeps, run the tests that guard it, and require them to
fail.

    py tools/mutate_p12.py            every mutation
    py tools/mutate_p12.py Y05 Y12    only these

Same runner as tools/mutate_p11.py: each mutation replaces exact snippets
(each must occur once), runs its tests, and restores the files whatever
happens; a mutation the tests do not catch ("survived") fails the run. It
edits sources: run it with nothing else running against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mutate_p11 import _apply, ROOT, TIMEOUT_S  # noqa: E402,F401  (one runner)
import mutate_p11  # noqa: E402

SES = 'archeus/core/application/sessions.py'
CON = 'archeus/core/sessions/continuity.py'
REN = 'archeus/core/sessions/render.py'
SVC = 'archeus/core/sessions/service.py'
HAR = 'archeus/harnesses/sessions.py'
EX = 'archeus/core/application/executions.py'
HO = 'archeus/core/execution/handoff.py'
MGR = 'archeus/core/execution/manager.py'
T = 'tests/v1/integration/test_sessions.py'
I = 'tests/v1/integration/test_execution.py'
B = 'tests/v1/unit/test_session_boundaries.py'
C1 = 'tests/v1/judge/test_c01_resume_continuity.py'
S4 = 'tests/v1/judge/test_s04_limit_and_fallback.py'

MUTATIONS = [
    # ── current state wins (D9) ──
    ('Y01', 'resume reads the checkpoint\'s state instead of the rows', [(CON,
     "            tasks.append({'id': t.id, 'key': t.key, 'title': t.title, 'state': t.state,",
     "            tasks.append({'id': t.id, 'key': t.key, 'title': t.title, 'state': next((\n"
     "                x.split(': ')[-1] for c in rows.where(conn, entities.Checkpoint, task_id=t.id)\n"
     "                for x in c.entity.completed_steps if x.startswith(t.key + ' ')), t.state),")],
     [C1 + '::test_C13_current_state_wins_over_what_a_checkpoint_recorded']),
    ('Y02', 'a cached package reused without the freshness check', [(CON,
     "                and context.fresh(tx.conn, prow.entity):",
     "                and True:")],
     [T + '::test_T15_a_fresh_package_is_reused_and_a_stale_one_rebuilt']),
    ('Y17', 'the brief read from the owner\'s cursor, not the session\'s', [(CON,
     "    changes = digest(conn, since=session.last_seen_seq, project_id=session.project_id,",
     "    changes = digest(conn, since=0, project_id=session.project_id,")],
     [T + '::test_T17_the_brief_shows_only_what_changed_after_the_session_s_own_cursor']),
    ('Y18', 'the package a session was given not recorded on it', [(SES,
     "        'last_seen_seq': head, 'context_package_id': ctx['package_id'],",
     "        'last_seen_seq': head,")],
     [T + '::test_T15_a_fresh_package_is_reused_and_a_stale_one_rebuilt']),
    # ── who may act, and where (§17) ──
    ('Y03', 'a non-user actor changes a session', [(SES,
     "def _user(actor):\n    if actor.kind != 'user_device':",
     "def _user(actor):\n    if False:")],
     [T + '::test_T02_only_a_user_device_changes_a_session']),
    ('Y04', 'a session linked to a mission of another scope', [(SES,
     "    if m.workspace_id != workspace_id or m.project_id != project_id:",
     "    if False:")],
     [T + '::test_T04_a_session_continues_only_a_mission_of_its_own_scope']),
    # ── hand-off (§10.2, D10, D11) ──
    ('Y05', 'the target loses its lineage', [(SES,
     "        handoff_from_session_id=src.id, handoff_request=request_id, handoff_artifact_sha=sha,",
     "        handoff_from_session_id=None, handoff_request=request_id, handoff_artifact_sha=sha,")],
     [T + '::test_T20_a_handoff_is_a_new_linked_session_and_the_source_is_untouched']),
    ('Y06', 'the hand-off writes its source', [(SES,
     "    sha = artifacts.put(text.encode('utf-8'))\n    t = entities.Session(",
     "    sha = artifacts.put(text.encode('utf-8'))\n"
     "    tx.update(entities.Session, src.id, {'last_active_at': _now()}, actor=actor)\n"
     "    t = entities.Session(")],
     [T + '::test_T20_a_handoff_is_a_new_linked_session_and_the_source_is_untouched']),
    ('Y07', 'the target inherits the source\'s provider session', [(SES,
     "        project_id=src.project_id, mission_id=src.mission_id, model=model, effort=effort,",
     "        project_id=src.project_id, mission_id=src.mission_id, model=model, effort=effort,\n"
     "        provider_session_ref=src.provider_session_ref,")],
     [T + '::test_T21_the_target_gets_the_rendered_artifact_and_none_of_the_source_s_own_state']),
    ('Y08', 'a rendering not redacted', [(REN,
     "def _cap(text, cap, keep='head'):\n    text = redact(text)",
     "def _cap(text, cap, keep='head'):\n    text = text")],
     [T + '::test_T21_the_target_gets_the_rendered_artifact_and_none_of_the_source_s_own_state']),
    ('Y09', 'a duplicate resume request moves the cursor again', [(SES,
     "    if s.last_request == request_id:",
     "    if False:")],
     [T + '::test_T11_the_same_resume_request_twice_changes_nothing']),
    ('Y10', 'a duplicate hand-off request makes a second target', [(SES,
     "    if got:\n        return dict(view_of(got[0].entity), duplicate=True)",
     "    if False:\n        return dict(view_of(got[0].entity), duplicate=True)")],
     [T + '::test_T22_the_same_handoff_request_makes_one_target']),
    ('Y23', 'a model the target harness does not offer passed to it', [(SES,
     "    model = _vocabulary(model, models, 'model', harness_id) or (",
     "    model = model or (")],
     [T + '::test_T23_an_unknown_model_is_refused_and_an_inherited_one_dropped']),
    ('Y24', 'a transcript artifact includes tool output', [(HAR,
     "                if obj.get('role') in ('user', 'assistant') and obj.get('text'):",
     "                if obj.get('text'):")],
     [T + '::test_T21_the_target_gets_the_rendered_artifact_and_none_of_the_source_s_own_state']),
    # ── model switch, interruption, restart ──
    ('Y16', 'a model switch drops the mission link', [(SES,
     "        'last_active_at': _now(), 'model': model, 'effort': effort,",
     "        'last_active_at': _now(), 'model': model, 'effort': effort, 'mission_id': None,")],
     [T + '::test_T12_a_model_switch_keeps_the_session_and_its_mission']),
    ('Y15', 'an interrupted session moves its mission', [(SES,
     "    s = lifecycle.load(tx, entities.Session, session_id).entity\n"
     "    return view_of(_fire(tx, s, 'vanished', actor, reason))",
     "    s = lifecycle.load(tx, entities.Session, session_id).entity\n"
     "    if s.mission_id:\n"
     "        lifecycle.fire(tx, entities.Mission, s.mission_id, 'block', actor=actor, reason='x')\n"
     "    return view_of(_fire(tx, s, 'vanished', actor, reason))")],
     [T + '::test_T32_the_sweep_marks_a_vanished_provider_session_lost']),
    ('Y19', 'a pending launch replayed at boot', [(SVC,
     "        expired = self._do(S.expire_launches, self.system)['expired']",
     "        with self.db.read() as r:\n"
     "            expired = [x.entity.id for x in rows.where(r, entities.Session)\n"
     "                       if x.entity.launch_seq > x.entity.launched_seq]\n"
     "        for sid in expired:\n"
     "            self._launch(sid)")],
     [T + '::test_T30_a_restarted_core_expires_pending_launches_and_opens_nothing']),
    # ── execution hand-off (§10.1) ──
    ('Y11', 'the continuation skips P9', [(HO,
     "            auth = authorization.check_dispatch(tx, actor=actor, policy=policy,\n"
     "                                                missions=missions, mission=m, plan=plan, task=t)",
     "            auth = {'outcome': 'covered', 'policy_decision_id': e.policy_decision_id}")],
     [I + '::test_E80_a_continuation_meets_the_policy_as_it_is_now']),
    ('Y12', 'the continuation ignores P10\'s refusal', [(HO,
     "        if result not in ('selected', 'fallback'):",
     "        if False:")],
     [I + '::test_E81_a_continuation_goes_only_where_the_router_sends_it']),
    ('Y13', 'a hand-off charged an attempt', [(EX,
     "              {'exit_reason': 'handoff', 'exit_code': exit_code, 'charged': False,",
     "              {'exit_reason': 'handoff', 'exit_code': exit_code, 'charged': True,")],
     [I + '::test_E79_pressure_hands_off_and_the_task_continues_where_it_was']),
    ('Y14', 'a hand-off moves its task', [(HO,
     "    rd = route.id if route.decided_by == 'router' else None\n",
     "    lifecycle.fire(tx, entities.Task, t.id, 'execution_failed_retry', actor=actor,\n"
     "                   reason='moved')\n"
     "    rd = route.id if route.decided_by == 'router' else None\n")],
     [I + '::test_E79_pressure_hands_off_and_the_task_continues_where_it_was']),
    ('Y20', 'an ended execution derives no checkpoint', [(EX,
     "    if checkpoint.ran(e):\n        checkpoint.derive(",
     "    if False:\n        checkpoint.derive(")],
     [C1 + '::test_C13_current_state_wins_over_what_a_checkpoint_recorded']),
    ('Y21', 'pressure ignored', [(MGR,
     "        if (p['pressure'] or 0.0) < PRESSURE_HANDOFF or p.get('handing_off'):",
     "        if True:")],
     [I + '::test_E79_pressure_hands_off_and_the_task_continues_where_it_was']),
    ('Y22', 'a limit seen at the exit leaves the account as it was', [(MGR,
     "            self._do(X.account_limited, account_id=e.account_id)\n"
     "            self._do(X.request_handoff, execution_id=e.id, stop_reason='limit',",
     "            self._do(X.request_handoff, execution_id=e.id, stop_reason='limit',")],
     [S4 + '::test_crossing_the_ceiling_mid_run_halts_at_the_boundary_and_hands_off']),
    ('Y25', 'a hook request answered on a stale reading of the stream', [(MGR,
     "        if pending:\n            # what the agent wrote before it asked",
     "        if False:\n            # what the agent wrote before it asked")],
     [I + '::test_E82_output_written_before_a_tool_call_is_read_before_the_call_is_answered']),
]


if __name__ == '__main__':
    mutate_p11.MUTATIONS = MUTATIONS
    sys.exit(mutate_p11.run(sys.argv[1:]))
