"""The isolated launch on the MXC transport, and the child object it hands the adapter.

`base.spawn` gets an object with `pid`, `poll()` and `wait(timeout)`, and the adapter reads
the stream file the child wrote. The MXC launcher is not a file-handle process: its stdin is a
payload and its output is read from pipes Core drains, so a pump thread feeds the prompt in and
appends what comes out to the stream. One thread owns the launch's handles (`MxcLaunch.wait`
runs once, on it), and every stop of Core's goes through `MxcLaunch.cancel` with a reason.
"""

import threading

from ..harnesses import base
from .isolation import IsolationContext, IsolationUnavailable, base_create_time

#: how long a stop waits for the pump to hand the launch back before it ends it itself
PUMP_JOIN_S = 10.0
#: a real agent stream runs for hours, and the transport's 256 KiB default would end it. The
#: stream goes to disk, not memory, so this bounds what one execution can write
STREAM_BYTES = 256 * 1024 * 1024


def _refused(err):
    return base.SpawnFailed('isolation: %s%s' % (err.reason,
                                                 ' (%s)' % err.detail if err.detail else ''))


class MxcChild:
    """One running MXC launch as the process it stands for. `poll()` answers only once the
    pump returned, so every output byte has reached the stream first."""

    def __init__(self, launch, paths):
        self.launch, self.paths, self.pid = launch, paths, launch.pid
        self.reason = None          # why a stop of Core's ended it; None for an end of its own
        self.fault = None
        self._exit = self._in = self._out = None
        self._done, self._stop = threading.Event(), threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        launch.process.attach(self._write, self._read)

    def _write(self, name, data):
        self._out.write(data)       # unbuffered: the adapter tails this file while it grows

    def _read(self, size):
        return self._in.read(size)

    def _pump(self):
        code = 1                    # an end with no workload outcome is never a clean exit
        try:
            with open(self.paths.prompt, 'rb') as self._in, \
                    open(self.paths.stream, 'ab', buffering=0) as self._out:
                code = self.launch.wait(cancelled=self._stop.is_set)
        except Exception as err:
            self.fault = err
            self.launch.cancel(reason='the pump failed: %s' % type(err).__name__)
        finally:
            self._exit = code
            self._done.set()

    def start(self):
        self._thread.start()

    def poll(self):
        return self._exit if self._done.is_set() else None

    def wait(self, timeout=None):
        self._done.wait(timeout)
        return self.poll()

    def cancel(self, reason='cancelled'):
        """End the launch through `MxcLaunch.cancel`: the pump is told to stop and records
        the reason as it ends the launch, so the handles it holds are never closed under it.
        Idempotent, and the first reason is the only one: the ledger and `reason` agree.
        Returns the launch's end state."""
        with self._lock:
            if self.reason is None and not self._done.is_set():
                self.reason = self.launch.stop_reason = reason
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(PUMP_JOIN_S)
        return self.launch.cancel(reason=self.reason or reason)


class MxcIsolationContext(IsolationContext):
    """`IsolationContext` for a boundary whose transport owns the child's stdio: the same
    six conditions are established, and no inherited handle is opened for the prompt or the
    stream."""

    def _limits(self):
        limits = dict(self.request.limits)
        transport = {'output_limit': limits.get('output_bytes', STREAM_BYTES)}
        if 'total_bytes' in limits:
            transport['total_limit'] = limits['total_bytes']
        out = {'transport': transport}
        if 'timeout_s' in limits:
            out['timeout_ms'] = int(limits['timeout_s'] * 1000)
        return out

    def launch(self, argv, *, cwd, env, paths):
        authority, request = self.authority, self.request
        try:
            rec = authority.establish(request, paths)
        except IsolationUnavailable as err:
            raise _refused(err)
        launch = None
        try:
            launch = authority.boundary.launch(
                list(argv), cwd=cwd, env=env, profile=rec.profile,
                job=authority.held_job(rec.execution_id), stdin=None, stdout=None,
                **self._limits())
            rec.pid, rec.create_time = launch.pid, base_create_time(launch.pid)
            authority._save(rec)
            child = MxcChild(launch, paths)
            authority._live[rec.execution_id] = child
            authority.children[(rec.execution_id, request.process_seq)] = child
            child.start()
            return child, None
        except Exception as err:        # nothing half-started survives
            if launch is not None:
                launch.cancel(reason='launch failed')
            if isinstance(err, IsolationUnavailable):
                raise _refused(err)
            raise base.SpawnFailed('isolation: launch_failed (%s)' % err)
