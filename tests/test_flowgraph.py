"""The session flow graph: what it reads, what it refuses to invent, and what it
promises never to hold in memory.

The fixtures here write the shapes the three CLIs ACTUALLY emit, checked against
real files on the machine this was written for — deliberately not
`harness.make_jsonl`, whose user lines carry a top-level `role`/`content` that
Claude Code has never written, and which has no `uuid`, no `tool_use` and no
`toolUseResult` at all. A parser tested against a fixture nobody's CLI produces
is a parser tested against itself.
"""

import io
import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from harness import Sandbox
from claude_sessions import flowgraph, gui


def _write(path, objs):
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        for o in objs:
            f.write(json.dumps(o) + '\n')
    return str(path)


def _ts(sec):
    return '2026-09-01T10:00:%02d.000Z' % sec


#: A Claude Code turn as the file really records it: the prompt arrives behind a
#: system reminder, the tool call is a block of the ASSISTANT message, and the
#: result comes back on a USER line carrying `toolUseResult` beside it.
def _claude(target):
    return _write(target, [
        {'type': 'user', 'uuid': 'u1', 'parentUuid': None, 'isSidechain': False,
         'timestamp': _ts(0), 'message': {'role': 'user', 'content': [
             {'type': 'text', 'text': '<system-reminder>be good</system-reminder>'},
             {'type': 'text', 'text': 'fix the parser'}]}},
        {'type': 'assistant', 'uuid': 'a1', 'parentUuid': 'u1', 'timestamp': _ts(1),
         'message': {'role': 'assistant', 'model': 'claude-opus-5',
                     'usage': {'input_tokens': 10, 'output_tokens': 5,
                               'cache_read_input_tokens': 100},
                     'content': [{'type': 'text', 'text': 'on it'},
                                 {'type': 'tool_use', 'id': 'tu1', 'name': 'Read',
                                  'input': {'file_path': 'D:/x/app.py'}}]}},
        {'type': 'user', 'uuid': 'u2', 'parentUuid': 'a1', 'timestamp': _ts(3),
         'sourceToolAssistantUUID': 'a1', 'toolUseResult': {'stdout': '42 lines'},
         'message': {'role': 'user', 'content': [
             {'type': 'tool_result', 'tool_use_id': 'tu1', 'content': 'ok'}]}},
        {'type': 'assistant', 'uuid': 'a2', 'parentUuid': 'u2', 'timestamp': _ts(4),
         'message': {'role': 'assistant', 'model': 'claude-opus-5', 'content': [
             {'type': 'tool_use', 'id': 'tu2', 'name': 'Task',
              'input': {'description': 'explore the repo'}}]}},
    ])


def _types(evs):
    return [e['type'] for e in evs]


def test_a_claude_turn_becomes_typed_events(tmp_path):
    evs = list(flowgraph.build_events(_claude(tmp_path / 's.jsonl')))
    assert _types(evs) == ['prompt', 'assistant', 'tool', 'result', 'spawn']
    tool = evs[2]
    assert tool['name'] == 'Read' and tool['target'] == 'D:/x/app.py'
    assert evs[1]['tok_in'] == 110 and evs[1]['tok_out'] == 5
    assert evs[4]['name'] == 'Task', 'a subagent is a spawn, not another tool'


def test_a_prompt_survives_a_system_reminder_in_front_of_it(tmp_path):
    """The reminder is its own block. Joining the blocks and then testing the
    result — which is what the transcript drawer does — throws the prompt away
    with the chatter on every hooked account."""
    evs = list(flowgraph.build_events(_claude(tmp_path / 's.jsonl')))
    assert evs[0]['text'] == 'fix the parser'
    assert 'system-reminder' not in evs[0]['text']


def test_a_tool_call_is_timed_by_the_result_that_closed_it(tmp_path):
    """No transcript carries a duration. It is the gap between the call and its
    result, so it is knowable only at the result — which is why the result is
    what carries it, and points BACK at the call."""
    evs = list(flowgraph.build_events(_claude(tmp_path / 's.jsonl')))
    res = evs[3]
    assert res['dur'] == 2.0
    assert evs[3 - res['ref']]['name'] == 'Read', 'ref counts events backwards'
    assert 'dur' not in evs[2], 'the call cannot know its own duration'


