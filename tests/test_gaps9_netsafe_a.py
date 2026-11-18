"""T-1361: highest-risk test gaps in claude_sessions/netsafe.py lines 11-50.

Source slice: claude_sessions/netsafe.py:11-50 (card tip 10d688c0; re-located at
worktree tip 76edd1f6, same lines, same content). No source edit.

Ranked candidate probes, denial and fail-closed first. Closest existing test is in
tests/test_netsafe.py. These are candidates, not measured coverage.
 1. 37-39  credential + newurl with no host ('https:///evil') is refused.
           closest: test_any_header_outside_the_plain_set (hosts only)
 2. 28-31  credential + unparseable newurl ('http://[::1') is refused by the
           ValueError branch.  closest: test_f9 (bad port, not urlsplit)
 3. 37-40  plain Host and Content-Length only follow a cross-host redirect.
           closest: test_a_request_with_only_plain_headers (no host or length)
 4. 37     plain-only https->http downgrade is followed (set test short-circuits).
           closest: test_same_origin_redirects (credential only)
 5. 19-21  explicit default ports on a credential downgrade are refused.
           closest: test_f7 (http->https only)
 6. 32     same scheme, different explicit port with credential is refused.
           closest: test_same_origin_redirects (8443 vs default)
 7. 37     mixed plain and credential header set is refused across origin.
           closest: none (single-header cases only)
 8. 35-40  upper-case scheme in newurl is the same origin.
           closest: test_same_origin_redirects (host case only)
 9. 46-50  install() twice builds and installs the opener once.
           closest: test_importing_a_module_that_calls_urlopen (presence only)
10. 37-40  refused credential redirect sends exactly one request, end to end
           through an OpenerDirector with an in-process fake http handler.
           closest: test_gateway/test_omniroute live loopback pair (real servers)

Probe -> branch caught:
 test_credential_redirect_to_a_host_less_url_is_refused     _origin empty host, line 21 / 32
 test_unparseable_redirect_target_is_refused                 try/except ValueError, lines 28-31
 test_plain_host_and_length_headers_follow_across_hosts      _PLAIN_HEADERS members host, content-length, line 14
 test_plain_only_downgrade_is_followed                       set difference short-circuit, line 37
 test_default_port_downgrade_with_credential_is_refused      upgrade tuple (80, 443) direction, line 32
 test_same_scheme_other_explicit_port_is_refused             port inequality, line 32
 test_mixed_headers_with_one_credential_are_refused          set difference nonempty, line 37
 test_upper_case_scheme_is_the_same_origin                   urlsplit scheme normalisation, line 20
 test_install_builds_and_installs_the_opener_once            _installed guard, lines 48-50
 test_refused_credential_redirect_sends_no_second_request    refuse path returns None, line 39
"""

import email.message
import http.client
import io
import urllib.error
import urllib.request
import urllib.response

import pytest

from claude_sessions import netsafe

CRED = {'Authorization': 'Bearer SYNTH'}
PLAIN = {'Accept': 'application/json', 'User-Agent': 'x/1'}


def _redirect(headers, url, new):
    req = urllib.request.Request(url, headers=headers)
    return netsafe.SameOriginRedirect().redirect_request(req, None, 302, 'Found', {}, new)


def test_credential_redirect_to_a_host_less_url_is_refused():
    assert _redirect(CRED, 'https://a.example/x', 'https:///evil.example/y') is None


def test_unparseable_redirect_target_is_refused():
    assert _redirect(CRED, 'http://a.example/x', 'http://[::1') is None


def test_plain_host_and_length_headers_follow_across_hosts():
    headers = {'Host': 'a.example', 'Content-Length': '2'}
    assert _redirect(headers, 'https://a.example/x', 'https://evil.example/y') is not None


def test_plain_only_downgrade_is_followed():
    assert _redirect(PLAIN, 'https://a.example/x', 'http://a.example/y') is not None


def test_default_port_downgrade_with_credential_is_refused():
    assert _redirect(CRED, 'https://a.example:443/x', 'http://a.example:80/y') is None


def test_same_scheme_other_explicit_port_is_refused():
    assert _redirect(CRED, 'https://a.example:8443/x', 'https://a.example:9443/y') is None
    assert _redirect(CRED, 'https://a.example:8443/x', 'https://a.example:8443/y') is not None


def test_mixed_headers_with_one_credential_are_refused():
    mixed = {'Accept': 'application/json', 'Authorization': 'Bearer SYNTH'}
    assert _redirect(mixed, 'https://a.example/x', 'https://evil.example/y') is None
    assert _redirect(mixed, 'https://a.example/x', 'https://a.example/y') is not None


def test_upper_case_scheme_is_the_same_origin():
    assert _redirect(CRED, 'https://a.example/x', 'HTTPS://a.example/y') is not None


def test_install_builds_and_installs_the_opener_once(monkeypatch):
    calls = []

    def build(*handlers):
        calls.append(('build', handlers))
        return 'OPENER'

    def install(opener):
        calls.append(('install', opener))

    monkeypatch.setattr(netsafe, '_installed', False)
    monkeypatch.setattr(urllib.request, 'build_opener', build)
    monkeypatch.setattr(urllib.request, 'install_opener', install)
    netsafe.install()
    netsafe.install()
    assert calls == [('build', (netsafe.SameOriginRedirect,)), ('install', 'OPENER')]


class _FakeHTTP(urllib.request.BaseHandler):
    """In-process stand-in for the network: replies in order, records each request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def _reply(self, req):
        self.sent.append(req)
        code, location = self.replies[len(self.sent) - 1]
        hdrs = http.client.HTTPMessage()
        if location:
            hdrs['Location'] = location
        resp = urllib.response.addinfourl(io.BytesIO(b'{}'), hdrs, req.full_url, code)
        resp.msg = 'OK' if code == 200 else 'Found'
        return resp

    http_open = https_open = _reply


def _opener(fake):
    opener = urllib.request.OpenerDirector()
    for handler in (fake, netsafe.SameOriginRedirect(), urllib.request.HTTPErrorProcessor(),
                    urllib.request.HTTPDefaultErrorHandler()):
        opener.add_handler(handler)
    return opener


def test_refused_credential_redirect_sends_no_second_request():
    fake = _FakeHTTP([(302, 'https://evil.example/y')])
    with pytest.raises(urllib.error.HTTPError) as e:
        _opener(fake).open(urllib.request.Request('https://a.example/x', headers=CRED), timeout=5)
    assert e.value.code == 302
    assert [r.full_url for r in fake.sent] == ['https://a.example/x']


def test_followed_plain_redirect_keeps_its_plain_headers_and_no_credential_appears():
    fake = _FakeHTTP([(302, 'https://evil.example/y'), (200, None)])
    with _opener(fake).open(urllib.request.Request('https://a.example/x', headers=PLAIN),
                            timeout=5) as r:
        assert r.code == 200
    assert [x.full_url for x in fake.sent] == ['https://a.example/x', 'https://evil.example/y']
    assert fake.sent[1].get_header('Accept') == 'application/json'
    assert not fake.sent[1].has_header('Authorization')
