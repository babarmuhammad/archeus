"""The red-team probes of the stream path, kept as regressions: base.read_stream,
execution/output.read, the Claude Code adapter's normalise, and the redactor they share. Driven
the way the API drives them: a stream file, `output.read(execution, adapter, offset)`, then
`public_output`. Every shape here leaked or blew up once, or held when it was tried. Every
secret is synthetic."""

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


def esc(text):
    return ''.join('%su%04x' % (chr(92), ord(c)) for c in text)


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


# ── a client-chosen offset (routes.py execution_stream `from=`, any integer) ──

def test_an_offset_inside_the_begin_line_still_reads_the_key_as_open(rig):
    """from=N inside the BEGIN line: the rest of that line is skipped, the key is still open."""
    rig.write([B, S, S, E])
    for n in (1, 5, 10, 20, 25):
        assert 'SYNTH' not in rig.text(n), n


def test_offset_inside_a_line_in_the_middle_of_the_body_held(rig):
    rig.write([B, S, S, E])
    for n in (rig.starts[1] + 3, rig.starts[2] + 3):
        assert 'SYNTH' not in rig.text(n), n


# ── a key over several strings: the state travels through every kind of event ──

def test_key_begin_in_one_event_body_in_the_next(rig):
    rig.write([ev(B), ev(S)])
    assert 'SYNTH' not in rig.text()


def test_key_begin_in_a_json_event_body_in_stderr_lines(rig):
    rig.write([ev(B), S, S, E])
    assert 'SYNTH' not in rig.text()


def test_key_begin_in_stderr_body_in_a_json_event(rig):
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


def test_stream_json_stderr_events_carry_the_key_state(rig):
    rig.write([{'type': 'stderr', 'text': B}, {'type': 'stderr', 'text': S}])
    assert 'SYNTH' not in rig.text()


def test_an_end_mentioned_in_a_json_event_does_not_close_a_stderr_key(rig):
    """An assistant event that merely mentions the END marker between the BEGIN line and a
    body line does not close a key printed on stderr, from any offset."""
    for got in every_start(rig, [B, ev('rotate by deleting ' + E), S, S, S]):
        assert 'SYNTH' not in got


def test_prose_in_an_event_does_not_end_a_key_printed_on_stderr(rig):
    for got in every_start(rig, [B, ev('working on the deploy now'), S, E]):
        assert 'SYNTH' not in got


def test_a_begin_mentioned_in_a_json_event_leaves_later_stderr_prose(rig):
    """Availability: an assistant event that mentions the BEGIN marker does not mask the
    stderr prose after it, from any offset."""
    for got in every_start(rig, [ev('grep for ' + B), 'real error one', 'real error two']):
        assert 'real error two' in got, got


# ── keys longer than a checkpoint apart: no look-back decides ──

def long_key(fmt, n=2200, w=63):
    ls = [B] + [fmt % ('A' * w + '%03d' % (i % 1000)) for i in range(n)] + [E]
    return ls


@pytest.mark.parametrize('name,fmt', [
    ('plain', '%s'), ('arrow', '   12→%s'), ('docker', '2026-01-01T00:00:00Z %s'),
    ('gt', '> %s'), ('crlf', '%s\r')])
def test_key_longer_than_a_checkpoint_paged(rig, name, fmt):
    ls = long_key(fmt)
    ls[2100] = ls[2100].replace('AAA', S, 1)
    rig.write(ls)
    assert rig.starts[1500] > base.CHECKPOINT
    assert 'SYNTH' not in rig.text(rig.starts[1500])
    assert 'SYNTH' not in rig.text(rig.starts[2050])


def test_key_longer_than_a_checkpoint_with_short_lines(rig):
    ls = [B] + ['a%04d' % i for i in range(19500)] + [E]
    ls[19000] = S
    rig.write(ls)
    assert 'SYNTH' not in rig.text(rig.starts[18990])


def test_key_longer_than_a_checkpoint_with_a_dash_line_inside_it(rig):
    ls = [B] + [B64] * 600 + ['-----'] + [B64] * 600 + ['SYNTH' + B64] + [E]
    rig.write(ls)
    assert rig.starts[1100] - rig.starts[1] > base.CHECKPOINT
    assert 'SYNTH' not in rig.text(rig.starts[1190])


