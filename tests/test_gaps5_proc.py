"""proc.run_capped stop and reap lifecycle, with Popen and threading.Timer faked."""

import subprocess

import pytest

from claude_sessions import proc


class FakeStdout:
    def __init__(self, chunks, *, raise_on_call=None, raise_exc=None):
        self._chunks = list(chunks)
        self.closed = False
        self.close_count = 0
        self._raise_on_call = raise_on_call
        self._raise_exc = raise_exc
        self._calls = 0

    def read1(self, n):
        self._calls += 1
        if self._calls == self._raise_on_call:
            raise self._raise_exc
        if self._chunks:
            return self._chunks.pop(0)[:n]
        return b''

    def close(self):
        self.closed = True
        self.close_count += 1


class FakeProcess:
    def __init__(self, chunks, returncode=0, *, raise_on_call=None, raise_exc=None,
                 alive_after_terminate=False, wait_timeout_once=False):
        self.stdout = FakeStdout(chunks, raise_on_call=raise_on_call, raise_exc=raise_exc)
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        self.alive = True
        self.wait_calls = []
        self._alive_after_terminate = alive_after_terminate
        self._wait_timeout_once = wait_timeout_once

    def terminate(self):
        self.terminated = True
        if not self._alive_after_terminate:
            self.alive = False

    def kill(self):
        self.killed = True
        self.alive = False

    def poll(self):
        return None if self.alive else self.returncode

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if self._wait_timeout_once and len(self.wait_calls) == 1:
            raise subprocess.TimeoutExpired(cmd=['fake'], timeout=timeout)
        self.alive = False
        return self.returncode


class FakeTimer:
    def __init__(self, fn, fire_on_start):
        self.fn = fn
        self.fire_on_start = fire_on_start
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True
        if self.fire_on_start:
            self.fn()

    def cancel(self):
        self.cancelled = True


def _patch(monkeypatch, fake_proc, fire_timer=False):
    timers = []

    def fake_popen(args, **kwargs):
        if fake_proc is None:
            raise FileNotFoundError("No such file or directory: 'fake'")
        return fake_proc

    def fake_timer(interval, fn):
        t = FakeTimer(fn, fire_timer)
        timers.append(t)
        return t

    monkeypatch.setattr(proc.subprocess, 'Popen', fake_popen)
    monkeypatch.setattr(proc.threading, 'Timer', fake_timer)
    return timers


def test_read1_raises_midstream_kills_child_and_propagates(monkeypatch):
    fake_p = FakeProcess([b'hello'], raise_on_call=2, raise_exc=OSError("pipe broken"))
    timers = _patch(monkeypatch, fake_p)

    with pytest.raises(OSError, match="pipe broken"):
        proc.run_capped(['fake'], timeout=5, max_bytes=100)

    assert fake_p.killed is True
    assert fake_p.stdout.closed is True
    assert fake_p.stdout.close_count == 1
    assert timers[0].started is True
    assert timers[0].cancelled is True


def test_timer_cancelled_on_successful_return(monkeypatch):
    fake_p = FakeProcess([b'data', b''])
    timers = _patch(monkeypatch, fake_p)

    proc.run_capped(['fake'], timeout=5, max_bytes=100)

    assert timers[0].started is True
    assert timers[0].cancelled is True


def test_cut_true_exactly_max_bytes_terminate_and_reap(monkeypatch):
    fake_p = FakeProcess([b'xxxxxx'], returncode=-15)
    timers = _patch(monkeypatch, fake_p)

    r = proc.run_capped(['fake'], timeout=5, max_bytes=5)

    assert r.cut is True
    assert r.stdout == b'xxxxx'
    assert fake_p.terminated is True
    assert fake_p.killed is False
    assert fake_p.stdout.closed is True
    assert fake_p.stdout.close_count == 1
    assert timers[0].cancelled is True


def test_timeout_fires_before_any_byte_returns_kill_code(monkeypatch):
    fake_p = FakeProcess([b''], returncode=-9)
    _patch(monkeypatch, fake_p, fire_timer=True)

    r = proc.run_capped(['fake'], timeout=1, max_bytes=100)

    assert fake_p.killed is True
    assert r.returncode == -9
    assert r.cut is False
    assert r.stdout == b''


def test_terminate_wait_timeoutexpired_falls_through_to_kill(monkeypatch):
    fake_p = FakeProcess([b'xxxx'], returncode=-9,
                         alive_after_terminate=True, wait_timeout_once=True)
    timers = _patch(monkeypatch, fake_p)

    r = proc.run_capped(['fake'], timeout=5, max_bytes=3)

    assert fake_p.terminated is True
    assert fake_p.killed is True
    assert fake_p.wait_calls == [0.5, None]
    assert r.cut is True
    assert r.stdout == b'xxx'
    assert timers[0].cancelled is True


def test_popen_raises_filenotfound_no_timer_started(monkeypatch):
    timers = _patch(monkeypatch, None)

    with pytest.raises(FileNotFoundError):
        proc.run_capped(['nonexistent'], timeout=5, max_bytes=100)

    assert timers == []


def test_max_bytes_zero_one_byte_returns_empty_cut_true(monkeypatch):
    fake_p = FakeProcess([b'x'], returncode=-15)
    timers = _patch(monkeypatch, fake_p)

    r = proc.run_capped(['fake'], timeout=5, max_bytes=0)

    assert r.cut is True
    assert r.stdout == b''
    assert r.stderr == b''
    assert fake_p.terminated is True
    assert timers[0].cancelled is True


def test_stdout_closed_child_still_alive_wait_reaps_not_cut(monkeypatch):
    fake_p = FakeProcess([b''], returncode=0)
    timers = _patch(monkeypatch, fake_p)

    r = proc.run_capped(['fake'], timeout=5, max_bytes=100)

    assert r.cut is False
    assert r.stdout == b''
    assert len(fake_p.wait_calls) >= 1
    assert fake_p.alive is False
    assert timers[0].cancelled is True


def test_nonzero_exit_before_cap_returncode_returned_cut_false(monkeypatch):
    fake_p = FakeProcess([b'error output\n', b''], returncode=1)
    _patch(monkeypatch, fake_p)

    r = proc.run_capped(['fake'], timeout=5, max_bytes=200)

    assert r.returncode == 1
    assert r.cut is False
    assert r.stdout == b'error output\n'
    assert r.stderr == b''


def test_exactly_max_bytes_is_not_cut(monkeypatch):
    fake_p = FakeProcess([b'abcde', b''], returncode=0)
    _patch(monkeypatch, fake_p)

    r = proc.run_capped(['fake'], timeout=5, max_bytes=5)

    assert r.cut is False
    assert r.stdout == b'abcde'
    assert r.returncode == 0


def test_no_output_exits_zero_empty_stdout_not_cut_reaped(monkeypatch):
    fake_p = FakeProcess([b''], returncode=0)
    timers = _patch(monkeypatch, fake_p)

    r = proc.run_capped(['fake'], timeout=5, max_bytes=100)

    assert r.stdout == b''
    assert r.cut is False
    assert r.returncode == 0
    assert fake_p.alive is False
    assert fake_p.stdout.closed is True
    assert timers[0].cancelled is True
