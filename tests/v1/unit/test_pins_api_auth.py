"""Mutation-pinning tests for archeus/api/auth.py (T-822).

Each test here names a security-relevant branch whose removal or inversion would
survive every existing test in the suite.  The mutation that each test catches is
stated in its name; a scratch proof under /work/scratch applies the mutation and
quotes the resulting failure."""

import hmac

import pytest

from archeus.api import auth


def _cred(**over):
    t = auth.new_token()
    c = dict(token_hash=auth.token_hash(t), principal_id='prn_x', device_id='dvc_x',
             device_state='ACTIVE', scopes=('observe',), expires_at=None, revoked_at=None)
    c.update(over)
    return c, auth.token_hash(t)


class TestBearerWhitespace:
    def test_trailing_whitespace_is_stripped_before_token_kind_check(self):
        t = auth.new_token()
        assert auth.bearer('Bearer ' + t + '  ') == t
        assert auth.bearer('Bearer ' + t + '\t') == t

    def test_token_that_is_only_whitespace_is_rejected(self):
        assert auth.bearer('Bearer   ') is None


class TestLiveExpiryBoundary:
    def test_credential_expiring_at_exactly_now_is_not_live(self):
        c, h = _cred(expires_at='2026-06-15T12:00:00.000Z')
        assert not auth.live(c, h, now='2026-06-15T12:00:00.000Z')

    def test_credential_expiring_one_ms_after_now_is_live(self):
        c, h = _cred(expires_at='2026-06-15T12:00:00.001Z')
        assert auth.live(c, h, now='2026-06-15T12:00:00.000Z')


class TestLiveTimingSafeComparison:
    def test_live_uses_hmac_compare_digest_not_equality(self, monkeypatch):
        c, h = _cred()
        called = []
        original = hmac.compare_digest

        def spy(a, b):
            called.append((a, b))
            return original(a, b)

        monkeypatch.setattr('archeus.api.auth.hmac.compare_digest', spy)
        assert auth.live(c, h)
        assert len(called) == 1
        assert called[0] == (c['token_hash'].encode('ascii'), h.encode('ascii'))

    def test_live_returns_false_when_compare_digest_says_mismatch(self, monkeypatch):
        c, h = _cred()
        monkeypatch.setattr('archeus.api.auth.hmac.compare_digest', lambda a, b: False)
        assert not auth.live(c, h)


class TestLoopbackPeer:
    @pytest.mark.parametrize('addr', [
        '127.0.0.1',
        ('127.0.0.1', 9999),
        '::1',
        ('::1', 12345),
        '127.0.0.2',
        '127.255.255.255',
        ('127.1.2.3', 80),
    ])
    def test_loopback_addresses_are_accepted(self, addr):
        assert auth.loopback_peer(addr)

    @pytest.mark.parametrize('addr', [
        '10.0.0.1',
        '192.168.1.1',
        '::2',
        ('10.0.0.1', 80),
        '0.0.0.0',
        'localhost',
        '256.0.0.1',
    ])
    def test_non_loopback_addresses_are_rejected(self, addr):
        assert not auth.loopback_peer(addr)


class TestLaunchCodesMintPurge:
    def test_expired_codes_are_purged_on_mint(self):
        now = [100.0]
        codes = auth.LaunchCodes(clock=lambda: now[0], ttl=10.0)
        codes._mint('payload_a')
        codes._mint('payload_b')
        assert len(codes) == 2
        now[0] = 111.0
        codes._mint('payload_c')
        assert len(codes) == 1

    def test_unexpired_codes_survive_purge(self):
        now = [100.0]
        codes = auth.LaunchCodes(clock=lambda: now[0], ttl=60.0)
        codes._mint('payload_a')
        now[0] = 130.0
        codes._mint('payload_b')
        assert len(codes) == 2
