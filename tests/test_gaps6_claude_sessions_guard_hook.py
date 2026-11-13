"""T-1296: claude_sessions/guard_hook.py:28-58; candidate gaps, not coverage.

Ranked final probes; closest test_hook_encoding.test_a_block_still_blocks_when_its_message_is_non_ascii
only tests healthy pipe/non-ASCII subprocess, not any failure seam below.
1 :48/:51 test_encoding_failure_still_blocks
2 :48/:51 test_pipe_failure_still_blocks
3 :39 test_only_selected_field_is_searched (test_tui_hooks.test_guard_hook_blocks_and_passes uses command only)
4 :41 test_inline_flags_search_multiline (same closest test has single line)
5 :42 test_invalid_regex_has_no_block_claim (same closest test has valid regex)
6 :35 test_bad_json_never_searches (same closest test has valid JSON)
7 :37/:39 test_payload_shapes (same closest test has object tool_input)
8 :29/:32 test_short_argv_and_exact_default (same closest test supplies message)
9 :44 test_falsy_inputs_and_missing_field (same closest test supplies command)
10 :58 test_wrapper_converts_unexpected_error (same closest test uses subprocess normal inputs).
"""

import builtins
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def guard(monkeypatch):
    import sys

    with monkeypatch.context() as patch:
        patch.setattr(sys, 'stdout', io.StringIO())
        patch.setattr(sys, 'stderr', io.StringIO())
        from claude_sessions import guard_hook
    streams = SimpleNamespace(argv=['guard', 'command', 'danger'],
                              stdin=io.StringIO(), stdout=io.StringIO(),
                              stderr=io.StringIO())
    monkeypatch.setattr(guard_hook, 'sys', streams)
    return guard_hook


def payload(guard, data):
    guard.sys.stdin = io.StringIO(json.dumps(data))


def test_encoding_failure_still_blocks(guard):
    payload(guard, {'tool_input': {'command': 'danger'}})
    write = Mock(side_effect=UnicodeEncodeError('ascii', '\u2603', 0, 1, 'synthetic'))
    guard.sys.stderr = SimpleNamespace(write=write)
    assert guard.main() == 2
    write.assert_called_once_with('archeus: blocked by archeus\n')
    assert guard.sys.stdout.getvalue() == ''


def test_pipe_failure_still_blocks(guard):
    guard.sys.argv.append('custom')
    payload(guard, {'tool_input': {'command': 'danger'}})
    write = Mock(side_effect=BrokenPipeError('synthetic'))
    guard.sys.stderr = SimpleNamespace(write=write)
    assert guard.main() == 2
    write.assert_called_once_with('archeus: custom\n')
    assert guard.sys.stdout.getvalue() == ''


def test_only_selected_field_is_searched(guard, monkeypatch):
    payload(guard, {'tool_input': {'command': 'safe', 'other': 'danger; executable()'},
                    'command': 'danger'})
    real_search = guard.re.search
    search = Mock(wraps=real_search)
    monkeypatch.setattr(guard.re, 'search', search)
    assert guard.main() == 0
    search.assert_called_once_with('danger', 'safe')
    assert guard.sys.stderr.getvalue() == guard.sys.stdout.getvalue() == ''


def test_inline_flags_search_multiline(guard):
    guard.sys.argv[2] = '(?ms)^danger.*end$'
    payload(guard, {'tool_input': {'command': 'safe\ndanger\nend'}})
    assert guard.main() == 2
    assert guard.sys.stderr.getvalue() == 'archeus: blocked by archeus\n'


def test_invalid_regex_has_no_block_claim(guard):
    guard.sys.argv[2] = '['
    payload(guard, {'tool_input': {'command': 'danger'}})
    assert guard.main() == 0
    assert guard.sys.stderr.getvalue() == guard.sys.stdout.getvalue() == ''


def test_bad_json_never_searches(guard, monkeypatch):
    guard.sys.stdin = io.StringIO('{"tool_input":')
    search = Mock(side_effect=AssertionError('must not search'))
    monkeypatch.setattr(guard.re, 'search', search)
    assert guard.main() == 0
    search.assert_not_called()
    assert guard.sys.stderr.getvalue() == ''


def test_payload_shapes(guard):
    for data in ([], None, ['danger']):
        payload(guard, data)
        assert guard.main() == 0
    for value in (['danger'], 1, 'danger'):
        payload(guard, {'tool_input': value})
        with pytest.raises(AttributeError):
            guard.main()
    assert guard.sys.stderr.getvalue() == guard.sys.stdout.getvalue() == ''


def test_short_argv_and_exact_default(guard, monkeypatch):
    load = Mock(side_effect=AssertionError('stdin forbidden'))
    with monkeypatch.context() as patch:
        patch.setattr(guard.json, 'load', load)
        for argv in ([], ['guard'], ['guard', 'command']):
            guard.sys.argv = argv
            assert guard.main() == 0
        load.assert_not_called()
    guard.sys.argv = ['guard', 'command', 'danger']
    payload(guard, {'tool_input': {'command': 'danger'}})
    assert guard.main() == 2
    assert guard.sys.stderr.getvalue() == 'archeus: blocked by archeus\n'


def test_falsy_inputs_and_missing_field(guard):
    for data in ({}, {'tool_input': None}, {'tool_input': {}},
                 {'tool_input': False}, {'tool_input': []},
                 {'tool_input': {'other': 'danger'}}):
        payload(guard, data)
        assert guard.main() == 0
    assert guard.sys.stderr.getvalue() == guard.sys.stdout.getvalue() == ''


def test_wrapper_converts_unexpected_error(guard):
    source = Path(guard.__file__).read_text(encoding='utf-8')
    def exit_with(code):
        raise SystemExit(code)

    fake_sys = SimpleNamespace(argv=['guard', 'command', 'danger'],
                               stdin=io.StringIO('{"tool_input": 1}'),
                               stdout=io.StringIO(), stderr=io.StringIO(),
                               exit=Mock(side_effect=exit_with))
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        return fake_sys if name == 'sys' else real_import(name, *args, **kwargs)

    namespace = {'__name__': '__main__',
                 '__builtins__': dict(vars(builtins), __import__=fake_import)}
    with pytest.raises(SystemExit) as exc:
        exec(compile(source, guard.__file__, 'exec'), namespace)
    assert exc.value.code == 0
    fake_sys.exit.assert_called_once_with(0)
    assert fake_sys.stderr.getvalue() == fake_sys.stdout.getvalue() == ''

