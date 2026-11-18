"""T-317: the ten highest-risk uncovered branches of archeus/core/routing/router.py,
as tests. Fail-closed and denial paths first (a harness that offers no account, the
last-resort partition held among fallbacks, an item the enforcement mode cannot
enforce, an open breaker that recorded nothing), then the ordering, tie and boundary
values, then the error paths. Nothing here reads the OS, the clock, the network or an
adapter: every input is the JSON a decision records, so the file runs unchanged on
Linux and on Windows. Same builders as test_routing_units.py, imported and not
copied (the style of test_ap1_units.py and test_broker_execution.py).

Each test names the source branch it kills; removing or inverting that branch fails
the test.
"""

import pytest

from archeus.core.routing import router as R
from v1.unit.test_routing_units import acct, call, harness, own, snap, steps, task

LAST = 10 ** 9                                        # R._LAST: a harness's own priority
UNTIL = '2026-09-26T10:05:00.000Z'
NOW = '2026-09-26T10:00:00.000Z'


def reason(d, resource):
    return next(c['reason'] for c in d['candidates'] if c['resource'] == resource)


def field(d, resource, k):
    return next(c[k] for c in d['candidates'] if c['resource'] == resource)


def reset(key):
    """One written reset exactly as the snapshot builder carries it
    (domain/instants.py `ahead`: `at` as written, `key` the same instant in UTC)."""
    return {'at': key, 'key': key}


# ── 1. fail-closed: a candidate with nothing to run on ──────────────────────

def test_a_harness_that_offers_no_account_at_all_is_blocked_never_selected():
    """router.py:297-298, `_health`'s `if not a: return 'no account to run on'`.

    Kills: deleting that guard, which lets a harness whose snapshot carries no
    account at all (no registration, not even the default one) be elected and run
    work on nothing. Nothing else in the router refuses it: its policy, health and
    usage are all absent, so every later step passes an empty account."""
    for req in (task(), call()):
        d = R.route(req, snap([harness('h')], []))
        assert (d['result'], d['selected'], d['harness_id']) == ('blocked', None, None)
        assert steps(d) == {'h': 'health'} and reason(d, 'h') == 'no account to run on'
        assert d['unblock_at'] is None and d['fallback_from'] == []


# ── 2. the last-resort partition holds among fallbacks too ──────────────────

def test_a_last_resort_fallback_never_precedes_a_normal_one_that_may_also_fall_back():
    """router.py:449-450, `fb = sorted(..., key=lambda c: (_last_resort(c, req),
    order_key(c, req, snap)))`.

    Kills: the `_last_resort` term of the fallback sort key. The protected account
    is the better candidate by every ordering key (priority 1 against 5), so with
    the term dropped the router falls back to a `last_resort` account while an
    ordinary one is standing right there with its ceiling exceeded (ADR-0041 §1:
    protection comes before every ordering key, in the fallback list as well)."""
    s = snap([harness('h')], [acct('acc_lr', 'h', priority=1, consumption='last_resort',
                                   fallback='allow'),
                              acct('acc_n', 'h', priority=5, usage=70.0, fallback='allow'),
                              acct('acc_x', 'h', priority=9, usage=100.0)])
    d = R.route(task(), s)
    assert (d['result'], d['selected'], d['account_id']) == ('fallback', 'acc_n', 'acc_n')
    assert steps(d) == {'acc_lr': 'partition', 'acc_n': 'allocation', 'acc_x': 'health'}
    # what it fell back FROM is what availability stopped, never the protected one
    assert d['fallback_from'] == ['acc_x']
    assert reason(d, 'acc_lr') == 'a last-resort account, used only as a fallback'
    assert d['why'].startswith('its policy allows fallback (usage at 70% (+3 projected)')


# ── 3. enforcement: only the recorded ALLOW authorises anything ─────────────

@pytest.mark.parametrize('decision', ['DENY', 'allow', 'ALLOWED'])
def test_nothing_but_the_exact_word_allow_authorises_an_item(decision):
    """router.py:202-203 + 204-209, `_enforcement`: the `d == 'ALLOW'` test, the
    `mode == 'sandbox' and d == 'ALLOW_WITHIN_BOUNDARY'` test and the fall-through
    `return 'cannot enforce %s %s'` for every other decision.

    Kills: a widening of the accepted set (a `startswith`, a `casefold()`, an
    `in ('ALLOW', 'DENY')`). P9's DENY, a decision written in lower case and an
    unknown verb must all stop the task: what is not expressly authorised is
    refused, and the router never guesses."""
    d = R.route(task(items=[('write_repo', decision, None)]),
                snap([harness('h', enforcement='none')], [own('h')]))
    assert (d['result'], steps(d)) == ('blocked', {'h': 'enforcement'})
    assert reason(d, 'h') == 'cannot enforce %s write_repo (enforcement: none)' % decision


