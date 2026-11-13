"""T-1164: the ten highest-risk uncovered branches of archeus/core/routing/
router.py lines 1-271 inclusive (tip 56d53504), as tests. Fail-closed and
denial branches first (a required effort off the router's own scale that no
check refuses, a required model the account offers but cannot meet, an
unpermited subscription rotation, a task isolated against a broker map that
names its harness at all, an item later than the first the mode cannot
enforce), then the boundaries (an empty sandbox boundary, a context window
exactly at the minimum and one token below, the stable within-tier offer
order), then the error paths (the no-offers reason without a discovery note).

The ten risk probes started as: (1) empty account offers, (2) required named
model absent, (3) context exact and one below, (4) unknown tier cannot satisfy
a larger tier, (5) required effort unsupported, (6) model/harness efforts
disjoint, (7) sandbox unsupported boundary, (8) missing headless capability,
(9) unknown provider terms, (10) broker auth-kind mismatch. The found-covered
ones were replaced, each by the genuinely uncovered branch or fault
composition beside it, as recorded per test below: 1 covered
(test_pi_discovery.py:292) -> replaced by the no-note reason leg (175-179);
2 covered (test_routing_units.py:191) -> replaced by offered-but-unfit
(186-190); 3 kept, uncovered (183-197); 4 covered (test_routing_units.py:208)
-> replaced by the every-item loop of `_enforcement` (226-234); 5 covered
(test_routing_units.py:224) -> replaced by the off-scale leg of the effort
block (200-216); 6 covered (test_effort_selection.py:80/110) -> replaced by
the rotation first-key (251-254); 7 covered as a list boundary
(test_gaps_core_routing_router.py:96) -> replaced by the empty-dict leg
(230-232); 8 covered (test_knowledge_units.py:108) -> replaced by the
task subject leg (150-153); 9 headless leg covered (test_routing_units.py:454)
-> replaced by the rotation default (246-247); 10 covered for a mapped harness
(test_broker_execution.py:397) -> replaced by the unmapped harness and the
reason's no-account leg (262-269).

Branches finally selected (each test names the one it kills):
  router.py:200-216  a required effort outside EFFORTS carried into the decision
  router.py:186-190  a required model offered but failing `fits` (not tier/context fit)
  router.py:246-254  rotation unstated defaults to not-permitted (ADR-0021)
  router.py:251-254  the one usable subscription is the first by (priority, id)
  router.py:262-269  a harness the broker gate does not name runs nowhere
  router.py:226-234  every item is checked, not just the first
  router.py:230-232  an empty boundary bounds nothing a sandbox can hold
  router.py:150-153  the headless step reaches tasks never
  router.py:183-197  `>=` on the context minimum and the no-fit reason text
  router.py:175-179  the no-offers reason when discovery recorded no note

Nothing here reads the OS, the clock, the network or an adapter: every input
is the JSON a decision records, so the file runs unchanged on Linux and on
Windows. Same builders as test_routing_units.py, imported and not copied (the
style of test_gaps_core_routing_router.py). Tests are independent; no other
test_gaps3 file is imported and no queue order is relied on.
"""

import pytest

from archeus.core.routing import router as R
from v1.unit.test_routing_units import acct, call, harness, snap, steps, task

# xfail (not a fixture problem): router.py:201 writes `c['effort'] = effort`
# before any scale check, and the only guard that reads the scale —
# `elif allowed and effort in EFFORTS` at router.py:210 — skips the clamp
# (and its `effort_required` refusal at router.py:212-213) instead of refusing
# the level. A task whose effort is off entities.EFFORTS, on a harness that
# (mis)states it, is therefore elected with that effort carried into the
# decision: the closed scale the module itself declares at router.py:56 is
# enforced for clamping but not for eligibility, and nothing refuses it.
EFFORT_XFAIL = pytest.mark.xfail(
    strict=True,
    reason='router.py:210-213: an effort outside EFFORTS skips the clamp leg '
           'without the effort_required refusal; router.py:201 has already '
           'carried it into the decision',
)


# ── fail-closed and denials ─────────────────────────────────────────────────

