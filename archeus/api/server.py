"""The HTTP transport (p3.5b design gate §4, §5).

`ThreadingHTTPServer` on 127.0.0.1 only. Every request runs the §4 pipeline,
in this order, each step failing closed:

    1 Host is exactly 127.0.0.1:<port>             403 host_not_allowed
    2 fetch metadata / Origin are same-origin      403 cross_site
    3 no token or access_token in the query        401 token_in_url
    4 body at most 1 MiB                           413 payload_too_large
    5 a known route, with its method               404 / 405
    6 a live device credential (if the route has a scope)   401 unauthenticated
    7 the credential carries the route's scope     403 scope_required
    8 a JSON object body; an idempotency_key on a keyed command   400
    9 the handler: ONE command through the writer, or ONE read query

so a refused request writes nothing. Requests and streams draw on separate
bounded pools (32 and 8), acquired without blocking. Every response — JSON,
static, the "SPA not built" page, an error, a stream — carries the security
headers. The request log records method, route template, status, duration and
device: never a header, a query string or a body.
"""

import concurrent.futures
import json
import logging
import os
import secrets
import socket
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from ..core.application import errors, queries
from ..core.domain.values import Ref
from . import auth, routes, sse
from .routes import Refused
from .schemas import Invalid, validate

MAX_BODY = 1 << 20
#: After refusing a body it will not read, the server keeps reading (and
#: discarding) this long and this much before it closes, so the refusal is
#: received instead of a reset (a socket closed with unread data sends RST).
LINGER_S = 2.0
LINGER_BYTES = 16 << 20
REQUEST_SLOTS = 32
COMMAND_TIMEOUT_S = 30.0
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

log = logging.getLogger('archeus.core')

