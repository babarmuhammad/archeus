"""T-716: the ten highest-risk uncovered branches of archeus/node/broker_bridge.py.

Fail-closed and denial paths first (a missing Authorization, a padded bearer token, the
bridge's own 413, the cumulative header budget, the colonless header line), then the
canonical-frame and forwarding decisions, then the boundary values of Content-Length,
and last the error paths (a pipe that dies mid-relay, a busy refusal that must never
move a slot). Same in-process fakes and loopback-socket style as test_broker_bridge.py
and test_broker_gaps.py: the only OS calls are the ones those files already make, and
the pipe to Core is always a fake. No native operation, no real process, no network
beyond loopback, nothing platform-specific, nothing written to disk.
"""

import io
import socket
import threading

import pytest

from archeus.node import broker_bridge as W

BODY = b'{"model":"claude-x","messages":[]}'


def raw(*lines, body=b''):
    return ('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1') + body


def ok_request(body=BODY, extra=()):
    return raw('POST /v1/messages?beta=true HTTP/1.1', 'Host: 127.0.0.1:9',
               'Authorization: Bearer brk_x', 'Content-Length: %d' % len(body), *extra,
               body=body)


class Pipe:
    """A fake connection to Core's pipe: records what was sent, answers *reply*."""

    def __init__(self, reply=b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok'):
        self.sent, self.reply, self.closed = b'', [reply], False

    def sendall(self, data):
        self.sent += data

    def recv(self, n):
        return self.reply.pop(0) if self.reply else b''

    def close(self):
        self.closed = True


def _nope():
    raise OSError('no pipe')


def _read_to_eof(c, reset_ends_it=False):
    out = b''
    while True:
        try:
            chunk = c.recv(65536)
        except ConnectionResetError:
            if reset_ends_it:       # a close with bytes the bridge never read is an RST
                return out
            raise
        if not chunk:
            return out
        out += chunk


def _exchange(bridge, data):
    with socket.create_connection(('127.0.0.1', bridge.port), timeout=5) as c:
        c.sendall(data)
        return _read_to_eof(c, reset_ends_it=True)


# ── 1. no Authorization header at all: the bridge refuses, it does not crash or admit ──
#
# Source branch: `_admit_bridge`, `if not _BRK_AUTH.fullmatch(req.header('authorization')
# or ''): raise Unauthorized` (broker_bridge.py:101-103). Every existing test sends some
# Authorization value; none omits the header. Drop the `or ''` and header() returns None
# (AttributeError -> a 500, not a 401); drop the raise and an unauthenticated request
# reaches the pipe.

def test_a_request_with_no_authorization_header_at_all_is_refused_before_the_pipe():
    calls = []
    b = W.Bridge(lambda: calls.append(1) or Pipe())
    try:
        b.start(lambda port: None)
        no_auth_post = raw('POST /v1/messages HTTP/1.1', 'Host: x',
                           'Content-Length: %d' % len(BODY), body=BODY)
        assert _exchange(b, no_auth_post).startswith(b'HTTP/1.1 401')
        # a GET without a Content-Length too: admission decides before any length logic
        no_auth_get = raw('GET /v1/messages HTTP/1.1', 'Host: x')
        assert _exchange(b, no_auth_get).startswith(b'HTTP/1.1 401')
        assert calls == []                          # the pipe to Core was never opened
    finally:
        b.close()


# ── 2. the bearer token is admitted only in its exact shape ──
#
# Source branch: `_BRK_AUTH.fullmatch` (broker_bridge.py:43 and 102). Existing tests use
# one wrong value ('Bearer nope'). Switch fullmatch to match, or widen the scheme or the
# token class, and each padded/smuggled shape below is admitted instead of refused; the
# accepted side pins the scheme's case-insensitivity and the full token character class.

@pytest.mark.parametrize('value,verdict', [
    ('Bearer brk_ok smuggled', 401),                # fullmatch -> match would admit this
    ('brk_ok', 401),                                # no scheme at all
    ('Basic brk_ok', 401),                          # the wrong scheme
    ('Bearer  brk_ok', 401),                        # two spaces: the regex wants exactly one
    ('Bearer\tbrk_ok', 401),                        # an interior tab (tab survives the strip)
    ('Bearer brk.ok', 401),                         # '.' is not in the token class
    ('Bearer brk_', 401),                           # an empty token after the prefix
    ('bEARer brk_A-_9', 200),                       # scheme case-free, full token class
], ids=['smuggled', 'no-scheme', 'wrong-scheme', 'two-spaces', 'inner-tab', 'dot',
        'empty-token', 'good-case-free'])
def test_only_the_exact_bearer_shape_of_the_broker_token_is_admitted(value, verdict):
    pipes = []
    b = W.Bridge(lambda: pipes.append(Pipe()) or pipes[-1])
    try:
        b.start(lambda port: None)
        data = raw('POST /v1/messages HTTP/1.1', 'Host: x', 'Authorization: ' + value,
                   'Content-Length: %d' % len(BODY), body=BODY)
        out = _exchange(b, data)
        if verdict == 401:
            assert out.startswith(b'HTTP/1.1 401') and pipes == []
        else:
            assert out.endswith(b'\r\n\r\nok')
            (p,) = pipes
            req = W.read_request(io.BytesIO(p.sent))
            assert req.header('authorization') == value     # relayed byte for byte
    finally:
        b.close()


# ── 3. the bridge's own 413: a declared body over MAX_BODY dies on the head alone ──
#
# Source branches: `if n > cap: raise TooLarge` (broker_bridge.py:165-166), reached with
# `_admit_bridge` through `_serve`'s `except BadRequest: _send(local_reply(r.status ...))`
# (broker_bridge.py:286-287), and the `cap = min(max_body, admit(req))` line (156).
# No existing test ever raises broker_bridge.TooLarge (the 413s elsewhere come from
# Core's own limits in broker.py). Invert `>` and the server waits for 16 MB instead,
# and the 413 status only exists if TooLarge.status survives.

def test_an_oversized_declared_body_is_a_413_answered_before_any_body_byte_is_read():
    calls = []
    b = W.Bridge(lambda: calls.append(1) or Pipe())
    try:
        b.start(lambda port: None)
        head_only = raw('POST /v1/messages HTTP/1.1', 'Host: x',
                        'Authorization: Bearer brk_x',
                        'Content-Length: %d' % (W.MAX_BODY + 1))
        assert _exchange(b, head_only).startswith(b'HTTP/1.1 413')
        assert calls == []                                     # no body, no pipe
    finally:
        b.close()
    # the parser side of the same line: the admit() cap, not max_body, decides, and
    # min() means the smaller of the two always wins
    over = raw('POST /x HTTP/1.1', 'Authorization: Bearer brk_x', 'Content-Length: 3',
               body=b'abc')
    with pytest.raises(W.TooLarge) as raised:
        W.read_request(io.BytesIO(over), max_body=10 ** 9, admit=lambda req: 2)
    assert raised.value.status == 413
    fit = raw('POST /x HTTP/1.1', 'Authorization: Bearer brk_x', 'Content-Length: 2',
              body=b'ab')
    assert W.read_request(io.BytesIO(fit), max_body=10 ** 9, admit=lambda req: 2).body \
        == b'ab'
    with pytest.raises(W.TooLarge):                            # min, not max: max_body wins
        W.read_request(io.BytesIO(ok_request(body=b'x' * 11)), max_body=10,
                       admit=lambda req: 10 ** 9)


# ── 4. the header budget is total bytes across all lines, not a per-line limit ──
#
# Source branches: `budget -= len(raw) + 2` in the header loop (broker_bridge.py:132)
# and `line = f.readline(budget + 1); if len(line) > budget or not line.endswith(...)`
# in `_line` (broker_bridge.py:93-95). The existing bound test only sends ONE oversized
# line; delete the per-line budget subtraction and 40 lines of 900 bytes each (~36 KB)
# are parsed, and the exact-fill side pins the off-by-ones on both checks (the blank
# terminator itself must fit inside the budget).

def test_the_header_budget_is_total_bytes_across_lines_not_a_per_line_limit():
    start = 'GET /a HTTP/1.1'
    budget = W.MAX_HEADER_BYTES - len(start) - 2
    many = ['X-%03d: %s' % (i, 'v' * 900) for i in range(40)]
    assert 40 < W.MAX_HEADERS                          # 'too many headers' cannot fire
    assert max(len(m) for m in many) * 4 < budget      # every line is small on its own
    assert sum(len(m) + 2 for m in many) > budget + 1000
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(raw(start, *many)))
    # the exact edge: fill the budget to its last two bytes (the blank terminator's
    # share) and it parses; one more byte anywhere and it is refused
    fixed = ['X-a: ' + 'v' * 500, 'X-b: ' + 'v' * 500]
    used = sum(len(f) + 2 for f in fixed)
    fill = budget - used - 2
    last = 'X-z: ' + 'v' * (fill - 2 - len('X-z: '))
    assert len(last) + 2 == fill
    W.read_request(io.BytesIO(raw(start, *fixed, last)))
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(raw(start, *fixed, last + 'v')))


