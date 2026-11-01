"""Native N3 fixture-only check: hardlink gate + origin attestor + network boundary.

Card T-463 rewrite of the reviewed draft (inputs/n3_check_draft.py) applying every
Required and Should finding of the independent review
(/work/inputs/review-n1-n4-drafts.claude.md) for n3:

  N3-R1  empty-root vs staged-SDK deadlock: the fixture root is now created by
         ``safe_root(parent)`` from tools.pv20_mxc.native.common (fresh uuid4 name), and
         the operator-staged SDK lives OUTSIDE it at ``<parent>\\sdk`` and is COPIED into
         the root before any check. Neither the emptiness test nor the SDK pre-stage can
         contradict the other, so the preflight cannot deadlock.
  N3-R2  the deny-all baseline (B2) now points the container client AT THE LISTENER
         (``curl -s -m 6 --noproxy * http://127.0.0.1:<pport>/denybase`` under the deny-all
         policy, the F3c form of mxc_diag3.py:32) instead of a never-resolving
         ``.invalid`` host, so 0 hits is not guaranteed by construction, and it expects
         curl exit 7 (a refused/blocked connect), which is the pinned observation
         (PV20-mxc-feasibility.md:11, :48). ``client_run`` takes an explicit command.
  N3-R3  no denial is recorded from a leak check alone: every denial case (a) carries a
         positive control INSIDE THE SAME container command line (a work-folder
         ``type prot.txt`` printing PROTECTED_IN plus an ``echo`` proof file the script
         verifies host-side), (b) requires ``rc`` to be an int (never 'timeout'), and
         (c) is additionally bracketed by the same-form asserted positive controls A1p,
         A7, B0, B0f, B1 and the paired canaries in this same script run, so a container
         that never started cannot pass any denial row.
  N3-S1  gate_scan fail-closed: entries that raise OSError land in ``blocked`` and DO
         block a launch (the draft listed them under reparse points, which did not block).
  N3-S2  gate_scan prunes Windows junctions instead of descending them
         (``st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT``; ``os.walk`` alone does
         not skip junctions).
  N3-S3  the delayed-attestation case REQUIRES a late record; a missing late record is no
         longer a pass — it is recorded INCONCLUSIVE and the run stops.
  N3-S4  ``SetInformationJobObject`` and ``AssignProcessToJobObject`` returns are checked,
         and the launcher's Core-Job membership is asserted before any attestation record
         that relies on ``in_core_job`` is trusted.
  N3-S5  every host-side curl now carries ``--noproxy *`` (as separate argv items), so an
         operator ``http_proxy`` can never push a "loopback-only" request to an external
         proxy. The container deny-all/blocked curls carry it too.
  N3-S6  a forbidden-listener control was added: a host control proves the forbidden
         listener logs hits, and under the proxy policy the container is blocked from it
         (0 hits, curl exit 7), showing the WFP boundary beyond the proxy endpoint holds
         on this run (form PINNED PV20-mxc-feasibility.md:48).

Hard rules honored (card T-463): stdlib only; the single non-stdlib import is exactly the
common_api.md names from ``tools.pv20_mxc.native.common`` (written by card T-460; this
checkout does not carry it). One parent-directory argument; the fixture root is created by
``safe_root(parent)`` and removed by ``remove_fixture(root)`` ONLY at the end of a fully
passed run (preserved on FAIL, on setup errors and under --keep). No process is ever killed
except through ``Children.kill_own()`` over the processes this script started (no
command-line sweep, no PowerShell at all, therefore also no -ErrorAction Stop concern). No
elevation, no installs, no network except this script's own 127.0.0.1 listeners. No home,
credential or account path is read, written or printed; the only environment reads are
``SystemRoot`` (absolute curl path, form PINNED mxc_diag2.py:4). The script runs no ACL
tool: the repo's static gate forbids one anywhere under tools/.
Nothing is printed that did not pass through ``Recorder.record`` or ``redact``; no SID,
token, username or machine name is ever produced. Every case is reported through
``Recorder.record`` as PASS, FAIL or INCONCLUSIVE using the frozen case names from
tools/pv20_mxc/protocol.py ``STAGES['N3']``; the run stops at the first FAIL (Recorder
raises StopRun). All command lines are built with argv lists or
``subprocess.list2cmdline`` — never nested shell quoting (hence: the parent path must
contain no spaces; refused at setup). The journal ``n3_results.json`` under the root is
rewritten after every verdict and preserved with the root on any stop.

Not run by Qwen. Claude reviews and runs only under the owner's separate fixture-only
authorization.

Usage (reviewer, from the repo root, after owner authorization):
    python -m tools.pv20_mxc.native.n3_check <fixture-parent> [--keep]
The operator pre-stages the SDK (one-time ``npm install @microsoft/mxc-sdk@1.0.1
--ignore-scripts``, separately authorized) at
    <fixture-parent>\\sdk\\node_modules\\@microsoft\\mxc-sdk\\bin\\x64\\wxc-exec.exe
which this script copies into the fresh fixture root and never otherwise touches.

Exit codes: Recorder.exit_code() — 0 all PASS, 1 any FAIL (stopped at first), 2 any
INCONCLUSIVE (the four MISSING stubs always make a clean run end at 2); 3 setup/preflight
refusal; 2 (with preserved root) on a containment-breach stop.
"""

import ctypes
import http.server
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
from ctypes import wintypes

from tools.pv20_mxc.native.common import (
    Children,
    Recorder,
    StopRun,
    redact,
    remove_fixture,
    safe_root,
)
from tools.pv20_mxc.protocol import STAGES

N3_CASES = STAGES["N3"].cases

