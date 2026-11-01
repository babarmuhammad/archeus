"""T-233: the ten highest-risk GAPs of the T-211 broker test inventory, as tests.

Fail-closed and trust-boundary gaps first: the real network exit `send_upstream`, the
pinned TLS connection, the shipped `NativeTransport`, the resolver failure paths,
non-OSError upstream failures, the 2xx stream deadline, the bridge's drain byte cap,
same-name duplicate forwarded headers, request-line framing the parser has never seen,
and the client-gone paths. Same in-process fakes and the same loopback-socket style as
test_provider_broker.py, test_broker_bridge.py and test_broker_execution.py: no native
operation, no network beyond the loopback sockets those files already use, no long-lived
server outliving a test.
"""

import http.client
import io
import socket
import ssl
import threading
import time

import pytest

from archeus.core.domain import ids
from archeus.node import broker as B
from archeus.node import broker_bridge as W

MODEL = 'claude-x'
UPSTREAM_KEY = 'sk-ant-api03-UPSTREAM-SECRET'
BODY = b'{"model":"claude-x","messages":[{"role":"user","content":"hi"}]}'

# ── the fake transport, fake upstream and request helpers of test_provider_broker.py ──


class Transport:
    def __init__(self, fail_launch=False):
        self.created, self.closed, self.fail_launch = [], [], fail_launch

    def create(self, name, principal):
        self.created.append((name, principal))
        return 'ep%d' % len(self.created)

    def launch_bridge(self, endpoint, binding):
        if self.fail_launch:
            raise B.BrokerUnavailable('no Job')
        return 4321

    def close(self, endpoint):
        self.closed.append(endpoint)


class Resp:
    def __init__(self, status=200, headers=(), chunks=(b'ok',), reason='OK'):
        self.status, self.reason, self._h, self._c = status, reason, list(headers), list(chunks)

    def getheaders(self):
        return self._h

    def read1(self, n):
        return self._c.pop(0) if self._c else b''

    def read(self, n):
        data = b''.join(self._c)
        self._c = []
        return data[:n]


def binding(**kw):
    kw = dict(dict(core_instance='core1', execution_id=ids.new_id('execution'), process_seq=1,
                   principal='archeus.x', route_decision_id='rte_1', account_id='acc_1',
                   harness_id='claude_code', model=MODEL,
                   upstream=B.Upstream('https://api.example.com'),
                   limits=B.BrokerLimits(max_requests=3)), **kw)
    return B.BrokerBinding(**kw)


def broker(live=True, send=None, transport=None, **kw):
    calls = []

    def default_send(up, addrs, method, path, headers, body, timeout):
        calls.append((up, addrs, method, path, dict(headers), body))
        return Resp(headers=[('content-type', 'application/json'), ('request-id', 'r1')])
    kw.setdefault('resolve', lambda host, port: ['93.184.216.34'])
    b = B.Broker(core_instance='core1',
                 live=live if callable(live) else (lambda bd, d: live),
                 credentials=lambda bd: {'x-api-key': UPSTREAM_KEY},
                 upstream_of=lambda a: B.Upstream('https://api.example.com'),
                 transport=transport or Transport(),
                 send=send or default_send, **kw)
    return b, calls


def request(method='POST', target='/v1/messages', token=None, body=BODY, extra=()):
    lines = ['%s %s HTTP/1.1' % (method, target), 'Host: 127.0.0.1:4321']
    if token:
        lines.append('Authorization: Bearer %s' % token)
    lines += list(extra)
    if method == 'POST':
        lines.append('Content-Length: %d' % len(body))
    else:
        body = b''
    return io.BytesIO(('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1') + body)


def serve(b, data, principal='archeus.x'):
    out = []
    row = b.serve(data, out.append, principal)
    return b''.join(out), row


def issued(b, **kw):
    bd = binding(**kw)
    token, d, ep, port = b.issue(bd)
    return bd, token, d


def _body(out):
    return out.split(b'\r\n\r\n', 1)[1]


