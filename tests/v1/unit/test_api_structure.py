"""The API cannot mutate the domain, the route table is pinned, and there is
one engine (p3.5b design gate §10 L1–L3, §11 invariants 1–4, 7)."""

import ast
import os
import re

from archeus.api import auth, routes

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


def _py(*parts):
    base = os.path.join(ROOT, *parts)
    for d, subdirs, files in os.walk(base):
        subdirs[:] = [s for s in subdirs if s not in ('__pycache__', 'static', 'node_modules')]
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(d, f)
                yield os.path.relpath(path, ROOT).replace(os.sep, '/'), \
                    ast.parse(open(path, encoding='utf-8').read())


def _imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ''
            for a in node.names:
                yield '%s.%s' % (mod, a.name) if mod else a.name


FORBIDDEN = re.compile(r'(^|\.)(lifecycle|engine|rows|writer|runtime|connection|migrate|'
                       r'sqlite3|Tx|Database)($|\.)')


def test_the_api_and_the_cli_import_no_mutation_path():
    """L1: no lifecycle, no engine, no rows, no writer module, no database —
    what they may change, they change through an application command."""
    bad = []
    for top in (('archeus', 'api'), ('archeus', 'cli')):
        for path, tree in _py(*top):
            bad += ['%s: %s' % (path, n) for n in _imports(tree) if FORBIDDEN.search(n)
                    and not (top[1] == 'cli' and n in ('core.runtime', '..core.runtime'))]
    # the one allowed crossing: `archeus core` IS the Core, and starts the runtime
    assert all('runtime' in b and b.startswith('archeus/cli/') for b in bad), bad


def test_the_only_mutation_is_one_writer_submit_of_an_application_command():
    calls, sql = [], []
    for path, tree in _py('archeus', 'api'):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in ('submit', 'execute') and 'writer' in ast.unparse(
                        node.func.value):
                    calls.append(path)
                receiver = ast.unparse(node.func.value)
                if node.func.attr in ('fire', '_fire', 'transition') or (
                        node.func.attr in ('insert', 'append') and receiver == 'tx'):
                    sql.append('%s: %s.%s(' % (path, receiver, node.func.attr))
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(
                    r'\b(INSERT|UPDATE|DELETE|REPLACE)\b', node.value):
                sql.append('%s: SQL %r' % (path, node.value[:40]))
    assert calls == ['archeus/api/server.py'], calls        # Handler.run, and nothing else
    assert not sql, sql
    handlers = [n for _p, t in _py('archeus', 'api') for n in ast.walk(t)
                if isinstance(n, ast.Call) and ast.unparse(n.func) == 'req.run']
    targets = sorted({ast.unparse(n.args[0]) for n in handlers})
    assert targets == ['commands.create_mission', 'commands.register_device',
                       'commands.revoke_device', 'conversation.post_message',
                       'knowledge.confirm', 'knowledge.forget',
                       'knowledge.import_meeting', 'knowledge.record_feedback',
                       'knowledge.reject', 'knowledge.retract', 'knowledge.supersede',
                       'own_calls.decide_provider_terms',
                       'req.api.authorization.create_rule', 'req.api.authorization.decide',
                       'req.api.authorization.retire_rule',
                       'req.api.authorization.set_profile',
                       'req.api.conversations.choose', 'req.api.missions.pause',
                       'req.api.missions.resume', 'world.ack_digest',
                       'world.create_project', 'world.declare_constraint'], targets


def test_the_api_never_decides_policy_or_branches_on_an_actors_kind():
    """§11 invariant 4: that is P9's, inside the application layer."""
    bad = []
    for path, tree in _py('archeus', 'api'):
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and n.attr in ('policy', 'evaluate', 'snapshot'):
                bad.append('%s: .%s' % (path, n.attr))
            if isinstance(n, (ast.Name, ast.Attribute)):
                name = n.id if isinstance(n, ast.Name) else n.attr
                if 'Policy' in name and name != 'PolicyDenied':
                    bad.append('%s: %s' % (path, name))
            if isinstance(n, ast.Compare) and any(
                    isinstance(x, ast.Attribute) and x.attr == 'kind'
                    for x in [n.left] + n.comparators):
                bad.append('%s: compares a .kind' % path)
    assert not bad, bad


