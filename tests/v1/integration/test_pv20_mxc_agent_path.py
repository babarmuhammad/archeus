"""T-457: the agent path and the verifier path over the closed MXC seam.

Both paths run through production code — `base.spawn` → `IsolationContext.launch` for
an agent, `LocalNode.run_confined_check` → `Isolation.run_confined` for a verifier —
down to the boundary seam. What stands in for the Windows MXC boundary is
`MxcBoundary` below: it does what such a boundary does, which is compile the policy of
the process it is asked to launch with Core's own compiler (`mxc.compile_policy`) and
spawn it through `mxc.spawn`, by way of the one production MXC launch,
`local.MxcLaunch`, into the Job Core already holds. `mxc.FakeMxc` scripts the launcher
and the workload outcome separately, which is what `mxc.FakeOutcome` is for.

Nothing here starts a process, opens a socket or calls a Windows API: `no_process`
fails the test if `subprocess.Popen`, `proc.run`, `proc.spawn_detached` or
`local._stream` is reached, and `os_tripwire` (imported from the unit file, the way
tests here share fixtures) fails it again at teardown for the native primitives.
"""

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from claude_sessions import proc

from archeus.core.domain import ids
from archeus.harnesses import base
from archeus.infra.paths import (ExecPaths, VerifyPaths, isolation_state,
                                 processes_registry, verify_consumed)
from archeus.node import isolation as iso
from archeus.node import local, mxc, mxc_native, staging

from v1.unit.test_pv20_isolation import (FakeBoundary, make_satisfying_request,
                                         os_tripwire)

#: the commit a verifier's checkout is exported from, and an import sits on
SEED = 'b' * 40
#: what the seed's one file holds, before the agent's edit
SEED_CONTENT = b'print("x")\n'


def digest(content):
    return hashlib.sha1(b'blob %d\0' % len(content) + content).hexdigest()


def record(mode, oid, size, path):
    """One `ls-tree -r -z -l --full-tree` record, as the store's Git answers them."""
    return b'%s blob %s %s\t%s\0' % (mode.encode(), oid.encode(), str(size).encode(),
                                      path.encode())


# ── the fakes: an MXC boundary, and the launcher behind it ────────────────────

def outcome(launcher_exit=0, agent_outcome=3, stdout=b'', stderr=b''):
    """The launcher's own exit, kept apart from what the workload reports."""
    return mxc.FakeOutcome(launcher_exit=launcher_exit, agent_outcome=agent_outcome,
                           stdout=stdout, stderr=stderr)


def script(specs):
    """One scripted answer per launch; the last repeats."""
    specs = list(specs) or [outcome()]
    while True:
        for spec in specs:
            yield spec


class Transport:
    """What an MXC boundary holds behind its seam: Core's policy compiler in front of
    `mxc.spawn`, which admits nothing of its own while `NATIVE_RUN_ENABLED` is False."""

    compile_policy = staticmethod(mxc.compile_policy)

    def __init__(self, outcomes=()):
        self.launcher = mxc.FakeMxc(script(outcomes))
        self.spawned = []

    def spawn(self, policy, *, exe, job):
        self.spawned.append((policy, exe, job))
        return mxc.spawn(policy, exe=exe, job=job, backend=self.launcher)