@EFFORT_XFAIL
def test_a_required_effort_off_the_routers_own_scale_is_never_satisfied():
    """router.py:200-216: `if effort and effort in (h.get('efforts') or ())`,
    the `elif allowed and effort in EFFORTS` scale guard and the
    `effort_required` refusals it owns.

    Kills: inverting or dropping the `effort in EFFORTS` term of router.py:210
    without adding a refusal — an effort the router's own closed scale does
    not name is one NO model accepts, so a task that REQUIRES it must stop at
    `model`, not run with it. The nearest tests (test_routing_units.py:224
    `effort='max'`, test_effort_selection.py:80/110) all stay on the scale,
    so none ever reaches this leg with an off-scale effort."""
    s = snap([harness('h', efforts=('low', 'turbo'))], [acct('acc_a', 'h')])
    d = R.route(call(effort='turbo', effort_required=True), s)
    assert d['selected'] is None
    assert steps(d) == {'acc_a': 'model'}
    assert 'does not accept effort turbo' in d['candidates'][0]['reason']


def test_a_required_model_the_account_offers_but_cannot_meet_is_a_denial_not_a_substitute():
    """router.py:186-190: `if want and want in offers and fits(offers[want])`
    falling to `elif want and req.get('model_required')` — the chain must NOT
    treat an offered-but-unfit model as no requirement.

    Kills: dropping `fits(offers[want])` from router.py:181, which would name
    the small model against a mid minimum (fail-open: the required model runs
    under the requirement), and dropping the `model_required` leg, which would
    silently substitute. test_routing_units.py:191 only ever asks for an id
    NOT in the offers at all, and test_routing_units.py:218 never sets
    `model_required`, so this composition of the two is unreached."""
    s = snap([harness('h', models=('big:small',))], [acct('acc_a', 'h')])
    d = R.route(call(models={'h': 'big'}, model_required=True, min_model_tier='mid'), s)
    assert (d['result'], d['selected']) == ('blocked', None)
    assert steps(d) == {'acc_a': 'model'}
    assert d['candidates'][0]['reason'] == (
        'model big is not an offer of this account that meets the requirement')
    # without the requirement there is no named model to deny, only the tier
    # minimum to fail — and it is the tier, not the name, that is reported
    d = R.route(call(models={'h': 'big'}, min_model_tier='mid'), s)
    assert (d['result'], steps(d)) == ('blocked', {'acc_a': 'model'})
    assert d['candidates'][0]['reason'] == 'offers no model of tier mid'


def test_a_task_is_never_stopped_by_an_undeclared_headless_capability():
    """router.py:150-153: the `req['subject'] == 'archeus_call'` conjunct of
    the headless step — a task is not tool-less and the capability only means
    anything for an own call.

    Kills: dropping the subject test, which would stop EVERY task on a harness
    that does not declare headless (a fail-closed hangry mutation no existing
    test catches: every harness the other builders make carries 'headless',
    and the one snapshot without it, test_knowledge_units.py:108, is an own
    call). Complements, not repeats: that covered test owns the own-call leg."""
    h = harness('h')
    h['capabilities'] = [c for c in h['capabilities'] if c != 'headless']
    assert 'headless' not in h['capabilities']
    d = R.route(task(), snap([h], [acct('acc_a', 'h')]))
    assert (d['result'], d['selected'], steps(d)) == ('selected', 'acc_a', {'acc_a': None})


def test_a_subscription_rotation_nobody_answered_is_no_answer_and_no_rotation():
    """router.py:246-247: `t.get('rotation', 'unknown') != 'permitted'` — the
    default leg when the terms entry answers headless but says NOTHING about
    rotation (the snapshot key is simply absent).

    Kills: defaulting the missing answer to 'permitted' — ADR-0021 is a
    permission, and an unasked permission is refused; with that default the
    second subscription would stand for election and the task would rotate
    across subscriptions nobody permitted rotating. test_routing_units.py:454
    always passes an explicit `rotation` value ('unknown' or 'permitted'), so
    the default itself is unreached, and its rotation assertion names
    `acc_b`-after-`acc_a` only through an explicit 'unknown'."""
    terms = {'h': {'headless': 'permitted'}}
    accts = [acct('acc_a', 'h', auth='subscription_oauth'),
             acct('acc_b', 'h', priority=2, auth='subscription_oauth')]
    d = R.route(task(), snap([harness('h', exempt=False)], accts, terms=terms))
    assert d['selected'] == 'acc_a'
    assert steps(d) == {'acc_a': None, 'acc_b': 'provider_terms'}
    assert next(c['reason'] for c in d['candidates']
                if c['resource'] == 'acc_b') == (
        'rotation across h subscriptions is not permitted (ADR-0021): only acc_a is used')
    # the answer, once actually given, is what decides — not the default
    terms['h']['rotation'] = 'permitted'
    d = R.route(task(), snap([harness('h', exempt=False)], accts, terms=terms))
    assert (d['selected'], steps(d)) == ('acc_a', {'acc_a': None, 'acc_b': 'election'})


