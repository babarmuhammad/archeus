"""The spine in the terminal (ADR-0054 §7): the six stations as one cluster from the
generated table, never guessed. `spine_of` is held to the SPA's `spineOf` by the shared
parity cases (test_parity.py); this holds the cluster and the row."""

import json
import os

import pytest

from archeus.cli.tui import _tables, present as P, screens as SC
from archeus.cli.tui.view import Style

SPINE_JSON = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'clients', 'app', 'tokens',
                          'spine.json')


def test_the_terminals_table_is_the_json_the_spa_reads():
    with open(SPINE_JSON, encoding='utf-8') as f:
        sp = json.load(f)
    assert _tables.SPINE['stations'] == sp['stations']
    assert _tables.SPINE['states'] == sp['states']
    assert _tables.SPINE['sentences'] == sp['sentences']
    assert set(_tables.SPINE['marks']) == set(sp['marks'])
    for kind, m in _tables.SPINE['marks'].items():
        assert m['role'] == sp['marks'][kind]['role'], kind
        want = sp['marks'][kind]
        c = _tables.CLASSES[want['class']] if 'class' in want else want
        assert (m['glyph'], m['ascii']) == (c['glyph'], c['ascii']), kind


@pytest.mark.parametrize('state, held_from, unicode, plain', [
    ('EXECUTING', None, '✓✓✓●○○ Executing', '+++*oo Executing'),
    ('BLOCKED', 'EXECUTING', '✓✓✓■○○ Blocked', '+++#oo Blocked'),
    ('PAUSED', 'EXECUTING', '✓✓✓‖○○ Paused', '+++=oo Paused'),
    ('APPROVAL_REQUIRED', None, '✓✓◆○○○ Waiting for approval', '++!ooo Waiting for approval'),
    ('BLOCKED', None, '?????? Blocked', '?????? Blocked'),
    ('COMPLETED', None, '✓✓✓✓✓✓ Done — verified and reviewed', '++++++ Done — verified and reviewed'),
    ('CREATED', None, '○○○○○○ Created', 'oooooo Created'),
    ('CANCELLED', 'EXECUTING', '–––––– Cancelled', '------ Cancelled'),
    ('FAILED', None, '✓✓✓✕○○ Failed', '+++xoo Failed'),
    ('APPROVED', None, '✓✓✓○○○ Approved — not started', '+++ooo Approved — not started'),
])
def test_the_cluster_and_its_word(state, held_from, unicode, plain):
    assert P.spine(state, held_from) == unicode
    assert P.spine(state, held_from, ascii=True) == plain


def test_a_state_this_client_does_not_know_is_its_own_word_and_no_stations():
    assert P.spine('FROM_A_NEWER_CORE', 'EXECUTING') == 'FROM_A_NEWER_CORE'
    assert P.spine_of('FROM_A_NEWER_CORE')['marks'] == []


def test_a_hold_names_no_position_without_a_station_in_held_from():
    for bad in (None, '', 'NOT_A_STATE', 'COMPLETED', 'APPROVED', 'BLOCKED', 7, [], {}):
        assert P.spine_of('BLOCKED', bad)['marks'] == ['unknown'] * 6, bad
        assert P.spine_of('PAUSED', bad)['text'] == 'Paused, position unknown.', bad


def test_cancelled_ignores_a_leftover_held_from():
    assert P.spine_of('CANCELLED', 'EXECUTING') == P.spine_of('CANCELLED', None)


def test_only_a_completed_mission_is_drawn_done():
    cells = P.spine_cells('COMPLETED')
    assert {c['role'] for c in cells} == {'state.done'}
    for state in _tables.PRESENTATION['mission']:
        if state != 'COMPLETED':
            assert not P.spine_of(state, 'EXECUTING')['done'], state
            assert 'state.done' not in {c['role'] for c in P.spine_cells(state, 'EXECUTING')}, state
    assert {c['role'] for c in P.spine_cells('EXECUTING')} == {'text', 'state.active', 'text-3'}


def test_every_state_has_a_text_equivalent():
    for state in _tables.PRESENTATION['mission']:
        assert P.spine_of(state, 'EXECUTING')['text'], state


def test_a_mission_row_carries_the_cluster_beside_the_badge_and_keeps_the_word():
    class Doc:
        def __init__(self):
            self.rows = []

        def add(self, text, target=None):
            self.rows.append(text)

    class App:
        st = Style(colour=False, ascii=False)

        @staticmethod
        def now_ms():
            return 0

    mission = {'id': 'msn_1', 'title': 'Fix add', 'state': 'BLOCKED', 'held_from': 'EXECUTING',
               'updated_at': None}
    doc = Doc()
    SC.mission_row(App, doc, mission)
    assert '■ Blocked  ✓✓✓■○○  Fix add' in doc.rows[0], doc.rows[0]
    App.st = Style(colour=False, ascii=True)
    doc = Doc()
    SC.mission_row(App, doc, dict(mission, state='EXECUTING', held_from=None))
    assert '* Executing  +++*oo  Fix add' in doc.rows[0], doc.rows[0]
