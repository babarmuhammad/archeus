"""T-1445: claude_sessions/plan_execute.py lines 63-140 at tip 026ea58e (re-located at 44aaf17f).

Candidate gaps, not measured coverage. Ten ranked candidates, data loss first:

1  :68-71  test_failed_write_keeps_previous_plan                 (fixed: write_atomic)
2  :68-71  test_saved_file_has_exactly_two_keys                  (low value)
3  :74-80  missing file and invalid JSON return '': SKIP, pinned by tests/test_plan_execute.py:454,459
4  :74-80  list or number JSON raises AttributeError: NO CALLER (load_plan only used by tests), not written
5  :63-65  test_plan_store_path_is_under_home_claude
6  :68-80  test_round_trip_keeps_unicode_and_newlines
7  :108-117 test_step_lines_ignores_decimals_and_indented_lines
8  :108-117 test_step_indices_are_line_positions_not_numbers
9  :108-117 test_step_lines_strip_carriage_returns
10 :85-99  WEAK_MODEL_PLAN_INSTRUCTIONS wording: low value, not written

Seams: tmp_path for files; monkeypatch HOME, USERPROFILE and json.dump. No model, no subprocess.
"""

import json
import os

import pytest

from claude_sessions import plan_execute


def test_failed_write_keeps_previous_plan(tmp_path, monkeypatch):
    target = tmp_path / 'last_plan.json'
    plan_execute.save_plan('1. old step\n2. verify', str(target))
    before = target.read_text(encoding='utf-8')

    def failing_replace(src, dst):
        raise OSError(28, 'No space left on device')

    monkeypatch.setattr(os, 'replace', failing_replace)
    plan_execute.save_plan('1. new step', str(target))
    assert target.read_text(encoding='utf-8') == before


def test_saved_file_has_exactly_two_keys(tmp_path):
    target = tmp_path / 'plan.json'
    plan_execute.save_plan('1. a', str(target))
    assert set(json.loads(target.read_text(encoding='utf-8'))) == {'plan_text', 'generated_at'}


def test_plan_store_path_is_under_home_claude(tmp_path, monkeypatch):
    monkeypatch.setattr(plan_execute._c, '_USERPROFILE', str(tmp_path))
    assert plan_execute.plan_store_path() == os.path.join(str(tmp_path), '.claude', 'last_plan.json')


def test_round_trip_keeps_unicode_and_newlines(tmp_path):
    text = 'café → step\r\n1. ünïčode\n'
    target = tmp_path / 'plan.json'
    plan_execute.save_plan(text, str(target))
    assert plan_execute.load_plan(str(target)) == text


def test_step_lines_ignores_decimals_and_indented_lines():
    plan = '1. a\n10. b\n1.5 ratio\n1) a\n   2. indented\n'
    indices, lines = plan_execute._step_lines(plan)
    assert indices == [0, 1]
    assert lines == ['1. a', '10. b']


def test_step_indices_are_line_positions_not_numbers():
    plan = 'intro\n\n1. a\nmid\n2. b'
    indices, lines = plan_execute._step_lines(plan)
    assert indices == [2, 4]
    assert lines == ['1. a', '2. b']


def test_step_lines_strip_carriage_returns():
    indices, lines = plan_execute._step_lines('1. a\r\n2. b\r\n')
    assert indices == [0, 1]
    assert lines == ['1. a', '2. b']