#: §5.1, the whole table: (method, path, scope, idempotency).
EXPECTED = {
    ('GET', '/', None, None), ('GET', '/assets/*', None, None),
    ('GET', '/v1/health', 'observe', None), ('GET', '/v1/version', 'observe', None),
    ('GET', '/v1/missions', 'observe', None), ('GET', '/v1/missions/{id}', 'observe', None),
    ('POST', '/v1/missions', 'control', 'required'),
    ('POST', '/v1/missions/{id}/pause', 'control', 'required'),
    ('POST', '/v1/missions/{id}/resume', 'control', 'required'),
    ('GET', '/v1/events', 'observe', None), ('GET', '/v1/events/stream', 'observe', None),
    ('POST', '/v1/devices/launch/code', 'admin', 'exempt'),
    ('POST', '/v1/devices/launch/redeem', None, 'exempt'),
    ('POST', '/v1/devices/{id}/revoke', 'admin', 'required'),
}

#: P4's rows (p4-design-gate §10). `create_project` is admin (D7: it gives Core
#: filesystem reach); the digest ack is monotone, so it needs no key.
P4 = {
    ('GET', '/v1/status', 'observe', None),
    ('GET', '/v1/projects', 'observe', None), ('GET', '/v1/projects/{id}', 'observe', None),
    ('POST', '/v1/projects', 'admin', 'required'),
    ('POST', '/v1/projects/{id}/constraints', 'control', 'required'),
    ('GET', '/v1/repositories/{id}/inspections', 'observe', None),
    ('GET', '/v1/digest', 'observe', None), ('POST', '/v1/digest/ack', 'control', None),
}

#: P5's rows (p5-design-gate §6): a read and a preview that writes nothing, so
#: both are observe and neither takes an idempotency key.
P5 = {
    ('GET', '/v1/context/{id}', 'observe', None),
    ('POST', '/v1/context/preview', 'observe', None),
}

#: P6's rows (p6-design-gate §9): the knowledge lifecycle is control; meeting
#: import reads a file on the machine and the provider-terms answer is the
#: user's own, so both are admin (P4 D7's reasoning).
P6 = {
    ('GET', '/v1/knowledge', 'observe', None), ('GET', '/v1/knowledge/{id}', 'observe', None),
    ('POST', '/v1/knowledge/{id}/confirm', 'control', 'required'),
    ('POST', '/v1/knowledge/{id}/reject', 'control', 'required'),
    ('POST', '/v1/knowledge/{id}/retract', 'control', 'required'),
    ('POST', '/v1/knowledge/{id}/supersede', 'control', 'required'),
    ('POST', '/v1/knowledge/forget', 'control', 'required'),
    ('POST', '/v1/feedback', 'control', 'required'),
    ('POST', '/v1/meetings/import', 'admin', 'required'),
    ('GET', '/v1/route-decisions', 'observe', None),
    ('GET', '/v1/route-decisions/{id}', 'observe', None),
    ('GET', '/v1/provider-terms', 'observe', None),
    ('POST', '/v1/provider-terms/{id}', 'admin', 'required'),
}


#: P7's rows (p7-design-gate §9): a posted message is a control command whose
#: reply arrives as `message.created`; the challenge choice (or a clarification's
#: answer) is control too; intents and ideas are reads.
P7 = {
    ('GET', '/v1/conversations/{id}/messages', 'observe', None),
    ('POST', '/v1/conversations/{id}/messages', 'control', 'required'),
    ('GET', '/v1/intents/{id}', 'observe', None),
    ('POST', '/v1/intents/{id}/clarify', 'control', 'required'),
    ('GET', '/v1/ideas', 'observe', None),
}
#: P8 reads only: planning is the worker's, and no route edits or runs a plan
P8 = {
    ('GET', '/v1/missions/{id}/plan', 'observe', None),
    ('GET', '/v1/plans/{id}', 'observe', None),
}


#: P9 (p9-design-gate §18): policy inspection and administration, approvals
P9 = {
    ('GET', '/v1/policies', 'observe', None),
    ('POST', '/v1/policies/rules', 'admin', 'required'),
    ('POST', '/v1/policies/rules/{id}/retire', 'admin', 'required'),
    ('POST', '/v1/policies/profile', 'admin', 'required'),
    ('POST', '/v1/policies/simulate', 'observe', None),
    ('GET', '/v1/policy-decisions', 'observe', None),
    ('GET', '/v1/policy-decisions/{id}', 'observe', None),
    ('GET', '/v1/approvals', 'observe', None),
    ('GET', '/v1/approvals/{id}', 'observe', None),
    ('POST', '/v1/approvals/{id}/decide', 'approve', 'required'),
}


