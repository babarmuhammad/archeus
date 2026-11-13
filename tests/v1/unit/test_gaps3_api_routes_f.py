"""T-1157 — the ten highest-risk uncovered branches of `archeus/api/routes.py`
lines **1087-1383** inclusive (tip 56d53504): the `ROUTES` rows, the class
projection `_NAMED`/`CLASS`/`PRIVILEGED`, `QUERY`, `STREAM`, `REPLAYABLE`,
`_compile`, `_COMPILED` and `match`. No source file is edited here, and no
branch outside that range is owned by it: the handlers are reached only through
the rows this slice declares.

The ten final branches, numbered as the sections that test them below. Four are
the card's own probes (3, 7, 9, 10 of its list); six replace a probe that is
already covered — the replaced probe, the covering test and the evidence are in
the completion report, together with the risk ranking. Grouped as the card asks:
fail-closed and denial first (risk order 1, 2, 9, 7, 8), then boundaries
(3, 4, 10), then error paths (5, 6):

 1. no verb but the row's own reaches a route, a scope or a class: a HEAD or an
    OPTIONS never inherits the GET row                      routes.py:1379, 1331-1332
 2. an `observe` row never reaches the writer, and every row that reaches the
    writer is a command row with a command scope    routes.py:1087-1296, 1331-1333
 3. a literal segment of a path is matched literally, never as a regex
                                                             routes.py:1362, 1364
 4. the end anchor is an end: a trailing newline is not the row's path
                                                             routes.py:1362, 1366 (xfail)
 5. the 405/404 decision cannot leak from one request to the next
                                                             routes.py:1374
 6. a path known only through a `{parameter}` still answers 405, never 404
                                                            routes.py:1375-1383
 7. every row is the matcher's own answer for its own path — nothing shadows it,
    and `_COMPILED` pairs each row with its own pattern       routes.py:1369
 8. a segment that is both a literal row and a valid id chooses the row of its
    verb AND that row's handler, with no privileged side effect on the read side
                                     routes.py:1098, 1115-1118, 1156, 1161, 1171-1174
 9. only the monotone digest ack may ever come back from an offline queue
                                                            routes.py:1357, 1352, 1333
10. `QUERY` names exactly the query parameters the handlers read — the API
    reference and the typed client are generated from it      routes.py:1336-1350

Everything is driven through the fake-request seams the neighbouring unit tests
use (a plain object for `server.Handler`, `db.read()` as a counting context
manager, the application function the handler reads patched with `monkeypatch`).
No live server, socket, thread, subprocess, sleep or OS call; nothing is written
to disk and no environment value is read. Platform-neutral: no case-insensitive
comparison, no path separator, no OS error text, no host environment. No other
test module is imported and no queue order is relied on.
"""

import ast
import inspect
import re
from types import SimpleNamespace

import pytest

from archeus.api import routes, schemas
from archeus.api.routes import Refused
from archeus.api.schemas import Invalid

MODULE = routes.__name__
TABLE = {(r.method, r.path): r for r in routes.ROUTES}
TOKEN = 'msnabc123'                                     # never a literal segment of a row

#: The privileged rows that write through an `Api` collaborator instead of
#: `req.run`, and the collaborator verb each must still reach to be alive.
COLLABORATOR_ROWS = {
    ('POST', '/v1/devices/launch/code'): {'mint'},
    ('POST', '/v1/devices/pair/start'): {'mint'},
    ('POST', '/v1/sessions'): {'launch', 'register'},
    ('POST', '/v1/sessions/{id}/resume'): {'resume'},
    ('POST', '/v1/sessions/{id}/handoff'): {'handoff'},
}


# ── the seams ──

class _Runs:
    """`req.run` as the server's is: one writer submit, recorded. `forbid` makes
    any submit a hard failure — the seam the read rows are driven with."""

    def __init__(self, forbid=False):
        self.calls = []
        self.forbid = forbid

    def __call__(self, fn, kwargs, *, actor_id=None, keyed=True):
        if self.forbid:
            raise AssertionError('a read ran a command: %r %r' % (fn, kwargs))
        self.calls.append(SimpleNamespace(fn=fn, kwargs=kwargs, keyed=keyed))
        return {'ok': True}