class MxcBoundary(FakeBoundary):
    """A boundary that launches: it hands `local.MxcLaunch` the policy of the one
    process it is asked to start, and returns that launch as the child.

    `env_rows` is what the boundary's own side of the host adds to the environment
    block — a Windows boundary's `SYSTEMROOT`, which the caller's built-from-nothing
    environment has no business naming — and `kill_on_close` is what Core's Job close
    does to a tree it holds.
    """

    def __init__(self, *, sdk, readonly=(), denied=(), outcomes=(), agent=None):
        super().__init__()
        self.sdk_root, self.pins = sdk
        self.readonly, self.denied = tuple(readonly), tuple(denied)
        self.backend = Transport(outcomes)
        self.launches = []
        self.serial = 0
        self.outcome_reader = agent if agent is not None else (lambda p: p.agent_outcome)
        self.env_rows = {'SYSTEMROOT': 'C:\\Windows'}
        self.timeout_ms = 5000
        self.kill_on_close = False
        self.before_construct = None
        self.before_start = None
        self.held = []

    def host_env(self, env):
        """The environment block with this boundary's rows added for the names it does
        not already carry: on Windows Core builds `SystemRoot` itself, and the same name
        twice, whatever its case, is a policy error."""
        have = {name.upper() for name in env}
        return {**env, **{k: v for k, v in self.env_rows.items() if k.upper() not in have}}

    def launch(self, argv, *, cwd, env, profile, job, stdin, stdout, **extra):
        call = {'argv': list(argv), 'cwd': cwd, 'env': dict(env), 'profile': profile,
                'job': job, 'stdin': stdin, 'stdout': stdout}
        call.update({k: v for k, v in extra.items()})
        self.launch_calls.append(call)
        if not self.launch_ok:
            raise iso.IsolationUnavailable('launch', 'synthetic refusal')
        if self.before_construct is not None:
            self.before_construct()
        launch = local.MxcLaunch(backend=self.backend, sdk_root=self.sdk_root,
                                 pins=self.pins, outcome=self.outcome_reader,
                                 workspace=cwd, readonly=self.readonly,
                                 denied=self.denied, cwd=cwd,
                                 command_line=' '.join(argv),
                                 env=self.host_env(env),
                                 timeout_ms=self.timeout_ms)
        self.launches.append(launch)
        self.held.append((launch, job))
        if self.before_start is not None:
            self.before_start()
        launch.start(job=job)
        # what the boundary owes the caller: the inherited handles are the files Core
        # opened, and the workload's answer is the bytes it printed into them
        path = stdout.get('stdio') if isinstance(stdout, dict) else stdout
        if isinstance(path, str) and launch.process is not None:
            with open(path, 'ab' if stdout.get('mode') == 'append' else 'wb') as f:
                f.write(launch.process.stdout.getvalue())
        return launch

    def create_job(self, execution_id):
        # an unnamed, non-inheritable Job of its own, as a real one is: distinct
        # handles, so a resume can never be handed the closed Job of the process before
        return dict(super().create_job(execution_id),
                    handle='synthetic-job-%d' % (self.serial + 1,))

    def close_job(self, job):
        self.serial += 1
        super().close_job(job)
        if self.kill_on_close:
            for launch, held in self.held:
                if held is job and launch.process is not None:
                    launch.process.terminate()


class FakeWin32:
    """Every native call the MXC transport owns. None of them may be reached while
    admission is closed."""

    CALLS = ('protected_policy', 'remove_policy', 'pipe', 'attribute_list',
             'delete_attribute_list', 'create_process_w', 'creation_time', 'in_job',
             'resume_thread', 'terminate_process', 'close_handle', 'poll', 'read',
             'write')

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name in FakeWin32.CALLS:
            def reached(*args, **kwargs):
                self.calls.append(name)
                raise AssertionError('the native transport reached %s' % name)
            return reached
        raise AttributeError(name)


@pytest.fixture
def sdk(tmp_path):
    """An expanded MXC SDK: the two artifacts the reviewed pin names, and no other."""
    root = tmp_path / 'mxc-sdk'
    (root / 'bin' / 'x64').mkdir(parents=True)
    (root / 'package.json').write_text(
        json.dumps({'name': staging.MXC_PACKAGE, 'version': staging.MXC_VERSION}),
        encoding='utf-8')
    (root / staging.MXC_EXE).write_bytes(b'the fake launcher')
    pins = {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest()
            for rel in ('package.json', staging.MXC_EXE)}
    return str(root), pins


@pytest.fixture(autouse=True)
def no_process(monkeypatch):
    """No real process, no real Git, no detached fallback reachable by accident; the
    fake pid has the one creation time Core's own identity read answers with."""
    hits = []

    def trip(what):
        def reached(*args, **kwargs):
            hits.append(what)
            raise AssertionError('%s was reached: a real process started' % what)
        return reached

    monkeypatch.setattr(subprocess, 'Popen', trip('subprocess.Popen'))
    monkeypatch.setattr(proc, 'run', trip('proc.run'))
    monkeypatch.setattr(proc, 'spawn_detached', trip('proc.spawn_detached'))
    monkeypatch.setattr(local, '_stream', trip('local._stream'))
    monkeypatch.setattr(proc, 'process_create_time', lambda pid: 17.0)
    monkeypatch.setattr(iso, 'base_create_time', lambda pid: 17.0)
    yield hits
    assert hits == [], 'a real process was started: %r' % (hits,)


# ── the two paths, wired ─────────────────────────────────────────────────────

class Agent:
    """The adapter seam: it hands the spec to `base.spawn` and decides nothing."""

    id = 'fake-agent'

    def __init__(self):
        self.stops = []

    def start(self, spec):
        return base.spawn(spec, [sys.executable, '-c', 'pass'])[0]

    def resume(self, spec, state):
        return base.spawn(spec, [sys.executable, '-c', 'pass'])[0]

    def stop(self, handle, grace_s=0.0):
        self.stops.append(handle)


