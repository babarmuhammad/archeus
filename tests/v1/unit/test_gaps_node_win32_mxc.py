"""T-717: the fail-closed branches of archeus/node/win32_mxc.py left untested.

Every OS call goes through the same settable-kernel32 seam the existing tests
use (Function / fake_api in test_win32_mxc.py), so no real handle, file, pipe or
process is touched and this file runs identically on Linux and on Windows.
"""

import ctypes as c
from types import SimpleNamespace

import pytest

from archeus.node import win32_mxc as w

PRIVATE = 'C:\\private'
ROOT = 'C:\\'
DIRECTORY_ACCESS = 0x80
FILE_ACCESS = 0x40000000
DIRECTORY_ATTRIBUTES = 0x10
REPARSE_ATTRIBUTES = 0x400
FILE_ATTRIBUTES = 0x80
BACKUP_SEMANTICS = 0x02000000
OPEN_REPARSE_POINT = 0x00200000
OPEN_TARGET_DIRECTORY = 0x80
HEX = set('0123456789abcdef')


class Function:
    def __init__(self, callback=lambda *args: 1):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


def fake_api(monkeypatch):
    """Win32Api over a kernel32 of settable callables; errors[0] is the faked last error."""
    errors = [122]
    monkeypatch.setattr(c, 'get_last_error', lambda: errors[0], raising=False)
    kernel = SimpleNamespace(**{name: Function() for name in w.SIGNATURES})
    api = object.__new__(w.Win32Api)
    api.functions = w.bind(kernel)
    api.errors = errors
    return api


def policy_api(monkeypatch):
    """fake_api shaped for protected_policy, with a ledger of every open, query, write, close."""
    api = fake_api(monkeypatch)
    api.private_directory = PRIVATE
    api.names, api.events = {}, []
    api.opened, api.closed, api.deleted = [], [], []
    api.attributes, api.refused, api.refused_query = {}, set(), set()
    api.writes, api.written, api.accepted = [], [], []
    api.next = [900]

    def create_file(path, access, share, security, disposition, flags, template):
        api.events.append(('open', path))
        api.opened.append((path, access, share, disposition, flags))
        kind = 'directory' if access == DIRECTORY_ACCESS else 'file'
        if kind in api.refused or path in api.refused:
            return w.INVALID_HANDLE
        api.next[0] += 1
        api.names[api.next[0]] = path
        return api.next[0]

    def information(handle, level, tag, size):
        api.events.append(('query', handle))
        if handle in api.refused_query:
            return 0
        tag._obj.attributes = api.attributes.get(api.names[handle], DIRECTORY_ATTRIBUTES)
        return 1

    def write(handle, chunk, size, written, overlapped):
        if len(api.writes) >= 8:
            raise AssertionError('WriteFile kept being called without finishing')
        api.writes.append(chunk)
        size = api.written.pop(0) if api.written else size
        api.accepted.append(size)
        written._obj.value = size
        return 1

    def delete(path):
        api.deleted.append(path)
        return 0 if path in api.refused else 1

    api.functions['CreateFileW'].callback = create_file
    api.functions['GetFileInformationByHandleEx'].callback = information
    api.functions['WriteFile'].callback = write
    api.functions['CloseHandle'].callback = lambda handle: api.closed.append(handle) or 1
    api.functions['DeleteFileW'].callback = delete
    return api


def paths(api):
    return [entry[0] for entry in api.opened]


def attributes(*handles):
    return w.Attributes(c.create_string_buffer(64), (w.HANDLE * len(handles))(*handles))


def create(api, callback):
    api.functions['CreateProcessW'].callback = callback
    return api


# -- protected_policy: the directory lease and its denial paths --------------


def test_directory_lease_is_taken_root_first_and_kept_open_on_success(monkeypatch):
    api = policy_api(monkeypatch)
    path, lease = api.protected_policy(b'{}')
    assert api.events == [('open', ROOT), ('query', 901),
                          ('open', PRIVATE), ('query', 902), ('open', path)]
    assert lease.directories == [901, 902]
    assert lease.file == 903
    assert api.closed == [] and api.deleted == []


def test_reparse_point_in_the_chain_refuses_the_whole_lease(monkeypatch):
    api = policy_api(monkeypatch)
    api.attributes[PRIVATE] = DIRECTORY_ATTRIBUTES | REPARSE_ATTRIBUTES
    with pytest.raises(ValueError, match='must not contain reparse points'):
        api.protected_policy(b'{}')
    assert paths(api) == [ROOT, PRIVATE]
    assert api.closed == [902, 901]
    assert api.deleted == []


