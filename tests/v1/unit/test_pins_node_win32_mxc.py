"""T-820: pins for the security-relevant branches of archeus/node/win32_mxc.py.

Each test names one condition of the module and fails when that condition is
inverted, removed or loosened (mutation-proved under /work/scratch, never in the
repo). Nothing here touches a Windows API, the network or a real process: every
kernel32 entry is faked through the module's own `bind`, and the private
directory is an `ntpath` literal so the walk-up behaves identically on any host.
"""

import ctypes as c
import os
from types import SimpleNamespace

import pytest

from archeus.node import win32_mxc as w

PRIVATE = 'C:\\private\\home'
ROOTS = ['C:\\', 'C:\\private', PRIVATE]
STD = (101, 102, 103)


def _ok(*args):
    return 1


class Function:
    def __init__(self, name, callback):
        self.name, self.callback = name, callback
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.callback(*args)


class Api:
    """Every declared kernel32 entry faked, one argument ledger kept per name."""

    def __init__(self, monkeypatch, **callbacks):
        for name in callbacks:
            assert name in w.SIGNATURES, name
        self.errors = [0]
        monkeypatch.setattr(w.c, 'get_last_error', lambda: self.errors[0], raising=False)
        self.names = {name: Function(name, callbacks.get(name, _ok)) for name in w.SIGNATURES}
        self.api = object.__new__(w.Win32Api)
        self.api.functions = w.bind(SimpleNamespace(**self.names))

    def set(self, name, callback):
        self.names[name].callback = callback

    def args(self, name):
        return self.names[name].calls

    def called(self, name):
        return bool(self.names[name].calls)

    def closed(self):
        return [args[0] for args in self.args('CloseHandle')]


def policy_api(monkeypatch, attributes=0x10, **callbacks):
    """An api whose private directory is `PRIVATE`: three components, root first."""
    def create(path, *rest):
        opened.append(101 + len(opened))
        return opened[-1]

    def info(handle, info_class, tag, size):
        tag._obj.attributes = attributes
        return 1

    def write(handle, chunk, size, written, overlapped):
        written._obj.value = size
        return 1

    opened = []
    callbacks.setdefault('CreateFileW', create)
    callbacks.setdefault('GetFileInformationByHandleEx', info)
    callbacks.setdefault('WriteFile', write)
    fake = Api(monkeypatch, **callbacks)
    fake.api.private_directory = PRIVATE
    return fake


def attributes_of(handles):
    return w.Attributes(c.create_string_buffer(128), (w.HANDLE * len(handles))(*handles))


def launch_api(monkeypatch, handles=STD, **callbacks):
    fake = Api(monkeypatch, **callbacks)
    fake.attributes = attributes_of(handles)
    fake.std = handles
    return fake


def launch(fake, flags=0x80404, inherit_handles=True, std_handles=None):
    return fake.api.create_process_w(
        application='launcher.exe', command_line='launcher.exe policy.json', flags=flags,
        attributes=fake.attributes, inherit_handles=inherit_handles,
        std_handles=fake.std if std_handles is None else std_handles, cwd=PRIVATE, env={})


# -- module surface -----------------------------------------------------------


def test_private_directory_is_pinned_absolute(monkeypatch):
    kernel = SimpleNamespace(**{name: Function(name, _ok) for name in w.SIGNATURES})
    monkeypatch.setattr(w.sys, 'platform', 'win32')
    monkeypatch.setattr(w.c, 'WinDLL', lambda *args, **kwargs: kernel, raising=False)
    api = w.Win32Api('private-home')
    assert os.path.isabs(api.private_directory)
    assert api.private_directory == os.path.abspath('private-home')


# -- protected_policy: the directory chain ------------------------------------


def test_ancestors_are_verified_root_first_and_held(monkeypatch):
    fake = policy_api(monkeypatch)
    path, lease = fake.api.protected_policy(b'{}')
    assert [args[0] for args in fake.args('CreateFileW')] == ROOTS + [path]
    assert [args[0] for args in fake.args('GetFileInformationByHandleEx')] == [101, 102, 103]
    assert list(lease.directories) == [101, 102, 103]
    assert lease.file == 104
    assert not fake.called('CloseHandle')


