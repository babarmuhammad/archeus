# ruff: noqa: F811  (the imported reviewed fixture is taken as an argument)
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
import ast
import os
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from archeus.api import origin
from archeus.core import pv20, runtime
from archeus.core.application import resources, verification
from archeus.node import broker, isolation, local, mxc, mxc_heartbeat, mxc_watchdog_host
from archeus.node import mxc_boundary, mxc_native, mxc_watchdog, origin_native
from archeus.core.domain import entities, ids
from archeus.core.execution import manager as manager_mod
from archeus.core.domain.values import Ref
from archeus.core.verification import evidence
from archeus.core.verification import worker as worker_mod
from archeus.core.verification.worker import VerifyWorker
from archeus.harnesses.base import BROKER_ELIGIBLE as broker_eligible
from archeus.node.pv20_switches import Pv20Switches

from .test_broker_execution import Spy
from .test_provider_broker import binding
from .test_execution_units import _spawn_rig
from .test_gaps_core_application_verification import IMP, Missions, _do, _errored, _seed, db, who
from .test_mxc_boundary import Jobs, LauncherApi
from .test_pv20_mxc_pins import SDK_FILES, reviewed, tree  # noqa: F401
from .test_pv20_isolation import make_satisfying_request, new_execution_id, os_tripwire  # noqa: F401


def assert_closed(core=None):
    assert origin.ORIGIN_ENFORCEMENT_ENABLED is False
    assert isolation.PRODUCTION_DISPATCH_ENABLED is False
    assert isolation.A4_ENFORCED is False
    assert mxc.NATIVE_RUN_ENABLED is False
    assert broker.BROKER_DISPATCH_ENABLED is False
    assert verification.CONFINED_VERIFICATION_ENABLED is False
    assert mxc_heartbeat.HEARTBEAT_ENABLED is False
    assert mxc_watchdog_host.HOST_ENABLED is False
    assert local.LocalNode.store_fetch_accepted is False
    assert resources.ISOLATED_DISPATCH is None
    if core is not None:
        assert not any(vars(core.pv20_switches).values())


class OriginApi:
    def tcp_rows(self):
        return [origin_native.TcpRow('127.0.0.1', 50000, '127.0.0.1', 7337, 5, 42)]

    def process(self, pid, jobs):
        return origin_native.RawProcess(True, 100, 0, 'user.exe', 7, False)

    def core_pid(self):
        return 900

    def core_session(self):
        return 7


class RunningHost:
    def __init__(self, host, events):
        self.host, self.events = host, events
        events.append('host_started')
        host.tick()

    def ready(self):
        return True

    def close(self):
        self.events.append('host_closed')


