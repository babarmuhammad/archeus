"""T-775: the highest-risk uncovered branches of `archeus/cli/tui/client.py`, as
units. Fail-closed and denial paths first — a stream that is refused 401 stops
reconnecting instead of hammering the port, the local token is read only for a
Core that discovery says is running (never for `not_running`, never for
`unreadable`, and no Core at all when the token file is gone), a frame Core never
finished writing is never handed to the TUI, a `shutdown` frame is dropped, a
malformed frame is a lost stream and not a frame, and a transport failure that is
neither a URLError nor an OSError still has to arrive as the (0, `network`)
refusal every caller catches (xfail: it does not). Then boundaries — the event
head is a number or nothing (`0` is a real head, an absent head is None, a
garbage head must be a refusal: xfail), a cursor of `0` is still sent as
`Last-Event-ID`, a frame with `id: 0` is still a cursor, the stream timeout is
longer than Core's heartbeat, and the reconnect backoff doubles to its 8 s cap
and resets on an open. Then error paths — an error body that is not JSON, an
error body that names no code, an empty answer, a POST's JSON body and its
`Content-Type`, and the one place the token is allowed to appear at all.

Same in-process fake style as tests/v1/unit/test_gaps_api_sse.py and
tests/v1/unit/test_fix_client.py: the transport is faked at the seam the module
owns (`_OPENER.open`) and the stream is faked at the seam `Stream` owns
(`core.events`), so no socket, no server, no thread and no sleep is involved —
`Stream.run()` is driven on the test's own thread against a fake `_halt` that
records the backoff instead of sleeping it, exactly as tests/v1/tui/test_client.py
drives it. Nothing here is Windows-specific and nothing reads the environment,
the filesystem or a terminal; every answer is explicit bytes.
"""

import email.message
import http.client
import inspect
import io
import json
import socket
import urllib.error

import pytest

from archeus.api import sse
from archeus.cli.tui import client as C, sync as S
from archeus.infra import discovery

PORT = 7337
TOKEN = 'tok_' + 'k' * 32
BASE = 'http://127.0.0.1:%d' % PORT


# ── the two seams: what `_OPENER.open` answers, and what `core.events` yields ──

class _Headers:
    """What `http.client` hands a reader's header lookups (case-insensitive)."""

    def __init__(self, **kw):
        self._h = {k.lower(): v for k, v in kw.items()}

    def get(self, name, default=None):
        return self._h.get(name.lower(), default)


class _Answer:
    """One HTTP answer: bytes to read, or — for a stream — raw wire lines to walk.

    An item of `lines` may be a callable, which the stream calls as it passes it
    (that is how a test stops a `Stream` mid-frame without a thread or a sleep).
    """

    def __init__(self, body=b'null', headers=None, lines=()):
        self.body, self.headers, self.lines = body, _Headers(**(headers or {})), list(lines)
        self.entered = self.exited = False

    def read(self):
        return self.body

    def __iter__(self):
        for item in self.lines:
            if callable(item):
                item()
                continue
            yield item

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *exc):
        self.exited = True
        return False


class _Opener:
    """`urllib.request.build_opener(...).open`: records every Request it is given."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def open(self, req, timeout=None):
        self.calls.append({'method': req.method, 'url': req.full_url, 'body': req.data,
                           'headers': {k.lower(): v for k, v in req.headers.items()},
                           'timeout': timeout})
        if not self.answers:
            raise AssertionError('the client asked %s %d times; the test scripted fewer'
                                 % (req.full_url, len(self.calls)))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    @property
    def last(self):
        return self.calls[-1]


@pytest.fixture
def opener(monkeypatch):
    """Replace the module's opener — the only way into the wire that the module
    itself does not own, and the one `test_fix_client.py`'s servers leave alone."""
    made = []

    def make(*answers):
        o = _Opener(*answers)
        made.append(o)
        monkeypatch.setattr(C, '_OPENER', o)
        return o
    return make


def _core():
    return C.Core(PORT, TOKEN)


def _refused(code, body=b'{}'):
    """The HTTPError `urllib` raises for an answer Core refused with."""
    return urllib.error.HTTPError('%s/v1/x' % BASE, code, 'refused',
                                  email.message.Message(), io.BytesIO(body))


