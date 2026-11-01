"""Native readers for the origin attestor (PV-20 B9): port -> owning PID, and PID -> one
process observation. The Windows calls sit behind `Win32OriginApi`; the readers
below only reduce an api object's answers to the attestor's `PeerOwner` and
`ProcessInfo`, so every decision runs against a fake api in a test.

Importing this module loads no DLL and calls nothing native. Nothing here is used
by production code until the origin gate is activated.

Liveness is a wait on the process handle that times out (not signalled): F9C saw
OpenProcess succeed and IsProcessInJob answer TRUE for a dead PID, so neither is
read as "alive". Ancestry follows the parent PID only while each parent is alive and
was created before its child, so a recycled parent PID ends the chain instead of
extending it.
"""
import ctypes as c
import sys
import time
from dataclasses import dataclass

from ..api.origin import AttestationReaders
from .attest import DEFAULT_LAUNCHER, PeerOwner, ProcessInfo

MAX_ANCESTORS = 32
ESTABLISHED = 5
LOOPBACK = '127.0.0.1'


@dataclass(frozen=True)
class TcpRow:
    local_addr: str
    local_port: int
    remote_addr: str
    remote_port: int
    state: int
    pid: int


@dataclass(frozen=True)
class RawProcess:
    alive: bool
    creation_time: "int | None"
    parent_pid: int
    name: str
    session_id: int
    in_jobs: bool


def native_readers(api, *, core_port, jobs, clock=time.monotonic, launcher=DEFAULT_LAUNCHER,
                   max_age_s=None, reattest=False):
    """The attestor's readers over *api*; *jobs* returns Core's held Job handles."""

    def resolve_owner(peer_port):
        pids = {row.pid for row in api.tcp_rows()
                if row.state == ESTABLISHED and row.pid > 0
                and row.local_addr == LOOPBACK and row.local_port == peer_port
                and row.remote_addr == LOOPBACK and row.remote_port == core_port}
        return PeerOwner(pid=pids.pop() if len(pids) == 1 else None)

    def read_process(pid):
        process = api.process(pid, tuple(jobs()))
        if process is None:
            return ProcessInfo(alive=False, creation_time=None, ancestors=(),
                               in_core_job=False)
        return ProcessInfo(alive=process.alive, creation_time=process.creation_time,
                           ancestors=_ancestors(api, process),
                           in_core_job=process.in_jobs,
                           same_session=process.session_id == api.core_session())

    return AttestationReaders(resolve_owner=resolve_owner, read_process=read_process,
                              clock=clock, launcher=launcher, max_age_s=max_age_s,
                              reattest=reattest)


def _ancestors(api, process):
    names, seen = [], set()
    child, parent_pid = process, process.parent_pid
    while parent_pid and parent_pid not in seen and len(names) < MAX_ANCESTORS:
        seen.add(parent_pid)
        parent = api.process(parent_pid, ())
        if (parent is None or not parent.alive or parent.creation_time is None
                or child.creation_time is None or parent.creation_time >= child.creation_time):
            break
        names.append(parent.name.lower().removesuffix('.exe'))
        child, parent_pid = parent, parent.parent_pid
    return tuple(names)


DWORD = c.c_uint32
HANDLE = c.c_void_p
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x100000
WAIT_TIMEOUT = 258
TH32CS_SNAPPROCESS = 2
TCP_TABLE_OWNER_PID_ALL = 5
AF_INET = 2
ERROR_INSUFFICIENT_BUFFER = 122


class FileTime(c.Structure):
    _fields_ = [('low', DWORD), ('high', DWORD)]


class ProcessEntry(c.Structure):
    _fields_ = [('size', DWORD), ('usage', DWORD), ('pid', DWORD), ('heap', c.c_size_t),
                ('module', DWORD), ('threads', DWORD), ('parent', DWORD),
                ('priority', c.c_long), ('flags', DWORD), ('exe', c.c_wchar * 260)]


class TcpRowOwnerPid(c.Structure):
    _fields_ = [('state', DWORD), ('local_addr', DWORD), ('local_port', DWORD),
                ('remote_addr', DWORD), ('remote_port', DWORD), ('pid', DWORD)]


def _address(value):
    return '.'.join(str(b) for b in value.to_bytes(4, 'little'))


