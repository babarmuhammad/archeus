"""T-1006: the ten highest-risk uncovered branches of archeus/node/broker.py lines
301-600 (inclusive), fail-closed and denial first, then boundaries, then error paths.

The branch ownership here stays inside that slice: the request-time destination recheck
and every reply-scrubbing / stream / error-body / refusal branch it reaches. The ten
selected branches, each cited as source file:line in the matching test below:

 1. broker.py:460  _forward rechecks check_destination per request (a destination that
    turns non-public after issue is a 403 before credentials are read or anything sent).
 2. broker.py:497  the >=400 error-body loop breaks on `d not in self._grants`: a grant
    revoked mid error-body read has its body suppressed whole (Content-Length: 0).
 3. broker.py:500  the >=400 error-body loop through the `resp.read(65536)` fallback
    (a response object with no read1): relayed clean whole, or suppressed for the key.
 4. broker.py:575  _leaks on a str that is not latin-1 encodable (replace): a leaking
    non-latin-1 response header is dropped, never a 500.
 5. broker.py:485  resp.reason is None: the status line is relayed with an empty reason,
    nothing is invented for it.
 6. broker.py:496  an OSError raised while reading the >=400 error body: one local 500,
    never a half-relayed upstream status line followed by a second reply.
 7. broker.py:393  the pipe client goes away mid-stream (write raises OSError after the
    head was relayed): no second response, no crash, the slot and counter are freed.
 8. broker.py:590  a request body that is not decodable: UnicodeDecodeError is a local
    400 (the JSON-mandatory fail-closed path), never a 500.
 9. broker.py:531  the 200-stream sliding window with a chunk that is entirely a proper
    prefix of a key form: held (no write), then flushed byte-for-byte, grant intact.
10. broker.py:520  the 200-stream loop through the `resp.read(65536)` fallback: relayed
    whole and in order from a response object that only has read.

Replaced probes (already covered, evidence in the T-1006 report): terms withdrawn and
unhealthy account (test_broker_execution.py broker_live tests plus the 'dead' case of
test_provider_broker.py), wrong endpoint at authorize (test_broker_listener.py
test_a_token_answers_only_at_the_listener_it_was_issued_at), revocation replay
(test_provider_broker.py 'unknown' case, test_broker_listener.py revoked-token test),
secret redirect (test_provider_broker.py redirect test asserts the Location never
relayed), byte cap and request cap (test_the_response_cap_ends_the_stream, the
ERROR_BODY_MAX test, the ceiling tests), upstream error and scrub failure in their
covered shapes (the OSError / HTTPException 502 tests, the key-in-reason/headers/
error-body/stream tests): each is replaced above by a genuinely uncovered branch of the
same risk family.

Same in-process fakes as test_provider_broker.py / test_broker_gaps.py: a fake transport,
a fake upstream response, an in-memory request; no native operation, no network, no real
process, no real DLL, nothing OS-level beyond those seams. Self-contained on purpose:
this file imports nothing from any other test_gaps2 file and depends on no queue order.
"""

import io

import pytest

from archeus.core.domain import ids
from archeus.node import broker as B

MODEL = 'claude-x'
UPSTREAM_KEY = 'sk-ant-api03-UPSTREAM-SECRET'
BODY = b'{"model":"claude-x","messages":[{"role":"user","content":"hi"}]}'


class Transport:
    def __init__(self, fail_launch=False):
        self.created, self.closed, self.fail_launch = [], [], fail_launch

    def create(self, name, principal):
        self.created.append((name, principal))
        return 'ep%d' % len(self.created)

    def cancel(self):
        pass

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


class PlainResp:
    """An upstream response object with `read` only: no streaming read1 anywhere, so the
    broker must reach the bytes through the read(65536) fallback of both loops."""

    def __init__(self, status=200, headers=(), chunks=(b'ok',), reason='OK'):
        self.status, self.reason, self._h, self._c = status, reason, list(headers), list(chunks)
        self.reads = 0

    def getheaders(self):
        return self._h

    def read(self, n):
        self.reads += 1
        return self._c.pop(0)[:n] if self._c else b''


def binding(**kw):
    kw = dict(dict(core_instance='core1', execution_id=ids.new_id('execution'), process_seq=1,
                   principal='archeus.x', route_decision_id='rte_1', account_id='acc_1',
                   harness_id='claude_code', model=MODEL,
                   upstream=B.Upstream('https://api.example.com'),
                   limits=B.BrokerLimits(max_requests=3)), **kw)
    return B.BrokerBinding(**kw)