class _Out:
    """The queue the TUI hands `Stream`: it only ever needs `put`."""

    def __init__(self):
        self.got = []

    def put(self, item):
        self.got.append(item)


class _Halt:
    """`threading.Event` for `Stream.run` on the test's own thread: `wait` records
    the backoff instead of sleeping it, and stops the loop at a bound the test
    chose, so a stream that should have stopped cannot spin the test."""

    def __init__(self, max_waits=6):
        self.waited, self._down, self.max_waits = [], False, max_waits

    def set(self):
        self._down = True

    def is_set(self):
        return self._down

    def wait(self, delay):
        self.waited.append(delay)
        if len(self.waited) >= self.max_waits:
            self._down = True


#: a scripted stream stops the reconnect loop exactly where a test puts this
QUIT = object()


class _Stream:
    """The event stream `Stream` reads: each `events(last)` call replays what the
    test scripted (frames, an exception to raise mid-stream, a callable to run,
    `QUIT` to stop) and records the cursor it was asked to resume from."""

    def __init__(self, *calls):
        self.calls, self.cursors, self.halt = list(calls), [], None

    def events(self, last):
        self.cursors.append(last)
        call = self.calls.pop(0) if self.calls else []
        if isinstance(call, BaseException):
            raise call
        for item in call:
            if isinstance(item, BaseException):
                raise item
            if item is QUIT:
                if self.halt is None:
                    raise AssertionError('QUIT scripted outside _run')
                self.halt.set()
                continue
            if callable(item):
                item()
                continue
            yield dict(item)


def _run(stream_core, max_waits=6):
    """Drive `Stream.run()` here, on the test's thread: no thread is started, and
    no backoff is slept. The scripted stream may use `QUIT` to stop the loop."""
    out, s = _Out(), C.Stream(stream_core, _Out())
    s.out, s._halt = out, _Halt(max_waits=max_waits)
    stream_core.halt = s._halt
    s.run()
    return out, s


def _signals(out):
    return [v for k, v in out.got if k == 'signal']


def _frames(out):
    return [v for k, v in out.got if k == 'frame']


# ── refusal paths: what a bad answer from Core becomes (client.py:26-33, 46-53, 87-90) ──

def test_an_error_body_that_is_not_json_is_still_a_refusal_with_the_http_status(opener):
    """client.py:49-50 — an HTML traceback, a gateway page or a truncated body must
    not become a crash and must not invent a code: the status Core answered with is
    the status, and the code falls back to `http_<status>`."""
    o = opener(_refused(500, b'<html>Traceback (most recent call last)</html>'))
    with pytest.raises(C.CoreError) as e:
        _core().get('/v1/missions')
    assert (e.value.status, e.value.code, e.value.detail) == (500, 'http_500', {})
    assert len(o.calls) == 1


@pytest.mark.parametrize('code', [400, 401, 403, 404, 409, 410, 429, 500, 503],
                          ids=lambda c: 's%d' % c)
def test_the_status_core_refused_with_is_the_status_the_refusal_carries(opener, code):
    """client.py:87-88, 53 — nothing in the client re-maps a status; the TUI and
    `cli/main` branch on it, so a collapsed 401 into 500 is a lost token story."""
    opener(_refused(code, json.dumps({'error': 'nope'}).encode('utf-8')))
    with pytest.raises(C.CoreError) as e:
        _core().get('/v1/missions')
    assert (e.value.status, e.value.code) == (code, 'nope')


def test_the_error_and_detail_core_named_are_kept_verbatim(opener):
    """client.py:53, 29-33 — `detail` is what the status line shows the operator."""
    opener(_refused(403, json.dumps({'error': 'insufficient_scope',
                                     'detail': {'scopes': ['lead']}}).encode('utf-8')))
    with pytest.raises(C.CoreError) as e:
        _core().get('/v1/missions')
    assert e.value.refusal() == {'status': 403, 'code': 'insufficient_scope',
                                 'detail': {'scopes': ['lead']}}


@pytest.mark.parametrize('body, detail', [(b'{}', {}),
                                           (b'{"detail": {"k": 1}}', {'k': 1}),
                                           (b'{"error": null}', {}),
                                           (b'{"error": ""}', {}),
                                           (b'{"error": false, "detail": []}', {})],
                          ids=['empty', 'detail-only', 'error-null', 'error-empty', 'both-falsy'])
