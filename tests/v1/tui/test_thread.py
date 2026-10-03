"""T2 in the TUI (ADR-0026 §1, design system's TUI table; p19-design-gate B2):
a row whose object Core's digest names carries the thread's rule on its own
left edge — on every list, the relations view included — and only then; the
rule is never the cursor's `›`, and an acknowledged digest leaves no rule."""

from archeus.cli.tui.view import Style
from archeus.cli._api import endpoints
from claude_sessions import render

from .test_acceptance import _StubApp

RULE = '│'


def _missions():
    return [{'id': 'msn_%d' % i, 'title': 'mission %d' % i, 'state': 'EXECUTING',
             'updated_at': '2026-10-03T12:00:00Z', 'version': 1} for i in range(3)]


def _digest(*refs):
    return {'count': len(refs), 'up_to_seq': 9, 'truncated': False,
            'groups': [{'ref': {'kind': k, 'id': i}, 'headline': 'progressed', 'count': 1}
                       for k, i in refs]}


def _lines(app):
    """The body rows naming an object: (kind, id) -> the row's text as drawn."""
    app.frame()
    return {(x['target'][1], x['target'][2]): render.strip_ansi(x['text'])
            for x in app._doc.lines if x['target'] and x['target'][0] == 'open'}


def _data(digest):
    return {'/v1/missions': {'missions': _missions()}, '/v1/attention': {'items': [], 'count': 0},
            '/v1/ideas': {'ideas': []}, '/v1/digest': digest,
            '/v1/sync': {'client': {'scopes': ['observe', 'control']}}}


def test_a_changed_row_carries_the_rule_and_no_other_row_does():
    app = _StubApp(_data(_digest(('mission', 'msn_1'))))
    app.go({'view': 'work'})
    rows = _lines(app)
    assert set(rows) >= {('mission', 'msn_0'), ('mission', 'msn_1'), ('mission', 'msn_2')}
    for key, text in rows.items():
        assert text.startswith(RULE) == (key == ('mission', 'msn_1')), (key, text)
    # the rule takes the row's own left edge: the layout does not move
    assert len(rows[('mission', 'msn_1')]) == len(rows[('mission', 'msn_0')])


def test_the_rule_is_not_the_cursor_and_both_can_stand_on_one_row():
    app = _StubApp(_data(_digest(('mission', 'msn_0'))))
    app.go({'view': 'work'})
    frame = [render.strip_ansi(x) for x in app.frame()]
    focused = [x for x in frame if x.startswith('›')]
    assert focused and focused[0].startswith('› ' + RULE), focused


def test_an_acknowledged_digest_leaves_no_rule():
    app = _StubApp(_data(_digest()))
    app.go({'view': 'work'})
    assert not any(t.startswith(RULE) for t in _lines(app).values())


def test_the_relations_view_rules_the_neighbour_the_digest_names():
    me = {'kind': 'mission', 'id': 'msn_1'}
    graph = {'edges': [
        {'from': {'kind': 'session', 'id': 'ses_1'}, 'to': me, 'field': 'sessions.mission_id',
         'rel': None, 'tier': None, 'inactive': False, 'structural': False},
        {'from': {'kind': 'plan', 'id': 'pln_1'}, 'to': me, 'field': 'plans.mission_id',
         'rel': None, 'tier': None, 'inactive': False, 'structural': False}]}
    data = dict(_data(_digest(('session', 'ses_1'))), **{
        '/v1/missions/msn_1': dict(_missions()[1], objective='o'),
        '/v1/missions/msn_1/plan': {'versions': []},
        endpoints.world_graph(focus='mission:msn_1', depth=1, limit=1000): graph})
    app = _StubApp(data)
    app.open('mission', 'msn_1', 'relations')
    rows = _lines(app)
    assert rows[('session', 'ses_1')].startswith(RULE)
    assert not rows[('plan', 'pln_1')].startswith(RULE)


def test_an_ascii_terminal_gets_a_bar_it_can_print():
    s = Style(colour=False, ascii=True)
    assert s.line(RULE + ' x', 4).startswith('|')
