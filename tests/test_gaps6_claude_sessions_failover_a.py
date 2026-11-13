"""T-1282: claude_sessions/failover.py:230-369 (proxy guard, body intake, route split,
profile lookup, forwarded headers, passthrough and relay); candidate gaps, not coverage.

Ranked final probes (denial/fail-closed first, then boundaries, then error paths):
1  :359 test_post_guard_refusal_reads_no_body_and_forwards_nothing
2  :346 test_get_guard_refusal_reads_no_marker_and_forwards_nothing
3  :365 test_negative_content_length_refused_before_read            (strict xfail)
4  :365 test_oversized_content_length_refused_before_body_read      (strict xfail)
5  :363 test_malformed_content_length_refused_not_forwarded_empty   (strict xfail)
6  :366 test_only_exact_messages_paths_enter_failover
7  :244 test_pinned_profile_reloaded_per_request_never_borrows      (closest: test_failover.py profile-by-id tests)
8  :255 test_forwarded_auth_from_selected_profile_hop_by_hop_out
9  :324 test_upstream_exception_text_not_in_client_error_body      (strict xfail)
10 :309 test_relay_disconnect_closes_owned_conn_without_retry

Seams: object.__new__(_Handler) with fake _guard/_proxy.guard outcome, BytesIO
rfile/wfile, scripted _open/_relay/_passthrough/_failover and fake response/socket.
Only the guard, marker and profile lookups are faked where they would reach disk;
settings are a synthetic dict. No sockets, subprocesses or real home reads.
"""

import email.message
import io
import json

import pytest

from claude_sessions import config as _c
from claude_sessions import failover

_CAP = 64 << 20


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(_c, 'settings_file', str(tmp_path / 'archeus.json'))
    monkeypatch.setattr(failover, '_marker_path', lambda: str(tmp_path / 'marker'))
    monkeypatch.setattr(failover, '_marker', lambda: b'synthetic-marker')


class _Body(io.BytesIO):
    def __init__(self, data=b''):
        super().__init__(data)
        self.reads = []

    def read(self, n=-1):
        self.reads.append(n)
        return super().read(n)


def _handler(command='POST', path='/v1/messages', headers=None, body=b''):
    h = object.__new__(failover._Handler)
    h.command = command
    h.path = path
    h.headers = email.message.Message()
    for k, v in (headers or {}).items():
        h.headers[k] = v
    h.rfile = _Body(body)
    h.wfile = io.BytesIO()
    h.sent = []
    h.close_connection = False
    h.send_response = lambda code, *a: h.sent.append(('status', code))
    h.send_header = lambda k, v: h.sent.append(('header', k, v))
    h.end_headers = lambda: h.sent.append(('end',))
    h._note = lambda *a: None
    h._learn = lambda *a: None
    return h


def _guard(monkeypatch, verdict):
    calls = []

    def fake(handler, key, marker_path, label):
        calls.append((key, label))
        return verdict

    monkeypatch.setattr(failover._proxy, 'guard', fake)
    return calls


def _route(h, monkeypatch):
    routed = []
    h._passthrough = lambda body: routed.append(('passthrough', body))
    h._failover = lambda body: routed.append(('failover', body))
    return routed


class _Sock:
    def __init__(self):
        self.timeouts = []

    def settimeout(self, t):
        self.timeouts.append(t)


class _Conn:
    def __init__(self, sock=None):
        self.sock = sock
        self.closed = 0

    def close(self):
        self.closed += 1


class _Resp:
    def __init__(self, status, chunks=(), headers=(('Content-Type', 'text/event-stream'),),
                 content_length='10'):
        self.status = status
        self._chunks = list(chunks)
        self._headers = list(headers)
        self._cl = content_length

    def getheader(self, name):
        return self._cl if name == 'Content-Length' else None

    def getheaders(self):
        return list(self._headers)

    def read(self, n=-1):
        step = self._chunks.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