def test_the_one_usable_subscription_is_the_first_by_priority_then_id_and_only_it():
    """router.py:251: `first = min(subs, key=lambda x: ((x.get('policy') or
    {}).get('priority', _LAST), x['id']))` and the `first['id'] != a['id']`
    refusal of router.py:252-254 — both terms of the pick and the exact
    reason naming it.

    Kills: dropping `x['id']` from the min key (the pick then depends on the
    snapshot's account order: with the accounts listed [acc_z, acc_m, ...] an
    id-less key picks acc_z and refuses acc_m instead), dropping the priority
    term (acc_z, listed first, is kept over the priority-2 acc_b's rival),
    and dropping the `auth_kind` filter of router.py:250 (the api-key acc_a
    would become the named 'only' subscription). The covered rotation test,
    test_routing_units.py:462, has one subscription per priority and an
    explicit 'unknown', so no tie and no default ever decide anything."""
    terms = {'h': {'headless': 'permitted', 'rotation': 'unknown'}}
    accts = [acct('acc_z', 'h', auth='subscription_oauth'),
             acct('acc_m', 'h', auth='subscription_oauth'),
             acct('acc_b', 'h', priority=2, auth='subscription_oauth'),
             acct('acc_a', 'h', auth='api_key')]
    d = R.route(task(), snap([harness('h', exempt=False)], accts, terms=terms))
    assert d['selected'] == 'acc_a'                       # an api key is not rotation
    assert steps(d) == {'acc_a': None, 'acc_m': 'election',
                        'acc_z': 'provider_terms', 'acc_b': 'provider_terms'}
    by = {c['resource']: c['reason'] for c in d['candidates']}
    assert by['acc_z'] == by['acc_b'] == (
        'rotation across h subscriptions is not permitted (ADR-0021): only acc_m is used')


def test_a_task_stops_at_the_broker_when_the_gate_names_nothing_for_its_harness():
    """router.py:262-269: `kinds = (gate.get('broker') or {}).get(c['_h']['id'])
    or ()` with a harness the gate does not name, and the `else 'no account'`
    leg of the reason — fail-closed: an unmapped harness dispatches nowhere.

    Kills: `if not kinds: return None` (an account of ANY auth kind would then
    run on a harness the gate says nothing about), and swapping the reason's
    legs. The covered filter, test_broker_execution.py:397, drops the codex
    default account, whose auth kind is None, never asserts the reason text,
    and never puts a REGISTERED api-key account under an unmapped harness."""
    s = snap([harness('h')], [acct('acc_a', 'h', auth='api_key')],
             isolated_dispatch={'broker': {'other_harness': ['api_key']}})
    d = R.route(task(), s)
    assert (d['result'], d['selected']) == ('blocked', None)
    assert steps(d) == {'acc_a': 'broker'}
    assert d['candidates'][0]['reason'] == (
        'cannot run isolated: h reaches its model through the broker only with no account')


def test_every_item_of_the_policy_is_checked_not_just_the_first():
    """router.py:226-234: the `for i in items` loop, its `if d == 'ALLOW':
    continue` and the fall-through refusal — a later item stops the task even
    when every earlier one is clean, and the refusal names THAT item.

    Kills: reading only `items[0]` (or breaking before the refusal): the task
    would run with a git_push ASK unenforced on a mode-none harness. Every
    existing enforcement case — test_routing_units.py:440 (U-E) and both
    cases in test_gaps_core_routing_router.py — hands exactly ONE item, so
    the loop never turns twice anywhere."""
    hs = [harness('h', enforcement='none')]
    d = R.route(task(items=[('read_files', 'ALLOW', None), ('git_push', 'ASK', None)]),
                snap(hs, [acct('acc_a', 'h')]))
    assert (d['result'], steps(d)) == ('blocked', {'acc_a': 'enforcement'})
    assert d['candidates'][0]['reason'] == (
        'cannot enforce ASK git_push (enforcement: none)')
    d = R.route(task(items=[('read_files', 'ALLOW', None),
                            ('write_repo', 'ALLOW', None)]),
                snap(hs, [acct('acc_a', 'h')]))
    assert d['selected'] == 'acc_a'