# Cases the inputs do not support; reported as explicit INCONCLUSIVE stubs (card T-463).
MISSING_STUBS = (
    ("forbidden-ipv4-ipv6-descendants",
     "MISSING: no IPv6 listener and no descendant-process variant is attempted in this "
     "run; only an IPv4 forbidden-listener control exists (recorded under "
     "deny-all-both-directions)."),
    ("malformed-replay-destination-model-redirect-limits",
     "MISSING: no malformed/replayed request, destination-model change, or redirect "
     "limit is exercised; no stub exists."),
    ("privileged-effect-origin-matrix",
     "MISSING: no privileged-effect matrix is run; the single ACCEPT condition lives "
     "under broker-reach."),
    ("revocation-broker-core-death",
     "MISSING: no mid-run grant revocation and no real Core/wxc-exec death during an "
     "open broker session is attempted."),
)

EXIT_BREACH = 2
EXIT_SETUP = 3
SAFE_PARENT = re.compile(r"\A[A-Za-z]:\\[A-Za-z0-9_.\\-]+\Z")
REPARSE = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT (INFERRED constant, as in fixtures.py)
FILETIME_BITS = 32
PROCESS_QUERY_LIMITED = 0x001000
PROCESS_SET_QUOTA = 0x000100
PROCESS_TERMINATE = 0x000001
PROCESS_SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x00000102
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
iphlpapi = ctypes.WinDLL("iphlpapi")
k32.CreateJobObjectW.restype = wintypes.HANDLE
k32.OpenProcess.restype = wintypes.HANDLE
k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
k32.AssignProcessToJobObject.restype = wintypes.BOOL
k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                        wintypes.DWORD]
k32.SetInformationJobObject.restype = wintypes.BOOL
k32.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
k32.WaitForSingleObject.restype = wintypes.DWORD
k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
k32.GetExitCodeProcess.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]
k32.GetProcessTimes.restype = wintypes.BOOL
_FT = ctypes.POINTER(wintypes.FILETIME)
k32.GetProcessTimes.argtypes = [wintypes.HANDLE, _FT, _FT, _FT, _FT]


class SetupError(Exception):
    """Preflight refusal: nothing was launched, exit 3, root preserved."""


class Row(ctypes.Structure):  # mxc_f9.py:27-28 shape (verbatim)
    _fields_ = [("state", wintypes.DWORD), ("la", wintypes.DWORD), ("lp", wintypes.DWORD),
                ("ra", wintypes.DWORD), ("rp", wintypes.DWORD), ("pid", wintypes.DWORD)]


class ProcEntry32(ctypes.Structure):  # mxc_f9.py:47-48 shape (verbatim)
    _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                ("h", ctypes.c_void_p), ("m", wintypes.DWORD), ("t", wintypes.DWORD),
                ("ppid", wintypes.DWORD), ("pc", ctypes.c_long), ("f", wintypes.DWORD),
                ("exe", ctypes.c_char * 260)]


class BasicLimitInfo(ctypes.Structure):  # mxc_f9.py:118-119 (verbatim)
    _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", wintypes.DWORD),
                ("f", ctypes.c_size_t), ("g", wintypes.DWORD), ("h", wintypes.DWORD)]


class IoLimitInfo(ctypes.Structure):  # mxc_f9.py:122-123 (verbatim)
    _fields_ = [(x, ctypes.c_uint64) for x in "abcdef"]


class ExtendedLimitInfo(ctypes.Structure):  # mxc_f9.py:126-127 (verbatim)
    _fields_ = [("Basic", BasicLimitInfo), ("Io", IoLimitInfo), ("p", ctypes.c_size_t),
                ("j", ctypes.c_size_t), ("pk", ctypes.c_size_t), ("jk", ctypes.c_size_t)]


def tcp_owner(cport, sport):
    """Owning PID of the (client port, server port) IPv4 ESTABLISHED pair (mxc_f9.py:31-44)."""
    size = wintypes.DWORD(0)
    iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 5, 0)
    buf = ctypes.create_string_buffer(size.value + 4096)
    size = wintypes.DWORD(len(buf))
    if iphlpapi.GetExtendedTcpTable(buf, ctypes.byref(size), False, 2, 5, 0):
        return None
    n = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0]
    rows = (Row * n).from_buffer(buf, 4)

    def sw(p):
        return ((p & 0xFF) << 8) | ((p >> 8) & 0xFF)

    for r in rows:
        if sw(r.lp & 0xFFFF) == cport and sw(r.rp & 0xFFFF) == sport:
            return r.pid
    return None


def proc_snapshot():
    """pid -> (parent pid, exe name) (mxc_f9.py:51-61)."""
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    pe = ProcEntry32()
    pe.size = ctypes.sizeof(pe)
    out = {}
    ok = k32.Process32First(snap, ctypes.byref(pe))
    while ok:
        out[pe.pid] = (pe.ppid, pe.exe.decode(errors="replace"))
        ok = k32.Process32Next(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return out


def in_job(pid, job):
    """IsProcessInJob (mxc_f9.py:64-71); None = cannot check."""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not h:
        return None
    r = wintypes.BOOL()
    k32.IsProcessInJob(h, job, ctypes.byref(r))
    k32.CloseHandle(h)
    return bool(r.value)


def creation_time(pid):
    """Process creation time via GetProcessTimes (ctypes form INFERRED; binding the PID
    plus creation time at accept is REQUIRED per PV20-mxc-feasibility.md:65 rule (1)).
    None = cannot bind -> the attestor must fail closed."""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not h:
        return None
    c = wintypes.FILETIME()
    e = wintypes.FILETIME()
    ka = wintypes.FILETIME()
    u = wintypes.FILETIME()
    ok = k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(ka),
                             ctypes.byref(u))
    k32.CloseHandle(h)
    if not ok:
        return None
    return (c.dwHighDateTime << FILETIME_BITS) | c.dwLowDateTime