def test_post_guard_refusal_reads_no_body_and_forwards_nothing(monkeypatch):
    _guard(monkeypatch, False)
    h = _handler('POST', '/v1/messages', {'Content-Length': '12'}, b'{"model":"a"}')
    routed = _route(h, monkeypatch)

    h.do_POST()

    assert h.rfile.reads == []
    assert routed == []
    assert h.sent == [] and h.wfile.getvalue() == b''


def test_get_guard_refusal_reads_no_marker_and_forwards_nothing(monkeypatch):
    _guard(monkeypatch, False)
    marker_reads = []
    monkeypatch.setattr(failover, '_marker', lambda: marker_reads.append(1) or b'm')
    h = _handler('GET', failover._marker_path())
    passed = []
    h._passthrough = lambda body: passed.append(body)

    h.do_GET()

    assert marker_reads == []
    assert passed == []
    assert h.sent == [] and h.wfile.getvalue() == b''


@pytest.mark.xfail(strict=True, reason="failover.py:362-365 passes a negative Content-Length to rfile.read(n) unchecked")
def test_negative_content_length_refused_before_read(monkeypatch):
    """Premise: a negative Content-Length is invalid HTTP and must be refused, not
    handed to rfile.read(-1), which reads to EOF on a socket."""
    _guard(monkeypatch, True)
    h = _handler('POST', '/v1/messages', {'Content-Length': '-1'}, b'x')
    routed = _route(h, monkeypatch)

    h.do_POST()

    assert not any(n < 0 for n in h.rfile.reads)
    assert routed == []


@pytest.mark.xfail(strict=True, reason="failover.py:365 has no request-size cap; rfile.read(n) takes the raw Content-Length")
def test_oversized_content_length_refused_before_body_read(monkeypatch):
    """Premise: a body far beyond any Claude request is refused before rfile.read
    is asked for it. _CAP is the test's bound, not a value taken from the source."""
    _guard(monkeypatch, True)

    class _Empty(_Body):
        def read(self, n=-1):
            self.reads.append(n)
            return b''

    h = _handler('POST', '/v1/messages', {'Content-Length': str(1 << 40)})
    h.rfile = _Empty()
    routed = _route(h, monkeypatch)

    h.do_POST()

    assert all(n <= _CAP for n in h.rfile.reads)
    assert routed == []


@pytest.mark.xfail(strict=True, reason="failover.py:363-364 normalizes a malformed Content-Length to 0 and forwards an empty body")
def test_malformed_content_length_refused_not_forwarded_empty(monkeypatch):
    """Premise: an unparsable Content-Length is a client error (400), not a zero-
    length body that is then forwarded upstream."""
    _guard(monkeypatch, True)
    h = _handler('POST', '/v1/messages', {'Content-Length': 'abc'}, b'{"model":"a"}')
    routed = _route(h, monkeypatch)

    h.do_POST()

    assert routed == []


@pytest.mark.parametrize('path, expected', [
    ('/v1/messages', 'failover'),
    ('/v1/messages/count_tokens', 'failover'),
    ('/v1/messages?beta=true', 'failover'),
    ('/v1/messages/count_tokens?beta=true', 'failover'),
    ('/v1/messages2', 'passthrough'),
    ('/v1/messages/', 'passthrough'),
    ('/v1/messages/count_tokens/x', 'passthrough'),
])
def test_only_exact_messages_paths_enter_failover(monkeypatch, path, expected):
    _guard(monkeypatch, True)
    body = b'{"model":"a"}'
    h = _handler('POST', path, {'Content-Length': str(len(body))}, body)
    routed = _route(h, monkeypatch)

    h.do_POST()

    assert routed == [(expected, body)]


