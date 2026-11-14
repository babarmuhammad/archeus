"""T-1377 · Close the test gaps in claude_sessions/plugins.py recommendations (297-340).

Exact source slice: ``claude_sessions/plugins.py`` lines 297-340 at tip ``73ad7a90``
(re-located at ``3885bc1d``). No source file is edited; no new dependency.

Ten candidate branches, ranked denial/fail-closed first, then boundaries, then
error paths. Selected probes and the source branch each test catches:

 1. plugins.py:315-323  registered only when the marketplace is in known_marketplaces
 2. plugins.py:321      folded into probe 7: source lookup for a marketplace the table does not know
 3. plugins.py:322      desc read only from '<name>@<marketplace>'
 4. plugins.py:322      missing entry gives ''; a non-string description is str()'d and cut to 200
 5. plugins.py:314,323 installed only for the exact key 'name@marketplace'
 6. plugins.py:313     harness with no RECOMMENDED entry gives [] (the `or ()`)
 7. plugins.py:318-321 a marketplace outside RECOMMENDED_SOURCES yields source ''
 8. plugins.py:318-324 output order matches the RECOMMENDED tuple order
 9. plugins.py:316     the entries reader is called once per home, not per row
10. plugins.py:313     the harness id comes from harnesses.of(cfg_dir)['id']

The installed / known_marketplaces readers, versions._marketplace_entries and
harnesses.of are faked; no CLI, subprocess, real home or credential is read.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import harnesses, plugins, versions

CFG = '/synthetic/cfg'
OFFICIAL = 'claude-plugins-official'


@pytest.fixture
def home(monkeypatch):
    state = {'installed': [], 'known': [], 'entries': {}, 'harness': 'claude',
             'entry_calls': [], 'of_calls': []}

    def fake_of(cfgdir=None):
        state['of_calls'].append(cfgdir)
        return {'id': state['harness']}

    def fake_entries(cfg_dir=None):
        state['entry_calls'].append(cfg_dir)
        return state['entries']

    monkeypatch.setattr(plugins, 'installed', lambda cfg_dir=None: state['installed'])
    monkeypatch.setattr(plugins, 'known_marketplaces',
                        lambda cfg_dir=None: [{'name': n} for n in state['known']])
    monkeypatch.setattr(harnesses, 'of', fake_of)
    monkeypatch.setattr(versions, '_marketplace_entries', fake_entries)
    return state


def _rows(cfg=CFG):
    return plugins.recommendations(cfg)


def test_registered_is_true_only_for_a_marketplace_the_home_knows(home):
    home['known'] = [OFFICIAL]
    rows = {r['marketplace']: r for r in _rows()}
    assert rows[OFFICIAL]['registered'] is True
    assert rows['openai-codex']['registered'] is False
    assert rows['openai-codex']['source'] == plugins.RECOMMENDED_SOURCES['openai-codex']


def test_desc_comes_only_from_the_exact_name_at_marketplace_entry(home):
    home['entries'] = {
        'code-review@other-mkt': {'description': 'WRONG'},
    }
    row = next(r for r in _rows() if r['name'] == 'code-review')
    assert row['desc'] == ''

    home['entries']['code-review@%s' % OFFICIAL] = {'description': 'Right'}
    row = next(r for r in _rows() if r['name'] == 'code-review')
    assert row['desc'] == 'Right'


def test_a_non_string_description_is_coerced_and_cut_to_200(home):
    home['entries'] = {
        'code-review@%s' % OFFICIAL: {'description': 12345},
        'commit-commands@%s' % OFFICIAL: {'description': 'y' * 300},
    }
    rows = {r['name']: r for r in _rows()}
    assert rows['code-review']['desc'] == '12345'
    assert rows['commit-commands']['desc'] == 'y' * 200


def test_installed_needs_the_exact_key_and_a_bare_name_does_not_count(home):
    home['installed'] = [{'key': 'code-review'}]
    row = next(r for r in _rows() if r['name'] == 'code-review')
    assert row['installed'] is False

    home['installed'] = [{'key': 'code-review@%s' % OFFICIAL}]
    row = next(r for r in _rows() if r['name'] == 'code-review')
    assert row['installed'] is True


def test_a_harness_with_no_recommendation_entry_gives_an_empty_list(home):
    home['harness'] = 'some-future-cli'
    assert _rows() == []


def test_a_marketplace_outside_the_source_table_yields_an_empty_source(home, monkeypatch):
    monkeypatch.setattr(plugins, 'RECOMMENDED',
                        {'claude': (('thing', 'mystery-mkt', 'Why it helps.'),)})
    rows = _rows()
    assert rows == [{'name': 'thing', 'marketplace': 'mystery-mkt',
                     'why': 'Why it helps.', 'source': '', 'desc': '',
                     'installed': False, 'registered': False}]


def test_rows_come_out_in_the_order_the_table_lists_them(home):
    got = [r['name'] for r in _rows()]
    assert got == [n for n, _m, _w in plugins.RECOMMENDED['claude']]


def test_the_entries_reader_is_called_once_for_the_whole_home(home):
    rows = _rows()
    assert len(rows) == len(plugins.RECOMMENDED['claude'])
    assert home['entry_calls'] == [CFG]


def test_the_harness_comes_from_the_home_not_from_claude(home, monkeypatch):
    monkeypatch.setattr(plugins, 'RECOMMENDED',
                        {'claude': (('from-claude', OFFICIAL, 'Claude row.'),),
                         'codex': (('from-codex', 'openai-codex', 'Codex row.'),)})
    home['harness'] = 'codex'
    assert [r['name'] for r in _rows('/synthetic/codex')] == ['from-codex']
    assert home['of_calls'] == ['/synthetic/codex']
