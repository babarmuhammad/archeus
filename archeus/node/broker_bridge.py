"""PV-20 provider broker, execution side (PV20-08 §1): the HTTP bridge a CLI inside the
isolation boundary talks to. It holds only the execution's broker token, which arrives
in the CLI's own request; it loads no account, reads no Core state and decides nothing.
It parses one bounded HTTP/1.1 request per connection, refuses malformed framing, and
relays a canonical copy over the pipe Core opened for it. Core parses that copy again
(`read_request`) and trusts nothing the bridge says.

Stdlib only, and nothing that loads an account: this module runs under the execution's
isolated identity.
"""

import re
import socket
import socketserver
import threading
from dataclasses import dataclass, field, replace

MAX_HEADERS = 64
MAX_HEADER_BYTES = 32 * 1024
MAX_BODY = 16 * 1024 * 1024
CONCURRENT = 2
#: a connection that goes quiet for this long, or takes this long to send one request,
#: is cut, so an idle client cannot hold a slot (PV20-08 §1; round 2 review S1)
IDLE_S = 10.0
DEADLINE_S = 30.0
_TOKEN = set("!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
#: names a request may carry at most once (PV20-08 §1, wire contract)
_SINGLE = ('content-length', 'host', 'authorization', 'x-api-key')
#: the only client headers that reach the upstream, by exact name (the broker decides
#: again); a name carrying any credential word is never forwarded, listed or not
FORWARD = frozenset({'anthropic-version', 'anthropic-beta', 'content-type', 'accept',
                     'user-agent'})
NEVER = ('key', 'token', 'auth', 'cookie', 'secret', 'credential')
#: what the bridge admits before reading a body: the execution's own broker token
_BRK_AUTH = re.compile(r'(?i:bearer) brk_[A-Za-z0-9_-]+')
#: a control character anywhere in a line but its CRLF: a bare CR, NUL, C0 but tab, DEL
CTL = re.compile(rb'[\x00-\x08\x0a-\x1f\x7f]')


class BadRequest(ValueError):
    """Framing the bridge and Core refuse; never forwarded. *status* is what the client gets."""
    status = 400


class TooLarge(BadRequest):
    status = 413


class Unauthorized(BadRequest):
    status = 401


@dataclass(frozen=True)
class Request:
    method: str
    target: str                 # origin-form: path plus optional `?query`
    headers: tuple = field(default_factory=tuple)      # ((name, value), ...) as received
    body: bytes = b''

    def header(self, name):
        name = name.lower()
        got = [v for k, v in self.headers if k.lower() == name]
        return got[0] if got else None

    @property
    def path(self):
        return self.target.partition('?')[0]

    @property
    def query(self):
        return self.target.partition('?')[2]


def forwarded(name):
    n = name.lower()
    return n in FORWARD and not any(w in n for w in NEVER)


def clean(text):
    """True when *text* holds no control character (a header value relayed back must not)."""
    return not CTL.search(text.encode('latin-1', 'replace'))


def _line(f, budget):
    line = f.readline(budget + 1)
    if len(line) > budget or not line.endswith(b'\r\n'):
        raise BadRequest('a line is too long or not CRLF-terminated')
    if CTL.search(line[:-2]):
        raise BadRequest('a line holds a control character')
    return line[:-2]


def _admit_bridge(req):
    if not _BRK_AUTH.fullmatch(req.header('authorization') or ''):
        raise Unauthorized('only the execution broker token is admitted here')
    return MAX_BODY


def read_request(f, *, max_headers=MAX_HEADERS, max_header_bytes=MAX_HEADER_BYTES,
                 max_body=MAX_BODY, admit=None):
    """One request from the binary stream *f*, bounded, or BadRequest. Origin-form only:
    no absolute-form, CONNECT, upgrade, chunked body, pipelining or encoded path alias.
    *admit(request)*, when given, decides on the head alone, before any body is read: it
    raises to refuse, and returns the body size it allows."""
    budget = max_header_bytes
    start = _line(f, budget)
    budget -= len(start) + 2
    parts = start.split(b' ')
    if len(parts) != 3 or parts[2] != b'HTTP/1.1':
        raise BadRequest('not an HTTP/1.1 request line')
    try:
        method, target = parts[0].decode('ascii'), parts[1].decode('ascii')
    except UnicodeDecodeError:
        raise BadRequest('a request line is ASCII') from None
    if method not in ('GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
        raise BadRequest('method %r is not relayed' % method[:16])
    path = target.partition('?')[0]
    if (not path.startswith('/') or path.startswith('//') or '%' in path or '\\' in path
            or any(seg in ('.', '..') for seg in path.split('/'))):
        raise BadRequest('the target is not a plain origin-form path')
    headers = []
    while True:
        raw = _line(f, budget)
        budget -= len(raw) + 2
        if not raw:
            break
        if raw[:1] in (b' ', b'\t'):
            raise BadRequest('folded header lines are refused')
        name, sep, value = raw.partition(b':')
        try:
            name, value = name.decode('ascii'), value.decode('latin-1').strip(' \t')
        except UnicodeDecodeError:
            raise BadRequest('a header name is ASCII') from None
        if not sep or not name or not set(name) <= _TOKEN:
            raise BadRequest('a malformed header line')
        headers.append((name, value))
        if len(headers) > max_headers:
            raise BadRequest('too many headers')
    low = [k.lower() for k, _ in headers]
    for name in _SINGLE:
        if low.count(name) > 1:
            raise BadRequest('%s appears more than once' % name)
    if 'transfer-encoding' in low:
        raise BadRequest('a chunked or transfer-encoded request body is refused')
    if 'upgrade' in low:
        raise BadRequest('protocol upgrades are refused')
    req = Request(method, target, tuple(headers))
    cap = max_body if admit is None else min(max_body, admit(req))
    length = req.header('content-length')
    if length is None:
        if method in ('POST', 'PUT', 'PATCH'):
            raise BadRequest('a request body needs a Content-Length')
        return req
    if not length.isdigit():
        raise BadRequest('Content-Length is not a number')
    n = int(length)
    if n > cap:
        raise TooLarge('the body is over %d bytes' % cap)
    body = f.read(n)
    if len(body) != n:
        raise BadRequest('the body ended early')
    return Request(method, target, req.headers, body)


def frame(req):
    """The canonical bytes of *req*: its request line, its headers one per line with the
    length Core will check, a blank line, the body."""
    out = ['%s %s HTTP/1.1' % (req.method, req.target)]
    out += ['%s: %s' % (k, v) for k, v in req.headers if k.lower() != 'content-length']
    out.append('Content-Length: %d' % len(req.body))
    return ('\r\n'.join(out) + '\r\n\r\n').encode('latin-1') + req.body


def local_reply(status, reason):
    """A response the bridge (or Core) answers itself, closing the connection."""
    return ('HTTP/1.1 %d %s\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
            % (status, reason)).encode('ascii')


def _send(sock, data):
    try:
        sock.sendall(data)
    except OSError:
        pass                            # the client went away: nothing to tell it


def _cut(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


class Bridge:
    """The execution-local listener. *connect* opens one connection to Core's pipe and
    returns an object with `sendall`, `recv` and `close` (the native backend's; a test
    passes a fake). The listener is bound when the bridge is made, and it keeps that
    port until `close`: there is no gap between readiness and the CLI's start in which
    another process could take it."""

    def __init__(self, connect, *, host='127.0.0.1', concurrent=CONCURRENT, idle_s=IDLE_S,
                 deadline_s=DEADLINE_S):
        self._connect = connect
        self._slots = threading.BoundedSemaphore(concurrent)
        self._idle, self._deadline = idle_s, deadline_s
        bridge = self

        class _Handler(socketserver.BaseRequestHandler):
            def handle(self):
                bridge.serve(self.request)

        self._server = socketserver.ThreadingTCPServer((host, 0), _Handler,
                                                       bind_and_activate=True)
        self._server.daemon_threads = True
        self._thread = None

    @property
    def port(self):
        return self._server.server_address[1]

    def start(self, ready):
        """Serve in a thread; *ready(port)* is told once the listener accepts."""
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        ready(self.port)

    def close(self):
        self._server.shutdown()
        self._server.server_close()

    def serve(self, sock):
        if not self._slots.acquire(blocking=False):
            _send(sock, local_reply(503, 'Busy'))
            return
        try:
            sock.settimeout(self._idle)
            cut = threading.Timer(self._deadline, _cut, (sock,))
            cut.start()
            try:
                req = read_request(sock.makefile('rb'), admit=_admit_bridge)
            except BadRequest as r:
                _send(sock, local_reply(r.status, 'Refused'))
                return
            except OSError:
                _send(sock, local_reply(400, 'Bad Request'))
                return
            finally:
                cut.cancel()
            # only what Core may use goes over the pipe: the broker token and the
            # forwardable headers. A caller's cookie, proxy or key header never leaves
            keep = tuple((k, v) for k, v in req.headers
                         if k.lower() == 'authorization' or forwarded(k))
            try:
                pipe = self._connect()
            except OSError:
                _send(sock, local_reply(502, 'Bad Gateway'))
                return
            try:
                pipe.sendall(frame(replace(req, headers=keep)))
                while True:
                    chunk = pipe.recv(65536)
                    if not chunk:
                        break
                    sock.sendall(chunk)
            except OSError:
                pass                    # either side went away: the connection ends
            finally:
                pipe.close()
        finally:
            self._slots.release()
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
