"""T-839: pins on the Win32 boundary of `archeus/node/isolation.py` (lines 1850-2254).

The block is `if WINDOWS:`-only, so everywhere it is not the platform it never runs and
every existing test of it skips: a mutation of those comparisons, early returns and
handle bookkeeping survives the suite on POSIX. Here the block's own AST is executed
against a faked `ctypes` (its two `ctypes` imports excepted), so the real code paths run
with no Win32 entry point, no network and no process. Every name the block binds lives
in `Host.ns`; `Host.give(name, fn)` replaces one Win32 answer for one test, and the
defaults in `Host.answer_*` are the healthy answer of that call.
"""

import ast
import ctypes
import ctypes.wintypes
import os
import struct
import types
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.node import isolation as iso, mxc


SOURCE = str(iso.__file__)
KEY = ids.new_id('execution')
USER = 'S-1-5-21-1111-2222-3333-1001'
AC_SID = 'S-1-15-2-2860417396-1414370549'
CAP_SID = 'S-1-15-3-1'
# wintypes follows the host's C long (8 bytes on Linux and macOS); the faked SID and ACL
# bytes are laid out with Windows widths.
WIN32_TYPES = SimpleNamespace(**{**vars(ctypes.wintypes), 'DWORD': ctypes.c_uint32, 'ULONG': ctypes.c_uint32,
                                 'LONG': ctypes.c_int32, 'BOOL': ctypes.c_int32})
GROUP_SID = 'S-1-15-2-1'
INTEGRITY = 'S-1-16-8192'
PID = 4242
SE_OBJECT_TYPE, DACL_SECURITY_INFORMATION = 1, 0x4
CREATED = (0x22222222 << 32) | 0x11111111
#: (low, high) of each of the four FILETIMEs `GetProcessTimes` fills: created, exited,
#: kernel, user. All four differ so only the creation time can answer.
TIMES = ((0x11111111, 0x22222222), (0x33333333, 0x44444444),
         (0x55555555, 0x66666666), (0x77777777, 0x88888888))


class _Fn:
    def __init__(self, lib, name):
        self.lib, self.name = lib, name
        self.restype, self.argtypes = None, None


class _Lib:
    def __init__(self, name):
        self._name = name

    def __getattr__(self, item):
        fn = _Fn(self._name, item)
        object.__setattr__(self, item, fn)
        return fn


def _fake_ctypes(libs):
    mod = types.ModuleType('pv20_win32_under_test')
    mod.__dict__.update(vars(ctypes))
    mod.WinDLL = lambda name, *a, **kw: libs.setdefault(name, _Lib(name))
    return mod


def _imports_ctypes(node):
    if isinstance(node, ast.Import):
        return any(alias.name == 'ctypes' for alias in node.names)
    return isinstance(node, ast.ImportFrom) and node.module == 'ctypes'


_CODE = None


def _block():
    global _CODE
    if _CODE is None:
        with open(SOURCE, encoding='utf-8') as f:
            tree = ast.parse(f.read(), SOURCE)
        branches = [n for n in tree.body if isinstance(n, ast.If)
                    and isinstance(n.test, ast.Name) and n.test.id == 'WINDOWS']
        assert len(branches) == 1, SOURCE
        block = branches[0]
        assert block.body and block.body[-1].end_lineno - block.lineno > 400, SOURCE
        body = [n for n in block.body if not _imports_ctypes(n)]
        assert len(body) == len(branches[0].body) - 2, 'the block must open with ctypes'
        _CODE = compile(ast.Module(body, type_ignores=[]), SOURCE, 'exec')
    return _CODE


def _handle(value):
    """The plain int behind a handle, whether it is one or a ctypes out-param."""
    if value is None:
        return None
    inner = getattr(value, 'value', value)
    return inner if isinstance(inner, int) else 0


def _addr(value):
    """Where the caller's buffer lives: an array, an instance or a `byref()` of one."""
    return ctypes.addressof(getattr(value, '_obj', value))


def _true(*args):
    return 1


def sid_bytes(text):
    """A SID in memory: revision, sub-authority count, identifier authority (big-endian)
    and the sub-authorities (little-endian), which is what both the token readers and
    `parse_ace` walk."""
    parts = text.split('-')
    subs = [int(s, 0) for s in parts[3:]]
    blob = bytearray(8 + 4 * len(subs))
    blob[0] = int(parts[1])
    blob[1] = len(subs)
    blob[2:8] = int(parts[2], 0).to_bytes(6, 'big')
    for i, sub in enumerate(subs):
        blob[8 + 4 * i:12 + 4 * i] = sub.to_bytes(4, 'little')
    return bytes(blob)


