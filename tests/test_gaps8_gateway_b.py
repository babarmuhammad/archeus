"""Anthropic to OpenAI request translation (T-1325).

Source slice: claude_sessions/gateway.py lines 139-215, to_openai_request.
Selected branches, denial and fail-closed first:

  161-162  thinking and redacted_thinking never reach any OpenAI message, tool-call turn included
  176-185  an image block is dropped under warn key 'blk:image' while the text still translates
  186-190  an assistant turn with no text gives content None and keeps tool_calls
  170-175, 194  tool_result becomes role tool messages ahead of the user text in the same turn
  163-169  tool_use arguments are JSON text; a missing input becomes '{}'
  153-155  string content passes through unchanged, even when empty
  199-205  nameless tools are dropped; a missing input_schema becomes {}
  145-148  an array system is flattened into one system message; an empty system adds none
  206-209  max_tokens is omitted when absent; temperature 0 is kept
  212-214  cache_control warns once under key 'cache' and is not forwarded

Seam: gateway._emit records warning lines and gateway._warned is a fresh set per
test, so the real once-per-key logic runs and is observed.
"""
import json

import pytest

from claude_sessions import gateway


@pytest.fixture
def warned(monkeypatch):
    lines = []
    monkeypatch.setattr(gateway, '_warned', set())
    monkeypatch.setattr(gateway, '_emit', lines.append)
    return lines


def test_thinking_blocks_never_reach_a_tool_call_turn(warned):
    out = gateway.to_openai_request({'model': 'm', 'messages': [{'role': 'assistant', 'content': [
        {'type': 'thinking', 'thinking': 'secret-plan', 'signature': 'sig-x'},
        {'type': 'redacted_thinking', 'data': 'opaque-blob'},
        {'type': 'text', 'text': 'checking'},
        {'type': 'tool_use', 'id': 'tu_9', 'name': 'Bash', 'input': {'cmd': 'ls'}}]}]})
    assert len(out['messages']) == 1
    m = out['messages'][0]
    assert m['content'] == 'checking'
    assert m['tool_calls'][0]['id'] == 'tu_9'
    blob = json.dumps(out)
    for leaked in ('secret-plan', 'sig-x', 'opaque-blob'):
        assert leaked not in blob
    assert gateway._warned == set()
    assert warned == []


def test_an_image_is_reported_under_its_own_key_while_the_text_still_translates(warned):
    out = gateway.to_openai_request({'model': 'm', 'messages': [{'role': 'user', 'content': [
        {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': 'AAAA'}},
        {'type': 'text', 'text': 'describe it'}]}]})
    assert out['messages'] == [{'role': 'user', 'content': 'describe it'}]
    assert gateway._warned == {'blk:image'}
    assert len(warned) == 1 and 'image' in warned[0]
    assert 'AAAA' not in json.dumps(out)


def test_an_assistant_turn_with_only_a_tool_call_has_null_content(warned):
    out = gateway.to_openai_request({'model': 'm', 'messages': [{'role': 'assistant', 'content': [
        {'type': 'tool_use', 'id': 't1', 'name': 'Read', 'input': {}}]}]})
    assert out['messages'] == [{'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 't1', 'type': 'function', 'function': {'name': 'Read', 'arguments': '{}'}}]}]


def test_every_tool_result_precedes_the_user_text_and_keeps_its_call_id(warned):
    out = gateway.to_openai_request({'model': 'm', 'messages': [{'role': 'user', 'content': [
        {'type': 'tool_result', 'tool_use_id': 'tu_1', 'content': [
            {'type': 'text', 'text': 'a'}, {'type': 'text', 'text': 'b'}]},
        {'type': 'tool_result', 'tool_use_id': 'tu_2', 'content': 'plain'},
        {'type': 'text', 'text': 'next'}]}]})
    assert out['messages'] == [
        {'role': 'tool', 'tool_call_id': 'tu_1', 'content': 'a\nb'},
        {'role': 'tool', 'tool_call_id': 'tu_2', 'content': 'plain'},
        {'role': 'user', 'content': 'next'}]


def test_tool_use_input_is_json_text_and_a_missing_input_is_an_empty_object(warned):
    out = gateway.to_openai_request({'model': 'm', 'messages': [{'role': 'assistant', 'content': [
        {'type': 'tool_use', 'id': 'a', 'name': 'N', 'input': {'path': 'x', 'n': 1}},
        {'type': 'tool_use', 'id': 'b', 'name': 'M'}]}]})
    calls = out['messages'][0]['tool_calls']
    assert calls[0]['function']['arguments'] == '{"path": "x", "n": 1}'
    assert calls[1]['function']['arguments'] == '{}'


def test_string_content_passes_through_unchanged_even_when_empty(warned):
    out = gateway.to_openai_request({'model': 'm', 'messages': [
        {'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': ''}]})
    assert out['messages'] == [{'role': 'user', 'content': 'hi'},
                               {'role': 'assistant', 'content': ''}]


def test_a_nameless_tool_is_dropped_and_a_missing_schema_becomes_an_empty_object(warned):
    out = gateway.to_openai_request({'model': 'm', 'messages': [], 'tools': [
        {'description': 'no name'}, {'name': 'Glob', 'description': 'find'}]})
    assert out['tools'] == [{'type': 'function', 'function': {
        'name': 'Glob', 'description': 'find', 'parameters': {}}}]


def test_an_empty_system_adds_no_system_message_and_an_array_joins_in_order(warned):
    for system in (None, '', [], [{'type': 'text', 'text': ''}]):
        out = gateway.to_openai_request({'model': 'm', 'system': system,
                                         'messages': [{'role': 'user', 'content': 'hi'}]})
        assert out['messages'] == [{'role': 'user', 'content': 'hi'}]
    out = gateway.to_openai_request({'model': 'm', 'system': ['a', {'type': 'text', 'text': 'b'}],
                                     'messages': []})
    assert out['messages'] == [{'role': 'system', 'content': 'a\nb'}]


def test_max_tokens_is_omitted_when_absent_and_a_zero_temperature_survives(warned):
    out = gateway.to_openai_request({'model': 'm', 'messages': [], 'temperature': 0})
    assert 'max_tokens' not in out
    assert out['temperature'] == 0
    bare = gateway.to_openai_request({'model': 'm', 'messages': []})
    assert 'temperature' not in bare
    full = gateway.to_openai_request({'model': 'm', 'messages': [],
                                      'max_tokens': 64, 'temperature': 0.7})
    assert full['max_tokens'] == 64 and full['temperature'] == 0.7


def test_a_cache_control_on_a_message_block_warns_once_and_is_not_forwarded(warned):
    body = {'model': 'm', 'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': 'x', 'cache_control': {'type': 'ephemeral'}}]}]}
    out = gateway.to_openai_request(body)
    gateway.to_openai_request(body)
    assert gateway._warned == {'cache'}
    assert len(warned) == 1 and 'cache_control' in warned[0]
    assert 'cache_control' not in json.dumps(out)
    assert out['messages'] == [{'role': 'user', 'content': 'x'}]
