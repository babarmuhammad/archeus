"""T-1307 — close the highest-risk test gaps in claude_sessions/proxy_base.py,
lines 292-325 inclusive (tip 53865a4a of pv20-fx79n; re-located by reading the
source, the card's line numbers came from an older tip).

Slice: `guard()` — Host, browser fetch-metadata, configured-key handling, the
marker exemption and the bytes comparison of the presented credential.

Selected branches, denial/fail-closed first, then boundaries, then error paths:

 1. :322  hmac.compare_digest receives UTF-8 bytes for both operands, never a
          non-ASCII str
 2. :323  distinct non-ASCII credentials that share an ASCII prefix are denied;
          the encoding does not collapse them
 3. :322  lone surrogates compare with surrogatepass, equal ones pass, unequal
          ones are denied, nothing raises
 4. :316  a whitespace-only x-api-key is present and does not fall back to a
          valid Authorization bearer (fail closed)
 5. :317  only the exact `Bearer ` prefix is removed; lowercase or run-together
          prefixes fail the configured-key comparison
 6. :318  padding around the presented credential is trimmed; internal
          whitespace stays significant
 7. :315  an empty or blank configured key skips the credential compare and
          never skips the Host or browser checks
 8. :315  the exact marker path skips the credential compare; a suffix or query
          variant of it does not
 9. :308  a bad Host is denied before any compare, marker path included
10. :311  a browser header denies before any compare, even with the right
          non-ASCII key or on the marker path

Closest existing tests (tests/test_gaps3_claude_sessions_proxy_base_guard.py):
x-api-key precedence, non-latin-1 and non-ASCII bearer refusal, host case and
padding, keyless mode, marker exemption and browser denial on the marker. Those
assert the outcome; these probes add the compare-call spy (no compare on a
refusal, bytes operands), the lowercase/run-together prefix, the surrogate and
prefix-collision inputs, the marker suffix variant and the whitespace-only
x-api-key that must not fall back.

Pure over the handler interface: a recording fake handler, no socket, no
subprocess, no config file. A spy wraps hmac.compare_digest and calls the real
one, so the outcome and the call count are both observed.
"""

import hmac
import json
import types

import pytest

from claude_sessions import proxy_base

PORT = 20307
MARKER = '/__archeus_test__/health'
LABEL = 'gaptest'
GOOD_HOST = '127.0.0.1:%d' % PORT


class _Headers:
    def __init__(self, init):
        self._d = {k.lower(): v for k, v in init.items()}

    def get(self, name, default=None):
        return self._d.get(name.lower(), default)


class _RFile:
    def read(self, n):
        return b''


class _WFile:
    def __init__(self, handler):
        self.h = handler

    def write(self, b):
        self.h.out += b
        return len(b)


class FakeHandler:
    def __init__(self, headers=None, path='/v1/messages'):
        self.headers = _Headers(headers or {})
        self.path = path
        self.server = types.SimpleNamespace(server_address=('127.0.0.1', PORT))
        self.code = None
        self.out = b''
        self.rfile = _RFile()
        self.wfile = _WFile(self)

    def send_response(self, code):
        self.code = code

    def send_header(self, name, value):
        pass

    def end_headers(self):
        pass


@pytest.fixture
def compares(monkeypatch):
    """Record every hmac.compare_digest call; the real comparison still decides."""
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, 'compare_digest', spy)
    return calls


def _run(headers=None, path='/v1/messages', key='k'):
    h = FakeHandler(headers, path=path)
    return proxy_base.guard(h, key, MARKER, LABEL), h


def _assert_denied(h, why):
    assert h.code == 403
    body = json.loads(h.out.decode('utf-8'))
    assert body['error']['message'] == 'archeus %s: refused (%s)' % (LABEL, why)


OK = {'Host': GOOD_HOST}


def test_compare_digest_receives_utf8_bytes_for_both_operands(compares):
    ok, _h = _run(dict(OK, Authorization='Bearer päss'), key='päss')
    assert ok is True
    assert compares == [('päss'.encode('utf-8'), 'päss'.encode('utf-8'))]
    assert all(isinstance(x, bytes) for pair in compares for x in pair)


