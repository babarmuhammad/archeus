"""T-1383: branch gaps in claude_sessions/usage.py lines 49-105.

Covers _creds, _read_token, _token_expired, _account_email, account_meta and
_spend_of. Every credential file is a synthetic fixture under tmp_path with
obvious fake tokens; the real config dir is never read.
"""
import json
import os

import pytest

from claude_sessions import usage

FAKE_TOKEN = 'tok-fake'


def _write_creds(cfgdir, payload):
    os.makedirs(cfgdir, exist_ok=True)
    path = os.path.join(cfgdir, '.credentials.json')
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
    with open(path, 'wb') as f:
        f.write(data)
    return path


def test_creds_read_only_and_malformed_is_empty(tmp_path):
    """Branch: _creds never writes, and every malformed shape returns {} without
    raising. A valid file keeps its bytes and mtime after the read. Caught by: a
    write-back in _creds, or a narrower except that lets a shape error escape."""
    good = _write_creds(str(tmp_path / 'ok'), {'claudeAiOauth': {'accessToken': FAKE_TOKEN}})
    before = (open(good, 'rb').read(), os.stat(good).st_mtime_ns)
    assert usage._creds(str(tmp_path / 'ok')) == {'accessToken': FAKE_TOKEN}
    assert (open(good, 'rb').read(), os.stat(good).st_mtime_ns) == before

    shapes = {
        'list': b'[1, 2, 3]',
        'not-json': b'not json at all',
        'null-root': b'null',
        'null-oauth': b'{"claudeAiOauth": null}',
    }
    for name, raw in shapes.items():
        cfg = str(tmp_path / name)
        path = _write_creds(cfg, raw)
        snapshot = (raw, os.stat(path).st_mtime_ns)
        assert usage._creds(cfg) == {}, name
        assert usage._read_token(cfg) is None, name
        assert (open(path, 'rb').read(), os.stat(path).st_mtime_ns) == snapshot, name


def test_creds_cfgdir_default_and_override(monkeypatch, tmp_path):
    """Branch: _creds `cfgdir or _c.config_dir`. None reads the configured dir; an
    explicit cfgdir overrides it. Caught by: ignoring the argument, or inverting
    the `or`."""
    default_dir = str(tmp_path / 'default')
    other_dir = str(tmp_path / 'other')
    _write_creds(default_dir, {'claudeAiOauth': {'accessToken': 'tok-default'}})
    _write_creds(other_dir, {'claudeAiOauth': {'accessToken': 'tok-other'}})
    monkeypatch.setattr(usage._c, 'config_dir', default_dir)

    assert usage._read_token() == 'tok-default'
    assert usage._read_token(other_dir) == 'tok-other'


def test_token_expired_boundaries(monkeypatch, tmp_path):
    """Branch: _token_expired `float(exp)/1000 <= now`. Equal to now is expired; one
    second later is not. Missing, zero and non-numeric expiresAt are not expired.
    Caught by: `<` for `<=`, or a try that returns True on a bad value."""
    now = 1_700_000_000.0
    monkeypatch.setattr(usage.time, 'time', lambda: now)
    cases = {
        'equal': (int(now * 1000), True),
        'future': (int(now * 1000) + 1000, False),
        'past': (int(now * 1000) - 1000, True),
        'missing': (None, False),
        'zero': (0, False),
        'text': ('soon', False),
    }
    for name, (exp, want) in cases.items():
        cfg = str(tmp_path / name)
        oauth = {'accessToken': FAKE_TOKEN}
        if exp is not None:
            oauth['expiresAt'] = exp
        _write_creds(cfg, {'claudeAiOauth': oauth})
        assert usage._token_expired(cfg) is want, name


def test_account_email_precedence(tmp_path):
    """Branch: _account_email checks each key at top level before the nested account
    value, and tries the keys in order email_address, emailAddress, email. A missing
    file gives ''. Caught by: checking nested before top-level, or reordering keys."""
    top_first = str(tmp_path / 'top')
    _write_creds(top_first, {'claudeAiOauth': {
        'email': 'top@example.test', 'account': {'email_address': 'nest@example.test'}}})
    assert usage._account_email(top_first) == 'nest@example.test'

    key_order = str(tmp_path / 'order')
    _write_creds(key_order, {'claudeAiOauth': {
        'email': 'third@example.test', 'emailAddress': 'second@example.test',
        'email_address': 'first@example.test'}})
    assert usage._account_email(key_order) == 'first@example.test'

    assert usage._account_email(str(tmp_path / 'absent')) == ''


def test_account_meta_no_token_leak(tmp_path):
    """Branch: account_meta returns only plan and tier, '' for missing fields, and
    never the token. Caught by: returning the whole oauth block."""
    cfg = str(tmp_path / 'meta')
    _write_creds(cfg, {'claudeAiOauth': {'accessToken': FAKE_TOKEN,
                                         'subscriptionType': 'max'}})
    meta = usage.account_meta(cfg)
    assert meta == {'plan': 'max', 'tier': ''}
    assert FAKE_TOKEN not in json.dumps(meta)


def test_read_token_absent_is_none(tmp_path):
    """Branch: _read_token returns None when accessToken is absent, without raising.
    Caught by: indexing with [] instead of .get."""
    cfg = str(tmp_path / 'noacc')
    _write_creds(cfg, {'claudeAiOauth': {'subscriptionType': 'pro'}})
    assert usage._read_token(cfg) is None


def test_spend_disabled_is_none():
    """Branch: _spend_of returns None when spend is not enabled, even with an amount
    present. Caught by: dropping the `enabled` guard."""
    data = {'spend': {'enabled': False, 'used': {'amount_minor': 250, 'exponent': 2}}}
    assert usage._spend_of(data) is None
    assert usage._spend_of({}) is None


def test_spend_bad_amount_is_zero():
    """Branch: _spend_of TypeError arm. A non-numeric amount_minor gives used 0.0,
    while pct and currency are still returned. Caught by: letting the TypeError
    escape, or dropping the sibling fields."""
    data = {'spend': {'enabled': True, 'percent': 5, 'used': {
        'amount_minor': 'abc', 'exponent': 2, 'currency': 'EUR'}}}
    assert usage._spend_of(data) == {'used': 0.0, 'pct': 5, 'currency': 'EUR'}


def test_spend_defaults_and_rounding():
    """Branch: _spend_of defaults: percent missing gives 0, currency missing gives
    'USD', and the amount is rounded to 2 decimals. Caught by: a changed default or
    dropping round()."""
    data = {'spend': {'enabled': True, 'used': {'amount_minor': 1234, 'exponent': 2}}}
    assert usage._spend_of(data) == {'used': 12.34, 'pct': 0, 'currency': 'USD'}

    rounded = {'spend': {'enabled': True, 'used': {'amount_minor': 1234, 'exponent': 3}}}
    assert usage._spend_of(rounded)['used'] == 1.23


@pytest.mark.xfail(
    strict=True,
    reason="claude_sessions/usage.py:101 `used.get('exponent') or 2` turns an explicit "
           "exponent 0 into 2, so 250 minor units give 2.5 instead of 250.0")
def test_spend_exponent_zero_is_honoured():
    """PREMISE: exponent 0 means no minor unit (for example a zero-decimal currency),
    so 250 minor units is 250.0. No test or docstring pins the current 2.5."""
    data = {'spend': {'enabled': True, 'used': {'amount_minor': 250, 'exponent': 0}}}
    assert usage._spend_of(data)['used'] == 250.0
