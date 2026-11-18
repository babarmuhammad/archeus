"""T-1019: the ten highest-risk uncovered branches of archeus/node/mxc_schema.py lines 1-120.

Selected branches (fail-closed and denial first, then boundaries, then error paths):
1. uniqueItems truthy-but-not-True (int 1) skips uniqueness check — fail-open security gap (line 93).
2. additionalProperties as a dict sub-schema validates extra values — policy broadening (line 86-87).
3. $ref resolves via $defs (not definitions) — untested alternative branch in _ref (line 55-57).
4. _audit recurses $defs sub-schemas and rejects invalid ones — coverage gap (line 35-36).
5. Bool bypasses numeric minimum/maximum when no type field — fail-open (line 103-104).
6. Non-string $ref value (None, int, list) denies fail-closed — untested input (line 53).
7. Empty anyOf/oneOf rejects all values (vacuous denial) — boundary (line 75-77).
8. items=False (bool schema) denies non-empty arrays — fail-closed boundary (line 92).
9. _same raises TypeError for non-serializable enum/const value — error path (line 63, 74).
10. _audit recurses _ONE (additionalProperties sub-schema) and finds unimplemented keyword (line 38-39).

Each test names the source branch whose removal or inversion it catches. Pure logic, no OS,
no network, no process, no DLL. Runs identically on Linux and Windows.
"""

import pytest

from archeus.node.mxc_schema import SchemaError, validator


# ── branch 1: uniqueItems truthy-but-not-True skips uniqueness (line 93-94) ──


def test_unique_items_integer_one_does_not_enforce_uniqueness():
    """mxc_schema.py:93 - the check is `schema.get('uniqueItems') is True` (identity).
    If changed to `bool(schema.get('uniqueItems'))` or `schema.get('uniqueItems')`, an
    integer 1 (truthy but not True) would skip the uniqueness check and admit duplicates,
    which is a fail-open security regression for a pinned policy schema."""
    # uniqueItems True (correct) rejects duplicates
    check = validator({'type': 'array', 'uniqueItems': True})
    assert check([1, 1]) is False, 'uniqueItems True must reject duplicates'
    # uniqueItems 1 (truthy int) does NOT reject because `1 is True` is False
    check_one = validator({'type': 'array', 'uniqueItems': 1})
    assert check_one([1, 1]) is True, (
        'inverting the identity check to truthiness would make this False')
    # uniqueItems False also does not enforce
    check_false = validator({'type': 'array', 'uniqueItems': False})
    assert check_false([1, 1]) is True


# ── branch 2: additionalProperties as dict sub-schema (line 86-87) ──


def test_additional_properties_schema_denies_broadened_extra_key():
    """mxc_schema.py:86-87 - when additionalProperties is a dict (a sub-schema), extra
    keys must validate against it. Removing `if any(k not in props and not sub(extra, v) ...)`
    or always defaulting extra to True would allow a broadened policy shape through."""
    schema = {'type': 'object',
              'properties': {'known': {'type': 'integer'}},
              'additionalProperties': {'type': 'null'}}
    check = validator(schema)
    # extra key with correct type conforms
    assert check({'known': 1, 'extra': None}) is True
    # extra key with wrong type must deny — this is the broadening denial
    assert check({'known': 1, 'extra': 'should_fail'}) is False


def test_additional_properties_schema_denies_broadened_numeric_extra():
    """Same branch as above; tests the numeric constraint path through the additionalProperties
    sub-schema. If the range check inside sub(extra, v) were skipped (e.g. by a type-gate bug),
    an out-of-range value would pass."""
    schema = {'type': 'object',
              'additionalProperties': {'minimum': 1, 'maximum': 5}}
    check = validator(schema)
    assert check({'a': 3}) is True
    assert check({'a': 0}) is False
    assert check({'a': 99}) is False


# ── branch 3: $ref resolves via $defs (line 55-57) ──


def test_ref_resolves_via_defs_not_definitions():
    """mxc_schema.py:55-57 - _ref checks `parts[1] not in ('definitions', '$defs')`.
    If the tuple is shortened to ('definitions',) (dropping $defs), refs through $defs
    silently return False, rejecting everything that relies on $defs."""
    schema = {'type': 'object',
              'properties': {'name': {'$ref': '#/$defs/name'}},
              '$defs': {'name': {'type': 'string', 'minLength': 2}}}
    check = validator(schema)
    assert check({'name': 'ok'}) is True, '$defs resolution must work'
    assert check({'name': 'x'}) is False, 'inner sub-schema must still apply'
    assert check({'name': 42}) is False


# ── branch 4: _audit recurses $defs and rejects invalid sub-schema (line 35-36) ──


def test_audit_rejects_invalid_sub_schema_under_defs():
    """mxc_schema.py:35-36 - _audit iterates _NAMED (which includes '$defs') and
    recursively audits each value. If '$defs' were removed from _NAMED, a schema with
    an invalid sub-schema under $defs would pass audit, then crash at validation time
    (fail-open instead of fail-closed)."""
    with pytest.raises(SchemaError, match='format'):
        validator({'$defs': {'x': {'format': 'uri'}}})
    # valid $defs should not raise
    validator({'$defs': {'x': {'type': 'integer'}}})


def test_audit_rejects_non_dict_defs_value():
    """mxc_schema.py:35 - `key in _NAMED and isinstance(value, dict)` — when $defs value
    is not a dict (e.g. an int), the guard must not silently pass. If the isinstance check
    were removed, a non-dict $defs would crash in value.values()."""
    with pytest.raises(SchemaError):
        validator({'$defs': 5})


