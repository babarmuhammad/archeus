"""Gateway request guard and POST routing (T-1324).

Source slice: claude_sessions/gateway.py lines 447-507, _Handler.do_GET and
_Handler.do_POST. Selected branches, denial and fail-closed first:

  475-476  guard refusal returns before the body is read, parsed or routed
  469-470  GET guard refusal writes no 404; the readiness marker returns before the guard
  498-502  missing or refused upstream target answers 502 and calls no upstream
  480-481  a non-integer Content-Length counts as zero and reads no bytes
  484-487  a non-JSON body answers 400 and calls no upstream
  494-496  an unsupported path answers 404 without a target check
  489-493  count_tokens answers locally with the estimate
  477      the query string is stripped before the endswith test
  503-506  stream selects _stream, anything else selects _once, exactly one runs
  484/503  premise: a JSON array body is a 400 (strict xfail, gateway.py:503 crashes)

Seams: proxy_base.guard, _marker_path, _serving_daemon, _Handler._profile and the
upstream methods are faked; handlers are built without a socket server.
"""
import io
import json

import pytest

from claude_sessions import gateway

PROF = {'id': 'p1', 'api_key': 'k', 'gateway_target_base_url': 'https://models.example.test/v1'}


class _Rfile:
    def __init__(self, data):
        self.data = data
        self.reads = []

    def read(self, n):
        self.reads.append(n)
        return self.data[:n]


def _handler(path='/v1/messages', body=b'{}', length=None):
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.headers = {'Content-Length': str(len(body)) if length is None else length}
    h.rfile = _Rfile(body)
    h.wfile = io.BytesIO()
    h.statuses = []
    h.send_response = h.statuses.append
    h.send_header = lambda *a: None
    h.end_headers = lambda: None
    return h


def _sent(h):
    raw = h.wfile.getvalue()
    status = h.statuses[-1] if h.statuses else None
    return status, (json.loads(raw) if raw else None)


@pytest.fixture
def routed(monkeypatch):
    calls = []
    monkeypatch.setattr(gateway._proxy, 'guard', lambda h, key, marker, label: True)
    monkeypatch.setattr(gateway, '_marker_path', lambda: '/marker')
    monkeypatch.setattr(gateway._Handler, '_profile', lambda self: PROF)
    monkeypatch.setattr(gateway._Handler, '_upstream_call',
                        lambda self, body, prof: calls.append(('upstream',)))
    monkeypatch.setattr(gateway._Handler, '_once',
                        lambda self, body, prof: calls.append(('once', body)))
    monkeypatch.setattr(gateway._Handler, '_stream',
                        lambda self, body, prof: calls.append(('stream', body)))
    return calls


def _record_target_checks(monkeypatch):
    checked = []
    monkeypatch.setattr(gateway, 'target_error', lambda url: checked.append(url) or '')
    return checked


def test_a_refused_post_reads_no_body_and_routes_nothing(routed, monkeypatch):
    monkeypatch.setattr(gateway._proxy, 'guard', lambda h, key, marker, label: False)
    h = _handler(body=b'{"stream": true}')
    h.do_POST()
    assert h.rfile.reads == []
    assert h.statuses == []
    assert routed == []


def test_a_refused_get_writes_no_404_and_the_marker_is_answered_before_the_guard(monkeypatch):
    class _Daemon:
        marker_path = '/marker'

        def serves_marker(self, handler):
            return False

    class _Marker:
        marker_path = '/marker'

        def serves_marker(self, handler):
            return True

    guard_calls = []
    monkeypatch.setattr(gateway, '_serving_daemon', lambda: _Daemon())
    monkeypatch.setattr(gateway, '_marker_path', lambda: '/marker')
    monkeypatch.setattr(gateway._proxy, 'guard',
                        lambda h, key, marker, label: guard_calls.append(h) or False)
    h = _handler(path='/v1/messages')
    h.do_GET()
    assert guard_calls == [h]
    assert h.statuses == []
    assert h.wfile.getvalue() == b''

    monkeypatch.setattr(gateway, '_serving_daemon', lambda: _Marker())
    guard_calls.clear()
    m = _handler(path='/marker')
    m.do_GET()
    assert guard_calls == []
    assert m.statuses == []


@pytest.mark.parametrize('profile, message', [
    ({'id': 'p1', 'gateway_target_base_url': 'https://api.anthropic.com/v1'},
     'refusing to target api.anthropic.com'),
    ({'id': 'p1'}, 'no gateway target configured'),
])
def test_a_missing_or_refused_target_fails_closed_with_a_502(routed, monkeypatch, profile, message):
    monkeypatch.setattr(gateway._Handler, '_profile', lambda self: profile)
    h = _handler(body=b'{"messages": []}')
    h.do_POST()
    status, obj = _sent(h)
    assert status == 502
    assert obj['error']['type'] == 'api_error'
    assert message in obj['error']['message']
    assert routed == []


def test_a_non_numeric_content_length_reads_nothing_and_is_an_empty_body(routed):
    h = _handler(body=b'{"stream": true}', length='abc')
    h.do_POST()
    assert h.rfile.reads == []
    assert routed == [('once', {})]


def test_a_non_json_body_is_a_400_and_reaches_no_upstream(routed):
    h = _handler(body=b'not json{')
    h.do_POST()
    status, obj = _sent(h)
    assert status == 400
    assert obj['error']['type'] == 'invalid_request_error'
    assert routed == []


def test_an_unsupported_path_is_a_404_that_names_only_the_path(routed, monkeypatch):
    checked = _record_target_checks(monkeypatch)
    h = _handler(path='/v1/other?x=1')
    h.do_POST()
    status, obj = _sent(h)
    assert status == 404
    assert obj['error']['type'] == 'not_found_error'
    assert obj['error']['message'] == 'unsupported path /v1/other'
    assert checked == []
    assert routed == []


def test_count_tokens_is_answered_locally_with_the_estimate(routed, monkeypatch):
    checked = _record_target_checks(monkeypatch)
    payload = {'system': 'x' * 400, 'messages': [{'role': 'user', 'content': 'y' * 80}]}
    h = _handler(path='/v1/messages/count_tokens', body=json.dumps(payload).encode())
    h.do_POST()
    assert _sent(h) == (200, {'input_tokens': 120})
    assert checked == []
    assert routed == []


def test_a_query_string_does_not_hide_the_messages_route(routed):
    h = _handler(path='/v1/messages?beta=true', body=b'{}')
    h.do_POST()
    assert routed == [('once', {})]
    assert h.statuses == []


@pytest.mark.parametrize('body, expected', [
    (b'{"stream": true}', 'stream'),
    (b'{"stream": false}', 'once'),
    (b'{}', 'once'),
])
def test_exactly_one_writer_runs_and_stream_true_selects_the_stream_one(routed, body, expected):
    h = _handler(body=body)
    h.do_POST()
    assert [c[0] for c in routed] == [expected]


def test_a_json_array_body_is_a_400_invalid_request(routed):
    h = _handler(body=b'[]')
    h.do_POST()
    status, obj = _sent(h)
    assert status == 400
    assert obj['error']['type'] == 'invalid_request_error'
    assert routed == []
