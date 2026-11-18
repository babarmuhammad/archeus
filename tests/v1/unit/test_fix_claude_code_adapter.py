import pytest

from archeus.harnesses.claude_code.adapter import normalise


@pytest.mark.parametrize('raw', [
    {'type': 'assistant', 'message': {'content': 'x'}},
    {'type': 'assistant', 'message': 'x'},
    {'type': 'assistant', 'message': {'content': ['x', 1, None]}},
    {'type': 'user', 'message': 'x'},
    {'type': 'user', 'message': {'content': 7}},
    {'type': 'result', 'usage': 'many'},
])
def test_a_malformed_stream_line_normalises_without_raising(raw):
    assert isinstance(normalise(raw), list)


def test_status_and_collect_result_fold_a_long_stream_without_holding_it(tmp_path, monkeypatch):
    import json
    from archeus.harnesses import base
    from archeus.harnesses.claude_code.adapter import ClaudeCodeAdapter

    lines = [{'type': 'system', 'subtype': 'init', 'session_id': 'first'}]
    lines += [{'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'x'}]}}] * 1600
    lines += [{'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'done',
               'session_id': 'last'}]
    (tmp_path / 'stream.jsonl').write_text('\n'.join(json.dumps(x) for x in lines) + '\n')
    handle = base.ProcessHandle('exe_1', 2 ** 22 - 1, None, str(tmp_path))
    batches = []
    real = base.read_stream
    monkeypatch.setattr(base, 'read_stream',
                        lambda p, o=0, m=None: batches.append(m) or real(p, o, m))
    a = ClaudeCodeAdapter()
    assert a.status(handle).exit_code == 0
    assert a.collect_result(handle).session_ref == 'last'
    assert batches and None not in batches
