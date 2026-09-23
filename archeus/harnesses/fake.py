"""The fake harness adapter (execution-architecture §3: `fake`).

A real subprocess — `fake_agent.py` driven by a scenario — under the same
process I/O contract as every real adapter, so the registry, stream tailing and
reconciliation paths are exercised from the first phase. The scenario is the
task contract's `fake_scenario` list (see fake_agent.py for the step format).

It needs no account, no network and no model: fake/scripted calls are the one
model-call class that is unrestricted (plan §31.4).
"""

import json
import os
import sys

from claude_sessions import proc

from . import base

AGENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fake_agent.py')

_NOT_YET = 'the fake harness does not simulate %s until P11 (pause/resume/hand-off)'


class FakeHarness:
    id = 'fake'

    def __init__(self):
        self._children = {}     # execution_id -> Popen, for exit codes of what we started
        self._stopped = set()

    def discover(self):
        return base.HarnessInfo(self.id, True, '1', sys.executable)

    def capabilities(self, account):
        return base.Capabilities(frozenset({'code_edit', 'shell', 'structured_output',
                                            'headless'}), 'hook', ('fake-model',))

    def authenticate(self, account):
        return base.AuthStatus(True, 'fake accounts need no login')

    def start(self, spec):
        steps = list(spec.task_contract.get('fake_scenario', ()))
        argv = [sys.executable, AGENT, json.dumps(steps)]
        handle, child = base.spawn(spec, argv)
        self._children[spec.execution_id] = child
        return handle

    def send(self, handle, message):
        raise NotImplementedError('the fake harness is non-interactive: its input is the '
                                  'stdin file')

    def pause(self, handle):
        raise NotImplementedError(_NOT_YET % 'pause')

    def resume(self, spec, state):
        raise NotImplementedError(_NOT_YET % 'resume')

    def handoff(self, checkpoint):
        raise NotImplementedError(_NOT_YET % 'hand-off')

    def status(self, handle):
        child = self._children.get(handle.execution_id)
        if child is not None:
            code = child.poll()
            return base.ProcStatus('running' if code is None else 'exited', code)
        # not ours (a restarted Core): the pid only counts if it is still the
        # process that was created at the recorded time
        alive = (handle.create_time is not None
                 and proc.process_create_time(handle.pid) == handle.create_time)
        if alive:
            return base.ProcStatus('running')
        ended = base.read_json(os.path.join(handle.exec_dir, 'ended')) or {}
        return base.ProcStatus('exited', ended.get('exit_code'))

    def inspect(self, handle):
        events, offset = base.read_stream(os.path.join(handle.exec_dir, 'stream.jsonl'))
        return base.Snapshot(tuple(events), offset)

    def stop(self, handle, *, grace_s=0.0):
        # no hook to halt at a tool boundary, so stop is the registry kill
        if not proc.kill_pid_tree(handle.pid, handle.create_time):
            if proc.process_create_time(handle.pid) is not None:
                raise base.StopRefused('pid %d is not the process this execution started'
                                       % handle.pid)
            return                                  # already gone
        self._stopped.add(handle.execution_id)
        child = self._children.get(handle.execution_id)
        if child is not None:
            try:
                child.wait(timeout=10)
            except Exception:
                pass

    def collect_result(self, handle):
        st = self.status(handle)
        if st.state == 'running':
            raise RuntimeError('execution %s is still running' % handle.execution_id)
        events = self.inspect(handle).events
        results = [e for e in events if e.get('type') == 'result']
        usage = [e['usage'] for e in events if isinstance(e.get('usage'), dict)]
        if handle.execution_id in self._stopped:
            reason = 'killed'
        else:
            reason = 'ok' if st.exit_code == 0 else 'error'
        return base.ExecutionResult(
            exit_reason=reason, exit_code=st.exit_code,
            reported_summary=results[-1].get('summary', '') if results else '',
            usage=usage[-1] if usage else {},
            transcript_path=os.path.join(handle.exec_dir, 'stream.jsonl'))
