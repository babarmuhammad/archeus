"""T-1297: claude_sessions/limit_hook.py:50-87; candidate gaps, not coverage.

Ranked final probes, closest assertions and missing compositions:
1 :61/:69 test_execution_latches_before_env_check; test_p05_seams.test_limit_hook_keeps_the_latch_and_skips_rotation_in_an_execution counts calls, not order.
2 :61/:83 test_latch_failure_prevents_offer; test_rotate_live.test_the_hook_latches_the_account_and_applies_the_mode has no latch error.
3 :70/:83 test_offer_failure_keeps_latch; same closest test has successful offer.
4 :53 test_cwd_selection; same closest test supplies cwd only.
5 :54/:55/:70 test_offer_arguments; same closest test uses string session id.
6 :71/:86 test_success_stdout_is_bell_only; same closest test calls handle only.
7 :77 test_malformed_json_has_no_work; test_the_hook_never_raises_and_never_blocks checks process exit, not seam calls.
8 :79 test_non_objects_have_no_work; same closest test lacks side-effect assertions.
9 :82/:83 test_handle_error_has_no_success; same closest test lacks handle failure.
10 :85 test_falsy_output_suppresses_print; same closest test lacks falsy handle output.
"""

import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def hook(monkeypatch, tmp_path):
    import sys

    with monkeypatch.context() as patch:
        patch.setattr(sys, 'stdout', io.StringIO())
        from claude_sessions import limit_hook
    from claude_sessions import quota, rotate

    events = []
    monkeypatch.setattr(quota, 'note_limit',
                        lambda *a, **k: events.append(('latch', a, k)))
    monkeypatch.setattr(rotate, 'offer',
                        lambda *a, **k: events.append(('offer', a, k)))
    monkeypatch.setattr(limit_hook, 'os', SimpleNamespace(
        environ={}, getcwd=Mock(return_value=str(tmp_path))))
    monkeypatch.setattr(limit_hook, 'sys', SimpleNamespace(stdin=io.StringIO()))
    monkeypatch.setattr(limit_hook, 'print', Mock(), raising=False)
    return limit_hook, quota, rotate, events


def feed(module, data):
    module.sys.stdin = io.StringIO(json.dumps(data))


def test_execution_latches_before_env_check(hook):
    module, _, _, events = hook

    class Environment(dict):
        def get(self, name):
            events.append(('env', name))
            return 'execution'

    module.os.environ = Environment()
    assert module.handle({'cwd': 'synthetic'}) == {'terminalSequence': '\a'}
    assert events == [('latch', (None,), {'window': True}),
                      ('env', 'ARCHEUS_EXECUTION_ID')]


def test_latch_failure_prevents_offer(hook, monkeypatch):
    module, quota, rotate, _ = hook
    latch = Mock(side_effect=OSError('synthetic latch failure'))
    offer = Mock()
    monkeypatch.setattr(quota, 'note_limit', latch)
    monkeypatch.setattr(rotate, 'offer', offer)
    feed(module, {'cwd': 'synthetic'})
    assert module.main() == 0
    latch.assert_called_once_with(None, window=True)
    offer.assert_not_called()
    module.print.assert_not_called()


def test_offer_failure_keeps_latch(hook, monkeypatch):
    module, _, rotate, events = hook

    def fail(*args, **kwargs):
        events.append(('offer_failed',))
        raise OSError('synthetic offer failure')

    offer = Mock(side_effect=fail)
    monkeypatch.setattr(rotate, 'offer', offer)
    feed(module, {'cwd': 'synthetic'})
    assert module.main() == 0
    assert events == [('latch', (None,), {'window': True}), ('offer_failed',)]
    assert offer.call_count == 1
    module.print.assert_not_called()


def test_cwd_selection(hook):
    module, _, _, events = hook
    for data, expected in (({'cwd': 'explicit'}, 'explicit'), ({}, module.os.getcwd.return_value),
                           ({'cwd': ''}, module.os.getcwd.return_value)):
        events.clear()
        module.os.getcwd.reset_mock()
        module.handle(data)
        assert events[1][1][0] == expected
        assert module.os.getcwd.call_count == (0 if data.get('cwd') else 1)


def test_offer_arguments(hook):
    module, _, _, events = hook
    module.handle({'cwd': 'synthetic', 'session_id': 123})
    assert events == [('latch', (None,), {'window': True}),
                      ('offer', ('synthetic', '', '123'),
                       {'why': 'rate_limit in a live session'})]


def test_success_stdout_is_bell_only(hook):
    module, _, _, events = hook
    feed(module, {'cwd': 'synthetic', 'session_id': 'SYNTHETIC_SECRET',
                  'transcript_path': 'private-transcript', 'prompt': 'private-prompt'})
    assert module.main() == 0
    module.print.assert_called_once_with(json.dumps({'terminalSequence': '\a'}))
    assert json.loads(module.print.call_args.args[0]) == {'terminalSequence': '\a'}
    assert [event[0] for event in events] == ['latch', 'offer']


def test_malformed_json_has_no_work(hook):
    module, _, _, events = hook
    module.sys.stdin = io.StringIO('{"cwd":')
    assert module.main() == 0
    assert events == []
    module.os.getcwd.assert_not_called()
    module.print.assert_not_called()


def test_non_objects_have_no_work(hook):
    module, _, _, events = hook
    for data in ([], None, 'text', 7):
        feed(module, data)
        assert module.main() == 0
    assert events == []
    module.os.getcwd.assert_not_called()
    module.print.assert_not_called()


def test_handle_error_has_no_success(hook, monkeypatch):
    module, _, _, events = hook
    handle = Mock(side_effect=RuntimeError('synthetic'))
    monkeypatch.setattr(module, 'handle', handle)
    feed(module, {'cwd': 'synthetic'})
    assert module.main() == 0
    handle.assert_called_once_with({'cwd': 'synthetic'})
    assert events == []
    module.print.assert_not_called()


def test_falsy_output_suppresses_print(hook, monkeypatch):
    module, _, _, events = hook
    handle = Mock()
    monkeypatch.setattr(module, 'handle', handle)
    for value in (None, {}, [], '', False):
        handle.return_value = value
        feed(module, {})
        assert module.main() == 0
    module.print.assert_not_called()
    handle.return_value = {'terminalSequence': '\a'}
    feed(module, {})
    assert module.main() == 0
    module.print.assert_called_once_with(json.dumps({'terminalSequence': '\a'}))
    assert events == []