# ── 5. a header line with no colon at all is refused ──
#
# Source branch: `if not sep or not name or not set(name) <= _TOKEN` (broker_bridge.py:
# 142-143) with the line carrying no ':'. Existing tests cover an empty name (': 1', sep
# is present) and a name with illegal characters (a colon is present); none removes the
# separator. Drop `not sep` and a bare line becomes a header with name ''... actually
# with name equal to the whole line, which Core would then frame onward.

def test_a_header_line_without_a_colon_is_refused():
    data = ok_request(extra=('X-No-Colon',))
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(data))
    calls = []
    b = W.Bridge(lambda: calls.append(1) or Pipe())
    try:
        b.start(lambda port: None)
        assert _exchange(b, data).startswith(b'HTTP/1.1 400') and calls == []
    finally:
        b.close()


# ── 6. frame(): exactly one Content-Length, and it always describes the body ──
#
# Source branch: the `k.lower() != 'content-length'` filter and the appended canonical
# line inside frame() (broker_bridge.py:177-178). The existing relay test collects header
# names into a SET, which cannot see a duplicate. Remove the filter and the stale value
# rides alongside the canonical one (two Content-Length lines on the pipe, which Core
# refuses and the CLI would never recover from).

def test_the_frame_carries_exactly_one_content_length_that_matches_the_body():
    stale = W.Request('POST', '/x', (('Content-Length', '999'), ('X-A', 'b')), b'abc')
    framed = W.frame(stale)
    assert b'999' not in framed
    lines = framed.split(b'\r\n\r\n', 1)[0].lower().split(b'\r\n')
    assert [l for l in lines if l.startswith(b'content-length:')] == [b'content-length: 3']
    assert framed.endswith(b'\r\n\r\nabc')
    # and over the pipe: the kept headers plus frame() must hold one length, not zero or
    # two, even though the request as received carried its own Content-Length line
    pipes = []
    b = W.Bridge(lambda: pipes.append(Pipe()) or pipes[-1])
    try:
        b.start(lambda port: None)
        _exchange(b, ok_request())
        (p,) = pipes
        head = p.sent.split(b'\r\n\r\n', 1)[0].lower()
        assert head.count(b'content-length:') == 1
        assert W.read_request(io.BytesIO(p.sent)).header('content-length') == str(len(BODY))
    finally:
        b.close()


