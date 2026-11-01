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
