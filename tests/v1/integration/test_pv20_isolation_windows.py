"""PV-20 S1 — the real OS boundary (Windows only): the C6 acceptance properties.

These run against the live Win32 mechanism the go/no-go spike validated (pure ctypes,
no admin). They establish what a synthetic fake cannot — the §3.7 / R6-A **sole-holder**
and **kill-on-close** properties, the AppContainer identity's real SID, and §4.9's
zero network capability.

C6 keeps its full strength here (the S1 gate forbids weakening it to inspecting only
Core's own handle): Core is the *sole* holder of an *unnamed*, *non-inheritable* Job;
a child cannot acquire or retain a Job handle; and closing the Job ends the *full*
descendant tree. The cross-process handle mechanism is the spike's `NtQueryObject` /
`NtQuerySystemInformation` path exposed as `job_handles_of`, never `GetFileType`.

Nothing here changes an ACL anywhere: S1 applies no ACE (grant application is outside
it), and the isolated processes run a `System32` executable, which is AppContainer-
readable without one. Every identity is named from a freshly minted execution id, so a
run can never reuse a name a previous run (or a leftover ACE) still carries, and every
identity and Job is released on teardown — and a release that fails fails the test.

**Opt-in only.** These create and delete real AppContainer profiles, create Jobs and
start real processes, so an ordinary run (CI included) skips the whole module before
importing anything that could reach the OS. Run them deliberately, with
`ARCHEUS_REAL_BOUNDARY=1`, and only when that run has been authorized.
"""

import os
import subprocess
import sys
import time

import pytest

if not sys.platform.startswith('win'):
    pytest.skip('the real isolation boundary is Windows-only', allow_module_level=True)
if os.environ.get('ARCHEUS_REAL_BOUNDARY') != '1':
    pytest.skip('real OS boundary tests run only with ARCHEUS_REAL_BOUNDARY=1',
                allow_module_level=True)

from archeus.core.domain import ids             # noqa: E402
from archeus.infra.paths import archeus_home    # noqa: E402
from archeus.node import isolation as iso       # noqa: E402
from claude_sessions import proc                # noqa: E402

SYSTEM_ROOT = os.environ.get('SystemRoot', r'C:\Windows')
CMD = os.path.join(SYSTEM_ROOT, 'System32', 'cmd.exe')
PYTEST_SIDS = set(iso.NETWORK_CAPABILITY_SIDS)


def _minimal_env(**extra):
    """The whole environment an isolated test process gets, built here: never the
    test runner's own, which carries whatever secrets the shell holds."""
    return {'SystemRoot': SYSTEM_ROOT, 'ComSpec': CMD,
            'PATH': os.path.join(SYSTEM_ROOT, 'System32'), **extra}


@pytest.fixture
def owned_home(tmp_path, monkeypatch):
    """The test's own ARCHEUS_HOME, set here rather than trusted to a conftest, and
    checked through the resolver Core itself uses: if it does not resolve inside this
    test's temporary directory, the test fails before any OS object exists."""
    monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path / 'archeus-home'))
    home, root = os.path.realpath(archeus_home()), os.path.realpath(str(tmp_path))
    if os.path.commonpath([home, root]) != root:
        pytest.fail('ARCHEUS_HOME %s is not under this test\'s temporary directory' % home)
    return home


@pytest.fixture
def boundary(owned_home):
    b = iso.WindowsBoundary()
    created = {'profiles': [], 'jobs': []}
    b._pv20_created = created
    yield b
    for h in created['jobs']:
        b.close_job(h)
    left = []
    for eid in created['profiles']:
        try:
            b.delete_profile(eid)
        except iso.IsolationUnavailable as err:
            left.append((iso.profile_name(eid), str(err)))
            continue
        if b.profile_exists(eid):
            left.append((iso.profile_name(eid), 'package directory still present'))
    if left:
        pytest.fail('real AppContainer profiles were not cleaned up: %r' % (left,))


