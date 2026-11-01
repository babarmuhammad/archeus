"""N1 native fixture-only check: two principals P/Q + Core-held Job (card T-461).

Rewritten from the reviewed draft inputs/n1_check_draft.py per the independent review
inputs/review-n1-n4-drafts.claude.md (findings N1-R1..R3, N1-S1..S5) and the native
evidence in inputs/PV20-mxc-feasibility.md (T1/T2/T4a/T4b, F1a/F1b, F2, F4 matrix).
Written in the no-network container; NOT run here. The reviewer runs it only under the
separate owner authorization for native N1-N4 fixture runs.

Usage:  python -m tools.pv20_mxc.native.n1_check <fixture-parent>
  Exactly one argument, the parent directory. The root is created by safe_root(parent)
  (fresh marker-verified direct child) and removed by remove_fixture(root) only at the
  end of a fully passed run. While the INCONCLUSIVE stubs remain, no run reaches
  all-PASS, so the root is always preserved for review.

Operator pre-stages <parent>\\sdk\\node_modules\\@microsoft\\mxc-sdk\\bin\\x64\\wxc-exec.exe
(pinned @microsoft/mxc-sdk@1.0.1, wxc-exec x64, policy schema 1.0.0, containment
processcontainer; the one-time npm staging is separately authorized and operator done).
This script creates only wa, wb, outside and *.json policies under the fresh root.

Safety posture (hard rules honoured): stdlib only; imports only the contract names
listed in common_api.md from tools.pv20_mxc.native.common; no environment variable is
read (host tools and the container's powershell.exe/cmd.exe resolve via PATH, as the
F4 matrix ran them); never kill a process this script did not start (Children.kill_own
for the launchers it started, and exact-PID taskkill for the one launcher whose death
IS the measured event; the draft's unscoped alive/sweep pair is deleted - what remains
is one READ-ONLY process snapshot filtered to Name -eq cmd.exe, which kills nothing);
no elevation, no installs, no listeners, no network at all (deny in every policy); no
home, credential or account path read, written or printed; no SID, username or machine
name ever printed (identity rows are recorded as redacted comparison booleans); every
denial is paired with a same-form positive control run as the same principal under the
same grant, so a container that never started cannot pass it; each of the 13 cases is
reported through Recorder.record as PASS, FAIL or INCONCLUSIVE using the exact
protocol.STAGES['N1'] case names; stop at the first FAIL (Recorder raises after
printing; the root is preserved); command lines are argv lists or
subprocess.list2cmdline output, never nested shell quoting; the PowerShell read path
uses -ErrorAction Stop so the non-terminating access-denied error becomes catchable
and its PermissionDenied category is the acceptance marker.

ui.disable:false is set only on the identity-probe policies because powershell.exe
fails 0xC0000142 under the default policy (measured, F4 matrix); it is an explicit
dimension of those rows, never a retry.

Cases needing a contract the inputs do not show working natively are explicit
INCONCLUSIVE stubs naming the missing contract - never a silent pass.

Exit codes: 0 all 13 cases PASS (unreachable while stubs exist) / 1 first FAIL /
2 no FAIL but an INCONCLUSIVE is present / 3 setup error before or between steps.
"""
import ctypes, json, os, re, secrets, subprocess, sys, time
from ctypes import wintypes

from tools.pv20_mxc.native.common import Recorder, Children, StopRun, safe_root, remove_fixture, redact

STAGE = 'N1'
EXE_TAIL = ('sdk', 'node_modules', '@microsoft', 'mxc-sdk', 'bin', 'x64', 'wxc-exec.exe')
PROCESS_SET_QUOTA, PROCESS_TERMINATE = 0x0100, 0x0001
PROCESS_QUERY_LIMITED, STILL_ACTIVE = 0x1000, 259
SAFE_PARENT = re.compile(r'\A[A-Za-z]:\\[A-Za-z0-9_.\\-]+\Z')
LIMKILL_ON_JOB_CLOSE = 0x2000  # values pinned in pv20-mxc-protocol-codex.md:414-422
JobObjectExtendedLimitInformation = 9

