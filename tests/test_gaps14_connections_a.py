"""Gap tests for connections.build_hierarchy and _signature: the cache hit and
force paths, the signature inputs, node and parent construction, the rolled-up
file totals, dependency-edge filtering and truncation, and a failed cache save.
The project is a small tree under tmp_path; the cache lives under tmp_path too,
and repo discovery and import scanning are faked."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import config as _c
from claude_sessions import connections


def _mkfile(base, rel, content=''):
    p = os.path.join(base, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(content)
    return p


def _by_id(g):
    return {n['id']: n for n in g['nodes']}


@pytest.fixture
def env(monkeypatch, tmp_path):
    wd = tmp_path / 'wd'

    def workdir(_project_path):
        os.makedirs(str(wd), exist_ok=True)
        return str(wd)

    def workfile(_project_path, *parts):
        return os.path.join(str(wd), *parts)

    monkeypatch.setattr(connections._store, 'workdir', workdir)
    monkeypatch.setattr(connections._store, 'workfile', workfile)
    monkeypatch.setattr(connections, '_discover_repos', lambda root, pf: [])
    monkeypatch.setattr(connections, '_all_import_targets', lambda root, files: [])
    return str(wd)


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / 'proj'
    _mkfile(str(root), 'a/x.py', 'x = 1\n')
    _mkfile(str(root), 'a/b/y.py', 'y = 2\n')
    _mkfile(str(root), 'top.py', 'z = 3\n')
    return str(root)


def _cache_file(wd):
    return os.path.join(wd, connections._CACHE_NAME)


def test_cache_hit_serves_the_stored_graph(env, proj):
    first = connections.build_hierarchy(proj)
    with open(_cache_file(env), encoding='utf-8') as f:
        stored = json.load(f)
    stored['nodes'][0]['label'] = 'FROM-CACHE'
    with open(_cache_file(env), 'w', encoding='utf-8') as f:
        json.dump(stored, f)
    again = connections.build_hierarchy(proj)
    assert again['nodes'][0]['label'] == 'FROM-CACHE'
    assert again['meta']['signature'] == first['meta']['signature']


def test_force_bypasses_the_cache_and_rewrites_it(env, proj):
    connections.build_hierarchy(proj)
    with open(_cache_file(env), encoding='utf-8') as f:
        stored = json.load(f)
    stored['nodes'][0]['label'] = 'FROM-CACHE'
    with open(_cache_file(env), 'w', encoding='utf-8') as f:
        json.dump(stored, f)
    fresh = connections.build_hierarchy(proj, force=True)
    assert fresh['nodes'][0]['label'] != 'FROM-CACHE'
    with open(_cache_file(env), encoding='utf-8') as f:
        assert json.load(f)['nodes'][0]['label'] != 'FROM-CACHE'


def test_signature_changes_on_delete_and_on_mtime(tmp_path):
    root = str(tmp_path)
    a = _mkfile(root, 'a.py')
    b = _mkfile(root, 'b.py')
    base = connections._signature(root, [a, b])
    assert base == connections._signature(root, [a, b])
    assert connections._signature(root, [a]) != base
    os.utime(a, (1_000_000_000, 1_000_000_000))
    os.utime(b, (1_000_000_000, 1_000_000_000))
    before = connections._signature(root, [a, b])
    os.utime(b, (1_000_000_100, 1_000_000_100))
    assert connections._signature(root, [a, b]) != before


def test_signature_counts_an_unreadable_file_and_includes_the_version(tmp_path, monkeypatch):
    root = str(tmp_path)
    a = _mkfile(root, 'a.py')
    gone = os.path.join(root, 'gone.py')
    sig = connections._signature(root, [a, gone])
    assert f'|{len([a, gone])}|' in sig
    monkeypatch.setattr(connections, 'MODEL_VERSION', 'vTEST')
    assert connections._signature(root, [a, gone]).startswith('vTEST|')


def test_root_and_first_component_typing(env, proj):
    by = _by_id(connections.build_hierarchy(proj))
    assert by['root:']['type'] == 'root'
    assert by['root:']['label'] == os.path.basename(proj)
    assert by['dir:a']['type'] == 'repo'
    assert by['dir:a/b']['type'] == 'dir'
    assert by['dir:a/b']['depth'] == 2


def test_file_parents_and_depths(env, proj):
    by = _by_id(connections.build_hierarchy(proj))
    assert by['file:top.py']['parent'] == 'root:'
    assert by['file:top.py']['depth'] == 1
    assert by['file:a/x.py']['parent'] == 'dir:a'
    assert by['file:a/b/y.py']['parent'] == 'dir:a/b'
    assert by['file:a/b/y.py']['depth'] == 3


def test_total_files_roll_up_the_tree(env, proj):
    by = _by_id(connections.build_hierarchy(proj))
    assert by['dir:a/b']['total_files'] == 1
    assert by['dir:a']['own_files'] == 0
    assert by['dir:a']['total_files'] == 2
    assert by['root:']['total_files'] == 3


def test_dep_edges_drop_self_and_unknown_and_keep_heaviest(monkeypatch, env, proj):
    pairs = ([('file:a/x.py', 'file:top.py')] * 2
             + [('file:top.py', 'file:top.py'),
                ('file:a/x.py', 'file:nowhere.py'),
                ('file:a/b/y.py', 'file:top.py')])
    monkeypatch.setattr(connections, '_all_import_targets', lambda root, files: pairs)
    g = connections.build_hierarchy(proj)
    assert [(e['source'], e['target'], e['weight']) for e in g['dep_edges']] == [
        ('file:a/x.py', 'file:top.py', 2),
        ('file:a/b/y.py', 'file:top.py', 1)]
    assert g['meta']['truncated'] is False

    monkeypatch.setattr(connections, 'MAX_DEP_EDGES', 1)
    g = connections.build_hierarchy(proj, force=True)
    assert [e['weight'] for e in g['dep_edges']] == [2]
    assert g['meta']['truncated'] is True


def test_walk_cap_sets_truncated(env, proj):
    assert connections.build_hierarchy(proj, force=True)['meta']['truncated'] is False
    g = connections.build_hierarchy(proj, max_files=2, force=True)
    assert g['meta']['truncated'] is True
    assert g['meta']['counts']['files'] == 2


def test_failed_save_still_returns_the_graph(monkeypatch, env, proj):
    monkeypatch.setattr(_c, 'write_json_atomic', lambda *a, **k: False)
    g = connections.build_hierarchy(proj)
    assert 'root:' in _by_id(g)
    assert g['meta']['counts']['files'] == 3
