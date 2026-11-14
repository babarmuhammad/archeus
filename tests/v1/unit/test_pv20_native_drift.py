# ruff: noqa: F811  (the imported fixtures are taken as arguments)
"""Drift guard: the N2 and N4 native scripts, run end to end against the production MXC classes.

The scripts' own unit tests stand in fakes for the harness, so they pinned the interfaces the
harness used to have and nothing caught the production classes moving on. Here the harness is
the scripts' own `Harness`, built the way their `prepare` builds it, and what it drives is
production: `MxcLaunch`, `mxc_native.Backend` and its transport, `mxc_ledger.Ledger` and
`reconcile`, `MxcBoundary`, `Isolation.run_confined`, `ConfinedChild`, `staging`, `BrokerLaunch`.
A call the scripts make with arguments production refuses fails these tests.

Nothing native runs. Windows is a scripted machine (`World`): its Win32 api and its Job
implement the signatures of the real ones (compared below), the workload is a table keyed on the
command line, time is virtual, and the only things replaced on the script side are the ones that
touch the OS (`live_ctime`, the junction, the host listeners) or only judge what a container left
behind (`judge`, covered by the scripts' own tests). Core's Git store functions are replaced by
fakes that refuse a call the real signature would refuse.
"""

import inspect
import json
import os
import re
import subprocess
import threading
import time
from collections import deque
from types import SimpleNamespace

import pytest

from archeus.node import isolation as iso
from archeus.node import local, mxc, mxc_ledger, mxc_native, win32_mxc
from tools.pv20_mxc.native import common, n2_check as n2, n4_check as n4
from tools.pv20_mxc.native.common import StopRun
from tools.pv20_mxc.protocol import STAGES

from .test_mxc_boundary import sdk  # noqa: F401  (a fixture)
from .test_pv20_isolation import os_tripwire  # noqa: F401  (autouse: no native primitive)

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='the scripts drive Windows path grammar')

REAL_API = win32_mxc.Win32Api
REAL_JOBS = getattr(iso, 'WindowsBoundary', None)
SYSTEMROOT = 'C:\\Windows'
EXE_NAMES = ('claude.exe', 'curl.exe')


# ── the scripted machine ─────────────────────────────────────────────────────

class Proc:
    def __init__(self, pid, policy):
        self.pid, self.ctime, self.policy = pid, pid * 100, policy
        self.cmd = policy['process']['commandLine'] if policy else ''
        self.job, self.started, self.killed = None, False, False
        self.exit_at, self.code, self.flood = None, 0, False
        self.out, self.err = [], []


class World:
    def __init__(self):
        self.now, self.serial = 0.0, 1000
        self.handles, self.policies, self.procs = {}, {}, {}
        self.up = None
        self.edited = None
        self.procs[os.getpid()] = Proc(os.getpid(), None)
        self.procs[os.getpid()].ctime = 777

    def clock(self):
        return self.now

    def pause(self, seconds):
        self.now += seconds

    def handle(self, kind, **info):
        self.serial += 1
        self.handles[self.serial] = (kind, info)
        return self.serial

    def proc_of(self, handle):
        return self.procs[self.handles[handle][1]['pid']]

    def exited(self, p):
        return p.killed or (p.exit_at is not None and self.now >= p.exit_at)

    def kill(self, p):
        if not self.exited(p):
            p.code = 1
        p.killed = True

    def live_ctime(self, pid):
        p = self.procs.get(pid)
        return p.ctime if p is not None and not self.exited(p) else None