def test_an_unpaired_tool_call_reports_no_duration(tmp_path):
    """A live session is read while the tool is still running, and a session that
    crashed never closes its last call. Neither may invent a number."""
    p = _write(tmp_path / 'open.jsonl', [
        {'type': 'assistant', 'uuid': 'a1', 'timestamp': _ts(1), 'message': {
            'role': 'assistant', 'content': [
                {'type': 'tool_use', 'id': 'tu9', 'name': 'Bash',
                 'input': {'command': 'sleep 600'}}]}}])
    evs = list(flowgraph.build_events(p))
    assert _types(evs) == ['tool'] and 'dur' not in evs[0]


def test_an_api_error_is_its_own_event(tmp_path):
    p = _write(tmp_path / 'e.jsonl', [
        {'type': 'user', 'isApiErrorMessage': True, 'timestamp': _ts(2),
         'message': {'role': 'user', 'content': [
             {'type': 'text', 'text': "You've hit your session limit"}]}}])
    evs = list(flowgraph.build_events(p))
    assert _types(evs) == ['error'] and 'session limit' in evs[0]['text']


def test_a_sidechain_gets_a_lane_of_its_own(tmp_path):
    p = _write(tmp_path / 'sc.jsonl', [
        {'type': 'user', 'uuid': 'u1', 'timestamp': _ts(0),
         'message': {'role': 'user', 'content': [{'type': 'text', 'text': 'go'}]}},
        {'type': 'assistant', 'uuid': 's1', 'parentUuid': None, 'isSidechain': True,
         'timestamp': _ts(1), 'message': {'role': 'assistant', 'content': [
             {'type': 'text', 'text': 'subagent thinking'}]}},
        {'type': 'assistant', 'uuid': 's2', 'parentUuid': 's1', 'isSidechain': True,
         'timestamp': _ts(2), 'message': {'role': 'assistant', 'content': [
             {'type': 'text', 'text': 'subagent done'}]}}])
    evs = list(flowgraph.build_events(p))
    assert evs[0].get('lane', 0) == 0
    assert evs[1]['lane'] == evs[2]['lane'] > 0, \
        'a sidechain and its continuation belong to one lane'


def test_a_malformed_line_does_not_raise(tmp_path):
    """Transcripts are user data. A half-written last line is what a LIVE session
    looks like the moment a poll reads it."""
    p = str(tmp_path / 'bad.jsonl')
    with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write('not json at all\n')
        f.write('\n')
        f.write(json.dumps({'type': 'user', 'timestamp': _ts(0), 'message': {
            'role': 'user', 'content': [{'type': 'text', 'text': 'still here'}]}}) + '\n')
        f.write('{"type": "assistant", "message": {"role": "assist')   # truncated
    evs = list(flowgraph.build_events(p))
    assert _types(evs) == ['prompt']


def test_a_missing_file_is_empty_not_an_error(tmp_path):
    assert list(flowgraph.build_events(str(tmp_path / 'nope.jsonl'))) == []


# ── the other two harnesses ──────────────────────────────────────────────────

