"""The red-team probes of archeus/core/redact.py (text and structural paths), kept as
regressions: every shape here leaked or blew up once, or held when it was tried. The
deliberate obfuscations no pattern can see are listed as xfail. Every secret is synthetic."""

import json
import random
import time

import pytest

from archeus.core.redact import last_mark, redact, redact_json, scrub, scrub_json

BS = chr(92)
S = 'SYNTHBODYabcdef0123456789'
MB = 1 << 20


def gone(out, secret=S):
    assert secret not in out, out[:200]


def pem(kind='', body=S, nl='\n'):
    return '-----BEGIN %sPRIVATE KEY-----%s%s%s-----END %sPRIVATE KEY-----' % (kind, nl, body, nl, kind)


# ── private keys: the kinds, the line endings, what stands around them ──

@pytest.mark.parametrize('kind', ['', 'RSA ', 'EC ', 'OPENSSH ', 'ENCRYPTED ', 'DSA '])
def test_pem_kinds_held(kind):
    gone(redact('x\n' + pem(kind)))


def test_pem_crlf_held():
    gone(redact(pem(nl='\r\n')))


def test_pem_text_before_begin_on_same_line_held():
    gone(redact('cat key: ' + pem()))


def test_pem_escaped_newlines_held():
    gone(redact(pem(nl=BS + 'n')))


def test_pem_body_without_end_held():
    gone(redact('-----BEGIN RSA PRIVATE KEY-----\n' + S))


def test_pem_pgp_private_key_block():
    """`gpg --export-secret-keys --armor` says PRIVATE KEY BLOCK."""
    t = '-----BEGIN PGP PRIVATE KEY BLOCK-----\n\n%s\n=abcd\n-----END PGP PRIVATE KEY BLOCK-----' % S
    gone(redact(t))
    assert last_mark('-----BEGIN PGP PRIVATE KEY BLOCK-----\n' + S) == 'BEGIN'


@pytest.mark.parametrize('marker', [
    '-----BEGIN\tPRIVATE KEY-----',
    '-----BEGIN  PRIVATE KEY-----',
    '-----BEGIN PRIVATE KEY-----',
    '-----begin private key-----',
    '-----BEGIN PRIVATE KEY----',
    '----BEGIN PRIVATE KEY-----',
    '-----BEGIN PRIVATE' + '\n' + 'KEY-----',
], ids=['tab', 'two-spaces', 'nbsp', 'lowercase', 'four-dashes', 'four-dashes-before', 'split-over-two-lines'])
def test_pem_marker_variants(marker):
    """A marker is not one exact spelling: any blank, any case, four dashes or more."""
    gone(redact(marker + '\n' + S))


@pytest.mark.xfail(strict=True, reason='deliberate obfuscation: no regex sees a zero-width '
                   'character, a Unicode hyphen or a spelled-out escape (an agent that wants a key '
                   'out can also base64 it)')
@pytest.mark.parametrize('marker', [
    '-----BEGIN​ PRIVATE KEY-----',
    '-----BEGIN PRIVATE​ KEY-----',
    '‐' * 5 + 'BEGIN PRIVATE KEY' + '‐' * 5,
    BS + 'u002d' * 5 + 'BEGIN PRIVATE KEY-----',
], ids=['zwsp-1', 'zwsp-2', 'unicode-hyphen', 'escaped-u002d'])
def test_pem_marker_obfuscation_unfixable_by_regex(marker):
    gone(redact(marker + '\n' + S))


@pytest.mark.xfail(strict=True, reason='not claimed: a key body that lost its marker is base64 '
                   'like any other')
def test_pem_body_without_any_marker():
    b = 'b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW'
    assert b not in redact('id_ed25519:\n' + b)


# ── token formats ──