def test_an_error_body_that_names_no_code_falls_back_and_never_keeps_a_falsy_detail(
        opener, body, detail):
    """client.py:53 (`body.get('error') or ...`) and 30 (`detail or {}`) — an empty
    or absent code is the status fallback, and an empty or absent detail is `{}`:
    a refusal is always printable, whatever the answer body left out."""
    opener(_refused(403, body))
    with pytest.raises(C.CoreError) as e:
        _core().get('/v1/x')
    err = e.value.refusal()
    assert err['status'] == 403 and err['code'] == 'http_403'
    assert err['detail'] == detail


def test_the_refusal_the_status_line_prints_is_built_from_a_detail_of_the_right_shape(opener):
    """client.py:51-53 — the body's shape is guarded (`isinstance(body, dict)`) but
    `detail` is not, and `sync.explain` dereferences it (`d.get('field')` for
    `invalid_request`, archeus/cli/tui/sync.py:120 and 152): an answer body naming a
    plain-string detail is an AttributeError inside the code that shows the error."""
    opener(_refused(400, json.dumps({'error': 'invalid_request',
                                     'detail': 'the field'}).encode('utf-8')))
    with pytest.raises(C.CoreError) as e:
        _core().get('/v1/missions')
    assert 'Invalid' in S.explain(e.value.refusal())


@pytest.mark.parametrize('boom, why', [(ConnectionRefusedError(), 'ConnectionRefusedError'),
                                       (urllib.error.URLError('refused'), 'URLError'),
                                       # socket.timeout IS TimeoutError on 3.10+, and the
                                       # class name is what the operator is told
                                       (socket.timeout(), 'TimeoutError')],
                          ids=['refused', 'urlerror', 'timeout'])
def test_a_transport_failure_is_the_network_refusal_and_names_itself_without_the_token(
        opener, boom, why):
    """client.py:89-90 — the caller's only handle on why nothing answered is
    `detail['why']`; it carries the exception's class and none of its text, which
    is where a URL (and with it anything else) would leak."""
    opener(boom)
    with pytest.raises(C.CoreError) as e:
        _core().get('/v1/missions')
    assert (e.value.status, e.value.code, e.value.detail) == (0, 'network', {'why': why})
    assert TOKEN not in repr((str(e.value), e.value.detail, e.value.refusal()))


def test_an_http_layer_break_on_a_read_is_a_network_refusal_too(opener):
    """client.py:89 — the read path must answer with Core's bytes or with a refusal."""
    opener(http.client.BadStatusLine('garbage on the wire'))
    with pytest.raises(C.CoreError) as e:
        _core().get('/v1/missions')
    assert (e.value.status, e.value.code) == (0, 'network')


# ── what goes on the wire (client.py:60, 78-108) ──

def test_the_token_is_in_exactly_one_header_and_in_nothing_else(opener):
    """client.py:80-84 — the token is a Bearer header on the loopback URL and
    appears nowhere else: not in the URL, not in a second header, and a read asks
    for JSON."""
    o = opener(_Answer(body=b'{"missions": []}'))
    _core().get('/v1/missions')
    call = o.last
    assert call['url'] == BASE + '/v1/missions' and call['method'] == 'GET'
    assert set(call['headers']) == {'authorization', 'accept'}
    assert call['headers']['authorization'] == 'Bearer ' + TOKEN
    assert call['headers']['accept'] == 'application/json'
    assert TOKEN not in call['url']
    assert [v for k, v in call['headers'].items() if TOKEN in v] == ['Bearer ' + TOKEN]


def test_a_post_is_json_with_a_content_type_and_a_get_is_neither(opener):
    """client.py:79, 81-82 — only a POST carries a body, and only a body earns a
    `Content-Type`; the body is the JSON, so a command that mutates the dict after
    sending still sends what was sent."""
    o = opener(_Answer(body=b'{"id": "msn_1"}'))
    _core().post('/v1/missions', {'title': 'ünïcode', 'n': 2})
    call = o.last
    assert call['method'] == 'POST'
    assert call['body'] == json.dumps({'title': 'ünïcode', 'n': 2}).encode('utf-8')
    assert call['headers']['content-type'] == 'application/json'
    o2 = opener(_Answer(body=b'{}'))
    _core().get('/v1/x')
    assert o2.last['body'] is None and 'content-type' not in o2.last['headers']


