"""Regression tests for hostile-audit findings on archeus/harnesses/calls.py."""

import pytest

from archeus.harnesses import calls


@pytest.mark.parametrize('tokens', [-1, 1.5])
def test_a_negative_token_count_is_not_a_usage_figure(tokens):
    assert calls._usage({'usage': {'input_tokens': tokens}}) == {}