@pytest.mark.parametrize('tag', [DIRECTORY_ATTRIBUTES | REPARSE_ATTRIBUTES,
                                 FILE_ATTRIBUTES,
                                 FILE_ATTRIBUTES | REPARSE_ATTRIBUTES],
                         ids=['junction', 'plain-file', 'reparse-file'])
def test_a_component_that_is_not_a_real_directory_is_refused(monkeypatch, tag):
    api = policy_api(monkeypatch)
    api.attributes[ROOT] = tag
    with pytest.raises(ValueError, match='must not contain reparse points'):
        api.protected_policy(b'{}')
    assert paths(api) == [ROOT]
    assert api.closed == [901]
    assert api.deleted == []


def test_an_unverifiable_component_fails_closed_without_a_policy_file(monkeypatch):
    api = policy_api(monkeypatch)
    api.refused_query.add(901)
    api.errors[0] = 5
    with pytest.raises(w.Win32Error, match='GetFileInformationByHandleEx: 5'):
        api.protected_policy(b'{}')
    assert paths(api) == [ROOT]
    assert api.closed == [901] and api.deleted == []


def test_a_refused_component_open_closes_the_lease_held_so_far(monkeypatch):
    api = policy_api(monkeypatch)
    api.refused.add(PRIVATE)
    api.errors[0] = 5
    with pytest.raises(w.Win32Error, match='CreateFileW: 5'):
        api.protected_policy(b'{}')
    assert paths(api) == [ROOT, PRIVATE]
    assert api.closed == [901] and api.deleted == []


def test_a_refused_file_open_never_touches_a_file_it_never_held(monkeypatch):
    api = policy_api(monkeypatch)
    api.refused.add('file')
    api.errors[0] = 5
    with pytest.raises(w.Win32Error, match='CreateFileW: 5'):
        api.protected_policy(b'{}')
    assert len(api.opened) == 3
    assert api.closed == [902, 901]
    assert w.INVALID_HANDLE not in api.closed
    assert api.deleted == []


def test_a_write_that_accepts_nothing_fails_closed_and_removes_the_file(monkeypatch):
    api = policy_api(monkeypatch)
    api.written = [0]
    with pytest.raises(w.Win32Error) as caught:
        api.protected_policy(b'{}')
    assert (caught.value.api, caught.value.code) == ('WriteFile', 29)
    assert len(api.writes) == 1, 'the zero-byte guard did not stop the loop'
    assert api.deleted == [paths(api)[-1]]
    assert api.closed == [903, 902, 901]


def test_a_short_write_continues_where_the_kernel_stopped(monkeypatch):
    api = policy_api(monkeypatch)
    data = bytes(range(256)) * 400
    api.written = [40000, 40000, 22400]
    path, lease = api.protected_policy(data)
    assert [len(chunk) for chunk in api.writes] == [65536, 62400, 22400]
    assert b''.join(chunk[:size] for chunk, size in zip(api.writes, api.accepted)) == data
    assert sum(api.accepted) == len(data)
    assert api.deleted == [] and api.closed == [] and lease.file == 903
    assert path.startswith(PRIVATE + '\\')


def test_policy_opens_never_follow_a_link_and_never_clobber(monkeypatch):
    api = policy_api(monkeypatch)
    path, _ = api.protected_policy(b'{}')
    for entry in api.opened[:2]:
        assert entry[1:] == (DIRECTORY_ACCESS, 1, 3, BACKUP_SEMANTICS | OPEN_REPARSE_POINT)
    assert api.opened[2][1:] == (FILE_ACCESS, 1, 1, OPEN_REPARSE_POINT | OPEN_TARGET_DIRECTORY)
    name = path[len(PRIVATE) + 1:]
    assert name.endswith('.json') and set(name[:-5]) <= HEX


# -- remove_policy: the lease must always come back --------------------------


def test_a_refused_delete_still_gives_back_every_leased_handle(monkeypatch):
    api = policy_api(monkeypatch)
    path, lease = api.protected_policy(b'{}')
    api.closed, api.deleted, api.refused = [], [], {path}
    api.errors[0] = 2
    with pytest.raises(w.Win32Error, match='DeleteFileW: 2'):
        api.remove_policy(path, lease)
    assert api.deleted == [path]
    assert api.closed == [903, 902, 901]


def test_remove_policy_gives_back_the_lease_once_and_deletes_the_file(monkeypatch):
    api = policy_api(monkeypatch)
    path, lease = api.protected_policy(b'{}')
    api.closed, api.deleted = [], []
    api.remove_policy(path, lease)
    assert api.deleted == [path]
    assert api.closed == [903, 902, 901]


