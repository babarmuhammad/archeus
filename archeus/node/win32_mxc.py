import ctypes as c
import ntpath
import os
import sys
import uuid
from dataclasses import dataclass


DWORD = c.c_uint32
BOOL = c.c_int32
HANDLE = c.c_void_p
PTR = c.c_void_p
SIZE = c.c_size_t
PDWORD = c.POINTER(DWORD)
INVALID_HANDLE = c.c_void_p(-1).value


class SecurityAttributes(c.Structure):
    _fields_ = [('length', DWORD), ('descriptor', PTR), ('inherit', BOOL)]


class StartupInfo(c.Structure):
    _fields_ = [('cb', DWORD), ('reserved', c.c_wchar_p), ('desktop', c.c_wchar_p),
                ('title', c.c_wchar_p), ('x', DWORD), ('y', DWORD), ('xsize', DWORD),
                ('ysize', DWORD), ('xchars', DWORD), ('ychars', DWORD), ('fill', DWORD),
                ('flags', DWORD), ('show', c.c_uint16), ('reserved_size', c.c_uint16),
                ('reserved_bytes', PTR), ('stdin', HANDLE), ('stdout', HANDLE),
                ('stderr', HANDLE)]


class StartupInfoEx(c.Structure):
    _fields_ = [('startup', StartupInfo), ('attributes', PTR)]


class ProcessInformation(c.Structure):
    _fields_ = [('process', HANDLE), ('thread', HANDLE), ('pid', DWORD), ('tid', DWORD)]


class FileTime(c.Structure):
    _fields_ = [('low', DWORD), ('high', DWORD)]


class AttributeTag(c.Structure):
    _fields_ = [('attributes', DWORD), ('tag', DWORD)]


SIGNATURES = {
    'CreateFileW': ([c.c_wchar_p, DWORD, DWORD, PTR, DWORD, DWORD, HANDLE], HANDLE),
    'GetFileInformationByHandleEx': ([HANDLE, c.c_int, PTR, DWORD], BOOL),
    'DeleteFileW': ([c.c_wchar_p], BOOL),
    'CreatePipe': ([c.POINTER(HANDLE), c.POINTER(HANDLE),
                    c.POINTER(SecurityAttributes), DWORD], BOOL),
    'SetHandleInformation': ([HANDLE, DWORD, DWORD], BOOL),
    'GetHandleInformation': ([HANDLE, PDWORD], BOOL),
    'SetNamedPipeHandleState': ([HANDLE, PDWORD, PDWORD, PDWORD], BOOL),
    'PeekNamedPipe': ([HANDLE, PTR, DWORD, PDWORD, PDWORD, PDWORD], BOOL),
    'ReadFile': ([HANDLE, PTR, DWORD, PDWORD, PTR], BOOL),
    'WriteFile': ([HANDLE, PTR, DWORD, PDWORD, PTR], BOOL),
    'InitializeProcThreadAttributeList': ([PTR, DWORD, DWORD, c.POINTER(SIZE)], BOOL),
    'UpdateProcThreadAttribute': ([PTR, DWORD, SIZE, PTR, SIZE, PTR, PTR], BOOL),
    'DeleteProcThreadAttributeList': ([PTR], None),
    'CreateProcessW': ([c.c_wchar_p, c.c_wchar_p, PTR, PTR, BOOL, DWORD, PTR,
                        c.c_wchar_p, c.POINTER(StartupInfoEx),
                        c.POINTER(ProcessInformation)], BOOL),
    'GetProcessTimes': ([HANDLE, c.POINTER(FileTime), c.POINTER(FileTime),
                         c.POINTER(FileTime), c.POINTER(FileTime)], BOOL),
    'IsProcessInJob': ([HANDLE, HANDLE, c.POINTER(BOOL)], BOOL),
    'ResumeThread': ([HANDLE], DWORD),
    'TerminateProcess': ([HANDLE, DWORD], BOOL),
    'CloseHandle': ([HANDLE], BOOL),
    'GetExitCodeProcess': ([HANDLE, PDWORD], BOOL),
    'WaitForSingleObject': ([HANDLE, DWORD], DWORD),
}