@pytest.fixture
def candidate(tmp_path, monkeypatch, reviewed):
    monkeypatch.setattr(pv20, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(pv20, '_claimed', set())
    events, cores = [], []
    close = broker.Broker.close

    def broker_close(self):
        if not self._closed:
            events.append('broker_closed')
        close(self)

    monkeypatch.setattr(broker.Broker, 'close', broker_close)
    bindings = pv20.NativeBindings(
        identity_reader=lambda pid: 9000 if pid == 900 else None,
        terminate=lambda pid, created: True, engage_sentinel=lambda: True,
        start_host=lambda host, **kw: RunningHost(host, events),
        win32=lambda root: LauncherApi(), origin_api=OriginApi, jobs=Jobs)
    args = dict(ledger_dir=tmp_path / 'ledger', sdk_root=tree(tmp_path / 'sdk', SDK_FILES),
                authorize=lambda eid, adapter: True, plan=lambda spec: None,
                bindings=bindings, broker_options=dict(
                    core_instance='fixture', live=lambda binding: True,
                    credentials=lambda binding: {}, upstream_of=lambda account: None),
                principal_of=lambda evidence: None, core_port=7337, core_identity=(900, 9000),
                enabled=True, clock=lambda: 100.0, timeout_ms=5000,
                ports=runtime.Ports(executors=[], callers=[], sessions=[], brain=object()))

    def activate(**changes):
        core = pv20.activate_pv20(**dict(args, **changes))
        cores.append(core)
        return core

    yield SimpleNamespace(args=args, activate=activate, events=events, cores=cores)
    for core in cores:
        core.stop()


@pytest.fixture
def quiet_core(monkeypatch):
    for cls in (runtime.EngineLoop, runtime.ExecLoop, runtime.WorldLoop):
        monkeypatch.setattr(cls, 'start', lambda self: None)
    monkeypatch.setattr(runtime.discovery, 'token_protection', lambda: (True, None))

    class Server:
        def __init__(self, api, port):
            self.api, self.port = api, port

        def serve_forever(self, **kw):
            pass

        def shutdown(self):
            pass

        def server_close(self):
            pass

    monkeypatch.setattr(runtime.server, 'Server', Server)


def test_production_core_binds_every_switch(candidate, quiet_core):
    core = candidate.activate()
    switches = core.pv20_switches
    assert len(vars(switches)) == 10 and all(vars(switches).values())
    core.start()
    activation = core.pv20
    assert core.manager.node is activation.node
    assert core.manager.broker is activation.broker
    assert core.manager.switches is switches
    assert core.manager.router.switches is switches
    assert core.verify.world.node is activation.node
    assert core.verify.world.switches is switches
    assert core.api.origin_enforcement_enabled is True
    assert core.api.origin_backend is activation.backend
    assert core.api.origin_registry is activation.registry
    assert core.api.isolated_dispatch_qualified is False
    boundary = activation.node.isolation.boundary
    assert boundary.switches is switches and boundary.available() is True
    assert boundary.watchdog._status()['state'] == 'IDLE'
    assert activation.node.isolation.node is activation.node
    eid = new_execution_id()
    assert activation.node.isolation.requested(eid, SimpleNamespace(id='claude_code')) is True
    activation.node.heartbeat.beat()
    assert activation.host.channel.read()[-1]['kind'] == 'beat'
    assert verification.confined(SimpleNamespace(import_revision='rev'), 'rev', None,
                                 switches=switches) is True
    context = origin.ConnectionContext(None, ('127.0.0.1', 7337), ('127.0.0.1', 50000), 'g1')
    evidence = core.api.origin_backend.attest(context)
    assert evidence.origin == origin.OriginClass.USER
    assert core.api.origin_registry.approved(context, evidence) is True
    assert core.api.origin_backend.valid(context, evidence) is True
    assert_closed()
    core.stop()
    assert_closed(core)
    assert candidate.events == ['host_started', 'broker_closed', 'host_closed']


def test_uncalled_core_starts_closed(quiet_core):
    core = runtime.Core(ports=runtime.Ports(executors=[], callers=[], sessions=[], brain=object()))
    try:
        core.start()
        assert_closed(core)
        assert core.api.origin_enforcement_enabled is False
        assert core.api.origin_backend.readers is None
        assert core.manager.broker is None
        assert core.manager.node.isolation._authorize is None
        assert core.manager.switches is None and core.manager.router.switches is None
        assert core.verify.world.switches is None
    finally:
        core.stop()


@pytest.mark.parametrize('change,reason', [
    ({'enabled': False}, 'activation_closed'),
    ({'enabled': 1}, 'activation_closed'),
    ({'bindings': None}, 'backend_unavailable'),
    ({'authorize': None}, 'backend_unavailable'),
    ({'core_port': 0}, 'invalid_parameters'),
    ({'core_identity': (900, 0)}, 'invalid_parameters'),
    ({'max_age_s': float('nan')}, 'invalid_parameters'),
])
def test_refusal_changes_nothing(candidate, change, reason):
    with pytest.raises(pv20.ActivationRefused) as caught:
        candidate.activate(**change)
    assert caught.value.reason == reason
    assert candidate.events == []
    assert not candidate.args['ledger_dir'].exists()
    assert_closed(runtime.Core())


def test_default_call_is_closed(candidate):
    args = dict(candidate.args)
    del args['enabled']
    with pytest.raises(pv20.ActivationRefused, match='activation_closed'):
        pv20.activate_pv20(**args)
    assert candidate.events == []
    assert not candidate.args['ledger_dir'].exists()


def test_non_windows_refuses_before_building(candidate, monkeypatch):
    monkeypatch.setattr(pv20, 'sys', SimpleNamespace(platform='linux'))
    with pytest.raises(pv20.ActivationRefused, match='windows_required'):
        candidate.activate()
    assert candidate.events == []
    assert not candidate.args['ledger_dir'].exists()
    assert_closed(runtime.Core())


STEPS = [
    (pv20.staging, 'mxc_sdk_pins'), (pv20.staging, 'verify_mxc'),
    (pv20.staging, 'mxc_schema_validator'), (pv20.mxc_ledger, 'Ledger'),
    (pv20.tempfile, 'TemporaryDirectory'), (pv20.origin_native, 'native_readers'),
    (pv20, 'WindowsOriginBackend'), (pv20.origin, 'CorePathRegistry'),
    (pv20.broker_listener, 'loopback_broker'), (pv20.mxc_heartbeat, 'Channel'),
    (pv20.mxc_watchdog_host, 'WatchdogHost'), (pv20.mxc_heartbeat, 'HeartbeatSender'),
    (pv20.mxc_heartbeat, 'WatchdogProxy'), (pv20.mxc_boundary, 'MxcBoundary'),
    (pv20.local, 'LocalNode'), (pv20, 'Activation'), (runtime, 'Core'),
]


@pytest.mark.parametrize('module,name', STEPS, ids=[name for _, name in STEPS])
@pytest.mark.parametrize('existing', [False, True])
def test_each_build_failure_rolls_back(candidate, monkeypatch, module, name, existing):
    root = candidate.args['ledger_dir']
    if existing:
        root.mkdir()
        (root / 'keep').write_bytes(b'previous ledger state')

    def fail(*args, **kw):
        raise RuntimeError('injected build failure')

    with monkeypatch.context() as patch:
        patch.setattr(module, name, fail)
        with pytest.raises(pv20.ActivationRefused, match='build_failed'):
            candidate.activate()
    assert candidate.cores == []
    if 'host_started' in candidate.events:
        assert candidate.events.count('host_closed') == 1
        assert candidate.events[-2:] == ['broker_closed', 'host_closed']
    if existing:
        assert [p.name for p in root.iterdir()] == ['keep']
        assert (root / 'keep').read_bytes() == b'previous ledger state'
    else:
        assert not root.exists()
    assert_closed(runtime.Core())
    assert all(vars(candidate.activate().pv20_switches).values())


@pytest.mark.parametrize('part', ['win32', 'origin_api', 'jobs', 'start_host'])
def test_native_build_failure_rolls_back(candidate, part):
    def fail(*args, **kw):
        raise OSError('backend unavailable')

    bindings = replace(candidate.args['bindings'], **{part: fail})
    reason = 'build_failed' if part == 'start_host' else 'backend_unavailable'
    with pytest.raises(pv20.ActivationRefused, match=reason):
        candidate.activate(bindings=bindings)
    assert not candidate.args['ledger_dir'].exists()
    assert 'host_started' not in candidate.events
    assert_closed(runtime.Core())


@pytest.mark.parametrize('ready', [False, None, 1])
def test_watchdog_must_be_ready(candidate, monkeypatch, ready):
    monkeypatch.setattr(RunningHost, 'ready', lambda self: ready)
    with pytest.raises(pv20.ActivationRefused, match='watchdog_unavailable'):
        candidate.activate()
    assert candidate.events == ['host_started', 'broker_closed', 'host_closed']
    assert not candidate.args['ledger_dir'].exists()
    assert_closed(runtime.Core())


def test_boundary_must_be_available(candidate, monkeypatch):
    monkeypatch.setattr(pv20.mxc_boundary.MxcBoundary, 'available', lambda self: False)
    with pytest.raises(pv20.ActivationRefused, match='boundary_unavailable'):
        candidate.activate()
    assert candidate.events == ['host_started', 'broker_closed', 'host_closed']
    assert not candidate.args['ledger_dir'].exists()


def test_twice_refused_even_after_close(candidate):
    core = candidate.activate()
    with pytest.raises(pv20.ActivationRefused, match='already_activated'):
        candidate.activate()
    assert candidate.events == ['host_started']
    core.stop()
    with pytest.raises(pv20.ActivationRefused, match='already_activated'):
        candidate.activate()
    assert candidate.events == ['host_started', 'broker_closed', 'host_closed']


def test_switch_bundle_cannot_be_partial_or_mutated():
    assert not any(vars(Pv20Switches()).values())
    with pytest.raises(ValueError):
        Pv20Switches(broker_dispatch=True)
    with pytest.raises(ValueError):
        Pv20Switches(origin_enforcement=1)
    with pytest.raises(FrozenInstanceError):
        Pv20Switches().host = True


def test_native_backend_receives_constructor_switch(candidate):
    core = candidate.activate()
    boundary = core.pv20.node.isolation.boundary
    backend = mxc_native.Backend(boundary.win32, boundary, boundary.schema_validator,
                                 switches=core.pv20_switches)
    assert backend.switches is core.pv20_switches
    assert backend.switches.native_run is True
    assert mxc.NativeMxc(None, None).switches is None


def test_native_launch_uses_switch_without_global_flip(candidate, tmp_path):
    core = candidate.activate()
    boundary = core.pv20.node.isolation.boundary
    work = tmp_path / 'workspace'
    work.mkdir()
    eid = new_execution_id()
    identity = boundary.create_profile(eid)
    assert boundary.grant_established(str(work), identity['sid'], 'rw') is True
    launch = boundary._launch(
        ['cmd.exe'], str(work), {'SYSTEMROOT': 'C:\\Windows', 'LOCALAPPDATA': str(work)},
        identity['profile'], 5000)
    assert launch.backend.switches is core.pv20_switches
    policy = launch.policy

    class Reached(Exception):
        pass

    def reached(raw):
        raise Reached()

    transport = SimpleNamespace(stage_policy=reached)
    native = mxc.NativeMxc(transport, lambda raw: True, switches=core.pv20_switches)
    with pytest.raises(Reached):
        native.spawn(policy, exe='C:\\fixture\\wxc-exec.exe', job=1)
    with pytest.raises(mxc.MxcUnavailable, match='native MXC execution disabled'):
        mxc.NativeMxc(transport, lambda raw: True).spawn(
            policy, exe='C:\\fixture\\wxc-exec.exe', job=1)
    assert_closed()


def test_store_fetch_uses_explicit_switch(candidate):
    core = candidate.activate()
    args = ('project', 'relative', 'HEAD', '0' * 40, 'refs/archeus/fixture')
    with pytest.raises(local.StoreError, match='not a fetch Core may make'):
        core.pv20.node.store_fetch(*args, workdirs=(), switches=core.pv20_switches)
    with pytest.raises(local.StoreError, match='no fetch into a store'):
        local.LocalNode.store_fetch(*args, workdirs=())


def test_a4_requires_admission_and_invariant(candidate, tmp_path):
    core = candidate.activate()
    authority = core.pv20.node.isolation
    request = make_satisfying_request(new_execution_id(), str(tmp_path / 'layout'))
    with pytest.raises(isolation.IsolationUnavailable, match='a4_unmet.*production_dispatch'):
        authority.establish(request)
    assert authority.record(request.execution_id).state == 'failed'
    request = make_satisfying_request(new_execution_id(), str(tmp_path / 'other-layout'))
    assert authority.requested(request.execution_id, SimpleNamespace(id='claude_code')) is True
    assert authority.establish(request).state == 'established'
    authority.teardown(request.execution_id, reason='test ended')


def test_authorization_refusal_has_no_ordinary_fallback(candidate):
    core = candidate.activate(authorize=lambda eid, adapter: False)
    with pytest.raises(isolation.IsolationUnavailable, match='authorization_refused'):
        core.pv20.node.isolation.requested(new_execution_id(), SimpleNamespace(id='claude_code'))


@pytest.mark.parametrize('state', ['FIRED', 'UNCERTAIN', 'ARMED', 'STOOD_DOWN'])
def test_watchdog_initial_state_must_be_idle(candidate, monkeypatch, state):
    tick = mxc_watchdog_host.WatchdogHost.tick

    def changed(self):
        tick(self)
        status = self.channel.read_status()
        self.channel.write_status(dict(status, state=state))

    monkeypatch.setattr(mxc_watchdog_host.WatchdogHost, 'tick', changed)
    with pytest.raises(pv20.ActivationRefused, match='watchdog_unavailable'):
        candidate.activate()
    assert candidate.events == ['host_started', 'broker_closed', 'host_closed']
    assert not candidate.args['ledger_dir'].exists()


def test_unreadable_status_rolls_back(candidate, monkeypatch):
    monkeypatch.setattr(mxc_heartbeat.Channel, 'read_status', lambda self: None)
    with pytest.raises(pv20.ActivationRefused, match='build_failed'):
        candidate.activate()
    assert candidate.events == ['host_started', 'broker_closed', 'host_closed']
    assert not candidate.args['ledger_dir'].exists()


def test_concurrent_activation_has_one_winner(candidate):
    def activate():
        try:
            return candidate.activate()
        except pv20.ActivationRefused as error:
            return error.reason

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: activate(), range(2)))
    assert sum(isinstance(result, runtime.Core) for result in results) == 1
    assert results.count('already_activated') == 1
    assert candidate.events == ['host_started']


