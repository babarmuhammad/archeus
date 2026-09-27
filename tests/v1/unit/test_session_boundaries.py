"""P12 phase boundaries (p12-design-gate §5, §23, §24): what session and
context continuity may not reach — a policy engine, a router or a context
engine of its own, a model, a process, a mission's lifecycle, an approval —
proven on the source."""

import ast
import os

from v1.unit.test_execution_boundaries import ROOT, _imports, _strings, _tree

P12 = ('archeus/core/application/sessions.py', 'archeus/core/sessions/continuity.py',
       'archeus/core/sessions/render.py', 'archeus/core/sessions/service.py',
       'archeus/core/execution/checkpoint.py', 'archeus/core/execution/handoff.py',
       'archeus/harnesses/sessions.py')


def _calls(rel):
    return [n for n in ast.walk(_tree(rel)) if isinstance(n, ast.Call)]


def test_Y1_p12_has_no_policy_engine_router_or_context_engine_of_its_own():
    for rel in P12:
        bad = {i for i in _imports(rel) if 'policy.engine' in i or 'policy.rules' in i
               or 'routing.router' in i or i.endswith(('.select', '.gather'))}
        assert not bad, (rel, bad)
    # P9 and P10 through their entry points, P5 through its one recorder
    src = open(os.path.join(ROOT, 'archeus/core/execution/handoff.py'), encoding='utf-8').read()
    assert 'authorization.check_dispatch(' in src and 'router.route(' in src
    cont = open(os.path.join(ROOT, 'archeus/core/sessions/continuity.py'), encoding='utf-8').read()
    assert 'record_context_package(' in cont and 'context.assemble(' not in cont


def test_Y2_p12_calls_no_model_and_spawns_nothing_but_through_the_node():
    for rel in P12:
        imps = _imports(rel)
        assert not {i for i in imps if 'llmcall' in i or i.endswith('core.calls')
                    or i.endswith('OwnCalls')}, rel
        assert 'archeus_call' not in _strings(rel), rel
        names = {ast.unparse(n.func) for n in _calls(rel)}
        assert not {x for x in names if x.startswith('subprocess.') or 'Popen' in x
                    or 'spawn_terminal' in x or x.endswith('.start')}, (rel, names)
    svc = {ast.unparse(n.func) for n in _calls('archeus/core/sessions/service.py')}
    assert 'self.node.open_terminal' in svc


def test_Y3_no_p12_module_moves_a_mission_and_only_a_refused_continuation_moves_a_task():
    for rel in P12:
        for n in _calls(rel):
            f = ast.unparse(n.func)
            if f.endswith(('missions._fire', 'missions.fire')):
                raise AssertionError((rel, f))
            if f.endswith('lifecycle.fire') and len(n.args) >= 2:
                cls = ast.unparse(n.args[1])
                assert 'Mission' not in cls and 'Plan' not in cls, (rel, cls)
                if 'Task' in cls:
                    assert rel.endswith('handoff.py') and \
                        ast.unparse(n.args[3]) == "'execution_failed_retry'", (rel, n.args)
    # a session's commands move only sessions
    for n in _calls('archeus/core/application/sessions.py'):
        if ast.unparse(n.func).endswith('lifecycle.fire'):
            assert ast.unparse(n.args[1]) == 'entities.Session'


def test_Y4_p12_writes_no_approval_rule_route_decision_or_policy_decision():
    for rel in P12:
        for n in _calls(rel):
            if ast.unparse(n.func).endswith('.insert') and n.args:
                made = ast.unparse(n.args[0])
                assert not any(k in made for k in ('Approval', 'PolicyRule', 'PolicyDecision',
                                                   'RouteDecision', 'Plan(', 'Verification',
                                                   'Review')), (rel, made)


def test_Y5_no_rendering_is_ever_read_back_into_core():
    """A rendering is a delivery (§12): the only readers of the artifact store
    in P12 are the launcher's delivery copy and a continuation's prompt."""
    readers = set()
    for rel in P12:
        for n in _calls(rel):
            if ast.unparse(n.func) == 'artifacts.get':
                readers.add(rel)
    assert readers == {'archeus/core/sessions/service.py', 'archeus/core/execution/checkpoint.py'}
    for rel in P12:
        assert not {i for i in _imports(rel) if i.endswith('json.loads')}, rel


def test_Y6_the_context_engine_gained_no_session_subject():
    from archeus.core.domain import entities
    assert entities.CONTEXT_SUBJECTS == ('mission', 'project', 'message')


def test_Y7_no_later_phase_module_exists_yet():
    for rel in ('archeus/core/verification', 'archeus/core/execution/integration.py',
                'archeus/core/automation', 'archeus/api/pairing.py', 'archeus/harnesses/codex',
                'archeus/node/remote.py'):
        assert not os.path.exists(os.path.join(ROOT, rel)), rel
