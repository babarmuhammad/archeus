# ruff: noqa: F811  (the imported fixtures are taken as arguments)
"""T-457: the agent path and the verifier path over the closed MXC seam.

Both paths run through production code — `base.spawn` → `IsolationContext.launch` for
an agent, `LocalNode.run_confined_check` → `Isolation.run_confined` for a verifier —
into the production `MxcBoundary`, which compiles the policy of the process it is asked to
launch with Core's own compiler (`mxc.compile_policy`) and spawns it through `local.MxcLaunch`
over the native transport, into the Job Core already holds. What stands in for Windows
are the injected fakes of `test_mxc_boundary`: `LauncherApi` scripts the launcher and the
workload outcome separately, and `Jobs` is the Job and process half. `Traced` adds only a
tap on what the boundary launches.

Nothing here starts a process, opens a socket or calls a Windows API: `no_process`
fails the test if `subprocess.Popen`, `proc.run`, `proc.spawn_detached` or
`local._stream` is reached, and `os_tripwire` (imported from the unit file, the way
tests here share fixtures) fails it again at teardown for the native primitives.
Native admission is closed in the shipped code; `gate` opens it for a test over those fakes.
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
from archeus.node import local, mxc, mxc_ledger, mxc_native, staging
from archeus.node.mxc_boundary import MxcBoundary

from v1.unit.test_mxc_boundary import (Jobs, gate, make, outcome, script,  # noqa: F401
                                       seed_journal, sdk)
from v1.unit.test_pv20_isolation import make_satisfying_request, os_tripwire  # noqa: F401

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


# ── the boundary under test, and the fakes behind it ──────────────────────────

class Traced(MxcBoundary):
    """The production boundary with a tap on what it is asked to launch, and the knobs
    these tests turn: a refusal, a change made between the grants and the launch, and
    what Core's Job close does to a tree it holds."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.launch_calls, self.launches, self.held = [], [], []
        self.launch_ok = True
        self.before_grant = self.before_launch = None

    def create_profile(self, execution_id):
        if self.before_grant is not None:
            self.before_grant()
        return super().create_profile(execution_id)

    def launch(self, argv, *, cwd, env, profile, job, stdin, stdout):
        return self._tap(super().launch, argv, cwd, env, profile, job, stdin=stdin,
                         stdout=stdout)

    def launch_confined(self, argv, *, cwd, env, profile, job, timeout, stdin_path, out_path):
        return self._tap(super().launch_confined, argv, cwd, env, profile, job,
                         timeout=timeout, stdin_path=stdin_path, out_path=out_path)

    def _tap(self, launch, argv, cwd, env, profile, job, **handles):
        self.launch_calls.append({'argv': list(argv), 'cwd': cwd, 'env': dict(env),
                                  'profile': profile, 'job': job, **handles})
        if not self.launch_ok:
            raise iso.IsolationUnavailable('launch', 'synthetic refusal')
        if self.before_launch is not None:
            self.before_launch()
        child = launch(argv, cwd=cwd, env=env, profile=profile, job=job, **handles)
        self.launches.append(getattr(child, 'launch', child))
        self.held.append((self.launches[-1], job))
        return child


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


def kill_on_close(case):
    """What Core's Job close does to a tree it holds."""
    case.jobs.on_close.append(lambda job: [launch.process.terminate() for launch, held in
                                           case.boundary.held if held is job
                                           and launch.process is not None])