class Win32Error(Exception):
    def __init__(self, api, code):
        self.api, self.code = api, code
        super().__init__(f'{api}: {code}')


@dataclass
class Attributes:
    buffer: object
    handles: object


@dataclass
class PolicyLease:
    file: object
    directories: list


def bind(kernel):
    functions = {}
    for name, (args, result) in SIGNATURES.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
        functions[name] = function
    return functions


def environment_block(env):
    entries = []
    for key, value in sorted(env.items(), key=lambda item: item[0].upper()):
        if not key or '=' in key or '\0' in key or '\0' in value:
            raise ValueError('invalid environment entry')
        entries.append(f'{key}={value}')
    return c.create_unicode_buffer('\0'.join(entries) + '\0\0')


class Win32Api:
    def __init__(self, private_directory):
        if sys.platform != 'win32':
            raise RuntimeError('Win32Api requires Windows')
        self.functions = bind(c.WinDLL('kernel32', use_last_error=True))
        self.private_directory = os.path.abspath(os.fspath(private_directory))

    def _error(self, name):
        return Win32Error(name, c.get_last_error())

    def _call(self, name, *args):
        result = self.functions[name](*args)
        if not result:
            raise self._error(name)
        return result

    def protected_policy(self, data: bytes) -> tuple[str, object]:
        directories, handle = [], None
        path = ntpath.join(self.private_directory, uuid.uuid4().hex + '.json')
        try:
            parts = []
            directory = self.private_directory
            while True:
                parts.append(directory)
                parent = ntpath.dirname(directory)
                if parent == directory:
                    break
                directory = parent
            for directory in reversed(parts):
                held = self.functions['CreateFileW'](
                    directory, 0x80, 1, None, 3, 0x02200000, None)
                if held == INVALID_HANDLE:
                    raise self._error('CreateFileW')
                directories.append(held)
                tag = AttributeTag()
                self._call('GetFileInformationByHandleEx', held, 9, c.byref(tag), c.sizeof(tag))
                if tag.attributes & 0x400 or not tag.attributes & 0x10:
                    raise ValueError('policy directory must not contain reparse points')
            handle = self.functions['CreateFileW'](path, 0x40000000, 1, None, 1, 0x00200080,
                                                   None)
            if handle == INVALID_HANDLE:
                handle = None
                raise self._error('CreateFileW')
            offset = 0
            while offset < len(data):
                chunk = data[offset:offset + 65536]
                written = DWORD()
                self._call('WriteFile', handle, chunk, len(chunk), c.byref(written), None)
                if not written.value:
                    raise Win32Error('WriteFile', 29)
                offset += written.value
            return path, PolicyLease(handle, directories)
        except BaseException:
            if handle is not None:
                self.close_handle(handle)
                self._call('DeleteFileW', path)
            raise
        finally:
            if sys.exc_info()[0] is not None:
                for held in reversed(directories):
                    self.close_handle(held)

    def remove_policy(self, path, handle):
        try:
            self.close_handle(handle.file)
            self._call('DeleteFileW', path)
        finally:
            for directory in reversed(handle.directories):
                self.close_handle(directory)

    def pipe(self, *, parent_reads: bool) -> tuple[object, object]:
        read, write = HANDLE(), HANDLE()
        security = SecurityAttributes(c.sizeof(SecurityAttributes), None, True)
        try:
            self._call('CreatePipe', c.byref(read), c.byref(write), c.byref(security), 65536)
            parent, child = ((read.value, write.value) if parent_reads
                             else (write.value, read.value))
            self._call('SetHandleInformation', parent, 1, 0)
            mode = DWORD(1)
            self._call('SetNamedPipeHandleState', parent, c.byref(mode), None, None)
            return parent, child
        except BaseException:
            for handle in (read.value, write.value):
                if handle:
                    self.close_handle(handle)
            raise

    def attribute_list(self, handles: tuple) -> object:
        if not handles or len(set(handles)) != len(handles):
            raise ValueError('distinct inherited handles required')
        size = SIZE()
        result = self.functions['InitializeProcThreadAttributeList'](None, 1, 0, c.byref(size))
        if result or c.get_last_error() != 122:
            raise self._error('InitializeProcThreadAttributeList')
        buffer = c.create_string_buffer(size.value)
        self._call('InitializeProcThreadAttributeList', buffer, 1, 0, c.byref(size))
        values = (HANDLE * len(handles))(*handles)
        try:
            self._call('UpdateProcThreadAttribute', buffer, 0, 0x00020002,
                       values, c.sizeof(values), None, None)
        except BaseException:
            self.functions['DeleteProcThreadAttributeList'](buffer)
            raise
        return Attributes(buffer, values)

    def delete_attribute_list(self, attributes):
        self.functions['DeleteProcThreadAttributeList'](attributes.buffer)

    def create_process_w(self, *, application, command_line, flags, attributes,
                         inherit_handles, std_handles, cwd, env) -> tuple:
        if not inherit_handles or tuple(attributes.handles) != tuple(std_handles):
            raise ValueError('standard handles must equal inheritance list')
        if flags & 0x80404 != 0x80404:
            raise ValueError('suspended extended Unicode creation required')
        startup = StartupInfoEx()
        startup.startup.cb = c.sizeof(startup)
        startup.startup.flags = 0x100
        startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = std_handles
        startup.attributes = c.cast(attributes.buffer, PTR)
        command = c.create_unicode_buffer(command_line)
        environment = environment_block(env)
        info = ProcessInformation()
        try:
            self._call('CreateProcessW', application, command, None, None, True,
                       flags, environment, cwd, c.byref(startup), c.byref(info))
        except BaseException:
            for handle in (info.thread, info.process):
                if handle:
                    self.close_handle(handle)
            raise
        return info.process, info.thread, info.pid

    def creation_time(self, process) -> int:
        times = [FileTime() for _ in range(4)]
        self._call('GetProcessTimes', process, *(c.byref(value) for value in times))
        return times[0].low | times[0].high << 32

    def in_job(self, job, process) -> bool:
        result = BOOL()
        self._call('IsProcessInJob', process, job, c.byref(result))
        return bool(result.value)

    def resume_thread(self, thread) -> int:
        result = self.functions['ResumeThread'](thread)
        if result == 0xffffffff:
            raise self._error('ResumeThread')
        return result

    def terminate_process(self, process):
        self._call('TerminateProcess', process, 1)

    def close_handle(self, handle):
        self._call('CloseHandle', handle)

    def poll(self, process) -> int | None:
        status = self.functions['WaitForSingleObject'](process, 0)
        if status == 0xffffffff:
            raise self._error('WaitForSingleObject')
        if status == 258:
            return None
        if status != 0:
            raise Win32Error('WaitForSingleObject', status)
        code = DWORD()
        self._call('GetExitCodeProcess', process, c.byref(code))
        return code.value

    def read(self, handle, size: int) -> bytes | None:
        if not 0 < size <= 65536:
            raise ValueError('read size must be between 1 and 65536')
        available = DWORD()
        if not self.functions['PeekNamedPipe'](handle, None, 0, None, c.byref(available), None):
            if c.get_last_error() == 109:
                return b''
            raise self._error('PeekNamedPipe')
        if not available.value:
            return None
        # Peek bounds reads; PIPE_NOWAIT also prevents blocking if another reader races us.
        buffer = c.create_string_buffer(min(size, available.value))
        count = DWORD()
        if not self.functions['ReadFile'](handle, buffer, len(buffer), c.byref(count), None):
            code = c.get_last_error()
            if code == 109:
                return b''
            if code == 232:
                return None
            raise Win32Error('ReadFile', code)
        return buffer.raw[:count.value]

    def write(self, handle, data: bytes) -> int:
        count = DWORD()
        # PIPE_NOWAIT writes only available capacity, returning zero when the pipe is full.
        if not self.functions['WriteFile'](handle, data[:65536], min(len(data), 65536),
                                           c.byref(count), None):
            if c.get_last_error() == 232:
                return 0
            raise self._error('WriteFile')
        return count.value