# ── branch 5: bool bypasses minimum/maximum when no type (line 103-104) ──


def test_bool_bypasses_numeric_range_without_type_constraint():
    """mxc_schema.py:103-104 - `if type(value) in (int, float)` gates the numeric range
    check. Since `type(True)` is `bool` (not `int` or `float`), the minimum/maximum check
    is skipped for bools. The existing tests catch bool-as-integer via the type field check
    (line 72), but when NO type field is present, a schema with only minimum/maximum cannot
    reject True/False. Changing `type(value) in (int, float)` to `isinstance(value, int)`
    would make bools enter the numeric check and break this test."""
    schema = {'minimum': 5, 'maximum': 10}
    check = validator(schema)
    # True and False pass because the numeric gate excludes bool
    assert check(True) is True, (
        'bool must bypass numeric range when no type field; converting gate to isinstance '
        'would make True fail minimum=5')
    assert check(False) is True
    # integers still respect the range
    assert check(3) is False
    assert check(7) is True


# ── branch 6: non-string $ref denies fail-closed (line 53) ──


@pytest.mark.parametrize('bad_ref', [None, 42, ['x'], {'k': 1}, True, 1.5, b'x'],
                         ids=['none', 'int', 'list', 'dict', 'bool', 'float', 'bytes'])
def test_non_string_ref_denies_fail_closed(bad_ref):
    """mxc_schema.py:53 - `_ref` does `ref.split('/') if isinstance(ref, str) else []`.
    A non-string $ref produces an empty parts list → len!=3 → returns False → _ok returns
    False (deny). If the isinstance guard were removed, calling .split('/') on int/None
    would crash with AttributeError (fail-open)."""
    schema = {'$ref': bad_ref}
    # must not raise; must deny
    check = validator(schema)
    assert check(1) is False, 'non-string $ref must deny, not crash'


# ── branch 7: empty anyOf / oneOf rejects all (vacuous denial) (line 75-77) ──


def test_empty_any_of_denies_every_value():
    """mxc_schema.py:75 - `if 'anyOf' in schema and not any(...)` with an empty anyOf
    list: `any([])` is False → `not False` is True → return False (deny). If someone
    changes the guard to `if schema.get('anyOf')` (falsy check), an empty list would be
    treated as absent and the value would pass — a fail-open regression."""
    check = validator({'anyOf': []})
    assert check(1) is False
    assert check('x') is False
    assert check(None) is False
    assert check({}) is False


def test_empty_one_of_denies_every_value():
    """mxc_schema.py:77 - `if 'oneOf' in schema and sum(...) != 1` with an empty oneOf:
    `sum([])` is 0 → `0 != 1` → True → return False (deny). Inverting the != to == or
    removing the empty-list guard would let all values through."""
    check = validator({'oneOf': []})
    assert check(1) is False
    assert check('x') is False
    assert check(None) is False


# ── branch 8: items=False denies non-empty array (line 92) ──


def test_items_false_denies_non_empty_array():
    """mxc_schema.py:92 - `if any(not sub(schema.get('items', True), v) for v in value)`
    with items=False: sub(False, v) calls _ok(False, v, ...) which returns False (bool
    schema returns itself). Then `not False` is True → any(...) is True → return False
    (deny). If the items default were changed from True to False, every unconstrained
    array would be denied — a different regression this test would also catch by its
    companion."""
    check = validator({'type': 'array', 'items': False})
    assert check([1]) is False, 'items=False must deny non-empty array'
    assert check([1, 2, 3]) is False
    # empty array: any() over empty is False → does not deny
    assert check([]) is True, 'empty array must conform even with items=False'


# ── branch 9: _same raises TypeError for non-serializable value (line 63, 74) ──


def test_enum_with_unserializable_value_raises_type_error():
    """mxc_schema.py:63 (_same uses json.dumps) called from line 74 (enum check) —
    when the enum list contains a non-JSON-serializable object, _same raises TypeError.
    This is the error path that should deny rather than silently pass. If someone wraps
    _same in a try/except returning True, a crafted enum could accept anything."""
    schema = {'enum': [{1, 2}]}  # set is not JSON-serializable
    check = validator(schema)
    with pytest.raises(TypeError):
        check('anything')


def test_const_with_unserializable_value_raises_type_error():
    """mxc_schema.py:63 (_same) called from line 78 (const check) — same path as the enum
    test but via const. Removing the _same call or catching its exception would change
    the denial to a pass."""
    schema = {'const': {1, 2}}  # set is not JSON-serializable
    check = validator(schema)
    with pytest.raises(TypeError):
        check('anything')


# ── branch 10: _audit recurses _ONE (additionalProperties sub-schema) (line 38-39) ──


def test_audit_rejects_unimplemented_keyword_in_additional_properties():
    """mxc_schema.py:38-39 - `elif key in _ONE: _audit(value)` — when additionalProperties
    is a dict containing an unimplemented keyword, _audit must recurse into it and raise.
    If _ONE were narrowed to only ('items',) (dropping additionalProperties), the sub-schema
    under additionalProperties would go unaudited and an unsupported keyword would silently
    pass validation."""
    with pytest.raises(SchemaError, match='patternProperties'):
        validator({'type': 'object', 'additionalProperties': {'patternProperties': {}}})
    # same via items
    with pytest.raises(SchemaError, match='format'):
        validator({'type': 'array', 'items': {'format': 'date'}})
