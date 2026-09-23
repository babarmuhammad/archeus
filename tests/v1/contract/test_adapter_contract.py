"""G7 — harness adapters are normalised and replaceable (execution-architecture §3).

The fake adapter is checked here, now, as a REAL subprocess against the frozen
contract: spawn marker before the process, prompt on stdin, JSONL stream file,
pid + create_time, exit codes, cancellation that refuses a recycled PID, and
the spawn rule that never starts one execution twice. The claude_code and
codex adapters join this file in P11 against recorded stream fixtures.
"""

import hashlib
import json
import os
import sys
import time

import pytest

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.harnesses.fake import FakeHarness
from archeus.infra.paths import ExecPaths
from claude_sessions import proc


def _spec(tmp_path, steps=(), prompt='do the thing', **kw):
    return base.ExecutionSpec(execution_id=ids.new_id('execution'), prompt=prompt,
                              workdir=str(tmp_path), task_contract={'fake_scenario': list(steps)},
                              **kw)


def _wait_exit(adapter, handle, timeout=30):
    deadline = time.monotonic() + timeout
    while adapter.status(handle).state == 'running':
        assert time.monotonic() < deadline, 'fake agent did not exit'
        time.sleep(0.05)
    return adapter.status(handle)


def _wait_events(handle, n, timeout=30):
    path = os.path.join(handle.exec_dir, 'stream.jsonl')
    deadline = time.monotonic() + timeout
    while True:
        events, _ = base.read_stream(path)
        if len(events) >= n:
            return events
        assert time.monotonic() < deadline, 'stream never reached %d events: %s' % (n, events)
        time.sleep(0.05)


def test_the_fake_adapter_implements_the_contract():
    fake = FakeHarness()
    assert isinstance(fake, base.HarnessAdapter)
    assert fake.discover().installed
    assert fake.authenticate(base.AccountRef('acc')).ok
    assert fake.capabilities(base.AccountRef('acc')).enforcement in ('hook', 'sandbox', 'none')


def test_a_run_follows_the_process_io_contract(tmp_path, archeus_home):
    fake = FakeHarness()
    usage = {'input_tokens': 1200, 'output_tokens': 80}
    spec = _spec(tmp_path, [
        {'emit': {'type': 'assistant', 'text': 'DECISION: keep the old flag name'}},
        {'emit': {'type': 'result', 'summary': 'added --version', 'usage': usage}},
    ], prompt='add a --version flag\n' * 50)
    handle = fake.start(spec)
    paths = ExecPaths(spec.execution_id)

    # every file lives under ARCHEUS_HOME/run/exec/<execution id>/
    assert paths.dir == os.path.join(str(archeus_home), 'run', 'exec', spec.execution_id)
    assert handle.exec_dir == paths.dir
    marker = base.read_json(paths.spawning)
    assert marker['execution_id'] == spec.execution_id and marker['attempt'] == 1
    assert open(paths.prompt, encoding='utf-8').read() == spec.prompt
    assert base.read_json(paths.pid) == {'pid': handle.pid, 'create_time': handle.create_time}

    st = _wait_exit(fake, handle)
    assert st.exit_code == 0
    events, offset = base.read_stream(paths.stream)
    started = events[0]
    assert started['type'] == 'started' and started['pid'] == handle.pid
    # the prompt arrived on stdin, whole
    assert started['stdin_sha256'] == hashlib.sha256(spec.prompt.encode()).hexdigest()
    # the child was tagged, so the legacy account hooks stand down inside it
    assert started['execution_id'] == spec.execution_id
    assert events[1]['text'].startswith('DECISION:')
    assert offset == os.path.getsize(paths.stream)

    result = fake.collect_result(handle)
    assert (result.exit_reason, result.exit_code) == ('ok', 0)
    assert result.reported_summary == 'added --version' and result.usage == usage
    assert result.transcript_path == paths.stream
    base.mark_ended(paths, st.exit_code)
    assert base.read_json(paths.ended)['exit_code'] == 0


def test_a_crash_is_an_error_exit_with_its_output_kept(tmp_path):
    fake = FakeHarness()
    handle = fake.start(_spec(tmp_path, [{'emit': {'type': 'error', 'error': 'rate_limit'}},
                                         {'exit': 3}]))
    assert _wait_exit(fake, handle).exit_code == 3
    result = fake.collect_result(handle)
    assert result.exit_reason == 'error'
    assert fake.inspect(handle).events[-1] == {'type': 'error', 'error': 'rate_limit'}


