"""The refusals of `archeus/api/server.py` that nothing else reaches (T-308).

§4's pipeline is a sequence of fail-closed gates, and each has a bound or an
order this suite pins and no other test does: the Host check runs against a
request with no Host header at all, a token in the query is refused on the very
routes that need no credential, `Content-Length` is read as a number and bounded
on BOTH sides before it reaches `rfile.read`, and the refusals keep the
documented order when one request is oversized *and* cross-site *and* carries a
URL token. The socket half is asserted too: the stdlib's own refusals answer in
our shape, a HEAD gets the headers without the body, the request pool never
swallows a slot and never starves the stream, and the lingering close is bounded
in bytes and in time.

Where the judge's client cannot go, the request is written on a bare socket: a
request with no Host header, a broken request line, a `Content-Length` the
server must not turn into a read length. Nothing here makes an OS call beyond
the sockets the suite always opens, starts a process, or sleeps.
"""

import json
import socket
import sys
import threading
import time

import pytest

from archeus.api import routes, server
from archeus.infra.eventlog import outbox
from v1.judge.http import SSEClient, TempCore, free_port, request

MAX_BODY = server.MAX_BODY
CSP = ("default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; "
       "frame-ancestors 'none'")


@pytest.fixture
def core(archeus_home):
    c = TempCore(archeus_home).start()
    yield c
    c.stop()


@pytest.fixture
def unread_at_finish(monkeypatch):
    """How much the client still had in flight when the handler finished. The
    same hook as tests/v1/integration/conftest.py's fixture of this name, which a
    unit test cannot reach: the peek must run before `finish`'s own linger drains
    the socket, and before the close. A read of a still-live socket is a race, so
    the peek is bounded by the 0.5 s the conftest documents."""
    done, unread, real = threading.Event(), [], server.Handler.finish

    def finish(self):
        if self.command == 'POST':
            self.connection.settimeout(0.5)
            try:
                unread.append(len(self.connection.recv(1 << 20, socket.MSG_PEEK)))
            except OSError:
                unread.append(0)
            self.connection.settimeout(None)
            done.set()
        real(self)
    monkeypatch.setattr(server.Handler, 'finish', finish)
    return done, unread


def _head(core):
    with core.core.db.read() as conn:
        return outbox.head(conn)


def _keys(core):
    with core.core.db.read() as conn:
        return conn.execute('SELECT COUNT(*) FROM idempotency_keys').fetchone()[0]


class _Reply:
    """What a bare socket sees: the status line (None for the headerless answer
    the stdlib gives a request line it could not parse), the headers, the bytes,
    and the socket error that ended the exchange, if any."""

    def __init__(self, status, headers, body, error):
        self.status, self.headers, self.body, self.error = status, headers, body, error

    def json(self):
        return json.loads(self.body)


def _split(out):
    head, sep, body = out.partition(b'\r\n\r\n')
    if not sep or not head.startswith(b'HTTP/'):
        return None, {}, out                                # a headerless HTTP/0.9 answer
    lines = head.split(b'\r\n')
    words = lines[0].split(b' ')
    status = int(words[1]) if len(words) > 1 and words[1].isdigit() else None
    headers = {}
    for line in lines[1:]:
        k, colon, v = line.partition(b':')
        if colon:
            headers[k.decode('latin-1').lower().strip()] = v.decode('latin-1').strip()
    return status, headers, body


def _raw(core, line, headers=(), body=b'', timeout=5.0):
    """One request on a bare socket, in a single write of head plus body: a
    refusal then happens over bytes that are already in the peer's queue, which is
    the situation §4's lingering close exists for. Stops at the end of the answer
    rather than at the close, so a refusal that goes on to linger stays quick;
    the headerless answer has no length to stop at and is read to the close."""
    head = ('%s\r\n' % line).encode('latin-1') + ''.join(
        '%s: %s\r\n' % kv for kv in headers).encode('latin-1') + b'\r\n'
    out, err = b'', None
    s = socket.create_connection(('127.0.0.1', core.port), timeout=timeout)
    s.settimeout(timeout)
    try:
        try:
            s.sendall(head + body)
        except OSError as e:
            err = type(e).__name__
        while True:
            try:
                chunk = s.recv(65536)
            except OSError as e:
                err = err or type(e).__name__
                break
            if not chunk:
                break
            out += chunk
            status, h, payload = _split(out)
            if status is not None and len(payload) >= int(h.get('content-length') or 0):
                break
    finally:
        s.close()
    status, hdrs, payload = _split(out)
    return _Reply(status, hdrs, payload, err)


