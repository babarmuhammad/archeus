import ctypes as c
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from archeus.node import win32_mxc as w


class Function:
    def __init__(self, callback=lambda *args: 1):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


def fake_api(monkeypatch):
    errors = [122]
    monkeypatch.setattr(c, 'get_last_error', lambda: errors[0], raising=False)
    kernel = SimpleNamespace(**{name: Function() for name in w.SIGNATURES})
    api = object.__new__(w.Win32Api)
    api.functions = w.bind(kernel)
    return api, errors


def test_signatures_cover_every_api(monkeypatch):
    api, _ = fake_api(monkeypatch)
    expected = {
        'CreateFileW', 'GetFileInformationByHandleEx', 'DeleteFileW', 'CreatePipe',
        'SetHandleInformation', 'GetHandleInformation', 'SetNamedPipeHandleState',
        'PeekNamedPipe', 'ReadFile', 'WriteFile', 'InitializeProcThreadAttributeList',
        'UpdateProcThreadAttribute', 'DeleteProcThreadAttributeList', 'CreateProcessW',
        'GetProcessTimes', 'IsProcessInJob', 'ResumeThread', 'TerminateProcess',
        'CloseHandle', 'GetExitCodeProcess', 'WaitForSingleObject',
    }
    assert set(api.functions) == expected
    for name, function in api.functions.items():
        assert function.argtypes == w.SIGNATURES[name][0]
        assert function.restype is w.SIGNATURES[name][1]
        assert function.argtypes
    for name in ('CreateFileW',):
        assert api.functions[name].restype is c.c_void_p
    assert c.sizeof(w.HANDLE) == c.sizeof(c.c_void_p)


def test_non_windows_constructor(monkeypatch, tmp_path):
    monkeypatch.setattr(w.sys, 'platform', 'linux')
    with pytest.raises(RuntimeError, match='Win32Api requires Windows'):
        w.Win32Api(tmp_path)


def test_error_only_api_and_code(monkeypatch):
    api, errors = fake_api(monkeypatch)
    errors[0] = 5
    api.functions['CloseHandle'].callback = lambda *args: 0
    with pytest.raises(w.Win32Error) as caught:
        api.close_handle(123)
    assert caught.value.api == 'CloseHandle'
    assert caught.value.code == 5
    assert str(caught.value) == 'CloseHandle: 5'


def test_pipe_inheritance_and_nowait(monkeypatch):
    api, _ = fake_api(monkeypatch)
    calls = []

    def create(read, write, security, size):
        assert security._obj.inherit == 1
        read._obj.value, write._obj.value = 101, 102
        return 1

    api.functions['CreatePipe'].callback = create
    api.functions['SetHandleInformation'].callback = lambda *args: calls.append(args) or 1
    api.functions['SetNamedPipeHandleState'].callback = (
        lambda handle, mode, *args: calls.append((handle, mode._obj.value)) or 1)
    assert api.pipe(parent_reads=True) == (101, 102)
    assert api.pipe(parent_reads=False) == (102, 101)
    assert calls == [(101, 1, 0), (101, 1), (102, 1, 0), (102, 1)]


def test_attribute_contents(monkeypatch):
    api, _ = fake_api(monkeypatch)
    calls = []

    def initialize(buffer, count, flags, size):
        size._obj.value = 128
        return int(buffer is not None)

    api.functions['InitializeProcThreadAttributeList'].callback = initialize
    api.functions['UpdateProcThreadAttribute'].callback = lambda *args: calls.append(args) or 1
    attributes = api.attribute_list((101, 102, 103))
    assert tuple(attributes.handles) == (101, 102, 103)
    assert len(calls) == 1
    assert calls[0][2] == 0x20002
    assert tuple(calls[0][3]) == (101, 102, 103)
    assert calls[0][4] == 3 * c.sizeof(w.HANDLE)
    api.delete_attribute_list(attributes)


