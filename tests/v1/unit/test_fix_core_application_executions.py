"""Regression tests for hostile-audit findings on how a harness's reported usage enters the ledger."""

import math

import pytest

from archeus.core.application import executions
from archeus.core.domain import entities, ids


@pytest.mark.parametrize('cost', [float('nan'), float('inf'), -1.0])
def test_a_cost_that_is_not_a_finite_amount_is_not_a_usage_figure(cost):
    assert 'cost_usd' not in executions._usage({'total_cost_usd': cost, 'input_tokens': 3})


@pytest.mark.parametrize('tokens', [-1, 1.5, 12.0])
def test_a_token_count_that_is_not_a_whole_number_is_not_a_usage_figure(tokens):
    assert executions._usage({'input_tokens': tokens}) == {}


def test_a_usable_usage_is_kept():
    got = executions._usage({'input_tokens': 3, 'total_cost_usd': 0.25})
    assert got == {'tokens_in': 3, 'cost_usd': 0.25}


@pytest.mark.parametrize('cost', [math.nan, math.inf, -0.5])
def test_the_ledger_refuses_a_cost_that_is_not_a_finite_amount(cost):
    with pytest.raises(ValueError):
        entities.UsageLedger(id=ids.new_id('usage_ledger'), route_decision_id=ids.new_id('route_decision'), cost_usd=cost)
