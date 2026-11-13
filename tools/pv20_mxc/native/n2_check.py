"""N2 native fixture-only check: the PRODUCTION MXC launch stack, driven once for real.

Not run by its author. It runs only after the owner has read the review sheet
(.collab/N2-review-sheet-2026-11-01.md) and authorised the run.

Usage:  python -m tools.pv20_mxc.native.n2_check <fixture-parent>
  Exactly one argument: a directory at or below the fixture base (fixture_base(): the
  ARCHEUS_FIXTURE_BASE variable, else pv20-fixtures next to the repository; letters, digits, dot,
  underscore, hyphen). The fixture root is safe_root(parent), a fresh uuid child with a
  marker, and remove_fixture(root) deletes it only when the whole run exits 0. The
  declared INCONCLUSIVE rows keep a clean run at exit 2, so the root is normally kept.
  The operator pre-stages the SDK at <parent>\\sdk\\node_modules\\@microsoft\\mxc-sdk
  (the same staging N1 and N3 used); this script copies it into the fresh root.

What it drives (production code, nothing re-implemented): mxc.compile_policy and
validate_policy, staging.stage_mxc and verify_mxc, win32_mxc.Win32Api (protected policy
file, pipes, suspended CreateProcessW), mxc_native.Backend (suspended create, Job
assign, membership verify, single resume), isolation.WindowsBoundary (the real
KILL_ON_JOB_CLOSE Job), mxc_ledger.Ledger and reconcile, mxc_cancel and local.MxcLaunch
(the end: revoke, end Job, quiescence, read-back, record). The only script-side
stand-ins are the ones the repository does not supply: the pinned schema validator
(returns True), the reviewed hash pins (computed from the staged copy), the resource
reader (launcher identity gone) and the workload outcome (launcher exit code). Each is
named in its row. The Job is ended by the boundary's own terminate_job, the production
default of MxcLaunch.

Safety posture: stdlib plus the production modules above; no network of any kind (every
policy denies egress and ingress); no ACL tool or API and no profile API; no process is
terminated unless this script created it and its creation time still matches (the Job
close is the kill); listing a directory is never used as evidence; command lines are
argv lists through list2cmdline (the fixture path has no spaces and no shell
metacharacters, refused at setup); every path a container is told about is under the
fresh root; the production modules are imported with every home, profile, temp and
config variable pointed at an empty folder inside the root, then restored, so nothing
reads the real profile at import; the host files the containers write are read back
only after an lstat (regular, single link, no reparse point). Only SystemRoot is read
from the environment, once, to name cmd.exe.

Diagnostic (--diag-descendants, optional --allow-image-copy and --allow-system32-ro): six rows
that tell a child's failure to start from its failure to write. Before any row is launched or
anything is copied, the System32 grant is pre-checked read-only with the production scans; a
refused grant leaves the C rows unlaunched ("not admissible"). The result is printed and written,
with every row's label, evidence and launcher exit code, to diag_results.json in the fixture root.
--diag-precheck alone runs only the argument checks and that pre-check: nothing is created.
Both are meant to be started with `python -B`: without it, importing the production modules may
write bytecode caches outside the fixture.

Exit codes: 0 all cases PASS / 1 first FAIL / 2 no FAIL but an INCONCLUSIVE is present
(a diagnostic run is always 2; --diag-precheck exits 2 when System32 is not admissible) /
3 setup error, budget overrun or a surviving launcher.
"""
import hashlib
import importlib
import json
import ntpath
import os
import re
import secrets
import stat
import subprocess
import sys
import time
import traceback
from collections import namedtuple
from types import SimpleNamespace

from tools.pv20_mxc.native import common
from tools.pv20_mxc.native.common import Recorder, StopRun, redact, remove_fixture, safe_root
from tools.pv20_mxc.protocol import STAGES

STAGE = 'N2'
SDK_TAIL = ('sdk', 'node_modules', '@microsoft', 'mxc-sdk')
SAFE_PARENT = re.compile(r'\A[A-Za-z]:\\[A-Za-z0-9_.\\-]+\Z')
SYSTEMROOT = re.compile(r'(?i)\A[A-Za-z]:\\windows\Z')
JOURNAL = 'n2_journal.jsonl'
BUDGET_S = 1100.0            # protocol.STAGES['N2'].budget is 1200
QUIESCE_S = 5.0
CHAIN_MAX = 6000             # well under the 8191 character cmd.exe limit
EVIDENCE_MAX = 65536
STILL_ACTIVE = 259
DIAG = '--diag-descendants'
IMAGE_FLAG, SYSTEM_FLAG = '--allow-image-copy', '--allow-system32-ro'
DIAG_FLAGS = (DIAG, IMAGE_FLAG, SYSTEM_FLAG)
DIAG_PRECHECK = '--diag-precheck'
RESULTS = 'diag_results.json'
RET_37, NOT_37 = 'returned 37', 'did not return 37'
W_OK, W_UNPROVED, W_NOT = 'started, write ok', 'started, write not proved', 'did not return code'
VOID_LABELS = frozenset({'control failed', 'no evidence', 'launch refused', 'not admissible',
                         'diagnostic error', 'not authorized'})
REPARSE = 0x400
HOME_VARS = ('USERPROFILE', 'HOME', 'HOMEPATH', 'TEMP', 'TMP', 'CLAUDE_CONFIG_DIR',
             'ARCHEUS_HOME', 'APPDATA', 'LOCALAPPDATA', 'XDG_CONFIG_HOME')
PROD = ('archeus.node.mxc', 'archeus.node.staging', 'archeus.node.win32_mxc',
        'archeus.node.mxc_ledger', 'archeus.node.isolation', 'archeus.node.local')
# the production ledger shapes (mxc_ledger._validate)
CLEAN = ['intent', 'ownership', 'disposal', 'completion']
QUARANTINED = ['intent', 'ownership', 'quarantine']
QUARANTINED_EARLY = ['intent', 'quarantine']
DEAD_UNVERIFIED, STILL_RUNNING, DEAD_CLEAN, UNKNOWN_OWNER = (
    'DEAD_UNVERIFIED', 'STILL_RUNNING', 'DEAD_CLEAN', 'UNKNOWN_OWNER')


class SetupError(Exception):
    """The fixture or a native setup step cannot be built; nothing is run past it."""


# --------------------------------------------------------------------------
# Pure logic (no OS call): everything below this line up to "native" is unit tested
# --------------------------------------------------------------------------

def fixture_base():
    # The default is a sibling of the repository, not a temp dir: safe_root refuses any
    # parent inside the user profile or the repository.
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
    return os.environ.get('ARCHEUS_FIXTURE_BASE') or os.path.join(os.path.dirname(repo), 'pv20-fixtures')


def parent_ok(parent):
    """True only for a canonical drive path of safe characters at or below fixture_base()."""
    if not isinstance(parent, str) or not SAFE_PARENT.match(parent):
        return False
    parts = parent.split('\\')
    if any(p in ('', '.', '..') or p.endswith('.') for p in parts[1:]):
        return False
    low, base = ntpath.normcase(parent), ntpath.normcase(fixture_base())
    return low == base or low.startswith(base + '\\')


def systemroot_ok(value):
    return isinstance(value, str) and bool(SYSTEMROOT.match(value))


def layout(root):
    """Every directory the run uses, all under root. Class names follow PV-20 7.5."""
    j = lambda *p: os.path.join(root, *p)
    lay = {'root': root, 'sdk': j('sdk'), 'private': j('private'), 'ledger': j('ledger'),
           'outside': j('outside'), 'runtime': j('runtime'), 'localappdata': j('localappdata'),
           'envhome': j('envhome'), 'faults': j('faults'), 'rev': j('rev', 'state')}
    for who in ('p', 'q'):
        lay[who] = {'request': j(who, 'req'), 'response': j(who, 'resp'),
                    'sentinel': j(who, 'sent'), 'state': j(who, 'state')}
    lay['core'] = {'lifecycle': j('core', 'lifecycle'), 'halt': j('core', 'halt'),
                   'core-private': j('core', 'private')}
    return lay


def grants(lay, who):
    """(read-write, read-only) for one execution; the workspace (cwd) is the last rw."""
    me = lay[who]
    return (me['request'], me['state']), (me['response'], me['sentinel'], lay['runtime'])