def test_ancestor_open_uses_open_reparse_point_and_attribute_class(monkeypatch):
    fake = policy_api(monkeypatch)
    fake.api.protected_policy(b'{}')
    for args in fake.args('CreateFileW')[:len(ROOTS)]:
        assert args[1:] == (0x80, 1, None, 3, 0x02200000, None)
    assert [args[1] for args in fake.args('GetFileInformationByHandleEx')] == [9, 9, 9]
    assert {args[3] for args in fake.args('GetFileInformationByHandleEx')} == {
        c.sizeof(w.AttributeTag)}


@pytest.mark.parametrize('attributes', [0x400, 0x410], ids=['reparse', 'reparse+dir'])
def test_reparse_point_in_the_chain_is_refused(monkeypatch, attributes):
    fake = policy_api(monkeypatch, attributes=attributes)
    with pytest.raises(ValueError, match='must not contain reparse points'):
        fake.api.protected_policy(b'{}')
    assert len(fake.args('CreateFileW')) == 1
    assert not fake.called('WriteFile')
    assert fake.closed() == [101]


@pytest.mark.parametrize('attributes', [0x00, 0x80], ids=['none', 'archive'])
def test_non_directory_component_is_refused(monkeypatch, attributes):
    fake = policy_api(monkeypatch, attributes=attributes)
    with pytest.raises(ValueError, match='must not contain reparse points'):
        fake.api.protected_policy(b'{}')
    assert not fake.called('WriteFile')


def test_unopenable_ancestor_stops_before_the_policy_file(monkeypatch):
    def create(path, *rest):
        return w.INVALID_HANDLE if path == ROOTS[1] else 101

    fake = policy_api(monkeypatch, CreateFileW=create)
    fake.errors[0] = 32
    with pytest.raises(w.Win32Error, match='CreateFileW: 32'):
        fake.api.protected_policy(b'{}')
    assert [args[0] for args in fake.args('CreateFileW')] == ROOTS[:2]
    assert not fake.called('WriteFile')
    assert fake.closed() == [101]


def test_policy_file_is_created_write_once_and_read_shared(monkeypatch):
    fake = policy_api(monkeypatch)
    path, _ = fake.api.protected_policy(b'{}')
    handle_args = fake.args('CreateFileW')[len(ROOTS)]
    assert handle_args[1:] == (0x40000000, 1, None, 1, 0x00200080, None)
    assert path == handle_args[0]
    assert path.startswith(PRIVATE + '\\') and path.endswith('.json')
    assert '..' not in path


def test_whole_payload_is_written_in_bounded_chunks(monkeypatch):
    fake = policy_api(monkeypatch)
    fake.api.protected_policy(b'{}')
    assert fake.args('WriteFile')[-1][1:3] == (b'{}', 2)


def test_partial_writes_advance_by_what_the_api_reported(monkeypatch):
    def write(handle, chunk, size, written, overlapped):
        sizes.append(size)
        written._obj.value = min(3, size)
        return 1

    sizes = []
    data = bytes(range(256)) * 300
    fake = policy_api(monkeypatch, WriteFile=write)
    fake.api.protected_policy(data)
    assert all(size <= 65536 for size in sizes)
    assert b''.join(args[1][:min(3, args[2])] for args in fake.args('WriteFile')) == data


def test_write_that_reports_no_bytes_is_an_error_and_not_a_loop(monkeypatch):
    def write(handle, chunk, size, written, overlapped):
        calls.append(size)
        assert len(calls) <= 2, 'the write loop made no progress'
        written._obj.value = 0
        return 1

    calls = []
    fake = policy_api(monkeypatch, WriteFile=write)
    with pytest.raises(w.Win32Error, match='WriteFile: 29'):
        fake.api.protected_policy(b'{}')
    assert len(calls) == 1


