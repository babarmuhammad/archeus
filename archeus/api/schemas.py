"""Request and response shapes for the route table (p3.5b §5.1, A11).

Plain dicts in a small JSON-Schema-like subset, because two consumers read the
same declaration: the route boundary validates a request body's SHAPE against
it (domain validation stays in the entities), and tools/gen_api_docs.py turns
it into TypeScript types and the API reference. A shape written twice drifts.

    {'type': 'object', 'properties': {...}, 'required': [...]}  (no extra keys)
    {'type': 'string' | 'integer' | 'boolean', 'enum'?: [...]}
    {'type': 'array', 'items': <schema>}
    {'ref': '<name in TYPES>'}          a named type
    'nullable': True                    also accepts null
    {'type': 'object'} with no properties: any JSON object
"""

from ..core.domain import entities, states
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
            'required': ['state', 'observed_seq', 'parked']}},
        'required': ['core', 'engine']},
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
REDEEM = {'type': 'object', 'properties': {
    'code': {'type': 'string'}, 'platform': {'type': 'string', 'enum': ['web', 'desktop']}},
    'required': ['code', 'platform']}


class Invalid(ValueError):
    def __init__(self, field, why):
        super().__init__('%s: %s' % (field or 'body', why))
        self.field, self.why = field, why


_PY = {'string': str, 'integer': int, 'boolean': bool, 'array': list, 'object': dict}


def validate(value, schema, field=None):
    """Raise Invalid(field, why) when *value* does not have *schema*'s shape."""
    if 'ref' in schema:
        return validate(value, TYPES[schema['ref']], field)
    if value is None:
        if schema.get('nullable'):
            return
        raise Invalid(field, 'is required' if field else 'a JSON object is required')
    t = schema['type']
    ok = isinstance(value, _PY[t]) and not (t == 'integer' and isinstance(value, bool))
    if not ok:
        raise Invalid(field, 'must be %s %s' % ('an' if t[0] in 'aeiou' else 'a', t))
    if 'enum' in schema and value not in schema['enum']:
        raise Invalid(field, 'must be one of %s' % ', '.join(map(str, schema['enum'])))
    if t == 'array':
        for i, item in enumerate(value):
            validate(item, schema['items'], '%s[%d]' % (field, i))
    if t == 'object' and 'properties' in schema:
        props = schema['properties']
        for name in schema.get('required', ()):
            if name not in value:
                raise Invalid(name if field is None else '%s.%s' % (field, name), 'is required')
        for name, v in value.items():
            sub = name if field is None else '%s.%s' % (field, name)
            if name not in props:
                if schema.get('open'):
                    continue
                raise Invalid(sub, 'is not a known field')
            validate(v, props[name], sub)