def agent_case(tmp_path, sdk, **kw):
    """A node whose isolated launches reach the MXC transport, under a plan that
    satisfies §3.4: the execution's own work dir as its workspace and the mailbox and
    state rows writable, everything else read and execute only."""
    eid = ids.new_id('execution')
    planned = make_satisfying_request(eid, str(tmp_path / 'layout'))
    work = ExecPaths(eid).work
    os.makedirs(os.path.join(work, 'src'), exist_ok=True)
    with open(os.path.join(work, 'src', 'main.py'), 'xb') as f:
        f.write(SEED_CONTENT)
    grants = tuple(iso.Grant(work, g.access, g.row) if g.row == 'workspace' else g
                   for g in planned.grants)
    request = dataclasses.replace(planned, workspace=work, grants=grants)
    h = make(tmp_path, sdk, cls=Traced, **kw)
    node = local.LocalNode()
    # the node is the authority's instrument, as it is in production: the registry the
    # §3.7 evidence lands in is the one reconciliation reads
    authority = iso.Isolation(node, boundary=h.boundary, plan=lambda spec: request)
    node.isolation = authority
    spec = base.ExecutionSpec(execution_id=eid, prompt='go', workdir=work)
    return SimpleNamespace(node=node, authority=authority, boundary=h.boundary, jobs=h.jobs,
                           api=h.api, ledger=h.ledger, events=h.events,
                           request=request, spec=spec, agent=Agent(),
                           runtime=request.grant_for('runtime').path, work=work)


@pytest.fixture
def checks(tmp_path, sdk, gate, monkeypatch):
    """Confined verifier checks, driven by the real `run_confined_check`."""
    tool = tmp_path / 'staged' / 'toolchain'
    tool.mkdir(parents=True)
    (tool / 'runner.exe').write_bytes(b'the staged runner')
    h = make(tmp_path, sdk, cls=Traced)
    recorded = []

    def export(project_id, revision, dest, workdirs, deadline):
        # the tree of *revision*, and no `.git`: Core writes it as data
        os.mkdir(os.path.join(dest, 'src'))
        with open(os.path.join(dest, 'src', 'main.py'), 'xb') as f:
            f.write(SEED_CONTENT)

    monkeypatch.setattr(local, '_export_tree', export)
    node = local.LocalNode()
    node.isolation = iso.Isolation(node, boundary=h.boundary)

    def run(verification_id, attempt, argv=('runner', 'check'), timeout=30):
        return node.run_confined_check(verification_id, attempt, list(argv),
                                       toolchain=[str(tool)], timeout=timeout,
                                       record=recorded.append, project_id='proj',
                                       revision=SEED, workdirs=[])

    return SimpleNamespace(node=node, boundary=h.boundary, jobs=h.jobs, api=h.api,
                           events=h.events, run=run, recorded=recorded, tool=str(tool))


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
    assert {r['confinement']['ac_sid'] for r in results} == {''}      # no SID exists to claim
    assert [a[0] for a in checks.jobs.assigned] == [c['job'] for c in calls]
    assert len({tuple(sorted(c['job'].items())) for c in calls}) == 3
    assert [c['cwd'] for c in calls] == [VerifyPaths(v, n).checkout for v, n in attempts]
    for (vid, n), call in zip(attempts, calls):
        p = VerifyPaths(vid, n)
        assert call['env']['PATH'] == os.pathsep.join([checks.tool])
        assert call['env']['TEMP'] == call['env']['TMP'] == p.tmp
        assert call['env']['USERPROFILE'] == os.path.dirname(p.checkout)
        assert not [k for k in call['env']
                    if k.startswith(('ARCHEUS_', 'CLAUDE_', 'GIT_', 'HTTP', 'SSH_'))]
    for (vid, n), launch, made in zip(attempts, checks.boundary.launches,
                                      checks.api.created):
        fs = launch.policy.raw['filesystem']
        checkout = os.path.normpath(VerifyPaths(vid, n).checkout)
        assert fs['readwritePaths'] == [checkout, os.path.dirname(checkout)]
        assert fs['readonlyPaths'] == [os.path.normpath(checks.tool)]
        assert fs['deniedPaths'] == []
        assert launch.policy.raw['process']['cwd'] == checkout
        assert launch.policy.raw['ui']['disable'] is True
        assert os.path.basename(made['application']) == os.path.basename(staging.MXC_EXE)
    assert checks.events[:4] == ['create_suspended', 'assign_job', 'verify_job', 'resume']
    assert checks.jobs.closed == [c['job'] for c in calls]
    for vid, n in attempts:                            # every identity released
        assert not checks.boundary.profile_exists(iso.Principal('verify', vid, n).key)


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
    checks.api.outcomes = script(
        [outcome(launcher_exit=0, agent_outcome=1,
                 stdout=b'{"ok": true, "exit_code": 0, "verdict": "pass"}\n')])
    result = checks.run(ids.new_id('verification'), 0)
    assert result['exit_code'] == 1 and result['error'] is None
    launch = checks.boundary.launches[0]
    assert b'"verdict": "pass"' in result['output']                    # the claim, unread
    assert launch.launcher_exit == 0            # the launcher's own success, unused
    assert checks.recorded == [result]


