"""T-1274: claude_sessions/provision.py:110-166 at 6bbd3b44; same current slice.

Selected candidates, not measured coverage. Closest existing assertions:
166 unknown sources; test_surface_parity.py:332 checks account binding only.
125 first real CLAUDE.md; test_multihome.py:108 checks discovery, not selection.
137 per-account sets; test_multihome.py:108 does not compute provisioning diff.
139 full hook identities; test_surface_parity.py:148 checks hook reader states.
128 conflict order; test_multihome.py:59 checks home deduplication, not union.
143 boolean missing flags; test_surface_parity.py:332 does not assert flags.
148 counts/totals; test_surface_parity.py:148 does not assert diff totals.
156 clean boundary; test_multihome.py:119 tests disabled harness, not diff.
157 sorted recognized sources; test_surface_parity.py:332 checks no binding.
117 malformed read-only snapshot; test_surface_parity.py:332 has no write traps.
"""

import copy
from types import SimpleNamespace

import pytest

from claude_sessions import hooks, provision as p


def account(tmp_path, name, **kwargs):
    row = {'name': name, 'dir': str(tmp_path / name), 'marketplaces': {},
           'plugins': set(), 'hooks': {}, 'n_hooks': 0, 'agents': {}, 'skills': {},
           'statusline': False, 'claude_md': False,
           'claude_md_path': str(tmp_path / name / 'CLAUDE.md')}
    row.update(kwargs)
    return row


@pytest.fixture
def plan(monkeypatch):
    def run(*rows):
        monkeypatch.setattr(hooks, 'account_dirs', lambda: [(r['name'], r['dir']) for r in rows])
        states = {r['dir']: r for r in rows}
        monkeypatch.setattr(p, '_state', lambda name, directory: states[directory])
        return p.diff()

    return run


def test_unknown_or_nameless_plugin_cannot_invent_marketplace():
    known = {'known': {'source': 'synthetic'}}
    assert [p._plugin_source(known, key) for key in (
        'bare', '', '@known', 'plugin@missing', 'plugin@', 'a@b@known')] == [
            '', '', '', '', '', 'known']


def test_first_existing_claude_md_is_selected(plan, tmp_path):
    selected = []

    class Observed(dict):
        def __getitem__(self, key):
            value = super().__getitem__(key)
            if key == 'claude_md_path':
                selected.append(value)
            return value

    rows = [Observed(account(tmp_path, 'a')),
            Observed(account(tmp_path, 'b', claude_md=True)),
            Observed(account(tmp_path, 'c', claude_md=True))]
    result = plan(*rows)
    assert selected == [str(tmp_path / 'b' / 'CLAUDE.md')]
    assert result['accounts'][0]['missing']['claude_md'] is True
    assert all(r['missing']['claude_md'] is False for r in result['accounts'][1:])


def test_missing_sets_stay_per_account(plan, tmp_path):
    a = account(tmp_path, 'a', plugins={'z@market'}, marketplaces={'market': {}})
    b = account(tmp_path, 'b', plugins={'bare'})
    before = copy.deepcopy([a, b])
    result = plan(a, b)
    ma, mb = [r['missing'] for r in result['accounts']]
    assert ma['plugins'] == ['bare'] and ma['marketplaces'] == []
    assert mb['plugins'] == ['z@market'] and mb['marketplaces'] == ['market']
    assert [a, b] == before


def test_hook_identity_uses_event_and_full_command(plan, tmp_path):
    prefix = 'x' * 45
    keys = [('Stop', (prefix + 'a',)), ('Stop', (prefix + 'b',)),
            ('Start', (prefix + 'a',))]
    a = account(tmp_path, 'a', hooks=dict.fromkeys(keys, {}), n_hooks=3)
    b = account(tmp_path, 'b', hooks={keys[0]: {}}, n_hooks=1)
    missing = plan(a, b)['accounts'][1]['missing']['hooks']
    assert missing == ['Start ' + 'x' * 40, 'Stop ' + 'x' * 40]


def test_union_conflict_follows_last_account_order(plan, monkeypatch, tmp_path):
    a = account(tmp_path, 'a', plugins={'one@market'}, marketplaces={'market': {'owner': 'a'}})
    b = account(tmp_path, 'b', marketplaces={'market': {'owner': 'b'}})
    seen = []

    def source(markets, key):
        seen.append(copy.deepcopy(markets))
        return markets['market']['owner']

    monkeypatch.setattr(p, '_plugin_source', source)
    assert plan(a, b)['plugin_sources'] == {'one@market': 'b'}
    assert plan(b, a)['plugin_sources'] == {'one@market': 'a'}
    assert seen == [{'market': {'owner': 'b'}}, {'market': {'owner': 'a'}}]


def test_missing_flags_require_available_source(plan, tmp_path):
    a, b = account(tmp_path, 'a'), account(tmp_path, 'b')
    first = plan(a, b)
    assert all(not r['missing']['statusline'] and not r['missing']['claude_md']
               for r in first['accounts'])
    a.update(statusline=True, claude_md=True)
    rows = plan(a, b)['accounts']
    assert (rows[0]['missing']['statusline'], rows[0]['missing']['claude_md']) == (False, False)
    assert (rows[1]['missing']['statusline'], rows[1]['missing']['claude_md']) == (True, True)


def test_have_and_todo_count_categories_once(plan, tmp_path):
    a = account(tmp_path, 'a', marketplaces={'m': {}}, plugins={'p@m', 'q@m'},
                hooks={('Stop', ('run',)): {}}, n_hooks=2, agents={'a.md': 'a'},
                skills={'s': 's'}, statusline=True, claude_md=True)
    rows = plan(a, account(tmp_path, 'b'))['accounts']
    assert rows[0]['have'] == {'marketplaces': 1, 'plugins': 2, 'hooks': 2,
                               'agents': 1, 'skills': 1, 'statusline': True, 'claude_md': True}
    assert rows[0]['todo'] == 0 and rows[1]['todo'] == 8


def test_clean_empty_identical_then_one_missing(plan, tmp_path):
    assert plan() == {'accounts': [], 'clean': True, 'plugin_sources': {}}
    a, b = account(tmp_path, 'a'), account(tmp_path, 'b')
    assert plan(a, b)['clean'] is True
    a['skills']['one'] = 'source'
    assert plan(a, b)['clean'] is False
    b['skills']['one'] = 'other-source'
    assert plan(a, b)['clean'] is True


def test_plugin_sources_sorted_and_only_known(plan, tmp_path):
    a = account(tmp_path, 'a', plugins={'z@known', 'a@unknown', 'bare', '@known'},
                marketplaces={'known': {}})
    sources = plan(a)['plugin_sources']
    assert list(sources) == ['@known', 'a@unknown', 'bare', 'z@known']
    assert list(sources.values()) == ['', '', '', 'known']


def test_malformed_snapshot_fails_without_mutation(plan, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('diff attempted a write')

    monkeypatch.setattr(p, '_c', SimpleNamespace(write_json_atomic=forbidden))
    monkeypatch.setattr(p, 'os', SimpleNamespace(makedirs=forbidden))
    monkeypatch.setattr(p, 'apply', forbidden)
    a = account(tmp_path, 'a', plugins=None)
    original = copy.deepcopy(a)
    with pytest.raises(TypeError):
        plan(a)
    assert a == original
