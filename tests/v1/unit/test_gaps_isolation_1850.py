"""T-337 — the uncovered fail-closed branches of `archeus/node/isolation.py` 1856-2260.

The block under test is `WindowsBoundary` and its Win32 readers, which live under the
module-level `if WINDOWS:`. Nothing here needs Windows or the Windows API:

* on Windows the real `iso.WindowsBoundary` is used, and the autouse `win32` fixture
  replaces every Win32 binding the block calls with a recorder that fails the test the
  moment an OS call is reached that its test did not answer (the same tripwire
  discipline as `test_pv20_isolation.py`'s `os_tripwire`, armed from the start);
* on any other platform the very same source section is loaded out of the file and
  exec'd over a fake ctypes (`FakeCTypes`), so the branches that run here are the ones
  that run there. Anything the fake cannot model raises instead of guessing.

Either way the code under test is the code in the file, and every OS answer is a knob
the test turns. Fixtures are platform-neutral: no Windows path, no case sensitivity, no
localized error text, no environment value, no live process, no sleep.
"""

import ast
import builtins
import os
import textwrap
from types import SimpleNamespace

import pytest

from archeus.core.domain import ids
from archeus.node import isolation as iso
from archeus.node import mxc

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SOURCE = os.path.join(REPO, 'archeus', 'node', 'isolation.py')


# ── the fake ctypes: enough of the type layer to build the block, never an OS ──

class Scalar:
    """A ctypes scalar instance (`W.DWORD(0)`): `.value`, truthiness, `int()`."""

    def __init__(self, value=0):
        self.value = value

    def __bool__(self):
        return bool(self.value)

    def __int__(self):
        return int(self.value)

    def __repr__(self):
        return 'Scalar(%r)' % (self.value,)


class Ref:
    """`byref(x)`: the house fake style, `ref._obj` being the thing referred to."""

    def __init__(self, target):
        self._obj = target

    def __repr__(self):
        return 'Ref(%r)' % (self._obj,)


class Array:
    """`(c_byte * n)()` — zeroed bytes, and `sizeof` of it is `n`."""

    def __init__(self, item, count):
        self.item, self.count = item, count
        self.buf = bytearray(item.size * count)


class ScalarType:
    def __init__(self, name, size):
        self.name, self.size = name, size

    def __call__(self, value=0):
        return Scalar(value)

    def __mul__(self, count):
        return lambda: Array(self, int(count))

    def __repr__(self):
        return self.name


class PointerType:
    def __init__(self, target, size=8):
        self.target, self.size = target, size

    def __call__(self, value=0):
        return Scalar(value)


class Structure:
    """A ctypes Structure: fields exist and hold what a test writes into them."""

    _fields_ = ()

    def __init__(self, *args, **kw):
        for name, typ in type(self)._fields_:
            nested = isinstance(typ, type) and issubclass(typ, Structure)
            setattr(self, name, typ() if nested else 0)
        for name, value in kw.items():
            setattr(self, name, value)

    @classmethod
    def from_buffer_copy(cls, *args):
        raise AssertionError('the fake ctypes does not model from_buffer_copy')


def _sizeof(obj):
    if isinstance(obj, type):
        if issubclass(obj, Structure):
            return 8 * max(1, len(obj._fields_))
        raise AssertionError('the fake ctypes cannot size %r' % (obj,))
    if isinstance(obj, Structure):
        return _sizeof(type(obj))
    if isinstance(obj, (ScalarType, PointerType)):
        return obj.size
    if isinstance(obj, Array):
        return len(obj.buf)
    raise AssertionError('the fake ctypes cannot size %r' % (obj,))


class _RawCall:
    """A function of a real DLL: reaching it is a test failure, never a syscall."""

    def __init__(self, dll, name):
        self.dll, self.name, self.restype, self.argtypes = dll, name, None, None

    def __call__(self, *args, **kw):
        raise AssertionError('the real %s.%s was reached' % (self.dll, self.name))


class _Dll:
    def __init__(self, name):
        self.name = name

    def __getattr__(self, attr):
        if attr == 'GetLastError':
            return lambda: 0
        return _RawCall(self.name, attr)