F = None
EXE = None
POLN = [0]


class SetupError(Exception):
    """Raised when the fixture or a native setup call cannot be built; nothing leaked."""


class _BASIC(ctypes.Structure):
    _fields_ = [('a', ctypes.c_int64), ('b', ctypes.c_int64), ('LimitFlags', wintypes.DWORD),
                ('c', ctypes.c_size_t), ('d', ctypes.c_size_t), ('e', wintypes.DWORD),
                ('f', ctypes.c_size_t), ('g', wintypes.DWORD), ('h', wintypes.DWORD)]


class _IO(ctypes.Structure):
    _fields_ = [(x, ctypes.c_uint64) for x in 'abcdef']


class _EXT(ctypes.Structure):
    _fields_ = [('Basic', _BASIC), ('Io', _IO), ('p', ctypes.c_size_t), ('j', ctypes.c_size_t),
                ('pk', ctypes.c_size_t), ('jk', ctypes.c_size_t)]


def _pn(tag):
    POLN[0] += 1
    return 'n1-%03d-%s' % (POLN[0], tag)


def _snip(text):
    """Detail strings always pass through redact() so no SID, username or machine
    name can reach the transcript, whatever the container echoed."""
    return redact(' '.join((text or '').split())[:120])


def _policy(name, argv, work, extra=None, timeout=60000):
    """Deny-all policy; the fixture work folder is the only grant; commandLine is
    built with subprocess.list2cmdline from an argv list (no nested shell quoting)."""
    pol = {'version': '1.0.0', 'containment': 'processcontainer',
           'lifecycle': {'destroyOnExit': True, 'preservePolicy': False},
           'process': {'commandLine': subprocess.list2cmdline(list(argv)), 'timeout': timeout},
           'filesystem': {'readwritePaths': [work]},
           'network': {'egress': {'default': 'deny'},
                       'ingress': {'default': 'deny', 'hostLoopback': 'deny'}}}
    if extra:
        pol.update(extra)
    path = os.path.join(F, name + '.json')
    with open(path, 'x', encoding='utf-8') as fh:
        json.dump(pol, fh)
    return path


def _run_container(name, argv, work, extra=None, timeout=90):
    """Start wxc-exec by argv list via subprocess.run, which owns and, on its own
    timeout, kills only this child it started. Returns (rc, out); rc None = timeout."""
    path = _policy(_pn(name), argv, work, extra)
    try:
        r = subprocess.run([EXE, '--debug', path], capture_output=True, text=True,
                           timeout=timeout, cwd=F)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except subprocess.TimeoutExpired:
        return None, 'launcher timeout'


def _cmd_snapshot(tok):
    """READ-ONLY count of the harness cmd.exe pair only: Name is filtered to cmd.exe
    so the querying powershell.exe cannot match itself, and this function kills
    nothing. Replaces the draft's unscoped alive/sweep pair entirely."""
    ps = ("(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'cmd.exe' "
          "-and $_.CommandLine -like '*in (1,1,{0})*' } | Measure-Object).Count").format(tok)
    try:
        r = subprocess.run(['powershell.exe', '-NoProfile', '-Command', ps],
                           capture_output=True, text=True, timeout=30)
        text = (r.stdout or '').strip()
        return int(text) if r.returncode == 0 and text.isdigit() else -1
    except Exception:
        return -1  # a failed query is never read as "zero survivors"


def _count_pos(tok, want, budget):
    """Poll for a positive count against a real wall-clock deadline (N1-S2)."""
    end = time.monotonic() + budget
    while True:
        if _cmd_snapshot(tok) >= want:
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(0.4)


def _wait_count0(toks, budget):
    """Shared wall-clock deadline across all tokens (draft budgeted per token)."""
    end = time.monotonic() + budget
    while True:
        if all(_cmd_snapshot(t) == 0 for t in toks):
            return True
        if time.monotonic() >= end:
            return False
        time.sleep(0.4)