def test_key_longer_than_a_checkpoint_interleaved_json_line_before_the_offset(rig):
    ls = [B] + [B64] * 1500 + [{'type': 'system', 'subtype': 'x'}, 'SYNTH' + B64, E]
    rig.write(ls)
    assert 'SYNTH' not in rig.text(rig.starts[1502])


def test_a_hash_line_far_into_the_stream_is_not_a_key(rig):
    """Availability: a hash line before a read start far into the stream is not a key."""
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


@pytest.mark.parametrize('spelled', [
    esc('-----') + 'BEGIN PRIVATE KEY-----',
    '-----BEGIN' + esc(' ') + 'PRIVATE' + esc(' ') + 'KEY-----',
    esc('-----B').upper().replace('U', 'u') + 'EGIN PRIVATE KEY-----',
], ids=['hyphens', 'spaces', 'letter'])
@pytest.mark.parametrize('lead', [0, 37])
def test_an_oversized_json_line_with_an_escaped_marker_opens_the_key(rig, monkeypatch, spelled, lead):
    monkeypatch.setattr(base, 'MAX_LINE', 4096)
    line = '{"text":"' + 'x' * lead + spelled + '","pad":"' + 'p' * 5000 + '"}'
    assert len(line) > base.MAX_LINE
    rig.write([line, S, E])
    assert 'SYNTH' not in rig.text()


def test_an_escape_cut_by_the_read_boundary_still_opens_the_key(rig, monkeypatch):
    monkeypatch.setattr(base, 'MAX_LINE', 4096)
    for cut in range(1, 7):
        head = b'x' * (base.MAX_LINE + 1 - cut)
        rig.write([head + esc('-----').encode() + b'BEGIN PRIVATE KEY-----' + b'y' * 100, S])
        assert 'SYNTH' not in rig.text(), cut


@pytest.mark.parametrize('gap', [100, 5000, 9000])
@pytest.mark.parametrize('blank', [b' ', b'\t'])
def test_a_marker_whose_blanks_span_a_read_boundary_opens_the_key(rig, monkeypatch, gap, blank):
    monkeypatch.setattr(base, 'MAX_LINE', 4096)
    head = b'x' * (base.MAX_LINE + 1 - 100) + b'-----BEGIN' + blank * gap
    rig.write([head + b'PRIVATE' + blank * gap + b'KEY-----' + b'y' * 100, S])
    assert 'SYNTH' not in rig.text()


def test_a_marker_whose_blanks_end_at_the_first_read_boundary(rig, monkeypatch):
    monkeypatch.setattr(base, 'MAX_LINE', 4096)
    head = b'x' * (base.MAX_LINE + 1 - 110) + b'-----BEGIN' + b' ' * 100
    assert len(head) == base.MAX_LINE + 1
    rig.write([head + b'PRIVATE KEY-----' + b'y' * 100, S])
    assert 'SYNTH' not in rig.text()


def test_an_oversized_line_with_no_marker_leaves_later_lines_alone(rig, monkeypatch):
    monkeypatch.setattr(base, 'MAX_LINE', 4096)
    rig.write([b'x' * 5000 + esc('\xe9\xe9\xe9 ' + 'A' * 100).encode(), 'later line of text'])
    assert 'later line of text' in rig.text()


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

def test_window_start_inside_a_key_begun_megabytes_before(rig):
    """A read from 0 of a stream over MAX_BYTES starts at a line inside a key that began
    megabytes before, and the lines carry a prefix."""
    line = '   12→' + B64
    n = (output.MAX_BYTES + (1 << 20)) // (len(line.encode()) + 1)
    ls = [B] + [line] * n + [E, 'tail']
    ls[n - 50] = '   12→SYNTH' + B64
    rig.write(ls)
    got = rig.read(0)
    leaked = 'SYNTH' in json.dumps(got)       # not `assert 'SYNTH' not in ...`: pytest's diff of a 70 KB string takes a minute
    assert got['truncated'] and not leaked


# ── the key state's own rules (redact.scrub, and the fold of base.read_stream) ──

def every_start(rig, lines):
    """What a read from 0 and a read from each line start answer."""
    rig.write(lines)
    return [rig.text(s) for s in rig.starts]


def test_a_stderr_key_runs_to_its_end_line_whatever_its_lines_say(rig):
    for got in every_start(rig, [B, 'Proc-Type: 4,ENCRYPTED', 'this line is prose now', 'SYNTHpw1', E, 'after']):
        assert 'SYNTH' not in got and 'prose' not in got and 'after' in got


