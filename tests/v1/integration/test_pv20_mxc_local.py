"""Local MXC seams with scripted processes only; no MXC module is installed."""

from dataclasses import dataclass
import hashlib
import io
import json
import os
from types import SimpleNamespace

import pytest

from archeus.node import linkscan, local, mxc_ledger, staging


@dataclass(frozen=True)
class MxcPolicy:
    raw: dict


class FakeProcess:
    pid = 123

    def __init__(self, launcher_exit):
        self.launcher_exit = launcher_exit
        self.stdin, self.stdout, self.stderr = io.BytesIO(), io.BytesIO(), io.BytesIO()

    def wait(self, timeout=None):
        return self.launcher_exit

    def terminate(self):
        raise AssertionError('Job teardown belongs to isolation authority')


class FakeMxc:
    def __init__(self, launcher_exit=0):
        self.process = FakeProcess(launcher_exit)
        self.calls = []
        self.events = []

    def compile_policy(self, *, workspace, readonly=(), denied=(), cwd,
                       command_line, env=None, timeout_ms, ui=False,
                       egress='deny', proxy_url=None):
        assert ui is False and egress == 'deny' and proxy_url is None
        self.calls.append('compile')
        return MxcPolicy({'filesystem': {'readwritePaths': [workspace],
                                        'readonlyPaths': list(readonly)}})

    def spawn(self, policy, *, exe, job, before_resume=None):
        self.calls.append(('spawn', exe, job))
        # the ordering the transport owes the ledger: membership verified, the ownership
        # seam, then the single resume (mxc.FakeMxc follows the same contract)
        self.events.extend(('create_suspended', 'assign_job', 'verify_job'))
        if before_resume is not None:
            before_resume(self.process)
        self.events.append('resume')
        return self.process


@pytest.fixture
def launch_args(tmp_path):
    sdk = tmp_path / 'sdk'
    (sdk / 'bin/x64').mkdir(parents=True)
    (sdk / 'package.json').write_text(json.dumps({
        'name': staging.MXC_PACKAGE, 'version': staging.MXC_VERSION}), encoding='utf-8')
    (sdk / staging.MXC_EXE).write_bytes(b'fake launcher')
    pins = {rel: hashlib.sha256((sdk / rel).read_bytes()).hexdigest()
            for rel in ('package.json', staging.MXC_EXE)}
    work = tmp_path / 'work'
    work.mkdir()
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    return dict(sdk_root=sdk, pins=pins, workspace=str(work), readonly=(str(runtime),),
                cwd=str(work), command_line='fixture command', env={}, timeout_ms=1000)


@pytest.mark.parametrize('launcher,agent', [(0, 7), (9, 0), (0, 0)])
def test_launcher_exit_does_not_decide_workload_outcome(launch_args, launcher, agent):
    backend = FakeMxc(launcher)
    observed = []

    def outcome(process):
        observed.append(process)
        return agent

    launch = local.MxcLaunch(backend=backend, outcome=outcome, **launch_args)
    job = object()
    process = launch.start(job=job)
    assert process.stdout is backend.process.stdout
    assert process.wait(1) == agent
    assert launch.launcher_exit == launcher
    assert observed == [backend.process]
    assert backend.calls == ['compile', ('spawn', str(launch_args['sdk_root'] / staging.MXC_EXE), job)]
    with pytest.raises(staging.StageError, match='consumed'):
        launch.start(job=job)


@pytest.mark.parametrize('agent', [None, True, '0'])
def test_missing_or_forged_result_never_inherits_launcher_success(launch_args, agent):
    launch = local.MxcLaunch(backend=FakeMxc(), outcome=lambda p: agent, **launch_args)
    launch.start(job=object())
    with pytest.raises(staging.StageError, match='outcome is unavailable'):
        launch.wait()


@pytest.mark.parametrize('kind', ['rw', 'ro'])
@pytest.mark.parametrize('when', ['prepare', 'launch'])
def test_every_grant_scanned_twice(launch_args, tmp_path, kind, when):
    outside = tmp_path / 'outside'
    outside.write_bytes(b'outside')
    grant = launch_args['workspace'] if kind == 'rw' else launch_args['readonly'][0]
    backend = FakeMxc()
    def link():
        try:
            os.link(outside, os.path.join(grant, 'alias'))
        except OSError as err:
            pytest.skip('hardlinks unavailable: %s' % err)

    if when == 'prepare':
        link()
        with pytest.raises(staging.StageError, match='second name'):
            local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
        assert backend.calls == []
    else:
        launch = local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
        link()
        with pytest.raises(staging.StageError, match='second name'):
            launch.start(job=object())
        assert backend.calls == ['compile']


@pytest.mark.parametrize('kind', ['rw', 'ro'])
@pytest.mark.parametrize('when', ['grant', 'launch'])
@pytest.mark.parametrize('failure', ['linked', 'unreadable'])
def test_shared_hardlink_gate_refuses(launch_args, monkeypatch, kind, when, failure):
    backend = FakeMxc()
    launch = (local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
              if when == 'launch' else None)
    root = launch_args['workspace'] if kind == 'rw' else launch_args['readonly'][0]

    def scan(path):
        if path == root:
            if failure == 'unreadable':
                raise PermissionError('outside-sensitive-path')
            return ['nested/alias']
        return []

    monkeypatch.setattr(linkscan, 'multi_linked_files', scan)
    with pytest.raises(staging.StageError) as caught:
        if when == 'grant':
            local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
        else:
            launch.start(job=object())
    message = str(caught.value)
    assert ('nested/alias' if failure == 'linked' else 'hardlink scan failed') in message
    assert 'outside-sensitive-path' not in message
    assert root not in message
    assert backend.calls == (['compile'] if when == 'launch' else [])