def broker(live=True, send=None, transport=None, resolve=None, credentials=None, **kw):
    calls = []

    def default_send(up, addrs, method, path, headers, body, timeout):
        return Resp(headers=[('content-type', 'application/json'), ('request-id', 'r1')])

    def recording(up, addrs, method, path, headers, body, timeout):
        calls.append((up, addrs, method, path, dict(headers), body))
        return (send or default_send)(up, addrs, method, path, headers, body, timeout)
    kw.setdefault('limits', B.BrokerLimits(max_requests=3))
    b = B.Broker(core_instance='core1',
                 live=live if callable(live) else (lambda bd, d: live),
                 credentials=credentials or (lambda bd: {'x-api-key': UPSTREAM_KEY}),
                 upstream_of=lambda a: B.Upstream('https://api.example.com'),
                 transport=transport or Transport(),
                 resolve=resolve or (lambda host, port: ['93.184.216.34']),
                 send=recording, **kw)
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


def _body(out):
    return out.split(b'\r\n\r\n', 1)[1]


# ── 1. fail closed first: the destination is rechecked when the request is sent ──
# branch: broker.py:460 `addrs = check_destination(b.upstream, self._resolve)` raising.
# Closest existing test: test_broker_gaps.py
# test_a_resolver_that_fails_or_names_nothing_issues_nothing - it only ever fails the
# resolver at issue, and test_an_upstream_failure_is_never_retried fails *send*, not the
# recheck; neither can see a 403 that happens between them, before credentials and send.

def test_a_destination_that_leaks_after_issue_is_refused_before_credentials_or_send():
    public = [True]

    def resolve(host, port):
        return ['93.184.216.34'] if public[0] else ['169.254.169.254']
    creds = []

    def credentials(bd):
        creds.append(bd)
        return {'x-api-key': UPSTREAM_KEY}
    b, calls = broker(resolve=resolve, credentials=credentials)
    bd, token, d = issued(b)
    public[0] = False                                    # the pinned name re-resolves elsewhere
    out, row = serve(b, request(token=token))
    assert row['status'] == 403 and out.startswith(b'HTTP/1.1 403')
    assert creds == [] and calls == []                   # nothing read, nothing sent
    assert UPSTREAM_KEY.encode() not in out and b'169.254' not in out
    assert b._in_flight == 0 and b._grants[d]['active'] == 0 and b._grants[d]['requests'] == 1


# ── 2. a grant revoked mid error-body read keeps its body whole or hidden ──
# branch: broker.py:497 `d not in self._grants` breaking the >=400 loop.
# Closest: test_fix_node_broker.py::test_a_revoked_grant_stops_relaying_a_stream_even_
# while_core_still_calls_it_live cuts a 200 stream; the trickle test in
# test_provider_broker.py breaks that same loop with *live* turning False, never with a
# revoke - so removing the d-check would pass both.

def test_a_grant_revoked_mid_error_body_read_has_its_body_suppressed_whole():
    box = {}

    class Revoking(Resp):
        def read1(self, n):
            if len(self._c) == 3:                        # on the first read only
                box['b'].revoke(box['bd'].execution_id)  # the grant ends mid body
            return super().read1(n)
    b, calls = broker(live=lambda bd, d: True,           # live never says no: only the d-check can end it
                      send=lambda *a: Revoking(status=529,
                                               chunks=[b'internal server trouble', b' more', b' tail']))
    box['b'], box['bd'] = b, None
    bd, token, d = issued(b)
    box['bd'] = bd
    out, row = serve(b, request(token=token))
    assert row['status'] == 529 and row['bytes_out'] == 0
    assert b'Content-Length: 0' in out and out.endswith(b'\r\n\r\n')
    assert b'internal server trouble' not in out         # not one body byte relayed
    assert d not in b._grants and b._in_flight == 0
    assert len(calls) == 1 and calls[0][1] == ['93.184.216.34']


# ── 3. the error body through the read(65536) fallback: whole or nothing ──
# branch: broker.py:500 `resp.read(65536)` (no read1 on the response).
# Closest: test_an_upstream_error_body_is_relayed_without_the_key_or_not_at_all uses the
# read1 fake only; drop the fallback and every Resp there still works.