def test_non_ascii_credentials_sharing_an_ascii_prefix_do_not_collide(compares):
    ok, h = _run(dict(OK, Authorization='Bearer sk-ä1'), key='sk-ä2')
    assert ok is False
    _assert_denied(h, 'bad credentials')
    ok, _h = _run(dict(OK, Authorization='Bearer sk-ä2'), key='sk-ä2')
    assert ok is True
    ok, h = _run(dict(OK, Authorization='Bearer sk-e2'), key='sk-ä2')
    assert ok is False
    _assert_denied(h, 'bad credentials')


def test_lone_surrogates_compare_without_raising_and_unequal_ones_are_denied(compares):
    ok, _h = _run(dict(OK, Authorization='Bearer \ud800'), key='\ud800')
    assert ok is True
    ok, h = _run(dict(OK, Authorization='Bearer \udc00'), key='\ud800')
    assert ok is False
    _assert_denied(h, 'bad credentials')
    assert len(compares) == 2


def test_a_whitespace_only_x_api_key_is_present_and_does_not_fall_back_to_a_good_bearer(compares):
    ok, h = _run(dict(OK, **{'x-api-key': '   ', 'Authorization': 'Bearer k'}), key='k')
    assert ok is False
    _assert_denied(h, 'bad credentials')
    ok, _h = _run(dict(OK, **{'x-api-key': '', 'Authorization': 'Bearer k'}), key='k')
    assert ok is True


@pytest.mark.parametrize('auth', ['bearer k', 'BEARER k', 'Bearerk', 'Basic k', 'Bearer'])
def test_only_the_exact_bearer_prefix_is_stripped(compares, auth):
    ok, h = _run(dict(OK, Authorization=auth), key='k')
    assert ok is False, auth
    _assert_denied(h, 'bad credentials')
    assert len(compares) == 1


def test_padding_is_trimmed_and_internal_whitespace_stays_significant(compares):
    ok, _h = _run(dict(OK, **{'x-api-key': '  k  '}), key='k')
    assert ok is True
    ok, _h = _run(dict(OK, Authorization='Bearer a b'), key='a b')
    assert ok is True
    ok, h = _run(dict(OK, Authorization='Bearer a  b'), key='a b')
    assert ok is False
    _assert_denied(h, 'bad credentials')


@pytest.mark.parametrize('key', ['', '   '])
def test_a_blank_configured_key_skips_the_compare_but_not_host_or_browser(compares, key):
    ok, _h = _run(OK, key=key)
    assert ok is True
    assert compares == []
    ok, h = _run({'Host': 'evil.example:%d' % PORT}, key=key)
    assert ok is False
    _assert_denied(h, 'bad host')
    ok, h = _run(dict(OK, Origin='https://evil.example'), key=key)
    assert ok is False
    _assert_denied(h, 'browser-originated request')
    assert compares == []


def test_the_exact_marker_path_skips_the_compare_and_its_suffix_variants_do_not(compares):
    ok, _h = _run(OK, path=MARKER, key='k')
    assert ok is True
    assert compares == []
    for path in (MARKER + '?probe=1', MARKER + '/', MARKER.rstrip('/')[:-1]):
        ok, h = _run(OK, path=path, key='k')
        assert ok is False, path
        _assert_denied(h, 'bad credentials')
    assert len(compares) == 3


def test_a_bad_host_is_denied_before_any_compare_including_on_the_marker_path(compares):
    for path in ('/v1/messages', MARKER):
        ok, h = _run({'Host': 'evil.example:%d' % PORT, 'Authorization': 'Bearer k'},
                     path=path, key='k')
        assert ok is False, path
        _assert_denied(h, 'bad host')
    assert compares == []


def test_a_browser_header_is_denied_before_any_compare_even_with_the_right_key(compares):
    right = 'päss'
    for path in ('/v1/messages', MARKER):
        ok, h = _run(dict(OK, Authorization='Bearer ' + right, Origin='https://x.example'),
                     path=path, key=right)
        assert ok is False, path
        _assert_denied(h, 'browser-originated request')
    assert compares == []