def test_unsupported_harness_refuses(candidate):
    core = candidate.activate()
    with pytest.raises(isolation.IsolationUnavailable, match='unsupported_harness'):
        core.pv20.node.isolation.requested(new_execution_id(), SimpleNamespace(id='codex'))


def test_production_never_reaches_activation():
    root = Path(runtime.__file__).resolve().parents[1]
    for path in root.rglob('*.py'):
        if path == Path(pv20.__file__).resolve():
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            imported, used = [], []
            if isinstance(node, ast.ImportFrom):
                imported = [node.module or ''] + [alias.name for alias in node.names]
            elif isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.Name):
                used = [node.id]
            elif isinstance(node, ast.Attribute):
                used = [node.attr]
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                used = [node.value]
            assert not [name for name in imported
                        if name in ('pv20', 'activate_pv20') or name.endswith('.pv20')], (
                path, node.lineno)
            assert not [name for name in used
                        if name == 'activate_pv20' or name.endswith('core.pv20')], (
                path, node.lineno)


def test_host_entry_point_follows_the_switch_object(candidate, tmp_path, monkeypatch):
    core = candidate.activate()
    host = core.pv20.host
    parts = {'clock': host.clock, 'identity_reader': host.identity_reader,
             'terminate': host.terminate, 'engage_sentinel': host.engage_sentinel}
    argv = ['--root', str(tmp_path / 'chan'), '--ledger', str(tmp_path / 'ledger'),
            '--core-pid', '900', '--core-create-time', '9000', '--deadline-s', '5',
            '--poll-s', '0.1']
    assert mxc_watchdog_host.HOST_ENABLED is False
    assert mxc_watchdog_host.main(argv, bindings=dict(parts, switches=Pv20Switches())) == 2
    assert mxc_watchdog_host.main(argv, bindings=parts) == 2
    assert not (tmp_path / 'chan').exists()
    monkeypatch.setattr(mxc_watchdog_host.WatchdogHost, 'run',
                        lambda self, poll_s: {'state': 'IDLE'})
    assert mxc_watchdog_host.main(
        argv, bindings=dict(parts, switches=core.pv20_switches)) == 0


