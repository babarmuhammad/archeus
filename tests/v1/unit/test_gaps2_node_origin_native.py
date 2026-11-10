"""T-1000: the ten highest-risk uncovered branches of `archeus/node/origin_native.py`
lines 1-215 — the `Win32OriginApi` DLL wrappers (TCP table, process probe, snapshot
walk, session) and the creation-time boundary of `_ancestry` — over the seam fakes of
`test_origin_native.py`. Nothing here loads a DLL, opens a socket or touches a real
process: the api is built with the `object.__new__` seam (`_win32`) and every kernel32
and iphlpapi answer is a scripted Python fake, reviewed to run identically on Windows.

Selected branches (source line -> test), fail-closed and denial first, then the
boundary, then the error paths:

1. L182  `alive = WaitForSingleObject(...) == WAIT_TIMEOUT`: a signalled (dead) handle
   must read dead even when OpenProcess succeeded and IsProcessInJob says TRUE (F9C).
2. L178-180 `if not handle: return None`: an un-openable PID is "no process", with no
   further handle use and no CloseHandle of a handle that was never owned.
3. L202-204 `if snapshot in (None, c_void_p(-1).value): raise`: a failed snapshot is a
   reader error, never the silent `(0, '')` "no parent" answer.
4. L206-213 the snapshot walk matches only the requested pid (recycled ancestry):
   skips non-matching entries via Process32NextW, absent pid answers `(0, '')`, and
   the snapshot handle is closed in the finally.
5. L171-175 `ProcessIdToSessionId` failure raises OSError: an unreadable session is a
   reader error, never the default DWORD 0 (which could match Core's own session).
6. L153-159 `GetExtendedTcpTable` failures: sizing call != ERROR_INSUFFICIENT_BUFFER
   and fill call != 0 both raise — never an empty table read as "no peers".
7. L151-164, L119-124 row decode: count from the buffer head, rows at offset 4,
   `_address` little-endian octets and `_port` the byte swap; a mis-decoded near-miss
   row must not own the peer port.
8. L183-186 `GetProcessTimes` failure leaves creation_time None (unreadable, not 0);
   success reads low | high << 32 of the CreationTime slot.
9. L83-84 `_ancestry` boundary: a parent created in the same creation tick as its
   child (creation_time >=, equality included) ends the chain — only strictly older
   parents count, so a recycled parent cannot lend its name.
10. L198-199 the process handle is closed in the finally even when the Job probe
   raises mid-way, after open/wait/times and before the snapshot walk.
"""

import ctypes as c
import struct

import pytest

from archeus.node import attest, origin_native
from archeus.node.origin_native import (AF_INET, ERROR_INSUFFICIENT_BUFFER, ESTABLISHED,
                                         PROCESS_QUERY_LIMITED_INFORMATION,
                                         TCP_TABLE_OWNER_PID_ALL, TcpRow, native_readers)

from .test_origin_native import CORE, CORE_PID, JOB, PEER, SESSION, T0, FakeApi, _proc, _win32

SYNCHRONIZE_READ = PROCESS_QUERY_LIMITED_INFORMATION | origin_native.SYNCHRONIZE
PEER_ROWS = [TcpRow('127.0.0.1', PEER, '127.0.0.1', CORE, ESTABLISHED, 4124)]


def _readers(api, **kw):
    return native_readers(api, core_port=CORE, jobs=lambda: [JOB], clock=lambda: T0, **kw)