def access_ace(ace_type, sid, mask, flags=0):
    body = sid_bytes(sid)
    return (bytes([ace_type, flags]) + (8 + len(body)).to_bytes(2, 'little')
            + mask.to_bytes(4, 'little') + body)


class Host:
    """One execution of the `if WINDOWS:` block with every Win32 call faked."""

    def __init__(self, backend=None, native_run=False):
        self.libs = {}
        self.impl = {}
        self.calls = []
        self.closed = []
        self.freed = []
        self.keep = []
        self.sids = {}
        self.token = {}
        self.objects = {}
        self.type_answers = ['Job']
        self.type_calls = 0
        self.error = 0
        self.strict = False
        self.job_handle = 0x77
        self.process_handle = 0x5150
        self.file_handle = 0x99
        self.set_info = None
        self.assignments = []
        self.inherit = []
        self.opens = []
        self.dups = 0
        self.next_dup = 0x6001
        self.exit_code = 259
        self.active = 0
        self.handle_flags = 0
        self.nt_status = [0]
        self.handle_table = bytes(16)
        self.dacl_error = 0
        self.null_dacl = False
        self.acl_info_fail = False
        self.aces = []
        self.acl_in_use = None
        self.ace_fail = ()
        self.ace_null = ()
        self.sd_addr = self.raw(bytes(32))
        self.acl_addr = 0
        ns = dict(vars(iso))
        ns.update(C=_fake_ctypes(self.libs), W=WIN32_TYPES, WINDOWS=True)
        exec(_block(), ns)
        self.ns = ns
        for name, fn in [(k, v) for k, v in ns.items() if isinstance(v, _Fn)]:
            api = fn.name
            self.impl.setdefault(api, getattr(self, 'answer_' + api, _true))
            ns[name] = (lambda *args, api=api: self._call(api, *args))
        ns['_err'] = lambda: self.error
        self.name_of('')
        self.type_of('Job')
        self.boundary = ns['WindowsBoundary'](backend=backend, native_run=native_run)

    def _call(self, api, *args):
        self.calls.append((api, args))
        return self.impl[api](*args)

    def give(self, api, fn):
        self.impl[api] = fn

    def fail(self, api, code=5):
        self.impl[api] = lambda *args: self.reject(code)

    def reject(self, code=5):
        self.error = code
        return 0

    def calls_of(self, api):
        return [args for name, args in self.calls if name == api]

    def raw(self, data):
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        self.keep.append(buf)
        return ctypes.addressof(buf)

    def wide(self, text):
        buf = ctypes.create_unicode_buffer(text)
        self.keep.append(buf)
        return ctypes.addressof(buf)

    def sid(self, text):
        """Where *text* lives in memory, and the answer `_ConvertSidToStringSidW` gives
        for that address."""
        addr = self.raw(sid_bytes(text))
        self.sids[addr] = text
        return addr

    def _info(self, text):
        length = (2 * len(text)).to_bytes(2, 'little')
        blob = bytearray(24)
        blob[0:2] = length
        blob[8:16] = self.wide(text).to_bytes(8, 'little')
        return bytes(blob)

    def type_of(self, text):
        self.objects[self.ns['OBJECT_TYPE_INFORMATION']] = self._info(text)

    def name_of(self, text):
        self.objects[self.ns['OBJECT_NAME_INFORMATION']] = self._info(text)

    def object_blob(self, cls, text='', length=None, pointer=True):
        """A UNICODE_STRING by hand: the length at 0 and the buffer at 8, so a reader
        that looks in another word cannot answer."""
        blob = bytearray(24)
        blob[0:2] = (2 * len(text) if length is None else length).to_bytes(2, 'little')
        blob[8:16] = (self.wide(text) if pointer else 0).to_bytes(8, 'little')
        self.objects[cls] = bytes(blob)

    def group_blob(self, sids):
        blob = struct.pack('<I', len(sids)) + bytes(4)
        for text in sids:
            blob += struct.pack('<QI', self.sid(text), 0) + bytes(4)
        return blob

    def use_token(self, *, user=USER, appcontainer=1, ac=AC_SID, integrity=INTEGRITY,
                  capabilities=(CAP_SID,), groups=(GROUP_SID,)):
        def point(text):
            return struct.pack('<Q', self.sid(text)) if text else bytes(8)
        self.token = {
            self.ns['TOKEN_USER']: point(user),
            self.ns['TOKEN_IS_APPCONTAINER']: struct.pack('<I', appcontainer)
            if appcontainer is not None else None,
            self.ns['TOKEN_APPCONTAINER_SID']: point(ac),
            self.ns['TOKEN_INTEGRITY_LEVEL']: point(integrity),
            self.ns['TOKEN_CAPABILITIES']: self.group_blob(capabilities),
            self.ns['TOKEN_GROUPS']: self.group_blob(groups),
        }

    def handles_of_pid(self, pid, rows):
        """The `NtQuerySystemInformation` answer: *rows* of (pid, handle) after a
        16-byte header whose first ULONG is the count."""
        he = self.ns['_HE']
        def entry(p, h):
            return bytes(he(Object=0, pid=p, Handle=h, Granted=0, creator=0,
                            TypeIndex=0, Attributes=0, Reserved=0))
        self.handle_table = struct.pack('<I', len(rows)) + bytes(12) + \
            b''.join(entry(p, h) for p, h in rows)

    def refuse_open(self, code=5):
        self.give('OpenProcess', lambda *args: self.reject(code))

    # ── the healthy answer of each Win32 call ──

    def answer_CloseHandle(self, handle):
        self.closed.append(_handle(handle))
        return 1

    def answer_CreateJobObjectW(self, sa, name):
        return self.job_handle

    def answer_SetInformationJobObject(self, handle, cls, ref, size):
        li = ref._obj
        self.set_info = {'cls': cls, 'size': size, 'sizeof': ctypes.sizeof(self.ns['_ELI']),
                         'flags': int(li.Basic.LimitFlags),
                         'active': int(li.Basic.ActiveProcessLimit),
                         'memory': int(li.JobMemoryLimit),
                         'cpu': int(li.Basic.PerJobUserTimeLimit),
                         'per_process_cpu': int(li.Basic.PerProcessUserTimeLimit),
                         'process_memory': int(li.ProcessMemoryLimit)}
        return 1

    def answer_QueryInformationJobObject(self, job, cls, buf, size, got):
        if cls != self.ns['JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION']:
            return self.reject(87)
        offset = getattr(self.ns['_JBAI'], 'ActiveProcesses').offset
        ctypes.memmove(_addr(buf) + offset,
                       struct.pack('<I', self.active), 4)
        return 1

    def answer_AssignProcessToJobObject(self, job, process):
        self.assignments.append((_handle(job), _handle(process)))
        return 1

    def answer_CreateFileW(self, path, access, share, sa, creation, flags, template):
        return self.file_handle

    def answer_GetExitCodeProcess(self, handle, ref):
        ref._obj.value = self.exit_code
        return 1

    def answer_GetProcessTimes(self, handle, *times):
        for i, ft in enumerate(times):
            ft._obj.dwLowDateTime, ft._obj.dwHighDateTime = TIMES[i]
        return 1

    def answer_OpenProcess(self, access, inherit, pid):
        self.opens.append((access, inherit, pid))
        return self.process_handle

    def answer_GetCurrentProcess(self):
        return 0xFFFFFFFFFFFFFFFE

    def answer_DuplicateHandle(self, source, handle, target, out, access, inherit, options):
        self.dups += 1
        out._obj.value = self.next_dup
        self.next_dup += 1
        return 1

    def answer_SetHandleInformation(self, handle, mask, value):
        self.inherit.append((_handle(handle), mask, value))
        return 1

    def answer_GetHandleInformation(self, handle, ref):
        ref._obj.value = self.handle_flags
        return 1

    def answer_LocalFree(self, mem):
        addr = _handle(mem)
        if addr:
            self.freed.append(addr)
        return 0

    def answer_NtQueryObject(self, handle, cls, buf, size, got):
        if self.strict and handle is None:
            raise AssertionError('a null handle was queried')
        if cls == self.ns['OBJECT_TYPE_INFORMATION'] and len(self.type_answers) > 1:
            answer = self.type_answers[min(self.type_calls, len(self.type_answers) - 1)]
            self.type_calls += 1
            data = self._info(answer)
        else:
            data = self.objects.get(cls)
        if data is None:
            return 0xC0000004
        ctypes.memmove(buf, data, len(data))
        return 0

    def answer_NtQuerySystemInformation(self, info_class, buf, size, got):
        status = self.nt_status.pop(0) if len(self.nt_status) > 1 else self.nt_status[0]
        if status:
            return status
        ctypes.memmove(buf, self.handle_table, len(self.handle_table))
        return 0

    def answer_OpenProcessToken(self, process, access, ref):
        ref._obj.value = 0x101
        return 1

    def answer_GetTokenInformation(self, token, cls, buf, size, got):
        data = self.token.get(cls)
        if data is None:
            return self.reject(5)
        got._obj.value = len(data)
        if size < len(data):
            return self.reject(122)
        ctypes.memmove(buf, data, len(data))
        return 1

    def answer_ConvertSidToStringSidW(self, psid, ref):
        text = self.sids.get(psid)
        if text is None:
            return self.reject(87)
        buf = ctypes.create_unicode_buffer(text)
        self.keep.append(buf)
        ref._obj.contents = buf
        return 1

    def answer_GetNamedSecurityInfoW(self, path, kind, what, owner, group, dacl, sacl, sd):
        if self.dacl_error:
            return self.dacl_error
        sd._obj.value = self.sd_addr
        if not self.null_dacl and self.acl_addr:
            dacl._obj.value = self.acl_addr
        return 0

    def answer_GetAclInformation(self, pacl, info, size, cls):
        if self.acl_info_fail:
            return self.reject(5)
        info._obj.AceCount = len(self.aces)
        info._obj.AclBytesInUse = self.acl_in_use if self.acl_in_use is not None \
            else 8 + sum(len(ace) for ace in self.aces)
        return 1

    def answer_GetAce(self, pacl, index, pace):
        # A failing call still leaves a usable pointer behind: the code has to check the
        # call *and* the pointer, and neither fake can stand for the other.
        pace._obj.value = self.acl_addr + 8 + sum(len(a) for a in self.aces[:index])
        if index in self.ace_fail:
            return self.reject(5)
        if index in self.ace_null:
            pace._obj.value = 0
            return 1
        return 1

    def acl(self, aces, in_use=None):
        self.aces = list(aces)
        self.acl_in_use = in_use
        self.acl_addr = self.raw(bytes([2, 0])
                                 + (8 + sum(len(a) for a in self.aces)).to_bytes(2, 'little')
                                 + len(self.aces).to_bytes(2, 'little') + bytes(2)
                                 + b''.join(self.aces))