def test_the_text_after_an_end_line_that_closes_a_key_is_kept(rig):
    rig.write([B, S, S[:5] + E + ' tail', 'after'])
    assert [e['text'] for e in rig.read(0)['events']] == ['[redacted]', '[redacted]', '[redacted] tail', 'after']


def test_prose_ends_a_key_of_the_json_channel_from_any_offset(rig):
    lines = [ev('grep for ' + B), ev('nothing like that is in the tree'), ev('run 0123456789abcdefABCDEF'),
             'hash 0123456789abcdefABCDEF']
    for got in every_start(rig, lines):
        assert '0123456789abcdefABCDEF' in got


def test_a_key_over_json_strings_keeps_its_armor_headers_inside_it(rig):
    rig.write([{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Write', 'id': 't', 'input': {
        'lines': ['-----BEGIN PGP PRIVATE KEY BLOCK-----', 'Comment: made by some tool here', '', S, '=abcd',
                  '-----END PGP PRIVATE KEY BLOCK-----']}}]}}])
    assert 'SYNTH' not in rig.text()


def test_a_key_over_two_real_shaped_assistant_events(rig):
    def turn(text):
        return {'type': 'assistant', 'message': {
            'id': 'msg_01', 'type': 'message', 'role': 'assistant', 'model': 'claude-x-1',
            'content': [{'type': 'text', 'text': text}], 'stop_reason': None,
            'usage': {'input_tokens': 3, 'output_tokens': 9, 'service_tier': 'standard'}},
            'parent_tool_use_id': None, 'session_id': '5f1c0a8e-0000-4000-8000-000000000001'}
    for got in every_start(rig, [turn('the key: ' + B), turn(S), turn(E), turn('done with it')]):
        assert 'SYNTH' not in got
    assert 'done with it' in rig.text()


def test_an_escaped_marker_in_a_json_line_opens_the_key_for_a_paged_read(rig):
    line = json.dumps({'type': 'stderr', 'text': B}).replace('-', '\\u002d')
    for got in every_start(rig, [line, S, E]):
        assert 'SYNTH' not in got


def test_a_read_from_inside_a_line_starts_at_the_next_one(rig):
    rig.write(['first line', 'second line'])
    assert [e['text'] for e in rig.read(3)['events']] == ['second line']


def test_a_stream_written_anew_is_folded_anew(rig, monkeypatch):
    monkeypatch.setattr(base, 'CHECKPOINT', 64)
    rig.write([B] + [B64] * 20)
    rig.text(rig.starts[15])
    rig.write(['plain line %03d ' % i + 'x' * 50 for i in range(30)])
    got = rig.read(rig.starts[15])
    assert got['events'] and all(e['text'].startswith('plain line') for e in got['events'])


def test_the_fold_remembers_a_bounded_number_of_streams(tmp_path, monkeypatch):
    monkeypatch.setattr(base, '_SEEN_MAX', 2)
    for i in range(4):
        p = tmp_path / ('s%d.jsonl' % i)
        p.write_bytes(b'line\n')
        base.read_stream(str(p))
        assert len(base._SEEN) <= 2


# ── blowups ──

def test_a_window_of_tiny_lines_reads_only_the_newest_lines(rig):
    """The window is the newest MAX_EVENTS lines too, not the whole 4 MiB of 2M lines."""
    with open(rig.paths.stream, 'wb') as f:
        f.write(b'a\n' * (output.MAX_BYTES // 2))
    t = time.perf_counter()
    got = rig.read(0)
    dt = time.perf_counter() - t
    assert len(got['events']) == output.MAX_EVENTS
    assert dt < 2, '%.1fs for one 4 MiB window of 2-byte lines' % dt


def test_an_event_nested_past_the_depth_cap_is_a_stderr_line(rig):
    """Availability: an event nested past base.MAX_DEPTH is a stderr line, so no reader of it
    (public.system_value, a JSON encoder) recurses that deep."""
    inner = 'x'
    for _ in range(700):
        inner = {'a': inner}
    rig.write([{'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'name': 'x', 'id': 't', 'input': inner}]}}])
    got = rig.read(0)
    json.dumps(got)
    assert [e['type'] for e in got['events']] == ['stderr']


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

def test_the_result_summary_is_redacted(rig):
    """The summary collect_result hands record_end is cut from a result already redacted."""
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