def _port(value):
    return ((value & 0xff) << 8) | ((value >> 8) & 0xff)


class Win32OriginApi:
    """The real api. Built only on an explicit call, never at import; tests use a fake."""

    def __init__(self):
        if sys.platform != 'win32':
            raise RuntimeError('Win32OriginApi requires Windows')
        kernel = c.WinDLL('kernel32', use_last_error=True)
        self.kernel = kernel
        self.iphlp = c.WinDLL('iphlpapi', use_last_error=True)
        kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [DWORD, c.c_int32, DWORD], HANDLE
        kernel.CloseHandle.argtypes = [HANDLE]
        kernel.WaitForSingleObject.argtypes = [HANDLE, DWORD]
        kernel.WaitForSingleObject.restype = DWORD
        kernel.GetProcessTimes.argtypes = [HANDLE] + [c.POINTER(FileTime)] * 4
        kernel.IsProcessInJob.argtypes = [HANDLE, HANDLE, c.POINTER(c.c_int32)]
        kernel.CreateToolhelp32Snapshot.argtypes = [DWORD, DWORD]
        kernel.CreateToolhelp32Snapshot.restype = HANDLE
        kernel.Process32FirstW.argtypes = [HANDLE, c.POINTER(ProcessEntry)]
        kernel.Process32NextW.argtypes = [HANDLE, c.POINTER(ProcessEntry)]
        kernel.ProcessIdToSessionId.argtypes = [DWORD, c.POINTER(DWORD)]
        kernel.GetCurrentProcessId.restype = DWORD
        self.iphlp.GetExtendedTcpTable.argtypes = [
            c.c_void_p, c.POINTER(DWORD), c.c_int32, DWORD, DWORD, DWORD]

    def tcp_rows(self):
        size = DWORD(0)
        args = (AF_INET, TCP_TABLE_OWNER_PID_ALL, 0)
        if self.iphlp.GetExtendedTcpTable(None, c.byref(size), False, *args) != ERROR_INSUFFICIENT_BUFFER:
            raise OSError('GetExtendedTcpTable: no size')
        buffer = c.create_string_buffer(size.value + 4096)
        size = DWORD(len(buffer))
        if self.iphlp.GetExtendedTcpTable(buffer, c.byref(size), False, *args) != 0:
            raise OSError('GetExtendedTcpTable failed')
        count = DWORD.from_buffer(buffer).value
        rows = (TcpRowOwnerPid * count).from_buffer(buffer, 4)
        return [TcpRow(_address(r.local_addr), _port(r.local_port), _address(r.remote_addr),
                       _port(r.remote_port), r.state, r.pid) for r in rows]

    def core_session(self):
        return self._session(self.kernel.GetCurrentProcessId())

    def _session(self, pid):
        session = DWORD()
        if not self.kernel.ProcessIdToSessionId(pid, c.byref(session)):
            raise OSError('ProcessIdToSessionId failed')
        return session.value

    def process(self, pid, jobs):
        handle = self.kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if not handle:
            return None
        try:
            alive = self.kernel.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
            times = [FileTime() for _ in range(4)]
            created = None
            if self.kernel.GetProcessTimes(handle, *(c.byref(t) for t in times)):
                created = times[0].low | times[0].high << 32
            in_jobs = False
            for job in jobs:
                inside = c.c_int32()
                if self.kernel.IsProcessInJob(handle, job, c.byref(inside)) and inside.value:
                    in_jobs = True
            parent, name = self._entry(pid)
            return RawProcess(alive, created, parent, name, self._session(pid), in_jobs)
        finally:
            self.kernel.CloseHandle(handle)

    def _entry(self, pid):
        snapshot = self.kernel.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot in (None, c.c_void_p(-1).value):
            raise OSError('CreateToolhelp32Snapshot failed')
        try:
            entry = ProcessEntry()
            entry.size = c.sizeof(entry)
            more = self.kernel.Process32FirstW(snapshot, c.byref(entry))
            while more:
                if entry.pid == pid:
                    return entry.parent, entry.exe
                more = self.kernel.Process32NextW(snapshot, c.byref(entry))
            return 0, ''
        finally:
            self.kernel.CloseHandle(snapshot)
