"""T-1431: the account and vocabulary checks of archeus/core/application/sessions.py,
lines 55-78 and 249-251 at tip 026ea58e: _account_of, _vocabulary, _live_homes. Ranked,
denial and fail-closed first:

1. 63-64 _account_of: account_id None returns None and loads no Account row.
2. 66-67 _account_of: an account of another harness raises 'account <id> is not a <harness> account'.
3. 68-69 _account_of: a DISABLED account raises 'account <id> is disabled'.
4. 66 before 68 _account_of: a mismatched disabled account reports the harness error.
5. 70 _account_of: a matching, not-disabled account is returned itself, for every
   health the attention path reads (UNAUTHENTICATED, LIMITED, OPEN).
6. 76-77 _vocabulary: a value in `offered` is returned unchanged.
7. 76-77 _vocabulary: a truthy value not in `offered` raises '<harness> does not offer
   <what> <value!r>' and is never translated.
8. 76 _vocabulary: an empty `offered` still refuses a truthy value.
9. 78 _vocabulary: None and '' return None, with no refusal even when `offered` is empty.
10. 250-251 _live_homes: returns resources.bound_homes(tx.conn, tx.live) unchanged.

Fakes: lifecycle.load (the module sessions.py imports) is replaced; resources.bound_homes
is replaced at its module attribute because _live_homes imports resources inside the function.
"""

import types

import pytest

from archeus.core.application import lifecycle, resources
from archeus.core.application import sessions as S


def _account(harness_id='claude', health='OPEN', aid='acc_1'):
    return types.SimpleNamespace(id=aid, harness_id=harness_id, health=health)


@pytest.fixture
def loads(monkeypatch):
    seen = []
    state = {'entity': None}

    def load(tx, cls, eid):
        seen.append((cls, eid))
        if state['entity'] is None:
            raise AssertionError('lifecycle.load must not be called')
        return types.SimpleNamespace(entity=state['entity'])
    monkeypatch.setattr(lifecycle, 'load', load)
    return types.SimpleNamespace(seen=seen, state=state)


def test_account_of_none_returns_none_and_loads_nothing(loads):
    assert S._account_of(None, None, 'claude') is None
    assert loads.seen == []


def test_account_of_another_harness_is_refused_by_name(loads):
    loads.state['entity'] = _account(harness_id='pi')
    with pytest.raises(ValueError) as e:
        S._account_of(None, 'acc_1', 'claude')
    assert str(e.value) == 'account acc_1 is not a claude account'


def test_account_of_a_disabled_account_is_refused_by_name(loads):
    loads.state['entity'] = _account(health='DISABLED')
    with pytest.raises(ValueError) as e:
        S._account_of(None, 'acc_1', 'claude')
    assert str(e.value) == 'account acc_1 is disabled'


def test_account_of_reports_the_harness_error_before_the_disabled_one(loads):
    loads.state['entity'] = _account(harness_id='pi', health='DISABLED')
    with pytest.raises(ValueError) as e:
        S._account_of(None, 'acc_1', 'claude')
    assert str(e.value) == 'account acc_1 is not a claude account'


@pytest.mark.parametrize('health', ['UNAUTHENTICATED', 'LIMITED', 'OPEN'])
def test_account_of_returns_a_matching_account_that_is_not_disabled(loads, health):
    acc = _account(health=health)
    loads.state['entity'] = acc
    assert S._account_of(None, 'acc_1', 'claude') is acc


def test_vocabulary_returns_a_value_the_harness_offers_unchanged():
    assert S._vocabulary('opus', ('opus', 'sonnet'), 'model', 'claude') == 'opus'


@pytest.mark.parametrize('offered', [('opus', 'sonnet'), ()], ids=['offered', 'none-offered'])
def test_vocabulary_refuses_a_value_not_offered_and_never_translates_it(offered):
    with pytest.raises(ValueError) as e:
        S._vocabulary('gpt-x', offered, 'model', 'claude')
    assert str(e.value) == "claude does not offer model 'gpt-x'"


@pytest.mark.parametrize('value', [None, ''], ids=['none', 'empty'])
def test_vocabulary_maps_none_and_empty_to_none_even_with_nothing_offered(value):
    assert S._vocabulary(value, (), 'model', 'claude') is None


def test_live_homes_returns_bound_homes_of_the_live_connection_unchanged(monkeypatch):
    calls = []
    sentinel = object()
    monkeypatch.setattr(resources, 'bound_homes',
                        lambda conn, live: calls.append((conn, live)) or sentinel)
    tx = types.SimpleNamespace(conn='conn_x', live='live_y')
    assert S._live_homes(tx) is sentinel
    assert calls == [('conn_x', 'live_y')]
