"""T-1160 — close the highest-risk test gaps in claude_sessions/proxy_base.py,
lines 276-358 inclusive (tip 56d53504).

The slice owns `guard()` (292-325), `deny()` (328-346) and `write_json()`
(349-358), plus the tail of `Daemon.stop()` (276-278) and the thin delegators
`_own_ctime()`/`pid_alive()` (281-289). The stop() tail and the delegators
were ranked and lost to the guard branches — their fail-closed paths are
already exercised by tests/test_failover.py (`test_a_refused_stop_keeps_the_
lock_of_a_daemon_it_cannot_identify`, `test_a_stop_that_fails_to_kill_the_
daemon_keeps_the_lock`); see the card report for the full ranking.

Final ten selected branches (denial-first, then boundaries, then error paths;
replacements for the already-covered probes 1, 4, 5, 8 are documented with
evidence in /work/QWEN-DONE-T-1160.md):

 1. Host names the right loopback literal on the WRONG port          :308-310
 2. missing / blank Host denies, and host runs before browser+bearer :306-313
 3. fetch-metadata headers deny on the MARKER endpoint                :311-315
 4. x-api-key takes precedence over Authorization                     :316-318
 5. non-ASCII bearer denies without raising; + non-latin-1 key collision :322-323
 6. Host compared case-insensitively and stripped of padding          :306
 7. empty fetch-metadata header is absent, a blank one is not         :312
 8. configured key is stripped; keyless mode skips only the bearer    :314-315
 9. deny() drains only an in-range body, and drains BEFORE replying   :334-341
10. a failing drain read or a failing body write still denies         :339-341, :355-357

No socket, no subprocess, no host state: guard()/deny()/write_json() are
pure over the handler interface, so the seam is a recording fake handler
instead of the loopback server tests/test_failover.py needs, and the config
root is pinned to tmp_path exactly as that file pins it. Independent of any
other test_gaps3 file and of collection order.
"""

import json
import types

import pytest

from claude_sessions import config as _c
from claude_sessions import proxy_base

PORT = 20129
MARKER = '/__archeus_test__/health'
KEY = 'k'
LABEL = 'gaptest'
OK_AUTH = {'Authorization': 'Bearer k'}
GOOD_HOST = '127.0.0.1:%d' % PORT


@pytest.fixture(autouse=True)
def _no_real_config(monkeypatch, tmp_path):
    """proxy_base holds the config module and uses it lazily (Server
    .handle_error, Daemon.lock_path); pin the seam test_failover.py pins so no
    entrypoint in this slice can reach the real settings file."""
    monkeypatch.setattr(_c, 'settings_file', str(tmp_path / 'archeus.json'))


class _Headers:
    """`email.message.get()` semantics, which is what the real handler's
    .headers is: case-insensitive lookup, default None."""

    def __init__(self, init):
        self._d = {k.lower(): v for k, v in init.items()}

    def get(self, name, default=None):
        return self._d.get(name.lower(), default)


class _RFile:
    def __init__(self, handler):
        self.h = handler

    def read(self, n):
        self.h.log.append(('read', n))
        if self.h.fail_read:
            raise OSError('simulated reset while draining the denied body')
        return b''


class _WFile:
    def __init__(self, handler):
        self.h = handler

    def write(self, b):
        if self.h.fail_write:
            raise OSError('simulated reset while writing the refusal')
        self.h.log.append(('write', len(b)))
        self.h.out += b
        return len(b)


class FakeHandler:
    """Every interaction guard/deny/write_json can have with a request, in
    order, so denial content, state and call ORDER are all assertable."""

    def __init__(self, headers=None, path='/v1/messages', port=PORT,
                 fail_read=False, fail_write=False):
        self.headers = _Headers(headers or {})
        self.path = path
        self.server = types.SimpleNamespace(server_address=('127.0.0.1', port))
        self.log = []            # ordered (op, detail) tuples
        self.code = None
        self.sent_headers = {}
        self.out = bytearray()
        self.fail_read = fail_read
        self.fail_write = fail_write
        self.rfile = _RFile(self)
        self.wfile = _WFile(self)

    def send_response(self, code):
        self.log.append(('response', code))
        self.code = code

    def send_header(self, name, value):
        self.log.append(('header', name, value))
        self.sent_headers[name.lower()] = value

    def end_headers(self):
        self.log.append(('end_headers',))


