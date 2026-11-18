"""T-1457: gap probes for archeus/core/routing/router.py elimination steps
_installed, _capability and _model (lines 144-216), called directly on a candidate
dict. Probes the existing router tests do not assert: a harness with no
`installed` key, several missing capabilities listed sorted and joined, the
harness-offer fallback when the account states no models, and an effort the model
and harness share exactly, which must not be refused under effort_required.
"""

from archeus.core.routing import router as R


def _cand(harness, account=None):
    return {'_h': harness, '_a': account or {}, 'model': None, 'effort': None}


def test_a_harness_with_no_installed_key_is_refused_as_not_installed():
    # router.py:145-146 a missing key reads as falsy, so it is refused (fail closed)
    assert R._installed(_cand({'id': 'h', 'capabilities': []}), {}, {}) == 'not installed'


def test_several_missing_capabilities_are_listed_sorted_and_comma_joined():
    # router.py:158-160 sorted(set(requested) - set(declared)) joined with ', '
    c = _cand({'id': 'h', 'capabilities': ['m']})
    assert R._capability(c, {'capabilities': ['z', 'a', 'm']}, {}) == 'lacks a, z'


def test_a_wanted_model_is_taken_from_the_harness_offers_when_the_account_states_none():
    # router.py:169-170 _offers falls back to the harness list when the account's is None
    h = {'id': 'h', 'models': [{'id': 'm1', 'tier': 'mid', 'context_window': None}]}
    c = _cand(h, {'id': 'a', 'models': None})
    assert R._model(c, {'models': {'h': 'm1'}}, {}) is None
    assert c['model'] == 'm1'


def test_an_effort_the_model_and_harness_share_exactly_is_kept_under_effort_required():
    # router.py:210-213 an equal effort after fit() is not a refusal (the != boundary)
    h = {'id': 'h', 'efforts': ['high'],
         'models': [{'id': 'm', 'tier': 'large', 'context_window': None, 'efforts': ['high']}]}
    c = _cand(h, {'id': 'a'})
    req = {'models': {'h': 'm'}, 'effort': 'high', 'effort_required': True}
    assert R._model(c, req, {}) is None
    assert c['effort'] == 'high'
