r"""T-1021 — the second gap sweep over `archeus/node/mxc.py`, slice lines 1-240.

CHOSEN BRANCHES (risk-ranked; refusals first, then boundaries). Selection was measured, not
assumed: a `sys.settrace` line/arc trace over the four reference suites (test_node_mxc.py,
test_node_mxc_policy.py, test_node_mxc_gaps.py, test_pv20_mxc_policy_b4.py; 498 passed,
51 skipped) shows every line of 1-240 executed EXCEPT 53-56, the `os.name == 'nt'` gate in
`_path` — its only coverage lives behind `skipif(os.name != 'nt')`. A mutation run over the
same suites (each condition inverted/removed once, whole suite re-executed) left exactly four
in-slice survivors besides that gate: the process-section key-set (198), the `_text` leg of
`_path` (46), the anonymous-password conjunct of the proxy rule (168), and the raw-dict
disjunct of `validate_policy` (182). Entries 1-9 are those refusals; entry 10 is the gate's
accept side.

    1  mxc.py:198-202   `set(p) != {...}`                     a process dict with an extra or
       missing key must not validate — the key-set gate is the contract that no smuggled
       field (integrity level, token, network flag) reaches the launcher.
    2  mxc.py:55        `':' in rest`                         an ADS name (`::$INDEX_ALLOCATION`,
       `file:stream`) over a granted directory — the review R9 alias class.
    3  mxc.py:55        segment ends with '.'                  `C:\ws.` resolves to the grant
       itself on Win32 yet slips past the string overlap gate (commonpath sees a sibling).
    4  mxc.py:55        segment ends with ' '                  `C:\ws ` — same, via trailing space.
    5  mxc.py:54        drive-shape gate                       `\\?\C:\`, UNC, `\x`, `1:\x`:
       forms whose overlap check `commonpath` raises on, so the gate is the only refusal.
    6  mxc.py:46        `not _text(value)` (NUL)               a NUL would truncate the name at
       the OS open boundary while every string comparison kept the full path.
    7  mxc.py:43-47     `not _text(value)` (bytes)             `os.fspath` accepts bytes; only
       the text check keeps a byte path out of the document — and it must be a policy error,
       not a leaked `TypeError`.
    8  mxc.py:168       `not url.password`                     `http://:pw@127.0.0.1:18080` —
       credentials must not ride in the proxy URL that lands in the policy document.
    9  mxc.py:182       `not isinstance(policy.raw, dict)`     a MxcPolicy carrying a non-dict
       must refuse as "not a policy", not die deeper with the wrong error class.
    10 mxc.py:53-57     nt-gate accept side + scan order       clean drive paths must PASS the
       gate, ancestors before contents, writable grants before readonly ones.

No Windows is required: `mxc.os` is swapped at the same monkeypatch seams the existing suites
use (module attributes, `linkscan.multi_linked_files`, `FakeMxc`, `object.__new__`), with path
rules delegated to pure-Python `ntpath` — the same implementation Windows' `os.path` is — and
lstat/scandir served from an in-memory tree. Every test here runs, and must pass, identically
on Linux and on the Windows review run; nothing skips.

Card probes 5-10 (deny/rw overlap, ro overlap, empty grants, bad proxy, UI refusal, schema
error) were dropped as already covered: the trace shows their lines/arcs executed and every
targeted mutant against their existing assertions (both `_within` directions of 226/228, the
cwd-in-grants disjunct 223, the empty-rw gate 214, each proxy conjunct 165-171, the UI
conjuncts 126-128, each schema disjunct) FAILS the existing suites. Evidence in the T-1021
report.
"""

import ntpath
import os
import stat
from types import SimpleNamespace

import pytest

from archeus.node import linkscan, mxc
from archeus.node.mxc import MxcUnavailable as ERROR