# -- pipe: a pipe that cannot be made non-blocking must not be handed out -----


@pytest.mark.parametrize('stage', ['SetHandleInformation', 'SetNamedPipeHandleState'],
                         ids=['clear-inherit', 'nowait-mode'])
def test_a_pipe_that_cannot_be_configured_is_closed_and_refused(monkeypatch, stage):
    api = fake_api(monkeypatch)
    closed = []

    def create(read, write, security, size):
        assert security._obj.inherit == 1 and size == 65536
        read._obj.value, write._obj.value = 101, 102
        return 1

    api.functions['CreatePipe'].callback = create
    api.functions[stage].callback = lambda *args: 0
    api.functions['CloseHandle'].callback = lambda handle: closed.append(handle) or 1
    api.errors[0] = 5
    with pytest.raises(w.Win32Error, match=stage + ': 5'):
        api.pipe(parent_reads=True)
    assert closed == [101, 102]


def test_pipe_cleanup_skips_a_handle_the_kernel_never_gave(monkeypatch):
    api = fake_api(monkeypatch)
    closed = []

    def create(read, write, security, size):
        read._obj.value = 101
        return 1

    api.functions['CreatePipe'].callback = create
    api.functions['SetHandleInformation'].callback = lambda *args: 0
    api.functions['CloseHandle'].callback = lambda handle: closed.append(handle) or 1
    with pytest.raises(w.Win32Error, match='SetHandleInformation'):
        api.pipe(parent_reads=False)
    assert closed == [101]


# -- attribute_list: the inheritance allowlist --------------------------------


@pytest.mark.parametrize('handles', [(), (7, 7), (7, 7, 8)],
                         ids=['empty', 'duplicate', 'duplicate-plus'])
def test_the_inheritance_allowlist_must_be_nonempty_and_distinct(monkeypatch, handles):
    api = fake_api(monkeypatch)
    calls = []
    api.functions['InitializeProcThreadAttributeList'].callback = (
        lambda *args: calls.append(args) or 0)
    api.functions['UpdateProcThreadAttribute'].callback = lambda *args: calls.append(args) or 1
    with pytest.raises(ValueError, match='distinct inherited handles required'):
        api.attribute_list(handles)
    assert calls == []


@pytest.mark.parametrize('outcome', ['succeeded', 'other-error'],
                         ids=['probe-succeeds', 'probe-other-error'])
def test_the_attribute_list_size_probe_fails_closed(monkeypatch, outcome):
    api = fake_api(monkeypatch)
    api.errors[0] = 5 if outcome == 'other-error' else 122
    updated = []

    def initialize(buffer, count, flags, size):
        if buffer is not None:                       # the real call, never reached
            return 1
        if outcome == 'succeeded':                   # a sizing probe must never succeed
            return 1
        size._obj.value = 40                         # ERROR_MORE_DATA with a lying code
        return 0

    api.functions['InitializeProcThreadAttributeList'].callback = initialize
    api.functions['UpdateProcThreadAttribute'].callback = lambda *args: updated.append(1) or 1
    with pytest.raises(w.Win32Error, match='InitializeProcThreadAttributeList'):
        api.attribute_list((101, 102))
    assert updated == []


def test_the_attribute_list_buffer_is_the_size_the_kernel_asked_for(monkeypatch):
    api = fake_api(monkeypatch)
    seen = []

    def initialize(buffer, count, flags, size):
        if buffer is None:
            size._obj.value = 40
            return 0
        seen.append(len(buffer))
        return 1

    updated = []
    api.functions['InitializeProcThreadAttributeList'].callback = initialize
    api.functions['UpdateProcThreadAttribute'].callback = (
        lambda buffer, *args: updated.append(buffer) or 1)
    held = api.attribute_list((101, 102))
    assert seen == [40]
    assert updated == [held.buffer]
    assert tuple(held.handles) == (101, 102)


# -- create_process_w: the creation contract ---------------------------------


@pytest.mark.parametrize('flags', [0x80400, 0x00404, 0x80004, 0],
                         ids=['not-suspended', 'not-extended', 'not-unicode', 'no-flags'])
def test_a_child_that_is_not_suspended_extended_and_unicode_is_refused(monkeypatch, flags):
    api = fake_api(monkeypatch)
    started = []
    create(api, lambda *args: started.append(args) or 1)
    held = attributes(101, 102, 103)
    with pytest.raises(ValueError, match='suspended extended Unicode creation required'):
        api.create_process_w(application='cmd.exe', command_line='cmd /c exit 7', flags=flags,
                             attributes=held, inherit_handles=True,
                             std_handles=(101, 102, 103), cwd=PRIVATE, env={})
    assert started == []