class ScriptKernel:
    """Every kernel32 call one `Win32OriginApi.process` makes, answered from a script
    and recorded in call order; `closed` makes a leaked handle visible. Plain Python
    answers only — the seam is the `_win32` `object.__new__` one, as in the existing
    `Kernel` fake, whose answers here are deliberately *not* reused because that fake
    records nothing and always answers 'alive'."""

    def __init__(self, *, handle=77, wait=origin_native.WAIT_TIMEOUT, times_ok=True,
                 low=1, high=2, in_job=0, injob_ok=True, session=SESSION, session_ok=True,
                 snapshot=5, entries=()):
        self.handle, self.wait = handle, wait
        self.times_ok, self.low, self.high = times_ok, low, high
        self.in_job, self.injob_ok = in_job, injob_ok
        self.session, self.session_ok = session, session_ok
        self.snapshot, self.pending = snapshot, list(entries)
        self.calls, self.closed = [], []

    def OpenProcess(self, access, inherit, pid):
        self.calls.append(('open', access, inherit, pid))
        return self.handle

    def CloseHandle(self, handle):
        self.closed.append(handle)

    def WaitForSingleObject(self, handle, ms):
        self.calls.append(('wait', handle, ms))
        return self.wait

    def GetProcessTimes(self, handle, *times):
        self.calls.append(('times', handle))
        if self.times_ok:
            times[0]._obj.low, times[0]._obj.high = self.low, self.high
        return 1 if self.times_ok else 0

    def IsProcessInJob(self, handle, job, inside):
        self.calls.append(('injob', handle, job))
        if not self.injob_ok:
            return 0
        inside._obj.value = self.in_job
        return 1

    def CreateToolhelp32Snapshot(self, flags, pid):
        self.calls.append(('snapshot', flags, pid))
        return self.snapshot

    def Process32FirstW(self, snapshot, entry):
        return self._step('first', snapshot, entry)

    def Process32NextW(self, snapshot, entry):
        return self._step('next', snapshot, entry)

    def _step(self, name, snapshot, entry):
        self.calls.append((name, snapshot))
        if not self.pending:
            return 0
        pid, parent, exe = self.pending.pop(0)
        entry._obj.pid, entry._obj.parent, entry._obj.exe = pid, parent, exe
        return 1

    def ProcessIdToSessionId(self, pid, session):
        self.calls.append(('session', pid))
        if not self.session_ok:
            return 0
        session._obj.value = self.session
        return 1

    def GetCurrentProcessId(self):
        return CORE_PID


class FakeIphlp:
    """Both `GetExtendedTcpTable` calls — the sizing probe (buf None) and the fill —
    with scriptable return codes, and a log of the flags each call used."""

    def __init__(self, size_rc=ERROR_INSUFFICIENT_BUFFER, fill_rc=0, payload=b''):
        self.size_rc, self.fill_rc, self.payload = size_rc, fill_rc, payload
        self.calls = []

    def GetExtendedTcpTable(self, buf, size, reverse, af, table, reserved):
        self.calls.append((buf is None, reverse, af, table, reserved))
        if buf is None:
            size._obj.value = 8
            return self.size_rc
        buf[:len(self.payload)] = self.payload
        return self.fill_rc


class KernelApi:
    """A fake attestor api over a scripted kernel, built with the `_win32` seam and
    never constructed for real. `rows` answers `tcp_rows`; `None` delegates to the
    kernel-paired iphlp fake."""

    def __init__(self, kernel, rows=()):
        self.kernel = kernel
        self.api = _win32(kernel)
        self.api.iphlp = FakeIphlp()
        self.rows = list(rows) if rows else None

    def tcp_rows(self):
        return list(self.rows) if self.rows is not None else self.api.tcp_rows()

    def process(self, pid, jobs):
        return self.api.process(pid, jobs)

    def core_pid(self):
        return CORE_PID

    def core_session(self):
        return self.api.core_session()


def _raw_addr(ip):
    """The DWORD a loopback/other IPv4 looks like to `_address`'s inverse: octets in
    little-endian order. Written independently of the source so a flipped byte order
    inside `_address` cannot be self-fulfilling."""
    return int.from_bytes(bytes(int(o) for o in ip.split('.')), 'little')


def _raw_port(port):
    """The DWORD `_port`'s byte swap reads as *port*, built from the host-order bytes
    of the port, not from the source expression."""
    return int.from_bytes(struct.pack('>H', port), 'little')


def _raw_row(state, local_addr, local_port, remote_addr, remote_port, pid):
    return struct.pack('<6I', state, _raw_addr(local_addr), _raw_port(local_port),
                       _raw_addr(remote_addr), _raw_port(remote_port), pid)


# ── 1. liveness is the wait answer, never OpenProcess or the Job (F9C) ──