def test_runtime_reverified_at_launch(launch_args):
    backend = FakeMxc()
    launch = local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
    (launch_args['sdk_root'] / staging.MXC_EXE).write_bytes(b'tampered')
    with pytest.raises(staging.StageError, match='hashes'):
        launch.start(job=object())
    assert backend.calls == ['compile']


def test_no_job_no_spawn(launch_args):
    backend = FakeMxc()
    launch = local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
    with pytest.raises(staging.StageError, match='Core-held Job'):
        launch.start(job=None)
    assert backend.calls == ['compile']


def test_unfinished_launcher_cannot_supply_result(launch_args):
    launch = local.MxcLaunch(backend=FakeMxc(None), outcome=lambda p: 0, **launch_args)
    launch.start(job=object())
    with pytest.raises(staging.StageError, match='has not exited'):
        launch.wait()


def test_spawn_failure_never_retries_or_falls_back(launch_args):
    backend = FakeMxc()

    def refuse(policy, *, exe, job):
        raise OSError('fixture refusal')

    backend.spawn = refuse
    launch = local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
    with pytest.raises(OSError, match='fixture refusal'):
        launch.start(job=object())
    with pytest.raises(staging.StageError, match='consumed'):
        launch.start(job=object())


def test_a_backend_without_a_ledger_is_asked_for_no_ownership_hook(launch_args):
    """The wiring the ledger owes the transport is only owed when there is a ledger:
    with an injected backend and no journal, no ownership fact is promised, nothing is
    journalled, and an ending that cannot read a Job says so."""
    backend = FakeMxc()
    hooks = []
    real = backend.spawn

    def spawn(policy, *, exe, job, before_resume=None):
        hooks.append(before_resume)
        return real(policy, exe=exe, job=job)

    backend.spawn = spawn
    launch = local.MxcLaunch(backend=backend, outcome=lambda p: 0, **launch_args)
    launch.start(job=object())
    assert hooks == [None]
    assert backend.events == ['create_suspended', 'assign_job', 'verify_job', 'resume']
    assert launch.wait() == 0
    assert launch.completed == 0 and launch.launcher_exit == 0
    assert launch.end_state == {'state': mxc_ledger.DEAD_UNVERIFIED,
                                'reason': 'launcher exited',
                                'quiescence': 'no boundary Job was held to read'}


def test_cancel_reports_what_it_could_not_verify(launch_args):
    """A cancel is the same ending as a timeout, and with no boundary to end and no
    reader to believe it is honest about being unverified rather than clean."""
    launch = local.MxcLaunch(backend=FakeMxc(None), outcome=lambda p: 0, **launch_args)
    launch.start(job=object())
    state = launch.cancel(reason='host timeout')
    assert state['state'] == mxc_ledger.DEAD_UNVERIFIED
    assert state['reason'] == 'host timeout'
    assert state['quiescence'] == 'no boundary Job was held to read'
    assert launch.cancel() is state
    assert launch.completed is None and launch.launcher_exit is None


def test_outcome_reader_required_before_any_backend_call(launch_args):
    backend = FakeMxc()
    with pytest.raises(staging.StageError, match='outcome reader'):
        local.MxcLaunch(backend=backend, outcome=None, **launch_args)
    assert backend.calls == []


def test_verifier_preparation_checks_its_own_grants(tmp_path, monkeypatch):
    verification_id = local.ids.new_id('verification')
    attempt = tmp_path / 'attempt'
    own = attempt / 'own'
    p = SimpleNamespace(dir=str(attempt), checkout=str(own / 'checkout'),
                        home=str(own / 'home'), tmp=str(own / 'tmp'),
                        config=str(own / 'config'), out=str(attempt / 'out'))
    monkeypatch.setattr(local, 'VerifyPaths', lambda vid, n: p)
    monkeypatch.setattr(local, '_export_tree', lambda *a: None)
    monkeypatch.setattr(local.base, '_verifier_env', lambda *a: {'FIXTURE': '1'})
    tool = tmp_path / 'tool'
    tool.mkdir()
    seen = []
    scan = staging.scan_grants

    def scanned(grants):
        seen.append(grants)
        scan(grants)

    monkeypatch.setattr(staging, 'scan_grants', scanned)

    class Authority:
        def run_confined(self, request, argv, **kwargs):
            assert kwargs['prepare']() == {'FIXTURE': '1'}
            assert request.workspace == p.checkout
            assert argv == ['fixture']
            result = {'exit_code': 7, 'error': None}
            kwargs['record'](result)
            return result

    records = []
    node = local.LocalNode(isolation=Authority())
    result = node.run_confined_check(verification_id, 1, ['fixture'], toolchain=[str(tool)],
                                    timeout=1, record=records.append, project_id='fixture',
                                    revision='fixture', workdirs=[])
    assert records == [result]
    assert seen == [(str(own), str(tool))]
    with pytest.raises(FileExistsError):
        node.run_confined_check(verification_id, 1, ['fixture'], toolchain=[str(tool)],
                                timeout=1, record=records.append, project_id='fixture',
                                revision='fixture', workdirs=[])