@pytest.mark.parametrize('forged', [None, True, '0', 1.0])
def test_a_workload_outcome_that_is_not_an_exit_code_is_refused(checks, forged):
    """The outcome reader is Core's and bound to this process: a launcher answering
    anything else is no verdict, and the Job goes before the answer can be retried."""
    checks.api.outcomes = script([outcome(launcher_exit=0, agent_outcome=forged)])
    verification_id = ids.new_id('verification')
    with pytest.raises(staging.StageError, match='outcome is unavailable'):
        checks.run(verification_id, 0)
    assert checks.recorded == []
    assert len(checks.jobs.closed) == 1
    # the profile is left for reclaim: its name is still held and no residue was written
    assert checks.boundary.profile_exists(iso.Principal('verify', verification_id, 0).key)
    assert not os.path.exists(os.path.join(checks.boundary.ledger.root,
                                           'registration-residue.log'))


@pytest.mark.parametrize('when', ['prepare', 'grant', 'launch'])
def test_a_grant_with_a_second_name_for_one_file_is_refused_at_every_scan(checks, when):
    """The hardlink gate runs when the attempt's rows are prepared, when the MXC grant
    is taken, and again immediately before the launcher is spawned."""
    verification_id = ids.new_id('verification')
    checkout = VerifyPaths(verification_id, 0).checkout
    if when == 'prepare':
        link_second_name(checks.tool, 'second.txt')
    elif when == 'grant':
        checks.boundary.before_grant = lambda: link_second_name(checkout, 'second.txt')
    else:
        checks.boundary.before_launch = lambda: link_second_name(checkout, 'second.txt')
    result = checks.run(verification_id, 0)
    assert result['exit_code'] is None
    expected = {'prepare': 'prepare_failed', 'grant': 'isolation: condition_unmet:grants',
                'launch': 'launch_failed'}[when]
    assert result['error'].startswith(expected)
    if when != 'grant':                  # the grant read says only that the row is not held
        assert 'a second name' in result['error']
    # the gate refused it, not the policy compiler's own scan, and before a spawn
    assert 'invalid MXC policy' not in result['error']
    assert checks.api.created == [] and checks.api.policies == []
    assert checks.boundary.launches == []
    assert len(checks.boundary.launch_calls) == (1 if when == 'launch' else 0)
    assert len(checks.recorded) == 1


def test_a_confined_check_answers_with_the_identity_and_job_it_ran_under(checks):
    verification_id = ids.new_id('verification')
    key = iso.Principal('verify', verification_id, 2).key
    result = checks.run(verification_id, 2)
    assert result['error'] is None and result['truncated'] is False
    assert result['output'] == b''
    assert result['confinement'] == {
        'isolated': True, 'ac_profile': iso.profile_name(key),
        'ac_sid': '', 'capabilities': [],
        'job': 'core-held-unnamed-kill-on-close'}


# ── the agent path ───────────────────────────────────────────────────────────