def test_explicit_environment_and_creation(monkeypatch):
    api, _ = fake_api(monkeypatch)
    attributes = w.Attributes(c.create_string_buffer(128), (w.HANDLE * 3)(101, 102, 103))
    calls = []
    api.functions['CreateProcessW'].callback = lambda *args: calls.append(args) or 1
    api.create_process_w(application='cmd.exe', command_line='cmd /c exit 7', flags=0x80404,
                         attributes=attributes, inherit_handles=True,
                         std_handles=(101, 102, 103), cwd='C:\\private', env={})
    assert len(calls) == 1
    args = calls[0]
    assert args[4] is True
    assert args[5] & 4
    assert args[6] is not None
    assert args[6][:2] == '\0\0'
    assert args[7] == 'C:\\private'
    startup = args[8]._obj
    assert startup.startup.cb == c.sizeof(w.StartupInfoEx)
    assert startup.startup.flags == 0x100
    assert (startup.startup.stdin, startup.startup.stdout,
            startup.startup.stderr) == (101, 102, 103)
    assert startup.attributes == c.addressof(attributes.buffer)
    assert w.environment_block({'z': '2', 'A': '1'})[:9] == 'A=1\0z=2\0\0'


def test_partial_allocation_cleanup(monkeypatch):
    api, errors = fake_api(monkeypatch)
    closed = []
    api.functions['CloseHandle'].callback = lambda handle: closed.append(handle) or 1

    def pipe(read, write, *args):
        read._obj.value, write._obj.value = 101, 102
        return 0

    errors[0] = 5
    api.functions['CreatePipe'].callback = pipe
    with pytest.raises(w.Win32Error, match='CreatePipe: 5'):
        api.pipe(parent_reads=True)
    assert closed == [101, 102]
    closed.clear()

    def create(*args):
        info = args[-1]._obj
        info.process, info.thread = 201, 202
        return 0

    api.functions['CreateProcessW'].callback = create
    attributes = w.Attributes(c.create_string_buffer(128), (w.HANDLE * 3)(101, 102, 103))
    with pytest.raises(w.Win32Error, match='CreateProcessW: 5'):
        api.create_process_w(application='cmd.exe', command_line='cmd /c exit 7',
                             flags=0x80404, attributes=attributes, inherit_handles=True,
                             std_handles=(101, 102, 103), cwd='C:\\private', env={})
    assert closed == [202, 201]


def test_attribute_update_failure_deletes_list(monkeypatch):
    api, errors = fake_api(monkeypatch)
    deleted = []

    def initialize(buffer, count, flags, size):
        size._obj.value = 128
        return int(buffer is not None)

    api.functions['InitializeProcThreadAttributeList'].callback = initialize
    api.functions['UpdateProcThreadAttribute'].callback = lambda *args: 0
    api.functions['DeleteProcThreadAttributeList'].callback = lambda value: deleted.append(value)
    with pytest.raises(w.Win32Error, match='UpdateProcThreadAttribute: 122'):
        api.attribute_list((101, 102, 103))
    assert len(deleted) == 1


def test_pending_eof_bounded_io_and_exit_259(monkeypatch):
    api, errors = fake_api(monkeypatch)
    api.functions['WaitForSingleObject'].callback = lambda *args: 258
    assert api.poll(1) is None
    api.functions['WaitForSingleObject'].callback = lambda *args: 0

    def exit_code(handle, code):
        code._obj.value = 259
        return 1

    api.functions['GetExitCodeProcess'].callback = exit_code
    assert api.poll(1) == 259
    assert api.read(1, 2) is None
    errors[0] = 109
    api.functions['PeekNamedPipe'].callback = lambda *args: 0
    assert api.read(1, 2) == b''
    errors[0] = 232
    api.functions['WriteFile'].callback = lambda *args: 0
    assert api.write(1, b'x') == 0
    with pytest.raises(ValueError):
        api.read(1, 65537)


def test_read_and_write_bound_each_transfer(monkeypatch):
    api, _ = fake_api(monkeypatch)

    def peek(handle, buffer, size, count, available, left):
        available._obj.value = 20
        return 1

    def read(handle, buffer, size, count, overlapped):
        assert size == 3
        c.memmove(buffer, b'abc', 3)
        count._obj.value = 3
        return 1

    def write(handle, buffer, size, count, overlapped):
        assert size == 65536
        assert len(buffer) == size
        count._obj.value = 17
        return 1

    api.functions['PeekNamedPipe'].callback = peek
    api.functions['ReadFile'].callback = read
    api.functions['WriteFile'].callback = write
    assert api.read(1, 3) == b'abc'
    assert api.write(1, b'x' * 100000) == 17