def test_an_error_body_from_a_response_without_read1_is_relayed_clean_or_suppressed():
    text = b'overloaded ' + b'for you'
    b, calls = broker(send=lambda *a: PlainResp(status=529, chunks=[b'overloaded ', b'for you']))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 529 and row['bytes_out'] == len(text)
    assert out.endswith(text) and b'Content-Length: %d' % len(text) in out
    assert calls and 'x-api-key' in calls[0][4]

    b, calls = broker(send=lambda *a: PlainResp(
        status=529, chunks=[b'bad ', b'echo: ' + UPSTREAM_KEY.encode(), b' end']))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 529 and row['bytes_out'] == 0
    assert UPSTREAM_KEY.encode() not in out and b'Content-Length: 0' in out
    assert out.endswith(b'\r\n\r\n') and b'echo' not in _body(out)


# ── 4. scrub failure: a leaking header that is not latin-1 cannot become a 500 ──
# branch: broker.py:575 `data.encode('latin-1', 'replace')` on a str beyond latin-1.
# Closest: test_a_key_echoed_in_an_error_body_or_header_is_never_relayed echoes pure
# latin-1 text; without the 'replace' handler every one of those still passes while a
# non-latin-1 value would raise UnicodeEncodeError out of the scrub and 500 the request.

def test_a_leaking_response_header_that_is_not_latin_1_is_dropped_not_a_server_error():
    b, calls = broker(send=lambda *a: Resp(
        headers=[('X-Echo', '\u2713 caf\u00e9 \u5bc2\u3068 ' + UPSTREAM_KEY),
                 ('request-id', 'r9')]))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 200 and out.startswith(b'HTTP/1.1 200')
    head = out.split(b'\r\n\r\n')[0]
    assert b'X-Echo' not in head and UPSTREAM_KEY.encode() not in out
    assert b'request-id: r9' in head and out.endswith(b'ok') and calls


# ── 5. a status line without a reason: relayed empty, never invented ──
# boundary: broker.py:485 `reason = resp.reason or ''` with resp.reason None.
# Closest: the reason-scrub tests set reason to a *string* (with the key or a control
# character) and assert the empty result of scrubbing; none has reason absent, so an
# unguarded `resp.reason` (TypeError -> 500) or an invented default passes them all.

def test_a_status_line_with_no_reason_is_relayed_empty_never_filled_in():
    b, calls = broker(send=lambda *a: Resp(chunks=[b'ok'], reason=None))
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 200 and out.startswith(b'HTTP/1.1 200 \r\n')
    assert b'Internal' not in out and out.endswith(b'ok') and len(calls) == 1


# ── 6. an error body whose read dies: one local 500, never a half reply ──
# branch: broker.py:496 loop raising OSError from resp.read1 while the head is still
# unwritten. Closest: test_an_upstream_failure_is_never_retried fails *send* (nothing
# was being read) and the Stalls test fails a 200 stream after its head went out;
# neither pins that a >=400 status line never reaches the client when its body died.

def test_an_error_body_that_dies_mid_read_becomes_one_local_500():
    class Dies(Resp):
        def read1(self, n):
            raise OSError('the upstream stalled')
    b, calls = broker(send=lambda *a: Dies(status=529, chunks=[b'never read']))
    _, token, d = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 500 and row['bytes_out'] == 0
    assert out.count(b'HTTP/1.1') == 1 and out.startswith(b'HTTP/1.1 500 Internal Error')
    assert b'529' not in out and b'never read' not in out and len(calls) == 1
    assert b._in_flight == 0 and b._grants[d]['active'] == 0


# ── 7. the client goes away mid-stream: no second response, no crash, slot freed ──
# branch: broker.py:393 put() raising OSError from the stream writes with written
# non-empty (the `if not written:` guard at 443 must then stay silent).
# Closest: test_an_error_after_the_response_began_does_not_start_a_second_one fails the
# *read* side, and test_broker_gaps.py client-gone only covers the _reply of a 401; no
# test fails a write mid _forward, so an inverted written-guard passes them all.

