"""T-1008: highest-risk branch gaps of archeus/node/mxc_native.py lines 1-320.

Selected branches (file: archeus/node/mxc_native.py):
 1. :12-14,109  exact numeric Win32 creation flags (suspended + extended
    startupinfo + unicode env) - refusal of an unsuspended/unallowlisted launch.
 2. :245-246,250-251  Process.terminate() when TerminateProcess itself faults:
    cleanup must still close every handle, release the lease once and reraise.
 3. :272-275  drain precedence: a real cancel outranks an already-due deadline.
 4. :137-138 vs :141-142,148,243  Job assignment goes to the boundary, never to
    the kernel seam; membership/resume/terminate get their exact handles.
 5. :147-149  Transport.resume marks the child resumed before ResumeThread: a
    kernel fault mid-resume must still refuse any second resume.
 6. :40,264-265  a second drain is refused with the specific AlreadyDraining type.
 7. :274  the I/O deadline fires on the exact tick (``>=``, not ``>``).
 8. :260-263  a cached exit code of 0 replays as 0, never as 'launcher closed'.
 9. :213-214  Process.close keeps the FIRST close fault across several failures.
10. :130-135  (justified xfail) a close fault in the create_suspended finally
    loop must not skip the remaining closes, attribute-list delete or lease.

Every OS call is faked through the injected Win32 seam (same ledger discipline
as test_mxc_native_gaps.py): no real DLL, handle, pipe, process or file exists,
every test is single-threaded and runs identically on Linux and Windows. A test
passes only when the source opens, closes, kills and releases exactly what it
owes, once.
"""

from types import SimpleNamespace

import pytest

from archeus.node import mxc, mxc_native as native

POLICY = 'C:\\protected\\policy.json'
APP = 'C:\\launcher.exe'


class FakeApi:
    """Kernel seam ledger: a handle left open is a leak, a second close of a
    live number or an ask that should have gone to the boundary is a fault."""

    def __init__(self):
        self.handles = {}
        self.events = []
        self.closes = []
        self.released = []
        self.reads = {1: [], 2: []}
        self.sizes = []
        self.writes = []
        self.delivered = []
        self.now = 0
        self.exit = 17
        self.polls = 0
        self.poll_targets = []
        self.resume_calls = []
        self.resume_faults = []
        self.terminate_targets = []
        self.terminate_fail = False
        self.query_targets = []
        self.member = True
        self.created = 456
        self.creation_time_fail = False
        self.failing_close = set()
        self.policy_path = POLICY
        self.kwargs = None

    # -- allocation ledger -------------------------------------------------
    def allocate(self, name):
        self.events.append(name)
        handle = len(self.events) + 100
        self.handles[handle] = name
        return handle

    def close_handle(self, handle):
        name = self.handles.pop(handle)          # KeyError proves a double close
        if name in self.failing_close:
            self.handles[handle] = name          # the kernel refused: it stays open
            raise OSError('close ' + name)
        self.closes.append(name)

    # -- the injected Win32 protocol ----------------------------------------
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
        if self.creation_time_fail:
            raise OSError('GetProcessTimes refused')
        return self.created

    def assign_job(self, job, process):                  # must never be reached:
        raise AssertionError('jobs belong to the boundary')   # jobs go to boundary

    def in_job(self, job, process):
        self.events.append('query')
        self.query_targets.append(self.handles.get(process, 'CLOSED'))
        return self.member

    def resume_thread(self, thread):
        self.resume_calls.append(self.handles.get(thread, 'CLOSED'))
        if self.resume_faults:
            raise self.resume_faults.pop(0)
        return 1

    def terminate_process(self, process):
        self.terminate_targets.append(self.handles.get(process, 'CLOSED'))
        if self.terminate_fail:
            raise OSError('TerminateProcess refused')
        self.events.append('kill')

    def poll(self, process):
        self.polls += 1
        self.poll_targets.append(self.handles.get(process, 'CLOSED'))
        return self.exit

    def read(self, handle, size):
        assert 0 < size <= 65536, 'Win32Api.read refuses a size outside 1..65536'
        self.sizes.append(size)
        queue = self.reads[int(self.handles[handle][-1])]
        return queue.pop(0) if queue else None

    def write(self, handle, data):
        assert 0 < len(data) <= 65536, 'a full chunk is the largest legal write'
        self.writes.append(data)
        self.delivered.append(len(data))
        return len(data)

    def pause(self, seconds):
        self.now += seconds                       # virtual clock: no real sleeping