TOKENS = {
    'brk': 'brk_' + 'Zq9-_' * 9, 'hook': 'hook_' + 'Zq9-_' * 9, 'dev': 'dev_' + 'Zq9-_' * 9,
    'node': 'node_' + 'Zq9-_' * 9, 'sk-ant': 'sk-ant-api03-' + 'Zq9' * 12, 'sk': 'sk-' + 'Zq9' * 12,
    'ghp': 'ghp_' + 'Zq9' * 12, 'github_pat': 'github_pat_' + 'Zq9' * 12,
    'glpat': 'glpat-' + 'Zq9' * 6, 'AKIA': 'AKIA' + 'ABCD1234' * 2, 'AIza': 'AIza' + 'Zq9' * 12,
    'xoxb': 'xoxb-' + 'Zq9' * 6, 'sk_live': 'sk_live_' + 'Zq9' * 8, 'npm': 'npm_' + 'Zq9' * 8,
    'gsk': 'gsk_' + 'Zq9' * 8,
}


@pytest.mark.parametrize('name', sorted(TOKENS))
@pytest.mark.parametrize('frame', ['k=%s', '"k":"%s"', BS + '"%s' + BS + '"', 'x %s y', '%s'], ids=range(5))
def test_token_formats_in_frames(name, frame):
    t = TOKENS[name]
    gone(redact(frame % t), t[8:])


@pytest.mark.parametrize('t', [
    'Authorization: Bearer %s' % S, 'bearer\t%s' % S, 'Bearer\n%s' % S, '"Authorization": "Bearer %s"' % S,
])
def test_bearer_forms_held(t):
    gone(redact(t))


JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SYNTHSIGabcdef'


@pytest.mark.parametrize('before', ['', 'token=', '"', ' ', BS + 'n', '/', 'Bearer '])
def test_jwt_held(before):
    gone(redact(before + JWT), 'SYNTHSIGabcdef')


@pytest.mark.parametrize('before', ['access_token_', 'jwt-', 'x', 'token0'])
def test_jwt_glued_to_a_word_character(before):
    """The left edge refuses a JWT glued to a word; its payload still starts at a dot."""
    gone(redact(before + JWT), 'SYNTHSIGabcdef')


def test_jwt_empty_signature_alg_none():
    gone(redact('eyJhbGciOiJub25lIn0.eyJzdWIiOiJTWU5USCJ9.'), 'eyJzdWIiOiJTWU5USCJ9')


@pytest.mark.parametrize('t', [
    'Authorization: Basic dXNlcjpTWU5USEVUSUM=',
    'authorization=basic dXNlcjpTWU5USEVUSUM=',
    '{"Authorization": "Basic dXNlcjpTWU5USEVUSUM="}',
    "{'Authorization': 'Basic dXNlcjpTWU5USEVUSUM='}",
    BS.join(['{', '"Authorization', '": ', '"Basic dXNlcjpTWU5USEVUSUM="}']),
], ids=['header', 'equals', 'json-text', 'python-repr', 'escaped-json'])
def test_basic_auth_forms(t):
    """A quote may stand between the name and its colon: a traceback prints headers as a dict
    repr."""
    gone(redact(t), 'dXNlcjpTWU5USEVUSUM')


@pytest.mark.parametrize('t', [
    'curl -u admin:SYNTHpass1 https://x', "curl -u 'admin:SYNTHpass1' https://x",
    'curl -u "admin:SYNTHpass1" https://x', 'curl -uadmin:SYNTHpass1 https://x',
    'curl --user "admin:SYNTHpass1" https://x', 'curl --user=admin:SYNTHpass1 https://x',
], ids=['plain', 'single-quoted', 'double-quoted', 'attached', 'long-quoted', 'long-equals'])
def test_curl_user_forms(t):
    gone(redact(t), 'SYNTHpass1')


@pytest.mark.parametrize('t', [
    'https://user:SYNTHpass1@host/x', 'https://SYNTHtoken12345@host/x',
])
def test_url_userinfo(t):
    gone(redact(t), 'SYNTHpass1' if 'pass' in t else 'SYNTHtoken12345')