class Tracker:
    """Wraps the boundary to remember what to clean up after a test."""

    def __init__(self, b):
        self.b = b

    def profile(self, eid):
        ident = self.b.create_profile(eid)
        self.b._pv20_created['profiles'].append(eid)
        return ident


def _isolated_stream_run(b, tracker_created, args, env):
    """Launch *args* in a real AppContainer + Core-held Job with Core-opened stdio and
    exactly the environment *env*, wait for exit, and return (stdout_text, token)."""
    eid = ids.new_id('execution')
    name = iso.profile_name(eid)
    ident = b.create_profile(eid)
    tracker_created['profiles'].append(eid)
    job = b.create_job(eid)
    tracker_created['jobs'].append(job)
    root = os.path.join(archeus_home(), 'run', 'probe')
    os.makedirs(root, exist_ok=True)
    prompt = os.path.join(root, 'p')
    stream = os.path.join(root, 's')
    open(prompt, 'w').close()
    open(stream, 'w').close()
    handles = []
    try:
        handles.append(b.open_inherited(prompt, 'read'))
        handles.append(b.open_inherited(stream, 'append'))
        child = b.launch(args, cwd=root, env=env, profile=name,
                         job=job, stdin=handles[0], stdout=handles[1])
        tok = b.token(child.pid)
        child.wait(20)
        return open(stream, encoding='utf-8').read(), tok, ident
    finally:
        for h in handles:
            b.close_handle(h)


# ── item 1: a real per-execution AppContainer identity ────────────────────────

def test_identity_sid_and_package_dir(boundary):
    t = Tracker(boundary)
    eid = ids.new_id('execution')
    ident = t.profile(eid)
    assert ident['created'] is True and ident['existed'] is False
    assert ident['sid'].startswith('S-1-15-2-')          # a real AppContainer SID
    assert ident['package_dir'] == 'materialized'
    # the identity is what its name says it is (spike C1)
    assert boundary.derive_sid(eid) == ident['sid']


def test_two_executions_get_distinct_sids(boundary):
    t = Tracker(boundary)
    a = t.profile(ids.new_id('execution'))
    bb = t.profile(ids.new_id('execution'))
    assert a['sid'] != bb['sid']


# ── item 2 + C6: the Core-held unnamed, non-inheritable, kill-on-close Job ─────

def test_job_is_unnamed_and_non_inheritable(boundary):
    job = boundary.create_job(ids.new_id('execution'))
    boundary._pv20_created['jobs'].append(job)
    facts = boundary.job_facts(job)
    assert facts['type'] == 'Job'
    assert not facts['name']                             # unnamed: nothing to open by
    assert facts['inheritable'] is False                 # non-inheritable: sole holder


def test_core_is_the_sole_job_holder(boundary):
    # R6-A: Core becomes the sole holder — the count of unnamed non-inheritable Job
    # handles in Core's own process rises by exactly one when it creates a Job.
    def unnamed_jobs():
        return [h for h in boundary.job_handles_of(os.getpid())
                if h['type'] == 'Job' and not h['name'] and not h['inheritable']]
    before = len(unnamed_jobs())
    job = boundary.create_job(ids.new_id('execution'))
    boundary._pv20_created['jobs'].append(job)
    after = len(unnamed_jobs())
    assert after - before == 1


def _spawn_suspended_in_job(boundary, job, argv):
    """Create a (plain) process suspended, assign it to the Core-held Job, then resume.
    Its children are inherited into the same Job, so closing it must end the tree."""
    command = subprocess.list2cmdline([str(a) for a in argv])
    si = iso._SI()
    si.cb = __import__('ctypes').sizeof(iso._SI)
    pi = iso._PI()
    ok = iso._CreateProcessW(None, command, None, None, False, iso.CREATE_SUSPENDED,
                             None, None, __import__('ctypes').byref(si), __import__('ctypes').byref(pi))
    if not ok:
        raise OSError('CreateProcess failed (%s)' % iso.kernel32.GetLastError())
    try:
        boundary.assign_job(job, pi.hProcess)            # in the Job before it runs
    except Exception:
        # outside the Job, kill-on-close cannot reach it: end it here, then fail
        iso._TerminateProcess(pi.hProcess, 1)
        iso._CloseHandle(pi.hThread)
        iso._CloseHandle(pi.hProcess)
        raise
    iso._ResumeThread(pi.hThread)
    iso._CloseHandle(pi.hThread)
    return pi.dwProcessId, pi.hProcess


