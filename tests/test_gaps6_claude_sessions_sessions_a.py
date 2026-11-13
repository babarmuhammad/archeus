"""T-1286: claude_sessions/sessions.py:118-248 at 6bbd3b44; current branches below.

Candidate probes are not measured coverage. Selected, refusal first:
139 extra-key disk rejection: test_session_cache.py:128 checks missing keys only.
162 stale stat refusal: test_sessions.py:19 has no warm authority.
185 fold exception: test_session_cache.py:52 exercises successful publication.
181 harness selection: test_harnesses.py checks routing, not parser store order.
164 independent key dimensions: test_session_cache.py:70 changes both dimensions.
183 torn replay order: test_sessions.py:56 has garbage, not a torn title suffix.
178 isolated mutable stats: test_sessions.py:23 tests one transcript.
235 synthetic plus repeated usage: test_sessions.py:45 has no model composition.
205 timestamp extrema: test_sessions.py:23 does not assert extrema/last context.
218 malformed nested message: test_sessions.py:56 uses invalid JSON only.
"""

import copy
import json
from types import SimpleNamespace

import pytest

from claude_sessions import sessions as s, stats


@pytest.fixture
def replay(monkeypatch):
    disk = {}
    monkeypatch.setattr(s, '_info_cache', {})
    monkeypatch.setattr(stats, '_load_disk_cache', lambda: disk)
    monkeypatch.setattr(stats, '_cache_dirty', False)
    monkeypatch.setattr(s._harnesses, 'of_path', lambda p: {'id': 'claude'})
    monkeypatch.setattr(s._harnesses, 'impl', lambda kind, hid: s._fold_claude)
    return disk


def test_extra_disk_field_forces_replay(replay, monkeypatch, tmp_path):
    p = str(tmp_path / 'a.jsonl')
    monkeypatch.setattr(s, 'os', SimpleNamespace(stat=lambda p: SimpleNamespace(
        st_mtime_ns=1, st_size=2)))
    replay[p] = {'key': [1, 2, s._STATS_SCHEMA],
                 'stats': dict(copy.deepcopy(s._EMPTY_STATS), obsolete=True)}
    seen = []
    monkeypatch.setattr(s._t, 'iter_json', lambda p: seen.append(p) or iter([
        {'type': 'ai-title', 'title': 'fresh'}]))
    assert s._parse_session(p)['title'] == 'fresh'
    assert seen == [p]
    assert 'obsolete' not in replay[p]['stats']


def test_stat_failure_never_serves_warm_authority(replay, monkeypatch, tmp_path):
    p = str(tmp_path / 'missing')
    s._info_cache[p] = ((1, 2, s._STATS_SCHEMA), {'models': ['remote']})
    replay[p] = {'stats': {'models': ['remote']}}

    def fail(path):
        raise OSError('stat fault')

    monkeypatch.setattr(s, 'os', SimpleNamespace(stat=fail))
    monkeypatch.setattr(s, '_disk_cache_hit', lambda *a: pytest.fail('disk consulted'))
    got = s._parse_session(p)
    assert got == s._EMPTY_STATS and got is not s._EMPTY_STATS
    assert got['models'] == [] and got['usage_by_model'] == {}


def test_fold_failure_publishes_neither_cache(replay, monkeypatch, tmp_path):
    p = tmp_path / 'a.jsonl'
    p.write_text('{}\n', encoding='utf-8')

    def fail(obj, state):
        state['models'].append('partial')
        raise RuntimeError('fold fault')

    monkeypatch.setattr(s._harnesses, 'impl', lambda *a: fail)
    with pytest.raises(RuntimeError, match='fold fault'):
        s._parse_session(str(p))
    assert s._info_cache == {} and replay == {}
    assert stats._cache_dirty is False


def test_path_harness_owns_fold_and_store_order(replay, monkeypatch, tmp_path):
    p = tmp_path / 'a.jsonl'
    p.write_text('{}\n{}\n', encoding='utf-8')
    calls = []
    monkeypatch.setattr(s._harnesses, 'of_path', lambda path: {'id': 'alternate'})

    def select(kind, hid):
        calls.append((kind, hid))

        def fold(obj, state):
            assert str(p) not in s._info_cache and str(p) not in replay
            state['count'] += 7

        return fold

    monkeypatch.setattr(s._harnesses, 'impl', select)
    assert s._parse_session(str(p))['count'] == 14
    assert calls == [('fold', 'alternate')]
    assert replay[str(p)]['stats']['count'] == 14


