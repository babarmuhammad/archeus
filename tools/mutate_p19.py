"""The P19 mutation suite (p19-design-gate B13): break each gate's invariant,
run the test written for it, and require it to fail. B1, one edge
implementation (P01-P08); B2, the change rule on the Relations list and the
TUI (P09-P14).

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
     '&depth=1&limit=1000', '&depth=2&limit=1000')],
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
]

if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