def test_an_isolated_agent_launch_compiles_one_policy_and_spawns_once(tmp_path, sdk, gate):
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
    rows = {g.row: os.path.normpath(g.path) for g in case.request.grants}
    assert raw['filesystem']['readwritePaths'] == [workspace, rows['request'], rows['state']]
    assert raw['filesystem']['readonlyPaths'] == [rows['runtime'], rows['hook'],
                                                  rows['response'], rows['sentinel']]
    assert raw['filesystem']['deniedPaths'] == []
    assert raw['process']['cwd'] == workspace == os.path.normpath(call['cwd'])
    assert raw['process']['commandLine'] == subprocess.list2cmdline(call['argv'])
    assert raw['process']['inheritDefaultEnv'] is False
    assert raw['process']['timeout'] == case.boundary.timeout_ms
    assert raw['ui'] == {'disable': True, 'clipboard': 'none', 'injection': False}
    assert raw['network'] == {'egress': {'default': 'deny'},
                              'ingress': {'default': 'deny', 'hostLoopback': 'deny'}}
    assert raw['telemetry'] == {'enabled': False}
    assert raw['lifecycle'] == {'destroyOnExit': True, 'preservePolicy': False}
    env = dict(call['env'])
    if 'SYSTEMROOT' not in {name.upper() for name in env}:
        env['SYSTEMROOT'] = 'C:\\Windows'
    assert set(raw['process']['env']) == {'%s=%s' % kv for kv in env.items()}
    assert call['env']['ARCHEUS_EXECUTION_ID'] == case.spec.execution_id
    # an edit and a local commit are inside the one writable grant; a push is not
    assert call['env']['GIT_TERMINAL_PROMPT'] == '0' and call['env']['GIT_ASKPASS'] == ''
    assert call['env']['GIT_CONFIG_KEY_0'] == 'credential.helper'
    assert call['env']['GIT_CONFIG_VALUE_0'] == ''
    assert 'SSH_AUTH_SOCK' not in call['env']
    assert [os.path.normcase(c['application']) for c in case.api.created] == [os.path.normcase(
        os.path.join(case.boundary.sdk_root, *staging.MXC_EXE.split('/')))]
    assert [a[0] for a in case.jobs.assigned] == [call['job']]
    assert case.events == ['create_suspended', 'assign_job', 'verify_job', 'resume']
    assert (handle.pid, launch.pid) == (1000, 1000)
    line = next(x for x in registry_lines() if x.get('op') == 'spawn'
                and x['execution_id'] == case.spec.execution_id)
    assert line['isolated'] is True and line['ac_profile'] == call['profile']
    # the record holds the marker Core derived, and the registry claims no SID for it
    assert case.authority.record(case.spec.execution_id).sid.startswith('psec:')
    assert line['ac_sid'] == ''


@pytest.mark.parametrize('ask', [('ui', 'enable'), ('ui', 1), ('ui', None),
                                 ('egress', 'allow'), ('proxy_url',
                                  'http://proxy.example/')])
def test_a_policy_that_asks_for_a_ui_or_an_egress_is_never_compiled(tmp_path, sdk, ask, gate):
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
                                                                          sdk, mutate, gate):
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
        tmp_path, sdk, monkeypatch, gate):
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
    assert launch.policy.raw['filesystem']['readwritePaths'][0] == os.path.normpath(work)

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
                                                              monkeypatch, gate):
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
    assert case.api.created == []


def test_an_import_ref_that_exists_already_is_never_written_again(tmp_path, sdk,
                                                                 monkeypatch, gate):
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
        tmp_path, sdk, no_process, monkeypatch, cause):
    assert mxc.NATIVE_RUN_ENABLED is False
    if cause != 'admission':
        monkeypatch.setattr(mxc, 'NATIVE_RUN_ENABLED', True)
    case = agent_case(tmp_path, sdk)
    if cause == 'boundary':
        case.boundary.launch_ok = False
    elif cause == 'establish':
        seed_journal(case, mxc_ledger.journal_name(case.spec.execution_id, 1), 'intent')
    with pytest.raises(base.SpawnFailed, match='isolation:'):
        case.node.spawn(case.agent, case.spec, isolated=True)
    assert len(case.boundary.launch_calls) == (1 if cause == 'boundary' else 0)
    assert case.api.created == [] and case.api.events == []  # the transport is dark
    # no retry: the marker stays, and a second spawn is reconciliation's, not Core's
    with pytest.raises(base.AlreadySpawned):
        case.node.spawn(case.agent, case.spec, isolated=True)
    assert len(case.boundary.launch_calls) == (1 if cause == 'boundary' else 0)
    assert no_process == []                       # never a detached shell
    lines = [x for x in registry_lines() if x['execution_id'] == case.spec.execution_id]
    assert [x for x in lines if x.get('op') == 'spawn'] == []
    if cause != 'boundary':
        assert [x['op'] for x in lines] == ['isolation_failed']