class _Db:
    def __init__(self):
        self.reads = 0

    def read(self):
        outer = self

        class _Cm:
            def __enter__(_self):
                outer.reads += 1
                return 'conn'

            def __exit__(_self, *exc):
                return False

        return _Cm()


def _req(body=None, params=None, query=None, forbid=False):
    return SimpleNamespace(
        body=body or {}, params=params or {}, query=query or {}, headers={},
        api=SimpleNamespace(db=_Db(),
                            resources=SimpleNamespace(registry=None, callers=None),
                            missions=SimpleNamespace(pause='pause', resume='resume',
                                                     pause_all='pause_all',
                                                     resume_all='resume_all'),
                            pairing=SimpleNamespace(mint='pairing-mint'),
                            launch=SimpleNamespace(mint='launch-mint')),
        run=_Runs(forbid=forbid))


def _drive(method, path, body=None, params=None, query=None, forbid=False):
    """Call THE row `match` answers for this request, on a fake request."""
    row = routes.match(method, path)[0]
    req = _req(body, params, query, forbid)
    out = row.handler(req)
    return row, req, out


def _refused(method, path):
    with pytest.raises(Refused) as e:
        routes.match(method, path)
    return e.value


def _concrete(path):
    out = path
    if out.endswith('/*'):
        out = out[:-2] + '/' + TOKEN + '.js'
    while '{' in out:
        before, _, rest = out.partition('{')
        _param, _, after = rest.partition('}')
        out = before + TOKEN + after
    return out


def _module_fn(name):
    f = getattr(routes, name, None)
    return f if inspect.isfunction(f) and f.__module__ == MODULE else None


def _defs(f):
    return {n.name: n for n in ast.parse(inspect.getsource(f)).body
            if isinstance(n, ast.FunctionDef)}


def _collect(f, acc, seen, read):
    """`read(node, acc)` over `f` and every module-level function it may reach."""
    if f.__name__ in seen:
        return acc
    seen.add(f.__name__)
    node = _defs(f).get(f.__name__)
    if node is not None:
        read(node, acc)
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                sub = _module_fn(n.func.id)
                if sub is not None:
                    _collect(sub, acc, seen, read)
    return acc


def _calls(f):
    def read(node, acc):
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                acc.add(ast.unparse(n.func))
    return _collect(f, set(), set(), read)


def _query_names(f):
    def read(node, acc):
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                name = ast.unparse(n.func)
                if name == '_one' and len(n.args) == 2 and ast.unparse(n.args[0]) == \
                        'req.query' and isinstance(n.args[1], ast.Constant):
                    acc.add(n.args[1].value)
                elif name.endswith('req.query.get') and n.args and isinstance(
                        n.args[0], ast.Constant):
                    acc.add(n.args[0].value)
    return _collect(f, set(), set(), read)


def _writer_calls(reached):
    return sorted(c for c in reached if c == 'req.run' or c.endswith('.run')
                  or c == 'submit' or 'writer' in c)


# ── 1. no verb but the row's own ──

def test_no_verb_but_the_rows_own_reaches_a_route_a_scope_or_a_class():
    assert {r.method for r in routes.ROUTES} == {'GET', 'POST'}
    assert not [k for k in routes.CLASS if k[0] not in ('GET', 'POST')]
    assert not [k for k in routes.PRIVILEGED if k[0] not in ('GET', 'POST')]
    for verb in ('HEAD', 'OPTIONS', 'get', 'post', 'CONNECT', 'TRACE'):
        for r in routes.ROUTES:
            e = _refused(verb, _concrete(r.path))
            assert (e.status, e.code) == (405, 'method_not_allowed'), (verb, r.method, r.path)
            # nothing is classified for the foreign verb, so server.py:451's
            # `CLASS.get(..., 'privileged')` still treats the pair as privileged
            assert routes.CLASS.get((verb, r.path), 'privileged') == 'privileged', r.path
    # the four families, by hand: public, observe, authority and privileged all
    # refuse a HEAD or an OPTIONS rather than answering with the GET row
    for verb, path in (('HEAD', '/'), ('OPTIONS', '/assets/app.js'),
                       ('HEAD', '/manifest.webmanifest'), ('OPTIONS', '/v1/health'),
                       ('HEAD', '/v1/missions/' + TOKEN), ('OPTIONS', '/v1/events/stream'),
                       ('HEAD', '/v1/devices/launch/redeem'),
                       ('OPTIONS', '/v1/devices/pair/redeem'), ('HEAD', '/v1/estop'),
                       ('OPTIONS', '/v1/approvals/x/decide')):
        assert _refused(verb, path).status == 405, (verb, path)