def test_a_client_that_goes_away_mid_stream_gets_no_second_response_and_frees_its_slot():
    b, calls = broker(send=lambda *a: Resp(chunks=[b'x' * 200, b'y' * 200, b'z' * 200]))
    _, token, d = issued(b)
    pieces, attempts = [], []

    def gone_write(data):
        attempts.append(data)                          # what the broker still tries to write
        if pieces:
            raise OSError('client gone')                # the head went out; now the pipe is dead
        pieces.append(data)
    row = b.serve(request(token=token), gone_write, 'archeus.x')   # must not raise
    assert row['status'] == 500 and row['bytes_out'] == 0
    assert len(pieces) == 1 and pieces[0].startswith(b'HTTP/1.1 200')
    assert len(attempts) == 2                          # the head, then the one write that died
    assert b'500' not in attempts[-1]                  # no second response is even attempted
    assert pieces[0].count(b'HTTP/1.1') == 1 and b'Internal Error' not in pieces[0]
    assert b._in_flight == 0 and b._grants[d]['active'] == 0 and b._grants[d]['requests'] == 1
    assert len(calls) == 1                               # never retried on the dead pipe


# ── 8. a body that cannot be decoded is a refusal, never a 500 ──
# branch: broker.py:590 UnicodeDecodeError in _model_of -> Refused(400).
# Closest: test_the_body_must_name_exactly_the_pinned_model feeds 'not json' (valid
# UTF-8 -> ValueError) and the deep-nesting test only exercises RecursionError; drop
# UnicodeDecodeError from the except and every one of those still passes while an
# undecodable body escapes to the generic 500 handler.

@pytest.mark.parametrize('body', [b'\xff\xfe{"model":"claude-x"}',
                                 b'{"model":"claude-\x80\x81"}'])
def test_a_body_that_is_not_decodable_is_a_local_400_never_a_500(body):
    b, calls = broker()
    _, token, _ = issued(b)
    out, row = serve(b, request(token=token, body=body))
    assert row['status'] == 400 and out.startswith(b'HTTP/1.1 400')
    assert b'500' not in out and calls == []


# ── 9. the sliding window holds a pure key prefix, then flushes it byte for byte ──
# branch: broker.py:531 `if cut:` taking the cut == 0 side (a whole chunk that is a
# proper prefix of a key form is held without any write) and the later flush of it.
# Closest: the split-across-chunks tests always prepend 'ok ' to the first chunk, so
# cut > 0 every time; inverting `if cut:` still passes them (their body may be empty),
# but here the exact bytes and their grouping are pinned.

def test_a_chunk_that_is_entirely_a_key_prefix_is_held_then_flushed_byte_for_byte():
    prefix = UPSTREAM_KEY[:12].encode()                  # 'sk-ant-api03': a proper prefix
    chunks = [prefix, b'x' * 40, b'done.']
    assert prefix != UPSTREAM_KEY.encode() and prefix in UPSTREAM_KEY.lower().encode()
    b, calls = broker(send=lambda *a: Resp(chunks=list(chunks)))
    _, token, d = issued(b)
    pieces = []
    row = b.serve(request(token=token), pieces.append, 'archeus.x')
    assert row['status'] == 200
    assert _body(b''.join(pieces)) == prefix + b'x' * 40 + b'done.'
    assert pieces[1] == prefix + b'x' * 40               # held, then written in one piece
    assert pieces[-1] == b'done.' and d in b._grants    # holding is not a leak: no revoke
    assert serve(b, request(token=token))[1]['status'] == 200


# ── 10. the 200 stream through the read(65536) fallback ──
# branch: broker.py:520 `resp.read(65536)` (the response has no read1).
# Closest: every stream test in test_provider_broker.py uses the read1 fake; remove
# the fallback and only AttributeError-to-500 paths like these would show it, which no
# existing test can produce.

def test_a_clean_stream_from_a_response_without_read1_is_relayed_whole_and_in_order():
    chunks = [b'alpha', b'beta beta', b'gamma']
    b, calls = broker(send=lambda *a: PlainResp(chunks=list(chunks)))
    _, token, d = issued(b)
    out, row = serve(b, request(token=token))
    assert row['status'] == 200 and row['bytes_out'] == sum(len(c) for c in chunks)
    assert _body(out) == b''.join(chunks)                # nothing lost, nothing doubled
    assert out.split(b'\r\n\r\n', 1)[0].startswith(b'HTTP/1.1 200')
    assert d in b._grants and b._in_flight == 0 and len(calls) == 1
