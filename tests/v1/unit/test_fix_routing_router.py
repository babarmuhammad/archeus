"""Regression tests for hostile-audit findings on archeus/core/routing/router.py."""

import pytest

from archeus.core.routing import router as R

from .test_routing_units import acct, harness, own, snap, task


@pytest.mark.parametrize('boundary', [None, {}])
def test_a_boundary_item_without_a_boundary_is_not_sandbox_enforceable(boundary):
    items = [('write_repo', 'ALLOW_WITHIN_BOUNDARY', boundary)]
    d = R.route(task(items=items), snap([harness('h', enforcement='sandbox')], [own('h')]))
    assert d['result'] != 'selected'


def test_a_degraded_account_with_an_exhausted_window_is_never_a_fallback():
    s = snap([harness('h')], [acct('acc_a', 'h', usage=100, health='DEGRADED', fallback='allow')])
    d = R.route(task(), s)
    assert d['result'] == 'blocked' and d['selected'] is None


def test_a_degraded_account_below_its_window_is_still_a_fallback():
    s = snap([harness('h')], [acct('acc_a', 'h', usage=10, health='DEGRADED', fallback='allow')])
    assert R.route(task(), s)['result'] == 'fallback'
