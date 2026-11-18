"""T-1394: the highest-risk uncovered branches of `archeus/node/broker.py`, lines 619-690 (`_forms`,
`_foreign_credential`, `_prefix_tail`, `_leaks`, `_bearer`, `_model_of`, `_no_dupes`; `_reply` is outside the
selection).

Selected branches, ranked fail-closed first, then boundaries, then error paths:

 1. broker.py:627-629  _foreign_credential: an `sk-ant-` sequence that does not start a whole API key is
                       foreign; every whole key is not.
 2. broker.py:619-624  _forms: the key itself, its base64 at the three alignments (whole 3-byte groups),
                       and its JSON \\uXXXX escapes.
 3. broker.py:644-648  _leaks: the key is found at a base64 alignment inside a larger blob, and case-folded.
 4. broker.py:644-648  _leaks: a str is encoded latin-1 with 'replace'; bytes and bytearray are used as is;
                       a blob without the key is not a leak.
 5. broker.py:632-641  _prefix_tail: no suffix that is a proper prefix of a form gives 0; a suffix that is a
                       proper prefix of the key is held back.
 6. broker.py:656-662  _model_of: a body that is not JSON (ValueError, UnicodeDecodeError, RecursionError)
                       is Refused 400 before any model check.
 7. broker.py:663-664  _model_of: a JSON array, a different model, or a non-str pinned model (None == None)
                       is Refused 403; the pinned model itself passes.
 8. broker.py:667-670  _no_dupes: a duplicate key at any depth is refused 400, never the first one taken.
 9. broker.py:651-653  _bearer: the scheme is matched case-insensitively; 'Basic' and a missing header give None.
10. broker.py:651-653  _bearer: 'Bearer ' gives '' and the authorize that follows refuses '' and None alike
                       (401), so the empty token is not a grant. Premise checked: no defect, no xfail.

Existing coverage that is not repeated: tests/v1/unit/test_gaps2_node_broker_a.py, test_gaps2_node_broker_b.py
and test_gaps5_node_broker.py drive forwarding, revoke and the stream-level redaction through the broker;
test_gaps2_node_broker_b.py:175 covers a leak after issue at stream level. These tests stay at the helper level,
where the composition (alignment, folding, duplicate keys at depth) is not reachable by a stream test alone.

Seams: pure functions and a fake request with header(name); the authorize refusal is reached through the
unbound method with a stub self, which returns before touching the grant table. Keys are synthetic
('sk-ant-api03-' plus ASCII); no socket, no upstream, no subprocess, no environment value.
"""

import base64
import threading
from types import SimpleNamespace

import pytest

from archeus.node import broker as B

KEY = 'sk-ant-api03-ABCDEFGHIJKLMNOPQRS'


class Req:
    def __init__(self, authorization):
        self.authorization = authorization

    def header(self, name):
        return self.authorization if name == 'authorization' else None


def test_a_sequence_that_does_not_start_a_whole_key_is_foreign_and_a_whole_key_is_not():
    assert B._foreign_credential('before %s after' % KEY) is False
    assert B._foreign_credential('x sk-ant-xyz') is True
    assert B._foreign_credential('%s and sk-ant-bogus' % KEY) is True
    assert B._foreign_credential('no marker here') is False


def test_the_forms_are_the_key_its_three_base64_alignments_and_its_json_escapes():
    k = KEY.encode('latin-1')
    expected = (k,
                base64.b64encode(k[0:30]),
                base64.b64encode(k[1:31]),
                base64.b64encode(k[2:32]),
                ''.join('\\u%04x' % ord(c) for c in KEY).encode('ascii'))
    assert B._forms(KEY) == expected


def test_the_key_is_a_leak_at_a_base64_alignment_inside_a_larger_blob():
    k = KEY.encode('latin-1')
    assert B._leaks(b'zz' + base64.b64encode(k[1:31]) + b'!!', KEY) is True
    assert B._leaks(b'Q' + base64.b64encode(k[2:32]), KEY) is True
    assert B._leaks(b'\x00' + base64.b64encode(k[0:30]), KEY) is True


def test_an_upper_case_copy_of_the_key_is_a_leak_and_an_unrelated_blob_is_not():
    assert B._leaks(KEY.upper().encode('ascii'), KEY) is True
    assert B._leaks(b'nothing to see here', KEY) is False


def test_a_str_is_encoded_latin1_with_replace_and_bytes_are_used_as_they_are():
    assert B._leaks('€' + KEY, KEY) is True
    assert B._leaks(bytearray(KEY.encode('ascii')), KEY) is True
    assert B._leaks('€ only, no key', KEY) is False


def test_the_held_back_tail_is_the_longest_proper_prefix_of_a_form_at_the_end():
    forms = tuple(f.lower() for f in B._forms(KEY))
    assert B._prefix_tail(b'hello sk-ant-ap', forms) == len('sk-ant-ap')
    assert B._prefix_tail(b'nothing that could start a key', forms) == 0


def test_a_body_that_is_not_json_is_refused_400_before_any_model_check():
    for body in (b'{not json', b'\xff', b'[' * 200000):
        with pytest.raises(B.Refused) as refused:
            B._model_of(body, 'pinned-model')
        assert refused.value.status == 400


def test_a_json_array_a_different_model_or_a_non_str_pin_is_refused_403_and_the_pin_passes():
    with pytest.raises(B.Refused) as a:
        B._model_of(b'[{"model": "pinned-model"}]', 'pinned-model')
    assert a.value.status == 403
    with pytest.raises(B.Refused) as b:
        B._model_of(b'{"model": "other"}', 'pinned-model')
    assert b.value.status == 403
    with pytest.raises(B.Refused) as c:
        B._model_of(b'{}', None)
    assert c.value.status == 403
    assert B._model_of(b'{"model": "pinned-model"}', 'pinned-model') is None


def test_a_duplicate_key_at_any_depth_is_refused_400_and_never_the_first_taken():
    with pytest.raises(B.Refused) as nested:
        B._model_of(b'{"outer": {"model": "pinned-model", "model": "pinned-model"}}',
                    'pinned-model')
    assert nested.value.status == 400
    with pytest.raises(B.Refused) as top:
        B._model_of(b'{"model": "other", "model": "pinned-model"}', 'pinned-model')
    assert top.value.status == 400


def test_the_bearer_token_is_read_under_any_case_of_the_scheme_and_other_schemes_give_none():
    assert B._bearer(Req('Bearer abc')) == 'abc'
    assert B._bearer(Req('bearer abc')) == 'abc'
    assert B._bearer(Req('Basic abc')) is None
    assert B._bearer(Req(None)) is None


def test_an_empty_bearer_token_is_not_a_grant_because_authorize_refuses_it_like_none():
    assert B._bearer(Req('Bearer ')) == ''
    stub = SimpleNamespace(_lock=threading.Lock(), _grants={})
    for token in ('', None):
        with pytest.raises(B.Refused) as refused:
            B.Broker.authorize(stub, token, 'principal')
        assert refused.value.status == 401
