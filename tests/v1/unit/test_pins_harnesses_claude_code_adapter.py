"""T-835: pins on `archeus/harnesses/claude_code/adapter.py` — the comparisons,
early returns, membership checks and defaults a wrong edit loosens in silence.
Each test names one condition of the module and fails if that branch is inverted,
removed or relaxed. Fake launchers only: no process, no network, no Windows API.

What these tests do NOT show: what the real CLI does with the flags, the quota
vocabulary itself (`quota` owns that), or anything the base spawn contract pins."""

import json
import os
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.harnesses.claude_code import adapter as cc


def _spec(tmp_path, **kw):
    home = kw.pop('home', str(tmp_path / 'account-home'))
    os.makedirs(home, exist_ok=True)
    return base.ExecutionSpec(execution_id=ids.new_id('execution'), prompt='go',
                              workdir=str(tmp_path / 'work'),
                              account=base.AccountRef('claude-code:t', home), **kw)


def _handle(exec_dir, pid=424242, create_time=None, execution_id=None):
    return base.ProcessHandle(execution_id or ids.new_id('execution'), pid,
                              create_time, exec_dir)


def _result_raw(**kw):
    raw = {'type': 'result', 'subtype': 'success', 'result': 'done', 'is_error': False}
    raw.update(kw)
    return raw


def test_a_stderr_line_is_passed_through_unchanged():
    line = {'type': 'stderr', 'text': 'Traceback (most recent call last)'}
    assert cc.normalise(line) == [line]


def test_a_usage_that_is_not_an_object_emits_no_usage_event():
    ok = cc.normalise({'type': 'assistant', 'message': {'content': [],
                                                        'usage': {'input_tokens': 1}}})
    assert ok == [{'type': 'usage', 'usage': {'input_tokens': 1}}]
    for bad in ('many', 7, ['tokens'], True):
        out = cc.normalise({'type': 'assistant', 'message': {'content': [], 'usage': bad}})
        assert [e for e in out if e['type'] == 'usage'] == []


def test_a_tool_result_error_flag_is_a_bool_whatever_the_stream_sent():
    (ev,) = cc.normalise({'type': 'user', 'message': {'content': [
        {'type': 'tool_result', 'tool_use_id': 'tu_1', 'is_error': 'yes'}]}})
    assert ev['is_error'] is True
    (ev,) = cc.normalise({'type': 'user', 'message': {'content': [
        {'type': 'tool_result', 'tool_use_id': 'tu_1'}]}})
    assert ev['is_error'] is False


def test_the_limit_event_says_whether_a_plan_window_ran_out():
    # a bare 429 is a limit but never a window: only the window markers answer that
    rate = cc.normalise(_result_raw(is_error=True, result='HTTP 429: too many requests'))
    assert [e['type'] for e in rate] == ['limit', 'result']
    assert rate[0]['window'] is False
    window = cc.normalise(_result_raw(is_error=True, result="You've hit your session limit"))
    assert window[0]['window'] is True


def test_the_result_summary_is_cut_at_two_thousand_chars():
    assert cc.normalise(_result_raw(result='x' * 2500))[-1]['summary'] == 'x' * 2000


def test_billed_models_come_only_from_a_usage_object():
    assert cc.normalise(_result_raw(modelUsage={'b': {}, 'a': {}}))[-1]['billed'] == ['a', 'b']
    for bad in (['a'], 'a', 7, None):
        assert cc.normalise(_result_raw(modelUsage=bad))[-1]['billed'] == []


def test_the_hook_gates_every_tool_with_its_own_deadline(tmp_path):
    spec = _spec(tmp_path, hook_settings=('python', '-I', 'hook.py'))
    path = cc.ClaudeCodeAdapter(exe='claude')._settings(spec)
    with open(path, encoding='utf-8') as f:
        hooks = json.load(f)['hooks']
    (pre,) = hooks['PreToolUse']
    assert pre['matcher'] == '*'
    assert pre['hooks'][0]['command'] == '"python" "-I" "hook.py"'
    assert pre['hooks'][0]['timeout'] == cc.HOOK_TIMEOUT_S
    (compact,) = hooks['PreCompact']
    assert compact['hooks'][0]['command'] == '"python" "-I" "hook.py"'
    assert compact['hooks'][0]['timeout'] == 30


@pytest.mark.parametrize('estimate, want', [(None, '60'), (2, '40'), (9, '60')],
                         ids=['unset', 'size2', 'unknown'])
def test_the_turn_bound_follows_the_estimated_task_size(tmp_path, estimate, want):
    contract = {} if estimate is None else {'estimate': estimate}
    a = cc.ClaudeCodeAdapter(exe='claude').argv(_spec(tmp_path, task_contract=contract),
                                                'sess-1')
    assert a[a.index('--max-turns') + 1] == want


