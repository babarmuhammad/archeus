from types import SimpleNamespace

import pytest

from archeus.node import mxc, mxc_native as native


class FakeWin32:
    def __init__(self, failure=None):
        self.handles = {}
        self.failure = failure
        self.events = []
        self.reads = {1: [b'out', b''], 2: [b'err', b'']}
        self.now = 0
        self.exit = 17
        self.stalled = False

    def point(self, name):
        self.events.append(name)
        if self.failure == name:
            raise OSError(name)

    def allocate(self, name):
        self.point(name)
        handle = len(self.events) + 100
        self.handles[handle] = name
        return handle

    def protected_policy(self, data):
        return 'C:\\protected\\policy.json', self.allocate('policy')

    def remove_policy(self, path, handle):
        self.close_handle(handle)

    def pipe(self, *, parent_reads):
        number = sum(name.startswith('parent') for name in self.handles.values())
        parent = self.allocate('parent%d' % number)
        try:
            return parent, self.allocate('child%d' % number)
        except BaseException:
            self.close_handle(parent)
            raise

    def attribute_list(self, handles):
        self.allowlist = handles
        return self.allocate('attributes')

    def delete_attribute_list(self, handle):
        self.close_handle(handle)

    def create_process_w(self, **kwargs):
        self.kwargs = kwargs
        self.point('create')
        process = self.allocate('process')
        try:
            return process, self.allocate('thread'), 123
        except BaseException:
            self.close_handle(process)
            raise

    def creation_time(self, process):
        self.point('time')
        return 456

    def assign_job(self, job, process):
        assert job == 'core-job'
        self.point('assign')

    def in_job(self, job, process):
        self.point('query')
        return self.failure != 'membership'

    def resume_thread(self, thread):
        self.point('resume')
        return 1

    def terminate_process(self, process):
        self.events.append('kill')

    def close_handle(self, handle):
        del self.handles[handle]

    def poll(self, process):
        return self.exit

    def read(self, handle, size):
        index = int(self.handles[handle][-1])
        queue = self.reads[index]
        return queue.pop(0) if queue else None

    def write(self, handle, data):
        return 0 if self.stalled else len(data)

    def pause(self, seconds):
        self.now += seconds


def setup(api):
    transport = native.Transport(api, api, clock=lambda: api.now, pause=api.pause,
                                 output_limit=8)
    policy = SimpleNamespace(raw={'process': {'cwd': 'C:\\work', 'timeout': 10}})
    path = transport.stage_policy(policy.raw)
    return transport, policy, path


def create(api):
    transport, policy, path = setup(api)
    child = transport.create_suspended(['C:\\space ü\\launcher.exe', '--debug', path],
                                       policy=policy)
    return transport, child


@pytest.mark.parametrize('failure', ['policy', 'parent0', 'child0', 'parent1', 'child1',
                                    'parent2', 'child2', 'attributes', 'create',
                                    'process', 'thread', 'time'])
def test_allocation_fault_closes_every_handle(failure):
    api = FakeWin32(failure)
    with pytest.raises(OSError):
        create(api)
    assert api.handles == {}
    if failure == 'time':
        assert 'kill' in api.events


def test_suspended_allowlist_and_resume_once():
    api = FakeWin32()
    transport, child = create(api)
    assert api.kwargs['flags'] & native.CREATE_SUSPENDED
    assert api.kwargs['application'] == 'C:\\space ü\\launcher.exe'
    assert api.kwargs['command_line'].startswith('"C:\\space ü\\launcher.exe" --debug ')
    assert api.kwargs['std_handles'] == api.allowlist
    assert len(api.allowlist) == 3 and 'core-job' not in api.allowlist
    assert child.create_time == 456
    transport.assign_job('core-job', child)
    assert transport.in_job('core-job', child)
    assert transport.resume(child) == 1
    with pytest.raises(mxc.MxcUnavailable, match='already resumed'):
        transport.resume(child)
    assert api.events.count('resume') == 1
    child.terminate()
    child.terminate()
    assert api.events.count('kill') == 1
    assert api.handles == {}