def test_stop_kills_a_running_execution(tmp_path):
    fake = FakeHarness()
    handle = fake.start(_spec(tmp_path, [{'emit': {'type': 'working'}}, {'sleep': 60}]))
    _wait_events(handle, 2)
    assert fake.status(handle).state == 'running'
    assert proc.process_create_time(handle.pid) == handle.create_time
    fake.stop(handle, grace_s=0)
    assert _wait_exit(fake, handle, timeout=15).state == 'exited'
    assert fake.collect_result(handle).exit_reason == 'killed'
    fake.stop(handle, grace_s=0)            # stopping what is gone is a no-op


def test_stop_refuses_a_pid_that_now_belongs_to_another_process(tmp_path):
    """PID reuse: the recorded create time no longer matches, so nothing is
    killed — the survivor proves it."""
    fake = FakeHarness()
    handle = fake.start(_spec(tmp_path, [{'sleep': 60}]))
    try:
        forged = base.ProcessHandle(handle.execution_id, handle.pid, 'not-its-create-time',
                                    handle.exec_dir)
        with pytest.raises(base.StopRefused):
            fake.stop(forged, grace_s=0)
        assert fake.status(handle).state == 'running'
    finally:
        fake.stop(handle, grace_s=0)


def test_a_restarted_core_finds_the_process_by_pid_and_create_time(tmp_path):
    """A new adapter instance has no Popen: liveness comes from the handle."""
    first = FakeHarness()
    handle = first.start(_spec(tmp_path, [{'sleep': 60}]))
    try:
        again = FakeHarness()
        assert again.status(handle).state == 'running'
        stale = base.ProcessHandle(handle.execution_id, handle.pid, None, handle.exec_dir)
        assert again.status(stale).state == 'exited'    # unknown identity never counts
    finally:
        first.stop(handle, grace_s=0)


def test_an_execution_is_never_spawned_twice(tmp_path):
    fake = FakeHarness()
    spec = _spec(tmp_path)
    handle = fake.start(spec)
    _wait_exit(fake, handle)
    with pytest.raises(base.AlreadySpawned):
        FakeHarness().start(spec)                     # e.g. outbox re-delivery


def test_a_failed_spawn_leaves_a_tombstone_not_a_maybe(tmp_path):
    spec = _spec(tmp_path)
    missing = str(tmp_path / 'no-such-dir')
    bad = base.ExecutionSpec(execution_id=spec.execution_id, prompt='x', workdir=missing)
    with pytest.raises(base.SpawnFailed):
        base.spawn(bad, [sys.executable, '-c', 'pass'])
    paths = ExecPaths(spec.execution_id)
    assert os.path.exists(paths.spawning)
    assert base.read_json(paths.ended)['exit_code'] is None
    assert not os.path.exists(paths.pid)


def test_the_stream_reader_resumes_from_an_offset_and_keeps_partial_lines(tmp_path):
    path = str(tmp_path / 'stream.jsonl')
    with open(path, 'wb') as f:
        f.write(b'{"type": "a"}\nTraceback (most recent call last):\n{"type": "b"')
    events, offset = base.read_stream(path)
    assert events == [{'type': 'a'},
                      {'type': 'stderr', 'text': 'Traceback (most recent call last):'}]
    with open(path, 'ab') as f:
        f.write(b'}\n')
    more, end = base.read_stream(path, offset)
    assert more == [{'type': 'b'}] and end == os.path.getsize(path)
    assert base.read_stream(str(tmp_path / 'absent.jsonl'), 7) == ([], 7)


def test_the_fake_agent_is_stdlib_only():
    """It stands in for a foreign CLI: importing Archeus would let it cheat the
    contract it is meant to exercise."""
    import ast
    from archeus.harnesses import fake_agent
    tree = ast.parse(open(fake_agent.__file__, encoding='utf-8').read())
    imported = {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
                for a in n.names}
    imported |= {(n.module or '').split('.')[0] for n in ast.walk(tree)
                 if isinstance(n, ast.ImportFrom)}
    assert imported <= set(sys.stdlib_module_names), imported


@pytest.mark.xfail(strict=True, reason="phase:P11")
def test_the_claude_code_adapter_normalises_a_recorded_stream():
    from archeus.harnesses.claude_code import adapter          # noqa: F401  (P11)
    fixture = os.path.join(os.path.dirname(__file__), 'fixtures', 'claude_code_stream.jsonl')
    assert json.loads(open(fixture, encoding='utf-8').readline())


@pytest.mark.xfail(strict=True, reason="phase:P11")
def test_the_codex_adapter_normalises_a_recorded_stream():
    from archeus.harnesses.codex import adapter                # noqa: F401  (P11)
    fixture = os.path.join(os.path.dirname(__file__), 'fixtures', 'codex_stream.jsonl')
    assert json.loads(open(fixture, encoding='utf-8').readline())