NOT_BUILT = b"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Archeus</title></head>
<body><h1>The Archeus app is not built</h1>
<p>Core is running. Build the app once with <code>npm ci &amp;&amp; npm run build</code> in
<code>clients/app/</code>, then reload this page.</p></body></html>
"""


#: A fixed table, not `mimetypes`: on Windows that reads the registry, which can
#: map `.js` to `text/plain` — and with `nosniff` a browser then refuses to run
#: the SPA's module script at all.
TYPES = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
         '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon',
         '.woff2': 'font/woff2', '.json': 'application/json'}


class Raw:
    """A non-JSON response body."""

    def __init__(self, body, content_type, cache='no-store'):
        self.body, self.content_type, self.cache = body, content_type, cache


class Static:
    def __init__(self, directory=STATIC_DIR):
        self.dir = directory

    def index(self):
        try:
            with open(os.path.join(self.dir, 'index.html'), 'rb') as f:
                return 200, Raw(f.read(), 'text/html; charset=utf-8')
        except FileNotFoundError:
            return 200, Raw(NOT_BUILT, 'text/html; charset=utf-8')

    def asset(self, name):
        assets = os.path.join(self.dir, 'assets')
        # membership in the directory listing, not path arithmetic: a name with
        # a separator or `..` is simply not in it
        try:
            present = name in os.listdir(assets)
        except OSError:
            present = False
        path = os.path.join(assets, name)
        if not present or not os.path.isfile(path):
            raise Refused(404, 'not_found')
        kind = TYPES.get(os.path.splitext(name)[1].lower(), 'application/octet-stream')
        with open(path, 'rb') as f:
            return 200, Raw(f.read(), kind, cache='public, max-age=31536000, immutable')


def translate(e):
    """(status, code, detail, headers) for any exception a request can raise:
    the §5.5 table. `GuardFailed`/`InvalidTransition` come before `ValueError`,
    which they (or their bases) are."""
    if isinstance(e, Refused):
        return e.status, e.code, e.detail, e.headers
    if isinstance(e, Invalid):
        return 400, 'invalid_request', ({'why': e.why} if e.field is None
                                        else {'field': e.field, 'why': e.why}), {}
    if isinstance(e, errors.GuardFailed):
        return 422, 'guard_failed', {'machine': e.machine, 'from': e.frm, 'to': e.to,
                                     'trigger': e.trigger, 'guard': e.result.guard,
                                     'reason': e.result.reason}, {}
    if isinstance(e, errors.InvalidTransition):
        detail = {'machine': e.machine, 'from': e.frm, 'to': e.to}
        if isinstance(e, errors.IllegalTrigger):
            detail['trigger'] = e.trigger
        return 422, 'invalid_transition', detail, {}
    if isinstance(e, errors.NotPermitted):
        return 403, 'not_permitted', {'why': str(e)}, {}
    if isinstance(e, errors.NotEligible):
        return 409, 'approval_not_eligible', {'approval_id': e.approval_id, 'why': e.why,
                                              'detail': e.detail}, {}
    if isinstance(e, errors.PolicyDenied):
        # refused before anything was written: the decision that answers it
        # (a plan's denial, a dispatch's `unrecoverable`) is recorded by P9
        d = e.decision
        return 423, 'policy_denied', {'task': e.task_key, 'action_class': d.action.action_class,
                                      'decision': d.decision, 'reason': d.reason}, {}
    if isinstance(e, errors.VersionConflict):
        return 409, 'version_conflict', {'current': e.current}, {}
    if isinstance(e, errors.NotFound):
        return 404, 'not_found', {'id': str(e.args[0]) if e.args else None}, {}
    if isinstance(e, errors.CursorExpired):
        return 410, 'cursor_expired', {'reason': e.reason, 'floor': e.floor, 'head': e.head}, {}
    if isinstance(e, errors.Conflict):
        return 409, 'conflict', dict(e.detail, why=str(e)), {}
    if isinstance(e, errors.IdempotencyConflict):
        return 400, 'invalid_request', {'field': 'idempotency_key', 'why': str(e)}, {}
    if isinstance(e, (errors.WriterBusy, concurrent.futures.TimeoutError)):
        return 503, 'busy', {}, {'Retry-After': '1'}
    if isinstance(e, errors.WriterClosed):
        return 503, 'core_stopping', {}, {}
    if isinstance(e, ValueError):
        return 400, 'invalid_request', {'why': str(e)}, {}
    ref = secrets.token_hex(6)
    log.error('internal error %s', ref, exc_info=e)
    return 500, 'internal', {'ref': ref}, {}


class Api:
    """What the handlers reach: the database, the Missions actions (which carry
    the Policy port), the launch codes, the streams and Core's health."""

    def __init__(self, *, db, missions, port, health, version, conversations=None,
                 authorization=None,
                 heartbeat_s=15.0, launch_clock=time.monotonic, static_dir=STATIC_DIR,
                 command_timeout=COMMAND_TIMEOUT_S):
        self.db, self.missions, self.health, self.version = db, missions, health, version
        self.conversations = conversations
        self.authorization = authorization
        self.origin = auth.Origin(port)
        self.launch = auth.LaunchCodes(clock=launch_clock)
        self.static = Static(static_dir)
        self.stopping = False
        self.sse = sse.Streams(db, heartbeat_s=heartbeat_s, stopping=lambda: self.stopping)
        self.requests = threading.BoundedSemaphore(REQUEST_SLOTS)
        self.command_timeout = command_timeout

    def authenticate(self, header):
        token = auth.bearer(header)
        if token is None:
            return None, None
        h = auth.token_hash(token)
        with self.db.read() as conn:
            cred = queries.credential(conn, h)
        if not auth.live(cred, h):
            return None, None
        return {'principal_id': cred['principal_id'], 'device_id': cred['device_id'],
                'scopes': cred['scopes']}, h