class FakeCTypes:
    """What the block imports as `ctypes` (and `ctypes.wintypes`), minus the OS."""

    Structure = Structure
    sizeof = staticmethod(_sizeof)
    byref = staticmethod(lambda target: Ref(target))
    wintypes = None                                   # filled in below

    POINTER = staticmethod(lambda target: PointerType(target))
    WinDLL = staticmethod(lambda name: _Dll(name))

    def __init__(self):
        self._scalars = {}

    def __getattr__(self, name):
        if name.startswith('c_'):
            wide = name in ('c_void_p', 'c_size_t', 'c_ssize_t', 'c_longlong',
                            'c_ulonglong', 'c_ulong', 'c_wchar_p')
            t = self._scalars.get(name)
            if t is None:
                t = self._scalars[name] = ScalarType(name, 8 if wide else 4)
            return t
        raise AttributeError(name)

    # the pointer-reading primitives: a test that needs them must answer around them
    def cast(self, *args):
        raise AssertionError('the fake ctypes does not model cast (answer the caller)')

    def addressof(self, *args):
        raise AssertionError('the fake ctypes does not model addressof')

    def string_at(self, *args):
        raise AssertionError('the fake ctypes does not model string_at')

    def wstring_at(self, target, size=None):
        value = getattr(target, 'value', target)
        if isinstance(value, str):
            return value if size is None else value[:size // 2]
        raise AssertionError('the fake ctypes does not model wstring_at of %r' % (target,))

    def create_string_buffer(self, raw=b'', size=None):
        buf = Array(ScalarType('c_char', 1), size if size is not None else len(raw))
        buf.buf = bytearray(raw)
        return buf


class _Wintypes:
    """`ctypes.wintypes`, faked: `PWSTR`/`ULONG_PTR` are deliberately absent, because
    the block fills them in and that fallback is part of what is under test."""

    def __init__(self, c):
        self._c = c
        for name, size in (('WORD', 2), ('USHORT', 2), ('SHORT', 2), ('UCHAR', 1),
                           ('BOOL', 4), ('INT', 4), ('UINT', 4), ('DWORD', 4),
                           ('LONG', 4), ('ULONG', 4), ('LONGLONG', 8), ('WCHAR', 2)):
            setattr(self, name, ScalarType(name, size))
        self.HANDLE = ScalarType('HANDLE', 8)
        self.HWND = ScalarType('HWND', 8)

    def __getattr__(self, name):
        raise AttributeError(name)


class _FILETIME(Structure):
    _fields_ = [('dwLowDateTime', ScalarType('DWORD', 4)),
                ('dwHighDateTime', ScalarType('DWORD', 4))]


FAKE_C = FakeCTypes()
FAKE_W = _Wintypes(FAKE_C)
FAKE_W.FILETIME = _FILETIME
FAKE_C.wintypes = FAKE_W

_REAL_IMPORT = builtins.__import__


def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == 'ctypes' or name.startswith('ctypes.'):
        return FAKE_C
    return _REAL_IMPORT(name, globals, locals, fromlist, level)


def _windows_block():
    """The module's `if WINDOWS:` section, exec'd over the fake ctypes.

    The exec'd namespace starts as a copy of the module's own globals, so the helpers
    the block shares with the rest of `isolation.py` (`IsolationUnavailable`,
    `validated_profile`, `parse_ace`, `NULL_DACL`, `mxc`, `os`) are the real ones, and
    the names the block defines for itself (`C`, `W`, `_win`, `_err`, every `_Xxx`
    Win32 binding) are the ones a test patches."""
    with open(SOURCE, encoding='utf-8') as f:
        src = f.read()
    tree = ast.parse(src)
    node = next(n for n in tree.body
                if isinstance(n, ast.If) and getattr(n.test, 'id', None) == 'WINDOWS')
    lines = src.splitlines(True)[node.body[0].lineno - 1:node.body[-1].end_lineno]
    ns = dict(vars(iso))
    ns.update({'__name__': 'archeus.node.isolation.windows_block',
               '__file__': SOURCE,
               '__builtins__': dict(vars(builtins), __import__=_fake_import)})
    exec(compile(''.join(textwrap.dedent(''.join(lines)).splitlines(True)), SOURCE, 'exec'), ns)
    return ns


def _definition_line(name):
    """The line `def <name>` of `WindowsBoundary` sits on. The report quotes line
    numbers; this is what keeps them honest if the block ever moves."""
    with open(SOURCE, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == 'WindowsBoundary')
    found = [n.lineno for n in ast.walk(cls)
             if isinstance(n, ast.FunctionDef) and n.name == name]
    if not found:                                        # a module-level helper of the block
        found = [n.lineno for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(found) != 1:
        raise AssertionError('%s is defined at %r in %s' % (name, found, SOURCE))
    return found[0]


if iso.WindowsBoundary is None:
    BLOCK = _windows_block()
else:                                   # Windows: the real module, with every call answered
    BLOCK = vars(iso)
BOUNDARY = BLOCK['WindowsBoundary']

#: every Win32 entry point the block calls, all of them tripped by the `win32` fixture
WIN32_BINDINGS = (
    '_CloseHandle', '_CreateFileW', '_CreateJobObjectW', '_QueryInformationJobObject',
    '_SetInformationJobObject', '_AssignProcessToJobObject', '_GetExitCodeProcess',
    '_GetProcessTimes', '_OpenProcess', '_GetCurrentProcess', '_DuplicateHandle',
    '_SetHandleInformation', '_GetHandleInformation', '_LocalFree', '_QueryObject',
    '_NtQuerySystemInformation', '_OpenProcessToken', '_GetTokenInformation',
    '_ConvertSidToStringSidW', '_GetSecurityInfoByNameW', '_GetAclInformation', '_GetAce',
)


def _val(x):
    return getattr(x, 'value', x)


class Win32:
    """The knobs a test turns. Every binding starts as a tripwire; `answer` replaces one
    and `closes` makes `_CloseHandle` a recorder."""

    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        self.calls = {}
        self.closed = []
        self.freed = []
        self.error = 0
        for name in WIN32_BINDINGS:
            monkeypatch.setitem(BLOCK, name, _tripwire(self, name))
        monkeypatch.setitem(BLOCK, '_err', lambda: self.error)

    def answer(self, name, result=1):
        """Replace one binding with a stub returning *result* (or `result(*args)` when it
        is callable, so a test can answer from the arguments), recording its arguments."""
        seen = self.calls.setdefault(name, [])

        def stub(*args, **kw):
            seen.append(args)
            return result(*args, **kw) if callable(result) else result

        self.monkeypatch.setitem(BLOCK, name, stub)
        return seen

    def closes(self):
        """`CloseHandle` as a recorder: `win32.closed` is what the code closed, in order."""
        def stub(handle):
            self.closed.append(_val(handle))
            return 1
        self.monkeypatch.setitem(BLOCK, '_CloseHandle', stub)
        return self.closed

    def reached(self):
        """Which answered bindings were actually called — empty means the OS stayed out."""
        return {n: list(v) for n, v in self.calls.items() if n in WIN32_BINDINGS}


def _tripwire(win32, name):
    def trip(*args, **kw):
        raise AssertionError('the real %s was reached: %r' % (name, args))
    return trip


@pytest.fixture
def win32(monkeypatch):
    """Every OS answer the boundary can ask for, tripped until the test answers it."""
    return Win32(monkeypatch)


@pytest.fixture
def boundary():
    return BOUNDARY()


def new_exec_id():
    return ids.new_id('execution')


def new_verify_key():
    return iso.Principal('verify', ids.new_id('verification'), 0).key


def token_report(**changes):
    t = {'user_sid': 'S-1-5-21-7-8-9-1001', 'is_appcontainer': 0, 'ac_sid': None,
         'integrity': '0x2000', 'capability_sids': ['S-1-15-3-1']}
    t.update(changes)
    return t


# ── 1. the MXC seams stay shut (1885-1913) ────────────────────────────────────

@pytest.mark.parametrize('op,reason', [
    ('create_profile', 'mxc_lifecycle_unverified'),
    ('delete_profile', 'mxc_lifecycle_unverified'),
    ('derive', 'mxc_identity_unverified'),
    ('derive_sid', 'mxc_identity_unverified'),
    ('profile_exists', 'mxc_lifecycle_unverified'),
])
def test_every_unverified_mxc_operation_refuses(boundary, op, reason):
    with pytest.raises(iso.IsolationUnavailable) as err:
        getattr(boundary, op)(new_exec_id())
    assert err.value.reason == reason


def test_the_boundary_is_never_available(boundary):
    # available() -> True would put Core on the unverified MXC lifecycle path at all
    assert boundary.available() is False


def test_an_unnamed_capability_inventory_is_the_only_answer(boundary):
    # §4.9: a capability found here is a design change, not a setting
    assert boundary.capability_grants() == ()


@pytest.mark.parametrize('op', ['create_profile', 'delete_profile', 'derive',
                                'derive_sid', 'profile_exists'])
def test_the_principal_is_validated_before_the_seam_is_touched(boundary, monkeypatch, op):
    # dropping `validated_profile(...)` would hand a caller-supplied name to MXC
    seen = []

    def guard(key):
        seen.append(key)
        raise iso.IsolationUnavailable('profile_name', 'not a principal')
    monkeypatch.setitem(BLOCK, 'validated_profile', guard)
    with pytest.raises(iso.IsolationUnavailable) as err:
        getattr(boundary, op)('made-up-name')
    assert err.value.reason == 'profile_name' and seen == ['made-up-name']


def test_a_real_key_passes_the_real_guard_and_reaches_the_seam(boundary):
    # the guard validates, it does not veto: what the validator accepts gets to MXC
    key = iso.Principal('exec', ids.new_id('execution'), 0).key
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.create_profile(key)
    assert err.value.reason == 'mxc_lifecycle_unverified'


# ── 2. create_job: fail closed, and never leak the handle (1916-1941) ─────────

def _job_answers(win32):
    """The happy call set of `create_job`, up to the `job_facts` read-back."""
    win32.answer('_CreateJobObjectW', 0x77)
    win32.answer('_SetHandleInformation', 1)
    win32.answer('_SetInformationJobObject', 1)
    win32.closes()


def test_a_job_that_could_not_be_created_is_refused_without_a_close(boundary, win32):
    # `_CreateJobObjectW` answers NULL: there is nothing to close, and nothing to keep
    win32.answer('_CreateJobObjectW', 0)
    win32.closes()
    win32.error = 5
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.create_job(new_exec_id())
    assert err.value.reason == 'job_create' and 'winerror=5' in err.value.detail
    assert win32.closed == [] and win32.calls.get('_SetInformationJobObject') is None


@pytest.mark.parametrize('label,facts', [
    ('wrong-type', {'type': 'File', 'name': '', 'inheritable': False}),
    ('unnamed-query', {'type': None, 'name': '', 'inheritable': False}),
    ('named', {'type': 'Job', 'name': '\\BaseNamedObjects\\shared', 'inheritable': False}),
    ('name-unknown', {'type': 'Job', 'name': None, 'inheritable': False}),
    ('inheritable', {'type': 'Job', 'name': '', 'inheritable': True})],
    ids=['wrong-type', 'unnamed-query', 'named', 'name-unknown', 'inheritable'])
def test_a_job_that_is_not_unnamed_and_unshared_is_closed_and_refused(
        boundary, win32, monkeypatch, label, facts):
    # R6-A: Core must hold one unnamed, non-inheritable Job; anything else is refused
    _job_answers(win32)
    asked = []

    def job_facts(self, handle):
        asked.append(handle)
        return dict(facts)
    monkeypatch.setattr(BOUNDARY, 'job_facts', job_facts)
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.create_job(new_exec_id())
    assert err.value.reason == 'job_limits' and asked == [0x77]
    assert win32.closed == [0x77]


@pytest.mark.parametrize('label,failing,api', [
    ('inherit-flag', '_SetHandleInformation', 'SetHandleInformation'),
    ('limits', '_SetInformationJobObject', 'SetInformationJobObject'),
])
def test_a_job_that_could_not_be_configured_is_closed_and_refused(
        boundary, win32, label, failing, api):
    # the handle exists here, so refusing it without closing leaks a Job Core made
    win32.answer('_CreateJobObjectW', 0x77)
    win32.answer('_SetHandleInformation', 1)
    win32.answer('_SetInformationJobObject', 1)
    win32.answer(failing, 0)
    win32.error = 6
    win32.closes()
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.create_job(new_exec_id())
    assert err.value.reason == 'winapi' and err.value.name.startswith(api)
    assert win32.closed == [0x77]                       # the Job Core made is closed


def test_a_verifier_job_without_the_facts_is_closed_like_any_other(boundary, win32, monkeypatch):
    # the budget branch of `create_job` is not a second, gentler gate (T-090's values
    # are asserted in test_pv20_isolation.py; what is new here is that it still refuses)
    _job_answers(win32)
    monkeypatch.setattr(BOUNDARY, 'job_facts', lambda self, h: {
        'type': 'Job', 'name': '\\BaseNamedObjects\\shared', 'inheritable': True})
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.create_job(new_verify_key())
    assert err.value.reason == 'job_limits' and win32.closed == [0x77]


# ── 3. the Job facts and its accounting (1943-1966) ───────────────────────────

@pytest.mark.parametrize('label,flags,inheritable', [
    ('plain', 0x0, False), ('inherit', 0x1, True), ('both', 0x3, True),
    ('protect-only', 0x2, False),
])
def test_the_inheritable_fact_is_the_inherit_bit_alone(
        boundary, monkeypatch, label, flags, inheritable):
    monkeypatch.setattr(BOUNDARY, '_obj_type', lambda self, h: 'Job')
    monkeypatch.setattr(BOUNDARY, '_obj_name', lambda self, h: '')
    monkeypatch.setattr(BOUNDARY, '_handle_flags', lambda self, h: flags)
    assert boundary.job_facts(0x11) == {'type': 'Job', 'name': '',
                                        'inheritable': inheritable}


@pytest.mark.skipif(iso.WindowsBoundary is None, reason='reads a real ctypes buffer')
def test_a_named_object_is_read_through_the_pointer_in_the_first_field(boundary, win32):
    import ctypes
    name = r'\BaseNamedObjects\probe'

    def query(handle, info_class, buf, size, got):
        # NtQueryObject's layout: Length, MaximumLength, 4 bytes of padding, Buffer, then
        # the characters Buffer points at (what the type query's reader already relies on)
        base, text = ctypes.addressof(buf), name.encode('utf-16-le')
        ctypes.memmove(base + 16, text, len(text))
        ctypes.c_ushort.from_address(base).value = len(text)
        ctypes.c_ushort.from_address(base + 2).value = len(text)
        ctypes.c_void_p.from_address(base + 8).value = base + 16
        return 0
    win32.answer('_QueryObject', query)
    assert boundary._obj_name(0x11) == name


def test_no_handle_is_no_facts(boundary):
    # a Job handle Core does not have is reported as unknown, never as unnamed+free
    assert boundary.job_facts(None) is None


def test_handle_flags_refuse_to_answer_as_zero(boundary, win32):
    # `GetHandleInformation` failing must not read as "not inheritable"
    win32.answer('_GetHandleInformation', 0)
    win32.error = 6
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary._handle_flags(0x11)
    assert err.value.reason == 'handle_state' and 'winerror=6' in err.value.detail


def test_active_processes_are_read_as_the_accounting_reports_them(boundary, win32):
    seen = win32.answer('_QueryInformationJobObject',
                        lambda *a: (setattr(a[2]._obj, 'ActiveProcesses', 5) or 1))
    assert boundary.job_active_processes(0x77) == 5
    (job, cls, ref, size, got), = seen
    assert (job, cls, got) == (0x77, 1, None)          # JobObjectBasicAccountingInformation


def test_active_processes_that_cannot_be_read_are_not_zero(boundary, win32):
    # 0 active processes would read as an empty Job the fence would accept
    win32.answer('_QueryInformationJobObject', 0)
    win32.error = 5
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.job_active_processes(0x77)
    assert err.value.reason == 'winapi' and 'QueryInformationJobObject' in str(err.value)


# ── 4. assignment and the two closings (1962-1974) ────────────────────────────

def test_assigning_without_a_job_is_refused_before_the_call(boundary, win32):
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.assign_job(None, 0x51)
    assert err.value.reason == 'job_missing'
    assert win32.calls.get('_AssignProcessToJobObject') is None


def test_an_assignment_that_is_refused_is_an_isolation_failure(boundary, win32):
    win32.answer('_AssignProcessToJobObject', 0)
    win32.error = 5
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.assign_job(0x77, 0x51)
    assert err.value.reason == 'winapi' and 'AssignProcessToJobObject' in str(err.value)


@pytest.mark.parametrize('op', ['close_job', 'close_handle'])
def test_closing_nothing_reaches_nothing(boundary, win32, op):
    # CloseHandle(None) would close whatever handle 0 turns out to be, or fail silently
    win32.closes()
    getattr(boundary, op)(None)
    assert win32.closed == []


@pytest.mark.parametrize('op', ['close_job', 'close_handle'])
def test_a_handle_is_closed_exactly_once(boundary, win32, op):
    win32.closes()
    getattr(boundary, op)(0x77)
    assert win32.closed == [0x77]


def test_a_job_handle_report_keeps_only_jobs_and_closes_everything(
        boundary, monkeypatch, win32):
    # §3.7/R6-A sole-holder evidence: the enumeration's duplicates are Core's to close
    handles = [1, 2, 3]
    kinds = {1: 'Job', 2: 'File', 3: 'Job'}
    monkeypatch.setattr(BOUNDARY, '_handles_of', lambda self, pid: list(handles))
    monkeypatch.setattr(BOUNDARY, '_obj_type', lambda self, h: kinds[h])
    monkeypatch.setattr(BOUNDARY, '_obj_name', lambda self, h: '')
    monkeypatch.setattr(BOUNDARY, '_handle_flags', lambda self, h: 0)
    win32.closes()
    out = boundary.job_handles_of(4242)
    assert [h['handle'] for h in out] == [1, 3] and all(h['type'] == 'Job' for h in out)
    assert win32.closed == [1, 2, 3]


# ── 5. the token read (2080-2097) and its buffers (2118-2158) ─────────────────

def test_a_process_whose_token_cannot_be_opened_is_never_reported(boundary, win32):
    win32.answer('_OpenProcess', 0)
    win32.error = 5
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.token(4242)
    assert err.value.reason == 'token' and 'winerror=5' in err.value.detail
    assert win32.closed == []


def test_a_token_that_cannot_be_opened_still_closes_the_process(boundary, win32):
    win32.answer('_OpenProcess', 0x51)
    win32.answer('_OpenProcessToken', 0)
    win32.error = 5
    win32.closes()
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.token(4242)
    assert err.value.reason == 'winapi' and 'OpenProcessToken' in str(err.value)
    assert win32.closed == [0x51]                       # the process handle, never leaked


def test_a_token_handle_that_was_never_handed_over_is_not_closed(boundary, win32, monkeypatch):
    # `if tok:` is the guard: closing handle 0 would close something Core does not own
    win32.answer('_OpenProcess', 0x51)
    win32.answer('_OpenProcessToken', 1)                 # leaves tok as HANDLE() -> falsy
    win32.closes()
    monkeypatch.setattr(BOUNDARY, '_token_sid', lambda self, tok, cls: None)
    monkeypatch.setattr(BOUNDARY, '_token_flag', lambda self, tok, cls: 0)
    monkeypatch.setattr(BOUNDARY, '_token_integrity', lambda self, tok: None)
    monkeypatch.setattr(BOUNDARY, '_token_groups', lambda self, tok, cls: [])
    assert boundary.token(4242)['user_sid'] is None
    assert win32.closed == [0x51]                        # the process handle only


def test_the_token_report_carries_both_group_classes(boundary, win32, monkeypatch):
    win32.answer('_OpenProcess', 0x51)
    win32.answer('_OpenProcessToken', lambda *a: (setattr(a[2]._obj, 'value', 0x99) or 1))
    win32.closes()
    monkeypatch.setattr(BOUNDARY, '_token_sid',
                        lambda self, tok, cls: 'S-1-15-2-9' if cls == 31 else 'S-1-5-21-1')
    monkeypatch.setattr(BOUNDARY, '_token_flag', lambda self, tok, cls: 0)
    monkeypatch.setattr(BOUNDARY, '_token_integrity', lambda self, tok: '0x2000')
    monkeypatch.setattr(BOUNDARY, '_token_groups',
                        lambda self, tok, cls: ['S-1-15-3-1'] if cls == 30 else ['S-1-5-11'])
    tok = boundary.token(4242)
    assert tok['user_sid'] == 'S-1-5-21-1' and tok['ac_sid'] == 'S-1-15-2-9'
    assert tok['is_appcontainer'] == 0 and tok['integrity'] == '0x2000'
    assert tok['capability_sids'] == ['S-1-15-3-1', 'S-1-5-11']     # both classes, in order
    assert win32.closed == [0x99, 0x51]


@pytest.mark.parametrize('reader,answer', [
    ('_token_sid', None), ('_token_flag', None), ('_token_groups', [])],
    ids=['no-sid', 'no-appcontainer-flag', 'no-groups'])
def test_a_token_that_refuses_to_be_read_reads_as_unknown(boundary, win32, reader, answer):
    # ERROR_INSUFFICIENT_BUFFER is the only reason to retry; anything else stops here
    calls = win32.answer('_GetTokenInformation', 0)
    win32.error = 5
    assert getattr(boundary, reader)(0x99, 1) == answer
    assert len(calls) == 1                              # one attempt, never a retry loop


def test_a_buffer_that_never_fits_gives_up_and_says_nothing(boundary, win32):
    # the grow-and-retry loop is bounded at 4: an OS that never answers cannot spin here
    calls = win32.answer('_GetTokenInformation', 0)
    win32.error = 122
    buf, got = BOUNDARY()._token_buffer(0x99, 1)
    assert (buf, got) == (None, None) and len(calls) == 4


def test_a_null_sid_pointer_is_answered_without_calling_the_api(boundary, win32):
    # `_ConvertSidToStringSidW` on a NULL SID would be a call on nothing
    assert BLOCK['_sid_str'](None) is None and BLOCK['_sid_str'](0) is None
    assert win32.reached() == {}


# ── 6. the identity read is an observation or nothing (2098-2116) ─────────────

CREATE = 0x01DB123489ABCDEF


def proc(**changes):
    p = SimpleNamespace(pid=4242, create_time=CREATE,
                        observed_backend='processcontainer', observed_tier='base-container')
    for name, value in changes.items():
        setattr(p, name, value)
    return p


def arm_identity(monkeypatch, started, token):
    left = list(started)

    def process_started(self, pid):
        if not left:
            pytest.fail('process_started was asked more often than the branch needs')
        return left.pop(0)
    monkeypatch.setattr(BOUNDARY, 'process_started', process_started)
    monkeypatch.setattr(BOUNDARY, 'token', lambda self, pid: dict(token))
    return left


@pytest.mark.parametrize('label,started,changes,cause', [
    ('no-process', [None], {}, 'dead or reused identity owner'),
    ('reused-pid', [CREATE + 1], {}, 'dead or reused identity owner'),
    ('changed-mid-read', [CREATE, CREATE + 1], {}, 'identity owner changed during inspection'),
    ('appcontainer-unknown', [CREATE, CREATE], {'token': {'is_appcontainer': None}},
     'incomplete native token report'),
    ('appcontainer-out-of-range', [CREATE, CREATE], {'token': {'is_appcontainer': 2}},
     'incomplete native token report'),
    ('no-integrity', [CREATE, CREATE], {'token': {'integrity': None}},
     'incomplete native token report'),
    ('backend-requested', [CREATE, CREATE], {'proc': {'observed_backend': None}},
     'UNVERIFIED: effective backend/tier'),
    ('tier-requested', [CREATE, CREATE], {'proc': {'observed_tier': 'lite-container'}},
     'UNVERIFIED: effective backend/tier')],
    ids=['no-process', 'reused-pid', 'changed-mid-read', 'appcontainer-unknown',
         'appcontainer-out-of-range', 'no-integrity', 'backend-requested', 'tier-requested'])
def test_read_identity_refuses_what_it_cannot_observe(monkeypatch, label, started, changes, cause):
    token = changes.get('token', {})
    left = arm_identity(monkeypatch, started, token_report(**token))
    with pytest.raises(mxc.MxcUnavailable) as err:
        BOUNDARY().read_identity(proc(**changes.get('proc', {})))
    assert cause in str(err.value) and left == []


def test_read_identity_reports_only_what_it_observed(monkeypatch):
    left = arm_identity(monkeypatch, [CREATE, CREATE],
                        token_report(is_appcontainer=1, ac_sid='S-1-15-2-9'))
    report = BOUNDARY().read_identity(proc())
    assert isinstance(report, mxc.IdentityReport)
    assert (report.pid, report.create_time) == (4242, CREATE)
    assert (report.user_sid, report.is_appcontainer, report.ac_sid) == (
        'S-1-5-21-7-8-9-1001', True, 'S-1-15-2-9')
    assert (report.integrity, report.backend, report.tier) == (
        '0x2000', 'processcontainer', 'base-container')
    assert report.capability_sids == ('S-1-15-3-1',) and left == []


# ── 7. the launch seam (2232-2252) ───────────────────────────────────────────

def test_nothing_launches_before_a_closed_mxc_policy_exists(boundary, win32):
    # the one path that would start a process is closed to every caller
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.launch(['x.exe'], cwd='.', env={}, profile='archeus.exec.x',
                        job=0x77, stdin=1, stdout=2)
    assert err.value.reason == 'mxc_policy_required'
    assert win32.reached() == {}                      # no CreateProcessW, no CreateFileW


@pytest.mark.parametrize('label,handle', [
    ('null', 0), ('invalid', -1), ('32bit', 0xFFFFFFFF), ('64bit', 0xFFFFFFFFFFFFFFFF)])
def test_a_stdio_handle_that_is_not_a_handle_is_refused(boundary, win32, tmp_path, label, handle):
    # an unchecked INVALID_HANDLE_VALUE would be handed to the child as its stdio
    win32.answer('_CreateFileW', handle)
    win32.error = 2
    with pytest.raises(iso.IsolationUnavailable) as err:
        boundary.open_inherited(str(tmp_path / 'stdio-out'), 'append')
    assert err.value.reason == 'stdio' and '(2)' in err.value.detail


@pytest.mark.parametrize('mode,access,creation', [
    ('read', 0x80000000 | 0x80, 3), ('append', 0x40000000 | 0x4 | 0x80, 4)])
def test_the_stdio_open_asks_for_what_its_mode_means(tmp_path, win32, mode, access, creation):
    # never inherited (bInheritHandle 0, share 3, security attrs NULL): transport whitelists
    path = str(tmp_path / 'stdio-stream')
    seen = win32.answer('_CreateFileW', 0x33)
    assert BOUNDARY().open_inherited(path, mode) == 0x33
    (got_path, got_access, share, sa, disp, attrs, tmpl), = seen
    assert os.path.normcase(got_path) == os.path.normcase(os.path.abspath(path))
    assert (got_access, share, sa, disp, attrs, tmpl) == (access, 3, None, creation, 1, None)


def test_spawn_turns_an_mxc_refusal_into_an_isolation_failure(monkeypatch, win32):
    asked = []

    def refuse(policy, *, exe, job, backend=None, native_run=False):
        asked.append((policy, exe, job, backend, native_run))
        raise mxc.MxcUnavailable('native MXC execution disabled')
    monkeypatch.setattr(mxc, 'spawn', refuse)
    b = BOUNDARY(backend='synthetic-backend', native_run=True)
    with pytest.raises(iso.IsolationUnavailable) as err:
        b.spawn('policy', exe='x.exe', job=0x77)
    assert err.value.reason == 'mxc' and isinstance(err.value.__cause__, mxc.MxcUnavailable)
    assert asked == [('policy', 'x.exe', 0x77, 'synthetic-backend', True)]


def test_spawn_hands_the_backend_it_was_built_with(monkeypatch, win32):
    asked = []

    def backend_spawn(policy, *, exe, job, backend=None, native_run=False):
        asked.append((backend, native_run))
        return 'child'
    monkeypatch.setattr(mxc, 'spawn', backend_spawn)
    assert BOUNDARY(backend='synthetic-backend', native_run=False).spawn(
        'policy', exe='x.exe', job=0x77) == 'child'
    assert asked == [('synthetic-backend', False)]


# ── the line numbers this file and the report quote ───────────────────────────

@pytest.mark.parametrize('method,line', [
    ('_sid_str', 2126), ('available', 2139), ('create_profile', 2147),
    ('create_job', 2170), ('job_facts', 2197), ('job_active_processes', 2206),
    ('assign_job', 2216), ('close_job', 2228), ('close_handle', 2233),
    ('job_handles_of', 2265), ('_handle_flags', 2302), ('token', 2341),
    ('read_identity', 2359), ('_token_buffer', 2420), ('capability_grants', 2432),
    ('open_inherited', 2494), ('launch', 2504), ('spawn', 2508),
])
def test_the_branches_quoted_here_are_where_this_file_says_they_are(method, line):
    assert _definition_line(method) == line