@pytest.mark.parametrize('wait, alive',
                         [(origin_native.WAIT_TIMEOUT, True), (0, False)],
                         ids=['timeout-alive', 'signalled-dead'])
def test_only_a_wait_timeout_reads_alive_a_signalled_handle_is_dead(wait, alive):
    kernel = ScriptKernel(wait=wait, in_job=1, entries=[(4124, 0, 'curl.exe')])
    proc = _win32(kernel).process(4124, (JOB,))
    assert proc.alive is alive
    assert proc.in_jobs is True                      # the Job answer is never liveness
    assert ('wait', kernel.handle, 0) in kernel.calls
    assert kernel.closed == [kernel.snapshot, kernel.handle]


# ── 2. an un-openable PID is no process, and no handle is ever used or "closed" ──

def test_a_pid_the_kernel_will_not_open_is_no_process_and_denied_dead():
    kernel = ScriptKernel(handle=0)
    assert _win32(kernel).process(4124, (JOB,)) is None
    assert kernel.calls == [('open', SYNCHRONIZE_READ, False, 4124)]
    assert kernel.closed == []                       # nothing was owned, nothing closed
    r = _readers(KernelApi(kernel, rows=PEER_ROWS))
    assert r.read_process(4124).alive is False
    result = attest.attest_peer(**r.attest_kwargs(PEER))
    assert not result.ok and result.binding is None and attest.DEAD in result.failures


# ── 3. a failed snapshot is a reader error, never a silent "no parent" ──

@pytest.mark.parametrize('sentinel', [None, c.c_void_p(-1).value],
                         ids=['none', 'invalid-handle-value'])
def test_a_failed_snapshot_raises_instead_of_answering_no_parent(sentinel):
    kernel = ScriptKernel(snapshot=sentinel, entries=[(4124, 300, 'curl.exe')])
    with pytest.raises(OSError, match='CreateToolhelp32Snapshot'):
        _win32(kernel).process(4124, (JOB,))
    assert not any(n in ('first', 'next') for n, *_ in kernel.calls)
    assert kernel.closed == [kernel.handle]           # only the process handle: the failed
    # snapshot is not a handle and is never "closed"


# ── 4. the snapshot walk matches only the requested pid (recycled ancestry) ──

def test_the_snapshot_walk_skips_entries_until_the_pid_matches_and_closes_the_snapshot():
    hit = ScriptKernel(entries=[(7, 1, 'other.exe'), (4124, 300, 'CU.EXE')])
    proc = _win32(hit).process(4124, (JOB,))
    assert (proc.parent_pid, proc.name) == (300, 'CU.EXE')   # the *matching* entry only
    assert [n for n, *_ in hit.calls] == ['open', 'wait', 'times', 'injob', 'snapshot',
                                          'first', 'next', 'session']
    assert hit.closed == [hit.snapshot, hit.handle]
    miss_kernel = ScriptKernel(entries=[(7, 1, 'other.exe'), (8, 2, 'second.exe')])
    miss = _win32(miss_kernel).process(4124, (JOB,))
    assert (miss.parent_pid, miss.name) == (0, '')             # absent pid: no ancestry
    assert miss_kernel.closed == [miss_kernel.snapshot, miss_kernel.handle]


# ── 5. an unreadable session is a reader error, never the default DWORD 0 ──

def test_a_session_that_cannot_be_read_is_a_reader_error_never_session_zero():
    kernel = ScriptKernel(session_ok=False, entries=[(4124, 0, 'curl.exe')])
    wrapper = KernelApi(kernel, rows=PEER_ROWS)
    with pytest.raises(OSError, match='ProcessIdToSessionId'):
        wrapper.process(4124, (JOB,))
    assert kernel.closed == [kernel.snapshot, kernel.handle]   # the finally still runs
    with pytest.raises(OSError, match='ProcessIdToSessionId'):
        wrapper.core_session()
    result = attest.attest_peer(**_readers(wrapper).attest_kwargs(PEER))
    assert not result.ok and result.binding is None
    assert result.failures == (attest.READER_ERROR,)


# ── 6. a TCP table that cannot be read is a reader error, never an empty table ──

