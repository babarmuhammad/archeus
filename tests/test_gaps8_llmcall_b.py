"""T-1327: the highest-risk uncovered branches of claude_sessions/llmcall.py
run_headless, lines 96-157 of the card (96-160 in this worktree: the card's
numbers are three lines short from the Popen call on), at tip 6b1a30b8.
Denial and fail-closed first, then boundaries, then error paths.

Selected branches (worktree line, probe):
1. run_headless 118-119          Popen failure: Result(None, ..., 'could not start <argv0>'), on_spawn never called
2. run_headless 120-121          on_spawn receives the Popen before communicate runs
3. run_headless 141-149          non-zero exit: quota.note_failure gets the full envelope, events.record once
4. run_headless 124-129          cancel set while running: kill_tree runs. Already-finished process: no kill
5. run_headless 151-157          TimeoutExpired: kill_tree, timeout text recorded, timed_out Result
6. run_headless 158-160          generic communicate exception: kill_tree, exception text is the error
7. run_headless 165-168          finally sets done and joins the watcher on success (no watcher left alive)
8. run_headless 143              error text cut to 300 characters
9. run_headless 150              exit 0 returns stripped stdout, empty error, no quota or events call
10. run_headless 131-134         cancel None starts no watcher thread and the call completes normally (control)
Extra: run_headless 161-164      BaseException kills the tree and propagates (not in the card's ten)

Seams: a fake Popen (subprocess.Popen replaced for the duration of each test), fake
proc.kill_tree, fake quota.note_failure and events.record. No child process is started.
"""

import subprocess
import threading

import pytest

from claude_sessions import events, llmcall, proc, quota


class FakeProc:
    def __init__(self, rc=0, stdout='', comm=None):
        self.pid = 4242
        self.returncode = rc
        self.running = False
        self._stdout = stdout
        self._comm = comm

    def poll(self):
        return None if self.running else self.returncode

    def communicate(self, input=None, timeout=None):
        if self._comm is not None:
            return self._comm(self, timeout)
        return (self._stdout, None)


@pytest.fixture
def rig(monkeypatch):
    class Rig:
        pass

    r = Rig()
    r.log, r.procs, r.killed, r.noted, r.recorded = [], [], [], [], []
    r.make = lambda cmd: FakeProc()
    r.spawn_error = None
    r.on_kill = None

    def fake_popen(cmd, **kw):
        r.log.append('popen')
        if r.spawn_error is not None:
            raise r.spawn_error
        p = r.make(cmd)
        r.procs.append(p)
        return p

    def fake_kill(p):
        r.killed.append(p)
        p.running = False
        p.returncode = -9
        if r.on_kill is not None:
            r.on_kill(p)

    monkeypatch.setattr(subprocess, 'Popen', fake_popen)
    monkeypatch.setattr(proc, 'kill_tree', fake_kill)
    monkeypatch.setattr(events, 'record', lambda src, msg, **kw: r.recorded.append((src, msg, kw)))
    monkeypatch.setattr(quota, 'note_failure', lambda args, env, text: r.noted.append((args, env, text)))
    return r


def _new_threads(before):
    return [t for t in threading.enumerate() if t not in before]


def _join_new(before):
    for t in _new_threads(before):
        t.join(2.0)


CMD = ['claude', '-p', '--max-turns', '20']


def test_popen_failure_names_the_program_and_never_spawns_on_spawn(rig):
    rig.spawn_error = OSError('no such file')
    spawned = []
    res = llmcall.run_headless(['no-such-exe-xyz'], 'x', on_spawn=spawned.append)
    assert res.returncode is None and res.stdout == '' and not res.timed_out
    assert res.error.startswith('could not start ') and 'no such file' in res.error
    assert spawned == []
    assert rig.log == ['popen'] and rig.killed == [] and rig.recorded == []


def test_popen_failure_error_names_argv0_without_brackets(rig):
    rig.spawn_error = OSError('no such file')
    res = llmcall.run_headless(['no-such-exe-xyz'], 'x')
    assert res.error.startswith('could not start no-such-exe-xyz: ')


def test_on_spawn_gets_the_popen_before_communicate(rig):
    seen = []

    def comm(p, timeout):
        seen.append('communicate')
        return ('ok', None)

    rig.make = lambda cmd: FakeProc(comm=comm)
    res = llmcall.run_headless(CMD, 'x', on_spawn=lambda p: seen.append(('on_spawn', p)))
    assert seen == [('on_spawn', rig.procs[0]), 'communicate']
    assert res == (0, 'ok', '', '', False)


