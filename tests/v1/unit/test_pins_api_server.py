"""T-404 hand-mutant pins on `archeus/api/server.py` (unit; Linux and Windows).

Each test below exists to fail when one specific security-relevant condition
of the module is inverted, removed or loosened, and no existing test notices.
The card's report lists the twenty conditions examined with file:line and the
verdict COVERED (with the test that already pins it) or UNCOVERED; the
UNCOVERED ones are pinned here, one test per condition, with the mutant that
kills it named in the docstring.

Platform rules kept: no network, no real process, no sleeps at all, fixtures
are in-memory or `tmp_path` bytes with explicit contents, no case-insensitive
behaviour is relied on, no OS error texts are asserted, pytest ids stay short.
The fakes use the seams the existing unit tests use: `object.__new__(Handler)`,
fakes on the `Api` attributes `_serve` reads, and `monkeypatch` on
`routes.match` (the same module-attribute seam the file under test already
calls through).
"""

import io
import json
from http.client import HTTPMessage
import threading
from types import SimpleNamespace

import pytest

from archeus.api import auth, routes, server
from archeus.api.routes import Refused
from archeus.api.schemas import Invalid

PORT = 8777
HOST = '127.0.0.1:%d' % PORT


# ── the fakes ──

class _RFile:
    """A scripted `self.rfile`: `read` consumes, `read1` (the linger's peek) is EOF."""

    def __init__(self, data=b''):
        self._buf = io.BytesIO(data)
        self._size = len(data)

    def read(self, n=-1):
        return self._buf.read(n)

    def read1(self, n):
        return b''

    def remaining(self):
        return self._size - self._buf.tell()


class _Api:
    """Only what `Handler._serve` reads of `Api`. `auth.Origin` is the real one:
    its checks are pure; the slot pool is a real semaphore; there is no db, no
    writer and no OS call (every route used here has `scope=None`)."""

    def __init__(self, free_slots=4):
        self.origin = auth.Origin(PORT)
        self.stopping = False
        self.requests = threading.BoundedSemaphore(free_slots)
        self.origin_enforcement_enabled = False
        self.seen = {}

    def attest(self, peer):
        return auth.USER


def _route(method, path, scope=None, idempotent=None, schema=None):
    return routes.Route(method, path, None, scope, idempotent, schema, None)


def _post():
    """A POST route with a request shape but no idempotency demand: the body
    parse is exercised, the key gate is not."""
    return _route('POST', '/v1/missions', schema={'type': 'object'})


def _serve(api, monkeypatch, route, *, headers=None, body=b''):
    """One `Handler._serve` over the fakes; returns (handler, bodies_the_handler_saw)."""
    seen = []

    def handler(req):                                   # the route's own code, faked
        seen.append(req.body)
        return None if route.path == routes.STREAM else (200, {'ok': True})

    route = route._replace(handler=handler)
    h = object.__new__(server.Handler)
    h.server = SimpleNamespace(api=api)
    h.command, h.path = route.method, route.path
    h.headers = HTTPMessage()
    for k, v in dict({'Host': HOST}, **(headers or {})).items():
        h.headers[k] = v
    if body and 'Content-Length' not in h.headers:
        h.headers['Content-Length'] = str(len(body))   # a real client names the length
    h.client_address = ('127.0.0.1', 4321)
    h.rfile, h.wfile = _RFile(body), io.BytesIO()
    h.connection = SimpleNamespace(shutdown=lambda how: None, settimeout=lambda s: None)
    h.close_connection = False
    h._status = None
    h.answers = []

    def respond(status, obj, resp_headers=None):
        h._status = status
        h.answers.append((status, obj, dict(resp_headers or {})))

    h._respond = respond                                # capture, never a socket
    monkeypatch.setattr(routes, 'match', lambda m, p: (route, {}))
    h._serve()
    return h, seen


# ── Static.root_file: `except FileNotFoundError -> Refused(404)` (server.py:105) ──

def test_missing_pwa_root_file_is_a_404_not_a_500(tmp_path):
    """Mutant: drop the `except FileNotFoundError` (or widen it past 404) and the
    missing file becomes a 500, which no existing test asks for."""
    st = server.Static(str(tmp_path / 'nothing'))
    with pytest.raises(Refused) as got:
        st.root_file('sw.js')
    assert (got.value.status, got.value.code) == (404, 'not_found')


def test_pwa_root_file_keeps_its_table_type(tmp_path):
    """Mutant: loosen the `self.ROOT[name]` membership (e.g. `.get(name)`) and
    the served type is no longer the table's, or the lookup no longer refuses."""
    d = tmp_path / 'static'
    d.mkdir()
    (d / 'manifest.webmanifest').write_bytes(b'{"name": "Archeus"}')
    status, raw = server.Static(str(d)).root_file('manifest.webmanifest')
    assert status == 200 and raw.body == b'{"name": "Archeus"}'
    assert raw.content_type == 'application/manifest+json'


# ── Static.asset: TYPES.get default and the listing/isfile checks (server.py:117-119) ──