@pytest.mark.parametrize('size_rc, fill_rc, reason',
                         [(0, 0, 'no size'), (5, 0, 'no size'),
                          (ERROR_INSUFFICIENT_BUFFER, 112, 'GetExtendedTcpTable failed')],
                         ids=['size-zero', 'size-other-error', 'fill-fails'])
def test_a_tcp_table_that_cannot_be_read_raises_and_denies_with_reader_error(size_rc, fill_rc,
                                                                              reason):
    kernel = ScriptKernel()
    wrapper = KernelApi(kernel)
    wrapper.api.iphlp = FakeIphlp(size_rc=size_rc, fill_rc=fill_rc)
    with pytest.raises(OSError, match=reason):
        wrapper.tcp_rows()
    result = attest.attest_peer(**_readers(wrapper).attest_kwargs(PEER))
    assert not result.ok and result.failures == (attest.READER_ERROR,)


# ── 7. the row decode: count, offset 4, address octets and the port byte swap ──

def test_the_tcp_table_is_decoded_field_by_field_and_a_near_miss_row_never_owns_the_peer():
    payload = (struct.pack('<I', 2)
               + _raw_row(ESTABLISHED, '127.0.0.1', PEER, '127.0.0.1', CORE, 4124)
               + _raw_row(ESTABLISHED, '127.0.0.1', PEER, '10.0.0.5', CORE, 9999))
    kernel = ScriptKernel()
    wrapper = KernelApi(kernel)
    wrapper.api.iphlp = FakeIphlp(payload=payload)
    assert wrapper.tcp_rows() == [
        TcpRow('127.0.0.1', PEER, '127.0.0.1', CORE, ESTABLISHED, 4124),
        TcpRow('127.0.0.1', PEER, '10.0.0.5', CORE, ESTABLISHED, 9999)]
    assert wrapper.api.iphlp.calls == [(True, False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0),
                                       (False, False, AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)]
    assert _readers(wrapper).resolve_owner(PEER).pid == 4124   # only the true peer row
    assert _readers(wrapper).resolve_owner(PEER + 1).pid is None


# ── 8. a failed GetProcessTimes is an unreadable creation time, never 0 ──

def test_a_failed_getprocesstimes_leaves_the_creation_time_unreadable_not_zero():
    kernel = ScriptKernel(times_ok=False, entries=[(4124, 0, 'curl.exe')])
    proc = _win32(kernel).process(4124, (JOB,))
    assert proc.creation_time is None and proc.alive is True
    assert (_win32(ScriptKernel(low=1, high=2)).process(4124, (JOB,)).creation_time
            == (2 << 32) | 1)                                  # CreationTime slot only
    result = attest.attest_peer(**_readers(KernelApi(kernel, rows=PEER_ROWS))
                                .attest_kwargs(PEER))
    assert not result.ok and result.binding is None
    assert attest.CREATION_TIME_UNREADABLE in result.failures


# ── 9. the creation-time boundary: equal timestamps are not "created before" ──

def test_a_parent_created_in_the_same_tick_as_the_child_ends_the_chain():
    api = FakeApi()
    api.table[300] = _proc(300, 0, 100, 'explorer.exe')
    api.table[4124] = _proc(4124, 300, 100, 'curl.exe')        # equal tick, not strictly older
    info = _readers(api).read_process(4124)
    assert info.ancestors == ()                                # >= includes equality
    assert info.alive is True and info.in_core_job is False
    assert info.outside_core is True and info.same_session is True


# ── 10. the process handle is closed in the finally even when the Job probe fails ──

def test_a_failing_job_probe_still_closes_the_process_handle_once_and_in_order():
    kernel = ScriptKernel(injob_ok=False, entries=[(4124, 300, 'curl.exe')])
    with pytest.raises(OSError, match='IsProcessInJob'):
        _win32(kernel).process(4124, (0xdead,))
    assert kernel.closed == [kernel.handle]                    # exactly once, via finally
    assert [n for n, *_ in kernel.calls] == ['open', 'wait', 'times', 'injob']
    # liveness and times were probed before the Job answer, and the walk never started