def test_an_interrupt_during_the_build_tears_everything_down(candidate, monkeypatch):
    class Stop(BaseException):
        pass

    def interrupted(*args, **kw):
        raise Stop

    with monkeypatch.context() as patch:
        patch.setattr(pv20.mxc_boundary, 'MxcBoundary', interrupted)
        with pytest.raises(Stop):
            candidate.activate()
    assert candidate.events == ['host_started', 'broker_closed', 'host_closed']
    assert not candidate.args['ledger_dir'].exists()
    assert all(vars(candidate.activate().pv20_switches).values())


def test_rollback_keeps_files_the_build_left_in_the_ledger_dir(candidate, monkeypatch):
    root = candidate.args['ledger_dir']

    def leaves_a_file(*args, **kw):
        (root / 'stray').write_bytes(b'left')
        raise RuntimeError('injected build failure')

    monkeypatch.setattr(pv20.local, 'LocalNode', leaves_a_file)
    with pytest.raises(pv20.ActivationRefused, match='build_failed'):
        candidate.activate()
    assert [p.name for p in root.iterdir()] == ['stray']


def test_a_closed_activation_cannot_start_a_core(candidate, quiet_core):
    core = candidate.activate()
    core.pv20.close()
    with pytest.raises(runtime.RefuseStart, match='PV-20 activation is closed'):
        core.start()
    assert core.db is None and core.loop is None and core.lock is None