@pytest.fixture
def make_host():
    made = []

    def make(**kwargs):
        one = Host(**kwargs)
        made.append(one)
        return one

    return make


@pytest.fixture
def host(make_host):
    return make_host()


def proc(**over):
    given = {'pid': PID, 'create_time': CREATED, 'observed_backend': 'processcontainer',
             'observed_tier': 'base-container'}
    given.update(over)
    return SimpleNamespace(**given)


UNVERIFIED = [('create_profile', 'mxc_lifecycle_unverified'),
              ('delete_profile', 'mxc_lifecycle_unverified'),
              ('derive', 'mxc_identity_unverified'),
              ('derive_sid', 'mxc_identity_unverified'),
              ('profile_exists', 'mxc_lifecycle_unverified')]


def test_the_boundary_never_reports_itself_available(host):
    assert host.boundary.available() is False


@pytest.mark.parametrize('method,reason', UNVERIFIED, ids=[m[0] for m in UNVERIFIED])
def test_an_unverified_mxc_operation_never_answers(host, method, reason):
    with pytest.raises(iso.IsolationUnavailable) as err:
        getattr(host.boundary, method)(KEY)
    assert err.value.reason == reason


@pytest.mark.parametrize('method', [m[0] for m in UNVERIFIED], ids=[m[0] for m in UNVERIFIED])
def test_a_name_is_refused_before_the_unverified_operation(host, method):
    with pytest.raises(iso.IsolationUnavailable) as err:
        getattr(host.boundary, method)('archeus.spike.life0')
    assert err.value.reason == 'profile_name'