def test_failed_policy_write_deletes_the_partial_file(monkeypatch):
    fake = policy_api(monkeypatch, WriteFile=lambda *args: 0)
    fake.errors[0] = 5
    with pytest.raises(w.Win32Error, match='WriteFile: 5'):
        fake.api.protected_policy(b'{}')
    path = fake.args('CreateFileW')[-1][0]
    assert [args[0] for args in fake.args('DeleteFileW')] == [path]
    assert fake.closed() == [104, 103, 102, 101]


def test_failed_ancestor_check_closes_only_what_it_held(monkeypatch):
    def info(handle, info_class, tag, size):
        seen.append(handle)
        tag._obj.attributes = 0x10 if handle == 101 else 0x400
        return 1

    seen = []
    fake = policy_api(monkeypatch, GetFileInformationByHandleEx=info)
    with pytest.raises(ValueError, match='must not contain reparse points'):
        fake.api.protected_policy(b'{}')
    assert seen == [101, 102]
    assert fake.closed() == [102, 101]


def test_remove_policy_closes_the_file_before_deleting_it(monkeypatch):
    events = []
    fake = Api(monkeypatch)
    fake.set('CloseHandle', lambda handle: events.append(('close', handle)) or 1)
    fake.set('DeleteFileW', lambda path: events.append(('delete', path)) or 1)
    fake.api.remove_policy('C:\\private\\home\\a.json', w.PolicyLease(201, [202, 203]))
    assert events == [('close', 201), ('delete', 'C:\\private\\home\\a.json'),
                      ('close', 203), ('close', 202)]


def test_remove_policy_frees_directories_when_the_delete_fails(monkeypatch):
    events = []
    fake = Api(monkeypatch)
    fake.set('CloseHandle', lambda handle: events.append(('close', handle)) or 1)
    fake.set('DeleteFileW', lambda path: 0)
    fake.errors[0] = 33
    with pytest.raises(w.Win32Error, match='DeleteFileW: 33'):
        fake.api.remove_policy('C:\\private\\home\\a.json', w.PolicyLease(201, [202, 203]))
    assert events == [('close', 201), ('close', 203), ('close', 202)]


# -- pipes --------------------------------------------------------------------


def test_pipe_buffer_and_security_attributes_are_inherited(monkeypatch):
    def create(read, write, security, size):
        read._obj.value, write._obj.value = 101, 102
        return 1

    fake = Api(monkeypatch, CreatePipe=create)
    assert fake.api.pipe(parent_reads=True) == (101, 102)
    assert fake.args('CreatePipe')[0][3] == 65536
    security = fake.args('CreatePipe')[0][2]._obj
    assert security.length == c.sizeof(w.SecurityAttributes)
    assert security.inherit == 1


def test_pipe_cleanup_closes_only_handles_that_exist(monkeypatch):
    def create(read, write, security, size):
        read._obj.value = 101
        return 1

    fake = Api(monkeypatch, CreatePipe=create, SetHandleInformation=lambda *args: 0)
    with pytest.raises(w.Win32Error, match='SetHandleInformation'):
        fake.api.pipe(parent_reads=True)
    assert fake.closed() == [101]


# -- the inherited-handle allowlist ------------------------------------------


@pytest.mark.parametrize('handles', [(), (101, 101)], ids=['empty', 'duplicate'])
def test_attribute_list_requires_distinct_handles(monkeypatch, handles):
    fake = Api(monkeypatch)
    with pytest.raises(ValueError, match='distinct inherited handles required'):
        fake.api.attribute_list(handles)
    assert not fake.called('InitializeProcThreadAttributeList')
    assert not fake.called('UpdateProcThreadAttribute')


