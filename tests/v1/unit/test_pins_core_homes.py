"""T-834: pins for archeus/core/homes.py branches the existing suite leaves
uncovered (mutation-proven against a scratch copy of the module; see
/work/QWEN-DONE-T-834.md). Each test names one condition and fails when that
condition is removed, inverted or loosened. No disk, no network, no Windows
API: every short-name probe is injected."""

from archeus.core import homes as H


def _no_shorts(_prefix):
    return None


def test_norm_path_gives_a_bare_drive_its_root_slash():
    assert H.norm_path('C:/a/..', path_flavour='windows') == 'c:/'


def test_comp_uses_no_form_for_a_missing_or_empty_short_name():
    assert H._comp('a') == '(?:a)'
    assert H._comp('a', short='') == '(?:a)'
    assert H._comp('a', short='a') == '(?:a)'


def test_non_string_and_blank_home_entries_are_dropped_without_failing():
    h = H.Homes(['', '   ', 5, None, '/srv/keep'],
                [('h', 'hk:/k/e', 7), ('h', 'hk2:/k/e', None),
                 ('h', 'hk3:/k/e', '  '), ('h', 'hk4:/k/e', '/srv/keep')],
                shorts=_no_shorts)
    assert H.scrub_text('/srv/keep/x', h) == 'its home/x'


def test_default_accounts_are_never_probed_for_short_names():
    probed = []
    H.Homes(['d:/reg/home/x'], [('hh', 'hh:/k/e', 'c:/usr/relhome')],
            shorts=lambda p: probed.append(p) or None)
    assert probed == ['d:/reg', 'd:/reg/home', 'd:/reg/home/x']


def test_relative_value_survives_path_keys_when_a_home_never_normalizes():
    h = H.Homes(['C:foo'], shorts=_no_shorts)
    assert H.public_value({'ref': 'rel/x'}, h, path_keys=('ref',)) == {'ref': 'rel/x'}


def test_the_longer_default_key_wins_over_its_shorter_prefix_key():
    short_key, long_key = 'hc:/a', 'hc:/a b'
    rows = [('h', short_key, 'c:/a/b'), ('h', long_key, 'c:/a/b')]
    h = H.Homes([], rows, shorts=_no_shorts)
    assert H.scrub_text(long_key, h) == H.public_account_id(long_key)
    assert H.scrub_text(short_key, h) == H.public_account_id(short_key)


def test_public_value_recurses_into_tuples_not_only_lists():
    key = 'hh:c:/acct/home'
    h = H.Homes([], [('h', key, None)], shorts=_no_shorts)
    out = H.public_value({'a': (key, 'plain'), 'b': [key]}, h)
    assert out == {'a': [H.public_account_id(key), 'plain'],
                   'b': [H.public_account_id(key)]}


def test_public_value_maps_a_key_value_with_surrounding_space():
    key = 'hh:c:/acct/home'
    h = H.Homes([], [('h', key, None)], shorts=_no_shorts)
    assert H.public_value({'account': '  ' + key + ' '}, h) \
        == {'account': H.public_account_id(key)}


def test_public_value_nulls_only_real_homes_under_path_keys():
    h = H.Homes(['/home/mab/.claude'], shorts=_no_shorts)
    assert H.public_value({'ref': 'D:/elsewhere/file.txt'}, h, path_keys=('ref',)) \
        == {'ref': 'D:/elsewhere/file.txt'}
    assert H.public_value({'ref': '/home/mab/.claude'}, h, path_keys=('ref',)) \
        == {'ref': None}
