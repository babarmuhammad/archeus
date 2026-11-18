"""T-1011: the highest-risk uncovered branches of `archeus/node/mxc_context.py`, lines
1-128 inclusive (the whole slice: `_refused`, `MxcChild`, `MxcIsolationContext`).

Nothing here starts a process, loads a DLL or reaches a Windows primitive: the launch is
the seam-faked `FakeLaunch`/`FakeProcess` below (the same shape `local.MxcLaunch` and
`mxc_native.Process` present to this module), the boundary, the request and the OS
tripwire are the ones `test_pv20_isolation.py` already uses, and the one OS read this
slice makes (`base_create_time`) is faked in the `case` fixture. Every pump thread is the
real thread the source starts; what is scripted is only the transport underneath it.

The ten selected branches, ranked by risk (fail-closed and denial first, then bounds,
then error paths), with the branch each test would catch by removal or inversion:

1. 126-128 `isinstance(err, IsolationUnavailable)` TRUE after the launch call: a refusal
   of the transport keeps its stable code instead of dissolving into `launch_failed`.
2. 101-104 + 23-24 (both arms of the detail ternary): an establishment refusal is
   `SpawnFailed('isolation: <code> (<detail>)')`, with no second attempt anywhere.
3. 75-81 under the lock, racing the drain: one reason wins, and the launch is ended only
   once the pump handed the launch back.
4. 81 `self.reason or reason` TRUE: the first reason is the one the launch is told, even
   by a second caller with newer text.
5. 76 `not self._done.is_set()` FALSE + 81 FALSE: a stop that arrives after the end is
   never recorded as a stop of Core's, and the launch is still told.
6. 79-80 `self._thread.is_alive()` FALSE: a stop before the pump ever ran ends the launch
   instead of joining a thread that never started.
7. 39 with 119-121 (`child is None`): a construction the transport refused ends the launch,
   registers nothing and never starts a pump.
8. 91-93 a present but zero bound stays the bound: it is never widened to `STREAM_BYTES`.
9. 95-96 `int(timeout_s * 1000)`: the deadline is truncated, never rounded up.
10. 52-58 `launch.wait` raising: the transport's error never leaves the pump, the pump
   ends the launch itself and the child still answers an exit.

The two reachable branches left in the slice are closed last, so that nothing in 1-128
goes unexercised:

11. 41-45 the sink and the reader `attach` was handed: output reaches the stream file
    while the launch is still running, and the prompt comes back through the pump's read.
12. 121-125 `child is not None` (the cleanup at 124-125): a child that was built and
    registered, and then could not be started at all, ends its launch and drops its
    registration, or the profile reads busy until Core restarts.
"""

import dataclasses
import os
import threading
import time
from types import SimpleNamespace

import pytest

from archeus.harnesses import base
from archeus.infra.paths import ExecPaths
from archeus.node import isolation as iso, mxc_context, mxc_native
from archeus.node.mxc_context import MxcChild, MxcIsolationContext

# the synthetic boundary, the satisfying request and the autouse OS tripwire the
# isolation gap tests already use (importing the tripwire arms it here too)
from v1.unit.test_pv20_isolation import (FakeBoundary, authority,  # noqa: F401
                                         os_tripwire)  # noqa: F401

END = 'quarantined'


class FakeProcess:
    """`mxc_native.Process` as this slice meets it: the child attaches its sink and its
    stdin reader and never touches a handle. `attach` can refuse, as it does for a
    launcher that is already draining or already closed."""

    def __init__(self, refuse=None):
        self.refuse = refuse
        self.attached, self.terminations, self.closes = [], [], []

    def attach(self, sink=None, stdin_reader=None):
        if self.refuse is not None:
            raise self.refuse
        self.attached.append((sink, stdin_reader))

    def terminate(self):
        self.terminations.append('terminate')

    def close(self):
        self.closes.append('close')


