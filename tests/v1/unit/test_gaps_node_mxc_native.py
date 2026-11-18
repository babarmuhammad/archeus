"""T-782: refusal and fail-closed branches of archeus/node/mxc_native.py left
untested by test_mxc_native.py and test_mxc_native_gaps.py.

Every OS call is faked through the injected Win32 seam (same ledger discipline as
test_mxc_native_gaps.py): no handle, pipe, process or file is opened for real, and
the file runs identically on Linux and on Windows. A test passes only when the
source opens, closes, kills and releases exactly what it owes, once.
"""

from types import SimpleNamespace

import pytest

from archeus.node import mxc, mxc_native as native

POLICY = 'C:\\protected\\policy.json'
APP = 'C:\\launcher.exe'


class Boom(BaseException):
    """A fault that is NOT an Exception: only an `except BaseException` is safe."""


class FakeWin32:
    """Handle ledger for the transport seam: a handle left open is a leak,
    a second close or a read on a closed handle is a KeyError."""

    def __init__(self):
        self.handles = {}
        self.events = []
        self.closes = []
        self.released = []
        self.reads = {1: [b'out', b''], 2: [b'err', b'']}
        self.sizes = []
        self.read_log = []
        self.writes = []
        self.accepted = []
        self.delivered = []
        self.now = 0
        self.exit = 17
        self.polls = 0
        self.created = 456
        self.member = True
        self.policy_path = POLICY
        self.payload = None

    def allocate(self, name):
        self.events.append(name)
        handle = len(self.events) + 100
        self.handles[handle] = name
        return handle

    def close_handle(self, handle):
        name = self.handles.pop(handle)          # KeyError proves a double close
        self.closes.append(name)

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
        return self.member

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
        self.read_log.append(self.handles[handle])  # KeyError if the pipe was closed
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


# -- refusals before anything is created --------------------------------------


@pytest.mark.parametrize('extra, fault', [({'nan': float('nan')}, ValueError),
                                          ({'inf': float('inf')}, ValueError),
                                          ({'obj': object()}, TypeError)],
                         ids=['nan', 'inf', 'object'])
def test_stage_policy_refuses_a_body_json_cannot_write(extra, fault):
    """mxc_native.py:50 - json.dumps(..., allow_nan=False) runs BEFORE the
    protected file is created: a policy with a non-finite float or an
    unserializable value is refused while the protected store is untouched."""
    api, transport, policy = bare()
    raw = {'process': {'cwd': 'C:\\work', 'timeout': 10}}
    raw.update(extra)
    with pytest.raises(fault):
        transport.stage_policy(raw)
    assert api.events == []                       # protected_policy was never reached
    assert api.payload is None
    assert api.handles == {}


def test_unstaged_policy_path_is_refused_before_any_allocation():
    """mxc_native.py:84 - `self._policies.pop(path)` is the ownership gate: a
    policy_path nobody staged cannot be launched with, fails with KeyError,
    creates no process, and must not release or leak the lease held for another
    path."""
    api, transport, policy, path = stage()
    with pytest.raises(KeyError):
        transport.create_suspended([APP, path], policy=policy,
                                   policy_path='C:\\evil\\policy.json')
    assert 'create' not in api.events
    assert api.released == []                     # the real lease is untouched
    assert list(transport._policies) == [path]
    assert list(api.handles.values()) == ['policy']


def test_nul_in_the_application_path_refuses_before_any_allocation():
    """mxc_native.py:90-91 - the NUL scan covers argv[0] itself, not just the
    trailing arguments: a poisoned launcher path never reaches CreateProcessW
    and the staged lease is released."""
    api, transport, policy, path = stage()
    with pytest.raises(mxc.MxcUnavailable, match='NUL in launcher arguments'):
        transport.create_suspended(['C:\\laun\x00sher.exe', path], policy=policy)
    assert 'create' not in api.events
    assert api.released == [path]
    assert api.handles == {}


def test_created_child_inherits_no_environment_and_gets_the_policy_cwd():
    """mxc_native.py:103 - env must be an empty dict (None would inherit the
    node's whole environment into the container) and cwd comes from the policy,
    with the extended-startup and unicode-environment flags set."""
    api, child = launched()
    assert api.kwargs['env'] == {}
    assert type(api.kwargs['env']) is dict        # an explicit block, not inherit
    assert api.kwargs['cwd'] == 'C:\\work'
    assert api.kwargs['inherit_handles'] is True
    for flag in (native.CREATE_SUSPENDED, native.EXTENDED_STARTUPINFO_PRESENT,
                 native.CREATE_UNICODE_ENVIRONMENT):
        assert api.kwargs['flags'] & flag
    child.terminate()
    assert api.handles == {}


# -- the suspended-launch ordering, from the refusal side ----------------------


@pytest.mark.parametrize('member', [1, 1.0, 'verified', object()],
                         ids=['one', 'float', 'text', 'object'])
