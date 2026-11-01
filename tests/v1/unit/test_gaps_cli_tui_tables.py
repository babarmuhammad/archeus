"""The highest-risk gaps around the generated client tables (p17-design-gate A1):
`archeus/cli/tui/_tables.py` is pure data — every executable branch that can break
lives in the consumers that index it (`present`, `sync`, the app's key router,
`screens`, `view`). These tests pin those branches to the data: the fail-closed
paths first (an unknown state, an unknown trigger, a frame with no subject, a
kind with an empty rule table, a destination nobody can reach), then the boundary
values (one-column glyphs, one-key tabs, exactly-two edge words, empty vs filled
tables), then the error paths (the direct `[...]` indexes that raise mid-render).
Nothing here reads the OS: the tables are the unit under test.
"""

import json
import os
import re

from claude_sessions import render

from archeus.cli.tui import _tables, present, screens, sync, view
from archeus.cli.tui.tokens import COLOURS

ST = view.Style()
STATE_KEY = re.compile(r'[A-Z][A-Z0-9_]*\Z')
MACHINE_KEY = re.compile(r'[a-z][a-z0-9_]*\Z')
ROOT = os.path.join(os.path.dirname(__file__), '..', '..', '..')
TOKENS = os.path.join(ROOT, 'clients', 'app', 'tokens')
#: the kinds whose invalidation table is empty by decision (gen_ui.py keeps
#: whatever the JSON says; nothing else may silently join or leave this set)
EMPTY_RULE_KINDS = {'execution_node', 'model'}


def _json(name):
    with open(os.path.join(TOKENS, name), encoding='utf-8') as f:
        return json.load(f)


def _oneline(s):
    return isinstance(s, str) and bool(s) and not any(c in s for c in '\n\t\x00\x1b')


def _states(machine):
    return sorted(set(present.PRESENTATION.get(machine, {})) | set(present.TRIGGERS.get(machine, {})))


# ── fail-closed and denial paths first ───────────────────────────────────────

def test_offers_only_what_the_trigger_table_lists_and_nothing_else():
    """present.py:17-18: TRIGGERS.get(machine, {}).get(state, []) then `any`.
    Inverting the empty-list default would offer commands the machines never
    declared; a trigger the table lost silently denies every command from it."""
    assert set(present.TRIGGERS) == set(present.PRESENTATION)
    for machine, by_state in present.TRIGGERS.items():
        for state, triggers in by_state.items():
            assert state in present.PRESENTATION[machine], (machine, state)
            assert isinstance(triggers, list) and triggers, (machine, state)
            assert len(set(triggers)) == len(triggers), (machine, state)
            for t in triggers:
                assert isinstance(t, str) and t and t == t.strip() and ' ' not in t
                assert present.offers(machine, state, t) is True, (machine, state, t)
            assert present.offers(machine, state, 'not_a_real_trigger') is False
    assert present.offers('no_such_machine', 'RUNNING', 'stop') is False
    assert present.offers('mission', 'NO_SUCH_STATE', 'cancel') is False
    assert present.offers('mission', 'CREATED') is False


def test_an_unknown_or_empty_state_stays_unknown_never_borrows_a_class():
    """present.py:23-25: `cls = PRESENTATION.get(...); if not cls:` returns the
    neutral '?' row. If a falsy class ever entered the table this branch would
    guess a look for a state Core never sent; if a '' state key entered the
    table, '' would render as a real state."""
    for machine in sorted(present.PRESENTATION):
        for state in ('NO_SUCH_STATE', '__NOT_A_STATE__'):
            look = present.present(machine, state)
            assert look == {'cls': 'neutral', 'glyph': '?', 'role': 'text-2', 'label': state}
            assert ST.glyph(look) == '?'          # view.py:97-99, fail-closed twice
        assert '' not in present.PRESENTATION[machine]
        assert '' not in present.LABELS.get(machine, {})
        assert '' not in present.TRIGGERS.get(machine, {})


