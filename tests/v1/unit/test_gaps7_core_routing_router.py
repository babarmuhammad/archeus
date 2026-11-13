"""T-1323 — the ten highest-risk uncovered branches of archeus/core/routing/
router.py lines 173-216 inclusive (tip d429bf96: `_model` 173-217, `fits`
183-185, the effort block 199-215, `_enforcement` from 219).

Selected branches, denial and fail-closed first, then boundaries, then errors:

 1. router.py:200, 214-215  a harness advertising an off-scale effort (turbo),
    a model advertising only low: a required turbo refuses at the model step.
 2. router.py:200, 214-215  with several models, an off-scale required effort
    never selects one of them; an optional one still runs with no effort.
 3. router.py:200, 214  an explicit model that states only recognised efforts,
    under a harness with an unknown required effort: refused, not routed.
 4. router.py:203-209  disjoint stated sets: a known required effort the model
    does not state refuses, and so does an unknown one the harness lists.
 5. router.py:214  a required effort absent from the harness list refuses; the
    optional form of the same request still runs.
 6. router.py:210-213  a required recognised effort that needs a clamp refuses
    rather than substituting a lower level.
 7. router.py:210-212  an optional recognised effort clamps to the highest
    allowed level at or below it, and the off-scale rule does not touch it.
 8. router.py:203-207  an unspecified model effort list is not an incompatible
    one: the requested level stands; an explicit narrow list refuses it.
 9. router.py:186-190  a required model the account offers but cannot meet
    refuses before the effort is looked at.
10. router.py:173-216  a refused off-scale request leaves the snapshot and the
    next valid decision exactly as a fresh one would.

Existing coverage, not copied: tests/v1/unit/test_gaps3_core_routing_router_a.py
(`test_a_required_effort_off_the_routers_own_scale_is_never_satisfied`: harness
(low, turbo) with an account on default models, and
`test_a_required_model_the_account_offers_but_cannot_meet_is_a_denial_not_a_substitute`)
and tests/v1/unit/test_routing_units.py (effort 'max', and the stated-efforts
composition through test_effort_selection.py). None of them puts a stated effort
list on the chosen model next to an off-scale or unknown required effort, which
is what probes 1-4 and 8 need. The fixture builders are copied here (not
imported) so this file stands on its own.

Pure decision logic: every input is a JSON-shaped snapshot and request. No
clock, no file, no process, no OS call; runs the same on every platform.
"""

import copy

from archeus.core.routing import router as R


def _harness(id_, efforts=(), models=('m-large:large',)):
    ms = []
    for m in models:
        mid, _, tier = m.partition(':')
        ms.append({'id': mid, 'tier': tier or None, 'context_window': None})
    return {'id': id_, 'installed': True, 'capabilities': ['code_edit', 'headless', 'shell'],
            'enforcement': 'hook', 'structured_output': 'native', 'efforts': list(efforts),
            'models': ms, 'exempt': True}


def _model(id_, efforts=None, tier='large'):
    m = {'id': id_, 'tier': tier, 'context_window': None}
    if efforts is not None:
        m['efforts'] = list(efforts)
    return m


def _acct(id_, harness_id):
    return {'id': id_, 'ref': id_, 'harness': harness_id, 'label': id_.upper(),
            'auth_kind': 'api_key', 'registered': True, 'health': 'AVAILABLE', 'why_not': None,
            'policy': {'priority': 1, 'allocation_pct': 80, 'reserve_pct': 10,
                       'brain_reserve_pct': 10, 'fallback': 'ask', 'budgets': {},
                       'project_allow': [], 'project_deny': []},
            'usage': {'windows': {'5h': 0.0}, 'age_s': 0, 'resets_at': {}},
            'ledger': {'tokens_today': 0, 'cost_today': 0, 'running': 0}}


def _snap(harnesses, accounts):
    return {'now': '2026-09-26T10:00:00.000Z', 'harnesses': harnesses, 'accounts': accounts,
            'terms': {}, 'affinity': None, 'approved_fallbacks': []}


def _call(**kw):
    return dict({'subject': 'archeus_call', 'purpose': 'brain', 'capabilities': ['headless'],
                 'structured_output': True, 'min_model_tier': None, 'models': {},
                 'preferred': {}, 'forbidden': {}, 'required': {}, 'size': None,
                 'policy': None}, **kw)