def test_nonzero_exit_records_once_with_the_full_envelope(rig):
    envelope = '{"result": "limit hit", "usage": {"input_tokens": 1}}'
    rig.make = lambda cmd: FakeProc(rc=3, stdout=envelope)
    res = llmcall.run_headless(CMD, 'x')
    assert res.returncode == 3 and not res.timed_out
    assert res.reason == 'limit hit'
    assert res.error == 'claude exited 3: limit hit'
    assert rig.noted == [(CMD, None, envelope)]
    assert rig.recorded == [('subprocess', 'claude exited 3: limit hit', {'detail': 'claude -p'})]


def test_cancel_while_running_kills_the_tree_once(rig):
    cancel = threading.Event()
    killed = threading.Event()
    rig.on_kill = lambda p: killed.set()

    def comm(p, timeout):
        cancel.set()
        killed.wait(2.0)
        return ('', None)

    def make(cmd):
        p = FakeProc(comm=comm)
        p.running = True
        return p

    rig.make = make
    before = set(threading.enumerate())
    try:
        llmcall.run_headless(CMD, 'x', cancel=cancel)
    finally:
        cancel.set()
        _join_new(before)
    assert rig.killed == [rig.procs[0]]


def test_cancel_after_the_process_finished_kills_nothing(rig):
    cancel = threading.Event()

    def comm(p, timeout):
        cancel.set()
        return ('ok', None)

    rig.make = lambda cmd: FakeProc(comm=comm)
    before = set(threading.enumerate())
    try:
        res = llmcall.run_headless(CMD, 'x', cancel=cancel)
    finally:
        cancel.set()
        _join_new(before)
    assert res == (0, 'ok', '', '', False)
    assert rig.killed == []


def test_timeout_kills_the_tree_and_records_the_timeout(rig):
    def comm(p, timeout):
        raise subprocess.TimeoutExpired(CMD, timeout)

    rig.make = lambda cmd: FakeProc(comm=comm)
    res = llmcall.run_headless(CMD, 'x', timeout=7)
    assert res.returncode is None and res.stdout == '' and res.timed_out
    assert res.error.startswith('timed out after 7s') and 'OmniRoute' in res.error
    assert rig.killed == [rig.procs[0]]
    assert rig.recorded == [('subprocess', res.error, {'detail': 'claude -p'})]


def test_generic_communicate_exception_kills_the_tree_and_returns_its_text(rig):
    def comm(p, timeout):
        raise RuntimeError('pipe broke')

    rig.make = lambda cmd: FakeProc(comm=comm)
    res = llmcall.run_headless(CMD, 'x')
    assert res == (None, '', '', 'pipe broke', False)
    assert rig.killed == [rig.procs[0]]
    assert rig.noted == [] and rig.recorded == []


def test_watcher_thread_is_stopped_when_the_call_returns(rig):
    cancel = threading.Event()
    rig.make = lambda cmd: FakeProc(rc=0, stdout='ok')
    before = set(threading.enumerate())
    try:
        llmcall.run_headless(CMD, 'x', cancel=cancel)
        assert not any(t.is_alive() for t in _new_threads(before))
        assert rig.killed == []
    finally:
        cancel.set()
        _join_new(before)


def test_base_exception_kills_the_tree_and_propagates(rig):
    def comm(p, timeout):
        raise KeyboardInterrupt

    rig.make = lambda cmd: FakeProc(comm=comm)
    with pytest.raises(KeyboardInterrupt):
        llmcall.run_headless(CMD, 'x')
    assert rig.killed == [rig.procs[0]]
    assert rig.noted == [] and rig.recorded == []


def test_error_text_is_cut_to_300_characters(rig):
    rig.make = lambda cmd: FakeProc(rc=1, stdout='x' * 500)
    res = llmcall.run_headless(CMD, 'x')
    assert res.reason == 'x' * 500
    assert res.error == 'claude exited 1: ' + 'x' * 300
    assert rig.recorded[0][1] == res.error


def test_exit_zero_returns_stripped_stdout_and_no_failure_side_effects(rig):
    rig.make = lambda cmd: FakeProc(rc=0, stdout='  hello \n')
    res = llmcall.run_headless(CMD, 'x')
    assert res == (0, 'hello', '', '', False)
    assert rig.noted == [] and rig.recorded == []


def test_no_cancel_starts_no_watcher_thread(rig):
    rig.make = lambda cmd: FakeProc(rc=0, stdout='ok')
    before = set(threading.enumerate())
    res = llmcall.run_headless(CMD, 'x')
    assert res == (0, 'ok', '', '', False)
    assert _new_threads(before) == []
    assert rig.killed == []
