"""THE route table (api-and-realtime §1, p3.5b design gate §5.1) — all of it.

Each row is `(method, path, handler, scope, idempotent, request_schema,
response_schema)`. `scope` is the credential scope the route needs (None:
public — only the static SPA and `launch/redeem`, which authenticates by its
code). `idempotent` is 'required' for a command that must carry an
`idempotency_key`, 'exempt' for `launch/*` (a response holding a secret must
not be stored in `idempotency_keys`), None for a read. The docs and the
TypeScript client are generated from this table (tools/gen_api_docs.py).

A handler only ever runs one application command through the writer
(`req.run`) or one query inside `Database.read()`. It never moves an
entity itself, never evaluates policy and never branches on an actor's kind:
those are the application layer's, and P9's.

P4 adds the world (p4-design-gate §10): status, projects, constraints,
inspections and the digest.

Deliberately absent (a test pins the table): cancel, accept, request-changes,
approvals (P9), executions and routing (P10, P11), `/v1/now` and the execution
stream (P16), pairing and a device list (P15), hooks (P11), a manual
re-inspect (the world worker covers it), `/v1/world/graph` (P18) and the rest
of knowledge (P6).
"""

import re
from collections import namedtuple

from ..core.application import commands, queries, world
from ..core.world import digest as world_digest
from ..core.world import status as world_status
from . import auth, schemas
from .schemas import Invalid

Route = namedtuple('Route', 'method path handler scope idempotent request_schema '
                            'response_schema')


class Refused(Exception):
    """A request refused at the HTTP layer: `status` + `code` (+ detail)."""

    def __init__(self, status, code, detail=None, headers=None):
        super().__init__('%s %s' % (status, code))
        self.status, self.code, self.detail = status, code, detail or {}
        self.headers = headers or {}


def _one(query, name):
    values = query.get(name)
    return None if not values else values[-1]


def _cursor(raw, field):
    if raw is None or not re.fullmatch(r'\d{1,18}', raw):
        raise Invalid(field, 'is an integer >= 0')
    return int(raw)


def _loopback(req):
    if not auth.loopback_peer(req.peer):
        raise Refused(403, 'host_not_allowed', {'why': 'only from this machine'})


# ── handlers ──

def static_index(req):
    return req.api.static.index()


def static_asset(req):
    return req.api.static.asset(req.params['path'])


def health(req):
    return 200, req.api.health()


def version(req):
    return 200, {'version': req.api.version, 'api': 'v1'}


def list_missions(req):
    with req.api.db.read() as conn:
        return 200, {'missions': queries.list_missions(conn, _one(req.query, 'state'),
                                                       _one(req.query, 'project'))}


def get_mission(req):
    with req.api.db.read() as conn:
        return 200, queries.get_mission(conn, req.params['id'])


def create_mission(req):
    b = req.body
    return 200, req.run(commands.create_mission, {
        'title': b['title'], 'objective': b['objective'], 'project_id': b.get('project_id'),
        'success_criteria': b.get('success_criteria', [])})


def pause_mission(req):
    return 200, req.run(req.api.missions.pause, {'mission_id': req.params['id']})


def resume_mission(req):
    return 200, req.run(req.api.missions.resume, {'mission_id': req.params['id']})


def events(req):
    after = _cursor(_one(req.query, 'after') or '0', 'cursor')
    raw = _one(req.query, 'limit')
    limit = 500 if raw is None else _cursor(raw, 'limit')
    if not 1 <= limit <= 1000:
        raise Invalid('limit', 'is 1..1000')
    with req.api.db.read() as conn:
        return 200, {'events': queries.events(conn, after, limit=limit)}


def events_stream(req):
    raw = req.headers.get('Last-Event-ID')      # a reconnect carries it: it wins
    if raw is None:
        raw = _one(req.query, 'after')
    return req.api.sse.serve(req, None if raw is None else _cursor(raw, 'cursor'))


def launch_code(req):
    _loopback(req)
    code = req.api.launch.mint(req.principal['principal_id'], req.principal['device_id'])
    return 200, {'code': code, 'expires_in': int(auth.LAUNCH_TTL_S)}


def launch_redeem(req):
    _loopback(req)
    minter = req.api.launch.redeem(req.body['code'])
    if minter is None:
        raise Refused(401, 'invalid_launch_code')
    # the token is made here and only its hash enters the command, which runs
    # with no idempotency key: nothing stores the response that carries it (A4)
    token = auth.new_token()
    out = req.run(commands.register_device, {
        'name': 'browser (%s)' % req.body['platform'], 'platform': req.body['platform'],
        'token_hash': auth.token_hash(token), 'scopes': list(auth.LAUNCH_SCOPES)},
        actor_id=minter[0], keyed=False)
    return 200, {'device_id': out['device_id'], 'token': token}


def status(req):
    with req.api.db.read() as conn:
        return 200, world_status.status(conn, _one(req.query, 'project'))


def list_projects(req):
    with req.api.db.read() as conn:
        return 200, {'projects': world_status.projects(conn)}


