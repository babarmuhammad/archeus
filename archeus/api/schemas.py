"""Request and response shapes for the route table (p3.5b §5.1, A11).

Plain dicts in a small JSON-Schema-like subset, because two consumers read the
same declaration: the route boundary validates a request body's SHAPE against
it (domain validation stays in the entities), and tools/gen_api_docs.py turns
it into TypeScript types and the API reference. A shape written twice drifts.

    {'type': 'object', 'properties': {...}, 'required': [...]}  (no extra keys)
    {'type': 'string' | 'integer' | 'number' | 'boolean', 'enum'?: [...]}
    {'type': 'array', 'items': <schema>}
    {'ref': '<name in TYPES>'}          a named type
    'nullable': True                    also accepts null
    {'type': 'object'} with no properties: any JSON object
"""

from ..core.context.levels import LEVELS, STORES
from ..core.domain import entities, shapes, states
from ..core.domain.shapes import Invalid  # noqa: F401 (re-exported)
from ..core.domain.values import ORIGINS

KEY = {'type': 'string'}

#: Named types, emitted as TypeScript interfaces.
TYPES = {
    'Criterion': {'type': 'object', 'properties': {
        'text': {'type': 'string'},
        'check': {'type': 'string', 'enum': list(entities.CRITERION_CHECKS)},
        'origin': {'type': 'string', 'enum': list(ORIGINS)}},
        'required': ['text', 'check']},
    'Mission': {'type': 'object', 'open': True, 'properties': {
        'id': {'type': 'string'}, 'state': {'type': 'string',
                                            'enum': sorted(states.states('mission'))},
        'title': {'type': 'string'}, 'objective': {'type': 'string'},
        'workspace_id': {'type': 'string'}, 'project_id': {'type': 'string', 'nullable': True},
        'version': {'type': 'integer'}, 'created_at': {'type': 'string'},
        'updated_at': {'type': 'string'}},
        'required': ['id', 'state', 'title', 'objective', 'version', 'created_at',
                     'updated_at']},
    'Transition': {'type': 'object', 'properties': {
        'from': {'type': 'string'}, 'to': {'type': 'string'}, 'trigger': {'type': 'string'},
        'seq': {'type': 'integer'}}, 'required': ['from', 'to', 'trigger', 'seq']},
    'CommandResult': {'type': 'object', 'properties': {
        'id': {'type': 'string'}, 'state': {'type': 'string'}, 'version': {'type': 'integer'},
        'changed': {'type': 'boolean'}, 'seq': {'type': 'integer', 'nullable': True},
        'transitions': {'type': 'array', 'items': {'ref': 'Transition'}}},
        'required': ['id', 'state', 'version', 'changed', 'seq', 'transitions']},
    'Created': {'type': 'object', 'properties': {
        'id': {'type': 'string'}, 'state': {'type': 'string'}, 'version': {'type': 'integer'},
        'seq': {'type': 'integer'}}, 'required': ['id', 'state', 'version', 'seq']},
    'Event': {'type': 'object', 'properties': {
        'seq': {'type': 'integer'}, 'id': {'type': 'string'}, 'type': {'type': 'string'},
        'at': {'type': 'string'},
        'actor': {'type': 'object', 'properties': {'kind': {'type': 'string'},
                                                   'id': {'type': 'string'}},
                  'required': ['kind', 'id']},
        'cause_chain': {'type': 'array', 'items': {'type': 'string'}},
        'subject': {'ref': 'Subject'},
        'scope': {'ref': 'Scope'},
        'visibility': {'type': 'string', 'enum': ['user', 'system']},
        'payload': {'type': 'object'}},
        'required': ['seq', 'id', 'type', 'at', 'actor', 'cause_chain', 'subject', 'scope',
                     'visibility', 'payload']},
    'Subject': {'type': 'object', 'properties': {'kind': {'type': 'string'},
                                                 'id': {'type': 'string'}},
                'required': ['kind', 'id']},
    'Scope': {'type': 'object', 'properties': {
        'workspace': {'type': 'string'}, 'project': {'type': 'string', 'nullable': True}},
        'required': ['workspace', 'project']},
    'StreamFrame': {'type': 'object', 'properties': {'subject': {'ref': 'Subject'},
                                                     'scope': {'ref': 'Scope'}},
                    'required': ['subject', 'scope']},
    'Health': {'type': 'object', 'properties': {
        'core': {'type': 'object', 'properties': {
            'pid': {'type': 'integer'}, 'started_at': {'type': 'string'},
            'version': {'type': 'string'}, 'schema': {'type': 'integer'},
            'ports': {'type': 'string', 'enum': ['stub', 'real']}},
            'required': ['pid', 'started_at', 'version', 'schema', 'ports']},
        'engine': {'type': 'object', 'properties': {
            'state': {'type': 'string', 'enum': ['starting', 'reconciling', 'running', 'idle',
                                                 'failed', 'stopped']},
            'observed_seq': {'type': 'integer'}, 'parked': {'type': 'integer'}},
            'required': ['state', 'observed_seq', 'parked']},
        'world': {'type': 'object', 'properties': {
            'state': {'type': 'string', 'enum': ['starting', 'reconciling', 'running', 'idle',
                                                 'failed', 'stopped']},
            'pending': {'type': 'integer'}}, 'required': ['state', 'pending']},
        'knowledge': {'type': 'object', 'properties': {
            'state': {'type': 'string', 'enum': ['starting', 'reconciling', 'running', 'idle',
                                                 'failed', 'stopped']},
            'pending': {'type': 'integer'}}, 'required': ['state', 'pending']}},
        'required': ['core', 'engine', 'world', 'knowledge']},
    'Version': {'type': 'object', 'properties': {'version': {'type': 'string'},
                                                 'api': {'type': 'string'}},
                'required': ['version', 'api']},
    'MissionList': {'type': 'object', 'properties': {
        'missions': {'type': 'array', 'items': {'ref': 'Mission'}}}, 'required': ['missions']},
    'EventPage': {'type': 'object', 'properties': {
        'events': {'type': 'array', 'items': {'ref': 'Event'}}}, 'required': ['events']},
    'LaunchCode': {'type': 'object', 'properties': {'code': {'type': 'string'},
                                                    'expires_in': {'type': 'integer'}},
                   'required': ['code', 'expires_in']},
    'Redeemed': {'type': 'object', 'properties': {'device_id': {'type': 'string'},
                                                  'token': {'type': 'string'}},
                 'required': ['device_id', 'token']},
    # ── the world (P4, p4-design-gate §8-§10) ──
    'Finding': {'type': 'object', 'open': True, 'properties': {
        'constraint_id': {'type': 'string'}, 'constraint': {'type': 'string'},
        'kind': {'type': 'string', 'nullable': True,
                 'enum': sorted(entities.CONSTRAINT_SPECS)},
        'status': {'type': 'string', 'enum': ['violated', 'satisfied', 'unchecked']},
        'reason': {'type': 'string', 'nullable': True},
        'violations': {'type': 'array', 'items': {'type': 'array',
                                                  'items': {'type': 'string'}}},
        'violation_count': {'type': 'integer'}},
        'required': ['constraint_id', 'constraint', 'kind', 'status', 'reason', 'violations',
                     'violation_count']},
    'Repository': {'type': 'object', 'open': True, 'properties': {
        'id': {'type': 'string'}, 'project_id': {'type': 'string'}, 'path': {'type': 'string'},
        'kind': {'type': 'string', 'enum': ['repo', 'submodule', 'worktree']},
        'architecture_state': {'type': 'string', 'enum': list(states.states('architecture'))},
        'last_revision': {'type': 'string', 'nullable': True},
        'last_inspection_id': {'type': 'string', 'nullable': True},
        'findings': {'type': 'array', 'items': {'ref': 'Finding'}},
        'version': {'type': 'integer'}},
        'required': ['id', 'project_id', 'path', 'kind', 'architecture_state', 'version']},
    'Project': {'type': 'object', 'open': True, 'properties': {
        'id': {'type': 'string'}, 'name': {'type': 'string'},
        'state': {'type': 'string', 'enum': ['ACTIVE', 'ARCHIVED']},
        'root_paths': {'type': 'array', 'items': {'type': 'string'}},
        'repositories': {'type': 'array', 'items': {'ref': 'Repository'}},
        'version': {'type': 'integer'}},
        'required': ['id', 'name', 'state', 'root_paths', 'version']},
    'ProjectList': {'type': 'object', 'properties': {
        'projects': {'type': 'array', 'items': {'ref': 'Project'}}}, 'required': ['projects']},
    'ProjectCreated': {'type': 'object', 'properties': {
        'project': {'ref': 'Project'},
        'repositories': {'type': 'array', 'items': {'ref': 'Repository'}}},
        'required': ['project', 'repositories']},
    'KnowledgeItem': {'type': 'object', 'open': True, 'properties': {
        'id': {'type': 'string'}, 'type': {'type': 'string'}, 'title': {'type': 'string'},
        'state': {'type': 'string', 'enum': list(states.states('knowledge_item'))},
        'constraint': {'type': 'object', 'nullable': True}, 'version': {'type': 'integer'}},
        'required': ['id', 'type', 'title', 'state', 'version']},
    'ConstraintDeclared': {'type': 'object', 'properties': {
        'knowledge_item': {'ref': 'KnowledgeItem'}, 'changed': {'type': 'boolean'},
        'stale': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['knowledge_item', 'changed', 'stale']},
    'Inspection': {'type': 'object', 'open': True, 'properties': {
        'id': {'type': 'string'}, 'repository_id': {'type': 'string'},
        'revision': {'type': 'string', 'nullable': True},
        'extractor_version': {'type': 'integer'},
        'state': {'type': 'string', 'enum': list(states.states('repository_inspection'))},
        'attempts': {'type': 'integer'}, 'failure': {'type': 'string', 'nullable': True},
        'version': {'type': 'integer'}},
        'required': ['id', 'repository_id', 'revision', 'extractor_version', 'state',
                     'attempts', 'version']},
    'InspectionList': {'type': 'object', 'properties': {
        'inspections': {'type': 'array', 'items': {'ref': 'Inspection'}}},
        'required': ['inspections']},
    'Status': {'type': 'object', 'properties': {
        'source': {'type': 'string', 'enum': ['deterministic']},
        'as_of_seq': {'type': 'integer'},
        'projects': {'type': 'array', 'items': {'type': 'object'}},
        'missions': {'type': 'array', 'items': {'ref': 'Mission'}},
        'drift': {'type': 'array', 'items': {'ref': 'Finding'}},
        'unchecked': {'type': 'array', 'items': {'ref': 'Finding'}},
        'unknown_project': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['source', 'as_of_seq', 'projects', 'missions', 'drift', 'unchecked',
                     'unknown_project']},
    'DigestGroup': {'type': 'object', 'properties': {
        'ref': {'ref': 'Subject'},
        'headline': {'type': 'string', 'enum': ['needs_you', 'drift_found', 'failed',
                                                'completed', 'drift_cleared', 'progressed']},
        'count': {'type': 'integer'}, 'first_seq': {'type': 'integer'},
        'last_seq': {'type': 'integer'}, 'project_id': {'type': 'string', 'nullable': True},
        'types': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['ref', 'headline', 'count', 'first_seq', 'last_seq', 'project_id',
                     'types']},
    'Digest': {'type': 'object', 'properties': {
        'from_seq': {'type': 'integer'}, 'up_to_seq': {'type': 'integer'},
        'count': {'type': 'integer'}, 'groups': {'type': 'array', 'items': {'ref': 'DigestGroup'}},
        'truncated': {'type': 'boolean'}},
        'required': ['from_seq', 'up_to_seq', 'count', 'groups', 'truncated']},
    'Acked': {'type': 'object', 'properties': {
        'up_to_seq': {'type': 'integer'}, 'changed': {'type': 'boolean'}},
        'required': ['up_to_seq', 'changed']},
    'ContextRef': {'type': 'object', 'open': True, 'properties': {
        'kind': {'type': 'string'}, 'id': {'type': 'string'},
        'version': {'type': 'integer'}, 'seq': {'type': 'integer'}},
        'required': ['kind', 'id']},
    'ContextItem': {'type': 'object', 'properties': {
        'ref': {'ref': 'ContextRef'}, 'level': {'type': 'string', 'enum': list(LEVELS)},
        'store': {'type': 'string', 'enum': list(STORES)}, 'type': {'type': 'string'},
        'source_kind': {'type': 'string'}, 'source_ref': {'type': 'string'},
        'observed_at': {'type': 'string', 'nullable': True},
        'freshness': {'type': 'string', 'enum': ['current', 'stale']},
        'relevance': {'type': 'number'}, 'signals': {'type': 'object'},
        'reason': {'type': 'string'}, 'tokens': {'type': 'integer'},
        'conflicts_with': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['ref', 'level', 'store', 'type', 'source_kind', 'source_ref',
                     'observed_at', 'freshness', 'relevance', 'signals', 'reason', 'tokens',
                     'conflicts_with']},
    'ContextExcluded': {'type': 'object', 'properties': {
        'ref': {'ref': 'ContextRef'}, 'level': {'type': 'string', 'enum': list(LEVELS)},
        'freshness': {'type': 'string', 'enum': ['current', 'stale', 'superseded']},
        'reason': {'type': 'string'}}, 'required': ['ref', 'level', 'freshness', 'reason']},
    'ContextConflict': {'type': 'object', 'properties': {
        'items': {'type': 'array', 'items': {'type': 'string'}},
        'preferred': {'type': 'string'}, 'kind': {'type': 'string'},
        'reason': {'type': 'string'}}, 'required': ['items', 'preferred', 'kind', 'reason']},
    'ContextBudget': {'type': 'object', 'properties': {
        'limit_tokens': {'type': 'integer'}, 'used_tokens': {'type': 'integer'},
        'levels': {'type': 'object'}}, 'required': ['limit_tokens', 'used_tokens', 'levels']},
    'ContextPreview': {'type': 'object', 'open': True, 'properties': {
        'subject_kind': {'type': 'string', 'enum': list(entities.CONTEXT_SUBJECTS)},
        'subject_id': {'type': 'string'}, 'workspace_id': {'type': 'string'},
        'project_id': {'type': 'string', 'nullable': True},
        'as_of_seq': {'type': 'integer'}, 'as_of_at': {'type': 'string', 'nullable': True},
        'query': {'type': 'string'},
        'levels': {'type': 'array', 'items': {'type': 'string', 'enum': list(LEVELS)}},
        'budget': {'ref': 'ContextBudget'}, 'scoring': {'type': 'object'},
        'items': {'type': 'array', 'items': {'ref': 'ContextItem'}},
        'excluded': {'type': 'array', 'items': {'ref': 'ContextExcluded'}},
        'conflicts': {'type': 'array', 'items': {'ref': 'ContextConflict'}},
        'assumptions': {'type': 'array', 'items': {'type': 'string'}},
        'missing_information': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['subject_kind', 'subject_id', 'workspace_id', 'project_id', 'as_of_seq',
                     'as_of_at', 'query', 'levels', 'budget', 'scoring', 'items', 'excluded',
                     'conflicts', 'assumptions', 'missing_information']},
    'ContextPackage': {'type': 'object', 'open': True, 'properties': {
        'id': {'type': 'string'}, 'version': {'type': 'integer'},
        'created_at': {'type': 'string'}, 'subject_kind': {'type': 'string'},
        'subject_id': {'type': 'string'}, 'as_of_seq': {'type': 'integer'},
        'budget': {'ref': 'ContextBudget'},
        'items': {'type': 'array', 'items': {'ref': 'ContextItem'}},
        'excluded': {'type': 'array', 'items': {'ref': 'ContextExcluded'}},
        'conflicts': {'type': 'array', 'items': {'ref': 'ContextConflict'}}},
        'required': ['id', 'version', 'created_at', 'subject_kind', 'subject_id', 'as_of_seq',
                     'budget', 'items', 'excluded', 'conflicts']},
    'KnowledgeList': {'type': 'object', 'properties': {
        'knowledge': {'type': 'array', 'items': {'ref': 'KnowledgeItem'}}},
        'required': ['knowledge']},
    'KnowledgeDetail': {'type': 'object', 'open': True, 'properties': {
        'id': {'type': 'string'}, 'state': {'type': 'string'},
        'chain': {'type': 'array', 'items': {'type': 'string'}},
        'relations': {'type': 'array', 'items': {'type': 'object'}}},
        'required': ['id', 'state', 'chain', 'relations']},
    'KnowledgeChanged': {'type': 'object', 'open': True, 'properties': {
        'knowledge_item': {'ref': 'KnowledgeItem'}, 'changed': {'type': 'boolean'}},
        'required': ['knowledge_item', 'changed']},
    'Forgotten': {'type': 'object', 'properties': {
        'dry_run': {'type': 'boolean'}, 'mode': {'type': 'string', 'enum': ['retract', 'purge']},
        'changes': {'type': 'array', 'items': {'type': 'object'}},
        'changed': {'type': 'boolean'}}, 'required': ['dry_run', 'mode', 'changes', 'changed']},
    'FeedbackRecorded': {'type': 'object', 'properties': {
        'feedback_id': {'type': 'string'},
        'promoted': {'ref': 'KnowledgeItem', 'nullable': True}, 'seq': {'type': 'integer'}},
        'required': ['feedback_id', 'promoted', 'seq']},
    'Meeting': {'type': 'object', 'open': True, 'properties': {
        'id': {'type': 'string'}, 'name': {'type': 'string'}, 'held_at': {'type': 'string'},
        'project_id': {'type': 'string', 'nullable': True},
        'notes_artifact_id': {'type': 'string', 'nullable': True}},
        'required': ['id', 'name', 'held_at', 'project_id']},
    'MeetingImported': {'type': 'object', 'properties': {
        'meeting': {'ref': 'Meeting'}, 'changed': {'type': 'boolean'}},
        'required': ['meeting', 'changed']},
    'RouteDecision': {'type': 'object', 'open': True, 'properties': {
        'id': {'type': 'string'}, 'purpose': {'type': 'string', 'nullable': True},
        'decided_by': {'type': 'string', 'nullable': True},
        'selected': {'type': 'string', 'nullable': True},
        'model': {'type': 'string', 'nullable': True},
        'candidates': {'type': 'array', 'items': {'type': 'object'}},
        'explanation': {'type': 'string'},
        'outcome': {'type': 'object', 'nullable': True}},
        'required': ['id', 'selected', 'candidates', 'explanation', 'outcome']},
    'RouteDecisionList': {'type': 'object', 'properties': {
        'route_decisions': {'type': 'array', 'items': {'ref': 'RouteDecision'}}},
        'required': ['route_decisions']},
    'ProviderTerms': {'type': 'object', 'open': True, 'properties': {
        'id': {'type': 'string'},
        'headless': {'type': 'string', 'enum': list(entities.TERMS)},
        'rotation': {'type': 'string', 'enum': list(entities.TERMS)},
        'note': {'type': 'string'}}, 'required': ['id', 'headless', 'rotation']},
    'ProviderTermsList': {'type': 'object', 'properties': {
        'provider_terms': {'type': 'array', 'items': {'ref': 'ProviderTerms'}}},
        'required': ['provider_terms']},
    'ProviderTermsDecided': {'type': 'object', 'properties': {
        'provider_terms': {'ref': 'ProviderTerms'}}, 'required': ['provider_terms']},
    'ApiError': {'type': 'object', 'properties': {'error': {'type': 'string'},
                                               'detail': {'type': 'object'}},
              'required': ['error', 'detail']},
}

CREATE_MISSION = {'type': 'object', 'properties': {
    'title': {'type': 'string'}, 'objective': {'type': 'string'},
    'project_id': {'type': 'string', 'nullable': True},
    'success_criteria': {'type': 'array', 'items': {'ref': 'Criterion'}},
    'idempotency_key': KEY}, 'required': ['title', 'objective', 'idempotency_key']}
KEYED = {'type': 'object', 'properties': {'idempotency_key': KEY},
         'required': ['idempotency_key']}
EMPTY = {'type': 'object', 'properties': {}, 'required': []}
CREATE_PROJECT = {'type': 'object', 'properties': {
    'name': {'type': 'string'}, 'root_paths': {'type': 'array', 'items': {'type': 'string'}},
    'idempotency_key': KEY}, 'required': ['name', 'root_paths', 'idempotency_key']}
DECLARE_CONSTRAINT = {'type': 'object', 'properties': {
    'statement': {'type': 'string'},
    'kind': {'type': 'string', 'nullable': True, 'enum': sorted(entities.CONSTRAINT_SPECS)},
    'spec': {'type': 'object', 'nullable': True}, 'idempotency_key': KEY},
    'required': ['statement', 'idempotency_key']}
ACK = {'type': 'object', 'properties': {'up_to_seq': {'type': 'integer'}},
       'required': ['up_to_seq']}
CONTEXT_PREVIEW = {'type': 'object', 'properties': {
    'subject': {'type': 'object', 'properties': {
        'kind': {'type': 'string', 'enum': list(entities.CONTEXT_SUBJECTS)},
        'id': {'type': 'string'}}, 'required': ['kind', 'id']},
    'query': {'type': 'string', 'nullable': True},
    'levels': {'type': 'array', 'nullable': True,
               'items': {'type': 'string', 'enum': list(LEVELS)}},
    'limit_tokens': {'type': 'integer', 'nullable': True}},
    'required': ['subject']}
KNOWLEDGE_MOVE = {'type': 'object', 'properties': {
    'reason': {'type': 'string', 'nullable': True},
    'expected_version': {'type': 'integer', 'nullable': True}, 'idempotency_key': KEY},
    'required': ['idempotency_key']}
SUPERSEDE = {'type': 'object', 'properties': {
    'title': {'type': 'string'}, 'text': {'type': 'string', 'nullable': True},
    'idempotency_key': KEY}, 'required': ['title', 'idempotency_key']}
FORGET = {'type': 'object', 'properties': {
    'selector': {'type': 'object'},
    'mode': {'type': 'string', 'nullable': True, 'enum': ['retract', 'purge']},
    'dry_run': {'type': 'boolean', 'nullable': True}, 'idempotency_key': KEY},
    'required': ['selector', 'idempotency_key']}
FEEDBACK = {'type': 'object', 'properties': {
    'subject': {'type': 'object', 'properties': {'kind': {'type': 'string'},
                                                 'id': {'type': 'string'}},
                'required': ['kind', 'id']},
    'signal': {'type': 'string', 'enum': ['positive', 'negative', 'correction']},
    'text': {'type': 'string', 'nullable': True},
    'promote': {'type': 'object', 'nullable': True, 'properties': {
        'type': {'type': 'string', 'enum': ['PREFERENCE', 'LESSON']},
        'title': {'type': 'string'}, 'text': {'type': 'string', 'nullable': True},
        'supersedes_id': {'type': 'string', 'nullable': True}}, 'required': ['type', 'title']},
    'idempotency_key': KEY}, 'required': ['subject', 'signal', 'idempotency_key']}
IMPORT_MEETING = {'type': 'object', 'properties': {
    'path': {'type': 'string'}, 'project_id': {'type': 'string', 'nullable': True},
    'held_at': {'type': 'string', 'nullable': True}, 'idempotency_key': KEY},
    'required': ['path', 'idempotency_key']}
PROVIDER_TERMS = {'type': 'object', 'properties': {
    'headless': {'type': 'string', 'enum': list(entities.TERMS)},
    'rotation': {'type': 'string', 'nullable': True, 'enum': list(entities.TERMS)},
    'note': {'type': 'string', 'nullable': True}, 'idempotency_key': KEY},
    'required': ['headless', 'idempotency_key']}
REDEEM = {'type': 'object', 'properties': {
    'code': {'type': 'string'}, 'platform': {'type': 'string', 'enum': ['web', 'desktop']}},
    'required': ['code', 'platform']}


def validate(value, schema, field=None):
    """Raise Invalid(field, why) when *value* does not have *schema*'s shape;
    a `ref` names one of this module's TYPES."""
    return shapes.validate(value, schema, field, types=TYPES)