# ── 2. an observe row never reaches the writer ──

def test_an_observe_row_never_reaches_a_writer_and_a_writing_row_is_a_command_row():
    writing = set()
    for r in routes.ROUTES:
        bad = _writer_calls(_calls(r.handler))
        if not bad:
            continue
        writing.add((r.method, r.path))
        assert r.method == 'POST', (r.method, r.path, bad)          # a read never writes
        assert routes.CLASS[(r.method, r.path)] in ('privileged', 'authority', 'ordinary'), \
            (r.path, routes.CLASS[(r.method, r.path)], bad)         # never public, never observe
        assert r.scope in ('control', 'approve', 'admin', None), (r.path, r.scope, bad)
        # the only writer with no scope of its own is the one a device credential
        # gates instead of a credential scope, and it is the only one allowed to be
        assert (r.scope is None) == (routes.CLASS[(r.method, r.path)] == 'authority'), \
            (r.path, r.scope, routes.CLASS[(r.method, r.path)], bad)
    observe = {(r.method, r.path) for r in routes.ROUTES if r.scope == 'observe'}
    assert observe & writing == set()
    assert routes.PRIVILEGED & observe == set()
    # the analysis is not vacuous: the commands really are found, and the whole
    # privileged set agrees with it but the five rows named above, which are
    # alive through an Api collaborator and must still reach one
    assert len(writing) == 46
    assert routes.PRIVILEGED - writing == set(COLLABORATOR_ROWS)
    assert writing - routes.PRIVILEGED == {('POST', '/v1/digest/ack')}   # the monotone ack
    for key, verbs in COLLABORATOR_ROWS.items():
        reached = {c.rsplit('.', 1)[-1] for c in _calls(TABLE[key].handler)}
        assert reached & verbs, (key, sorted(reached)[:8])


# ── 3. a literal is a literal ──

def test_a_literal_in_a_path_is_matched_literally_and_never_as_a_regex():
    dotted = sorted({r.path for r in routes.ROUTES if '.' in r.path})
    assert dotted == ['/manifest.webmanifest', '/sw.js'], dotted
    for path in dotted:
        row = next(r for r in routes.ROUTES if r.path == path)
        assert routes.match(row.method, path)[0] is row             # the row itself routes
        for i, ch in enumerate(path):
            if ch != '.':
                continue
            for sub in ('X', '9', '-', ' ', '/'):
                near = path[:i] + sub + path[i + 1:]
                assert _refused(row.method, near).status == 404, (path, near)
    # the wildcard row's base is a literal too: `re.escape(path[:-2])`, routes.py:1362
    assert _refused('GET', '/assetsX/' + TOKEN + '.js').code == 'not_found'
    assert _refused('GET', '/asset/' + TOKEN + '.js').code == 'not_found'
    # the same property on the compiler, where a dropped `re.escape` is invisible
    # to any request that only ever names a real path
    assert routes._compile('/a.b/c').match('/aXb/c') is None
    assert routes._compile('/a.b/{id}').match('/aXb/' + TOKEN) is None
    assert routes._compile('/a.b/{id}').match('/a.b/' + TOKEN).groupdict() == {'id': TOKEN}
    # and a metacharacter inside a PARAMETER is data, not syntax
    route, params = routes.match('GET', '/v1/missions/a.b+c(d)*')
    assert (route.handler, params) == (routes.get_mission, {'id': 'a.b+c(d)*'})


# ── 4. the end anchor is an end ──

@pytest.mark.xfail(strict=True, reason='source defect: the patterns are anchored with '
                     '`$`, which also matches just before a trailing newline, so '
                     '`/v1/health\\n` is routed to `health` and the wildcard swallows '
                     '`/assets/app.js\\n` into `path=\'app.js\'` '
                     '(archeus/api/routes.py:1366 and :1362); the anchor must be `\\Z`')
