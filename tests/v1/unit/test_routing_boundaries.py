"""P10 phase boundaries (p10-design-gate §18, B-*; B7, the run-time spy, is
in tests/v1/integration/test_routing.py): what the router may not
reach — authorisation, approval, policy, execution, processes, P11+ — proven
on the source and at run time. The router is pure; the application module
around it records decisions and asks P9's machinery, and nothing else."""

import ast
import os

import pytest

from archeus.core.application import resources
from archeus.harnesses import base
from archeus.harnesses.fake import FakeCaller, FakeHarness

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ROUTER = 'archeus/core/routing/router.py'
USAGE = 'archeus/core/routing/usage.py'
APP = 'archeus/core/application/resources.py'
P10 = (ROUTER, USAGE, APP)


def _tree(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return ast.parse(f.read())


def _imports(rel):
    out = set()
    for n in ast.walk(_tree(rel)):
        if isinstance(n, ast.ImportFrom):
            out.add('.' * n.level + (n.module or ''))
        elif isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
    return out


def _calls(rel):
    out = set()
    for n in ast.walk(_tree(rel)):
        if isinstance(n, ast.Call):
            f = n.func
            out.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', None))
    return out


def _strings(rel):
    return {n.value for n in ast.walk(_tree(rel))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def test_B1_the_router_is_pure_it_imports_nothing():
    """Same inputs, same decision: it can read nothing but its arguments."""
    assert _imports(ROUTER) == set()


def test_B2_no_p10_module_spawns_a_process_or_opens_a_socket():
    bad = ('subprocess', 'socket', 'urllib', 'http', 'multiprocessing', 'proc', 'os.system')
    for rel in P10:
        for name in _imports(rel):
            assert not any(b in name.split('.') for b in bad), (rel, name)
        assert not _calls(rel) & {'Popen', 'spawn', 'spawn_detached', 'kill_tree', 'system',
                                  'run_headless'}, rel


def test_B3_p10_never_executes_verifies_reviews_or_calls_a_model():
    """Selecting a resource is not running it (P11), and an adapter is only
    ever asked what it declares (discover, capabilities) or, by the transport
    before a registration, whether a login works (authenticate)."""
    for rel in P10:
        assert not _calls(rel) & {'start', 'send', 'pause', 'stop', 'inspect', 'status',
                                  'collect_result', 'handoff', 'verify', 'review',
                                  'record_spawn', 'record_exit', 'dispatch_task'}, rel
        assert 'call' not in _calls(rel), rel         # no adapter.call(): no model call


def test_B4_p10_never_authorises_approves_or_changes_policy():
    """No P9 decision is made, widened or answered here: the router's only
    link to P9 is reading the recorded dispatch decision."""
    forbidden = {'check_dispatch', 'evaluate', 'evaluate_task', 'evaluate_action', 'judge',
                 'record', 'record_plan_decision', 'decide', '_approve', '_approve_route',
                 'create_rule', 'retire_rule', 'set_profile', 'simulate'}
    for rel in P10:
        assert not _calls(rel) & forbidden, (rel, _calls(rel) & forbidden)
        assert not {'..policy', '..policy.engine', '..policy.rules'} & _imports(rel), rel
    # the one Approval P10 ever writes is a PENDING question of kind `route`:
    # it states no state and no decision, so the entity's default (PENDING) holds
    tree = _tree(APP)
    made = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and ast.unparse(n.func) == 'entities.Approval']
    assert len(made) == 1
    kw = {k.arg: ast.unparse(k.value) for k in made[0].keywords}
    assert kw['kind'] == "'route'" and not {'state', 'decision', 'decided_by',
                                            'decided_at'} & set(kw)
    fired = [ast.unparse(n.args[3]) for n in ast.walk(tree) if isinstance(n, ast.Call)
             and ast.unparse(n.func) == 'lifecycle.fire' and len(n.args) > 3]
    assert set(fired) <= {"'auth_ok' if auth['ok'] else 'auth_failed'",
                          "'user_enables' if enabled else 'user_disables'"}, fired


def test_B5_the_router_names_no_harness():
    """No hidden Claude (or any other harness) rule: capability and the
    recorded preferences decide, never a harness id in the code."""
    for s in _strings(ROUTER):
        assert 'claude' not in s.lower() and s not in ('pi', 'codex', 'fake'), s


def test_B6_a_snapshot_reports_capabilities_as_declared_never_more():
    h = FakeHarness('x', capabilities=('shell',), models=('m',))
    v = resources.harness_view(h, True)
    assert v['capabilities'] == ['shell'] and v['models'] == [
        {'id': 'm', 'tier': None, 'context_window': None}]
    off = resources.harness_view(FakeCaller('y', installed=False), True)
    assert (off['installed'], off['capabilities'], off['models']) == (False, [], [])


def test_B8_core_registers_only_the_fake_harness_for_execution():
    """P11 owns real execution adapters: the runtime's registry is the fake one."""
    tree = _tree('archeus/core/runtime.py')
    regs = [ast.unparse(n.args[0]) for n in ast.walk(tree) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == 'register']
    assert regs == ['FakeHarness()']


def test_B9_no_later_phase_module_exists_yet():
    for rel in ('archeus/core/execution', 'archeus/node', 'archeus/harnesses/claude_code',
                'archeus/harnesses/codex'):
        assert not os.path.exists(os.path.join(ROOT, rel)), rel


def test_B10_a_router_decision_is_frozen_but_for_an_own_calls_outcome():
    from archeus.core.domain import entities, ids
    assert entities.RouteDecision.frozen_fields() == {
        f for f in entities.RouteDecision.__dataclass_fields__} - {'id', 'outcome'}
    assert entities.UsageLedger.frozen_fields() >= {'route_decision_id', 'execution_id',
                                                    'account_id'}
    with pytest.raises(ValueError, match='route decision'):      # usage never detached
        entities.UsageLedger(id=ids.new_id('usage_ledger'), execution_id=ids.new_id(
            'execution'), tokens_in=1)


def test_B11_an_adapter_probe_is_never_made_inside_a_command():
    """`authenticate` is a side effect: only the transport-facing service calls
    it, before the command; no command takes an adapter."""
    tree = _tree(APP)
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        if fn.args.args and fn.args.args[0].arg == 'tx':
            names = {getattr(c.func, 'attr', None) for c in ast.walk(fn)
                     if isinstance(c, ast.Call)}
            assert 'authenticate' not in names and 'probe' not in names, fn.name


@pytest.mark.parametrize('adapter', [FakeHarness(), FakeCaller('x')])
def test_B12_the_fake_adapters_declare_a_known_tier(adapter):
    """A scripted harness offers a model the router can place (P10): an
    untiered default would silently exclude it from every tier minimum."""
    caps = adapter.capabilities(None)
    assert any(isinstance(m, base.ModelInfo) and m.tier == 'large' for m in caps.models)
