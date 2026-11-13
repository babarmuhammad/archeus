"""T-1299: claude_sessions/clientstate.py:36-173; candidate gaps, not coverage.

Ranked final probes and closest assertions:
1 :50 test_live_reads_never_request_quarantine; test_clientstate.test_a_corrupt_client_json_does_not_crash_the_page checks result, not load contract.
2 :61/:64 test_project_selection_is_account_scoped; test_a_project_is_found_by_its_real_path tests one Windows account only.
3 :63 test_malformed_projects_are_empty; test_an_unknown_project_is_empty_not_an_error tests empty dict only.
4 :135/:136 test_ttl_boundary_and_refresh; closest test_clientstate usage tests do not exercise hook cache.
5 :136 test_future_cache_requires_refresh; same closest tests lack rewound clock.
6 :134 test_cache_paths_are_account_scoped; test_multihome.test_claude_homes_still_come_from_the_accounts_list checks enumeration, not activity.
7 :152 test_only_newest_files_are_opened; closest test_clientstate usage tests do not bound transcript reads.
8 :160 test_hook_shapes_and_session_dedup; same closest tests lack attachment folding.
9 :166 test_last_hit_uses_newest_mtime; same closest tests lack cross-session last-hit age.
10 :171/:172 test_failed_cache_write_recomputes; same closest tests lack cache write failures.
"""

import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from claude_sessions import clientstate, store


@pytest.fixture
def activity(monkeypatch, tmp_path):
    state = SimpleNamespace(now=2000000, cache={}, rows={}, files={}, events=[])
    state.load_original = clientstate.jsonstore.load
    state.account = str(tmp_path / 'acct')
    state.root = str(tmp_path / 'projects')
    state.project = os.path.join(state.root, 'project')
    monkeypatch.setattr(clientstate, '_path',
                        lambda name, cfgdir=None: os.path.join(cfgdir or state.account, name))
    monkeypatch.setattr(clientstate.jsonstore, 'load',
                        lambda path, **kwargs: state.cache.get(path, {}))
    monkeypatch.setattr(clientstate, 'time', SimpleNamespace(time=lambda: state.now))
    monkeypatch.setattr(store, 'projects_root', lambda cfgdir: state.root)
    state.walk = Mock(return_value=['project'])
    monkeypatch.setattr(clientstate, '_listdir', state.walk)

    def listdir(path):
        assert path == state.project
        state.events.append(('list', path))
        return list(state.files) + ['notes.txt']

    def mtime(path):
        state.events.append(('stat', path))
        return state.files[os.path.basename(path)]

    monkeypatch.setattr(clientstate, 'os', SimpleNamespace(
        path=SimpleNamespace(join=os.path.join, getmtime=mtime), listdir=listdir))

    def read(path, **kwargs):
        assert kwargs == {'prefilter': 'hook_success'}
        state.events.append(('read', path))
        return iter(state.rows.get(os.path.basename(path), []))

    state.read = Mock(side_effect=read)
    monkeypatch.setattr(clientstate.transcripts, 'iter_json', state.read)
    state.write = Mock(return_value=False)
    monkeypatch.setattr(clientstate._c, 'write_json_atomic', state.write)
    return state


def hook(name='sample'):
    return {'attachment': {'type': 'hook_success', 'hookName': name}}


def test_live_reads_never_request_quarantine(activity, monkeypatch, tmp_path):
    account = tmp_path / 'live'
    account.mkdir()
    path = account / '.claude.json'
    load = Mock(wraps=activity.load_original)
    quarantine = Mock(side_effect=AssertionError('live file must stay'))
    monkeypatch.setattr(clientstate.jsonstore, 'load', load)
    monkeypatch.setattr(clientstate.jsonstore, '_quarantine', quarantine)
    for raw in (b'{"projects":', b'[]', b'{"projects":{}}'):
        path.write_bytes(raw)
        assert clientstate.client_json(str(account)) == (
            {'projects': {}} if raw == b'{"projects":{}}' else {})
        assert path.read_bytes() == raw
        assert list(account.iterdir()) == [path]
    assert load.call_count == 3
    for call in load.call_args_list:
        assert call.args == (str(path),)
        assert call.kwargs == {'expect': dict, 'quarantine': False}
    quarantine.assert_not_called()
    activity.write.assert_not_called()
    activity.walk.assert_not_called()

def test_project_selection_is_account_scoped(activity, monkeypatch):
    account_a, account_b = activity.account, activity.account + '-b'
    seen = []
    records = {
        account_a: {'projects': {'alias': {'account': 'a'}, 'other': {'secret': 'foreign'}}},
        account_b: {'projects': {'alias': {'account': 'b'}}},
    }
    monkeypatch.setattr(clientstate, 'client_json', lambda cfgdir: records[cfgdir])

    def norm(path):
        seen.append(path)
        return 'selected' if path in ('alias', 'requested') else path

    monkeypatch.setattr(clientstate, '_norm', norm)
    assert clientstate.project_state('requested', account_a) == {'account': 'a'}
    assert clientstate.project_state('requested', account_b) == {'account': 'b'}
    assert clientstate.project_state('missing', account_a) == {}
    assert 'requested' in seen and 'alias' in seen and 'other' in seen
    records[account_a]['projects']['alias'] = ['bad row']
    assert clientstate.project_state('requested', account_a) == {}