@pytest.mark.parametrize('failure', ['assign', 'query', 'membership', 'resume'])
def test_job_fault_kills_and_closes(failure, monkeypatch):
    api = FakeWin32(failure)
    transport, policy, _ = setup(api)
    # setup's staged lease is unused: NativeMxc stages its own policy.
    for path, handle in list(transport._policies.items()):
        api.remove_policy(path, handle)
    transport._policies.clear()
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    monkeypatch.setattr(mxc, 'validate_policy', lambda policy: None)
    monkeypatch.setattr(mxc, '_path', lambda path: path)
    backend = mxc.NativeMxc(transport, lambda raw: True)
    with pytest.raises((OSError, mxc.MxcUnavailable)):
        backend.spawn(policy, exe='C:\\launcher.exe', job='core-job')
    assert 'kill' in api.events
    assert api.handles == {}

def test_both_outputs_and_eof_keep_launcher_status():
    api = FakeWin32()
    _, child = create(api)
    child.stdin.write(b'input')
    assert child.wait() == 17
    assert child.launcher_exit == 17
    assert child.stdout.read() == b'out'
    assert child.stderr.read() == b'err'
    assert child.stdin.closed
    assert api.handles == {}


def test_output_bound():
    api = FakeWin32()
    api.reads[1] = [b'12345678', b'9']
    _, child = create(api)
    with pytest.raises(mxc.MxcUnavailable, match='bound'):
        child.wait()
    assert api.handles == {}


@pytest.mark.parametrize('kind', ['stdin', 'descendant', 'both-full', 'cancel'])
def test_deadline_and_cancel_during_drain(kind):
    api = FakeWin32()
    api.exit = None
    api.stalled = True
    api.reads = {1: [], 2: []}
    if kind == 'both-full':
        api.reads = {1: [b'12345678', b'9'], 2: [b'12345678', b'9']}
    if kind == 'descendant':
        api.exit = 0
    _, child = create(api)
    child.stdin.write(b'stalled')
    with pytest.raises((TimeoutError, mxc.MxcUnavailable)):
        child.wait(cancelled=lambda: kind == 'cancel' and api.now > 0)
    child.terminate()
    assert api.handles == {}




def test_caller_can_close_stdin_before_wait():
    api = FakeWin32()
    _, child = create(api)
    child.stdin.write(b'input')
    child.stdin.close()
    assert child.wait() == 17
    assert api.handles == {}


@pytest.mark.parametrize('application', ['launcher.exe', '\\launcher.exe', 'C:launcher.exe'])
def test_relative_application_refused_and_policy_released(application):
    api = FakeWin32()
    transport, policy, path = setup(api)
    with pytest.raises(mxc.MxcUnavailable, match='absolute'):
        transport.create_suspended([application, '--debug', path], policy=policy)
    assert api.handles == {}
    assert 'create' not in api.events


@pytest.mark.parametrize('count', [0, 2, 0xffffffff])
def test_wrong_suspend_count_cannot_retry(count):
    api = FakeWin32()
    transport, child = create(api)
    api.resume_thread = lambda thread: count
    with pytest.raises(mxc.MxcUnavailable, match='suspend count'):
        transport.resume(child)
    with pytest.raises(mxc.MxcUnavailable, match='already resumed'):
        transport.resume(child)
    child.terminate()
    assert api.handles == {}


def test_full_outputs_are_serviced_in_same_turn():
    api = FakeWin32()
    api.reads = {1: [b'12345678', b''], 2: [b'abcdefgh', b'']}
    reads = []
    read = api.read

    def check(handle, size):
        reads.append((api.now, api.handles[handle]))
        return read(handle, size)

    api.read = check
    _, child = create(api)
    assert child.wait() == 17
    assert reads[:2] == [(0, 'parent1'), (0, 'parent2')]
    assert child.stdout.read() == b'12345678'
    assert child.stderr.read() == b'abcdefgh'
    assert api.handles == {}


def test_native_backend_stays_disabled():
    api = FakeWin32()
    backend = native.Backend(api, api, lambda raw: True)
    with pytest.raises(mxc.MxcUnavailable, match='disabled'):
        backend.spawn(None, exe='C:\\launcher.exe', job='core-job')
    assert api.handles == {}


def test_quoted_argument_and_trailing_backslash():
    api = FakeWin32()
    transport, policy, path = setup(api)
    child = transport.create_suspended(
        ['C:\\launcher.exe', 'a"b', 'space \\', path], policy=policy)
    assert api.kwargs['command_line'] == (
        'C:\\launcher.exe a\\"b "space \\\\" C:\\protected\\policy.json')
    child.terminate()
    assert api.handles == {}
