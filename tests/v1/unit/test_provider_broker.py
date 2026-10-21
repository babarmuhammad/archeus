"""PV-20 provider broker, Core side (PV20-08 §1): grants, the per-request recheck, the
endpoint/model/limit policy, header handling, destinations, revocation. Synthetic: a fake
transport and a fake upstream; no native operation, no network."""

import io

import pytest

from archeus.api import auth
from archeus.core.domain import ids
from archeus.node import broker as B
from archeus.node import broker_bridge as W

MODEL = 'claude-x'
BODY = b'{"model":"claude-x","messages":[{"role":"user","content":"hi"}]}'


class Transport:
    def __init__(self, fail_launch=False):
        self.created, self.closed, self.fail_launch = [], [], fail_launch

    def create(self, name, principal):
        self.created.append((name, principal))
        return 'ep%d' % len(self.created)

    def launch_bridge(self, endpoint, binding):
        if self.fail_launch:
            raise B.BrokerUnavailable('no Job')
        return 4321

    def close(self, endpoint):
        self.closed.append(endpoint)


class Resp:
    def __init__(self, status=200, headers=(), chunks=(b'ok',), reason='OK'):
        self.status, self.reason, self._h, self._c = status, reason, list(headers), list(chunks)

    def getheaders(self):
        return self._h

    def read1(self, n):
        return self._c.pop(0) if self._c else b''


def binding(**kw):
    kw = dict(dict(core_instance='core1', execution_id=ids.new_id('execution'), process_seq=1,
                   principal='archeus.x', route_decision_id='rte_1', account_id='acc_1',
                   harness_id='claude_code', model=MODEL,
                   upstream=B.Upstream('https://api.example.com'),
                   limits=B.BrokerLimits(max_requests=3)), **kw)
    return B.BrokerBinding(**kw)


def broker(live=True, send=None, transport=None, **kw):
    calls = []

    def default_send(up, addrs, method, path, headers, body, timeout):
        calls.append((up, addrs, method, path, dict(headers), body))
        return Resp(headers=[('content-type', 'application/json'), ('Set-Cookie', 'a=b'),
                             ('Connection', 'keep-alive'), ('request-id', 'r1')])
    b = B.Broker(core_instance='core1',
                 live=live if callable(live) else (lambda bd, d: live),
                 credentials=lambda bd: {'x-api-key': 'UPSTREAM-SECRET'},
                 upstream_of=lambda a: B.Upstream('https://api.example.com'),
                 transport=transport or Transport(),
                 resolve=lambda host, port: ['93.184.216.34'],
                 send=send or default_send, **kw)
    return b, calls


def request(method='POST', target='/v1/messages', token=None, body=BODY, extra=()):
    lines = ['%s %s HTTP/1.1' % (method, target), 'Host: 127.0.0.1:4321']
    if token:
        lines.append('Authorization: Bearer %s' % token)
    lines += list(extra)
    if method == 'POST':
        lines.append('Content-Length: %d' % len(body))
    else:
        body = b''
    return io.BytesIO(('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1') + body)


def serve(b, data, principal='archeus.x'):
    out = []
    row = b.serve(data, out.append, principal)
    return b''.join(out), row


def issued(b, **kw):
    bd = binding(**kw)
    token, d, ep, port = b.issue(bd)
    return bd, token, d


# ── tokens and grants ──

def test_a_broker_token_is_its_own_kind_that_no_core_route_accepts():
    t = B.new_token()
    assert t.startswith('brk_') and ids.token_kind(t) == 'broker'
    assert auth.bearer('Bearer ' + t) is None


def test_issue_mints_a_fresh_token_and_keeps_only_its_digest():
    b, _ = broker()
    bd, token, d = issued(b)
    assert d == B.digest(token) and token not in repr(b._grants)
    assert b.transport.created[0][1] == 'archeus.x'
    assert bd.execution_id in b.transport.created[0][0]
    _, token2, d2 = issued(b, execution_id=bd.execution_id, process_seq=2)
    assert token2 != token and d not in b._grants and d2 in b._grants   # one generation


@pytest.mark.parametrize('kw,status', [
    ({'limits': B.BrokerLimits()}, 403),                        # no request ceiling
    ({'limits': B.BrokerLimits(max_requests=0)}, 403),
    ({'core_instance': 'other'}, 403),
    ({'upstream': B.Upstream('http://api.example.com')}, 403),
])
def test_issue_refuses_and_creates_nothing(kw, status):
    b, _ = broker()
    with pytest.raises(B.Refused) as r:
        issued(b, **kw)
    assert r.value.status == status and b.transport.created == [] and b._grants == {}


def test_the_shipped_native_transport_refuses_so_nothing_is_ever_granted():
    b, _ = broker(transport=B.NativeTransport())
    with pytest.raises(B.BrokerUnavailable):
        issued(b)
    assert b._grants == {}