def test_a_job_that_was_never_created_is_never_configured(host):
    host.give('CreateJobObjectW', lambda *args: None)
    with pytest.raises(iso.IsolationUnavailable) as err:
        host.boundary.create_job(KEY)
    assert err.value.reason == 'job_create'
    assert host.calls_of('SetInformationJobObject') == [] and host.closed == []


def test_every_execution_job_is_kill_on_close_and_never_inheritable(host):
    assert host.boundary.create_job(KEY) == 0x77
    assert host.set_info['cls'] == host.ns['JOB_OBJECT_EXTENDED_LIMIT_INFORMATION']
    assert host.set_info['flags'] == host.ns['JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE']
    assert host.set_info['size'] == host.set_info['sizeof']
    assert host.inherit == [(0x77, host.ns['HANDLE_FLAG_INHERIT'], 0)]
    assert host.closed == []


@pytest.mark.parametrize('kind', ['exec', 'verify'])
def test_only_a_verifier_job_carries_the_budgets(host, kind):
    key = KEY if kind == 'exec' else iso.Principal('verify', ids.new_id('verification'), 0).key
    host.boundary.create_job(key)
    if kind == 'verify':
        assert host.set_info['flags'] == 0x2000 | 0x8 | 0x200 | 0x4
        assert (host.set_info['active'], host.set_info['memory'], host.set_info['cpu']) \
            == (iso.VERIFY_ACTIVE_PROCESSES, iso.VERIFY_JOB_MEMORY, iso.VERIFY_JOB_CPU_100NS)
        assert host.set_info['per_process_cpu'] == host.set_info['process_memory'] == 0
    else:
        assert host.set_info['flags'] == 0x2000
        assert (host.set_info['active'], host.set_info['memory'], host.set_info['cpu']) == (0, 0, 0)


