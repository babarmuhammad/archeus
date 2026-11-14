"""T-1385: claude_sessions/themes.py lines 47-79 at tip 73ad7a90 (_rgb,
_cube_idx, hex_to_x256, _mix). Candidate probes, not measured coverage.

Branches: 70 cube wins a tie (cube_d <= gray_d); 52-53 _cube_idx keeps the
lower index on a tie; 66 gray index clamped to 0..23; 73-79 _mix endpoints and
rounding; corners 16 and 231; 48 _rgb hash-less and upper-case input.
"""

import pytest

from claude_sessions import themes


def test_black_and_white_corners():
    assert themes.hex_to_x256('#000000') == 16
    assert themes.hex_to_x256('#ffffff') == 231


def test_tie_prefers_cube(monkeypatch):
    monkeypatch.setattr(themes, '_CUBE', (0, 95, 128, 175, 215, 255))
    cube = 16 + 36 * 2 + 6 * 2 + 2
    assert themes.hex_to_x256('#808080') == cube


def test_cube_idx_tie_takes_lower_index(monkeypatch):
    monkeypatch.setattr(themes, '_CUBE', (0, 10, 20, 30, 40, 50))
    assert themes._cube_idx(5) == 0


def test_exact_gray_uses_ramp():
    assert 128 not in themes._CUBE
    gray = 232 + round((128 - 8) / 10)
    assert themes.hex_to_x256('#808080') == gray


def test_result_always_in_colour_range_excluding_system_colours():
    seen = set()
    for r in range(0, 256, 17):
        for g in range(0, 256, 17):
            for b in range(0, 256, 17):
                idx = themes.hex_to_x256('#%02x%02x%02x' % (r, g, b))
                seen.add(idx)
    assert min(seen) >= 16 and max(seen) <= 255


def test_rgb_case_and_hash_optional():
    assert themes.hex_to_x256('FFFFFF') == themes.hex_to_x256('#ffffff') == 231
    assert themes._rgb('#7DCFFF') == themes._rgb('7dcfff') == (0x7d, 0xcf, 0xff)


def test_mix_endpoints_are_exact():
    assert themes._mix('#7dcfff', '#0d1117', 0) == '#7dcfff'
    assert themes._mix('#7dcfff', '#0d1117', 1) == '#0d1117'


def test_mix_midpoint_rounds_half_to_even():
    assert themes._mix('#000000', '#ffffff', 0.5) == '#808080'
