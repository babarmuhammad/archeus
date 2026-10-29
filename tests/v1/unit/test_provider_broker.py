"""PV-20 provider broker, Core side (PV20-08 §1): grants, the per-request recheck, the
endpoint/model/limit policy, header handling, destinations, revocation. Synthetic: a fake
transport and a fake upstream; no native operation, no network."""

import base64
import io
import logging
import threading
import time

import pytest

from archeus.api import auth
from archeus.core.domain import ids
from archeus.node import broker as B
from archeus.node import broker_bridge as W

MODEL = 'claude-x'
UPSTREAM_KEY = 'sk-ant-api03-UPSTREAM-SECRET'
BODY =b'{"model":"claude-x","messages":[{"role":"user","content":"hi"}]}'


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

    def read(self, n):
        data = b''.join(self._c)
        self._c = []
        return data[:n]


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
                 credentials=lambda bd: {'x-api-key': UPSTREAM_KEY},
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


def test_a_refused_or_probe_request_leaves_the_grant_counts_unchanged():
    b, _ = broker()
    _, token, d = issued(b, limits=B.BrokerLimits(max_requests=10, concurrent=2))
    g = b._grants[d]
    serve(b, request('HEAD', '/api/hello', token))
    assert g['active'] == 0 and b._in_flight == 0
    serve(b, request('POST', '/v1/nope', token))
    assert g['active'] == 0 and b._in_flight == 0
    g['active'] = 2
    assert serve(b, request(token=token))[1]['status'] == 429
    assert g['active'] == 2 and b._in_flight == 0 and g['requests'] == 0


def _wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.01)
    return cond()


def test_a_flooding_grant_cannot_starve_a_legit_grant():
    gate, entered = threading.Event(), []

    def send(up, addrs, method, path, headers, body, timeout):
        if headers.get('anthropic-beta') == 'flood':
            entered.append(1)
            gate.wait(10)
        return Resp()
    b, _ = broker(send=send)
    _, flood, _ = issued(b, limits=B.BrokerLimits(max_requests=100, concurrent=B.POOL))
    _, legit, _ = issued(b)
    statuses, lock = [], threading.Lock()

    def fire():
        _, row = serve(b, request(token=flood, extra=('anthropic-beta: flood',)))
        with lock:
            statuses.append(row['status'])
    threads = [threading.Thread(target=fire) for _ in range(40)]
    for t in threads:
        t.start()
    assert _wait_for(lambda: b.busy_refused == 38)     # all 40 decided, 2 still in flight
    legit_row = serve(b, request(token=legit))[1]
    gate.set()
    for t in threads:
        t.join(5)
    assert legit_row['status'] == 200
    assert sorted(statuses) == [200, 200] + [503] * 38
    assert b.busy_refused == 38 and b._in_flight == 0


def test_the_pool_refuses_a_grant_once_it_is_full_and_counts_the_refusal():
    gate, entered = threading.Event(), []

    def send(up, addrs, method, path, headers, body, timeout):
        if headers.get('anthropic-beta') == 'hold':
            entered.append(1)
            gate.wait(10)
        return Resp()
    b, _ = broker(send=send, pool=3)
    tokens = [issued(b)[1] for _ in range(4)]
    threads = [threading.Thread(target=serve,
                                args=(b, request(token=t, extra=('anthropic-beta: hold',))))
               for t in tokens[:3]]
    for t in threads:
        t.start()
    assert _wait_for(lambda: len(entered) == 3)
    row = serve(b, request(token=tokens[3]))[1]
    gate.set()
    for t in threads:
        t.join(5)
    assert row['status'] == 503 and b.busy_refused == 1
    assert 503 in [r['status'] for r in b.audit]
    assert b._in_flight == 0


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
    assert low['x-api-key'] == UPSTREAM_KEY and 'authorization' not in low
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
        'User-Agent: claude-cli/1', 'anthropic-beta: tools-1',
        'anthropic-api-key: caller', 'x-stainless-auth: caller')))
    (_, _, _, _, headers, _), = calls
    low = {k.lower() for k in headers}
    assert low == {'x-api-key', 'content-length', 'user-agent', 'anthropic-beta'}


