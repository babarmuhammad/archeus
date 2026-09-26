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
inspections and the digest. P5 adds the context package and its preview
(p5-design-gate §6): the preview is a POST because it carries a request, and it
writes nothing, so it takes no idempotency key. P6 adds knowledge (its
lifecycle, forget, feedback), meeting import (admin: it reads a file), the
route decisions of Archeus's own calls, and the provider-terms answer
(ADR-0021; admin, and only the user may give it) (p6-design-gate §9). P7 adds
the conversation (a posted message is read by the intent worker; the reply
arrives as `message.created`), the intents, the challenge choice and the ideas
(p7-design-gate §9). P8 adds two reads: a mission's plan (the version in force
and every version) and one exact plan version — no command: planning is the
planning worker's, and editing a plan is P16's (p8-design-gate §19).

Deliberately absent (a test pins the table): cancel, accept, request-changes,
approvals (P9), executions and routing (P10, P11), `/v1/now` and the execution
stream (P16), pairing and a device list (P15), hooks (P11), a manual
re-inspect (the world worker covers it), `/v1/world/graph` (P18) and the rest
of knowledge (P6).
"""

import re
from collections import namedtuple

from ..core.application import commands, queries, world
from ..core.application import calls as own_calls
from ..core.application import conversation, knowledge, resources
from ..core.context import assemble as context
from ..core.knowledge import ingest
from ..harnesses.calls import real_callers
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


def get_mission_plan(req):
    with req.api.db.read() as conn:
        return 200, queries.mission_plan(conn, req.params['id'])


def get_plan(req):
    with req.api.db.read() as conn:
        return 200, queries.get_plan(conn, req.params['id'])


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


def get_context_package(req):
    with req.api.db.read() as conn:
        return 200, queries.get_context_package(conn, req.params['id'])


def preview_context(req):
    b = req.body
    kw = {k: b[k] for k in ('query', 'levels', 'limit_tokens') if b.get(k) is not None}
    if 'limit_tokens' in kw and kw['limit_tokens'] < 1:
        raise Invalid('limit_tokens', 'is an integer >= 1')
    with req.api.db.read() as conn:
        return 200, context.assemble(conn, b['subject']['kind'], b['subject']['id'], **kw)


def list_knowledge(req):
    with req.api.db.read() as conn:
        return 200, {'knowledge': queries.list_knowledge(
            conn, _one(req.query, 'project'), _one(req.query, 'state'), _one(req.query, 'type'))}


def get_knowledge(req):
    with req.api.db.read() as conn:
        return 200, queries.get_knowledge(conn, req.params['id'])


def _move(req):
    kw = {'knowledge_item_id': req.params['id']}
    for k in ('reason', 'expected_version'):
        if req.body.get(k) is not None:
            kw[k] = req.body[k]
    return kw


def confirm_knowledge(req):
    return 200, req.run(knowledge.confirm, _move(req))


def reject_knowledge(req):
    return 200, req.run(knowledge.reject, _move(req))


def retract_knowledge(req):
    return 200, req.run(knowledge.retract, _move(req))


def supersede_knowledge(req):
    return 200, req.run(knowledge.supersede, {'knowledge_item_id': req.params['id'],
                                              'title': req.body['title'],
                                              'text': req.body.get('text') or ''})


def forget_knowledge(req):
    b = req.body
    return 200, req.run(knowledge.forget, {
        'selector': b['selector'], 'mode': b.get('mode') or 'retract',
        'dry_run': True if b.get('dry_run') is None else b['dry_run']})


def record_feedback(req):
    b = req.body
    return 200, req.run(knowledge.record_feedback, {
        'subject': b['subject'], 'signal': b['signal'], 'text': b.get('text') or '',
        'promote': b.get('promote')})


def import_meeting(req):
    b = req.body
    n = ingest.read_notes(b['path'], b.get('held_at'),
                          allow_undated=b.get('allow_undated') is True)
    return 200, req.run(knowledge.import_meeting, {
        'name': n['name'], 'held_at': n['held_at'], 'notes_sha256': n['sha256'],
        'notes_size': n['size'], 'imported_from': n['path'], 'project_id': b.get('project_id')})


def list_route_decisions(req):
    with req.api.db.read() as conn:
        return 200, {'route_decisions': queries.route_decisions(
            conn, _one(req.query, 'source'), _one(req.query, 'purpose'))}


def get_route_decision(req):
    with req.api.db.read() as conn:
        return 200, queries.get_route_decision(conn, req.params['id'])


def list_provider_terms(req):
    with req.api.db.read() as conn:
        return 200, {'provider_terms': queries.provider_terms(
            conn, [c.id for c in real_callers()])}


def decide_provider_terms(req):
    b = req.body
    return 200, req.run(own_calls.decide_provider_terms, {
        'harness_id': req.params['id'], 'headless': b['headless'],
        'rotation': b.get('rotation'), 'note': b.get('note') or ''})


def list_accounts(req):
    with req.api.db.read() as conn:
        return 200, {'accounts': resources.accounts(conn)}


def register_account(req):
    """The adapter probes the login first (outside any transaction); the
    command records the account and the probe's answer."""
    b = req.body
    probe = req.api.resources.probe(b['harness_id'], b.get('home_ref'))
    return 200, req.run(resources.register_account, {
        'harness_id': b['harness_id'], 'label': b['label'], 'auth_kind': b['auth_kind'],
        'home_ref': b.get('home_ref'), 'auth': probe})