# ── the fake pipe and loopback-socket helpers of test_broker_bridge.py ──


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


def _exchange(bridge, data):
    with socket.create_connection(('127.0.0.1', bridge.port), timeout=5) as c:
        c.sendall(data)
        return _read_to_eof(c, reset_ends_it=True)


def _read_to_eof(c, reset_ends_it=False):
    out = b''
    while True:
        try:
            chunk = c.recv(65536)
        except ConnectionResetError:
            if reset_ends_it:               # a close with bytes the bridge never read is an RST
                return out
            raise
        if not chunk:
            return out
        out += chunk


# ── 1. send_upstream: the only real network exit, and the no-proxy claim ──

def test_send_upstream_builds_exactly_the_checked_connection_and_reads_no_proxy(monkeypatch):
    made = []

    class Conn:
        def __init__(self, *a, **kw):
            made.append(('plain', a, kw))

        def request(self, method, path, body=None, headers=None):
            made.append(('request', method, path, body, tuple(sorted(headers.items()))))

        def getresponse(self):
            return 'RESP'

    class Pinned(Conn):
        def __init__(self, host, addr, port, timeout):
            made.append(('pinned', host, addr, port, timeout))

    monkeypatch.setattr(http.client, 'HTTPConnection', Conn)
    monkeypatch.setattr(B, '_Pinned', Pinned)
    # the variables a proxy-aware client would read: every connection made must ignore them
    for var in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy',
               'all_proxy'):
        monkeypatch.setenv(var, 'http://127.0.0.1:9/')

    assert B.send_upstream(B.Upstream('https://api.example.com/v2/'), ['93.184.216.34'],
                           'POST', '/v1/messages?beta=true', {'a': 'b'}, b'{}', 5) == 'RESP'
    # the TLS connection is built for the name but aimed at the already-checked address
    assert made[0] == ('pinned', 'api.example.com', '93.184.216.34', 443, 5)
    assert made[1] == ('request', 'POST', '/v2/v1/messages?beta=true', b'{}', (('a', 'b'),))
    made.clear()

    B.send_upstream(B.Upstream('http://127.0.0.1:8080', 'provider_proxy'), ['127.0.0.1'],
                    'POST', '/v1/messages', {}, b'{}', 7)
    # the proxy is the exact registered loopback endpoint, never the proxy sink
    assert made[0] == ('plain', ('127.0.0.1', 8080), {'timeout': 7})
    assert not any(e[1][1] == 9 for e in made if e[0] == 'plain')         # never the sink


# ── 2. _Pinned: the socket goes to the checked address, TLS verifies the name ──
#
# A test-only CA and a certificate for `broker.test`, never used outside this file and
# this loopback server: static material so the test needs no generator and no network.