@pytest.mark.parametrize('t', [
    'aws_secret_access_key=SYNTH/SECRET+VALUE0123',
    '{"aws_secret_access_key": "SYNTH/SECRET+VALUE0123"}',
    BS.join(['{', '"aws_secret_access_key', '": ', '"SYNTH/SECRET+VALUE0123', '"}']),
    'export AWS_SECRET_ACCESS_KEY=SYNTH/SECRET+VALUE0123',
])
def test_aws_secret_held(t):
    gone(redact(t), 'SYNTH/SECRET')


# ── dict structure ──

def test_dict_key_is_a_secret():
    out = json.dumps(redact_json({'sk-ant-api03-' + 'Zq9' * 12: 'v', 'brk_' + 'Zq9-_' * 9: 'w'}))
    gone(out, 'Zq9')
    assert out.count('[redacted]') == 2


def test_pem_split_over_two_strings_of_a_list():
    """A key a tool prints as the lines of a JSON array is one key over its strings."""
    gone(json.dumps(redact_json({'lines': ['-----BEGIN PRIVATE KEY-----', S, '-----END PRIVATE KEY-----']})))


def test_pem_split_over_two_values_of_a_dict():
    gone(json.dumps(redact_json({'a': '-----BEGIN PRIVATE KEY-----', 'b': S})))


def test_key_holding_pem_marker_redacts_its_value():
    gone(json.dumps(redact_json({'-----BEGIN PRIVATE KEY-----': S})))


def test_a_key_line_used_as_a_json_field_name_is_held():
    gone(json.dumps(redact_json({'lines': ['-----BEGIN PRIVATE KEY-----', {S: None}]})))


def test_a_marker_used_as_a_json_field_name_opens_the_key_for_later_fields():
    gone(json.dumps(redact_json({'-----BEGIN PRIVATE KEY-----': None, 'body': S})))


def test_a_field_name_after_a_value_is_scrubbed_in_document_order():
    gone(json.dumps(redact_json({'a': '-----BEGIN PRIVATE KEY-----', S: 'v'})))
    gone(json.dumps(redact_json([{'a': '-----BEGIN PRIVATE KEY-----'}, {S: 'v'}])))


def test_field_names_stay_when_no_key_is_open():
    assert redact_json({'type': 'assistant', 'n': {'x': 1}}) == {'type': 'assistant', 'n': {'x': 1}}


def test_names_of_an_open_key_do_not_lose_a_field():
    got = redact_json({'a': '-----BEGIN PRIVATE KEY-----', S: 1, S + 'x': 2})
    assert len(got) == 3 and list(got.values()) == ['[redacted]', 1, 2]


@pytest.mark.parametrize('frag', ['AQID', 'Q', 'AQID==', 'AQID\nBAUG', ' AQID \r\n'])
def test_a_short_key_fragment_in_an_open_key_is_held(frag):
    out = redact_json({'lines': ['-----BEGIN PRIVATE KEY-----', frag, '-----END PRIVATE KEY-----']})
    assert out['lines'][1] == '[redacted]', out


def test_a_short_fragment_after_the_end_line_is_kept():
    out = redact_json({'lines': ['-----BEGIN PRIVATE KEY-----', S, '-----END PRIVATE KEY-----', 'AQID']})
    assert out['lines'][-1] == 'AQID'


def test_prose_still_ends_an_open_key_and_a_short_word_is_masked_before_it():
    out = redact_json(['-----BEGIN PRIVATE KEY-----', 'AQID', 'three plain words', 'AQID'])
    assert out[1] == '[redacted]' and out[3] == 'AQID'


def test_a_short_fragment_is_held_in_the_stderr_channel_too():
    state = scrub('-----BEGIN PRIVATE KEY-----', None, 'json')[1]
    assert scrub('AQID', state, 'stderr')[0] == '[redacted]'


