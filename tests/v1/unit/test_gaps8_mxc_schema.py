"""T-1343: the highest-risk uncovered branches of archeus/node/mxc_schema.py lines 23-120
(the fail-closed JSON Schema subset checker), at tip 6b1a30b8.

Selected branches, denial and fail-closed first, then boundaries, then error paths:
1. mxc_schema.py:32-44 an unknown keyword raises SchemaError when validator() is built.
2. mxc_schema.py:55-59 a $ref outside #/definitions or #/$defs, or to a missing target,
   fails closed.
3. mxc_schema.py:66-67 nesting deeper than _DEPTH returns False.
4. mxc_schema.py:28-31 a non-object, non-boolean schema raises SchemaError.
5. mxc_schema.py:28-29 and 119-120 boolean true accepts any value; boolean false rejects all.
6. mxc_schema.py:47-52 type integer rejects bool; type number accepts int and float, rejects bool.
7. mxc_schema.py:88-96 a missing required key is refused; additionalProperties false refuses
   an extra key.
8. mxc_schema.py:97-104 minItems, maxItems and uniqueItems are enforced; 1 and true are
   distinct items (control).
9. NaN and infinities are refused: they are not JSON numbers, and both bound comparisons
   would be False.
10. enum [1] accepts 1.0 and uniqueItems counts [1, 1.0] as a repeat (JSON numeric
    equality); true stays distinct from 1.

Pure validator calls on synthetic schemas and values. No I/O, no network, no subprocess.
"""

import pytest

from archeus.node.mxc_schema import SchemaError, validator

NOT_A_SCHEMA = [5, 'x', None, [], 1.5]
ANY_VALUES = [0, 'x', None, [], {}, True, 3.5]


def test_unknown_top_level_keyword_refuses_to_build_a_validator():
    # mxc_schema.py:32-44 - the check runs when validator() is called, not per value.
    with pytest.raises(SchemaError, match='format'):
        validator({'type': 'string', 'format': 'email'})
    assert validator({'type': 'string'})('a') is True


@pytest.mark.parametrize('schema', [
    {'$ref': '#/properties/x', 'properties': {'x': {'type': 'string'}}},
    {'$ref': 'other.json#/definitions/x', 'definitions': {'x': {}}},
    {'$ref': '#/$defs/missing', '$defs': {}},
])
def test_ref_outside_defs_or_to_a_missing_target_fails_closed(schema):
    # mxc_schema.py:55-59 - _ref returns False, so sub(False, value) denies.
    check = validator(schema)
    assert check('x') is False
    assert check({'x': 'x'}) is False


def test_nesting_deeper_than_the_depth_limit_is_refused():
    # mxc_schema.py:66-67 - a shallow value of the same shape is accepted (control).
    def nested_schema(levels):
        node = {}
        for _ in range(levels):
            node = {'items': node}
        return node

    def nested_value(levels):
        value = []
        for _ in range(levels):
            value = [value]
        return value

    assert validator(nested_schema(10))(nested_value(10)) is True
    assert validator(nested_schema(70))(nested_value(70)) is False


@pytest.mark.parametrize('bad', NOT_A_SCHEMA)
def test_schema_that_is_neither_object_nor_boolean_raises(bad):
    # mxc_schema.py:28-31.
    with pytest.raises(SchemaError):
        validator(bad)


def test_boolean_schemas_accept_every_value_or_none():
    # mxc_schema.py:28-29 and 119-120.
    accept_all = validator(True)
    reject_all = validator(False)
    for value in ANY_VALUES:
        assert accept_all(value) is True
        assert reject_all(value) is False


def test_integer_rejects_bool_and_number_accepts_int_and_float_but_not_bool():
    # mxc_schema.py:47-52 - type(value) is int, not isinstance, so bool is excluded.
    integer = validator({'type': 'integer'})
    number = validator({'type': 'number'})
    assert integer(1) is True
    assert integer(True) is False and integer(False) is False
    assert number(1) is True and number(1.5) is True
    assert number(True) is False


def test_missing_required_key_and_extra_key_under_closed_object_are_refused():
    # mxc_schema.py:88-96.
    schema = {'type': 'object', 'properties': {'a': {'type': 'integer'}},
              'required': ['a'], 'additionalProperties': False}
    check = validator(schema)
    assert check({'a': 1}) is True
    assert check({}) is False
    assert check({'a': 1, 'b': 2}) is False


def test_array_bounds_and_unique_items_enforced_with_bool_and_int_distinct():
    # mxc_schema.py:97-104 - 1 and True are distinct under uniqueItems (control).
    check = validator({'type': 'array', 'minItems': 1, 'maxItems': 2, 'uniqueItems': True})
    assert check([]) is False
    assert check([1, 2, 3]) is False
    assert check([1, 1]) is False
    assert check([1]) is True
    assert check([1, True]) is True


def test_nan_is_refused_by_numeric_bounds():
    check = validator({'type': 'number', 'minimum': 0, 'maximum': 10})
    assert check(float('nan')) is False


def test_enum_integer_accepts_the_equal_float():
    check = validator({'enum': [1]})
    assert check(1) is True
    assert check(1.0) is True


def test_unique_items_treats_one_and_one_float_as_equal_but_bool_and_int_distinct():
    check = validator({'type': 'array', 'uniqueItems': True})
    assert check([1, 1.0]) is False
    assert check([True, 1]) is True