_CA_PEM = """-----BEGIN CERTIFICATE-----
MIIDLzCCAhegAwIBAgIUJx3cmY7fxYtv+dKFFrnX1FoetsYwDQYJKoZIhvcNAQEL
BQAwHjEcMBoGA1UEAwwTUFYyMCBicm9rZXIgdGVzdCBDQTAgFw0yNjEwMzAxMjE4
MzNaGA8yMTI2MTAwNjEyMTgzM1owHjEcMBoGA1UEAwwTUFYyMCBicm9rZXIgdGVz
dCBDQTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBALVKRWGFSNvwGbAC
gJG0IQleFn9YiIalsrG9NzcV7QUfVvCpVcZRDM9MuvgS8QS1FOTCMWWoPWyinL1h
b4/jQYHiQcjifkprO2zJpzU7HbagWG7lCT0kLWrOlKoTuJObOG3YSpR/RfxGwd8+
cKoTZDcdV6qjs4Zo41mBixgJgjFrhuEPoSslSxJprLRlGgVSnEgGFUoH/maSEM1a
wW/dDO/jrM88M5FEGtVxNRhYgP1+iMsc0xrQwRrmFdxoSW0pDeSqkroiERvYoRSF
yC8nuyblwLfLPdMMXPdKO0bjn8mvvkakYizs6uS7sGXtFVjpDwpfXyXpiBgOuA2s
OaWh4AsCAwEAAaNjMGEwHQYDVR0OBBYEFJs8hjQzwuAY9Niqf+gyFi6kbVLCMB8G
A1UdIwQYMBaAFJs8hjQzwuAY9Niqf+gyFi6kbVLCMA8GA1UdEwEB/wQFMAMBAf8w
DgYDVR0PAQH/BAQDAgEGMA0GCSqGSIb3DQEBCwUAA4IBAQBowRBVdE8padZ9oHqC
OrM5DD68VIqC7YGhWgYMR4xbhgx6J/2bHUrJVT4zQ1xQjJ/Jcrd6xWsD/BUQ9aEj
ghDxkFPd6E14UrbrD54n4tZni9PSBy+X6kzNcJtnEWq7j7re74+kScyg3CxEguXL
Z4k3XnFdkF6tiIBx/+gaIRiLbsHEP52sLQDTbi0PMQwXyD5ltJ4YiK8+IBf3xGaY
x02w9lG8d0yhi4IlNWshg7WGU0Vik/uxsCe7JORiHGKnR6x6WQP0Oj71bGI7vq6f
U6qIE27g2zqbdPblD6y9N+eL/CsjVuTwp5NVumHUmkQrPCTL1twB5u9/7UVFsuBY
F40N
-----END CERTIFICATE-----
"""

