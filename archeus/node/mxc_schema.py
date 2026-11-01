"""A zero dependency checker for the JSON Schema subset the MXC policy schema is read with.

The schema is a reviewed artifact (hash pinned in `mxc_pins.json`); this module only
applies it. Anything the checker does not implement refuses the schema up front, so a
keyword is never silently ignored: a schema that needs more fails closed until a reviewed
change adds it here.
"""

import json
import re

_ANNOTATIONS = frozenset(('$schema', '$id', '$comment', 'title', 'description', 'default',
                          'examples'))
_NAMED = ('properties', 'definitions', '$defs')
_ONE = ('items', 'additionalProperties')
_MANY = ('allOf', 'anyOf', 'oneOf')
_PLAIN = frozenset(('type', 'enum', 'const', 'required', 'minItems', 'maxItems', 'uniqueItems',
                    'minimum', 'maximum', 'minLength', 'maxLength', 'pattern', '$ref'))
_TYPES = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'null': type(None)}
_DEPTH = 64


class SchemaError(ValueError):
    pass


def _audit(schema):
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise SchemaError('a schema must be an object or a boolean')
    for key, value in schema.items():
        if key in _ANNOTATIONS or key in _PLAIN:
            continue
        if key in _NAMED and isinstance(value, dict):
            for sub in value.values():
                _audit(sub)
        elif key in _ONE:
            _audit(value)
        elif key in _MANY and isinstance(value, list):
            for sub in value:
                _audit(sub)
        else:
            raise SchemaError('schema keyword not implemented: %s' % key)


def _type(value, name):
    if name == 'integer':
        return type(value) is int
    if name == 'number':
        return type(value) in (int, float)
    return type(value) is _TYPES[name] if name in _TYPES else False


def _ref(ref, root):
    parts = ref.split('/') if isinstance(ref, str) else []
    if len(parts) != 3 or parts[0] != '#' or parts[1] not in ('definitions', '$defs'):
        return False
    return root.get(parts[1], {}).get(parts[2], False)


def _same(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _ok(schema, value, root, depth):
    if depth > _DEPTH:
        return False
    if isinstance(schema, bool):
        return schema
    sub = lambda s, v: _ok(s, v, root, depth + 1)  # noqa: E731
    if '$ref' in schema and not sub(_ref(schema['$ref'], root), value):
        return False
    types = schema.get('type')
    if types is not None and not any(_type(value, t) for t in
                                     ([types] if isinstance(types, str) else types)):
        return False
    if 'enum' in schema and not any(_same(value, e) for e in schema['enum']):
        return False
    if 'const' in schema and not _same(value, schema['const']):
        return False
    if any(not sub(s, value) for s in schema.get('allOf', ())):
        return False
    if 'anyOf' in schema and not any(sub(s, value) for s in schema['anyOf']):
        return False
    if 'oneOf' in schema and sum(bool(sub(s, value)) for s in schema['oneOf']) != 1:
        return False
    if isinstance(value, dict):
        props = schema.get('properties', {})
        if any(k not in value for k in schema.get('required', ())):
            return False
        if any(k in props and not sub(props[k], v) for k, v in value.items()):
            return False
        extra = schema.get('additionalProperties', True)
        if any(k not in props and not sub(extra, v) for k, v in value.items()):
            return False
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', len(value)):
            return False
        if any(not sub(schema.get('items', True), v) for v in value):
            return False
        if schema.get('uniqueItems') is True and any(
                _same(a, b) for i, a in enumerate(value) for b in value[:i]):
            return False
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0) or len(value) > schema.get('maxLength', len(value)):
            return False
        if 'pattern' in schema and not re.search(schema['pattern'], value):
            return False
    if type(value) in (int, float):
        if value < schema.get('minimum', value) or value > schema.get('maximum', value):
            return False
    return True


def validator(schema):
    """`raw -> bool` for *schema*; raises SchemaError now if it uses anything this
    checker does not implement."""
    _audit(schema)
    return lambda raw: _ok(schema, raw, schema, 0) is True