def test_malformed_projects_are_empty(activity, monkeypatch):
    monkeypatch.setattr(clientstate, '_norm', lambda path: path)
    for projects in (['bad'], 'bad', 1):
        monkeypatch.setattr(clientstate, 'client_json',
                            lambda cfgdir, value=projects: {'projects': value})
        assert clientstate.project_state('requested', activity.account) == {}


def test_ttl_boundary_and_refresh(activity):
    path = os.path.join(activity.account, 'archeus-activity.json')
    cached = {'sessions': 17, 'hits': {'cached': {}}, 'at': activity.now - 899.5}
    activity.cache[path] = cached
    assert clientstate.hook_activity(activity.account) == {
        'sessions': 17, 'hits': {'cached': {}}}
    activity.walk.assert_not_called()
    cached['at'] = activity.now - clientstate.ACTIVITY_TTL
    assert clientstate.hook_activity(activity.account) == {'sessions': 0, 'hits': {}}
    assert activity.walk.call_count == 1
    cached['at'] = activity.now
    assert clientstate.hook_activity(activity.account, refresh=True) == {
        'sessions': 0, 'hits': {}}
    assert activity.walk.call_count == 2
    assert activity.write.call_count == 2


def test_future_cache_requires_refresh(activity):
    path = os.path.join(activity.account, 'archeus-activity.json')
    activity.cache[path] = {'at': activity.now + 1000000, 'sessions': 99, 'hits': {}}
    assert clientstate.hook_activity(activity.account) == {'sessions': 0, 'hits': {}}
    activity.walk.assert_called_once_with(activity.root)


def test_cache_paths_are_account_scoped(activity):
    account_b = activity.account + '-b'
    for account, count in ((activity.account, 2), (account_b, 9)):
        activity.cache[os.path.join(account, 'archeus-activity.json')] = {
            'at': activity.now, 'sessions': count,
            'hits': {'sample': {'sessions': count, 'last_days': 0}}}
    assert clientstate.hook_activity(activity.account)['hits']['sample']['sessions'] == 2
    assert clientstate.hook_activity(account_b)['hits']['sample']['sessions'] == 9
    activity.walk.assert_not_called()
    activity.read.assert_not_called()
    activity.write.assert_not_called()


def test_only_newest_files_are_opened(activity):
    activity.files = {'old.jsonl': 1, 'middle.jsonl': 2, 'new.jsonl': 3}
    out = clientstate.hook_activity(activity.account, limit=2)
    assert out == {'sessions': 2, 'hits': {}}
    assert [os.path.basename(call.args[0]) for call in activity.read.call_args_list] == [
        'new.jsonl', 'middle.jsonl']
    assert [event[0] for event in activity.events] == [
        'list', 'stat', 'stat', 'stat', 'read', 'read']


def test_hook_shapes_and_session_dedup(activity):
    activity.files = {'a.jsonl': activity.now, 'b.jsonl': activity.now - 10}
    activity.rows = {
        'a.jsonl': [{}, {'attachment': []}, {'attachment': 'bad'},
                    {'attachment': {'type': 'other', 'hookName': 'foreign'}},
                    hook(), hook()],
        'b.jsonl': [hook(), hook()],
    }
    assert clientstate.hook_activity(activity.account) == {
        'sessions': 2, 'hits': {'sample': {'sessions': 2, 'last_days': 0}}}


def test_last_hit_uses_newest_mtime(activity):
    activity.files = {'old.jsonl': activity.now - 5 * 86400,
                      'new.jsonl': activity.now - 2 * 86400,
                      'empty.jsonl': activity.now}
    activity.rows = {'old.jsonl': [hook()], 'new.jsonl': [hook()]}
    assert clientstate.hook_activity(activity.account) == {
        'sessions': 3, 'hits': {'sample': {'sessions': 2, 'last_days': 2}}}


def test_failed_cache_write_recomputes(activity):
    activity.files = {'a.jsonl': activity.now}
    activity.rows = {'a.jsonl': [hook()]}
    first = clientstate.hook_activity(activity.account)
    activity.rows['a.jsonl'] = []
    second = clientstate.hook_activity(activity.account)
    assert first == {'sessions': 1, 'hits': {'sample': {'sessions': 1, 'last_days': 0}}}
    assert second == {'sessions': 1, 'hits': {}}
    assert activity.walk.call_count == activity.read.call_count == activity.write.call_count == 2
    assert activity.cache == {}
    path, value = activity.write.call_args.args
    assert path == os.path.join(activity.account, 'archeus-activity.json')
    assert value == dict(second, at=activity.now)

