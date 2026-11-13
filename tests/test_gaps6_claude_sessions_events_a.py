"""T-1292: claude_sessions/events.py:64-140 at 6bbd3b44; same current slice.

Selected probes, not measured coverage; closest test_events.py assertions:
100 cut-crossing credentials; :234 has credentials but no cut boundary.
117 src/proj redaction; :234 only checks msg/detail.
109 failed append retry; :83 checks False only, not subsequent retry.
107 exact dedupe boundary/backwards recovery; :98 has no fake clock boundary.
104 source/decimal/integer composition; :137/:164 test dimensions separately.
112 oldest 250 memo eviction; :98 never fills memo.
103 invalid level/redacted-empty no I/O; :45 uses supported warn only.
122 complete append before rotation fault; :83 faults path, not rotation.
140 torn tail/newest valid limit; :69 spies on reader, no torn suffix.
139 reader failure no recursion; :114 tests absent file only.
"""

import builtins
import json

import pytest

from claude_sessions import events as e, transcripts


@pytest.fixture
def audit(monkeypatch, tmp_path):
    p = tmp_path / 'events.jsonl'
    clock = [1000.0]
    monkeypatch.setattr(e, 'path', lambda: str(p))
    monkeypatch.setattr(e, '_recent', {})
    monkeypatch.setattr(e.time, 'time', lambda: clock[0])
    monkeypatch.setattr(e, '_rotate', lambda path: None)
    return p, clock


def test_cut_crossing_secrets_redacted_before_clipping(audit):
    p, _ = audit
    token = 'sk-ant-' + 'A' * 50
    assert e.record('source', ' ' + 'm' * 190 + ' ' + token,
                    detail='d' * 990 + ' ' + token)
    row = json.loads(p.read_text(encoding='utf-8'))
    assert row['msg'] == ('m' * 190 + ' [redacted]')[:200]
    assert row['detail'] == ('d' * 990 + ' [redacted]')[:1000]
    assert 'sk-ant-' not in p.read_text(encoding='utf-8')


@pytest.mark.xfail(strict=True, reason='src/proj persist credentials without redaction: claude_sessions/events.py:114-117')
def test_source_and_project_cannot_persist_credentials(audit):
    p, _ = audit
    token = 'sk-' + 'A' * 20
    assert e.record(token, 'failure', proj=token)
    raw = p.read_text(encoding='utf-8')
    assert token not in raw
    row = json.loads(raw)
    assert row['src'] == row['proj'] == '[redacted]'


@pytest.mark.xfail(strict=True, reason='Memo updated before failed append suppresses retry: claude_sessions/events.py:109-121')
def test_failed_append_does_not_suppress_same_event_retry(audit, monkeypatch):
    p, _ = audit
    attempts = []

    def flaky(path, *args, **kwargs):
        attempts.append(path)
        if len(attempts) == 1:
            raise OSError('append fault')
        return builtins.open(path, *args, **kwargs)

    monkeypatch.setattr(e, 'open', flaky, raising=False)
    assert e.record('source', 'failure') is False
    assert e.record('source', 'failure') is True
    assert len(attempts) == 2
    assert len(p.read_text(encoding='utf-8').splitlines()) == 1


@pytest.mark.xfail(strict=True, reason='Backward clock keeps future memo and suppresses recovery: claude_sessions/events.py:107-109')
def test_dedupe_exact_boundary_and_backward_clock_recovery(audit):
    p, clock = audit
    assert e.record('source', 'failure')
    clock[0] += e._DEDUPE_SEC - 0.001
    assert e.record('source', 'failure') is False
    clock[0] = 1000.0 + e._DEDUPE_SEC
    assert e.record('source', 'failure') is True
    assert len(p.read_text(encoding='utf-8').splitlines()) == 2
    clock[0] = 1.0
    assert e.record('source', 'failure') is True


def test_dedupe_separates_sources_and_integer_identities(audit):
    p, _ = audit
    assert e.record('a', 'HTTP 429 slow 1.23')
    assert e.record('a', 'HTTP 429 slow 9.87') is False
    assert e.record('b', 'HTTP 429 slow 9.87')
    assert e.record('a', 'HTTP 500 slow 9.87')
    assert e.record('a', 'pid 12')
    assert e.record('a', 'pid 13')
    rows = [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines()]
    assert [(r['src'], r['msg']) for r in rows] == [
        ('a', 'HTTP 429 slow 1.23'), ('b', 'HTTP 429 slow 9.87'),
        ('a', 'HTTP 500 slow 9.87'), ('a', 'pid 12'), ('a', 'pid 13')]


def test_memo_overflow_evicts_oldest_250_keeps_current(audit):
    _, clock = audit
    e._recent.update({('old', str(i)): float(i) for i in range(500)})
    clock[0] = 1000
    assert e.record('current', 'failure')
    assert len(e._recent) == 251
    assert all(('old', str(i)) not in e._recent for i in range(250))
    assert all(('old', str(i)) in e._recent for i in range(250, 500))
    assert e._recent[('current', 'failure')] == 1000


def test_invalid_level_normalized_empty_message_never_resolves_path(audit, monkeypatch):
    p, _ = audit
    assert e.record('source', 'failure', level='INVALID')
    assert json.loads(p.read_text(encoding='utf-8'))['lvl'] == 'error'
    monkeypatch.setattr(e, 'path', lambda: pytest.fail('empty message resolved path'))
    assert e.record('source', '  ') is False
    monkeypatch.setattr(e, 'redact', lambda value: '')
    assert e.record('source', 'redacted away') is False


def test_rotation_fault_follows_complete_append_once(audit, monkeypatch):
    p, _ = audit
    calls = []

    def rotate(path):
        raw = p.read_bytes()
        assert raw.endswith(b'\n')
        assert json.loads(raw)['msg'] == 'failure'
        calls.append(path)
        raise OSError('rotation fault')

    monkeypatch.setattr(e, '_rotate', rotate)
    assert e.record('source', 'failure') is False
    assert calls == [str(p)]
    assert len(p.read_bytes().splitlines()) == 1


def test_reader_torn_tail_counts_valid_newest_records(audit):
    p, _ = audit
    p.write_bytes(b'{"msg":"one"}\nnot-json\n[]\n{"msg":"two"}\n{"msg":')
    assert e.read(limit=1) == [{'msg': 'two'}]
    assert e.read(limit=2) == [{'msg': 'two'}, {'msg': 'one'}]
    assert p.read_bytes().endswith(b'{"msg":')


def test_reader_fault_returns_empty_without_recursive_write(audit, monkeypatch):
    p, _ = audit
    p.write_bytes(b'{"msg":"evidence"}\n')
    before = p.read_bytes()

    def fail(path):
        yield {'msg': 'partial'}
        raise OSError('reader fault')

    monkeypatch.setattr(transcripts, 'iter_json', fail)
    monkeypatch.setattr(e, 'record', lambda *a, **k: pytest.fail('recursive append'))
    monkeypatch.setattr(e, '_rotate', lambda *a: pytest.fail('reader rotated'))
    assert e.read() == []
    assert p.read_bytes() == before