def test_the_route_table_is_exactly_the_p35b_to_p9_tables():
    """L2, and P9's E4: nothing from P10 (route), P11 (executions, stop,
    estop, hooks), P14 (automations), P15 (pair, device list) or P16 (/v1/now,
    the execution stream) — a later phase adds its rows with its own tests."""
    got = {(r.method, r.path, r.scope, r.idempotent) for r in routes.ROUTES}
    assert got == EXPECTED | P4 | P5 | P6 | P7 | P8 | P9
    assert len(routes.ROUTES) == len(EXPECTED | P4 | P5 | P6 | P7 | P8 | P9)
    # E7: no plan route takes a command (no execution control from P8)
    assert not [r for r in routes.ROUTES if 'plan' in r.path and r.method != 'GET']
    for word in ('route/', 'execution', 'estop', 'stop', 'pair', '/now', 'hook', 'dispatch',
                 'cancel', 'accept', 'account', 'graph', 'attention', 'automation'):
        assert not [r.path for r in routes.ROUTES if word in r.path], word
    # the only `route` paths are own-call decisions (P6), never the P10 router
    assert {r.path for r in routes.ROUTES if 'route' in r.path} == {
        '/v1/route-decisions', '/v1/route-decisions/{id}'}
    assert not [r.path for r in routes.ROUTES if r.path.endswith('/inspect')]


def test_every_scope_is_a_coarse_credential_scope_and_approve_is_only_deciding():
    assert {r.scope for r in routes.ROUTES} <= set(auth.SCOPES) | {None}
    # P9: the approve scope reaches exactly one route, the decision
    assert [r.path for r in routes.ROUTES if r.scope == 'approve'] == [
        '/v1/approvals/{id}/decide']
    assert auth.LAUNCH_SCOPES == ('observe',)
    public = {r.path for r in routes.ROUTES if r.scope is None}
    assert public == {'/', '/assets/*', '/v1/devices/launch/redeem'}


def test_every_command_route_declares_its_request_and_response_shape():
    for r in routes.ROUTES:
        if r.method == 'POST':
            assert r.request_schema is not None and r.response_schema, r.path
            if r.idempotent == 'required':
                assert 'idempotency_key' in r.request_schema['required'], r.path


def _calls(name, *tops):
    out = []
    for top in tops:
        for path, tree in _py(*top):
            for n in ast.walk(tree):
                if isinstance(n, ast.Call):
                    f = ast.unparse(n.func)
                    if f == name or f.endswith('.' + name):
                        out.append(path)
    return sorted(set(out))


def test_one_engine_host_and_one_database_opener_outside_the_tests():
    """L3: Engine(...) is built by the Core runtime and the in-process judge
    binding; Database.open(...) likewise. Both take core.lock first."""
    places = (('archeus',), ('claude_sessions',), ('tools',), ('tests', 'v1', 'judge'))
    assert _calls('Engine', *places) == ['archeus/core/runtime.py', 'tests/v1/judge/client.py']
    assert _calls('Database.open', *places) == ['archeus/core/runtime.py',
                                                'tests/v1/judge/client.py']
    for path in ('archeus/core/runtime.py', 'tests/v1/judge/client.py'):
        src = open(os.path.join(ROOT, path), encoding='utf-8').read()
        assert src.index('discovery.acquire(') < src.index('Database.open('), path


def test_nothing_in_p35b_writes_a_process_registry():
    """P11 owns run/processes.jsonl; nothing here may even name it."""
    docs = set()
    for top in (('archeus', 'api'), ('archeus', 'cli'), ('archeus', 'core')):
        for path, tree in _py(*top):
            for n in ast.walk(tree):
                body = getattr(n, 'body', None)
                if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)):
                    docs.add(id(body[0].value))
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant) and id(n) not in docs and isinstance(
                        n.value, str):
                    assert 'processes.jsonl' not in n.value, path
                if isinstance(n, (ast.Name, ast.Attribute)):
                    assert 'processes_registry' not in ast.unparse(n), path
