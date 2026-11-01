"""T-247: branches of the native transport left untested by test_mxc_native.py.

Every OS call is faked through the injected Win32 seam, so no handle, pipe or
process is opened and the file runs identically on Linux and on Windows. The
fake keeps a handle ledger and a policy-lease ledger: a test passes only when the
source closes exactly what it opened, once.
"""

import ctypes as c
from types import SimpleNamespace

import pytest

from archeus.node import mxc, mxc_native as native, win32_mxc as w

POLICY = 'C:\\protected\\policy.json'
APP = 'C:\\launcher.exe'


class FakeWin32:
    """Handle ledger for the transport seam: a handle left open is a leak."""

    def __init__(self):
        self.handles = {}
        self.events = []
        self.closes = []
        self.released = []
        self.reads = {1: [b'out', b''], 2: [b'err', b'']}
        self.sizes = []
        self.writes = []
        self.accepted = []
        self.delivered = []
        self.now = 0
        self.exit = 17
        self.polls = 0
        self.created = 456
        self.policy_path = POLICY
        self.failing_close = set()

    # -- allocation ledger -------------------------------------------------
    def allocate(self, name):
        self.events.append(name)
        handle = len(self.events) + 100
        self.handles[handle] = name
        return handle

    def close_handle(self, handle):
        name = self.handles.pop(handle)          # KeyError proves a double close
        if name in self.failing_close:
            self.failing_close.discard(name)     # one injected fault, then it works
            self.handles[handle] = name
            raise OSError(name)
        self.closes.append(name)

    # -- the injected seam -------------------------------------------------
    def protected_policy(self, data):
        self.payload = data
        return self.policy_path, self.allocate('policy')

    def remove_policy(self, path, handle):
        self.released.append(path)
        self.close_handle(handle)

    def pipe(self, *, parent_reads):
        number = sum(name.startswith('parent') for name in self.handles.values())
        return self.allocate('parent%d' % number), self.allocate('child%d' % number)

    def attribute_list(self, handles):
        self.allowlist = handles
        return self.allocate('attributes')

    def delete_attribute_list(self, handle):
        self.close_handle(handle)

    def create_process_w(self, **kwargs):
        self.kwargs = kwargs
        self.events.append('create')
        return self.allocate('process'), self.allocate('thread'), 123

    def creation_time(self, process):
        return self.created

    def assign_job(self, job, process):
        assert job == 'core-job'
        self.events.append('assign')

    def in_job(self, job, process):
        self.events.append('query')
        return True

    def resume_thread(self, thread):
        self.events.append('resume')
        return 1

    def terminate_process(self, process):
        self.events.append('kill')

    def poll(self, process):
        self.polls += 1
        return self.exit

    def read(self, handle, size):
        assert 0 < size <= 65536, 'Win32Api.read refuses a size outside 1..65536'
        self.sizes.append(size)
        queue = self.reads[int(self.handles[handle][-1])]
        return queue.pop(0) if queue else None

    def write(self, handle, data):
        assert 0 < len(data) <= 65536, 'a full chunk is the largest legal write'
        self.writes.append(data)
        accepted = self.accepted.pop(0) if self.accepted else len(data)
        self.delivered.append(accepted)
        return accepted

    def pause(self, seconds):
        self.now += seconds                       # virtual clock: no real sleeping


def bare(**changes):
    """Fake plus transport on a virtual clock, with nothing staged."""
    api = FakeWin32()
    for name, value in changes.items():
        setattr(api, name, value)
    transport = native.Transport(api, api, clock=lambda: api.now, pause=api.pause,
                                 output_limit=8)
    policy = SimpleNamespace(raw={'process': {'cwd': 'C:\\work', 'timeout': 10}})
    return api, transport, policy


def stage(**changes):
    """Fake plus a transport holding one staged protected policy."""
    api, transport, policy = bare(**changes)
    return api, transport, policy, transport.stage_policy(policy.raw)


def launched(**changes):
    """A suspended, fully leased child: allocation and resume already succeeded."""
    api, transport, policy, path = stage(**changes)
    return api, transport.create_suspended([APP, path], policy=policy)


# -- Transport: stage_policy and creation-time validation --------------------


@pytest.mark.parametrize('limit', [0, -1], ids=['zero', 'negative'])
def test_nonpositive_output_bound_is_refused(limit):
    api = FakeWin32()
    with pytest.raises(ValueError, match='positive output bound required'):
        native.Transport(api, api, output_limit=limit)
    with pytest.raises(ValueError, match='positive output bound required'):
        native.Backend(api, api, lambda raw: True, output_limit=limit)
    assert api.handles == {}


def test_backend_forwards_transport_options():
    api = FakeWin32()
    backend = native.Backend(api, api, lambda raw: True, output_limit=4096)
    assert backend.transport.output_limit == 4096
    assert backend.transport.boundary is api
    assert native.Backend.compile_policy is mxc.compile_policy


