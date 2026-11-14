"""T-1329: claude_sessions/omniroute.py lines 318-408 (dead and alive model cache
reads and writes, including corrupt cache files); candidate gaps, not coverage.

Ranked final probes (denial/fail-closed first, then boundaries, then error paths):
1  :400-404  test_record_result_ignores_timeout_and_error           (closest: test_omniroute.py record_result_learns_from_a_real_turn, timeout only)
2  :405-407  test_record_result_unchanged_status_keeps_timestamp    (closest: test_omniroute.py record_result_is_a_noop_when_status_unchanged)
3  :378-379  test_save_dead_stamps_gone_auth_and_ignores_error      (closest: test_omniroute.py dead_cache_roundtrip_and_recovery)
4  :380-381  test_save_dead_timeout_pops_existing_verdict           (closest: test_omniroute.py dead_cache_roundtrip_and_recovery, timeout never present)
5  :324-326  test_load_dead_excludes_exact_age_and_non_dict_rows    (closest: test_omniroute.py dead_cache_expires)
6  :334-336  test_load_alive_returns_only_fresh_works_rows          (closest: test_omniroute.py record_result_learns_from_a_real_turn)
7  :348-361  test_order_fairly_alive_head_then_round_robin           (closest: test_omniroute.py order_fairly_* tests, each half alone)
8  :372-377  test_save_dead_corrupt_file_read_as_empty_and_rewritten (closest: none)
9  :383-387  test_save_dead_write_failure_is_swallowed               (closest: none; control)
10 :372-377  test_save_dead_list_cache_does_not_crash               (PREMISE, strict xfail: list cache raises TypeError at :377)

Seams: omniroute.dead_path -> tmp_path file, time.time -> fake clock,
omniroute._DEAD_TTL / _ALIVE_TTL -> small values. No network, no subprocess, no
real settings dir or home reads. Synthetic cache content only.
"""

import json
import time

import pytest

from claude_sessions import omniroute


@pytest.fixture
def cache(monkeypatch, tmp_path):
    path = tmp_path / 'omniroute-dead.json'
    clock = {'now': 1_000_000.0}
    monkeypatch.setattr(omniroute, 'dead_path', lambda: str(path))
    monkeypatch.setattr(omniroute, '_DEAD_TTL', 100)
    monkeypatch.setattr(omniroute, '_ALIVE_TTL', 60)
    monkeypatch.setattr(time, 'time', lambda: clock['now'])
    return path, clock


def _write(path, data):
    path.write_text(json.dumps(data), encoding='utf-8')


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_record_result_ignores_timeout_and_error(cache):
    path, _ = cache
    omniroute.record_result('m1', False, 'request timed out')
    omniroute.record_result('m2', False, 'boom')
    assert not path.exists()
    assert omniroute.load_dead() == {}
    assert omniroute.load_alive() == []


def test_record_result_unchanged_status_keeps_timestamp(cache):
    path, clock = cache
    omniroute.record_result('m', False, 'HTTP 410: gone')
    stamped = _read(path)['m']['ts']
    clock['now'] += 50
    omniroute.record_result('m', False, 'HTTP 410: gone')
    assert _read(path)['m'] == {'status': 'gone', 'ts': stamped}
    clock['now'] = stamped + 100
    assert omniroute.load_dead() == {}


def test_save_dead_stamps_gone_auth_and_ignores_error(cache):
    path, clock = cache
    old = {'status': 'gone', 'ts': clock['now'] - 500}
    _write(path, {'a': old})
    omniroute.save_dead([{'id': 'a', 'status': 'error', 'ok': False},
                         {'id': 'b', 'status': 'auth', 'ok': False}])
    data = _read(path)
    assert data['a'] == old
    assert data['b'] == {'status': 'auth', 'ts': clock['now']}


def test_save_dead_timeout_pops_existing_verdict(cache):
    path, clock = cache
    _write(path, {'a': {'status': 'gone', 'ts': clock['now']},
                  'keep': {'status': 'auth', 'ts': clock['now']}})
    omniroute.save_dead([{'id': 'a', 'status': 'timeout', 'ok': False}])
    assert set(_read(path)) == {'keep'}


def test_load_dead_excludes_exact_age_and_non_dict_rows(cache):
    path, clock = cache
    now = clock['now']
    _write(path, {'edge': {'status': 'gone', 'ts': now - 100},
                  'young': {'status': 'gone', 'ts': now - 99},
                  'auth_ok': {'status': 'auth', 'ts': now},
                  'limited': {'status': 'limited', 'ts': now},
                  'no_ts': {'status': 'gone'},
                  'junk': 'gone',
                  'listy': ['gone']})
    assert omniroute.load_dead() == {'young': 'gone', 'auth_ok': 'auth'}


def test_load_alive_returns_only_fresh_works_rows(cache):
    path, clock = cache
    now = clock['now']
    _write(path, {'fresh': {'status': 'works', 'ts': now - 59},
                  'edge': {'status': 'works', 'ts': now - 60},
                  'gone_row': {'status': 'gone', 'ts': now},
                  'junk': 'works'})
    assert omniroute.load_alive() == ['fresh']


def test_order_fairly_alive_head_then_round_robin(cache):
    ids = ['a/1', 'a/2', 'a/3', 'b/1', 'c/1']
    assert omniroute.order_fairly(ids, alive=['a/2', 'zz/9']) == \
        ['a/2', 'a/1', 'b/1', 'c/1', 'a/3']


def test_save_dead_corrupt_file_read_as_empty_and_rewritten(cache):
    path, clock = cache
    path.write_text('{not json', encoding='utf-8')
    omniroute.save_dead([{'id': 'n', 'ok': True}])
    assert _read(path) == {'n': {'status': 'works', 'ts': clock['now']}}


def test_save_dead_write_failure_is_swallowed(cache, monkeypatch, tmp_path):
    blocker = tmp_path / 'blocker'
    blocker.write_text('x', encoding='utf-8')
    monkeypatch.setattr(omniroute, 'dead_path', lambda: str(blocker / 'omniroute-dead.json'))
    omniroute.save_dead([{'id': 'a', 'ok': True}])
    assert blocker.read_text(encoding='utf-8') == 'x'


@pytest.mark.xfail(strict=True, reason=(
    'claude_sessions/omniroute.py:377 save_dead indexes a JSON list read at :372 '
    '(only the read is inside try/except); TypeError escapes to record_result at :408'))
def test_save_dead_list_cache_does_not_crash(cache):
    path, _ = cache
    path.write_text('[{"id": "old"}]', encoding='utf-8')
    omniroute.save_dead([{'id': 'a', 'ok': True}])
    assert _read(path)['a']['status'] == 'works'