def _run(headers=None, path='/v1/messages', key=KEY, port=PORT):
    h = FakeHandler(headers, path=path, port=port)
    return proxy_base.guard(h, key, MARKER, LABEL), h


def _assert_denied(h, why):
    """The handler holds exactly one 403 whose JSON body names `why`, with a
    Content-Length that matches the bytes actually written."""
    body = bytes(h.out)
    assert h.code == 403, h.log
    assert h.sent_headers.get('content-type') == 'application/json'
    assert int(h.sent_headers['content-length']) == len(body)
    assert json.loads(body.decode('utf-8')) == {
        'type': 'error', 'error': {
            'type': 'permission_error',
            'message': 'archeus %s: refused (%s)' % (LABEL, why)}}


# ── denials, fail-closed first ───────────────────────────────

def test_guard_denies_a_loopback_host_naming_the_wrong_port():
    """Branch: proxy_base.py:308-310, Host not in the port-parameterized
    allowlist. A request aimed at a squatter on another loopback port must not
    be answered by the daemon that merely parses Host."""
    for host in ('127.0.0.1:%d' % (PORT + 1),
                 'localhost:%d' % (PORT + 1),
                 '[::1]:%d' % (PORT + 1)):
        ok, h = _run(dict(OK_AUTH, Host=host))
        assert ok is False, host
        _assert_denied(h, 'bad host')
    # the same three literals on OUR port are accepted: the port, not the
    # literal, is what the denials above are about
    for host in (GOOD_HOST, 'localhost:%d' % PORT, '[::1]:%d' % PORT):
        ok, _h = _run(dict(OK_AUTH, Host=host))
        assert ok is True, host


def test_guard_denies_a_request_without_a_usable_host_before_anything_else():
    """Branch: proxy_base.py:306 (`or ''`) then :308-310. Absent, empty and
    blank Host all deny — and with NO credentials present the refusal still
    names 'bad host', proving Host is checked before the bearer; with both a
    bad Host and an Origin present it still names 'bad host'."""
    for host in (None, '', '   '):
        hdrs = {} if host is None else {'Host': host}
        ok, h = _run(hdrs)                              # no Authorization either
        assert ok is False, repr(host)
        _assert_denied(h, 'bad host')
    ok, h = _run({'Origin': 'https://evil.example'})    # bad host AND browser
    assert ok is False
    _assert_denied(h, 'bad host')
    # and the browser check runs before the bearer: no credentials, an Origin
    # present, is still refused as browser-originated, never as 'bad credentials'
    ok, h = _run({'Host': GOOD_HOST, 'Origin': 'https://evil.example'})
    assert ok is False
    _assert_denied(h, 'browser-originated request')


def test_guard_denies_browser_origin_on_the_marker_endpoint():
    """Branch: proxy_base.py:311-313 with handler.path == marker_path — the
    path exemption at :315 covers the bearer check ONLY. A rebound page may
    not use the readiness probe to fingerprint ports or learn the marker."""
    for hdr in ('Origin', 'Referer', 'Sec-Fetch-Site', 'Sec-Fetch-Mode'):
        ok, h = _run(dict(OK_AUTH, Host=GOOD_HOST, **{hdr: 'https://evil.example'}),
                     path=MARKER)
        assert ok is False, hdr
        _assert_denied(h, 'browser-originated request')
    # the same marker request with no fetch-metadata header proceeds: the
    # path itself is not why the four above were refused
    ok, _h = _run(dict(OK_AUTH, Host=GOOD_HOST), path=MARKER)
    assert ok is True