_SERVER_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIIDUzCCAjugAwIBAgIUDBnUplBfG5T2Zj1isK0GsSjQ4CAwDQYJKoZIhvcNAQEL
BQAwHjEcMBoGA1UEAwwTUFYyMCBicm9rZXIgdGVzdCBDQTAgFw0yNjEwMzAxMjE4
MzNaGA8yMTI2MTAwNjEyMTgzM1owFjEUMBIGA1UEAwwLYnJva2VyLnRlc3QwggEi
MA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQC2d2qy0Ptlv7vKUmWxmydwSahI
oZ1kMfCxZ0BPJHCMmDvjGHIsvLaT2LZI5jmnY0/vjTvIVI+oavS0al4vPlZ+U33e
GZWAakm+V3s06nxAHA2GC7BfvKAq9Qpgf2KixIYpe3GByP8epVNp79zvdjrOyfX4
5/QmiCqXM6IaCn+8t7i53SbkpVgtlrjSOqNcIQ0sCUJed6auXa994O9omKk41CIN
A7VXi1t8iJyqvEd8LoFH27tLc7h+UEwBLQzrdOAjN0mUWwa6RbU4cfMN9U7DxHO6
G7IjBw0M+D/D3S2f85uSdVLJz9GxI4wsCdKvz5T6GUYLzOSTRhf3yObewomFAgMB
AAGjgY4wgYswFgYDVR0RBA8wDYILYnJva2VyLnRlc3QwDAYDVR0TAQH/BAIwADAO
BgNVHQ8BAf8EBAMCB4AwEwYDVR0lBAwwCgYIKwYBBQUHAwEwHQYDVR0OBBYEFI49
yZlfutr7jynwkYrALQl0eyJAMB8GA1UdIwQYMBaAFJs8hjQzwuAY9Niqf+gyFi6k
bVLCMA0GCSqGSIb3DQEBCwUAA4IBAQCDupwJeNegsePDl7NDNu7SUaJHYFG3VPX2
YoUjFYlYHWx297gBrE+8TUY24VaAc3P8JSKwg/PGfmJSBIC/Mcxh/mkNtQTMTRFy
cBvYbEPp/6wjpblSCTmLGm1s+Rc/C7Irx1D2vAyiFWIC6SpKw+7Jo9JZ/sM3ESHc
YjXDLuoAFE42v3MukX8MBRPduVDEAwIstNl4Q1zPK5ErSNP7r0knW4o04Xr5qfr3
cT4aun0WzlQDo+dCkAwl1BZOuu4Oj8NUFZ6iS5FaOJ6Z2hQYPZhoez4LzW7WsCSf
duWUpG4Ri/71p5x/lZJb4EEOV8suXQPuCOiG7o8c06eerer6rfT7
-----END CERTIFICATE-----
"""

_SERVER_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC2d2qy0Ptlv7vK
UmWxmydwSahIoZ1kMfCxZ0BPJHCMmDvjGHIsvLaT2LZI5jmnY0/vjTvIVI+oavS0
al4vPlZ+U33eGZWAakm+V3s06nxAHA2GC7BfvKAq9Qpgf2KixIYpe3GByP8epVNp
79zvdjrOyfX45/QmiCqXM6IaCn+8t7i53SbkpVgtlrjSOqNcIQ0sCUJed6auXa99
4O9omKk41CINA7VXi1t8iJyqvEd8LoFH27tLc7h+UEwBLQzrdOAjN0mUWwa6RbU4
cfMN9U7DxHO6G7IjBw0M+D/D3S2f85uSdVLJz9GxI4wsCdKvz5T6GUYLzOSTRhf3
yObewomFAgMBAAECggEAExVbuy54sIxUQWWLPb9OqWOGvmvquGUxuXglRXG39Lhi
QQ7YOB4XkVBvxiGQA5XzMQhqKXpQmQpwo+LhDVtdc/Ja/mzaEjdrlYT0PZVNn+3f
KzcTP/wMG1oL9wozoHbh2jpPJYYGSqf7WJ/N0Vyh62k7eMgXpKUGoVA04rjY4b1/
FqgFw9Ds54IL2n6eFWWD3/3Oe5MAbJvgtu40/IhSiYFpNl+Z4xrIZp92UqpG8gha
GwXlNaT7pkdWTesTrekScHrDo83KY0Fc3gor6FyQ4UwuDImEHm/zQYcVTQNuGFPr
czqIZAGydZdQp+uP5QYAGga/YZxX25wKvxYTso+5aQKBgQDZF2JWI7N4HTvzkYBq
xt6KQWeWysd+iSoZXQsG+QlL5U4ZNvbbzst7cHEfVbc57sY6FLpMdSCAHxj3Tnmn
+c/by1vpQdE4GkqqYf9x7KCC/o8Z2anoTsuidMwYxdKDszCZc5OPri1VRelfEudn
Ut5l9APRDF2EU5S3IHMwYyu9bQKBgQDXK16N8TO7bUpQZ5l9sAt1QX+slvwYzzQK
jXMdBhC4dIObp3Rv4nSnZsowNfg1xm2kUzQ/it0HAV4iKh6cThorAcTedQOdMRKO
74tfHP/uCK1jL+4lTHcvtuOGKd8cVYtIS0WcSDeHYR+X0uHLMDOrc4W0LdeeUyMH
EVz8PIJleQKBgQCrlLXeSz1P1BtMOVX8Ds5ZC7SqE/903Uhu34EVs8NLPyNo/m5B
8MIXABoIoCC/Ix99TGCqiXB0kx+SZ23z+5fzqlkslR6dbvpQjD/vdQywPC4ySjzm
JVEBR7sAYWovOXNR9W1NhGbEHQuEX1aR7YdloWVa1qEbM0w5KOah+d/aSQKBgDTS
r9bW5SVZMkpE9LiXdGin2MktE9yfWZ5RlXYFnCs8Z2baGEqzZIIISRDG3xWMjjQu
PQBwfcyPeGWYw4UJ44C1YXhfb7CycGTox+VkwCvWs4JLLQK5H/V1x6uTMfPJyHTK
Dd/NFtzEajYijk4MmlK3/JX8PxfePxYoHBTMYhK5AoGAZrde3vQYNFsxgjf15Pb+
mo7cGteQTTgvLRdpFlCiGcxC1c0HZ5NUi11KX8TbrXPPWI3T4CRpjyxzCRLLEREJ
0VdjPcQk70GZPK2oD5UCFtLdyRFVHRvSIX2F89n8mIH2HMv/O9PGPwJfDidxTl6L
Vki9DAftjKGQkfm1fL08grI=
-----END PRIVATE KEY-----
"""


