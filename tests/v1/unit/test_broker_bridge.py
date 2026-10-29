"""PV-20 provider broker, execution side (PV20-08 §1): the bridge's bounded HTTP/1.1
parser, its canonical framing, and the relay over a fake pipe. No native operation."""

import io
import socket
import threading
import time

import pytest

from archeus.node import broker_bridge as W

BODY = b'{"model":"claude-x","messages":[]}'


def raw(*lines, body=b''):
    return ('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1') + body


def ok_request(body=BODY, extra=()):
    return raw('POST /v1/messages?beta=true HTTP/1.1', 'Host: 127.0.0.1:9',
               'Authorization: Bearer brk_x', 'Content-Length: %d' % len(body), *extra,
               body=body)


def test_a_request_is_parsed_and_framed_canonically():
    req = W.read_request(io.BytesIO(ok_request(extra=('anthropic-version: 2023-06-01',))))
    assert (req.method, req.path, req.query, req.body) == ('POST', '/v1/messages',
                                                          'beta=true', BODY)
    assert req.header('ANTHROPIC-VERSION') == '2023-06-01'
    again = W.read_request(io.BytesIO(W.frame(req)))
    assert again == W.read_request(io.BytesIO(W.frame(again)))
    assert again.body == BODY and again.header('content-length') == str(len(BODY))


@pytest.mark.parametrize('data', [
    raw('GET http://evil.example/v1/messages HTTP/1.1', 'Host: x'),       # absolute-form
    raw('CONNECT api.anthropic.com:443 HTTP/1.1', 'Host: x'),
    raw('GET /v1/messages HTTP/1.0', 'Host: x'),
    raw('GET /v1/%2e%2e/admin HTTP/1.1', 'Host: x'),                       # encoded alias
    raw('GET /v1/../admin HTTP/1.1', 'Host: x'),
    raw('GET //v1/messages HTTP/1.1', 'Host: x'),
    raw('GET /v1\\messages HTTP/1.1', 'Host: x'),
    raw('GET /v1/messages HTTP/1.1', 'Host: a', 'Host: b'),
    raw('GET /v1/messages HTTP/1.1', 'Authorization: a', 'authorization: b'),
    raw('GET /v1/messages HTTP/1.1', 'x-api-key: a', 'X-Api-Key: b'),
    raw('POST /v1/messages HTTP/1.1', 'Content-Length: 2', 'Content-Length: 2', body=b'{}'),
    raw('POST /v1/messages HTTP/1.1', 'Transfer-Encoding: chunked', body=b'0\r\n\r\n'),
    raw('GET /v1/messages HTTP/1.1', 'Upgrade: websocket', 'Connection: Upgrade'),
    raw('GET /v1/messages HTTP/1.1', 'X-A: 1', ' folded'),
    raw('GET /v1/messages HTTP/1.1', 'Bad Name: 1'),
    raw('POST /v1/messages HTTP/1.1', 'Host: x', body=b'{}'),            # no length
    raw('POST /v1/messages HTTP/1.1', 'Content-Length: -1'),
    raw('POST /v1/messages HTTP/1.1', 'Content-Length: 10', body=b'{}'),   # ends early
    b'GET /v1/messages HTTP/1.1\n\n',                                       # bare LF
])
def test_malformed_or_ambiguous_framing_is_refused(data):
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(data))


def test_the_bounds_hold_at_their_edge():
    many = ['X-%d: 1' % i for i in range(W.MAX_HEADERS)]
    W.read_request(io.BytesIO(raw('GET /a HTTP/1.1', *many)))
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(raw('GET /a HTTP/1.1', *many, 'X-last: 1')))
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(raw('GET /a HTTP/1.1', 'X: ' + 'a' * W.MAX_HEADER_BYTES)))
    W.read_request(io.BytesIO(ok_request(body=b'x' * 10)), max_body=10)
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(ok_request(body=b'x' * 11)), max_body=10)


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


def _exchange(bridge, data):
    with socket.create_connection(('127.0.0.1', bridge.port), timeout=5) as c:
        c.sendall(data)
        out = b''
        while True:
            chunk = c.recv(65536)
            if not chunk:
                return out
            out += chunk


