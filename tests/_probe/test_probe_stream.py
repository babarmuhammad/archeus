"""Red-team probes of the stream path: base.read_stream, execution/output.read, the Claude Code
adapter's normalise, and the redactor they share. Driven the way the API drives them: a stream
file, `output.read(execution, adapter, offset)`, then `public_output`.

A FAILING test is a confirmed leak or blowup. Every secret is synthetic."""

import json
import os
import time

import pytest

from archeus.core.application.public import public_output
from archeus.core.domain import entities, ids
from archeus.core.execution import output
from archeus.core.homes import Homes
from archeus.harnesses import base
from archeus.harnesses.claude_code.adapter import ClaudeCodeAdapter, normalise
from archeus.infra.paths import ExecPaths

S = 'SYNTHBODYabcdef0123456789'
B = '-----BEGIN PRIVATE KEY-----'
E = '-----END PRIVATE KEY-----'
B64 = 'A' * 63
HOMES = Homes([], [], shorts=lambda _: None)


class Rig:
    def __init__(self, tmp_path, monkeypatch):
        monkeypatch.setenv('ARCHEUS_HOME', str(tmp_path))
        self.exe = entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                                      mission_id=ids.new_id('mission'), harness_id='claude_code',
                                      pid=4242, create_time=1.0)
        self.paths = ExecPaths(self.exe.id)
        os.makedirs(self.paths.dir, exist_ok=True)
        self.adapter = ClaudeCodeAdapter(exe='claude')
        self.starts = []

    def write(self, lines):
        """Lines (str, bytes or a dict for one JSON event) -> the stream file; the byte offset of each."""
        parts, self.starts, n = [], [], 0
        for ln in lines:
            if isinstance(ln, dict):
                ln = json.dumps(ln)
            ln = (ln.encode('utf-8') if isinstance(ln, str) else ln) + b'\n'
            self.starts.append(n)
            n += len(ln)
            parts.append(ln)
        with open(self.paths.stream, 'wb') as f:
            f.writelines(parts)
        return n

    def read(self, offset=0):
        return public_output(output.read(self.exe, self.adapter, offset), HOMES)

    def text(self, offset=0):
        return json.dumps(self.read(offset))

    def drain(self, offset=0):
        """Every page a client sees by following next_offset."""
        seen = []
        while True:
            o = self.read(offset)
            seen.append(json.dumps(o))
            if o['next_offset'] == offset:
                return ''.join(seen)
            offset = o['next_offset']