def _alive(pid):
    """Exit-code probe through a query-only handle. os.kill is not usable here: on
    Windows every signal value except the two console events calls TerminateProcess."""
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not h:
        return False
    try:
        code = wintypes.DWORD(0)
        return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == STILL_ACTIVE
    finally:
        k.CloseHandle(h)


def _new_token():
    """Per-run random 9-digit token via secrets, not a pre-publishable constant (R1)."""
    return str(secrets.randbelow(900000000) + 100000000)


def _loop_argv(tok):
    """The only matchable children: the cmd.exe /c cmd.exe /c for-loop pair, built as
    an argv list; for /l needs an integer literal, so the token is digits only."""
    return ['cmd.exe', '/c', 'cmd.exe', '/c', 'for', '/l', '%i', 'in',
            '(1,1,%s)' % tok, 'do', '@rem', 'x']


def _probe_argv(target, evid):
    """Identity + read probe in one container run, powershell.exe direct (no cmd
    wrapper, hence no nested quoting). Get-Content runs with -ErrorAction Stop so an
    access-denied read is a catchable terminating error (N1-R3). Success leaves the
    target content in evid, written INSIDE the caller's granted folder and checked
    host-side; a denied read leaves no evid and shows the PermissionDenied category."""
    script = ('$i=[Security.Principal.WindowsIdentity]::GetCurrent();'
              "'USER='+$i.User.Value;'GROUPS='+($i.Groups|%%{$_.Value}) -join ',';"
              "try{Get-Content -ErrorAction Stop -LiteralPath '%s'|"
              "Out-File -Encoding ascii -LiteralPath '%s'}"
              "catch{'READ_'+'DENIED'}") % (target, evid)
    return ['powershell.exe', '-NoProfile', '-Command', script]


def _canary(rec, tag, wa):
    """Container write to F\\outside while only wa is granted, paired with a same-form
    positive control (write inside the grant) in the same group, so a container that
    never started cannot pass vacuously (N1-S5). True = canary held."""
    ctl = os.path.join(wa, 'ctl_%s.txt' % tag)
    rc, out = _run_container('ctl_' + tag, ['cmd.exe', '/c', 'echo X>%s' % ctl], wa)
    if rc != 0 or not os.path.exists(ctl):
        rec.record('positive-controls', 'FAIL',
                   'canary %s paired control (write inside grant) did not run: rc=%s %s'
                   % (tag, rc, _snip(out)))
        return False
    br = os.path.join(F, 'outside', 'breach_%s.txt' % tag)
    rc2, out2 = _run_container('canary_' + tag, ['cmd.exe', '/c', 'echo X>%s' % br], wa)
    if os.path.exists(br):
        rec.record('positive-controls', 'FAIL',
                   'CONTAINMENT BREACH (%s): wrote outside the granted folder' % tag)
        return False
    if rc2 is None:
        rec.record('positive-controls', 'FAIL',
                   'canary %s launcher did not run: %s' % (tag, _snip(out2)))
        return False
    rec.record('positive-controls', 'PASS',
               'canary %s: control wrote inside grant, outside write absent' % tag)
    return True