def _steps(d):
    return {c['resource']: c['eliminated_at_step'] for c in d['candidates']}


def _with_models(h, *models):
    h['models'] = list(models)
    return h


def test_a_required_off_scale_effort_refuses_when_the_model_states_only_low():
    """Kills: dropping the `effort in EFFORTS` guard on router.py:200 without
    keeping a refusal (the `fit` call then raises on an off-scale name), and
    inverting the `effort_required` test at router.py:214. An optional turbo on
    the same snapshot must still route, with no effort set."""
    h = _with_models(_harness('h', efforts=('low', 'turbo')), _model('lo', ['low']))
    s = _snap([h], [_acct('acc_a', 'h')])
    d = R.route(_call(models={'h': 'lo'}, effort='turbo', effort_required=True), s)
    assert d['selected'] is None
    assert _steps(d) == {'acc_a': 'model'}
    assert d['candidates'][0]['reason'] == 'does not accept effort turbo'
    d = R.route(_call(models={'h': 'lo'}, effort='turbo'), s)
    assert (d['selected'], d['effort']) == ('acc_a', None)


def test_several_models_never_let_an_off_scale_required_effort_pick_one_without_it():
    """Kills: a model-selection change that returns the first offer ahead of the
    effort refusal. With two offers, one stating only low and one stating low
    and high, a required turbo still refuses and no model is recorded."""
    h = _with_models(_harness('h', efforts=('low', 'high', 'turbo')),
                     _model('a', ['low']), _model('b', ['low', 'high']))
    s = _snap([h], [_acct('acc_a', 'h')])
    for models in ({}, {'h': 'a'}, {'h': 'b'}):
        d = R.route(_call(models=models, effort='turbo', effort_required=True), s)
        assert (d['selected'], d['model'], d['effort']) == (None, None, None), models
        assert _steps(d) == {'acc_a': 'model'}, models


def test_an_explicit_model_with_only_known_efforts_refuses_an_unknown_required_effort():
    """Kills: moving the effort block (router.py:199-215) after the
    `want and want in offers` branch, so a chosen model that does not state the
    effort is returned as a selection. Refused at `model`, never routed."""
    h = _with_models(_harness('h', efforts=('low', 'turbo')), _model('lo', ['low']))
    s = _snap([h], [_acct('acc_a', 'h')])
    d = R.route(_call(models={'h': 'lo'}, effort='turbo', effort_required=True), s)
    assert (d['selected'], d['model']) == (None, None)
    assert 'does not accept effort turbo' in d['candidates'][0]['reason']


def test_disjoint_stated_efforts_refuse_both_a_known_and_an_unknown_required_effort():
    """Kills: dropping the `stated and not allowed` arm (router.py:205-209). With
    the model stating only low and the harness listing high and turbo, a required
    high refuses as 'accepts none of the efforts of its harness', and a required
    turbo refuses at the scale check (router.py:214) even though the harness lists it."""
    h = _with_models(_harness('h', efforts=('high', 'turbo')), _model('lo', ['low']))
    s = _snap([h], [_acct('acc_a', 'h')])
    d = R.route(_call(models={'h': 'lo'}, effort='high', effort_required=True), s)
    assert d['selected'] is None
    assert d['candidates'][0]['reason'] == 'model lo accepts none of the efforts of its harness'
    d = R.route(_call(models={'h': 'lo'}, effort='turbo', effort_required=True), s)
    assert d['selected'] is None
    assert d['candidates'][0]['reason'] == 'does not accept effort turbo'


def test_a_required_effort_the_harness_does_not_list_refuses_and_optional_runs():
    """Kills: the `elif effort and req.get('effort_required')` leg at router.py:214
    being dropped. A harness with no efforts listed refuses a required high
    (known, but unlisted) and a required turbo; the same requests optional route."""
    h = _with_models(_harness('h'), _model('mdl'))
    s = _snap([h], [_acct('acc_a', 'h')])
    for effort in ('high', 'turbo'):
        d = R.route(_call(effort=effort, effort_required=True), s)
        assert d['selected'] is None, effort
        assert d['candidates'][0]['reason'] == 'does not accept effort %s' % effort
        d = R.route(_call(effort=effort), s)
        assert (d['selected'], d['effort']) == ('acc_a', None), effort