class FakeLaunch:
    """`local.MxcLaunch`'s public shape for this slice, with the drain scripted. The
    drain blocks until the test releases it (`hold`), which is how a long agent looks;
    `ends_now` is a launch that finished before Core looked at it. `cancel` is idempotent
    like the real one: the second caller is told the first ending."""

    def __init__(self, *, pid=424242, code=17, ends_now=False, wait_raises=None,
                 cancel_raises=None, process=None):
        self.pid, self.code = pid, code
        self.process = process if process is not None else FakeProcess()
        self.stop_reason, self.end_state = None, None
        self.waits, self.cancels, self.order = [], [], []
        self.entered, self.hold = threading.Event(), threading.Event()
        self.saw_stop = None
        self.ends_now, self.wait_raises, self.cancel_raises = ends_now, wait_raises, cancel_raises
        if ends_now:
            self.hold.set()

    def wait(self, timeout=None, *, cancelled=None):
        self.waits.append(cancelled)
        self.entered.set()
        # a drain owns its handles until it returns, and sees a stop of Core's only
        # through the predicate this slice handed it: that is what ends a long agent
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.hold.is_set():
                break
            if cancelled is not None and cancelled():
                break
            time.sleep(0.005)
        else:
            raise AssertionError('the drain never ended')
        self.saw_stop = cancelled() if cancelled is not None else None
        self.order.append('pump returned')
        if self.wait_raises is not None:
            raise self.wait_raises
        return self.code

    def driven_by_transport(self):
        """The two hooks `attach` was given, as the transport meets them."""
        return self.process.attached[0] if self.process.attached else (None, None)

    def cancel(self, *, reason='cancelled', outcome=None):
        self.cancels.append(reason)
        self.order.append('launch ended')
        if self.cancel_raises is not None:
            raise self.cancel_raises
        if self.end_state is None:
            self.end_state = {'state': END, 'reason': reason}
        return self.end_state


class MxcFakeBoundary(FakeBoundary):
    """The MXC half of the boundary: it takes the transport's bounds, hands back the
    launch under test, and can refuse the launch or the attach the way the production
    MXC boundary does. Opening an inherited stdio handle is a failure: this context opens
    none."""

    def __init__(self):
        super().__init__()
        self.refuse = None                # the error `launch` raises, if it refuses
        self.establish_refuses = None     # the error `create_profile` raises
        self.attach_refuses = None        # the error the handed launch's attach raises
        self.wait_raises = None
        self.cancel_raises = None
        self.ends_now = False
        self.handed, self.bounds, self.opened = [], [], []

    def create_profile(self, execution_id):
        if self.establish_refuses is not None:
            raise self.establish_refuses
        return FakeBoundary.create_profile(self, execution_id)

    def open_inherited(self, path, mode):
        self.opened.append((path, mode))
        raise AssertionError('the MXC launch opens no inherited handle')

    def launch(self, argv, *, cwd, env, profile, job, stdin, stdout, **limits):
        self.launch_calls.append({'argv': argv, 'cwd': cwd, 'env': env, 'profile': profile,
                                  'job': job, 'stdin': stdin, 'stdout': stdout})
        self.bounds.append(limits)
        if self.refuse is not None:
            raise self.refuse
        launch = FakeLaunch(ends_now=self.ends_now, wait_raises=self.wait_raises,
                            cancel_raises=self.cancel_raises,
                            process=FakeProcess(refuse=self.attach_refuses))
        self.handed.append(launch)
        return launch


@pytest.fixture
def case(tmp_path, monkeypatch, boundary):
    """Core's authority for one execution over the fake MXC boundary, with the process I/O
    files its task reads and writes. The detached launcher is booby-trapped: the isolated
    path has no fallback to reach. The pump's join is shortened so a drain the test holds
    never puts it near a second of real waiting."""
    monkeypatch.setattr(mxc_context, 'base_create_time', lambda pid: 1730000000)
    monkeypatch.setattr(mxc_context, 'PUMP_JOIN_S', 0.05)
    monkeypatch.setattr(base.proc, 'spawn_detached',
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError('the detached launcher was reached')))
    a, b, req, node = authority(tmp_path, boundary=boundary)
    paths = ExecPaths(req.execution_id)
    os.makedirs(paths.dir, exist_ok=True)
    with open(paths.prompt, 'wb') as f:
        f.write(b'go\n')
    yield SimpleNamespace(authority=a, boundary=b, request=req, node=node, paths=paths)
    for launch in b.handed:                       # no pump thread outlives its test
        launch.hold.set()
    for child in list(a.children.values()):
        child.cancel('test teardown')