@pytest.mark.parametrize('held,stdio,inherits',
                         [((101, 102, 103), (101, 102, 103), False),
                          ((101, 102, 103), (101, 102, 999), True),
                          ((101, 102, 103), (103, 102, 101), True),
                          ((101, 101, 102), (101, 102, 102), True),
                          ((101, 102, 103), (101, 102), True)],
                         ids=['no-inherit', 'foreign-handle', 'reordered', 'same-set', 'short'])
def test_creation_refuses_stdio_outside_the_exact_inheritance_allowlist(monkeypatch, held,
                                                                        stdio, inherits):
    api = fake_api(monkeypatch)
    started = []
    create(api, lambda *args: started.append(args) or 1)
    with pytest.raises(ValueError, match='standard handles must equal inheritance list'):
        api.create_process_w(application='cmd.exe', command_line='cmd /c exit 7',
                             flags=0x80404, attributes=attributes(*held),
                             inherit_handles=inherits, std_handles=stdio, cwd=PRIVATE, env={})
    assert started == []


@pytest.mark.parametrize('filled,wanted', [({'process'}, [201]), ({'thread'}, [202]),
                                            (set(), []), ({'process', 'thread'}, [202, 201])],
                         ids=['process-only', 'thread-only', 'nothing', 'both'])
def test_a_failed_creation_closes_only_what_the_kernel_filled(monkeypatch, filled, wanted):
    api = fake_api(monkeypatch)
    closed = []
    api.functions['CloseHandle'].callback = lambda handle: closed.append(handle) or 1

    def create_process(*args):
        info = args[-1]._obj
        if 'process' in filled:
            info.process = 201
        if 'thread' in filled:
            info.thread = 202
        return 0

    api.errors[0] = 5
    create(api, create_process)
    with pytest.raises(w.Win32Error, match='CreateProcessW: 5'):
        api.create_process_w(application='cmd.exe', command_line='cmd /c exit 7',
                             flags=0x80404, attributes=attributes(101, 102, 103),
                             inherit_handles=True, std_handles=(101, 102, 103),
                             cwd=PRIVATE, env={})
    assert closed == wanted


# -- process control: no optimistic answers ----------------------------------


def test_a_failed_resume_is_not_reported_as_a_resume_count(monkeypatch):
    api = fake_api(monkeypatch)
    api.functions['ResumeThread'].callback = lambda thread: 0xffffffff
    api.errors[0] = 5
    with pytest.raises(w.Win32Error, match='ResumeThread: 5'):
        api.resume_thread(202)
    api.functions['ResumeThread'].callback = lambda thread: 1
    assert api.resume_thread(202) == 1


def test_job_membership_answers_the_kernel_and_not_the_hope(monkeypatch):
    api = fake_api(monkeypatch)
    asked = []

    def reply(value):
        def call(process, job, result):
            asked.append((process, job))
            result._obj.value = value
            return 1
        return call

    api.functions['IsProcessInJob'].callback = reply(0)
    assert api.in_job(300, 201) is False
    assert asked == [(201, 300)]                    # (process, job), never the other way round
    api.functions['IsProcessInJob'].callback = reply(1)
    assert api.in_job(300, 201) is True
    api.errors[0] = 87
    api.functions['IsProcessInJob'].callback = lambda process, job, result: 0
    api.errors[0] = 87
    with pytest.raises(w.Win32Error, match='IsProcessInJob: 87'):
        api.in_job(300, 201)


def test_a_refused_termination_is_never_a_quiet_success(monkeypatch):
    api = fake_api(monkeypatch)
    asked = []
    api.functions['TerminateProcess'].callback = (
        lambda process, code: asked.append((process, code)) or 0)
    api.errors[0] = 5
    with pytest.raises(w.Win32Error, match='TerminateProcess: 5'):
        api.terminate_process(201)
    assert asked == [(201, 1)]


def test_creation_time_keeps_both_halves_of_the_creation_stamp(monkeypatch):
    api = fake_api(monkeypatch)
    given = []

    def times(process, *outs):
        given.append(process)
        for index, out in enumerate(outs):        # creation, exit, kernel, user
            out._obj.low, out._obj.high = 0x1000 * index + 0x11, 0x1000 * index + 0x22
        return 1

    api.functions['GetProcessTimes'].callback = times
    assert api.creation_time(201) == 0x2200000011
    assert given == [201]
    api.functions['GetProcessTimes'].callback = lambda *args: 0
    api.errors[0] = 6
    with pytest.raises(w.Win32Error, match='GetProcessTimes: 6'):
        api.creation_time(201)


