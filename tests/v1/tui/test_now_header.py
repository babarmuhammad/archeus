"""The TUI's Now header is the SPA's state sentence, word for word (rulebook
§46.4 S-3, ADR-0027 §5): the same two counts from the same reads (the missions
not SETTLED, Attention's count), painted as the screen's headline (`text`, not
`text-2`), with no greeting and no glyph. The sentence itself is held to the
SPA's `stateSentence` by the shared parity cases (`test_parity.py`)."""

import json
import os

import pytest

from archeus.cli.tui.view import Style
from claude_sessions import render

from .test_acceptance import _StubApp

CASES = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'clients', 'app', 'test',
                     'fixtures', 'parity.json')
with open(CASES, encoding='utf-8') as _f:
    SPA = {tuple(c['args']): c['out'] for c in json.load(_f)['cases'] if c['fn'] == 'stateSentence'}

def _app(active, needs):
    # `active` missions plus three settled ones, which count for nothing
    ms = [{'id': 'msn_a%d' % i, 'title': 'active %d' % i, 'state': ('EXECUTING', 'PLANNING')[i % 2],
           'updated_at': '2026-10-04T12:00:00Z', 'version': 1} for i in range(active)]
    ms += [{'id': 'msn_s%d' % i, 'title': 'settled %d' % i, 'state': s,
            'updated_at': '2026-10-04T12:00:00Z', 'version': 1}
           for i, s in enumerate(('COMPLETED', 'PAUSED', 'APPROVAL_REQUIRED'))]
    app = _StubApp({'/v1/missions': {'missions': ms},
                    '/v1/attention': {'items': [], 'count': needs},
                    '/v1/ideas': {'ideas': []}, '/v1/digest': {'count': 0, 'groups': []},
                    '/v1/sync': {'client': {'scopes': ['observe', 'control']}}})
    app.st = Style(colour=True)
    app.go({'view': 'now'})
    app.frame()
    return app


@pytest.mark.parametrize('active,needs', sorted(SPA))
def test_the_now_header_is_the_spas_sentence_painted_as_the_headline(active, needs):
    app = _app(active, needs)
    head = app._doc.lines[0]['text']
    assert render.strip_ansi(head) == '  ' + SPA[(active, needs)], head
    assert head == '  ' + app.st.paint(SPA[(active, needs)], 'text'), 'not painted as the headline'


def test_the_cases_cover_zero_one_and_two_of_each_count():
    assert set(SPA) == {(a, n) for a in (0, 1, 2) for n in (0, 1, 2)}