def agent_case(tmp_path, sdk, **kw):
    """A node whose isolated launches reach the MXC transport, under a plan that
    satisfies §3.4: the execution's own work dir as its one writable grant (the shape
    `Isolation.default_plan` gives it), everything else read and execute only."""
    eid = ids.new_id('execution')
    planned = make_satisfying_request(eid, str(tmp_path / 'layout'))
    work = ExecPaths(eid).work
    os.makedirs(os.path.join(work, 'src'), exist_ok=True)
    with open(os.path.join(work, 'src', 'main.py'), 'xb') as f:
        f.write(SEED_CONTENT)
    grants = tuple(iso.Grant(work, g.access, g.row) if g.row == 'workspace' else g
                   for g in planned.grants)
    request = dataclasses.replace(planned, workspace=work, grants=grants)
    boundary = MxcBoundary(sdk=sdk, readonly=(request.grant_for('runtime').path,), **kw)
    node = local.LocalNode()
    # the node is the authority's instrument, as it is in production: the registry the
    # §3.7 evidence lands in is the one reconciliation reads
    authority = iso.Isolation(node, boundary=boundary, plan=lambda spec: request)
    node.isolation = authority
    spec = base.ExecutionSpec(execution_id=eid, prompt='go', workdir=work)
    return SimpleNamespace(node=node, authority=authority, boundary=boundary,
                           request=request, spec=spec, agent=Agent(),
                           runtime=request.grant_for('runtime').path, work=work)


@pytest.fixture
def checks(tmp_path, sdk, monkeypatch):
    """Confined verifier checks, driven by the real `run_confined_check`."""
    tool = tmp_path / 'staged' / 'toolchain'
    tool.mkdir(parents=True)
    (tool / 'runner.exe').write_bytes(b'the staged runner')
    boundary = MxcBoundary(sdk=sdk, readonly=(str(tool),))
    recorded = []

    def export(project_id, revision, dest, workdirs, deadline):
        # the tree of *revision*, and no `.git`: Core writes it as data
        os.mkdir(os.path.join(dest, 'src'))
        with open(os.path.join(dest, 'src', 'main.py'), 'xb') as f:
            f.write(SEED_CONTENT)

    monkeypatch.setattr(local, '_export_tree', export)
    node = local.LocalNode()
    node.isolation = iso.Isolation(node, boundary=boundary)

    def run(verification_id, attempt, argv=('runner', 'check'), timeout=30):
        return node.run_confined_check(verification_id, attempt, list(argv),
                                       toolchain=[str(tool)], timeout=timeout,
                                       record=recorded.append, project_id='proj',
                                       revision=SEED, workdirs=[])

    return SimpleNamespace(node=node, boundary=boundary, run=run, recorded=recorded,
                           tool=str(tool))


def registry_lines():
    path = processes_registry()
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def link_second_name(directory, name):
    """A second name for one file inside a grant: the same bytes, reachable twice."""
    first = os.path.join(directory, 'one.txt')
    if not os.path.exists(first):
        with open(first, 'xb') as f:
            f.write(b'these bytes have two names\n')
    second = os.path.join(directory, name)
    os.link(first, second)
    return second


# ── the verifier path: two fresh verifiers, one attempt each ──────────────────

def test_two_fresh_verifiers_get_two_executions_of_their_own(checks):
    """Admission, identity, Job, checkout, environment and policy are each attempt's
    own: nothing is shared with, or reused from, another verifier's run."""
    first, second = ids.new_id('verification'), ids.new_id('verification')
    attempts = [(first, 0), (second, 0), (first, 1)]
    results = [checks.run(vid, n) for vid, n in attempts]
    calls = checks.boundary.launch_calls
    assert len(calls) == 3 == len(checks.recorded)
    assert [r['exit_code'] for r in results] == [3, 3, 3]
    assert [r['confinement']['ac_profile'] for r in results] == [c['profile']
                                                                 for c in calls]
    assert len({c['profile'] for c in calls}) == 3
    assert len({r['confinement']['ac_sid'] for r in results}) == 3
    assert [c['job'] for c in calls] == [s[2] for s in checks.boundary.backend.spawned]
    assert len({tuple(sorted(c['job'].items())) for c in calls}) == 3
    assert [c['cwd'] for c in calls] == [VerifyPaths(v, n).checkout for v, n in attempts]
    for (vid, n), call in zip(attempts, calls):
        p = VerifyPaths(vid, n)
        assert call['env']['PATH'] == os.pathsep.join([checks.tool])
        assert call['env']['TEMP'] == call['env']['TMP'] == p.tmp
        assert call['env']['USERPROFILE'] == os.path.dirname(p.checkout)
        assert not [k for k in call['env']
                    if k.startswith(('ARCHEUS_', 'CLAUDE_', 'GIT_', 'HTTP', 'SSH_'))]
    for (vid, n), (policy, exe, _job) in zip(attempts,
                                             checks.boundary.backend.spawned):
        fs = policy.raw['filesystem']
        checkout = os.path.normpath(VerifyPaths(vid, n).checkout)
        assert fs['readwritePaths'] == [checkout]
        assert fs['readonlyPaths'] == [os.path.normpath(checks.tool)]
        assert fs['deniedPaths'] == []
        assert policy.raw['process']['cwd'] == checkout
        assert policy.raw['ui']['disable'] is True
        assert os.path.basename(exe) == os.path.basename(staging.MXC_EXE)
    assert checks.boundary.backend.launcher.events[:4] == ['create_suspended',
                                                           'assign_job', 'verify_job',
                                                           'resume']
    assert checks.boundary.closed == [c['job'] for c in calls]
    assert checks.boundary.profiles == set()          # every identity released