def test_the_empty_invalidation_table_stales_nothing_and_a_headless_frame_stales_nothing():
    """sync.py:177-179: RULES.get(kind, []) then any() — a frame with no
    subject, an unknown kind, or a kind whose table is empty must make nothing
    stale (a wrong default here re-reads the whole cache, or worse, trusts it)."""
    everything = ['/v1/missions', '/v1/missions/m1/plan', '/v1/digest', '/v1/attention',
                  '/v1/executions/e9/checkpoints', '/v1/status']
    headless = [{}, {'data': None}, {'data': {}}, {'data': {'subject': None}},
                {'data': {'subject': {}}}, {'data': {'subject': {'kind': None}}}]
    for frame in headless:
        stale = sync.stale_by(frame)
        assert all(stale(p) is False for p in everything), frame
    stale = sync.stale_by({'data': {'subject': {'kind': 'no_such_kind', 'id': 'x1'}}})
    assert all(stale(p) is False for p in everything)
    for kind in [k for k, v in sync.RULES.items() if not v]:      # pinned to EMPTY_RULE_KINDS
        assert kind in EMPTY_RULE_KINDS
        stale = sync.stale_by({'data': {'subject': {'kind': kind, 'id': 'x1'}}})
        assert all(stale(p) is False for p in everything), kind
    assert {k for k, v in sync.RULES.items() if not v} == EMPTY_RULE_KINDS
    assert set(sync.RULES) >= EMPTY_RULE_KINDS


def test_the_trigger_table_says_exactly_what_the_core_state_machine_declares():
    """present.py:17-18 only asks the table, so a trigger the table lost denies
    every command from that state forever, and one it invented offers a move the
    machines do not have. The table's own source is gen_ui.py:233-245 reading
    Core's states.TABLE; re-running that derivation is the only way to see the
    difference, because a table-only test cannot notice what the table lacks."""
    from archeus.core.domain import states
    out = {}
    for m, frm, _to, trig, _g in states.TABLE:
        if frm != '[*]' and trig:
            out.setdefault(m, {}).setdefault(frm, set()).add(trig)
    assert present.TRIGGERS == {m: {s: sorted(t) for s, t in v.items()}
                                for m, v in out.items()}


def test_the_copied_tables_are_the_json_the_spa_reads():
    """A1 in full: test_boundaries.py pins navigation and invalidation to their
    JSON; CLASSES, PRESENTATION and EDGE_WORDS are the same generated promise
    and are read identically by both clients — drift here shows one state with
    two faces, and only one of the two clients can be fixed by re-running the
    generator."""
    p, e = _json('presentation.json'), _json('edges.json')
    assert _tables.CLASSES == p['classes']
    assert _tables.PRESENTATION == p['machines']
    assert _tables.EDGE_WORDS == e['words']
    for machine, table in p['machines'].items():
        for state in table:
            want = p.get('labels', {}).get(machine, {}).get(state)
            if want:                                    # the auto-labelled rest belong to the generator
                assert _tables.LABELS[machine][state] == want, (machine, state)


def test_a_destination_nobody_can_type_is_a_navigation_denial():
    """app.py:301: `next((d for d in DESTINATIONS if d['tui'] == c), None)` —
    a duplicate `tui` key makes the second destination permanently unreachable
    (its else-branch dies) and app.py:194 indexes 'attention' with a no-default
    `next`, so a lost row crashes every top line."""
    ids = [d['id'] for d in _tables.DESTINATIONS]
    tuis = [d['tui'] for d in _tables.DESTINATIONS]
    assert len(set(ids)) == len(ids) and len(set(tuis)) == len(tuis)
    for d in _tables.DESTINATIONS:
        assert set(d) == {'id', 'mod', 'label', 'key', 'tui', 'phone', 'blurb'}, d
        assert MACHINE_KEY.match(d['id']), d
        assert d['mod'] in ('alt', 'ctrl'), d
        assert len(d['tui']) == 1 and d['tui'].isprintable() and ord(d['tui']) < 128, d
        assert _oneline(d['label']) and _oneline(d['blurb']) and _oneline(d['phone']), d
    assert 'attention' in ids
    for id_ in ids:                                   # screens.py:56: next(...), no default
        assert screens.dest(id_)['id'] == id_
    by_tui = {d['tui']: d['id'] for d in _tables.DESTINATIONS}
    assert len(by_tui) == len(tuis)


def test_control_sections_rotate_and_the_default_section_exists():
    """app.py:333-336: `cur = r.get('section') or 'autonomy'` then
    `ids.index(cur) % len(ids)` — a missing 'autonomy' raises ValueError on the
    first Tab ever pressed, an empty list raises ZeroDivisionError, a duplicate
    id makes two sections one."""
    ids = [s['id'] for s in _tables.CONTROL_SECTIONS]
    assert ids and len(set(ids)) == len(ids)
    assert 'autonomy' in ids
    for s in _tables.CONTROL_SECTIONS:
        assert MACHINE_KEY.match(s['id']) and _oneline(s['label']), s


