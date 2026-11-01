"""The MXC transport pumps a long-running launcher: output goes to a Core-supplied
sink as it arrives (bounded per stream and in total), stdin comes from a Core-supplied
reader, the deadline is the policy's (task limits), and one drain thread owns the
handles while any other thread can only ask it to stop."""

import threading
from types import SimpleNamespace

import pytest

from archeus.node import mxc, mxc_native as native

APP = 'C:\\launcher.exe'


class FakeWin32:
    def __init__(self, reads=None, exit=17):
        self.handles, self.events, self.closes = {}, [], []
        self.reads = reads if reads is not None else {1: [b'out', b''], 2: [b'err', b'']}
        self.input = []
        self.writes = []
        self.now, self.exit = 0, exit
        self.n = 0

    def allocate(self, name):
        self.n += 1
        self.handles[self.n + 100] = name
        return self.n + 100

    def protected_policy(self, data):
        return 'C:\\protected\\policy.json', self.allocate('policy')

    def remove_policy(self, path, handle):
        self.close_handle(handle)

    def pipe(self, *, parent_reads):
        number = sum(name.startswith('parent') for name in self.handles.values())
        return self.allocate('parent%d' % number), self.allocate('child%d' % number)

    def attribute_list(self, handles):
        return self.allocate('attributes')

    def delete_attribute_list(self, handle):
        self.close_handle(handle)

    def create_process_w(self, **kwargs):
        return self.allocate('process'), self.allocate('thread'), 123

    def creation_time(self, process):
        return 456

    def terminate_process(self, process):
        self.events.append('kill')

    def close_handle(self, handle):
        self.closes.append(self.handles.pop(handle))

    def poll(self, process):
        return self.exit

    def read(self, handle, size):
        queue = self.reads[int(self.handles[handle][-1])]
        return queue.pop(0) if queue else None

    def write(self, handle, data):
        self.writes.append(data)
        return len(data)

    def pause(self, seconds):
        self.now += seconds
        assert self.now < 5, 'runaway drain'


class Sink:
    def __init__(self, hook=None):
        self.got, self.hook = [], hook

    def __call__(self, name, data):
        self.got.append((name, data))
        if self.hook:
            self.hook(len(self.got))


def launch(api=None, *, timeout=10, **limits):
    api = api or FakeWin32()
    limits.setdefault('output_limit', 8)
    transport = native.Transport(api, api, clock=lambda: api.now, pause=api.pause, **limits)
    policy = SimpleNamespace(raw={'process': {'cwd': 'C:\\work', 'timeout': timeout}})
    path = transport.stage_policy(policy.raw)
    return api, transport.create_suspended([APP, path], policy=policy)


def test_partial_reads_reach_the_sink_in_arrival_order_and_not_the_memory_stream():
    api, child = launch(FakeWin32({1: [b'ab', None, b'cd', b''], 2: [b'', ]}))
    sink = Sink()
    child.attach(sink)
    assert child.wait() == 17
    assert sink.got == [('stdout', b'ab'), ('stdout', b'cd')]
    assert child.stdout.read() == b'' and child.stderr.read() == b''
    assert api.handles == {}


def test_each_stream_is_named_for_the_sink():
    api, child = launch(FakeWin32({1: [b'o', b''], 2: [b'e', b'']}))
    sink = Sink()
    child.attach(sink)
    child.wait()
    assert sink.got == [('stdout', b'o'), ('stderr', b'e')]


def test_without_a_sink_the_memory_streams_still_fill():
    api, child = launch()
    child.attach(stdin_reader=lambda size: b'')
    child.wait()
    assert child.stdout.read() == b'out' and child.stderr.read() == b'err'


def test_the_per_stream_bound_stops_the_launch_and_withholds_the_chunk():
    api, child = launch(FakeWin32({1: [b'12345678', b'9'], 2: [b'']}, exit=None))
    sink = Sink()
    child.attach(sink)
    with pytest.raises(mxc.MxcUnavailable, match='bound exceeded'):
        child.wait()
    assert sink.got == [('stdout', b'12345678')]
    assert api.events == ['kill'] and api.handles == {}
    assert child.poll() == 1


