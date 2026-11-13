"""T-1313 — gap tests for `claude_sessions/usage.py` lines 311-352 (inclusive) at
worktree tip d429bf96 (card tip 51f4af3f; the lines still match).

Source slice: `_extract_windows()` — the non-dict guard (318-319), the `norm()`
finite-window normalizer (321-326), the authoritative `limits[]` pass with its
per-entry filters (328-338), the legacy top-level fallback that runs only when
`limits[]` yielded nothing (340-348), and the daily-first stable sort (350-352).

Selected branches (denial/fail-closed first, then boundaries, then error paths):
 1. :326      float NaN and string 'nan' drop the entry; they are never clamped
 2. :326      +inf clamps to 100, -inf to 0, in both the limits and legacy schemas
 3. :323      numeric strings (exponent, padded) normalize; an invalid string is
              ignored without losing its valid sibling
 4. :335      a missing or None percent is ignored; a missing reset stays None
 5. :341      a valid limits[] entry suppresses every legacy utilization key
 6. :341      an empty or all-invalid limits[] falls back to the legacy values
 7. :333      non-dict limits[] entries are skipped among valid windows
 8. :318-319  a non-dict top-level payload returns [] and is not mutated
 9. :326      0, 100, 0.5 and out-of-range values: clamp only, never rescale
10. :351      mixed session / weekly / model labels sort daily-first and stably;
              equal-priority entries keep their reset and label

Only in-memory dicts are used: no file, network, subprocess or environment read.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import usage  # noqa: E402


def _model(name, pct, reset=None):
    return {'kind': 'weekly_scoped', 'percent': pct, 'resets_at': reset,
            'scope': {'model': {'display_name': name}}}


def test_nan_and_nan_string_drop_the_entry_instead_of_clamping():
    """Branch :326. norm() returns None for NaN, so a NaN-valued limits entry is
    dropped and the legacy values are used. Clamping NaN to a bound (via
    max/min) would report a fake percentage."""
    data = {
        'limits': [{'kind': 'session', 'percent': float('nan')},
                   {'kind': 'weekly_all', 'percent': 'nan'}],
        'five_hour': {'utilization': 30, 'resets_at': 'L'},
    }
    assert usage._extract_windows(data) == [('session', 30.0, 'L')]
    assert usage._extract_windows({'limits': [_model('Fable', 42)],
                                   'seven_day': {'utilization': float('nan')}}) == [
        ('Fable', 42.0, None)]


def test_infinities_clamp_to_0_and_100_in_both_schemas():
    """Branch :326 (clamp arms). min(inf, 100) and max(0.0, -inf) are the only
    paths that turn an infinite value into a window; '1e999' parses to inf too."""
    limits = {'limits': [{'kind': 'session', 'percent': float('inf')},
                         {'kind': 'weekly_all', 'percent': float('-inf')}]}
    assert usage._extract_windows(limits) == [('session', 100.0, None),
                                              ('weekly', 0.0, None)]
    legacy = {'five_hour': {'utilization': '1e999'},
              'seven_day': {'utilization': -float('inf')}}
    assert usage._extract_windows(legacy) == [('session', 100.0, None),
                                              ('weekly', 0.0, None)]


def test_numeric_strings_normalize_and_invalid_sibling_is_skipped():
    """Branch :323. float('1.5e1') and float(' 25 ') parse; float('abc') raises
    ValueError, is caught and the entry is skipped, while its valid neighbour is
    kept. A broader except would lose the neighbour too."""
    data = {'limits': [{'kind': 'session', 'percent': '1.5e1'},
                       {'kind': 'weekly_all', 'percent': 'abc'},
                       _model('Fable', ' 25 ')]}
    assert usage._extract_windows(data) == [('session', 15.0, None),
                                            ('Fable', 25.0, None)]


def test_missing_or_none_percent_is_ignored_and_missing_reset_is_none():
    """Branch :335. norm(None) and a missing key both return None (TypeError is
    caught at :322-325), so the entry is skipped; a valid entry without
    resets_at keeps reset None rather than a default."""
    data = {'limits': [{'kind': 'session'},
                       {'kind': 'weekly_all', 'percent': None, 'resets_at': 'X'},
                       _model('Opus', 12)]}
    assert usage._extract_windows(data) == [('Opus', 12.0, None)]


def test_valid_limits_entry_suppresses_every_legacy_key():
    """Branch :341. With one usable limits[] row, the legacy keys (even
    contradicting ones) must be ignored entirely; the `if not out` gate is what
    keeps them out. Removing it would append the legacy 90/80 to the banner."""
    data = {'limits': [{'kind': 'session', 'percent': 10, 'resets_at': 'R1'}],
            'five_hour': {'utilization': 90, 'resets_at': 'L'},
            'seven_day': {'utilization': 80}}
    assert usage._extract_windows(data) == [('session', 10.0, 'R1')]


def test_empty_or_all_invalid_limits_fall_back_to_legacy_values():
    """Branch :341 (fallback arm). An empty array, or one whose only entry is
    unusable, must hand over to the legacy keys. The array is not authoritative
    when it has nothing usable."""
    assert usage._extract_windows({'limits': [], 'five_hour': {'utilization': 33,
                                                              'resets_at': 'L'}}) == [
        ('session', 33.0, 'L')]
    assert usage._extract_windows({'limits': [{'percent': 'x'}],
                                   'seven_day': {'utilization': 44}}) == [
        ('weekly', 44.0, None)]


def test_non_dict_limits_entries_are_skipped_among_valid_windows():
    """Branch :333. Strings, None, numbers and lists in limits[] must be skipped
    one by one. A bare `item.get` (no isinstance) raises AttributeError on the
    first one and drops every window."""
    data = {'limits': ['junk', None, 7, {'kind': 'session', 'percent': 20}, ['x']]}
    assert usage._extract_windows(data) == [('session', 20.0, None)]


def test_non_dict_top_level_returns_empty_and_mutates_nothing():
    """Branch :318-319. A list, string, None or number payload returns [] and is
    left untouched; no key is read from it and nothing is written back."""
    for payload in ([1, 2], 'text', None, 42):
        before = list(payload) if isinstance(payload, list) else payload
        assert usage._extract_windows(payload) == []
        assert payload == before


def test_boundaries_clamp_only_and_never_rescale():
    """Branch :326 boundaries. 0.5 must stay 0.5 (not 50 or 0.5/100), 100 and 0
    stay put, and out-of-range values clamp to the bounds. The removed 0..1
    heuristic in the docstring at :314-316 would rescale 0.5 to 50."""
    data = {'limits': [_model('a', 0), _model('b', 100), _model('c', 0.5),
                       _model('d', 150), _model('e', -3), _model('f', 99.5)]}
    out = usage._extract_windows(data)
    assert [label for label, _p, _r in out] == ['a', 'b', 'c', 'd', 'e', 'f']
    assert [p for _label, p, _r in out] == [0.0, 100.0, 0.5, 100.0, 0.0, 99.5]


def test_mixed_labels_sort_daily_first_and_stably():
    """Branch :351. Sessions sort first, the all-models weekly next, and per-model
    labels last in their original order. Within one priority the input order and
    each entry's reset and label are kept, because the sort is stable."""
    data = {'limits': [
        _model('Fable', 10),
        {'kind': 'session', 'percent': 30, 'resets_at': 'S'},
        _model('Opus', 40, 'O1'),
        {'kind': 'weekly_all', 'percent': 20, 'resets_at': 'W'},
        {'kind': 'session', 'percent': 50, 'resets_at': 'S2'},
    ]}
    assert usage._extract_windows(data) == [
        ('session', 30.0, 'S'),
        ('session', 50.0, 'S2'),
        ('weekly', 20.0, 'W'),
        ('Fable', 10.0, None),
        ('Opus', 40.0, 'O1'),
    ]