def test_codex_records_a_turn_twice_and_the_graph_draws_it_once(tmp_path):
    """A rollout carries the prompt as the `event_msg` the UI showed AND as the
    `response_item` the model was sent, plus a developer preamble and an
    `<environment_context>` wearing the same shape. Taking both drew every
    prompt twice and the preamble as a third."""
    p = _write(tmp_path / 'rollout.jsonl', [
        {'timestamp': _ts(0), 'type': 'session_meta',
         'payload': {'cwd': 'D:/x', 'session_id': 'abc'}},
        {'timestamp': _ts(1), 'type': 'turn_context', 'payload': {'model': 'gpt-5.5'}},
        {'timestamp': _ts(2), 'type': 'event_msg',
         'payload': {'type': 'user_message', 'message': 'reply with hello'}},
        {'timestamp': _ts(3), 'type': 'response_item', 'payload': {
            'type': 'message', 'role': 'developer',
            'content': [{'type': 'input_text', 'text': '<permissions instructions>'}]}},
        {'timestamp': _ts(3), 'type': 'response_item', 'payload': {
            'type': 'message', 'role': 'user',
            'content': [{'type': 'input_text', 'text': 'reply with hello'}]}},
        {'timestamp': _ts(4), 'type': 'response_item', 'payload': {
            'type': 'function_call', 'call_id': 'c1', 'name': 'shell',
            'arguments': '{"command": "ls"}'}},
        {'timestamp': _ts(7), 'type': 'response_item', 'payload': {
            'type': 'function_call_output', 'call_id': 'c1', 'output': 'a  b  c'}},
        {'timestamp': _ts(8), 'type': 'event_msg',
         'payload': {'type': 'agent_message', 'message': 'hello'}},
        {'timestamp': _ts(9), 'type': 'response_item', 'payload': {
            'type': 'message', 'role': 'assistant',
            'content': [{'type': 'output_text', 'text': 'hello'}]}},
    ])
    evs = list(flowgraph.build_events(p, harness='codex'))
    assert _types(evs) == ['model', 'prompt', 'tool', 'result', 'assistant']
    assert evs[1]['text'] == 'reply with hello'
    assert evs[3]['dur'] == 3.0 and evs[3 - evs[3]['ref']]['name'] == 'shell'


def test_codex_token_counts_are_cumulative_and_are_reported_as_a_delta(tmp_path):
    def count(i, o):
        return {'timestamp': _ts(i), 'type': 'event_msg', 'payload': {
            'type': 'token_count',
            'info': {'total_token_usage': {'input_tokens': i, 'output_tokens': o}}}}
    evs = list(flowgraph.build_events(
        _write(tmp_path / 'r.jsonl', [count(10, 5), count(30, 9)]), harness='codex'))
    assert [e['tok_in'] for e in evs] == [10, 20], \
        'the file reports a running total; the graph reports what a turn spent'


def test_a_pi_message_becomes_an_event(tmp_path):
    p = _write(tmp_path / 'pi.jsonl', [
        {'type': 'session', 'id': 'x', 'timestamp': _ts(0), 'cwd': 'D:/x'},
        {'type': 'model_change', 'timestamp': _ts(0), 'modelId': 'claude-sonnet-4-5'},
        {'type': 'message', 'id': 'm1', 'timestamp': _ts(1), 'message': {
            'role': 'user', 'content': [{'type': 'text', 'text': 'say hi'}]}},
        {'type': 'message', 'id': 'm2', 'timestamp': _ts(2), 'message': {
            'role': 'assistant', 'model': 'claude-sonnet-4-5',
            'usage': {'input': 4, 'output': 2, 'cacheRead': 0, 'cacheWrite': 0},
            'content': [{'type': 'text', 'text': 'hi'}]}},
        {'type': 'message', 'id': 'm3', 'timestamp': _ts(3), 'message': {
            'role': 'assistant', 'stopReason': 'error',
            'errorMessage': 'provider refused', 'content': []}},
    ])
    evs = list(flowgraph.build_events(p, harness='pi'))
    assert _types(evs) == ['model', 'prompt', 'assistant', 'error']
    assert evs[2]['tok_in'] == 4 and evs[2]['tok_out'] == 2


# ── the promise about memory ─────────────────────────────────────────────────

def _fat(path, n, filler=4000):
    """A transcript whose SIZE is tool traffic, which is what a real one is."""
    with io.open(path, 'w', encoding='utf-8', newline='\n') as f:
        for i in range(n):
            f.write(json.dumps({
                'type': 'assistant', 'uuid': 'a%d' % i, 'timestamp': _ts(i % 60),
                'message': {'role': 'assistant', 'content': [
                    {'type': 'tool_use', 'id': 't%d' % i, 'name': 'Read',
                     'input': {'file_path': 'x', 'pad': 'z' * filler}}]}}) + '\n')
            f.write(json.dumps({
                'type': 'user', 'uuid': 'u%d' % i, 'timestamp': _ts(i % 60),
                'toolUseResult': {'stdout': 'q' * filler},
                'message': {'role': 'user', 'content': [
                    {'type': 'tool_result', 'tool_use_id': 't%d' % i,
                     'content': 'q' * filler}]}}) + '\n')
    return str(path)