class AttestorHandler(http.server.BaseHTTPRequestHandler):
    """Listener of mxc_f9.py:91-107 with the pinned deviation: attestation runs AT ACCEPT,
    before the response (PV20-mxc-feasibility.md:65 rule (3)); the delayed re-resolution
    is a comparison record, never the verdict."""

    def do_GET(self):
        st = self.server.state
        cport = self.client_address[1]
        sport = self.server.server_address[1]
        port = sport
        st["log"].append((port, self.path, "accept",
                          attest(cport, sport, st["wxc"], st["job"])))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"OK")
        self.wfile.flush()
        if st["delay"] > 0:
            time.sleep(st["delay"] / 1000)
            st["log"].append((port, self.path, "late",
                              attest(cport, sport, st["wxc"], st["job"])))

    def log_message(self, *a):
        pass


def attest(cport, sport, wxc_pid, job):
    """mxc_f9.py:74-86 chain walk plus the pinned fail-closed reading
    (PV20-mxc-feasibility.md:65 rules (1)(2)): the TCP table alone never accepts; a dead
    owner PID or an unbindable creation time is REJECT."""
    pid = tcp_owner(cport, sport)
    if not pid:
        return {"pid": None, "verdict": "UNRESOLVED"}
    procs = proc_snapshot()
    alive = pid in procs
    ct = creation_time(pid)
    chain = []
    p = pid
    while p in procs and len(chain) < 12:  # chain walk from mxc_f9.py:78-83
        chain.append(procs[p][1])
        p = procs[p][0]
        if p == wxc_pid:
            chain.append("wxc-exec(root)")
            break
    rec = {"pid": pid, "exe": procs.get(pid, (0, "?"))[1] if alive else "?gone",
           "alive": alive, "ctime": ct,
           "ancestry_has_wxc": "wxc-exec(root)" in chain,
           "in_core_job": in_job(pid, job), "chain": chain}
    if not alive:
        rec["verdict"] = "REJECT_DEAD"
    elif ct is None:
        rec["verdict"] = "REJECT_NOBIND"
    elif not rec["ancestry_has_wxc"]:
        rec["verdict"] = "REJECT_ANCESTRY"
    elif not rec["in_core_job"]:
        rec["verdict"] = "REJECT_NOJOB"
    else:
        rec["verdict"] = "ACCEPT"
    return rec


