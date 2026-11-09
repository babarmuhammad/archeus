"""T-724: the highest-risk branches of `archeus/api/auth.py` that no existing
test reached, driven through fakes only — no server, no OS call, no network, no
sleep. Fail-closed and denial paths first (loopback peer, expiry, malformed
redeemables, foreign token kinds), then the breaker and counter edges, then
the error paths (remote_host's refusal, iso's shape, the cache override).

The closest existing file is `test_api_auth_units.py`; its style (module-level
`from archeus.api import auth`, a `_cred`-style local builder, an injected
`Clock` like `test_presence_units.py` uses) is copied here. Nothing is edited
in `archeus/`."""

from datetime import datetime, timezone

import pytest

from archeus.api import auth


class Clock:
    """The same injected clock seam `test_presence_units.py` uses."""

    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def _cred(**over):
    """A `queries.credential` row like the one in `test_api_auth_units.py`."""
    t = auth.new_token()
    c = dict(token_hash=auth.token_hash(t), principal_id='prn_x', device_id='dvc_x',
             device_state='ACTIVE', scopes=('observe',), expires_at=None, revoked_at=None)
    c.update(over)
    return c, auth.token_hash(t)


# ── loopback peer: the gate in front of minting and redemption (routes.py:106) ──

@pytest.mark.parametrize('peer', [('10.0.0.1', 5), ('192.168.1.1', 7337), ('::2', 1),
                                  ('fe80::1', 1), ('0.0.0.0', 1), ('localhost', 7337),
                                  ('127000001', 0), ('', 0), (None, 0)])
def test_a_non_loopback_peer_is_never_taken_as_local(peer):
    """auth.py:151 `return host == '127.0.0.1' or host == '::1' or
    str(host).startswith('127.')` negated (or any disjunct widened) makes an
    off-machine peer local, and routes.py:106 then lets it mint and redeem
    codes. Every one of these must be refused."""
    assert auth.loopback_peer(peer) is False


@pytest.mark.parametrize('peer', [('127.0.0.1', 5), ('127.0.0.1', 0), ('127.5.5.5', 9),
                                  ('127.255.255.254', 1), ('::1', 443)])
def test_the_whole_loopback_substance_and_the_v6_loopback_are_local(peer):
    """auth.py:151, dropping any disjunct: without `== '127.0.0.1'` the plain
    v4 answer dies, without `== '::1'` the v6 loopback is refused, and without
    `startswith('127.')` the rest of 127/8 (a real loopback net) is refused;
    each refusal locks the user's own CLI out of the authority routes."""
    assert auth.loopback_peer(peer) is True


def test_a_plain_string_address_is_judged_like_the_host_of_a_tuple():
    """auth.py:150 `host = address[0] if isinstance(address, tuple) else address`:
    remove the else branch and a bare string peer raises TypeError instead of
    answering; invert the isinstance and `('10.0.0.1', 5)[0]` vs '10.0.0.1'
    swap answers. The CLI hands both shapes (routes.py:106 passes req.peer)."""
    assert auth.loopback_peer('127.0.0.1') is True            # tuple branch says True too
    assert auth.loopback_peer('::1') is True
    assert auth.loopback_peer('10.0.0.1') is False


# ── live(): expiry is decided by the hash match and by `now`, fail-closed ──

def test_a_credential_is_dead_at_the_very_instant_it_expires():
    """auth.py:84 `cred['expires_at'] > (now or now_iso())` flipped to `>=`:
    a credential whose expires_at equals the moment of checking would still
    authenticate. At the boundary the credential must already be refused."""
    c, h = _cred(expires_at='2030-01-01T00:00:00.000Z')
    assert auth.live(c, h, now='2029-12-31T23:59:59.999Z')          # one ms before: alive
    assert not auth.live(c, h, now='2030-01-01T00:00:00.000Z')      # exactly at: dead
    assert not auth.live(c, h, now='2030-01-01T00:00:00.001Z')      # and after


def test_the_injected_now_decides_expiry_not_the_wall_clock():
    """auth.py:84 `(now or now_iso())` reduced to `now_iso()` (or `or` flipped):
    the caller's *now* is ignored, so a caller checking 'was this alive at the
    request stamp' gets a live answer from the wall clock instead. The injected
    now is 2031, long past expiry, while the wall clock is not."""
    c, h = _cred(expires_at='2030-01-01T00:00:00.000Z')
    assert auth.live(c, h)                                          # control: alive today
    assert not auth.live(c, h, now='2031-01-01T00:00:00.000Z')      # dead at the given now


# ── LaunchCodes: memory hygiene, frozen grants, hostile redeemables ──

def test_expired_launch_codes_are_swept_when_a_new_one_is_minted():
    """auth.py:169 `self._codes = {h: v for h, v in self._codes.items() if
    v[0] > now}` removed: expired codes sit in the table forever, so a minting
    loop grows memory without bound and `len(codes)` lies about what is live."""
    c = Clock()
    codes = auth.LaunchCodes(clock=c)
    a = codes.mint('prn_a', 'dvc_a')
    assert codes.redeem(a) is not None
    b = codes.mint('prn_a', 'dvc_a')                                # live until 160
    c.now = 160.1
    codes.mint('prn_a', 'dvc_b')                                     # the sweep runs here
    assert len(codes) == 1                                           # b is gone, not parked
    with codes._lock:
        assert list(codes._codes.values())[0][1][1] == 'dvc_b'       # only the new one is kept