def test_the_total_bound_stops_two_streams_each_within_their_own():
    api, child = launch(FakeWin32({1: [b'123456', b''], 2: [b'abcdef', b'']}),
                        total_limit=10)
    sink = Sink()
    child.attach(sink)
    with pytest.raises(mxc.MxcUnavailable, match='bound exceeded'):
        child.wait()
    assert sink.got == [('stdout', b'123456')]
    assert api.handles == {}


def test_the_total_bound_defaults_to_two_full_streams_and_counts_across_reads():
    api = FakeWin32({1: [b'1234', b'5678', b''], 2: [b'abcd', b'efgh', b'']})
    _, child = launch(api)
    assert child.transport.total_limit == 16
    sink = Sink()
    child.attach(sink)
    assert child.wait() == 17
    assert sum(len(d) for _, d in sink.got) == 16


@pytest.mark.parametrize('limits', [{'total_limit': 0}, {'total_limit': -1}])
def test_a_nonpositive_total_bound_is_refused(limits):
    api = FakeWin32()
    with pytest.raises(ValueError, match='positive output bound'):
        native.Transport(api, api, **limits)


def test_cancel_during_the_drain_keeps_what_was_delivered_and_closes_everything():
    api, child = launch(FakeWin32({1: [b'a', b'b', b'c'], 2: []}, exit=None))
    sink = Sink()
    child.attach(sink)
    with pytest.raises(mxc.MxcUnavailable, match='cancelled during drain'):
        child.wait(cancelled=lambda: len(sink.got) == 2)
    assert sink.got == [('stdout', b'a'), ('stdout', b'b')]
    assert api.events == ['kill'] and api.handles == {}
    with pytest.raises(mxc.MxcUnavailable, match='launcher cancelled'):
        child.wait()


def test_another_thread_can_only_ask_the_drain_to_stop():
    api, child = launch(FakeWin32({1: [b'a', b'b', b'c'], 2: []}, exit=None))
    seen = []

    def from_core(count):
        if count == 1:
            t = threading.Thread(target=child.terminate)
            t.start()
            t.join()
            seen.append((dict(api.handles), list(api.events), child.poll()))

    child.attach(Sink(from_core))
    with pytest.raises(mxc.MxcUnavailable, match='cancelled during drain'):
        child.wait()
    handles, events, poll = seen[0]
    assert handles and events == [] and poll is None
    assert api.events == ['kill'] and api.handles == {}


def test_a_sink_that_terminates_on_the_drain_thread_does_not_pull_handles_from_under_it():
    api, child = launch(FakeWin32({1: [b'a', b'b'], 2: []}, exit=None))
    child.attach(Sink(lambda count: child.terminate()))
    with pytest.raises(mxc.MxcUnavailable, match='cancelled during drain'):
        child.wait()
    assert api.events == ['kill'] and api.closes.count('process') == 1
    assert api.handles == {}


def test_a_sink_that_raises_ends_the_launch_with_its_own_error():
    api, child = launch(FakeWin32({1: [b'a', b'b'], 2: []}, exit=None))
    sink = Sink(lambda count: (_ for _ in ()).throw(OSError('disk full')))
    child.attach(sink)
    with pytest.raises(OSError, match='disk full'):
        child.wait()
    assert len(sink.got) == 1
    assert api.events == ['kill'] and api.handles == {}
    assert child.poll() == 1
    with pytest.raises(mxc.MxcUnavailable, match='launcher cancelled'):
        child.wait()


def test_the_stdin_reader_is_fed_until_eof_then_the_pipe_closes_once():
    api, child = launch(FakeWin32({1: [None] * 5 + [b''], 2: [None] * 5 + [b'']}))
    chunks = [b'abc', None, b'def', b'']
    asked = []

    def reader(size):
        asked.append(size)
        return chunks.pop(0)

    child.attach(stdin_reader=reader)
    assert child.wait() == 17
    assert api.writes == [b'abc', b'def']
    assert chunks == [] and len(asked) == 4 and set(asked) == {65536}
    assert api.closes.count('parent0') == 1
    assert child.stdin.closed and api.handles == {}


