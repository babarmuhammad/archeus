"""A redirect must never carry a credential to another origin (audit H-05)."""

import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from claude_sessions import gateway, netsafe, omniroute


def _serve(handler):
    srv = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def pair():
    seen = {}

    class Other(BaseHTTPRequestHandler):
        def do_GET(self):
            seen['auth'] = self.headers.get('Authorization')
            seen['key'] = self.headers.get('x-api-key')
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')

        do_POST = do_GET

        def log_message(self, *a):
            pass

    other = _serve(Other)

    class Redirecting(BaseHTTPRequestHandler):
        def do_GET(self):
            n = int(self.headers.get('Content-Length') or 0)
            self.rfile.read(n)
            # 'localhost' is another origin than the 127.0.0.1 the request named
            self.send_response(302)
            self.send_header('Location', 'http://localhost:%d/steal' % other.server_address[1])
            self.send_header('Content-Length', '0')
            self.end_headers()

        do_POST = do_GET

        def log_message(self, *a):
            pass

    first = _serve(Redirecting)
    yield 'http://127.0.0.1:%d' % first.server_address[1], seen
    first.shutdown()
    other.shutdown()


def test_the_gateway_upstream_call_does_not_follow_a_redirect_with_its_key(pair):
    base, seen = pair
    prof = {'gateway_target_base_url': base, 'gateway_target_api_key': 'SYNTH-GATEWAY-KEY'}
    with pytest.raises(urllib.error.HTTPError) as e:
        gateway._Handler._upstream_call(object(), {'model': 'm', 'messages': []}, prof)
    assert e.value.code == 302 and seen == {}


def test_the_omniroute_get_does_not_follow_a_redirect_with_its_key(pair):
    base, seen = pair
    with pytest.raises(urllib.error.HTTPError):
        omniroute._get(base, '/v1/models', 'SYNTH-OMNIROUTE-KEY')
    assert seen == {}


def test_an_x_api_key_header_is_a_credential_too(pair):
    base, seen = pair
    req = urllib.request.Request(base + '/x', headers={'x-api-key': 'SYNTH'})
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(req, timeout=5)
    assert seen == {}


def test_a_redirect_without_a_credential_is_still_followed(pair):
    base, seen = pair
    with urllib.request.urlopen(base + '/x', timeout=5) as r:
        assert r.status == 200
    assert seen['auth'] is None


def _redirect(url, new, scheme_headers):
    req = urllib.request.Request(url, headers=scheme_headers)
    return netsafe.SameOriginRedirect().redirect_request(req, None, 302, 'Found', {}, new)


def test_same_origin_redirects_keep_the_credential_and_scheme_or_host_changes_do_not():
    h = {'Authorization': 'Bearer SYNTH'}
    assert _redirect('https://a.example/x', 'https://A.example/y', h) is not None
    assert _redirect('https://a.example/x', 'https://b.example/y', h) is None
    assert _redirect('https://a.example/x', 'http://a.example/y', h) is None
    assert _redirect('https://a.example:8443/x', 'https://a.example/y', h) is None


@pytest.mark.parametrize('name', ['api-key', 'x-goog-api-key', 'x-auth-token',
                                  'anthropic-auth-token', 'X-Custom-Secret', 'Proxy-Authorization'])
def test_any_header_outside_the_plain_set_is_held_back_from_another_origin(name):
    h = {name: 'SYNTH'}
    assert _redirect('https://a.example/x', 'https://evil.example/y', h) is None
    assert _redirect('https://a.example/x', 'https://a.example/y', h) is not None


def test_a_request_with_only_plain_headers_follows_a_redirect_and_ports_are_normalised():
    plain = {'Accept': 'application/json', 'User-Agent': 'x/1', 'Content-Type': 'application/json',
             'anthropic-version': '2023-06-01', 'anthropic-beta': 'b'}
    assert _redirect('https://a.example/x', 'https://evil.example/y', plain) is not None
    h = {'Authorization': 'Bearer SYNTH'}
    assert _redirect('https://a.example/x', 'https://a.example:443/y', h) is not None
    assert _redirect('http://a.example/x', 'http://A.example:80/y', h) is not None
    assert _redirect('https://a.example/x', 'https://a.example:444/y', h) is None


def test_importing_a_module_that_calls_urlopen_installs_the_handler():
    assert any(isinstance(x, netsafe.SameOriginRedirect)
               for x in urllib.request._opener.handlers)