def test_an_attempt_is_admitted_once_and_a_second_reading_of_it_is_refused(checks):
    verification_id = ids.new_id('verification')
    key = iso.Principal('verify', verification_id, 0).key
    first = checks.run(verification_id, 0)
    assert first['error'] is None and first['exit_code'] == 3
    with open(verify_consumed(key), encoding='utf-8') as f:
        assert f.read().strip() == key
    assert not os.path.lexists(isolation_state(key))
    again = checks.run(verification_id, 0)
    assert again['exit_code'] is None
    assert again['error'] == 'isolation: attempt_consumed'
    assert again['output'] == b'' and again['confinement'] == {}
    assert len(checks.boundary.launch_calls) == 1
    assert checks.recorded == [first, again]


def test_the_verdict_is_the_workloads_exit_not_a_claim_the_process_printed(checks):
    checks.boundary.backend.launcher.outcomes = script(
        [outcome(launcher_exit=0, agent_outcome=1,
                 stdout=b'{"ok": true, "exit_code": 0, "verdict": "pass"}\n')])
    result = checks.run(ids.new_id('verification'), 0)
    assert result['exit_code'] == 1 and result['error'] is None
    assert b'"verdict": "pass"' in result['output']
    launch = checks.boundary.launches[0]
    assert launch.launcher_exit == 0            # the launcher's own success, unused
    assert launch.process.stdout.tell() == 0    # never read for the verdict
    assert checks.recorded == [result]


@pytest.mark.parametrize('forged', [None, True, '0', 1.0])
def test_a_workload_outcome_that_is_not_an_exit_code_is_refused(checks, forged):
    """The outcome reader is Core's and bound to this process: a launcher answering
    anything else is no verdict, and the Job goes before the answer can be retried."""
    checks.boundary.backend.launcher.outcomes = script(
        [outcome(launcher_exit=0, agent_outcome=forged)])
    with pytest.raises(staging.StageError, match='outcome is unavailable'):
        checks.run(ids.new_id('verification'), 0)
    assert checks.recorded == []
    assert len(checks.boundary.closed) == 1
    assert checks.boundary.deleted == []        # the profile is left for reclaim


@pytest.mark.parametrize('when', ['prepare', 'grant', 'launch'])
def test_a_grant_with_a_second_name_for_one_file_is_refused_at_every_scan(checks, when):
    """The hardlink gate runs when the attempt's rows are prepared, when the MXC grant
    is taken, and again immediately before the launcher is spawned."""
    verification_id = ids.new_id('verification')
    checkout = VerifyPaths(verification_id, 0).checkout
    if when == 'prepare':
        link_second_name(checks.tool, 'second.txt')
    elif when == 'grant':
        checks.boundary.before_construct = lambda: link_second_name(checkout,
                                                                     'second.txt')
    else:
        checks.boundary.before_start = lambda: link_second_name(checkout, 'second.txt')
    result = checks.run(verification_id, 0)
    assert result['exit_code'] is None and 'a second name' in result['error']
    expected = 'prepare_failed' if when == 'prepare' else 'launch_failed'
    assert result['error'].startswith(expected)
    # the gate refused it, not the policy compiler's own scan, and before a spawn
    assert 'invalid MXC policy' not in result['error']
    assert checks.boundary.backend.spawned == []
    assert len(checks.boundary.launches) == (0 if when in ('prepare', 'grant') else 1)
    assert len(checks.recorded) == 1