windows = pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only Win32 bindings')


def until(check):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = check()
        if result is not None:
            return result
        time.sleep(0.001)
    pytest.fail('Win32 operation exceeded test deadline')


@windows
@pytest.mark.real_process
@pytest.mark.parametrize('terminate', [False, True])
def test_suspended_cmd_lifecycle(tmp_path, terminate):
    api = w.Win32Api(tmp_path)
    handles, attributes, process = [], None, None
    closed = []
    try:
        pairs = [api.pipe(parent_reads=value) for value in (False, True, True)]
        handles.extend(handle for pair in pairs for handle in pair)
        # Extra inheritable pipe tests kernel allowlisting: its reader must see EOF.
        extra = api.pipe(parent_reads=True)
        handles.extend(extra)
        inherited = tuple(pair[1] for pair in pairs)
        attributes = api.attribute_list(inherited)
        assert tuple(attributes.handles) == inherited
        for parent, child in pairs:
            bits = w.DWORD()
            api._call('GetHandleInformation', parent, c.byref(bits))
            assert bits.value & 1 == 0
            api._call('GetHandleInformation', child, c.byref(bits))
            assert bits.value & 1 == 1
        command = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32', 'cmd.exe')
        process, thread, pid = api.create_process_w(
            application=command,
            command_line=subprocess.list2cmdline([command, '/d', '/c', 'exit 7']),
            flags=0x80404, attributes=attributes, inherit_handles=True,
            std_handles=inherited, cwd=str(tmp_path), env={})
        handles.extend((process, thread))
        assert pid > 0
        assert type(api.creation_time(process)) is int
        assert api.creation_time(process) > 0
        assert api.poll(process) is None
        api.close_handle(extra[1])
        handles.remove(extra[1])
        closed.append(extra[1])
        assert api.read(extra[0], 1) == b''
        for child in inherited:
            api.close_handle(child)
            handles.remove(child)
            closed.append(child)
        if terminate:
            api.terminate_process(process)
            assert until(lambda: api.poll(process)) == 1
        else:
            assert api.resume_thread(thread) == 1
            assert until(lambda: api.poll(process)) == 7
        for parent, _ in pairs[1:]:
            assert until(lambda parent=parent: api.read(parent, 65536)) == b''
    finally:
        if process is not None and api.poll(process) is None:
            api.terminate_process(process)
            until(lambda: api.poll(process))
        if attributes is not None:
            api.delete_attribute_list(attributes)
        for handle in reversed(handles):
            api.close_handle(handle)
            closed.append(handle)
    for handle in closed:
        bits = w.DWORD()
        assert not api.functions['GetHandleInformation'](handle, c.byref(bits))
        assert c.get_last_error() == 6


@windows
@pytest.mark.real_process
def test_policy_lease_and_nonblocking_capacity(tmp_path):
    api = w.Win32Api(tmp_path)
    path, lease = api.protected_policy(b'{"private":true}')
    try:
        assert os.path.isabs(path)
        with open(path, 'rb') as policy:
            assert policy.read() == b'{"private":true}'
        handle = api.functions['CreateFileW'](path, 0x40000000, 7, None, 3, 0x80, None)
        if handle != w.INVALID_HANDLE:
            api.close_handle(handle)
            pytest.fail('policy writable during lease')
        assert not api.functions['DeleteFileW'](path)
    finally:
        api.remove_policy(path, lease)
    assert not os.path.exists(path)
    parent, child = api.pipe(parent_reads=False)
    try:
        total = 0
        for _ in range(1024):
            count = api.write(parent, b'x' * 65536)
            total += count
            if count == 0:
                break
        else:
            pytest.fail('pipe did not reach capacity')
        assert total > 0
    finally:
        api.close_handle(parent)
        api.close_handle(child)
