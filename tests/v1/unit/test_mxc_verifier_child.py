"""PV20 B11: the child of a confined verifier check on MXC, over a launch that is a stub.

Nothing here starts a process: the launch is an object whose `wait` is scripted, which is
all `ConfinedChild` asks of it (`process.attach`, `wait`).
"""

import threading

import pytest

from archeus.node import mxc_native, mxc_verifier, staging
from archeus.node.mxc_verifier import ConfinedChild


class Launch:
    def __init__(self, result=7, gate=None):
        self.result, self.gate, self.attached = result, gate, None
        self.process, self.stop_reason, self.cancelled = self, None, None

    def attach(self, sink, stdin_reader):
        self.attached = (sink, stdin_reader)

    def cancel(self, *, reason):
        self.cancelled = reason
        return {'reason': reason}

    def wait(self, cancelled=lambda: False):
        if self.gate is not None:
            while not cancelled():
                if self.gate.wait(0.01):
                    break
            else:
                raise mxc_native.MxcUnavailable('launcher cancelled during drain')
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.fixture
def files(tmp_path):
    stdin, out = tmp_path / 'stdin', tmp_path / 'out.log'
    stdin.write_bytes(b'')
    out.write_bytes(b'')
    return str(stdin), str(out)


def child(launch, files, timeout=7):
    return ConfinedChild(launch, timeout, *files)


def test_the_exit_is_the_workloads_and_a_zero_is_an_exit(files):
    assert child(Launch(7), files).wait(5) == 7
    assert child(Launch(0), files).wait(5) == 0


def test_the_sink_appends_stdout_and_stderr_and_the_reader_is_the_stdin_file(tmp_path):
    stdin, out = tmp_path / 'stdin', tmp_path / 'out.log'
    stdin.write_bytes(b'abc')
    out.write_bytes(b'before|')
    gate = threading.Event()
    launch = Launch(gate=gate)
    c = child(launch, (str(stdin), str(out)))
    sink, reader = launch.attached
    sink('stdout', b'one|')
    sink('stderr', b'two|')
    assert open(out, 'rb').read() == b'before|one|two|'         # flushed, not held back
    assert reader(2) == b'ab' and reader(8) == b'c' and reader(8) == b''
    gate.set()
    assert c.wait(5) == 7


def test_a_child_that_has_not_ended_answers_none(files):
    gate = threading.Event()
    c = child(Launch(gate=gate), files)
    assert c.wait(0) is None and c.wait(0.05) is None
    gate.set()
    assert c.wait(5) == 7


def test_wait_gives_a_slow_launch_the_time_it_was_given(files):
    gate = threading.Event()
    c = child(Launch(gate=gate), files)
    threading.Timer(0.1, gate.set).start()
    assert c.wait(5) == 7


def test_a_deadline_is_a_timeout_fault_with_exit_one(files):
    c = child(Launch(TimeoutError('launcher I/O deadline')), files, timeout=9)
    assert c.wait(5) == 1
    assert c.fault == 'timed out after 9s'


def test_a_bound_or_a_transport_fault_is_a_fault_not_an_exception(files):
    c = child(Launch(mxc_native.MxcUnavailable('launcher output bound exceeded')), files)
    assert c.wait(5) == 1
    assert c.fault == 'launcher_failed: launcher output bound exceeded'
    d = child(Launch(OSError('disk full')), files)
    assert d.wait(5) == 1 and d.fault == 'launcher_failed: disk full'


def test_a_fault_of_cores_own_is_raised_from_wait_and_is_no_fault(files):
    c = child(Launch(staging.StageError('MXC workload outcome is unavailable')), files)
    with pytest.raises(staging.StageError, match='outcome is unavailable'):
        c.wait(5)
    assert c.fault is None
    d = child(Launch(ValueError('a bug')), files)
    with pytest.raises(ValueError, match='a bug'):
        d.wait(5)
    assert d.fault is None


def test_both_files_are_closed_once_the_drain_is_over(files):
    c = child(Launch(), files)
    c.wait(5)
    assert c._stdin.closed and c._out.closed


def test_a_launch_that_cannot_be_attached_leaves_no_file_open(files, monkeypatch):
    opened = []

    def recording(path, mode):
        opened.append(open(path, mode))
        return opened[-1]
    monkeypatch.setattr(mxc_verifier, 'open', recording, raising=False)
    launch = Launch()

    def refuse(sink, stdin_reader):
        raise mxc_native.MxcUnavailable('launcher is not attachable')
    launch.attach = refuse
    with pytest.raises(mxc_native.MxcUnavailable, match='not attachable'):
        child(launch, files)
    assert len(opened) == 2 and all(f.closed for f in opened)


def test_cancel_stops_the_drain_and_ends_the_launch_with_the_first_reason(files):
    launch = Launch(gate=threading.Event())
    c = child(launch, files)
    assert c.wait(0) is None
    assert c.cancel('over the cap') == {'reason': 'over the cap'}
    assert c.wait(0) == 1 and c.fault == 'launcher_failed: launcher cancelled during drain'
    c.cancel('second')
    assert launch.stop_reason == 'over the cap' and launch.cancelled == 'second'