@pytest.mark.parametrize('broken', ['typed', 'named', 'inheritable'])
def test_a_job_core_might_share_is_refused(host, broken):
    if broken == 'typed':
        host.type_of('File')
    elif broken == 'named':
        host.name_of('SharedJob')
    else:
        host.handle_flags = host.ns['HANDLE_FLAG_INHERIT']
    with pytest.raises(iso.IsolationUnavailable) as err:
        host.boundary.create_job(KEY)
    assert err.value.reason == 'job_limits'
    assert host.closed == [0x77]


@pytest.mark.parametrize('step', ['SetInformationJobObject', 'SetHandleInformation',
                                  'GetHandleInformation'])
def test_a_job_that_could_not_be_made_safe_is_closed(host, step):
    host.fail(step, 5)
    with pytest.raises(iso.IsolationUnavailable):
        host.boundary.create_job(KEY)
    assert host.closed == [0x77]


def test_job_facts_are_read_from_the_object_and_the_handle(host):
    assert host.boundary.job_facts(0x77) == {'type': 'Job', 'name': '',
                                             'inheritable': False}
    host.strict = True
    assert host.boundary.job_facts(None) is None
    host.handle_flags = host.ns['HANDLE_FLAG_INHERIT']
    assert host.boundary.job_facts(0x77)['inheritable'] is True
    host.handle_flags = 0x2
    assert host.boundary.job_facts(0x77)['inheritable'] is False


def test_the_active_process_count_comes_from_the_accounting_block(host):
    host.active = 3
    assert host.boundary.job_active_processes(0x77) == 3
    assert host.calls_of('QueryInformationJobObject')[0][1] \
        == host.ns['JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION']
    host.active = 0
    assert host.boundary.job_active_processes(0x77) == 0


def test_assigning_a_process_needs_a_job_to_assign_it_to(host):
    with pytest.raises(iso.IsolationUnavailable) as err:
        host.boundary.assign_job(None, 0x5150)
    assert err.value.reason == 'job_missing'
    assert host.assignments == []
    host.boundary.assign_job(0x77, 0x5150)
    assert host.assignments == [(0x77, 0x5150)]


def test_a_handle_that_does_not_exist_is_never_closed(host):
    host.boundary.close_job(None)
    host.boundary.close_handle(None)
    assert host.closed == []
    host.boundary.close_job(0x77)
    host.boundary.close_handle(0x5150)
    assert host.closed == [0x77, 0x5150]


@pytest.mark.parametrize('setup,answer', [
    ('gone', None),
    ({'exit_code': 0}, None),
    ({}, CREATED),
    ('no-code', 'raise'),
    ('no-times', 'raise'),
    ('refused', 'raise'),
], ids=['gone', 'exited', 'runs', 'no-code', 'no-times', 'refused'])
def test_what_runs_under_a_pid(host, setup, answer):
    if setup == 'gone':
        host.refuse_open(host.ns['ERROR_INVALID_PARAMETER'])
    elif setup == 'refused':
        host.refuse_open(5)
    elif setup == 'no-code':
        host.fail('GetExitCodeProcess', 6)
    elif setup == 'no-times':
        host.fail('GetProcessTimes', 5)
    elif isinstance(setup, dict):
        for name, value in setup.items():
            setattr(host, name, value)
    if answer == 'raise':
        with pytest.raises(iso.IsolationUnavailable) as err:
            host.boundary.process_started(PID)
        assert err.value.reason == 'process_state'
    else:
        assert host.boundary.process_started(PID) == answer
    assert host.closed == ([] if setup in ('gone', 'refused') else [0x5150])


def test_only_job_objects_are_counted_as_holders(host):
    host.type_answers = ['Job', 'File', 'Job']
    host.handles_of_pid(PID, [(PID, 11), (PID, 12), (PID, 13), (99, 14)])
    found = host.boundary.job_handles_of(PID)
    assert [(_handle(h['handle']), h['type'], h['name'], h['inheritable']) for h in found] \
        == [(0x6001, 'Job', '', False), (0x6003, 'Job', '', False)]
    assert sorted(host.closed) == sorted([0x5150, 0x6001, 0x6002, 0x6003])