def test_a_path_that_only_adds_a_trailing_newline_is_not_the_rows_path():
    # Only the anchor itself: the rows whose literal text ends the path. A
    # `{parameter}` row keeps a trailing newline inside the VALUE instead, because
    # `[^/]+` accepts it, which is a different question (parameter charset, not the
    # anchor) and is not asserted here.
    assert routes.match('GET', '/v1/health')[0].handler is routes.health   # control
    for path in ('/v1/health', '/manifest.webmanifest', '/sw.js',
                 '/assets/' + TOKEN + '.js'):
        e = _refused('GET', path + '\n')
        assert (e.status, e.code) == (404, 'not_found'), path
    assert routes._compile('/a.b').match('/a.b\n') is None


# ── 5. one request cannot answer for the next ──

def test_a_refusal_cannot_leave_the_router_answering_for_the_next_request():
    # a 405 first: the `known` of the request that set it must not survive it,
    # or every later unknown path is a 405 (routes.py:1374, `known = False`)
    assert _refused('DELETE', '/v1/missions').status == 405
    assert _refused('GET', '/v1/nothing/here').status == 404
    assert _refused('GET', '/v1/nothing/here/at/all').status == 404
    # and the other way round: a 404 must not steal the 405 from the next request
    assert _refused('GET', '/v1/nothing/here').status == 404
    assert _refused('PATCH', '/v1/estop').status == 405
    # alternating, through a parameter row, a wildcard row and one success between
    assert _refused('POST', '/v1/missions/' + TOKEN).status == 405
    routes.match('GET', '/assets/' + TOKEN + '.js')
    assert _refused('GET', '/v1/nothing/here').status == 404
    assert _refused('PUT', '/v1/automations/' + TOKEN + '/simulate').status == 405
    assert _refused('GET', '/assets').status == 404
    assert routes.match('GET', '/v1/health')[0].handler is routes.health


# ── 6. a path known only through a parameter is still known ──

@pytest.mark.parametrize('verb,path', [
    ('POST', '/v1/missions/' + TOKEN),                      # GET /v1/missions/{id}
    ('PUT', '/v1/tasks/' + TOKEN + '/executions'),           # GET /v1/tasks/{id}/executions
    ('DELETE', '/v1/automations/' + TOKEN + '/simulate'),   # GET /v1/automations/{id}/simulate
    ('POST', '/v1/knowledge/' + TOKEN),                      # GET /v1/knowledge/{id}
    ('GET', '/v1/executions/' + TOKEN + '/stop'),            # POST /v1/executions/{id}/stop
    ('GET', '/v1/missions/' + TOKEN + '/pause'),             # POST /v1/missions/{id}/pause
    ('POST', '/v1/verifications/' + TOKEN),                  # GET /v1/verifications/{id}
], ids=['mission-id', 'task-executions', 'automation-simulate', 'knowledge-id',
        'execution-stop', 'mission-pause', 'verification-id'])
def test_a_path_known_only_through_a_parameter_answers_405_and_never_404(verb, path):
    e = _refused(verb, path)
    assert (e.status, e.code, e.detail) == (405, 'method_not_allowed', {})
    # the path IS known, through a `{parameter}` row: with its own verb it routes,
    # and the parameter is the token, so the 405 above came from that row alone
    row = next(r for r in routes.ROUTES if _concrete(r.path) == path)
    got, params = routes.match(row.method, path)
    assert got is row and set(params) == set(re.findall(r'\{(\w+)\}', row.path))


# ── 7. every row is reachable at its own path ──

def test_every_row_is_the_matchers_own_answer_for_its_path():
    assert len(TABLE) == len(routes.ROUTES)                   # one row per (method, path)
    assert len(routes._COMPILED) == len(routes.ROUTES)
    assert [(r.method, r.path) for r, _rx in routes._COMPILED] == \
        [(r.method, r.path) for r in routes.ROUTES]           # _COMPILED is in table order
    assert all(rx.pattern == routes._compile(r.path).pattern for r, rx in routes._COMPILED)
    for r in routes.ROUTES:
        path = _concrete(r.path)
        got, params = routes.match(r.method, path)
        assert got is r, (r.method, r.path, path, got.method, got.path)   # nothing shadows it
        if r.path.endswith('/*'):
            assert params == {'path': TOKEN + '.js'}, params
        else:
            assert params == {k: TOKEN for k in re.findall(r'\{(\w+)\}', r.path)}, params