def test_kill_on_close_ends_the_full_descendant_tree(boundary, tmp_path):
    job = boundary.create_job(ids.new_id('execution'))
    boundary._pv20_created['jobs'].append(job)
    marker = str(tmp_path / 'pids.txt')
    # a parent that spawns a grandchild, records both pids, then idles
    parent_code = (
        'import subprocess,sys,os,time;'
        'g=subprocess.Popen([sys.executable,"-c","import time;[time.sleep(1) for _ in range(60)]"]);'
        'open(r%r,"w").write("%%d %%d" %% (os.getpid(), g.pid));g.poll();'
        '[time.sleep(1) for _ in range(60)]' % marker)
    cpid, hproc = _spawn_suspended_in_job(boundary, job, [sys.executable, '-c', parent_code])
    try:
        gpid = None
        deadline = time.time() + 15
        while time.time() < deadline:
            if os.path.exists(marker):
                parts = open(marker).read().split()
                if len(parts) == 2:
                    cpid, gpid = int(parts[0]), int(parts[1])
                    break
            time.sleep(0.2)
        assert gpid is not None, 'grandchild never reported'
        assert proc.process_create_time(cpid) is not None
        assert proc.process_create_time(gpid) is not None
        # a member of the Job holds no Job handle of its own (it cannot retain one)
        assert boundary.job_handles_of(cpid) == []
        boundary.close_job(job)                          # kill-on-close: the tree dies
        boundary._pv20_created['jobs'].remove(job)
        time.sleep(1.5)
        assert proc.process_create_time(cpid) is None, 'parent survived kill-on-close'
        assert proc.process_create_time(gpid) is None, 'grandchild survived kill-on-close'
    finally:
        iso._CloseHandle(hproc)


# ── item 9 + §5.1: the isolated process under a real token ────────────────────

def test_isolated_process_is_appcontainer_with_no_network_capability(boundary):
    text, tok, ident = _isolated_stream_run(
        boundary, boundary._pv20_created, [CMD, '/c', 'echo hi'], env=_minimal_env())
    assert tok['is_appcontainer'] == 1
    assert tok['ac_sid'] == ident['sid']
    assert not (set(tok['capability_sids']) & PYTEST_SIDS)   # no network capability
    assert tok['integrity'] == '0x1000'                       # AppContainer integrity


def test_explicit_environment_block_reaches_the_process(boundary):
    # §5.1 / spike: the environment is the block Core passed, never inherited by luck.
    text, tok, ident = _isolated_stream_run(
        boundary, boundary._pv20_created, [CMD, '/c', 'echo HELLO=%HELLO%'],
        env=_minimal_env(HELLO='world'))
    assert 'HELLO=world' in text


def test_pending_record_never_created_reclaims_idempotently(boundary):
    """Finding 1 on the real OS: a pending identity whose AppContainer profile was
    never created must reclaim idempotently. The real `_DeleteAppContainerProfile`
    answers `ERROR_NOT_FOUND` (0x80070490), which the boundary treats as already-gone,
    so teardown reports success, removes the record, and quarantines nothing -- a
    property the synthetic fake cannot distinguish from a real delete. No OS profile is
    created here; only a record file under the test's temporary ARCHEUS_HOME is written
    and removed."""
    eid = ids.new_id('execution')
    name = iso.profile_name(eid)
    # the real already-absent answer must not raise (the 0x80070490 branch)
    boundary.delete_profile(eid)
    a = iso.Isolation(boundary=boundary)
    a._save(iso.IsolationRecord(execution_id=eid, profile=name, state='pending'))
    assert a.record(eid).state == 'pending'
    out = a.teardown(eid, reason='recovered')
    assert out['profile'] == 'torn_down'            # already-absent handled, no false failure
    assert a.record(eid) is None                    # record removed after cleanup
    assert eid not in a.quarantined()               # nothing left standing
    assert eid not in a.reclaim(live_execution_ids=[])