def test_the_bridge_relays_one_canonical_request_and_the_reply():
    pipes = []

    def connect():
        pipes.append(Pipe())
        return pipes[-1]
    b = W.Bridge(connect)
    seen = []
    try:
        port = b.port
        assert port                              # bound before anyone is told it is ready
        b.start(seen.append)
        assert seen == [port] and b.port == port
        out = _exchange(b, ok_request())
        assert out.endswith(b'\r\n\r\nok') and out.startswith(b'HTTP/1.1 200')
        (p,) = pipes
        assert W.read_request(io.BytesIO(p.sent)).body == BODY and p.closed
    finally:
        b.close()


def test_the_bridge_answers_bad_framing_itself_and_never_opens_the_pipe():
    calls = []
    b = W.Bridge(lambda: calls.append(1) or Pipe())
    try:
        b.start(lambda port: None)
        out = _exchange(b, raw('CONNECT x:443 HTTP/1.1', 'Host: x'))
        assert out.startswith(b'HTTP/1.1 400') and calls == []
    finally:
        b.close()


def test_a_pipe_that_cannot_be_opened_is_a_502_and_a_busy_bridge_a_503():
    def nope():
        raise OSError('no pipe')
    b = W.Bridge(nope)
    try:
        b.start(lambda port: None)
        assert _exchange(b, ok_request()).startswith(b'HTTP/1.1 502')
        b._slots = threading.BoundedSemaphore(1)
        b._slots.acquire()
        # a real request, sent in full: the 503 must arrive, not a reset (PV20-09 review S-2)
        assert _exchange(b, ok_request()).startswith(b'HTTP/1.1 503')
        assert b.busy_refused == 1
    finally:
        b.close()


def test_a_busy_client_that_trickles_is_closed_after_the_total_drain_time(monkeypatch):
    monkeypatch.setattr(W, 'DRAIN_S', 0.3)
    b = W.Bridge(_nope)
    try:
        b.start(lambda port: None)
        b._slots = threading.BoundedSemaphore(1)
        b._slots.acquire()
        stop, closed = threading.Event(), threading.Event()
        with socket.create_connection(('127.0.0.1', b.port), timeout=4) as c:
            c.sendall(ok_request())

            def trickle():
                try:
                    while not stop.is_set():
                        c.sendall(b'x')
                        time.sleep(0.05)
                except OSError:
                    closed.set()        # the bridge closed on its own: the next send fails
            threading.Thread(target=trickle, daemon=True).start()
            got = _read_to_eof(c)       # the 503, then the bridge's FIN
            closed_in_time = closed.wait(2.0)
            stop.set()
        assert got.startswith(b'HTTP/1.1 503') and closed_in_time
    finally:
        b.close()


def _nope():
    raise OSError('no pipe')


@pytest.mark.parametrize('data', [
    raw('POST /v1/messages HTTP/1.1', 'X-A: b\rc', 'Host: x'),
    raw('GET /v1/messages\rX HTTP/1.1', 'Host: x'),
    raw('GET /v1/messages HTTP/1.1', 'X-A: \x00'),
    raw('GET /v1/messages HTTP/1.1', 'X-A: b\x7f'),
])
def test_a_control_character_in_a_line_is_refused(data):
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(data))


def test_a_request_without_the_broker_token_is_refused_before_its_body_is_read():
    calls = []
    b = W.Bridge(lambda: calls.append(1) or Pipe(), idle_s=0.5)
    try:
        b.start(lambda port: None)
        out = _exchange(b, raw('POST /v1/messages HTTP/1.1', 'Host: x',
                               'Authorization: Bearer nope', 'Content-Length: 100'))
        assert out.startswith(b'HTTP/1.1 401') and calls == []
    finally:
        b.close()


def test_an_idle_client_is_cut_and_gives_its_slot_back():
    b = W.Bridge(_nope, concurrent=1, idle_s=0.3)
    try:
        b.start(lambda port: None)
        with socket.create_connection(('127.0.0.1', b.port), timeout=5) as c:
            c.sendall(b'POST /v1/messages HTTP/1.1\r\nHost: x\r\n')
            got = b''
            while True:
                chunk = c.recv(65536)
                if not chunk:
                    break
                got += chunk
        assert got.startswith(b'HTTP/1.1 400')
        assert _exchange(b, ok_request()).startswith(b'HTTP/1.1 502')
    finally:
        b.close()