def test_guard_gives_x_api_key_precedence_over_authorization():
    """Branch: proxy_base.py:316-318, the `or` chain and its order. Reversing
    the chain (Authorization first) passes every pre-existing test but lets a
    stolen-header mix match the wrong credential."""
    ok, h = _run({'Host': GOOD_HOST, 'x-api-key': 'nope',
                  'Authorization': 'Bearer k'})
    assert ok is False                       # the wrong x-api-key wins
    _assert_denied(h, 'bad credentials')
    ok, _h = _run({'Host': GOOD_HOST, 'x-api-key': 'k',
                   'Authorization': 'Bearer nope'})
    assert ok is True                        # the right x-api-key wins too
    ok, _h = _run({'Host': GOOD_HOST, 'x-api-key': '',
                   'Authorization': 'Bearer k'})
    assert ok is True                        # an EMPTY x-api-key is absent, not a credential


def test_guard_refuses_a_question_mark_bearer_for_a_non_latin1_key():
    """Contract: only a bearer equal to the configured credential authenticates.
    Branch: proxy_base.py:322-323. The configured key with U+0100 was folded
    to '?' by the 'replace' encoding, so a client sending a literal '?' pair
    authenticated. A header is decoded as latin-1, so no client can send U+0100
    and the exact key cannot match either: refusal is the reachable behaviour."""
    ok, h = _run({'Host': GOOD_HOST, 'Authorization': 'Bearer pa??ss'},
                 key='pa\u0100\u0100ss')
    assert ok is False
    _assert_denied(h, 'bad credentials')


def test_guard_denies_a_non_ascii_bearer_without_raising():
    """Branch: proxy_base.py:322-323 as written — drop the two .encode calls and
    hmac.compare_digest raises TypeError on a non-ASCII str, which lands in
    Server.handle_error as an unauthenticated traceback instead of a 403. A
    latin-1-round-trippable key must still authenticate: that is the other half
    of why the encoding is latin-1 and not 'ascii'."""
    ok, h = _run({'Host': GOOD_HOST, 'Authorization': 'Bearer k\ufffd\ufffd'})
    assert ok is False
    _assert_denied(h, 'bad credentials')
    ok, _h = _run({'Host': GOOD_HOST, 'Authorization': 'Bearer p\u00e4ss'},
                  key='p\u00e4ss')
    assert ok is True                        # latin-1-representable key+match pass
    ok, h = _run({'Host': GOOD_HOST, 'Authorization': 'Bearer pass'},
                 key='p\u00e4ss')
    assert ok is False
    _assert_denied(h, 'bad credentials')


# ── boundaries ───────────────────────────────────────────────

def test_guard_accepts_the_loopback_host_in_any_case_and_padded_with_spaces():
    """Boundary: proxy_base.py:306, `.strip().lower()`. Drop either and every
    pre-existing denial test still passes while a proxy sitting behind a
    normalizing intermediary is locked out of its own allowlist."""
    for host in ('LOCALHOST:%d' % PORT, 'LocalHost:%d' % PORT,
                 ' %s ' % GOOD_HOST, '\tlocalhost:%d\t' % PORT,
                 '[::1]:%d' % PORT):
        ok, h = _run(dict(OK_AUTH, Host=host))
        assert ok is True, repr(host)


def test_guard_treats_an_empty_fetch_metadata_header_as_absent_but_not_a_blank_one():
    """Boundary: proxy_base.py:312, the truthiness test. `if ... is not None`
    passes every presence-based test on file yet 403s every client that sends a
    present-but-empty Origin; a whitespace-only value IS a browser sending the
    header and must deny."""
    base = dict(OK_AUTH, Host=GOOD_HOST)
    base.update({'Origin': '', 'Referer': '',
                 'Sec-Fetch-Site': '', 'Sec-Fetch-Mode': ''})
    ok, _h = _run(base)
    assert ok is True                        # four empty headers == none sent
    for hdr in ('Origin', 'Referer', 'Sec-Fetch-Site', 'Sec-Fetch-Mode'):
        ok, h = _run(dict(base, **{hdr: ' '}))
        assert ok is False, hdr
        _assert_denied(h, 'browser-originated request')