def test_a_launch_grant_is_frozen_at_mint_scopes_and_supersede():
    """auth.py:187 `(principal_id, device_id, tuple(scopes), supersede)`:
    without `tuple(...)` the caller's list is stored by reference, so a minter
    (or a bug in the caller) widens the grant after the code left; without the
    stored *supersede* the redeem would revoke the wrong slot (p20 D1)."""
    codes = auth.LaunchCodes(clock=Clock())
    scopes = ['observe', 'control']
    code = codes.mint('prn_a', 'dvc_a', scopes=scopes, supersede='slot-a')
    scopes.append('admin')                                           # tamper after minting
    got = codes.redeem(code)
    assert got == ('prn_a', 'dvc_a', ('observe', 'control'), 'slot-a')
    assert isinstance(got[2], tuple)                                 # frozen, not the caller's list
    assert codes.redeem(code) is None                                # the pop is still the use


@pytest.mark.parametrize('bad', [b'x' * 22, ('x',), ['x'], {'x': 1}, 5, 3.5, True, 0])
def test_redeem_is_none_for_anything_that_is_not_a_usable_string(bad):
    """auth.py:174 `if not isinstance(code, str) or not code: return None`
    removed: `token_hash(b'x')` dies with AttributeError inside the lock (bytes,
    list, tuple, dict, float and bool have no `.encode`), turning a hostile
    redeem body into a 500 instead of the same answer as an unknown code."""
    codes = auth.LaunchCodes(clock=Clock())
    good = codes.mint('prn_a', 'dvc_a')
    assert codes.redeem(bad) is None
    assert codes.redeem(good) is not None                            # the gate spent nothing


def test_bearer_refuses_wellformed_tokens_of_every_other_kind():
    """auth.py:62 `ids.token_kind(token) != 'device'` dropped: a node, broker or
    execution token of perfect shape walks the bearer gate and reaches the
    credential lookup, exactly the cross-credential confusion the prefix table
    (ids.TOKEN_PREFIXES) exists to stop. Same ULID body as a real device token."""
    body = auth.new_token()[4:]                                      # the random part of dev_...
    for prefix in ('node', 'hook', 'brk'):
        assert auth.bearer('Bearer %s_%s' % (prefix, body)) is None, prefix
    assert auth.bearer('Bearer dev_' + body) == 'dev_' + body        # the control


# ── PairingCodes: the breaker counts only real failures, and reopens ──

def test_a_successful_pairing_redeem_never_counts_toward_the_breaker():
    """auth.py:227-228 `if grant is not None: return grant` removed: a correct
    code is popped and then recorded as a failure, so honest redeemers help an
    attacker trip the D10 breaker, and the honest code itself answers None.
    Also pins the trip boundary: the 10th failure is still None, the 11th
    raises (a `>=` flip burns the 10th)."""
    c = Clock()
    codes = auth.PairingCodes(clock=c)
    good = codes.mint({'starter': 'prn_a', 'scopes': ['observe']})
    for _ in range(codes.FAIL_LIMIT - 1):                            # 9 failures, under
        assert codes.redeem('wrong') is None
    assert codes.redeem(good) == {'starter': 'prn_a', 'scopes': ['observe']}
    assert codes.redeem('wrong') is None                             # 10th: still not locked
    with pytest.raises(auth.PairingLocked):                          # 11th: locked
        codes.redeem('wrong')


def test_the_pairing_breaker_reopens_with_a_working_code_after_its_window():
    """auth.py:234 `_locked_until = now + self.FAIL_WINDOW_S` wrong (or the
    clear at 232-233 dropped): after FAIL_WINDOW_S the breaker is supposed to
    be closed again — a fresh mint must redeem, and a fresh set of FAIL_LIMIT
    failures must again stop at the boundary instead of relocking at once."""
    c = Clock()
    codes = auth.PairingCodes(clock=c)
    stale = codes.mint({'starter': 'prn_a'})
    with pytest.raises(auth.PairingLocked):
        for _ in range(codes.FAIL_LIMIT + 1):
            codes.redeem('wrong')
    assert len(codes) == 0 and stale not in repr(codes.__dict__)     # burned, hashes only
    with pytest.raises(auth.PairingLocked):
        codes.redeem('wrong')                                        # still closed
    c.now += codes.FAIL_WINDOW_S                                     # window passed exactly
    fresh = codes.mint({'starter': 'prn_b'})                         # minting never stopped
    assert codes.redeem(fresh) == {'starter': 'prn_b'}
    for _ in range(codes.FAIL_LIMIT):                                # old failures did not linger
        assert codes.redeem('wrong') is None