def test_pinned_profile_reloaded_per_request_never_borrows(monkeypatch):
    settings = {
        'provider_active': 'pb',
        'providers': [
            {'id': 'pa', 'name': 'A', 'base_url': 'http://127.0.0.1:1/a', 'api_key': 'ka'},
            {'id': 'pb', 'name': 'B', 'base_url': 'http://127.0.0.1:2/b', 'api_key': 'kb'},
        ],
    }
    monkeypatch.setattr(_c, 'load_settings', lambda: settings)
    monkeypatch.setattr(failover, '_SERVING', 'pa')
    h = _handler()

    first = h._profile()
    assert first['id'] == 'pa' and first['api_key'] == 'ka'

    settings['providers'][0]['base_url'] = 'http://127.0.0.1:3/new'
    assert h._profile()['base_url'] == 'http://127.0.0.1:3/new'

    settings['providers'] = [settings['providers'][1]]
    assert h._profile() is None


def test_forwarded_auth_from_selected_profile_hop_by_hop_out(monkeypatch):
    h = _handler('POST', '/v1/messages', {
        'Host': 'caller.invalid',
        'Content-Length': '999',
        'Authorization': 'Bearer caller',
        'x-api-key': 'caller',
        'Connection': 'keep-alive',
        'Transfer-Encoding': 'chunked',
        'anthropic-version': '2023-06-01',
        'Content-Type': 'application/json',
    })
    before = list(h.headers.items())

    out = h._fwd_headers(5, {'api_key': 'synthetic-key'})

    assert 'Host' not in out and 'Connection' not in out and 'Transfer-Encoding' not in out
    assert out['Content-Length'] == '5'
    assert out['Authorization'] == 'Bearer synthetic-key'
    assert out['x-api-key'] == 'synthetic-key'
    assert out['anthropic-version'] == '2023-06-01'
    assert out['Content-Type'] == 'application/json'
    assert list(h.headers.items()) == before

    keyless = h._fwd_headers(0, {'api_key': ''})
    assert 'Authorization' not in keyless and 'x-api-key' not in keyless
    assert keyless['Content-Length'] == '0'


def test_upstream_unreachable_returns_502_without_exception_text(monkeypatch):
    h = _handler()
    h._profile = lambda: {'id': 'p'}

    def _open(prof, body, timeout=None):
        raise OSError('synthetic dial failure')

    h._open = _open

    h._passthrough(b'{}')

    assert h.sent[0] == ('status', 502)
    payload = json.loads(h.wfile.getvalue())
    assert payload['error']['type'] == 'api_error'


@pytest.mark.xfail(strict=True, reason="failover.py:322-324 copies the raw exception text into the client error body")
def test_upstream_exception_text_not_in_client_error_body(monkeypatch):
    """Premise: the client error body names the failure, not the raw exception text
    that may carry an upstream address or a credential fragment."""
    h = _handler()
    h._profile = lambda: {'id': 'p'}

    def _open(prof, body, timeout=None):
        raise OSError('dial synthetic-host failed with SYNTHETIC-TOKEN-123')

    h._open = _open

    h._passthrough(b'{}')

    assert b'SYNTHETIC-TOKEN-123' not in h.wfile.getvalue()


def test_relay_disconnect_closes_owned_conn_without_retry(monkeypatch):
    sock = _Sock()
    conn = _Conn(sock)
    resp = _Resp(200, chunks=[b'part1', ConnectionResetError('client left')])
    opened = []
    h = _handler('POST', '/v1/messages')
    h._profile = lambda: {'id': 'p', 'failover_models': ['b']}

    def _open(prof, body, timeout=None):
        opened.append(json.loads(body)['model'])
        return conn, resp

    h._open = _open

    h._failover(json.dumps({'model': 'a', 'x': 1}).encode())

    assert len(opened) == 1
    assert h.wfile.getvalue() == b'part1'
    assert conn.closed == 1
    assert sock.timeouts[-1] is None


def test_relay_streaming_response_marks_connection_close(monkeypatch):
    sock = _Sock()
    conn = _Conn(sock)
    resp = _Resp(200, chunks=[b'data: 1\n\n', b''], content_length=None)
    h = _handler('POST', '/v1/messages')

    h._relay(resp, conn, {})

    assert h.close_connection is True
    assert h.wfile.getvalue() == b'data: 1\n\n'
    assert conn.closed == 1