@pytest.mark.parametrize('body, want', [(b'', None), (b'null', None),
                                        (b'{"ok": true}', {'ok': True})],
                          ids=['empty', 'null', 'object'])
def test_an_empty_answer_reads_as_no_answer_and_not_as_a_broken_parse(opener, body, want):
    """client.py:96, 100 (`r.read() or b'null'`) — Core answers 204-style on some
    routes; without the fallback `json.loads(b'')` raises and the TUI dies on a
    successful answer."""
    opener(_Answer(body=body))
    assert _core().post('/v1/x', {}) == want


@pytest.mark.parametrize('seq, want', [('17', 17), ('0', 0), ('', None), (None, None)],
                          ids=['head-17', 'head-0', 'head-empty', 'head-absent'])
def test_the_event_head_is_a_number_or_nothing_at_all(opener, seq, want):
    """client.py:95-96 — head 0 is a real head (falsy but kept) and a head Core did
    not send is None, not 0: an `int(seq or 0)` invents a head at the very start of
    time and the connection machine would believe a read that never had one."""
    opener(_Answer(body=b'{"missions": []}', headers={'X-Archeus-Seq': seq}
                   if seq is not None else {}))
    data, head = _core().get('/v1/missions')
    assert data == {'missions': []} and type(head) is type(want) and head == want


def test_a_malformed_event_head_is_a_refusal_not_a_crash(opener):
    """client.py:95-96 — a malformed head is a broken answer, and a broken answer
    is a refusal in this module everywhere else: `get()` answers with Core's bytes
    and a number, or raises CoreError, and nothing in between."""
    opener(_Answer(body=b'{}', headers={'X-Archeus-Seq': 'not-a-number'}))
    with pytest.raises(C.CoreError):
        _core().get('/v1/missions')


def test_the_stream_reads_the_documented_route_with_the_long_timeout_and_no_cursor(opener):
    """client.py:102-108 — the stream is a GET on Core's route asking for
    `text/event-stream`, with no `Last-Event-ID` at all on a first read, and on the
    timeout that outlasts Core's heartbeat rather than the 10 s of a read."""
    o = opener(_Answer(lines=[]))
    list(_core().events())
    call = o.last
    assert call['url'] == BASE + '/v1/events/stream' and call['method'] == 'GET'
    assert call['headers']['accept'] == 'text/event-stream'
    assert 'last-event-id' not in call['headers']
    assert call['timeout'] == C.STREAM_TIMEOUT_S
    assert [v for k, v in call['headers'].items() if TOKEN in v] == ['Bearer ' + TOKEN]


def test_the_stream_timeout_is_longer_than_the_heartbeat_it_must_not_misread():
    """client.py:22 — the comment says the stream timeout is longer than Core's
    heartbeat so a quiet stream is not a lost one; shorten it below the heartbeat
    and the TUI reconnects every idle interval and shows a live Core as lost."""
    heartbeat = inspect.signature(sse.Streams.__init__).parameters['heartbeat_s'].default
    assert C.STREAM_TIMEOUT_S > heartbeat
    assert C.TIMEOUT_S < C.STREAM_TIMEOUT_S


@pytest.mark.parametrize('last_id, want', [(None, None), (0, '0'), (7, '7'),
                                           (10 ** 9, str(10 ** 9)), ('12', '12')],
                          ids=['none', 'zero', 'seven', 'big', 'string'])
def test_a_cursor_of_zero_is_still_sent_because_zero_is_a_real_position(opener, last_id, want):
    """client.py:106-107 (`is not None`, not truthiness) — replaying from head 0
    and not sending a cursor are different requests; `if last_id:` silently loses
    every event after a resync that landed on 0."""
    o = opener(_Answer(lines=[]))
    list(_core().events(last_id))
    got = o.last['headers'].get('last-event-id')
    assert got == want, (last_id, o.last['headers'])


# ── the frame reader (client.py:109-130) ──

def test_the_stream_says_it_is_open_before_any_frame_and_then_gives_the_answer_back(opener):
    """client.py:109, 108 (`with`) — the open marker is the first thing out, it is
    the only thing out of a stream that never frames, and the response is closed on
    the way out however the read ends."""
    answer = _Answer(lines=[])
    opener(answer)
    assert list(_core().events()) == [{'event': C.OPENED}]
    assert answer.exited is True