class _TlsServer:
    """A loopback TLS server holding the test certificate for `broker.test`. It records
    completed handshakes and the request bytes of each one; a handshake that the client
    refuses never contributes a request. It dies with the test."""

    def __init__(self, tmp_path):
        cert = tmp_path / 'srv.crt'
        key = tmp_path / 'srv.key'
        cert.write_text(_SERVER_CERT_PEM)
        key.write_text(_SERVER_KEY_PEM)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        self._ctx = ctx
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.requests = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                client, _ = self.sock.accept()
            except OSError:
                return
            try:
                tls = self._ctx.wrap_socket(client, server_side=True)
            except OSError:                       # the client refused the certificate
                try:
                    client.close()
                except OSError:
                    pass
                continue
            try:
                self.requests.append(tls.recv(4096))
                tls.sendall(b'HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n'
                            b'Connection: close\r\n\r\n')
            except OSError:
                pass
            try:
                tls.close()
            except OSError:
                pass

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


def test_the_pinned_connection_goes_to_the_checked_address_but_verifies_the_name(tmp_path,
                                                                                 monkeypatch):
    server = _TlsServer(tmp_path)
    ca = tmp_path / 'ca.crt'
    ca.write_text(_CA_PEM)

    def default_context():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(str(ca))        # trust the test CA; nothing else can
        return ctx
    monkeypatch.setattr(B.ssl, 'create_default_context', default_context)
    try:
        good = B._Pinned('broker.test', '127.0.0.1', server.port, 5.0)
        good.connect()
        assert isinstance(good.sock, ssl.SSLSocket)          # TLS over the checked address
        good.request('GET', '/v1/messages')
        assert good.getresponse().status == 204              # the server served the request
        good.close()
        # a name the certificate does not cover dies in the handshake, before a single
        # request byte: a re-resolved or substituted address is never trusted. And the
        # name would not even resolve — a SSLCertVerificationError can only mean the
        # socket went to the pinned address, as it must.
        bad = B._Pinned('evil.test', '127.0.0.1', server.port, 5.0)
        with pytest.raises(ssl.SSLCertVerificationError):
            bad.connect()
        assert len(server.requests) == 1
        assert server.requests[0].startswith(b'GET /v1/messages HTTP/1.1')
    finally:
        server.close()


# ── 3. the shipped NativeTransport: fail closed, every operation ──

def test_the_shipped_native_transport_refuses_everything_a_grant_would_need():
    t = B.NativeTransport()
    with pytest.raises(B.BrokerUnavailable):
        t.create('archeus.pv20.broker.core1.exec1.1.aabb', 'archeus.x')
    with pytest.raises(B.BrokerUnavailable):
        t.launch_bridge('ep1', binding())         # not just create(): the launch refuses too
    assert t.close('ep1') is None                  # and closing is a harmless no-op


# ── 4. check_destination: DNS trouble closes the route, it never opens one ──

def _dns_down(host, port):
    raise OSError('dns down')


@pytest.mark.parametrize('resolve,status', [
    (_dns_down, 502),
    (lambda host, port: [], 403),
])
def test_a_resolver_that_fails_or_names_nothing_issues_nothing(resolve, status):
    with pytest.raises(B.Refused) as raised:
        B.check_destination(B.Upstream('https://api.example.com'), resolve)
    assert raised.value.status == status
    b, calls = broker(resolve=resolve)
    with pytest.raises(B.Refused) as raised:
        issued(b)
    assert raised.value.status == status
    assert calls == [] and b.transport.created == [] and b._grants == {}    # nothing created


@pytest.mark.parametrize('upstream,resolve', [
    (B.Upstream('https://api.example.com:not-a-port'), lambda host, port: ['93.184.216.34']),
    (B.Upstream('http://127.0.0.1:not-a-port', 'provider_proxy'), None),
    (B.Upstream('https://api.example.com'), lambda host, port: ['not-an-ip']),
])
def test_an_upstream_that_cannot_be_read_is_refused_not_raised(upstream, resolve):
    with pytest.raises(B.Refused) as raised:
        B.check_destination(upstream, resolve)
    assert raised.value.status == 403