@pytest.mark.xfail(strict=True, reason='accepted residue (owner decisions item 110): a token or a '
                   'marker cut over two JSON strings or events is not carried; the pieces are '
                   'separate strings, and a carry would need its own state in every checkpoint')
@pytest.mark.parametrize('parts', [('sk-ABCD', 'EFGHIJKL'), ('ghp_ABCD', 'EFGHIJKL'),
                                   ('Bearer ', 'ABCDEFGHIJKL')])
def test_a_token_cut_over_two_strings(parts):
    out = redact_json({'content': [{'text': p} for p in parts]})
    assert ''.join(b['text'] for b in out['content']) != ''.join(parts)


@pytest.mark.xfail(strict=True, reason='accepted residue (owner decisions item 110): see '
                   'test_a_token_cut_over_two_strings')
def test_a_marker_cut_over_two_strings():
    gone(json.dumps(redact_json({'lines': ['-----BEGIN PRIVATE ', 'KEY-----', S]})))


def test_bearer_split_over_name_and_value():
    gone(json.dumps(redact_json({'Authorization': 'Bearer ' + S})))
    gone(json.dumps(redact_json({'Authorization': 'Basic dXNlcjpTWU5USEVUSUM='})), 'dXNlcjpTWU5USEVUSUM')


def test_nested_json_inside_a_json_string_held_when_plain():
    inner = json.dumps({'Authorization': 'Bearer ' + S, 'k': pem()})
    gone(json.dumps(redact_json({'out': inner})))


def test_nested_json_in_a_string_with_basic_auth():
    """The quoted Basic form, reached through a JSON document held in a string."""
    inner = json.dumps({'Authorization': 'Basic dXNlcjpTWU5USEVUSUM='})
    gone(json.dumps(redact_json({'out': inner})), 'dXNlcjpTWU5USEVUSUM')


def test_key_collisions_keep_every_field_and_the_order():
    secrets = ['sk-AAAAAAAA%d' % i for i in range(5)]
    d = {secrets[0]: 1, '[redacted]': 2, secrets[1]: 3, '[redacted] #1': 4, 'plain': 5, secrets[2]: 6,
         '[redacted] #0': 7, 'x ' + secrets[3]: 8, 'x [redacted]': 9, '[redacted] #3 #3': 10}
    out = redact_json(d)
    assert list(out.values()) == list(d.values())
    assert len(out) == len(d)
    gone(json.dumps(out), 'AAAAAAAA')


def test_key_collision_fuzz_never_drops_a_field_or_reorders():
    rnd = random.Random(7)
    parts = ['[redacted]', ' #', '0', '1', '2', 'sk-AAAAAAAA', 'sk-BBBBBBBB', 'k', ' ', 'brk_CCCCCCCCC']
    for _ in range(3000):
        d = {}
        for i in range(rnd.randint(1, 9)):
            d[''.join(rnd.choice(parts) for _ in range(rnd.randint(1, 5)))] = i
        out = redact_json(d)
        assert list(out.values()) == list(d.values()), (d, out)
        gone(json.dumps(out), 'AAAAAAAA')
        gone(json.dumps(out), 'BBBBBBBB')
        gone(json.dumps(out), 'CCCCCCCCC')


def test_non_str_keys_and_values():
    out = redact_json({1: 'sk-AAAAAAAAAA', None: ['sk-BBBBBBBBBB'], 2.5: {'k': 'sk-CCCCCCCCCC'}, True: 'x'})
    gone(str(out), 'AAAAAAAAAA')
    gone(str(out), 'BBBBBBBBBB')
    gone(str(out), 'CCCCCCCCCC')