def test_asset_of_an_unknown_type_is_octet_stream(tmp_path):
    """Mutants: change the `application/octet-stream` default (or delete a TYPES
    row) and this fails; no test in the repo asserts either today."""
    d = tmp_path / 'static'
    (d / 'assets').mkdir(parents=True)
    (d / 'assets' / 'data.bin').write_bytes(b'\x00\x01')
    (d / 'assets' / 'app.js').write_bytes(b'//x')
    st = server.Static(str(d))
    status, raw = st.asset('data.bin')
    assert (status, raw.content_type) == (200, 'application/octet-stream')
    assert raw.cache == 'public, max-age=31536000, immutable'
    _s, js = st.asset('app.js')
    assert js.content_type == 'text/javascript; charset=utf-8'


def test_asset_must_be_a_listed_file(tmp_path):
    """Mutants: `not present or not isfile` -> `and`, or dropping the isfile
    check, and a listed directory or an absent listing raises something other
    than Refused(404)."""
    d = tmp_path / 'static'
    (d / 'assets' / 'sub').mkdir(parents=True)
    (d / 'assets' / 'ok.js').write_bytes(b'//')
    with pytest.raises(Refused) as got:
        server.Static(str(d)).asset('sub')              # listed, but not a file
    assert (got.value.status, got.value.code) == (404, 'not_found')
    with pytest.raises(Refused) as got:
        server.Static(str(tmp_path / 'nothing')).asset('ok.js')   # no listing at all
    assert (got.value.status, got.value.code) == (404, 'not_found')


# ── Handler.send_error: only a 400 is `invalid_request` (server.py:346) ──

def test_send_error_maps_only_400_to_invalid_request():
    """Mutant: move the `== 400` to another code (or drop the branch) and the
    stdlib's own refusals stop matching the API shape; nothing tests them today."""
    h = object.__new__(server.Handler)
    answers = []
    h._respond = lambda status, obj, headers=None: answers.append((status, obj))
    h.send_error(400)
    h.send_error(414)
    assert answers[0] == (400, {'error': 'invalid_request', 'detail': {}})
    assert answers[1] == (414, {'error': 'http_414', 'detail': {}})


# ── Handler._respond: HEAD sends the headers, never the body (server.py:362) ──

def test_head_carries_the_headers_but_no_body():
    """Mutant: invert `self.command != 'HEAD'` (or delete it) and a HEAD body
    leaks or a GET body disappears; no existing test issues a HEAD request."""
    h = object.__new__(server.Handler)
    sent = []
    h.send_response = lambda status: sent.append(('status', status))
    h.send_header = lambda k, v: sent.append((k, v))
    h.end_headers = lambda: sent.append(('end', None))
    h.wfile = io.BytesIO()
    body = b'{"ok":true}'
    h.command = 'HEAD'
    h._respond(200, {'ok': True})
    assert h.wfile.getvalue() == b''
    assert ('Content-Length', str(len(body))) in sent
    assert ('Cache-Control', 'no-store') in sent
    h.command = 'GET'
    h._respond(200, {'ok': True})
    assert h.wfile.getvalue() == body


# ── Handler._body: the idempotency gate and the JSON-object gate (server.py:372-386) ──

def _keyed(idempotent='required', schema=None):
    return _route('POST', '/v1/missions', scope='control', idempotent=idempotent,
                  schema={'type': 'object'} if schema is None else schema)


def _body(route, raw):
    return server.Handler._body(object.__new__(server.Handler), route, raw)


def test_keyed_command_needs_a_real_idempotency_key():
    """Mutants: drop `key.strip()` (a blank key passes), drop the `isinstance`
    (a number or null passes), or loosen `idempotent == 'required'`; the real
    integration bodies only ever carry missing/null keys, never a blank one."""
    assert _body(_keyed(), b'{"idempotency_key": "k1"}') == {'idempotency_key': 'k1'}
    for raw in (b'{}', b'{"idempotency_key": "   "}', b'{"idempotency_key": ""}',
                b'{"idempotency_key": 5}', b'{"idempotency_key": null}',
                b'{"idempotency_key": true}'):
        with pytest.raises(Invalid) as got:
            _body(_keyed(), raw)
        assert (got.value.field, got.value.why) == ('idempotency_key',
                                                    'is required on every command'), raw
    assert _body(_keyed(idempotent=None), b'{}') == {}          # exempt: never asked for
    assert _body(_keyed(idempotent='exempt'), b'{}') == {}


def test_the_body_must_be_a_json_object_or_the_request_is_invalid():
    """Mutant: remove `not isinstance(body, dict)` or the decode guard, and a
    list/number/binary body stops being an Invalid 400 (the HTTP-level floor
    only proves it is *some* 4xx)."""
    for raw in (b'[1, 2]', b'"s"', b'5', b'null'):
        with pytest.raises(Invalid) as got:
            _body(_keyed(), raw)
        assert got.value.why == 'the body is a JSON object', raw
    for raw in (b'not json', b'\xff\xfe', b'\x00{"idempotency_key": "k"}'):
        with pytest.raises(Invalid) as got:
            _body(_keyed(), raw)
        assert got.value.why == 'the body is not JSON', raw


# ── Handler._serve: Content-Length and the body limit (server.py:396-416) ──

