"""T-1447: claude_sessions/gateway.py lines 218-300 at tip 026ea58e (re-located at 44aaf17f).

Candidate gaps, not measured coverage. Ten ranked candidates, silent data loss first:

1  :275-285 test_object_arguments_are_passed_through_not_emptied  (fixed)
2  :249-256 test_list_content_is_flattened_to_text                (fixed)
3  :245-248 test_finish_reason_mapping_including_unknown
4  :249-251 test_empty_choices_yields_empty_message
5  :252-256 test_tool_call_ids_fall_back_to_index
6  :263-266 test_usage_missing_fields_become_zero
7  :232-243 test_cache_control_detected_only_in_list_content
8  :218-229 image-only flatten returns '': covered by tests/test_gateway.py:99 (image dropped loudly); not written
9  :288-301 iter_sse [DONE] and noise: already pinned by tests/test_gateway.py:198; SKIP
10 :288-301 test_iter_sse_decodes_utf8_lines

Pure functions and io.BytesIO only: no socket, no HTTP server, no subprocess, no upstream.
"""

import io

import pytest

from claude_sessions import gateway


def test_object_arguments_are_passed_through_not_emptied():
    out = gateway.to_anthropic_response({'choices': [{'message': {'tool_calls': [
        {'id': 'c1', 'function': {'name': 'Read', 'arguments': {'p': 'a.py'}}}]},
        'finish_reason': 'tool_calls'}]}, 'm')
    assert out['content'][0]['input'] == {'p': 'a.py'}


def test_list_content_is_flattened_to_text():
    out = gateway.to_anthropic_response({'choices': [{'message': {'content': [
        {'type': 'text', 'text': 'a'}, {'type': 'text', 'text': 'b'}]},
        'finish_reason': 'stop'}]}, 'm')
    assert out['content'] == [{'type': 'text', 'text': 'a\nb'}]


@pytest.mark.parametrize('finish, stop', [
    ('stop', 'end_turn'),
    ('length', 'max_tokens'),
    ('tool_calls', 'tool_use'),
    ('function_call', 'tool_use'),
    ('content_filter', 'end_turn'),
    (None, 'end_turn'),
    ('eos', 'end_turn'),
])
def test_finish_reason_mapping_including_unknown(finish, stop):
    out = gateway.to_anthropic_response({'choices': [{'message': {'content': 'x'},
                                                      'finish_reason': finish}]}, 'm')
    assert out['stop_reason'] == stop


def test_empty_choices_yields_empty_message():
    out = gateway.to_anthropic_response({'choices': []}, 'm')
    assert out['content'] == []
    assert out['id'] == 'msg_gateway'
    assert out['model'] == 'm'
    assert out['stop_reason'] == 'end_turn'


def test_tool_call_ids_fall_back_to_index():
    out = gateway.to_anthropic_response({'choices': [{'message': {'tool_calls': [
        {'function': {'arguments': '{}'}},
        {'id': 'c2', 'function': {'arguments': '{}'}}]},
        'finish_reason': 'tool_calls'}]}, 'm')
    assert [b['id'] for b in out['content']] == ['call_0', 'c2']
    assert out['content'][0]['name'] == ''


def test_usage_missing_fields_become_zero():
    out = gateway.to_anthropic_response({'choices': [{'message': {'content': 'x'}}],
                                         'usage': {'prompt_tokens': None}}, 'm')
    assert out['usage'] == {'input_tokens': 0, 'output_tokens': 0}
    bare = gateway.to_anthropic_response({'choices': [{'message': {'content': 'x'}}]}, 'm')
    assert bare['usage'] == {'input_tokens': 0, 'output_tokens': 0}


def test_cache_control_detected_only_in_list_content():
    marked = {'type': 'text', 'text': 'x', 'cache_control': {'type': 'ephemeral'}}
    assert gateway._has_cache_control({'messages': [
        {'role': 'user', 'content': [marked]}]}) is True
    assert gateway._has_cache_control({'messages': [
        {'role': 'user', 'content': 'cache_control appears only as text'}]}) is False
    assert gateway._has_cache_control({'system': ['plain string block']}) is False
    assert gateway._has_cache_control({'system': [marked]}) is True


def test_iter_sse_decodes_utf8_lines():
    body = io.BytesIO('data: {"t": "café"}\n\n'.encode('utf-8'))
    assert list(gateway.iter_sse(body)) == [{'t': 'café'}]