@pytest.mark.parametrize('creds', [
    {'authorization': 'Bearer sk-ant-oat01-x'},
    {'x-api-key': 'K', 'authorization': 'Bearer sk-ant-oat01-x'},
    {'x-api-key': 'bad\r\nInjected: 1'},
    {'x-api-key': ''},
    {},
    {'x-api-key': 'sk-ant-oat01-SECRET'},          # a subscription token, whatever its header
    {'x-api-key': 'SK-ANT-OAT01-SECRET'},
    {'x-api-key': 'sk-ant-ort01-SECRET'},          # a refresh token: not an API key either
    {'x-api-key': 'Sk-Ant-Ort01-SECRET'},
    {'x-api-key': 'sk-ant-admin01-SECRET'},        # any other sk-ant- family: allow-list refuses
    {'x-api-key': 'UPSTREAM-SECRET'},              # an unknown shape: refused, not sent
    {'x-api-key': 'sk-other-api03-SECRET'},
    {'x-api-key': 'sk-ant-api03-SECRET\r\nInjected: yes'},     # an API key with a header smuggled behind it
])
def test_the_upstream_credential_is_one_api_key_or_nothing_is_sent(creds):
    b, calls = broker()
    b._credentials = lambda bd: creds
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 403 and calls == [] and b'Injected' not in out


def test_an_sk_ant_api_key_is_sent_in_any_letter_case():
    b, calls = broker()
    b._credentials = lambda bd: {'x-api-key': 'SK-ANT-API03-SECRET'}
    _, token, _ = issued(b)
    _, row = serve(b, request(token=token))
    assert row['status'] == 200 and calls[0][4]['x-api-key'] == 'SK-ANT-API03-SECRET'


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
    checks = []
    b, _ = broker(live=lambda bd, d: checks.append(1) or len(checks) <= 2,
                  send=lambda *a: Resp(chunks=[b'one', b'two', b'three']))
    _, token, _ = issued(b)
    out, _ = serve(b, request(token=token))
    assert out.endswith(b'one') and b'two' not in out


def test_the_response_cap_ends_the_stream():
    b, _ = broker(send=lambda *a: Resp(chunks=[b'12345', b'67890']))
    _, token, _ = issued(b, limits=B.BrokerLimits(max_requests=3, max_response=7))
    out, row = serve(b, request(token=token))
    assert out.endswith(b'12345') and row['bytes_out'] == 5


def _body(out):
    return out.split(b'\r\n\r\n', 1)[1]


STREAM_FORMS = [
    ('exact', lambda k: k),
    ('case-folded', lambda k: k.lower()),
    ('base64', lambda k: base64.b64encode(k)),
    ('json', lambda k: ''.join('\\u%04x' % ord(c) for c in k.decode()).encode()),
]