def make_dirs(lay):
    flat = [lay[k] for k in ('private', 'outside', 'runtime', 'localappdata', 'envhome',
                             'faults', 'rev')]
    nested = [d for who in ('p', 'q') for d in lay[who].values()] + list(lay['core'].values())
    for d in flat + nested:
        os.makedirs(d, exist_ok=True)


def seed_dirs(lay):
    """label -> directory that gets a host-written seed.txt holding a per-run secret."""
    out = {'outside': lay['outside'], 'runtime': lay['runtime'], 'rev': lay['rev']}
    for who in ('p', 'q'):
        out.update({'%s.%s' % (who, k): v for k, v in lay[who].items()})
    out.update({'core.%s' % k: v for k, v in lay['core'].items()})
    return out


def command_line(argv):
    if not argv or not all(isinstance(a, str) and a and '\0' not in a for a in argv):
        raise ValueError('argv must be a list of non-empty strings')
    text = subprocess.list2cmdline(list(argv))
    if len(text) > CHAIN_MAX:
        raise ValueError('command line too long')
    return text


def cmd_argv(cmd_exe, chain):
    """One cmd.exe /d /s /c line: /s strips exactly the outer quotes list2cmdline adds."""
    return [cmd_exe, '/d', '/s', '/c', chain]


def new_token():
    """A letter-terminated token: a trailing digit before > would be read as a handle."""
    return 'T%dZ' % (secrets.randbelow(900000000) + 100000000)


Item = namedtuple('Item', 'kind label cmd path secret')
POSITIVE = ('write_ok', 'dir_ok', 'read_ok', 'file_ok')
NEGATIVE = ('write_no', 'dir_no', 'read_no')


def w_ok(label, path, cmd_path=None):
    tok = new_token()
    return Item('write_ok', label, 'echo %s>%s' % (tok, cmd_path or path), path, tok)


def w_no(label, path, cmd_path=None):
    return Item('write_no', label, 'echo bad>%s' % (cmd_path or path), path, None)


def r_ok(label, src, evidence, secret):
    return Item('read_ok', label, 'type %s>%s' % (src, evidence), evidence, secret)


def r_no(label, src, evidence, secret):
    return Item('read_no', label, 'type %s>%s' % (src, evidence), evidence, secret)


def file_ok(label, cmd, path):
    return Item('file_ok', label, cmd, path, None)


def sub(cmd_exe, kind, label, path, tail, secret=None, depth=1):
    """A descendant (depth 1 child, 2 grandchild) doing the filesystem act itself."""
    head = ' '.join([cmd_exe, '/d', '/c'] * depth)
    return Item(kind, label, '%s %s' % (head, tail), path, secret)


def done_item(lay_dir):
    return w_ok('done', os.path.join(lay_dir, 'done.txt'))


def chain_of(items):
    return ' & '.join(i.cmd for i in items)


def judge(items, look):
    """Host-side verdict over what the container left behind.

    look(path) -> None when absent, '<dir>' for a directory, '<link>' for a link or a
    multiply linked file, else the file text. Returns (kind, label) for the first
    failure or None. The 'done' marker is judged first: a chain that did not reach its
    end proves nothing about the denials before it. 'control' = a positive row failed,
    'breach' = a denial row shows the container got through.
    """
    ordered = sorted(items, key=lambda i: i.label != 'done')
    for i in ordered:
        seen = look(i.path)
        text = seen if isinstance(seen, str) and seen not in ('<dir>', '<link>') else ''
        if i.kind in ('write_ok', 'read_ok'):
            ok = seen is not None and i.secret in text
        elif i.kind == 'dir_ok':
            ok = seen == '<dir>'
        elif i.kind == 'file_ok':
            ok = bool(text.strip())
        elif i.kind in ('write_no', 'dir_no'):
            ok = seen is None
        elif i.kind == 'read_no':
            ok = seen is None or i.secret not in text
        else:
            raise ValueError('unknown item kind')
        if not ok:
            return ('control' if i.kind in POSITIVE else 'breach', i.label)
    return None


def env_findings(text, expected):
    """Parse `set` output. expected maps NAME -> value. Names are compared upper case,
    values case-insensitively; a host profile path (\\Users\\) anywhere is a leak."""
    seen = {}
    for line in (text or '').splitlines():
        name, eq, value = line.partition('=')
        if eq and name:
            seen[name.strip().upper()] = value.strip()
    want = {k.upper(): v for k, v in expected.items()}
    return {'missing': sorted(k for k in want if k not in seen),
            'mismatched': sorted(k for k, v in want.items()
                                 if k in seen and seen[k].lower() != v.lower()),
            'profile_leak': any('\\users\\' in v.lower() for v in seen.values()),
            'extra': sorted(k for k in seen if k not in want)}


def policy_problems(raw, rw, ro, env):
    """What the compiled (requested) policy must say, whatever the backend later does."""
    p = raw.get('process', {})
    fs = raw.get('filesystem', {})
    bad = []
    if raw.get('network') != {'egress': {'default': 'deny'},
                              'ingress': {'default': 'deny', 'hostLoopback': 'deny'}}:
        bad.append('network is not deny-all')
    if raw.get('ui') != {'disable': True, 'clipboard': 'none', 'injection': False}:
        bad.append('ui is not blocked')
    if p.get('inheritDefaultEnv') is not False:
        bad.append('default environment is inherited')
    if p.get('env') != ['%s=%s' % kv for kv in sorted(env.items())]:
        bad.append('environment is not exactly the explicit entries')
    if (sorted(fs.get('readwritePaths', ())) != sorted(os.path.normpath(x) for x in rw)
            or sorted(fs.get('readonlyPaths', ())) != sorted(os.path.normpath(x) for x in ro)
            or fs.get('deniedPaths') != []):
        bad.append('grants are not exactly the requested folders')
    if 'runtimeConfig' in raw or 'processContainer' in raw:
        bad.append('a proxy or capability block is present')
    return bad


def oracle_state(ops):
    """The reconcile state a journal of this shape must get on a restart, or None when
    reconcile must skip it (completed). Anything else is a shape this run never makes."""
    if ops == CLEAN:
        return None
    if ops in (QUARANTINED, QUARANTINED_EARLY):
        return DEAD_UNVERIFIED
    raise ValueError('journal shape the run never produces')


def compare_reconcile(results, expected):
    """expected: id -> state, or None for 'must be skipped'. Exact, both directions."""
    bad = []
    for eid, want in sorted(expected.items()):
        got = results.get(eid)
        if got != want:
            bad.append('%s: got %s, wanted %s' % (eid, got, want))
    bad += ['%s: unexpected journal reconciled as %s' % (e, results[e])
            for e in sorted(set(results) - set(expected))]
    return bad


def journal_ops(read_records, ledger, journal):
    data = ledger.journals().get(journal)
    records, invalid = read_records(data, journal)
    return [r['op'] for r in records], invalid


def import_isolated(modules, home, environ=None, import_fn=importlib.import_module,
                    loaded=sys.modules):
    """Import the production modules with every home/profile/temp/config variable pointing
    at an empty folder, then restore them. The config module reads a settings file under
    the profile when it is imported, so it must not be loaded before this runs."""
    environ = os.environ if environ is None else environ
    if 'claude_sessions.config' in loaded:
        raise SetupError('the config module was imported before the profile was pointed away')
    saved = {k: environ.get(k) for k in HOME_VARS}
    try:
        for k in HOME_VARS:
            environ[k] = home
        return {name: import_fn(name) for name in modules}
    finally:
        for k, v in saved.items():
            if v is None:
                environ.pop(k, None)
            else:
                environ[k] = v


class Budget:
    def __init__(self, limit, clock=time.monotonic):
        self.limit, self.clock, self.start = limit, clock, clock()

    def check(self):
        if self.clock() - self.start > self.limit:
            raise SetupError('time budget exceeded; stopped between steps, root preserved')


def finish(code, root, remove, say=print):
    """Delete the fixture only when the whole run exited 0."""
    if code == 0:
        remove(root)
        say(redact('all cases PASS; fixture removed (%s)' % root))
    else:
        say(redact('run finished with code %d; root preserved at %s' % (code, root)))
    return code


def _snip(text):
    return redact(' '.join((text or '').split())[:120])


def _tail(text):
    """The end of the launcher output: with --debug the start is policy echo, the error is last."""
    return redact(' '.join((text or '').split())[-200:])