# ── T-064 (P23): what an isolated process can reach on loopback ───────────────
# Authorised 2026-10-14 (owner, T-064): one AppContainer profile per run with zero
# capability SIDs, a kill-on-close Job, and only System32 curl.exe and cmd.exe inside
# it, against one pytest-owned 127.0.0.1 listener, one per-run named pipe and one
# closed port. Nothing here changes an ACL, a firewall rule or a loopback exemption.

import ctypes                                   # noqa: E402
import json                                     # noqa: E402
import secrets                                  # noqa: E402
import socket                                   # noqa: E402
import struct                                   # noqa: E402
import threading                                # noqa: E402
from ctypes import wintypes                     # noqa: E402

SYS32 = os.path.join(SYSTEM_ROOT, 'System32')
CURL = os.path.join(SYS32, 'curl.exe')


def _evidence(card, **facts):
    """Each observation, verbatim, to the file the run names (outside the basetemp,
    which is deleted); nothing when the run names none."""
    path = os.environ.get('ARCHEUS_NATIVE_EVIDENCE')
    if path:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(dict(card=card, **facts), default=str) + '\n')


class _Listener:
    """One TCP listener on 127.0.0.1 in this process. It answers any connection with a
    minimal HTTP response and keeps it open (T-068 reads the connection table while
    they exist), recording each peer."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.peers, self.held, self._stop = [], [], False
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        while not self._stop:
            try:
                c, addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.peers.append(addr)
            self.held.append(c)
            try:
                c.settimeout(2)
                c.recv(1024)
                c.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok')
            except OSError:
                pass

    def close(self):
        self._stop = True
        self._t.join(5)
        for c in self.held:
            c.close()
        self.sock.close()


def _closed_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Pipe:
    """One inbound named pipe with a per-run random name, created with the default
    security descriptor (no DACL is written), local clients only."""

    def __init__(self):
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.CreateNamedPipeW.restype = wintypes.HANDLE
        k.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                       wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                       wintypes.DWORD, ctypes.c_void_p]
        k.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        k.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        self.k = k
        self.name = r'\\.\pipe\archeus-probe-%s' % secrets.token_hex(8)
        # PIPE_ACCESS_INBOUND, PIPE_TYPE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS
        self.h = k.CreateNamedPipeW(self.name, 0x1, 0x8, 1, 0, 4096, 0, None)
        if self.h in (None, 0, wintypes.HANDLE(-1).value):
            raise OSError('CreateNamedPipeW failed (%s)' % ctypes.get_last_error())
        self.got = None
        self._t = threading.Thread(target=self._serve, daemon=True)
        self._t.start()

    def _serve(self):
        self.k.ConnectNamedPipe(self.h, None)      # ERROR_PIPE_CONNECTED is a connect too
        buf = ctypes.create_string_buffer(256)
        n = wintypes.DWORD(0)
        if self.k.ReadFile(self.h, buf, 256, ctypes.byref(n), None):
            self.got = buf.raw[:n.value]
        else:
            self.got = b''

    def close(self):
        if self._t.is_alive():                     # nobody else connected: unblock it
            with open(self.name, 'wb') as f:
                f.write(b'self')
        self._t.join(5)
        self.k.CloseHandle(self.h)


def _probe_runs(b, key, argvs, *, observe=None):
    """Launch each argv in turn inside one AppContainer profile (zero capability SIDs)
    and one Core-held kill-on-close Job, with Core-opened stdio, cwd System32 and the
    minimal environment. *observe(child)* runs while the process is alive."""
    created = b._pv20_created
    ident = b.create_profile(key)
    created['profiles'].append(key)
    job = b.create_job(key)
    created['jobs'].append(job)
    root = os.path.join(archeus_home(), 'run', 'probe')
    os.makedirs(root, exist_ok=True)
    prompt = os.path.join(root, 'p')
    open(prompt, 'w').close()
    out = []
    for i, argv in enumerate(argvs):
        stream = os.path.join(root, 's%d' % i)
        open(stream, 'w').close()
        hs = [b.open_inherited(prompt, 'read'), b.open_inherited(stream, 'append')]
        try:
            # LOCALAPPDATA: an AppContainer CreateProcessW answers ERROR_ENVVAR_NOT_FOUND
            # (203) for a block without it (T-064, build 26200); the system points it at
            # the container's own folder
            child = b.launch(argv, cwd=SYS32, env=_minimal_env(LOCALAPPDATA=os.environ['LOCALAPPDATA']),
                             profile=iso.profile_name(key),
                             job=job, stdin=hs[0], stdout=hs[1])
            seen = observe(child) if observe else None
            rc = child.wait(30)
        finally:
            for h in hs:
                b.close_handle(h)
        out.append({'argv': [os.path.basename(argv[0])] + list(argv[1:]), 'rc': rc,
                    'out': open(stream, encoding='utf-8', errors='replace').read().strip(),
                    'pid': child.pid, 'observed': seen})
    return ident, out


def _curl(port):
    return [CURL, '-q', '-sS', '-m', '5', '--noproxy', '*', 'http://127.0.0.1:%d/' % port]


def test_t064_loopback_and_pipe_reach_from_an_appcontainer(boundary):
    lst, pipe = _Listener(), _Pipe()
    closed = _closed_port()
    try:
        # control: this process reaches its own listener, so a refusal below is the
        # boundary's and not a dead listener
        with socket.create_connection(('127.0.0.1', lst.port), timeout=5) as c:
            c.sendall(b'GET / HTTP/1.0\r\n\r\n')
            control = c.recv(64)
        before = len(lst.peers)
        eid = ids.new_id('execution')
        ident, runs = _probe_runs(boundary, eid, [
            _curl(lst.port),
            _curl(closed),
            [CMD, '/d', '/c', 'echo ping>%s' % pipe.name],
        ], observe=lambda child: boundary.token(child.pid) if child.poll() is None else None)
        time.sleep(0.5)
        reached = lst.peers[before:]
    finally:
        lst.close()
        pipe.close()
    _evidence('T-064', profile=iso.profile_name(eid), sid=ident['sid'],
              listener_port=lst.port, closed_port=closed, pipe=pipe.name,
              control_reply=control, listener_peers_from_container=reached,
              pipe_received=pipe.got, runs=runs)
    assert control.startswith(b'HTTP/1.0 200')
    listener, closed_run, piped = runs
    # observed 2026-10-14 (build 26200): the listener is never reached (curl 28, a
    # timeout, not a refusal), the closed port is refused (curl 7), the pipe is denied
    assert reached == [] and listener['rc'] == 28
    assert closed_run['rc'] == 7
    assert piped['rc'] != 0 and pipe.got == b'self'        # only the test's own unblock
    for r in runs:
        tok = r['observed']
        assert tok is None or (tok['is_appcontainer'] == 1 and tok['ac_sid'] == ident['sid']
                               and not set(tok['capability_sids']) & PYTEST_SIDS)


# ── T-068 (K-O4): who is on the other end of a loopback connection ────────────
# Authorised 2026-10-14 (owner, T-068, after T-064): T-064's probe plus read-only
# observations from this process: the TCP table's owner PID for connections to the
# listener, that PID's token, and the DACLs of the ARCHEUS_HOME tree this test made.
# A token is opened only for this process and the processes this test launched.

_TCP_STATES = {1: 'CLOSED', 2: 'LISTEN', 3: 'SYN_SENT', 4: 'SYN_RCVD', 5: 'ESTABLISHED',
               6: 'FIN_WAIT1', 7: 'FIN_WAIT2', 8: 'CLOSE_WAIT', 9: 'CLOSING',
               10: 'LAST_ACK', 11: 'TIME_WAIT', 12: 'DELETE_TCB'}


def _tcp_rows(port):
    """GetExtendedTcpTable(AF_INET, TCP_TABLE_OWNER_PID_ALL): every IPv4 row with *port*
    at either end."""
    ip = ctypes.WinDLL('iphlpapi')
    size = wintypes.DWORD(0)
    ip.GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 5, 0)
    for _ in range(4):
        buf = (ctypes.c_byte * (size.value + 4096))()
        size = wintypes.DWORD(ctypes.sizeof(buf))
        if ip.GetExtendedTcpTable(buf, ctypes.byref(size), False, 2, 5, 0) == 0:
            break
    else:
        raise OSError('GetExtendedTcpTable kept growing')
    raw = bytes(buf)
    n = struct.unpack_from('<I', raw, 0)[0]
    out = []
    for i in range(n):
        st, la, lp, ra, rp, pid = struct.unpack_from('<IIIIII', raw, 4 + 24 * i)
        lp, rp = socket.ntohs(lp & 0xFFFF), socket.ntohs(rp & 0xFFFF)
        if port in (lp, rp):
            out.append({'state': _TCP_STATES.get(st, st),
                        'local': '%s:%d' % (socket.inet_ntoa(struct.pack('<I', la)), lp),
                        'remote': '%s:%d' % (socket.inet_ntoa(struct.pack('<I', ra)), rp),
                        'pid': pid})
    return out


def _token_of(b, pid):
    """OpenProcess(QUERY_LIMITED_INFORMATION) + GetTokenInformation on *pid*: user SID,
    AppContainer SID and flag, integrity level, and the PID's creation time."""
    h = iso._OpenProcess(iso.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return {'pid': pid, 'error': 'OpenProcess winerror=%s' % iso._err()}
    tok = wintypes.HANDLE()
    try:
        if not iso._OpenProcessToken(h, iso.TOKEN_QUERY, ctypes.byref(tok)):
            return {'pid': pid, 'error': 'OpenProcessToken winerror=%s' % iso._err()}
        try:
            return {'pid': pid, 'user': b._token_sid(tok, iso.TOKEN_USER),
                    'is_appcontainer': b._token_flag(tok, iso.TOKEN_IS_APPCONTAINER),
                    'ac_sid': b._token_sid(tok, iso.TOKEN_APPCONTAINER_SID),
                    'integrity': b._token_integrity(tok),
                    'created': proc.process_create_time(pid)}
        finally:
            iso._CloseHandle(tok)
    finally:
        iso._CloseHandle(h)


def _busy(n=300000):
    return [CMD, '/d', '/c', 'for /l %%i in (1,1,%d) do @rem' % n]


def test_t068_origin_of_user_appcontainer_and_verifier_principals(boundary):
    lst = _Listener()
    mine = {os.getpid()}
    seen = {}
    try:
        control = socket.create_connection(('127.0.0.1', lst.port), timeout=5)
        control.sendall(b'GET / HTTP/1.0\r\n\r\n')
        control.recv(64)
        user_rows = _tcp_rows(lst.port)
        user = _token_of(boundary, os.getpid())

        def during(tag):
            def look(child):
                mine.add(child.pid)
                time.sleep(1.0)                        # curl is mid-connect by now
                rows = _tcp_rows(lst.port)
                seen[tag] = {'rows': rows, 'token': _token_of(boundary, child.pid),
                             'row_tokens': {r['pid']: _token_of(boundary, r['pid'])
                                            for r in rows if r['pid'] in mine}}
                return seen[tag]
            return look

        eid = ids.new_id('execution')
        ac_ident, ac_runs = _probe_runs(boundary, eid, [_curl(lst.port)],
                                        observe=during('appcontainer'))
        vkey = iso.Principal('verify', ids.new_id('verification'), 0).key
        v_ident, v_runs = _probe_runs(boundary, vkey, [_curl(lst.port)],
                                      observe=during('verifier'))

        # early exit: the process ends before it is observed. Its handle is still held
        # (the IsolatedProcess), so the PID cannot name another process yet
        ekey = ids.new_id('execution')
        early = {}

        def after_exit(child):
            mine.add(child.pid)
            child.wait(10)
            early['exit_code'] = child.poll()
            early['by_pid'] = _token_of(boundary, child.pid)
            return early
        e_ident, e_runs = _probe_runs(boundary, ekey, [[CMD, '/d', '/c', 'exit 0']],
                                      observe=after_exit)
        control.close()
    finally:
        lst.close()

    home = archeus_home()
    dacls = {}
    for d, subdirs, _files in os.walk(home):
        dacls[os.path.relpath(d, home)] = boundary.dacl(d)
    _evidence('T-068', listener_port=lst.port, user_rows=user_rows, user_token=user,
              appcontainer={'profile': iso.profile_name(eid), 'sid': ac_ident['sid'],
                            'runs': ac_runs},
              verifier={'key': vkey, 'profile': iso.profile_name(vkey), 'sid': v_ident['sid'],
                        'derived_sid': boundary.derive_sid(vkey), 'runs': v_runs},
              early_exit={'profile': iso.profile_name(ekey), 'sid': e_ident['sid'],
                          'runs': e_runs},
              listener_peers=lst.peers, archeus_home=home, dacls=dacls)
    # the user process: this test, on both ends of its own connection
    assert {r['pid'] for r in user_rows if r['state'] == 'ESTABLISHED'} == {os.getpid()}
    assert user['is_appcontainer'] == 0 and user['ac_sid'] is None
    for tag, ident in (('appcontainer', ac_ident), ('verifier', v_ident)):
        tok = seen[tag]['token']
        assert tok['is_appcontainer'] == 1 and tok['ac_sid'] == ident['sid']
        assert tok['user'] == user['user'] and tok['integrity'] == '0x1000'
    assert v_ident['sid'] == boundary.derive_sid(vkey)
    assert early['exit_code'] == 0 and early['by_pid'].get('ac_sid') == e_ident['sid']


# ── T-063 part 1 (A6-5): the real confined verifier path, no grant ───────────
# Authorised 2026-10-14 (owner, T-063 part 1): one verifier attempt through the node's
# real run_confined_check, with the profile and Job the node creates, a System32
# command, and no ACL grant (S2-G stays T-004's).

def test_t063_the_real_confined_path_refuses_before_launch_without_grants(boundary):
    from archeus.node.local import LocalNode
    node = LocalNode()
    node.isolation = iso.Isolation(node, boundary=boundary)
    vid = ids.new_id('verification')
    key = iso.Principal('verify', vid, 0).key
    got = []
    result = node.run_confined_check(vid, 0, [CMD, '/d', '/c', 'echo confined'],
                                     toolchain=(SYS32,), timeout=10, record=got.append)
    rec = node.isolation.record(key)
    _evidence('T-063', key=key, profile=iso.profile_name(key), result=result, recorded=got,
              record=rec.as_dict() if rec else None,
              profile_exists_after=boundary.profile_exists(key))
    # observed 2026-10-14: condition 2 holds for no row - nothing grants the checkout,
    # scratch or toolchain to the attempt's SID - so nothing is launched, the verdict
    # is recorded as an isolation error, and the profile the node made is gone
    assert result['error'].startswith('isolation: condition_unmet:grants')
    assert result['exit_code'] is None and got == [result]
    assert rec is not None and rec.state == 'failed'
    assert boundary.profile_exists(key) is False