def test_the_bundle_takes_only_booleans():
    with pytest.raises(ValueError):
        Pv20Switches(*[1] * 10)


@pytest.mark.parametrize('opened', [True, False])
def test_heartbeat_follows_the_switch_object(tmp_path, opened):
    switches = Pv20Switches(*[opened] * 10)
    channel = mxc_heartbeat.Channel(str(tmp_path / 'chan'))
    assert mxc_heartbeat.HEARTBEAT_ENABLED is False
    for build in (lambda: mxc_heartbeat.HeartbeatSender(channel, lambda: 1.0, switches=switches),
                  lambda: mxc_heartbeat.WatchdogProxy(channel, lambda: 1.0, max_age_s=2.0,
                                                      switches=switches)):
        if opened:
            build()
        else:
            with pytest.raises(mxc_watchdog.WatchdogUnavailable):
                build()


@pytest.mark.parametrize('opened', [True, False])
def test_the_router_gate_follows_the_switch_object(monkeypatch, opened):
    seen = {}
    monkeypatch.setattr(resources, 'current_authorization', lambda *args: None)
    monkeypatch.setattr(resources, 'task_snapshot', lambda conn, **kw: (
        {}, {'isolated_dispatch': {'broker': {'claude_code': ['subscription_oauth']}}}, {}))
    monkeypatch.setattr(resources.R, 'route', lambda req, snap: seen.update(snap=snap))
    monkeypatch.setattr(resources, 'record_route',
                        lambda *args, **kw: SimpleNamespace(entity=None))
    router = resources.ResourceRouter(
        SimpleNamespace(ids=lambda: []), None, switches=Pv20Switches(*[opened] * 10))
    router.route('subject', 'now', tx=SimpleNamespace(conn=None), actor=None,
                 authorization=None, plan=None, task=None,
                 mission=SimpleNamespace(id='m', workspace_id=None, project_id=None))
    gate = seen['snap'].get('isolated_dispatch')
    assert gate == ({'broker': {h: list(k) for h, k in broker_eligible.items()}}
                    if opened else None)


@pytest.mark.parametrize('opened', [True, False])
def test_the_manager_grants_by_the_switch_object_not_the_global(monkeypatch, tmp_path, opened):
    manager, e, mission, adapter, log = _spawn_rig(monkeypatch, tmp_path, True)
    manager.broker = Spy()
    manager.switches = Pv20Switches(*[opened] * 10)
    e.harness_id, e.account_id, e.route_decision_id, e.model = (
        'claude_code', 'acc_1', 'rte_1', 'claude-x')
    get = manager_mod.rows.get

    def rows_get(r, k, i):
        if k is entities.Account:
            return SimpleNamespace(entity=SimpleNamespace(auth_kind='api_key', home_ref=None))
        return get(r, k, i)

    monkeypatch.setattr(manager_mod.rows, 'get', rows_get)
    assert broker.BROKER_DISPATCH_ENABLED is False
    assert manager._spawn(e, mission) is True
    assert [call[0] for call in manager.broker.calls] == (['issue'] if opened else [])