def test_start_refuses_membership_that_is_truthy_but_not_true(member):
    """mxc_native.py:72 - `is not True`: only the kernel's own True proves Job
    membership; a truthy stand-in must terminate the suspended child, resume it
    never, and close every handle."""
    api, transport, policy, path = stage(member=member)
    with pytest.raises(mxc.MxcUnavailable, match='membership unverified'):
        transport.start('core-job', [APP, path], policy=policy)
    assert api.events.count('kill') == 1
    assert 'resume' not in api.events
    assert api.released == [path]
    assert api.handles == {}


@pytest.mark.parametrize('mode', ['assign', 'membership'], ids=['assign-fault', 'not-member'])
def test_ownership_hook_never_runs_before_membership_is_proven(mode):
    """mxc_native.py:74-75 - the ledger hook is only reachable after the
    membership check passed: a launch that fails assignment or verification must
    never let the durable-ownership write happen against an unassigned child."""
    api, transport, policy, path = stage(member=(mode != 'membership'))
    if mode == 'assign':
        def refuse(job, process):
            raise OSError('injected assignment failure')
        api.assign_job = refuse
    seen = []

    def before_resume(child):
        seen.append(child)

    with pytest.raises((OSError, mxc.MxcUnavailable)):
        transport.start('core-job', [APP, path], policy=policy,
                        before_resume=before_resume)
    assert seen == []                             # the hook never ran
    assert 'resume' not in api.events
    assert api.events.count('kill') == 1
    assert api.handles == {}


# -- Process: termination, completion and drain safety --------------------------


def test_terminate_after_a_bare_close_never_touches_the_kernel_again():
    """mxc_native.py:180 - once every handle is closed the child cannot be
    terminated or polled: terminate_process would fire on a stale handle and a
    second close would double-release the policy lease; both are refused."""
    api, child = launched()
    child.close()                                 # handles gone, lease released once
    assert child.launcher_exit is None
    child.terminate()                             # nothing left to kill or close
    assert api.events.count('kill') == 0
    assert api.released == [POLICY]
    assert api.closes.count('policy') == 1
    assert child.is_alive() is False
    assert api.polls == 0                         # is_alive asked the kernel zero times
    assert api.handles == {}


def test_zero_exit_code_is_completion_not_pending():
    """mxc_native.py:224 - poll() means pending with None only; a launcher that
    exits 0 with drained outputs returns 0 well before the deadline, and the
    already-exited child is never terminated."""
    api, child = launched(exit=0)
    assert child.wait() == 0
    assert child.launcher_exit == 0
    assert api.now < 0.01                         # the 10 ms deadline was never reached
    assert api.events.count('kill') == 0
    assert api.released == [POLICY]
    assert api.handles == {}


def test_a_non_exception_fault_in_the_drain_still_kills_and_closes():
    """mxc_native.py:230 - the drain guard is `except BaseException`, not
    `except Exception`: a fault outside the Exception tree still terminates the
    live launcher, releases the lease and empties the handle ledger."""
    api, child = launched()

    def boom(handle, size):
        raise Boom('injected non-Exception fault')

    api.read = boom
    child.stdin.write(b'input')
    with pytest.raises(Boom):
        child.wait()
    assert api.events.count('kill') == 1
    assert api.released == [POLICY]
    assert child.stdin.closed
    assert api.handles == {}


# -- boundaries on the hostile pipe streams -------------------------------------

def test_output_bound_accumulates_across_reads_not_just_per_read():
    """mxc_native.py:214 - the bound compares stream.tell() + len(data), so a
    stream smuggled past the limit in legal-sized chunks still trips: 4+4 fills
    the 8-byte bound and a further 1-byte read must abort the drain."""
    api, child = launched(exit=None, reads={1: [b'1234', b'1234', b'9', b''], 2: [b'']})
    with pytest.raises(mxc.MxcUnavailable, match='launcher output bound exceeded'):
        child.wait()
    assert api.events.count('kill') == 1
    assert api.released == [POLICY]
    assert api.handles == {}


def test_no_kernel_read_happens_after_a_stream_reported_eof():
    """mxc_native.py:206 - once a stream reported EOF its pipe is closed and is
    never read again: the ledger raises KeyError on any read of a closed handle,
    so a queue still holding b'HACKED' can only stay unread if the guard holds."""
    api, child = launched(reads={1: [b'', b'HACKED'], 2: [b'out', b'']})
    assert child.wait() == 17
    assert child.stdout.read() == b''             # nothing was smuggled in post-EOF
    assert child.stderr.read() == b'out'
    assert api.read_log == ['parent1', 'parent2', 'parent2']
    assert api.handles == {}


def test_stdin_is_flushed_in_chunks_of_at_most_65536_bytes():
    """mxc_native.py:219 - a pending write larger than one pipe chunk goes out
    as [65536, remainder]: every byte once, none beyond the legal write size."""
    api, child = launched()
    payload = b'x' * 65536 + b'y' * 4464
    child.stdin.write(payload)
    assert child.wait() == 17
    assert b''.join(api.writes) == payload
    assert [len(chunk) for chunk in api.writes] == [65536, 4464]
    assert sum(api.delivered) == len(payload)
    assert api.handles == {}