def test_a_required_recognised_effort_that_needs_a_clamp_refuses_instead_of_substituting():
    """Kills: dropping the `c['effort'] != effort and effort_required` test at
    router.py:212-213. The harness takes high, the model takes low and medium:
    a required high must not run as medium."""
    h = _with_models(_harness('h', efforts=('low', 'medium', 'high')),
                     _model('mdl', ['low', 'medium']))
    s = _snap([h], [_acct('acc_a', 'h')])
    d = R.route(_call(models={'h': 'mdl'}, effort='high', effort_required=True), s)
    assert d['selected'] is None
    assert _steps(d) == {'acc_a': 'model'}
    assert d['candidates'][0]['reason'] == 'model mdl does not accept effort high'


def test_an_optional_recognised_effort_clamps_to_the_allowed_level_below_it():
    """Kills: `fit` returning the request unchanged (router.py:211), or clamping
    upward. An optional high on a model that takes low and medium runs as
    medium, the highest allowed level below it."""
    h = _with_models(_harness('h', efforts=('low', 'medium', 'high')),
                     _model('mdl', ['low', 'medium']))
    s = _snap([h], [_acct('acc_a', 'h')])
    d = R.route(_call(models={'h': 'mdl'}, effort='high'), s)
    assert (d['selected'], d['model'], d['effort']) == ('acc_a', 'mdl', 'medium')


def test_an_unspecified_model_effort_list_is_not_an_incompatible_one():
    """Kills: treating a model with no `efforts` key as stating none (`stated`
    empty must leave the requested level standing, router.py:203-204). An explicit
    list that intersects nothing the harness takes must refuse the same request."""
    h = _with_models(_harness('h', efforts=('low', 'medium', 'high')), _model('open'))
    s = _snap([h], [_acct('acc_a', 'h')])
    d = R.route(_call(models={'h': 'open'}, effort='high', effort_required=True), s)
    assert (d['selected'], d['effort']) == ('acc_a', 'high')
    h = _with_models(_harness('h', efforts=('low', 'medium', 'high')), _model('narrow', ['low']))
    s = _snap([h], [_acct('acc_a', 'h')])
    d = R.route(_call(models={'h': 'narrow'}, effort='high', effort_required=True), s)
    assert d['selected'] is None


def test_a_required_model_refusal_is_reported_before_any_effort_check():
    """Kills: running the effort block (router.py:199) ahead of the required-model
    branch at router.py:189. A model the account cannot meet and an off-scale
    effort both fail; the reason named is the model's, and no model is recorded."""
    h = _with_models(_harness('h', efforts=('low', 'turbo')), _model('big', None, tier='small'))
    s = _snap([h], [_acct('acc_a', 'h')])
    d = R.route(_call(models={'h': 'big'}, model_required=True, min_model_tier='mid',
                      effort='turbo', effort_required=True), s)
    assert (d['selected'], d['model']) == (None, None)
    assert d['candidates'][0]['reason'] == (
        'model big is not an offer of this account that meets the requirement')


def test_a_refused_off_scale_request_leaves_nothing_behind_for_the_next_decision():
    """Kills: a route that writes the refused effort or model onto the shared
    snapshot (the candidate dicts are rebuilt each call, so this checks the
    snapshot itself). The refused call's snapshot compares equal before and
    after, and a valid call on the same snapshot picks up exactly its own effort."""
    h = _with_models(_harness('h', efforts=('low', 'high', 'turbo')),
                     _model('mdl', ['low', 'high']))
    s = _snap([h], [_acct('acc_a', 'h')])
    before = copy.deepcopy(s)
    d = R.route(_call(models={'h': 'mdl'}, effort='turbo', effort_required=True), s)
    assert d['selected'] is None
    assert s == before
    d = R.route(_call(models={'h': 'mdl'}, effort='low', effort_required=True), s)
    assert (d['selected'], d['model'], d['effort']) == ('acc_a', 'mdl', 'low')
    assert s == before
