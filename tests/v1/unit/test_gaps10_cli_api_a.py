"""T-1388: the highest-risk uncovered branches of `archeus/cli/_api.py` lines 12-111
(`_q`, `_path`, and the builders `metrics_days`, `usage_by`, `list_missions`, `events`,
`get_mission`, `revoke_device`, `reprioritise_mission`), as tests.

Selected branches, denial and fail-closed first:
- `_q` returns no '?' when every value is None (`list_missions()`, `events()`, `usage_by()`),
  and drops a None in the middle while keeping 0 and False (`events(after=0, limit=None)`,
  `list_missions(state=False)`).
- `metrics_days`, `usage_by` and `events` are keyword-only: a positional call raises
  TypeError before any URL is built.
- `_path` quotes '?', ' ' and non-ASCII into the one segment, never a second segment or a
  query (`get_mission('a b?c')`, `get_mission('mis_é')`), and does not re-substitute a literal
  '{id}' carried inside an id (`get_mission('{id}')`).
- `_q` percent-encodes '+' so a form decoder does not read it as a space (`events(after='a+b')`).
- `revoke_device('a/../b')` keeps the id inside one segment of the device route.

Not selected, with reasons: an id of '..' and an empty id (`_path`, line 17-19). The empty id
is pinned on purpose by tests/v1/unit/test_gaps_cli_api.py
(`test_an_empty_id_is_its_own_path_and_never_the_list_route`), and the server answers '..'
with no 500 (tests/v1/integration/test_api_errors.py PATH_JUNK), so a builder refusal is not a
justified premise. The id-None TypeError, the '&'/'=' query escape, the route spelling of
`reprioritise_mission` and the zero filter are already asserted in test_gaps_cli_api.py.

Each test names the source branch whose removal or inversion it catches. No network, no
socket, no HTTP, no filesystem: the builders are pure string functions.
"""

import pytest

from archeus.cli._api import endpoints


def test_a_builder_with_every_filter_none_has_no_question_mark():
    # _api.py:12-14 `if q` in _q: an all-None filter list must not leave a bare '?'
    assert endpoints.list_missions() == '/v1/missions'
    assert endpoints.events() == '/v1/events'
    assert endpoints.usage_by() == '/v1/usage'


def test_a_none_in_the_middle_is_dropped_and_zero_stays():
    # _api.py:13 `if v is not None`: the None limit goes, the 0 after stays, in order
    assert endpoints.events(after=0, limit=None) == '/v1/events?after=0'


def test_false_is_a_value_and_survives_the_absence_filter():
    # _api.py:13: False is not None, so it is kept (as 'False'); only None is absent
    assert endpoints.list_missions(state=False) == '/v1/missions?state=False'


@pytest.mark.parametrize('call', [
    lambda: endpoints.metrics_days(7),
    lambda: endpoints.usage_by('project'),
    lambda: endpoints.events('5'),
], ids=['metrics_days', 'usage_by', 'events'])
def test_a_positional_filter_is_refused_before_any_url_is_built(call):
    # _api.py:30, 34, 90 `*`: a positional filter would be read as the wrong parameter,
    # so the signature refuses it with TypeError and no path string is returned
    with pytest.raises(TypeError):
        call()


def test_a_question_mark_or_space_in_an_id_stays_inside_its_segment():
    # _api.py:17-19 `quote(id_, safe='')`: '?' and ' ' become %3F and %20, so no
    # query begins inside the id and no second path segment appears
    got = endpoints.get_mission('a b?c')
    assert got == '/v1/missions/a%20b%3Fc'
    assert '?' not in got and ' ' not in got


def test_a_non_ascii_id_is_percent_encoded_as_utf8():
    # _api.py:17-19: the quote call encodes the id; a raw non-ASCII byte in a URL is
    # not a valid request target, so the segment is the UTF-8 percent form
    assert endpoints.get_mission('mis_é') == '/v1/missions/mis_%C3%A9'


def test_a_literal_placeholder_inside_an_id_is_not_substituted_again():
    # _api.py:17-19: `partition('{id}')` runs on the route template, never on the id, so
    # an id that spells '{id}' is one encoded segment and not a second substitution
    assert endpoints.get_mission('{id}') == '/v1/missions/%7Bid%7D'


def test_a_plus_in_a_query_value_is_encoded_not_read_as_a_space():
    # _api.py:14 `quote_via=quote`: a '+' left raw is decoded back to a space by a
    # form-style parser; quote() must send it as %2B
    assert endpoints.events(after='a+b') == '/v1/events?after=a%2Bb'


def test_a_device_id_with_dot_segments_stays_one_segment_of_the_device_route():
    # _api.py:102-103 revoke_device: 'a/../b' is one encoded segment, so the request goes to
    # the revoke route of that one device and cannot climb to another route family
    got = endpoints.revoke_device('a/../b')
    assert got == '/v1/devices/a%2F..%2Fb/revoke'
    assert got.split('/') == ['', 'v1', 'devices', 'a%2F..%2Fb', 'revoke']
