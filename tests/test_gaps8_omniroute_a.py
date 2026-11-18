"""T-1328: claude_sessions/omniroute.py lines 56-123 (prepare_launch: refusals and
their order before the session opens); candidate gaps, not coverage.

Ranked final probes (denial/fail-closed first, then boundaries, then error paths):
1  :99-103   test_unreachable_provider_refused_before_env_built      (closest: test_omniroute.py fails_before_the_session_opens)
2  :111-116  test_failover_start_failure_refused_before_env_built   (closest: none; provider_env never reached)
3  :104-108  test_gateway_start_failure_refused_with_gateway_prefix (closest: none)
4  :95-98    test_omniroute_daemon_failure_refused_before_probe     (closest: test_omniroute.py ensure_running_failure_propagates)
5  :99       test_gateway_profile_skips_reachability_probe          (closest: none; generic tests only)
6  :118-122  test_omniroute_model_missing_lists_available_ids       (closest: test_omniroute.py unknown_model_raises_valueerror)
7  :118      test_auto_model_never_consults_catalogue               (closest: test_omniroute.py unknown_model_raises_valueerror)
8  :119-120  test_empty_catalogue_does_not_block_a_model            (closest: generic-only does_not_validate test)
9  :90-91    test_missing_profile_returns_empty_without_side_effects (closest: none)
10 :117,123  test_falsy_env_values_dropped_and_warning_returned      (closest: test_omniroute.py provider_env filters empties; does not reach line 117)

Seams: monkeypatched omniroute.is_reachable, omniroute.ensure_running,
omniroute.list_models, config.provider_env, gateway.ensure_running,
failover.enabled and failover.ensure_running with recording fakes. Synthetic
profile dicts only; no network, no subprocess, no real settings or home reads.
context_warning is real (pure function).
"""

import pytest

from claude_sessions import config as c
from claude_sessions import failover
from claude_sessions import gateway
from claude_sessions import omniroute


@pytest.fixture
def seams(monkeypatch):
    rec = {'reach': [], 'ensure': [], 'list': [], 'env': [], 'gw': [], 'fo': []}

    def fake_reach(*a, **k):
        rec['reach'].append(a)
        return rec.get('reach_ret', True)

    def fake_ensure(*a, **k):
        rec['ensure'].append(a)
        return rec.get('ensure_ret', (True, 'running'))

    def fake_list(*a, **k):
        rec['list'].append(a)
        return rec.get('catalogue', [])

    def fake_env(prof, model=None):
        rec['env'].append((prof, model))
        return rec.get('env_ret', {'ANTHROPIC_BASE_URL': 'http://h'})

    def fake_gw(prof):
        rec['gw'].append(prof)
        return rec.get('gw_ret', (True, 'up'))

    def fake_fo(prof):
        rec['fo'].append(prof)
        return rec.get('fo_ret', (True, 'up'))

    monkeypatch.setattr(omniroute, 'is_reachable', fake_reach)
    monkeypatch.setattr(omniroute, 'ensure_running', fake_ensure)
    monkeypatch.setattr(omniroute, 'list_models', fake_list)
    monkeypatch.setattr(c, 'provider_env', fake_env)
    monkeypatch.setattr(gateway, 'ensure_running', fake_gw)
    monkeypatch.setattr(failover, 'enabled', lambda prof: rec.get('fo_enabled', False))
    monkeypatch.setattr(failover, 'ensure_running', fake_fo)
    return rec


def _generic(**over):
    return c.new_profile(**{'id': 'p', 'kind': 'generic', 'base_url': 'http://h', **over})


def test_unreachable_provider_refused_before_env_built(seams):
    seams['reach_ret'] = False
    with pytest.raises(RuntimeError, match='http://dead:1'):
        omniroute.prepare_launch('m', _generic(base_url='http://dead:1'))
    assert seams['env'] == []
    assert seams['gw'] == [] and seams['fo'] == []


def test_failover_start_failure_refused_before_env_built(seams):
    seams['fo_enabled'] = True
    seams['fo_ret'] = (False, 'port taken')
    with pytest.raises(RuntimeError, match=r'^Failover proxy: port taken$'):
        omniroute.prepare_launch('m', _generic())
    assert seams['env'] == []


def test_gateway_start_failure_refused_with_gateway_prefix(seams):
    seams['gw_ret'] = (False, 'port busy')
    prof = _generic(gateway_kind='openai')
    with pytest.raises(RuntimeError, match=r'^Gateway: port busy$'):
        omniroute.prepare_launch('m', prof)
    assert seams['gw'] == [prof]
    assert seams['env'] == []
    assert seams['fo'] == []


def test_omniroute_daemon_failure_refused_before_probe(seams):
    seams['ensure_ret'] = (False, 'daemon dead')
    with pytest.raises(RuntimeError, match=r'^OmniRoute: daemon dead$'):
        omniroute.prepare_launch('auto/coding', c.new_profile(id='p', kind='omniroute'))
    assert seams['reach'] == []
    assert seams['env'] == []


def test_gateway_profile_skips_reachability_probe(seams):
    prof = _generic(gateway_kind='openai')
    env, warn = omniroute.prepare_launch('m', prof)
    assert seams['reach'] == []
    assert len(seams['gw']) == 1
    assert env == {'ANTHROPIC_BASE_URL': 'http://h'}
    assert warn == ''


def test_omniroute_model_missing_lists_available_ids(seams):
    seams['catalogue'] = [('free/x', 'X'), ('free/y', 'Y')]
    prof = c.new_profile(id='p', kind='omniroute', base_url='http://127.0.0.1:20128')
    with pytest.raises(ValueError) as exc:
        omniroute.prepare_launch('gone/model', prof)
    msg = str(exc.value)
    assert "'gone/model'" in msg
    assert "['free/x', 'free/y']" in msg


def test_auto_model_never_consults_catalogue(seams):
    prof = c.new_profile(id='p', kind='omniroute', base_url='http://127.0.0.1:20128')
    env, _warn = omniroute.prepare_launch(omniroute.AUTO_MODEL, prof)
    assert seams['list'] == []
    assert env == {'ANTHROPIC_BASE_URL': 'http://h'}


def test_empty_catalogue_does_not_block_a_model(seams):
    seams['catalogue'] = []
    prof = c.new_profile(id='p', kind='omniroute', base_url='http://127.0.0.1:20128')
    env, _warn = omniroute.prepare_launch('free/anything', prof)
    assert len(seams['list']) == 1
    assert env == {'ANTHROPIC_BASE_URL': 'http://h'}


@pytest.mark.parametrize('prof', [None, {}])
def test_missing_profile_returns_empty_without_side_effects(seams, prof):
    assert omniroute.prepare_launch('m', prof) == ({}, '')
    assert seams['reach'] == [] and seams['ensure'] == []
    assert seams['env'] == [] and seams['gw'] == [] and seams['fo'] == []


def test_falsy_env_values_dropped_and_warning_returned(seams):
    seams['env_ret'] = {'ANTHROPIC_BASE_URL': 'http://h', 'EMPTY': '',
                        'NONE': None, 'ZERO': 0, 'KEEP': 'v'}
    env, warn = omniroute.prepare_launch('m', _generic(), ctx_bytes=40000)
    assert env == {'ANTHROPIC_BASE_URL': 'http://h', 'KEEP': 'v'}
    assert 'tokens of context' in warn