@pytest.mark.parametrize('form', [f for _, f in STREAM_FORMS], ids=[n for n, _ in STREAM_FORMS])
@pytest.mark.parametrize('split', ['first', 'middle', 'last'])
def test_a_form_of_the_key_split_across_stream_chunks_cuts_the_stream(form, split):
    f = form(UPSTREAM_KEY.encode())
    j = {'first': 1, 'middle': len(f) // 2, 'last': len(f) - 1}[split]
    b, _ = broker(send=lambda *a: Resp(chunks=[b'ok ' + f[:j], f[j:] + b' tail']))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    # bytes before the held window may already be relayed; the held tail and the rest never are
    assert row['status'] == 200 and _body(out) in (b'', b'ok ') and b'tail' not in out
    assert serve(b, request(token=token))[1]['status'] == 401     # the grant was revoked


def test_a_clean_stream_is_relayed_unchanged_and_in_order():
    chunks = [b'a' * 300, b'bb', b'c' * 1000, b'end c2']   # ends in a base64 prefix of the key, so the held tail is flushed at EOF
    b, _ = broker(send=lambda *a: Resp(chunks=list(chunks)))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert _body(out) == b''.join(chunks) and row['bytes_out'] == len(b''.join(chunks))


FORWARDED = ['anthropic-version', 'anthropic-beta', 'content-type', 'accept', 'user-agent']


@pytest.mark.parametrize('name', FORWARDED)
@pytest.mark.parametrize('value', ['sk-ant-oat01-SECRET', 'SK-ANT-ORT01-SECRET',
                                   'see sk-ant-admin01 here'])
def test_a_forwarded_header_with_a_credential_that_is_not_an_api_key_is_refused(name, value):
    b, calls = broker()
    _, token, _ = issued(b)
    _, row = serve(b, request(token=token, extra=('%s: %s' % (name, value),)))
    assert row['status'] == 403 and calls == []


@pytest.mark.parametrize('name', FORWARDED)
def test_every_occurrence_of_a_forwarded_header_is_checked(name):
    b, calls = broker()
    _, token, _ = issued(b, limits=B.BrokerLimits(max_requests=10))
    bad = '%s: sk-ant-oat01-SECRET' % name
    ok = '%s: ok' % name
    assert serve(b, request(token=token, extra=(ok, bad)))[1]['status'] == 403
    assert serve(b, request(token=token, extra=(bad, ok)))[1]['status'] == 403
    assert calls == []


def test_an_api_key_in_a_forwarded_header_is_allowed():
    b, calls = broker()
    _, token, _ = issued(b)
    _, row = serve(b, request(token=token, extra=('anthropic-beta: sk-ant-api03-ok',)))
    assert row['status'] == 200 and calls[0][4]['anthropic-beta'] == 'sk-ant-api03-ok'


def test_the_key_in_a_status_reason_is_not_relayed():
    b, _ = broker(send=lambda *a: Resp(reason='OK ' + UPSTREAM_KEY))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 200 and UPSTREAM_KEY.encode() not in out
    assert out.startswith(b'HTTP/1.1 200 \r\n')


@pytest.mark.parametrize('extra', [
    ('anthropic-beta: sk-an', 'user-agent: t-oat01-SPLITSECRET'),       # split across headers
    ('anthropic-beta: sk-an', 'anthropic-beta: t-oat01-SPLITSECRET'),   # split across occurrences
    ('anthropic-beta: sk-ant-apioat01-SPLITSECRET',),                   # api-looking, not a key
])
def test_a_credential_split_across_forwarded_headers_is_refused(extra):
    b, calls = broker()
    _, token, _ = issued(b, limits=B.BrokerLimits(max_requests=10))
    _, row = serve(b, request(token=token, extra=extra))
    assert row['status'] == 403 and calls == []


def test_a_whole_api_key_split_across_forwarded_headers_is_sent():
    b, calls = broker()
    _, token, _ = issued(b)
    _, row = serve(b, request(token=token, extra=('anthropic-beta: sk-ant-api03-a',
                                                  'user-agent: b')))
    assert row['status'] == 200 and len(calls) == 1


@pytest.mark.parametrize('prefix', [b'', b'A', b'AB'])
def test_the_key_in_a_base64_blob_at_any_offset_is_not_relayed(prefix):
    blob = base64.b64encode(prefix + UPSTREAM_KEY.encode())
    b, _ = broker(send=lambda *a: Resp(status=529, chunks=[blob]))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 529 and b'Content-Length: 0' in out and blob not in out


@pytest.mark.parametrize('prefix', [b'', b'A', b'AB'])
def test_the_key_in_a_base64_stream_blob_at_any_offset_cuts_the_stream(prefix):
    blob = base64.b64encode(prefix + UPSTREAM_KEY.encode())
    b, _ = broker(send=lambda *a: Resp(chunks=[blob]))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert _body(out) == b'' and blob not in out
    assert serve(b, request(token=token))[1]['status'] == 401


def test_a_stream_is_relayed_as_it_arrives_without_a_held_window():
    b, _ = broker(send=lambda *a: Resp(chunks=[b'hello', b'world']))
    _, token, _ = issued(b)
    pieces = []
    b.serve(request(token=token), pieces.append, 'archeus.x')
    assert pieces[1] == b'hello'


def test_a_listed_name_that_carries_a_credential_word_is_never_forwarded(monkeypatch):
    monkeypatch.setattr(W, 'FORWARD', W.FORWARD | {'x-key-hint', 'anthropic-auth-token'})
    b, calls = broker()
    _, token, _ = issued(b)
    serve(b, request(token=token, extra=('X-Key-Hint: caller', 'Anthropic-Auth-Token: caller')))
    (_, _, _, _, headers, _), = calls
    assert not {k.lower() for k in headers} & {'x-key-hint', 'anthropic-auth-token'}


def test_a_control_character_in_a_header_is_refused_before_the_upstream_sees_it():
    b, calls = broker()
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token, extra=(
        'User-Agent: claude-cli/1\rAuthorization: Bearer CALLER',)))
    assert row['status'] == 400 and calls == [] and b'CALLER' not in out