def test_native_mxc_admission_is_closed_and_the_transport_is_never_touched(tmp_path):
    assert mxc.NATIVE_RUN_ENABLED is False
    api = FakeWin32()
    native = mxc_native.Backend(api, Jobs(), lambda raw: True)
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
        tmp_path, sdk, no_process, gate):
    case = agent_case(tmp_path, sdk)
    kill_on_close(case)
    first = case.node.spawn(case.agent, case.spec, isolated=True)
    job_one = case.boundary.launch_calls[0]['job']
    assert case.authority.held_job(case.spec.execution_id) == job_one
    # the stop ends through the launch, which is what completes its journal (routing a
    # kill to it is the execution context's, B7): the next process may only follow that
    ended = case.boundary.launches[0].cancel(reason='stopped', outcome=0)
    assert ended['state'] == mxc_ledger.DEAD_CLEAN and case.jobs.terminated == [job_one]
    assert case.node.kill(case.agent, first) == 'killed'
    assert case.agent.stops == [first]
    assert case.node.fence_isolation(case.spec.execution_id) is None
    assert case.jobs.closed == [job_one]
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
    # one identity for both processes, and one journal for each: never a new principal
    eid = case.spec.execution_id
    assert sorted(case.ledger.journals()) == [mxc_ledger.journal_name(eid, 1),
                                              mxc_ledger.journal_name(eid, 2)]
    assert case.authority.record(eid).state == 'established'
    spawns = [x for x in registry_lines() if x.get('op') == 'spawn'
              and x['execution_id'] == case.spec.execution_id]
    assert [x['process_seq'] for x in spawns] == [1, 2]
    assert {x['ac_profile'] for x in spawns} == {calls[0]['profile']}
    assert [e for e in case.events if e != 'end_job'] == [
        'create_suspended', 'assign_job', 'verify_job', 'resume'] * 2


def test_a_resume_is_refused_while_the_process_before_it_never_ended_with_a_completion(
        tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk)
    first = case.node.spawn(case.agent, case.spec, isolated=True)
    assert case.node.kill(case.agent, first) == 'killed'
    assert case.node.fence_isolation(case.spec.execution_id) is None
    case.node.ended(first, 0, 1)
    with pytest.raises(base.SpawnFailed, match='generation_unresolved'):
        case.node.spawn(case.agent, dataclasses.replace(case.spec, process_seq=2),
                        isolated=True, resume_state={'session': 'one'})
    assert len(case.boundary.launch_calls) == 1 and len(case.api.created) == 1


class Compiler:
    """A backend that only compiles: the launch under test is never started."""
    compile_policy = staticmethod(mxc.compile_policy)


def fresh_launch(case, **over):
    """An `MxcLaunch` of the case's own workspace, as the boundary would build one."""
    work = case.request.workspace
    args = dict(backend=Compiler(), sdk_root=case.boundary.sdk_root,
                pins=case.boundary.pins, outcome=lambda p: p.agent_outcome,
                workspace=work, cwd=work, command_line='agent.exe',
                env={'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': work},
                timeout_ms=1000)
    args.update(over)
    return local.MxcLaunch(**args)


def test_an_mxc_launch_is_consumed_once_however_the_caller_asks(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk)
    case.node.spawn(case.agent, case.spec, isolated=True)
    launch = case.boundary.launches[0]
    with pytest.raises(staging.StageError, match='already consumed'):
        launch.start(job={'job': 'a second one'})
    assert len(case.api.created) == 1
    with pytest.raises(staging.StageError, match='has not started'):
        fresh_launch(case).wait()


def test_a_launch_without_a_core_held_job_or_outcome_reader_is_refused(tmp_path, sdk, gate):
    case = agent_case(tmp_path, sdk)
    with pytest.raises(staging.StageError, match='Core-owned outcome reader'):
        fresh_launch(case, outcome='the workspace can write this')
    with pytest.raises(staging.StageError, match='Core-held Job'):
        fresh_launch(case).start(job=None)
    assert len(case.api.created) == 0
