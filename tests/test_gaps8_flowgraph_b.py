"""T-1342: the highest-risk uncovered branches of claude_sessions/flowgraph.py lines 459-500
(build_events, tail_events, session_meta), at tip 6b1a30b8.

Selected branches, denial and fail-closed first, then boundaries, then error paths:
1. flowgraph.py:472-473 limit 2 stops the generator after two events (control).
2. flowgraph.py:469-473 limit 0 must yield nothing. Source yields before the limit check,
   so one event comes out. Strict xfail: source defect, not a fixture mistake.
3. flowgraph.py:467 an unknown harness id falls back to the Claude parser.
4. flowgraph.py:476-485 tail_events returns the events and the last event's o as next offset.
5. flowgraph.py:484-485 an empty batch returns the caller's offset unchanged.
6. flowgraph.py:459-465 build_events is a generator; nothing is read before iteration.
7. flowgraph.py:469 offset and path are forwarded to the parser unchanged.
8. flowgraph.py:490-496 models come from assistant and model events, deduplicated, names
   starting '<' skipped; tool, prompt and result events add nothing.
9. flowgraph.py:497-500 session_meta carries sid, harness, project, the file basename and
   the supports list.
10. flowgraph.py:494-495 events without a name add no model (control).

Seam: flowgraph._PARSERS and flowgraph._claude are replaced with synthetic generators.
No transcript file is opened, nothing is written outside tmp_path, no subprocess or network.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from claude_sessions import flowgraph


class Feed:
    """A synthetic parser: yields the given events and counts what it was asked for."""

    def __init__(self, events):
        self.events = list(events)
        self.calls = []
        self.pulled = 0

    def __call__(self, path, offset):
        self.calls.append((path, offset))
        for e in self.events:
            self.pulled += 1
            yield e


def _e(o, kind, name=None, t=1.0):
    e = {'o': o, 't': t, 'type': kind}
    if name is not None:
        e['name'] = name
    return e


@pytest.fixture
def feed(monkeypatch):
    f = Feed([_e(1, 'prompt'), _e(2, 'assistant', 'claude-a'), _e(3, 'tool', 'Bash')])
    monkeypatch.setitem(flowgraph._PARSERS, 'fake', f)
    return f


def _path(tmp_path):
    return tmp_path / 'sub' / 'sess.jsonl'


def test_limit_two_stops_after_two_events(feed, tmp_path):
    # flowgraph.py:472-473 - without the return, all three events come out.
    got = list(flowgraph.build_events(_path(tmp_path), harness='fake', limit=2))
    assert [e['o'] for e in got] == [1, 2]
    assert feed.pulled == 2, 'the parser must not be advanced past the limit'


def test_limit_zero_yields_nothing(feed, tmp_path):
    assert list(flowgraph.build_events(_path(tmp_path), harness='fake', limit=0)) == []


def test_unknown_harness_falls_back_to_the_claude_parser(monkeypatch, tmp_path):
    # flowgraph.py:467 - `_PARSERS.get(harness) or _claude`.
    claude = Feed([_e(7, 'prompt')])
    monkeypatch.setattr(flowgraph, '_claude', claude)
    got = list(flowgraph.build_events(_path(tmp_path), harness='no-such-cli'))
    assert [e['o'] for e in got] == [7]
    assert claude.calls == [(_path(tmp_path), 0)]


def test_tail_events_returns_the_batch_and_the_last_o(feed, tmp_path):
    # flowgraph.py:476-485 - next offset is the last event's o, not the caller's offset.
    events, nxt = flowgraph.tail_events(_path(tmp_path), 0, harness='fake')
    assert [e['o'] for e in events] == [1, 2, 3]
    assert nxt == 3


def test_tail_events_empty_batch_keeps_the_callers_offset(monkeypatch, tmp_path):
    # flowgraph.py:484-485 - `out[-1]['o'] if out else offset`.
    monkeypatch.setitem(flowgraph._PARSERS, 'fake', Feed([]))
    assert flowgraph.tail_events(_path(tmp_path), 7, harness='fake') == ([], 7)


def test_build_events_reads_nothing_until_iterated(feed, tmp_path):
    # flowgraph.py:459-465 - the function body is a generator; no call before next().
    gen = flowgraph.build_events(_path(tmp_path), harness='fake')
    assert feed.calls == [] and feed.pulled == 0
    assert next(gen)['o'] == 1
    assert feed.calls == [(_path(tmp_path), 0)] and feed.pulled == 1


def test_offset_and_path_reach_the_parser_unchanged(feed, tmp_path):
    # flowgraph.py:469 - fn(path, offset) is called with the caller's values.
    list(flowgraph.build_events(_path(tmp_path), harness='fake', offset=5))
    assert feed.calls == [(_path(tmp_path), 5)]


def test_models_are_deduplicated_and_skip_synthetic_names(monkeypatch, tmp_path):
    # flowgraph.py:490-496 - only assistant and model events contribute, first seen order.
    events = [
        _e(1, 'prompt', 'claude-x'),
        _e(2, 'assistant', 'claude-a'),
        _e(3, 'tool', 'claude-tool'),
        _e(4, 'assistant', 'claude-a'),
        _e(5, 'assistant', '<synthetic>'),
        _e(6, 'model', 'claude-b'),
        _e(7, 'result', 'claude-r'),
        _e(8, 'assistant', 'claude-c'),
    ]
    monkeypatch.setitem(flowgraph._PARSERS, 'fake', Feed(events))
    evs = list(flowgraph.build_events(_path(tmp_path), harness='fake'))
    meta = flowgraph.session_meta(_path(tmp_path), evs, harness='fake')
    assert meta['models'] == ['claude-a', 'claude-b', 'claude-c']


def test_session_meta_carries_identity_and_supports(tmp_path):
    # flowgraph.py:497-500 - sid, harness, project, basename and supports list.
    meta = flowgraph.session_meta(_path(tmp_path), [_e(1, 'prompt')],
                                  harness='claude', sid='abcd', project='alpha')
    assert meta['sid'] == 'abcd'
    assert meta['harness'] == 'claude'
    assert meta['project'] == 'alpha'
    assert meta['file'] == 'sess.jsonl'
    assert meta['supports'] == list(flowgraph.SUPPORTS['claude'])


def test_nameless_model_and_assistant_events_add_no_model(tmp_path):
    # flowgraph.py:494-495 - the `n and` guard: no name, no model.
    events = [_e(1, 'assistant'), _e(2, 'model', ''), _e(3, 'assistant', None)]
    meta = flowgraph.session_meta(_path(tmp_path), events, harness='claude')
    assert meta['models'] == []
