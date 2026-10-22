"""PV-20 provider broker, Core side (PV20-08 §1; T-050): how an isolated execution reaches
its model without ever holding a provider credential.

    CLI -> execution-local HTTP bridge -> named pipe -> this broker -> the pinned provider

Core owns the upstream credential, the policy and the pipe. Each process generation gets
one grant, bound to (core instance, execution, process, isolated principal, route decision,
account, model) and named by a fresh `brk_` token whose sha256 alone is recorded. Every
request is checked again here: the token, the principal the pipe observed, that the
generation is still the live one (`live`, Core's database answer), the endpoint, the model,
the limits. The bridge is untrusted transport; nothing it says is believed.

Native operations - creating the pipe with its descriptor, launching the bridge inside the
execution's Job, observing a pipe client's principal - are the injected `transport`'s. The
shipped `NativeTransport` refuses all of them, and there is no TCP fallback: until the
native backend exists and N3 proves it, no grant can be issued (fail closed).

Off unless `BROKER_DISPATCH_ENABLED`, which only the composition root sets (PV20-17
activates complete admission at once, never the broker alone).

Known limits, recorded (PV20-09 review round 4):
- S5, the terms and the account's health in `broker_live`, is deferred to PV20-17 by owner
  decision.
- A grant's share of the pool is a cap per grant, not a reservation: while other grants
  hold the pool, a grant gets 503 (owner choice: per-token concurrency share).
- Same-host clients can hold the bridge's connection slots. That is a denial of service to
  the execution's own CLI only, not a leak.
- The key scrub catches the key as itself, case-folded, in base64 and as JSON \\u escapes.
  A part of the key, or another encoding, in an upstream error body is not caught.
"""

import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import re
import secrets
import socket
import ssl
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..core.domain import ids
from . import broker_bridge as wire

BROKER_DISPATCH_ENABLED = False
PREFIX = ids.TOKEN_PREFIXES['broker']

#: what a broker grant forwards (PV20-08 §1): the Anthropic messages endpoint, and the
#: CLI's reachability probe, answered here. Every other target is a local 404.
MESSAGES = '/v1/messages'
HELLO = '/api/hello'
#: the upstream credential: one API key, as a header value
_KEY = re.compile(r'[!-~]+')
#: response headers never relayed back into the boundary
_DROP_BACK = {'connection', 'keep-alive', 'proxy-connection', 'proxy-authenticate', 'te',
              'trailer', 'transfer-encoding', 'upgrade', 'set-cookie', 'content-length'}
#: the audit keeps the last rows only: a client can send requests without end
AUDIT_MAX = 1024
#: in-flight requests the broker holds across all grants; one grant gets a quarter of them
POOL = 8
#: an upstream error body is relayed at most this long, and only if it holds no key, or not at all
ERROR_BODY_MAX = 64 * 1024
#: a subscription login token family (PV20-08b): the OAuth access (sk-ant-oat) and refresh
#: (sk-ant-ort) tokens. Matched case-insensitively: never the upstream credential
_SUBSCRIPTION = 'sk-ant-o'


class Refused(Exception):
    """A request or grant the broker will not serve: *status* is what the client gets."""

    def __init__(self, status, why):
        super().__init__(why)
        self.status = status


class BrokerUnavailable(Exception):
    """A native operation the broker needs does not exist (yet): nothing starts."""


@dataclass(frozen=True)
class BrokerLimits:
    """Core-authored policy, never the execution's to choose. `max_requests` has no
    default on purpose: a grant without a request ceiling is refused at issue."""
    max_requests: int = None
    max_headers: int = wire.MAX_HEADERS
    max_header_bytes: int = wire.MAX_HEADER_BYTES
    max_body: int = wire.MAX_BODY
    concurrent: int = wire.CONCURRENT
    max_response: int = 1 << 30
    idle_s: float = 120.0
    deadline_s: float = 1800.0


@dataclass(frozen=True)
class Upstream:
    """Where a grant's requests go: the account's pinned provider. `kind` is `https`, or
    `provider_proxy` for a registered proxy at an exact loopback http endpoint."""
    url: str
    kind: str = 'https'


@dataclass(frozen=True)
class BrokerBinding:
    core_instance: str
    execution_id: str
    process_seq: int
    principal: str              # the isolated principal the pipe must observe
    route_decision_id: str
    account_id: str
    harness_id: str
    model: str
    upstream: Upstream
    limits: BrokerLimits = field(default_factory=BrokerLimits)


def new_token():
    return '%s_%s' % (PREFIX, secrets.token_urlsafe(32))


def digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def pipe_name(b, nonce):
    """The pipe's logical name: Core's values only, so an execution cannot choose it."""
    return 'archeus.pv20.broker.%s.%s.%d.%s' % (b.core_instance, b.execution_id,
                                                b.process_seq, nonce)


def check_destination(up, resolve=None):
    """The addresses *up* may be reached at, or Refused. https to public addresses only;
    a provider proxy only at an exact loopback http endpoint. Resolved here, and the
    connection goes to these addresses, so a name cannot re-resolve somewhere else."""
    u = urlsplit(up.url)
    if u.username or u.password or u.fragment or u.query or not u.hostname:
        raise Refused(403, 'the upstream is not a plain host URL')
    if up.kind == 'provider_proxy':
        try:
            ip = ipaddress.ip_address(u.hostname)
        except ValueError:
            raise Refused(403, 'a provider proxy is named by a loopback address') from None
        if u.scheme != 'http' or not ip.is_loopback or u.port is None:
            raise Refused(403, 'a provider proxy is an exact loopback http endpoint')
        return [str(ip)]
    if up.kind != 'https' or u.scheme != 'https':
        raise Refused(403, 'the upstream is not https')
    resolve = resolve or (lambda host, port: [a[4][0] for a in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM)])
    try:
        addrs = sorted(set(resolve(u.hostname, u.port or 443)))
    except OSError:
        raise Refused(502, 'the upstream does not resolve') from None
    if not addrs or not all(ipaddress.ip_address(a).is_global for a in addrs):
        raise Refused(403, 'the upstream resolves to a non-public address')
    return addrs


