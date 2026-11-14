"""T-1266 — close the highest-risk test gaps in claude_sessions/config.py,
lines 426-717 inclusive (tip 6bbd3b44; re-located by reading the source, the
card's line numbers came from an older tip, and the file is 1571 lines at this
worktree's tip).

Slice: `load_settings`, `migrate_settings` and its helpers, the provider
profile readers and the port allocator, `effective_perm`, `launch_defaults`,
and the hidden-project helpers.

Selected branches, denial/fail-closed first, then boundaries, then error paths:

 1. :625  a missing or unknown requested profile id is None even while a valid
          active profile exists; no fallback to another credential
 2. :675  every non-auto mode passes through a routed or unsupported model;
          auto is suppressed only for a routed provider or an exact unsupported
          model id
 3. :699  an explicit empty project permission beats account auto, a project
          plan wins, and the model is the account's, never the project pin
 4. :483  partly migrated legacy settings are renamed and folded into one
          profile in one call; the credential is carried, unknown keys stay
 5. :498  existing profiles block a second profile, obsolete flat keys are
          removed, and a replay reports no change
 6. :502  the permission flip runs once; a later deliberate empty value and a
          project restriction both survive a second run
 7. :438  a saved false or empty value beats the default; an unknown key is
          parked for round-trip and never becomes an active option
 8. :435  two loads of a missing file do not share a default list container
 9. :616  a malformed provider container and entries without an id are skipped;
          every returned profile gets its own default list
10. :647  occupied failover ports are skipped in steps of two; a stored even
          port whose gateway collides with a fresh allocation is a strict xfail

Closest existing tests: tests/test_providers.py (the flat-to-profile fold, the
dead-name drop, the replay of one migration, the deleted-profile rule and the
four-profile allocation sequence) and tests/test_config.py (a settings
round-trip, unknown keys dropped from the active set, a corrupt file and the
no-shared-default dict). These probes pin the cases those leave open: the
partly migrated state, the existing-profile replay, the once-only permission
flag, the falsy saved values, the list containers, the malformed container and
the stored-port collision.

Seams: `config.settings_file` points at a file under tmp_path, `uuid.uuid4` is
fixed, and no test reads the real account, the real settings file or the
environment.
"""

import json
import uuid
from types import SimpleNamespace

import pytest

from claude_sessions import config as c


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    p = tmp_path / 'archeus.json'
    monkeypatch.setattr(c, 'settings_file', str(p))
    return p


@pytest.fixture
def fixed_ids(monkeypatch):
    monkeypatch.setattr(uuid, 'uuid4', lambda: SimpleNamespace(hex='feedbeef' + '0' * 24))


def write(path, obj):
    path.write_text(json.dumps(obj), encoding='utf-8')


def done(extra):
    s = {'provider_keys_migrated': True, 'provider_profiles_migrated': True}
    s.update(extra)
    return s


def test_an_unknown_or_empty_requested_profile_is_none_beside_a_valid_active_one():
    s = {'providers': [{'id': 'p1', 'name': 'One', 'base_url': 'http://a'}],
         'provider_active': 'p1'}
    assert c.active_provider(s)['id'] == 'p1'
    assert c.provider_profile('p1', s)['id'] == 'p1'
    assert c.provider_profile('zz', s) is None
    assert c.provider_profile('p', s) is None
    assert c.provider_profile('', s) is None
    assert c.provider_profile(None, s) is None


@pytest.mark.parametrize('perm', ['plan', 'acceptEdits', 'bypassPermissions', 'default', ''])
def test_every_non_auto_mode_passes_through_even_where_auto_is_suppressed(perm):
    assert c.effective_perm(perm, model='claude-haiku-4-5', routed='http://gw') == perm


def test_auto_is_suppressed_only_for_a_routed_provider_or_an_exact_unsupported_model():
    assert c.effective_perm('auto', routed='http://gw') == ''
    assert c.effective_perm('auto', model='claude-haiku-4-5') == ''
    assert c.effective_perm('auto', model='claude-haiku-4-5-extra') == 'auto'
    assert c.effective_perm('auto', model='claude-opus-4-7') == 'auto'
    assert c.effective_perm('auto') == 'auto'


def test_an_explicit_empty_project_permission_beats_account_auto_and_a_plan_wins(settings_path):
    write(settings_path, {
        'default_model': 'claude-opus-4-7', 'default_permission': 'auto',
        'project_defaults': {'D--x': {'permission': '', 'model': 'claude-haiku-4-5'},
                             'D--y': {'permission': 'plan', 'model': 'claude-haiku-4-5'}}})
    assert c.launch_defaults('D--x') == ('claude-opus-4-7', '')
    assert c.launch_defaults('D--y') == ('claude-opus-4-7', 'plan')
    assert c.launch_defaults('D--z') == ('claude-opus-4-7', 'auto')


def test_partly_migrated_legacy_settings_are_renamed_then_folded_in_one_call(fixed_ids):
    s = {c._UNKNOWN_KEYS: {
        'omniroute_base_url': 'http://o:20128',
        'omniroute_api_key': 'sk-synth',
        'omniroute_exec_model': 'auto/coding',
        'future_key': 'keep'}}
    out, changed = c.migrate_settings(s)
    assert changed
    prof = out['providers'][0]
    assert prof['kind'] == 'omniroute'
    assert prof['name'] == 'OmniRoute'
    assert prof['base_url'] == 'http://o:20128'
    assert prof['api_key'] == 'sk-synth'
    assert prof['model'] == 'auto/coding'
    assert out['provider_active'] == prof['id']
    assert out[c._UNKNOWN_KEYS] == {'future_key': 'keep'}
    assert 'provider_api_key' not in out


