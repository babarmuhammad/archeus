"""The PV20 B12 mutation suite: break each branch of the composition root `activate_pv20`, the
switch bundle and the sites that read the bundle, run the test written for it, and require it
to fail.

    py tools/mutate_pv20_activate.py                 every mutation
    py tools/mutate_pv20_activate.py PA01 PA10       only these

It edits archeus/core/pv20.py and the files the bundle reaches, and restores them whatever
happens: run it with nothing else against the tree.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mutate_p18  # noqa: E402

PV = 'archeus/core/pv20.py'
SW = 'archeus/node/pv20_switches.py'
RT = 'archeus/core/runtime.py'
ENGINE = 'archeus/core/engine.py'
MGR = 'archeus/core/execution/manager.py'
ISO = 'archeus/node/isolation.py'
LOCAL = 'archeus/node/local.py'
MXC = 'archeus/node/mxc.py'
NATIVE = 'archeus/node/mxc_native.py'
BOUNDARY = 'archeus/node/mxc_boundary.py'
HOST = 'archeus/node/mxc_watchdog_host.py'
LISTENER = 'archeus/node/broker_listener.py'
VER = 'archeus/core/application/verification.py'
WORKER = 'archeus/core/verification/worker.py'
RES = 'archeus/core/application/resources.py'
T = 'tests/v1/unit/test_pv20_activate.py::'

BINDS = T + 'test_production_core_binds_every_switch'
REFUSAL = T + 'test_refusal_changes_nothing'
ROLLBACK = T + 'test_each_build_failure_rolls_back'
READY = T + 'test_watchdog_must_be_ready'
IDLE = T + 'test_watchdog_initial_state_must_be_idle'
TWICE = T + 'test_twice_refused_even_after_close'
BUNDLE = T + 'test_switch_bundle_cannot_be_partial_or_mutated'
NATIVE_LAUNCH = T + 'test_native_launch_uses_switch_without_global_flip'
STORE = T + 'test_store_fetch_uses_explicit_switch'
A4 = T + 'test_a4_requires_admission_and_invariant'
AUTH = T + 'test_authorization_refusal_has_no_ordinary_fallback'
HARNESS = T + 'test_unsupported_harness_refuses'
HOST_SWITCH = T + 'test_host_entry_point_follows_the_switch_object'
BROKER_GATE = T + 'test_the_manager_grants_by_the_switch_object_not_the_global'
ROUTER_GATE = T + 'test_the_router_gate_follows_the_switch_object'
CONFINED = T + 'test_confined_verification_follows_the_switch_object'
ROUTE = T + 'test_the_verify_worker_routes_by_the_switch_object'
CALLERS = T + 'test_callers_hand_the_switch_object_on'

MUTATIONS = [
    ('PA01', 'activation proceeds without the explicit enable', [(PV,
     "    if enabled is not True:\n", "    if False:\n")], [T + 'test_default_call_is_closed']),
    ('PA02', 'activation proceeds off Windows', [(PV,
     "    if sys.platform != 'win32':", "    if False:")],
     [T + 'test_non_windows_refuses_before_building']),
    ('PA03', 'missing native bindings are not refused up front', [(PV,
     "    if bindings is None or not all(", "    if not all(")], [REFUSAL]),
    ('PA04', 'a non-callable part is not refused up front', [(PV,
     "callable(part) for part in (", "True for part in (")], [REFUSAL]),
    ('PA05', 'the Core port is not bounded', [(PV,
     " and 0 < core_port < 65536", "")], [REFUSAL]),
    ('PA06', 'a Core identity with a zero part is accepted', [(PV,
     "            and all(type(n) is int and n > 0 for n in core_identity)\n",
     "")], [REFUSAL]),
    ('PA07', 'a non-finite time bound is accepted', [(PV,
     "type(n) in (int, float) and 0 < n < float('inf')", "type(n) in (int, float)")],
     [REFUSAL]),
    ('PA08', 'the second activation of a ledger dir is not refused', [(PV,
     "        if root in _claimed:", "        if False:")], [TWICE]),
    ('PA09', 'a successful activation is not recorded as claimed', [(PV,
     "            _claimed.add(root)", "            pass")], [TWICE]),
    ('PA10', 'a ledger dir the build made is left behind', [(PV,
     "                resources.callback(_remove_empty, root)", "                pass")],
     [ROLLBACK]),
    ('PA11', 'rollback fails on a file the build left in the ledger dir', [(PV,
     "        if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):", "        if True:")],
     [T + 'test_rollback_keeps_files_the_build_left_in_the_ledger_dir']),
    ('PA12', 'the private dir outlives a failed build', [(PV,
     "            private = resources.enter_context(tempfile.TemporaryDirectory(dir=root))",
     "            private = tempfile.mkdtemp(dir=root)")], [ROLLBACK]),
    ('PA13', 'the broker is not closed on rollback', [(PV,
     "            resources.callback(broker.close)", "            pass")], [READY]),
    ('PA14', 'the watchdog host is not closed on rollback', [(PV,
     "            resources.callback(running.close)", "            pass")], [READY]),
    ('PA15', 'a host that is not ready is accepted', [(PV,
     "            if running.ready() is not True:", "            if False:")], [READY]),
    ('PA16', 'a watchdog that is not idle is accepted', [(PV,
     "            if proxy._status()['state'] != 'IDLE':", "            if False:")], [IDLE]),
    ('PA17', 'an unavailable boundary is accepted', [(PV,
     "            if boundary.available() is not True:", "            if False:")],
     [T + 'test_boundary_must_be_available']),
    ('PA18', 'a refused activation does not tear down what it started', [(PV,
     "        except ActivationRefused:\n            resources.close()\n            raise",
     "        except ActivationRefused:\n            raise")],
     [T + 'test_boundary_must_be_available']),
    ('PA19', 'a build failure does not tear down what it started', [(PV,
     "        except Exception as error:\n            resources.close()\n",
     "        except Exception as error:\n")], [ROLLBACK]),
    ('PA20', 'an interrupt does not tear down what it started', [(PV,
     "        except BaseException:\n            resources.close()\n            raise",
     "        except BaseException:\n            raise")],
     [T + 'test_an_interrupt_during_the_build_tears_everything_down']),
    ('PA21', 'a native binding that cannot be built is a build failure, not a refusal', [(PV,
     "                raise ActivationRefused('backend_unavailable') from error", "                raise")],
     [T + 'test_native_build_failure_rolls_back']),
    ('PA22', 'the Core is built without the activation', [(PV,
     "Core(port=core_port, ports=ports, pv20=activation)", "Core(port=core_port, ports=ports)")],
     [BINDS]),
    ('PA23', 'the activation never closes its parts', [(PV,
     "        self.closed = True\n        self.resources.close()", "        self.closed = True")],
     [BINDS]),
    ('PA24', 'a closed activation still reports its switches', [(PV,
     "        self.closed = True\n", "")], [BINDS]),
    ('PA25', 'the sender is built without the bundle', [(PV,
     "HeartbeatSender(channel, clock, switches=switches)", "HeartbeatSender(channel, clock)")],
     [BINDS]),
    ('PA26', 'the proxy is built without the bundle', [(PV,
     "max_age_s=max_age_s, switches=switches)", "max_age_s=max_age_s)")], [BINDS]),
    ('PA27', 'the boundary is built without the bundle', [(PV,
     "env_rows=env_rows, switches=switches)", "env_rows=env_rows)")], [BINDS]),
    ('PA28', 'the node is built without the bundle', [(PV,
     "heartbeat=sender, switches=switches)", "heartbeat=sender)")], [BINDS]),
    ('PA29', 'the node is built without Core authorization', [(PV,
     "LocalNode(boundary=boundary, authorize=authorize, plan=plan,",
     "LocalNode(boundary=boundary, plan=plan,")], [A4, AUTH]),
    ('PA30', 'the host is built without the bundle', [(PV,
     "                switches=switches)\n            running", "                )\n            running")],
     [BINDS]),
    ('PA31', 'the broker is not built from its options', [(LISTENER,
     "B.Broker(transport=self, **broker_options)", "None")], [BINDS]),
    ('PS01', 'a partial bundle is accepted', [(SW,
     " or len(set(values)) != 1", "")], [BUNDLE]),
    ('PS02', 'a non-boolean bundle is accepted', [(SW,
     "any(type(value) is not bool for value in values) or ", "")],
     [T + 'test_the_bundle_takes_only_booleans']),
    ('PS03', 'the bundle can be changed after construction', [(SW,
     "@dataclass(frozen=True)", "@dataclass")], [BUNDLE]),
    ('PS04', 'a site without a bundle ignores its own default', [(SW,
     "    return default if switches is None else getattr(switches, name)",
     "    return getattr(switches, name) if switches is not None else False")],
     ['tests/v1/unit/test_mxc_boundary.py']),
    ('PW01', 'a closed activation still reports its switches open', [(RT,
     "        if self.pv20 is None or self.pv20.closed:\n            return Pv20Switches()",
     "        if self.pv20 is None:\n            return Pv20Switches()")], [BINDS]),
    ('PW02', 'a closed activation may start a Core', [(RT,
     "        if self.pv20.closed:\n            raise RefuseStart('PV-20 activation is closed')",
     "        if False:\n            raise RefuseStart('PV-20 activation is closed')")],
     [T + 'test_a_closed_activation_cannot_start_a_core']),
    ('PW03', 'the API origin enforcement is not the bundle\'s', [(RT,
     "{'origin_enforcement_enabled': self.pv20.switches.origin_enforcement,",
     "{'origin_enforcement_enabled': False,")], [BINDS]),
    ('PW04', 'stopping the Core leaves the activation open', [(RT,
     "        if self.pv20 is not None:\n            self.pv20.close()",
     "        if False:\n            self.pv20.close()")], [BINDS]),
    ('PW05', 'the engine builds its manager without the activation node', [(ENGINE,
     "node=pv20.node if pv20 is not None else None,", "node=None,")], [BINDS]),
    ('PW06', 'the engine builds its manager without the broker', [(ENGINE,
     "broker=pv20.broker if pv20 is not None else None,", "broker=None,")], [BINDS]),
    ('PW07', 'the engine builds its manager without the bundle', [(ENGINE,
     "switches=pv20.switches if pv20 is not None else None)", "switches=None)")], [BINDS]),
    ('PW08', 'the router is built without the bundle', [(RT,
     "                                                 switches=self.pv20_switches)),",
     "                                                 switches=None)),")], [BINDS]),
    ('PW09', 'the verify worker is built without the bundle', [(RT,
     "                             switches=self.pv20_switches),", "                             switches=None),")],
     [BINDS]),
    ('PW10', 'the verify worker is built without the node', [(RT,
     "node=self.pv20.node if self.pv20 is not None else None,", "node=None,")], [BINDS]),
    ('PK01', 'the manager brokers by the global flag', [(MGR,
     "        broker_enabled = (self.switches.broker_dispatch if self.switches is not None\n"
     "                          else broker_mod.BROKER_DISPATCH_ENABLED)",
     "        broker_enabled = broker_mod.BROKER_DISPATCH_ENABLED")], [BROKER_GATE]),
    ('PK02', 'the manager brokers whatever the bundle says', [(MGR,
     "        broker_enabled = (self.switches.broker_dispatch if self.switches is not None\n"
     "                          else broker_mod.BROKER_DISPATCH_ENABLED)",
     "        broker_enabled = True")], [BROKER_GATE]),
    ('PK03', 'the manager fetches without the bundle', [(MGR,
     "workdirs=workdirs, **fetch_options)", "workdirs=workdirs)")], [CALLERS]),
    ('PK04', 'the store fetch reads the global flag', [(LOCAL,
     "        if (switches.store_fetch if switches is not None\n"
     "                else LocalNode.store_fetch_accepted) is not True:",
     "        if LocalNode.store_fetch_accepted is not True:")], [STORE]),
    ('PK05', 'the router gate ignores the bundle', [(RES,
     "        if self.switches is not None and self.switches.isolated_dispatch:",
     "        if False:")], [ROUTER_GATE]),
    ('PK06', 'the router gate opens for a closed bundle', [(RES,
     "        if self.switches is not None and self.switches.isolated_dispatch:",
     "        if self.switches is not None:")], [ROUTER_GATE]),
    ('PK07', 'the confined check reads the global flag', [(VER,
     "    active = (switches.confined_verification if switches is not None\n"
     "              else CONFINED_VERIFICATION_ENABLED)",
     "    active = CONFINED_VERIFICATION_ENABLED")], [CONFINED]),
    ('PK08', 'the worker routes by the global flag', [(WORKER,
     "        active = (self.switches.confined_verification if self.switches is not None\n"
     "                  else V.CONFINED_VERIFICATION_ENABLED)",
     "        active = V.CONFINED_VERIFICATION_ENABLED")], [ROUTE]),
    ('PK09', 'the worker starts a confined row without the bundle', [(WORKER,
     "                           **self._switch)\n            self._run_confined(",
     "                           )\n            self._run_confined(")], [CALLERS]),
    ('PK10', 'the worker retries without the bundle', [(WORKER,
     "self._do(V.retry, verification_id=v.id, **self._switch)['state'] != 'RUNNING':\n"
     "            return True\n        if v.subject.kind == 'task':",
     "self._do(V.retry, verification_id=v.id)['state'] != 'RUNNING':\n"
     "            return True\n        if v.subject.kind == 'task':")], [CALLERS]),
    ('PK11', 'native admission reads the global flag', [(MXC,
     "        if not (self.switches.native_run if self.switches is not None else NATIVE_RUN_ENABLED):",
     "        if not NATIVE_RUN_ENABLED:")], [NATIVE_LAUNCH]),
    ('PK12', 'the native backend drops the bundle', [(NATIVE,
     "schema_validator, switches=switches)", "schema_validator)")],
     [T + 'test_native_backend_receives_constructor_switch']),
    ('PK13', 'the boundary launches without the bundle', [(BOUNDARY,
     "transport=transport, switches=self.switches,", "transport=transport,")], [NATIVE_LAUNCH]),
    ('PK14', 'a harness that is not the supported one is dispatched isolated', [(ISO,
     "        if enforcing and getattr(adapter, 'id', None) != 'claude_code':", "        if False:")],
     [HARNESS]),
    ('PK15', 'an authorization refusal falls back to an ordinary launch', [(ISO,
     "            if enforcing:\n                raise IsolationUnavailable('authorization_refused')",
     "            if False:\n                raise IsolationUnavailable('authorization_refused')")],
     [AUTH]),
    ('PK16', 'production dispatch reads the global flag', [(ISO,
     "        if not (self.switches.production_dispatch if self.switches is not None\n"
     "                else production_dispatch_enabled()) and not is_test_harness(adapter):",
     "        if not production_dispatch_enabled() and not is_test_harness(adapter):")], [BINDS]),
    ('PK17', 'A4 is not checked at establishment', [(ISO,
     "        if self.switches is not None and self.switches.a4 and request.kind != 'verify':",
     "        if False:")], [A4]),
    ('PK18', 'A4 also judges a verifier launch as a harness', [(ISO,
     "self.switches.a4 and request.kind != 'verify':", "self.switches.a4:")],
     [T + 'test_a_verifier_launch_is_not_judged_as_a_harness_dispatch']),
    ('PK19', 'every execution counts as dispatched through the harness', [(ISO,
     "harness_id='claude_code' if request.execution_id in self._dispatch else None,",
     "harness_id='claude_code',")], [A4]),
    ('PK20', 'a dispatched execution is not remembered as dispatched', [(ISO,
     "        if self.record(execution_id) is not None:\n            if enforcing:\n"
     "                self._dispatch.add(execution_id)\n            return True",
     "        if self.record(execution_id) is not None:\n            return True")],
     [T + 'test_a_resume_after_a_restart_is_still_a_harness_dispatch']),
    ('PK21', 'the host entry point reads the global flag', [(HOST,
     "    if bindings is None or enabled(bindings.get('switches'), 'host', HOST_ENABLED) is not True:",
     "    if bindings is None or HOST_ENABLED is not True:")], [HOST_SWITCH]),
]


if __name__ == '__main__':
    mutate_p18.MUTATIONS = MUTATIONS
    sys.exit(mutate_p18.run(sys.argv[1:]))