def test_a_stdin_reader_with_nothing_yet_keeps_the_pipe_open_until_the_deadline():
    api, child = launch(FakeWin32(exit=None), timeout=0.01)
    child.attach(stdin_reader=lambda size: None)
    with pytest.raises(TimeoutError, match='launcher I/O deadline'):
        child.wait()
    assert 'parent0' in api.closes and api.writes == []
    assert api.handles == {}


def test_a_stdin_reader_that_raises_ends_the_launch():
    api, child = launch(FakeWin32(exit=None))

    def reader(size):
        raise ValueError('prompt file vanished')

    child.attach(stdin_reader=reader)
    with pytest.raises(ValueError, match='vanished'):
        child.wait()
    assert api.events == ['kill'] and api.handles == {}


def test_deadline_expiry_keeps_the_output_so_far_and_kills_the_running_launcher():
    api, child = launch(FakeWin32({1: [b'x'], 2: []}, exit=None), timeout=0.01)
    sink = Sink()
    child.attach(sink)
    with pytest.raises(TimeoutError, match='launcher I/O deadline'):
        child.wait()
    assert sink.got == [('stdout', b'x')]
    assert api.events == ['kill'] and api.handles == {}
    assert child.poll() == 1


def test_a_caller_timeout_overrides_the_policy_deadline():
    api, child = launch(FakeWin32(exit=None), timeout=1000)
    with pytest.raises(TimeoutError):
        child.wait(0.005)
    assert api.now < 0.1


def test_the_deadline_is_the_task_limit_the_policy_was_compiled_from(tmp_path):
    policy = mxc.compile_policy(
        workspace=str(tmp_path), cwd=str(tmp_path), command_line='agent.exe',
        env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': str(tmp_path)}, timeout_ms=2500)
    api = FakeWin32()
    transport = native.Transport(api, api)
    path = transport.stage_policy(policy.raw)
    child = transport.create_suspended([APP, path], policy=policy)
    assert child.timeout == 2.5
    child.terminate()


def test_poll_is_none_until_the_drain_has_returned_whatever_the_kernel_says():
    api, child = launch(FakeWin32({1: [b'a', b'b', b''], 2: [b'']}))
    seen = []
    child.attach(Sink(lambda count: seen.append(child.poll())))
    assert child.poll() is None
    assert child.wait() == 17
    assert seen == [None, None]
    assert child.poll() == 17


def test_a_second_wait_replays_the_exit_and_feeds_the_sink_nothing():
    api, child = launch()
    sink = Sink()
    child.attach(sink)
    assert child.wait() == 17
    got, writes = list(sink.got), list(api.writes)
    assert child.wait() == 17
    assert sink.got == got and api.writes == writes


def test_a_wait_from_inside_the_drain_is_refused_not_nested():
    api, child = launch(FakeWin32({1: [b'a'], 2: []}, exit=None))
    child.attach(Sink(lambda count: child.wait()))
    with pytest.raises(mxc.MxcUnavailable, match='already draining'):
        child.wait()
    assert api.events == ['kill'] and api.handles == {}


def test_a_wait_from_another_thread_is_refused_while_the_drain_runs():
    api, child = launch(FakeWin32({1: [b'a', b'b'], 2: []}, exit=None), timeout=0.01)
    errors = []

    def other(count):
        def attempt():
            try:
                child.wait()
            except mxc.MxcUnavailable as err:
                errors.append(str(err))
        t = threading.Thread(target=attempt)
        t.start()
        t.join()

    child.attach(Sink(other))
    with pytest.raises(TimeoutError):
        child.wait()
    assert errors and set(errors) == {'launcher already draining'}


def test_attach_is_refused_during_the_drain_and_after_close():
    api, child = launch(FakeWin32({1: [b'a'], 2: []}, exit=None))
    refused = []

    def late(count):
        with pytest.raises(mxc.MxcUnavailable, match='not attachable'):
            child.attach(Sink())
        refused.append(count)

    child.attach(Sink(late))
    with pytest.raises(TimeoutError):
        child.wait(0.005)
    assert refused
    with pytest.raises(mxc.MxcUnavailable, match='not attachable'):
        child.attach(Sink())