class FakeApi:
    """The Win32 surface of the transport: the signatures of `win32_mxc.Win32Api`."""
    world = None

    def __init__(self, private_directory):
        self.w, self.pairs, self.count = FakeApi.world, {}, 0

    def protected_policy(self, data: bytes) -> tuple[str, object]:
        path = 'C:\\protected\\p%d.json' % (len(self.w.policies) + 1)
        self.w.policies[path] = json.loads(data)
        return path, self.w.handle('policy')

    def remove_policy(self, path, handle):
        self.close_handle(handle)

    def pipe(self, *, parent_reads: bool) -> tuple[object, object]:
        index, self.count = self.count % 3, self.count + 1
        parent = self.w.handle('pipe', index=index, proc=None)
        child = self.w.handle('child')
        self.pairs[child] = parent
        return parent, child

    def attribute_list(self, handles: tuple) -> object:
        return self.w.handle('attributes')

    def delete_attribute_list(self, attributes):
        self.close_handle(attributes)

    def create_process_w(self, *, application, command_line, flags, attributes,
                         inherit_handles, std_handles, cwd, env):
        w = self.w
        p = Proc(w.serial + 1, w.policies[command_line.rsplit(' ', 1)[-1].strip('"')])
        w.serial = p.pid
        w.procs[p.pid] = p
        for child in std_handles[1:]:
            w.handles[self.pairs[child]][1]['proc'] = p
        return w.handle('process', pid=p.pid), w.handle('thread', pid=p.pid), p.pid

    def creation_time(self, process) -> int:
        return self.w.proc_of(process).ctime

    def in_job(self, job, process) -> bool:
        return self.w.proc_of(process).job == job

    def resume_thread(self, thread) -> int:
        p = self.w.proc_of(thread)
        p.started, p.exit_at = True, self.w.now
        behave(self.w, p)
        return 1

    def terminate_process(self, process):
        self.w.kill(self.w.proc_of(process))

    def close_handle(self, handle):
        del self.w.handles[handle]

    def poll(self, process) -> int | None:
        w, p = self.w, self.w.proc_of(process)
        return p.code if w.exited(p) else None

    def read(self, handle, size: int) -> bytes | None:
        w = self.w
        _, info = w.handles[handle]
        p = info['proc']
        if p is None or not p.started:
            return None
        queue = p.out if info['index'] == 1 else p.err
        if info['index'] == 1 and p.flood and not w.exited(p):
            return b'N' * size
        if queue:
            return queue.pop(0)
        return b'' if w.exited(p) else None

    def write(self, handle, data: bytes) -> int:
        return len(data)


class FakeJobs:
    """The Job and process half of the boundary: the signatures of `WindowsBoundary`."""
    world = None

    def __init__(self, *, backend=None, native_run=False):
        self.w, self.closed = FakeJobs.world, []

    def create_job(self, execution_id):
        return self.w.handle('job')

    def job_facts(self, handle):
        return {'type': 'Job', 'name': '', 'inheritable': False}

    def job_active_processes(self, job):
        return sum(1 for p in self.w.procs.values() if p.job == job and not self.w.exited(p))

    def assign_job(self, job, process_handle):
        self.w.proc_of(process_handle).job = job

    def terminate_job(self, job):
        for p in [p for p in self.w.procs.values() if p.job == job]:
            self.w.kill(p)

    def close_job(self, job):
        self.terminate_job(job)
        self.closed.append(job)

    def close_handle(self, handle):
        pass

    def process_started(self, pid):
        return self.w.live_ctime(pid)

    def open_inherited(self, path, mode):
        return {'stdio': path, 'mode': mode}

    def broad_writer(self, path):
        return None


def sse_lines(sid, reply, tool=None):
    events = [{'type': 'system', 'session_id': sid}]
    if tool:
        events.append({'type': 'assistant', 'session_id': sid, 'message': {'content': [
            {'type': 'tool_use', 'id': tool, 'name': 'Edit', 'input': {}}]}})
    events.append({'type': 'result', 'session_id': sid, 'is_error': False, 'result': reply})
    return [(json.dumps(e) + '\n').encode() for e in events]


def behave(w, p):
    """What the workload does, keyed on its command line."""
    c = p.cmd
    if 'MXC-N^2' in c:
        p.out.append(b'MXC-N2\r\n')
    elif 'for /l' in c and '400000' in c:
        p.flood, p.exit_at = True, None
    elif 'for /l' in c:
        p.code, p.exit_at = 1, w.now + p.policy['process']['timeout'] / 1000
    elif 'FORGED-PASS' in c:
        p.out.append(re.search(r'FORGED-PASS-\w+', c).group(0).encode())
        p.code = 3
    elif 'claude.exe' in c:
        cli(w, p)
    elif 'curl.exe' in c:
        curl(w, p)