# ── boundary values ───────────────────────────────────────────────────────────

def test_a_badge_glyph_occupies_exactly_one_terminal_column():
    """view.py:102-106: the badge is `glyph + ' ' + label`, laid out by
    render.fit at the full line width (view.py:108-111). A two-codepoint or
    East-Asian-wide glyph silently shifts every column of every screen."""
    for name, c in _tables.CLASSES.items():
        assert set(c) == {'glyph', 'ascii', 'role', 'name'}, name
        assert len(c['glyph']) == 1 and render.disp_width(c['glyph']) == 1, (name, c)
        assert not c['glyph'].isspace() and ord(c['glyph']) >= 0x21, (name, c)
        assert len(c['ascii']) == 1 and c['ascii'].isprintable() and ord(c['ascii']) < 128, name
    for machine in sorted(present.PRESENTATION):
        for state in present.PRESENTATION[machine]:
            look = present.present(machine, state)
            badge = ST.badge(machine, state)
            assert badge == look['glyph'] + ' ' + look['label'], (machine, state)
            assert view.width_of(badge) == 2 + render.disp_width(look['label']), (machine, state)


def test_an_ascii_terminal_gets_a_translated_table_not_a_raw_glyph():
    """view.py:108-111: Style.line translates with _ASCII before fitting. A
    CLASSES glyph missing from that map survives as non-ASCII bytes an ASCII
    terminal cannot encode — the width math and the fallback both break."""
    for c in _tables.CLASSES.values():
        assert ord(c['glyph']) in view._ASCII, c
        assert all(ord(ch) < 128 for ch in view._ASCII[ord(c['glyph'])]), c
    text = ''.join(c['glyph'] for c in _tables.CLASSES.values())
    out = view.Style(ascii=True).line(text, 200)
    assert all(ord(ch) < 128 for ch in out), repr(out)


def test_every_class_role_is_a_colour_in_both_themes():
    """view.py:113-121 (Style.paint): `COLOURS[self.theme].get(role)` — a role
    missing from the theme silently renders the state without its colour, and
    colour-alone-never is the accessibility rule the badge exists to honour."""
    for name, c in _tables.CLASSES.items():
        assert c['role'] in COLOURS['dark'] and c['role'] in COLOURS['light'], (name, c)
        assert _oneline(c['name']), name


def test_edge_words_are_exactly_the_forward_and_back_pair():
    """present.py:256-258: `w = EDGE_WORDS.get(field); return w[0 if holder else 1]`
    — a one- or three-word entry raises IndexError mid-relations-render, or
    silently says the wrong thing about who contains whom."""
    for field, words in present.EDGE_WORDS.items():
        assert isinstance(words, list) and len(words) == 2 and words[0] != words[1], (field, words)
        assert _oneline(words[0]) and _oneline(words[1]), field
        assert words[0] == words[0].strip().lower() and words[1] == words[1].strip().lower(), field
        assert re.match(r'[A-Za-z_][A-Za-z0-9_]*\.[a-z][A-Za-z0-9_]*\Z', field), field
        assert present.edge_words(field, True) == words[0], field
        assert present.edge_words(field, False) == words[1], field
    assert present.edge_words('no_such.field', True) == 'no_such.field'      # the else branch


def test_inspector_tab_lists_are_never_empty_never_shadowed_never_missing_their_words():
    """app.py:250-251 and screens.py:1069-1085: INSPECTOR_TABS.get(kind,
    ['detail']), `tabs[0]`, and the direct `TABS[t]['key']`/`['label']` indexes
    — an unknown tab id raises KeyError mid-draw, an empty list raises
    IndexError/ZeroDivisionError (app.py:335), and two tabs sharing a key make
    the second unreachable through the key router at app.py:305-308."""
    for kind, tabs in _tables.INSPECTOR_TABS.items():
        assert MACHINE_KEY.match(kind), kind
        assert isinstance(tabs, list) and tabs, kind
        assert len(set(tabs)) == len(tabs), kind
        keys = []
        for t in tabs:
            assert t in _tables.TABS, (kind, t)
            keys.append(_tables.TABS[t]['key'])
        assert len(set(keys)) == len(keys), (kind, keys)
    for tid, tab in _tables.TABS.items():
        assert MACHINE_KEY.match(tid), tid
        assert set(tab) == {'label', 'key'}, tid
        assert _oneline(tab['label']), tid
        assert len(tab['key']) == 1 and tab['key'].isprintable() and ord(tab['key']) < 128, tid
    assert 'detail' in _tables.TABS             # the fallback ['detail'] of app.py:250


