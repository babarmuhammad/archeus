"""The live-session strip on the dashboard: who counts as live, what the payload
is allowed to weigh, and the two ways the surface could quietly stop working.

The reference this adopts (zoetrope) was offered exactly the obvious version of
this feature — a fleet of tailers drawing every live session's graph on one
canvas — and its maintainer declined it, because several trees do not fit at a
readable size and the fleet pays for the parse continuously. So what is gated
here is the shape that survives that: ONE definition of live, a bounded payload,
and a list that hands off to the single-session graph rather than duplicating it.
"""

import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from harness import Sandbox
from claude_sessions import gui_api, stats


def _ts(off):
    import datetime
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=off)
    return t.strftime('%Y-%m-%dT%H:%M:%S.000Z')


def _session(path, turns=3, age=0, open_tool=False):
    """A Claude transcript in the shape the real file has, aged by `age`."""
    objs = []
    for i in range(turns):
        objs += [
            {'type': 'user', 'uuid': 'u%d' % i, 'timestamp': _ts(age + 30 - i),
             'message': {'role': 'user', 'content': [
                 {'type': 'text', 'text': 'do thing %d' % i}]}},
            {'type': 'assistant', 'uuid': 'a%d' % i, 'parentUuid': 'u%d' % i,
             'timestamp': _ts(age + 29 - i),
             'message': {'role': 'assistant', 'model': 'claude-opus-5',
                         'usage': {'input_tokens': 10, 'output_tokens': 5},
                         'content': [
                             {'type': 'text', 'text': 'ok'},
                             {'type': 'tool_use', 'id': 'tu%d' % i, 'name': 'Bash',
                              'input': {'command': 'ls'}}]}},
        ]
        if not (open_tool and i == turns - 1):
            objs.append(
                {'type': 'user', 'uuid': 'r%d' % i, 'parentUuid': 'a%d' % i,
                 'timestamp': _ts(age + 28 - i),
                 'toolUseResult': {'stdout': 'x'},
                 'message': {'role': 'user', 'content': [
                     {'type': 'tool_result', 'tool_use_id': 'tu%d' % i,
                      'content': 'ok'}]}})
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        for o in objs:
            f.write(json.dumps(o) + '\n')
    if age:
        old = time.time() - age
        os.utime(path, (old, old))
    return path


@pytest.fixture
def sb(monkeypatch, tmp_path):
    s = Sandbox(monkeypatch, tmp_path)
    gui_api._dash_cache = None
    gui_api._dash_cached_at = 0.0
    gui_api._flow_live_cache.clear()
    yield s
    gui_api._dash_cache = None
    gui_api._flow_live_cache.clear()


def _live(sb, **kw):
    _actual, _enc, folder, sids = sb.add_project('alpha')
    _session(os.path.join(folder, sids[0] + '.jsonl'), **kw)
    return gui_api.api_flow_live({}, None)


def test_a_session_touched_now_is_live_and_one_touched_an_hour_ago_is_not(sb):
    assert len(_live(sb)['sessions']) == 1
    gui_api._dash_cache = None
    assert _live(sb, age=3600)['sessions'] == []


def test_the_count_and_the_list_cannot_disagree_about_what_live_means(sb):
    """`total` and `sessions` are two answers to one question and used to be two
    conditions. They are built under one `if` now, so a change to LIVE_WINDOW
    moves both or neither."""
    out = _live(sb)
    assert out['total'] == len(out['sessions']) == 1
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'stats.py'),
        encoding='utf-8').read()
    body = src[src.index('live_by_acct[acct] ='):]
    assert 'live_b.append(row)' in body[:400], \
        'the list must be appended under the same test that bumps the count'


def test_the_payload_carries_no_transcript_text(sb):
    """A full event carries up to TEXT_CAP characters. Eight sessions x 160 of
    those is half a megabyte of prose for a row of coloured ticks that renders
    none of it — and this rides a 10-second poll."""
    out = _live(sb)
    ev = out['sessions'][0]['events'][0]
    assert set(ev) == {'t', 'type', 'name', 'dur'}
    assert 'do thing' not in json.dumps(out), 'no prompt text reaches the page'


