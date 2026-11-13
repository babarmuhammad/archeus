"""T-1298: claude_sessions/transcripts.py:21-87; candidate gaps, not coverage.

Ranked final probes and closest tests in test_primitives:
1 :53/:56 test_prefix_survives_torn_tail; test_iter_json_pages_over_objects_not_lines lacks scalar JSON/torn tail.
2 :58/:59 test_zero_limit_yields_nothing; same closest test only positive limit.
3 :41 test_budget_counts_utf8_bytes; test_iter_json_stops_at_max_bytes uses ASCII and loose bounds.
4 :42 test_exact_budget_stops_before_parse; same closest test lacks parse/read counts.
5 :44 test_tuple_prefilter_precedes_parse; test_iter_json_prefilter_skips_before_parsing lacks parse spy/tuple/empty filter.
6 :56 test_offset_counts_only_matching_objects; test_iter_json_pages_over_objects_not_lines lacks prefilter/non-objects.
7 :35 test_open_failure_and_replacement_are_read_only; test_a_missing_transcript_is_empty_not_an_error lacks decoding/write checks.
8 :58 test_close_stops_reads; test_iter_json_is_a_generator_not_a_readlines lacks closure/read-count checks.
9 :65/:69 test_iso_offsets_and_invalid_inputs; closest transcript tests do not assert timestamp behavior.
10 :83/:87 test_stat_race_preserves_names_and_zero_limit; closest transcript tests do not assert listing race behavior.
"""

import io
import json
import os
from unittest.mock import Mock

import pytest

from claude_sessions import transcripts


class CountingFile(io.StringIO):
    def __init__(self, text):
        super().__init__(text)
        self.reads = 0

    def __next__(self):
        self.reads += 1
        return super().__next__()


def stream(monkeypatch, text):
    handle = CountingFile(text)
    opener = Mock(return_value=handle)
    monkeypatch.setattr(transcripts, 'open', opener, raising=False)
    return handle, opener


def test_prefix_survives_torn_tail(monkeypatch):
    handle, _ = stream(monkeypatch, '\n[]\nnull\nbad\n{"n":1}\n7\n{"n":2}\n{"n":')
    assert list(transcripts.iter_json('synthetic', offset=1, limit=2)) == [{'n': 2}]
    assert handle.closed


@pytest.mark.xfail(strict=True, reason='Yield precedes zero-limit check: claude_sessions/transcripts.py:58-59')
def test_zero_limit_yields_nothing(monkeypatch):
    stream(monkeypatch, '{"n":1}\n{"n":2}\n')
    assert list(transcripts.iter_json('synthetic', limit=0)) == []


@pytest.mark.xfail(strict=True, reason='Byte budget counts Unicode characters: claude_sessions/transcripts.py:41')
def test_budget_counts_utf8_bytes(monkeypatch):
    line = '{"text":"\u00e9\u00e9"}\n'
    stream(monkeypatch, line)
    assert len(line.encode('utf-8')) > len(line)
    assert list(transcripts.iter_json('synthetic', max_bytes=len(line))) == []


def test_exact_budget_stops_before_parse(monkeypatch):
    first = '{"n":1}\n'
    handle, _ = stream(monkeypatch, first + '{"n":2}\n{"n":3}\n')
    loads = Mock(wraps=json.loads)
    monkeypatch.setattr(transcripts.json, 'loads', loads)
    assert list(transcripts.iter_json('synthetic', max_bytes=len(first))) == [{'n': 1}]
    loads.assert_called_once_with(first.strip())
    assert handle.reads == 2 and handle.closed


def test_tuple_prefilter_precedes_parse(monkeypatch):
    text = 'unrelated garbage\n{"kind":"keep"}\n{"kind":"other"}\n{"kind":"also"}\n'
    stream(monkeypatch, text)
    loads = Mock(wraps=json.loads)
    monkeypatch.setattr(transcripts.json, 'loads', loads)
    assert list(transcripts.iter_json('synthetic', prefilter=('keep', 'also'))) == [
        {'kind': 'keep'}, {'kind': 'also'}]
    assert [call.args[0] for call in loads.call_args_list] == [
        '{"kind":"keep"}', '{"kind":"also"}']
    loads.reset_mock()
    stream(monkeypatch, '{"kind":"other"}\n')
    assert list(transcripts.iter_json('synthetic', prefilter=())) == [{'kind': 'other'}]
    loads.assert_called_once_with('{"kind":"other"}')


def test_offset_counts_only_matching_objects(monkeypatch):
    handle, _ = stream(monkeypatch,
                       '{"n":0}\nkeep invalid\n["keep"]\n'
                       '{"keep":1}\nnull\n{"keep":2}\n{"keep":3}\n')
    assert list(transcripts.iter_json('synthetic', prefilter='keep',
                                      offset=1, limit=1)) == [{'keep': 2}]
    assert handle.reads == 6 and handle.closed


def test_open_failure_and_replacement_are_read_only(monkeypatch, tmp_path):
    missing = Mock(side_effect=OSError('synthetic refusal'))
    with monkeypatch.context() as patch:
        patch.setattr(transcripts, 'open', missing, raising=False)
        assert list(transcripts.iter_json('synthetic')) == []
    missing.assert_called_once_with('synthetic', 'r', encoding='utf-8', errors='replace')
    path = tmp_path / 's.jsonl'
    raw = b'{"n":1}\n{"text":"\xff"}\n{"n":2}\n'
    path.write_bytes(raw)
    assert list(transcripts.iter_json(path)) == [
        {'n': 1}, {'text': '\ufffd'}, {'n': 2}]
    assert path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [path]


def test_close_stops_reads(monkeypatch):
    handle, opener = stream(monkeypatch, '{"n":1}\n{"n":2}\n')
    iterator = transcripts.iter_json('synthetic')
    try:
        assert next(iterator) == {'n': 1}
        assert handle.reads == 1 and not handle.closed
    finally:
        iterator.close()
    assert handle.closed and handle.reads == 1
    opener.assert_called_once_with('synthetic', 'r', encoding='utf-8', errors='replace')


def test_iso_offsets_and_invalid_inputs():
    epoch = transcripts.iso_to_epoch('2020-01-01T00:00:00Z')
    assert epoch == 1577836800
    assert transcripts.iso_to_epoch('2020-01-01T01:30:00+01:30') == epoch
    for value in (None, 0, [], {}, '', '2020-02-30T00:00:00Z', 'not-a-date'):
        assert transcripts.iso_to_epoch(value) is None


def test_stat_race_preserves_names_and_zero_limit(monkeypatch, tmp_path):
    folder = str(tmp_path)
    monkeypatch.setattr(transcripts.os, 'listdir',
                        Mock(return_value=['old.jsonl', 'gone.jsonl', 'new.jsonl', 'notes.txt']))

    def mtime(path):
        name = os.path.basename(path)
        if name == 'gone.jsonl':
            raise OSError('synthetic stat race')
        return {'old.jsonl': 1, 'new.jsonl': 2}[name]

    stat = Mock(side_effect=mtime)
    monkeypatch.setattr(transcripts.os.path, 'getmtime', stat)
    assert transcripts.session_files(folder, limit=0) == [
        'new.jsonl', 'old.jsonl', 'gone.jsonl']
    assert stat.call_count == 3
    assert transcripts.session_files(folder, newest_first=False, limit=2) == [
        'gone.jsonl', 'old.jsonl']