# ── 7. the forward list and the credential gate, decided on the bridge itself ──
#
# Source branches: `forwarded()` (`n in FORWARD and not any(w in n for w in NEVER)`,
# broker_bridge.py:82-84) inside the keep filter of _serve (broker_bridge.py:296-297).
# The existing relay test forwards exactly one listed name (anthropic-version); the
# other four are never sent through a bridge, and the NEVER half is only exercised on
# Core's side of the pipe. Drop the `and not any(...)` clause and a listed name that
# carries a credential word rides the pipe the moment FORWARD gains an entry.

def test_the_forward_list_and_the_credential_gate_decide_what_reaches_the_pipe(monkeypatch):
    monkeypatch.setattr(W, 'FORWARD', W.FORWARD | {'x-secret-leak', 'proxy-cookie'})
    assert 'x-secret-leak' in W.FORWARD and W.forwarded('anthropic-beta')
    assert not W.forwarded('X-Secret-Leak') and not W.forwarded('Proxy-Cookie')
    pipes = []
    b = W.Bridge(lambda: pipes.append(Pipe()) or pipes[-1])
    try:
        b.start(lambda port: None)
        _exchange(b, ok_request(extra=(
            'anthropic-version: v1', 'anthropic-beta: b1', 'content-type: application/json',
            'accept: application/json', 'user-agent: cli/1', 'cookie: c=1',
            'x-api-key: caller', 'x-secret-leak: s', 'Proxy-Cookie: c')))
        (p,) = pipes
        names = {k.lower() for k, _ in W.read_request(io.BytesIO(p.sent)).headers}
        assert names == {'authorization', 'content-length', 'anthropic-version',
                         'anthropic-beta', 'content-type', 'accept', 'user-agent'}
    finally:
        b.close()


# ── 8. Content-Length: the twelve/thirteen-digit cliff and the zero body ──
#
# Source branches: `_DIGITS = re.compile(r'[0-9]{1,12}')` with
# `if not _DIGITS.fullmatch(length)` (broker_bridge.py:33, 162-163) and `n = int(length)`
# feeding `n > cap` (164-166). Existing values are '²', '9'*5000, '+5', '-1', '5x': the
# 12/13-digit edge itself is untested, where a {1,12} -> {1,13} change turns a clean
# "not a number" refusal into a 413 (or, past int()'s trust boundary, into a different
# refusal). '0' -> empty body is the other untested corner.

