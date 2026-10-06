"""Authentication, not authorization (p3.5b design gate §3 D2, D5, D7, §4).

This layer answers two questions only: is this a live device credential, and
does the credential carry the route's coarse scope. Whether a principal may
fire a given trigger on a given subject is P9's, decided inside the
application layer; nothing here reads a mission, a policy or an actor kind.

Secrets: a device token is `dev_` + 256 random bits, sent only as
`Authorization: Bearer`. Core stores `sha256(token)`; the one plaintext copy at
rest is `run/local-token`. A launch code lives in this process's memory for
60 s, is used once, and is never logged or persisted.
"""

import hashlib
import hmac
import re
import secrets
import threading
import time
from datetime import datetime, timezone

from ..core.domain import ids

SCOPES = ('observe', 'control', 'approve', 'admin')
#: The local token (the CLI, `archeus core --open`) holds every scope.
LOCAL_SCOPES = SCOPES
#: A browser device made from a launch code is read-only (USER D-scope) unless
#: its minter asks for more of its own scopes (p16-design-gate D2).
LAUNCH_SCOPES = ('observe',)
LAUNCH_TTL_S = 60.0
LAUNCH_PLATFORMS = ('web', 'desktop')
#: P15 pairing (p15-design-gate §6): a code's life, a paired client's default
#: scopes, its credential's life (D8) and the platforms it may declare.
PAIR_TTL_S = 120.0
PAIR_SCOPES = ('observe', 'control', 'approve')
PAIRED_TOKEN_DAYS = 180
PAIR_PLATFORMS = ('web', 'desktop', 'ios', 'android')
PIN = re.compile(r'[0-9]{6,12}')

CSP = ("default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; "
       "frame-ancestors 'none'")


def security_headers(cache='no-store'):
    """The headers every response carries (§4), whatever produced it."""
    return {'Content-Security-Policy': CSP, 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'Cache-Control': cache}


def new_token():
    return '%s_%s' % (ids.TOKEN_PREFIXES['device'], secrets.token_urlsafe(32))


def token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def bearer(header):
    """The token of an `Authorization: Bearer <token>` header, or None."""
    scheme, _, token = (header or '').partition(' ')
    token = token.strip()
    if scheme.lower() != 'bearer' or not token or ids.token_kind(token) != 'device':
        return None
    return token


def iso(dt):
    return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def now_iso():
    return iso(datetime.now(timezone.utc))


def live(cred, presented_hash, now=None):
    """True when a `queries.credential` row is a usable device credential:
    the hash matches (compared as bytes), it is neither revoked nor expired,
    and its device is ACTIVE."""
    if cred is None or not hmac.compare_digest(cred['token_hash'].encode('ascii'),
                                               presented_hash.encode('ascii')):
        return False
    if cred['revoked_at'] is not None or cred['device_state'] != 'ACTIVE':
        return False
    return cred['expires_at'] is None or cred['expires_at'] > (now or now_iso())


class Origin:
    """The accepted origins: `http://127.0.0.1:<port>` (D10, §18.3) and, when
    the user enables remote access, `https://<host>` for each configured tunnel
    host (p15-design-gate §8.2, D16). `localhost` is deliberately NOT a second
    name for the local one: a second origin is a second IndexedDB token and a
    second stream leader (A41)."""

    def __init__(self, port, remote_hosts=()):
        self.port = port
        self.host = '127.0.0.1:%d' % port
        self.origin = 'http://' + self.host
        self.remote = tuple(remote_host(h) for h in remote_hosts)

    def host_ok(self, host):
        return host == self.host or host in self.remote

    def local_host(self, host):
        """The request named the loopback origin, not a tunnel's host: half of
        what makes a request local — the other half is the peer (p15 §8.3)."""
        return host == self.host

    def origin_for(self, host):
        """The origin a request naming *host* must come from; no Host (never a
        real request: the Host check runs first) is the local one."""
        return self.origin if host in (None, self.host) else 'https://%s' % host

    def fetch_ok(self, headers):
        """Fetch metadata: a browser request is same-origin (or typed into the
        address bar), and its Origin is the one its own Host names — a tunnel
        host only over https; a request with neither header is not a browser's."""
        site = headers.get('Sec-Fetch-Site')
        if site is not None and site not in ('same-origin', 'none'):
            return False
        origin = headers.get('Origin')
        return origin is None or origin == self.origin_for(headers.get('Host'))


