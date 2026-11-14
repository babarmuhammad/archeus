"""T-1423: claude_sessions/omniroute.py model classification, lines 212-282.

Ranked candidate branches, exclusion correctness first:
1. classify_models 262-264  combo owner and auto/ ids go to autos, never usable
2. classify_models 267-268  HALF_OPEN is not OPEN: the provider stays usable
3. classify_models 270      lockout matches root; an empty lockout model is ignored
4. classify_models 272-273  zero and missing context are both 'not a chat model'
5. classify_models 274-275  missing capabilities mean no tool support
6. classify_models 268-275  first matching exclusion reason wins
7. classify_models 279      sort: CLOSED first, then provider, then id
8. classify_models 257-260  None health and None entries give empty results
9. fetch_both 246-249       results keep catalog, health order when health finishes first
10. usable_models 237-238   unreachable catalog and empty health fail closed

Not written: KeyError on m['id'] (line 261), unreachable because catalog() keeps
only truthy ids. The UNKNOWN-provider case is pinned by tests/test_omniroute.py.
"""

import threading

from claude_sessions import omniroute


def _m(mid, owner='p', ctx=8000, caps=None, root=None):
    e = {'id': mid, 'owned_by': owner, 'name': mid,
         'capabilities': {'tool_calling': True} if caps is None else caps}
    if ctx is not None:
        e['context_length'] = ctx
    if root is not None:
        e['root'] = root
    return e


def _h(providers=(), lockouts=()):
    return {'providers': [{'name': n, 'state': s} for n, s in providers],
            'lockouts': list(lockouts), 'summary': {}}


def test_combo_and_auto_ids_never_usable():
    entries = [_m('combo-x', owner='combo'), _m('auto/fast')]
    usable, autos, excluded = omniroute.classify_models(entries, _h())
    assert usable == []
    assert autos == ['combo-x', 'auto/fast']
    assert excluded == {}


def test_half_open_provider_stays_usable():
    usable, _, excluded = omniroute.classify_models(
        [_m('m1', owner='p')], _h(providers=[('p', 'HALF_OPEN')]))
    assert [u['id'] for u in usable] == ['m1']
    assert usable[0]['state'] == 'HALF_OPEN'
    assert excluded == {}


def test_lockout_matches_root_and_ignores_empty_model():
    h = _h(lockouts=[{'provider': 'p', 'model': 'base-model', 'reason': 'q', 'remaining_ms': 1},
                     {'provider': 'p', 'model': '', 'reason': 'q', 'remaining_ms': 1}])
    entries = [_m('alias', root='base-model'), _m('free', root='')]
    usable, _, excluded = omniroute.classify_models(entries, h)
    assert [u['id'] for u in usable] == ['free']
    assert excluded == {'p — quota lockout': ['alias']}


def test_zero_and_missing_context_are_not_chat_models():
    entries = [_m('zero', ctx=0), _m('none', ctx=None)]
    usable, _, excluded = omniroute.classify_models(entries, _h())
    assert usable == []
    assert excluded == {'p — not a chat model': ['zero', 'none']}


def test_missing_capabilities_means_no_tool_support():
    entries = [_m('nocaps', caps=None), _m('off', caps={'tool_calling': False})]
    entries[0].pop('capabilities')
    usable, _, excluded = omniroute.classify_models(entries, _h())
    assert usable == []
    assert excluded == {'p — no tool support': ['nocaps', 'off']}


def test_first_exclusion_reason_wins():
    entry = _m('both', ctx=None)
    _, _, excluded = omniroute.classify_models([entry], _h(providers=[('p', 'OPEN')]))
    assert excluded == {'p — provider circuit open': ['both']}


def test_usable_sort_closed_then_provider_then_id():
    entries = [_m('m2a', owner='p2'), _m('m1b', owner='p1'),
               _m('m1a', owner='p1'), _m('m0c', owner='p0')]
    h = _h(providers=[('p0', 'HALF_OPEN'), ('p1', 'CLOSED'), ('p2', 'CLOSED')])
    usable, _, _ = omniroute.classify_models(entries, h)
    assert [u['id'] for u in usable] == ['m1a', 'm1b', 'm2a', 'm0c']


def test_classify_none_inputs_are_empty():
    assert omniroute.classify_models(None, None) == ([], [], {})
    assert omniroute.classify_models(None, _h()) == ([], [], {})


def test_fetch_both_keeps_catalog_health_order(monkeypatch):
    done = threading.Event()
    cat = [_m('x')]
    hel = _h(providers=[('p', 'CLOSED')])

    def health(base, key):
        done.set()
        return hel

    def catalog(base, key):
        done.wait(5)
        return cat

    monkeypatch.setattr(omniroute, 'health', health)
    monkeypatch.setattr(omniroute, 'catalog', catalog)
    assert omniroute.fetch_both('http://x') == (cat, hel)


def test_usable_models_fails_closed_with_fakes(monkeypatch):
    monkeypatch.setattr(omniroute, 'catalog', lambda base, key='': [])
    monkeypatch.setattr(omniroute, 'health', lambda base, key='': _h())
    assert omniroute.usable_models('http://x') == ([], [], {})
