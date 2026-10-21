"""PV-20 provider broker against a fake upstream on loopback (PV20-08 §1, §4): the real
`send_upstream`, a registered provider proxy at an exact loopback endpoint. SSE order,
upstream errors relayed, redirects never followed, a grant ending mid-stream, no retry,
and the whole path bridge -> broker over an in-process pipe. No native operation."""

import http.server
import io
import json
import socket
import threading
import time

import pytest

from archeus.node import broker as B
from archeus.node import broker_bridge as W

MODEL = 'claude-x'
BODY = b'{"model":"claude-x","messages":[]}'
EVENTS = [b'event: message_start\ndata: {"n":1}\n\n', b'event: ping\ndata: {}\n\n',
          b'event: content_block_delta\ndata: {"n":2}\n\n', b'event: message_stop\ndata: {}\n\n']


class Upstream:
    def __init__(self):
        self.hits, self.seen = [], []
        up = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                up.hits.append(self.path)
                up.seen.append((dict(self.headers), body))
                mode = json.loads(body).get('mode')
                if mode == 'redirect':
                    self.send_response(302)
                    self.send_header('Location', 'http://127.0.0.1:1/elsewhere')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                if mode == 'error':
                    msg = b'{"type":"error","error":{"type":"overloaded_error"}}'
                    self.send_response(529)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(msg)))
                    self.end_headers()
                    self.wfile.write(msg)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Connection', 'close')
                self.end_headers()
                for ev in EVENTS:
                    self.wfile.write(ev)
                    self.wfile.flush()
                    time.sleep(0.02)

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def upstream():
    u = Upstream()
    yield u
    u.close()


class Transport:
    def __init__(self):
        self.closed = []

    def create(self, name, principal):
        return name

    def launch_bridge(self, endpoint, binding):
        return 1

    def close(self, endpoint):
        self.closed.append(endpoint)


def make(port, live=lambda b, d: True):
    up = B.Upstream('http://127.0.0.1:%d' % port, 'provider_proxy')
    b = B.Broker(core_instance='c1', live=live, credentials=lambda bd: {'x-api-key': 'K'},
                 upstream_of=lambda a: up, transport=Transport())
    bd = B.BrokerBinding(core_instance='c1', execution_id='exe_1', process_seq=1,
                         principal='p', route_decision_id='rte_1', account_id='acc_1',
                         harness_id='claude_code', model=MODEL, upstream=up,
                         limits=B.BrokerLimits(max_requests=10, idle_s=5))
    token, _, _, _ = b.issue(bd)
    return b, token


def req(token, *extra, mode=None):
    """A request whose body, forwarded verbatim, tells the fake upstream what to do."""
    doc = {'model': MODEL, 'messages': []}
    if mode:
        doc['mode'] = mode
    body = json.dumps(doc, separators=(',', ':')).encode()
    lines = ['POST /v1/messages HTTP/1.1', 'Host: x', 'Authorization: Bearer ' + token,
             'Content-Length: %d' % len(body), *extra]
    return io.BytesIO(('\r\n'.join(lines) + '\r\n\r\n').encode() + body)


def run(b, data):
    out = []
    row = b.serve(data, out.append, 'p')
    return b''.join(out), row


def test_sse_events_arrive_in_order_and_the_upstream_sees_core_credentials(upstream):
    b, token = make(upstream.port)
    out, row = run(b, req(token, 'anthropic-version: 2023-06-01'))
    assert row['status'] == 200 and out.split(b'\r\n\r\n', 1)[1] == b''.join(EVENTS)
    (headers, body), = upstream.seen
    low = {k.lower(): v for k, v in headers.items()}
    assert body == BODY and low['x-api-key'] == 'K' and 'authorization' not in low
    assert low['anthropic-version'] == '2023-06-01'


def test_an_upstream_error_is_relayed_as_it_is(upstream):
    b, token = make(upstream.port)
    out, row = run(b, req(token, mode='error'))
    assert row['status'] == 529 and out.startswith(b'HTTP/1.1 529')
    assert out.endswith(b'overloaded_error"}}')


def test_a_redirect_is_not_followed(upstream):
    b, token = make(upstream.port)
    out, row = run(b, req(token, mode='redirect'))
    assert row['status'] == 502 and upstream.hits == ['/v1/messages']


def test_a_stream_ends_when_its_grant_does(upstream):
    state = {'n': 0}

    def live(bd, d):
        state['n'] += 1
        return state['n'] <= 2              # authorize, then one chunk
    b, token = make(upstream.port, live)
    out, row = run(b, req(token))
    body = out.split(b'\r\n\r\n', 1)[1]
    assert row['status'] == 200 and body and body != b''.join(EVENTS)


def test_an_unreachable_upstream_is_one_502_never_a_retry():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()                               # nothing listens there now
    b, token = make(port)
    assert run(b, req(token))[1]['status'] == 502


def test_a_proxy_that_is_not_loopback_gets_no_grant():
    b = B.Broker(core_instance='c1', live=lambda *a: True, credentials=lambda bd: {},
                 upstream_of=None, transport=Transport())
    bd = B.BrokerBinding(core_instance='c1', execution_id='exe_1', process_seq=1, principal='p',
                         route_decision_id='r', account_id='a', harness_id='claude_code',
                         model=MODEL, upstream=B.Upstream('http://10.1.2.3:8080',
                                                          'provider_proxy'),
                         limits=B.BrokerLimits(max_requests=1))
    with pytest.raises(B.Refused):
        b.issue(bd)


def test_bridge_to_broker_end_to_end_over_an_in_process_pipe(upstream):
    """The CLI's view: plain HTTP to the bridge; Core parses the bridge's canonical copy
    again and answers through the same pipe."""
    b, token = make(upstream.port)

    class Pipe:
        def __init__(self):
            self.buf, self.out = b'', []

        def sendall(self, data):
            self.buf += data

        def recv(self, n):
            if self.buf is not None:
                b.serve(io.BytesIO(self.buf), self.out.append, 'p')
                self.buf = None
            return self.out.pop(0) if self.out else b''

        def close(self):
            pass
    bridge = W.Bridge(Pipe)
    try:
        bridge.start(lambda port: None)
        with socket.create_connection(('127.0.0.1', bridge.port), timeout=5) as c:
            c.sendall(req(token).getvalue())
            got = b''
            while True:
                chunk = c.recv(65536)
                if not chunk:
                    break
                got += chunk
        assert got.startswith(b'HTTP/1.1 200') and got.endswith(EVENTS[-1])
    finally:
        bridge.close()