def test_a_resume_continues_one_session_a_new_run_opens_one(tmp_path):
    a = cc.ClaudeCodeAdapter(exe='claude')
    resumed = a.argv(_spec(tmp_path, resume_ref='sess-old'), 'sess-old')
    assert resumed[resumed.index('--resume') + 1] == 'sess-old'
    assert '--session-id' not in resumed
    fresh = a.argv(_spec(tmp_path), 'sess-new')
    assert fresh[fresh.index('--session-id') + 1] == 'sess-new'
    assert '--resume' not in fresh


def test_the_config_dir_is_the_private_one_isolated_the_home_otherwise(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path / 'profile'))
    monkeypatch.setenv('USERPROFILE', str(tmp_path / 'profile'))
    home_ref = '~' + os.sep + 'cl'
    isolated = _spec(tmp_path, home=home_ref, isolation=SimpleNamespace())
    env = cc.ClaudeCodeAdapter()._env(isolated)
    assert env['CLAUDE_CONFIG_DIR'] == base.ExecPaths(isolated.execution_id).config
    plain = _spec(tmp_path, home=home_ref)
    want = os.path.join(str(tmp_path / 'profile'), 'cl')
    assert cc.ClaudeCodeAdapter()._env(plain)['CLAUDE_CONFIG_DIR'] == want
    assert cc.ClaudeCodeAdapter._home(plain) == want


def test_the_provider_key_names_reach_the_child_as_removals(tmp_path):
    env = cc.ClaudeCodeAdapter()._env(_spec(tmp_path, env={'PATH_KEEP': 'x'}))
    for name in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN'):
        assert env[name] is None
    assert env['PATH_KEEP'] == 'x'


@pytest.mark.parametrize('state', [None, {}, {'session': ''}, {'other': 1}],
                         ids=['none', 'empty', 'blank', 'foreign'])
def test_a_resume_without_a_session_starts_nothing(monkeypatch, tmp_path, state):
    monkeypatch.setattr(base.proc, 'spawn_detached', lambda *a, **k: (_ for _ in ()).throw(
        AssertionError('a real process launch was reached')))

    def no_spawn(spec, argv):
        raise AssertionError('spawn was reached without a session')
    monkeypatch.setattr(base, 'spawn', no_spawn)
    with pytest.raises(base.SpawnFailed, match='session'):
        cc.ClaudeCodeAdapter(exe='claude').resume(_spec(tmp_path), state)


def test_status_trusts_only_the_recorded_child_and_the_recorded_process(tmp_path,
                                                                        monkeypatch):
    a = cc.ClaudeCodeAdapter(exe='claude')
    mine = _handle(str(tmp_path), pid=1111)
    a._children[mine.execution_id] = SimpleNamespace(pid=mine.pid, poll=lambda: None)
    assert a.status(mine) == base.ProcStatus('running', None)
    # the recorded child is someone else's pid: its answer about itself proves nothing
    ghost = _handle(str(tmp_path), pid=2222, execution_id=mine.execution_id)
    assert a.status(ghost) == base.ProcStatus('exited', None)
    # the same pid, a different process: the pid was recycled, ours is gone
    stranger = _handle(str(tmp_path), pid=3333, create_time='ct-mine')
    monkeypatch.setattr(cc.proc, 'process_create_time', lambda pid: 'ct-other')
    assert a.status(stranger) == base.ProcStatus('exited', None)
    monkeypatch.setattr(cc.proc, 'process_create_time', lambda pid: 'ct-mine')
    assert a.status(stranger) == base.ProcStatus('running', None)


def test_stop_refuses_a_pid_that_is_not_its_process(tmp_path, monkeypatch):
    a = cc.ClaudeCodeAdapter(exe='claude')
    killed = []
    monkeypatch.setattr(cc.proc, 'kill_pid_tree',
                        lambda pid, ct: killed.append((pid, ct)) or True)
    mine = _handle(str(tmp_path))
    a.stop(mine)
    assert killed == [(mine.pid, mine.create_time)]
    assert mine.execution_id in a._stopped

    def kill_fails(pid, ct):
        return False
    monkeypatch.setattr(cc.proc, 'kill_pid_tree', kill_fails)
    # the pid answers: a live process the kill did not take is a stranger, refuse
    monkeypatch.setattr(cc.proc, 'process_create_time', lambda pid: 'ct-anyone')
    with pytest.raises(base.StopRefused):
        a.stop(_handle(str(tmp_path), pid=999999))

    # the pid answers nothing: our process is simply gone — no refusal, no record
    monkeypatch.setattr(cc.proc, 'process_create_time', lambda pid: None)
    gone = _handle(str(tmp_path))
    a.stop(gone)
    assert gone.execution_id not in a._stopped