@pytest.mark.parametrize('opened', [True, False])
def test_confined_verification_follows_the_switch_object(db, monkeypatch, opened):
    actor = who('system')
    switches = Pv20Switches(*[opened] * 10)
    w = _seed(db, actor, execution={'isolated': True, 'import_revision': IMP})
    start = dict(missions=Missions(), subject=Ref('task', w['tid']), verifier='code',
                 execution_id=w['eid'], revision=IMP, switches=switches)
    if opened:
        assert _do(db, verification.start, actor=actor, **start)['state'] == 'RUNNING'
    else:
        with pytest.raises(verification.Refused, match='verification withheld'):
            _do(db, verification.start, actor=actor, **start)
    monkeypatch.setattr(verification, 'CONFINED_VERIFICATION_ENABLED', True)
    w = _seed(db, actor, execution={'isolated': True, 'import_revision': IMP})
    vid = _errored(db, actor, w, revision=IMP)
    monkeypatch.setattr(verification, 'CONFINED_VERIFICATION_ENABLED', not opened)
    retry = dict(verification_id=vid, switches=switches)
    if opened:
        assert _do(db, verification.retry, actor=actor, **retry)['state'] == 'RUNNING'
    else:
        with pytest.raises(verification.Refused, match='is not retried'):
            _do(db, verification.retry, actor=actor, **retry)


@pytest.mark.parametrize('opened', [True, False])
def test_the_verify_worker_routes_by_the_switch_object(opened):
    class Reached(Exception):
        pass

    def read():
        raise Reached

    worker = VerifyWorker(SimpleNamespace(read=read), actor=None, missions=None,
                          switches=Pv20Switches(*[opened] * 10))
    task = SimpleNamespace(kind=next(iter(evidence.CODE_KINDS)),
                           acceptance=[{'check': 'automatic'}])
    execution = SimpleNamespace(import_revision='rev')
    assert verification.CONFINED_VERIFICATION_ENABLED is False
    if opened:
        with pytest.raises(Reached):
            worker._confined_route(None, task, execution)
    else:
        assert worker._confined_route(None, task, execution) is None


def test_a_verifier_launch_is_not_judged_as_a_harness_dispatch(candidate, monkeypatch, tmp_path):
    authority = candidate.activate().pv20.node.isolation
    monkeypatch.setattr(isolation, 'check_invariant', lambda *args: {name: (True, 'held') for name in isolation.CONDITIONS})
    key = isolation.Principal('verify', ids.new_id('verification'), 0).key
    request = make_satisfying_request(key, str(tmp_path / 'verifier'))
    assert request.kind == 'verify'
    assert authority.establish(request).state == 'established'
    authority.teardown(key, reason='test ended')


def handed_on(module, matches):
    tree = ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
    return [ast.unparse(kw.value) for node in ast.walk(tree)
            if isinstance(node, ast.Call) and matches(node)
            for kw in node.keywords if kw.arg in ('switches', None)]


def test_callers_hand_the_switch_object_on():
    def command(name):
        return lambda node: bool(node.args) and ast.unparse(node.args[0]) == name

    assert handed_on(manager_mod, lambda node: isinstance(node.func, ast.Attribute)
                     and node.func.attr == 'store_fetch') == ['fetch_options']
    assert handed_on(worker_mod, command('V.start')) == ['self._switch']
    assert handed_on(worker_mod, command('V.retry')) == ['self._switch'] * 2


def test_a_resume_after_a_restart_is_still_a_harness_dispatch(candidate, tmp_path):
    core = candidate.activate()
    first = core.pv20.node.isolation
    request = make_satisfying_request(new_execution_id(), str(tmp_path / 'layout'))
    adapter = SimpleNamespace(id='claude_code')
    assert first.requested(request.execution_id, adapter) is True
    assert first.establish(request).state == 'established'
    restarted = isolation.Isolation(
        core.pv20.node, boundary=first.boundary, authorize=lambda eid, adapter: True,
        plan=lambda spec: None, switches=core.pv20_switches)
    assert restarted.requested(request.execution_id, adapter) is True
    assert restarted.establish(request).state == 'established'
    restarted.teardown(request.execution_id, reason='test ended')


def test_a_lock_failure_in_start_tears_the_activation_down(candidate, monkeypatch):
    core = candidate.activate()

    def held(*args):
        raise RuntimeError('lock held')

    monkeypatch.setattr(runtime.discovery, 'acquire', held)
    with pytest.raises(RuntimeError, match='lock held'):
        core.start()
    assert core.pv20.closed is True
    assert candidate.events == ['host_started', 'broker_closed', 'host_closed']


def test_stop_finishes_the_core_when_a_part_will_not_close(candidate, quiet_core, monkeypatch):
    def stuck(self):
        raise OSError('host will not close')

    monkeypatch.setattr(RunningHost, 'close', stuck)
    core = candidate.activate()
    core.start()
    with pytest.raises(OSError, match='host will not close'):
        core.stop()
    assert core.db is None and core.lock is None and core.pv20.closed is True
    assert candidate.events[-1] == 'broker_closed'