class Boundary:
    """Core's job boundary: the only party allowed to assign a process to a Job."""

    def __init__(self, api):
        self.api = api
        self.calls = []

    def assign_job(self, job, process):
        self.calls.append((job, self.api.handles.get(process, 'CLOSED')))


def bare(**changes):
    api = FakeApi()
    for name, value in changes.items():
        setattr(api, name, value)
    boundary = Boundary(api)
    transport = native.Transport(api, boundary, clock=lambda: api.now,
                                 pause=api.pause, output_limit=8)
    policy = SimpleNamespace(raw={'process': {'cwd': 'C:\\work', 'timeout': 10}})
    return api, boundary, transport, policy


def stage(**changes):
    api, boundary, transport, policy = bare(**changes)
    return api, boundary, transport, policy, transport.stage_policy(policy.raw)


def launched(**changes):
    api, boundary, transport, policy, path = stage(**changes)
    return api, boundary, transport, transport.create_suspended([APP, path],
                                                                policy=policy)


# -- 1. the creation flags are the exact Windows ABI values ---------------------

def test_create_flags_are_the_exact_windows_suspend_and_startupinfo_values():
    """Branch: create_process_w flags (:12-14,109).  Closest existing test,
    test_created_child_inherits_no_environment_and_gets_the_policy_cwd, ANDs the
    live module constants, so mutating a constant (e.g. CREATE_SUSPENDED to 0x0)
    still passes: the launcher would be created running, before any ledger or
    ownership fact exists.  The numbers, not the names, are the contract."""
    api, _, transport, policy, path = stage()
    child = transport.create_suspended([APP, path], policy=policy)
    assert (native.CREATE_SUSPENDED, native.EXTENDED_STARTUPINFO_PRESENT,
            native.CREATE_UNICODE_ENVIRONMENT) == (0x4, 0x80000, 0x400)
    assert api.kwargs['flags'] == 0x4 | 0x80000 | 0x400
    assert type(api.kwargs['flags']) is int
    child.terminate()
    assert api.handles == {}


# -- 2. terminate(): the kernel refusing the kill is not permission to leak -----

def test_a_terminate_the_kernel_refuses_still_closes_every_handle_and_reraises():
    """Branches: except BaseException in terminate (:245-246) and the re-raise
    (:250-251).  No existing test ever makes terminate_process raise: line and
    branch traces of all four existing mxc_native test files show 245, 246 and
    251 are never executed and (250, True) is never observed."""
    api, _, _, child = launched(terminate_fail=True)
    with pytest.raises(OSError, match='TerminateProcess refused'):
        child.terminate()
    assert api.terminate_targets == ['process']       # one attempt on the right handle
    assert child.launcher_exit is None                # a refused kill is not exit 1
    assert api.released == [POLICY]                   # the lease went despite the fault
    assert api.handles == {}                          # every closeable handle closed
    with pytest.raises(mxc.MxcUnavailable, match='launcher cancelled'):
        child.wait()
    child.terminate()                                 # a second ask is refused
    assert api.terminate_targets == ['process']


# -- 3. a real cancel outranks an already-due deadline ---------------------------

def test_a_cancel_wins_over_the_deadline_when_both_are_already_due():
    """Branch: precedence of the cancel check (:272-273) over the deadline check
    (:274-275).  Closest existing test, test_deadline_and_cancel_during_drain,
    accepts either error type and never makes both due at the same iteration,
    so swapping the two checks still passes."""
    api, _, transport, policy, path = stage()
    child = transport.create_suspended([APP, path], policy=policy)
    child.transport.clock = lambda: 999.0             # deadline already past
    with pytest.raises(mxc.MxcUnavailable, match='cancelled during drain'):
        child.wait(timeout=0, cancelled=lambda: True)
    assert api.handles == {} and api.events.count('kill') == 1

    other, _, transport2, policy2, path2 = stage()
    child2 = transport2.create_suspended([APP, path2], policy=policy2)
    child2.transport.clock = lambda: 999.0            # same, but nobody cancelled
    with pytest.raises(TimeoutError, match='launcher I/O deadline'):
        child2.wait(timeout=0)
    assert other.handles == {} and other.events.count('kill') == 1


