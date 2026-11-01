"""The one redactor (archeus/core/redact.py) against every credential shape the
audit found leaking. Every value here is synthetic."""

import json
import random
import time

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


def _walk(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _walk(k)
            yield from _walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v)
    else:
        yield x


# a secret as the last thing in a string is where a `\S+` or `\Z` tail used to
# take the closing quote of the JSON with it
@pytest.mark.parametrize('text', [
    'run curl -u admin:SYNTHhunter2', 'aws_secret_access_key=SYNTH0123',
    'export AWS_SECRET_ACCESS_KEY=$SYNTH', 'a key -----BEGIN PRIVATE KEY----- then SYNTHbase64',
    'a key -----BEGIN PRIVATE KEY-----\nSYNTHBODY0123\n', 'https://u:SYNTHpass@',
    '-----BEGIN PRIVATE KEY-----\\"', 'Authorization: Basic dXNlcjpTWU5USEVUSUM=',
])
@pytest.mark.parametrize('opts', [{}, {'ensure_ascii': False}, {'separators': (',', ':')}])
def test_a_secret_ending_a_string_never_breaks_the_json(text, opts):
    payload = {'text': text, 'list': [text, 1], 'n': {text: text}}
    out = json.loads(redact(json.dumps(payload, **opts)))
    assert set(out) == {'text', 'list', 'n'} and '[redacted]' in out['text']
    assert 'SYNTH' not in out['text']
    again = json.loads(redact(json.dumps(redact(json.dumps(payload)))))
    assert isinstance(again, str)


def test_a_quoted_aws_key_keeps_its_name_and_loses_its_value():
    out = json.loads(redact(json.dumps({'env': {'aws_secret_access_key': 'SYNTH0123'}})))
    assert out == {'env': {'aws_secret_access_key': '[redacted]'}}
    out = redact('aws_secret_access_key="SYNTH0123" next')
    assert 'SYNTH' not in out and out.endswith('" next')


def test_redacting_any_dumped_payload_with_secrets_embedded_still_parses():
    rng = random.Random(20)
    secrets = [t for t, _ in LEAKS.values()] + [
        'curl -u a:SYNTH', 'aws_secret_access_key=SYNTH', '-----BEGIN PRIVATE KEY-----']
    bits = secrets + ['"', '\\', '\\"', '\n', '\t', '{', '}', '[', ']', ',', ':', ' ', '\xe9', '\u2028',
                      '\x00', 'plain', '://', '@', '-u ', '=', "'", '\\n', '\\\\']

    def text():
        return ''.join(rng.choice(bits) for _ in range(rng.randint(0, 12)))

    for _ in range(400):
        payload = {text(): [text(), {text(): text()}, rng.randint(0, 9), None, True]}
        for opts in ({}, {'ensure_ascii': False}, {'separators': (',', ':'), 'sort_keys': True}):
            dumped = json.dumps(payload, **opts)
            back = json.loads(redact(dumped))
            assert len(list(_walk(back))) == len(list(_walk(payload)))
            assert isinstance(json.loads(redact(json.dumps(dumped))), str)


# the longest an input can make each pattern work: a start at every position, a
# long run that fails at its end, or a run that backtracks
_N = 120_000
_WORST = {
    'jwt': ['eyJ' * (_N // 3), 'eyJabcde.' + 'b' * _N, 'eyJabcde.' + 'a.' * (_N // 2), 'eyJabcde.' * (_N // 9)],
    'pem': ['-----BEGIN PRIVATE KEY-----' * (_N // 27), '-----BEGIN ' + 'A' * _N,
            '-----BEGIN A' * (_N // 12), '-----BEGIN PRIVATE KEY-----' + 'ab \\n' * (_N // 5) + '\\"',
            '-----BEGIN PRIVATE KEY-----' + '-----END ' * (_N // 9)],
    'authorization': ['authorization:' + ' ' * _N, 'authorization: basic ' * (_N // 21)],
    'bearer': ['bearer' + ' ' * _N, 'bearer   ' * (_N // 9), 'bearer abcdefg ' * (_N // 15)],
    'userinfo': ['://a:' + 'b' * _N, '://a:b' * (_N // 6), '://a' + ':a' * (_N // 2), '://' * (_N // 3)],
    'curl -u': ['-u ' + 'a' * _N, '-u a' * (_N // 4), '-u a' + ':' * _N, '-u' + ' ' * _N, '-u -u ' * (_N // 6)],
    'aws': ['aws_secret_access_key' + ' ' * _N, 'aws_secret_access_key ' * (_N // 22),
            'aws_secret_access_key"' * (_N // 22), 'AWS_SECRET_ACCESS_KEY=' * (_N // 22)],
    'prefixes': ['brk_' * (_N // 4), 'sk-' * (_N // 3), 'ghp_' * (_N // 4), 'AKIA' * (_N // 4),
                 'AIza' * (_N // 4), 'xoxb-' * (_N // 5), 'gsk_' + 'a' * _N, 'sk-' + 'a' * _N],
    'plain': ['x' * _N, '"' * _N, '\\' * _N],
}


@pytest.mark.parametrize('name', sorted(_WORST))
def test_every_pattern_is_linear_on_its_worst_input(name):
    for text in _WORST[name]:
        t = time.perf_counter()
        redact(text)
        # a quadratic pattern needs seconds here (the JWT one took 3.8 s at 120 KB)
        assert time.perf_counter() - t < 0.5, text[:40]