def test_a_transcript_is_never_materialised(tmp_path):
    """The same gate `transcript.page` carries, for the same reason: these files
    reach 100 MB and a generator that quietly buffered would look identical until
    someone opened a real session."""
    p = _fat(tmp_path / 'fat.jsonl', 400)
    size = os.path.getsize(p)
    assert size > 1_000_000, 'the fixture is not big enough to be evidence'

    import tracemalloc
    tracemalloc.start()
    got = list(flowgraph.build_events(p, limit=20))
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(got) == 20
    assert peak < size // 4, (
        'peak %d bytes for a %d byte transcript — it was materialised' % (peak, size))


def test_no_event_carries_a_whole_tool_result(tmp_path):
    """Truncation happens where the text is READ. Trimming it in the renderer
    means the payload has already been built out of a 2 MB build log."""
    evs = list(flowgraph.build_events(_fat(tmp_path / 'f.jsonl', 4), limit=8))
    assert evs and all(len(e.get('text', '')) <= flowgraph.TEXT_CAP for e in evs)


def test_a_follow_poll_returns_only_what_is_new(tmp_path):
    p = _claude(tmp_path / 's.jsonl')
    first, off = flowgraph.tail_events(p, 0)
    assert first and off > 0
    again, off2 = flowgraph.tail_events(p, off)
    assert again == [] and off2 == off, 'a poll with nothing new must add nothing'

    with io.open(p, 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps({'type': 'user', 'uuid': 'u9', 'timestamp': _ts(9),
                            'message': {'role': 'user', 'content': [
                                {'type': 'text', 'text': 'and now this'}]}}) + '\n')
    more, off3 = flowgraph.tail_events(p, off)
    assert _types(more) == ['prompt'] and more[0]['text'] == 'and now this'
    assert off3 > off


# ── the page ─────────────────────────────────────────────────────────────────

def _page(tmp_path):
    p = _claude(tmp_path / 's.jsonl')
    evs = list(flowgraph.build_events(p))
    meta = flowgraph.session_meta(p, evs, harness='claude', sid='abcd', project='alpha')
    return flowgraph.render_flow_html(evs, meta)


def test_the_page_is_self_contained(tmp_path):
    html = _page(tmp_path)
    assert '<script src' not in html and 'cdn' not in html.lower()
    assert '/vendor/' not in html, 'this page is also opened from a file:// path'
    assert '__FLOW_JSON__' not in html and '__CSS__' not in html, 'a slot was left unfilled'
    assert '"type": "tool"' in html or '"type":"tool"' in html


def test_the_page_escapes_a_project_name_that_is_markup(tmp_path):
    p = _claude(tmp_path / 's.jsonl')
    evs = list(flowgraph.build_events(p))
    meta = flowgraph.session_meta(p, evs, sid='abcd', project='<img src=x onerror=1>')
    html = flowgraph.render_flow_html(evs, meta)
    markup = html[:html.index('<script>')]
    assert '<img src=x' not in markup and '&lt;img' in markup, \
        'a name reaching MARKUP is html-escaped; the same name inside the data ' \
        'blob is a JSON string and is escaped by _script_json instead'


def test_a_data_blob_cannot_close_the_script_tag(tmp_path):
    """`</script>` inside a JSON string ends the SCRIPT, not the string — the
    parser that matters here is the HTML one. `_script_json` is the one place
    that is handled, which is why it is imported rather than re-implemented."""
    p = _write(tmp_path / 'x.jsonl', [
        {'type': 'user', 'timestamp': _ts(0), 'message': {'role': 'user', 'content': [
            {'type': 'text', 'text': 'try </script><img src=x> this'}]}}])
    evs = list(flowgraph.build_events(p))
    html = flowgraph.render_flow_html(evs, flowgraph.session_meta(p, evs))
    assert '</script><img' not in html
    assert '<\\/script>' in html


_WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'claude_sessions', 'web')