def test_a_rejected_body_still_counts_against_the_ceiling():
    b, calls = broker()
    _, token, _ = issued(b, limits=B.BrokerLimits(max_requests=2))
    bad = b'{"model":"claude-other","messages":[]}'
    assert [serve(b, request(token=token, body=bad))[1]['status'] for _ in range(2)] == [403, 403]
    assert serve(b, request(token=token))[1]['status'] == 429 and calls == []


def test_an_unauthenticated_head_is_refused_before_any_body_is_read():
    b, calls = broker()
    _, token, _ = issued(b)
    head = (b'POST /v1/messages HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer nope\r\n'
            b'Content-Length: 99999999\r\n\r\n')
    assert serve(b, io.BytesIO(head))[1]['status'] == 401 and calls == []


def test_a_deeply_nested_body_is_a_400_not_an_escape():
    b, calls = broker()
    _, token, _ = issued(b)
    depth = 200_000                 # past every build's limit: 5000 deep parses on 3.14, Linux and macOS
    body = b'[' * depth + b']' * depth
    assert serve(b, request(token=token, body=body))[1]['status'] == 400 and calls == []


def test_the_audit_is_bounded_and_keeps_short_endpoints():
    b, _ = broker()
    for _ in range(B.AUDIT_MAX + 50):
        serve(b, request(token='brk_nope'))
    assert len(b.audit) == B.AUDIT_MAX
    serve(b, request('GET', '/' + 'a' * 5000, token='brk_nope'))
    assert len(b.audit[-1]['endpoint']) <= 200


def test_an_unexpected_error_is_a_local_500_that_carries_no_text_of_it():
    def boom(*a):
        raise ValueError('upstream said UPSTREAM-SECRET')
    b, _ = broker(send=boom)
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 500 and out.startswith(b'HTTP/1.1 500')
    assert b'UPSTREAM-SECRET' not in out and 'UPSTREAM-SECRET' not in repr(b.audit)


def test_the_upstream_key_and_the_broker_token_never_reach_a_log_an_output_or_an_error(
        caplog, capsys):
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger='archeus.broker')

    def boom(*a):
        raise ValueError('upstream said UPSTREAM-SECRET')
    b, _ = broker(send=boom)
    _, token, _ = issued(b)
    outs = [serve(b, request(token=token))[0],
            serve(b, request(token='brk_nope'))[0],
            serve(b, request(token=token, body=b'{"model":"x"}'))[0]]
    ok, _ = broker()
    _, ok_token, _ = issued(ok)
    outs.append(serve(ok, request(token=ok_token))[0])
    seen = capsys.readouterr()
    text = '\n'.join([caplog.text, seen.out, seen.err, repr(list(b.audit)),
                      repr(list(ok.audit)), repr(b._grants), repr(ok._grants)]
                     + [o.decode('latin-1') for o in outs])
    for secret in ('UPSTREAM-SECRET', token, ok_token):
        assert secret not in text