def test_attribute_list_probe_must_fail_with_insufficient_buffer(monkeypatch):
    fake = Api(monkeypatch, InitializeProcThreadAttributeList=lambda *args: 1)
    fake.errors[0] = 122
    with pytest.raises(w.Win32Error, match='InitializeProcThreadAttributeList'):
        fake.api.attribute_list((101,))
    assert len(fake.args('InitializeProcThreadAttributeList')) == 1
    assert not fake.called('UpdateProcThreadAttribute')


def test_attribute_list_needs_the_right_probe_error(monkeypatch):
    fake = Api(monkeypatch, InitializeProcThreadAttributeList=lambda *args: 0)
    fake.errors[0] = 5
    with pytest.raises(w.Win32Error, match='InitializeProcThreadAttributeList: 5'):
        fake.api.attribute_list((101,))
    assert len(fake.args('InitializeProcThreadAttributeList')) == 1
    assert not fake.called('UpdateProcThreadAttribute')


def test_attribute_list_publishes_the_handle_list(monkeypatch):
    def initialize(buffer, count, flags, size):
        size._obj.value = 128
        return int(buffer is not None)

    fake = Api(monkeypatch, InitializeProcThreadAttributeList=initialize)
    fake.errors[0] = 122
    attributes = fake.api.attribute_list(STD)
    args = fake.args('UpdateProcThreadAttribute')[-1]
    assert args[1] == 0 and args[2] == 0x00020002
    assert tuple(args[3]) == STD
    assert args[4] == 3 * c.sizeof(w.HANDLE)
    assert args[5] is None and args[6] is None
    fake.api.delete_attribute_list(attributes)
    assert len(fake.args('DeleteProcThreadAttributeList')) == 1


def test_attribute_list_deletes_the_list_when_the_update_fails(monkeypatch):
    def initialize(buffer, count, flags, size):
        size._obj.value = 128
        return int(buffer is not None)

    fake = Api(monkeypatch, InitializeProcThreadAttributeList=initialize,
               UpdateProcThreadAttribute=lambda *args: 0)
    fake.errors[0] = 122
    with pytest.raises(w.Win32Error, match='UpdateProcThreadAttribute: 122'):
        fake.api.attribute_list((101, 102))
    assert len(fake.args('DeleteProcThreadAttributeList')) == 1


# -- creation -----------------------------------------------------------------


@pytest.mark.parametrize('case', ['no-inherit', 'reordered', 'subset', 'extra'])
def test_allowlist_must_equal_the_standard_handles(monkeypatch, case):
    fake = launch_api(monkeypatch)
    options = {'no-inherit': {'inherit_handles': False},
               'reordered': {'std_handles': (103, 102, 101)},
               'subset': {'std_handles': (101, 102)},
               'extra': {'std_handles': (101, 102, 103, 104)}}[case]
    with pytest.raises(ValueError, match='standard handles must equal inheritance list'):
        launch(fake, **options)
    assert not fake.called('CreateProcessW')


@pytest.mark.parametrize('flags', [0x80400, 0x404, 0x80004, 0, 0x80404 | 0x20],
                         ids=['no-suspend', 'no-extended', 'no-unicode-env', 'none', 'extra-flag'])
def test_creation_requires_exactly_suspended_extended_unicode(monkeypatch, flags):
    fake = launch_api(monkeypatch)
    with pytest.raises(ValueError, match='suspended extended Unicode creation required'):
        launch(fake, flags=flags)
    assert not fake.called('CreateProcessW')


def test_creation_wires_the_startup_info(monkeypatch):
    fake = launch_api(monkeypatch)
    launch(fake)
    args = fake.args('CreateProcessW')[-1]
    assert args[0] == 'launcher.exe' and args[4] is True and args[7] == PRIVATE
    assert args[6][:2] == '\0\0'
    startup = args[8]._obj
    assert startup.startup.cb == c.sizeof(w.StartupInfoEx)
    assert startup.startup.flags == 0x100
    assert (startup.startup.stdin, startup.startup.stdout,
            startup.startup.stderr) == STD
    assert startup.attributes == c.addressof(fake.attributes.buffer)


