"""T-1005 · archeus/node/broker.py lines 1-300: the ten highest-risk uncovered branches.

Slice: archeus/node/broker.py lines 1-300 inclusive (`new_token`, `digest`, `pipe_name`,
`check_destination`, `_Pinned`, `send_upstream`, `NativeTransport`, `_Deadline`,
`Broker.__init__`, the first refusals of `Broker.issue`). Code below line 300 is read-only
context: the branches of `issue`/`serve`/`_forward` that sit there belong to the next card,
and nothing here depends on this file's position in any queue.

Selected branches (evidence, closest existing test and the risk ranking live in
/work/QWEN-DONE-T-1005.md):
 1. broker.py:278 with 290-301  `Broker.limits` is inert: a broker built without Core's
                                policy still issues a grant                       [xfail]
 2. broker.py:165               `urlsplit()` itself raises ValueError on a malformed IPv6
                                literal, and only the `u.port` read is wrapped     [xfail]
 3. broker.py:170-171           `not u.hostname` - a URL that names no host at all
 4. broker.py:170-171           `u.fragment` on an https provider URL
 5. broker.py:170-171           `u.query` / `u.fragment` on the provider_proxy path
 6. broker.py:177-179           IPv6 proxy literals: `[::1]` is an exact loopback endpoint,
                                `[::2]` and `[fc00::1]` are not, and a proxy is never resolved
 7. broker.py:182-183           the shipped resolver (`resolve=None`) has never run:
                                getaddrinfo(name, port or 443, type=SOCK_STREAM), a[4][0]
 8. broker.py:198               every answer must be global, not only the first one
 9. broker.py:196               answers deduped and ordered - the connection takes addrs[0]
10. broker.py:155-157           `pipe_name` holds exactly Core's four values
11. broker.py:172-181 via `issue`  a refused destination leaves the live grant of the same
                                execution and the transport untouched

Fakes only: DNS, the native pipe, the upstream connection and the response are the seam
fakes `tests/v1/unit/test_provider_broker.py` and `tests/v1/unit/test_broker_gaps.py`
already use (copied, not imported, so this file stands on its own). No network, no native
operation, no DLL, no real process, no sleep, no assertion about threads or OS error text.
"""

import io
import ipaddress
import socket

import pytest

from archeus.core.domain import ids
from archeus.node import broker as B

MODEL = 'claude-x'
UPSTREAM_KEY = 'sk-ant-api03-UPSTREAM-SECRET'
BODY = b'{"model":"claude-x","messages":[{"role":"user","content":"hi"}]}'
PUBLIC = '93.184.216.34'


# ── the fakes of test_provider_broker.py / test_broker_gaps.py ──

class Transport:
    """The fake native transport: records every privileged call it is asked for."""

    def __init__(self):
        self.created, self.launched, self.closed = [], [], []

    def create(self, name, principal):
        self.created.append((name, principal))
        return 'ep%d' % len(self.created)

    def cancel(self):
        pass

    def launch_bridge(self, endpoint, binding):
        self.launched.append(endpoint)
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


def resolver(*answer):
    """A fake DNS seam that records every lookup it is asked to make."""

    seen = []

    def look(host, port):
        seen.append((host, port))
        return list(answer) or [PUBLIC]

    look.seen = seen
    return look


def binding(**kw):
    kw = dict(dict(core_instance='core1', execution_id=ids.new_id('execution'), process_seq=1,
                   principal='archeus.x', route_decision_id='rte_1', account_id='acc_1',
                   harness_id='claude_code', model=MODEL,
                   upstream=B.Upstream('https://api.example.com'),
                   limits=B.BrokerLimits(max_requests=3)), **kw)
    return B.BrokerBinding(**kw)