def test_guard_strips_the_configured_key_and_keyless_mode_skips_only_the_bearer():
    """Branches: proxy_base.py:314 (`key = (key or '').strip()`) and :315
    (`if key and handler.path != marker_path`). Drop `or ''` and a
    keyless-marker probe crashes; drop `.strip()` and a padded configured key
    locks the real client out; make the keyless skip unconditional and every
    request spends the user's upstream quota."""
    ok, _h = _run({'Host': GOOD_HOST, 'Authorization': 'Bearer k'},
                  key='  k  ')
    assert ok is True                        # padded key still authenticates
    for no_key in (None, ''):
        ok, _h = _run({'Host': GOOD_HOST}, key=no_key)
        assert ok is True, repr(no_key)      # keyless local mode: no bearer check
        ok, h = _run({'Host': GOOD_HOST, 'Origin': 'https://evil.example'},
                     key=no_key)
        assert ok is False, repr(no_key)     # ... but the browser check survives
        _assert_denied(h, 'browser-originated request')
        ok, h = _run({'Host': 'evil.example:%d' % PORT}, key=no_key)
        assert ok is False, repr(no_key)     # ... and so does the rebinding check
        _assert_denied(h, 'bad host')
    ok, _h = _run({'Host': GOOD_HOST}, key=KEY, path=MARKER)
    assert ok is True                        # marker exempt from the bearer only


# ── error paths ──────────────────────────────────────────────

def test_deny_drains_only_an_in_range_body_and_refuses_anyway():
    """Branches: proxy_base.py:334-338 — ValueError Content-Length, negatives
    and zero drain nothing, oversized drains nothing, the 1 MiB boundary itself
    drains, and a valid in-range body drains BEFORE the response is started:
    reply-first on Windows surfaces an RST instead of the 403."""
    def _deny(headers):
        h = FakeHandler(headers)
        assert proxy_base.deny(h, LABEL, 'bad host') is False
        return h

    def _reads(h):
        return [t[1] for t in h.log if t[0] == 'read']

    h = _deny({'Content-Length': '9'})
    assert _reads(h) == [9]
    assert h.log.index(('read', 9)) < h.log.index(('response', 403))
    assert h.log.index(('read', 9)) < h.log.index(('end_headers',))
    for bad in ('abc', '-5', '0', str((1 << 20) + 1), None):
        h = _deny({'Content-Length': bad} if bad is not None else {})
        assert _reads(h) == [], repr(bad)    # never hand read() a wild length
        assert h.code == 403, repr(bad)
        assert b'refused' in bytes(h.out), repr(bad)
    h = _deny({'Content-Length': str(1 << 20)})
    assert _reads(h) == [1 << 20]            # the top edge of the window drains


def test_deny_and_write_json_still_reply_when_a_socket_read_or_write_fails():
    """Branches: proxy_base.py:339-341 and :355-357, the two bare excepts. A
    client that dies mid-request must not turn an unauthenticated 403 into a
    traceback in Server.handle_error, and losing the reply is never a license
    to skip the refusal itself."""
    h = FakeHandler({'Content-Length': '9'}, fail_read=True)
    assert proxy_base.deny(h, LABEL, 'bad host') is False
    assert ('read', 9) in h.log
    assert h.code == 403
    _assert_denied(h, 'bad host')

    h2 = FakeHandler({'Host': 'evil.example:%d' % PORT, 'Content-Length': '9'},
                     fail_read=True)
    assert proxy_base.guard(h2, KEY, MARKER, LABEL) is False
    _assert_denied(h2, 'bad host')

    h3 = FakeHandler({}, fail_write=True)    # the peer is gone at write time
    assert proxy_base.write_json(h3, 403, {'type': 'error'}) is None
    assert h3.code == 403                    # the refusal was still composed
    assert h3.sent_headers.get('content-type') == 'application/json'
    assert bytes(h3.out) == b''              # and nothing claimed to go out