BASE_ENV = {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\Users\\t\\AppData'}

# ── the posix side (no OS faked): entries 6-9 ──────────────────────────────────────────


def policy(tmp_path, **changes):
    (tmp_path / 'work').mkdir(exist_ok=True)
    args = dict(workspace=str(tmp_path / 'work'), cwd=str(tmp_path / 'work'),
                command_line='agent.exe /d /c echo fixture', env=BASE_ENV, timeout_ms=1000)
    args.update(changes)
    return mxc.compile_policy(**args)


class Forbidden(mxc.FakeMxc):
    """A backend that reports being reached as a failure (same shape as test_node_mxc_gaps)."""

    def spawn(self, policy, *, exe, job, before_resume=None):
        pytest.fail('the launcher was reached; the privileged call was not refused')


def test_a_field_outside_the_process_contract_never_reaches_a_backend(tmp_path):
    """Entry 1 · mxc.py:198 `set(p) != {'commandLine','cwd','env','inheritDefaultEnv','timeout'}`.

    Existing: every legal shape is pinned and the value gates (155-161, 204-212) are mutation-
    killed, but no existing case changes the process dict's KEY SET — deleting that whole
    comparison survives every existing test. A smuggled field or a dropped contract field would
    launch. Closes the gap through the launch path itself, so a refusal that only existed in
    compile would also fail here."""
    smuggled = policy(tmp_path)
    smuggled.raw['process']['highIntegrity'] = True
    with pytest.raises(ERROR, match='invalid process policy'):
        mxc.spawn(smuggled, exe='unused', job=object(), backend=Forbidden())
    missing = policy(tmp_path)
    del missing.raw['process']['cwd']
    with pytest.raises(ERROR, match='invalid process policy'):
        # without the key-set gate this dies deeper with a KeyError, not a policy refusal
        mxc.spawn(missing, exe='unused', job=object(), backend=Forbidden())


class BytesPath:
    def __fspath__(self):
        return b'/work/secrets'


def test_a_nul_byte_in_a_policy_path_refuses_at_compile(tmp_path):
    """Entry 6 · mxc.py:46 `not _text(value)`. The suite's NUL coverage is all command
    line/env (mxc.py:144, 155); no existing test puts a NUL in a POLICY path, and dropping
    the `_text` leg there survives every existing test because `os.path.isabs` alone still
    catches the ''/relative cases. A name like 'secrets\\0evil' compares as one string and
    opens as another — truncation at the OS boundary, the alias class the gate exists for."""
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    truncated = str(tmp_path / 'secrets') + '\x00evil'
    with pytest.raises(ERROR, match='must be absolute'):
        policy(tmp_path, denied=(truncated,))
    with pytest.raises(ERROR, match='must be absolute'):
        policy(tmp_path, cwd=str(work) + '\x00')
    # the refusal must not be the blanket "anything wrong" path: a clean policy still compiles
    assert policy(tmp_path).raw['filesystem']['deniedPaths'] == []


def test_a_bytes_policy_path_is_refused_as_a_policy_error_not_a_type_error(tmp_path):
    """Entry 7 · mxc.py:43-47, the same `_text` leg seen from the fspath side. The existing
    closest test (test_node_mxc_policy.py:424 `test_a_path_that_is_not_text_is_refused`)
    accepts `(ERROR, TypeError)`, so an implementation that leaks a raw TypeError — or, with
    the `_text` leg deleted, serializes bytes into the document — passes it just as well.
    This pins the seam's promise: a malformed path is always MxcUnavailable, always the
    path-refusal message."""
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    with pytest.raises(ERROR, match='must be absolute'):
        policy(tmp_path, denied=(b'/work/secrets',))
    with pytest.raises(ERROR, match='must be absolute'):
        policy(tmp_path, denied=(BytesPath(),))
    with pytest.raises(ERROR, match='must be absolute'):
        policy(tmp_path, cwd=object())


def test_a_proxy_url_with_an_anonymous_password_refuses(tmp_path):
    """Entry 8 · mxc.py:168 `not url.password`. Existing cases cover no-credentials,
    username-only (`http://user@...`) and user:pass TOGETHER — so the username conjunct
    short-circuits before the password one is ever load-bearing: replacing `not url.password`
    with True survives every existing test, and `http://:pw@127.0.0.1:18080` — an
    anonymous-password URL whose credential lands verbatim in the policy document — compiles."""
    with pytest.raises(ERROR, match='loopback HTTP endpoint'):
        policy(tmp_path, proxy_url='http://:pw@127.0.0.1:18080')
    made = policy(tmp_path, proxy_url='http://127.0.0.1:18080')
    assert made.raw['runtimeConfig']['networkProxy'] == 'http://127.0.0.1:18080'


def test_a_policy_object_carrying_a_non_dict_never_validates(tmp_path):
    """Entry 9 · mxc.py:182 `or not isinstance(policy.raw, dict)`. The existing refusal tests
    only pass NON-MxcPolicy objects (None, {}, list, 'policy'), which die on the first
    disjunct; the second disjunct is dead across the suite (its mutant survives). A MxcPolicy
    whose raw is a string must be refused as "not a policy" — not as a substring match, not as
    a TypeError, not deeper inside the field checks with the wrong error class. Seam:
    `object.__new__`, as in test_pv20_mxc_policy_b4.py's _loose."""
    for not_a_dict in ('{"proxy": true}', 42):
        loose = object.__new__(mxc.MxcPolicy)
        object.__setattr__(loose, 'raw', not_a_dict)
        with pytest.raises(ERROR, match='MxcPolicy object required'):
            mxc.validate_policy(loose)
    loose = object.__new__(mxc.MxcPolicy)
    object.__setattr__(loose, 'raw', '{"runtimeConfig": {}}')
    with pytest.raises(ERROR, match='MxcPolicy object required'):
        mxc.spawn(loose, exe='unused', job=object(), backend=Forbidden())


# ── the faked nt side: entries 2-5 and 10 (no skipif: this IS how Windows behaves here) ─


WIN_RW = 'C:\\ws'
WIN_RO = 'C:\\tools'
WIN_ENV = {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': 'C:\\ws\\config'}


class _Listing:
    def __init__(self, children):
        self._children = list(children)

    def __enter__(self):
        return [SimpleNamespace(path=child) for child in self._children]

    def __exit__(self, *exc):
        return False


def fake_windows(monkeypatch, directories, files):
    """The `os` seam `mxc` sees: ntpath (Windows' own pure-Python path rules) for the name
    grammar, an in-memory tree for lstat/scandir, plus the linkscan seam the gaps tests
    already use. Returns the lstat call order so tests can assert the scan's shape."""
    tree = {ntpath.normcase('C:\\'): ('dir', [])}

    def ensure(directory):
        key = ntpath.normcase(directory)
        if key not in tree:
            parent = ntpath.dirname(directory)
            ensure(parent)
            tree[key] = ('dir', [])
            tree[ntpath.normcase(parent)][1].append(directory)
        return key

    for directory in directories:
        ensure(directory)
    for name in files:
        parent_key = ensure(ntpath.dirname(name))
        tree[parent_key][1].append(name)
        tree[ntpath.normcase(name)] = ('file', [])

    calls = []

    def lstat(path):
        calls.append(str(path))
        entry = tree.get(ntpath.normcase(path))
        if entry is None:
            raise OSError(2, 'fake windows: no such file: %r' % (path,))
        mode = stat.S_IFDIR if entry[0] == 'dir' else stat.S_IFREG
        return SimpleNamespace(st_mode=mode, st_nlink=1, st_file_attributes=0)

    def scandir(path):
        entry = tree.get(ntpath.normcase(path))
        if entry is None or entry[0] != 'dir':
            raise OSError(2, 'fake windows: not a directory: %r' % (path,))
        return _Listing(entry[1])

    path_rules = SimpleNamespace(
        isabs=ntpath.isabs, normpath=ntpath.normpath, splitdrive=ntpath.splitdrive,
        normcase=ntpath.normcase, commonpath=ntpath.commonpath, dirname=ntpath.dirname,
        join=ntpath.join,
        isdir=lambda p: tree.get(ntpath.normcase(p), ('?',))[0] == 'dir')
    monkeypatch.setattr(mxc, 'os', SimpleNamespace(
        name='nt', fspath=os.fspath, PathLike=os.PathLike,
        path=path_rules, lstat=lstat, scandir=scandir))
    monkeypatch.setattr(linkscan, 'multi_linked_files', lambda root: [])
    return calls


def windows_fixture(monkeypatch, readonly=()):
    return fake_windows(monkeypatch, [WIN_RW] + list(readonly),
                        [WIN_RW + '\\readme.txt'] + [r + '\\tool.exe' for r in readonly])


def compile_windows(**changes):
    args = dict(workspace=WIN_RW, cwd=WIN_RW, command_line='agent.exe /d /c echo fixture',
                env=WIN_ENV, timeout_ms=1000)
    args.update(changes)
    return mxc.compile_policy(**args)


def test_an_alternate_data_stream_name_refuses_under_the_nt_gate(monkeypatch):
    r"""Entry 2 · mxc.py:55 `':' in rest`. Existing ADS coverage is two `skipif(os.name!='nt')`
    cases that assert only "some MxcUnavailable", and the line never executes on Linux. This
    pins the class the alias actually enables: `C:\ws::$INDEX_ALLOCATION` NAMES THE GRANT ITSELF
    under Win32, yet the string overlap gate sees a sibling (commonpath answers 'c:\\'), so the
    gate is the only refusal; the `file:stream` form stands outside every grant entirely."""
    windows_fixture(monkeypatch)
    with pytest.raises(ERROR, match='plain drive paths'):
        compile_windows(denied=(WIN_RW + '::$INDEX_ALLOCATION',))
    with pytest.raises(ERROR, match='plain drive paths'):
        compile_windows(denied=('C:\\other\\report.txt:secrets',))
    made = compile_windows(denied=('C:\\other\\private',))
    assert made.raw['filesystem']['deniedPaths'] == ['C:\\other\\private']


def test_a_trailing_dot_alias_refuses_under_the_nt_gate(monkeypatch):
    r"""Entry 3 · mxc.py:55 `s[-1] in '. '` (dot). The only existing case is a suffix
    sweep that skips unless os.name=='nt' — and, for paths inside a grant, the overlap
    gate would catch the sibling spellings anyway. The load-bearing case is the alias of
    the grant itself: `C:\ws.` resolves to `C:\ws` on Win32 while commonpath sees two
    siblings, so without this clause a denied name could name the writable root. The
    mid-path form (`mid.\leaf`, outside every grant) proves every segment is checked."""
    windows_fixture(monkeypatch)
    with pytest.raises(ERROR, match='plain drive paths'):
        compile_windows(denied=(WIN_RW + '.',))
    with pytest.raises(ERROR, match='plain drive paths'):
        compile_windows(denied=('C:\\other\\mid.\\leaf',))
    made = compile_windows(denied=('C:\\other\\mid\\leaf',))
    assert made.raw['filesystem']['deniedPaths'] == ['C:\\other\\mid\\leaf']


def test_a_trailing_space_alias_refuses_under_the_nt_gate(monkeypatch):
    r"""Entry 4 · mxc.py:55 `s[-1] in '. '` (space). Same skip situation as the dot entry;
    `os.path.normpath` keeps the trailing space, so only this clause refuses `C:\ws `,
    which Win32 resolves to the grant itself — and the mid-path form proves the check
    is not just the last component."""
    windows_fixture(monkeypatch)
    with pytest.raises(ERROR, match='plain drive paths'):
        compile_windows(denied=(WIN_RW + ' ',))
    with pytest.raises(ERROR, match='plain drive paths'):
        compile_windows(denied=('C:\\other\\mid \\leaf',))
    made = compile_windows(denied=('C:\\other\\private',))
    assert made.raw['filesystem']['deniedPaths'] == ['C:\\other\\private']


@pytest.mark.parametrize('form', [
    '\\\\?\\C:\\evil',        # the \\?\ extended form commonpath cannot compare
    '\\\\server\\share\\x',   # UNC
    '\\x',                    # root-relative, driveless
    '1:\\x',                  # a digit passes Windows' isabs regex but is no drive letter
], ids=['extended', 'unc', 'rootless', 'digit-drive'])
def test_a_non_drive_absolute_form_refuses_under_the_nt_gate(monkeypatch, form):
    r"""Entry 5 · mxc.py:54 `not (len(drive)==2 and drive[1]==':' and drive[0].isascii()
    and drive[0].isalpha())`. The existing forms test only via `skipif(os.name!='nt')` with
    a bare MxcUnavailable match; on Linux the whole clause never executes and its mutant
    (drop the drive-shape gate) survives every test that runs. These forms are exactly the
    ones whose overlap check `commonpath` REJECTS with ValueError (different drives /
    incomparable roots) — an implementation without the gate accepts them and the grant
    overlap goes unchecked."""
    windows_fixture(monkeypatch)
    with pytest.raises(ERROR, match='plain drive paths'):
        compile_windows(denied=(form,))


def test_clean_windows_grants_pass_the_nt_gate_in_scan_order(monkeypatch):
    r"""Entry 10 · mxc.py:53-57 accept side + 76-107 walk order. The gate's pass-through
    arc executes nowhere in this container (the only control test skips on Linux), and no
    running test fixes the shape of the scan: ancestors before the grant, the grant before
    its contents, writable grants before readonly ones — the order that makes "refuse before
    opening anything" observable. A gate that refused everything would also flip the entire
    Windows suite red, but only this control catches it on Linux."""
    calls = windows_fixture(monkeypatch, readonly=[WIN_RO])
    made = compile_windows(readonly=(WIN_RO,), denied=('C:\\other\\private',))
    assert made.raw['filesystem']['readwritePaths'] == [WIN_RW]
    assert made.raw['filesystem']['readonlyPaths'] == [WIN_RO]
    assert made.raw['filesystem']['deniedPaths'] == ['C:\\other\\private']
    assert made.raw['process']['cwd'] == WIN_RW
    assert calls[:2] == ['C:\\', WIN_RW]                  # the ancestor is inspected first
    assert calls.index(WIN_RW) < calls.index(WIN_RW + '\\readme.txt')
    assert calls.index(WIN_RW + '\\readme.txt') < calls.index(WIN_RO)   # rw is scanned before ro
    assert calls.index(WIN_RO) < calls.index(WIN_RO + '\\tool.exe')
    # nothing outside the grants is opened — the denied path is never scanned
    assert not [c for c in calls if ntpath.normcase(c).startswith(ntpath.normcase('C:\\other'))]