def _base(core, host=True, token=True, extra=()):
    """The framing a client library would send: a Host (a name, none at all, or
    the loopback one), a credential, and a close so the exchange has an end."""
    h = [('Connection', 'close')]
    if host is True:
        h.insert(0, ('Host', '127.0.0.1:%d' % core.port))
    elif host:
        h.insert(0, ('Host', host))
    if token:
        h.insert(0, ('Authorization', 'Bearer ' + core.token))
    return h + list(extra)


def _post(core, path, body=b'', length=None, *, headers=(), **kw):
    """A POST whose framing is spelled out, so a test can name a length the bytes
    do not have. No `length` means the honest one."""
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    h = _base(core, extra=[('Content-Type', 'application/json'),
                           ('Content-Length', str(len(raw) if length is None else length))]
                        + list(headers), **kw)
    return _raw(core, 'POST %s HTTP/1.1' % path, h, raw)


def _get(core, path, *, headers=(), **kw):
    return _raw(core, 'GET %s HTTP/1.1' % path, _base(core, extra=list(headers), **kw))


# ── the Host gate, on a request no client library would send ──

def test_a_request_that_names_no_host_at_all_is_refused_as_not_local(core):
    """server.py `_serve`: `if not self.api.origin.host_ok(self.headers.get('Host'))`.
    The judge's client always sends a Host, so nothing else reaches the None, and
    `Origin.origin_for(None)` counts a missing Host as local: a request that
    names no Host must still be refused, and must write nothing."""
    before = _head(core)
    r = _get(core, '/v1/missions', host=False)
    assert (r.status, r.json()) == (403, {'error': 'host_not_allowed', 'detail': {
        'why': 'open Archeus at http://127.0.0.1:%d' % core.port}})
    assert r.error is None
    assert _head(core) == before


def test_a_request_that_names_no_host_reaches_not_even_the_public_page(core):
    """The Host gate is the first thing `_serve` does, before the query is even
    split: the asset route, the page and the health route are all behind it."""
    before = _head(core)
    for path in ('/', '/assets/app-1.js', '/v1/health'):
        r = _get(core, path, host=False, token=False)
        assert (r.status, r.json()['error']) == (403, 'host_not_allowed'), path
        assert r.error is None, path
    assert _head(core) == before


# ── a token in the query, on routes that need no credential at all ──

@pytest.mark.parametrize('name', ['token', 'access_token'])
@pytest.mark.parametrize('path', ['/', '/assets/app-1.js', '/v1/health',
                                  '/v1/devices/launch/redeem', '/nope'])
def test_a_token_in_the_query_is_refused_even_where_no_credential_is_needed(core, name, path):
    """server.py `_serve`: `if 'token' in self.query or 'access_token' in self.query:
    raise Refused(401, 'token_in_url')`, which runs before routing — so the
    public page, the scopeless authority route and an unknown path are refused
    for it too, and no handler runs."""
    before = _head(core)
    r = request(core.base_url, 'GET', '%s?%s=%s' % (path, name, core.token))
    assert (r.status, r.json()) == (401, {'error': 'token_in_url', 'detail': {}}), path
    assert _head(core) == before


@pytest.mark.parametrize('name', ['token', 'access_token'])
def test_a_blank_token_in_the_query_is_still_a_token_in_the_query(core, name):
    """`parse_qs(url.query, keep_blank_values=True)`: `?token=` is `?token=['']`,
    and a refusal is a refusal. Without keep_blank_values it would be no query
    value at all and the request would go through."""
    assert request(core.base_url, 'GET', '/v1/health?%s=' % name, token=None).status == 401
    assert (request(core.base_url, 'GET', '/v1/health?%s=' % name, token=None)
            ).json()['error'] == 'token_in_url'
    # the seam is live: the same route, with the value under another name and a
    # credential where it belongs, is answered
    assert request(core.base_url, 'GET', '/v1/health?state=%s' % core.token,
                   token=core.token).status == 200


# ── Content-Length: read as a number, bounded on both sides ──