def look_at(path):
    """lstat first, never follow: see judge() for the return values."""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        return '<link>'
    if stat.S_ISDIR(info.st_mode):
        return '<dir>'
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > EVIDENCE_MAX:
        return '<link>'
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            return fh.read(EVIDENCE_MAX)
    except OSError:
        return '<link>'


Row = namedtuple('Row', 'id kind exe flag extra pair chain ev child tok controls done')


def exit_chain(exe, tok, ev):
    return ('%s /d /c exit /b 37 & (if errorlevel 38 (echo OTHER) else (if errorlevel 37 (echo %s) '
            'else (echo OTHER)))>%s' % (exe, tok, ev))


def write_chain(exe, tok, child, ev):
    return ('%s /d /c "echo %s>%s & exit /b 41" & (if errorlevel 42 (echo OTHER) else '
            '(if errorlevel 41 (echo OBSERVED) else (echo OTHER)))>%s' % (exe, tok, child, ev))


def diag_line(cmd_exe, chain):
    # The WRITE chain has inner quotes. list2cmdline would send them as \" and cmd.exe would
    # not read them as quotes, so the raw line is built here instead (/s strips only the wrap).
    if len(chain) > CHAIN_MAX:
        raise ValueError('command line too long')
    return '%s /d /s /c "%s"' % (cmd_exe, chain)


def plain(info, kind):
    return (kind(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, 'st_file_attributes', 0) & REPARSE)


def diag_rows(lay, systemroot, seed):
    j = os.path.join
    s = ntpath.join(systemroot, 'System32')
    c = ntpath.join(s, 'cmd.exe')
    k = j(lay['root'], 'toolchain')
    kc = j(k, 'cmd.exe')
    w = lay['p']['state']
    specs = (('A1', 'exit', c, None, None, None), ('A2', 'write', c, None, None, 'A1'),
             ('B1', 'exit', kc, IMAGE_FLAG, k, None), ('B2', 'write', kc, IMAGE_FLAG, k, 'B1'),
             ('C1', 'exit', c, SYSTEM_FLAG, s, None), ('C2', 'write', c, SYSTEM_FLAG, s, 'C1'))
    rows = []
    for rid, kind, exe, flag, extra, pair in specs:
        low, tok = rid.lower(), new_token()
        ev = j(w, '%s.txt' % low)
        child = j(w, '%s-child.txt' % low) if kind == 'write' else None
        chain = exit_chain(exe, tok, ev) if kind == 'exit' else write_chain(exe, tok, child, ev)
        controls = [w_ok('control-write', j(w, 'ctl_w_%s.txt' % low)),
                    r_ok('control-read', j(w, 'seed.txt'), j(w, 'ctl_r_%s.txt' % low), seed)]
        rows.append(Row(rid, kind, exe, flag, extra, pair, chain, ev, child, tok, controls,
                        w_ok('done', j(w, 'done_%s.txt' % low))))
    return rows


def diag_gate(rows, flags):
    """(runnable, skipped): a row whose grant flag was not passed is skipped, never run."""
    runnable = [r for r in rows if r.flag is None or r.flag in flags]
    return runnable, [r for r in rows if r not in runnable]


def _text(seen):
    return seen.strip() if isinstance(seen, str) and seen not in ('<dir>', '<link>') else None


def diag_result(row, look):
    """One row's label from the host's own reads. A failed control or a missing done marker
    overrides any child evidence. An EXIT row says only whether the child returned 37. A WRITE
    row says whether the child returned its own code (the parent's OBSERVED line) and then
    whether the child's token file holds the token."""
    if judge(row.controls, look) is not None:
        return 'control failed'
    if judge([row.done], look) is not None:
        return 'no evidence'
    seen = _text(look(row.ev))
    if row.kind == 'exit':
        if seen == row.tok:
            return RET_37
        if seen == 'OTHER':
            return NOT_37
        return 'no evidence'
    if seen == 'OTHER':
        return W_NOT
    if seen != 'OBSERVED':
        return 'no evidence'
    wrote = judge([Item('write_ok', row.id, None, row.child, row.tok)], look) is None
    return W_OK if wrote else W_UNPROVED


def diag_interpret(labels):
    """The conclusions the evidence supports. First matching line wins; "returned" is RET_37
    and "not returned" is NOT_37. Void rows (VOID_LABELS) are named and count for nothing.

    1. A1 returned, A2 started and wrote        -> baseline creation and workspace write proved
    2. A1 returned, A2 started, write not proved -> investigate cwd and environment versus grants (3)
    3. A1 returned, A2 otherwise                -> baseline exit proved; no workspace conclusion
    4. A1 not returned, B1 and/or C1 returned   -> image or System32 access strongly supported (1)
    5. A1 absent or void, B1 and/or C1 returned -> no conclusion about image or System32 access
    6. some usable EXIT row, none returned      -> all exit rows did not return 37: inconclusive (2)
    7. otherwise                                -> no interpretation bullet matches

    After the line that matched, every started WRITE row (A2, B2, C2 with W_OK or W_UNPROVED)
    adds "child start proved by <row> (<label>)": a WRITE row proves its child ran from its own
    evidence, whatever the EXIT rows did.
    """
    void = sorted(r for r, v in labels.items() if v in VOID_LABELS)
    ok = {r: v for r, v in labels.items() if v not in VOID_LABELS}
    a1 = ok.get('A1')
    exits = [r for r in ('A1', 'B1', 'C1') if r in ok]
    returned = [r for r in ('B1', 'C1') if ok.get(r) == RET_37]
    if a1 == RET_37 and ok.get('A2') == W_OK:
        text = 'baseline creation and workspace write proved'
    elif a1 == RET_37 and ok.get('A2') == W_UNPROVED:
        text = ('baseline child started, write not proved with its control passing: investigate (3), '
                'inherited cwd and environment versus grants')
    elif a1 == RET_37:
        text = 'baseline exit proved; the write row gives no workspace conclusion'
    elif a1 == NOT_37 and returned:
        strong = {'B1': 'image location or access, cause (1), strongly supported; '
                        'loader dependency access still possible',
                  'C1': 'missing System32 access or dependency grant, cause (1), strongly supported'}
        text = '; '.join(strong[r] for r in returned)
    elif a1 is None and returned:
        text = 'A1 baseline not usable: no conclusion about image or System32 access'
    elif exits:
        text = ('all exit rows did not return 37: inconclusive for blanket denial (2); six rows cannot '
                'prove it. Image dependencies, UI initialization and environment remain alternatives')
    else:
        text = 'no interpretation bullet matches: %s' % ', '.join(
            '%s=%s' % kv for kv in sorted(ok.items()))
    for r in ('A2', 'B2', 'C2'):
        if ok.get(r) in (W_OK, W_UNPROVED):
            text += '; child start proved by %s (%s)' % (r, ok[r])
    if void:
        text = 'rows not usable (%s): %s' % (', '.join(void), text)
    return text


class _Rec(Recorder):
    """Recorder that also appends every verdict, redacted, to the journal in the root."""
    journal = None

    def record(self, case, status, detail=''):
        try:
            super().record(case, status, detail)
        finally:
            if (self.journal and status in ('PASS', 'FAIL', 'INCONCLUSIVE')
                    and case in STAGES[STAGE].cases):
                with open(self.journal, 'a', encoding='utf-8') as fh:
                    fh.write(json.dumps({'case': case, 'status': status,
                                         'detail': redact(detail)}) + '\n')


# --------------------------------------------------------------------------
# Native part: only reached from main(); every Windows call is below this line
# --------------------------------------------------------------------------

def _on_windows():
    return os.name == 'nt'


def _system_ok(root_env):
    return systemroot_ok(root_env) and os.path.isfile(ntpath.join(root_env, 'System32', 'cmd.exe'))


def _exit_code(pid):
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k.OpenProcess(0x1000, False, int(pid))
    if not h:
        return None
    try:
        code = wintypes.DWORD(0)
        return code.value if k.GetExitCodeProcess(h, ctypes.byref(code)) else None
    finally:
        k.CloseHandle(h)


def live_ctime(pid):
    """Creation time of pid while it is alive, else None (gone, exited or unreadable)."""
    if _exit_code(pid) != STILL_ACTIVE:
        return None
    return common._process_creation_time(pid)


class JobRef:
    """The script's one handle to a Core Job; closing it twice is a no-op."""

    def __init__(self, boundary, handle):
        self.boundary, self.handle = boundary, handle

    def close(self):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            self.boundary.close_job(handle)