_HOSTNAME = re.compile(r'(?=[a-z0-9.:-]*[a-z])[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
                       r'(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+(?::[0-9]{1,5})?')


def remote_host(host):
    """A tunnel host as its Host header will carry it: a DNS name with at least
    one dot, optionally `:port`. No wildcard, no IP literal, no scheme."""
    h = (host or '').strip().lower()
    if not _HOSTNAME.fullmatch(h) or h.split(':')[0].split('.')[-1].isdigit():
        raise ValueError('a remote host is a DNS name such as pc.tailnet.ts.net: %r' % host)
    return h


def loopback_peer(address):
    host = address[0] if isinstance(address, tuple) else address
    return host == '127.0.0.1' or host == '::1' or str(host).startswith('127.')


class LaunchCodes:
    """In-memory, single-use, short-lived codes: `{sha256(code): (expires,
    payload)}`. `redeem` pops under the lock, so of two concurrent redemptions
    exactly one finds the code — the pop IS the use. A launch code's payload is
    its minter, (principal, device)."""

    def __init__(self, clock=time.monotonic, ttl=LAUNCH_TTL_S):
        self.clock, self.ttl = clock, ttl
        self._codes = {}
        self._lock = threading.Lock()

    def _mint(self, payload, nbytes=32):
        code = secrets.token_urlsafe(nbytes)
        now = self.clock()
        with self._lock:
            self._codes = {h: v for h, v in self._codes.items() if v[0] > now}
            self._codes[token_hash(code)] = (now + self.ttl, payload)
        return code

    def _pop(self, code):
        if not isinstance(code, str) or not code:
            return None
        with self._lock:
            hit = self._codes.pop(token_hash(code), None)
        if hit is None or self.clock() > hit[0]:
            return None
        return hit[1]

    def mint(self, principal_id, device_id, scopes=LAUNCH_SCOPES):
        """*scopes* are the grant the minter asked for, already bounded by its
        own (p16-design-gate D2); the redeemer cannot change them."""
        return self._mint((principal_id, device_id, tuple(scopes)))

    def redeem(self, code):
        """(principal_id, device_id, scopes) of the minter's grant, or None — for
        a reused, expired, unknown and malformed code alike."""
        return self._pop(code)

    def __len__(self):
        return len(self._codes)


class PairingLocked(RuntimeError):
    """Too many failed redemptions: every live code was burned (p15 D10)."""


class PairingCodes(LaunchCodes):
    """Pairing bootstrap codes (p15-design-gate §6, D7, D10): 128 bits, 120 s,
    single use. The payload is the grant fixed at the start (starter, scopes,
    name, host label), so a redeemer cannot widen it. More than `FAIL_LIMIT`
    failed redemptions inside `FAIL_WINDOW_S` burn every live code and refuse
    redemption until the window has passed."""

    FAIL_LIMIT = 10
    FAIL_WINDOW_S = 60.0

    def __init__(self, clock=time.monotonic, ttl=PAIR_TTL_S):
        super().__init__(clock=clock, ttl=ttl)
        self._fails = []
        self._locked_until = float('-inf')

    def mint(self, grant):
        return self._mint(dict(grant), nbytes=16)

    def redeem(self, code):
        """The grant, or None (unknown, expired, reused, malformed alike);
        raises PairingLocked while the breaker is open."""
        now = self.clock()
        if now < self._locked_until:
            raise PairingLocked()
        grant = self._pop(code)
        if grant is not None:
            return grant
        with self._lock:
            self._fails = [t for t in self._fails if t > now - self.FAIL_WINDOW_S] + [now]
            if len(self._fails) > self.FAIL_LIMIT:
                self._codes.clear()
                self._fails = []
                self._locked_until = now + self.FAIL_WINDOW_S
                raise PairingLocked()
        return None


class StepUpFailures:
    """Consecutive wrong step-up PIN proofs per client, in memory (p15 D19):
    the `LIMIT`th revokes the client. A correct proof resets the count."""

    LIMIT = 5

    def __init__(self):
        self._n = {}
        self._lock = threading.Lock()

    def failed(self, device_id):
        """True when this failure is the one that must revoke."""
        with self._lock:
            self._n[device_id] = self._n.get(device_id, 0) + 1
            return self._n[device_id] >= self.LIMIT

    def reset(self, device_id):
        with self._lock:
            self._n.pop(device_id, None)
