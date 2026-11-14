"""T-1341: the highest-risk uncovered branches of claude_sessions/flowgraph.py lines 78-146
(harness_of, _ev, _said, _clip, _blocks, _target), at tip 6b1a30b8. Re-located at worktree
tip 4e253ad5: harness_of 79-86, _ev 89-102, _said 105-117, _clip 120-124, _blocks 127-132,
_TARGET_KEYS 136-137, _target 140-147.

Selected branches, denial and fail-closed first, then boundaries, then error paths:
1. flowgraph.py:141-142 _target returns '' for non-dict input.
2. flowgraph.py:143-146 _target takes file_path before command; a whitespace-only value is
   skipped and the next key is read; a non-str value is skipped.
3. flowgraph.py:114-116 _said drops empty text, text starting '<' and text starting 'Caveat:'.
4. flowgraph.py:117 a real prompt keeps a trailing space as separator (control).
5. flowgraph.py:121-124 _clip ignores non-str values, strips, then caps at TEXT_CAP.
6. flowgraph.py:130-132 _blocks wraps a plain string as one text block and drops non-dict blocks.
7. flowgraph.py:99-101 _ev drops None, '' and 0 values while keeping o, t and type.
8. flowgraph.py:85-86 harness_of returns the registry id of the file path.
9. flowgraph.py:100 PREMISE: a measured zero duration (dur 0.0) is dropped by _ev, so the
   page shows the call as untimed. The card's exit-code example has no exit field anywhere
   in flowgraph.py; dur is the real zero-valued field (flowgraph.py:216, 373).
10. flowgraph.py:136-137 tool input keys are read in documented order with 'query' last
    (control: order must hold).

Seam: harnesses.of_path is replaced for harness_of. Every other probe is a pure call on
synthetic values. No transcript is opened, nothing is written, no subprocess or network.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import flowgraph, harnesses


def test_target_non_dict_input_is_blank():
    assert flowgraph._target(None) == ''
    assert flowgraph._target('ls -la') == ''
    assert flowgraph._target(['command', 'ls']) == ''


def test_target_skips_blank_and_non_str_values_for_the_next_key():
    assert flowgraph._target({'file_path': '   ', 'command': 'ls -la'}) == 'ls -la'
    assert flowgraph._target({'file_path': 'a/b.py', 'command': 'ls'}) == 'a/b.py'
    assert flowgraph._target({'command': 5, 'path': 'p.txt'}) == 'p.txt'


def test_said_drops_harness_chatter_and_empty_text():
    assert flowgraph._said(None) == ''
    assert flowgraph._said('   ') == ''
    assert flowgraph._said('<system-reminder>hooks are on</system-reminder>') == ''
    assert flowgraph._said('Caveat: the following was generated locally') == ''


def test_said_keeps_a_real_prompt_with_a_trailing_separator():
    assert flowgraph._said('  fix the build  ') == 'fix the build '


def test_clip_ignores_non_strings_strips_then_caps():
    assert flowgraph._clip(None) == ''
    assert flowgraph._clip(['x']) == ''
    assert flowgraph._clip(42) == ''
    assert flowgraph._clip('  hi  ') == 'hi'
    assert flowgraph._clip('x' * (flowgraph.TEXT_CAP + 50)) == 'x' * flowgraph.TEXT_CAP
    assert flowgraph._clip(' ' * 10 + 'y' * 500) == 'y' * flowgraph.TEXT_CAP


def test_blocks_wraps_plain_string_and_drops_non_dict_blocks():
    assert flowgraph._blocks('hello') == [{'type': 'text', 'text': 'hello'}]
    assert flowgraph._blocks([{'type': 'text', 'text': 'a'}, 'junk', 3, None]) == [
        {'type': 'text', 'text': 'a'}]
    assert flowgraph._blocks(None) == []


def test_ev_keeps_identity_fields_and_drops_empty_values():
    e = flowgraph._ev(7, 1.5, 'tool', name=None, text='', n=0, target='ls')
    assert e == {'o': 7, 't': 1.5, 'type': 'tool', 'target': 'ls'}


def test_harness_of_returns_registry_id_for_the_path(monkeypatch, tmp_path):
    seen = []

    def fake_of_path(path):
        seen.append(path)
        return {'id': 'codex'}

    monkeypatch.setattr(harnesses, 'of_path', fake_of_path)
    path = str(tmp_path / 'rollout.jsonl')
    assert flowgraph.harness_of(path) == 'codex'
    assert seen == [path]


@pytest.mark.xfail(strict=True, reason=(
    "flowgraph.py:100 _ev drops every 0 value, so a call measured at 0.0 s loses dur "
    "(produced at flowgraph.py:216 and :373); the page then reads the call as untimed"))
def test_ev_keeps_a_measured_zero_duration():
    assert flowgraph._ev(3, 2.0, 'result', dur=0.0).get('dur') == 0.0


def test_target_reads_inputs_in_documented_order_with_query_last():
    assert flowgraph._target({'query': 'q', 'pattern': 'p'}) == 'p'
    assert flowgraph._target({'query': 'q', 'url': 'u', 'prompt': 'x'}) == 'u'
    assert flowgraph._target({'query': 'q', 'description': 'd'}) == 'd'
    assert flowgraph._target({'query': 'q'}) == 'q'