def test_a_comment_is_one_heartbeat_however_many_lines_it_spans(opener):
    """client.py:114-116, 128-129 — a comment line is a heartbeat and not a frame,
    and it is one heartbeat per event, not one per line; CRLF arrives the same."""
    opener(_Answer(lines=[b': hb\n', b': hb\n', b'\n']))
    assert list(_core().events()) == [{'event': C.OPENED}, {'event': 'heartbeat'}]
    opener(_Answer(lines=[b': hb\r\n', b'\r\n']))
    assert list(_core().events()) == [{'event': C.OPENED}, {'event': 'heartbeat'}]


def test_a_frame_is_handed_on_once_even_when_a_heartbeat_preceded_it(opener):
    """client.py:126 versus 128 (`if seen ... elif comment`) — a frame that shares
    its event with a comment is the frame, never the heartbeat and never two
    things; invert the two arms and the TUI believes an idle beat invalidated data."""
    opener(_Answer(lines=[b': hb\n', b'id: 7\n', b'event: mission.created\n',
                          b'data: {"subject": {"kind": "mission", "id": "msn_1"}}\n', b'\n']))
    assert list(_core().events()) == [{'event': C.OPENED},
                                       {'id': 7, 'event': 'mission.created',
                                        'data': {'subject': {'kind': 'mission',
                                                              'id': 'msn_1'}}}]


def test_a_frame_cut_off_before_its_blank_line_is_never_handed_on(opener):
    """client.py:126 — a frame is only real when its event ended: the last bytes of
    a dropped connection are half a frame, and handing them over would make the TUI
    act on an event Core never finished writing."""
    cut = _Answer(lines=[b'id: 1\n', b'event: mission.created\n', b'data: {"subject": "m'])
    opener(cut)
    with pytest.raises(ValueError):        # (124) the half line is not JSON: lost, not parsed
        list(_core().events())
    opener(_Answer(lines=[b'id: 1\n', b'event: mission.created\n']))
    assert list(_core().events()) == [{'event': C.OPENED}]


def test_a_blank_line_that_follows_nothing_is_not_an_event(opener):
    """client.py:126-130 — neither an empty frame nor a heartbeat is invented out of
    a bare delimiter, and the reader is reset between events."""
    opener(_Answer(lines=[b'\n', b'\n', b'id: 4\n', b'event: x\n', b'data: {}\n', b'\n']))
    assert list(_core().events()) == [{'event': C.OPENED},
                                      {'id': 4, 'event': 'x', 'data': {}}]


def test_the_frame_identity_arrives_as_a_number_because_it_is_sent_back_as_a_cursor(opener):
    """client.py:119-120 — `int(v)`, so a frame's id is a number the stream can
    replay; on the wire it is the `Last-Event-ID` of the next read, padded forms
    included."""
    opener(_Answer(lines=[b'id: 0007\n', b'event: mission.created\n', b'data: {}\n', b'\n']))
    frame = list(_core().events())[1]
    assert frame['id'] == 7 and type(frame['id']) is int
    o = opener(_Answer(lines=[]))
    list(_core().events(frame['id']))
    assert o.last['headers']['last-event-id'] == '7'


# ── the connection machine's signals (client.py:147-178) ──

def test_a_401_on_the_stream_stops_reconnecting():
    """client.py:166-168 — a credential the port will not accept does not get
    retried at the backoff rate forever: one refusal, one `unauthorized`, and the
    thread is done."""
    core = _Stream(C.CoreError(401, 'unauthorized'))
    out, s = _run(core, max_waits=8)
    assert out.got == [('signal', 'unauthorized')]
    assert len(core.cursors) == 1, 'it reconnected after a refusal that cannot work'
    assert s._halt.waited == []


def test_a_refusal_that_is_not_401_or_410_is_a_lost_stream_that_keeps_the_cursor():
    """client.py:165-177 — only 401 ends the stream and only 410 forgets the
    cursor; a 500 or a 403 is a lost stream that resumes where it stopped, so a
    restart mid-request does not replay the whole log."""
    core = _Stream([{'event': C.OPENED}, {'id': 9, 'event': 'mission.created', 'data': {}},
                    C.CoreError(503, 'http_503')],
                   [{'event': C.OPENED}, QUIT])
    out, s = _run(core, max_waits=4)
    assert core.cursors == [None, 9]
    assert 'stream_lost' in _signals(out)
    assert 'unauthorized' not in _signals(out) and 'resync' not in _signals(out)
    assert _frames(out) == [{'id': 9, 'event': 'mission.created', 'data': {}}]