def set_account_state(req):
    b = req.body
    with req.api.db.read() as conn:
        a = queries.get_account(conn, req.params['id'])
    probe = req.api.resources.probe(a['harness_id'], a['home_ref']) if b['enabled'] else None
    return 200, req.run(resources.set_account_enabled, {
        'account_id': req.params['id'], 'enabled': b['enabled'], 'auth': probe})


def set_resource_policy(req):
    b = req.body
    return 200, req.run(resources.set_resource_policy, dict(
        {k: b.get(k) for k in resources.POLICY_FIELDS},
        account_id=req.params['id'], expected_version=b.get('expected_version')))


def list_harnesses(req):
    return 200, {'harnesses': req.api.resources.harnesses()}


def set_mission_resources(req):
    b = req.body
    return 200, req.run(resources.set_mission_resources, {
        'mission_id': req.params['id'],
        'preferences': {k: b[k] for k in ('preferred_accounts', 'preferred_harnesses',
                                          'forbidden_accounts', 'forbidden_harnesses',
                                          'max_cost_band') if b.get(k) is not None}})


def list_messages(req):
    with req.api.db.read() as conn:
        return 200, {'messages': queries.messages(conn, req.params['id'],
                                                  _one(req.query, 'after'))}


def post_message(req):
    b = req.body
    return 200, req.run(conversation.post_message, {
        'text': b['text'], 'conversation_id': req.params['id'],
        'in_reply_to': b.get('in_reply_to')})


def get_intent(req):
    with req.api.db.read() as conn:
        return 200, queries.get_intent(conn, req.params['id'])


def clarify_intent(req):
    """A challenge's choice (`proceed` | `drop`), or the answer to a
    clarification as `text` — posted as a reply to the question, which the
    intent worker reads with the question in view."""
    b = req.body
    if (b.get('choice') is None) == (b.get('text') is None):
        raise Invalid('choice', 'give exactly one of choice and text')
    if b.get('choice') is not None:
        return 200, req.run(req.api.conversations.choose, {'intent_id': req.params['id'],
                                                           'choice': b['choice']})
    with req.api.db.read() as conn:
        asked = queries.question_of(conn, req.params['id'])
    out = req.run(conversation.post_message, {
        'text': b['text'], 'conversation_id': asked['conversation_id'],
        'in_reply_to': asked['id']})
    return 200, {'reply_id': None, 'intent_id': None, 'resolution': None,
                 'message_id': out['message_id']}


def list_ideas(req):
    with req.api.db.read() as conn:
        return 200, {'ideas': queries.list_ideas(conn, _one(req.query, 'state'))}


# ── policy and approvals (P9, p9-design-gate §18) ──

def get_policies(req):
    with req.api.db.read() as conn:
        return 200, queries.policies(conn)