def _counting_api(win32_mxc):
    class CountingApi(win32_mxc.Win32Api):
        """The production api plus counters, so 'no spawn' means zero CreateProcessW calls
        and 'never resumed' means zero ResumeThread calls."""
        creates = resumes = 0
        created = None

        def reset(self):
            self.creates = self.resumes = 0
            self._pid = None
            if self.created is None:
                self.created = []

        def create_process_w(self, **kw):
            self.creates += 1
            process, thread, pid = super().create_process_w(**kw)
            self._pid = pid
            return process, thread, pid

        def creation_time(self, process):
            value = super().creation_time(process)
            self.created.append((self._pid, value))
            return value

        def resume_thread(self, thread):
            self.resumes += 1
            return super().resume_thread(thread)
    return CountingApi


class Harness:
    def __init__(self, root, sdk_src, systemroot, budget):
        self.lay, self.budget = layout(root), budget
        self.cmd = ntpath.join(systemroot, 'System32', 'cmd.exe')
        self.env = {'SYSTEMROOT': systemroot, 'LOCALAPPDATA': self.lay['localappdata']}
        self.sdk_src, self.jobs, self.seq, self.ended, self.seeds = sdk_src, [], 0, {}, {}
        self.m, self.phase = None, 'setup'

    # ---- setup ----

    def prepare(self):
        lay = self.lay
        make_dirs(lay)
        for label, d in seed_dirs(lay).items():
            self.seeds[label] = new_token()
            with open(os.path.join(d, 'seed.txt'), 'x', encoding='utf-8') as fh:
                fh.write(self.seeds[label])
        with open(os.path.join(lay['outside'], 'known.txt'), 'x', encoding='utf-8') as fh:
            fh.write(self.seeds['outside'])
        mods = import_isolated(PROD, lay['envhome'])
        self.m = SimpleNamespace(**{n.rsplit('.', 1)[1]: mods[n] for n in PROD})
        staging = self.m.staging
        # ponytail: pins come from the staged copy because no reviewed hash inventory is
        # supplied; stage_mxc then proves the copy equals the source, nothing more.
        self.pins = staging._mxc_inventory(self.sdk_src)
        staging.stage_mxc(self.sdk_src, lay['sdk'], pins=self.pins)
        self.api = _counting_api(self.m.win32_mxc)(lay['private'])
        self.api.reset()
        self.boundary = self.m.isolation.WindowsBoundary()
        self.ledger = self.m.mxc_ledger.Ledger(lay['ledger'])
        self.m.mxc.NATIVE_RUN_ENABLED = True      # the owner-authorised native gate, this process only

    # ---- one production launch ----

    def reader(self, execution_id, owner):
        """Fixture resource reader. It proves one thing: the launcher this execution owned
        is gone (pid and creation time). MXC's own resources cannot be read back."""
        return True if live_ctime(owner['pid']) != owner['create_time'] else [execution_id]

    def eid(self, tag):
        self.seq += 1
        return 'n2_%02d_%s' % (self.seq, tag.replace('-', '_'))

    def name(self, eid):
        """The ledger journal of an execution's one process generation."""
        return self.m.mxc_ledger.journal_name(eid, 1)

    def make(self, tag, argv, rw, ro, *, reader=True, disposal=None, ledger=None,
             boundary=None, env=None, timeout_ms=60000, eid=None, line=None):
        self.budget.check()
        eid = eid or self.eid(tag)
        launch = self.m.local.MxcLaunch(
            api=self.api, boundary=boundary or self.boundary, ledger=ledger or self.ledger,
            schema_validator=lambda raw: True, execution_id=eid, sdk_root=self.lay['sdk'],
            pins=self.pins, outcome=lambda process: process.launcher_exit, workspace=rw[-1],
            writable=tuple(rw[:-1]), readonly=tuple(ro), cwd=rw[-1],
            command_line=line or command_line(argv), env=dict(self.env if env is None else env),
            timeout_ms=timeout_ms, resource_reader=self.reader if reader else None,
            disposal=disposal, quiescence_wait=QUIESCE_S)
        return eid, launch

    def job(self, eid, boundary=None):
        ref = JobRef(self.boundary, (boundary or self.boundary).create_job(eid))
        self.jobs.append(ref)
        return ref

    def go(self, tag, argv, rw, ro, **kw):
        """Compile, start in a fresh Core Job, wait, return what the production end left."""
        eid, launch = self.make(tag, argv, rw, ro, **kw)
        job = self.job(eid, kw.get('boundary'))
        self.phase = 'launch'
        launch.start(job=job.handle)
        code = launch.wait()
        out = launch.stdout.read().decode('utf-8', 'replace')
        err = launch.stderr.read().decode('utf-8', 'replace')
        self.ended[eid] = self.ops(eid)[0]
        return SimpleNamespace(eid=eid, launch=launch, job=job, code=code, out=out, err=err,
                               ops=self.ended[eid])

    def ops(self, eid):
        return journal_ops(self.m.mxc_ledger.read_records, self.ledger, self.name(eid))

    def job_count(self, job):
        return self.boundary.job_active_processes(job.handle)

    def wait_job(self, job, want, seconds):
        """Poll the Core Job's member count until want(count); returns the last count."""
        end, n = time.monotonic() + seconds, None
        while True:
            n = self.job_count(job)
            if want(n) or time.monotonic() >= end:
                return n
            time.sleep(0.2)

    def wait_dead(self, pid, ctime, seconds):
        end = time.monotonic() + seconds
        while live_ctime(pid) == ctime:
            if time.monotonic() >= end:
                return False
            time.sleep(0.2)
        return True

    def wind_down(self):
        """Close every Job (the kill), then check no launcher this script made is alive. One
        failed close, or Ctrl+C, does not skip the other Jobs. Returns the number of failures."""
        failed = 0
        for n, ref in enumerate(self.jobs, 1):
            try:
                ref.close()
            except BaseException as ex:
                failed += 1
                _say(lambda n=n, ex=ex: 'pv20 N2 wind-down: Job %d could not be closed: %s %s'
                     % (n, type(ex).__name__, _snip(str(ex))))
        if self.m is not None:
            self.m.mxc.NATIVE_RUN_ENABLED = False
        for n, (pid, ctime) in enumerate(list(getattr(getattr(self, 'api', None), 'created', None) or ()), 1):
            try:
                if not self.wait_dead(pid, ctime, 5.0):
                    failed += 1
                    if live_ctime(pid) == ctime:      # ours, same creation time: the one kill allowed
                        common._terminate_process(pid)
            except BaseException as ex:
                failed += 1
                _say(lambda n=n, ex=ex: 'pv20 N2 wind-down: launcher %d could not be checked: %s %s'
                     % (n, type(ex).__name__, _snip(str(ex))))
        return failed


def read_text(path):
    seen = look_at(path)
    return seen if isinstance(seen, str) and seen not in ('<dir>', '<link>') else ''


def probe(h, rec, case, tag, items, rw, ro):
    """One production launch running the items as a single chain, judged host-side."""
    items = list(items) + [done_item(rw[-1])]
    run = h.go(tag, cmd_argv(h.cmd, chain_of(items)), rw, ro)
    bad = judge(items, look_at)
    if bad:
        what = ('CONTAINMENT BREACH' if bad[0] == 'breach' else 'control did not hold')
        rec.record(case, 'FAIL', '%s (%s: %s); launcher rc=%s %s'
                   % (what, tag, bad[1], run.code, _tail(run.out + run.err)))
    if run.ops != CLEAN:
        rec.record(case, 'FAIL', '%s: the production end was not clean, ledger %s' % (tag, run.ops))
    return run


def step_adapter(h, rec):
    p_rw, p_ro = grants(h.lay, 'p')
    argv = [h.cmd, '/d', '/c', 'echo', 'MXC-N^2']           # caret: a --debug policy echo cannot fake it
    try:
        run = h.go('echo', argv, p_rw[-1:], p_ro[-1:])
    except Exception as err:
        rec.record('production-adapter', 'FAIL',
                   'production launch raised %s: %s' % (type(err).__name__, _snip(str(err))))
    if run.code != 0 or 'MXC-N2' not in run.out:
        rec.record('production-adapter', 'FAIL',
                   'launcher or control did not run: rc=%s %s' % (run.code, _tail(run.out + run.err)))
    rec.record('positive-controls', 'PASS', 'production launch ran cmd.exe echo, caret-differentiated sentinel')
    state = (run.launch.end_state or {}).get('state')
    if run.ops != CLEAN or state != DEAD_CLEAN:
        rec.record('production-adapter', 'FAIL',
                   'ledger %s end state %s, wanted intent, ownership, disposal, completion and %s'
                   % (run.ops, state, DEAD_CLEAN))
    raw = run.launch.policy.raw
    bad = policy_problems(raw, p_rw[-1:], p_ro[-1:], h.env)
    if bad:
        rec.record('production-adapter', 'FAIL', 'compiled policy: ' + '; '.join(bad))
    rec.record('production-adapter', 'PASS',
               'compiled, suspended create, Job assign and membership verified, single resume, '
               'workload exit %s, ledger %s, end %s' % (run.code, '>'.join(run.ops), state))