def test_tuple_set_and_bytes_are_redacted():
    """Generic callers only (manager.py hands redact_json an adapter's inventory dict)."""
    out = redact_json({'t': ('sk-AAAAAAAAAA',), 'b': b'sk-BBBBBBBBBB', 's': {'sk-CCCCCCCCCC'},
                       ('sk-DDDDDDDDDD',): 1, b'sk-EEEEEEEEEE': 2})
    for s in 'ABCDE':
        assert s * 10 not in str(out), s


def test_lone_surrogates_and_pairs_do_not_crash():
    t = 'a\ud800b sk-AAAAAAAAAA 😀 ' + pem()
    out = redact(t)
    gone(out, 'AAAAAAAAAA')
    gone(out)
    json.dumps(redact_json({'k\udc80': t}))


def test_a_cyclic_structure_returns():
    """Generic callers only. Run in a child with a hard timeout, so the suite cannot hang."""
    import subprocess
    import sys
    code = 'from archeus.core.redact import redact_json\na=[]\na.append(a)\nredact_json(a)'
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    try:
        r = subprocess.run([sys.executable, '-c', code], timeout=3, capture_output=True, cwd=root,
                           env=dict(os.environ, PYTHONPATH=root))
    except subprocess.TimeoutExpired:
        pytest.fail('redact_json did not return on a cyclic list in 3 s (infinite loop, memory grows)')
    assert r.returncode == 0, r.stderr[-500:]


def test_shared_substructure_is_walked_once():
    """Generic callers only: a DAG that shares sub-lists is walked once per container."""
    o = ['sk-AAAAAAAAAAA']
    for _ in range(18):
        o = [o, o]
    t = time.perf_counter()
    redact_json(o)
    assert time.perf_counter() - t < 2, 'depth 18 sharing takes 2^18 visits; depth 22 would take ~16x'


# ── time: over 2 s for 1 MB is a finding ──

def _timed(fn, limit=2.0):
    t = time.perf_counter()
    fn()
    dt = time.perf_counter() - t
    assert dt < limit, '%.2fs' % dt


