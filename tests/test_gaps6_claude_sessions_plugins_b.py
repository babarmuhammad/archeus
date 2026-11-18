"""T-1277: claude_sessions/plugins.py:131-244 and 457-487 at 6bbd3b44 (plugin review and provenance cannot bless uninspected content).

Selected candidates, not measured coverage. Ranked, with the closest existing test:
1  475 no local clone and no consent: refused     tests/test_plugins_worktrees.py covers install gating, not this confirm branch
2  468 traversal name stays inside the root       none; strict xfail below
3  487 gate verdict and plan bind the plugin      tests/test_plugins_worktrees.py covers install gating only
4  480 unreadable tree propagates, no consent     none
5  485 agents/ is agent, all else skill, once     none
6  175 same plugin in two scopes stays two rows   tests/test_plugins_worktrees.py:24 fixture, no scope assertion
7  149 malformed marketplace shape not trusted    none; strict xfail below
8  210 packaging names excluded, look-alikes kept tests/test_plugins_worktrees.py:75 covers README and package only
9  239 same name in two plugins: source-order owner tests/test_plugins_worktrees.py:64 checks one owner per name
10 140 corrupt or scalar inventory, file untouched tests/test_plugins_worktrees.py:99 checks no crash, not no rewrite

Branch each test catches: 475 (no-clone confirm branch), 468 (root candidate loop), 487 (gate
return and plan build), 480 (walk error path), 485 (kind classification), 175 (installed row
per entry, clipping), 149 (known_marketplaces source shape, xfail), 210 (_NOT_CONTENT filter),
239 (provenance_index overwrite order), 140 (_read_json default fallback).
"""

import builtins
import json
import os
import types

import pytest

from claude_sessions import config as _c
from claude_sessions import diffview, plugins, skillscan


@pytest.fixture
def review(monkeypatch, tmp_path):
    root = tmp_path / 'market'
    (root / 'plugins').mkdir(parents=True)
    rec = types.SimpleNamespace(root=root, gate=[], gate_result=True, confirms=[],
                                confirm_result=False)

    def gate(root_, plan, source=''):
        rec.gate.append((root_, plan, source))
        return rec.gate_result

    def confirm(old, new, title):
        rec.confirms.append((old, new, title))
        return rec.confirm_result

    monkeypatch.setattr(plugins, 'known_marketplaces', lambda cfg_dir=None: [
        {'name': 'm', 'path': str(root), 'source': '', 'repo': '', 'updated': ''}])
    monkeypatch.setattr(skillscan, 'review_gate', gate)
    monkeypatch.setattr(diffview, 'confirm', confirm)
    return rec


def plugin_tree(root, *files):
    for rel in files:
        path = root / 'plugins' / 'p' / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x\n')


def test_uncloned_plugin_needs_consent_and_is_never_scanned(review):
    review.confirm_result = False
    assert plugins.review_plugin('p', 'm') is False
    assert review.gate == [] and len(review.confirms) == 1
    assert review.confirms[0][2] == 'Install without review?'
    review.confirm_result = True
    assert plugins.review_plugin('p', 'm') is True
    assert review.gate == []


def test_traversal_name_cannot_inspect_outside_the_marketplace(review, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'x.md').write_bytes(b'x\n')
    plugins.review_plugin('../../outside', 'm')
    assert not any(os.path.normpath(c[0]) == os.path.normpath(str(outside))
                   for c in review.gate)


def test_gate_verdict_and_plan_bind_the_selected_plugin(review):
    plugin_tree(review.root, 'plugin.json', 'agents/a.md', 'skills/s/SKILL.md')
    review.gate_result = False
    assert plugins.review_plugin('p', 'm') is False
    (root, plan, source), = review.gate
    assert os.path.normpath(root) == os.path.normpath(str(review.root / 'plugins' / 'p'))
    assert source == 'p@m'
    assert sorted(rel for rel, _, _ in plan) == ['agents/a.md', 'plugin.json',
                                                 'skills/s/SKILL.md']
    assert all(label == f'(plugin p@m) {rel}' for rel, label, _ in plan)


def test_unreadable_tree_propagates_instead_of_consent(review, monkeypatch):
    plugin_tree(review.root, 'plugin.json')

    def unreadable(top, *a, **k):
        raise OSError('synthetic-unreadable')

    monkeypatch.setattr(os, 'walk', unreadable)
    with pytest.raises(OSError, match='synthetic-unreadable'):
        plugins.review_plugin('p', 'm')
    assert review.gate == [] and review.confirms == []


def test_plan_classifies_agents_and_lists_each_file_once_without_opening(review):
    plugin_tree(review.root, 'agents/a.md', 'agents/deep/b.md', 'commands/c.md',
                'agentsx/d.md', 'hooks/h.json', 'skills/s/SKILL.md')

    def no_open(*a, **k):
        raise AssertionError('review_plugin opened a file')

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(builtins, 'open', no_open)
        plugins.review_plugin('p', 'm')
    (root, plan, source), = review.gate
    assert len(plan) == 6
    assert {rel: kind for rel, _, kind in plan} == {
        'agents/a.md': 'agent', 'agents/deep/b.md': 'agent', 'commands/c.md': 'skill',
        'agentsx/d.md': 'skill', 'hooks/h.json': 'skill', 'skills/s/SKILL.md': 'skill'}