def test_each_key_dimension_invalidates_but_exact_hit_skips_disk(replay, monkeypatch, tmp_path):
    p = str(tmp_path / 'a')
    clock = SimpleNamespace(st_mtime_ns=1, st_size=2)
    monkeypatch.setattr(s, 'os', SimpleNamespace(stat=lambda p: clock))
    reads = []
    monkeypatch.setattr(s._t, 'iter_json', lambda p: reads.append(p) or iter([]))
    first = s._parse_session(p)
    with monkeypatch.context() as patch:
        patch.setattr(s, '_disk_cache_hit', lambda *a: pytest.fail('memory miss'))
        assert s._parse_session(p) is first
    clock.st_mtime_ns = 3
    second = s._parse_session(p)
    clock.st_size = 4
    third = s._parse_session(p)
    assert first is not second and second is not third
    assert reads == [p, p, p]


def test_torn_title_keeps_complete_ordered_replay(replay, tmp_path):
    p = tmp_path / 'a.jsonl'
    rows = [{'type': 'ai-title', 'title': 'first'},
            {'type': 'ai-title', 'title': 'second'},
            {'role': 'user', 'content': 'complete user text'}]
    p.write_bytes(('\n'.join(map(json.dumps, rows)) + '\n{"title":').encode())
    got = s._parse_session(str(p))
    assert (got['title'], got['preview'], got['count']) == (
        'first', 'complete user text', 1)
    assert replay[str(p)]['stats'] == got


def test_cold_sessions_own_mutable_usage(replay, tmp_path):
    paths = [tmp_path / name for name in ('a.jsonl', 'b.jsonl')]
    for p in paths:
        p.write_text('{}\n', encoding='utf-8')
    a, b = [s._parse_session(str(p)) for p in paths]
    a['models'].append('private')
    a['usage_by_model']['private'] = {'in': 9}
    assert b['models'] == [] and b['usage_by_model'] == {}
    assert s._EMPTY_STATS['models'] == [] and s._EMPTY_STATS['usage_by_model'] == {}


def test_synthetic_usage_excluded_real_usage_accumulates(replay):
    state = copy.deepcopy(s._EMPTY_STATS)
    for model in ('<synthetic>', 'real', 'real'):
        s._fold_claude({'message': {'role': 'assistant', 'model': model,
                                   'usage': {'input_tokens': 2, 'output_tokens': None,
                                             'cache_read_input_tokens': 3,
                                             'cache_creation_input_tokens': 4}}}, state)
    assert state['models'] == ['real'] and state['count'] == 3
    assert state['usage_by_model'] == {
        'real': {'in': 4, 'out': 0, 'cache_read': 6, 'cache_create': 8}}


def test_extrema_ignore_invalid_and_context_uses_last_nonempty(replay, monkeypatch):
    monkeypatch.setattr(s, '_iso_to_epoch', lambda ts: {'late': 9, 'early': 2}.get(ts))
    state = copy.deepcopy(s._EMPTY_STATS)
    for obj in ({'timestamp': 'late', 'gitBranch': 'a', 'cwd': 'one'},
                {'timestamp': 'early', 'gitBranch': 'b', 'cwd': 'two'},
                {'timestamp': 'bad', 'gitBranch': '', 'cwd': ''}):
        s._fold_claude(obj, state)
    assert (state['first_ts'], state['last_ts'], state['branch'], state['cwd']) == (
        2, 9, 'b', 'two')


@pytest.mark.xfail(strict=True, reason='Non-dict message aborts later replay: claude_sessions/sessions.py:218')
def test_api_error_and_malformed_message_do_not_poison_later_replay(replay, tmp_path):
    p = tmp_path / 'a.jsonl'
    rows = [{'isApiErrorMessage': True}, {'message': ['malformed']},
            {'role': 'user', 'content': 'later complete message'}]
    p.write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')
    got = s._parse_session(str(p))
    assert got['api_errors'] == 1 and got['preview'] == 'later complete message'