# -- 4. the Job belongs to the boundary; handles go where they belong ------------

def test_job_assignment_asks_the_boundary_and_every_kernel_ask_names_its_handle():
    """Branches: assign_job via self.boundary (:137-138) vs in_job/resume/
    terminate via the api (:141-142,148,243).  Every existing fake makes the
    boundary and the api the same object and ignores the handle arguments, so
    routing assignment through the kernel seam, or resuming the process handle
    instead of the thread handle, passes the whole current suite."""
    api, boundary, transport, policy, path = stage()
    child = transport.start('core-job', [APP, path], policy=policy)
    assert boundary.calls == [('core-job', 'process')]    # the boundary was asked, once
    assert api.query_targets == ['process']               # membership asked the kernel
    assert api.resume_calls == ['thread']                 # and the resume named the thread
    child.terminate()
    assert api.terminate_targets == ['process']
    assert api.handles == {}


def test_a_boundary_assignment_fault_kills_the_suspended_child_before_the_resume():
    """Branch: Transport.start except BaseException -> child.terminate (:86-89)
    driven through the boundary seam.  Closest existing test,
    test_start_fault_terminates_and_closes, injects the fault on the api object
    that also plays the boundary, so a source that assigned via the api instead
    would never see the fault and would resume an unassigned launcher."""
    api, boundary, transport, policy, path = stage()

    def refuse(job, process):
        raise OSError('injected boundary assignment failure')

    boundary.assign_job = refuse
    with pytest.raises(OSError, match='boundary assignment failure'):
        transport.start('core-job', [APP, path], policy=policy)
    assert api.terminate_targets == ['process']           # kill went to the process handle
    assert api.resume_calls == []                         # the launcher never ran
    assert api.handles == {}
    assert api.released == [POLICY]


# -- 5. a resume the kernel faulted on stays refused ------------------------------

def test_a_resume_the_kernel_faults_on_stays_marked_resumed_and_refuses_a_retry():
    """Branch: child.resumed is set BEFORE resume_thread (:147-149), so a
    kernel fault mid-resume cannot be retried.  Closest existing test,
    test_wrong_suspend_count_cannot_retry, only exercises a returning kernel;
    moving the flag after a successful call passes every current test, and a
    retry could then resume a launcher the ledger never cleared."""
    api, _, transport, child = launched()
    api.resume_faults = [OSError('ResumeThread refused')]
    with pytest.raises(OSError, match='ResumeThread refused'):
        transport.resume(child)
    assert child.resumed is True                    # the uncertainty is sticky
    assert api.resume_calls == ['thread']           # the kernel was asked exactly once
    with pytest.raises(mxc.MxcUnavailable, match='already resumed'):
        transport.resume(child)
    assert api.resume_calls == ['thread']           # the retry never reached the kernel
    child.terminate()
    assert api.handles == {}


# -- 6. the second drain is refused with the specific type ------------------------

def test_a_second_drain_is_refused_with_the_already_draining_type():
    """Branch: raise AlreadyDraining (:264-265, class at :40).  Closest unit
    test, test_a_wait_from_inside_the_drain_is_refused_not_nested, matches the
    message on mxc.MxcUnavailable only, so downgrading the raise to the base
    class still passes the whole unit suite (only an integration test checks
    the type).  The nested wait must also be side-effect free."""
    api, _, _, child = launched(exit=None, reads={1: [b'a', b''], 2: [b'']})
    seen = []

    def sink(name, data):
        polls, closes = api.polls, len(api.closes)
        try:
            child.wait()
        except BaseException as err:                      # recorded, not swallowed
            seen.append(err)
        seen.append(api.polls == polls and len(api.closes) == closes)

    child.attach(sink=sink)
    with pytest.raises(TimeoutError):
        child.wait(timeout=0.003)
    assert type(seen[0]) is native.AlreadyDraining      # the exact refusal, not the base
    assert 'already draining' in str(seen[0])
    assert seen[1:] == [True]                           # the refused wait touched no handle
    assert api.events.count('kill') == 1
    assert api.handles == {}


# -- 7. the deadline fires on the exact tick --------------------------------------

