"""T-1326: the highest-risk uncovered branches of claude_sessions/llmcall.py
lines 36-93 inclusive (build_headless_args and failure_reason), at tip 6b1a30b8.
Lines below are the current worktree numbers; the card's numbers are one line
off in places. Denial and fail-closed first, then boundaries, then error paths.

Selected branches (worktree line, probe):
1. build_headless_args 50-52      harness id: Claude flags never reach the argv
2. build_headless_args 54-58      Claude default argv order: -p, --max-turns, --disallowedTools, model, budget, extra
3. build_headless_args 59         prompt None: stdin is separators and the mark only
4. build_headless_args 55-56      empty model adds no --model flag
5. failure_reason 76-78           stdout not starting with '{' is returned stripped, otherwise unchanged
6. failure_reason 79-82           invalid JSON starting with '{' returns the raw text
7. failure_reason 83-84           a JSON list envelope returns the raw text. Unreachable as written: a
                                  string starting with '{' never parses to a list, so the probe reaches 77-78
8. failure_reason 85-88           'result' string wins; an empty 'result' falls through to 'error' and 'message'
9. failure_reason 89-92           nested {'error': {'message': ...}} is extracted; a non-string message returns raw
10. failure_reason 76            None stdout returns '' and never raises (control)

Seams: harnesses.impl and sessions.HEADLESS_MARK are monkeypatched; no subprocess.
"""

import json

import pytest

from claude_sessions import harnesses, llmcall, sessions

MARK = '<<archeus-test-mark>>'


@pytest.fixture
def mark(monkeypatch):
    monkeypatch.setattr(sessions, 'HEADLESS_MARK', MARK)
    return MARK


def _claude_argv(model_args=(), budget=(), extra=()):
    return (['claude', '-p', '--max-turns', llmcall.MAX_TURNS,
             '--disallowedTools', llmcall.DISALLOWED_TOOLS]
            + list(model_args) + list(budget) + list(extra))


def test_harness_id_keeps_claude_flags_out_of_the_argv(mark, monkeypatch):
    seen, calls = [], []

    def headless_argv(exe, model, no_tools=False):
        calls.append((exe, model, no_tools))
        return ['pi-cli', '--ephemeral']

    def impl(key, hid=None):
        seen.append((key, hid))
        return headless_argv

    monkeypatch.setattr(harnesses, 'impl', impl)
    args, stdin = llmcall.build_headless_args(
        'pi-cli', 'hi', model='m1', budget_args=('--max-budget-usd', '1'),
        extra_args=('--foo',), harness='pi', no_tools=True)
    assert args == ['pi-cli', '--ephemeral']
    assert calls == [('pi-cli', 'm1', True)]
    assert seen == [('headless_argv', 'pi')]
    assert stdin == 'hi\n\n' + MARK


def test_claude_default_argv_order(mark):
    args, _ = llmcall.build_headless_args(
        'claude', 'p', model='opus', budget_args=('--max-budget-usd', '2'), extra_args=('--x',))
    assert args == _claude_argv(('--model', 'opus'), ('--max-budget-usd', '2'), ('--x',))


def test_prompt_none_sends_separators_and_mark_only(mark):
    _, stdin = llmcall.build_headless_args('claude', None)
    assert stdin == '\n\n' + MARK


def test_prompt_always_ends_with_the_mark(mark):
    _, stdin = llmcall.build_headless_args('claude', 'work')
    assert stdin == 'work\n\n' + MARK
    assert stdin.endswith(MARK)


def test_empty_model_adds_no_model_flag(mark):
    args, _ = llmcall.build_headless_args('claude', 'p', model='')
    assert '--model' not in args
    assert args == _claude_argv()


def test_plain_stdout_is_stripped_and_otherwise_unchanged():
    assert llmcall.failure_reason('  plain text \n second  ') == 'plain text \n second'


def test_invalid_json_starting_with_brace_returns_raw_text():
    assert llmcall.failure_reason('{"result": "x"') == '{"result": "x"'
    assert llmcall.failure_reason('{ not json') == '{ not json'


def test_json_list_envelope_returns_raw_text():
    raw = '[{"result": "x"}]'
    assert llmcall.failure_reason(raw) == raw


def test_result_string_wins_and_empty_result_falls_through():
    assert llmcall.failure_reason(json.dumps({'result': '  Refused  ', 'error': 'E'})) == 'Refused'
    assert llmcall.failure_reason(json.dumps({'result': '   ', 'error': 'E'})) == 'E'
    assert llmcall.failure_reason(json.dumps({'result': '', 'message': 'M'})) == 'M'


def test_nested_error_message_is_extracted():
    assert llmcall.failure_reason(json.dumps({'error': {'message': '  nested boom '}})) == 'nested boom'


def test_non_string_nested_message_returns_raw_text():
    raw = json.dumps({'error': {'message': 5}})
    assert llmcall.failure_reason(raw) == raw


def test_none_stdout_returns_empty_and_never_raises():
    assert llmcall.failure_reason(None) == ''
    assert llmcall.failure_reason('') == ''