@pytest.mark.parametrize('length', ['abc', '1e3', '12 34', '0x10', '-abc', '+-1', '+ 7'])
def test_a_content_length_that_is_not_a_number_is_refused_before_anything_is_read(core,
                                                                                   length):
    """server.py `_serve`: `length = int(self.headers.get('Content-Length') or 0)`
    guarded by `except ValueError: length = None`, answered by
    `raise Invalid('Content-Length', 'is not a number')` with the socket closed
    and the answer delivered."""
    before, keys = _head(core), _keys(core)
    r = _raw(core, 'POST /v1/missions HTTP/1.1',
             _base(core, extra=[('Content-Type', 'application/json'),
                                ('Content-Length', length)]))
    assert (r.status, r.json(), r.error) == (400, {'error': 'invalid_request', 'detail': {
        'field': 'Content-Length', 'why': 'is not a number'}}, None)
    assert (_head(core), _keys(core)) == (before, keys)


@pytest.mark.parametrize('length', [0, -1, -(1 << 30), -MAX_BODY, '', ' '])
def test_a_content_length_that_is_not_a_positive_number_is_never_handed_to_the_socket(core,
                                                                                       length):
    """server.py `_serve`: `length = int(self.headers.get('Content-Length') or 0)`,
    `raw = self.rfile.read(length) if length is not None and 0 < length <= MAX_BODY
    else b''`. An empty length means no body; a negative one is never a read
    length. Drop the `0 < length` half and read(-1) waits for an EOF this test
    never sends: the answer must arrive on a socket that is still open, and the
    request must not be routed."""
    before, keys = _head(core), _keys(core)
    r = _post(core, '/v1/missions', b'', length=length)
    assert r.error is None, 'the handler blocked in rfile.read'
    assert (r.status, r.json()) == (400, {'error': 'invalid_request', 'detail': {
        'field': 'idempotency_key', 'why': 'is required on every command'}})
    assert (_head(core), _keys(core)) == (before, keys)


@pytest.mark.parametrize('pad, status, error', [
    (0, 400, 'invalid_request'),                               # exactly MAX_BODY: read
    (1, 413, 'payload_too_large'),                             # one byte more: refused
])
def test_exactly_one_mebibyte_is_read_and_one_byte_more_is_not(core, pad, status, error):
    """server.py `_serve`: the upper bound, `0 < length <= MAX_BODY` and then
    `if length > MAX_BODY: raise Refused(413, 'payload_too_large')`. The exact
    value is read and parsed (a JSON array is refused as a body, not as a size);
    one byte more is refused before anything is read."""
    before, keys = _head(core), _keys(core)
    raw = b'[' + b' ' * (MAX_BODY - 2 + pad) + b']'
    assert len(raw) == MAX_BODY + pad
    r = _raw(core, 'POST /v1/missions HTTP/1.1',
             _base(core, extra=[('Content-Type', 'application/json'),
                                ('Content-Length', str(len(raw)))]), raw)
    assert (r.status, r.json()['error'], r.error) == (status, error, None)
    if status == 400:
        assert r.json()['detail'] == {'why': 'the body is a JSON object'}
    assert (_head(core), _keys(core)) == (before, keys)


@pytest.mark.parametrize('case, status, error', [
    ('host', 403, 'host_not_allowed'),
    ('cross_site', 403, 'cross_site'),
    ('token', 401, 'token_in_url'),
    ('plain', 413, 'payload_too_large'),
    ('unknown_path', 413, 'payload_too_large'),
    ('no_credential', 413, 'payload_too_large'),
])
def test_an_oversized_body_never_masks_an_earlier_refusal(core, case, status, error):
    """§4's order under one hostile request: Host, then fetch metadata, then the
    URL token, then the size — and the size comes before `routes.match` and
    before the credential, so an oversized request to a path that does not exist
    or with no token at all is a 413 and not a 404 or a 401. The body is declared
    and never sent, so nothing is left unread and the answer is exact."""
    declare = MAX_BODY + 4096
    path = {'token': '/v1/missions?access_token=x',
            'unknown_path': '/nope'}.get(case, '/v1/missions')
    h = _base(core, host='evil.example' if case == 'host' else True,
              token=case != 'no_credential',
              extra=[('Content-Type', 'application/json'),
                     ('Content-Length', str(declare))]
                    + ([('Sec-Fetch-Site', 'cross-site')] if case == 'cross_site' else []))
    r = _raw(core, 'POST %s HTTP/1.1' % path, h)
    assert (r.status, r.json()['error'], r.error) == (status, error, None), r.body