def test_existing_profiles_block_a_second_one_and_obsolete_keys_go_once(fixed_ids):
    existing = {'id': 'p1', 'name': 'Mine', 'kind': 'generic', 'base_url': 'http://a'}
    s = {'provider_keys_migrated': True, 'providers': [existing],
         'provider_active': 'p1', 'provider_kind': 'generic',
         'provider_base_url': 'http://b', 'provider_api_key': 'sk-synth',
         'failover_port': 20131, 'gateway_port': 20132, 'headless_provider': True}
    out, changed = c.migrate_settings(s)
    assert changed
    assert out['providers'] == [existing]
    assert out['provider_active'] == 'p1'
    for dead in ('provider_kind', 'provider_base_url', 'provider_api_key',
                 'failover_port', 'gateway_port', 'headless_provider'):
        assert dead not in out
        assert dead not in out.get(c._UNKNOWN_KEYS, {})
    again, changed_again = c.migrate_settings(out)
    assert not changed_again
    assert again['providers'] == [existing]


def test_the_permission_flip_runs_once_and_later_deliberate_values_survive():
    out, changed = c.migrate_settings(done({
        'default_permission': '',
        'project_defaults': {'D--a': {'permission': ''},
                             'D--b': {'permission': 'plan'}}}))
    assert changed
    assert out['default_permission'] == 'auto'
    assert out['project_defaults']['D--a']['permission'] == 'auto'
    assert out['project_defaults']['D--b']['permission'] == 'plan'

    out['default_permission'] = ''
    out['project_defaults']['D--a']['permission'] = ''
    again, changed_again = c.migrate_settings(out)
    assert not changed_again
    assert again['default_permission'] == ''
    assert again['project_defaults']['D--a']['permission'] == ''
    assert again['project_defaults']['D--b']['permission'] == 'plan'


def test_saved_falsy_values_beat_defaults_and_unknown_keys_stay_parked(settings_path):
    write(settings_path, {'default_permission': '', 'memory_to_claudemd': False,
                          'future_flag': True})
    s = c.load_settings()
    assert s['default_permission'] == ''
    assert s['memory_to_claudemd'] is False
    assert 'future_flag' not in s
    assert s[c._UNKNOWN_KEYS] == {'future_flag': True}
    assert c._DEFAULT_SETTINGS['default_permission'] == 'auto'


def test_loads_of_a_missing_file_do_not_share_default_list_containers(settings_path):
    assert not settings_path.exists()
    first = c.load_settings()
    second = c.load_settings()
    first['harnesses_disabled'].append('pi')
    first['project_defaults']['D--x'] = {'hidden': True}
    assert second['harnesses_disabled'] == []
    assert second['project_defaults'] == {}
    assert c._DEFAULT_SETTINGS['harnesses_disabled'] == []


def test_malformed_provider_containers_and_idless_entries_are_skipped(fixed_ids):
    assert c.provider_profiles({'providers': 'nope'}) == []
    assert c.provider_profiles({'providers': {'id': 'p1'}}) == []
    raw = {'providers': [{'name': 'no id'}, 'text', None, {'id': 'p1', 'name': 'One'}]}
    profs = c.provider_profiles(raw)
    assert [p['id'] for p in profs] == ['p1']
    assert profs[0]['failover_models'] == [] and profs[0]['port'] == 0
    profs[0]['failover_models'].append('m')
    assert c.provider_profiles(raw)[0]['failover_models'] == []


def test_occupied_failover_ports_are_skipped_in_steps_of_two():
    base = c.PROFILE_PORT_BASE
    assert base == 20129
    assert c.free_profile_port({'providers': []}) == base
    assert c.free_profile_port({'providers': [{'id': 'a', 'port': base}]}) == base + 2
    assert c.free_profile_port({'providers': [{'id': 'a', 'port': base},
                                              {'id': 'b', 'port': base + 2}]}) == base + 4
    assert c.free_profile_port({'providers': [{'id': 'a', 'port': base + 2}]}) == base
    assert c.free_profile_port({'providers': [{'id': 'a', 'port': None}]}) == base


def test_an_odd_stored_port_never_makes_a_new_gateway_collide():
    base = c.PROFILE_PORT_BASE
    s = {'providers': [{'id': 'a', 'port': base + 2}]}
    new = c.free_profile_port(s)
    taken = {base + 2, c.gateway_port_of({'port': base + 2})}
    assert new not in taken and c.gateway_port_of({'port': new}) not in taken


@pytest.mark.xfail(
    strict=True,
    reason="claude_sessions/config.py:647-651 free_profile_port checks failover "
           "ports only: a stored even port 20130 owns gateway 20131, the next "
           "free failover port 20129 has gateway 20130, which is the stored "
           "profile's failover port")
def test_a_stored_even_port_does_not_let_a_new_gateway_collide():
    base = c.PROFILE_PORT_BASE
    s = {'providers': [{'id': 'a', 'port': base + 1}]}
    new = c.free_profile_port(s)
    taken = {base + 1, base + 2}
    assert new not in taken
    assert c.gateway_port_of({'port': new}) not in taken