def test_an_expired_cursor_exception_resyncs_and_rereads_from_the_head():
    """client.py:169-171 — a 410 means this log no longer exists: the cursor goes
    away and a resync is posted, so everything is read again instead of the stream
    sitting on a position nothing will answer for."""
    core = _Stream([{'event': C.OPENED}, {'id': 9, 'event': 'x', 'data': {}},
                    C.CoreError(410, 'cursor_expired')], [{'event': C.OPENED}, QUIT])
    out, s = _run(core, max_waits=3)
    assert _signals(out) == ['stream_open', 'frame', 'resync', 'stream_lost', 'stream_open']
    assert core.cursors == [None, None], 'the 410 must throw the cursor away, not resume on it'


def test_a_cursor_expired_frame_is_a_resync_that_forgets_the_cursor():
    """client.py:157-159 — the same signal from a frame on the wire (Core's prune
    race, api/sse.py:206): resync, cursor dropped, and no frame handed to the TUI."""
    core = _Stream([{'event': C.OPENED}, {'id': 5, 'event': 'cursor_expired',
                                          'data': {'reason': 'pruned'}}], [QUIT])
    out, s = _run(core, max_waits=2)
    assert _signals(out) == ['stream_open', 'resync', 'stream_lost']
    assert _frames(out) == []
    assert core.cursors == [None, None]


def test_a_shutdown_frame_is_dropped_without_a_frame_or_a_signal():
    """client.py:160 — Core's goodbye is not data and not invalidation: handing it
    on would make the TUI repaint off a stream that is closing, and it moves no
    cursor either, so a restart does not claim a position the log never had."""
    core = _Stream([{'event': C.OPENED}, {'id': 3, 'event': 'shutdown', 'data': {}}], [QUIT])
    out, s = _run(core, max_waits=2)
    assert _frames(out) == []
    assert 'frame' not in _signals(out)
    assert core.cursors == [None, None]


def test_the_open_marker_opens_the_connection_and_is_never_a_frame():
    """client.py:154-156 — the marker is the connection machine's `stream_open` and
    the only thing that resets the backoff; it is never posted as a frame."""
    core = _Stream([{'event': C.OPENED}, {'event': 'mission.created', 'data': {}}], [QUIT])
    out, s = _run(core, max_waits=2)
    assert _signals(out)[:2] == ['stream_open', 'frame']
    assert _frames(out) == [{'event': 'mission.created', 'data': {}}]
    assert all(f['event'] != C.OPENED for f in _frames(out))


def test_a_frame_with_no_identity_is_handed_on_but_moves_nothing():
    """client.py:161 (`f.get('id') is not None`) — a frame with no id invalidates
    the screen but is not a position; a `f.get('id')` truthiness test would drop an
    id of 0 and a missing-key KeyError would kill the stream."""
    core = _Stream([{'event': C.OPENED}, {'event': 'mission.created', 'data': {}}], [QUIT])
    out, s = _run(core, max_waits=2)
    assert _frames(out) == [{'event': 'mission.created', 'data': {}}]
    assert core.cursors == [None, None]


def test_a_frame_whose_id_is_zero_is_a_cursor():
    """client.py:161 — `id: 0` is a position, so the reconnect must ask for 0 and
    not start the log over; the `is not None` here is what a truthiness test loses."""
    core = _Stream([{'event': C.OPENED}, {'id': 0, 'event': 'x', 'data': {}}], [QUIT])
    out, s = _run(core, max_waits=2)
    assert core.cursors == [None, 0]
    assert _frames(out) == [{'id': 0, 'event': 'x', 'data': {}}]


def test_the_backoff_doubles_to_its_cap_and_starts_again_after_an_open():
    """client.py:148, 154-155, 177-178 — 0.25, then double, capped at 8 s so a Core
    that stays down is polled and not hammered, and an open stream resets it so the
    next dropout is noticed in a quarter second, not eight."""
    core = _Stream([OSError('down')], [OSError('down')], [{'event': C.OPENED}])
    out, s = _run(core, max_waits=3)
    assert s._halt.waited == [0.25, 0.5, 0.25]
    core2 = _Stream()                                    # never answers at all
    out2, s2 = _run(core2, max_waits=10)
    assert s2._halt.waited == [min(0.25 * 2 ** i, 8.0) for i in range(10)]


