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
import secrets
import threading
import time
from datetime import datetime, timezone

from ..core.domain import ids

SCOPES = ('observe', 'control', 'approve', 'admin')
#: The local token (the CLI, `archeus core --open`) holds every scope.
LOCAL_SCOPES = SCOPES
#: A browser device made from a launch code is read-only (USER D-scope).
LAUNCH_SCOPES = ('observe',)
LAUNCH_TTL_S = 60.0
LAUNCH_PLATFORMS = ('web', 'desktop')

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


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def live(cred, presented_hash, now=None):
    """True when a `queries.credential` row is a usable device credential:
    the hash matches (compared as bytes), it is neither revoked nor expired,
    and its device is ACTIVE."""
    if cred is None or not hmac.compare_digest(cred['token_hash'].encode('ascii'),
                                               presented_hash.encode('ascii')):
        return False
    if cred['revoked_at'] is not None or cred['device_state'] != 'ACTIVE':
        return False
    return cred['expires_at'] is None or cred['expires_at'] > (now or _now_iso())


class Origin:
    """The one accepted origin, `http://127.0.0.1:<port>` (D10, §18.3).
    `localhost` is deliberately NOT a second name for it: a second origin is a
    second IndexedDB token and a second stream leader (A41)."""

    def __init__(self, port):
        self.port = port
        self.host = '127.0.0.1:%d' % port
        self.origin = 'http://' + self.host

    def host_ok(self, host):
        return host == self.host

    def fetch_ok(self, headers):
        """Fetch metadata: a browser request is same-origin (or typed into the
        address bar); a request with neither header is not a browser's."""
        site = headers.get('Sec-Fetch-Site')
        if site is not None and site not in ('same-origin', 'none'):
            return False
        origin = headers.get('Origin')
        return origin is None or origin == self.origin


def loopback_peer(address):
    host = address[0] if isinstance(address, tuple) else address
    return host == '127.0.0.1' or host == '::1' or str(host).startswith('127.')


class LaunchCodes:
    """In-memory, single-use, 60 s codes: `{sha256(code): (expires, principal,
    device)}`. `redeem` pops under the lock, so of two concurrent redemptions
    exactly one finds the code — the pop IS the use."""

    def __init__(self, clock=time.monotonic, ttl=LAUNCH_TTL_S):
        self.clock, self.ttl = clock, ttl
        self._codes = {}
        self._lock = threading.Lock()

    def mint(self, principal_id, device_id):
        code = secrets.token_urlsafe(32)
        now = self.clock()
        with self._lock:
            self._codes = {h: v for h, v in self._codes.items() if v[0] > now}
            self._codes[token_hash(code)] = (now + self.ttl, principal_id, device_id)
        return code

    def redeem(self, code):
        """(principal_id, device_id) of the minter, or None — for a reused,
        expired, unknown and malformed code alike."""
        if not isinstance(code, str) or not code:
            return None
        with self._lock:
            hit = self._codes.pop(token_hash(code), None)
        if hit is None or self.clock() > hit[0]:
            return None
        return hit[1], hit[2]

    def __len__(self):
        return len(self._codes)
