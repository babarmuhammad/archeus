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
                       'commands.revoke_device', 'req.api.missions.pause',
                       'req.api.missions.resume'], targets


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


def test_the_route_table_is_exactly_the_p35b_table():
    """L2: nothing from P9 (approve), P10 (route), P11 (executions, stop,
    estop, hooks), P15 (pair, device list) or P16 (/v1/now, the execution
    stream) — a later phase adds its rows with its own tests."""
    got = {(r.method, r.path, r.scope, r.idempotent) for r in routes.ROUTES}
    assert got == EXPECTED
    assert len(routes.ROUTES) == len(EXPECTED)
    for word in ('approv', 'route', 'execution', 'estop', 'stop', 'pair', 'now', 'hook',
                 'status', 'cancel', 'accept', 'account'):
        assert not [r.path for r in routes.ROUTES if word in r.path], word


def test_every_scope_is_a_coarse_credential_scope_and_approve_has_no_route():
    assert {r.scope for r in routes.ROUTES} <= set(auth.SCOPES) | {None}
    assert 'approve' not in {r.scope for r in routes.ROUTES}
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