def test_an_early_refusal_of_an_oversized_body_leaves_nothing_unread(core, unread_at_finish):
    """server.py `_serve`: the Host, fetch and URL-token gates refuse before the
    size gate, so the unread body is marked at the read, not at the 413."""
    done, unread = unread_at_finish
    body = b'[' + b' ' * (2 * MAX_BODY) + b']'
    _post(core, '/v1/missions', body, length=len(body), host='evil.example')
    assert done.wait(15), 'the request never reached finish'
    assert unread == [0], '%d bytes of body were left in the peer when the socket closed' \
        % sum(unread)


# ── a command without its key ──

@pytest.mark.parametrize('key', [None, '', '   ', '\t\n', 7, 7.5, True, [], {}],
                         ids=['absent', 'empty', 'spaces', 'newline', 'int', 'float',
                              'true', 'list', 'dict'])
def test_a_keyed_command_is_refused_unwritten_without_a_usable_idempotency_key(core, key):
    """server.py `_body`: `if not (isinstance(key, str) and key.strip()):
    raise Invalid('idempotency_key', 'is required on every command')` — before
    `validate`, so no schema answer, and before the handler, so no write. `True`
    and `7` are the ones a bare `if not key` would let through."""
    before, keys = _head(core), _keys(core)
    body = {'title': 'keep the outbox ordered', 'objective': 'o'}
    if key is not None:
        body['idempotency_key'] = key
    r = _post(core, '/v1/missions', body)
    assert (r.status, r.json()) == (400, {'error': 'invalid_request', 'detail': {
        'field': 'idempotency_key', 'why': 'is required on every command'}}), key
    assert (_head(core), _keys(core)) == (before, keys)
    body['idempotency_key'] = 'usable-key-for-%s' % type(key).__name__
    assert _post(core, '/v1/missions', body).status == 200     # the route itself is live
    assert (_keys(core), _head(core) > before) == (keys + 1, True)   # and it did write


# ── the stdlib's own refusals, and HEAD ──

def test_an_unsupported_method_is_answered_in_our_shape_with_our_headers(core):
    """server.py `Handler.send_error`: the stdlib's refusals carry our headers and
    our shape, not its HTML page — including the CSP that keeps a refusal
    unparsable as markup."""
    r = _raw(core, 'FOO /v1/health HTTP/1.1', _base(core))
    assert (r.status, r.json(), r.error) == (501, {'error': 'http_501', 'detail': {}}, None)
    assert r.headers['content-type'].startswith('application/json')
    assert int(r.headers['content-length']) == len(r.body)
    assert r.headers['content-security-policy'] == CSP
    assert r.headers['x-content-type-options'] == 'nosniff'
    assert r.headers['cache-control'] == 'no-store' and r.headers['referrer-policy']
    assert b'<!doctype' not in r.body.lower()


@pytest.mark.parametrize('line, error, status', [
    ('this-is-not-a-request-line', 'invalid_request', 400),
    ('GET /v1/health HTTP/9.9', 'http_505', 505),
])
def test_a_malformed_request_line_is_refused_without_an_html_page_or_an_echo(core, line,
                                                                              error, status):
    """server.py `Handler.send_error(code, message, explain)`: the message and the
    explain are dropped, and the explain is the client's own request line — the
    stdlib puts it in an HTML page, which is a refusal that parses as content.
    The status line is version-dependent: 3.10 answers these as headerless HTTP/0.9
    (status None), 3.13 writes the status line; both carry our body."""
    r = _raw(core, line, timeout=3.0)
    assert r.status in (None, status) and r.error is None      # answered, not left hanging
    assert json.loads(r.body) == {'error': error, 'detail': {}}
    assert b'<!doctype' not in r.body.lower() and b'Error' not in r.body
    assert line.encode() not in r.body                         # nothing echoed back


def test_a_head_request_carries_the_headers_and_no_body(core):
    """server.py `_respond`: `if self.command != 'HEAD': self.wfile.write(body)`.
    The headers promise the body the same request gets by any other method; the
    answer withholds it. And for the methods that are answered, the promised
    length is the body that was written."""
    promised = json.dumps({'error': 'method_not_allowed', 'detail': {}},
                          separators=(',', ':')).encode()
    head = _raw(core, 'HEAD /v1/missions HTTP/1.1', _base(core))          # no HEAD route
    assert head.status == 405 and head.body == b''
    assert int(head.headers['content-length']) == len(promised)
    assert head.headers['content-security-policy'] == CSP
    gone = _raw(core, 'HEAD /nope HTTP/1.1', _base(core))                 # no route at all
    assert gone.status == 404 and gone.body == b''
    assert int(gone.headers['content-length']) == len(
        json.dumps({'error': 'not_found', 'detail': {}}, separators=(',', ':')).encode())
    for path in ('/v1/missions', '/v1/version', '/nope'):
        got = _get(core, path)
        assert got.body and int(got.headers['content-length']) == len(got.body), path