# ── 5. an upstream failure that is not an OSError is still a local 502 ──

def test_an_upstream_failure_that_is_not_an_oserror_is_a_local_502_and_never_retried():
    sent = []

    def boom(*a):
        sent.append(a)
        raise http.client.HTTPException('bad status line')
    b, _ = broker(send=boom)
    _, token, d = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 502 and row['bytes_out'] == 0 and len(sent) == 1
    assert out == W.local_reply(502, 'Bad Gateway')
    assert b._in_flight == 0 and b._grants[d]['active'] == 0


# ── 6. a 2xx stream that outlives the deadline ends at the deadline ──

def test_a_stream_that_outlives_its_deadline_ends_at_it():
    now, reads = [0.0], [0]

    class Trickle(Resp):
        def read1(self, n):
            now[0] += 0.3
            reads[0] += 1
            return b'x' if reads[0] <= 1000 else b''
    b, _ = broker(send=lambda *a: Trickle(status=200), clock=lambda: now[0])
    _, token, d = issued(b, limits=B.BrokerLimits(max_requests=3, deadline_s=1.0, idle_s=5.0))
    out, row = serve(b, request(token=token))
    # an upstream that stalls a 200 stream forever is bounded by the deadline, not by luck
    assert row['status'] == 200 and reads[0] <= 5 and reads[0] >= 1
    assert _body(out) == b'x' * reads[0] and row['bytes_out'] == reads[0]
    assert d in b._grants and b._in_flight == 0    # the deadline ended it; no leak cut happened


# ── 7. the bridge's drain byte cap: how much a refused client may still push ──

def test_a_refused_client_that_floods_past_the_drain_cap_is_closed_at_it(monkeypatch):
    monkeypatch.setattr(W, 'DRAIN_BYTES', 2048)
    monkeypatch.setattr(W, 'DRAIN_S', 100.0)       # the time cap cannot fire: only the cap can
    b = W.Bridge(_nope)
    try:
        b.start(lambda port: None)
        b._slots = threading.BoundedSemaphore(1)
        b._slots.acquire()
        stop, closed = threading.Event(), threading.Event()
        with socket.create_connection(('127.0.0.1', b.port), timeout=5) as c:
            got = b''
            while b'\r\n\r\n' not in got:          # the 503 arrives before anything is pushed
                chunk = c.recv(64)
                assert chunk, 'the busy refusal never arrived'
                got += chunk
            assert got.startswith(b'HTTP/1.1 503')

            def push():                            # what a refused, untrusted client may not do
                try:                               # is push past the cap and stay open forever
                    while not stop.is_set():
                        c.sendall(b'y' * 4096)
                        time.sleep(0.01)
                except OSError:
                    closed.set()                   # the bridge fully closed on its own
            p = threading.Thread(target=push, daemon=True)
            p.start()
            # the bridge must close the connection at the byte cap, not wait out the clock:
            # with DRAIN_S at 100 s, only the 2048-byte cap can end this within 5 seconds
            assert closed.wait(5.0), 'the flooding client was never closed out'
            stop.set()
            p.join(5)
        assert b.busy_refused == 1
    finally:
        b.close()


# ── 8. same-name duplicate forwarded headers: the defined behaviour, not an accident ──

def test_a_repeated_forwarded_header_reaches_the_upstream_once_with_its_last_value():
    b, calls = broker()
    _, token, _ = issued(b, limits=B.BrokerLimits(max_requests=4))
    _, row = serve(b, request(token=token, extra=('anthropic-beta: tools-1',
                                                  'anthropic-beta: slow-wink')))
    assert row['status'] == 200 and len(calls) == 1
    (_, _, _, _, headers, _), = calls
    low = {k.lower(): v for k, v in headers.items()}
    assert low['anthropic-beta'] == 'slow-wink'                    # the dict build: last wins
    assert not any('tools-1' in v for v in low.values())           # the first is gone, defined
    # and both occurrences entered the credential check: neither alone is a credential
    # word, the two joined are a subscription token, so nothing is sent
    _, row = serve(b, request(token=token, extra=('anthropic-beta: sk-an',
                                                  'anthropic-beta: t-oat01-SPLITSECRET')))
    assert row['status'] == 403 and len(calls) == 1