def test_creation_closes_a_partially_built_process(monkeypatch):
    def create(*args):
        args[-1]._obj.process = 201
        return 0

    fake = launch_api(monkeypatch, CreateProcessW=create)
    fake.errors[0] = 5
    with pytest.raises(w.Win32Error, match='CreateProcessW: 5'):
        launch(fake)
    assert fake.closed() == [201]


def test_creation_closes_the_thread_before_the_process(monkeypatch):
    def create(*args):
        info = args[-1]._obj
        info.process, info.thread = 201, 202
        return 0

    fake = launch_api(monkeypatch, CreateProcessW=create)
    fake.errors[0] = 5
    with pytest.raises(w.Win32Error, match='CreateProcessW: 5'):
        launch(fake)
    assert fake.closed() == [202, 201]


# -- the child's life ---------------------------------------------------------


def test_creation_time_reads_the_creation_slot(monkeypatch):
    def times(process, *slots):
        for index, slot in enumerate(slots):
            slot._obj.low, slot._obj.high = index + 1, index + 10
        return 1

    fake = Api(monkeypatch, GetProcessTimes=times)
    assert fake.api.creation_time(5) == 1 | (10 << 32)


def test_in_job_passes_process_first_and_returns_a_bool(monkeypatch):
    def query(process, job, result):
        result._obj.value = verdict.pop(0)
        return 1

    verdict = [1, 0]
    fake = Api(monkeypatch, IsProcessInJob=query)
    assert fake.api.in_job(6, 7) is True
    assert fake.api.in_job(6, 7) is False
    assert [args[:2] for args in fake.args('IsProcessInJob')] == [(7, 6), (7, 6)]


def test_resume_thread_refuses_the_invalid_handle_sentinel(monkeypatch):
    fake = Api(monkeypatch, ResumeThread=lambda *args: 0xffffffff)
    fake.errors[0] = 6
    with pytest.raises(w.Win32Error, match='ResumeThread: 6'):
        fake.api.resume_thread(3)


def test_resume_thread_returns_the_suspend_count(monkeypatch):
    fake = Api(monkeypatch, ResumeThread=lambda *args: 1)
    assert fake.api.resume_thread(3) == 1


def test_terminate_process_uses_exit_code_one(monkeypatch):
    fake = Api(monkeypatch)
    fake.api.terminate_process(9)
    assert fake.args('TerminateProcess') == [(9, 1)]


def test_terminate_process_reports_a_failure(monkeypatch):
    fake = Api(monkeypatch, TerminateProcess=lambda *args: 0)
    fake.errors[0] = 87
    with pytest.raises(w.Win32Error, match='TerminateProcess: 87'):
        fake.api.terminate_process(9)


# -- polling and pipe I/O -----------------------------------------------------


def test_poll_never_blocks(monkeypatch):
    fake = Api(monkeypatch, WaitForSingleObject=lambda *args: 258)
    assert fake.api.poll(4) is None
    assert fake.args('WaitForSingleObject') == [(4, 0)]
    assert not fake.called('GetExitCodeProcess')


def test_poll_returns_the_exit_code_when_signalled(monkeypatch):
    def code(process, out):
        out._obj.value = 7
        return 1

    fake = Api(monkeypatch, WaitForSingleObject=lambda *args: 0, GetExitCodeProcess=code)
    assert fake.api.poll(4) == 7
    assert fake.args('GetExitCodeProcess')[0][0] == 4


def test_poll_refuses_any_other_wait_status(monkeypatch):
    fake = Api(monkeypatch, WaitForSingleObject=lambda *args: 0x80)
    with pytest.raises(w.Win32Error) as caught:
        fake.api.poll(4)
    assert (caught.value.api, caught.value.code) == ('WaitForSingleObject', 0x80)
    assert not fake.called('GetExitCodeProcess')


