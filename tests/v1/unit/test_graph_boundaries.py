"""P18's boundaries (p18-design-gate §14): the graph is a view. Its query writes
nothing, routes nothing, recomputes no import graph, and its two routes open a
read and nothing else. Static checks over the source, because each of these
is a property of what the code CAN do, not of what one run happened to do."""

import ast
import inspect

from archeus.api import routes
from archeus.core.application import graph

SRC = inspect.getsource(graph)


def _imports(src):
    out = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.ImportFrom):
            out.add('.' * n.level + (n.module or ''))
            out.update('%s%s.%s' % ('.' * n.level, n.module or '', a.name) for a in n.names)
        elif isinstance(n, ast.Import):
            out.update(a.name for a in n.names)
    return out


def test_the_graph_query_imports_no_writer_router_extractor_or_client():
    imports = _imports(SRC)
    for banned in ('routing', 'cli', 'connections', 'inspection', 'claude_sessions', 'engine',
                   'commands', 'policy', 'execution', 'knowledge', 'lifecycle'):
        assert not [i for i in imports if banned in i.split('.')], (banned, imports)
    # the one thing from the writer module is its NotFound error
    assert {i for i in imports if 'writer' in i} == {'...infra.db.writer',
                                                     '...infra.db.writer.NotFound'}


def test_the_graph_query_calls_no_write():
    receivers = {n.func.value.id for n in ast.walk(ast.parse(SRC))
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and isinstance(n.func.value, ast.Name)}
    # no transaction, writer or artifact store is ever called: only rows, conn, outbox
    assert not receivers & {'tx', 'writer', 'db', 'store', 'artifacts', 'events'}, receivers
    assert not {n.id for n in ast.walk(ast.parse(SRC)) if isinstance(n, ast.Name)} & {
        'tx', 'writer', 'new_event'}
    # the SQL it runs itself are counts, never a write
    for sql in (n.value for n in ast.walk(ast.parse(SRC))
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value.lstrip().upper().startswith(('SELECT', 'INSERT', 'UPDATE', 'DELETE'))):
        assert sql.lstrip().upper().startswith('SELECT'), sql


def test_the_repository_graph_reads_the_stored_artifact_only():
    """M21: no filesystem walk, no extractor — only the artifact store's get,
    passed in by the route."""
    src = inspect.getsource(graph.repository_graph) + inspect.getsource(graph._tree)
    for banned in ('os.walk', 'os.listdir', 'open(', 'scandir', 'build_hierarchy', 'inspect('):
        assert banned not in src, banned
    assert 'read(sha)' in inspect.getsource(graph._payload)
    assert 'artifacts.get' in inspect.getsource(routes.repository_graph)


def test_the_graph_routes_open_a_read_and_never_run_a_command():
    for fn in (routes.world_graph, routes.repository_graph):
        src = inspect.getsource(fn)
        assert 'db.read()' in src and 'req.run' not in src and 'writer' not in src, fn


def test_a_route_decision_node_names_only_selection_facts():
    """P10 owns routing; the graph shows its recorded answer (A2)."""
    assert graph.ROUTE_ATTRS == ('harness_id', 'account_id', 'model', 'effort', 'result',
                                 'fallback_from')
    src = inspect.getsource(graph.node_of)
    for private in ('explanation', 'requirements', 'input_snapshot', 'outcome'):
        assert private not in src, private


def test_no_credential_kind_can_be_a_node():
    for kind in ('device', 'token', 'principal', 'user', 'event', 'account', 'usage_snapshot',
                 'idempotency_key', 'message', 'conversation'):
        assert kind not in graph.KINDS, kind
