"""T-1340: the highest-risk uncovered branches of claude_sessions/connections.py lines 321-350
(_cache_path, _load_cache, _save_cache), at tip 6b1a30b8. Re-located at worktree tip
4e253ad5: _cache_path 321-326, _load_cache 328-337, _save_cache 339-350.

Selected branches, denial and fail-closed first, then boundaries, then error paths:
1. connections.py:322-325 project_path wins; proj_folder is used only when project_path is
   empty; both empty gives ''.
2. connections.py:330-336 a missing cache returns None; a corrupt JSON cache returns None.
3. connections.py:341-342 an empty base is skipped without touching the store.
4. connections.py:344-348 the first base whose workdir is writable is used and True returned.
5. connections.py:347-349 a first base whose workdir raises falls through to proj_folder.
6. connections.py:350 every base failing returns False and writes nothing.
7. connections.py:345-346 a graph round-trips through JSON unchanged (control).
8. connections.py:332-333 a cache file holding a JSON dict is returned as that dict (control).
9. connections.py:328-329 PREMISE: load reads the same place save writes. Strict xfail: when
   save falls back to proj_folder, load still reads only project_path and misses the cache.
10. connections.py:344-346 PREMISE: a non-serialisable graph must not truncate the previous
    cache. Strict xfail: open('w') runs before json.dump, so the old cache is lost; the
    TypeError is swallowed by the except at 348 rather than raised.

Seam: connections._store.workfile and workdir are replaced with tmp_path-backed fakes; one
base can be made to raise on purpose. No real project folder, no subprocess, no network.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import connections
from claude_sessions import store as _store


class Stores:
    def __init__(self):
        self.fail = set()
        self.calls = []


@pytest.fixture
def stores(monkeypatch):
    s = Stores()

    def workfile(base, *parts):
        return os.path.join(base, _store.WORKDIR, *parts)

    def workdir(base):
        s.calls.append(base)
        if not base or base in s.fail:
            raise OSError('synthetic: base not writable')
        d = os.path.join(base, _store.WORKDIR)
        os.makedirs(d, exist_ok=True)
        return d

    monkeypatch.setattr(connections._store, 'workfile', workfile)
    monkeypatch.setattr(connections._store, 'workdir', workdir)
    return s


def _cache_file(base):
    return os.path.join(base, _store.WORKDIR, connections._CACHE_NAME)


def _graph():
    return {'nodes': [{'id': 'a', 'n': 3, 'tags': ['x', 'ü']}], 'meta': {'ok': True, 'none': None}}


def test_cache_path_prefers_project_then_folder(stores, tmp_path):
    pp, pf = str(tmp_path / 'project'), str(tmp_path / 'folder')
    assert connections._cache_path(pp, pf) == _cache_file(pp)
    assert connections._cache_path('', pf) == _cache_file(pf)
    assert connections._cache_path('', '') == ''
    assert connections._cache_path(None, None) == ''


def test_load_cache_missing_or_corrupt_returns_none(stores, tmp_path):
    pp = str(tmp_path / 'project')
    assert connections._load_cache(pp, '') is None
    os.makedirs(os.path.dirname(_cache_file(pp)))
    with open(_cache_file(pp), 'w', encoding='utf-8') as f:
        f.write('{"nodes": [')
    assert connections._load_cache(pp, '') is None


def test_save_skips_an_empty_base(stores, tmp_path):
    pf = str(tmp_path / 'folder')
    assert connections._save_cache(_graph(), '', pf) is True
    assert stores.calls == [pf]
    assert os.path.isfile(_cache_file(pf))


def test_save_uses_the_first_writable_base(stores, tmp_path):
    pp, pf = str(tmp_path / 'project'), str(tmp_path / 'folder')
    assert connections._save_cache(_graph(), pp, pf) is True
    assert os.path.isfile(_cache_file(pp))
    assert not os.path.exists(_cache_file(pf))
    assert stores.calls == [pp]


def test_save_falls_through_to_folder_when_first_base_raises(stores, tmp_path):
    pp, pf = str(tmp_path / 'project'), str(tmp_path / 'folder')
    stores.fail.add(pp)
    assert connections._save_cache(_graph(), pp, pf) is True
    assert not os.path.exists(_cache_file(pp))
    assert os.path.isfile(_cache_file(pf))
    assert stores.calls == [pp, pf]


def test_save_returns_false_when_every_base_fails(stores, tmp_path):
    pp, pf = str(tmp_path / 'project'), str(tmp_path / 'folder')
    stores.fail.update({pp, pf})
    assert connections._save_cache(_graph(), pp, pf) is False
    assert not os.path.exists(_cache_file(pp))
    assert not os.path.exists(_cache_file(pf))
    assert stores.calls == [pp, pf]


def test_graph_round_trips_through_the_cache(stores, tmp_path):
    pp = str(tmp_path / 'project')
    assert connections._save_cache(_graph(), pp, '') is True
    assert connections._load_cache(pp, '') == _graph()


def test_cache_file_holding_a_dict_loads_as_that_dict(stores, tmp_path):
    pp = str(tmp_path / 'project')
    os.makedirs(os.path.dirname(_cache_file(pp)))
    with open(_cache_file(pp), 'w', encoding='utf-8') as f:
        json.dump({'k': [1, 2]}, f)
    got = connections._load_cache(pp, '')
    assert type(got) is dict
    assert got == {'k': [1, 2]}


def test_load_finds_the_cache_save_wrote_through_the_fallback(stores, tmp_path):
    pp, pf = str(tmp_path / 'project'), str(tmp_path / 'folder')
    stores.fail.add(pp)
    assert connections._save_cache(_graph(), pp, pf) is True
    assert connections._load_cache(pp, pf) == _graph()


def test_unserialisable_graph_keeps_the_previous_cache(stores, tmp_path):
    pp = str(tmp_path / 'project')
    assert connections._save_cache(_graph(), pp, '') is True
    assert connections._save_cache({'bad': {1, 2}}, pp, '') is False
    assert connections._load_cache(pp, '') == _graph()