class _Pinned(http.client.HTTPSConnection):
    """HTTPS to an address already checked, verifying the certificate for the name."""

    def __init__(self, host, addr, port, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._addr = addr

    def connect(self):
        sock = socket.create_connection((self._addr, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def send_upstream(up, addrs, method, path, headers, body, timeout):
    """One request to the pinned upstream; the response object (a redirect is returned,
    never followed). No proxy variable is read: http.client reads none."""
    u = urlsplit(up.url)
    if up.kind == 'provider_proxy':
        conn = http.client.HTTPConnection(addrs[0], u.port, timeout=timeout)
    else:
        conn = _Pinned(u.hostname, addrs[0], u.port or 443, timeout)
    base = u.path.rstrip('/')
    conn.request(method, base + path, body=body, headers=headers)
    return conn.getresponse()


class NativeTransport:
    """The native pipe backend's operations. Not built: each refuses, so no grant exists
    and nothing falls back to TCP (PV20-08 §1; owner 2026-10-21, fail closed)."""

    def create(self, name, principal):
        raise BrokerUnavailable('the native broker pipe is not built (N3 has not run)')

    def launch_bridge(self, endpoint, binding):
        raise BrokerUnavailable('the bridge cannot be launched inside the Job yet')

    def close(self, endpoint):
        pass


class Broker:
    """Grants, by token digest, and the per-connection serve. *live(binding, digest)* is
    Core's recheck on every request: the generation is the execution's current one, its
    recorded digest is this one, the terms, account and ceilings still allow it.
    *credentials(binding)* returns the upstream's authentication headers and
    *upstream_of(account_id)* its pinned `Upstream`, both Core-held: no Core-held store of
    provider keys exists yet, so neither has a default and the composition root that
    switches the broker on must supply both. *limits* is Core's policy; its default has no
    request ceiling, so a broker made without one issues nothing."""

    def __init__(self, *, core_instance, live, credentials, upstream_of, limits=None,
                 transport=None, resolve=None, send=send_upstream, clock=time.monotonic,
                 audit=None, pool=POOL):
        self.core_instance = core_instance
        self._live, self._credentials, self.upstream_of = live, credentials, upstream_of
        self.limits = limits or BrokerLimits()
        self.transport = transport or NativeTransport()
        self._resolve, self._send, self._clock = resolve, send, clock
        self.audit = audit if audit is not None else deque(maxlen=AUDIT_MAX)
        self._pool, self._share = pool, max(1, pool // 4)
        self._in_flight = 0         # across all grants, against the pool
        self.busy_refused = 0       # 503s for the pool or a grant's share, counted
        self._grants = {}           # digest -> grant
        self._lock = threading.Lock()

    # ── grants ──

    def issue(self, binding):
        """(token, digest, endpoint, port) for a new process generation, or Refused /
        BrokerUnavailable: then the CLI must not start. Any earlier grant of the
        execution is revoked first: one live generation."""
        if binding.core_instance != self.core_instance:
            raise Refused(403, 'a binding from another Core instance')
        if not (isinstance(binding.limits.max_requests, int) and binding.limits.max_requests > 0):
            raise Refused(403, 'no request ceiling: the grant is refused')
        check_destination(binding.upstream, self._resolve)
        self.revoke(binding.execution_id)
        token = new_token()
        d = digest(token)
        endpoint = self.transport.create(pipe_name(binding, secrets.token_hex(8)),
                                         binding.principal)
        try:
            port = self.transport.launch_bridge(endpoint, binding)
        except BaseException:
            self.transport.close(endpoint)
            raise
        with self._lock:
            self._grants[d] = {'binding': binding, 'endpoint': endpoint, 'requests': 0,
                               'active': 0}
        return token, d, endpoint, port

    def revoke(self, execution_id):
        with self._lock:
            gone = [d for d, g in self._grants.items()
                    if g['binding'].execution_id == execution_id]
            grants = [self._grants.pop(d) for d in gone]
        for g in grants:
            self.transport.close(g['endpoint'])
        return len(grants)

    def sweep(self, live_ids):
        """Revoke every grant whose execution is no longer live: every end path, without
        each one having to remember."""
        with self._lock:
            ids = {g['binding'].execution_id for g in self._grants.values()}
        return sum(self.revoke(x) for x in ids - set(live_ids))

    def revoke_all(self):
        with self._lock:
            ids = {g['binding'].execution_id for g in self._grants.values()}
        return sum(self.revoke(x) for x in ids)

    close = revoke_all

    def authorize(self, token, principal):
        """The grant *token* names, for a client the pipe observed as *principal*."""
        if not (isinstance(token, str) and token.startswith(PREFIX + '_')):
            raise Refused(401, 'not a broker token')
        d = digest(token)
        with self._lock:
            g = next((v for k, v in self._grants.items()
                      if hmac.compare_digest(k.encode(), d.encode())), None)
        if g is None:
            raise Refused(401, 'the broker token is unknown or revoked')
        if not (isinstance(principal, str) and principal == g['binding'].principal):
            raise Refused(403, 'the pipe client is not the execution it was issued to')
        if not self._live(g['binding'], d):
            self.revoke(g['binding'].execution_id)
            raise Refused(401, 'the grant is no longer the live generation')
        return g, d

    # ── one pipe connection ──

    def serve(self, rfile, write, principal):
        """Serve one request read from *rfile*, writing the response with *write*;
        *principal* is what the native backend observed for the pipe client. Never
        raises: every refusal is a local response, and any other error is a local 500
        that carries no text of it. The head is checked before the body is read. Each
        message request (POST /v1/messages) counts against the grant's ceiling whatever
        its body; the hello probe and refused endpoints do not count. Returns the audit
        row."""
        row = {'execution_id': None, 'model': None, 'endpoint': None, 'status': None,
               'bytes_in': 0, 'bytes_out': 0, 'duration_ms': 0}
        t0 = self._clock()
        held = {}

        def admit(head):
            row['endpoint'] = ('%s %s' % (head.method, head.path))[:200]
            g, d = self.authorize(_bearer(head), principal)
            b = g['binding']
            held.update(g=g, d=d, b=b)
            row['execution_id'], row['model'] = b.execution_id, b.model
            if head.method == 'HEAD' and head.path == HELLO and not head.query:
                held['hello'] = True
                return 0
            if not (head.method == 'POST' and head.path == MESSAGES
                    and head.query in ('', 'beta=true')):
                raise Refused(404, 'not a brokered endpoint')
            with self._lock:
                if g['requests'] >= b.limits.max_requests:
                    raise Refused(429, 'the grant has used its requests')
                if g['active'] >= b.limits.concurrent:
                    raise Refused(429, 'too many requests at once')
                if g['active'] >= self._share:
                    self._busy('this grant holds its share of the broker')
                if self._in_flight >= self._pool:
                    self._busy('the broker is busy')
                g['requests'] += 1
                g['active'] += 1
                self._in_flight += 1
            held['active'] = True
            return b.limits.max_body

        try:
            req = wire.read_request(rfile, admit=admit)
            row['bytes_in'] = len(req.body)
            if held.get('hello'):
                write(wire.local_reply(204, 'No Content'))
                row['status'] = 204
                return row
            _model_of(req.body, held['b'].model)
            row['status'], row['bytes_out'] = self._forward(req, held['b'], held['d'], write,
                                                            t0)
        except wire.BadRequest as r:
            row['status'] = r.status
            _reply(write, r.status, 'Refused')
        except Refused as r:
            row['status'] = r.status
            _reply(write, r.status, 'Refused')
        except Exception:
            row['status'] = 500
            _reply(write, 500, 'Internal Error')
        finally:
            if held.get('active'):
                with self._lock:
                    held['g']['active'] -= 1
                    self._in_flight -= 1
            row['duration_ms'] = int((self._clock() - t0) * 1000)
            self.audit.append(row)
        return row

    def _busy(self, why):
        """A 503 for the pool or a grant's share; the caller holds the lock."""
        self.busy_refused += 1
        raise Refused(503, why)

    def _forward(self, req, b, d, write, t0):
        addrs = check_destination(b.upstream, self._resolve)
        creds = self._credentials(b)
        one = isinstance(creds, dict) and set(creds) == {'x-api-key'}
        key = creds['x-api-key'] if one else None
        if not (isinstance(key, str) and _KEY.fullmatch(key)):
            raise Refused(403, 'the upstream credential is not one API key')
        if key.lower().startswith(_SUBSCRIPTION):
            raise Refused(403, 'a subscription token is never the upstream credential')
        headers = {k: v for k, v in req.headers if wire.forwarded(k)}
        headers['x-api-key'] = key
        headers['Content-Length'] = str(len(req.body))
        try:
            resp = self._send(b.upstream, addrs, req.method, req.target, headers, req.body,
                              b.limits.idle_s)
        except (OSError, http.client.HTTPException):
            # never retried: the request may already have reached the provider
            write(wire.local_reply(502, 'Bad Gateway'))
            return 502, 0
        if 300 <= resp.status < 400:
            write(wire.local_reply(502, 'Bad Gateway'))   # a redirect is never followed
            return 502, 0
        reason = resp.reason or ''
        if not wire.clean(reason):
            reason = ''                 # a status line with a control character is not relayed
        out = ['HTTP/1.1 %d %s' % (resp.status, reason)]
        out += ['%s: %s' % (k, v) for k, v in resp.getheaders()
                if k.lower() not in _DROP_BACK and wire.clean('%s: %s' % (k, v))
                and not _leaks('%s: %s' % (k, v), key)]
        if resp.status >= 400:
            # an error body is read under the grant's deadline and liveness, like a stream;
            # it is relayed whole and without the key, or not at all
            buf, whole = bytearray(), False
            while True:
                if self._clock() - t0 > b.limits.deadline_s or not self._live(b, d):
                    break
                chunk = resp.read1(65536) if hasattr(resp, 'read1') else resp.read(65536)
                if not chunk:
                    whole = True
                    break
                buf += chunk
                if len(buf) > ERROR_BODY_MAX:
                    break
            body = bytes(buf) if whole and not _leaks(buf, key) else b''
            out += ['Content-Length: %d' % len(body), 'Connection: close']
            write(('\r\n'.join(out) + '\r\n\r\n').encode('latin-1') + body)
            return resp.status, len(body)
        out.append('Connection: close')
        write(('\r\n'.join(out) + '\r\n\r\n').encode('latin-1'))
        sent = 0
        while True:
            if self._clock() - t0 > b.limits.deadline_s or not self._live(b, d):
                break                   # the grant ended mid-stream: the stream ends
            chunk = resp.read1(65536) if hasattr(resp, 'read1') else resp.read(65536)
            if not chunk:
                break
            if sent + len(chunk) > b.limits.max_response:
                break
            write(chunk)
            sent += len(chunk)
        return resp.status, sent


def _reply(write, status, reason):
    try:
        write(wire.local_reply(status, reason))
    except OSError:
        pass                            # the client went away: nothing to tell it


def _leaks(data, key):
    """True when *data* holds *key* as itself, case-folded, in base64 or as JSON \\u escapes,
    the forms an upstream echoes. A part of the key, or another encoding, is not caught."""
    raw = data.encode('latin-1', 'replace') if isinstance(data, str) else bytes(data)
    k = key.encode('latin-1')
    forms = (k, base64.b64encode(k), ''.join('\\u%04x' % ord(c) for c in key).encode('ascii'))
    low = raw.lower()
    return any(f.lower() in low for f in forms)


def _bearer(req):
    scheme, _, token = (req.header('authorization') or '').partition(' ')
    return token.strip() if scheme.lower() == 'bearer' else None


def _model_of(body, model):
    """Read-only check: one unambiguous string `model`, the pinned one. The bytes forwarded
    are the ones received."""
    try:
        doc = json.loads(body, object_pairs_hook=_no_dupes)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise Refused(400, 'the body is not JSON') from None
    if not isinstance(doc, dict) or doc.get('model') != model or not isinstance(model, str):
        raise Refused(403, 'the request names a model its route did not pin')


def _no_dupes(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError('a duplicate JSON key')
    return dict(pairs)
