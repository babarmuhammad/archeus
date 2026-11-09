"""The one redactor (archeus/core/redact.py) against every credential shape the
audit found leaking. Every value here is synthetic."""

import json
import random
import time

import pytest

from archeus.core.domain import ids
from archeus.core.redact import redact, redact_json

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


# redact() is for free text. A JSON document goes through redact_json, which matches
# the parsed strings, so no secret can cut a quote or an escape of the JSON
@pytest.mark.parametrize('text', [
    'run curl -u admin:SYNTHhunter2', 'aws_secret_access_key=SYNTH0123',
    'export AWS_SECRET_ACCESS_KEY=$SYNTH', 'a key -----BEGIN PRIVATE KEY----- then SYNTHbase64',
    'a key -----BEGIN PRIVATE KEY-----\nSYNTHBODY0123\n', 'https://u:SYNTHpass@',
    '-----BEGIN PRIVATE KEY-----\\"', 'Authorization: Basic dXNlcjpTWU5USEVUSUM=',
])
@pytest.mark.parametrize('opts', [{}, {'ensure_ascii': False}, {'separators': (',', ':')}])
def test_a_secret_ending_a_string_never_breaks_the_json(text, opts):
    payload = {'text': text, 'list': [text, 1], 'n': {text: text}}
    out = json.loads(json.dumps(redact_json(payload), **opts))
    assert set(out) == {'text', 'list', 'n'} and '[redacted]' in out['text']
    assert 'SYNTH' not in json.dumps(out)


def test_a_quoted_aws_key_keeps_its_name_and_loses_its_value():
    out = redact_json({'env': {'aws_secret_access_key': 'SYNTH0123'}})
    assert out == {'env': {'aws_secret_access_key': '[redacted]'}}
    out = redact('aws_secret_access_key="SYNTH0123" next')
    assert 'SYNTH' not in out and out.endswith('" next')


def test_a_secret_named_by_its_key_is_redacted_in_a_document():
    out = redact_json({'Authorization': 'Basic dXNlcjpTWU5USEVUSUM=', 'headers': [{'user': 'bob'}]})
    assert out == {'Authorization': '[redacted]', 'headers': [{'user': 'bob'}]}


def test_redact_json_keeps_every_other_value_and_redacts_keys_and_deep_strings():
    doc = {'a': [1, 2.5, None, True, {'k': 'brk_' + 'Ab3-_' * 8}], 'brk_' + 'Zq9-_' * 8: 'v'}
    out = redact_json(doc)
    assert out['a'][:4] == [1, 2.5, None, True] and out['a'][4] == {'k': '[redacted]'}
    assert list(out)[1] == '[redacted]' and 'Zq9' not in json.dumps(out)
    deep = cur = []
    for _ in range(5000):
        cur.append([])
        cur = cur[0]
    cur.append('brk_' + 'Ab3-_' * 8)
    out = redact_json(deep)
    while isinstance(out, list):
        out = out[0]
    assert out == '[redacted]'


def test_redacting_any_payload_with_secrets_embedded_keeps_its_shape():
    rng = random.Random(20)
    secrets = [t for t, _ in LEAKS.values()] + [
        'curl -u a:SYNTH', 'aws_secret_access_key=SYNTH', '-----BEGIN PRIVATE KEY-----']
    bits = secrets + ['"', '\\', '\\"', '\n', '\t', '{', '}', '[', ']', ',', ':', ' ', '\xe9', chr(0x2028),
                      '\x00', 'plain', '://', '@', '-u ', '=', "'", '\\n', '\\\\', '\r', '\b']

    def text():
        return ''.join(rng.choice(bits) for _ in range(rng.randint(0, 12)))

    def shape(x):
        if isinstance(x, dict):
            return [shape(v) for v in x.values()]
        return [shape(v) for v in x] if isinstance(x, list) else type(x)

    for _ in range(400):
        payload = {text(): [text(), {text(): text()}, rng.randint(0, 9), None, True]}
        for opts in ({}, {'ensure_ascii': False}, {'separators': (',', ':'), 'sort_keys': True}):
            back = json.loads(json.dumps(redact_json(payload), **opts))
            assert shape(back) == shape(payload)


# the three leaks of the review of fix batches 9 and 10 (F1, F2), and the quoting
# an escaped string used to hide from the patterns
_KEY = ['-----BEGIN OPENSSH PRIVATE KEY-----', 'QyNTUxOQAAACDsecretsecretsecretsecret',
        '-----END OPENSSH PRIVATE KEY-----']


@pytest.mark.parametrize('prefix', ['%6d→', 'web-1  | ', '> ', '# ', '[12:00] ', ''])
def test_a_key_is_redacted_whatever_prefixes_its_lines(prefix):
    text = '\n'.join((prefix % i if '%' in prefix else prefix) + line for i, line in enumerate(_KEY))
    out = redact('before\n' + text + '\nafter')
    assert 'secretsecret' not in out and out.startswith('before\n') and out.endswith('\nafter')


