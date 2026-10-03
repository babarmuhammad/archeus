"""The P19 mutation suite (p19-design-gate B13): break each gate's invariant,
run the test written for it, and require it to fail. B1, one edge
implementation (P01-P08); B2, the change rule on the Relations list and the
TUI (P09-P14); B11, the generated client everywhere (P15-P20); B3, a mission's own
conversation and the mission Now tab (P21-P30).

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
CLI_STATUS = ('tests/v1/integration/test_cli_v1.py::'
              'test_status_of_a_mission_prints_what_core_reports_and_a_refusal_in_its_words')

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
     "grammar.resolve(conn, msg.text, mission=conv.mission_id)", "grammar.resolve(conn, msg.text, mission=None)")],
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
]

if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
