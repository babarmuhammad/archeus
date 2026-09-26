"""P9 phase boundaries (p9-design-gate §23, E1-E4, E7, E8, E10): what policy
and authorisation may not reach — resources, processes, execution,
verification, review, automation, provider terms — proven on the source and
on the tables. E5/E6 run in tests/v1/integration/test_policy.py (the spy on
every P9 test) and E9 there too."""

import ast
import os

from archeus.core.domain import states
from archeus.harnesses.fake import FakeHarness

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MODULES = ['archeus/core/policy/rules.py', 'archeus/core/policy/engine.py',
           'archeus/core/policy/worker.py', 'archeus/core/application/authorization.py']


def _tree(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return ast.parse(f.read())


def _imports(rel):
    out = set()
    for n in ast.walk(_tree(rel)):
        if isinstance(n, ast.ImportFrom):
            out.add('.' * n.level + (n.module or ''))
            out |= {'.' * n.level + (n.module + '.' if n.module else '') + a.name
                    for a in n.names}
        elif isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
    return out


FORBIDDEN = ('harnesses', 'engine', 'runtime', 'api', 'calls', 'planning.worker',
             'planning.planner.plan', 'claude_sessions', 'routing', 'execution', 'verification',
             'review', 'automation', 'node', 'subprocess', 'socket', 'urllib', 'http')


def test_E1_policy_imports_no_later_phase_resource_or_process_module():
    for rel in MODULES:
        for name in _imports(rel):
            parts = name.lstrip('.').split('.')
            for bad in FORBIDDEN:
                bad_parts = bad.split('.')
                if any(parts[i:i + len(bad_parts)] == bad_parts for i in range(len(parts))):
                    # `..policy.engine` is policy's own engine, not the P3.5 walking skeleton
                    assert (rel, name) in (('archeus/core/policy/worker.py', '..application'),
                                           ) or name.endswith('policy.engine') \
                        or name == '.engine', (rel, name)


def test_E2_policy_never_routes_spawns_executes_verifies_or_reviews():
    calls = {'route', 'start', 'spawn', 'resume', 'stop', 'pause', 'verify', 'review',
             'archeus_call', 'kill_tree', 'Popen'}
    for rel in MODULES:
        for n in ast.walk(_tree(rel)):
            if isinstance(n, ast.Call):
                f = n.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', None)
                # a regex match's offset; the MISSION's resume after a task approval
                # (unblock + redispatch, D13) — neither is a process
                if ast.unparse(f) in ('wild.start', 'missions.resume'):
                    continue
                assert name not in calls, (rel, name)


def test_E3_no_resource_is_read_or_bound_by_policy():
    for rel in MODULES:
        for n in ast.walk(_tree(rel)):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                assert n.value not in ('harness_id', 'account_id', 'account_ref', 'model',
                                       'node_id', 'provider'), (rel, n.value)
            if isinstance(n, ast.Attribute):
                assert n.attr not in ('harness_id', 'account_ref', 'route_decision_id'), (
                    rel, n.attr)


def test_E7_the_runtime_registers_only_the_fake_harness_for_execution():
    src = open(os.path.join(ROOT, 'archeus/core/runtime.py'), encoding='utf-8').read()
    registered = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute) and n.func.attr == 'register']
    assert [ast.unparse(c.args[0]) for c in registered] == ['FakeHarness()']
    assert FakeHarness.id == 'fake'


def test_E8_policy_never_reads_provider_terms():
    for rel in MODULES:
        src = open(os.path.join(ROOT, rel), encoding='utf-8').read()
        assert 'ProviderTerms' not in src and 'provider_terms' not in src, rel


def test_E10_the_state_machine_diff_is_the_two_p9_changes():
    """Against P8: mission `approve` is guarded, and `REASONING -> BLOCKED:
    plan_denied` exists (guarded). No other edge or guard moved."""
    guarded = {(m, t) for m, _f, _to, t, g in states.TABLE if g}
    assert ('mission', 'approve') in guarded and ('mission', 'plan_denied') in guarded
    assert ('REASONING', 'BLOCKED', 'plan_denied') in [
        (f, to, t) for f, to, t, _g in states.edges('mission')]
    approval = [(f, to, t) for f, to, t, _g in states.edges('approval') if t]
    assert approval == [('PENDING', 'APPROVED', 'approve'), ('PENDING', 'REJECTED', 'reject'),
                        ('PENDING', 'EXPIRED', 'ttl_elapsed'),
                        ('PENDING', 'SUPERSEDED', 'plan_replaced'),
                        ('APPROVED', 'CONSUMED', 'action_executed'),
                        ('APPROVED', 'EXPIRED', 'ttl_elapsed'),
                        ('APPROVED', 'SUPERSEDED', 'plan_replaced')]


def test_the_p9_triggers_are_fired_only_by_authorisation():
    """§12.4: the approval machine's triggers and the plan's `approved` /
    `rejected` are fired by authorization.py alone (a source scan)."""
    owned = {"'approved'", "'rejected'", "'plan_replaced'", "'ttl_elapsed'",
             "'action_executed'"}
    for d, _s, files in os.walk(os.path.join(ROOT, 'archeus')):
        for f in files:
            if not f.endswith('.py'):
                continue
            rel = os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, '/')
            for n in ast.walk(_tree(rel)):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr == 'fire'):
                    args = [ast.unparse(a) for a in n.args]
                    touched = (('entities.Approval' in args) or
                               ('entities.Plan' in args and set(args) & owned))
                    if touched:
                        assert rel == 'archeus/core/application/authorization.py', (rel, args)