@pytest.mark.parametrize('refusal', [False, True])
def test_a_close_error_does_not_replace_the_rollback_reason(candidate, monkeypatch, refusal):
    def stuck(self):
        raise OSError('host will not close')

    monkeypatch.setattr(RunningHost, 'close', stuck)
    if refusal:
        monkeypatch.setattr(pv20.mxc_boundary.MxcBoundary, 'available', lambda self: False)
        reason = 'boundary_unavailable'
    else:
        monkeypatch.setattr(pv20.mxc_boundary, 'MxcBoundary', lambda **kw: 1 / 0)
        reason = 'build_failed'
    with pytest.raises(pv20.ActivationRefused, match=reason):
        candidate.activate()
    assert candidate.events == ['host_started', 'broker_closed']


def test_the_same_port_cannot_be_activated_from_another_ledger_dir(candidate, tmp_path):
    candidate.activate()
    with pytest.raises(pv20.ActivationRefused, match='already_activated'):
        candidate.activate(ledger_dir=tmp_path / 'other-ledger')
    assert not (tmp_path / 'other-ledger').exists()
    assert candidate.events == ['host_started']


def test_the_same_ledger_dir_cannot_be_activated_on_another_port(candidate):
    candidate.activate()
    with pytest.raises(pv20.ActivationRefused, match='already_activated'):
        candidate.activate(core_port=7338)


@pytest.mark.parametrize('build', [
    lambda s: mxc_heartbeat.HeartbeatSender(None, None, switches=s),
    lambda s: mxc_heartbeat.WatchdogProxy(None, None, max_age_s=1.0, switches=s),
    lambda s: mxc.NativeMxc(None, None, switches=s),
    lambda s: resources.ResourceRouter(None, None, switches=s),
    lambda s: VerifyWorker(None, actor=None, missions=None, switches=s),
    lambda s: isolation.Isolation(switches=s),
    lambda s: mxc_boundary.MxcBoundary(switches=s),
    lambda s: manager_mod.ExecutionManager(
        None, actor=None, registry=None, node=SimpleNamespace(),
        work=SimpleNamespace(policy=None, missions=None, router=None), switches=s),
    lambda s: local.LocalNode(switches=s),
], ids=['sender', 'proxy', 'native', 'router', 'worker', 'isolation', 'boundary', 'manager',
         'node'])
def test_a_constructor_takes_only_the_real_bundle(build):
    duck = SimpleNamespace(**{name: True for name in vars(Pv20Switches())})
    with pytest.raises(TypeError, match='Pv20Switches'):
        build(duck)


def test_closing_keeps_a_ledger_dir_that_holds_journals(candidate):
    core = candidate.activate()
    root = candidate.args['ledger_dir']
    (root / 'journal.jsonl').write_bytes(b'{}')
    core.stop()
    assert [p.name for p in root.iterdir()] == ['journal.jsonl']


def _dispatcher(events, broker_, then=None):
    """A stand-in dispatch worker: signalled to stop, it finishes the step in flight."""
    class Dispatch:
        def __init__(self):
            self._stop = threading.Event()
            self._thread = threading.Thread(target=self.run)
            self._thread.start()

        def run(self):
            self._stop.wait()
            time.sleep(0.3)
            events.append('dispatch_done')
            if then:
                then(broker_)

        def stop(self):
            self._stop.set()

        def join(self, timeout):
            self._thread.join(timeout)

    return Dispatch()


def test_stop_joins_the_dispatch_workers_before_the_activation_closes(candidate, quiet_core):
    core = candidate.activate()
    core.start()
    core.exec = _dispatcher(candidate.events, core.pv20.broker)
    core.verify = _dispatcher(candidate.events, core.pv20.broker)
    core.stop()
    assert candidate.events == ['host_started', 'broker_closed', 'dispatch_done',
                                'dispatch_done', 'host_closed']


def test_a_core_without_an_activation_does_not_wait_for_its_workers(quiet_core, monkeypatch):
    monkeypatch.setattr(runtime.discovery, 'acquire', lambda s: SimpleNamespace(release=lambda: None))
    monkeypatch.setattr(runtime.discovery, 'remove_core_json', lambda: None)
    core = runtime.Core()
    core.exec = SimpleNamespace(stop=lambda: None, join=lambda t: pytest.fail('joined'))
    core.stop()


def test_no_listener_is_bound_after_the_activation_closed(candidate, quiet_core):
    core = candidate.activate()
    core.start()
    held = core.pv20.broker
    created = []
    held.transport.create = lambda *a: created.append(a)
    core.stop()
    with pytest.raises(broker.BrokerUnavailable, match='closed'):
        held.issue(binding(core_instance='fixture'))
    assert created == []


def test_a_held_workload_is_disposed_after_the_grants_and_before_the_watchdog(
        candidate, quiet_core, monkeypatch):
    core = candidate.activate()
    core.start()
    isolation_ = core.pv20.node.isolation
    monkeypatch.setattr(isolation_, 'held_jobs', lambda: {'exe_a': object(), 'exe_b': object()})
    monkeypatch.setattr(isolation_, 'teardown', lambda *a, **k: pytest.fail('torn down'))
    monkeypatch.setattr(isolation_, 'fence', lambda eid, wait=None: candidate.events.append(
        'fence %s %s' % (eid, wait)))
    core.stop()
    assert candidate.events == ['host_started', 'broker_closed', 'fence exe_a 0',
                                'fence exe_b 0', 'host_closed']