def test_poll_reports_the_last_error_when_the_wait_failed(monkeypatch):
    fake = Api(monkeypatch, WaitForSingleObject=lambda *args: 0xffffffff)
    fake.errors[0] = 6
    with pytest.raises(w.Win32Error) as caught:
        fake.api.poll(4)
    assert (caught.value.api, caught.value.code) == ('WaitForSingleObject', 6)


@pytest.mark.parametrize('size', [-1, 0, 65537], ids=['negative', 'zero', 'over-64k'])
def test_read_refuses_sizes_outside_one_to_65536(monkeypatch, size):
    fake = Api(monkeypatch)
    with pytest.raises(ValueError, match='read size must be between 1 and 65536'):
        fake.api.read(1, size)
    assert not fake.called('PeekNamedPipe')


def test_read_accepts_the_full_buffer(monkeypatch):
    fake = Api(monkeypatch)
    assert fake.api.read(1, 65536) is None
    assert fake.args('PeekNamedPipe')[-1][:3] == (1, None, 0)


def test_read_reports_eof_only_for_a_broken_pipe(monkeypatch):
    fake = Api(monkeypatch, PeekNamedPipe=lambda *args: 0)
    fake.errors[0] = 109
    assert fake.api.read(1, 8) == b''
    fake.errors[0] = 5
    with pytest.raises(w.Win32Error, match='PeekNamedPipe: 5'):
        fake.api.read(1, 8)
    assert not fake.called('ReadFile')


def test_read_maps_read_failures(monkeypatch):
    def peek(handle, buffer, size, count, available, left):
        available._obj.value = 6
        return 1

    fake = Api(monkeypatch, PeekNamedPipe=peek, ReadFile=lambda *args: 0)
    fake.errors[0] = 109
    assert fake.api.read(1, 8) == b''
    fake.errors[0] = 232
    assert fake.api.read(1, 8) is None
    fake.errors[0] = 5
    with pytest.raises(w.Win32Error, match='ReadFile: 5'):
        fake.api.read(1, 8)


def test_read_returns_only_the_bytes_the_api_reports(monkeypatch):
    def peek(handle, buffer, size, count, available, left):
        available._obj.value = 6
        return 1

    def read(handle, buffer, size, count, overlapped):
        c.memmove(buffer, b'abcdef', size)
        count._obj.value = 2
        return 1

    fake = Api(monkeypatch, PeekNamedPipe=peek, ReadFile=read)
    assert fake.api.read(1, 6) == b'ab'


def test_read_bounds_the_buffer_by_size_and_available(monkeypatch):
    source = b'0123456789abcdefghij'

    def peek(handle, buffer, size, count, available, left):
        available._obj.value = 20
        return 1

    def read(handle, buffer, size, count, overlapped):
        c.memmove(buffer, source, size)
        count._obj.value = size
        return 1

    fake = Api(monkeypatch, PeekNamedPipe=peek, ReadFile=read)
    assert fake.api.read(1, 4) == b'0123'
    assert fake.args('ReadFile')[-1][2] == 4
    assert fake.api.read(1, 40) == source
    assert fake.args('ReadFile')[-1][2] == 20


def test_write_sends_exactly_the_payload_it_was_given(monkeypatch):
    def write(handle, buffer, size, count, overlapped):
        count._obj.value = size
        return 1

    fake = Api(monkeypatch, WriteFile=write)
    assert fake.api.write(1, b'abc') == 3
    assert fake.args('WriteFile')[-1][:3] == (1, b'abc', 3)
    assert fake.api.write(1, b'x' * 100000) == 65536
    tail = fake.args('WriteFile')[-1]
    assert tail[2] == 65536 and len(tail[1]) == 65536 and tail[1] == b'x' * 65536


def test_write_reports_zero_only_for_a_closed_pipe(monkeypatch):
    fake = Api(monkeypatch, WriteFile=lambda *args: 0)
    fake.errors[0] = 232
    assert fake.api.write(1, b'abc') == 0
    fake.errors[0] = 5
    with pytest.raises(w.Win32Error, match='WriteFile: 5'):
        fake.api.write(1, b'abc')