def canary(h, rec, tag):
    """A write outside the grant, in the same chain as an inside write and a done marker."""
    p_rw, p_ro = grants(h.lay, 'p')
    items = [w_ok('inside', os.path.join(p_rw[-1], 'ctl_%s.txt' % tag)),
             w_no('outside', os.path.join(h.lay['outside'], 'breach_%s.txt' % tag))]
    probe(h, rec, 'positive-controls', 'canary-' + tag, items, p_rw[-1:], p_ro[-1:])
    rec.record('positive-controls', 'PASS', 'canary %s: inside write present, outside write absent' % tag)


def class_items(h, who, peer):
    lay, s = h.lay, h.seeds
    me, other, core = lay[who], lay[peer], lay['core']
    j = os.path.join
    ev = lambda n: j(me['state'], 'e_%s.txt' % n)
    items = [w_ok('request-write', j(me['request'], 'w.txt')),
             w_ok('state-write', j(me['state'], 'w.txt')),
             r_ok('response-read', j(me['response'], 'seed.txt'), ev('response'), s[who + '.response']),
             r_ok('sentinel-read', j(me['sentinel'], 'seed.txt'), ev('sentinel'), s[who + '.sentinel']),
             w_no('response-write', j(me['response'], 'w.txt')),
             w_no('sentinel-write', j(me['sentinel'], 'w.txt')),
             w_no('runtime-write', j(lay['runtime'], 'w.txt'))]
    for cls in ('lifecycle', 'halt', 'core-private'):
        items += [r_no(cls + '-read', j(core[cls], 'seed.txt'), ev(cls), s['core.' + cls]),
                  w_no(cls + '-write', j(core[cls], 'w.txt'))]
    for cls in ('request', 'response', 'sentinel', 'state'):
        items += [r_no('peer-%s-read' % cls, j(other[cls], 'seed.txt'), ev('peer_' + cls),
                       s['%s.%s' % (peer, cls)]),
                  # not w.txt: the peer's own run leaves that file in its writable folders,
                  # and a denial row is judged by the file being absent
                  w_no('peer-%s-write' % cls, j(other[cls], 'peer_w.txt'))]
    return items


def step_classes(h, rec):
    for who, peer in (('p', 'q'), ('q', 'p')):
        rw, ro = grants(h.lay, who)
        probe(h, rec, 'seven-resource-classes', 'classes-' + who, class_items(h, who, peer), rw, ro)
        rec.record('seven-resource-classes', 'PASS',
                   '%s execution: classes 1,7 writable, 2,3 read-only, 4,5,6 and the peer %s '
                   'untouched, both directions, each with a same-chain control' % (who, peer))


def step_effective(h, rec):
    lay, j = h.lay, os.path.join
    rw, ro = grants(lay, 'p')
    me = lay['p']
    env_path = j(me['state'], 'env.txt')
    items = [r_ok('own-seed', j(me['state'], 'seed.txt'), j(me['state'], 'e_own.txt'), h.seeds['p.state']),
             r_no('outside-read', j(lay['outside'], 'known.txt'), j(me['state'], 'e_out.txt'), h.seeds['outside']),
             r_no('traversal-read', '..\\..\\outside\\known.txt', j(me['state'], 'e_trav.txt'), h.seeds['outside']),
             w_no('outside-write', j(lay['outside'], 'w.txt')),
             w_no('traversal-write', j(lay['outside'], 'w2.txt'), cmd_path='..\\..\\outside\\w2.txt'),
             file_ok('environment', 'set>%s' % env_path, env_path)]
    run = probe(h, rec, 'effective-policy', 'effective', items, rw, ro)
    bad = policy_problems(run.launch.policy.raw, rw, ro, h.env)
    if bad:
        rec.record('effective-policy', 'FAIL', 'compiled policy: ' + '; '.join(bad))
    rec.record('effective-policy', 'PASS',
               'own folder readable, outside and traversal reads and writes denied, each with a same-chain '
               'control; the requested policy matches its compiled form')
    # The schema says PSEC may replace LOCALAPPDATA with a container-profile path and that supplied
    # entries are not a guarantee, so a difference is a recorded observation, never a FAIL.
    found = env_findings(read_text(env_path), h.env)
    if found['missing'] or found['mismatched'] or found['profile_leak']:
        rec.record('effective-policy', 'INCONCLUSIVE',
                   'environment seen inside differs from the explicit entries: missing=%s changed=%s '
                   'host_profile_path_present=%s (names only; the schema allows PSEC to replace entries); '
                   'other names=%s' % (found['missing'], found['mismatched'], found['profile_leak'],
                                       found['extra'] or 'none'))
    else:
        rec.record('effective-policy', 'PASS',
                   'environment seen inside is exactly the explicit entries (other names: %s)'
                   % (found['extra'] or 'none'))


def step_descendants(h, rec):
    lay, j, cmd = h.lay, os.path.join, h.cmd
    rw, ro = grants(lay, 'p')
    me, q, core = lay['p'], lay['q'], lay['core']
    items = [
        sub(cmd, 'dir_ok', 'child-md-inside', j(me['state'], 'dc_ok'), 'md ' + j(me['state'], 'dc_ok')),
        sub(cmd, 'dir_no', 'child-md-outside', j(lay['outside'], 'dc_no'), 'md ' + j(lay['outside'], 'dc_no')),
        sub(cmd, 'dir_ok', 'grandchild-md-inside', j(me['state'], 'gc_ok'), 'md ' + j(me['state'], 'gc_ok'), depth=2),
        sub(cmd, 'dir_no', 'grandchild-md-outside', j(lay['outside'], 'gc_no'), 'md ' + j(lay['outside'], 'gc_no'), depth=2),
        sub(cmd, 'dir_no', 'grandchild-md-peer', j(q['request'], 'gc_peer'), 'md ' + j(q['request'], 'gc_peer'), depth=2),
        sub(cmd, 'read_ok', 'child-copy-response', j(me['state'], 'dc_resp.txt'),
            'copy /y %s %s' % (j(me['response'], 'seed.txt'), j(me['state'], 'dc_resp.txt')), h.seeds['p.response']),
        sub(cmd, 'read_no', 'child-copy-core-private', j(me['state'], 'dc_core.txt'),
            'copy /y %s %s' % (j(core['core-private'], 'seed.txt'), j(me['state'], 'dc_core.txt')),
            h.seeds['core.core-private']),
        sub(cmd, 'read_no', 'grandchild-copy-peer', j(me['state'], 'gc_peer.txt'),
            'copy /y %s %s' % (j(q['state'], 'seed.txt'), j(me['state'], 'gc_peer.txt')), h.seeds['q.state'], depth=2)]
    probe(h, rec, 'hostile-descendants', 'descendants', items, rw, ro)
    rec.record('hostile-descendants', 'PASS',
               'child and grandchild processes got exactly the parent grants: inside and own-response '
               'acts worked, outside, peer and Core-private acts were denied')


def _refusal(h, rec, label, build, plant=None):
    """The production code must refuse, with zero CreateProcessW calls and no journal.
    With plant, the refusal must come at launch: plant() runs after the grant was accepted."""
    h.api.reset()
    before = set(h.ledger.journals())
    refused = None
    try:
        eid, launch = build()
    except Exception as err:
        refused = type(err).__name__
        if plant is not None:
            rec.record('setup-faults-no-spawn', 'FAIL',
                       '%s: refused (%s) before the launch-time change, so the launch re-check was not reached'
                       % (label, refused))
    else:
        if plant is not None:
            plant()                      # a fault of the script itself is not a refusal
            try:
                launch.start(job=h.job(eid).handle)
            except Exception as err:
                refused = type(err).__name__
    after = set(h.ledger.journals())
    if refused is None:
        rec.record('setup-faults-no-spawn', 'FAIL', '%s: production did not refuse' % label)
    if h.api.creates or h.api.resumes or after != before:
        rec.record('setup-faults-no-spawn', 'FAIL',
                   '%s: refused as %s but CreateProcessW=%d ResumeThread=%d journals %s'
                   % (label, refused, h.api.creates, h.api.resumes, sorted(after - before)))
    rec.record('setup-faults-no-spawn', 'PASS',
               '%s: refused (%s), zero CreateProcessW, no journal' % (label, refused))