def test_a_confined_check_answers_with_the_identity_and_job_it_ran_under(checks):
    verification_id = ids.new_id('verification')
    key = iso.Principal('verify', verification_id, 2).key
    result = checks.run(verification_id, 2)
    assert result['error'] is None and result['truncated'] is False
    assert result['output'] == b''
    assert result['confinement'] == {
        'isolated': True, 'ac_profile': iso.profile_name(key),
        'ac_sid': checks.boundary.derive_sid(key), 'capabilities': [],
        'job': 'core-held-unnamed-kill-on-close'}


# ── the agent path ───────────────────────────────────────────────────────────

def test_an_isolated_agent_launch_compiles_one_policy_and_spawns_once(tmp_path, sdk):
    """One policy, one spawn, into the Job Core holds, with the environment Core built
    and no UI for the launcher to put up: a launch that fails has no interface to
    retry through, because there is none."""
    case = agent_case(tmp_path, sdk)
    handle = case.node.spawn(case.agent, case.spec, isolated=True)
    calls = case.boundary.launch_calls
    assert len(calls) == 1
    call, launch = calls[0], case.boundary.launches[0]
    raw = launch.policy.raw
    workspace = os.path.normpath(case.request.workspace)
    assert raw['filesystem']['readwritePaths'] == [workspace]
    assert raw['filesystem']['readonlyPaths'] == [os.path.normpath(case.runtime)]
    assert raw['filesystem']['deniedPaths'] == []
    assert raw['process']['cwd'] == workspace == os.path.normpath(call['cwd'])
    assert raw['process']['commandLine'] == ' '.join(call['argv'])
    assert raw['process']['inheritDefaultEnv'] is False
    assert raw['process']['timeout'] == case.boundary.timeout_ms
    assert raw['ui'] == {'disable': True, 'clipboard': 'none', 'injection': False}
    assert raw['network'] == {'egress': {'default': 'deny'},
                              'ingress': {'default': 'deny', 'hostLoopback': 'deny'}}
    assert raw['telemetry'] == {'enabled': False}
    assert raw['lifecycle'] == {'destroyOnExit': True, 'preservePolicy': False}
    env = case.boundary.host_env(call['env'])
    assert set(raw['process']['env']) == {'%s=%s' % kv for kv in env.items()}
    assert call['env']['ARCHEUS_EXECUTION_ID'] == case.spec.execution_id
    # an edit and a local commit are inside the one writable grant; a push is not
    assert call['env']['GIT_TERMINAL_PROMPT'] == '0' and call['env']['GIT_ASKPASS'] == ''
    assert call['env']['GIT_CONFIG_KEY_0'] == 'credential.helper'
    assert call['env']['GIT_CONFIG_VALUE_0'] == ''
    assert 'SSH_AUTH_SOCK' not in call['env']
    assert case.boundary.backend.spawned == [(launch.policy, os.path.join(
        case.boundary.sdk_root, *staging.MXC_EXE.split('/')), call['job'])]
    assert case.boundary.backend.launcher.events == ['create_suspended', 'assign_job',
                                                     'verify_job', 'resume']
    assert (handle.pid, launch.pid) == (1000, 1000)
    line = next(x for x in registry_lines() if x.get('op') == 'spawn'
                and x['execution_id'] == case.spec.execution_id)
    assert line['isolated'] is True and line['ac_profile'] == call['profile']
    assert line['ac_sid'] == case.authority.record(case.spec.execution_id).sid


@pytest.mark.parametrize('ask', [('ui', 'enable'), ('ui', 1), ('ui', None),
                                 ('egress', 'allow'), ('proxy_url',
                                  'http://proxy.example/')])