def create_rule(req):
    b = req.body
    return 200, req.run(req.api.authorization.create_rule, {
        k: b.get(k) for k in ('scope_level', 'scope_ref', 'action_class', 'decision', 'locked',
                              'match', 'boundary', 'expires_at', 'supersedes_rule_id')}
        | {'outside': b.get('outside') or 'ASK', 'note': b.get('note') or ''})


def retire_rule(req):
    return 200, req.run(req.api.authorization.retire_rule, {'rule_id': req.params['id']})


def set_profile(req):
    b = req.body
    return 200, req.run(req.api.authorization.set_profile, {
        'scope': b['scope'], 'profile': b['profile'], 'mission_id': b.get('mission_id')})


def simulate_policy(req):
    b = req.body
    with req.api.db.read() as conn:
        return 200, req.api.authorization.simulate(
            conn, now=queries._now(), action=b['action'], mission_id=b.get('mission_id'),
            task_id=b.get('task_id'), stage=b.get('stage') or 'plan',
            extra_rules=b.get('extra_rules') or ())


def list_policy_decisions(req):
    with req.api.db.read() as conn:
        return 200, {'policy_decisions': queries.list_policy_decisions(
            conn, _one(req.query, 'mission'), _one(req.query, 'stage'))}


def get_policy_decision(req):
    with req.api.db.read() as conn:
        return 200, queries.get_policy_decision(conn, req.params['id'])


def list_approvals(req):
    with req.api.db.read() as conn:
        return 200, {'approvals': queries.list_approvals(
            conn, _one(req.query, 'state'), _one(req.query, 'mission'))}


def get_approval(req):
    with req.api.db.read() as conn:
        return 200, queries.get_approval(conn, req.params['id'])


