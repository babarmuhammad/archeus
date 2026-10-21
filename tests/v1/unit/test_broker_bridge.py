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
        # sent nothing: a busy bridge answers at once, without reading a request it will
        # not serve (unread bytes would turn its close into a reset, not a 503)
        assert _exchange(b, b'').startswith(b'HTTP/1.1 503')
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


def test_a_request_that_trickles_past_its_deadline_is_cut_and_frees_its_slot():
    b = W.Bridge(_nope, concurrent=1, idle_s=1.0, deadline_s=0.5)
    try:
        b.start(lambda port: None)
        with socket.create_connection(('127.0.0.1', b.port), timeout=5) as c:
            c.sendall(b'POST /v1/messages HTTP/1.1\r\nHost: x\r\n')
            for _ in range(60):             # each line well inside the idle limit
                try:
                    c.sendall(b'X-A: 1\r\n')
                except OSError:
                    break
                time.sleep(0.05)
            assert _exchange(b, ok_request()).startswith(b'HTTP/1.1 502')
    finally:
        b.close()


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
