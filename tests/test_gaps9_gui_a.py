"""T-1363: highest-risk test gaps in claude_sessions/gui.py lines 182-237.

Source slice: claude_sessions/gui.py:182-237, _clean_profile (card tip 10d688c0;
re-located at worktree tip 76edd1f6, same lines, same content). No source edit.

Ranked candidate probes, denial and fail-closed first. Closest existing test is in
tests/test_gui.py (test_a_profile_url_must_be_http, test_editing_a_profile_keeps_a_key_the_form_never_saw,
test_provider_save_roundtrip) unless noted. These are candidates, not measured coverage.
 1. 202-205 base_url: '//host', 'https://' and 'javascript:' refused, blank kept empty.
            closest: test_a_profile_url_must_be_http (file:, javascript:, ftp: over HTTP only)
 2. 207-209 kind matched exactly after trimming: 'OmniRoute' refused, ' omniroute ' accepted.
            closest: test_a_profile_url_must_be_http ('wat' only)
 3. 210-212 blank name refused after trimming; the name is capped at 60 characters.
            closest: test_a_profile_url_must_be_http (blank name, no cap)
 4. 213-215 gateway_kind: 'anthropic' refused, ' openai ' accepted, '' accepted.
            closest: none (gateway_kind never refused in tests/test_gui.py)
 5. 235-236 a blank secret keeps prev; a given secret replaces it.
            closest: test_editing_a_profile_keeps_a_key_the_form_never_saw (keep only, over HTTP)
 6. 233     the port is never taken from the body; prev port kept, 0 for a new profile.
            closest: test_provider_save_roundtrip (allocated on create only)
 7. 224     context_tokens clamped to 0..10000000 (negative, huge, string, blank).
            closest: none
 8. 227-228 gateway_target_base_url may be blank; non-http refused with the field name.
            closest: none (label check in tests/test_content_grid.py only)
 9. 224     PREMISE REWRITTEN: non-numeric context_tokens raises ValueError, not
            BadRequest. The premise that the caller sees a 500 is wrong: the HTTP
            dispatch maps every ValueError to 400 (claude_sessions/gui.py:680).
            closest: none
10. 220     PREMISE, strict xfail: body id overrides prev id. Latent: the endpoint
            looks prev up by the same body id (gui.py:246), so only a direct
            _clean_profile call reaches it.
            closest: none

Probe -> branch caught:
 test_base_url_must_be_http_with_a_host                  scheme and hostname test, lines 202-204
 test_kind_is_exact_after_trimming                       kind allow-list, lines 207-209
 test_name_is_required_and_capped_at_sixty               blank check and [:60], lines 210-212
 test_gateway_kind_is_empty_or_openai                    gateway allow-list, lines 213-215
 test_a_blank_secret_keeps_prev_and_a_given_one_replaces  secret or-fallback, lines 235-236
 test_port_never_comes_from_the_body                     port from prev, line 233
 test_context_tokens_is_clamped                          max/min clamp, line 224
 test_gateway_target_url_may_be_blank_or_http            _url empty return and refusal, lines 227-228
 test_a_non_numeric_context_tokens_is_a_value_error      int() call, line 224
 test_an_edit_keeps_the_stored_id_when_the_body_names_another  id source, line 220 (xfail)
"""

import pytest

from claude_sessions import gui
from claude_sessions.gui_api import BadRequest


def _body(**over):
    b = {'name': 'Prov', 'kind': 'generic', 'base_url': 'http://h:1'}
    b.update(over)
    return b


@pytest.mark.parametrize('bad', ['//host', 'https://', 'http://', 'javascript:alert(1)'])
def test_base_url_must_be_http_with_a_host(bad):
    with pytest.raises(BadRequest, match='Base URL'):
        gui._clean_profile(_body(base_url=bad))


def test_base_url_is_trimmed_and_loses_its_trailing_slash():
    assert gui._clean_profile(_body(base_url='  https://h/  '))['base_url'] == 'https://h'
    assert gui._clean_profile(_body(base_url='   '))['base_url'] == ''


def test_kind_is_exact_after_trimming():
    assert gui._clean_profile(_body(kind=' omniroute '))['kind'] == 'omniroute'
    with pytest.raises(BadRequest, match='kind must be'):
        gui._clean_profile(_body(kind='OmniRoute'))
    with pytest.raises(BadRequest, match='kind must be'):
        gui._clean_profile(_body(kind=''))


def test_name_is_required_and_capped_at_sixty():
    with pytest.raises(BadRequest, match='needs a name'):
        gui._clean_profile(_body(name='   '))
    assert gui._clean_profile(_body(name=' x '))['name'] == 'x'
    assert len(gui._clean_profile(_body(name='n' * 61))['name']) == 60


def test_gateway_kind_is_empty_or_openai():
    assert gui._clean_profile(_body(gateway_kind=' openai '))['gateway_kind'] == 'openai'
    assert gui._clean_profile(_body(gateway_kind=''))['gateway_kind'] == ''
    with pytest.raises(BadRequest, match='gateway_kind must be'):
        gui._clean_profile(_body(gateway_kind='anthropic'))


def test_a_blank_secret_keeps_prev_and_a_given_one_replaces():
    prev = {'id': 'p1', 'port': 7, 'api_key': 'SYNTH-OLD', 'gateway_target_api_key': 'SYNTH-GW'}
    kept = gui._clean_profile(_body(id='p1', api_key='   ', gateway_target_api_key=None), prev)
    assert kept['api_key'] == 'SYNTH-OLD' and kept['gateway_target_api_key'] == 'SYNTH-GW'
    new = gui._clean_profile(_body(id='p1', api_key=' SYNTH-NEW '), prev)
    assert new['api_key'] == 'SYNTH-NEW' and new['gateway_target_api_key'] == 'SYNTH-GW'
    fresh = gui._clean_profile(_body())
    assert fresh['api_key'] == '' and fresh['gateway_target_api_key'] == ''


def test_port_never_comes_from_the_body():
    prev = {'id': 'p1', 'port': 4321}
    assert gui._clean_profile(_body(id='p1', port=9999), prev)['port'] == 4321
    assert gui._clean_profile(_body(port=9999))['port'] == 0


@pytest.mark.parametrize('raw, want', [(-5, 0), ('4096', 4096), (None, 0), ('', 0),
                                       (10 ** 9, 10_000_000), (10_000_000, 10_000_000)])
def test_context_tokens_is_clamped(raw, want):
    assert gui._clean_profile(_body(context_tokens=raw))['context_tokens'] == want


def test_gateway_target_url_may_be_blank_or_http():
    assert gui._clean_profile(_body(gateway_target_base_url=''))['gateway_target_base_url'] == ''
    assert gui._clean_profile(_body(gateway_target_base_url='http://g:2/'))[
        'gateway_target_base_url'] == 'http://g:2'
    with pytest.raises(BadRequest, match='Gateway target URL'):
        gui._clean_profile(_body(gateway_target_base_url='ftp://g'))


def test_a_non_numeric_context_tokens_is_a_value_error():
    with pytest.raises(ValueError):
        gui._clean_profile(_body(context_tokens='abc'))


@pytest.mark.xfail(strict=True, reason=(
    "claude_sessions/gui.py:220 body id overrides prev id in _clean_profile; "
    "latent, because _api_provider_save (gui.py:246) looks prev up by the same body id"))
def test_an_edit_keeps_the_stored_id_when_the_body_names_another():
    prof = gui._clean_profile(_body(id='new'), {'id': 'old', 'port': 3})
    assert prof['id'] == 'old'
