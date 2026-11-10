import io
import json
import ntpath
import subprocess
import threading
import time
from contextlib import ExitStack
from typing import Protocol

from . import mxc
from .mxc import MxcUnavailable


CREATE_SUSPENDED = 0x4
EXTENDED_STARTUPINFO_PRESENT = 0x80000
CREATE_UNICODE_ENVIRONMENT = 0x400


class Win32(Protocol):
    # Each allocation returns ownership only on success; failed calls release partial allocations.
    # Fresh protected, non-reparse file; retain deny-write/delete lease until removal.
    def protected_policy(self, data: bytes) -> tuple[str, object]: ...
    def remove_policy(self, path, handle): ...
    # Parent ends noninheritable; child ends inheritable. No other handle is inherited.
    def pipe(self, *, parent_reads: bool) -> tuple[object, object]: ...
    def attribute_list(self, handles: tuple) -> object: ...
    def delete_attribute_list(self, attributes): ...
    def create_process_w(self, *, application, command_line, flags, attributes,
                         inherit_handles, std_handles, cwd, env) -> tuple: ...
    def creation_time(self, process) -> int: ...
    def in_job(self, job, process) -> bool: ...
    def resume_thread(self, thread) -> int: ...
    def terminate_process(self, process): ...
    def close_handle(self, handle): ...
    def poll(self, process) -> int | None: ...
    # None means pending, b'' means EOF. Calls must never block or exceed size.
    def read(self, handle, size: int) -> bytes | None: ...
    def write(self, handle, data: bytes) -> int: ...


class AlreadyDraining(MxcUnavailable):
    """A second wait on a launcher the drain thread already owns: nothing ended."""


class Transport:
    # output_limit bounds each of stdout and stderr; total_limit bounds both together
    # and defaults to twice the per-stream bound, the most two full streams can reach.
    def __init__(self, api: Win32, boundary, *, clock=time.monotonic, pause=time.sleep,
                 output_limit=256 * 1024, total_limit=None):
        if total_limit is None:
            total_limit = 2 * output_limit
        if not all(type(limit) is int and limit > 0 for limit in (output_limit, total_limit)):
            raise ValueError('positive output bound required')
        self.api, self.boundary = api, boundary
        self.clock, self.pause = clock, pause
        self.output_limit, self.total_limit = output_limit, total_limit
        self._policies = {}

    def stage_policy(self, raw):
        path, handle = self.api.protected_policy(
            json.dumps(raw, ensure_ascii=False, allow_nan=False).encode('utf-8'))
        if not ntpath.isabs(path) or not ntpath.splitdrive(path)[0]:
            self.api.remove_policy(path, handle)
            raise MxcUnavailable('absolute protected policy path required')
        self._policies[path] = handle
        return path

    def start(self, job, argv, *, policy, policy_path=None, before_resume=None):
        """Create suspended, assign, verify membership, then resume exactly once.

        `before_resume` is the ownership seam: the ledger builder must make the
        ownership facts durable before the launcher can run, and it is the only thing
        allowed between the membership verification and the resume. A hook that raises
        takes the same path as any other fault here: the suspended child is terminated,
        never resumed, and every handle is closed. It is a parameter and not a second
        code path, so a caller with no ledger still gets this same ordering.
        """
        if job is None:
            raise MxcUnavailable('Core-held Job required')
        child = self.create_suspended(argv, policy=policy, policy_path=policy_path)
        try:
            self.assign_job(job, child)
            if self.in_job(job, child) is not True:
                raise MxcUnavailable('launcher Job membership unverified')
            if before_resume is not None:
                before_resume(child)
            self.resume(child)
        except BaseException:
            child.terminate()
            raise
        return child

    def create_suspended(self, argv, *, policy, policy_path=None):
        path = argv[-1] if policy_path is None else policy_path
        lease = self._policies.pop(path)
        handles, attributes, child = [], None, None
        process = None
        try:
            if not ntpath.isabs(argv[0]) or not ntpath.splitdrive(argv[0])[0]:
                raise MxcUnavailable('absolute Windows application path required')
            if any('\0' in arg for arg in argv):
                raise MxcUnavailable('NUL in launcher arguments')
            pairs = []
            for parent_reads in (False, True, True):
                parent, inherited = self.api.pipe(parent_reads=parent_reads)
                handles.extend((parent, inherited))
                pairs.append((parent, inherited))
            inherited = tuple(pair[1] for pair in pairs)
            attributes = self.api.attribute_list(inherited)
            process, thread, pid = self.api.create_process_w(
                application=argv[0], command_line=subprocess.list2cmdline(argv),
                flags=CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
                attributes=attributes, inherit_handles=True, std_handles=inherited,
                cwd=policy.raw['process']['cwd'], env={})
            handles.extend((process, thread))
            created = self.api.creation_time(process)
            if type(created) is not int or created <= 0:
                raise MxcUnavailable('invalid launcher creation time')
            for handle in inherited:
                self.api.close_handle(handle)
                handles.remove(handle)
            child = Process(self, process, thread, pid, created,
                            tuple(pair[0] for pair in pairs), (path, lease),
                            policy.raw['process']['timeout'] / 1000)
            handles.clear()
            return child
        except BaseException:
            if process is not None:
                self.api.terminate_process(process)
            raise
        finally:
            with ExitStack() as cleanup:    # unwound last first; one failed release skips none
                if child is None:
                    cleanup.callback(self.api.remove_policy, path, lease)
                if attributes is not None:
                    cleanup.callback(self.api.delete_attribute_list, attributes)
                for handle in handles:
                    cleanup.callback(self.api.close_handle, handle)

    def assign_job(self, job, child):
        self.boundary.assign_job(job, child.process_handle)

    def in_job(self, job, child):
        return self.api.in_job(job, child.process_handle)

    def resume(self, child):
        if child.resumed:
            raise MxcUnavailable('launcher already resumed')
        child.resumed = True
        previous = self.api.resume_thread(child.thread_handle)
        if previous != 1:
            raise MxcUnavailable('launcher suspend count was not one')
        return previous