def decide_approval(req):
    """The client echoes the `action_hash` it displayed (X02). A DENY found at
    approve time is recorded and answered `423 policy_denied`."""
    b = req.body
    out = req.run(req.api.authorization.decide, {
        'approval_id': req.params['id'], 'decision': b['decision'],
        'action_hash': b['action_hash'], 'note': b.get('note'), 'step_up': b.get('step_up'),
        'expected_version': b.get('expected_version')})
    if out.get('denied'):
        raise Refused(423, 'policy_denied', dict(out['denied'], approval_id=out['approval_id']))
    return 200, out


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
    Route('GET', '/v1/missions/{id}/plan', get_mission_plan, 'observe', None, None,
          'MissionPlan'),
    Route('GET', '/v1/plans/{id}', get_plan, 'observe', None, None, 'Plan'),
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
    # ── context (P5) ──
    Route('GET', '/v1/context/{id}', get_context_package, 'observe', None, None,
          'ContextPackage'),
    Route('POST', '/v1/context/preview', preview_context, 'observe', None,
          schemas.CONTEXT_PREVIEW, 'ContextPreview'),
    # ── knowledge and own calls (P6) ──
    Route('GET', '/v1/knowledge', list_knowledge, 'observe', None, None, 'KnowledgeList'),
    Route('GET', '/v1/knowledge/{id}', get_knowledge, 'observe', None, None,
          'KnowledgeDetail'),
    Route('POST', '/v1/knowledge/{id}/confirm', confirm_knowledge, 'control', 'required',
          schemas.KNOWLEDGE_MOVE, 'KnowledgeChanged'),
    Route('POST', '/v1/knowledge/{id}/reject', reject_knowledge, 'control', 'required',
          schemas.KNOWLEDGE_MOVE, 'KnowledgeChanged'),
    Route('POST', '/v1/knowledge/{id}/retract', retract_knowledge, 'control', 'required',
          schemas.KNOWLEDGE_MOVE, 'KnowledgeChanged'),
    Route('POST', '/v1/knowledge/{id}/supersede', supersede_knowledge, 'control', 'required',
          schemas.SUPERSEDE, 'KnowledgeChanged'),
    Route('POST', '/v1/knowledge/forget', forget_knowledge, 'control', 'required',
          schemas.FORGET, 'Forgotten'),
    Route('POST', '/v1/feedback', record_feedback, 'control', 'required', schemas.FEEDBACK,
          'FeedbackRecorded'),
    Route('POST', '/v1/meetings/import', import_meeting, 'admin', 'required',
          schemas.IMPORT_MEETING, 'MeetingImported'),
    Route('GET', '/v1/route-decisions', list_route_decisions, 'observe', None, None,
          'RouteDecisionList'),
    Route('GET', '/v1/route-decisions/{id}', get_route_decision, 'observe', None, None,
          'RouteDecision'),
    Route('GET', '/v1/provider-terms', list_provider_terms, 'observe', None, None,
          'ProviderTermsList'),
    Route('POST', '/v1/provider-terms/{id}', decide_provider_terms, 'admin', 'required',
          schemas.PROVIDER_TERMS, 'ProviderTermsDecided'),
    # P10: resources and routing (p10-design-gate §10)
    Route('GET', '/v1/harnesses', list_harnesses, 'observe', None, None, 'HarnessList'),
    Route('GET', '/v1/accounts', list_accounts, 'observe', None, None, 'AccountList'),
    Route('POST', '/v1/accounts', register_account, 'admin', 'required',
          schemas.REGISTER_ACCOUNT, 'Account'),
    Route('POST', '/v1/accounts/{id}/state', set_account_state, 'admin', 'required',
          schemas.ACCOUNT_STATE, 'Account'),
    Route('POST', '/v1/resource-policies/{id}', set_resource_policy, 'admin', 'required',
          schemas.RESOURCE_POLICY, 'ResourcePolicy'),
    Route('POST', '/v1/missions/{id}/resources', set_mission_resources, 'admin', 'required',
          schemas.MISSION_RESOURCES, 'Mission'),
    # P7: conversation and intent (p7-design-gate §9)
    Route('GET', '/v1/conversations/{id}/messages', list_messages, 'observe', None, None,
          'MessageList'),
    Route('POST', '/v1/conversations/{id}/messages', post_message, 'control', 'required',
          schemas.POST_MESSAGE, 'MessagePosted'),
    Route('GET', '/v1/intents/{id}', get_intent, 'observe', None, None, 'Intent'),
    Route('POST', '/v1/intents/{id}/clarify', clarify_intent, 'control', 'required',
          schemas.CLARIFY, 'Replied'),
    Route('GET', '/v1/ideas', list_ideas, 'observe', None, None, 'IdeaList'),
    Route('GET', '/v1/policies', get_policies, 'observe', None, None, 'Policies'),
    Route('POST', '/v1/policies/rules', create_rule, 'admin', 'required',
          schemas.CREATE_RULE, 'RuleWritten'),
    Route('POST', '/v1/policies/rules/{id}/retire', retire_rule, 'admin', 'required',
          schemas.KEYED, 'RuleWritten'),
    Route('POST', '/v1/policies/profile', set_profile, 'admin', 'required',
          schemas.SET_PROFILE, 'ProfileSet'),
    Route('POST', '/v1/policies/simulate', simulate_policy, 'observe', None, schemas.SIMULATE,
          'Simulation'),
    Route('GET', '/v1/policy-decisions', list_policy_decisions, 'observe', None, None,
          'PolicyDecisionList'),
    Route('GET', '/v1/policy-decisions/{id}', get_policy_decision, 'observe', None, None,
          'PolicyDecision'),
    Route('GET', '/v1/approvals', list_approvals, 'observe', None, None, 'ApprovalList'),
    Route('GET', '/v1/approvals/{id}', get_approval, 'observe', None, None, 'Approval'),
    Route('POST', '/v1/approvals/{id}/decide', decide_approval, 'approve', 'required',
          schemas.DECIDE, 'Decided'),
)

#: The query parameters each GET route reads (for the docs and the client).
QUERY = {'/v1/missions': ('state', 'project'), '/v1/events': ('after', 'limit'),
         '/v1/events/stream': ('after',), '/v1/status': ('project',),
         '/v1/repositories/{id}/inspections': ('limit',),
         '/v1/knowledge': ('project', 'state', 'type'),
         '/v1/route-decisions': ('source', 'purpose'),
         '/v1/conversations/{id}/messages': ('after',), '/v1/ideas': ('state',),
         '/v1/policy-decisions': ('mission', 'stage'), '/v1/approvals': ('state', 'mission')}

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
