"""T-1448: structured-output unwrapping and budget argv in claude_sessions/llmcall.py
(_slice_between, unwrap_structured, budget_args; source lines 200-240 at worktree 44aaf17f).

Not measured coverage: the ten candidates were ranked by reading the source.
Probe 1 (envelope returned as the parsed value) is left out as a strict xfail:
unwrap_structured's docstring names the raw text as its last fallback, so the
envelope return is the documented path, not a defect. Probe 10 pins the outcome
(inf is passed to the CLI, NaN is dropped) without calling it a defect.
"""

import json

from claude_sessions import config, llmcall


def test_prose_result_keeps_cost_with_none_parsed():
    raw = json.dumps({'result': 'just prose, no json', 'total_cost_usd': 0.25})
    assert llmcall.unwrap_structured(raw) == (None, 0.25)


def test_cost_rejects_bool_and_string():
    result = json.dumps({'result': '{"a": 1}'})
    assert llmcall.unwrap_structured(json.dumps(
        {'total_cost_usd': True, 'result': '{"a": 1}'})) == ({'a': 1}, None)
    assert llmcall.unwrap_structured(json.dumps(
        {'total_cost_usd': '0.5', 'result': '{"a": 1}'})) == ({'a': 1}, None)
    assert llmcall.unwrap_structured(json.dumps(
        {'total_cost_usd': 2, 'result': '{"a": 1}'})) == ({'a': 1}, 2.0)
    assert llmcall.unwrap_structured(result) == ({'a': 1}, None)


def test_list_envelope_falls_back_to_raw_text():
    raw = json.dumps([{'a': 1}])
    assert llmcall.unwrap_structured(raw) == ([{'a': 1}], None)


def test_plain_text_raw_returns_parse_json_result_and_none_cost():
    raw = 'Here: {"x": 3} done'
    assert llmcall.unwrap_structured(raw) == ({'x': 3}, None)


def test_empty_raw_returns_none_pair():
    assert llmcall.unwrap_structured(None) == (None, None)
    assert llmcall.unwrap_structured('') == (None, None)


def test_slice_between_requires_close_after_open():
    assert llmcall._slice_between(')x(', '(', ')') == ''
    assert llmcall._slice_between('abc)', '(', ')') == ''
    assert llmcall._slice_between('(abc', '(', ')') == ''


def test_slice_between_spans_outermost_pair():
    text = '{"a":1} and {"b":2}'
    assert llmcall._slice_between(text, '{', '}') == text


def test_budget_args_formats_cap_with_g(monkeypatch):
    for cap, shown in ((10, '10'), (0.1, '0.1'), (2.5, '2.5')):
        monkeypatch.setattr(config, 'load_settings',
                            lambda cap=cap: {'headless_budget_usd': cap})
        assert llmcall.budget_args() == ['--max-budget-usd', shown]


def test_budget_args_empty_for_unset_zero_negative_or_bad(monkeypatch):
    def settings(value):
        monkeypatch.setattr(config, 'load_settings',
                            lambda: {'headless_budget_usd': value})
        return llmcall.budget_args()

    assert settings(None) == []
    assert settings(0) == []
    assert settings(-3) == []
    assert settings('abc') == []

    def broken():
        raise RuntimeError('settings unreadable')
    monkeypatch.setattr(config, 'load_settings', broken)
    assert llmcall.budget_args() == []


def test_budget_args_nan_and_inf_outcome(monkeypatch):
    def settings(value):
        monkeypatch.setattr(config, 'load_settings',
                            lambda: {'headless_budget_usd': value})
        return llmcall.budget_args()

    assert settings(float('nan')) == []
    assert settings(float('inf')) == ['--max-budget-usd', 'inf']