# ── boundaries ───────────────────────────────────────────────────────────────

def test_an_allow_within_boundary_that_states_nothing_bounds_nothing_a_sandbox_can_hold():
    """router.py:230-232: `(bs or isinstance(bs, list))` of the sandbox leg —
    an empty dict is neither a truthy boundary nor a list, so the item is not
    sandbox-expressible and the task stops.

    Kills: removing that guard, which leaves `all(... if b)` with nothing to
    check on a `{}` boundary (all of empty is True) and the task runs
    write_repo under a sandbox that holds nothing about it. The covered legs
    take a dicts with 'branches', a list of those, a None entry or an empty
    LIST (test_gaps_core_routing_router.py:96, test_routing_units.py:440); an
    empty DICT appears nowhere."""
    hs = [harness('h', enforcement='sandbox')]
    d = R.route(task(items=[('write_repo', 'ALLOW_WITHIN_BOUNDARY', {})]),
                snap(hs, [acct('acc_a', 'h')]))
    assert (d['result'], steps(d)) == ('blocked', {'acc_a': 'enforcement'})
    assert d['candidates'][0]['reason'] == (
        'cannot enforce ALLOW_WITHIN_BOUNDARY write_repo (enforcement: sandbox)')
    d = R.route(task(items=[('write_repo', 'ALLOW_WITHIN_BOUNDARY', {'paths': ['src/**']})]),
                snap(hs, [acct('acc_a', 'h')]))
    assert d['selected'] == 'acc_a'


def test_a_context_window_exactly_at_the_minimum_fits_and_one_token_below_does_not():
    """router.py:183-185 and 196-197: `(m.get('context_window') or 0) >= ctx`
    at the exact equality, and the no-fit reason's `need or 'any'` and
    `' with a %d-token context'` legs.

    Kills: `>` where `>=` is the contract (a 100000-token model refused for a
    100000-token need), dropping `or 0` (the unknown window then raises
    TypeError against a stated minimum instead of failing to fit), and losing
    either leg of the reason — the user would read 'offers no model of tier
    ' or a tierless lie. test_pressure_units.py:182 sits far from the
    boundary (150000 against 100000, 64000 against 128000) and asserts only
    the step, never the text."""
    h = harness('h', models=('exact:mid', 'wide:mid'))
    h['models'][0]['context_window'] = 100000                 # 'wide' stays None: unknown
    d = R.route(call(min_context_window=100000), snap([h], [acct('acc_a', 'h')]))
    assert (d['result'], d['selected'], d['model']) == ('selected', 'acc_a', 'exact')
    d = R.route(call(min_context_window=100001), snap([h], [acct('acc_a', 'h')]))
    assert (d['result'], steps(d)) == ('blocked', {'acc_a': 'model'})
    assert d['candidates'][0]['reason'] == (
        'offers no model of tier any with a 100001-token context')


# ── error paths ──────────────────────────────────────────────────────────────

def test_an_account_whose_discovery_found_nothing_and_recorded_no_note_says_only_that():
    """router.py:175-179: `if c['_a'].get('models') == []` with the
    `' (%s)' % note if note else ''` right leg — no note key, and a None note,
    both give the bare sentence, never a '(None)' parenthetical.

    Kills: interpolating the note unconditionally (the user is shown 'None'
    as the discovery's reason, and any UI matching on the exact sentence
    breaks). test_pi_discovery.py:292 covers only the with-note form
    ('exited 1' in the reason), so the no-note leg is unreached, and it is
    this account's OWN empty offer list that must decide — the harness still
    advertises a model, which _offers must not fall back to here."""
    for no_note in ({'models': []}, {'models': [], 'models_note': None}):
        a = acct('acc_a', 'h')
        a.update(no_note)
        d = R.route(call(), snap([harness('h')], [a]))
        assert d['result'] != 'selected'
        assert steps(d) == {'acc_a': 'model'}
        assert d['candidates'][0]['reason'] == 'offers no model it can run'