# ── 8. a segment that is both a row and an id, and the handler it chooses ──

OVERLAP = (                          # path, the POST row's handler, the GET row's handler
    ('/v1/missions/pause-all', 'pause_all', 'get_mission'),
    ('/v1/missions/resume-all', 'resume_all', 'get_mission'),
    ('/v1/missions/resume', None, 'get_mission'),
    ('/v1/knowledge/forget', 'forget_knowledge', 'get_knowledge'),
    ('/v1/knowledge/consolidate', 'consolidate_knowledge', 'get_knowledge'),
    ('/v1/context/preview', 'preview_context', 'get_context_package'),
)


def test_a_segment_that_is_both_a_row_and_an_id_chooses_the_verb_and_the_handler():
    for path, writer, reader in OVERLAP:
        segment = path.rsplit('/', 1)[-1]
        read_row, read_params = routes.match('GET', path)
        assert read_row.handler.__name__ == reader, path              # the id row reads it
        assert read_row.scope == 'observe', (path, read_row.scope)
        assert read_row.request_schema is None, path                  # a read takes no body
        assert read_params == {'id': segment}, (path, read_params)
        if writer is None:
            assert _refused('POST', path).status == 405, path         # no command row: 405
            continue
        write_row, write_params = routes.match('POST', path)
        assert write_row.handler.__name__ == writer, path              # the literal row wins
        assert write_params == {}, (path, write_params)                # it is not an id
        assert write_row.request_schema is not None, path              # a command has a body
        assert routes.CLASS[('POST', path)] not in ('public', 'authority'), path
        if _writer_calls(_calls(write_row.handler)):
            assert write_row.scope in ('control', 'approve', 'admin'), path
            assert write_row.idempotent == 'required', path            # a submit must be keyed
        else:
            # the one overlap that only looks: a POST row that runs no command is an
            # observe row, with no idempotency key to spend on it
            assert (write_row.scope, write_row.idempotent) == ('observe', None), path


def test_the_batch_the_single_and_the_read_of_one_name_run_what_they_must(monkeypatch):
    seen = []
    monkeypatch.setattr(routes.resources, 'homes', lambda conn, registry, callers: ('homes',))
    monkeypatch.setattr(routes.queries, 'get_mission',
                        lambda conn, id, homes: seen.append(('read', id)) or {'mission': id})
    monkeypatch.setattr(routes.queries, 'get_knowledge',
                        lambda conn, id: seen.append(('know', id)) or {'knowledge': id})

    # POST /v1/missions/pause-all: the batch command, keyed, with no mission id at all
    row, req, out = _drive('POST', '/v1/missions/pause-all', {'idempotency_key': 'key-1'})
    assert (row.handler, out) == (routes.pause_all, (200, {'ok': True}))
    assert len(req.run.calls) == 1
    assert req.run.calls[0].fn == req.api.missions.pause_all           # the batch, not the single
    assert req.run.calls[0].kwargs == {}                               # nothing per-mission
    assert req.run.calls[0].keyed is True

    # POST /v1/missions/{id}/pause: the single command, and never the batch one
    row, req, _o = _drive('POST', '/v1/missions/' + TOKEN + '/pause', {'idempotency_key': 'k'},
                          params={'id': TOKEN})
    assert row.handler is routes.pause_mission
    assert len(req.run.calls) == 1
    assert req.run.calls[0].fn == req.api.missions.pause
    assert req.run.calls[0].kwargs == {'mission_id': TOKEN, 'expected_version': None}

    # GET /v1/missions/pause-all: the read of the same name, and a submit is a failure
    row, req, out = _drive('GET', '/v1/missions/pause-all', params={'id': 'pause-all'},
                           forbid=True)
    assert (row.handler, out) == (routes.get_mission, (200, {'mission': 'pause-all'}))
    assert req.run.calls == [] and req.api.db.reads == 1
    assert seen == [('read', 'pause-all')]

    # POST /v1/knowledge/forget: the command, dry-run by default, keyed
    row, req, _o = _drive('POST', '/v1/knowledge/forget',
                          {'selector': {'project': 'prj_1'}, 'idempotency_key': 'k'})
    assert row.handler is routes.forget_knowledge and len(req.run.calls) == 1
    assert req.run.calls[0].fn is routes.knowledge.forget
    assert req.run.calls[0].kwargs == {'selector': {'project': 'prj_1'}, 'mode': 'retract',
                                       'dry_run': True}

    # GET /v1/knowledge/forget: the read of the same name runs nothing at all
    row, req, out = _drive('GET', '/v1/knowledge/forget', params={'id': 'forget'},
                           forbid=True)
    assert (row.handler, out) == (routes.get_knowledge, (200, {'knowledge': 'forget'}))
    assert req.run.calls == [] and req.api.db.reads == 1
    assert seen[-1] == ('know', 'forget')

    # a malformed body of an owned family is refused by the row's OWN request schema,
    # before any handler and so before any submit: nothing privileged is reached
    for template, body, field, why in (
            ('/v1/missions/{id}/pause', {}, 'idempotency_key', 'is required'),
            ('/v1/knowledge/forget', {'mode': 'purge'}, 'selector', 'is required'),
            ('/v1/knowledge/forget', {'selector': {'project': 'prj_1'},
                                      'idempotency_key': 'k', 'mode': 'sideways'},
             'mode', 'must be one of retract, purge'),
            ('/v1/digest/ack', {}, 'up_to_seq', 'is required')):
        row = TABLE[('POST', template)]
        with pytest.raises(Invalid) as e:
            schemas.validate(body, row.request_schema)
        assert (e.value.field, e.value.why) == (field, why), template


