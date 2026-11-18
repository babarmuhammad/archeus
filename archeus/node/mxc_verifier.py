"""The child of a confined verifier check on MXC (PV-20 B11).

`Isolation.run_confined` polls its child (`wait(t)` answers None while it runs) and reads
the check's output from a file Core owns. `MxcLaunch.wait` instead blocks until the
launcher exits and keeps the output in memory, so one drain thread owns it: the
transport's stdout and stderr are appended to the attempt's `out.log` as they arrive
(the file is outside every grant, only Core writes it), stdin is the attempt's empty
file, and the launch's own end (the Core-owned outcome, the ledger completion) runs on
that thread before the child reports an exit.

A drain that stops on a bound, the deadline or a transport fault is a `fault`: an error
result, never a verdict. A fault of Core's own (an outcome Core cannot read, a ledger
that refuses) is raised from `wait`, as it was before there was a thread.
"""

import threading

from . import mxc_native, staging
from .mxc_context import PUMP_JOIN_S


class ConfinedChild:
    def __init__(self, launch, timeout, stdin_path, out_path):
        self.launch, self.fault, self.code, self._raised = launch, None, None, None
        self._late = 'timed out after %ds' % timeout
        self._stop = threading.Event()
        self._stdin = open(stdin_path, 'rb')
        try:
            self._out = open(out_path, 'ab')
            launch.process.attach(sink=self._append, stdin_reader=self._stdin.read)
        except BaseException:
            self._close()
            raise
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _append(self, name, data):
        self._out.write(data)
        self._out.flush()

    def _close(self):
        for f in (self._stdin, getattr(self, '_out', None)):
            if f is not None:
                f.close()

    def _drain(self):
        try:
            self.code = self.launch.wait(cancelled=self._stop.is_set)
        except TimeoutError:
            self.fault = self._late
        except staging.StageError as err:
            self._raised = err
        except (mxc_native.MxcUnavailable, OSError) as err:
            self.fault = 'launcher_failed: %s' % err
        except BaseException as err:
            self._raised = err
        finally:
            self._close()

    def cancel(self, reason):
        """End the launch while the caller still holds its Job: the drain is told to stop and
        ends the launch itself, so the Job is never closed under a drain that still ends
        against it. The first reason is the one the launch records."""
        if self.launch.stop_reason is None:
            self.launch.stop_reason = reason
        self._stop.set()
        self._thread.join(PUMP_JOIN_S)
        return self.launch.cancel(reason=reason)

    def wait(self, timeout=None):
        """The workload's exit code once the drain and the launch's end are over, 1 for
        a drain that faulted (`fault` says why), None while it runs."""
        self._thread.join(timeout)
        if self._thread.is_alive():
            return None
        if self._raised is not None:
            raise self._raised
        return 1 if self.fault else self.code