def test_the_io_deadline_fires_on_the_exact_tick_not_one_pause_later():
    """Branch: clock() >= deadline (:274).  test_zero_timeout_never_enters_the
    _drain pins the immediate case and the policy-timeout test allows 2..12
    polls, so flipping >= to > (one extra loop on a hostile launcher) passes
    both.  With a virtual clock that lands exactly on the deadline the drain
    must run its two permitted turns and stop."""
    api, _, _, child = launched(exit=None, reads={1: [], 2: []})
    with pytest.raises(TimeoutError, match='launcher I/O deadline'):
        child.wait(timeout=0.002)                   # 0.001 per virtual pause
    assert api.polls == 2                           # a third turn means > instead of >=
    assert api.now == pytest.approx(0.002, abs=1e-12)
    assert api.events.count('kill') == 1
    assert api.handles == {}


# -- 8. a cached zero exit replays as zero, never as 'launcher closed' ------------

def test_a_zero_exit_replays_as_zero_and_never_as_a_closed_launcher():
    """Branch: if self.launcher_exit is None (:261).  The zero-exit completion
    test only calls wait once and the replay test uses exit 17, so turning the
    None test into a falsiness test (returning 'launcher closed' for a clean
    exit 0 forever) passes the entire current suite."""
    api, _, _, child = launched(exit=0, reads={1: [b''], 2: [b'']})
    assert child.wait() == 0
    polls, released = api.polls, list(api.released)
    assert child.wait() == 0                        # replay, not refusal
    assert child.poll() == 0
    assert api.polls == polls and api.released == released == [POLICY]
    assert api.events.count('kill') == 0
    assert api.handles == {}


# -- 9. several failed closes still report the first fault -------------------------

def test_the_first_close_fault_is_the_one_reraised_after_the_lease_is_gone():
    """Branch: failed = failed or err (:213-214) with two failing handles.
    Closest existing test, test_one_handle_that_will_not_close_does_not_keep_
    the_others_open, fails exactly one handle, so replacing the or-chain with
    'failed = err' (reporting the LAST fault) passes today.  The lease must go
    either way and no close may be retried."""
    api, _, _, child = launched(failing_close={'thread', 'parent1'})
    with pytest.raises(OSError, match='close thread'):      # the FIRST fault wins
        child.close()
    assert sorted(api.handles.values()) == ['parent1', 'thread']
    assert api.released == [POLICY]                         # the lease went despite them
    assert child._policy_lease is None
    assert api.closes == ['child0', 'child1', 'child2', 'attributes',
                          'process', 'parent0', 'parent2', 'policy']
    child.close()                                           # failed handles are not retried
    assert api.closes == ['child0', 'child1', 'child2', 'attributes',
                          'process', 'parent0', 'parent2', 'policy']


# -- 10. (justified xfail) a close fault must not abort creation cleanup -----------

@pytest.mark.xfail(strict=True, reason=(
    'mxc_native.py:130-135: an close_handle fault raised inside the '
    'create_suspended finally loop skips the remaining close_handle calls, '
    'delete_attribute_list and remove_policy, stranding the policy lease and '
    'the other handles; that contradicts the Win32 protocol contract at '
    'mxc_native.py:19 (failed calls release partial allocations), the '
    'fail-closed premise the sibling try-loop cleanup already satisfies in '
    'test_fault_while_releasing_inherited_handles_still_empties_the_ledger'))
def test_a_close_fault_during_creation_cleanup_still_releases_every_handle():
    """Branch: finally loop of create_suspended (:130-135) with a raising
    close_handle.  Closest existing tests, test_allocation_fault_closes_every_
    handle and test_fault_while_releasing_inherited_handles_still_empties_the_
    ledger, only inject faults while close_handle still succeeds (the gaps fake
    fails once and then works), so the loop's own fault path never runs.  The
    refused handle itself may stay open; what must not happen is the loop
    abandoning every cleanup call that comes after it."""
    api, _, transport, policy, path = stage(creation_time_fail=True,
                                            failing_close={'parent2'})
    with pytest.raises(OSError):
        transport.create_suspended([APP, path], policy=policy)
    assert 'kill' in api.events                     # the suspended child was killed
    assert set(api.handles.values()) == {'parent2'}  # only the refused close stays open
    assert api.released == [path]                   # the lease must not be stranded