# ── 9. request-line and header-name framing the parser met only beside these ──

@pytest.mark.parametrize('data', [
    b'GET /x HTTP/1.1 extra\r\n\r\n',              # four fields on the request line
    b'GET HTTP/1.1\r\n\r\n',                       # two fields: no target at all
    b'POST /v1/\xff HTTP/1.1\r\n\r\n',             # a non-ASCII target
    b'GET /x HTTP/1.1\r\nX\xff: 1\r\n\r\n',        # a non-ASCII header name
    b'GET /x HTTP/1.1\r\n: 1\r\n\r\n',             # an empty header name
])
def test_the_parser_refuses_a_request_line_or_name_outside_the_wire(data):
    with pytest.raises(W.BadRequest):
        W.read_request(io.BytesIO(data))
    calls = []
    b = W.Bridge(lambda: calls.append(1) or Pipe())
    try:
        b.start(lambda port: None)
        assert _exchange(b, data).startswith(b'HTTP/1.1 400') and calls == []
    finally:
        b.close()


# ── 10. the client that goes away: never a crash, never a spurious 500 ──

def test_a_client_that_goes_away_mid_response_never_crashes_the_broker_or_the_bridge():
    def gone(data):
        raise OSError('client gone')
    b, calls = broker()
    # an unauthenticated request: the refusal is answered to a client that is already off
    row = b.serve(request(token='brk_nope'), gone, 'archeus.x')
    assert row['status'] == 401 and calls == []
    assert len(b.audit) == 1 and b.audit[-1] is row        # audited, returned, never raised
    s = socket.socket()
    s.close()
    W._send(s, b'anything')                                # silent against a closed client


# ── a grant is refused at issue for limits and identity it could never serve ──

@pytest.mark.parametrize('limits', [
    dict(concurrent=0), dict(max_body=0), dict(deadline_s=0), dict(deadline_s=-1.0),
    dict(concurrent=True), dict(max_body='9'), dict(deadline_s=None)])
def test_a_grant_with_a_limit_that_can_never_be_met_is_refused_at_issue(limits):
    # T-657#13: concurrent=0 was a permanent 429, max_body=0 a permanent 413
    b, _ = broker()
    with pytest.raises(B.Refused) as raised:
        b.issue(binding(limits=B.BrokerLimits(max_requests=3, **limits)))
    assert raised.value.status == 403
    assert b.transport.created == [] and not b._grants


@pytest.mark.parametrize('field', ['principal', 'execution_id', 'account_id', 'harness_id',
                                   'model'])
@pytest.mark.parametrize('value', ['', None])
def test_a_binding_with_an_empty_identity_field_is_refused_at_issue(field, value):
    # T-657#2: principal='' plus a transport reporting '' authorised the empty client
    b, _ = broker()
    with pytest.raises(B.Refused) as raised:
        b.issue(binding(**{field: value}))
    assert raised.value.status == 403 and not b._grants


def test_case_variants_of_a_forwarded_header_reach_the_upstream_once():
    # T-657#9: the dict was keyed on the raw name, so both spellings went upstream
    b, calls = broker()
    _, token, _ = issued(b, limits=B.BrokerLimits(max_requests=4))
    _, row = serve(b, request(token=token, extra=('Anthropic-Beta: tools-1',
                                                  'anthropic-beta: slow-wink')))
    assert row['status'] == 200
    (_, _, _, _, headers, _), = calls
    assert [v for k, v in headers.items() if k.lower() == 'anthropic-beta'] == ['slow-wink']