class N3Check:
    def __init__(self, parent, rec):
        if not SAFE_PARENT.match(parent):
            # The root path reaches cmd.exe command lines (echo/type/dir chains), where
            # & ^ % ( ) ! quotes and spaces would change the command.
            raise SetupError("fixture parent must be an absolute drive path of letters, "
                             "digits, dot, underscore and hyphen only")
        self.rec = rec
        self.CH = Children()
        self.journal = []
        self.nspawns = 0
        self.F = safe_root(parent)
        self.RJ = os.path.join(self.F, "n3_results.json")
        sysroot = os.environ.get("SystemRoot")
        if not sysroot:
            raise SetupError("SystemRoot unavailable (setup only; never printed)")
        src = os.path.join(parent, "sdk", "node_modules", "@microsoft", "mxc-sdk")
        if not os.path.isfile(os.path.join(src, "bin", "x64", "wxc-exec.exe")):
            raise SetupError("staged SDK missing under <parent>\\sdk "
                             "(one-time separately authorized npm install --ignore-scripts)")
        node = parent
        for part in ("sdk", "node_modules", "@microsoft", "mxc-sdk"):
            node = os.path.join(node, part)
            if getattr(os.lstat(node), "st_file_attributes", 0) & REPARSE:
                raise SetupError("staged SDK path passes through a link or junction")
        _hl, rp, blocked = self.gate_scan(src)
        if rp or blocked:
            raise SetupError("staged SDK contains links, junctions or unreadable entries")
        # N3-R1: the SDK is staged OUTSIDE the created root and copied IN; the root is
        # always fresh (safe_root created it), so emptiness and pre-stage cannot conflict.
        try:
            shutil.copytree(src, os.path.join(self.F, "sdk", "node_modules", "@microsoft", "mxc-sdk"))
        except OSError as ex:
            raise SetupError("cannot copy staged SDK into the fixture: %r" % (ex,)) from ex
        self.EXE = os.path.join(self.F, "sdk", "node_modules", "@microsoft", "mxc-sdk",
                                "bin", "x64", "wxc-exec.exe")
        if not os.path.isfile(self.EXE):
            raise SetupError("SDK copy incomplete")
        self.CURL = os.path.join(sysroot, "System32", "curl.exe")
        if not os.path.isfile(self.CURL):
            raise SetupError("absolute curl.exe path missing (form PINNED mxc_diag2.py:4)")
        self.W = os.path.join(self.F, "work")      # the ONLY read-write grant
        self.O = os.path.join(self.F, "outside")   # canary target, never granted
        self.SEC = os.path.join(self.O, "secret.txt")
        self.PROT = os.path.join(self.W, "prot.txt")
        self.JX = os.path.join(self.W, "jx")
        self.state = {"delay": 0, "wxc": 0, "job": None, "log": []}
        self.used = set()

    # ------------------------------------------------------------------ reporting
    def check(self, case, status, detail=""):
        if case not in N3_CASES:
            raise AssertionError("case name %r is not in protocol STAGES['N3']" % (case,))
        self.used.add(case)
        self.journal.append({"case": case, "status": status, "detail": redact(detail)})
        try:
            with open(self.RJ, "w", encoding="utf-8") as fh:
                json.dump(self.journal, fh, indent=1)
        except OSError:
            pass
        self.rec.record(case, status, redact(detail))  # FAIL raises StopRun after printing

    def breach(self, msg):
        """Containment breach: stop at once, exit 2, root preserved (draft posture kept)."""
        self.journal.append({"case": "BREACH", "status": "FAIL", "detail": redact(msg)})
        try:
            with open(self.RJ, "w", encoding="utf-8") as fh:
                json.dump(self.journal, fh, indent=1)
        except OSError:
            pass
        print(redact("CONTAINMENT BREACH -> STOP (%s); root preserved at %s (journal %s)"
                     % (msg, self.F, self.RJ)), flush=True)
        sys.exit(EXIT_BREACH)

    def setup_tool(self, argv):
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired as ex:
            raise SetupError("fixture staging tool timed out: %r" % (ex,)) from ex
        if r.returncode != 0:
            raise SetupError("fixture staging mklink failed (rc %s)" % r.returncode)

    # ------------------------------------------------------------------ hardlink gate
    def gate_scan(self, folder):
        """Hard gate (PV20-mxc-feasibility.md:57: scan before grant, re-scan at launch).
        Regular files with st_nlink > 1 block; entries that cannot be lstat'ed block too
        (N3-S1 fail-closed); reparse points are listed but pruned from the descent, never
        followed (N3-S2)."""
        hl, rp, blocked = [], [], []
        for root, dirs, files in os.walk(folder):
            keep = []
            for n in dirs:
                fp = os.path.join(root, n)
                try:
                    st = os.lstat(fp)
                except OSError:
                    blocked.append(fp)
                    continue
                if getattr(st, "st_file_attributes", 0) & REPARSE:
                    rp.append(fp)  # junction/symlink: listed, NOT descended (N3-S2)
                    continue
                keep.append(n)
            dirs[:] = keep
            for n in files:
                fp = os.path.join(root, n)
                try:
                    st = os.lstat(fp)
                except OSError:
                    blocked.append(fp)  # N3-S1: unreadable entries FAIL CLOSED
                    continue
                if stat.S_ISREG(st.st_mode) and getattr(st, "st_nlink", 1) > 1:
                    hl.append(fp)
                if getattr(st, "st_file_attributes", 0) & REPARSE:
                    rp.append(fp)
        return hl, rp, blocked

    def gated_argv(self, tag, argv_cmd, extra=None):
        hl, rp, blocked = self.gate_scan(self.W)
        if hl or blocked:
            return None, {"hardlinks": hl, "reparse": rp, "blocked": blocked}
        return [self.EXE, "--debug", self.base_policy(tag, argv_cmd, extra)], \
            {"hardlinks": hl, "reparse": rp, "blocked": blocked}

    def base_policy(self, tag, argv_cmd, extra=None):
        """Policy shape of the F-scripts (mxc_f2.py:17-20); deny-all network; lifecycle
        and telemetry blocks per pv20-mxc-protocol-codex.md:177/:221. The commandLine is
        built with subprocess.list2cmdline from an argv list (card: never nested shell
        quoting)."""
        pol = {"version": "1.0.0", "containment": "processcontainer",
               "lifecycle": {"destroyOnExit": True, "preservePolicy": False},
               "process": {"commandLine": subprocess.list2cmdline(list(argv_cmd)),
                           "timeout": 30000},
               "filesystem": {"readwritePaths": [self.W]},
               "network": {"egress": {"default": "deny"},
                           "ingress": {"default": "deny", "hostLoopback": "deny"}},
               "telemetry": {"enabled": False}}
        if extra:
            pol.update(extra)
        path = os.path.join(self.F, "n3_%s.json" % tag)
        if os.path.exists(path):
            raise SetupError("policy name reused: %s" % tag)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(pol, fh)
        return path

    # ------------------------------------------------------------------ launching
    def wait_pid(self, pid, timeout=60):
        h = k32.OpenProcess(PROCESS_SYNCHRONIZE | PROCESS_QUERY_LIMITED, False, pid)
        if not h:
            return "nohandle"
        try:
            deadline = time.monotonic() + timeout
            while True:
                r = k32.WaitForSingleObject(h, 50)
                if r == WAIT_OBJECT_0:
                    break
                if r == WAIT_TIMEOUT:
                    if time.monotonic() > deadline:
                        return "timeout"
                    continue
                return "waiterr"
            code = wintypes.DWORD(0)
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return "noexitcode"
            return int(code.value)
        finally:
            k32.CloseHandle(h)

    def launch(self, tag, argv_cmd, extra=None):
        """Blocking gated wxc-exec run: stdout+stderr captured to a fixture file."""
        built, gate = self.gated_argv("a_%s" % tag, argv_cmd, extra)
        if built is None:
            return "REFUSED", gate
        outp = os.path.join(self.F, "out_%s.txt" % tag)
        if os.path.exists(outp):
            raise SetupError("output tag reused: %s" % tag)
        with open(outp, "wb") as fh:
            pid = self.CH.start(built, cwd=self.F, stdout=fh, stderr=subprocess.STDOUT)
        self.nspawns += 1
        rc = self.wait_pid(pid)
        with open(outp, "r", encoding="utf-8", errors="replace") as fh:
            out = fh.read()
        return (rc, out), gate

    def run_argv(self, argv, timeout=30):
        """Direct argv host run (host curl only). subprocess.run's timeout
        kills only the script's own child (allowed by the review; the pinned F1/F3 fault
        — cmd-wrapped curl — never occurs: curl is always invoked by absolute path with
        argv lists)."""
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return "timeout", ""
        return r.returncode, (r.stdout or "") + (r.stderr or "")

    def host_curl(self, url):
        # N3-S5: --noproxy as separate argv items so an operator http_proxy can never
        # send a "loopback-only" request to an external proxy.
        return self.run_argv([self.CURL, "-s", "-m", "5", "--noproxy", "*",
                              "-w", "CODE:%{http_code}", url])

    def client_run(self, tag, case, argv_cmd, delay=0, use_extra=True):
        """One gated wxc-exec run of the container curl client, launcher held in a fresh
        KILL_ON_JOB_CLOSE job (mxc_f9.py:130-148). N3-S4: both job calls are checked
        (a failed KILL_ON_JOB_CLOSE setup is a recorded FAIL, never unnoticed) and the
        launcher's job membership is returned so the caller can assert it BEFORE trusting
        any in_core_job observation. N3-R2: the command is an explicit argv list, chosen
        by the caller."""
        built, gate = self.gated_argv("b_%s" % tag, argv_cmd,
                                      self.PROXY_EXTRA if use_extra else None)
        if built is None:
            self.breach("B-phase gate REFUSED (hardlink/unreadable in granted folder): %s"
                        % gate)
        job = k32.CreateJobObjectW(None, None)
        if not job:
            self.check(case, "FAIL", "CreateJobObjectW returned NULL (N3-S4)")
            return {"accepts": [], "lates": [], "rc": "nojob",
                    "launcher_in_job": None, "gate": gate}
        try:
            lim = ExtendedLimitInfo()
            lim.Basic.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                               ctypes.byref(lim),
                                               ctypes.sizeof(lim)):
                self.check(case, "FAIL",
                           "SetInformationJobObject KILL_ON_JOB_CLOSE setup failed "
                           "(N3-S4; checked return, as n1 does)")
            self.state.update(delay=delay, log=[])
            pid = self.CH.start(built, cwd=self.F, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
            self.nspawns += 1
            hh = k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE |
                                 PROCESS_QUERY_LIMITED, False, pid)
            if not hh:
                self.check(case, "FAIL", "OpenProcess(launcher) failed (N3-S4)")
            try:
                if not k32.AssignProcessToJobObject(job, hh):
                    self.check(case, "FAIL",
                               "AssignProcessToJobObject failed (N3-S4; checked return)")
            finally:
                k32.CloseHandle(hh)
            self.state.update(wxc=pid, job=job)
            rc = self.wait_pid(pid)
            time.sleep(delay / 1000 + 0.5)  # mxc_f9.py:145-146
            launcher_in_job = in_job(pid, job)
        finally:
            k32.CloseHandle(job)
        accepts = [x for _p, path, kind, x in self.state["log"]
                   if tag in path and kind == "accept"]
        lates = [x for _p, path, kind, x in self.state["log"]
                 if tag in path and kind == "late"]
        return {"accepts": accepts, "lates": lates, "rc": rc,
                "launcher_in_job": launcher_in_job, "gate": gate}

    # ------------------------------------------------------------------ controls
    def canary(self, name):
        """Container write into <root>\\outside while only work is granted. R3: PAIRED
        with a positive control in the SAME container run — an echo proof file inside the
        granted work folder that is verified host-side; if the container never started,
        the proof is missing and the canary FAILs instead of passing vacuously."""
        proof = os.path.join(self.W, "proof_canary_%s.txt" % name)
        target = os.path.join(self.O, "canary_%s.txt" % name)
        marker = "CANARYPROOF_%s" % name
        argv = ["cmd.exe", "/c", "echo", "%s>%s" % (marker, proof), "&",
                "echo", "X>%s" % target]
        res, gate = self.launch("canary_%s" % name, argv)
        if res == "REFUSED":
            self.breach("canary %s gate-REFUSED (hardlink in granted folder): %s"
                        % (name, gate))
        rc, out = res
        if os.path.exists(target):
            self.breach("canary %s wrote %s outside the granted work folder" % (name, target))
        proof_ok = os.path.isfile(proof) and marker in self.read(proof)
        self.check("host-controls", "PASS" if (isinstance(rc, int) and proof_ok) else "FAIL",
                   "canary %s: no write outside work; paired positive control %s "
                   "(proof-in-work=%s rc=%s)"
                   % (name, "ran" if proof_ok else "DID NOT RUN", proof_ok, rc))

    def read(self, path):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def paired_denial(self, case, tag, inner_argv, leak_hit):
        """A denial run whose SAME container command line also carries the positive
        control (type prot.txt prints PROTECTED_IN, and an echo proof file inside work is
        verified host-side). PASS requires: rc is an int (not 'timeout'), the positive
        control observably ran in this exact container run, and no leak. A leak is a
        containment breach (exit 2). (R3: no denial is recorded from a leak check alone.)
        """
        proof = os.path.join(self.W, "proof_%s.txt" % tag)
        marker = "POSITIVE_%s" % tag
        argv = ["cmd.exe", "/c", "type", self.PROT, "&", "echo", "%s>%s" % (marker, proof)]
        argv += ["&"] + list(inner_argv)
        res, gate = self.launch(tag, argv)
        if res == "REFUSED":
            self.breach("paired denial %s gate-REFUSED unexpectedly: %s" % (tag, gate))
        rc, out = res
        if leak_hit(out, self):
            self.breach("denial %s leaked the outside secret/content" % tag)
        control_ok = ("PROTECTED_IN" in out and isinstance(rc, int)
                     and os.path.isfile(proof) and marker in self.read(proof))
        if not control_ok:
            self.check(case, "FAIL",
                       "paired positive control in the same container run did not "
                       "execute (PROTECTED_IN/proof/rc=%s) -> denial %s is unproven (R3)"
                       % (rc, tag))
            return
        self.check(case, "PASS",
                   "denial %s: container run provably executed (paired PROTECTED_IN + "
                   "proof file + int rc=%s) and nothing leaked; gate=%s"
                   % (tag, rc, {kk: len(vv) for kk, vv in gate.items()}))

    # ------------------------------------------------------------------ phases
    def phase_a(self):
        print(redact("== Phase A: strict storage with the hardlink gate =="), flush=True)
        os.makedirs(self.W)
        os.makedirs(self.O)
        self.canary("preA")
        with open(self.SEC, "w", encoding="utf-8") as fh:
            fh.write("SECRET_OUT")
        before = self.acl(self.SEC)
        with open(self.PROT, "w", encoding="utf-8") as fh:
            fh.write("PROTECTED_IN")
        self.setup_tool(["cmd.exe", "/c", "mklink", "/J", self.JX, self.O])
        if not os.path.exists(self.JX):
            raise SetupError("fixture junction staging failed")

        self.check("host-controls", "PASS" if os.path.isfile(
            os.path.join(self.JX, "secret.txt")) else "FAIL",
            "A1 host control: junction alias resolves to the outside secret (host side)")

        # R3: one asserted positive control with the SAME command form BEFORE the denials.
        res, _gate = self.launch("a_pos", ["cmd.exe", "/c", "type", self.PROT])
        if res == "REFUSED":
            self.breach("A1p anchor gate-REFUSED unexpectedly: %s" % _gate)
        rc, out = res
        anchor_ok = rc == 0 and "PROTECTED_IN" in out
        self.check("host-controls", "PASS" if anchor_ok else "FAIL",
                   "A1p same-form asserted positive control before any denial: container "
                   "type prot.txt printed PROTECTED_IN (rc=%s; feasibility:55 observed "
                   "readable)" % rc)
        self.check("host-controls", "INCONCLUSIVE",
                   "A12 F2f info (no protocol assertion): inherited-DACL file inside work "
                   "observed %s from the container (feasibility:55 says readable; readable "
                   "means the container shares the host user SID, restricted only by the "
                   "MXC process security environment)"
                   % ("readable" if "PROTECTED_IN" in out else "denied"))

        jx_secret = os.path.join(self.JX, "secret.txt")
        self.paired_denial("host-controls", "a_read_jx", ["type", jx_secret],
                           lambda out, s: "SECRET_OUT" in out)  # denial PINNED :52
        jx_write = os.path.join(self.JX, "w.txt")
        self.paired_denial("host-controls", "a_write_jx", ["echo", "WROTE>%s" % jx_write],
                           lambda out, s: os.path.exists(os.path.join(self.O, "w.txt")))
        # denial PINNED :52 (write through the junction)

        self.setup_tool(["cmd.exe", "/c", "mklink", "/H",
                           os.path.join(self.W, "hl.txt"), self.SEC])
        host_hl = (os.path.exists(os.path.join(self.W, "hl.txt"))
                   and self.read(self.SEC) == "SECRET_OUT")
        self.check("host-controls", "PASS" if host_hl else "FAIL",
                   "A4 host control: hardlink alias exists and the outside secret is "
                   "intact before the gate runs")

        hl, rp, blocked = self.gate_scan(self.W)
        self.check("host-controls", "PASS" if any(
            os.path.basename(x) == "hl.txt" for x in hl) else "FAIL",
            "A5 hardlink gate detects the planted link (link count > 1) before any grant "
            "use; listed=%d blocked-unreadable=%d (N3-S1 fail-closed)" % (len(rp), len(blocked)))
        n0 = self.nspawns
        res, gate = self.launch("a_gate_run", ["type", os.path.join(self.W, "hl.txt")])
        self.check("host-controls", "PASS" if (res == "REFUSED" and self.nspawns == n0) else "FAIL",
                   "A6 gated launcher REFUSED to spawn while a link-count>1 file was "
                   "granted (pinned F2c/F2d leak never rerun; feasibility:54): gate=%s"
                   % (gate if res == "REFUSED" else "SPAWNED!"))
        os.remove(os.path.join(self.W, "hl.txt"))  # remove this script's OWN planted link

        # R3 anchor again AFTER the gate episode: the gate is clean-sighted and a plain
        # container run works (cmd under the default policy runs, feasibility:14).
        res, gate = self.launch("a_clean_ok", ["cmd.exe", "/c", "echo", "GATE_OPEN"])
        if res == "REFUSED":
            self.check("host-controls", "FAIL",
                       "A7 gate clean-sighted control REFUSED on a clean folder: %s" % gate)
        rc, out = res
        self.check("host-controls", "PASS" if (rc == 0 and "GATE_OPEN" in out) else "FAIL",
                   "A7 positive control: clean rescan passed and a plain cmd run launched "
                   "and echoed (rc=%s)" % rc)

        self.paired_denial("host-controls", "a_direct_out", ["type", self.SEC],
                           lambda out, s: "SECRET_OUT" in out)  # denial PINNED :54
        self.paired_denial(
            "host-controls", "a_mklink",
            ["mklink", "/H", os.path.join(self.W, "hl2.txt"), self.SEC],
            lambda out, s: os.path.exists(os.path.join(self.W, "hl2.txt")))
        # A9 is INFERRED (container-side hardlink refusal; feasibility:57 host-only
        # creators + :54 direct denial)
        self.paired_denial("host-controls", "a_ancestors",
                           ["dir", self.F, "&", "dir", self.O],
                           lambda out, s: "secret.txt" in out.lower())  # denial PINNED :52

        drift = self.acl(self.SEC) != before
        self.check("host-controls", "FAIL" if drift else "PASS",
                   "A11 outside file unchanged after all storage runs (mode, size, mtime, "
                   "content; the DACL itself is not read)%s" % (" DRIFT" if drift else ""))

        try:
            os.rmdir(self.JX)  # junction first, before any tree deletion (feasibility:51)
        except OSError:
            pass
        self.check("host-controls", "PASS" if not os.path.exists(self.JX) else "FAIL",
                   "A13 junction removed with rmdir before phase B/teardown")

    def acl(self, path):
        st = os.stat(path)
        return (st.st_mode, st.st_size, st.st_mtime_ns, self.read(path))

    def phase_b(self):
        print(redact("== Phase B: origin attestor + network boundary (F9/F3 rerun) =="),
              flush=True)
        self.canary("preB")
        self.px = http.server.ThreadingHTTPServer(("127.0.0.1", 0), AttestorHandler)
        self.px.state = self.state
        threading.Thread(target=self.px.serve_forever, daemon=True).start()
        self.pport = self.px.server_address[1]
        self.fx = http.server.ThreadingHTTPServer(("127.0.0.1", 0), AttestorHandler)
        self.fx.state = self.state
        threading.Thread(target=self.fx.serve_forever, daemon=True).start()
        self.fport = self.fx.server_address[1]
        # Identity-less loopback proxy route (mxc_f9.py:114-116; pv20-mxc-protocol-codex
        # .md:234 unpackaged-host-proxy route; allowedProxyPeer left out — UNKNOWN).
        self.PROXY_EXTRA = {"processContainer": {"capabilities": ["internetClient"]},
                            "network": {"egress": {"default": "deny"},
                                        "ingress": {"default": "allow",
                                                    "hostLoopback": "allow"}},
                            "runtimeConfig": {"networkProxy": "http://127.0.0.1:%d"
                                              % self.pport}}

        rc0, out0 = self.host_curl("http://127.0.0.1:%d/hostctl" % self.pport)
        hits0 = self.hits(self.pport, "hostctl")
        self.check("host-controls",
                   "PASS" if (rc0 == 0 and "CODE:200" in out0 and len(hits0) >= 1) else "FAIL",
                   "B0 positive control: host reaches the attestor listener (form "
                   "mxc_diag3.py:24; 1 hit + CODE:200; hits=%d rc=%s)" % (len(hits0), rc0))
        rc0f, out0f = self.host_curl("http://127.0.0.1:%d/hostforbid" % self.fport)
        hits0f = self.hits(self.fport, "hostforbid")
        self.check("host-controls",
                   "PASS" if (rc0f == 0 and "CODE:200" in out0f and len(hits0f) >= 1) else "FAIL",
                   "B0f forbidden-listener host control (N3-S6): the host reaches the "
                   "forbidden listener and it logs the hit (hits=%d rc=%s)"
                   % (len(hits0f), rc0f))

        a = self.client_run("caseA", "broker-reach",
                            [self.CURL, "-s", "-m", "10",
                             "http://origin-probe.invalid/caseA"])
        acc = a["accepts"][0] if a["accepts"] else {}
        ok = (a["rc"] == 0 and a["launcher_in_job"] is True
             and acc.get("verdict") == "ACCEPT"
             and "curl" in str(acc.get("exe", "")).lower()
             and acc.get("ancestry_has_wxc") is True
             and acc.get("in_core_job") is True
             and acc.get("ctime") is not None
             and len(self.hits(self.pport, "caseA")) >= 1)
        self.check("broker-reach", "PASS" if ok else "FAIL",
                   "B1 F9A: live container client accepted only on (pid,creation-time) + "
                   "curl exe + wxc-exec ancestry + Core-job membership, with the launcher "
                   "itself asserted in the job BEFORE the record was trusted (N3-S4); "
                   "accept=%s rc=%s launcher_in_job=%s (feasibility:63)"
                   % (acc, a["rc"], a["launcher_in_job"]))

        # N3-R2: deny-all baseline pointed AT THE LISTENER (F3c form, mxc_diag3.py:32),
        # explicit command, --noproxy, and curl exit 7 (a .invalid host would exit 6 and
        # prove nothing).
        d = self.client_run("denybase", "deny-all-both-directions",
                            [self.CURL, "-s", "-m", "6", "--noproxy", "*",
                             "http://127.0.0.1:%d/denybase" % self.pport],
                            use_extra=False)
        hits = self.hits(self.pport, "denybase")
        if hits:
            self.breach("deny-all container reached the listener (network boundary; "
                        "PINNED feasibility:11, :48)")
        self.check("deny-all-both-directions",
                   "PASS" if (isinstance(d["rc"], int) and d["rc"] == 7) else "FAIL",
                   "B2 deny-all baseline: container curl DIRECTLY at the listener port "
                   "under deny-all egress+hostLoopback -> 0 hits and curl rc 7 (PINNED "
                   "feasibility:11, :48); paired with B1 (same script run, same listener, "
                   "container curl does reach it when allowed) and B0 (this listener "
                   "provably logs hits); rc=%s hits=%d" % (d["rc"], len(hits)))

        # N3-S6: the WFP boundary beyond the allowed proxy endpoint holds on this run:
        # under the proxy policy the container cannot reach the forbidden listener.
        fb = self.client_run("forbidx", "deny-all-both-directions",
                             [self.CURL, "-s", "-m", "8", "--noproxy", "*",
                              "http://127.0.0.1:%d/forbidx" % self.fport])
        fhits = self.hits(self.fport, "forbidx")
        self.check("deny-all-both-directions",
                   "PASS" if (isinstance(fb["rc"], int) and fb["rc"] == 7
                              and len(fhits) == 0) else "FAIL",
                   "B5 forbidden-listener control under the proxy policy: container curl "
                   "directly at the forbidden listener is blocked (rc 7, 0 hits; form "
                   "PINNED feasibility:48); paired with B0f (host control) and B1 "
                   "(allowed proxy route) in this same run; rc=%s hits=%d"
                   % (fb["rc"], len(fhits)))

        # B3: host-side forwarder must be rejected (F9B rerun).
        job = k32.CreateJobObjectW(None, None)
        if not job:
            self.check("wrong-peer-squatting-replacement", "FAIL",
                       "B3: CreateJobObjectW returned NULL (N3-S4)")
        try:
            self.state.update(delay=0, wxc=-1, job=job, log=[])  # mxc_f9.py:166 form
            rcb, outb = self.host_curl("http://127.0.0.1:%d/caseB" % self.pport)
            recs = [x for _p, path, kind, x in self.state["log"]
                    if "caseB" in path and kind == "accept"]
            b = recs[0] if recs else None
            ok = (rcb == 0 and b is not None
                  and str(b.get("verdict", "")).startswith("REJECT")
                  and b.get("ancestry_has_wxc") is False and not b.get("in_core_job"))
            self.check("wrong-peer-squatting-replacement", "PASS" if ok else "FAIL",
                       "B3 F9B: host-side forwarder (host curl, direct argv, --noproxy; "
                       "mxc_f9.py:167) REJECTED at accept — no wxc-exec ancestry, not in "
                       "the Core job; attest=%s hostrc=%s out=%r (feasibility:64)"
                       % (b, rcb, outb[-40:]))
        finally:
            k32.CloseHandle(job)

        # B4: delayed re-resolution after client exit — fail-closed, never another
        # process; forced PID reuse is UNKNOWN and NOT attempted (feasibility:65).
        for delay_ms in (50, 300, 1500):
            tag = "caseC%d" % delay_ms
            c = self.client_run(tag, "pid-exit-reuse-races",
                                [self.CURL, "-s", "-m", "10",
                                 "http://origin-probe.invalid/%s" % tag],
                                delay=delay_ms)
            acc = c["accepts"][0] if c["accepts"] else None
            late = c["lates"][0] if c["lates"] else None
            if not acc:
                self.check("pid-exit-reuse-races", "FAIL",
                           "B4c%d: no accept-time record at all (client never reached the "
                           "listener)" % delay_ms)
            if late is None:
                # N3-S3: a timing miss is NOT a pass.
                self.check("pid-exit-reuse-races", "INCONCLUSIVE",
                           "B4c%d: no late re-resolution record was produced (the delayed "
                           "re-attestation never ran); measurement did not happen — "
                           "stopping per review N3-S3" % delay_ms)
                raise StopRun("B4c%d: missing late record" % delay_ms)
            same = (late.get("pid") == acc.get("pid")
                    and late.get("ctime") == acc.get("ctime")
                    and late.get("ctime") is not None
                    and late.get("verdict") == "ACCEPT")
            fail_closed = str(late.get("verdict", "")).startswith("REJECT") or \
                late.get("verdict") == "UNRESOLVED"
            self.check("pid-exit-reuse-races",
                       "PASS" if (same or fail_closed) else "FAIL",
                       "B4c%d: request attested at accept; the late record is fail-closed "
                       "REJECT/UNRESOLVED or the SAME client by (pid,creation-time) — "
                       "never another process (corrected criterion per feasibility:65; "
                       "forced PID reuse stays unproven and is NOT forced here); "
                       "accept=%s late=%s" % (delay_ms, acc, late))

    def hits(self, port, needle):
        return [x for p, path, _kind, x in self.state["log"]
                if p == port and needle in path]

    # ------------------------------------------------------------------ driver
    def run_all(self):
        self.phase_a()
        self.phase_b()
        self.canary("post")
        self.px.shutdown()
        self.px.server_close()
        self.fx.shutdown()
        self.fx.server_close()
        for case, why in MISSING_STUBS:
            self.check(case, "INCONCLUSIVE", why)
        missing = set(N3_CASES) - self.used
        if missing:
            raise AssertionError("cases never reported: %s" % sorted(missing))


