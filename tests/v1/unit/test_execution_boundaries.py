"""P11 phase boundaries (p11-design-gate §24.4): what the execution orchestrator
may not reach — its own policy or routing, approvals it did not ask P9 for,
plans, verification, review, sessions, checkpoints, hand-off — proven on the
source."""

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__)))))
P11 = ('archeus/core/execution/manager.py', 'archeus/core/execution/canonical.py',
       'archeus/core/application/executions.py', 'archeus/node/local.py',
       'archeus/harnesses/hook.py', 'archeus/harnesses/claude_code/adapter.py')


def _tree(rel):
    return ast.parse(open(os.path.join(ROOT, rel), encoding='utf-8').read())


def _imports(rel):
    out = set()
    for n in ast.walk(_tree(rel)):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mod = '.' * n.level + (n.module or '')
            out |= {mod} | {mod + '.' + a.name for a in n.names}
    return out


def _strings(rel):
    return {n.value for n in ast.walk(_tree(rel)) if isinstance(n, ast.Constant)
            and isinstance(n.value, str)}


def test_X1_p11_has_no_policy_engine_and_no_router_of_its_own():
    for rel in P11:
        bad = {i for i in _imports(rel) if 'policy.engine' in i or 'policy.rules' in i
               or 'routing.router' in i or i.endswith('policy') or i.endswith('.rules')}
        assert not bad, (rel, bad)
    # it reaches P9 and P10 only through their application entry points
    src = open(os.path.join(ROOT, 'archeus/core/application/executions.py'),
               encoding='utf-8').read()
    assert 'authorization.evaluate_action(' in src and 'authorization.check_dispatch(' in src
    assert 'router.route(' in src


def test_X2_p11_writes_no_approval_rule_or_route_decision_itself():
    for rel in P11:
        for n in ast.walk(_tree(rel)):
            if isinstance(n, ast.Call) and ast.unparse(n.func).endswith('.insert') and n.args:
                made = ast.unparse(n.args[0])
                assert not any(k in made for k in ('Approval', 'PolicyRule', 'PolicyDecision',
                                                   'RouteDecision', 'Plan(', 'Session',
                                                   'Checkpoint', 'Verification', 'Review')), (
                    rel, made)


def test_X3_p11_fires_no_plan_verification_review_or_mission_success():
    forbidden = {'all_tasks_done', 'verified', 'accepted', 'checks_passed', 'checks_failed_retry',
                 'checks_failed_final', 'approve', 'reject', 'plan_auto_approved', 'redispatch',
                 'replan', 'pressure_or_account_change', 'checkpoint_written'}
    for rel in ('archeus/core/application/executions.py', 'archeus/core/execution/manager.py'):
        assert not (_strings(rel) & forbidden), (rel, _strings(rel) & forbidden)
        for n in ast.walk(_tree(rel)):
            if isinstance(n, ast.Call) and ast.unparse(n.func).endswith('fire') and n.args:
                kind = ast.unparse(n.args[1]) if len(n.args) > 1 else ''
                assert not any(k in kind for k in ('Plan', 'Verification', 'Review')), (rel,
                                                                                       kind)


def test_X4_the_node_touches_no_database_policy_or_routing():
    bad = {i for i in _imports('archeus/node/local.py')
           if any(k in i for k in ('infra.db', 'application', 'policy', 'routing', 'writer'))}
    assert not bad, bad


def test_X5_no_p11_module_calls_a_model():
    for rel in P11:
        imps = _imports(rel)
        assert not {i for i in imps if i.endswith('calls.OwnCalls') or i.endswith('llmcall')
                    or i == '..core.calls' or i == '...core.calls'}, rel
        assert 'archeus_call' not in _strings(rel), rel


def test_X6_the_hook_is_stdlib_only():
    imported = {i.split('.')[0] for i in _imports('archeus/harnesses/hook.py')}
    assert imported <= set(sys.stdlib_module_names), imported


def test_X7_no_later_phase_module_exists_yet():
    for rel in ('archeus/core/execution/checkpoint.py', 'archeus/core/execution/handoff.py',
                'archeus/core/execution/integration.py', 'archeus/harnesses/codex',
                'archeus/core/automation', 'archeus/node/remote.py'):
        assert not os.path.exists(os.path.join(ROOT, rel)), rel


def test_X8_only_the_node_spawns_and_kills_for_an_execution():
    """The manager acts on the world only through the node; the node, only
    through the adapter (spawn) and the P0.5 identity seam (kill)."""
    for rel in ('archeus/core/execution/manager.py', 'archeus/core/application/executions.py'):
        names = {ast.unparse(n.func) for n in ast.walk(_tree(rel)) if isinstance(n, ast.Call)}
        assert not {x for x in names if x.startswith('subprocess.') or 'kill_pid_tree' in x
                    or x.endswith('.start') and 'adapter' in x or 'Popen' in x}, (rel, names)


def test_X9_success_is_never_p11s_to_declare():
    src = open(os.path.join(ROOT, 'archeus/core/application/executions.py'),
               encoding='utf-8').read()
    assert "'execution_succeeded'" in src and 'SUCCEEDED' not in src.replace(
        'execution_succeeded', '')