def test_a_halt_while_frames_are_arriving_ends_without_a_lost_signal():
    """client.py:152-153 and 174-175 — `stop()` during a burst returns at once and
    says nothing: a TUI that is closing must not be told its stream dropped, and a
    quit mid-frame must not post a frame it will never draw."""
    halt = _Halt()
    core = _Stream([{'event': C.OPENED}, {'id': 1, 'event': 'x', 'data': {}},
                    lambda: halt.set(), {'id': 2, 'event': 'y', 'data': {}}])
    out = _Out()
    s = C.Stream(core, out)
    s._halt = halt
    s.run()
    assert out.got == [('signal', 'stream_open'),
                       ('frame', {'id': 1, 'event': 'x', 'data': {}}),
                       ('signal', 'frame')]
    assert core.cursors == [None]


def test_a_malformed_frame_is_a_lost_stream_and_is_never_handed_over(opener):
    """client.py:123-124 with 172 — a `data:` line that is not JSON kills the read
    inside the frame loop; the caller must see a lost stream and reconnect, not a
    traceback (and not a half-built frame)."""
    answer = _Answer(lines=[b'id: 3\n', b'event: x\n', b'data: {oops\n', b'\n'])
    opener(answer)
    out, s = _run(C.Core(PORT, TOKEN), max_waits=1)
    assert _frames(out) == []
    assert answer.exited is True                                    # (108) closed anyway


# ── the local Core, and who may read the token (client.py:63-76) ──

def test_the_local_core_is_only_found_when_a_core_is_running_and_a_token_is_there(monkeypatch):
    """client.py:68, 76 — the one path that does reach Core: the port discovery
    named, on loopback, with the token the token file holds."""
    monkeypatch.setattr(discovery, 'discover', lambda: ('running', {'port': 4599}))
    monkeypatch.setattr(discovery, 'read_local_token', lambda: TOKEN)
    core, why = C.Core.local()
    assert (why, core.base) == (None, 'http://127.0.0.1:4599')


def test_no_core_running_reads_no_token_and_builds_no_client(monkeypatch):
    """client.py:69-70 — with the lock free the TUI says so; reading the token file
    for a Core that is not there is a token read for nobody, and starting one here
    would break A4 (the TUI never starts Core)."""
    monkeypatch.setattr(discovery, 'discover', lambda: ('not_running', None))
    monkeypatch.setattr(discovery, 'read_local_token',
                        lambda: (_ for _ in ()).throw(AssertionError('the token was read '
                                                                     'for a Core that is not running')))
    assert C.Core.local() == (None, 'not_running')


def test_an_unreadable_core_reads_no_token_and_builds_no_client(monkeypatch):
    """client.py:71-72 — the lock is held but `core.json` is missing, malformed or
    names a dead process (A5): that port may belong to someone else by now, so the
    token is never read and never sent to it."""
    monkeypatch.setattr(discovery, 'discover',
                        lambda: ('unreadable', {'port': 4599, 'pid': 4242}))
    monkeypatch.setattr(discovery, 'read_local_token',
                        lambda: (_ for _ in ()).throw(AssertionError('the token was sent '
                                                                     'towards an unverified port')))
    assert C.Core.local() == (None, 'unreadable')


def test_a_running_core_with_no_token_file_builds_no_client(monkeypatch):
    """client.py:73-75 — a Core that is running is not a Core the TUI may speak to
    without a credential: `no_token`, and no client whose token header would be
    `Bearer None`."""
    monkeypatch.setattr(discovery, 'discover', lambda: ('running', {'port': 4599}))
    monkeypatch.setattr(discovery, 'read_local_token', lambda: None)
    assert C.Core.local() == (None, 'no_token')


def test_the_stream_thread_is_a_daemon_named_for_itself():
    """client.py:140 — a non-daemon stream thread outlives the TUI and the terminal
    is never given back; the name is what a hung exit is diagnosed by."""
    s = C.Stream(_Stream(), _Out())
    assert s.daemon is True and s.name == 'archeus-tui-stream'