def cli(w, p):
    up = w.up
    if '--version' in p.cmd:
        p.out.append(b'2.1.0 (Claude Code)\r\n')
        return
    mode, sid = up.mode, 'sess-n4'

    def post(content):
        up.hits.append(n4.Hit('POST', '/v1/messages', True, json.dumps(
            {'messages': [{'role': 'user', 'content': content}]}).encode(), 0.0))
    if mode['kind'] == 'stall':
        post('hang')
        up.stalled.set()
        p.exit_at = None
    elif mode['kind'] == 'edit':
        post('edit')
        with open(mode['path'], encoding='utf-8') as fh:
            text = fh.read()
        with open(mode['path'], 'w', encoding='utf-8') as fh:
            fh.write(text.replace(mode['old'], mode['new']))
        post([{'type': 'tool_result', 'tool_use_id': mode['tool'], 'is_error': False}])
        w.edited = mode['reply']
        p.out.extend(sse_lines(sid, mode['reply'], mode['tool']))
    else:
        post(w.edited if '--resume' in p.cmd else 'text')
        p.out.extend(sse_lines(sid, mode['reply']))


def curl(w, p):
    port = int(re.search(r'http://127\.0\.0\.1:(\d+)', p.cmd).group(1))
    if 'runtimeConfig' in p.policy and port == w.up.port:
        w.up.hits.append(n4.Hit('GET', '/ctl', False, b'', 0.0))
        p.out.append(b'CODE:401')
    else:
        p.code = 7
        p.out.append(b'CODE:000')


class FakeUpstream:
    def __init__(self, token):
        self.token, self.mode, self.hits = token, {'kind': 'text', 'reply': 'OK'}, []
        self.port = 40001
        self.url = 'http://127.0.0.1:%d' % self.port
        self.stalled, self.release = threading.Event(), threading.Event()

    def start(self):
        pass

    def close(self):
        self.release.set()

    def count(self):
        return len(self.hits)

    def seen(self, since=0):
        return list(self.hits[since:])


class FakeForbidden:
    def __init__(self):
        self.port, self.hits = 40002, 0

    def start(self):
        pass

    def close(self):
        pass


def checked(real, impl):
    """A fake of a production function that refuses what the real signature would."""
    sig = inspect.signature(real)

    def call(*args, **kwargs):
        sig.bind(*args, **kwargs)
        return impl(*args, **kwargs)
    return call


def install_store(monkeypatch, w, h, tmp_path):
    """Core's Git store, replaced. `seed_workspace` writes the tree the script's own checker
    expects; a second seed or import of one execution is refused, as the real ones refuse it."""
    node, seeded, imported = local.LocalNode, set(), set()
    results = deque([['M notes.txt'], ['M notes.txt', 'A new_file.txt', 'A done.txt', 'D src/app.txt']])

    def seed_workspace(project_id, execution_id, seed_revision, branch, *, workdirs):
        if execution_id in seeded:
            raise ValueError('already seeded')
        seeded.add(execution_id)
        work = h.m.paths.ExecPaths(execution_id).work
        os.makedirs(work)
        for rel, mode, data in n4.seed_files(h.secret):
            target = os.path.join(work, *rel.split('/'))
            if mode == '160000':
                os.makedirs(target)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'wb') as fh:
                fh.write(data)
        git = os.path.join(work, '.git')
        for name in ('objects', 'refs'):
            os.makedirs(os.path.join(git, name))
        for name, data in (('HEAD', b'ref: refs/heads/x\n'), ('config', local.SEED_CONFIG),
                           ('shallow', b''), ('index', b'')):
            with open(os.path.join(git, name), 'wb') as fh:
                fh.write(data)
        return work

    def import_workspace(project_id, execution_id, seed_revision, *, workdirs):
        if execution_id in imported:
            raise ValueError('already imported')
        imported.add(execution_id)
        return {'revision': 'a' * 40, 'files_changed': results.popleft() if results else []}

    def store_read(project_id, args, *, workdirs):
        return 'c' * 40 + '\n' if args[0] == 'rev-parse' else ''

    for name, impl in (('store_open', lambda project_id, *, workdirs: str(tmp_path / 'store')),
                       ('store_git', lambda mode, args, *, workdirs, git_dir=None, stdin=None,
                        timeout=120, sink=None: ''),
                       ('store_read', store_read),
                       ('store_seed_ref', lambda project_id, execution_id, commit, *, workdirs: None),
                       ('seed_workspace', seed_workspace), ('import_workspace', import_workspace)):
        monkeypatch.setattr(node, name, staticmethod(checked(getattr(node, name), impl)))
    monkeypatch.setattr(local, '_export_tree', checked(
        local._export_tree, lambda project_id, revision, top, workdirs, deadline: None))