def _read_pair(rec, label, reader_work, own_seed, own_evid, target, evid, secret, own_secret, ui):
    """Run the same probe form twice as the SAME principal: the positive control reads
    the principal's OWN seed and must produce the evidence content (proves the
    container ran and the probe works); the denial then attempts the peer seed and
    must produce no evidence file and no secret content. Returns the control output
    (for the identity booleans) or None when a FAIL was already recorded. The ui
    dimension (ui.disable:false, measured need for powershell.exe) is identical in
    the control and the denial run."""
    rc0, out0 = _run_container('pos-' + label, _probe_argv(own_seed, own_evid), reader_work, ui)
    ctl_txt = ''
    if os.path.exists(own_evid):
        try:
            with open(own_evid, encoding='utf-8', errors='replace') as fh:
                ctl_txt = fh.read()
        except OSError:
            ctl_txt = ''
    if rc0 is None or own_secret not in ctl_txt:
        rec.record('p-q-token-psec', 'FAIL',
                   '%s positive control (same probe on own seed) produced no evidence: rc=%s %s'
                   % (label, rc0, _snip(out0)))
        return None
    rc1, out1 = _run_container('den-' + label, _probe_argv(target, evid), reader_work, ui)
    low = (out1 or '').lower()
    if os.path.exists(evid) or secret.lower() in low:
        rec.record('p-q-token-psec', 'FAIL',
                   'CONTAINMENT BREACH (%s): peer secret content reached the container' % label)
        return None
    if not ('permissiondenied' in low or 'read_denied' in low or 'denied' in low):
        # Fail closed: a denial whose error we cannot name is not a proven denial.
        # Accepted markers per N1-R3: PermissionDenied category (feasibility:46),
        # the catch-printed READ_DENIED, or a generic denied category.
        rec.record('p-q-token-psec', 'FAIL',
                   '%s denial marker missing (fail closed): %s' % (label, _snip(out1)))
        return None
    rec.record('p-q-token-psec', 'PASS',
               '%s denied with same-form control passed (rc=%s %s)' % (label, rc1, _snip(out1)))
    return out0


def _list_pair(rec, case, label, work, granted_dir, ctl_file, denied_dir, denied_file):
    """dir-based row, same principal: the control lists the granted folder and must
    show a known file (proves the container ran); the denial lists a non-granted
    folder and must not show ITS known file. True = row passed, False = FAIL recorded."""
    rc0, out0 = _run_container('pos-' + label, ['cmd.exe', '/c', 'dir', '/b', granted_dir], work)
    if rc0 != 0 or ctl_file.lower() not in (out0 or '').lower():
        rec.record(case, 'FAIL', '%s positive control (dir of granted folder) failed: rc=%s %s'
                   % (label, rc0, _snip(out0)))
        return False
    rc1, out1 = _run_container('den-' + label, ['cmd.exe', '/c', 'dir', '/b', denied_dir], work)
    if denied_file.lower() in (out1 or '').lower():
        rec.record(case, 'FAIL', 'CONTAINMENT BREACH (%s): non-granted folder listed' % label)
        return False
    rec.record(case, 'PASS', '%s not listed with same-form control passed (rc=%s %s)'
               % (label, rc1, _snip(out1)))
    return True