class Handler(BaseHTTPRequestHandler):
    server_version = 'archeus'
    sys_version = ''

    # ── the request object handlers see ──

    def run(self, fn, kwargs, *, actor_id=None, keyed=True):
        actor = Ref('user_device', actor_id or self.principal['principal_id'])
        key = self.body.get('idempotency_key') if keyed else None
        fut = self.api.db.writer.submit(fn, dict(kwargs, actor=actor), idempotency_key=key)
        return fut.result(self.api.command_timeout)

    def start_stream(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        for k, v in auth.security_headers().items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.flush()
        self._status = 200

    def write(self, data):
        self.wfile.write(data)
        self.wfile.flush()

    # ── plumbing ──

    def log_message(self, *args):
        pass                                    # our own line, in _serve

    def send_error(self, code, message=None, explain=None):
        """The stdlib's own refusals (a malformed request line, a URI too long)
        carry our headers and shape too."""
        self._respond(code, {'error': 'invalid_request' if code == 400 else 'http_%d' % code,
                             'detail': {}})

    def _respond(self, status, obj, headers=None):
        if isinstance(obj, Raw):
            body, ctype, cache = obj.body, obj.content_type, obj.cache
        else:
            body = json.dumps(obj, separators=(',', ':')).encode('utf-8')
            ctype, cache = 'application/json', 'no-store'
        try:
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            for k, v in dict(auth.security_headers(cache), **(headers or {})).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
        except OSError:
            pass                                # the client went away
        self._status = status

    def _refuse(self, status, code, detail=None, headers=None):
        self._respond(status, {'error': code, 'detail': detail or {}}, headers)

    def _body(self, route, raw):
        if route.request_schema is None:
            return {}
        try:
            body = json.loads(raw.decode('utf-8')) if raw else {}
        except (UnicodeDecodeError, ValueError):
            raise Invalid(None, 'the body is not JSON') from None
        if not isinstance(body, dict):
            raise Invalid(None, 'the body is a JSON object')
        if route.idempotent == 'required':
            key = body.get('idempotency_key')
            if not (isinstance(key, str) and key.strip()):
                raise Invalid('idempotency_key', 'is required on every command')
        validate(body, route.request_schema)
        return body

    def _serve(self):
        started = time.monotonic()
        self._status, self.principal, self.body, self.token_hash = None, None, {}, None
        self._unread = False
        self.api = self.server.api
        self.peer = self.client_address
        template, slot = '-', None
        try:
            try:
                length = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                length = None
            # read first, bounded, so every refusal (the Host check included)
            # reaches a client that is still sending: answering with the body
            # unread resets the socket. The refusals keep §4's order below.
            raw = self.rfile.read(length) if length is not None and 0 < length <= MAX_BODY else b''
            if not self.api.origin.host_ok(self.headers.get('Host')):
                raise Refused(403, 'host_not_allowed',
                              {'why': 'open Archeus at %s' % self.api.origin.origin})
            if not self.api.origin.fetch_ok(self.headers):
                raise Refused(403, 'cross_site')
            url = urlsplit(self.path)
            self.query = parse_qs(url.query, keep_blank_values=True)
            if 'token' in self.query or 'access_token' in self.query:
                raise Refused(401, 'token_in_url')
            if length is None:
                self.close_connection = self._unread = True
                raise Invalid('Content-Length', 'is not a number')
            if length > MAX_BODY:
                self.close_connection = self._unread = True
                raise Refused(413, 'payload_too_large')
            route, self.params = routes.match(self.command, url.path)
            template = route.path
            if self.api.stopping:
                raise Refused(503, 'core_stopping')
            if route.path != routes.STREAM:
                if not self.api.requests.acquire(blocking=False):
                    raise Refused(503, 'busy', headers={'Retry-After': '1'})
                slot = self.api.requests
            if route.scope is not None:
                self.principal, self.token_hash = self.api.authenticate(
                    self.headers.get('Authorization'))
                if self.principal is None:
                    raise Refused(401, 'unauthenticated')
                if route.scope not in self.principal['scopes']:
                    raise Refused(403, 'scope_required', {'scope': route.scope})
            self.body = self._body(route, raw)
            out = route.handler(self)
            if out is not None:
                self._respond(*out)
        except concurrent.futures.TimeoutError as e:
            # a command timing out, not the client: an OSError since 3.11
            if self._status is None:
                self._refuse(*translate(e))
        except OSError:
            pass                                # a stream's client went away
        except Exception as e:
            if self._status is None:
                status, code, detail, headers = translate(e)
                self._refuse(status, code, detail, headers)
        finally:
            if slot is not None:
                slot.release()
            log.info('%s %s %s %.0fms %s', self.command, template, self._status,
                     (time.monotonic() - started) * 1000,
                     (self.principal or {}).get('device_id') or '-')
            if self._unread:
                self._linger()

    def _linger(self):
        """A lingering close: the answer is sent, so stop writing and read
        what the client is still sending until it stops, LINGER_S passes or
        LINGER_BYTES have gone by. Bounded both ways, so a client that sends
        forever costs at most that."""
        deadline, left = time.monotonic() + LINGER_S, LINGER_BYTES
        try:
            self.connection.shutdown(socket.SHUT_WR)
            while left > 0 and time.monotonic() < deadline:
                self.connection.settimeout(max(0.01, deadline - time.monotonic()))
                chunk = self.rfile.read1(65536)
                if not chunk:
                    return
                left -= len(chunk)
        except OSError:
            pass

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _serve


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # SO_REUSEADDR on Windows lets a second socket bind a port already in use,
    # which would hide a collision and invite a squatter: exclusive instead.
    # On POSIX it only lets a restart bind past the last run's TIME_WAIT
    # connections; a live listener still refuses it.
    allow_reuse_address = not sys.platform.startswith('win')

    def __init__(self, api, port):
        self.api = api
        super().__init__(('127.0.0.1', port), Handler)

    def server_bind(self):
        if sys.platform.startswith('win'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # TCPServer's bind, not HTTPServer's: that one then resolves
        # getfqdn('127.0.0.1') for a CGI-only server_name, a reverse DNS
        # lookup that stalled Core startup on macOS for over 30 s
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = '127.0.0.1', self.server_address[1]