# ── error paths: the direct indexes that raise mid-render ────────────────────

def test_no_listed_state_can_keyerror_the_renderer():
    """present.py:26: `c = CLASSES[cls]` after only the falsy check — one
    PRESENTATION value naming a class that gen_ui.py did not emit crashes
    every row that reads that state."""
    for machine in sorted(present.PRESENTATION):
        for state, cls in present.PRESENTATION[machine].items():
            assert STATE_KEY.match(state), (machine, state)
            assert isinstance(cls, str) and cls and cls == cls.strip(), (machine, state, cls)
            assert cls in _tables.CLASSES, (machine, state, cls)
            c = _tables.CLASSES[cls]
            look = present.present(machine, state)
            assert look['cls'] == cls and look['glyph'] == c['glyph'], (machine, state)
            assert look['role'] == c['role'], (machine, state)


def test_no_listed_state_shows_its_raw_enum_to_the_user():
    """present.py:28 and :33: `LABELS.get(machine, {}).get(state, state)` and
    `look['label'] or state` — a label the table lost renders ENDED_KILLED
    (an internal token) where a sentence belongs, an empty one renders a
    label-less badge."""
    assert set(present.LABELS) == set(present.PRESENTATION)
    for machine in sorted(present.PRESENTATION):
        assert set(present.LABELS[machine]) == set(present.PRESENTATION[machine]), machine
        for state in present.PRESENTATION[machine]:
            assert STATE_KEY.match(state), (machine, state)
        for state in _states(machine):
            label = present.LABELS.get(machine, {}).get(state)
            assert label is not None, (machine, state)          # not even a trigger-only state
            assert _oneline(label), (machine, state)
            assert label == label.strip() and label != state, (machine, state)
            assert present.badge(machine, state)['label'] == label, (machine, state)


def test_invalidation_patterns_are_paths_that_only_match_their_own_subject():
    """sync.py:163-170 (_compile) fed by RULES: a pattern missing its /v1/
    prefix, or carrying a stray space or backslash, compiles into an
    expression that never matches (nothing is ever re-read — a stale cache
    the user acts on) or matches too much. The {id} and single-star wildcards
    must stay anchored: one subject's frame stales one subject's reads."""
    for kind, patterns in sync.RULES.items():
        assert MACHINE_KEY.match(kind), kind
        assert isinstance(patterns, list), kind
        for p in patterns:
            assert p.startswith('/v1/') and p == p.strip(), (kind, p)
            assert ' ' not in p and '\\' not in p and '?' not in p, (kind, p)
            assert '{id}' not in p or p.count('{id}') == 1, (kind, p)
    stale = sync.stale_by({'data': {'subject': {'kind': 'mission', 'id': 'm1'}}})
    assert stale('/v1/missions') is True                        # '/v1/missions**'
    assert stale('/v1/missions/m1') is True
    assert stale('/v1/missions/m1/plan') is True                # '/v1/missions/*/plan'
    assert stale('/v1/digest') is True                          # the exact path
    assert stale('/v1/executions/e9') is False
    stale = sync.stale_by({'data': {'subject': {'kind': 'plan', 'id': 'p7'}}})
    assert stale('/v1/plans/p7') is True                        # '/v1/plans/{id}'
    assert stale('/v1/plans/p8') is False                       # {id} is anchored, not a prefix
    assert stale('/v1/plans/p7/') is False                      # \Z, not startswith
    stale = sync.stale_by({'data': {'subject': {'kind': 'checkpoint', 'id': 'c9'}}})
    assert stale('/v1/executions/c9/checkpoints') is True       # one star, not two
    assert stale('/v1/executions/other/checkpoints') is True    # * is any id: the table's choice
    assert stale('/v1/executions/c9') is False                  # the same kind's other rule
    assert stale('/v1/missions/m1') is False                    # someone else's rule