def test_a_policy_that_asks_for_a_ui_or_an_egress_is_never_compiled(tmp_path, sdk, ask):
    """Only the one shape Core itself compiles exists: an interface the launcher can
    put up, or a way out of the network, is refused where the policy is made."""
    case = agent_case(tmp_path, sdk)
    kw = {'workspace': case.request.workspace, 'cwd': case.request.workspace,
          'command_line': 'agent.exe', 'timeout_ms': 1000,
          'readonly': (case.runtime,),
          'env': {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': case.runtime}}
    kw[ask[0]] = ask[1]
    want = ('proxy must be an explicit loopback' if ask[0] == 'proxy_url'
            else 'unsupported UI or egress')
    with pytest.raises(mxc.MxcUnavailable, match=want):
        mxc.compile_policy(**kw)


@pytest.mark.parametrize('mutate', [('ui.clipboard', 'read-write', 'unsafe UI'),
                                    ('telemetry.enabled', True, 'unsafe UI'),
                                    ('network.egress.default', 'allow',
                                     'unsafe network')])
def test_a_policy_mutated_towards_a_ui_or_an_egress_is_refused_at_the_gate(tmp_path,
                                                                          sdk, mutate):
    case = agent_case(tmp_path, sdk)
    policy = mxc.compile_policy(workspace=case.work, cwd=case.work,
                                command_line='agent.exe', readonly=(case.runtime,),
                                timeout_ms=1000,
                                env={'SYSTEMROOT': 'C:\\Windows',
                                     'LOCALAPPDATA': case.runtime})
    raw = json.loads(json.dumps(policy.raw))
    where, value, want = mutate
    node = raw
    for part in where.split('.')[:-1]:
        node = node[part]
    node[where.split('.')[-1]] = value
    with pytest.raises(mxc.MxcUnavailable, match=want):
        mxc.validate_policy(mxc.MxcPolicy(raw))


def test_an_edit_inside_the_one_grant_is_imported_as_data_and_locally_committed(
        tmp_path, sdk, monkeypatch):
    """The agent's edit sits in its workspace and nowhere else; the import is Core's
    own walk plus one `fast-import` that writes the ref, whose parent is the seed."""
    case = agent_case(tmp_path, sdk)
    case.node.spawn(case.agent, case.spec, isolated=True)
    work = case.work
    edited, kept, added = (b'print("the agent edited this")\n', b'#!/bin/sh\n',
                          b'# added inside the grant\n')
    os.makedirs(os.path.join(work, 'notes'), exist_ok=True)
    with open(os.path.join(work, 'src', 'main.py'), 'wb') as f:
        f.write(edited)
    with open(os.path.join(work, 'src', 'tool.sh'), 'xb') as f:
        f.write(kept)
    with open(os.path.join(work, 'notes', 'added.md'), 'xb') as f:
        f.write(added)
    launch = case.boundary.launches[0]
    assert launch.policy.raw['filesystem']['readwritePaths'] == [os.path.normpath(work)]

    store = tmp_path / 'store'
    os.mkdir(store)
    seed = [record('100644', digest(SEED_CONTENT), len(SEED_CONTENT), 'src/main.py'),
            record('100755', digest(kept), len(kept), 'src/tool.sh'),
            record('100644', digest(b'gone\n'), 5, 'docs/stale.md')]
    tree_of_commit = [record('100644', digest(edited), len(edited), 'src/main.py'),
                      record('100755', digest(kept), len(kept), 'src/tool.sh'),
                      record('100644', digest(added), len(added), 'notes/added.md')]
    calls, stream = [], []
    commit, tree = 'c' * 40, 'd' * 40
    ref_of = local._import_ref(case.spec.execution_id)

    def store_git(mode, args, *, workdirs, git_dir=None, stdin=None, timeout=120,
                  sink=None):
        calls.append((mode, list(args), git_dir))
        if args[:3] == ['rev-parse', '--verify', '-q'] and args[-1] == ref_of:
            raise local.StoreError('unknown revision')      # absent: importable
        if args[0] == 'rev-parse':
            return commit + '\n'
        if args[0] == 'cat-file':
            return 'tree %s\nparent %s\n\n' % (tree, SEED)
        if args[0] == 'fast-import':
            stream.append(b''.join(stdin))
            return ''
        sink.feed(b''.join(seed if args[-1] == SEED else tree_of_commit))
        sink.end()
        return ''

    monkeypatch.setattr(local.LocalNode, 'store_open',
                        staticmethod(lambda project_id, *, workdirs: str(store)))
    monkeypatch.setattr(local.LocalNode, 'store_git', staticmethod(store_git))
    result = case.node.import_workspace('proj', case.spec.execution_id, SEED,
                                        workdirs=[])
    assert result['revision'] == commit and result['tree'] == tree
    assert result['files_changed'] == ['A notes/added.md', 'D docs/stale.md',
                                       'M src/main.py']
    assert (result['deleted'], result['dropped_dirs']) == (1, 0)
    # Core's walk named every file and Git was asked for nothing but the reads, the
    # one write and its read-back: no checkout, no clone, no write-tree, no index
    assert [a[1][0] for a in calls] == ['rev-parse', 'ls-tree', 'fast-import',
                                        'rev-parse', 'cat-file', 'ls-tree']
    assert [a[0] for a in calls] == ['trusted', 'trusted', 'import', 'trusted',
                                     'trusted', 'trusted']
    assert all(a[2] == str(store) for a in calls)
    assert calls[2][1] == ['fast-import', '--done', '--quiet']
    sent = stream[0]
    ref = ('refs/archeus/exec/%s/import' % case.spec.execution_id).encode()
    assert sent.startswith(b'commit ' + ref + b'\n')
    assert (b'\nfrom ' + SEED.encode() + b'\ndeleteall\n') in sent
    assert sent.endswith(b'done\n')
    assert (b'M 100644 inline src/main.py\ndata %d\n' % len(edited)) + edited in sent
    assert b'M 100755 inline src/tool.sh\n' in sent


def test_an_import_whose_tree_is_not_what_core_sent_is_refused(tmp_path, sdk,
                                                              monkeypatch):
    case = agent_case(tmp_path, sdk)
    content = b'print("one")\n'
    with open(os.path.join(case.work, 'src', 'main.py'), 'wb') as f:
        f.write(content)
    store = tmp_path / 'store'
    os.mkdir(store)
    seen = []
    ref_of = local._import_ref(case.spec.execution_id)

    def store_git(mode, args, *, workdirs, git_dir=None, stdin=None, timeout=120,
                  sink=None):
        seen.append(list(args))
        if args[:3] == ['rev-parse', '--verify', '-q'] and args[-1] == ref_of:
            raise local.StoreError('unknown revision')              # absent
        if args[0] == 'rev-parse':
            return 'c' * 40 + '\n'
        if args[0] == 'cat-file':
            return 'tree %s\nparent %s\n\n' % ('d' * 40, SEED)
        if args[0] == 'fast-import':
            for _chunk in stdin:
                pass
            return ''
        sink.feed(record('100644', 'e' * 40, len(content), 'src/main.py'))
        sink.end()
        return ''

    monkeypatch.setattr(local.LocalNode, 'store_open',
                        staticmethod(lambda project_id, *, workdirs: str(store)))
    monkeypatch.setattr(local.LocalNode, 'store_git', staticmethod(store_git))
    with pytest.raises(local.StoreError, match='is not what Core sent'):
        case.node.import_workspace('proj', case.spec.execution_id, SEED, workdirs=[])
    assert seen[-1][0] == 'ls-tree'
    assert case.boundary.backend.spawned == []


def test_an_import_ref_that_exists_already_is_never_written_again(tmp_path, sdk,
                                                                 monkeypatch):
    case = agent_case(tmp_path, sdk)
    store = tmp_path / 'store'
    os.mkdir(store)
    seen = []

    def store_git(mode, args, *, workdirs, git_dir=None, stdin=None, timeout=120,
                  sink=None):
        seen.append(list(args))
        if args[0] != 'rev-parse':
            raise AssertionError('the ref is probed before anything is read: %r' % (args,))
        return 'c' * 40

    monkeypatch.setattr(local.LocalNode, 'store_open',
                        staticmethod(lambda project_id, *, workdirs: str(store)))
    monkeypatch.setattr(local.LocalNode, 'store_git', staticmethod(store_git))
    ref = 'refs/archeus/exec/%s/import' % case.spec.execution_id
    with pytest.raises(local.StoreError, match='exists already: an import is written'):
        case.node.import_workspace('proj', case.spec.execution_id, SEED, workdirs=[])
    assert seen == [['rev-parse', '--verify', '-q', ref]]


# ── no retry, no fallback, no native run ─────────────────────────────────────

@pytest.mark.parametrize('cause', ['boundary', 'admission', 'establish'])
def test_an_isolated_launch_that_fails_retries_nothing_and_falls_back_to_nothing(
        tmp_path, sdk, no_process, cause):
    case = agent_case(tmp_path, sdk)
    api = FakeWin32()
    if cause == 'boundary':
        case.boundary.launch_ok = False
    elif cause == 'admission':
        assert mxc.NATIVE_RUN_ENABLED is False
        case.boundary.backend = mxc_native.Backend(api, case.boundary, lambda raw: True)
    else:
        case.boundary.create_fail = 'profile_create'
    with pytest.raises(base.SpawnFailed, match='isolation:'):
        case.node.spawn(case.agent, case.spec, isolated=True)
    assert len(case.boundary.launch_calls) == (0 if cause == 'establish' else 1)
    assert api.calls == []                                   # the transport is dark
    if cause != 'admission':
        assert case.boundary.backend.launcher.calls == []
    # no retry: the marker stays, and a second spawn is reconciliation's, not Core's
    with pytest.raises(base.AlreadySpawned):
        case.node.spawn(case.agent, case.spec, isolated=True)
    assert len(case.boundary.launch_calls) == (0 if cause == 'establish' else 1)
    assert no_process == []                       # never a detached shell
    lines = [x for x in registry_lines() if x['execution_id'] == case.spec.execution_id]
    assert [x for x in lines if x.get('op') == 'spawn'] == []
    if cause == 'establish':
        assert [x['op'] for x in lines] == ['isolation_failed']


def test_native_mxc_admission_is_closed_and_the_transport_is_never_touched(tmp_path):
    assert mxc.NATIVE_RUN_ENABLED is False
    api = FakeWin32()
    native = mxc_native.Backend(api, FakeBoundary(), lambda raw: True)
    work = tmp_path / 'work'
    work.mkdir()
    policy = mxc.compile_policy(workspace=str(work), cwd=str(work),
                                command_line='wxc-exec.exe --policy x',
                                env={'SYSTEMROOT': 'C:\\Windows',
                                     'LOCALAPPDATA': str(work)}, timeout_ms=1000)
    exe = str(tmp_path / 'wxc-exec.exe')
    for call in (lambda: mxc.spawn(policy, exe=exe, job={'job': 1}, backend=native,
                                   native_run=True),
                 lambda: mxc.spawn(policy, exe=exe, job={'job': 1}),
                 lambda: native.spawn(policy, exe=exe, job={'job': 1})):
        with pytest.raises(mxc.MxcUnavailable, match='native MXC execution disabled'):
            call()
    assert api.calls == []
    assert native.transport._policies == {}


# ── stop and resume ──────────────────────────────────────────────────────────

def test_a_stopped_execution_resumes_as_the_same_identity_with_a_new_process(
        tmp_path, sdk, no_process):
    case = agent_case(tmp_path, sdk)
    case.boundary.kill_on_close = True
    first = case.node.spawn(case.agent, case.spec, isolated=True)
    job_one = case.boundary.launch_calls[0]['job']
    assert case.authority.held_job(case.spec.execution_id) == job_one
    assert case.node.kill(case.agent, first) == 'killed'
    assert case.agent.stops == [first]
    assert case.node.fence_isolation(case.spec.execution_id) is None
    assert case.boundary.closed == [job_one]
    assert case.boundary.launches[0].process.is_alive() is False
    assert case.authority.held_job(case.spec.execution_id) is None
    case.node.ended(first, 0, 1)
    second = case.node.spawn(case.agent, dataclasses.replace(case.spec, process_seq=2),
                             isolated=True, resume_state={'session': 'one'})
    calls = case.boundary.launch_calls
    assert len(calls) == 2
    assert calls[0]['profile'] == calls[1]['profile']
    assert calls[0]['job'] != calls[1]['job']
    assert calls[0]['argv'] == calls[1]['argv'] and calls[0]['env'] == calls[1]['env']
    assert (first.pid, second.pid) == (1000, 1001)
    assert case.boundary.launches[1] is not case.boundary.launches[0]
    assert case.boundary.launches[1].policy.raw == case.boundary.launches[0].policy.raw
    # one identity for both processes: the resume was never a new principal
    assert case.boundary.created == [calls[0]['profile']] * 2
    assert case.authority.record(case.spec.execution_id).state == 'established'
    spawns = [x for x in registry_lines() if x.get('op') == 'spawn'
              and x['execution_id'] == case.spec.execution_id]
    assert [x['process_seq'] for x in spawns] == [1, 2]
    assert {x['ac_profile'] for x in spawns} == {calls[0]['profile']}
    assert case.boundary.backend.launcher.events == [
        'create_suspended', 'assign_job', 'verify_job', 'resume'] * 2


def fresh_launch(case, **over):
    """An `MxcLaunch` of the case's own workspace, as the boundary would build one."""
    work = case.request.workspace
    args = dict(backend=case.boundary.backend, sdk_root=case.boundary.sdk_root,
                pins=case.boundary.pins, outcome=lambda p: p.agent_outcome,
                workspace=work, cwd=work, command_line='agent.exe',
                env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': work},
                timeout_ms=1000)
    args.update(over)
    return local.MxcLaunch(**args)


def test_an_mxc_launch_is_consumed_once_however_the_caller_asks(tmp_path, sdk):
    case = agent_case(tmp_path, sdk)
    case.node.spawn(case.agent, case.spec, isolated=True)
    launch = case.boundary.launches[0]
    with pytest.raises(staging.StageError, match='already consumed'):
        launch.start(job={'job': 'a second one'})
    assert len(case.boundary.backend.spawned) == 1
    with pytest.raises(staging.StageError, match='has not started'):
        fresh_launch(case).wait()


def test_a_launch_without_a_core_held_job_or_outcome_reader_is_refused(tmp_path, sdk):
    case = agent_case(tmp_path, sdk)
    with pytest.raises(staging.StageError, match='Core-owned outcome reader'):
        fresh_launch(case, outcome='the workspace can write this')
    with pytest.raises(staging.StageError, match='Core-held Job'):
        fresh_launch(case).start(job=None)
    assert case.boundary.backend.spawned == []