def test_a_content_length_that_is_not_a_number_is_400(monkeypatch):
    """Mutant: make `_length` read a non-digit run as 0 (or drop the
    `re.fullmatch` guard so int() raises) and this stops being the typed 400."""
    h, seen = _serve(_Api(), monkeypatch, _post(),
                     headers={'Content-Length': '1e3'}, body=b'{}')
    assert seen == []
    status, obj, _hd = h.answers[0]
    assert (status, obj) == (400, {'error': 'invalid_request',
                                   'detail': {'field': 'Content-Length',
                                              'why': 'is not a number'}})
    assert h.close_connection is True and h._unread is True


def test_a_missing_content_length_is_an_empty_body_not_an_error(monkeypatch):
    """Mutant: make the missing header also fall into the error branch (or the
    error branch treat absent as zero) and the answer stops being 200."""
    h, seen = _serve(_Api(), monkeypatch, _post(), body=b'')
    assert seen == [{}] and h.answers[0][0] == 200


def test_the_body_limit_boundary_is_inclusive(monkeypatch):
    """Mutant: `0 < length <= MAX_BODY` -> `<` (or `>=` on the refusal below):
    exactly-MAX_BODY stops being read and parsed; the only existing oversized
    test is MAX_BODY+2, so the boundary itself is unpinned."""
    body = json.dumps({'k': ' ' * (server.MAX_BODY - len('{"k": ""}'))}).encode('utf-8')
    assert len(body) == server.MAX_BODY
    h, seen = _serve(_Api(), monkeypatch, _post(),
                     headers={'Content-Length': str(server.MAX_BODY)}, body=body)
    assert seen == [{'k': ' ' * (server.MAX_BODY - len('{"k": ""}'))}]
    assert h.rfile.remaining() == 0                    # fully drained: no RST
    assert h.answers and h.answers[0][0] == 200


def test_one_byte_over_the_limit_is_413_unread(monkeypatch):
    """Mutant: raise the bound (`length > MAX_BODY + 1`) and the oversized body
    is read and parsed instead of refused; the shape, the 413 code and the
    unread/linger flags are pinned here (the HTTP-level test only checks that
    some 4xx arrives)."""
    body = b'x' + json.dumps({'k': ' ' * (server.MAX_BODY - len('{"k": ""}'))}).encode('utf-8')
    h, seen = _serve(_Api(), monkeypatch, _post(),
                     headers={'Content-Length': str(server.MAX_BODY + 1)}, body=body)
    assert seen == []
    status, obj, _hd = h.answers[0]
    assert (status, obj) == (413, {'error': 'payload_too_large', 'detail': {}})
    assert h.close_connection is True and h._unread is True


# ── Handler._serve: the stream route draws no request slot (server.py:423) ──

def test_a_stream_is_answered_when_the_request_pool_is_full(monkeypatch):
    """Mutant: delete `route.path != routes.STREAM` (streams draw slots too)
    and the 0-slot pool refuses the stream; delete `slot.release()` and the
    fourth ordinary request is busy. Existing pool tests never fill REQUEST_SLOTS."""
    api = _Api(free_slots=0)
    _h, seen = _serve(api, monkeypatch, _route('GET', routes.STREAM))
    assert seen == [{}] and _h.answers == []           # the stream reached its handler
    _h2, seen2 = _serve(api, monkeypatch, _route('GET', '/v1/version'))
    assert seen2 == []
    status, obj, hd = _h2.answers[0]
    assert (status, obj['error'], hd) == (503, 'busy', {'Retry-After': '1'})
    api2 = _Api(free_slots=2)                          # the slot comes back: release()
    for _ in range(5):
        h3, seen3 = _serve(api2, monkeypatch, _route('GET', '/v1/version'))
        assert seen3 == [{}], 'a request slot leaked'


# ── Handler._serve: X-Archeus-Queued is refused unless replayable (server.py:472) ──

def test_any_queued_header_refuses_a_command_that_is_not_replayable(monkeypatch):
    """Mutants: `is not None` -> truthiness (an empty header value skips the
    refusal), or dropping the REPLAYABLE exclusion (the monotone digest ack
    stops being replayable); the one integration test only ever sends '1' on
    one refused route and one ack."""
    api = _Api()
    command = _route('POST', '/v1/missions', idempotent='required', schema={'type': 'object'})
    ack = _route('POST', '/v1/digest/ack', schema={'type': 'object'})
    for value in ('', '0', '1'):
        h, seen = _serve(api, monkeypatch, command,
                         headers={'X-Archeus-Queued': value}, body=b'{}')
        assert seen == [], value
        status, obj, _hd = h.answers[0]
        assert (status, obj['error']) == (409, 'queued_intent_refused'), value
    h, seen = _serve(api, monkeypatch, ack, headers={'X-Archeus-Queued': '1'}, body=b'{}')
    assert seen == [{}]                                # the declared replayable one answers
    _h, seen2 = _serve(api, monkeypatch, command, body=b'{"idempotency_key": "k"}')
    assert seen2 == [{'idempotency_key': 'k'}]         # no header at all: not refused
