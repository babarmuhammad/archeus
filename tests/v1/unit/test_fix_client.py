"""T-606: the TUI client's token goes to the loopback Core and nowhere else (no
proxy from the environment, no followed redirect), a hostile answer is a
CoreError, and a stream that breaks in the HTTP layer is reported as lost."""

import http.client
import http.server
import queue
import threading
import urllib.request

import pytest

from archeus.cli.tui import client as C


class _Server:
    def __init__(self, status=200, body=b'{"ok": true}', location=None):
        outer = self
        self.seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.seen.append((self.path, self.headers.get('Authorization')))
                self.send_response(status)
                if location:
                    self.send_header('Location', location)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.HTTPServer(('127.0.0.1', 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def servers():
    made = []

    def make(**kw):
        made.append(_Server(**kw))
        return made[-1]
    yield make
    for s in made:
        s.close()


def test_the_environment_proxy_never_sees_the_token(servers, monkeypatch):
    core, proxy = servers(), servers()
    for k in ('no_proxy', 'NO_PROXY'):
        monkeypatch.delenv(k, raising=False)
    for k in ('http_proxy', 'HTTP_PROXY'):
        monkeypatch.setenv(k, 'http://127.0.0.1:%d' % proxy.port)
    monkeypatch.setattr(urllib.request, '_opener', None)
    data, _seq = C.Core(core.port, 'tok_secret').get('/v1/x')
    assert data == {'ok': True}
    assert core.seen == [('/v1/x', 'Bearer tok_secret')]
    assert proxy.seen == []


def test_a_redirect_from_the_port_is_a_refusal_and_is_not_followed(servers):
    elsewhere = servers()
    core = servers(status=302, body=b'', location='http://127.0.0.1:%d/stolen' % elsewhere.port)
    with pytest.raises(C.CoreError) as e:
        C.Core(core.port, 'tok_secret').get('/v1/x')
    assert e.value.status == 302
    assert elsewhere.seen == []


@pytest.mark.parametrize('body', [b'null', b'[]', b'"no"', b'42'])
def test_an_error_body_that_is_not_an_object_is_still_a_core_error(servers, body):
    core = servers(status=500, body=body)
    with pytest.raises(C.CoreError) as e:
        C.Core(core.port, 'tok').get('/v1/x')
    assert (e.value.status, e.value.code) == (500, 'http_500')


def test_a_stream_that_breaks_in_the_http_layer_is_reported_as_lost():
    class Broken:
        def events(self, last):
            raise http.client.IncompleteRead(b'part')
            yield

    out = queue.Queue()
    s = C.Stream(Broken(), out)
    s.start()
    try:
        assert out.get(timeout=3) == ('signal', 'stream_lost')
    finally:
        s.stop()