# ── the bounded pools, and how a request ends ──

def test_the_stream_is_exempt_from_the_request_pool_and_a_refusal_gives_its_slot_back(core,
                                                                                      monkeypatch):
    """server.py `_serve`: `if route.path != routes.STREAM: if not
    self.api.requests.acquire(blocking=False): raise Refused(503, 'busy', ...)`,
    and `finally: if slot is not None: slot.release()`. One slot, so the leak and
    the starvation are both visible: a refused request that took it must give it
    back, and the held-for-the-life-of-the-connection stream must not need it."""
    monkeypatch.setattr(core.core.api, 'requests', threading.BoundedSemaphore(1))
    assert request(core.base_url, 'GET', '/v1/missions').status == 401   # took it ...
    assert core.http('GET', '/v1/version').status == 200                  # ... and gave it back
    core.core.api.requests.acquire()
    busy = core.http('GET', '/v1/version')
    assert (busy.status, busy.json()) == (503, {'error': 'busy', 'detail': {}})
    assert busy.headers.get('Retry-After') == '1'
    s = SSEClient(core.base_url, core.token)
    try:
        assert s.status == 200                                    # the stream needs no slot
    finally:
        s.close()
    core.core.api.requests.release()
    assert core.http('GET', '/v1/version').status == 200


class _Pipe:
    """The read end of a socket `_linger` drains, without an OS socket: `read1`
    as many times as the handler asks for and count the bytes it asked for."""

    def __init__(self, chunk=b'x' * 65536, fail=None):
        self.chunk, self.fail, self.requested = chunk, fail, 0

    def read1(self, n):
        self.requested += n
        if self.fail is not None:
            raise self.fail
        return self.chunk


class _Conn:
    def __init__(self):
        self.shutdowns = []

    def shutdown(self, how):
        self.shutdowns.append(how)

    def settimeout(self, seconds):
        pass


def _linger_handler(pipe):
    h = object.__new__(server.Handler)
    h.connection, h.rfile = _Conn(), pipe
    return h


def test_the_lingering_close_stops_at_its_byte_bound(monkeypatch):
    """server.py `_linger`: `while left > 0 and time.monotonic() < deadline` with
    `left -= len(chunk)` from `LINGER_BYTES`. Without the bound a client that
    keeps sending is read for ever."""
    monkeypatch.setattr(server, 'LINGER_BYTES', 4 << 16)
    pipe = _Pipe()
    h = _linger_handler(pipe)
    h._linger()
    assert h.connection.shutdowns == [socket.SHUT_WR]           # the answer is already out
    assert pipe.requested == 4 << 16                            # never one byte more


def test_the_lingering_close_stops_at_its_time_bound(monkeypatch):
    """server.py `_linger`: the same loop's other half, `time.monotonic() <
    deadline` against `deadline = time.monotonic() + LINGER_S` — a client that
    sends nothing at all is waited for, and only for that long."""
    monkeypatch.setattr(server, 'LINGER_S', 0.0)
    pipe = _Pipe()
    h = _linger_handler(pipe)
    h._linger()
    assert (pipe.requested, h.connection.shutdowns) == (0, [socket.SHUT_WR])


def test_the_lingering_close_survives_a_client_that_resets(monkeypatch):
    """server.py `_linger`: `except OSError: pass`. A reset here is ordinary: a
    client that has gone cannot be told anything, and the exception must not
    reach the handler's finally, where the request line is still logged."""
    monkeypatch.setattr(server, 'LINGER_S', 30.0)
    _linger_handler(_Pipe(fail=ConnectionResetError('gone')))._linger()      # must not raise


def _seen_after(seen, n, grace=5.0):
    """The handler's finally runs after the answer is on the wire, so a test that
    reads the answer and looks at the log at once can be earlier than the linger
    it is looking for. Wait for `n` entries, bounded, and report what is there."""
    deadline = time.monotonic() + grace
    while len(seen) < n and time.monotonic() < deadline:
        time.sleep(0.01)
    return list(seen)


