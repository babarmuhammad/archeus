"""The P19 mutation suite (p19-design-gate B13): break each gate's invariant,
run the test written for it, and require it to fail. B1, one edge
implementation (P01-P08); B2, the change rule on the Relations list and the
TUI (P09-P14); B11, the generated client everywhere (P15-P20); B3, a mission's own
conversation and the mission Now tab (P21-P30); B5, chat approve / reject
is the card's decision (P31-P40); B6, mission confirmation under `careful`
(P41-P50); B10a, `emergency stop`, `stop <running mission>` and the
explanation card (P51-P62); B10b, resource directives (P63-P74); B4, plan edit (P75-P89);
B9, the application theme (P90-P100); B7, the offline snapshot (P101-P110); B8, the
desktop shell, its tray and the legacy "Open Archeus V1" (P111-P133); B12, the
unification scenario (P134-P137); the R13 correction pass (P138-P146); the R13
follow-up of rulebook §46.4, S-3 (P147-P149), S-2 (P150-P153) and S-1 (P154-P158).

    py tools/mutate_p19.py            every mutation
    py tools/mutate_p19.py P01 P09    only these

The runner is tools/mutate_p18.py's (tools/mutate_p11.py's snippet engine:
each snippet occurs once, the guarding tests pass on the unmutated tree first,
files are restored whatever happens; a browser-guarded mutant rebuilds the
SPA). It edits sources: run it with nothing else running against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402  (its runner)

REL = 'clients/app/src/graph/relations.ts'
RELS = 'clients/app/src/components/Relations.tsx'
PRES = 'archeus/cli/tui/present.py'
SCR = 'archeus/cli/tui/screens.py'
REL_TS = 'node:test/relations.test.ts'
PARITY_TS = 'node:test/parity.test.ts'
PARITY_PY = 'tests/v1/tui/test_parity.py'
TUI_REL = 'tests/v1/tui/test_acceptance.py::test_relations_say_the_tier_and_the_field_in_words'
THREAD = 'tests/v1/tui/test_thread.py::'
ROWS = 'tests/v1/e2e/test_spa_rows.py::test_the_change_rule_marks_exactly_what_changed_on_every_list'
GATE = 'tests/v1/design/test_design_gates.py::test_no_client_assembles_an_edge'
DG = 'tests/v1/design/test_design_gates.py::'
PYAPI = 'archeus/cli/_api.py'
MAIN = 'archeus/cli/main.py'
PYCLIENT = 'tests/v1/unit/test_api_client.py'
G3 = 'tests/v1/judge/test_g03_one_model.py::test_every_client_agrees'
CONV = 'archeus/core/application/conversation.py'
QRY = 'archeus/core/application/queries.py'
GRAM = 'archeus/core/application/grammar.py'
INTENT = 'archeus/core/missions/intent.py'
MISSION = 'clients/app/src/surfaces/Mission.tsx'
NOW = 'clients/app/src/surfaces/Now.tsx'
THR = 'tests/v1/integration/test_mission_thread.py::'
THREAD_E2E = ('tests/v1/e2e/test_spa_mission_thread.py::'
              'test_the_mission_now_tab_is_its_thread_and_a_reply_reaches_a_row_there')
SPA_APPROVE = ('tests/v1/e2e/test_spa_mission_thread.py::'
               'test_an_approval_card_in_the_thread_decides_it_as_attention_does')
CA = 'tests/v1/integration/test_chat_approve.py::'
AUTHZ = 'archeus/core/application/authorization.py'
ROUTES = 'archeus/api/routes.py'
TUI_CA = 'tests/v1/tui/test_chat_approval.py::'
RULES = 'archeus/core/policy/rules.py'
ENGINE = 'archeus/core/engine.py'
PORTS = 'archeus/core/ports.py'
SC_ = 'tests/v1/integration/test_start_confirmation.py::'
CV = 'tests/v1/integration/test_chat_verbs.py::'
TUI_CV = 'tests/v1/tui/test_chat_verbs.py::'
DIR = 'tests/v1/integration/test_directives.py::'
ROUTER = 'archeus/core/routing/router.py'
RES = 'archeus/core/application/resources.py'
WORK = 'archeus/core/application/work.py'
VALIDATE = 'archeus/core/planning/validate.py'
PE = 'tests/v1/integration/test_plan_edit.py::'
PLAN_E2E = 'tests/v1/e2e/test_spa_plan_edit.py::test_the_plan_awaiting_approval_is_edited_on_its_tab'
TOK_CSS = 'clients/app/src/styles/tokens.css'
APP_CSS = 'clients/app/src/styles/app.css'
BOOT = 'clients/app/src/state/appearance.js'
INDEX = 'clients/app/index.html'
CONTROL = 'clients/app/src/surfaces/Control.tsx'
AP = 'tests/v1/e2e/test_spa_appearance.py::'
AP_CHOICE = AP + 'test_appearance_is_this_clients_choice_over_the_systems'
AP_FORCED = AP + 'test_forced_colours_override_any_choice'
AP_FIRST = AP + 'test_the_choice_is_on_html_before_the_stylesheet_and_survives_an_offline_start'
SNAP = 'clients/app/src/data/snapshot.ts'
APP_TSX = 'clients/app/src/App.tsx'
TRANSPORT = 'clients/app/src/api/transport.ts'
NOW_TSX = 'clients/app/src/surfaces/Now.tsx'
SNAP_TS = 'node:test/snapshot.test.ts'
OS = 'tests/v1/e2e/test_spa_offline_snapshot.py::'
OS_COLD = OS + 'test_an_offline_cold_start_shows_the_last_now_read_only'
OS_REVOKE = OS + 'test_revoking_this_client_clears_its_snapshot'
OS_OBSERVE = OS + 'test_a_client_paired_observe_only_keeps_nothing'
OS_NAMED = OS + 'test_offline_needs_you_names_what_waits_and_sits_in_the_app_frame'
CHANGE_E2E = ('tests/v1/e2e/test_spa_mission_thread.py::'
              'test_a_change_card_is_confirmed_through_the_existing_admin_route')
STOP_E2E = ('tests/v1/e2e/test_spa_mission_thread.py::'
            'test_the_stop_and_emergency_stop_cards_confirm_what_the_words_only_asked')
CLI_STATUS = ('tests/v1/integration/test_cli_v1.py::'
              'test_status_of_a_mission_prints_what_core_reports_and_a_refusal_in_its_words')

GUI = 'archeus/cli/gui.py'
QT = 'claude_sessions/gui_qt.py'
GAPI = 'claude_sessions/gui_api.py'
SH = 'tests/v1/integration/test_gui_shell.py::'
SH_CRED = SH + 'test_the_shells_credential_is_observe_and_control_named_desktop_shell_in_memory'
QT_RUN = ('tests/v1/e2e/test_gui_qt.py::'
          'test_the_window_keeps_its_profile_across_a_restart_and_the_tray_acts')
ATT = 'clients/app/src/surfaces/Attention.tsx'
VERIF = 'archeus/core/application/verification.py'
UNIFY = ('tests/v1/e2e/test_unification.py::'
         'test_create_on_desktop_observe_and_approve_on_mobile_execute_review_inspect')

GV = 'clients/app/src/graph/GraphView.tsx'
NOW_HDR = 'tests/v1/tui/test_now_header.py'
NOW_MAP = ('tests/v1/e2e/test_spa_now.py::'
           'test_the_live_map_holds_live_work_only_and_opens_the_full_graph')
S1 = 'tests/v1/e2e/test_spa_p16.py::test_nothing_scrolls_sideways_at_any_width'

MUTATIONS = [
    # ── B1: the clients say Core's edges, from where they stand ──
    ('P01', "the SPA's list shows containment", [(REL,
     '    if (e.structural) continue;\n', '')],
     [REL_TS, PARITY_TS]),
    ('P02', "the SPA's list says an edge from the wrong end", [(REL,
     'rel: edgeWords(e.field, holder, e.rel as string | null)',
     'rel: edgeWords(e.field, !holder, e.rel as string | null)')],
     [REL_TS, PARITY_TS]),
    ('P03', "the SPA's list points a reverse edge at the object itself", [(REL,
     'to: holder ? e.to : e.from,', 'to: e.to,')],
     [REL_TS, PARITY_TS]),
    ('P04', "the SPA's list shows a superseded neighbour as current", [(REL,
     '    if (e.inactive) row.inactive = true;\n', '')],
     [REL_TS, PARITY_TS]),
    ('P05', "the SPA's list reads two hops", [(REL,
     'depth: 1, limit: 1000', 'depth: 2, limit: 1000')],
     [REL_TS]),
    ('P06', "the TUI's list shows containment", [(PRES,
     "        if e.get('structural'):\n            continue\n", '')],
     [PARITY_PY]),
    ('P07', "the TUI's list says an edge from the wrong end", [(PRES,
     "edge_words(e['field'], holder, e.get('rel'))", "edge_words(e['field'], not holder, e.get('rel'))")],
     [PARITY_PY]),
    ('P08', 'a client assembles an edge again', [(SCR,
     "    edges = P.edge_rows(g['edges'], {'kind': kind, 'id': id_})\n",
     "    edges = P.edge_rows(g['edges'], {'kind': kind, 'id': id_}) + [\n"
     "        {'rel': 'continues', 'to': {'kind': 'mission', 'id': id_}, 'field': 'Execution.handoff_from'}]\n")],
     [GATE]),
    # ── B2: the thread's rule on the Relations list and every TUI row ──
    ('P09', "the SPA's Relations rows never carry the rule", [(RELS,
     '{...thread(changed(e.to.kind, e.to.id))}', '{...thread(false)}')],
     [ROWS]),
    ('P10', "the SPA's Relations rows never say it in words", [(RELS,
     '<Changed on={changed(e.to.kind, e.to.id)} />', '<Changed on={false} />')],
     [ROWS]),
    ('P11', 'the TUI marks no row', [(SCR,
     "                and (target[1], target[2]) in self.changed()):",
     "                and (target[1], target[2]) in set()):")],
     [THREAD + 'test_a_changed_row_carries_the_rule_and_no_other_row_does',
      THREAD + 'test_the_relations_view_rules_the_neighbour_the_digest_names']),
    ('P12', 'the TUI marks every row', [(SCR,
     "                and (target[1], target[2]) in self.changed()):",
     "                and (target[1], target[2]) is not None):")],
     [THREAD + 'test_a_changed_row_carries_the_rule_and_no_other_row_does',
      THREAD + 'test_an_acknowledged_digest_leaves_no_rule']),
    ('P13', "the TUI's rule is the cursor's glyph", [(SCR,
     "            text = self.st.paint('│', 'thread') + text[1:]",
     "            text = self.st.paint('›', 'thread') + text[1:]")],
     [THREAD + 'test_a_changed_row_carries_the_rule_and_no_other_row_does']),
    ('P14', "the TUI's rule moves the row", [(SCR,
     "            text = self.st.paint('│', 'thread') + text[1:]",
     "            text = self.st.paint('│', 'thread') + text")],
     [THREAD + 'test_a_changed_row_carries_the_rule_and_no_other_row_does']),
    # ── B11: the generated client everywhere ──
    ('P15', 'the SPA spells a path again', [('clients/app/src/surfaces/CommandBar.tsx',
     "p.startsWith(paths.listMessages('primary'))", "p.startsWith('/v1/conversations/')")],
     [DG + 'test_the_spa_reads_every_path_from_the_generated_client']),
    ('P16', 'the TUI spells a path again', [(SCR,
     "    g = doc.load(endpoints.digest(), 'the digest')",
     "    g = doc.load('/v1/digest', 'the digest')")],
     [DG + 'test_the_cli_and_the_tui_read_every_path_from_the_generated_client']),
    ('P17', 'the Python client puts an id in a path unencoded', [(PYAPI,
     "    return head + quote(id_, safe='') + tail if _ else r_path",
     "    return head + id_ + tail if _ else r_path")],
     [PYCLIENT]),
    ('P18', 'the Python client sends an absent query value', [(PYAPI,
     "    q = [(k, v) for k, v in pairs if v is not None]",
     "    q = [(k, v) for k, v in pairs]")],
     [PYCLIENT]),
    ('P19', "the CLI says a state Core did not report", [(MAIN,
     "    print('%s: %s (%s)' % (m['id'], m['state'], m['title']))",
     "    print('%s: %s (%s)' % (m['id'], 'COMPLETED', m['title']))")],
     [G3, CLI_STATUS]),
    ('P20', "the CLI drops Core's refusal", [(MAIN,
     "        print(sync.explain(e.refusal()), file=sys.stderr)\n", "")],
     [CLI_STATUS]),
    # ── B3: a mission's own conversation and the mission Now tab ──
    ('P21', 'a mission gets a new thread for every turn', [(CONV,
     "    got = tx.where(entities.Conversation, mission_id=mission_id)\n    if got:\n",
     "    got = tx.where(entities.Conversation, mission_id=mission_id)\n    if False:\n")],
     [THR + 'test_a_missions_id_names_its_one_thread_made_on_first_use']),
    ('P22', "a turn sent to a mission's thread lands in the primary conversation", [(CONV,
     "        conversation_id = thread(tx, actor, conversation_id)\n",
     "        conversation_id = primary(tx, actor)\n")],
     [THR + 'test_a_missions_id_names_its_one_thread_made_on_first_use']),
    ('P23', 'the thread leaves out the primary messages that link its mission', [(QRY,
     "                if any((x.get('ref') or {}).get('id') == mission_id for x in r.entity.links or ())]",
     "                if False]")],
     [THR + 'test_the_thread_shows_the_primary_messages_that_link_its_mission_in_order']),
    ('P24', 'the thread shows every primary message', [(QRY,
     "                if any((x.get('ref') or {}).get('id') == mission_id for x in r.entity.links or ())]",
     "                if True]")],
     [THR + 'test_the_thread_shows_the_primary_messages_that_link_its_mission_in_order']),
    ('P25', "a bare mission verb in a thread is not about its mission", [(GRAM,
     "        if m is None and mission and not p.arg:\n            m = rows.get(conn, entities.Mission, mission).entity\n", "")],
     [THR + 'test_a_bare_mission_verb_in_a_thread_is_about_its_mission_and_answered_there']),
    ('P26', "the intent worker forgets which thread a turn is in", [(INTENT,
     "grammar.resolve(conn, msg.text, mission=conv.mission_id,", "grammar.resolve(conn, msg.text, mission=None,")],
     [THR + 'test_a_bare_mission_verb_in_a_thread_is_about_its_mission_and_answered_there']),
    ('P27', "the mission's Now tab shows the primary conversation", [(MISSION,
     '<Conversation conversation={mission.id} scope=".mission-now"',
     '<Conversation conversation={mission.id && \'primary\'} scope=".mission-now"')],
     [THREAD_E2E]),
    ('P28', "the thread's line goes to the message's own card", [(NOW,
     "    if (e.closest('.conversation')) return false; // a message's own card is not a row\n", '')],
     [THREAD_E2E]),
    ('P29', "the tab's composer posts to the primary conversation", [(NOW,
     "run={(key) => api.postMessage(send(), conversation, { text, idempotency_key: key })}",
     "run={(key) => api.postMessage(send(), 'primary', { text, idempotency_key: key })}")],
     [THREAD_E2E]),
    ('P30', "the TUI's thread posts to the primary conversation", [(SCR,
     "            lambda key, v: app.core.post(endpoints.post_message(cid),",
     "            lambda key, v: app.core.post(endpoints.post_message('primary'),")],
     ['tests/v1/tui/test_mission_thread.py::test_its_message_command_posts_to_the_thread']),
    # ── B5: chat approve / reject is the card's decision ──
    ('P31', 'an approval is never said in the conversation', [(AUTHZ,
     "    approval_card(tx, actor, a, mission)\n", "")],
     [CA + 'test_an_approval_is_a_card_in_the_conversation_and_in_its_missions_thread']),
    ('P32', "the approval card does not link its mission, so its thread lacks it", [(CONV,
     "             links=[{'ref': {'kind': 'mission', 'id': mission.id}},\n"
     "                    {'ref': {'kind': 'approval', 'id': approval.id}}])\n\n\ndef decide_by_message",
     "             links=[{'ref': {'kind': 'approval', 'id': approval.id}}])\n\n\ndef decide_by_message")],
     [CA + 'test_an_approval_is_a_card_in_the_conversation_and_in_its_missions_thread']),
    ('P33', 'a chat decision needs no approve scope', [(ROUTES,
     "    if 'approve' not in req.principal['scopes']:\n"
     "        raise Refused(403, 'scope_required', {'scope': 'approve'})\n"
     "    try:\n        out = req.run(req.api.authorization.decide_by_message",
     "    try:\n        out = req.run(req.api.authorization.decide_by_message")],
     [CA + 'test_a_wrong_hash_a_missing_scope_or_another_word_writes_nothing']),
    ('P34', "a chat decision ignores the hash the user saw", [(CONV,
     "decision=p.verb,\n                 action_hash=action_hash,",
     "decision=p.verb,\n                 action_hash=tx.get(entities.Approval, approval_id).entity.action_hash,")],
     [CA + 'test_a_wrong_hash_a_missing_scope_or_another_word_writes_nothing']),
    ('P35', "a chat decision drops the step-up proof", [(CONV,
     "                 action_hash=action_hash, step_up=step_up,",
     "                 action_hash=action_hash, step_up=None,")],
     ['tests/v1/integration/test_presence.py::test_P19_B5_a_chat_approve_needs_the_same_step_up_as_the_card']),
    ('P36', 'a bare approve does not point at the card', [(CONV,
     "            for a in pending[:10]:", "            for a in pending[:0]:")],
     [CA + 'test_a_bare_approve_decides_nothing_and_points_at_the_card']),
    ('P37', "the SPA's card sends a bare word", [(NOW,
     "{ text: 'approve', decision, idempotency_key: key }",
     "{ text: 'approve', idempotency_key: key }")],
     [SPA_APPROVE]),
    ('P38', "the SPA's card decides in the primary conversation", [(NOW,
     "api.postMessage(send(), conversation, { text: 'approve', decision,",
     "api.postMessage(send(), 'primary', { text: 'approve', decision,")],
     [SPA_APPROVE]),
    ('P39', "the TUI's card sends a bare word", [(SCR,
     "            'text': text, 'decision': {'approval_id': aid, 'action_hash': a['action_hash'],\n"
     "                                       'expected_version': a['version']},\n",
     "            'text': text,\n")],
     [TUI_CA + 'test_approve_posts_the_turn_with_the_cards_hash_and_version_to_the_thread']),
    ('P40', "the TUI offers a PIN step-up it cannot take", [(SCR,
     "PIN, which Attention asks for.' if capability == 'pin'",
     "PIN, which Attention asks for.' if capability == 'pinned'")],
     [TUI_CA + 'test_a_pin_step_up_is_given_in_attention_not_here']),
    # ── B6: mission confirmation under `careful` ──
    ('P41', '`careful` allows a mission to start', [(RULES,
     "    'careful': _profile({}),", "    'careful': _profile({'mission.start': ('ALLOW', None)}),")],
     [SC_ + 'test_under_careful_the_mission_waits_in_created_for_its_start_approval']),
    ('P42', 'the engine fires START without asking P9', [(ENGINE,
     "            got = self._do(authorization.gate_start, policy=self.missions.policy,\n"
     "                           missions=self.missions, mission_id=m.id)\n",
     "            got = self._do(self.missions.fire, mission_id=m.id, trigger=START,\n"
     "                           reason='Archeus starts on the mission') or {'started': True}\n")],
     [SC_ + 'test_under_careful_the_mission_waits_in_created_for_its_start_approval']),
    ('P43', 'a waiting start asks again on every pass', [(AUTHZ,
     "    if live_approval(tx.conn, h) is None:\n        d = record(tx, actor=actor, stage='start',",
     "    if True:\n        d = record(tx, actor=actor, stage='start',")],
     [SC_ + 'test_under_careful_the_mission_waits_in_created_for_its_start_approval']),
    ('P44', 'approving a start does not start the mission', [(AUTHZ,
     "    elif a.kind == 'start':\n        out = missions.fire(",
     "    elif a.kind == 'never':\n        out = missions.fire(")],
     [SC_ + 'test_a_start_is_approved_from_the_conversation_card']),
    ('P45', 'rejecting a start does not cancel the mission', [(AUTHZ,
     "    if kind == 'start':\n        out = missions.cancel(",
     "    if kind == 'never':\n        out = missions.cancel(")],
     [SC_ + 'test_under_careful_rejecting_the_start_cancels_the_mission']),
    ('P46', 'a start approval is judged eligible like a plan approval', [(AUTHZ,
     "    if a.kind == 'start':\n        return None if mission.state == 'CREATED' else (\n"
     "            'not_awaiting', 'mission %s is %s' % (mission.id, mission.state))\n", "")],
     [SC_ + 'test_under_careful_the_mission_waits_in_created_for_its_start_approval']),
    ('P47', 'the e-stop holds a start', [(AUTHZ,
     "    ctx = dict(context(conn, mission, stage='start', now=now, actor=actor), estop=False)",
     "    ctx = context(conn, mission, stage='start', now=now, actor=actor)")],
     [SC_ + 'test_the_estop_does_not_hold_a_start_and_careful_still_asks']),
    ('P48', "a user's DENY rule asks instead of holding", [(AUTHZ,
     "    if decision == 'DENY':\n        return {'started': False, 'waiting': 'policy_denied'}\n",
     "")],
     [SC_ + 'test_a_users_deny_rule_holds_the_mission_without_asking']),
    ('P49', 'the stub policy holds every mission at its start', [(PORTS,
     "'ALLOW' if action.action_class\n                              in CORE_CLASSES else self.decision",
     "self.decision")],
     ['tests/v1/integration/test_planning_http.py::'
      'test_h01_the_mission_view_carries_the_plan_in_force_and_health_the_worker']),
    ('P50', "the TUI's matrix keeps its own copy of the classes", [(SCR,
     "    classes = list(p['profiles'][names[0]])\n",
     "    classes = [c for c in p['profiles'][names[0]] if c != 'mission.start']\n")],
     ['tests/v1/tui/test_acceptance.py::test_the_autonomy_matrix_lists_every_class_core_judges']),
    # ── B10a: `emergency stop`, `stop <running mission>`, the explanation card ──
    ('P51', '`emergency stop` is read from any words that begin with it', [(GRAM,
     "        return Control('estop', None, '') if key(p.arg) == 'stop' else None",
     "        return Control('estop', None, '')")],
     [CV + 'test_the_grammar_reads_emergency_stop_and_stop_by_the_missions_state']),
    ('P52', '`emergency stop` answers with no card to confirm it', [(CONV,
     "            cards.append(_card('estop', 'workspace', ids.GLOBAL_WORKSPACE))\n", "")],
     [CV + 'test_emergency_stop_asks_and_its_card_is_the_strips_command']),
    ('P53', '`stop` on a running mission is a plain cancel', [(GRAM,
     "            verb = 'stop_running' if m.state == 'EXECUTING' else 'cancel'",
     "            verb = 'cancel'")],
     [CV + 'test_stop_on_a_running_mission_asks_then_pauses_and_cancels_it_in_one_turn']),
    ('P54', 'the confirmed stop does not pause first', [(CONV,
     "        if m.state == 'EXECUTING':\n            self.missions.pause(",
     "        if False:\n            self.missions.pause(")],
     [CV + 'test_stop_on_a_running_mission_asks_then_pauses_and_cancels_it_in_one_turn']),
    ('P55', 'a confirmation may name any message', [(CONV,
     "        if row is None or row.entity.author != 'archeus' or not stop:",
     "        if row is None:")],
     [CV + 'test_a_confirmation_must_name_a_stop_card_and_say_stop']),
    ('P56', 'a confirmation need not say stop', [(CONV,
     "        if p is None or p.verb != 'stop':\n            raise ValueError('a message confirming",
     "        if p is None:\n            raise ValueError('a message confirming")],
     [CV + 'test_a_confirmation_must_name_a_stop_card_and_say_stop']),
    ('P57', '`why` attaches no route_explanation card', [(CONV,
     "                cards.append(_card('route_explanation', 'route_decision', rd))\n", "")],
     [CV + 'test_why_attaches_the_route_explanation_card_equal_to_the_record']),
    ('P58', "the explanation's words diverge from the record", [(CONV,
     "    return got[-1].explanation, got[-1].id",
     "    return 'Routing: ' + got[-1].explanation, got[-1].id")],
     [CV + 'test_why_attaches_the_route_explanation_card_equal_to_the_record']),
    ('P59', "the TUI's stop card confirms the mission, not its own card", [(SCR,
     "'confirm': {'message_id': m['id']}}),", "'confirm': {'message_id': id_}}),")],
     [TUI_CV + 'test_the_stop_card_posts_the_confirming_turn_naming_its_own_message']),
    ('P60', "the TUI's emergency-stop card runs another command", [(SCR,
     "                                         lambda key, v: app.core.post(endpoints.estop(),",
     "                                         lambda key, v: app.core.post(endpoints.rearm(),")],
     [TUI_CV + 'test_the_estop_card_runs_the_strips_command_and_says_when_it_is_engaged']),
    ('P61', "the SPA's stop card confirms the mission, not its own card", [(NOW,
     "{ text: 'stop', confirm: { message_id: message }, idempotency_key: key }",
     "{ text: 'stop', confirm: { message_id: message && id }, idempotency_key: key }")],
     [STOP_E2E]),
    ('P62', "the SPA's emergency-stop card runs another command", [(NOW,
     "run={(key) => api.estop(send(), { idempotency_key: key })} reread={['/v1']} />\n        </div>\n      )}\n    </article>\n  );\n}\n\n/** `stop` on",
     "run={(key) => api.rearm(send(), { idempotency_key: key })} reread={['/v1']} />\n        </div>\n      )}\n    </article>\n  );\n}\n\n/** `stop` on")],
     [STOP_E2E]),
    # ── B10b: resource directives (ADR-0042 §2-§4; G3, G4, G14) ──
    ('P63', "`don't use` narrows nothing", [(CONV,
     "            lists[fk].append(ref['id'])\n            applied.append((fk, ref))\n",
     "            applied.append((fk, ref))\n")],
     [DIR + 'test_dont_use_narrows_the_named_mission_with_its_message_and_intent']),
    ('P64', 'a directive drops its source message', [(CONV,
     "            {'key': k, 'id': r['id'], 'message_id': msg.id, 'intent_id': intent.id}",
     "            {'key': k, 'id': r['id'], 'message_id': None, 'intent_id': intent.id}")],
     [DIR + 'test_dont_use_narrows_the_named_mission_with_its_message_and_intent',
      DIR + 'test_the_brains_directive_lands_on_the_mission_it_creates']),
    ('P65', 'a protected account is preferred without a confirmation', [(CONV,
     "        if ref['id'] in lists[fk] or _consumption(tx, ref) in PROTECTED:",
     "        if ref['id'] in lists[fk]:")],
     [DIR + 'test_use_prefers_a_normal_account_and_proposes_a_protected_one']),
    ('P66', 'lifting a forbid applies at once', [(CONV,
     "        if ref['id'] in lists[fk] or _consumption(tx, ref) in PROTECTED:",
     "        if _consumption(tx, ref) in PROTECTED:")],
     [DIR + 'test_lifting_a_forbid_is_widening_and_only_proposed']),
    ('P67', 'a name that resolves to nothing is guessed', [(GRAM,
     "for h in sorted(harnesses) if key(h) == n]\n    return _one(got)",
     "for h in sorted(harnesses) if key(h) == n]\n    return _one(got) or next(\n"
     "        ({'kind': 'account', 'id': r.entity.id} for r in rows.where(conn, entities.Account)),"
     " None)")],
     [DIR + 'test_the_grammar_reads_use_and_dont_use_and_leaves_what_it_cannot_resolve',
      DIR + 'test_an_unresolved_name_from_the_brain_is_a_clarification_and_writes_nothing']),
    ('P68', "an ambiguous `don't use` changes the global policy", [(CONV,
     "                cards.append(_standing_card(tx, ref))\n"
     "                text += ' To make it standing, confirm it on the card.'",
     "                tx.update(entities.ResourcePolicy, tx.where(entities.ResourcePolicy, "
     "account_id=ref['id'])[0].entity.id, {'consumption': 'explicit_only'}, actor=actor)\n"
     "                cards.append(_standing_card(tx, ref))\n"
     "                text += ' To make it standing, confirm it on the card.'")],
     [DIR + 'test_an_ambiguous_dont_use_is_the_missions_and_offers_standing_without_applying_it']),
    ('P69', "a message that is not a user device's carries a directive", [(CONV,
     "    if p is None or p.entity.kind != 'user_device':\n        return ('Only a message",
     "    if p is None:\n        return ('Only a message")],
     [DIR + 'test_only_a_user_devices_message_carries_a_directive']),
    ('P70', 'a preference a conversation added lifts a protected account', [(ROUTER,
     "        (_ids(req.get('preferred'), 'accounts') - _ids(req.get('conversational'), 'accounts'))",
     "        _ids(req.get('preferred'), 'accounts')")],
     [DIR + 'test_a_conversational_preference_lifts_no_protected_account',
      DIR + 'test_a_preference_a_conversation_added_never_routes_to_an_explicit_only_account']),
    ('P71', "the router is not told which preferences a conversation added", [(RES,
     "           'conversational': {'accounts': [d['id'] for d in rp.get('directives') or ()\n"
     "                                           if d['key'] == 'preferred_accounts']},",
     "           'conversational': {'accounts': []},")],
     [DIR + 'test_a_preference_a_conversation_added_never_routes_to_an_explicit_only_account']),
    ('P72', 'a standing directive is applied to the mission instead', [(CONV,
     "        if d is not None and (d['scope'] == 'standing'\n"
     "                              or kind not in ('new_work', 'continue_work')):",
     "        if d is not None and kind not in ('new_work', 'continue_work', 'preference'):")],
     [DIR + 'test_never_is_a_standing_change_card_and_changes_no_policy']),
    ('P73', "the TUI's change card sends its own body, not Core's", [(SCR,
     "                                                   dict(cmd['body'], idempotency_key=key)),\n"
     "                      reread=reread + [endpoints.get_mission(cmd['id'])]",
     "                                                   dict(idempotency_key=key)),\n"
     "                      reread=reread + [endpoints.get_mission(cmd['id'])]")],
     [TUI_CV + 'test_a_change_card_runs_the_existing_admin_route_with_cores_own_body']),
    ('P74', "the SPA's change card sends its own body, not Core's", [(NOW,
     "api.setMissionResources(send(), card.command.id, { ...body, idempotency_key: key })",
     "api.setMissionResources(send(), card.command.id, { idempotency_key: key, preferred_accounts: [] })")],
     [CHANGE_E2E]),
    # ── B4: plan edit (P19 S2) ──
    ('P75', 'a version that is not the plan in force is edited', [(WORK,
     "        if prev.state != 'PROPOSED' or active_plan(tx.conn, prev.mission_id).entity.id != prev.id:",
     "        if False:")],
     [PE + 'test_a_replay_is_one_edit_and_a_stale_or_replaced_version_is_refused']),
    ('P76', "an edit skips the validator's 422", [(WORK,
     "        if found:                   # what the version's `ready` guard would refuse",
     "        if False:")],
     [PE + 'test_the_validator_refuses_with_a_422_and_nothing_is_written']),
    ('P77', "an edit is not judged on the requirements the plan must serve", [(WORK,
     "        explicit = planner.explicit_handles(prev.inputs)",
     "        explicit = []")],
     [PE + 'test_the_validator_refuses_with_a_422_and_nothing_is_written']),
    ('P78', "Core's serialisation edges are adopted as the person's", [(WORK,
     "                                     if (t.get('key'), d) not in added]) for t in tasks]",
     "                                     if True]) for t in tasks]")],
     [PE + 'test_cores_serialisation_edges_are_derived_again_not_adopted']),
    ('P79', 'the tasks keep their labels instead of Core keying them in order', [(WORK,
     "        key = {t['key']: 't%d' % i for i, t in enumerate(specs, 1)}",
     "        key = {t['key']: t['key'] for t in specs}")],
     [PE + 'test_an_edit_is_the_persons_next_version_and_asks_again']),
    ('P80', 'the edited version does not name its author', [(WORK,
     "            tx, actor=actor, mission_id=prev.mission_id, explicit=explicit, edited_by=who.id,",
     "            tx, actor=actor, mission_id=prev.mission_id, explicit=explicit, edited_by=None,")],
     [PE + 'test_an_edit_is_the_persons_next_version_and_asks_again']),
    ('P81', "the edited version loses the lists of the one it replaces", [(WORK,
     "            plan=dict({k: getattr(prev, k) for k in _PLAN_LISTS + ('summary', 'rollback')},",
     "            plan=dict({},")],
     [PE + 'test_an_edit_is_the_persons_next_version_and_asks_again']),
    ('P82', "the edited version's coverage is the replaced version's", [(WORK,
     "                      tasks=specs, coverage=planner.coverage(prev.inputs, specs)))",
     "                      tasks=specs, coverage=prev.coverage))")],
     [PE + 'test_an_edit_is_the_persons_next_version_and_asks_again']),
    ('P83', 'the mission is not sent back before the edit is proposed', [(WORK,
     "        self.missions.request_changes(tx, actor=actor, mission_id=prev.mission_id,\n"
     "                                      reason='plan v%d edited by %s' % (prev.plan_version, who.id))\n",
     "")],
     [PE + 'test_an_edit_is_the_persons_next_version_and_asks_again']),
    ('P84', "a stale `expected_version` is not refused", [(WORK,
     "        if expected_version is not None and expected_version != row.version:\n"
     "            raise lifecycle.VersionConflict(plan_id, expected_version, row.version)\n"
     "        prev = row.entity",
     "        prev = row.entity")],
     [PE + 'test_a_replay_is_one_edit_and_a_stale_or_replaced_version_is_refused']),
    ('P85', 'a plan edit needs only the control scope', [(ROUTES,
     "    Route('POST', '/v1/plans/{id}/edit', edit_plan, 'approve', 'required', schemas.EDIT_PLAN,",
     "    Route('POST', '/v1/plans/{id}/edit', edit_plan, 'control', 'required', schemas.EDIT_PLAN,")],
     [PE + 'test_only_the_approve_scope_and_only_while_the_plan_awaits_approval']),
    ('P86', "a planner's version hashes differently than it was stored", [(VALIDATE,
     "    body = {'plan': {k: v for k, v in plan.to_dict().items() if k not in _PLAN_SKIP\n"
     "                     and not (k == 'edited_by' and v is None)},",
     "    body = {'plan': {k: v for k, v in plan.to_dict().items() if k not in _PLAN_SKIP},")],
     ['tests/v1/unit/test_planning_units.py::'
      'test_a_planners_version_keeps_the_digest_it_was_stored_with']),
    ('P87', 'the SPA sends the tasks in another order than shown', [(MISSION,
     "api.editPlan(send(), p.id, { tasks: rows, expected_version: p.version, idempotency_key: key })",
     "api.editPlan(send(), p.id, { tasks: [...rows].reverse(), expected_version: p.version, "
     "idempotency_key: key })")],
     [PLAN_E2E]),
    ('P88', 'the SPA offers the editor whatever the plan and the mission', [(MISSION,
     "{p.in_force && p.state === 'PROPOSED' && offers('mission', mission.state, 'request_changes') ? ",
     "{true ? ")],
     [PLAN_E2E]),
    ('P89', "the TUI does not say a version is a person's", [(SCR,
     "    if p.get('edited_by'):                  # P19 S2: the TUI shows an edit, never makes one",
     "    if False:")],
     ['tests/v1/tui/test_plan_edit.py::test_the_persons_version_is_shown_as_such']),
    ('P90', 'an explicit light theme is not applied', [(TOK_CSS,
     ":root[data-theme='light'] {\n  color-scheme: light;",
     ":root[data-theme='lite'] {\n  color-scheme: light;")],
     [AP_CHOICE]),
    ('P91', "the OS's light scheme wins over an explicit dark", [(TOK_CSS,
     "@media (prefers-color-scheme: light) {\n  :root:not([data-theme='dark']) {",
     "@media (prefers-color-scheme: light) {\n  :root {")],
     [AP_CHOICE]),
    ('P92', "an explicit standard contrast does not hold off the OS's", [(TOK_CSS,
     "@media (prefers-contrast: more) {\n  :root:not([data-contrast='standard']) {",
     "@media (prefers-contrast: more) {\n  :root {")],
     [AP_CHOICE]),
    ('P93', 'an explicit high contrast is not applied', [(TOK_CSS,
     ":root[data-contrast='high'] {", ":root[data-contrast='higher'] {")],
     [AP_CHOICE]),
    ('P94', 'a theme stops a forced colour', [(TOK_CSS,
     ":root[data-theme='light'] {\n  color-scheme: light;",
     ":root[data-theme='light'] {\n  forced-color-adjust: none;\n  color-scheme: light;")],
     [AP_FORCED]),
    ('P95', 'the high-contrast rule outranks the forced-colours block', [(APP_CSS,
     ":where(html[data-contrast='high']) .thread-line {",
     "html[data-contrast='high'] .thread-line {")],
     [AP_FORCED]),
    ('P96', 'any stored name is a theme, a palette too', [(BOOT,
     "Object.prototype.hasOwnProperty.call(BG, p.theme) ? p.theme : 'system'",
     "p.theme ? p.theme : 'system'")],
     [AP_CHOICE]),
    ('P97', 'the choice is kept for this tab only', [(BOOT,
     "    if (next) localStorage.setItem(KEY, JSON.stringify(next));\n"
     "    p = JSON.parse(localStorage.getItem(KEY));",
     "    if (next) sessionStorage.setItem(KEY, JSON.stringify(next));\n"
     "    p = JSON.parse(sessionStorage.getItem(KEY));")],
     [AP_CHOICE]),
    ('P98', 'the theme colour stays dark whatever is chosen', [(BOOT,
     "m.setAttribute('content', BG[theme === 'system' ? os : theme]);",
     "m.setAttribute('content', BG.dark);")],
     [AP_CHOICE]),
    ('P99', 'the boot waits for the page like a module', [(INDEX,
     '<script src="/src/state/appearance.js"></script>',
     '<script defer src="/src/state/appearance.js"></script>')],
     [DG + 'test_t6_the_appearance_boot_runs_before_the_stylesheet', AP_FIRST]),
    ('P100', "the TUI names a theme that is not the terminal's", [(SCR,
     "    doc.add('  ' + app.st.paint(app.st.theme.capitalize(), 'text', True)",
     "    doc.add('  ' + app.st.paint('Dark', 'text', True)")],
     ['tests/v1/tui/test_appearance.py::test_the_terminal_names_its_own_theme_and_motion']),
    ('P101', 'every read is kept, not only the Now composition', [(SNAP,
     "  if (!NOW_READS.includes(path)) return;\n", "")],
     [OS_COLD]),
    ('P102', 'an ended mission is kept', [(SNAP,
     "missions.filter((m) => !ENDED.includes(m.state)) } : data;",
     "missions.filter((m) => !ENDED.includes(m.state) || true) } : data;")],
     [SNAP_TS, OS_NAMED]),
    ('P103', 'a client paired observe-only keeps a snapshot', [(SNAP,
     "!(c.origin === 'paired' && c.scopes.every((s) => s === 'observe'));",
     "!(c.origin === 'paired' && c.scopes.every((s) => s === 'nothing'));")],
     [SNAP_TS, OS_OBSERVE]),
    ('P104', 'a snapshot is as new as its newest read', [(SNAP,
     "kept.map((k) => k.at).sort()[0];", "kept.map((k) => k.at).sort().reverse()[0];")],
     [SNAP_TS]),
    ('P105', 'a cold start with no Core shows no snapshot', [(APP_TSX,
     "const kept = e instanceof CoreError && e.status === 0 ? await loadSnapshot() : null;",
     "const kept = e instanceof CoreError && e.status === 401 ? await loadSnapshot() : null;")],
     [OS_COLD]),
    ('P106', 'a client revoked while away keeps its snapshot', [(TRANSPORT,
     "      await clearToken();\n      await clearSnapshot();", "      await clearToken();\n      void clearSnapshot;")],
     [OS_REVOKE]),
    ('P107', 'a client revoked while open keeps its snapshot', [(APP_TSX,
     "    if (ended) return void clearSnapshot();", "    if (ended) return void clearSnapshot;")],
     [OS_REVOKE]),
    ('P108', 'the offline Now links a mission', [(NOW_TSX,
     "<StateBadge machine=\"mission\" state={m.state} /> <span className=\"title\">{m.title}</span>\n"
     "                </li>\n              ))}\n            </ul>\n          ) : (\n            <Empty>Nothing was in progress.</Empty>",
     "<StateBadge machine=\"mission\" state={m.state} /> <a href=\"#/now\" className=\"title\">{m.title}</a>\n"
     "                </li>\n              ))}\n            </ul>\n          ) : (\n            <Empty>Nothing was in progress.</Empty>")],
     [OS_COLD]),
    ('P109', 'what was read before the client was known is never kept', [(APP_TSX,
     "      if (s.data !== undefined) k(path, s.data, s.seq);", "      void s;")],
     [OS + 'test_what_was_read_before_the_client_was_known_is_kept']),
    ('P110', 'the snapshot is not keyed by the Core origin', [(SNAP,
     "s.put(k, `${k.origin} ${path}`)", "s.put(k, path)")],
     [OS_COLD]),
    ('P111', "the shell's credential may approve", [(GUI,
     "SHELL_SCOPES = ['observe', 'control']", "SHELL_SCOPES = ['observe', 'control', 'approve']")],
     [SH_CRED]),
    ('P112', "the shell's device row is not named", [(GUI,
     "{'code': code, 'platform': 'desktop', 'name': SHELL_NAME}",
     "{'code': code, 'platform': 'desktop'}")],
     [SH_CRED]),
    ('P113', 'Core ignores the name a redeem gives', [(ROUTES,
     "'name': (req.body.get('name') or '').strip() or 'browser (%s)' % req.body['platform'],",
     "'name': 'browser (%s)' % req.body['platform'],")],
     [SH_CRED]),
    ('P114', "the shell's credential is written to disk", [(GUI,
     "    return client.Core(info['port'], out['token'])",
     "    return open(discovery.core_json_path() + '.shell', 'w').write(out['token']) and "
     "client.Core(info['port'], out['token'])")],
     [SH_CRED]),
    ('P115', "the shell acts with the CLI's own admin token", [(GUI,
     "    return client.Core(info['port'], out['token'])", "    return client.Core(info['port'], token)")],
     [SH_CRED]),
    ('P116', "the window's page gets less than the local grant", [(MAIN,
     "{'scopes': ['observe', 'control', 'approve', 'admin']})", "{'scopes': ['observe']})")],
     [SH + 'test_the_page_opens_on_a_launch_code_with_the_full_local_grant']),
    ('P117', 'a running Core is started again', [(GUI,
     "    if state == 'not_running':\n        err = start()",
     "    if state != 'unreadable':\n        err = start()")],
     [SH + 'test_a_running_core_is_attached_and_never_started_again']),
    ('P118', 'a Core that is starting is not waited for', [(GUI,
     "    while state != 'running' and time.monotonic() < deadline:", "    while False:")],
     [SH + 'test_with_no_core_the_shell_starts_it_once_and_waits_for_it']),
    ('P119', 'the started Core has no console for its executions', [(GUI,
     "proc.spawn_detached(argv, hidden_console=True, log=start_log())",
     "proc.spawn_detached(argv, hidden_console=False, log=start_log())")],
     [SH + 'test_the_start_runs_archeus_core_in_the_background']),
    ('P120', 'Pause all reaches another route', [(GUI,
     "out = self._own.post(endpoints.pause_all(),", "out = self._own.post(endpoints.resume_all(),")],
     [SH + 'test_pause_all_pauses_what_runs_with_the_shells_credential']),
    ('P121', 'Pause all with Core down reads as a refusal', [(GUI,
     "return NOT_RUNNING if e.status == 0 else", "return NOT_RUNNING if e.status == -1 else")],
     [SH + 'test_with_core_down_pause_all_says_so']),
    ('P122', "the tray's e-stop starts Core", [(GUI,
     "        code = main.estop()", "        code = start_core() or main.estop()")],
     [SH + 'test_emergency_stop_with_core_down_never_starts_it']),
    ('P123', "the tray's e-stop is not archeus estop's code", [(GUI,
     "        code = main.estop()", "        code = main.pause('all')")],
     [SH + 'test_emergency_stop_is_archeus_estops_code']),
    ('P124', 'the Attention count is not Core\'s', [(GUI,
     "return self._own.get(endpoints.attention_items())[0]['count']",
     "return self._own.get(endpoints.attention_items())[0]['count'] * 0")],
     [SH + 'test_the_attention_count_is_cores', QT_RUN]),
    ('P125', 'the profile is outside the Qt shell\'s own entry', [(GUI,
     "os.path.join(paths.archeus_home(), 'QtWebEngine', 'archeus')",
     "os.path.join(paths.archeus_home(), 'profile')")],
     [SH + 'test_the_profile_lives_in_the_qt_shells_own_entry']),
    ('P126', 'the window keeps nothing across a restart', [(QT,
     "    profile = QWebEngineProfile('archeus', app)", "    profile = QWebEngineProfile(app)")],
     [QT_RUN]),
    ('P127', 'the window paints dark before the page, whatever the OS', [(QT,
     "page.setBackgroundColor(QColor(shell.preload_bg(dark)))",
     "page.setBackgroundColor(QColor(shell.preload_bg(True)))")],
     [QT_RUN]),
    ('P128', 'the pre-load background is the dark token whatever the scheme', [(GUI,
     "    return SHELL['dark' if dark else 'light']['bg']", "    return SHELL['dark']['bg']")],
     [SH + 'test_the_colours_outside_the_page_are_the_tokens_of_the_os_scheme']),
    ('P129', 'the tray icon carries the attention colour with nothing waiting', [(QT,
     "tray.setIcon(alert if n else plain)", "tray.setIcon(alert)")],
     [QT_RUN]),
    ('P130', 'hiding to the tray does not read Attention', [(QT,
     "            ev.ignore()\n            self.hide()\n            refresh()\n",
     "            ev.ignore()\n            self.hide()\n")],
     [QT_RUN]),
    ('P131', "the tray's Pause all runs the e-stop", [(QT,
     "('Pause all', lambda: say(shell.pause_all()))", "('Pause all', lambda: say(shell.estop()[1]))")],
     [QT_RUN]),
    ('P132', '"Open Archeus V1" opens the app with no launch code', [(GAPI,
     "    url = v1.launch_url(info)\n", "    url = 'http://127.0.0.1:%d/' % info['port']\n")],
     [SH + 'test_open_archeus_v1_from_the_legacy_gui']),
    ('P133', 'archeus gui without Qt starts Core anyway', [(GUI,
     "        import PyQt6.QtWebEngineWidgets  # noqa: F401\n", "        pass\n")],
     [SH + 'test_the_gui_verb_without_qt_says_so_and_starts_nothing']),
    # R13-01: the tray's Emergency stop asks first, Cancel the default
    ('P138', "the tray's e-stop stops without asking", [(QT,
     "('Emergency stop', estop),", "('Emergency stop', lambda: say(shell.estop()[1])),")],
     [QT_RUN]),
    ('P139', "the tray's e-stop box defaults to stopping", [(QT,
     "box.setDefaultButton(box.addButton(QMessageBox.StandardButton.Cancel))",
     "box.addButton(QMessageBox.StandardButton.Cancel); box.setDefaultButton(stop)")],
     [QT_RUN]),
    ('P140', "the tray's e-stop stops whatever the answer", [(QT,
     "        if box.clickedButton() is stop:\n", "        if True:\n")],
     [QT_RUN]),
    # R13-02: offline, Needs you and the digest are named; the view has the app frame
    ('P141', 'offline Needs you names no mission', [(NOW_TSX,
     "{title ? <span className=\"title\"> · {title}</span> : null}", "{title && null}")],
     [OS_NAMED]),
    ('P142', 'the offline digest names a row by its kind alone', [(NOW_TSX,
     "{title ? ` ${x.ref.kind === 'mission' ? '' : 'for '}${title}` : null}", "{title && null}")],
     [OS_NAMED]),
    ('P143', 'the offline digest never reads what Attention ties to a mission', [(NOW_TSX,
     "(mission ?? att.items.find((i) => i.ref.kind === ref.kind && i.ref.id === ref.id)?.mission_id ?? '')",
     "(mission ?? '')")],
     [OS_NAMED]),
    ('P144', 'offline Happening now shows the missions waiting on you', [(NOW_TSX,
     "<ul className=\"rows\">\n              {active.map((m) => (", "<ul className=\"rows\">\n              {all.map((m) => (")],
     [OS_COLD]),
    ('P145', 'the offline view sits outside the app frame', [(NOW_TSX,
     '<main className="main offline-now" data-offline-snapshot="">',
     '<main className="offline-now" data-offline-snapshot="">')],
     [OS_NAMED]),
    ('P146', 'a read whose body never arrived is taken for data', [(TRANSPORT,
     "const data = await r.json().catch(() => undefined);",
     "const data = await r.json().catch(() => ({ error: 'invalid_response', detail: {} }));")],
     [OS + 'test_a_read_whose_body_never_arrives_is_never_data']),
    # R13 follow-up, rulebook §46.4 S-3: the TUI's Now header is the SPA's state sentence
    ('P147', "the TUI's Now header is the pre-ADR line", [(SCR,
     "app.st.paint(P.state_sentence(len(active), needs), 'text')",
     "app.st.paint('Archeus · %d active · %d need you' % (len(active), needs), 'text')")],
     [NOW_HDR]),
    ('P148', "the TUI's Now header is painted secondary", [(SCR,
     "app.st.paint(P.state_sentence(len(active), needs), 'text')",
     "app.st.paint(P.state_sentence(len(active), needs), 'text-2')")],
     [NOW_HDR]),
    ('P149', "the TUI's sentence says one needs you in the plural", [(PRES,
     "'%s you.' % count(needs_you, 'needs', 'need')", "'%s you.' % count(needs_you, 'need', 'need')")],
     [PARITY_PY]),
    # S-2: the live map drops the full key list; its own keys show on keyboard focus
    ('P150', 'the live map is described by the full key list', [(GV,
     "aria-describedby={map ? undefined : 'graph-keys'}", 'aria-describedby="graph-keys"')],
     [NOW_MAP]),
    ('P151', 'the live map shows the full key caption', [(GV,
     "      {map ? (\n        // rulebook §46.4 S-2", "      {false ? (\n        // rulebook §46.4 S-2")],
     [NOW_MAP]),
    ('P152', "the live map's hint shows without focus", [(APP_CSS,
     ".map-hint {\n  display: none;", ".map-hint {\n  display: block;")],
     [NOW_MAP]),
    ('P153', "the live map's hint never shows", [(APP_CSS,
     ".graph-canvas:focus-visible ~ .map-hint {\n  display: block;",
     ".graph-canvas:focus-visible ~ .map-hint {\n  display: none;")],
     [NOW_MAP]),
    # S-1: a narrow approval card's task table is labelled rows
    ('P154', 'the approval card does not read its own width', [(APP_CSS,
     "  container: approval / inline-size;\n", "  container: none;\n")],
     [S1]),
    ('P155', 'the stacked rows carry no label', [(APP_CSS,
     "    content: attr(data-label);\n", "    content: none;\n")],
     [S1]),
    ('P156', 'the task table stacks at every width', [(APP_CSS,
     "@container approval (max-width: 51em) {", "@container approval (max-width: 999em) {")],
     [S1]),
    ('P157', 'the stacked table keeps its header row', [(APP_CSS,
     "  .approval .canonical thead {\n    display: none;", "  .approval .canonical thead {\n    display: table-header-group;")],
     [S1]),
    ('P158', 'a stacked value is labelled with another column', [(ATT,
     '<td className="mono" data-label="Class">', '<td className="mono" data-label="Target">')],
     [S1]),
    # B12: the unification scenario, one Core across the desktop, the phone and the TUI
    ('P134', 'a decision names no device', [(AUTHZ,
     "'decided_by': actor.id, 'decided_at': tx.now,", "'decided_by': None, 'decided_at': tx.now,")],
     [UNIFY]),
    ('P135', "the phone's approval drops its PIN", [(ATT,
     "step_up: needsPin ? pin : undefined", "step_up: undefined")],
     [UNIFY]),
    ('P136', "the desktop's review names no device", [(VERIF,
     "principal_id=actor.id if user else None,", "principal_id=None,")],
     [UNIFY]),
    ('P137', "a phone paired with a PIN keeps none", [(ROUTES,
     "'pin_hash': commands.hash_pin(b['pin']) if b.get('pin') else None},",
     "'pin_hash': None},")],
     [UNIFY]),
]

if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