@pytest.mark.parametrize('path', ['protected\\policy.json', '\\shared\\policy.json',
                                 'C:policy.json'],
                         ids=['relative', 'no-drive', 'drive-relative'])
def test_stage_policy_refuses_paths_without_a_drive(path):
    api, transport, policy, good = stage()
    api.policy_path = path
    with pytest.raises(mxc.MxcUnavailable, match='absolute protected policy path'):
        transport.stage_policy(policy.raw)
    assert api.released == [path]                  # the rejected lease was removed
    assert list(transport._policies) == [good]      # and never retained
    assert list(api.handles.values()) == ['policy']  # only the good lease stays open


def test_start_refuses_a_missing_job():
    api, transport, policy, path = stage()
    with pytest.raises(mxc.MxcUnavailable, match='Core-held Job required'):
        transport.start(None, [APP, path], policy=policy)
    assert 'create' not in api.events
    assert api.released == []
    assert list(transport._policies) == [path]
    assert list(api.handles.values()) == ['policy']


def test_nul_in_argv_refuses_creation_and_releases_the_lease():
    api, transport, policy, path = stage()
    with pytest.raises(mxc.MxcUnavailable, match='NUL in launcher arguments'):
        transport.create_suspended([APP, '-\x00debug', path], policy=policy)
    assert 'create' not in api.events
    assert api.released == [path]
    assert api.handles == {}


def test_explicit_policy_path_owns_the_lease_not_the_last_argument():
    api, transport, policy, path = stage()
    child = transport.create_suspended([APP, 'data\\file', 'decoy.json'], policy=policy,
                                       policy_path=path)
    assert api.kwargs['command_line'] == 'C:\\launcher.exe data\\file decoy.json'
    assert child._policy_lease[0] == path
    assert transport._policies == {}
    child.terminate()
    assert api.released == [path]
    assert api.handles == {}


@pytest.mark.parametrize('created', [0, -5, '456', True, 1.5],
                         ids=['zero', 'negative', 'text', 'bool', 'float'])
def test_creation_time_must_be_a_positive_int(created):
    api, transport, policy, path = stage(created=created)
    with pytest.raises(mxc.MxcUnavailable, match='invalid launcher creation time'):
        transport.create_suspended([APP, path], policy=policy)
    assert api.events.count('kill') == 1
    assert api.released == [path]
    assert api.handles == {}


def test_policy_lease_is_consumed_by_the_first_creation():
    api, transport, policy, path = stage()
    child = transport.create_suspended([APP, path], policy=policy)
    with pytest.raises(KeyError):
        transport.create_suspended([APP, path], policy=policy)
    assert api.events.count('create') == 1
    child.terminate()
    assert api.released == [path]
    assert api.handles == {}


def test_fault_while_releasing_inherited_handles_still_empties_the_ledger():
    api, transport, policy, path = stage(failing_close={'child2'})
    with pytest.raises(OSError):
        transport.create_suspended([APP, path], policy=policy)
    assert api.events.count('kill') == 1
    assert api.released == [path]
    assert api.handles == {}


# -- Process: liveness, cancellation, cached exit ----------------------------


def test_is_alive_stops_asking_the_kernel_once_closed():
    api, child = launched()
    api.exit = None
    assert child.is_alive() is True
    api.exit = 0
    assert child.is_alive() is False
    child.terminate()
    polls = api.polls
    assert child.is_alive() is False
    assert api.polls == polls
    assert api.handles == {}


def test_wait_after_terminate_refuses_a_dead_child():
    api, child = launched()
    child.terminate()
    polls = api.polls
    with pytest.raises(mxc.MxcUnavailable, match='launcher cancelled'):
        child.wait()
    assert api.polls == polls
    assert api.events.count('kill') == 1
    assert api.released == [POLICY]
    assert api.handles == {}


def test_wait_replays_the_launcher_exit_without_touching_the_kernel():
    api, child = launched()
    child.stdin.write(b'input')
    assert child.wait() == 17
    polls, reads, released = api.polls, len(api.sizes), list(api.released)
    assert child.wait() == 17
    assert api.polls == polls and len(api.sizes) == reads
    assert api.released == released == [POLICY]
    assert child.stdout.read() == b'out'
    assert api.handles == {}


def test_close_after_a_fault_releases_the_lease_exactly_once():
    api, child = launched(exit=None)
    with pytest.raises(TimeoutError, match='launcher I/O deadline'):
        child.wait(timeout=0)
    child.terminate()
    child.close()
    assert api.closes.count('policy') == 1
    assert api.released == [POLICY]
    assert api.handles == {}


def test_closing_an_already_released_handle_is_not_a_second_close():
    api, child = launched()
    handle = child._pipes[1]
    child._close(handle)
    child._close(handle)
    assert api.closes.count('parent1') == 1
    assert handle not in child._handles
    child.terminate()
    assert api.handles == {}


# -- Process: deadlines, bounds, stdin flushing ------------------------------


