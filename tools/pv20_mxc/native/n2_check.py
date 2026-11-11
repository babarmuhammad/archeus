"""N2 native fixture-only check: the PRODUCTION MXC launch stack, driven once for real.

Not run by its author. It runs only after the owner has read the review sheet
(.collab/N2-review-sheet-2026-11-01.md) and authorised the run.

Usage:  python -m tools.pv20_mxc.native.n2_check <fixture-parent>
  Exactly one argument: a directory at or below D:\\pv20-fixtures (letters, digits, dot,
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

Exit codes: 0 all cases PASS / 1 first FAIL / 2 no FAIL but an INCONCLUSIVE is present /
3 setup error, budget overrun or a surviving launcher.
"""
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
from collections import namedtuple
from types import SimpleNamespace

from tools.pv20_mxc.native import common
from tools.pv20_mxc.native.common import Recorder, StopRun, redact, remove_fixture, safe_root
from tools.pv20_mxc.protocol import STAGES

STAGE = 'N2'
FIXTURE_BASE = 'D:\\pv20-fixtures'
SDK_TAIL = ('sdk', 'node_modules', '@microsoft', 'mxc-sdk')
SAFE_PARENT = re.compile(r'\A[A-Za-z]:\\[A-Za-z0-9_.\\-]+\Z')
SYSTEMROOT = re.compile(r'(?i)\A[A-Za-z]:\\windows\Z')
JOURNAL = 'n2_journal.jsonl'
BUDGET_S = 1100.0            # protocol.STAGES['N2'].budget is 1200
QUIESCE_S = 5.0
CHAIN_MAX = 6000             # well under the 8191 character cmd.exe limit
EVIDENCE_MAX = 65536
STILL_ACTIVE = 259
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

def parent_ok(parent):
    """True only for a canonical drive path of safe characters at or below FIXTURE_BASE."""
    if not isinstance(parent, str) or not SAFE_PARENT.match(parent):
        return False
    parts = parent.split('\\')
    if any(p in ('', '.', '..') or p.endswith('.') for p in parts[1:]):
        return False
    low, base = ntpath.normcase(parent), ntpath.normcase(FIXTURE_BASE)
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
        self.m = None

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
             boundary=None, env=None, timeout_ms=60000, eid=None):
        self.budget.check()
        eid = eid or self.eid(tag)
        launch = self.m.local.MxcLaunch(
            api=self.api, boundary=boundary or self.boundary, ledger=ledger or self.ledger,
            schema_validator=lambda raw: True, execution_id=eid, sdk_root=self.lay['sdk'],
            pins=self.pins, outcome=lambda process: process.launcher_exit, workspace=rw[-1],
            writable=tuple(rw[:-1]), readonly=tuple(ro), cwd=rw[-1],
            command_line=command_line(argv), env=dict(self.env if env is None else env),
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
        """Close every Job (the kill), then check no launcher this script made is alive."""
        for ref in self.jobs:
            ref.close()
        if self.m is not None:
            self.m.mxc.NATIVE_RUN_ENABLED = False
        left = 0
        for pid, ctime in list(getattr(getattr(self, 'api', None), 'created', None) or ()):
            if not self.wait_dead(pid, ctime, 5.0):
                left += 1
                if live_ctime(pid) == ctime:      # ours, same creation time: the one kill allowed
                    common._terminate_process(pid)
        return left


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


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 1 or not parent_ok(argv[0]):
        print('usage: python -m tools.pv20_mxc.native.n2_check <fixture-parent at or below %s; letters, '
              'digits, dot, underscore, hyphen>' % FIXTURE_BASE, flush=True)
        return 3
    parent = argv[0]
    if not _on_windows() or not os.path.isdir(parent):
        print('SETUP ERROR: Windows only and the parent must exist', flush=True)
        return 3
    src = os.path.join(parent, *SDK_TAIL)
    root_env = os.environ.get('SystemRoot', '')
    if not _system_ok(root_env):
        print('SETUP ERROR: SystemRoot is not a plain drive\\Windows folder with cmd.exe', flush=True)
        return 3
    if not os.path.isfile(os.path.join(src, 'package.json')):
        print(redact('SETUP ERROR: staged SDK missing under the parent (operator stages it)'), flush=True)
        return 3
    rec, root, h, code = _Rec(STAGE), None, None, 3
    try:
        root = safe_root(parent)
        rec.journal = os.path.join(root, JOURNAL)
        h = Harness(root, src, root_env, Budget(BUDGET_S))
        run(h, rec)
        code = rec.exit_code()
    except StopRun:
        code = rec.exit_code() or 1
        print(redact('STOP at first FAIL; root preserved at %s' % root), flush=True)
    except SetupError as ex:
        print(redact('SETUP ERROR: %s; root preserved at %s' % (ex, root)), flush=True)
    except KeyboardInterrupt:
        print(redact('INTERRUPTED; Jobs closed, root preserved at %s' % root), flush=True)
    except Exception as ex:
        print(redact('UNEXPECTED ERROR: %s %s; root preserved at %s'
                     % (type(ex).__name__, _snip(str(ex)), root)), flush=True)
    left = h.wind_down() if h is not None else 0
    if left:
        print(redact('%d launcher(s) outlived the Job close; root preserved' % left), flush=True)
        code = 3
    if root is None or code == 3:
        return code
    try:
        return finish(code, root, remove_fixture)
    except ValueError as ex:
        print(redact('SETUP ERROR: fixture not removed: %s' % _snip(str(ex))), flush=True)
        return 3


if __name__ == '__main__':
    sys.exit(main())