SHAPES = {
    'plain': 'a ' * (MB // 2), 'dashes': '-' * MB, 'begin-no-key': '-----BEGIN ' * (MB // 11),
    'begin-A': ('-----BEGIN ' + 'A' * 32 + 'x') * (MB // 44), 'begin-spaces': '-----BEGIN ' + ' ' * MB,
    'end-flood': '-----BEGIN PRIVATE KEY-----' + '-----END ' * (MB // 9),
    'sk-short': 'sk-abc ' * (MB // 7), 'eyJ': 'eyJ' * (MB // 3), 'eyJ-esc': (BS + 'neyJabcd') * (MB // 9),
    'bearer-ws': 'bearer' + ' ' * MB, 'bearer-rep-ws': ('bearer' + ' ' * 100) * (MB // 106),
    'url-colon': '://' + 'a:' * (MB // 2), 'url-rep': ('://a:' + 'b' * 50) * (MB // 54),
    '-u-rep': ' -u a' * (MB // 5), '-u-ws': ' -u' + ' ' * MB, '-u-eq': ' -u' + '=' * MB,
    'aws-bs': 'aws_secret_access_key' + BS * MB, 'aws-rep': ('aws_secret_access_key' + BS) * (MB // 22),
    'aws-ws': 'aws_secret_access_key=' + ' ' * MB, 'basic-ws': ('authorization:' + ' ' * 100) * (MB // 114),
    'esc-n': (BS + 'n') * (MB // 2), 'nl': '\n' * MB, 'unicode': 'é' * MB,
    'pem-1mb': pem(body=('A' * 64 + '\n') * (MB // 65)),
}


@pytest.mark.parametrize('name', sorted(SHAPES))
def test_redact_is_linear_on_1mb(name):
    _timed(lambda: redact(SHAPES[name]))


def test_pem_state_helpers_on_1mb():
    big = '-----BEGIN PRIVATE KEY-----\n' + ('A' * 64 + '\n') * (MB // 65)
    _timed(lambda: scrub(big))
    _timed(lambda: scrub(big, 'stderr', 'stderr'))
    _timed(lambda: scrub(big, 'json', 'stderr'))
    _timed(lambda: last_mark('-----END ' * (MB // 9)))


def test_redact_json_one_mb_pairs_and_many_keys():
    _timed(lambda: redact_json({'x' * MB: 'y' * MB}))
    _timed(lambda: redact_json({'sk-AAAAAAAA%d' % i: 'sk-BBBBBBBBB' for i in range(100000)}))
    _timed(lambda: redact_json({'k%d sk-AAAAAAAA' % i: 'v' for i in range(100000)}))
    _timed(lambda: redact_json({str(i) + 'k' * 1000: 'y' * 1000 for i in range(1500)}))


def test_redact_json_deep_nesting_is_iterative():
    o = 'sk-AAAAAAAAAAA'
    for _ in range(100000):
        o = [o]
    assert redact_json(o) is not None
    o = 'sk-AAAAAAAAAAA'
    for _ in range(100000):
        o = {'k': o}
    assert redact_json(o) is not None


def test_a_plain_field_name_stays_while_a_key_is_open():
    out = redact_json(['-----BEGIN PRIVATE KEY-----', {'modelUsage': 'X'}])
    assert list(out[1]) == ['modelUsage'] and out[1]['modelUsage'] == '[redacted]'


def test_a_string_of_a_base64_line_and_prose_is_not_a_short_fragment():
    out = redact_json(['-----BEGIN PRIVATE KEY-----', 'AQID\nthree plain words'])
    assert out[1] == 'AQID\nthree plain words'


def test_a_field_name_is_read_before_its_own_value():
    assert S in redact_json({S: '-----BEGIN PRIVATE KEY-----'})


def test_an_empty_string_is_not_masked_while_a_key_is_open():
    assert redact_json(['-----BEGIN PRIVATE KEY-----', '', ' '])[1:] == ['', ' ']


# ── fx16: the review of fx15 ──

KEY = 'MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7'


@pytest.mark.parametrize('channel', ['json', 'stderr'])
def test_the_structural_words_of_an_event_stay_while_a_key_is_open(channel):
    state = scrub('-----BEGIN PRIVATE KEY-----', None, channel)[1]
    doc = {'type': 'result', 'subtype': 'success', 'result': 'done', 'role': 'assistant',
           'content': [{'type': 'text'}]}
    assert scrub_json(doc, state)[0] == doc


@pytest.mark.parametrize('frag', ['AQID', 'Zm9v', 'z9', 'AQIDbaug'])
def test_a_short_fragment_that_is_not_a_lowercase_word_is_still_held(frag):
    out = redact_json(['-----BEGIN PRIVATE KEY-----', frag])
    assert out[1] == '[redacted]', out


def test_a_field_name_that_reads_as_prose_does_not_end_the_key():
    out = redact_json(['-----BEGIN PRIVATE KEY-----', {'three plain words': 'AQID'}])
    assert out[1] == {'three plain words': '[redacted]'}


def test_prose_in_a_value_still_ends_the_key_after_a_prose_field_name():
    out = redact_json(['-----BEGIN PRIVATE KEY-----', {'three plain words': 'four more plain words'},
                       'AQID'])
    assert out[2] == 'AQID'


@pytest.mark.parametrize('line', [KEY + '!', "'%s'," % KEY, KEY[:40] + ' ' + BS, KEY + '",',
                                  KEY + BS + 'n', KEY + '!   '])
def test_a_body_line_with_a_few_trailing_characters_is_held(line):
    gone(json.dumps(redact_json({'t': '-----BEGIN PRIVATE KEY-----', 'u': line})), KEY[:30])


def test_a_body_line_used_as_a_field_name_with_a_colon_is_held():
    gone(json.dumps(redact_json([{'t': '-----BEGIN PRIVATE KEY-----'}, {KEY + ':': 1}])), KEY[:30])
