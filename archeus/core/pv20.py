import errno
import logging
import os
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass

from ..api import origin
from ..node import broker_listener, isolation, local, mxc_boundary, mxc_heartbeat
from ..node import mxc_ledger, mxc_watchdog_host, origin_native, staging
from ..node.origin_windows import WindowsOriginBackend
from ..node.pv20_switches import Pv20Switches
from ..node.win32_mxc import Win32Api

log = logging.getLogger(__name__)

_lock = threading.Lock()
_claimed = set()


class ActivationRefused(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class NativeBindings:
    """start_host owns a separate host process and returns ready()/close(); close joins
    its exit. A constructor that raises must release its own partial native resources.
    """
    identity_reader: object
    terminate: object
    engage_sentinel: object
    start_host: object
    win32: object = Win32Api
    origin_api: object = origin_native.Win32OriginApi
    jobs: object = None


class Activation:
    """Core.stop calls quiesce(), joins the workers that admit work, then close(). close()
    ends it in the order its parts were registered, last first: the broker (every grant
    revoked, no new one issued), the Jobs Core still holds, then the watchdog host and
    the private directory."""

    def __init__(self, *, switches, node, broker, host, backend, registry, resources):
        self.switches, self.node, self.broker = switches, node, broker
        self.host, self.backend, self.registry = host, backend, registry
        self.resources = resources
        self.closed = False

    def quiesce(self):
        """Admit nothing new while the workers finish: no grant is issued (one being
        issued is dropped before this returns), no identity established, no Job created."""
        try:
            self.broker.close()
        finally:
            self.node.isolation.close_admission()

    def close(self):
        self.closed = True
        self.resources.close()


def _dispose(node):
    """Every Job Core still holds, closed by Core (kill-on-close) and not left to the
    watchdog that goes next; one that will not close does not keep the others. The
    identity and its record stay (owner decision 117): an execution paused when Core
    stops resumes under them after a restart, and the next Core's sweep reclaims those
    of an execution that is no longer live."""
    if node is None:
        return
    first = None
    for execution_id in node.isolation.held_jobs():
        try:
            node.isolation.fence(execution_id, wait=0)
        except Exception as error:
            log.exception('PV-20 close could not close the Job of %s', execution_id)
            first = first or error
    if first is not None:
        raise first


def _rollback(resources):
    try:
        resources.close()
    except Exception:
        log.exception('PV-20 rollback could not close a part')


def _remove_empty(root):
    try:
        os.rmdir(root)
    except OSError as error:
        if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
            raise


def activate_pv20(*, ledger_dir, sdk_root, authorize, plan, bindings=None,
                  broker_options, principal_of, core_port, core_identity,
                  enabled=False, ports=None, clock=time.monotonic, deadline_s=15.0,
                  poll_s=0.2, max_age_s=2.0, timeout_ms=None, env_rows=None,
                  resource_reader=None, readback=None):
    if enabled is not True:
        raise ActivationRefused('activation_closed')
    if sys.platform != 'win32':
        raise ActivationRefused('windows_required')
    if bindings is None or not all(callable(part) for part in (
            bindings.identity_reader, bindings.terminate, bindings.engage_sentinel,
            bindings.start_host, bindings.win32, bindings.origin_api, authorize, plan,
            principal_of)):
        raise ActivationRefused('backend_unavailable')
    if not (type(core_port) is int and 0 < core_port < 65536
            and isinstance(core_identity, (tuple, list)) and len(core_identity) == 2
            and all(type(n) is int and n > 0 for n in core_identity)
            and all(type(n) in (int, float) and 0 < n < float('inf')
                    for n in (deadline_s, poll_s, max_age_s))):
        raise ActivationRefused('invalid_parameters')
    try:
        root = os.path.normcase(os.path.realpath(ledger_dir))
    except (TypeError, ValueError, OSError) as error:
        raise ActivationRefused('invalid_parameters') from error
    node = None
    with _lock:
        claims = {('ledger', root), ('port', core_port)}
        if claims & _claimed:
            raise ActivationRefused('already_activated')
        resources = ExitStack()
        try:
            pins = staging.mxc_sdk_pins()
            staging.verify_mxc(sdk_root, pins=pins)
            validator = staging.mxc_schema_validator(sdk_root)
            if not os.path.exists(root):
                os.mkdir(root)
                resources.callback(_remove_empty, root)
            ledger = mxc_ledger.Ledger(root)
            private = resources.enter_context(tempfile.TemporaryDirectory(dir=root))
            try:
                api = bindings.win32(private)
                native_origin = bindings.origin_api()
                jobs = bindings.jobs() if bindings.jobs is not None else isolation.WindowsBoundary()
            except Exception as error:
                raise ActivationRefused('backend_unavailable') from error
            switches = Pv20Switches(
                origin_enforcement=True, production_dispatch=True, confined_verification=True,
                native_run=True, heartbeat=True, host=True, broker_dispatch=True,
                a4=True, store_fetch=True, isolated_dispatch=True)

            def backend_of(port):
                readers = origin_native.native_readers(
                    native_origin, core_port=port,
                    jobs=lambda: node.isolation.held_jobs().values(),
                    clock=clock, max_age_s=max_age_s, reattest=True)
                return WindowsOriginBackend(readers=readers)

            backend = backend_of(core_port)
            registry = origin.CorePathRegistry((core_port,))
            broker = broker_listener.loopback_broker(
                backend_of=backend_of, principal_of=principal_of, **broker_options)
            channel = mxc_heartbeat.Channel(os.path.join(private, 'heartbeat'))
            host = mxc_watchdog_host.WatchdogHost(
                channel=mxc_heartbeat.Channel(channel.root), clock=clock,
                deadline_s=deadline_s, core=core_identity,
                identity_reader=bindings.identity_reader, terminate=bindings.terminate,
                engage_sentinel=bindings.engage_sentinel, journals=ledger.journals)
            running = bindings.start_host(host, poll_s=poll_s)
            resources.callback(running.close)
            resources.callback(lambda: _dispose(node))
            resources.callback(broker.close)
            if running.ready() is not True:
                raise ActivationRefused('watchdog_unavailable')
            sender = mxc_heartbeat.HeartbeatSender(channel, clock, switches=switches)
            proxy = mxc_heartbeat.WatchdogProxy(
                channel, clock, max_age_s=max_age_s, switches=switches)
            if proxy._status()['state'] != 'IDLE':
                raise ActivationRefused('watchdog_unavailable')
            boundary = mxc_boundary.MxcBoundary(
                win32=api, ledger=ledger, sdk_root=sdk_root, pins=pins, jobs=jobs,
                schema_validator=validator, broker=broker, watchdog=proxy,
                process_reader=bindings.identity_reader, resource_reader=resource_reader,
                readback=readback, timeout_ms=timeout_ms, env_rows=env_rows, switches=switches)
            if boundary.available() is not True:
                raise ActivationRefused('boundary_unavailable')
            node = local.LocalNode(boundary=boundary, authorize=authorize, plan=plan,
                                   heartbeat=sender, switches=switches)
            activation = Activation(switches=switches, node=node, broker=broker,
                                    host=host, backend=backend, registry=registry,
                                    resources=resources)
            from .runtime import Core
            core = Core(port=core_port, ports=ports, pv20=activation)
            _claimed.update(claims)
            return core
        except ActivationRefused:
            _rollback(resources)
            raise
        except Exception as error:
            _rollback(resources)
            raise ActivationRefused('build_failed') from error
        except BaseException:
            _rollback(resources)
            raise
