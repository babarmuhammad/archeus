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