# ── 9. the offline queue stays shut ──

def test_only_the_monotone_digest_ack_may_ever_come_back_from_an_offline_queue():
    assert routes.REPLAYABLE == frozenset({('POST', '/v1/digest/ack')})
    assert routes.REPLAYABLE <= set(TABLE)                          # every key is a real row
    assert not routes.REPLAYABLE & routes.PRIVILEGED                # nothing privileged
    ack = TABLE[('POST', '/v1/digest/ack')]
    assert (ack.method, ack.scope, ack.idempotent) == ('POST', 'control', None)
    assert ack.request_schema is schemas.ACK and ack.response_schema == 'Acked'
    assert routes.CLASS[('POST', '/v1/digest/ack')] == 'ordinary'
    # the class is not shared: it is the answer's monotone-ness, so no other row
    # may join it, and no replayable row may be public, authority or observe
    assert [k for k, c in routes.CLASS.items() if c == 'ordinary'] == [('POST',
                                                                        '/v1/digest/ack')]
    for key in routes.REPLAYABLE:
        assert routes.CLASS[key] not in ('public', 'authority', 'observe', 'privileged'), key
    # the stream anchor the same server branch reads is one GET observe row
    stream = [r for r in routes.ROUTES if r.path == routes.STREAM]
    assert [(r.method, r.scope) for r in stream] == [('GET', 'observe')]


# ── 10. QUERY says what the handlers read ──

def test_the_declared_query_parameters_are_exactly_the_ones_the_handlers_read():
    for path, names in routes.QUERY.items():
        assert ('GET', path) in TABLE, path                           # a real GET row
        assert isinstance(names, tuple) and names, (path, names)
        assert all(isinstance(n, str) and n for n in names), (path, names)
        assert len(set(names)) == len(names), (path, names)           # never named twice
    for r in routes.ROUTES:
        declared = set(routes.QUERY.get(r.path, ()))
        if r.method == 'GET':
            assert _query_names(r.handler) == declared, \
                (r.path, sorted(declared), sorted(_query_names(r.handler)))
        else:
            # a command arrives in its body: nothing read from the query string
            # can steer one, and the docs advertise no query for it either
            assert _query_names(r.handler) == set(), (r.path, sorted(_query_names(r.handler)))
    # the paging and narrowing surfaces the card names, spelled out
    assert routes.QUERY['/v1/events'] == ('after', 'limit')
    assert routes.QUERY['/v1/missions/{id}/timeline'] == ('before', 'limit')
    assert routes.QUERY['/v1/repositories/{id}/inspections'] == ('limit',)
    assert routes.QUERY['/v1/automations/{id}/simulate'] == ('days',)
    assert routes.QUERY['/v1/executions/{id}/stream'] == ('from',)
