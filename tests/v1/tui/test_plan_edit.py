"""A plan edit in the TUI (P19 S2; p19-design-gate B4): the TUI shows the
person's version as such and never edits — no screen sends the edit command."""

import os

from archeus.cli._api import endpoints

from .conftest import plain
from .test_acceptance import _StubApp

MID = 'msn_1'
TUI = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'archeus', 'cli', 'tui')


def _app(edited_by):
    plan = {'id': 'pln_2', 'plan_version': 2, 'state': 'PROPOSED', 'in_force': True,
            'current': True, 'edited_by': edited_by, 'waves': [['t1']],
            'tasks': [{'id': 'tsk_1', 'key': 't1', 'title': 'Deploy the fix', 'kind': 'code_change',
                       'state': 'PENDING', 'depends_on': []}]}
    app = _StubApp({
        endpoints.get_mission(MID): {'id': MID, 'title': 'Ship', 'state': 'APPROVAL_REQUIRED',
                                     'objective': 'o', 'version': 2},
        endpoints.get_mission_plan(MID): {'plan': plan, 'versions': [
            {'id': 'pln_2', 'plan_version': 2, 'state': 'PROPOSED', 'supersedes_plan_id': None}]},
        endpoints.attention_items(): {'items': [], 'count': 0}, endpoints.digest(): {'groups': []},
        endpoints.sync(): {'client': {'scopes': ['observe', 'control', 'approve', 'admin']}}})
    app.open('mission', MID, 'plan')
    return app


def test_the_persons_version_is_shown_as_such():
    assert 'edited by a person' in plain(_app('prn_1'))
    assert 'edited by a person' not in plain(_app(None))


def test_the_tui_never_edits_a_plan():
    app = _app('prn_1')
    plain(app)
    assert not [a for x in app._doc.lines for a in x['acts'] if 'edit' in a['label'].lower()]
    for name in os.listdir(TUI):
        if name.endswith('.py'):
            with open(os.path.join(TUI, name), encoding='utf-8') as f:
                assert 'edit_plan' not in f.read(), name