def test_only_a_refusal_that_left_a_body_unread_takes_the_linger_path(core, monkeypatch):
    """server.py `_serve`: `self.close_connection = self._unread = True` on the two
    refusals that do not read the body, and `if self._unread: self._linger()` in
    the finally. The requests that read everything must not take it: a slot held
    for the length of a linger is a request pool starved by a client that has
    nothing left to say."""
    seen, real = [], server.Handler._linger

    def spy(self):
        seen.append(self._unread)
        return real(self)
    monkeypatch.setattr(server.Handler, '_linger', spy)
    assert core.http('GET', '/v1/version').status == 200                  # nothing to drain
    assert _seen_after(seen, 1, 0.25) == []
    assert core.http('POST', '/v1/missions', body={'title': 'drained', 'objective': 'o',
                                                   'idempotency_key': 'linger-read-all'}
                     ).status == 200                                       # body and all
    assert _seen_after(seen, 1, 0.25) == []
    assert _raw(core, 'POST /v1/missions HTTP/1.1',
                _base(core, extra=[('Content-Length', 'abc')])).status == 400
    assert _seen_after(seen, 1) == [True]                 # the body it would not have parsed
    seen.clear()
    assert _raw(core, 'POST /v1/missions HTTP/1.1', _base(core, extra=[
        ('Content-Length', str(MAX_BODY + 4096))])).status == 413
    assert _seen_after(seen, 1) == [True]


def test_the_request_line_never_reaches_stderr(core, capsys):
    """server.py `Handler.log_message`: `pass`. The stdlib's version writes the
    request line to stderr, and the request line holds the query string — which
    is exactly where a token appears when a client puts it there."""
    request(core.base_url, 'GET', '/v1/version')
    core.http('POST', '/v1/missions', body={'title': 'no stderr', 'objective': 'o',
                                            'idempotency_key': 'no-stderr'})
    assert request(core.base_url, 'GET', '/v1/missions?token=' + core.token).status == 401
    captured = capsys.readouterr()
    assert captured.err == ''
    h = object.__new__(server.Handler)                         # the seam is live: it would
    h.client_address = ('127.0.0.1', 1)
    server.BaseHTTPRequestHandler.log_message(h, '%s %s', 'GET /v1/missions 200', ())
    assert 'GET /v1/missions 200' in capsys.readouterr().err


# ── the listener, and the shutdown order ──

@pytest.mark.skipif(sys.platform == 'win32',
                    reason='server_bind sets SO_EXCLUSIVEADDRUSE and the platform refuses the '
                           'second bind there, which is that platform\'s own branch of Server')
def test_a_second_live_listener_on_the_loopback_port_is_refused(core):
    """server.py `Server`: `allow_reuse_address = not sys.platform.startswith('win')`.
    SO_REUSEADDR must only outlast the last run's TIME_WAIT connections: a port
    Core is holding has to stay held, or a second process squats the API."""
    assert server.Server.allow_reuse_address is (not sys.platform.startswith('win'))
    with pytest.raises(OSError):
        server.Server(object(), core.port).server_close()


def test_a_core_listens_on_the_loopback_address_alone_and_names_itself_by_number():
    """server.py `Server.__init__` / `server_bind`: bound to ('127.0.0.1', port),
    and named without HTTPServer's reverse lookup of the CGI server_name."""
    port = free_port()
    s = server.Server(object(), port)
    try:
        assert s.server_address[0] == '127.0.0.1' and s.server_address[1] == port
        assert (s.server_name, s.server_port) == ('127.0.0.1', port)
    finally:
        s.server_close()


def test_shutdown_refuses_a_known_route_only_after_the_route_is_known(core):
    """server.py `_serve`: `route, self.params = routes.match(...)` runs before
    `if self.api.stopping: raise Refused(503, 'core_stopping')`, so a request for
    a path that does not exist is still a 404 during shutdown, and the stream —
    exempt from the request pool — is refused like every other route."""
    core.core.api.stopping = True
    try:
        stopping, gone, stream = (core.http('GET', '/v1/missions'),
                                  core.http('GET', '/nope'),
                                  core.http('GET', routes.STREAM))
    finally:
        core.core.api.stopping = False
    assert (stopping.status, stopping.json()['error']) == (503, 'core_stopping')
    assert (gone.status, gone.json()['error']) == (404, 'not_found')
    assert (stream.status, stream.json()['error']) == (503, 'core_stopping')
    assert core.http('GET', '/v1/missions').status == 200            # and again afterwards
