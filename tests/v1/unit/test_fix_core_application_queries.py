"""Regression tests for hostile-audit findings on archeus/core/application/queries.py."""

from archeus.core.application import queries


def test_a_task_key_with_a_non_decimal_digit_still_sorts():
    keys = ['T10', 'T2', 'T\u00b2', 'T1', 'other']
    got = sorted(({'key': k} for k in keys), key=queries._task_order)
    assert [t['key'] for t in got] == ['T1', 'T2', 'T10', 'T\u00b2', 'other']