def _junction(h, link, target):
    r = subprocess.run([h.cmd, '/d', '/c', 'mklink', '/J', link, target],
                       capture_output=True, timeout=30)
    if r.returncode != 0 or look_at(link) != '<link>':
        raise SetupError('could not create the fixture junction')


def _unjunction(link):
    os.rmdir(link)                       # removes the link only; never descends into the target
    if look_at(link) is not None:
        raise SetupError('fixture junction was not removed')


def _fault_launch(h, rec, label, tag, ledger=None, boundary=None):
    """Created suspended, then a fault before the resume: the child must never run."""
    lay = h.lay
    work = os.path.join(lay['faults'], tag)
    os.makedirs(work)
    marker = os.path.join(lay['outside'], 'spawned_%s.txt' % tag)
    argv = cmd_argv(h.cmd, 'echo X>%s' % marker)
    h.api.reset()
    first = len(h.api.created)
    eid, launch = h.make(tag, argv, (work,), (lay['runtime'],), ledger=ledger, boundary=boundary)
    job = h.job(eid, boundary)
    try:
        launch.start(job=job.handle)
    except Exception as err:
        raised = type(err).__name__
    else:
        raised = None
    time.sleep(3.0)                      # a resumed launcher would have written by now
    ops, invalid = h.ops(eid)
    h.ended[eid] = ops
    n = h.wait_job(job, lambda c: c == 0, QUIESCE_S)
    alive = [pid for pid, ct in h.api.created[first:] if live_ctime(pid) == ct]
    if (raised is None or h.api.creates != 1 or h.api.resumes != 0 or look_at(marker) is not None
            or ops != QUARANTINED_EARLY or invalid or n != 0 or alive):
        rec.record('setup-faults-no-spawn', 'FAIL',
                   '%s: raised=%s CreateProcessW=%d ResumeThread=%d marker=%s ledger=%s job_members=%s alive=%d'
                   % (label, raised, h.api.creates, h.api.resumes, look_at(marker) is not None,
                      ops, n, len(alive)))
    rec.record('setup-faults-no-spawn', 'PASS',
               '%s: created suspended, never resumed, terminated, Job empty, ledger %s'
               % (label, '>'.join(ops)))


def step_faults(h, rec):
    lay, j, m = h.lay, os.path.join, h.m
    argv = cmd_argv(h.cmd, 'echo X>%s' % j(lay['outside'], 'never.txt'))
    victim = j(lay['outside'], 'victim.txt')
    with open(victim, 'x', encoding='utf-8') as fh:
        fh.write('victim')
    runtime = (lay['runtime'],)

    def folder(name):
        d = j(lay['faults'], name)
        os.makedirs(d)
        return d

    work = folder('hl-grant')
    os.link(victim, j(work, 'alias'))
    _refusal(h, rec, 'hardlink in a grant at grant time', lambda: h.make('hl1', argv, (work,), runtime))
    os.unlink(j(work, 'alias'))
    work = folder('hl-launch')
    _refusal(h, rec, 'hardlink added between grant and launch',
             lambda: h.make('hl2', argv, (work,), runtime),
             plant=lambda: os.link(victim, j(work, 'alias')))
    os.unlink(j(work, 'alias'))
    work = folder('jn-grant')
    _junction(h, j(work, 'alias'), lay['outside'])
    try:
        _refusal(h, rec, 'junction inside a grant', lambda: h.make('jn1', argv, (work,), runtime))
    finally:
        _unjunction(j(work, 'alias'))
    real = folder('jn-real')
    sub_dir = j(real, 'sub')
    os.makedirs(sub_dir)
    link = j(lay['faults'], 'jn-anc')
    _junction(h, link, real)
    try:
        _refusal(h, rec, 'junction in a grant ancestor',
                 lambda: h.make('jn2', argv, (j(link, 'sub'),), runtime))
    finally:
        _unjunction(link)
    work = folder('env')
    _refusal(h, rec, 'no LOCALAPPDATA in the explicit environment',
             lambda: h.make('env', argv, (work,), runtime, env={'SYSTEMROOT': h.env['SYSTEMROOT']}))

    class FaultLedger(m.mxc_ledger.Ledger):
        def append(self, execution_id, op, **facts):
            if op == 'ownership':
                raise OSError('injected ownership write fault')
            return super().append(execution_id, op, **facts)

    class FaultBoundary(m.isolation.WindowsBoundary):
        def assign_job(self, job, process_handle):
            raise OSError('injected Job assignment fault')

    _fault_launch(h, rec, 'ownership record unwritable', 'own', ledger=FaultLedger(lay['ledger']))
    _fault_launch(h, rec, 'Job assignment fails', 'job', boundary=FaultBoundary())


def _echo_run(h, tag, **kw):
    p_rw, p_ro = grants(h.lay, 'p')
    return h.go(tag, [h.cmd, '/d', '/c', 'echo', 'MXC-N^2'], p_rw[-1:], p_ro[-1:], **kw)


def step_disposal(h, rec):
    run = _echo_run(h, 'noreader', reader=False)
    state = (run.launch.end_state or {}).get('state')
    if run.code != 0 or 'MXC-N2' not in run.out or run.ops != QUARANTINED or state != DEAD_UNVERIFIED:
        rec.record('disposal-quarantine', 'FAIL',
                   'no resource reader: rc=%s ledger %s state %s, wanted a quarantine, no disposal, no completion'
                   % (run.code, run.ops, state))
    rec.record('disposal-quarantine', 'PASS',
               'workload ran, no reader could verify disposal: quarantined (%s), never completed' % '>'.join(run.ops))

    def boom(owner):
        raise OSError('injected disposal fault')

    run = _echo_run(h, 'fault', disposal=boom)
    state = (run.launch.end_state or {}).get('state')
    if run.ops != QUARANTINED or state != DEAD_UNVERIFIED:
        rec.record('disposal-quarantine', 'FAIL', 'disposal fault: ledger %s state %s' % (run.ops, state))
    # same id, second life: the journal blocks the start, and the ledger takes no later transition
    eid, reuse, move = run.eid, None, None
    rw = grants(h.lay, 'p')[0][-1:]
    h.api.reset()
    try:
        _, again = h.make('reuse', [h.cmd, '/d', '/c', 'echo', 'X'], rw, (h.lay['runtime'],), eid=eid)
        again.start(job=h.job(eid).handle)
    except Exception as err:
        reuse = type(err).__name__
    try:
        h.ledger.append(h.name(eid), 'disposal', verified_absent=True)
    except ValueError as err:
        move = type(err).__name__
    if reuse is None or move is None or h.api.creates:
        rec.record('disposal-quarantine', 'FAIL',
                   'a quarantined execution id was reusable: restart=%s transition=%s CreateProcessW=%d'
                   % (reuse, move, h.api.creates))
    rec.record('disposal-quarantine', 'PASS',
               'disposal fault quarantined (%s); the id cannot start again and the ledger refuses a '
               'later disposal record' % '>'.join(run.ops))


def loop_argv(h):
    """A long cmd.exe tree: parent, child, and a loop that outlives any 5 s observation."""
    return [h.cmd, '/d', '/c', h.cmd, '/d', '/c', 'for', '/l', '%i', 'in',
            '(1,1,%s)' % (secrets.randbelow(900000000) + 100000000), 'do', '@rem', 'x']


def _start_loop(h, tag, rw, ro):
    eid, launch = h.make(tag, loop_argv(h), rw, ro, timeout_ms=120000)
    job = h.job(eid)
    launch.start(job=job.handle)
    n = h.wait_job(job, lambda c: c >= 1, 15.0)
    if not isinstance(n, int) or n < 1:
        raise SetupError('the container tree did not start (Job members %r)' % (n,))
    return eid, launch, job, n