def test_a_holders_inheritable_flag_is_read_from_its_handle(host):
    host.handles_of_pid(PID, [(PID, 11)])
    host.handle_flags = host.ns['HANDLE_FLAG_INHERIT']
    assert [h['inheritable'] for h in host.boundary.job_handles_of(PID)] == [True]


def test_an_object_that_cannot_be_queried_has_neither_type_nor_name(host):
    host.objects.clear()
    assert host.boundary._obj_type(0x77) is None
    assert host.boundary._obj_name(0x77) is None
    host.object_blob(host.ns['OBJECT_TYPE_INFORMATION'], text='Job', length=0)
    assert host.boundary._obj_type(0x77) is None
    host.object_blob(host.ns['OBJECT_TYPE_INFORMATION'], text='Job', pointer=False)
    assert host.boundary._obj_type(0x77) is None


def test_an_unnamed_object_reads_as_empty_and_never_as_unknown(host):
    name = host.ns['OBJECT_NAME_INFORMATION']
    host.object_blob(name, text='SharedJob')
    assert host.boundary._obj_name(0x77) == 'SharedJob'
    host.object_blob(name, text='SharedJob', length=0)
    assert host.boundary._obj_name(0x77) == ''
    host.object_blob(name, text='SharedJob', pointer=False)
    assert host.boundary._obj_name(0x77) == ''


def test_a_handle_whose_flags_cannot_be_read_is_not_taken_as_inheritable(host):
    host.fail('GetHandleInformation', 5)
    with pytest.raises(iso.IsolationUnavailable) as err:
        host.boundary._handle_flags(0x77)
    assert err.value.reason == 'handle_state'


def test_only_the_handles_of_that_pid_are_duplicated(host):
    host.handles_of_pid(PID, [(PID, 11), (99, 12), (PID, 13)])
    assert [_handle(h) for h in host.boundary._handles_of(PID)] == [0x6001, 0x6002]
    assert host.opens == [(host.ns['PROCESS_DUP_HANDLE'], False, PID)]
    assert host.calls_of('NtQuerySystemInformation')[0][0] == 0x40
    assert host.closed == [0x5150]


def test_a_process_that_cannot_be_opened_has_no_handles_to_report(host):
    host.handles_of_pid(PID, [(PID, 11)])
    host.refuse_open(5)
    assert host.boundary._handles_of(PID) == []
    assert host.dups == 0


@pytest.mark.parametrize('status', ['mismatch', 'unsigned', 'other'],
                         ids=['mismatch', 'unsigned', 'other'])
def test_only_a_short_buffer_is_enlarged_when_enumerating(host, status):
    host.handles_of_pid(PID, [(PID, 11)])
    if status == 'mismatch':
        host.nt_status = [host.ns['STATUS_INFO_LENGTH_MISMATCH'], 0]
    elif status == 'unsigned':
        host.nt_status = [0xC0000004, 0]
    else:
        host.nt_status = [0xC0000001]
    if status == 'other':
        with pytest.raises(iso.IsolationUnavailable) as err:
            host.boundary._handles_of(PID)
        assert err.value.reason == 'handle_enum'
        assert host.dups == 0
    else:
        assert [_handle(h) for h in host.boundary._handles_of(PID)] == [0x6001]


def test_the_token_is_query_only_and_both_handles_are_closed(host):
    host.use_token()
    report = host.boundary.token(PID)
    assert host.calls_of('OpenProcess')[0] \
        == (host.ns['PROCESS_QUERY_LIMITED_INFORMATION'], False, PID)
    assert host.calls_of('OpenProcessToken')[0][1] == host.ns['TOKEN_QUERY']
    assert report['user_sid'] == USER and report['is_appcontainer'] == 1
    assert report['ac_sid'] == AC_SID and report['integrity'] == '0x2000'
    assert report['capability_sids'] == [CAP_SID, GROUP_SID]
    assert host.closed == [0x101, 0x5150]


@pytest.mark.parametrize('route', ['open', 'token'], ids=['open', 'token'])
def test_a_process_whose_token_cannot_be_read_leaks_nothing(host, route):
    host.use_token()
    if route == 'open':
        host.refuse_open(5)
        with pytest.raises(iso.IsolationUnavailable) as err:
            host.boundary.token(PID)
        assert err.value.reason == 'token' and host.closed == []
    else:
        host.fail('OpenProcessToken', 5)
        with pytest.raises(iso.IsolationUnavailable):
            host.boundary.token(PID)
        assert host.closed == [0x5150]