def test_a_workload_that_will_not_go_does_not_keep_the_rest_or_the_watchdog_open(
        candidate, quiet_core, monkeypatch):
    core = candidate.activate()
    core.start()
    isolation_ = core.pv20.node.isolation
    monkeypatch.setattr(isolation_, 'held_jobs', lambda: {'exe_a': object(), 'exe_b': object()})

    def fence(eid, wait):
        candidate.events.append('fence ' + eid)
        if eid == 'exe_a':
            raise OSError('job will not close')

    monkeypatch.setattr(isolation_, 'fence', fence)
    with pytest.raises(OSError, match='job will not close'):
        core.stop()
    assert core.db is None and core.lock is None
    assert candidate.events[1:] == ['broker_closed', 'fence exe_a', 'fence exe_b', 'host_closed']


# ── fx16: the review of fx15 (S2-S4) and Codex #2 ──

class _Stuck:
    """A worker whose step in flight outlives any join."""

    def __init__(self):
        self.waited = []

    def stop(self):
        pass

    def join(self, timeout):
        self.waited.append(timeout)
        time.sleep(timeout)
        return True


def test_the_workers_share_one_quiesce_deadline_and_a_late_one_is_reported(
        candidate, quiet_core, monkeypatch, caplog):
    monkeypatch.setattr(runtime, 'QUIESCE_S', 0.4)
    core = candidate.activate()
    core.start()
    core.exec, core.verify, core.loop = _Stuck(), _Stuck(), _Stuck()
    started = time.monotonic()
    core.stop()
    assert time.monotonic() - started < 0.9
    assert sum(w.waited[0] for w in (core.exec, core.verify, core.loop)) < 0.6
    assert caplog.text.count('did not stop') == 3


def test_stop_closes_admission_before_it_joins_and_the_workloads_after(
        candidate, quiet_core, monkeypatch):
    core = candidate.activate()
    core.start()
    isolation_ = core.pv20.node.isolation
    monkeypatch.setattr(isolation_, 'held_jobs', lambda: {'exe_a': object()})
    monkeypatch.setattr(isolation_, 'fence',
                        lambda eid, wait: candidate.events.append('fence ' + eid))
    seen = []
    core.exec = _dispatcher(candidate.events, core.pv20.broker,
                            then=lambda b: seen.append(isolation_.closed))
    core.stop()
    assert seen == [True]
    assert candidate.events == ['host_started', 'broker_closed', 'dispatch_done',
                                'fence exe_a', 'host_closed']


def test_a_broker_that_will_not_close_does_not_stop_the_stop_short(
        candidate, quiet_core, monkeypatch):
    def stuck(self):
        raise OSError('broker will not close')

    core = candidate.activate()
    core.start()
    with monkeypatch.context() as patch:
        patch.setattr(broker.Broker, 'close', stuck)
        with pytest.raises(OSError, match='broker will not close'):
            core.stop()
    assert core.pv20.node.isolation.closed is True and core.db is None
    assert candidate.events[-1] == 'host_closed'


def test_a_late_worker_can_create_no_job_once_core_is_stopping(candidate, quiet_core, tmp_path):
    core = candidate.activate()
    authority = core.pv20.node.isolation
    request = make_satisfying_request(new_execution_id(), str(tmp_path / 'layout'))
    assert authority.requested(request.execution_id, SimpleNamespace(id='claude_code')) is True
    core.pv20.quiesce()
    with pytest.raises(isolation.IsolationClosed):
        authority.establish(request)
    with pytest.raises(isolation.IsolationClosed):
        authority._ensure_job(request.execution_id)
    assert authority.record(request.execution_id) is None and authority.held_jobs() == {}


def test_a_stop_closes_the_job_of_a_live_execution_and_keeps_the_record_it_resumes_from(
        candidate, quiet_core, tmp_path):
    core = candidate.activate()
    core.start()
    first = core.pv20.node.isolation
    request = make_satisfying_request(new_execution_id(), str(tmp_path / 'layout'))
    adapter = SimpleNamespace(id='claude_code')
    assert first.requested(request.execution_id, adapter) is True
    sid = first.establish(request).sid
    job = first.held_job(request.execution_id)
    core.stop()
    assert first.held_jobs() == {} and first.boundary.jobs.closed == [job]
    # the next Core: the manager resumes an isolated execution only while its record
    # exists, and the authority only under the identity that record names
    pv20._claimed.clear()                       # a restart is another process
    after = candidate.activate().pv20.node.isolation
    rec = after.record(request.execution_id)
    assert (rec.state, rec.failure, rec.owned, rec.sid) == ('established', '', True, sid)
    assert after.requested(request.execution_id, adapter) is True
    assert after.establish(request).sid == sid