def step_revocation(h, rec):
    lay, j = h.lay, os.path.join
    rev = lay['rev']
    eid, launch, job, before = _start_loop(h, 'live', (rev,), (lay['runtime'],))
    pid, ctime = launch.process.pid, launch.process.create_time
    state = launch.cancel(reason='revocation')
    after = h.wait_job(job, lambda c: c == 0, QUIESCE_S)
    ops, invalid = h.ops(eid)
    h.ended[eid] = ops
    if after != 0 or live_ctime(pid) == ctime or 'completion' in ops or invalid:
        rec.record('revocation', 'FAIL',
                   'cancel of a live tree: Job members %s -> %s, launcher alive=%s, ledger %s'
                   % (before, after, live_ctime(pid) == ctime, ops))
    held = r_ok('former-with-grant', j(rev, 'seed.txt'), j(rev, 'e_with.txt'), h.seeds['rev'])
    probe(h, rec, 'revocation', 'rev-with', [held], (rev,), (lay['runtime'],))
    rw, ro = grants(lay, 'p')
    gone = r_no('former-without-grant', j(rev, 'seed.txt'), j(rw[-1], 'e_without.txt'), h.seeds['rev'])
    probe(h, rec, 'revocation', 'rev-without', [gone], rw[-1:], ro[-1:])
    rec.record('revocation', 'PASS',
               'live tree of %s processes ended by the production cancel, Job empty, launcher gone, no '
               'completion journalled (ledger %s, state %s); the folder read with its grant and was '
               'denied once the grant was no longer in a policy' % (before, '>'.join(ops), (state or {}).get('state')))


def _reconcile(h):
    """A new Ledger object stands for the restarted Core: no memory survives but the files."""
    fresh = h.m.mxc_ledger.Ledger(h.lay['ledger'])
    return fresh.reconcile(live_ctime, h.reader)


def step_restart(h, rec):
    lay = h.lay
    # synthetic journals made with the production ledger, so every reconcile branch is reached
    own = common._process_creation_time(os.getpid())
    if not isinstance(own, int) or own <= 0:
        raise SetupError('cannot read this process creation time')
    digest = '0' * 64
    intent_only, reused = (h.name('n2_synth_intent'), h.name('n2_synth_reuse'))
    h.ledger.append(intent_only, 'intent', requested_policy_digest=digest,
                    planned=[], applied=[], observed={})
    h.ledger.append(reused, 'intent', requested_policy_digest=digest,
                    planned=[], applied=[], observed={})
    h.ledger.append(reused, 'ownership', pid=os.getpid(), create_time=own + 1,
                    requested_policy_digest=digest, applied=[], observed={}, owned=[])
    expected = {}
    for eid, ops in h.ended.items():
        expected[h.name(eid)] = oracle_state(ops)
    expected[intent_only] = DEAD_UNVERIFIED
    expected[reused] = UNKNOWN_OWNER

    eid, launch, job, members = _start_loop(h, 'crash', (lay['rev'],), (lay['runtime'],))
    pid, ctime = launch.process.pid, launch.process.create_time
    expected[h.name(eid)] = STILL_RUNNING
    first = _reconcile(h)
    bad = compare_reconcile(first, expected)
    if bad or live_ctime(pid) != ctime or h.job_count(job) < 1:
        rec.record('restart-reconciliation', 'FAIL',
                   'restart while the launcher lives: %s; launcher alive=%s'
                   % ('; '.join(bad) or 'states match', live_ctime(pid) == ctime))
    job.close()                           # the Core-death event: the last Job handle goes
    if not h.wait_dead(pid, ctime, 10.0):
        rec.record('restart-reconciliation', 'FAIL', 'launcher survived the close of the Core Job')
    expected[h.name(eid)] = DEAD_CLEAN
    second = _reconcile(h)
    bad = compare_reconcile(second, expected)
    if bad:
        rec.record('restart-reconciliation', 'FAIL', 'restart after Core death: ' + '; '.join(bad))
    stale = sum(1 for n in os.listdir(lay['private']) if n.endswith('.json'))
    rec.record('restart-reconciliation', 'PASS',
               'a restarted ledger left the live launcher alone (%s), then read it dead and clean once the '
               'Job closed; completed journals skipped, quarantined and reused-pid and intent-only '
               'journals stayed unverified; stale protected policy files after the crash: %d'
               % (STILL_RUNNING, stale))


def stage_toolchain(src, folder, lstat=os.lstat):
    """Byte-copy the host cmd.exe into the fixture; links and reparse points are refused
    before anything is written."""
    if not plain(lstat(src), stat.S_ISREG) or not plain(lstat(folder), stat.S_ISDIR):
        raise SetupError('image copy refused: source or toolchain folder is a link, reparse point or not plain')
    with open(src, 'rb') as fh:
        data = fh.read()
    dst = os.path.join(folder, 'cmd.exe')
    with open(dst, 'xb') as fh:
        fh.write(data)
    if not plain(lstat(dst), stat.S_ISREG):
        raise SetupError('image copy refused: the copy is not a plain file')
    with open(dst, 'rb') as fh:
        return verify_copy(data, fh.read()), dst


def verify_copy(src, dst):
    a, b = hashlib.sha256(src).hexdigest(), hashlib.sha256(dst).hexdigest()
    if a != b:
        raise SetupError('image copy hash mismatch: source %s, copy %s' % (a, b))
    return a


def _say(text):
    """Best-effort report: a closed or broken stdout, or an interrupt, must never stop cleanup or
    replace an error. text may be a callable, so its formatting runs inside the same guard."""
    try:
        text = redact(text() if callable(text) else text)
    except BaseException:
        return
    try:
        print(text, flush=True)
    except BaseException:
        try:
            print(text, file=sys.stderr, flush=True)
        except BaseException:
            pass


def diag_row(h, row):
    rw, ro = grants(h.lay, 'p')
    readonly = ro + ((row.extra,) if row.extra else ())
    chain = ' & '.join([row.chain] + [i.cmd for i in row.controls + [row.done]])
    h.phase = 'setup'
    run = h.go('diag-' + row.id.lower(), None, rw, readonly, line=diag_line(h.cmd, chain))
    h.phase = 'evidence'
    label = diag_result(row, look_at)
    evidence = {'ev': look_at(row.ev), 'child': look_at(row.child) if row.child else None}
    digest = hashlib.sha256(json.dumps(run.launch.policy.raw, sort_keys=True).encode()).hexdigest()
    _say('pv20 N2-diag %s %s policy=%s ledger=%s job_members=%d launcher_rc=%s %s'
         % (row.id, label, digest[:16], '>'.join(run.ops), h.job_count(run.job), run.code,
            _tail(run.out + run.err)))
    return {'label': label, 'evidence': evidence, 'launcher_rc': run.code, 'policy_sha256': digest}


def refusal_types(h):
    """The admission refusals the production launch raises: a refused grant (StageError from
    the link and reparse scans) and a refused policy (MxcUnavailable from compile_policy)."""
    m = getattr(h, 'm', None)
    return () if m is None else (m.staging.StageError, m.mxc.MxcUnavailable)


def failed_row(h, row, ex):
    """A known admission refusal in setup or launch is a finding. Anything else is a defect of
    the diagnostic: the row is void, its type, phase and traceback tail are printed."""
    phase = getattr(h, 'phase', 'setup')
    if phase in ('setup', 'launch') and isinstance(ex, refusal_types(h)):
        _say('pv20 N2-diag %s launch refused: %s %s' % (row.id, type(ex).__name__, _snip(str(ex))))
        return {'label': 'launch refused', 'phase': phase}
    tail = ''.join(traceback.format_exception(type(ex), ex, ex.__traceback__)).splitlines()[-4:]
    _say('pv20 N2-diag %s diagnostic error: %s in phase %s: %s'
         % (row.id, type(ex).__name__, phase, _snip(str(ex))))
    _say('pv20 N2-diag %s traceback tail: %s' % (row.id, ' | '.join(tail)))
    return {'label': 'diagnostic error', 'phase': phase, 'error': _snip(str(ex))}


def grant_admission(path, check_grants, scan_grants, error):
    """The two scans a launch runs on one granted path, read-only. None when admitted, else the
    refusal text, which names the first refusing path. A folder the second scan cannot list is
    not admitted either: the launch would fail on it the same way."""
    try:
        check_grants((path,), error)
        scan_grants((path,))
    except error as ex:
        return str(ex)
    except OSError as ex:
        return 'grant scan failed: %s' % type(ex).__name__
    return None