@pytest.fixture
def rig(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


def ev(text):
    return {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': text}]}}


# ── a key over several stderr lines: what the redactor's design covers ──

def test_key_over_stderr_lines_held(rig):
    rig.write(['boot', B, S, S, E, 'after'])
    assert 'SYNTH' not in rig.text()


def test_key_over_stderr_lines_crlf_held(rig):
    rig.write([B + '\r', S + '\r', E + '\r'])
    assert 'SYNTH' not in rig.text()


def test_key_every_kind_held(rig):
    for kind in ('RSA ', 'EC ', 'OPENSSH ', 'ENCRYPTED '):
        rig.write(['-----BEGIN %sPRIVATE KEY-----' % kind, S, '-----END %sPRIVATE KEY-----' % kind])
        assert 'SYNTH' not in rig.text(), kind


def test_key_text_before_begin_on_the_same_line_held(rig):
    rig.write(['leaked: ' + B, S, E])
    assert 'SYNTH' not in rig.text()


def test_key_json_escapes_in_a_json_event_held(rig):
    rig.write([ev(B + '\n' + S + '\n' + E), {'type': 'result', 'result': B + '\n' + S}])
    assert 'SYNTH' not in rig.text()


def test_paged_one_event_at_a_time_held(rig):
    """_scan reads in batches of 500; this reads one line per page the same way."""
    rig.write([B, S, S, S, E, 'tail'])
    events, off = [], 0
    while True:
        got, end = base.read_stream(rig.paths.stream, off, 1)
        events += got
        if end == off:
            break
        off = end
    from archeus.core.redact import redact_json
    assert 'SYNTH' not in json.dumps([redact_json(e) for r in events for e in normalise(r)])


def test_key_across_a_read_window_that_starts_at_each_line_held(rig):
    rig.write([B, S, S, S, E, 'tail'])
    for start in rig.starts:
        assert 'SYNTH' not in rig.text(start), start


# ── LEAK: a client-chosen offset (routes.py execution_stream `from=`, any integer) ──

def test_offset_inside_the_begin_marker(rig):
    """LEAK: from=N with N inside the BEGIN line leaves nothing in the 64 KiB look-back that
    reads as a marker, so every body line comes out as plain stderr text (base.py _inside_key)."""
    rig.write([B, S, S, E])
    for n in (1, 5, 10, 20, 25):
        assert 'SYNTH' not in rig.text(n), n


def test_offset_inside_a_line_in_the_middle_of_the_body_held(rig):
    rig.write([B, S, S, E])
    for n in (rig.starts[1] + 3, rig.starts[2] + 3):
        assert 'SYNTH' not in rig.text(n), n


# ── LEAK: state that does not travel ──

def test_key_begin_in_one_event_body_in_the_next(rig):
    """LEAK: redaction state crosses stderr lines only. Two assistant events (or two text blocks)
    are redacted separately, so the body of a key opened in the first is plain."""
    rig.write([ev(B), ev(S)])
    assert 'SYNTH' not in rig.text()


def test_key_begin_in_a_json_event_body_in_stderr_lines(rig):
    """LEAK: a JSON event line never sets `inside`, so stderr lines after one that opens a key
    are not redacted."""
    rig.write([ev(B), S, S, E])
    assert 'SYNTH' not in rig.text()


def test_key_begin_in_stderr_body_in_a_json_event(rig):
    """The body arrives as an event: the BEGIN line opened state but state is only used on stderr
    lines."""
    rig.write([B, ev(S), E])
    assert 'SYNTH' not in rig.text()


def test_key_over_two_text_blocks_of_one_event(rig):
    rig.write([{'type': 'assistant', 'message': {'content': [
        {'type': 'text', 'text': B}, {'type': 'text', 'text': S}]}}])
    assert 'SYNTH' not in rig.text()


def test_key_as_lines_of_a_tool_input_array(rig):
    rig.write([{'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'Write', 'id': 't', 'input': {'lines': [B, S, E]}}]}}])
    assert 'SYNTH' not in rig.text()


def test_stream_json_stderr_event_does_not_carry_state(rig):
    """A child's own {"type":"stderr"} JSON lines are passed through whole (adapter.normalise)."""
    rig.write([{'type': 'stderr', 'text': B}, {'type': 'stderr', 'text': S}])
    assert 'SYNTH' not in rig.text()


def test_json_line_between_begin_and_body_changes_the_paged_answer(rig):
    """LEAK: the look-back reads raw bytes, JSON lines included: an assistant event that merely
    mentions the END marker between the BEGIN line and a body line makes a read that starts
    after it think the key is closed (a sequential read ignores JSON lines)."""
    rig.write([B, ev('rotate by deleting ' + E), S, S, S])
    assert 'SYNTH' not in rig.text(rig.starts[3])
    assert 'SYNTH' not in rig.text(rig.starts[4])


def test_json_line_mentioning_begin_masks_later_stderr(rig):
    """Availability: an assistant event that mentions the BEGIN marker makes every read that
    starts after it redact all stderr to `[redacted]` until an END line (look-back vs sequential
    disagree)."""
    rig.write([ev('grep for ' + B), 'real error one', 'real error two'])
    got = rig.text(rig.starts[1])
    assert 'real error one' in got, got


# ── the 64 KiB look-back: keys longer than it ──

def long_key(fmt, n=2200, w=63):
    ls = [B] + [fmt % ('A' * w + '%03d' % (i % 1000)) for i in range(n)] + [E]
    return ls


@pytest.mark.parametrize('name,fmt', [
    ('plain', '%s'), ('arrow', '   12→%s'), ('docker', '2026-01-01T00:00:00Z %s'),
    ('gt', '> %s'), ('crlf', '%s\r')])
def test_key_longer_than_the_lookback_paged(rig, name, fmt):
    """The look-back fails closed only on a line that is pure base64 (base.py _KEY_BODY). LEAK for
    the arrow (Read tool), docker timestamp and `> ` prefixes the redact.py comment promises to
    cover."""
    ls = long_key(fmt)
    ls[2100] = ls[2100].replace('AAA', S, 1)
    rig.write(ls)
    assert rig.starts[1500] > base.KEY_PROBE
    assert 'SYNTH' not in rig.text(rig.starts[1500])
    assert 'SYNTH' not in rig.text(rig.starts[2050])


def test_key_longer_than_the_lookback_with_short_lines(rig):
    """LEAK: body lines under 16 characters never match _KEY_BODY, so a key past the look-back
    is not seen as one."""
    ls = [B] + ['a%04d' % i for i in range(19500)] + [E]
    ls[19000] = S
    rig.write(ls)
    assert 'SYNTH' not in rig.text(rig.starts[18990])


def test_key_longer_than_the_lookback_with_a_dash_line_inside_it(rig):
    """LEAK: any `-----` in the look-back (a divider an interleaved stderr line printed) turns
    the fail-closed branch off."""
    ls = [B] + [B64] * 600 + ['-----'] + [B64] * 600 + ['SYNTH' + B64] + [E]
    rig.write(ls)
    assert rig.starts[1100] - rig.starts[1] > base.KEY_PROBE
    assert 'SYNTH' not in rig.text(rig.starts[1190])


def test_key_longer_than_the_lookback_interleaved_json_line_before_the_offset(rig):
    """LEAK: the last line before the offset is a stdout JSON event: not base64, so fail-closed
    does not apply."""
    ls = [B] + [B64] * 1500 + [{'type': 'system', 'subtype': 'x'}, 'SYNTH' + B64, E]
    rig.write(ls)
    assert 'SYNTH' not in rig.text(rig.starts[1502])


def test_unrelated_hash_line_masks_following_stderr(rig):
    """Availability / false positive: a pure-base64 or hex line (a sha256) as the last line
    before a read start past 64 KiB, with no `-----` in the look-back, turns the read into a
    private key: all stderr after it is `[redacted]` until the page ends."""
    ls = ['z' * 80] * 1000 + ['e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
                              'Traceback: boom', 'ValueError: boom']
    rig.write(ls)
    got = rig.text(rig.starts[1001])
    assert 'boom' in got, got


# ── over-long lines (MAX_LINE) ──

def test_huge_line_then_key_lines_held(rig):
    big = b'x' * (base.MAX_LINE + 10)
    rig.write([big, B.encode(), S.encode(), E.encode()])
    assert 'SYNTH' not in rig.text()


def test_begin_marker_cut_by_the_max_line_boundary(rig):
    """The line is read MAX_LINE+1 bytes at a time: the BEGIN marker straddles two reads."""
    for cut in (1, 5, 13, 26):
        head = b'x' * (base.MAX_LINE + 1 - cut)
        rig.write([head + B.encode() + b' ' + b'y' * 100, S.encode(), E.encode()])
        assert 'SYNTH' not in rig.text(), cut


def test_key_whose_body_has_a_huge_line_in_the_middle(rig):
    rig.write([B, S, b'A' * (base.MAX_LINE + 10), S, E, 'after'])
    assert 'SYNTH' not in rig.text()


def test_huge_line_head_is_cut_at_200_bytes_after_a_secret_start(rig):
    """The 200-byte head of a dropped line is redacted whole later; a token cut by it keeps
    its first (<8) characters only. Held."""
    tok = 'sk-ant-api03-' + 'Zq9' * 20
    rig.write([b'p' * 190 + tok.encode() + b'q' * (base.MAX_LINE + 5)])
    assert 'Zq9Zq9Zq9' not in rig.text()


# ── the 4 MiB window: a key that began before it ──

def test_window_start_inside_a_key_longer_than_the_lookback(rig):
    """LEAK without any hostile offset: read from 0 on a stream over MAX_BYTES starts at a line
    inside the key (output._window), BEGIN is more than 64 KiB back, and the lines carry a
    prefix. A key this long is unusual; the module says it fails closed."""
    line = '   12→' + B64
    n = (output.MAX_BYTES + (1 << 20)) // (len(line.encode()) + 1)
    ls = [B] + [line] * n + [E, 'tail']
    ls[n - 50] = '   12→SYNTH' + B64
    rig.write(ls)
    got = rig.read(0)
    leaked = 'SYNTH' in json.dumps(got)       # not `assert 'SYNTH' not in ...`: pytest's diff of a 70 KB string takes a minute
    assert got['truncated'] and not leaked


# ── blowups ──

def test_a_window_of_tiny_lines_costs_seconds_and_hundreds_of_mb(rig):
    """read_stream is called with no max_events by adapter.inspect, so the whole 4 MiB window
    becomes events and MAX_EVENTS is applied afterwards (output.py:47-48). This writes
    the full window (MAX_BYTES): about 2M events, roughly 0.5 GB while it runs."""
    with open(rig.paths.stream, 'wb') as f:
        f.write(b'a\n' * (output.MAX_BYTES // 2))
    t = time.perf_counter()
    got = rig.read(0)
    dt = time.perf_counter() - t
    assert len(got['events']) == output.MAX_EVENTS
    assert dt < 2, '%.1fs for one 4 MiB window of 2-byte lines' % dt


def test_deeply_nested_tool_input_breaks_the_read(rig):
    """LEAK of availability: json.loads accepts ~990 levels, redact_json is iterative, then
    public.system_value recurses (two frames a level) and raises RecursionError: the output
    endpoint of that execution answers 500 on every read, from any offset before the line."""
    inner = 'x'
    for _ in range(700):
        inner = {'a': inner}
    rig.write([{'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'x', 'id': 't', 'input': inner}]}}])
    json.dumps(rig.read(0))


def test_one_hundred_thousand_deep_array_is_a_stderr_line(rig):
    rig.write(['[' * 100000 + ']' * 100000])
    got = rig.read(0)
    assert got['events'] and got['events'][0]['type'] == 'stderr'


def test_ten_thousand_keys_and_one_mb_line(rig):
    big = {'k%d' % i: 'sk-AAAAAAAAAA%d' % i for i in range(10000)}
    rig.write([{'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'x', 'id': 't', 'input': big}]}},
        ev('word ' * 200000)])
    t = time.perf_counter()
    text = rig.text()
    assert 'AAAAAAAAAA' not in text and time.perf_counter() - t < 2


def test_one_mb_line_with_a_key_in_it(rig):
    rig.write([ev('x' * (1 << 20) + '\n' + B + '\n' + S)])
    assert 'SYNTH' not in rig.text()


# ── the adapter's own fields ──

def test_result_summary_is_stored_unredacted(rig):
    """LEAK: normalise() puts `text[:2000]` of the result into `summary`; collect_result hands it
    to X.record_end(summary=...) which stores it as Execution.summary (executions.py:545) with no
    redact on that path. output.read redacts events, but this field never goes through it."""
    rig.write([{'type': 'result', 'subtype': 'success', 'is_error': False, 'session_id': 's',
                'result': 'done. token was Bearer ' + S}])
    handle = base.ProcessHandle(rig.exe.id, 4242, None, rig.paths.dir)
    res = rig.adapter.collect_result(handle)
    assert 'SYNTH' not in res.reported_summary, res.reported_summary


@pytest.mark.parametrize('raw', [
    {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': {'x': 'Bearer ' + S}}]}},
    {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': ['Bearer ' + S]}]}},
    {'type': 'assistant', 'parent_tool_use_id': {'k': 'Bearer ' + S}, 'message': {'content': [{'type': 'text'}]}},
    {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Bearer ' + S, 'input': 1}]}},
    {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': ['Bearer ' + S]}], 'usage': {'a': 'Bearer ' + S}}},
    {'type': 'assistant', 'message': {'content': 'Bearer ' + S, 'model': 'Bearer ' + S}},
    {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'Bearer ' + S}]}},
    {'type': 'result', 'result': 'Bearer ' + S, 'session_id': 'Bearer ' + S, 'subtype': 'Bearer ' + S,
     'modelUsage': {'Bearer ' + S: {}}, 'usage': {'Bearer ' + S: 'Bearer ' + S}},
    {'type': 'result', 'is_error': True, 'result': 'rate limit 429 Bearer ' + S},
    {'type': 'system', 'subtype': 'Bearer ' + S, 'session_id': 'Bearer ' + S},
    {'type': 'stderr', 'text': 'Bearer ' + S, 'extra': {'Bearer ' + S: 1}},
], ids=range(11))
def test_odd_shapes_neither_raise_nor_leak(raw):
    evs = normalise(raw)
    from archeus.core.redact import redact_json
    assert 'SYNTH' not in json.dumps([redact_json(e) for e in evs], default=str)


@pytest.mark.parametrize('raw', [
    {'type': None}, {'type': ['assistant']}, {'type': 'assistant', 'message': []},
    {'type': 'assistant', 'message': {'content': [None, 1, 'x', [], {'type': ['text']}]}},
    {'type': 'assistant', 'message': {'usage': 1, 'model': 5}},
    {'type': 'result', 'modelUsage': {1: 2}, 'usage': [1], 'total_cost_usd': 'x', 'result': None},
    {'type': 'result', 'modelUsage': [], 'usage': None, 'result': {'a': 1}},
    {'type': {'a': 1}},
])
def test_odd_types_do_not_raise(raw):
    normalise(raw)