def test_every_boundary_of_an_item_is_checked_before_a_sandbox_run():
    """router.py:204-207: `all(set(b) <= set(SANDBOX_KEYS) for b in (i['boundary']
    if isinstance(i['boundary'], list) else [i['boundary']]) if b)` — the list form
    (an item authorised under SEVERAL boundaries) and the `if b` that skips an
    absent entry.

    Kills: (a) reading only `i['boundary']` when it is a list, which would let a
    task run under a sandbox with a `branches` boundary no sandbox can express;
    (b) dropping `if b`, which raises TypeError on a `None` entry instead of
    ignoring it. Every existing case hands one dict or None, never a list."""
    def route(boundary):
        return R.route(task(items=[('write_repo', 'ALLOW_WITHIN_BOUNDARY', boundary)]),
                       snap([harness('h', enforcement='sandbox')], [own('h')]))

    d = route([{'paths': ['src/**']}, {'branches': ['main']}])
    assert (d['result'], steps(d)) == ('blocked', {'h': 'enforcement'})
    assert reason(d, 'h') == ('cannot enforce ALLOW_WITHIN_BOUNDARY write_repo '
                              '(enforcement: sandbox)')
    d = route({'paths': ['src/**'], 'branches': ['main']})
    assert steps(d) == {'h': 'enforcement'}           # two keys in one boundary: the same
    # every entry must express itself in the sandbox, and an absent entry holds nothing
    assert route([{'paths': ['src/**']}, None])['selected'] == 'h'
    assert route([])['selected'] == 'h'               # nothing to hold: nothing to break


# ── 4. the start breaker is a fact, and an unrecorded fact still stops ──────

@pytest.mark.parametrize('breaker', [
    {'state': 'open', 'until': UNTIL},                    # no `error` key at all
    {'state': 'open', 'until': UNTIL, 'error': None},     # nothing was recorded
    {'state': 'open', 'until': UNTIL, 'error': ''},       # an empty reason
])
def test_an_open_breaker_that_recorded_no_error_still_blocks(breaker):
    """router.py:290-291: `if b and b['state'] == 'open'` and the
    `b.get('error') or 'no reason recorded'` right leg.

    Kills: dropping the `or 'no reason recorded'`, which would tell the user
    'cannot start: None' (and in the `%s` of a reason the UI shows), and inverting
    the state test. An open breaker stops the harness whatever it managed to
    record about why."""
    h = harness('h')
    h['breaker'] = breaker
    d = R.route(task(), snap([h], [own('h')]))
    assert (d['result'], d['selected'], d['harness_id']) == ('blocked', None, None)
    assert steps(d) == {'h': 'breaker'} and reason(d, 'h') == 'cannot start: no reason recorded'
    assert d['unblock_at'] == UNTIL


def test_an_open_breaker_with_no_until_blocks_and_promises_no_time():
    """router.py:468-469: the `if u` of the breaker waits (a breaker that names no
    instant contributes no wait) and router.py:483-484's `result == 'blocked'`.

    Kills: removing `if u`, which puts `None` in `waits` and writes it as
    `unblock_at` — a decision that promises the user it may run again at nothing."""
    h = harness('h')
    h['breaker'] = {'state': 'open', 'until': None, 'error': 'no process'}
    d = R.route(task(), snap([h], [own('h')]))
    assert (d['result'], steps(d)['h'], d['unblock_at']) == ('blocked', 'breaker', None)
    assert reason(d, 'h') == 'cannot start: no process'


# ── 5. ordering: near its ceiling is a key, and it is worth stating ─────────

def test_an_account_near_its_ceiling_loses_the_tie_to_one_under_it():
    """router.py:321 (`c['constrained'] = w >= cap - NEAR`), router.py:386
    (`1 if c['constrained'] else 0`) and router.py:390 (`_WHY[4]`).

    Kills: inverting the ceiling term of `order_key` (the near-ceiling account
    would win, and the work would start where it is about to be stopped), and
    reading `>=` as `>` for `constrained` (55.0 against a ceiling of 60 is exactly
    `cap - NEAR`, so it IS near). Both accounts are under the ceiling for the task,
    share priority, tier and harness, and the near one comes first by id, so only
    this key decides."""
    s = snap([harness('h')], [acct('acc_a', 'h', usage=55.0),      # == ceiling - NEAR
                              acct('acc_b', 'h', usage=54.9)])
    d = R.route(task(), s)
    assert d['selected'] == 'acc_b' and steps(d) == {'acc_b': None, 'acc_a': 'election'}
    assert (field(d, 'acc_a', 'constrained'), field(d, 'acc_b', 'constrained')) == (True, False)
    assert d['why'] == 'it is your priority-1 account, and it is not near its ceiling'