def main(argv):
    keep = "--keep" in argv
    rest = [a for a in argv if a != "--keep"]
    if len(rest) != 1:
        print(redact("usage: python -m tools.pv20_mxc.native.n3_check <fixture-parent> "
                     "[--keep]"))
        return EXIT_SETUP
    rec = Recorder("N3")
    try:
        n3 = N3Check(os.path.abspath(rest[0]), rec)
    except SetupError as ex:
        print(redact("SETUP ERROR: %s" % ex))
        return EXIT_SETUP
    except (OSError, ValueError) as ex:
        # exception text can carry paths; only the type is printed
        print(redact("SETUP ERROR: %s" % type(ex).__name__))
        return EXIT_SETUP
    stopped = False
    try:
        n3.run_all()
    except StopRun:
        stopped = True
    except SetupError as ex:
        print(redact("SETUP ERROR during run: %s; root preserved" % ex))
        return EXIT_SETUP
    except AssertionError as ex:
        # Internal invariant broken (never a boundary claim): stop as a failure,
        # root preserved, no traceback (a traceback would print unredacted text).
        print(redact("STOP (internal invariant): %s; root preserved" % ex))
        return 1
    except Exception as ex:
        print(redact("UNEXPECTED ERROR: %s; root preserved" % type(ex).__name__))
        return EXIT_SETUP
    finally:
        try:
            n3.CH.kill_own()
        except OSError:
            pass
    code = rec.exit_code()
    passed = (not stopped) and code == 0
    if passed and not keep:
        try:
            remove_fixture(n3.F)
            print(redact("SUMMARY all recorded cases held (every INCONCLUSIVE row is a "
                         "declared MISSING stub or the A12 info row, never a skipped "
                         "measurement); fixture removed (MXC AppContainer profile "
                         "registrations are NOT deleted — residue PINNED "
                         "PV20-mxc-feasibility.md:17)"))
        except (OSError, ValueError) as ex:
            print(redact("fixture deletion incomplete: %s; root retained at %s"
                         % (type(ex).__name__, n3.F)))
    else:
        print(redact("root preserved at %s (journal %s); exit %s"
                     % (n3.F, n3.RJ, code)))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
