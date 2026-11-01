"""The one redactor (archeus/core/redact.py) against every credential shape the
audit found leaking. Every value here is synthetic."""

import pytest

from archeus.core.domain import ids
from archeus.core.redact import redact

KEY = 'a1B2c3D4' * 4

# (text, the part that must not survive)
LEAKS = {
    'broker token': ('ANTHROPIC_AUTH_TOKEN=brk_' + 'Ab3-_' * 8, 'Ab3-_Ab3'),
    'groq': ('api key gsk_' + KEY, KEY),
    'stripe live': ('sk_live_' + KEY, KEY),
    'basic header': ('Authorization: Basic dXNlcjpTWU5USEVUSUM=', 'dXNlcjpTWU5USEVUSUM'),
    'bearer with + / =': ('Authorization: Bearer abcdefgh+SYNTHTAIL/yyyy==', 'SYNTHTAIL'),
    'jwt': ('t eyJhbGciOiJTWU5USCJ9.eyJzdWIiOiJzeW50aCJ9.c3ludGhzaWc', 'c3ludGhzaWc'),
    'google': ('AIzaSy' + 'A-1234567890abcdefghijklmnopqrstu', 'A-1234567890abcdef'),
    'aws temp': ('ASIA' + 'ABCDEFGHIJKLMNOP', 'ABCDEFGHIJKLMNOP'),
    'aws secret keyed': ('AWS_SECRET_ACCESS_KEY=SYNTH/SECRET+VALUE0123', 'SYNTH/SECRET'),
    'url userinfo': ('https://user:SYNTHpass@git.example.com/x.git', 'SYNTHpass'),
    'curl -u': ('curl -u admin:SYNTHpass https://x', 'SYNTHpass'),
    'curl --user': ('curl --user admin:SYNTHpass https://x', 'SYNTHpass'),
    'pem block': ('-----BEGIN PRIVATE KEY-----\nSYNTHBODY0123\n-----END PRIVATE KEY-----\nafter',
                  'SYNTHBODY0123'),
    'pem truncated': ('-----BEGIN RSA PRIVATE KEY-----\nSYNTHBODY0123', 'SYNTHBODY0123'),
    'slack': ('xoxb-1234567890-' + 'abcdefghijkl', 'abcdefghijkl'),
    'npm': ('npm_' + KEY, KEY),
    'gitlab': ('glpat-' + 'AbCdEfGh0123456789', 'AbCdEfGh0123456789'),
    'anthropic upper case': ('SK-ANT-API03-' + 'A' * 40, 'A' * 40),
    'anthropic': ('sk-ant-api03-' + 'A' * 40, 'A' * 40),
}


@pytest.mark.parametrize('name', sorted(LEAKS))
def test_each_credential_format_is_redacted(name):
    text, secret = LEAKS[name]
    out = redact('before %s after' % text)
    assert secret not in out and '[redacted]' in out
    assert out.startswith('before ')


def test_every_minted_token_prefix_is_redacted():
    for prefix in ids.TOKEN_PREFIXES.values():
        out = redact('x %s_%s y' % (prefix, 'Zq9' * 10))
        assert 'Zq9' not in out, prefix


@pytest.mark.parametrize('text', [
    'the basic configuration of a bearer of tokens',
    'Authorization: none', 'ssh://git@host/repo.git', 'http://localhost:8080/x',
    'docker run -u 1000:1000 img', 'max_tokens=100000', 'commit 0123456789abcdef0123456789abcdef01234567',
    'see https://example.com/a:b@c/d', 'eyJ is not a token', 'AIza too short',
])
def test_ordinary_text_is_left_alone(text):
    assert redact(text) == text