def test_content_length_digit_count_and_zero_body_boundaries():
    def parse(length):
        data = raw('POST /x HTTP/1.1', 'Authorization: Bearer brk_x',
                   'Content-Length: ' + length, body=b'')
        return W.read_request(io.BytesIO(data))
    with pytest.raises(W.TooLarge) as raised:                # 12 digits: a number, but huge
        parse('9' * 12)
    assert raised.value.status == 413
    with pytest.raises(W.BadRequest) as raised:               # 13 digits: not a number at all
        parse('1' + '0' * 12)
    assert not isinstance(raised.value, W.TooLarge)
    req = parse('0')                                          # zero: a legitimate empty body
    assert req.body == b'' and req.header('content-length') == '0'


# ── 9. a pipe that dies mid-relay: the connection ends, no 500, no lost slot ──
#
# Source branches: `except OSError: pass` and `finally: pipe.close()` around the relay
# (broker_bridge.py:304-313) and the `finally: self._slots.release()` of _serve (314-315).
# test_broker_gaps.py only throws a closed socket at _send. If the relay OSError were
# re-raised, serve() would answer a spurious 500 to a client that already saw upstream
# bytes (two answers for one request); if the finally blocks were dropped, every dead
# pipe would permanently burn one of the CONCURRENT slots.

@pytest.mark.parametrize('fail_at', ['send', 'recv'])
def test_a_pipe_that_dies_mid_relay_ends_silently_and_returns_its_slot(fail_at):
    class Dying(Pipe):
        def __init__(self):
            super().__init__(reply=b'')
            self.reads = 0

        def sendall(self, data):
            if fail_at == 'send':
                raise ConnectionResetError('the pipe died at send')
            super().sendall(data)

        def recv(self, n):
            self.reads += 1
            if fail_at == 'recv':
                if self.reads == 1:
                    return b'HTTP/1.1 200 OK\r\n\r\nstream-data-A'
                raise ConnectionResetError('the pipe died mid-stream')
            return super().recv(n)

    dying, healthy = Dying(), Pipe()
    queue = [dying, healthy]
    b = W.Bridge(lambda: queue.pop(0) if queue else _nope())
    try:
        b.start(lambda port: None)
        out = _exchange(b, ok_request())
        assert out == (b'' if fail_at == 'send' else b'HTTP/1.1 200 OK\r\n\r\nstream-data-A')
        assert b'500' not in out and dying.closed              # silent, and the pipe was closed
        assert _exchange(b, ok_request()).endswith(b'\r\n\r\nok')   # the slot came back
    finally:
        b.close()


# ── 10. a busy refusal never moves a slot ──
#
# Source branch: the early return of _serve when `self._slots.acquire(blocking=False)`
# fails (broker_bridge.py:274-279): it must NOT run the `finally: release` that guards
# every accepted request. Move the acquire inside the try (or add a release) and the
# BoundedSemaphore either raises ValueError (the client then sees a 500 after the 503)
# or, past the bound, the bridge silently gains unbounded slots.

def test_a_busy_refusal_never_touches_the_slot_count(monkeypatch):
    monkeypatch.setattr(W, 'DRAIN_S', 0.2)         # bounded, well under a second
    b = W.Bridge(_nope)
    try:
        b.start(lambda port: None)
        b._slots = threading.BoundedSemaphore(1)
        b._slots.acquire()
        for _ in range(2):
            assert _exchange(b, ok_request()) == W.local_reply(503, 'Busy')
        assert b.busy_refused == 2
        b._slots.release()                          # free the one slot the test took
        assert _exchange(b, ok_request()).startswith(b'HTTP/1.1 502')
    finally:
        b.close()


# ── extra (below the ten, still fail-closed-relevant): the path check looks only at the
# path, never at the query ──
#
# Source branch: `path = target.partition('?')[0]` before the dot/percent/backslash
# checks (broker_bridge.py:125-129). Applying those checks to the whole target would
# refuse every legitimately encoded query; skipping them on the path lets '/v1/./admin'
# or '/v1\messages' through.

def test_dot_and_percent_rules_bind_the_path_not_the_query():
    ok = W.read_request(io.BytesIO(raw('GET /v1/messages?next=..%2Fadmin&b=\\x HTTP/1.1',
                                       'Host: x')))
    assert ok.path == '/v1/messages' and ok.query == 'next=..%2Fadmin&b=\\x'
    for target in ('/v1/./admin', '/./x', '/v1/../admin'):
        with pytest.raises(W.BadRequest):
            W.read_request(io.BytesIO(raw('GET %s HTTP/1.1' % target, 'Host: x')))