def test_a_bridge_that_cannot_be_launched_closes_its_endpoint():
    t = Transport(fail_launch=True)
    b, _ = broker(transport=t)
    with pytest.raises(B.BrokerUnavailable):
        issued(b)
    assert t.closed == ['ep1'] and b._grants == {}


def test_revoke_sweep_and_revoke_all_close_the_endpoints():
    b, _ = broker()
    a, _, _ = issued(b)
    c, _, _ = issued(b)
    assert b.sweep({c.execution_id}) == 1 and b.transport.closed == ['ep1']
    assert b.revoke_all() == 1 and b.transport.closed == ['ep1', 'ep2'] and b._grants == {}


# ── authorisation, rechecked on every request ──

@pytest.mark.parametrize('case', ['none', 'device', 'unknown', 'principal', 'dead'])
def test_a_request_is_refused_unless_its_grant_is_live_and_its_client_is_the_execution(case):
    live = {'v': case != 'dead'}
    b, calls = broker(live=lambda bd, d: live['v'])
    bd, token, _ = issued(b)
    tok = {'none': None, 'device': auth.new_token(), 'unknown': B.new_token()}.get(case, token)
    out, row = serve(b, request(token=tok),
                     principal='archeus.peer' if case == 'principal' else 'archeus.x')
    assert row['status'] == (403 if case == 'principal' else 401) and calls == []
    assert out.startswith(b'HTTP/1.1 %d' % row['status'])
    if case == 'dead':
        assert b._grants == {}                  # a dead generation is revoked on sight


# ── endpoints, model, limits ──

def test_the_hello_probe_is_answered_locally():
    b, calls = broker()
    _, token, _ = issued(b)
    out, row = serve(b, request('HEAD', '/api/hello', token))
    assert row['status'] == 204 and out.startswith(b'HTTP/1.1 204') and calls == []


@pytest.mark.parametrize('method,target', [('POST', '/v1/messages?beta=false'),
                                           ('POST', '/v1/messages/count_tokens'),
                                           ('GET', '/v1/models'), ('POST', '/v1/complete'),
                                           ('HEAD', '/api/hello?x=1')])
def test_every_other_endpoint_is_a_local_404(method, target):
    b, calls = broker()
    _, token, _ = issued(b)
    _, row = serve(b, request(method, target, token))
    assert row['status'] == 404 and calls == []


@pytest.mark.parametrize('body,status', [
    (b'{"model":"claude-other","messages":[]}', 403),
    (b'{"messages":[]}', 403),
    (b'["claude-x"]', 403),
    (b'{"model":"claude-x","model":"claude-other"}', 400),        # ambiguous
    (b'not json', 400),
])
def test_the_body_must_name_exactly_the_pinned_model(body, status):
    b, calls = broker()
    _, token, _ = issued(b)
    _, row = serve(b, request(token=token, body=body))
    assert row['status'] == status and calls == []


def test_the_request_ceiling_and_the_body_limit_are_enforced():
    b, calls = broker()
    _, token, _ = issued(b, limits=B.BrokerLimits(max_requests=2, max_body=len(BODY)))
    assert [serve(b, request(token=token))[1]['status'] for _ in range(3)] == [200, 200, 429]
    assert len(calls) == 2
    _, token, _ = issued(b, limits=B.BrokerLimits(max_requests=5, max_body=len(BODY) - 1))
    assert serve(b, request(token=token))[1]['status'] == 413


def test_concurrency_is_bounded_per_grant():
    b, calls = broker()
    _, token, d = issued(b, limits=B.BrokerLimits(max_requests=5, concurrent=1))
    b._grants[d]['active'] = 1
    assert serve(b, request(token=token))[1]['status'] == 429 and calls == []


# ── what is forwarded, what comes back ──

def test_the_client_authority_is_stripped_and_core_supplies_the_upstreams():
    b, calls = broker()
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token, extra=(
        'x-api-key: brk_also', 'Cookie: c=1', 'X-Forwarded-For: 1.2.3.4',
        'Forwarded: for=x', 'Connection: X-Secret', 'X-Secret: y', 'Proxy-Authorization: p',
        'anthropic-version: 2023-06-01', 'anthropic-beta: tools-1')))
    (up, addrs, method, path, headers, body), = calls
    low = {k.lower(): v for k, v in headers.items()}
    assert body == BODY and (method, path) == ('POST', '/v1/messages')
    assert addrs == ['93.184.216.34']
    assert low['x-api-key'] == 'UPSTREAM-SECRET' and 'authorization' not in low
    for gone in ('cookie', 'x-forwarded-for', 'forwarded', 'x-secret', 'proxy-authorization',
                 'host', 'connection'):
        assert gone not in low, gone
    assert low['anthropic-version'] == '2023-06-01' and low['anthropic-beta'] == 'tools-1'
    head = out.split(b'\r\n\r\n')[0].lower()
    assert b'set-cookie' not in head and b'keep-alive' not in head and b'request-id: r1' in head
    assert out.endswith(b'ok') and row['status'] == 200


