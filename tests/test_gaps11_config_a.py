"""Legacy provider fold and profile builder of claude_sessions/config.py (lines 538-603)."""
import re

import pytest

from claude_sessions import config as c


@pytest.fixture(autouse=True)
def fixed_port(monkeypatch):
    monkeypatch.setattr(c, 'free_profile_port', lambda s=None: 8123)


def test_no_kind_folds_nothing_even_with_url_and_model():
    s = {'providers': [], 'provider_base_url': 'http://h:1', 'provider_exec_model': 'm',
         'provider_api_key': 'sk-synth'}
    c._migrate_to_profiles(s)
    assert s['providers'] == []
    assert 'provider_active' not in s
    for dead in ('provider_base_url', 'provider_exec_model', 'provider_api_key'):
        assert dead not in s


def test_existing_providers_still_consume_flat_keys_silently():
    existing = {'id': 'p1', 'name': 'Mine', 'kind': 'generic', 'base_url': 'http://a'}
    s = {'providers': [existing], 'provider_active': 'p1',
         'provider_kind': 'generic', 'provider_base_url': 'http://b'}
    c._migrate_to_profiles(s)
    assert s['providers'] == [existing]
    assert s['provider_active'] == 'p1'
    assert 'provider_kind' not in s and 'provider_base_url' not in s
    assert 'provider_base_url' not in s.get(c._UNKNOWN_KEYS, {})


def test_take_flat_pops_parked_copy_when_no_top_level_value():
    s = {c._UNKNOWN_KEYS: {'provider_base_url': 'http://p'}}
    assert c._take_flat(s, 'provider_base_url') == 'http://p'
    assert 'provider_base_url' not in s[c._UNKNOWN_KEYS]


def test_take_flat_pops_both_top_level_and_parked_copies():
    s = {c._UNKNOWN_KEYS: {'omniroute_base_url': 'http://o', 'provider_base_url': 'http://p'}}
    out, _changed = c.migrate_settings(s)
    assert 'provider_base_url' not in out[c._UNKNOWN_KEYS]


def test_profile_name_fallback_provider_and_host():
    no_url = {'providers': [], 'provider_kind': 'generic', 'provider_exec_model': 'm'}
    c._migrate_to_profiles(no_url)
    assert no_url['providers'][0]['name'] == 'Provider'

    with_url = {'providers': [], 'provider_kind': 'generic', 'provider_exec_model': 'm',
                'provider_base_url': 'http://127.0.0.1:11434/v1'}
    c._migrate_to_profiles(with_url)
    assert with_url['providers'][0]['name'] == '127.0.0.1'


def test_omniroute_name_ignores_url():
    with_url = {'providers': [], 'provider_kind': 'omniroute',
                'provider_base_url': 'http://box:20128', 'provider_exec_model': 'auto/x'}
    c._migrate_to_profiles(with_url)
    assert with_url['providers'][0]['name'] == 'OmniRoute'

    bare = {'providers': [], 'provider_kind': 'omniroute'}
    c._migrate_to_profiles(bare)
    assert bare['providers'][0]['name'] == 'OmniRoute'


def test_headless_flag_sets_id_only_when_true():
    on = {'providers': [], 'provider_kind': 'generic', 'headless_provider': True}
    c._migrate_to_profiles(on)
    assert on['headless_provider_id'] == on['providers'][0]['id']
    assert 'headless_provider' not in on

    off = {'providers': [], 'provider_kind': 'generic', 'headless_provider': False}
    c._migrate_to_profiles(off)
    assert 'headless_provider_id' not in off


def test_profile_port_from_free_port_and_model_from_exec_model():
    s = {'providers': [], 'provider_kind': 'generic', 'provider_base_url': 'http://h:1',
         'provider_exec_model': 'qwen-x'}
    c._migrate_to_profiles(s)
    prof = s['providers'][0]
    assert prof['port'] == 8123
    assert prof['model'] == 'qwen-x'
    assert prof['kind'] == 'generic'
    assert prof['base_url'] == 'http://h:1'
    assert s['provider_active'] == prof['id']


def test_new_profile_drops_unknown_keys():
    p = c.new_profile(name='Mine', bogus=1, model='m')
    assert 'bogus' not in p
    assert p['name'] == 'Mine'
    assert p['model'] == 'm'
    assert set(p) == set(c.PROFILE_FIELDS)


def test_new_profile_id_generated_only_when_blank():
    assert re.fullmatch(r'[0-9a-f]{8}', c.new_profile()['id'])
    assert c.new_profile(id='abc123')['id'] == 'abc123'
    assert re.fullmatch(r'[0-9a-f]{8}', c.new_profile(id='')['id'])


def test_new_profile_defaults_do_not_alias_lists():
    a = c.new_profile()
    b = c.new_profile()
    assert a['failover_models'] is not b['failover_models']
    a['failover_models'].append('m-1')
    assert b['failover_models'] == []
    assert c.PROFILE_FIELDS['failover_models'] == []