class Rec:
    def __init__(self):
        self.rows = []

    def record(self, case, status, detail=''):
        self.rows.append((case, status, detail))
        if status == 'FAIL':
            raise StopRun('%s: %s' % (case, detail))

    def by_case(self):
        out = {}
        for case, status, _ in self.rows:
            out.setdefault(case, set()).add(status)
        return out


@pytest.fixture
def machine(monkeypatch, tmp_path):
    w = World()
    FakeApi.world = FakeJobs.world = w
    monkeypatch.setattr(win32_mxc, 'Win32Api', FakeApi)
    monkeypatch.setattr(iso, 'WindowsBoundary', FakeJobs, raising=False)
    monkeypatch.setattr(iso, 'WINDOWS', True, raising=False)
    monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', False)
    for fn in (mxc_native.Transport.__init__, local.MxcLaunch.__init__):
        monkeypatch.setitem(fn.__kwdefaults__, 'clock', w.clock)
        monkeypatch.setitem(fn.__kwdefaults__, 'pause', w.pause)
    monkeypatch.setattr(time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(n2, 'live_ctime', w.live_ctime)
    monkeypatch.setattr(common, '_process_creation_time', lambda pid: w.procs[pid].ctime)
    monkeypatch.setattr(n2, 'judge', lambda items, look: None)
    monkeypatch.setattr(n2, '_junction', lambda h, link, target: __import__('_winapi').CreateJunction(
        target, link))
    monkeypatch.setattr(n2, 'import_isolated', lambda modules, home, **kw: {
        name: __import__(name, fromlist=['x']) for name in modules})
    saved = dict(os.environ)

    def no_process(*args, **kwargs):
        raise AssertionError('a process was started: %r' % (args[:1],))
    monkeypatch.setattr(subprocess, 'Popen', no_process)
    yield w
    os.environ.clear()
    os.environ.update(saved)


def n2_harness(tmp_path, sdk):
    root = tmp_path / 'n2root'
    root.mkdir()
    return n2.Harness(str(root), sdk[0], SYSTEMROOT, n2.Budget(1e9))


def n4_harness(tmp_path, sdk, monkeypatch, w):
    cli_dir = tmp_path / 'cli'
    cli_dir.mkdir()
    (cli_dir / 'claude.exe').write_bytes(b'cli')
    root = tmp_path / 'n4root'
    root.mkdir()
    monkeypatch.setattr(n4, 'Upstream', FakeUpstream)
    monkeypatch.setattr(n4, 'Forbidden', FakeForbidden)

    def touch(port, probe=b''):
        if port == w.up.port:
            w.up.hits.append(n4.Hit('GET', '/hostctl', False, b'', 0.0))
        else:
            h.fb.hits += 1
    monkeypatch.setattr(n4, 'host_touch', touch)
    monkeypatch.setattr(n4, 'streamed', lambda times, ended, gap=0.5: True)

    def naive_git(h, work):
        with open(os.path.join(h.lay['ctl'], 'naive', 'fired_fsmonitor.txt'), 'w') as fh:
            fh.write('X')
        return 'rc=0'
    monkeypatch.setattr(n4, 'naive_git', naive_git)
    h = n4.Harness(str(root), sdk[0], str(cli_dir), SYSTEMROOT, n2.Budget(1e9))
    original = n4.Harness.prepare

    def prepare():
        original(h)
        w.up = h.up
    h.prepare = prepare
    return h


# ── the fakes are the production signatures ──────────────────────────────────

def _shape(fn):
    return [(p.name, p.kind) for p in inspect.signature(fn).parameters.values()]


@pytest.mark.parametrize('name', [n for n in dir(mxc_native.Win32) if not n.startswith('_')])
def test_the_fake_win32_api_has_the_production_signature(name):
    assert _shape(getattr(FakeApi, name)) == _shape(getattr(REAL_API, name))


@pytest.mark.skipif(REAL_JOBS is None, reason='no Windows boundary on this host')
@pytest.mark.parametrize('name', ['create_job', 'job_facts', 'job_active_processes', 'assign_job',
                                  'terminate_job', 'close_job', 'close_handle', 'process_started',
                                  'open_inherited', 'broad_writer', '__init__'])
def test_the_fake_job_has_the_production_signature(name):
    assert _shape(getattr(FakeJobs, name)) == _shape(getattr(REAL_JOBS, name))


def test_the_signature_checked_store_fake_refuses_what_the_real_one_would():
    fake = checked(local.LocalNode.store_open, lambda project_id, *, workdirs: 'store')
    assert fake('prj', workdirs=()) == 'store'
    for bad in (lambda: fake('prj'), lambda: fake('prj', workdirs=(), extra=1), lambda: fake()):
        with pytest.raises(TypeError):
            bad()


def test_production_refuses_the_shapes_the_scripts_used_to_pass(tmp_path):
    with pytest.raises(ValueError):
        mxc_ledger.journal_name('n2-01-echo', 1)
    with pytest.raises(ValueError):
        mxc_ledger.journal_name('n2_01_echo', 0)
    assert mxc_ledger.journal_name('n2_01_echo', 1) == 'n2_01_echo-p1'
    sig = inspect.signature(local.MxcLaunch.__init__)
    assert 'writable' in sig.parameters and 'process_seq' in sig.parameters
    assert 'end_job' in sig.parameters      # optional: the boundary's terminate_job is the default


# ── N2 ───────────────────────────────────────────────────────────────────────

def test_n2_runs_every_row_against_the_production_launch_stack(machine, tmp_path, sdk):
    h, rec = n2_harness(tmp_path, sdk), Rec()
    try:
        n2.run(h, rec)
    finally:
        left = h.wind_down()
    assert left == 0
    seen = rec.by_case()
    assert set(seen) == set(STAGES['N2'].cases)
    assert all('PASS' in s for s in seen.values())
    assert 'FAIL' not in set().union(*seen.values())


def test_n2_launches_are_named_by_the_ledger_and_end_the_way_the_rows_expect(machine, tmp_path, sdk):
    h, rec = n2_harness(tmp_path, sdk), Rec()
    try:
        n2.run(h, rec)
        journals = h.ledger.journals()
    finally:
        h.wind_down()
    assert journals and all(re.fullmatch(r'[A-Za-z0-9_]+-p1', name) for name in journals)
    for eid, ops in h.ended.items():
        assert h.name(eid) in journals
        records, invalid = mxc_ledger.read_records(journals[h.name(eid)], h.name(eid))
        assert not invalid and [r['op'] for r in records] == ops


def test_n2_only_makes_launches_production_accepts(machine, tmp_path, sdk):
    h = n2_harness(tmp_path, sdk)
    try:
        h.prepare()
        rw, ro = n2.grants(h.lay, 'p')
        eid, launch = h.make('canary-pre', ['C:\\x.exe'], rw, ro)
        assert eid == 'n2_01_canary_pre' and launch.journal == h.name(eid)
        fs = launch.policy.raw['filesystem']
        assert fs['readwritePaths'] == [os.path.normpath(rw[-1]), os.path.normpath(rw[0])]
        assert fs['readonlyPaths'] == [os.path.normpath(p) for p in ro]
        assert launch.policy.raw['process']['cwd'] == os.path.normpath(rw[-1])
    finally:
        h.wind_down()


def test_n2_ends_a_launch_with_the_boundarys_own_terminate_job(machine, tmp_path, sdk):
    h = n2_harness(tmp_path, sdk)
    try:
        h.prepare()
        eid, launch = h.make('loop', n2.loop_argv(h), (h.lay['rev'],), (h.lay['runtime'],))
        job = h.job(eid)
        launch.start(job=job.handle)
        assert h.job_count(job) == 1
        assert launch._end_job.__func__ is FakeJobs.terminate_job
        assert launch.cancel(reason='revocation')['state'] == mxc_ledger.DEAD_UNVERIFIED
        assert h.job_count(job) == 0
        assert h.ops(eid)[0] == n2.QUARANTINED
    finally:
        h.wind_down()


# ── N4 ───────────────────────────────────────────────────────────────────────

def test_n4_runs_every_row_against_the_production_launch_stack(machine, monkeypatch, tmp_path, sdk):
    h, rec = n4_harness(tmp_path, sdk, monkeypatch, machine), Rec()
    install_store(monkeypatch, machine, h, tmp_path)
    try:
        n4.run(h, rec)
    finally:
        left = h.wind_down()
    assert left == 0
    seen = rec.by_case()
    assert set(seen) == set(n4.CASES)
    assert 'FAIL' not in set().union(*seen.values())
    assert {case for case, s in seen.items() if 'PASS' not in s} == {n4.LIVE_CASE}


def test_n4_boundary_is_available_to_the_verifier_path(machine, monkeypatch, tmp_path, sdk):
    h = n4_harness(tmp_path, sdk, monkeypatch, machine)
    try:
        h.prepare()
        assert h.mxcb.available() is True
        assert h.node.isolation.boundary is h.mxcb
    finally:
        h.wind_down()


def test_n4_verifier_poll_does_not_meet_a_timeout_while_the_launch_runs(machine, monkeypatch, tmp_path, sdk):
    h = n4_harness(tmp_path, sdk, monkeypatch, machine)
    install_store(monkeypatch, machine, h, tmp_path)
    try:
        h.prepare()
        rec = Rec()
        n4.step_verifiers(h, rec)
    finally:
        h.wind_down()
    assert [s for _, s, _ in rec.rows] == ['PASS']


def test_n4_resume_generations_are_journals_p1_and_p2(machine, monkeypatch, tmp_path, sdk):
    h = n4_harness(tmp_path, sdk, monkeypatch, machine)
    install_store(monkeypatch, machine, h, tmp_path)
    try:
        h.prepare()
        h.make_seed_commit()
        ex = h.seeded()
        env = n4.cli_env(h.sr, ex, h.lay['cli'], h.broker())
        run1 = h.go('first', n4.cli_argv(h.cli_exe, 'a'), n4.exec_grants(ex)[0], (h.lay['cli'],),
                    env=env, eid=ex.eid, seq=1)
        h.mxcb.create_profile(ex.eid)
        run2 = h.go('second', n4.cli_argv(h.cli_exe, 'b'), n4.exec_grants(ex)[0], (h.lay['cli'],),
                    env=env, eid=ex.eid, seq=2)
        assert (run1.ops, run2.ops) == (n4.CLEAN, n4.CLEAN)
        assert sorted(h.ledger.journals()) == [ex.eid + '-p1', ex.eid + '-p2']
    finally:
        h.wind_down()


def test_n4_limits_go_through_the_transport_seam_production_uses(machine, monkeypatch, tmp_path, sdk):
    h = n4_harness(tmp_path, sdk, monkeypatch, machine)
    try:
        h.prepare()
        work = tmp_path / 'limits'
        work.mkdir()
        flood = [h.cmd, '/d', '/c', 'for', '/l', '%i', 'in', '(1,1,400000)', 'do', '@echo', 'N']
        eid, launch = h.make('flood', flood, (str(work),), (h.lay['toolchain'],),
                             transport={'output_limit': 1 << 16})
        assert launch.backend.transport.output_limit == 1 << 16
        launch.start(job=h.job(eid).handle)
        with pytest.raises(mxc.MxcUnavailable, match='output bound'):
            launch.wait(60)
        assert h.ops(eid) == n4.QUARANTINED
    finally:
        h.wind_down()