class Timers:
    """Stands in for threading.Timer: the test fires a request's deadline when it says so."""

    def __init__(self):
        self.made = []

    def __call__(self, delay, fn, args):
        t = _Timer(delay, fn, args)
        self.made.append(t)
        return t

    def fire_all(self):
        for t in self.made:
            t.fire()


class _Timer:
    def __init__(self, delay, fn, args):
        self.delay, self.fn, self.args, self.cancelled = delay, fn, args, False

    def start(self):
        pass

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.fn(*self.args)


def _read_to_eof(c, reset_ends_it=False):
    out = b''
    while True:
        try:
            chunk = c.recv(65536)
        except ConnectionResetError:
            if reset_ends_it:               # a cut with request bytes unread is an RST on Windows, a FIN elsewhere
                return out
            raise
        if not chunk:
            return out
        out += chunk


def test_a_request_that_trickles_past_its_deadline_is_cut_and_frees_its_slot():
    timers = Timers()
    b = W.Bridge(_nope, concurrent=1, idle_s=10.0, deadline_s=0.5, timer=timers)
    try:
        b.start(lambda port: None)
        with socket.create_connection(('127.0.0.1', b.port), timeout=5) as c:
            c.sendall(b'POST /v1/messages HTTP/1.1\r\nHost: x\r\n')
            assert _wait_for(lambda: timers.made)
            assert timers.made[0].delay == 0.5
            timers.fire_all()
            got = _read_to_eof(c, reset_ends_it=True)
        assert got == b''                   # cut: no reply, the connection just ends
        assert _exchange(b, ok_request()).startswith(b'HTTP/1.1 502')
    finally:
        b.close()


def test_a_relay_longer_than_the_deadline_is_not_cut():
    timers = Timers()

    class Slow(Pipe):
        def __init__(self):
            super().__init__(reply=b'')
            self.reply = [b'HTTP/1.1 200 OK\r\nContent-Length: 6\r\nConnection: close\r\n\r\n',
                          b'abc', b'def']
            self.started = False

        def recv(self, n):
            if not self.started:
                self.started = True
                timers.fire_all()           # the deadline passes while the reply is relayed
            return super().recv(n)
    b = W.Bridge(Slow, deadline_s=0.5, timer=timers)
    try:
        b.start(lambda port: None)
        assert _exchange(b, ok_request()).endswith(b'abcdef')
    finally:
        b.close()


@pytest.mark.parametrize('length', ['²', '9' * 5000, '+5', '-1', '5x'])
def test_a_content_length_that_is_not_ascii_digits_is_refused(length):
    data = raw('POST /v1/messages HTTP/1.1', 'Host: x', 'Authorization: Bearer brk_x',
               'Content-Length: ' + length)
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(data))
    b = W.Bridge(_nope)
    try:
        b.start(lambda port: None)
        assert _exchange(b, data).startswith(b'HTTP/1.1 400')
    finally:
        b.close()


def test_an_unexpected_error_in_the_bridge_is_a_local_500():
    def bad_connect():
        raise ValueError('not an OSError')
    b = W.Bridge(bad_connect)
    try:
        b.start(lambda port: None)
        assert _exchange(b, ok_request()).startswith(b'HTTP/1.1 500')
    finally:
        b.close()


def _wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.01)
    return cond()


def test_the_pipe_carries_only_the_broker_token_and_the_forwardable_headers():
    pipes = []

    def connect():
        pipes.append(Pipe())
        return pipes[-1]
    b = W.Bridge(connect)
    try:
        b.start(lambda port: None)
        _exchange(b, ok_request(extra=('Cookie: c=1', 'X-Api-Key: caller',
                                       'Proxy-Authorization: p', 'anthropic-version: 2023-06-01',
                                       'X-Custom: 1')))
        (p,) = pipes
        names = {k.lower() for k, _ in W.read_request(io.BytesIO(p.sent)).headers}
        assert names == {'authorization', 'anthropic-version', 'content-length'}
    finally:
        b.close()