def test_a_minted_pairing_grant_survives_the_caller_editing_its_dict():
    """auth.py:218 `_mint(dict(grant), ...)` without the copy: the caller keeps
    the dict, so whoever minted can still widen the grant after the code left
    (p15 §6: the grant is fixed at start). Only the top level is copied, so
    only the top level is tampered with here."""
    codes = auth.PairingCodes(clock=Clock())
    grant = {'starter': 'prn_a', 'scopes': ['observe'], 'name': 'phone'}
    code = codes.mint(grant)
    grant['starter'] = 'prn_evil'
    grant['name'] = 'other'
    grant['extra'] = 'x'
    assert codes.redeem(code) == {'starter': 'prn_a', 'scopes': ['observe'], 'name': 'phone'}


# ── StepUpFailures: one counter per client, sticky once revoked ──

def test_step_up_counters_are_per_device_and_reset_is_local_and_silent():
    """auth.py:252 `self._n.get(device_id, 0) + 1` keyed wrongly (or 257
    `self._n.pop(device_id, None)` without the default): one client's wrong PINs
    revoke another, a reset clears rivals, or resetting a never-seen device
    dies with KeyError on the path that is supposed to answer first."""
    f = auth.StepUpFailures()
    assert [f.failed('d_a') for _ in range(4)] == [False] * 4
    assert f.failed('d_a') is True                                   # the 5th revokes d_a
    assert f.failed('d_b') is False                                  # d_b starts clean: a merged
    # key would already answer True on d_b's very first failure
    assert f.failed('d_a') is True                                   # past the limit, still True
    f.reset('d_a')
    assert f.failed('d_a') is False                                  # d_a restarts clean
    with f.__dict__['_lock']:
        assert f._n['d_b'] == 1                                      # a rival-clearing reset dies here
    f.reset('d_never_seen')                                          # silent, no KeyError
    assert [f.failed('d_b') for _ in range(4)] == [False, False, False, True]   # d_b's own 5th


# ── the error paths: what a refusal looks like ──

@pytest.mark.parametrize('host, wanted', [
    ('  PC.TailNet.TS.NET  ', 'pc.tailnet.ts.net'),                  # trimmed and lowered
    ('a' * 63 + '.example', 'a' * 63 + '.example'),                  # the 63-char label fits
    ('9a.b.example:8443', '9a.b.example:8443'),                       # digit labels inside: fine
])
def test_a_remote_host_is_trimmed_and_lowered_into_its_host_header_form(host, wanted):
    """auth.py:143 `(host or '').strip().lower()` reduced (drop `strip()` and a
    configured ' host ' dies as ValueError, so remote access silently never
    turns on; drop `lower()` and the stored host never matches the lowered
    Host header, so every tunnel request 403s). auth.py:144 `_HOSTNAME` bounds
    pins the 63-char label: the regex is `{0,61}` between anchor characters."""
    assert auth.remote_host(host) == wanted


@pytest.mark.parametrize('host', [
    'a' * 64 + '.example',                                            # label over 63
    'a_b.example', 'a-.example', 'a-.b.example@',                     # characters not allowed
    'pc..net', 'pc.net:', '.pc.net', 'pc.net.',                       # empty labels, empty port
    '127.0.0.53',                                                      # last label digits: an IP
])
def test_anything_else_is_refused_as_a_value_error_naming_the_host(host):
    """auth.py:144-145 `if not _HOSTNAME.fullmatch(h) or ...isdigit(): raise
    ValueError(...)`: the guard weakened (search() for fullmatch, the isdigit
    tail check dropped) admits an IP literal or a forged shape as a tunnel
    host, and Origin would then accept `https://` traffic for it (D16). The
    message must name the offending host so the operator can see it."""
    with pytest.raises(ValueError) as got:
        auth.remote_host(host)
    assert repr(host) in str(got.value)


def test_iso_writes_the_millisecond_z_shape_that_expiry_comparisons_read():
    """auth.py:68 `dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')`:
    without the replace, `now_iso()` hands out '+00:00' stamps while every
    stored `expires_at` ends 'Z', and `live()`'s string compare (auth.py:84)
    orders '+00:00' *before* any 'Z' stamp of the same second, so an expired
    credential outlives its expiry. Pin the exact stored shape."""
    stamp = datetime(2026, 3, 4, 5, 6, 7, 123456, tzinfo=timezone.utc)
    assert auth.iso(stamp) == '2026-03-04T05:06:07.123Z'
    assert auth.iso(stamp) < '2026-03-04T05:06:07.124Z'              # comparable, as stored
    assert not auth.now_iso().endswith('+00:00')


def test_security_headers_can_carry_another_cache_directive():
    """auth.py:44-47 `'Cache-Control': cache` hardcoded to 'no-store': the
    cacheable responses (server.py:362 passes a cache argument) would be sent
    as no-store, breaking the asset page's caching while the other three
    security headers are supposed to stay exactly as they are."""
    h = auth.security_headers('public, max-age=31536000, immutable')
    assert h['Cache-Control'] == 'public, max-age=31536000, immutable'
    plain = auth.security_headers()
    assert h['Cache-Control'] != plain['Cache-Control']
    assert {k: v for k, v in h.items() if k != 'Cache-Control'} == \
        {k: v for k, v in plain.items() if k != 'Cache-Control'}