@pytest.fixture
def boundary():
    return MxcFakeBoundary()


def isolated(case, **limits):
    """One isolated launch through `MxcIsolationContext.launch`, with the task's limits
    as keyword bounds. Returns (child, the launch the boundary handed back)."""
    case.request = dataclasses.replace(case.request, limits=tuple(sorted(limits.items())))
    request = case.request
    ctx = MxcIsolationContext(case.authority, request)
    child, _ = ctx.launch(['agent.exe'], cwd=request.workspace,
                          env={'SYSTEMROOT': 'C:\\Windows'}, paths=case.paths)
    return child, case.boundary.handed[-1]


def drained(child, timeout=5.0):
    """Release the held drain, wait for the pump thread to hand the launch back, and
    answer the exit the child reports. Bounded: no test hangs on a fake that never ends."""
    child.launch.hold.set()
    child._thread.join(timeout)
    assert not child._thread.is_alive(), 'the pump never returned'
    return child.poll()


# ── 1, 2: the refusals, which are the whole fail-closed surface of the launch ──────

def test_a_transport_refusal_keeps_its_stable_code_and_is_never_launch_failed(case):
    """mxc_context.py:126-128, `isinstance(err, IsolationUnavailable)` TRUE after the
    launch: what the transport refused with a code is reported as that code."""
    case.boundary.refuse = iso.IsolationUnavailable('profile_unknown',
                                                    'psec:x was not reserved')
    with pytest.raises(base.SpawnFailed) as caught:
        isolated(case)
    assert str(caught.value) == 'isolation: profile_unknown (psec:x was not reserved)'
    assert 'launch_failed' not in str(caught.value)
    assert case.boundary.handed == [] and case.boundary.launch_calls != []
    assert case.authority.children == {} and case.authority._live == {}
    assert case.authority.record(case.request.execution_id).pid is None


@pytest.mark.parametrize('reason,detail,expected', [
    ('platform', 'this platform has no AppContainer boundary',
     'isolation: platform (this platform has no AppContainer boundary)'),
    ('mxc_ledger', '', 'isolation: mxc_ledger')],
    ids=['with-detail', 'no-detail'])
def test_an_establishment_refusal_is_the_end_of_the_launch(case, reason, detail, expected):
    """mxc_context.py:101-104 with the detail arms of 23-24: no identity, no launch, no
    pump, no stream file, and never a second attempt through the detached launcher."""
    case.boundary.establish_refuses = iso.IsolationUnavailable(reason, detail)
    with pytest.raises(base.SpawnFailed) as caught:
        isolated(case)
    assert str(caught.value) == expected
    assert case.boundary.launch_calls == [] and case.boundary.handed == []
    assert case.authority.children == {} and case.authority._live == {}
    assert not os.path.exists(case.paths.stream)


# ── 3-6: every stop of Core's, its reason, and who is allowed to end what ──────────