@pytest.mark.parametrize('dumps', [0, 1, 2, 3, 4])
def test_a_key_is_redacted_however_often_its_text_was_escaped(dumps):
    text = '\n'.join(_KEY)
    for _ in range(dumps):
        text = json.dumps(text)
    out = redact('x ' + text + ' tail')
    assert 'secretsecret' not in out and out.endswith(' tail')


@pytest.mark.parametrize('end', ['-----END PRIVATE KEY-----', ''])
@pytest.mark.parametrize('size', [100, 16384, 200_000])
def test_a_key_of_any_size_is_redacted_to_its_end_line_or_to_the_end_of_the_text(size, end):
    out = redact('before\n-----BEGIN PRIVATE KEY-----\n' + 'A' * size + 'SYNTH_PRIVATE_TAIL' + end + ' after')
    assert 'SYNTH_PRIVATE_TAIL' not in out and out.startswith('before\n')
    assert out.endswith(' after') == bool(end)


@pytest.mark.parametrize('before', ['\\n', '\\t', '\\r\\n', ' '])
def test_a_token_after_a_literal_escape_is_still_at_a_left_edge(before):
    jwt = 'eyJhbGciOiJTWU5USCJ9.eyJzdWIiOiJzeW50aCJ9.c3ludGhzaWc'
    assert 'c3ludGhzaWc' not in redact('token:' + before + jwt)
    assert 'c3ludGhzaWc' not in redact(json.dumps({'text': 'token:\n' + jwt}))
    assert redact('xeyJabcde.b.c') == 'xeyJabcde.b.c'                   # still not mid-word
    assert 'SYNTHpw' not in redact(before + '-u bob:SYNTHpw')


def test_a_doubly_escaped_aws_secret_and_a_quoted_userinfo_password_are_redacted():
    out = redact(json.dumps(json.dumps({'aws_secret_access_key': 'SYNTH0123', 'n': 1})))
    assert 'SYNTH' not in out and 'aws_secret_access_key' in out
    assert 'pa"ss' not in redact('postgres://admin:pa"ss@db/x') and 'db/x' in redact('postgres://admin:pa"ss@db/x')


# the longest an input can make each pattern work: a start at every position, a
# long run that fails at its end, or a run that backtracks
_N = 120_000
_WORST = {
    'jwt': ['eyJ' * (_N // 3), 'eyJabcde.' + 'b' * _N, 'eyJabcde.' + 'a.' * (_N // 2), 'eyJabcde.' * (_N // 9),
            '\\n' * (_N // 2) + 'eyJ', 'eyJabcde.b.' * (_N // 12)],
    'pem': ['-----BEGIN PRIVATE KEY-----' * (_N // 27), '-----BEGIN ' + 'A' * _N,
            '-----BEGIN A' * (_N // 12), '-----BEGIN PRIVATE KEY-----' + 'ab \\n' * (_N // 5) + '\\"',
            '-----BEGIN PRIVATE KEY-----' + '-----END ' * (_N // 9),
            '-----BEGIN PRIVATE KEY-----' + ('-----END ' + 'A' * 32) * (_N // 41),
            '-----BEGIN PRIVATE KEY-----' + ('-----END ' + 'A' * 32 + ' ') * (_N // 42) + '-----END PRIVATE KEY-----',
            '-----BEGIN PRIVATE KEY-----' + '→A' * (_N // 2),
            ('-----BEGIN PRIVATE KEY-----' + 'x' * 30000) * (_N // 30027)],
    'authorization': ['authorization:' + ' ' * _N, 'authorization: basic ' * (_N // 21)],
    'bearer': ['bearer' + ' ' * _N, 'bearer   ' * (_N // 9), 'bearer abcdefg ' * (_N // 15)],
    'userinfo': ['://a:' + 'b' * _N, '://a:b' * (_N // 6), '://a' + ':a' * (_N // 2), '://' * (_N // 3)],
    'curl -u': ['-u ' + 'a' * _N, '-u a' * (_N // 4), '-u a' + ':' * _N, '-u' + ' ' * _N, '-u -u ' * (_N // 6),
                '\\n-u a' * (_N // 7), '-u a:' + '\\' * _N],
    'aws': ['aws_secret_access_key' + ' ' * _N, 'aws_secret_access_key ' * (_N // 22),
            'aws_secret_access_key"' * (_N // 22), 'AWS_SECRET_ACCESS_KEY=' * (_N // 22),
            'aws_secret_access_key' + '\\' * _N, 'aws_secret_access_key\\"' * (_N // 23),
            'aws_secret_access_key\\"=\\"' * (_N // 26)],
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


def test_keys_that_redact_to_one_name_stay_distinct_fields():
    a, b = 'brk_' + 'Aa1-_' * 8, 'brk_' + 'Bb2-_' * 8
    out = redact_json({a: {'first': 1}, b: {'second': 2}, '[redacted]': 3, '[redacted] #0': 5, 'plain': [4]})
    assert sorted(map(json.dumps, out.values())) == sorted(['{"first": 1}', '{"second": 2}', '3', '5', '[4]'])
    assert out['plain'] == [4] and 'Aa1' not in json.dumps(out) and 'Bb2' not in json.dumps(out)
    assert sorted(redact_json({a: 'x', b: 'y'}).values()) == ['x', 'y']