def _write_installed(acct, plugins_by_key):
    d = acct / 'plugins'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'installed_plugins.json').write_text(json.dumps({'version': 2, 'plugins': plugins_by_key}),
                                              encoding='utf-8')


def test_same_plugin_in_two_scopes_stays_two_rows_with_their_own_clips(tmp_path, monkeypatch):
    acct = tmp_path / 'acct'
    _write_installed(acct, {'p@m': [
        {'scope': 'user', 'version': '1.2.3-long-version', 'gitCommitSha': '0123456789abcdef',
         'installPath': '/a'},
        {'scope': 'project', 'version': '9.9', 'gitCommitSha': 'fedcba9876543210',
         'installPath': '/b'}]})
    decoy = tmp_path / 'decoy'
    _write_installed(decoy, {'decoy@m': [{'scope': 'user', 'installPath': '/d'}]})
    monkeypatch.setattr(_c, 'config_dir', str(decoy))
    rows = plugins.installed(str(acct))
    assert [(r['key'], r['scope'], r['version'], r['sha'], r['path']) for r in rows] == [
        ('p@m', 'user', '1.2.3-long-v', '0123456789ab', '/a'),
        ('p@m', 'project', '9.9', 'fedcba987654', '/b')]


def test_null_marketplace_entry_is_an_empty_row(tmp_path):
    cfg = tmp_path / 'acct' / 'plugins'
    cfg.mkdir(parents=True)
    (cfg / 'known_marketplaces.json').write_text(json.dumps({
        'ok': None, 'good': {'source': {'source': 'github', 'repo': 'acme/g'}}}), encoding='utf-8')
    rows = {r['name']: r for r in plugins.known_marketplaces(str(tmp_path / 'acct'))}
    assert rows['good']['repo'] == 'acme/g'
    assert rows['ok']['repo'] == '' and rows['ok']['source'] == ''


def test_malformed_source_shape_is_not_trusted_metadata(tmp_path):
    cfg = tmp_path / 'acct' / 'plugins'
    cfg.mkdir(parents=True)
    (cfg / 'known_marketplaces.json').write_text(json.dumps({
        'good': {'source': {'source': 'github', 'repo': 'acme/g'}, 'installLocation': '/g'},
        'bad': {'source': 'https://evil.example/x'}}), encoding='utf-8')
    rows = {r['name']: r for r in plugins.known_marketplaces(str(tmp_path / 'acct'))}
    assert rows['good']['repo'] == 'acme/g'
    assert rows.get('bad', {}).get('repo', '') == ''


def test_packaging_names_are_excluded_and_look_alikes_kept(tmp_path):
    install = tmp_path / 'inst'
    for rel in ('skills/Readme.md', 'skills/license/x.md', 'skills/readme-tools/SKILL.md',
                'skills/package-helper/SKILL.md', 'agents/README.md', 'agents/package.json',
                'agents/packager.md', 'agents/tsconfig.json', 'agents/tsconfig-extra.md',
                'agents/notes.txt', '.mcp.json'):
        path = install / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'{}\n' if rel.endswith('.json') else b'x\n')
    assert plugins.contents(str(install)) == {
        'skill': ['package-helper', 'readme-tools'],
        'agent': ['packager', 'tsconfig-extra'],
        'mcp': ['(mcp servers)'],
    }


def test_same_content_name_in_two_plugins_has_source_order_owner(monkeypatch):
    installed = [{'key': 'a@m', 'path': '/pa'}, {'key': 'b@m', 'path': '/pb'}]
    trees = {'/pa': {'skill': ['shared'], 'hook': ['shared']},
             '/pb': {'skill': ['shared'], 'agent': ['shared']}}
    monkeypatch.setattr(plugins, 'installed', lambda cfg_dir=None: installed)
    monkeypatch.setattr(plugins, 'contents', lambda path: trees[path])
    idx = plugins.provenance_index('ignored')
    assert idx['skill'] == {'shared': 'b@m'}
    assert idx['hook'] == {'shared': 'a@m'}
    assert idx['agent'] == {'shared': 'b@m'}


def test_corrupt_or_scalar_inventory_falls_back_without_rewriting(tmp_path):
    bad = tmp_path / 'bad'
    (bad / 'plugins').mkdir(parents=True)
    (bad / 'plugins' / 'installed_plugins.json').write_bytes(b'{not json')
    (bad / 'plugins' / 'known_marketplaces.json').write_bytes(b'[1, 2]')
    bom = tmp_path / 'bom'
    (bom / 'plugins').mkdir(parents=True)
    (bom / 'plugins' / 'installed_plugins.json').write_bytes(
        b'\xef\xbb\xbf' + json.dumps({'plugins': {'p@m': [{'scope': 'user'}]}}).encode())
    (bom / 'plugins' / 'known_marketplaces.json').write_bytes(b'42')

    def snapshot():
        return {str(f): f.read_bytes() for f in tmp_path.rglob('*') if f.is_file()}

    before = snapshot()
    assert plugins.installed(str(bad)) == []
    assert plugins.known_marketplaces(str(bad)) == []
    assert [r['key'] for r in plugins.installed(str(bom))] == ['p@m']
    assert plugins.known_marketplaces(str(bom)) == []
    assert snapshot() == before