def test_an_upstream_header_with_a_control_character_is_not_relayed():
    b, _ = broker(send=lambda *a: Resp(headers=[('X-Bad', 'a\rInjected: 1'),
                                                ('request-id', 'r2')]))
    _, token, _ = issued(b)
    out, _ = serve(b, request(token=token))
    assert b'Injected' not in out and b'request-id: r2' in out.split(b'\r\n\r\n')[0]


def test_an_upstream_status_line_with_a_control_character_is_not_relayed():
    b, _ = broker(send=lambda *a: Resp(reason='OK\rSet-Cookie: s=1'))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 200 and out.startswith(b'HTTP/1.1 200 \r\n')
    assert b'Set-Cookie' not in out


def test_an_upstream_error_body_is_relayed_without_the_key_or_not_at_all():
    text = b'overloaded for you'
    b, _ = broker(send=lambda *a: Resp(status=529, chunks=[text]))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 529 and out.endswith(text)
    assert b'Content-Length: %d' % len(text) in out
    b, _ = broker(send=lambda *a: Resp(status=529,
                                       chunks=[b'overloaded for ' + UPSTREAM_KEY.encode()]))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 529 and UPSTREAM_KEY.encode() not in out
    assert out.endswith(b'\r\n\r\n') and b'Content-Length: 0' in out
    b, _ = broker(send=lambda *a: Resp(status=529, chunks=[b'x' * (B.ERROR_BODY_MAX + 1)]))
    _, token, _ = issued(b)
    out, _ = serve(b, request(token=token))
    assert out.endswith(b'\r\n\r\n') and b'Content-Length: 0' in out


_ECHOES = [
    lambda k: k,
    lambda k: k.lower(),
    lambda k: base64.b64encode(k),
    lambda k: ''.join('\\u%04x' % ord(c) for c in k.decode()).encode(),
]


@pytest.mark.parametrize('echo', _ECHOES)
def test_a_key_echoed_in_an_error_body_or_header_is_never_relayed(echo):
    key = UPSTREAM_KEY.encode()
    b, _ = broker(send=lambda *a: Resp(status=529, chunks=[b'bad ' + echo(key)]))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 529 and echo(key).lower() not in out.lower()
    assert b'Content-Length: 0' in out
    b, _ = broker(send=lambda *a: Resp(headers=[('X-Echo', echo(key).decode('latin-1'))]))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 200 and echo(key).lower() not in out.lower()
    assert b'X-Echo' not in out


def test_an_error_body_that_trickles_past_the_deadline_or_the_grant_end_is_not_relayed():
    now, reads = [0.0], [0]

    class Trickle(Resp):
        def read1(self, n):
            now[0] += 0.3
            reads[0] += 1
            return b'x' if reads[0] <= 1000 else b''
    b, _ = broker(send=lambda *a: Trickle(status=529), clock=lambda: now[0])
    _, token, _ = issued(b, limits=B.BrokerLimits(max_requests=3, deadline_s=1.0, idle_s=5.0))
    out, row = serve(b, request(token=token))
    assert row['status'] == 529 and b'Content-Length: 0' in out and out.endswith(b'\r\n\r\n')
    assert reads[0] <= 5 and b._in_flight == 0

    calls = []
    b, _ = broker(send=lambda *a: Resp(status=529, chunks=[b'overloaded']),
                  live=lambda bd, d: calls.append(1) or len(calls) == 1)
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 529 and b'Content-Length: 0' in out and b'overloaded' not in out
    assert b._in_flight == 0


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