def test_two_stops_in_flight_agree_on_one_reason_and_end_only_after_the_pump_returned(
        case, monkeypatch):
    """mxc_context.py:75-81 with the drain running: the lock picks one reason, both
    callers are told that one ending, the drain is stopped through the predicate the pump
    handed to `wait`, and no launch is ended while the pump still holds its handles."""
    monkeypatch.setattr(mxc_context, 'PUMP_JOIN_S', 5.0)      # the production-style bound
    child, launch = isolated(case)
    assert launch.entered.wait(5), 'the pump never reached the drain'
    answers, errors = [], []

    def stop(text):
        try:
            answers.append(child.cancel(text))
        except BaseException as err:                      # reported, never swallowed
            errors.append(err)

    first = threading.Thread(target=stop, args=('estop',))
    first.start()
    deadline = time.monotonic() + 1.0
    while child.reason is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert child.reason == 'estop', 'the first stop never reached the child'
    second = threading.Thread(target=stop, args=('limit',))
    second.start()
    first.join(5)
    second.join(5)
    assert errors == [] and len(answers) == 2 and answers[0] is answers[1]
    assert child.reason == launch.stop_reason == 'estop'
    assert launch.cancels == ['estop', 'estop']
    child._thread.join(5)
    assert not child._thread.is_alive()
    assert launch.saw_stop is True                        # the drain saw Core's stop
    assert launch.order[0] == 'pump returned'             # never ended under the pump
    assert launch.order.count('launch ended') == 2
    assert launch.process.terminations == [] and launch.process.closes == []
    assert child.poll() == 17


def test_the_second_caller_is_told_the_first_reason_and_ends_nothing_again(case):
    """mxc_context.py:81 `self.reason or reason` TRUE: once a stop of Core's is recorded,
    the launch is told that reason and never the newer text it is handed."""
    child, launch = isolated(case)
    assert launch.entered.wait(5), 'the pump never reached the drain'
    first = child.cancel('estop')                         # the join gives up: Core ends it
    second = child.cancel('limit')
    assert child.reason == 'estop' and launch.stop_reason == 'estop'
    assert launch.cancels == ['estop', 'estop']
    assert first is second == {'state': END, 'reason': 'estop'}
    assert drained(child) == 17 and launch.saw_stop is True


def test_a_stop_that_arrives_after_the_end_is_never_recorded_as_cores(case):
    """mxc_context.py:76 with `_done` set and 81 taking the caller's text: a launch that
    ended by itself is not rewritten into a cancelled one, and is still ended."""
    case.boundary.ends_now = True
    child, launch = isolated(case)
    assert drained(child) == 17
    state = child.cancel('ended')
    assert child.reason is None and launch.stop_reason is None
    assert launch.cancels == ['ended']
    assert state == {'state': END, 'reason': 'ended'}
    assert child.poll() == 17 and launch.process.terminations == []


def test_a_stop_before_the_pump_ever_ran_ends_the_launch_and_never_joins_it(case, monkeypatch):
    """mxc_context.py:79-80 `self._thread.is_alive()` FALSE: joining a thread that never
    started would raise before the launch was ended, leaving it running unended."""
    real_start = MxcChild.start
    started = []
    monkeypatch.setattr(MxcChild, 'start', lambda self: started.append(self))
    child, launch = isolated(case)
    assert started == [child] and launch.waits == []
    state = child.cancel('disarmed')
    assert state == {'state': END, 'reason': 'disarmed'}
    assert child.reason == launch.stop_reason == 'disarmed'
    assert launch.cancels == ['disarmed']
    launch.hold.set()                                     # it does run later, on its pump
    real_start(child)
    child._thread.join(5)
    assert not child._thread.is_alive() and launch.saw_stop is True
    assert child.poll() == 17 and launch.cancels == ['disarmed']


# ── 7: a construction the transport refused leaves nothing behind ─────────────────

def test_a_launch_whose_attach_was_refused_is_ended_and_never_registered(case):
    """mxc_context.py:39 with 119-121 (`child is None`): the refusal to attach ends the
    launch as `launch failed`, and neither a pump nor a registration survives it."""
    case.boundary.attach_refuses = mxc_native.MxcUnavailable('launcher is not attachable')
    with pytest.raises(base.SpawnFailed) as caught:
        isolated(case)
    assert str(caught.value) == 'isolation: launch_failed (launcher is not attachable)'
    launch = case.boundary.handed[0]
    assert launch.cancels == ['launch failed']
    assert launch.waits == [] and launch.process.attached == []
    assert case.authority.children == {} and case.authority._live == {}
    assert not os.path.exists(case.paths.stream)


# ── 8, 9: the bounds the transport is handed ─────────────────────────────────────