@pytest.mark.parametrize('size,usage,ok', [
    ('S', 58.0, True), ('S', 59.0, False),          # PROJECTED['S'] == 1
    ('L', 51.9, True), ('L', 52.0, False),          # PROJECTED['L'] == 8
])
def test_the_projected_bump_of_the_size_band_is_counted_exactly(size, usage, ok):
    """router.py:320-322: `bump = PROJECTED.get(req.get('size'), 0)` and
    `if w + bump >= cap`.

    Kills: a lost or mis-stated band in PROJECTED (S and M/L mixed, or the bump
    dropped) — the existing suite only ever moves the usage, always with an M
    task, so only the M edge is pinned. The task ceiling is 80-10-10 = 60, so an
    S task starts at 58 and not at 59, an L task at 51.9 and not at 52."""
    d = R.route(task(size=size), snap([harness('h')], [acct('acc_a', 'h', usage=usage)]))
    assert (d['result'] == 'selected') is ok


# ── 6. an approved fallback is matched on the resource's own key ────────────

def test_an_approved_fallback_names_the_default_account_by_its_ref_not_by_harness():
    """router.py:102-103 (`_key`: `c['account'] or c['account_ref'] or c['harness']`)
    read by router.py:451-457 (the approved-fallback pick).

    Kills: `_key` reduced to the harness id, or to the account id alone. The
    approval is stored against the resource's key; for an unregistered default
    account there is no id, so a match on the harness would let one approval open
    EVERY default account of that harness, and a key that ignored `account_ref`
    would never find the approval the user gave."""
    def s(approved):
        a = own('h')
        a['policy'] = {'consumption': 'last_resort'}         # protected: fallback only
        return snap([harness('h')], [a], approved_fallbacks=approved)

    d = R.route(task(), s(['h:default']))
    assert (d['result'], d['selected'], d['account_ref']) == ('fallback', 'h', 'h:default')
    assert d['why'].startswith('you approved running it there (a last-resort account')
    # the harness id is not the key of its default account, and nothing approved: no run
    assert (R.route(task(), s(['h']))['result'],
            R.route(task(), s([]))['result']) == ('blocked', 'blocked')


# ── 7. a wait with no `now` to compare against is still a wait ──────────────

def test_without_now_the_earliest_reset_is_named_even_when_it_reads_past():
    """router.py:465 + 470: `now = snap.get('now')` and
    `waits = [w for w in waits if now is None or w['key'] > now]`.

    Kills: the `now is None` left leg. A recorded decision replays with the `now`
    it was decided under, and a snapshot may carry none: comparing nothing then
    must name the earliest reset (the module's own rule), while the same reading
    beside a real `now` is past and therefore no wait at all."""
    def s(now):
        a = acct('acc_a', 'h', usage=100.0)
        a['usage']['resets_at'] = {'5h': reset('2020-01-01T00:00:00.000Z')}
        return snap([harness('h')], [a], now=now)

    assert (R.route(task(), s(None))['unblock_at']) == '2020-01-01T00:00:00.000Z'
    assert (R.route(task(), s(NOW))['unblock_at']) is None


# ── 8. the explanation of a fallback and of an ask come from the record ─────

def test_a_fallback_and_an_ask_are_explained_as_what_they_are():
    """router.py:500-504: `head = 'I fell back to %s because nothing preferred could
    run and %s.'` and the `ask` head 'Nothing could run within its limits; %s may be
    used only if you approve it.'.

    Kills: a fallback explained as a selection (the user is told nothing preferred
    could run and that the account may be used ONLY with their approval — an ask
    phrased as a choice is an approval the user never gave), and an ask naming a
    `selected` resource: `ask` answers WHERE, and only approves nothing."""
    def world(fallback):
        return snap([harness('h')], [acct('acc_a', 'h', priority=1, usage=100.0),
                                     acct('acc_b', 'h', priority=2, usage=70.0,
                                          fallback=fallback)])

    d = R.route(task(), world('allow'))
    assert d['result'] == 'fallback'
    assert R.explain(d, task()) == (
        'I fell back to ACC_B (h, its default model) because nothing preferred could '
        'run and its policy allows fallback (usage at 70% (+3 projected) is not under '
        'its 60% ceiling for tasks). Not used: ACC_A — a usage window is exhausted '
        '(100%).')

    d = R.route(task(), world('ask'))
    assert (d['result'], d['selected'], d['account_id']) == ('ask', None, 'acc_b')
    assert R.explain(d, task()) == (
        'Nothing could run within its limits; ACC_B (h, its default model) may be used '
        'only if you approve it. Not used: ACC_A — a usage window is exhausted (100%).')