def _step_job(rec, kids):
    """outer-job-close + child-grandchild: two launchers, each holding a 2-process
    cmd.exe tree, all in ONE Core-held KILL_ON_JOB_CLOSE job; every native return
    value is checked (lesson of N3-S4)."""
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.SetInformationJobObject.restype = wintypes.BOOL
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.AssignProcessToJobObject.restype = wintypes.BOOL
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    job = k.CreateJobObjectW(None, None)
    if not job:
        raise SetupError('CreateJobObjectW failed err=%d' % ctypes.get_last_error())
    lim = _EXT()
    lim.Basic.LimitFlags = LIMKILL_ON_JOB_CLOSE
    if not k.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                     ctypes.byref(lim), ctypes.sizeof(lim)):
        err = ctypes.get_last_error()
        k.CloseHandle(job)
        raise SetupError('SetInformationJobObject(KILL_ON_JOB_CLOSE) failed err=%d' % err)
    toks, pids = [], []
    for w in (os.path.join(F, 'wa'), os.path.join(F, 'wb')):
        tok = _new_token()
        pid = kids.start([EXE, _policy(_pn('job'), _loop_argv(tok), w, timeout=200000)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=F)
        h = k.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not h:
            err = ctypes.get_last_error()
            raise SetupError('OpenProcess(owned launcher %d) failed err=%d' % (pid, err))
        ok = k.AssignProcessToJobObject(job, h)
        k.CloseHandle(h)
        if not ok:
            err = ctypes.get_last_error()
            raise SetupError('AssignProcessToJobObject failed err=%d' % err)
        toks.append(tok)
        pids.append(pid)
    started = [_count_pos(t, 1, 30) for t in toks]  # wall-clock startup wait (replaces fixed 8 s sleep)
    before = [_cmd_snapshot(t) for t in toks]
    alive_pids = [_alive(p) for p in pids]
    if not all(started) or not all(alive_pids) or not all(b > 0 for b in before):
        # not a silent pass and not a vacuous one: a container that never started FAILs
        rec.record('child-grandchild', 'FAIL',
                   'trees not alive before job close (not all containers started): before=%s pids=%s'
                   % (before, alive_pids))
        return False
    rec.record('child-grandchild', 'INCONCLUSIVE',
               'cmd.exe /c cmd.exe /c trees observed alive via Name-filtered read-only counts '
               '(before=%s) and killed by the job close; missing contract: per-process principal and '
               'Core-Job membership verification of each descendant (F1b proves tree death, not membership)'
               % before)
    if not k.CloseHandle(job):  # the Core-death kernel event (feasibility:45)
        err = ctypes.get_last_error()
        rec.record('outer-job-close', 'FAIL', 'CloseHandle(Core job handle) failed err=%d' % err)
        return False
    if not (_wait_count0(toks, 5.0) and not any(_alive(p) for p in pids)):
        rec.record('outer-job-close', 'FAIL',
                   'survivors within 5 s wall-clock after closing the Core-held job; unowned survivors '
                   'preserved for review, kill_own covers only launchers this script started')
        return False
    rec.record('outer-job-close', 'PASS',
               'both trees and both launchers gone within 5 s wall-clock of CloseHandle (F1b pattern)')
    return True


def _step_launcher(rec, kids):
    """launcher-death: taskkill the ONLY launcher this script started here (exact PID
    via argv list, N1-S3 style: nothing is ever killed that the script did not start)
    and verify the whole tree is gone within 5 s wall-clock (T4a)."""
    tok = _new_token()
    wa = os.path.join(F, 'wa')
    pid = kids.start([EXE, _policy(_pn('kill'), _loop_argv(tok), wa, timeout=200000)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=F)
    if not (_count_pos(tok, 1, 30.0) and _alive(pid)):
        rec.record('launcher-death', 'FAIL',
                   'tree/launcher not alive before kill (container did not start)')
        return False
    killed = kids.kill_own()
    if not (killed >= 1 and _wait_count0([tok], 5.0) and not _alive(pid)):
        rec.record('launcher-death', 'FAIL',
                   'survivors within 5 s wall-clock after killing the owned launcher (killed=%s); '
                   'survivors preserved for review, never swept' % killed)
        return False
    rec.record('launcher-death', 'PASS',
               'tree gone within 5 s wall-clock after terminating the launcher the '
               'script itself started, identity-checked by creation time (T4a)')
    return True


def _stubs(rec):
    """Every case the inputs do not show working natively is an explicit INCONCLUSIVE
    stub naming the missing contract - never a silent pass."""
    rec.record('hardlink-grant-refusal', 'INCONCLUSIVE',
               'missing contract: host-side pre-grant link-count scan and re-scan at launch; F2c/F2d proved '
               'a host hardlink inside the grant escapes read+write, so this script must never launch a '
               'container over a hardlink-bearing grant (the gate is the n3/F2 A5-A7 work)')
    rec.record('access-matrix', 'INCONCLUSIVE',
               'sibling-write and outside/ancestor-list rows executed with paired controls; missing '
               'contract for the rest of the matrix: junction and protected-DACL rows (alias staging and '
               'DACL authoring not shown working natively; F2f marks the protected-DACL read info-only)')
    rec.record('hostile-creator-ancestor-acls', 'INCONCLUSIVE',
               'missing contract: hostile creator ACE staging on named principals plus effective-ACL '
               'readback (explicitly not done in F2; needs contracts/privileges the inputs do not provide)')
    rec.record('aliases', 'INCONCLUSIVE',
               'missing contract: safe fixture-local alias (junction/symlink) staging plus pre-launch '
               'reparse scan (junction behaviour measured in F2/N3 scope only; symlink needs privilege)')
    rec.record('handle-transfer', 'INCONCLUSIVE',
               'missing contract: fixture-only handle creation/transfer and inheritance verification '
               '(explicitly not done in F2)')
    rec.record('synthetic-authority-denial', 'INCONCLUSIVE',
               'missing contract: synthetic credential-authority resource and denial model (credential '
               'authority denial is listed as NOT tested in PV20-mxc-feasibility.md)')
    rec.record('core-death', 'INCONCLUSIVE',
               'stand-in only: closing the Core-held job handle is the same kernel event per '
               'feasibility:45 and is recorded under outer-job-close; missing contract: a real fixture '
               'Core process whose death (not a handle close) is the measured event')
    rec.record('stale-reopen', 'INCONCLUSIVE',
               'missing contract: MXC disposal verification and a stale-reopen probe (listed as untested; '
               'no native disposal binding exists in the reviewed inputs)')


def run(rec, kids):
    wa, wb = os.path.join(F, 'wa'), os.path.join(F, 'wb')
    for d in (wa, wb, os.path.join(F, 'outside')):
        os.makedirs(d, exist_ok=True)
    with open(os.path.join(F, 'outside', 'known.txt'), 'x', encoding='utf-8') as fh:
        fh.write('known')

    # ---- positive-controls: cmd.exe echo under the default (UI-blocked) policy, T1.
    # The command line carries MXC-N^1 so a --debug policy echo cannot fake the
    # MXC-N1 output (N1-S4); rc==0 is required on top of the sentinel.
    rc, out = _run_container('echo', ['cmd.exe', '/d', '/c', 'echo', 'MXC-N^1'], wa)
    if rc != 0 or 'MXC-N1' not in out:
        rec.record('positive-controls', 'FAIL', 'default-policy cmd.exe echo control: rc=%s %s'
                   % (rc, _snip(out)))
        return
    rec.record('positive-controls', 'PASS',
               'default-policy cmd.exe echo control (T1, caret-differentiated sentinel)')

    if not _canary(rec, 'pre', wa):
        return

    # seeds are host-side writes into the two folders (mxc_diag2 pattern); the values
    # carry a per-run random suffix so a stale transcript cannot reuse them
    seed_a = 'SECRET_A_%s' % _new_token()
    seed_b = 'SECRET_B_%s' % _new_token()
    with open(os.path.join(wa, 'secret_a.txt'), 'x', encoding='utf-8') as fh:
        fh.write(seed_a)
    with open(os.path.join(wb, 'secret_b.txt'), 'x', encoding='utf-8') as fh:
        fh.write(seed_b)

    # ---- p-q-token-psec: F1a behaviour (each instance reads its own folder, not the
    # peer's), both directions, every denial paired with the same-form control as the
    # same principal. powershell.exe needs ui.disable:false (measured 0xC0000142
    # otherwise, F4 matrix): an explicit dimension of these rows, never a retry.
    ui = {'ui': {'disable': False}}
    # each _read_pair first re-runs the SAME probe as a positive control on the
    # principal's OWN seed (must yield the evidence content), then the denial; the
    # control output doubles as the identity-probe source for that principal
    out_p = _read_pair(rec, 'p-reads-q', wa, os.path.join(wa, 'secret_a.txt'),
                       os.path.join(wa, 'ev_pb.txt'), os.path.join(wb, 'secret_b.txt'),
                       os.path.join(wa, 'ev_db.txt'), seed_b, seed_a, ui)
    if out_p is None:
        return
    out_q = _read_pair(rec, 'q-reads-p', wb, os.path.join(wb, 'secret_b.txt'),
                       os.path.join(wb, 'ev_qb.txt'), os.path.join(wa, 'secret_a.txt'),
                       os.path.join(wb, 'ev_dqb.txt'), seed_a, seed_b, ui)
    if out_q is None:
        return
    # N1-S1: identity rows are comparison booleans only; raw SIDs are never printed.
    ua = re.search(r'USER=(\S+)', out_p)
    ub = re.search(r'USER=(\S+)', out_q)
    ga = re.search(r'GROUPS=([^\r\n]+)', out_p)
    gb = re.search(r'GROUPS=([^\r\n]+)', out_q)
    if not (ua and ub and ga and gb):
        rec.record('p-q-token-psec', 'FAIL',
                   'identity probe did not emit USER=/GROUPS= in both own-read controls')
        return
    rec.record('p-q-token-psec', 'PASS',
               'token rows record-only, redacted booleans (feasibility:46: not AppContainer): '
               'user_sid_equal=%s groups_equal=%s; separation proven by behaviour, not token inspection'
               % (ua.group(1) == ub.group(1), ga.group(1) == gb.group(1)))

    # ---- access-matrix rows needing no new contract: sibling write denial and the
    # two list rows (F2 PASS rows), each with its same-form control.
    ctl_wa = _run_container('w-ctl', ['cmd.exe', '/c', 'echo W>%s' % os.path.join(wa, 'ok2.txt')], wa)
    if ctl_wa[0] != 0 or not os.path.exists(os.path.join(wa, 'ok2.txt')):
        rec.record('access-matrix', 'FAIL', 'in-grant write control did not run: rc=%s %s'
                   % (ctl_wa[0], _snip(ctl_wa[1])))
        return
    sib = os.path.join(wb, 'sibling.txt')
    _run_container('w-sib', ['cmd.exe', '/c', 'echo X>%s' % sib], wa)
    if os.path.exists(sib):
        rec.record('access-matrix', 'FAIL', 'CONTAINMENT BREACH: wrote into non-granted peer folder')
        return
    rec.record('access-matrix', 'PASS', 'sibling-folder write denied with in-grant write control passed (T2)')
    if not _list_pair(rec, 'access-matrix', 'outside-list', wa, wa, 'ctl_pre.txt',
                      os.path.join(F, 'outside'), 'known.txt'):
        return
    if not _list_pair(rec, 'access-matrix', 'wa-list-denied', wb, wb, 'secret_b.txt',
                      wa, 'secret_a.txt'):
        return
    if not _list_pair(rec, 'access-matrix', 'ancestor-list-denied', wa, wa, 'ctl_pre.txt',
                      F, 'outside'):
        return

    if not _canary(rec, 'mid', wa):
        return

    if not _step_job(rec, kids):
        return
    if not _step_launcher(rec, kids):
        return

    if not _canary(rec, 'post', wa):
        return

    _stubs(rec)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 1 or not os.path.isdir(argv[0]):
        print(redact('usage: python -m tools.pv20_mxc.native.n1_check <fixture-parent>'), flush=True)
        return 3
    if not SAFE_PARENT.match(argv[0]):
        print('SETUP ERROR: parent must be an absolute drive path of letters, digits, dot, '
              'underscore and hyphen only (it reaches cmd and PowerShell command lines)', flush=True)
        return 3
    parent = argv[0]
    global F, EXE
    EXE = os.path.join(parent, *EXE_TAIL)
    if not os.path.isfile(EXE):
        print(redact('SETUP ERROR: pinned wxc-exec missing at %s (operator stages the SDK)' % EXE),
              flush=True)
        return 3
    rec = Recorder(STAGE)
    kids = Children()
    try:
        F = safe_root(parent)
        run(rec, kids)
    except StopRun:  # Recorder raised after printing the first FAIL
        kids.kill_own()
        print(redact('STOP at first FAIL; root preserved at %s' % F), flush=True)
        return rec.exit_code() or 1
    except SetupError as ex:
        kids.kill_own()
        print(redact('SETUP ERROR: %s; root preserved at %s' % (ex, F)), flush=True)
        return 3
    except Exception as ex:  # any unexpected error: preserve everything, kill only owned
        kids.kill_own()
        print(redact('UNEXPECTED ERROR: %s; root preserved at %s'
                     % (type(ex).__name__, F)), flush=True)
        return 3
    kids.kill_own()
    code = rec.exit_code()
    if code == 0:
        remove_fixture(F)
        print(redact('all 13 cases PASS; fixture removed (%s)' % F), flush=True)
    else:
        print(redact('run finished with code %d; root preserved at %s' % (code, F)), flush=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
