import ctypes as c
import os
import sys
import time
from types import SimpleNamespace

import pytest

from archeus.node import isolation, mxc, mxc_native as native, win32_mxc as w


pytestmark = [
    pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only Core Job lifecycle'),
    pytest.mark.real_process,
]


def until(check):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = check()
        if result is not None:
            return result
        time.sleep(0.001)
    pytest.fail('Core Job operation exceeded test deadline')


def assert_invalid(api, handle):
    bits = w.DWORD()
    assert not api.functions['GetHandleInformation'](handle, c.byref(bits))
    assert c.get_last_error() == 6


class JobPids(c.Structure):
    _fields_ = [('assigned', w.DWORD), ('count', w.DWORD), ('pids', c.c_size_t * 16)]


class ObservedApi(w.Win32Api):
    def __init__(self, directory):
        super().__init__(directory)
        self.open = set()
        self.observers = []
        self.events = []
        kernel = c.WinDLL('kernel32', use_last_error=True)
        self.open_process = kernel.OpenProcess
        self.open_process.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.open_process.restype = w.HANDLE
        self.query_job = kernel.QueryInformationJobObject
        self.query_job.argtypes = [w.HANDLE, c.c_int, w.PTR, w.DWORD, w.PTR]
        self.query_job.restype = w.BOOL

    def protected_policy(self, data):
        path, lease = super().protected_policy(data)
        self.open.update([lease.file, *lease.directories])
        return path, lease

    def pipe(self, **options):
        pair = super().pipe(**options)
        self.open.update(pair)
        return pair

    def create_process_w(self, **options):
        assert options['flags'] & native.CREATE_SUSPENDED
        process, thread, pid = super().create_process_w(**options)
        self.open.update((process, thread))
        self.events.append('create')
        self.observe(pid)
        assert self.poll(process) is None
        return process, thread, pid

    def observe(self, pid):
        handle = self.open_process(0x100000 | 0x1000, False, pid)
        if not handle:
            raise self._error('OpenProcess')
        self.observers.append(handle)
        return handle

    def in_job(self, job, process):
        result = super().in_job(job, process)
        assert result is True
        self.events.append('query')
        return result

    def resume_thread(self, thread):
        self.events.append('resume')
        return super().resume_thread(thread)

    def close_handle(self, handle):
        super().close_handle(handle)
        assert_invalid(self, handle)    # at once: a later allocation may reuse the number
        self.open.discard(handle)

    def pids(self, job):
        info = JobPids()
        if not self.query_job(job, 3, c.byref(info), c.sizeof(info), None):
            raise self._error('QueryInformationJobObject')
        assert info.assigned <= 16
        return list(info.pids[:info.count])

    def assert_closed(self):
        assert not self.open


def setup(tmp_path):
    boundary = isolation.WindowsBoundary()
    assert boundary.available() is False
    assert mxc.NATIVE_RUN_ENABLED is False
    api = ObservedApi(tmp_path)
    transport = native.Transport(api, boundary)
    policy = SimpleNamespace(raw={'process': {'cwd': str(tmp_path), 'timeout': 10000}})
    command = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32', 'cmd.exe')
    return boundary, api, transport, policy, command


def test_core_job_close_kills_child_and_grandchild(tmp_path, monkeypatch):
    boundary, api, transport, policy, command = setup(tmp_path)
    job = boundary.create_job('mxc-transport-test')
    child = None
    assign = boundary.assign_job

    def assigned(job, process):
        assert api.poll(process) is None
        assert 'resume' not in api.events
        assign(job, process)
        api.events.append('assign')

    monkeypatch.setattr(boundary, 'assign_job', assigned)
    try:
        path = transport.stage_policy(policy.raw)
        child = transport.start(job, [command, '/d', '/q'], policy=policy, policy_path=path)
        assert api.events == ['create', 'assign', 'query', 'resume']
        with pytest.raises(mxc.MxcUnavailable, match='already resumed'):
            transport.resume(child)
        assert api.events.count('resume') == 1
        data = ('"' + command + '" /d /q\r\n').encode('ascii')
        offset = 0

        def send():
            nonlocal offset
            offset += api.write(child._pipes[0], data[offset:])
            return True if offset == len(data) else None

        until(send)

        def tree():
            pids = api.pids(job)
            return pids if len(pids) == 2 else None

        pids = until(tree)
        assert child.pid in pids
        grandchild = api.observe(next(pid for pid in pids if pid != child.pid))
        assert api.in_job(job, grandchild)
        assert api.poll(child.process_handle) is None
        assert api.poll(grandchild) is None
        boundary.close_job(job)
        assert_invalid(api, job)
        job = None
        for handle in api.observers:
            assert until(lambda handle=handle: api.poll(handle)) is not None
    finally:
        if job is not None:
            boundary.close_job(job)
        if child is not None:
            child.close()
        for handle in api.observers:
            if api.poll(handle) is None:
                api.terminate_process(handle)
                until(lambda handle=handle: api.poll(handle))
            api.close_handle(handle)
    api.assert_closed()
    assert not list(tmp_path.glob('*.json'))


def test_second_start_assignment_fault_leaves_no_child_or_handles(tmp_path, monkeypatch):
    boundary, api, transport, policy, command = setup(tmp_path)
    job = boundary.create_job('mxc-transport-fault-test')
    first = None
    try:
        path = transport.stage_policy(policy.raw)
        first = transport.start(job, [command, '/d', '/q'], policy=policy, policy_path=path)
        first.close()
        boundary.close_job(job)
        assert_invalid(api, job)
        job = None
        until(lambda: api.poll(api.observers[0]))
        api.events.clear()
        job = boundary.create_job('mxc-transport-fault-test-2')

        def refused(job, process):
            assert api.poll(process) is None
            raise OSError('injected assignment failure')

        monkeypatch.setattr(boundary, 'assign_job', refused)
        path = transport.stage_policy(policy.raw)
        with pytest.raises(OSError, match='injected assignment failure'):
            transport.start(job, [command, '/d', '/q'], policy=policy, policy_path=path)
        assert api.events == ['create']
        assert until(lambda: api.poll(api.observers[1])) == 1
        assert not api.open
    finally:
        if job is not None:
            boundary.close_job(job)
        if first is not None:
            first.close()
        for handle in api.observers:
            if api.poll(handle) is None:
                api.terminate_process(handle)
                until(lambda handle=handle: api.poll(handle))
            api.close_handle(handle)
    api.assert_closed()
    assert not list(tmp_path.glob('*.json'))