def test_the_identity_report_is_only_what_was_observed(host):
    host.use_token()
    report = host.boundary.read_identity(proc())
    assert report == mxc.IdentityReport(PID, CREATED, USER, True, AC_SID, '0x2000',
                                        'processcontainer', 'base-container',
                                        (CAP_SID, GROUP_SID))
    assert type(report.is_appcontainer) is bool


@pytest.mark.parametrize('label,setup,why', [
    ('nothing runs under it', {'started': [None, None]}, 'dead or reused identity owner'),
    ('the pid was reused', {'create_time': CREATED + 1}, 'dead or reused identity owner'),
    ('it changed while read', {'started': [CREATED, CREATED + 1]},
     'identity owner changed during inspection'),
    ('no container flag', {'token': {'appcontainer': 7}}, 'incomplete native token report'),
    ('no integrity level', {'token': {'integrity': None}}, 'incomplete native token report'),
    ('backend requested only', {'proc': {'observed_backend': None}},
     'UNVERIFIED: effective backend/tier'),
    ('tier requested only', {'proc': {'observed_tier': 'disabled'}},
     'UNVERIFIED: effective backend/tier'),
], ids=['dead', 'reused', 'changed', 'flag', 'integrity', 'backend', 'tier'])
def test_identity_is_refused_before_it_is_reported(host, label, setup, why):
    host.use_token(**setup.get('token', {}))
    if 'started' in setup:
        answers = list(setup['started'])
        host.boundary.process_started = lambda pid: answers.pop(0)
    given = dict(setup.get('proc', {}))
    target = proc(create_time=setup.get('create_time', CREATED), **given)
    with pytest.raises(mxc.MxcUnavailable, match=why):
        host.boundary.read_identity(target)


def test_every_group_entry_is_read_at_its_own_stride(host):
    one, two = host.sid(CAP_SID), host.sid(GROUP_SID)
    def entry(psid):
        return struct.pack('<QI', psid, 0) + bytes(4)
    host.token[host.ns['TOKEN_GROUPS']] = struct.pack('<I', 2) + bytes(4) \
        + entry(one) + entry(two) + entry(0x1)
    assert host.boundary._token_groups(None, host.ns['TOKEN_GROUPS']) == [CAP_SID, GROUP_SID]


def test_the_integrity_level_is_the_last_sub_authority(host):
    host.use_token()
    assert host.boundary._token_integrity(None) == '0x2000'
    host.use_token(integrity=None)
    assert host.boundary._token_integrity(None) is None


def test_a_token_report_is_read_when_it_fits_and_never_guessed(host):
    host.token[host.ns['TOKEN_GROUPS']] = host.group_blob([CAP_SID] * 12)
    assert host.boundary._token_groups(None, host.ns['TOKEN_GROUPS']) == [CAP_SID] * 12
    host.calls = []
    host.fail('GetTokenInformation', 5)
    assert host.boundary._token_sid(None, host.ns['TOKEN_USER']) is None
    assert len(host.calls_of('GetTokenInformation')) == 1

    def never_fits(token, cls, buf, size, got):
        got._obj.value = 4096
        return host.reject(122)

    host.calls = []
    host.give('GetTokenInformation', never_fits)
    assert host.boundary._token_flag(None, host.ns['TOKEN_IS_APPCONTAINER']) is None
    assert len(host.calls_of('GetTokenInformation')) == 4


def test_the_boundary_grants_no_capability_to_anybody(host):
    assert host.boundary.capability_grants() == ()


@pytest.mark.parametrize('route', ['user', 'convert', 'open'], ids=['user', 'convert', 'open'])
def test_a_token_that_names_no_user_is_an_error_not_a_blank(host, route):
    host.use_token(user=None if route == 'user' else USER)
    if route == 'open':
        host.fail('OpenProcessToken', 5)
    elif route == 'convert':
        host.fail('ConvertSidToStringSidW', 87)
    with pytest.raises(iso.IsolationUnavailable) as err:
        host.boundary._user_sid()
    assert err.value.reason == 'token'
    if route == 'user':
        assert 'no user' in err.value.detail
    assert host.closed == ([] if route == 'open' else [0x101])


def test_a_descriptor_that_cannot_be_read_is_never_read_as_empty(host):
    host.dacl_error = 5
    with pytest.raises(iso.IsolationUnavailable) as err:
        host.boundary.dacl('in.txt')
    assert err.value.reason == 'dacl_unreadable'
    assert host.freed == []
    host.dacl_error = 0
    host.acl([access_ace(0, 'S-1-1-0', 0x1200A9)], in_use=12)
    with pytest.raises(iso.IsolationUnavailable) as err:
        host.boundary.dacl('in.txt')
    assert err.value.reason == 'dacl_malformed'
    assert host.freed == [host.sd_addr]


