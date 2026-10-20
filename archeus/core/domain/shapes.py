"""A small JSON-Schema subset, and its validator: the one both the route
boundary (archeus/api/schemas.py, with its named TYPES) and Core's validation of
a model's structured output (ADR-0006, ADR-0022) check shapes with.

    {'type': 'object', 'properties': {...}, 'required': [...]}  (no extra keys
                                                               unless 'open')
    {'type': 'string' | 'integer' | 'number' | 'boolean', 'enum'?: [...]}
    {'type': 'array', 'items': <schema>, 'maxItems'?: n}
    {'ref': '<name in types>'}          a named type
    'nullable': True                    also accepts null
    'maxLength': n                      on a string
"""


class Invalid(ValueError):
    def __init__(self, field, why):
        super().__init__('%s: %s' % (field or 'body', why))
        self.field, self.why = field, why


_PY = {'string': str, 'integer': int, 'number': (int, float), 'boolean': bool, 'array': list,
       'object': dict}


def validate(value, schema, field=None, types=None):
    """Raise Invalid(field, why) when *value* does not have *schema*'s shape."""
    if value is None and schema.get('nullable'):       # also a nullable named type
        return
    if 'ref' in schema:
        return validate(value, (types or {})[schema['ref']], field, types)
    if value is None:
        if schema.get('nullable'):
            return
        raise Invalid(field, 'is required' if field else 'a JSON object is required')
    t = schema['type']
    ok = isinstance(value, _PY[t]) and not (t in ('integer', 'number')
                                            and isinstance(value, bool))
    if not ok:
        raise Invalid(field, 'must be %s %s' % ('an' if t[0] in 'aeiou' else 'a', t))
    if 'enum' in schema and value not in schema['enum']:
        raise Invalid(field, 'must be one of %s' % ', '.join(map(str, schema['enum'])))
    if t == 'string' and 'maxLength' in schema and len(value) > schema['maxLength']:
        raise Invalid(field, 'is longer than %d characters' % schema['maxLength'])
    if t == 'array':
        if 'maxItems' in schema and len(value) > schema['maxItems']:
            raise Invalid(field, 'has more than %d items' % schema['maxItems'])
        for i, item in enumerate(value):
            validate(item, schema['items'], '%s[%d]' % (field, i), types)
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
            validate(v, props[name], sub, types)