def get_project(req):
    with req.api.db.read() as conn:
        return 200, world_status.project(conn, req.params['id'])


def create_project(req):
    return 200, req.run(world.create_project, {'name': req.body['name'],
                                               'root_paths': req.body['root_paths']})


def declare_constraint(req):
    b = req.body
    return 200, req.run(world.declare_constraint, {
        'project_id': req.params['id'], 'statement': b['statement'],
        'kind': b.get('kind'), 'spec': b.get('spec')})


def list_inspections(req):
    raw = _one(req.query, 'limit')
    limit = 50 if raw is None else _cursor(raw, 'limit')
    if not 1 <= limit <= 500:
        raise Invalid('limit', 'is 1..500')
    with req.api.db.read() as conn:
        return 200, {'inspections': world_status.inspections(conn, req.params['id'], limit)}


def digest(req):
    with req.api.db.read() as conn:
        return 200, world_digest.digest(conn)


def ack_digest(req):
    return 200, req.run(world.ack_digest, {'up_to_seq': req.body['up_to_seq']}, keyed=False)


def revoke_device(req):
    out = req.run(commands.revoke_device, {'device_id': req.params['id']})
    req.api.sse.close_device(req.params['id'])          # before we answer (§3 D2)
    return 200, out


ROUTES = (
    Route('GET', '/', static_index, None, None, None, None),
    Route('GET', '/assets/*', static_asset, None, None, None, None),
    Route('GET', '/v1/health', health, 'observe', None, None, 'Health'),
    Route('GET', '/v1/version', version, 'observe', None, None, 'Version'),
    Route('GET', '/v1/missions', list_missions, 'observe', None, None, 'MissionList'),
    Route('GET', '/v1/missions/{id}', get_mission, 'observe', None, None, 'Mission'),
    Route('POST', '/v1/missions', create_mission, 'control', 'required',
          schemas.CREATE_MISSION, 'Created'),
    Route('POST', '/v1/missions/{id}/pause', pause_mission, 'control', 'required',
          schemas.KEYED, 'CommandResult'),
    Route('POST', '/v1/missions/{id}/resume', resume_mission, 'control', 'required',
          schemas.KEYED, 'CommandResult'),
    Route('GET', '/v1/events', events, 'observe', None, None, 'EventPage'),
    Route('GET', '/v1/events/stream', events_stream, 'observe', None, None, 'StreamFrame'),
    Route('POST', '/v1/devices/launch/code', launch_code, 'admin', 'exempt', schemas.EMPTY,
          'LaunchCode'),
    Route('POST', '/v1/devices/launch/redeem', launch_redeem, None, 'exempt', schemas.REDEEM,
          'Redeemed'),
    Route('POST', '/v1/devices/{id}/revoke', revoke_device, 'admin', 'required', schemas.KEYED,
          'CommandResult'),
    # ── the world (P4) ──
    Route('GET', '/v1/status', status, 'observe', None, None, 'Status'),
    Route('GET', '/v1/projects', list_projects, 'observe', None, None, 'ProjectList'),
    Route('GET', '/v1/projects/{id}', get_project, 'observe', None, None, 'Project'),
    Route('POST', '/v1/projects', create_project, 'admin', 'required', schemas.CREATE_PROJECT,
          'ProjectCreated'),
    Route('POST', '/v1/projects/{id}/constraints', declare_constraint, 'control', 'required',
          schemas.DECLARE_CONSTRAINT, 'ConstraintDeclared'),
    Route('GET', '/v1/repositories/{id}/inspections', list_inspections, 'observe', None, None,
          'InspectionList'),
    Route('GET', '/v1/digest', digest, 'observe', None, None, 'Digest'),
    Route('POST', '/v1/digest/ack', ack_digest, 'control', None, schemas.ACK, 'Acked'),
)

#: The query parameters each GET route reads (for the docs and the client).
QUERY = {'/v1/missions': ('state', 'project'), '/v1/events': ('after', 'limit'),
         '/v1/events/stream': ('after',), '/v1/status': ('project',),
         '/v1/repositories/{id}/inspections': ('limit',)}

STREAM = '/v1/events/stream'


def _compile(path):
    if path.endswith('/*'):
        return re.compile('^%s/(?P<path>.+)$' % re.escape(path[:-2]))
    parts = re.split(r'\{(\w+)\}', path)
    rx = ''.join(re.escape(p) if i % 2 == 0 else '(?P<%s>[^/]+)' % p
                 for i, p in enumerate(parts))
    return re.compile('^%s$' % rx)


_COMPILED = [(r, _compile(r.path)) for r in ROUTES]


def match(method, path):
    """(route, params) for a request; raises Refused 404 / 405."""
    known = False
    for route, rx in _COMPILED:
        m = rx.match(path)
        if m:
            known = True
            if route.method == method:
                return route, m.groupdict()
    if known:
        raise Refused(405, 'method_not_allowed')
    raise Refused(404, 'not_found')