def broker(send=None, transport=None, resolve=None, **kw):
    calls = []

    def default_send(up, addrs, method, path, headers, body, timeout):
        calls.append((up, addrs, method, path, dict(headers), body))
        return Resp(headers=[('content-type', 'application/json'), ('request-id', 'r1')])

    b = B.Broker(core_instance='core1',
                 live=lambda bd, d: True,
                 credentials=lambda bd: {'x-api-key': UPSTREAM_KEY},
                 upstream_of=lambda a: B.Upstream('https://api.example.com'),
                 transport=transport or Transport(),
                 resolve=resolve or resolver(PUBLIC),
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
    token, d, _endpoint, _port = b.issue(bd)
    return bd, token, d


def nothing_happened(t, b, calls):
    """No pipe, no launch, no close, no grant, no upstream request: a refusal that issued."""
    return (t.created, t.launched, t.closed, dict(b._grants), calls) == ([], [], [], {}, [])


# ── 1-2. the two refusals the source does not (yet) make: reported, kept strict ──

@pytest.mark.xfail(strict=True, reason='broker.py:278 keeps `limits or BrokerLimits()` but '
                                       'broker.py:290-301 validates only binding.limits: '
                                       'Broker.limits is never read anywhere in archeus/, so a '
                                       'broker composed without Core policy issues a grant even '
                                       'though the Broker docstring (broker.py:270-271) promises '
                                       '"a broker made without one issues nothing"')
def test_a_broker_composed_without_cores_policy_issues_nothing():
    t = Transport()
    b, calls = broker(transport=t, limits=None)
    assert b.limits.max_requests is None                 # the ceiling-less default
    with pytest.raises(B.Refused) as raised:
        b.issue(binding())                                # the binding does carry a ceiling
    assert raised.value.status == 403
    assert t.created == [] and t.launched == [] and b._grants == {} and calls == []


@pytest.mark.parametrize('url', ['http://[::1:8080', 'https://[::1:8080'],
                         ids=['proxy-bracket', 'https-bracket'])
def test_a_url_the_parser_itself_cannot_read_is_a_denial_that_creates_nothing(url):
    look = resolver(PUBLIC)
    with pytest.raises(B.Refused) as raised:
        B.check_destination(B.Upstream(url, 'provider_proxy'), look)
    assert raised.value.status == 403 and look.seen == []
    t = Transport()
    b, calls = broker(transport=t)
    with pytest.raises(B.Refused) as raised:
        b.issue(binding(upstream=B.Upstream(url, 'provider_proxy')))
    assert raised.value.status == 403 and nothing_happened(t, b, calls)


# ── 3-5. the plain-host check: the sub-conditions no existing case switches on ──

@pytest.mark.parametrize('url,kind', [
    ('https:///v1/messages', 'https'),
    ('api.example.com', 'https'),
    ('http://:8080', 'provider_proxy'),
], ids=['absent-authority', 'no-scheme-at-all', 'proxy-without-a-host'])
def test_a_url_that_names_no_host_ever_is_refused_before_a_lookup(url, kind):
    look = resolver(PUBLIC)
    with pytest.raises(B.Refused) as raised:
        B.check_destination(B.Upstream(url, kind), look)
    # with `not u.hostname` gone the resolver would answer these with a public address
    assert raised.value.status == 403 and look.seen == []
    t = Transport()
    b, calls = broker(transport=t)
    with pytest.raises(B.Refused) as raised:
        b.issue(binding(upstream=B.Upstream(url, kind)))
    assert raised.value.status == 403 and nothing_happened(t, b, calls)


def test_a_fragment_on_the_provider_url_is_refused_though_the_same_url_without_it_is_one():
    look = resolver(PUBLIC)
    assert B.check_destination(B.Upstream('https://api.example.com'), look) == [PUBLIC]
    assert look.seen == [('api.example.com', 443)]         # the name and the default port only
    for url in ('https://api.example.com#afterthought',
                'https://api.example.com:8443/v1#afterthought'):
        with pytest.raises(B.Refused) as raised:
            B.check_destination(B.Upstream(url), resolver(PUBLIC))
        assert raised.value.status == 403                  # only u.fragment tells these apart


def test_a_query_or_a_fragment_on_the_proxy_endpoint_is_refused_though_the_same_is_accepted():
    # the plain-host check sits above the kind branches: dropping it into the https arm would
    # make every existing case pass while a proxy grew a query string
    assert B.check_destination(B.Upstream('http://127.0.0.1:8080', 'provider_proxy')) == [
        '127.0.0.1']
    for url in ('http://127.0.0.1:8080?next=elsewhere', 'http://127.0.0.1:8080#afterthought'):
        with pytest.raises(B.Refused) as raised:
            B.check_destination(B.Upstream(url, 'provider_proxy'))
        assert raised.value.status == 403
    t = Transport()
    b, calls = broker(transport=t)
    with pytest.raises(B.Refused) as raised:
        b.issue(binding(upstream=B.Upstream('http://127.0.0.1:8080?next=elsewhere',
                                            'provider_proxy')))
    assert raised.value.status == 403 and nothing_happened(t, b, calls)


# ── 6. the proxy boundary in IPv6, where every existing case is IPv4 ──

def test_an_ipv6_proxy_is_only_the_exact_loopback_endpoint_and_is_never_resolved():
    look = resolver('8.8.8.8')
    good = B.check_destination(B.Upstream('http://[::1]:8080', 'provider_proxy'), look)
    assert good == ['::1'] and look.seen == []              # named, so never looked up
    for url in ('http://[::2]:8080', 'http://[fc00::1]:8080'):
        with pytest.raises(B.Refused) as raised:
            B.check_destination(B.Upstream(url, 'provider_proxy'), look)
        assert raised.value.status == 403
    assert look.seen == []                                  # no refusal asked the resolver
    t = Transport()
    b, calls = broker(transport=t)
    with pytest.raises(B.Refused):
        b.issue(binding(upstream=B.Upstream('http://[fc00::1]:8080', 'provider_proxy')))
    assert nothing_happened(t, b, calls)


# ── 7. the resolver the broker ships with, which no test has ever run ──

def test_the_shipped_resolver_is_asked_for_stream_addresses_of_the_name_and_port_only(
        monkeypatch):
    seen = []

    def fake_getaddrinfo(host, port, **kw):
        seen.append((host, port, kw))
        return [(2, 1, 6, '', (PUBLIC, port)), (2, 1, 6, '', ('8.8.4.4', port))]

    monkeypatch.setattr(B.socket, 'getaddrinfo', fake_getaddrinfo)
    assert B.check_destination(B.Upstream('https://api.example.com:8443')) == [
        '8.8.4.4', PUBLIC]
    assert seen == [('api.example.com', 8443, {'type': socket.SOCK_STREAM})]
    B.check_destination(B.Upstream('https://api.example.com'))
    assert seen[1] == ('api.example.com', 443, {'type': socket.SOCK_STREAM})
    # a credential in the URL never reaches the resolver: it is refused first
    with pytest.raises(B.Refused):
        B.check_destination(B.Upstream('https://user:pw@api.example.com'))
    assert len(seen) == 2
    # and the shipped resolver is no bypass: a loopback answer closes the route
    monkeypatch.setattr(B.socket, 'getaddrinfo',
                        lambda host, port, **kw: [(2, 1, 6, '', ('127.0.0.1', port))])
    with pytest.raises(B.Refused) as raised:
        B.check_destination(B.Upstream('https://api.example.com'))
    assert raised.value.status == 403


# ── 8-9. the answer set: every address must be public, and the order is load-bearing ──

@pytest.mark.parametrize('addrs', [
    ['1.1.1.1', '10.0.0.5'],
    ['2001:4860::8888', 'fc00::1'],
], ids=['v4-private-second', 'v6-private-second'])
def test_every_address_the_name_has_is_public_after_the_sort_not_only_the_first(addrs):
    # the sort puts the public answer FIRST here, so a check that looked only at addrs[0]
    # (which is the address send_upstream dials) accepts these and every existing test passes
    assert ipaddress.ip_address(sorted(set(addrs))[0]).is_global
    t = Transport()
    b, calls = broker(transport=t, resolve=resolver(*addrs))
    with pytest.raises(B.Refused) as raised:
        b.issue(binding())
    assert raised.value.status == 403 and nothing_happened(t, b, calls)


def test_the_addresses_a_name_has_are_deduped_and_in_one_deterministic_order():
    assert B.check_destination(B.Upstream('https://api.example.com'),
                               resolver(PUBLIC, '8.8.8.8', PUBLIC)) == ['8.8.8.8', PUBLIC]
    # the order is not cosmetic: the broker hands the account key to a connection at addrs[0]
    t = Transport()
    b, calls = broker(transport=t, resolve=resolver(PUBLIC, '8.8.8.8', PUBLIC))
    _bd, token, _d = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 200 and out.startswith(b'HTTP/1.1 200')
    assert calls[0][1] == ['8.8.8.8', PUBLIC]
    assert calls[0][4]['x-api-key'] == UPSTREAM_KEY


# ── 10. the pipe name: Core's values and nothing the execution can choose ──

def test_the_pipe_name_holds_exactly_cores_four_values_and_none_of_the_executions_own():
    bd = binding(execution_id='exe_7', process_seq=3, model='claude-secret-model',
                 account_id='acc_secret', harness_id='harness_secret',
                 route_decision_id='rte_secret')
    name = B.pipe_name(bd, 'aabbccdd')
    assert name == 'archeus.pv20.broker.core1.exe_7.3.aabbccdd'
    for own in (bd.principal, bd.model, bd.account_id, bd.harness_id, bd.route_decision_id):
        assert own not in name
    assert B.pipe_name(bd, '11223344') != name               # the nonce is the only variation


# ── 11. a refused destination must not destroy the grant that is keeping the CLI alive ──

def test_a_refused_destination_leaves_the_live_grant_of_that_execution_running_and_untouched():
    t = Transport()
    b, calls = broker(transport=t)
    bd, token, d = issued(b)
    before = (list(t.created), list(t.launched), list(t.closed))
    with pytest.raises(B.Refused) as raised:                  # same generation, bad provider
        b.issue(binding(execution_id=bd.execution_id, process_seq=2,
                        upstream=B.Upstream('http://10.1.2.3:8080', 'provider_proxy')))
    assert raised.value.status == 403
    assert (list(t.created), list(t.launched), list(t.closed)) == before   # no new pipe, no close
    assert d in b._grants and b.reach(bd.execution_id) is not None
    out, row = serve(b, request(token=token))                 # and the live grant still serves
    assert row['status'] == 200 and out.startswith(b'HTTP/1.1 200')
    assert calls and calls[-1][1] == [PUBLIC]