def system32_admission(systemroot, parent):
    """The production grant scans on System32 (the C rows' grant), run before anything is copied
    or granted. Only lstat and listdir: no handle, no ACL, no grant."""
    path = ntpath.join(systemroot, 'System32')
    mods = import_isolated(('archeus.node.linkscan', 'archeus.node.staging'), parent)
    linkscan_mod, staging_mod = mods['archeus.node.linkscan'], mods['archeus.node.staging']
    reason = grant_admission(path, linkscan_mod.check_grants, staging_mod.scan_grants,
                             staging_mod.StageError)
    return {'path': path, 'admitted': reason is None, 'reason': reason}


def admission_line(result):
    if result['admitted']:
        return 'pv20 N2-diag pre-check %s admitted' % result['path']
    return 'pv20 N2-diag pre-check %s not admissible: %s' % (result['path'], result['reason'])


def _row_record(row, admission, label, **extra):
    base = {'row': row.id, 'label': label, 'evidence': None, 'launcher_rc': None,
            'precheck': admission if row.flag == SYSTEM_FLAG else None}
    base.update(extra)
    return base


def _redact_strings(value):
    if isinstance(value, dict):
        return {k: _redact_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_strings(v) for v in value]
    return redact(value) if isinstance(value, str) else value


def write_results(root, doc):
    """Create the results file exclusively and never overwrite one. False when it was not written."""
    try:
        text = json.dumps(_redact_strings(doc), indent=2, sort_keys=True) + '\n'
        with open(os.path.join(root, RESULTS), 'x', encoding='utf-8') as fh:
            fh.write(text)
    except BaseException as ex:
        _say(lambda ex=ex: 'pv20 N2 results not written: %s %s' % (type(ex).__name__, _snip(str(ex))))
        return False
    return True


def diagnose(h, flags, admission):
    """Diagnostic only: never a PASS, so the exit code is 2 whenever the matrix ran and its results
    were written, 3 when they were not. A System32 row is launched only when the pre-check admitted
    the System32 grant."""
    h.prepare()
    toolchain = os.path.join(h.lay['root'], 'toolchain')
    rows = diag_rows(h.lay, h.env['SYSTEMROOT'], h.seeds['p.state'])
    runnable, skipped = diag_gate(rows, flags)
    recs = {}
    for r in skipped:
        _say('pv20 N2-diag %s SKIPPED not authorized (%s)' % (r.id, r.flag))
        recs[r.id] = _row_record(r, admission, 'not authorized')
    interpretation = None
    try:
        if any(r.flag == IMAGE_FLAG for r in runnable):
            os.makedirs(toolchain, exist_ok=True)
            digest, dst = stage_toolchain(h.cmd, toolchain)
            _say('pv20 N2-diag staged %s sha256=%s source and copy equal' % (dst, digest))
        for r in runnable:
            if r.flag == SYSTEM_FLAG and not admission['admitted']:
                _say('pv20 N2-diag %s not admissible: %s' % (r.id, admission['reason']))
                recs[r.id] = _row_record(r, admission, 'not admissible')
                continue
            try:
                out = diag_row(h, r)
            except SetupError:
                raise
            except Exception as ex:
                out = failed_row(h, r, ex)
            recs[r.id] = _row_record(r, admission, out.pop('label'), **out)
        interpretation = diag_interpret({k: v['label'] for k, v in recs.items()})
        _say('DIAGNOSTIC %s' % interpretation)
    finally:
        try:
            written = write_results(h.lay['root'], {'system32': admission, 'interpretation': interpretation,
                                                    'rows': [recs[r.id] for r in rows if r.id in recs]})
        except BaseException:
            written = False
    return 2 if written else 3


STUBS = (
    ('production-adapter',
     'missing contract: the reviewed hash inventory and the pinned JSON-schema validator are not supplied; '
     'the pins were computed from the staged copy and the validator returns True, so only wxc-exec own '
     'acceptance of the policy was observed'),
    ('effective-policy',
     'missing contract: native effective-grant and token identity read-back from inside the container '
     '(listed OPEN in F1a); the policy was observed by behaviour only'),
    ('seven-resource-classes',
     'missing contract: ACE-level per-class exclusion and any ACL read-back (path grants only; no ACL '
     'tool or API is allowed here)'),
    ('hostile-descendants',
     'missing contract: hostile creator descriptors and fixture-only handle inheritance and transfer '
     '(not done in F2 or N1)'),
    ('revocation',
     'missing contract: an applied-grant ledger or ACE read-back; path grants write no ACL, so there is '
     'nothing to revoke or read back beyond the policy leaving with the process'),
    ('disposal-quarantine',
     'missing contract: MXC profile and registration disposal verification; the fixture reader proves '
     'only that the launcher process is gone'),
    ('restart-reconciliation',
     'stand-in: Core death is a script-closed Job handle, not the death of a real Core process, and '
     'cleanup of stale protected policy files is not a production restart step'),
)


def stubs(rec):
    for case, why in STUBS:
        rec.record(case, 'INCONCLUSIVE', why)


def run(h, rec):
    h.prepare()
    step_adapter(h, rec)
    canary(h, rec, 'pre')
    step_classes(h, rec)
    canary(h, rec, 'mid')
    step_effective(h, rec)
    step_descendants(h, rec)
    step_faults(h, rec)
    step_disposal(h, rec)
    step_revocation(h, rec)
    canary(h, rec, 'post')
    step_restart(h, rec)
    stubs(rec)


def precheck_only(parent, systemroot):
    result = system32_admission(systemroot, parent)
    _say(admission_line(result))
    return 0 if result['admitted'] else 2


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    flags = {a for a in argv if a.startswith('--')}
    argv = [a for a in argv if a not in flags]
    valid = flags == {DIAG_PRECHECK} or (flags <= set(DIAG_FLAGS) and (not flags or DIAG in flags))
    if len(argv) != 1 or not parent_ok(argv[0]) or not valid:
        print('usage: python -m tools.pv20_mxc.native.n2_check <fixture-parent at or below %s; letters, '
              'digits, dot, underscore, hyphen> [--diag-precheck | --diag-descendants [--allow-image-copy] '
              '[--allow-system32-ro]]' % fixture_base(), flush=True)
        return 3
    parent = argv[0]
    if not _on_windows() or not os.path.isdir(parent):
        print('SETUP ERROR: Windows only and the parent must exist', flush=True)
        return 3
    root_env = os.environ.get('SystemRoot', '')
    if not _system_ok(root_env):
        print('SETUP ERROR: SystemRoot is not a plain drive\\Windows folder with cmd.exe', flush=True)
        return 3
    if flags == {DIAG_PRECHECK}:
        return precheck_only(parent, root_env)
    src = os.path.join(parent, *SDK_TAIL)
    if not os.path.isfile(os.path.join(src, 'package.json')):
        print(redact('SETUP ERROR: staged SDK missing under the parent (operator stages it)'), flush=True)
        return 3
    admission = system32_admission(root_env, parent) if flags else None
    if admission is not None:
        _say(admission_line(admission))
    rec, root, h, code, left = _Rec(STAGE), None, None, 3, 0
    try:
        root = safe_root(parent)
        rec.journal = os.path.join(root, JOURNAL)
        h = Harness(root, src, root_env, Budget(BUDGET_S))
        if flags:
            code = diagnose(h, flags, admission)
        else:
            run(h, rec)
            code = rec.exit_code()
    except StopRun:
        code = rec.exit_code() or 1
        _say('STOP at first FAIL; root preserved at %s' % root)
    except SetupError as ex:
        _say('SETUP ERROR: %s; root preserved at %s' % (ex, root))
    except KeyboardInterrupt:
        _say('INTERRUPTED; Jobs closed, root preserved at %s' % root)
    except Exception as ex:
        _say('UNEXPECTED ERROR: %s %s; root preserved at %s'
             % (type(ex).__name__, _snip(str(ex)), root))
    finally:
        left = h.wind_down() if h is not None else 0
    if left:
        _say('%d Job close(s) or launcher check(s) failed; root preserved' % left)
        code = 3
    if root is None or code == 3:
        return code
    try:
        return finish(code, root, remove_fixture, _say)
    except (OSError, ValueError) as ex:
        _say('SETUP ERROR: fixture not removed: %s' % _snip(str(ex)))
        return 3


if __name__ == '__main__':
    sys.exit(main())