def test_a_null_dacl_is_everyone_with_everything_and_an_empty_one_is_not(host):
    host.null_dacl = True
    assert host.boundary.dacl('in.txt') == list(iso.NULL_DACL)
    assert host.freed == [host.sd_addr]
    host.null_dacl = False
    host.acl([])
    assert host.boundary.dacl('in.txt') == []
    host.acl([access_ace(0, 'S-1-1-0', 0x1200A9), access_ace(1, USER, 0x2, 0x10)])
    assert host.boundary.dacl('in.txt') == [(0, 'S-1-1-0', 0x1200A9, 0), (1, USER, 0x2, 0x10)]
    (asked, kind, what) = host.calls_of('GetNamedSecurityInfoW')[-1][:3]
    assert asked == os.path.abspath('in.txt') and kind == SE_OBJECT_TYPE \
        and what == DACL_SECURITY_INFORMATION


@pytest.mark.parametrize('where,asked', [
    ('count', 0), ('ace', 2), ('pointer', 2)], ids=['count', 'ace', 'pointer'])
def test_a_half_read_acl_is_a_failure_never_a_short_list(host, where, asked):
    host.acl([access_ace(0, 'S-1-1-0', 0x1), access_ace(0, USER, 0x2)])
    if where == 'count':
        host.acl_info_fail = True
    elif where == 'ace':
        host.ace_fail = (1,)
    else:
        host.ace_null = (1,)
    with pytest.raises(iso.IsolationUnavailable) as err:
        host.boundary.dacl('in.txt')
    assert err.value.reason == 'dacl_unreadable'
    assert host.freed == [host.sd_addr]
    # how many ACEs the loop asked the OS for before it gave up: a read whose answer is
    # ignored never stops at the failing one
    assert len(host.calls_of('GetAce')) == asked


@pytest.mark.parametrize('mode,access,creation', [
    ('read', 0x80000000 | 0x80, 3),
    ('append', 0x40000000 | 0x4 | 0x80, 4)], ids=['read', 'append'])
def test_stdio_is_opened_in_one_direction_only(host, mode, access, creation):
    assert host.boundary.open_inherited('core-stdio', mode) == 0x99
    (opened, access_, share, sa, creation_, flags, template) = host.calls_of('CreateFileW')[0]
    assert opened == os.path.abspath('core-stdio') and access_ == access
    assert creation_ == creation and share == 3 and flags == 1
    assert sa is None and template is None


@pytest.mark.parametrize('answer', [None, 0, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF],
                         ids=['none', 'zero', 'minus', 'ff32', 'ff64'])
def test_stdio_that_cannot_be_opened_is_a_failure_not_a_handle(host, answer):
    host.file_handle = answer
    with pytest.raises(iso.IsolationUnavailable) as err:
        host.boundary.open_inherited('core-stdio', 'read')
    assert err.value.reason == 'stdio'


def test_launch_stays_refused_until_a_closed_policy_exists(host):
    with pytest.raises(iso.IsolationUnavailable) as err:
        host.boundary.launch(['exe'], cwd='.', env={}, profile='p', job=0x77,
                             stdin=None, stdout=None)
    assert err.value.reason == 'mxc_policy_required'


def test_spawn_forwards_the_injected_backend_and_wraps_a_refusal(make_host):
    seen = []

    def forwards(policy, *, exe, job, backend, native_run):
        seen.append((policy, exe, job, backend, native_run))
        return 'child'

    opened = make_host(backend='injected', native_run=True)
    opened.ns['mxc'] = SimpleNamespace(spawn=forwards, MxcUnavailable=mxc.MxcUnavailable)
    assert opened.boundary.spawn('policy', exe='exe', job=0x77) == 'child'
    assert seen == [('policy', 'exe', 0x77, 'injected', True)]

    def refuse(*args, **kw):
        raise mxc.MxcUnavailable('native MXC execution disabled')

    for backend in ('injected', None):
        refused = make_host(backend=backend)
        refused.ns['mxc'] = SimpleNamespace(spawn=refuse, MxcUnavailable=mxc.MxcUnavailable)
        with pytest.raises(iso.IsolationUnavailable) as err:
            refused.boundary.spawn('policy', exe='exe', job=0x77)
        assert err.value.reason == 'mxc'
        assert isinstance(err.value.__cause__, mxc.MxcUnavailable)
    shipped = make_host()
    with pytest.raises(iso.IsolationUnavailable) as err:
        shipped.boundary.spawn('policy', exe='exe', job=0x77)
    assert err.value.reason == 'mxc'