def test_the_strip_is_bounded_however_long_the_session_is(sb):
    out = _live(sb, turns=400)
    evs = out['sessions'][0]['events']
    assert len(evs) == gui_api._STRIP_EVENTS
    # …and it is the TAIL: a glance is about what just happened
    assert evs[-1]['t'] >= evs[0]['t']


def test_an_unanswered_call_is_what_the_session_is_busy_on(sb):
    """The one thing a glance is for. A tool at the end of the file has not come
    back, so the row says what the session is waiting on rather than what it
    last finished."""
    assert _live(sb, open_tool=True)['sessions'][0]['busy'] == 'Bash'
    gui_api._dash_cache = None
    gui_api._flow_live_cache.clear()
    assert _live(sb)['sessions'][0]['busy'] == ''


def test_the_row_carries_what_it_takes_to_open_the_full_graph(sb):
    """The strip is a door, not a second implementation. /flow needs exactly
    enc + sid + cfgdir, and a row that cannot supply them is a dead end."""
    s = _live(sb)['sessions'][0]
    assert s['enc' if 'enc' in s else 'encoded'] and s['sid'] and s['cfgdir']
    assert s['project'] and s['harness'] == 'claude'


def test_the_colours_come_from_the_one_table_that_defines_them(sb):
    """The strip and the full graph must teach the same vocabulary, so the page
    is handed flowgraph's own table rather than a copy in the JavaScript."""
    from claude_sessions import flowgraph
    assert _live(sb)['colors'] == flowgraph.EVENT_COLORS
    js = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'web',
        'instruments.js'), encoding='utf-8').read()
    trail = js[js.index('trail(c, w, h'):]
    for hexv in flowgraph.EVENT_COLORS.values():
        assert hexv not in trail, \
            'a second copy of the event palette is a second thing to keep in step'


def test_the_strip_is_not_a_second_poller(sb):
    """zoetrope refused a fleet of tailers for this exact reason. One fetch, on
    the dashboard's own loop, and the instrument never issues a request."""
    js = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'web', 'app.js'),
        encoding='utf-8').read()
    assert js.count("api('/api/flow/live'") == 1
    inst = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'web',
        'instruments.js'), encoding='utf-8').read()
    assert 'fetch(' not in inst and 'setInterval' not in inst


def test_the_second_poll_inside_one_turn_does_not_re_read_the_file(sb):
    """A live transcript is re-read whenever it grows, which is correct. Two
    polls inside one turn, or a second tab, must not each pay for it."""
    out = _live(sb, turns=60)
    path = list(gui_api._flow_live_cache)[0]
    calls = []
    real = gui_api._strip_of
    gui_api._strip_of = lambda p, h: (calls.append(p), real(p, h))[1]
    try:
        gui_api._dash_cache = None
        assert gui_api.api_flow_live({}, None)['sessions'][0]['events'] \
            == out['sessions'][0]['events']
        assert calls == [], 'an unchanged transcript is served from the signature'
        with io.open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'type': 'user', 'uuid': 'zz',
                                'timestamp': _ts(0), 'message': {
                                    'role': 'user', 'content': [
                                        {'type': 'text', 'text': 'more'}]}}) + '\n')
        gui_api._dash_cache = None
        gui_api.api_flow_live({}, None)
        assert calls == [path], 'a transcript that grew is re-read'
    finally:
        gui_api._strip_of = real


def test_the_named_list_is_capped_but_the_count_is_not(sb):
    """`total` is a true count of what is running; the list is what a glance can
    actually hold. A screen showing twenty strips is not a glance."""
    assert stats.LIVE_MAX < 20
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'stats.py'),
        encoding='utf-8').read()
    assert "'total': sum(live_by_acct.values())" in src, \
        'the count is summed from every live session, not from the capped list'
    assert '[:LIVE_MAX]' in src


def test_the_dashboard_card_survives_the_endpoint_failing(sb):
    """Promise.all rejects as a whole. Folding this fetch in with the other two
    would let one endpoint blank the entire dashboard."""
    js = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'claude_sessions', 'web', 'app.js'),
        encoding='utf-8').read()
    call = js[js.index("api('/api/flow/live'"):]
    assert '.catch(' in call[:120], 'the live fetch carries its own catch'
    allp = js[js.index('Promise.all([api(\'/api/dashboard\''):]
    assert '/api/flow/live' not in allp[:220]
