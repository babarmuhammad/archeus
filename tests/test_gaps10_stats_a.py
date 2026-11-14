"""T-1386: claude_sessions/stats.py lines 150-181 at tip 73ad7a90 (fmt_cost,
estimate_cost, _sum_usage), plus fmt_tok 184-189 at the same tip. Candidate
probes, not measured coverage.

Branches: 166-168 an unpriced model is counted at fallback rates and makes the
total inexact; 154-156 fmt_cost's three states; 162-173 empty and sparse usage;
169-172 cache multipliers and per-million scaling; 176-181 _sum_usage keys.
"""

import pytest

from claude_sessions import config, stats


@pytest.fixture(autouse=True)
def no_price_table(monkeypatch):
    monkeypatch.setattr(stats, '_cost_table', lambda: {})


def flat_rates(monkeypatch, table):
    def rates_for(model, cost_table):
        rates, known = table[model]
        return rates, known

    monkeypatch.setattr(stats, '_rates_for', rates_for)


def test_mixed_known_unknown_is_inexact_but_counted(monkeypatch):
    flat_rates(monkeypatch, {
        'known': ({'in': 1.0, 'out': 0}, True),
        'unknown': ({'in': 2.0, 'out': 0}, False),
    })
    cost, exact = stats.estimate_cost({'known': {'in': 1_000_000},
                                       'unknown': {'in': 1_000_000}})
    assert cost == pytest.approx(3.0)
    assert exact is False


def test_fmt_cost_three_states():
    assert stats.fmt_cost(0.0, False) == 'n/a'
    assert stats.fmt_cost(0.004, False) == '~0.00'
    assert stats.fmt_cost(0.0, True) == '0.00'


def test_fmt_cost_two_decimals_and_tilde_only_when_inexact():
    assert stats.fmt_cost(12.3456, True) == '12.35'
    assert stats.fmt_cost(12.3456, False) == '~12.35'


def test_estimate_empty_is_exact_zero():
    assert stats.estimate_cost(None) == (0.0, True)
    assert stats.estimate_cost({}) == (0.0, True)


def test_missing_usage_keys_count_zero(monkeypatch):
    flat_rates(monkeypatch, {'m': ({'in': 1.0, 'out': 2.0}, True)})
    assert stats.estimate_cost({'m': {}}) == (0.0, True)
    cost, exact = stats.estimate_cost({'m': {'out': 1_000_000}})
    assert cost == pytest.approx(2.0)
    assert exact is True


def test_cache_multipliers_applied(monkeypatch):
    flat_rates(monkeypatch, {'m': ({'in': 1.0, 'out': 0}, True)})
    cost, _ = stats.estimate_cost({'m': {'cache_read': 1_000_000}})
    assert cost == pytest.approx(config.CACHE_READ_MULT)
    cost, _ = stats.estimate_cost({'m': {'cache_create': 1_000_000}})
    assert cost == pytest.approx(config.CACHE_WRITE_MULT)


def test_sum_usage_missing_and_unknown_keys():
    zero = {'in': 0, 'out': 0, 'cache_read': 0, 'cache_create': 0}
    assert stats._sum_usage({}) == zero
    assert stats._sum_usage({'usage_by_model': None}) == zero
    got = stats._sum_usage({'usage_by_model': {
        'a': {'in': 2, 'out': 3, 'junk': 99},
        'b': {'in': 5, 'cache_read': 7},
    }})
    assert got == {'in': 7, 'out': 3, 'cache_read': 7, 'cache_create': 0}


def test_fmt_tok_boundaries():
    assert stats.fmt_tok(999) == '999'
    assert stats.fmt_tok(1000) == '1.0k'
    assert stats.fmt_tok(1_000_000) == '1.0M'


@pytest.mark.xfail(strict=True, reason=(
    'claude_sessions/stats.py:187-188 fmt_tok renders 999_999 as "1000.0k": '
    'the k branch does not roll over into M'))
def test_fmt_tok_does_not_render_four_digit_thousands():
    assert stats.fmt_tok(999_999) == '1.0M'