def test_only_the_standard_and_anthropic_headers_are_forwarded():
    b, calls = broker()
    _, token, _ = issued(b)
    serve(b, request(token=token, extra=(
        'api-key: caller', 'X-Goog-Api-Key: caller', 'X-Auth-Token: caller', 'X-Custom: 1',
        'User-Agent: claude-cli/1', 'anthropic-beta: tools-1')))
    (_, _, _, _, headers, _), = calls
    low = {k.lower() for k in headers}
    assert low == {'x-api-key', 'content-length', 'user-agent', 'anthropic-beta'}


@pytest.mark.parametrize('creds', [
    {'authorization': 'Bearer sk-ant-oat01-x'},
    {'x-api-key': 'K', 'authorization': 'Bearer sk-ant-oat01-x'},
    {'x-api-key': 'bad\r\nInjected: 1'},
    {'x-api-key': ''},
    {},
])
def test_the_upstream_credential_is_one_api_key_or_nothing_is_sent(creds):
    b, calls = broker()
    b._credentials = lambda bd: creds
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 403 and calls == [] and b'Injected' not in out


def test_the_audit_row_holds_ids_and_sizes_never_content():
    b, _ = broker()
    bd, token, _ = issued(b)
    _, row = serve(b, request(token=token))
    assert set(row) == {'execution_id', 'model', 'endpoint', 'status', 'bytes_in', 'bytes_out',
                        'duration_ms'}
    assert (row['execution_id'], row['model'], row['bytes_in']) == (bd.execution_id, MODEL,
                                                                    len(BODY))
    assert token not in repr(b.audit) and 'hi' not in repr(b.audit)


@pytest.mark.parametrize('status', [301, 302, 307, 308])
def test_a_redirect_is_never_followed(status):
    sent = []
    b, _ = broker(send=lambda *a: sent.append(a) or Resp(status, [('Location', 'http://x')]))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 502 and len(sent) == 1 and b'Location' not in out


def test_an_upstream_failure_is_never_retried():
    sent = []

    def boom(*a):
        sent.append(a)
        raise OSError('reset')
    b, _ = broker(send=boom)
    _, token, _ = issued(b)
    assert serve(b, request(token=token))[1]['status'] == 502 and len(sent) == 1


def test_a_stream_stops_when_the_grant_ends_mid_stream():
    state = {'live': True}
    b, _ = broker(live=lambda bd, d: state['live'],
                  send=lambda *a: Resp(chunks=[b'one', b'two', b'three']))
    _, token, _ = issued(b)
    out = []

    def write(data):
        out.append(data)
        if data == b'one':
            state['live'] = False
    b.serve(request(token=token), write, 'archeus.x')
    assert out[-1] == b'one'


def test_the_response_cap_ends_the_stream():
    b, _ = broker(send=lambda *a: Resp(chunks=[b'12345', b'67890']))
    _, token, _ = issued(b, limits=B.BrokerLimits(max_requests=3, max_response=7))
    out, row = serve(b, request(token=token))
    assert out.endswith(b'12345') and row['bytes_out'] == 5


# ── destinations ──

@pytest.mark.parametrize('url,kind,addrs', [
    ('http://api.example.com', 'https', ['93.184.216.34']),
    ('https://user:pw@api.example.com', 'https', ['93.184.216.34']),
    ('https://api.example.com/?x=1', 'https', ['93.184.216.34']),
    ('https://internal', 'https', ['10.0.0.5']),
    ('https://metadata', 'https', ['169.254.169.254']),
    ('https://core', 'https', ['127.0.0.1']),
    ('https://mixed', 'https', ['93.184.216.34', '192.168.1.2']),
    ('http://10.0.0.5:8080', 'provider_proxy', []),
    ('http://localhost:8080', 'provider_proxy', []),
    ('https://127.0.0.1:8080', 'provider_proxy', []),
    ('http://127.0.0.1', 'provider_proxy', []),                    # no exact port
    ('https://api.example.com', 'socks', ['93.184.216.34']),
])
def test_only_public_https_or_an_exact_loopback_proxy_is_a_destination(url, kind, addrs):
    with pytest.raises(B.Refused):
        B.check_destination(B.Upstream(url, kind), lambda h, p: addrs)


def test_the_good_destinations():
    assert B.check_destination(B.Upstream('https://api.example.com'),
                               lambda h, p: ['93.184.216.34']) == ['93.184.216.34']
    assert B.check_destination(B.Upstream('http://127.0.0.1:8080', 'provider_proxy')) == [
        '127.0.0.1']


def test_the_wire_parser_core_uses_is_the_bridges():
    assert B.wire is W