@pytest.mark.parametrize('status', [125, 126, 0x1000], ids=['abandoned', 'abandoned-0', 'unknown'])
def test_poll_never_invents_an_exit_code_from_an_unknown_wait(monkeypatch, status):
    api = fake_api(monkeypatch)
    asked = []
    api.functions['WaitForSingleObject'].callback = lambda *args: status
    api.functions['GetExitCodeProcess'].callback = lambda *args: asked.append(args) or 1
    with pytest.raises(w.Win32Error) as caught:
        api.poll(201)
    assert (caught.value.api, caught.value.code) == ('WaitForSingleObject', status)
    assert asked == []


def test_a_failed_wait_is_reported_instead_of_a_spurious_exit(monkeypatch):
    api = fake_api(monkeypatch)
    asked = []
    api.functions['WaitForSingleObject'].callback = lambda *args: 0xffffffff
    api.functions['GetExitCodeProcess'].callback = lambda *args: asked.append(args) or 1
    api.errors[0] = 6
    with pytest.raises(w.Win32Error, match='WaitForSingleObject: 6'):
        api.poll(201)
    assert asked == []


# -- pipe I/O: only the two documented soft failures are soft -----------------


@pytest.mark.parametrize('size', [0, -1, 65537, 1 << 40],
                         ids=['zero', 'negative', 'over-max', 'huge'])
def test_read_refuses_a_size_outside_the_pipe_contract(monkeypatch, size):
    api = fake_api(monkeypatch)
    asked = []
    api.functions['PeekNamedPipe'].callback = lambda *args: asked.append(args) or 1
    with pytest.raises(ValueError, match='read size must be between 1 and 65536'):
        api.read(1, size)
    assert asked == []


@pytest.mark.parametrize('code', [5, 232, 0], ids=['access', 'busy', 'false-zero'])
def test_a_peek_failure_that_is_not_eof_is_never_eof(monkeypatch, code):
    api = fake_api(monkeypatch)
    api.errors[0] = code
    api.functions['PeekNamedPipe'].callback = lambda *args: 0
    with pytest.raises(w.Win32Error) as caught:
        api.read(1, 4096)
    assert (caught.value.api, caught.value.code) == ('PeekNamedPipe', code)


@pytest.mark.parametrize('code,wanted', [(109, b''), (232, None), (5, 'error'), (0, 'error')],
                         ids=['eof', 'busy', 'access', 'false-zero'])
def test_readfile_failures_are_classified_exactly(monkeypatch, code, wanted):
    api = fake_api(monkeypatch)

    def peek(handle, buffer, size, read, available, left):
        available._obj.value = 8
        return 1

    api.functions['PeekNamedPipe'].callback = peek
    api.functions['ReadFile'].callback = lambda *args: 0
    api.errors[0] = code
    if wanted == 'error':
        with pytest.raises(w.Win32Error) as caught:
            api.read(1, 4096)
        assert (caught.value.api, caught.value.code) == ('ReadFile', code)
    else:
        assert api.read(1, 4096) is wanted


def test_read_never_asks_for_more_than_the_peek_promised(monkeypatch):
    api = fake_api(monkeypatch)
    asked = []

    def peek(handle, buffer, size, read, available, left):
        available._obj.value = 4
        return 1

    def readfile(handle, buffer, size, count, overlapped):
        asked.append(size)
        c.memmove(buffer, b'abcd', 4)
        count._obj.value = 999999                      # a kernel that lies about the length
        return 1

    api.functions['PeekNamedPipe'].callback = peek
    api.functions['ReadFile'].callback = readfile
    assert api.read(1, 65536) == b'abcd'
    assert asked == [4]


@pytest.mark.parametrize('code', [5, 109], ids=['access', 'broken-pipe'])
def test_a_write_failure_that_is_not_a_full_pipe_is_never_zero(monkeypatch, code):
    api = fake_api(monkeypatch)
    api.errors[0] = code
    api.functions['WriteFile'].callback = lambda *args: 0
    with pytest.raises(w.Win32Error) as caught:
        api.write(1, b'policy')
    assert (caught.value.api, caught.value.code) == ('WriteFile', code)


def test_write_bounds_one_transfer_at_the_pipe_capacity(monkeypatch):
    api = fake_api(monkeypatch)
    asked = []

    def write(handle, data, size, count, overlapped):
        asked.append((bytes(data), size))
        count._obj.value = size
        return 1

    api.functions['WriteFile'].callback = write
    assert api.write(1, b'x' * 70000) == 65536
    assert asked == [(b'x' * 65536, 65536)]