def test_the_flow_page_animates_only_compositor_properties():
    """The same rule the app's stylesheet is held to — and it needs its own gate,
    because `test_gui_flicker` parses the SPA page string and `flow.css` is not
    in it. A blur or a blend mode here tears the Qt surface exactly as it did
    there."""
    from test_gui_flicker import _decomment, _keyframes
    css = _decomment(io.open(os.path.join(_WEB, 'flow.css'), encoding='utf-8').read())
    blocks = _keyframes(css)
    assert blocks, 'no keyframes found — has the file moved?'
    for name, body in blocks:
        bad = set(re.findall(r'([-\w]+)\s*:', body)) - {'transform', 'opacity'}
        assert not bad, '@keyframes %s animates paint properties: %s' % (name, bad)
    for banned in ('backdrop-filter', 'mix-blend-mode', 'filter:blur', 'filter: blur'):
        assert banned not in css, '%s forces a compositor readback' % banned


def test_the_page_parks_when_nothing_is_visible():
    js = io.open(os.path.join(_WEB, 'flow.js'), encoding='utf-8').read()
    assert 'document.hidden' in js, 'the loop must not reschedule while hidden'
    assert "matchMedia('(prefers-reduced-motion: reduce)')" in js
    assert 'requestAnimationFrame' in js and 'raf = null' in js


def test_the_poll_writes_dom_only_when_it_changed():
    """This page polls once a second. An unconditional textContent= destroys and
    recreates the node on every tick — the exact bug the job modal shipped."""
    js = io.open(os.path.join(_WEB, 'flow.js'), encoding='utf-8').read()
    assert 'el.__v !== s' in js and 'el.__h !== s' in js
    assert js.count('.textContent =') <= 1, \
        'every text write goes through setTxt, which compares first'


# ── the route ────────────────────────────────────────────────────────────────

@pytest.fixture
def live(monkeypatch, tmp_path):
    sb = Sandbox(monkeypatch, tmp_path)
    _actual, enc, folder, sids = sb.add_project('alpha')
    _claude(os.path.join(folder, sids[0] + '.jsonl'))
    srv = gui.make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield 'http://127.0.0.1:%d' % srv.server_address[1], enc, sids[0]
    srv.shutdown()
    srv.server_close()


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read(), r.headers.get('Content-Type', '')
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get('Content-Type', '')


def test_the_flow_page_needs_the_run_token(live):
    """It is opened with window.open(), so it cannot carry the X-Archeus header
    and the token rides the query string — which means this route is the one
    doing the check. A local process that guessed the port is the case it
    closes; loopback is not a user-identity boundary."""
    base, enc, sid = live
    q = '?enc=%s&sid=%s' % (enc, sid)
    assert _get(base + '/flow' + q)[0] == 403
    assert _get(base + '/flow' + q + '&k=not-the-token')[0] == 403


def test_the_flow_page_answers_html_and_the_poll_answers_json(live):
    base, enc, sid = live
    q = '?enc=%s&sid=%s&k=%s' % (enc, sid, gui.TOKEN)
    code, body, ctype = _get(base + '/flow' + q)
    assert code == 200 and 'text/html' in ctype
    assert b'<canvas id="c">' in body

    code, body, ctype = _get(base + '/flow' + q + '&since=0')
    assert code == 200 and 'application/json' in ctype
    d = json.loads(body)
    assert [e['type'] for e in d['events']][:2] == ['prompt', 'assistant']
    assert d['offset'] > 0

    code, body, _ = _get(base + '/flow' + q + '&since=%d' % d['offset'])
    assert code == 200 and json.loads(body)['events'] == []


def test_the_route_refuses_a_name_that_did_not_come_from_the_encoder(live):
    """`enc` and `sid` are joined with a directory here, off the wire, and this
    handler runs OUTSIDE gui_api.call — so PARAM_CHECKS is not doing it."""
    base, enc, sid = live
    for bad in ('?enc=../../etc&sid=%s' % sid, '?enc=%s&sid=../secrets' % enc):
        code, body, _ = _get(base + '/flow' + bad + '&k=' + gui.TOKEN)
        assert code == 400, body[:200]
    code, _b, _c = _get(base + '/flow?enc=%s&sid=aaaa&k=%s' % (enc, gui.TOKEN))
    assert code == 404, 'a session with no transcript is missing, not broken'
