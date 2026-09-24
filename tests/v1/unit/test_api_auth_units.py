"""The auth primitives on their own (p3.5b design gate D2, D7, §4)."""

import threading

from archeus.api import auth


def test_a_token_is_dev_plus_256_random_bits_and_only_its_hash_is_kept():
    t = auth.new_token()
    assert t.startswith('dev_') and len(t) == 4 + 43
    assert auth.token_hash(t) != t and len(auth.token_hash(t)) == 64
    assert auth.new_token() != t


def test_bearer_accepts_only_a_device_token():
    t = auth.new_token()
    assert auth.bearer('Bearer ' + t) == t
    assert auth.bearer('bearer  ' + t) == t
    for bad in (None, '', 'Bearer', 'Bearer x', 'Basic ' + t, 'Bearer hook_abc',
                'Bearer exe_01J0000000000000000000000Z', t):
        assert auth.bearer(bad) is None, bad


def _cred(**over):
    t = auth.new_token()
    c = dict(token_hash=auth.token_hash(t), principal_id='prn_x', device_id='dvc_x',
             device_state='ACTIVE', scopes=('observe',), expires_at=None, revoked_at=None)
    c.update(over)
    return c, auth.token_hash(t)


def test_a_credential_is_live_only_when_active_unrevoked_and_unexpired():
    c, h = _cred()
    assert auth.live(c, h)
    assert not auth.live(None, h)
    assert not auth.live(c, auth.token_hash('dev_other'))
    for over in ({'revoked_at': '2026-01-01T00:00:00.000Z'}, {'device_state': 'REVOKED'},
                 {'device_state': 'PAIRING'}, {'expires_at': '2001-01-01T00:00:00.000Z'}):
        c, h = _cred(**over)
        assert not auth.live(c, h), over
    c, h = _cred(expires_at='2999-01-01T00:00:00.000Z')
    assert auth.live(c, h)


def test_one_origin_exactly():
    o = auth.Origin(7337)
    assert o.host_ok('127.0.0.1:7337')
    for host in ('localhost:7337', '127.0.0.1', '127.0.0.1:7338', '[::1]:7337', None, '',
                 '127.0.0.1:7337.evil.example'):
        assert not o.host_ok(host), host
    assert o.fetch_ok({})
    assert o.fetch_ok({'Sec-Fetch-Site': 'same-origin', 'Origin': 'http://127.0.0.1:7337'})
    assert o.fetch_ok({'Sec-Fetch-Site': 'none'})
    for h in ({'Sec-Fetch-Site': 'cross-site'}, {'Sec-Fetch-Site': 'same-site'},
              {'Origin': 'http://localhost:7337'}, {'Origin': 'null'},
              {'Origin': 'https://127.0.0.1:7337'}):
        assert not o.fetch_ok(h), h


def test_launch_codes_are_single_use_and_expire_on_the_injected_clock():
    now = [100.0]
    codes = auth.LaunchCodes(clock=lambda: now[0])
    a = codes.mint('prn_a', 'dvc_a')
    assert codes.redeem(a) == ('prn_a', 'dvc_a')
    assert codes.redeem(a) is None                          # the pop is the use
    b = codes.mint('prn_a', 'dvc_a')
    now[0] += 60.01
    assert codes.redeem(b) is None
    c = codes.mint('prn_a', 'dvc_a')
    now[0] += 59.99
    assert codes.redeem(c) == ('prn_a', 'dvc_a')
    for bad in (None, '', 5, 'x' * 43):
        assert codes.redeem(bad) is None
    assert len(codes) == 0
    assert c not in repr(codes.__dict__)                    # only hashes are held


def test_of_many_concurrent_redemptions_exactly_one_wins():
    codes = auth.LaunchCodes()
    code = codes.mint('prn_a', 'dvc_a')
    out, gate = [], threading.Barrier(16)

    def go():
        gate.wait()
        out.append(codes.redeem(code))
    threads = [threading.Thread(target=go) for _ in range(16)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(x is not None for x in out) == 1


def test_the_security_headers_are_the_documented_four():
    h = auth.security_headers()
    assert h == {'Content-Security-Policy': "default-src 'self'; script-src 'self'; "
                 "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
                 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
                 'Cache-Control': 'no-store'}
