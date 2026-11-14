"""Gap tests for the statusline limit and reset-time helpers: epoch validation,
the millisecond threshold, same-day versus later-day formatting, the plan-window
colour bands, the reset suffix, the non-dict guard, and the live percentage the
rotate hint reads. Input is plain dicts, as it would arrive on stdin."""

import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import config as _c
from claude_sessions import statusline as sl

_ANSI = re.compile(r'\x1b\[[0-9;]*m')


def _plain(s):
    return _ANSI.sub('', s)


def _expected(epoch):
    """What _reset_at should print for a seconds epoch, computed independently."""
    try:
        dt = datetime.fromtimestamp(epoch).astimezone()
    except (OverflowError, OSError, ValueError):
        return ''
    now = datetime.now(dt.tzinfo)
    return dt.strftime('%H:%M') if dt.date() == now.date() else dt.strftime('%a %H:%M')


def test_reset_at_rejects_bool_str_none_and_nan():
    assert sl._reset_at(True) == ''
    assert sl._reset_at(False) == ''
    assert sl._reset_at('1700000000') == ''
    assert sl._reset_at(None) == ''
    assert sl._reset_at(float('nan')) == ''


def test_reset_at_treats_only_huge_epochs_as_milliseconds():
    assert sl._reset_at(1.8e12) == sl._reset_at(1.8e9) != ''
    assert sl._reset_at(1e11) == _expected(1e11)


def test_reset_at_same_day_shows_time_only_later_day_shows_weekday():
    now = time.time()
    assert sl._reset_at(now) == _expected(now)
    assert re.fullmatch(r'\d{2}:\d{2}', sl._reset_at(now))
    later = now + 3 * 86400
    assert sl._reset_at(later) == _expected(later)
    assert re.fullmatch(r'\S+ \d{2}:\d{2}', sl._reset_at(later))


def test_reset_at_zero_and_negative_give_what_the_platform_gives():
    for epoch in (0, -1):
        out = sl._reset_at(epoch)
        assert isinstance(out, str)
        assert out == _expected(epoch)


def test_limit_bits_skips_non_numeric_and_truncates_floats():
    out = sl._limit_bits({'rate_limits': {
        'five_hour': {'used_percentage': True},
        'seven_day': {'used_percentage': 89.9}}})
    assert [_plain(s) for s in out] == ['7d 89%']


def test_limit_bits_colour_boundaries():
    def colour(pct):
        return sl._limit_bits({'rate_limits': {'five_hour': {'used_percentage': pct}}})[0]

    assert colour(75).startswith(_c.C_WARN)
    assert colour(74.9).startswith(_c.C_DIM)
    assert colour(90).startswith(_c.C_ERR)
    assert colour(89.9).startswith(_c.C_WARN)


def test_limit_bits_reset_suffix_only_when_the_epoch_is_usable():
    now = time.time()
    with_reset = sl._limit_bits({'rate_limits': {'five_hour': {
        'used_percentage': 10, 'resets_at': now}}})
    assert '→' in _plain(with_reset[0])
    without = sl._limit_bits({'rate_limits': {'five_hour': {
        'used_percentage': 10, 'resets_at': 'soon'}}})
    assert '→' not in _plain(without[0])


def test_limit_bits_non_dict_rate_limits_gives_no_rows():
    assert sl._limit_bits({'rate_limits': None}) == []
    assert sl._limit_bits({'rate_limits': 'oops'}) == []
    assert sl._limit_bits({}) == []


def test_live_pct_is_the_fuller_plan_window_unclamped_and_ignores_spend():
    assert sl._live_pct({'rate_limits': {
        'five_hour': {'used_percentage': 150}, 'seven_day': {'used_percentage': 20}}}) == 150.0
    assert sl._live_pct({'rate_limits': {
        'five_hour': {'used_percentage': 10},
        'seven_day': {'used_percentage': 30},
        'spend_limit': {'used_percentage': 500}}}) == 30.0


def test_live_pct_zero_when_nothing_numeric_and_bool_is_ignored():
    assert sl._live_pct({}) == 0.0
    assert sl._live_pct({'rate_limits': {'five_hour': {'used_percentage': True}}}) == 0.0
    assert sl._live_pct({'rate_limits': {'five_hour': {'used_percentage': 49.9}}}) < sl._ROTATE_FLOOR


def test_rotate_bit_guards_a_non_dict_rate_limits_before_live_pct():
    assert sl._rotate_bit({'rate_limits': 'oops'}) == ''