class Input(io.BytesIO):
    def close(self):
        if not self.closed:
            self.data = self.getvalue()
        super().close()

    def payload(self):
        return self.data if self.closed else self.getvalue()


class Process:
    def __init__(self, transport, process, thread, pid, created, pipes, policy_lease, timeout):
        self.transport, self.api = transport, transport.api
        self.process_handle, self.thread_handle = process, thread
        self.pid, self.create_time, self.resumed = pid, created, False
        self._pipes = list(pipes)
        self._handles = [process, thread, *pipes]
        self.stdin, self.stdout, self.stderr = Input(), io.BytesIO(), io.BytesIO()
        self.launcher_exit = None
        self._cancelled = False
        self._policy_lease, self.timeout = policy_lease, timeout
        self._sink, self._stdin_reader = self._buffer, None
        self._seen = {'stdout': 0, 'stderr': 0}
        self._draining = self._stop = False
        self._lock = threading.Lock()       # the drain's use of a handle against its close

    def _buffer(self, name, data):
        getattr(self, name).write(data)

    def attach(self, sink=None, stdin_reader=None):
        """Route output to `sink(name, data)` (name is 'stdout' or 'stderr') and feed
        stdin from `stdin_reader(size)`: bytes, None for nothing yet, b'' for EOF.
        Both are called only on the drain thread, never concurrently, and a callback
        that raises ends the launch like any other fault. Unset ones keep the
        in-memory streams and the buffered `stdin` payload."""
        if self._draining or not self._handles:
            raise MxcUnavailable('launcher is not attachable')
        if sink is not None:
            self._sink = sink
        self._stdin_reader = stdin_reader

    def poll(self):
        """The launcher exit once the drain returned or the launcher was terminated, else
        None. It never asks the kernel, so every output byte has reached the sink first."""
        return None if self._handles else self.launcher_exit

    def _close(self, handle):
        with self._lock:
            if handle in self._handles:
                self._handles.remove(handle)    # a handle that fails to close is not retried
                self.api.close_handle(handle)

    def _use(self, call, handle, *args):
        """*call* on a handle only while it is still open: a cancel that gave up waiting for
        a stuck drain closes the handles under it, and a closed number may name another
        object by the time the drain next looks."""
        with self._lock:
            if handle not in self._handles:
                raise MxcUnavailable('launcher closed during drain')
            return call(handle, *args)

    def close(self):
        failed = None
        for handle in self._handles[:]:
            try:
                self._close(handle)
            except Exception as err:
                failed = failed or err
        self.stdin.close()
        with self._lock:                # two closers must not release one lease twice
            lease, self._policy_lease = self._policy_lease, None
        try:
            if lease is not None:
                self.api.remove_policy(*lease)
        finally:
            if failed is not None:
                raise failed

    def terminate(self):
        if self._draining:
            self._stop = True       # the drain owns the handles: it ends the launch
            return
        failure = None
        with self._lock:                # check and call are one step: a close between them leaves the call on a closed number
            if self._cancelled or not self._handles:
                return
            self._cancelled = True
            try:
                if self.launcher_exit is None:
                    self.api.terminate_process(self.process_handle)
                self.launcher_exit = 1
            except BaseException as err:
                failure = err
        try:
            self.close()
        finally:
            if failure is not None:
                raise failure

    def is_alive(self):
        with self._lock:
            return bool(self._handles) and self.api.poll(self.process_handle) is None

    def wait(self, timeout=None, *, cancelled=lambda: False):
        if self._cancelled:
            raise MxcUnavailable('launcher cancelled')
        if not self._handles:
            if self.launcher_exit is None:
                raise MxcUnavailable('launcher closed')
            return self.launcher_exit
        if self._draining:
            raise AlreadyDraining('launcher already draining')
        self._draining = True
        deadline = self.transport.clock() + max(0, self.timeout if timeout is None else timeout)
        read_input = self._stdin_reader or io.BytesIO(self.stdin.payload()).read
        pending, offset, eof = b'', 0, set()
        try:
            while True:
                if self._stop or cancelled():
                    raise MxcUnavailable('launcher cancelled during drain')
                if self.transport.clock() >= deadline:
                    raise TimeoutError('launcher I/O deadline')
                for index, name in ((1, 'stdout'), (2, 'stderr')):
                    if index in eof:
                        continue
                    data = self._use(self.api.read, self._pipes[index], 65536)
                    if data == b'':
                        eof.add(index)
                        self._close(self._pipes[index])
                    elif data:
                        self._seen[name] += len(data)
                        if (self._seen[name] > self.transport.output_limit
                                or sum(self._seen.values()) > self.transport.total_limit):
                            raise MxcUnavailable('launcher output bound exceeded')
                        self._sink(name, data)
                if self._pipes[0] in self._handles:
                    if offset >= len(pending):
                        chunk = read_input(65536)
                        if chunk == b'':
                            self._close(self._pipes[0])
                            self.stdin.close()
                        else:
                            pending, offset = chunk or b'', 0
                    if offset < len(pending):
                        offset += self._use(self.api.write, self._pipes[0],
                                            pending[offset:offset + 65536])
                self.launcher_exit = self._use(self.api.poll, self.process_handle)
                if self.launcher_exit is not None and len(eof) == 2:
                    self.close()
                    self.stdout.seek(0)
                    self.stderr.seek(0)
                    return self.launcher_exit
                self.transport.pause(0.001)
        except BaseException:
            self._draining = False
            self.terminate()
            self.close()
            raise
        finally:
            self._draining = False


class Backend(mxc.NativeMxc):
    compile_policy = staticmethod(mxc.compile_policy)

    def __init__(self, api, boundary, schema_validator, *, switches=None, **options):
        super().__init__(Transport(api, boundary, **options), schema_validator, switches=switches)