def test_a_zero_output_bound_is_not_widened_to_the_default_stream_bound(case):
    """mxc_context.py:91-93: `output_bytes: 0` is a bound, not an absent key. Read with
    `or` instead of `get(..., STREAM_BYTES)` it silently becomes a 256 MiB allowance."""
    child, launch = isolated(case, output_bytes=0, total_bytes=0)
    assert case.boundary.bounds[0] == {'transport': {'output_limit': 0, 'total_limit': 0}}
    call = case.boundary.launch_calls[0]
    assert (call['stdin'], call['stdout']) == (None, None)
    assert call['job'] == {'job': case.request.execution_id}        # Core's own held Job
    assert drained(child) == 17
    assert launch.stop_reason is None             # nothing asked for it to be ended


def test_the_launch_deadline_is_truncated_and_never_rounded_up(case):
    """mxc_context.py:95-96 `int(timeout_s * 1000)`: 1.005 s is 1004 ms, because a deadline
    is never made longer than the task asked (a `round()` here hands back the extra ms)."""
    child, launch = isolated(case, timeout_s=1.005)
    assert case.boundary.bounds[0]['timeout_ms'] == 1004
    assert 'total_limit' not in case.boundary.bounds[0]['transport']
    assert drained(child) == 17
    assert launch.stop_reason is None             # it ended on its own, in time


# ── 10: the pump's own end ────────────────────────────────────────────────────────

def test_the_pump_end_never_leaks_the_transport_error_to_the_adapter(case):
    """mxc_context.py:52-58: the drain refusing (`AlreadyDraining`, the second wait) is
    the pump's fault to carry: it ends the launch itself, names the error type, and the
    child still answers an exit instead of running forever."""
    case.boundary.wait_raises = mxc_native.AlreadyDraining('launcher already draining')
    child, launch = isolated(case)
    assert drained(child) == 1                            # never 0 without an outcome
    assert isinstance(child.fault, mxc_native.AlreadyDraining)
    assert launch.cancels == ['the pump failed: AlreadyDraining']
    assert child.poll() == 1 and child.reason is None
    assert child.wait(0.2) == 1                           # the adapter's own reading
    assert launch.process.terminations == []


# ── 11, 12: the data path, and a child that never got as far as running ───────────

def test_the_sink_writes_where_the_adapter_is_already_tailing(case):
    """mxc_context.py:41-45: `attach` is handed the child's own two hooks, and while the
    pump still holds the launch they are the only stdio it has. Output that sits in a
    buffer until the end, or a prompt read from a handle the pump never opened, is an
    adapter that tails an empty stream."""
    child, launch = isolated(case)
    assert launch.entered.wait(5), 'the pump never reached the drain'
    sink, reader = launch.driven_by_transport()
    assert (sink, reader) == (child._write, child._read)     # the child's own, not a copy
    sink('output', b'first chunk')
    assert reader(2) == b'go'                                # the prompt, from the pump's read
    with open(case.paths.stream, 'rb') as f:                 # tailed while the launch runs
        assert f.read() == b'first chunk'
    sink('output', b', and the next')
    assert drained(child) == 17
    with open(case.paths.stream, 'rb') as f:
        assert f.read() == b'first chunk, and the next'


def test_a_child_that_could_never_be_started_leaves_no_registration(case, monkeypatch):
    """mxc_context.py:121-125 `child is not None`: the thread could not be started, so
    nothing will ever end this launch from inside. Its launch is ended here and the
    registration is dropped; left registered, the profile reads busy until Core restarts."""
    def no_thread(self):
        raise OSError(11, 'can not start new threads')
    monkeypatch.setattr(MxcChild, 'start', no_thread)
    with pytest.raises(base.SpawnFailed) as caught:
        isolated(case)
    assert str(caught.value) == 'isolation: launch_failed ([Errno 11] can not start new threads)'
    launch = case.boundary.handed[0]
    assert launch.cancels == ['launch failed'] and launch.waits == []
    assert case.authority.children == {} and case.authority._live == {}
    assert case.authority.record(case.request.execution_id).pid == launch.pid
    assert not os.path.exists(case.paths.stream)