def test_zero_timeout_never_enters_the_drain():
    api, child = launched(exit=None, reads={1: [], 2: []})
    with pytest.raises(TimeoutError, match='launcher I/O deadline'):
        child.wait(timeout=0)
    assert api.polls == 0
    assert api.now == 0
    assert api.events.count('kill') == 1
    assert api.handles == {}


def test_policy_timeout_bounds_the_drain_when_the_caller_gives_none():
    api, child = launched(exit=None, reads={1: [], 2: []})
    with pytest.raises(TimeoutError, match='launcher I/O deadline'):
        child.wait()
    assert 2 <= api.polls <= 12, 'the 10 ms policy timeout was neither enforced nor skipped'
    assert api.now == pytest.approx(0.01, abs=0.002)
    assert api.events.count('kill') == 1
    assert api.released == [POLICY]
    assert api.handles == {}


def test_output_bound_is_per_stream_and_inclusive():
    api, child = launched(reads={1: [b'12345678', b''], 2: [b'abcdefgh', b'']})
    assert child.wait() == 17
    assert child.stdout.read() == b'12345678'
    assert child.stderr.read() == b'abcdefgh'
    assert set(api.sizes) == {65536}
    assert api.events.count('kill') == 0
    assert api.released == [POLICY]
    assert api.handles == {}


def test_stderr_bound_exceeded_terminates_and_closes():
    api, child = launched(reads={1: [b'out', b''], 2: [b'123456789', b'']})
    with pytest.raises(mxc.MxcUnavailable, match='launcher output bound exceeded'):
        child.wait()
    assert api.events.count('kill') == 1
    assert api.released == [POLICY]
    assert api.handles == {}


def test_stalled_stdin_resumes_from_the_accepted_offset():
    api, child = launched(accepted=[0, 3, 5],
                          reads={1: [b'x', b'x', b'x', b''], 2: [b'y', b'y', b'y', b'']})
    child.stdin.write(b'01234567')
    assert child.wait() == 17
    assert api.writes == [b'01234567', b'01234567', b'34567']
    assert api.delivered == [0, 3, 5]              # the pipe was full once, then took the rest
    assert sum(api.delivered) == len(b'01234567')  # every byte reached it, none twice
    assert child.stdin.closed
    assert child.stdout.read() == b'xxx'
    assert child.stderr.read() == b'yyy'
    assert api.handles == {}


def test_an_already_exited_launcher_is_never_terminated():
    api, child = launched(exit=0, reads={1: [], 2: []})
    with pytest.raises(TimeoutError, match='launcher I/O deadline'):
        child.wait()
    assert child.launcher_exit == 1
    assert api.events.count('kill') == 0
    assert api.released == [POLICY]
    assert api.handles == {}


# -- win32_mxc: pure helpers with ctypes faked -------------------------------


class Function:
    def __init__(self, callback=lambda *args: 1):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


def test_environment_block_sorts_by_uppercased_key_and_double_terminates():
    block = w.environment_block({'b': '1', 'C': '2', 'A': '3'})
    assert block[:13] == 'A=3\0b=1\0C=2\0\0'


def test_environment_block_refuses_names_that_differ_only_in_case():
    # T-665#8: Windows folds names, so two spellings would be one ambiguous variable
    with pytest.raises(ValueError, match='duplicate environment entry'):
        w.environment_block({'PATH': 'a', 'Path': 'b'})


def test_environment_block_of_no_variables_is_only_the_terminators():
    assert w.environment_block({})[:2] == '\0\0'


@pytest.mark.parametrize('entry', [{'': 'value'}, {'a=b': 'value'}, {'a\x00b': 'value'},
                                   {'a': 'value\x00'}],
                         ids=['empty-key', 'equals-in-key', 'nul-in-key', 'nul-in-value'])
def test_environment_block_refuses_unusable_entries(entry):
    with pytest.raises(ValueError, match='invalid environment entry'):
        w.environment_block(entry)


def test_bind_binds_every_declared_signature_and_nothing_else():
    kernel = SimpleNamespace(**{name: Function() for name in w.SIGNATURES})
    bound = w.bind(kernel)
    assert set(bound) == set(w.SIGNATURES)
    for name, (args, result) in w.SIGNATURES.items():
        assert bound[name] is getattr(kernel, name)
        assert bound[name].argtypes == args
        assert bound[name].restype is result


def test_bind_refuses_a_kernel_that_is_missing_an_entry():
    names = list(w.SIGNATURES)
    kernel = SimpleNamespace(**{name: Function() for name in names[:-1]})
    with pytest.raises(AttributeError, match=names[-1]):
        w.bind(kernel)


def test_signatures_are_complete_ctypes_prototypes():
    for name, (args, result) in w.SIGNATURES.items():
        assert isinstance(args, list) and args, name
        assert all(isinstance(arg, type) and hasattr(arg, 'from_param') for arg in args), name
        assert result is None or (isinstance(result, type)
                                 and hasattr(result, 'from_param')), name
    assert c.sizeof(w.HANDLE) == c.sizeof(c.c_void_p)
    assert w.INVALID_HANDLE == c.c_void_p(-1).value
