"""T-1165: the ten highest-risk uncovered branches of archeus/core/routing/router.py
lines 272-540 inclusive (`_restriction` to `replay`) at tip 56d53504, as tests.
Fail-closed and denial paths first, then boundaries, then the error and ordering
paths. Nothing here reads the OS, the clock, the network or an adapter: every input
is the JSON a decision records, so the file runs unchanged on Linux and on Windows.
Same builders as test_routing_units.py, imported and not copied (the style of
test_ap1_units.py, test_broker_execution.py and test_gaps_core_routing_router.py,
whose `reason` and `field` helpers are imported too).

The final ten branches, ranked by risk, all owned by a function inside the slice:

1. `_restriction` router.py:283 - a forbidden account or harness stays refused when
   it is also the preferred one (the ordering never rescues it).
2. `_restriction` router.py:280-281 - a requirement naming BOTH a harness and an
   account admits only that pair (both halves of the disjunction must hold).
3. `_restriction` router.py:286-289 - a project in both `project_allow` and
   `project_deny` stays denied: the deny list is consulted first.
4. `_breaker` router.py:315-317 with router.py:475-479 - a candidate the breaker
   stopped is never a fallback, whatever its `fallback` policy says.
5. `_health` router.py:330-332 (and 327-329) - the exhaustion test reads the FULLEST
   of several windows, and a DEGRADED account with one full window is no fallback.
6. `_allocation` router.py:342-354 - the stale penalty is what breaks the ceiling and
   the reason reports it (`stale usage (+5)`), with the projected bump.
7. `_health` router.py:326-329 - CONSTRAINED is a routable health: it is elected, it
   is not a fallback-only state, and its ceiling still governs it.
8. `_named` router.py:301-303 with router.py:290-291 - a `required` account lifts an
   `explicit_only` class; a conversational preference never lifts anything.
9. `route` router.py:509-510 - only a BLOCKED decision may promise an unblock time:
   a `selected` or `ask` one carries none although a stop contributes a wait.
10. `order_key` router.py:406-407 with router.py:116 - continuity to a harness's OWN
    account, matched by its ref, outranks priority and the resource id.

Each test names the source branch it kills; removing or inverting that branch fails
the test.
"""

from archeus.core.routing import router as R
from v1.unit.test_gaps_core_routing_router import field, reason
from v1.unit.test_routing_units import acct, call, harness, own, snap, steps, task

UNTIL = '2026-09-26T10:05:00.000Z'            # the breaker's release, after `now`
FUTURE = '2026-09-26T11:30:00.000Z'           # a reset still ahead of `now`


def reading(usage, age=0, reset=None):
    """A usage reading as the snapshot carries it, with one entry per window
    (`resets_at` the {at, key} pair domain/instants.py writes)."""
    return {'windows': dict(usage), 'age_s': age,
            'resets_at': ({'5h': {'at': reset, 'key': reset}} if reset else {})}


def with_usage(a, usage, age=0, reset=None):
    a['usage'] = reading(usage, age, reset)
    return a


# ── 1. fail-closed and denial first ───────────────────────────────────────────────

def test_a_forbidden_account_or_harness_is_refused_even_when_it_is_the_preferred_one():
    # router.py:283 `_restriction`: `if kind == 'forbidden' and (hit_h or hit_a)`
    # runs before any ordering key, so a preference never rescues what was refused
    # (router.py:408 `pref` is the 2nd ordering element and router.py:446-453 is the
    # loop that must never see the refused candidate at all).
    # Closest existing test: test_routing_units.py:485 forbids an account nobody
    # prefers, and :128 prefers an account nobody forbids: neither composes the two,
    # so `if kind == 'forbidden' and (hit_h or hit_a) and not pref` passes them all.
    accts = [acct('acc_a', 'h', priority=1), acct('acc_b', 'h', priority=2)]
    s = snap([harness('h')], accts)
    d = R.route(task(preferred={'accounts': ['acc_a']},
                     forbidden={'accounts': ['acc_a']}), s)
    assert d['selected'] == 'acc_b'                      # preferred AND priority 1, and refused
    assert steps(d) == {'acc_a': 'restriction', 'acc_b': None}
    assert reason(d, 'acc_a') == 'is forbidden for this work'
    # and the same for a harness named in both lists: the refusal is by harness too
    s = snap([harness('a'), harness('b')], [own('a'), own('b')])
    d = R.route(call(preferred={'harnesses': ['b']}, forbidden={'harnesses': ['b']}), s)
    assert (d['selected'], steps(d)) == ('a', {'a': None, 'b': 'restriction'})


def test_a_requirement_that_names_a_harness_AND_an_account_admits_only_the_pair():
    # router.py:280-281 `_restriction`: `if kind == 'required' and ((hs and not hit_h)
    # or (accs and not hit_a))` - both halves must hold, so a candidate inside the
    # required harness is still refused when it is not the required account.
    # Closest existing test: test_routing_units.py:120 requires harnesses only and
    # :486 requires accounts only; with only one set populated either connective
    # (`or`, `and`) passes them, and the composition is what a device sends when it
    # pins a mission to one account of one harness.
    accts = [acct('acc_a', 'h'), acct('acc_b', 'h'), acct('acc_c', 'g')]
    s = snap([harness('h'), harness('g')], accts)
    d = R.route(task(required={'harnesses': ['h'], 'accounts': ['acc_b']}), s)
    assert d['selected'] == 'acc_b'
    # acc_a is in the required harness: only the account half of the requirement
    # refuses it, and the id tie would have elected it (acc_a < acc_b)
    assert steps(d) == {'acc_a': 'restriction', 'acc_b': None, 'acc_c': 'restriction'}
    assert reason(d, 'acc_a') == reason(d, 'acc_c') == 'is not the one you required'
    # an empty second half asks nothing of it: the harness half alone still refuses
    d = R.route(task(required={'harnesses': ['h'], 'accounts': []}), s)
    assert steps(d) == {'acc_a': None, 'acc_b': 'election', 'acc_c': 'restriction'}
    assert d['selected'] == 'acc_a'


def test_a_project_in_both_the_allowed_and_the_denied_lists_stays_denied():
    # router.py:286-289 `_restriction`: the deny list is consulted first, so denying
    # a project wins over allowing it whatever the allow list says (`if project in
    # deny` before `if allow and project not in allow`).
    # Closest existing test: test_routing_units.py:476-484 exercises a deny hit and
    # an allow miss on DIFFERENT projects; no test has ever carried both lists with
    # the same project in them, which is the only composition where the order of the
    # two checks is observable - checking allow first would let a denied project run.
    a = acct('acc_a', 'h', project_allow=['prj_x', 'prj_y'], project_deny=['prj_y'])
    accts = [a, acct('acc_b', 'h', priority=2)]
    s = snap([harness('h')], accts)
    d = R.route(task(project_id='prj_y'), s)
    assert (d['selected'], steps(d)['acc_a']) == ('acc_b', 'restriction')
    assert reason(d, 'acc_a') == 'excluded for project prj_y by your resource rules'
    # the same policy still admits an allowed project, so the refusal is the deny
    # list and not simply a policy that names nothing the task is
    d = R.route(task(project_id='prj_x'), s)
    assert (d['selected'], d['result']) == ('acc_a', 'selected')


def test_an_open_breaker_is_never_a_fallback_even_when_the_policy_allows_ones():
    # router.py:315-317 `_breaker` refuses with a reason and, unlike `_health`
    # (router.py:328) and `_allocation` (router.py:349, 356, 361), never sets
    # `fallbackable`: so router.py:475-479 has nothing to pick and the decision is
    # blocked, while router.py:494-495 still names the breaker's `until`.
    # Closest existing test: test_routing_units.py:498 (O7) shows an open breaker to
    # a second harness with a plain account and no fallback policy, and
    # test_gaps_core_routing_router.py's breaker tests assert the reason and the
    # unblock time: none of them asks whether a `fallback: allow` account walks past
    # an open breaker, which is what running onto a broken harness would cost.
    h = harness('h')
    h['breaker'] = {'state': 'open', 'error': 'three failures in a row', 'until': UNTIL}
    a = acct('acc_a', 'h', usage=10.0, fallback='allow')
    d = R.route(task(), snap([h], [a]))
    assert (d['result'], d['selected'], d['account_id']) == ('blocked', None, None)
    assert steps(d) == {'acc_a': 'breaker'}
    assert field(d, 'acc_a', 'fallbackable') is False
    assert reason(d, 'acc_a') == 'cannot start: three failures in a row'
    assert d['unblock_at'] == UNTIL and d['fallback_from'] == []


def test_the_fullest_window_is_the_one_that_exhausts_an_account_whichever_it_is_named():
    # router.py:330-332 `_health`: `raw = worst(a.get('usage'), penalty=False)` is the
    # MAX over every window the feed reported, so a 5-hour reading of 10% beside a
    # weekly one of 100% is exhausted, refused at `health` and - because this step
    # sets no `fallbackable` for a routable account - never a fallback either.
    # Closest existing test: test_routing_units.py:262 and
    # test_fix_routing_router.py's degraded pair all build ONE window ('5h', the only
    # key the shared builder writes), so reading `windows['5h']` instead of the
    # maximum passes every test in the suite and starts work on an exhausted account.
    a = with_usage(acct('acc_a', 'h', fallback='allow'), {'5h': 10.0, '7d': 100.0})
    b = with_usage(acct('acc_b', 'h', priority=2), {'5h': 10.0})
    d = R.route(task(), snap([harness('h')], [a, b]))
    assert (d['result'], d['selected']) == ('selected', 'acc_b')
    assert steps(d) == {'acc_a': 'health', 'acc_b': None}
    assert reason(d, 'acc_a') == 'a usage window is exhausted (100%)'
    assert field(d, 'acc_a', 'fallbackable') is False and d['fallback_from'] == []
    # and the same fullest window answers the DEGRADED question (router.py:327-329):
    # an account whose fullest window is exhausted is not even a fallback
    d = R.route(task(), snap([harness('h')], [
        with_usage(acct('acc_a', 'h', health='DEGRADED', fallback='allow'),
                   {'5h': 5.0, '7d': 100.0})]))
    assert (d['result'], d['selected']) == ('blocked', None)
    assert (reason(d, 'acc_a'), field(d, 'acc_a', 'fallbackable')) == (
        'account is DEGRADED', False)


# ── 2. boundaries: a reading, a state, a ceiling ──────────────────────────────────

def test_a_stale_reading_is_stopped_by_the_ceiling_and_says_so_with_its_penalty():
    # router.py:342-354 `_allocation`: `w = worst(usage)` (the fullest window plus
    # the STALE_PENALTY when `age_s > STALE_S`) then `w + bump >= cap`, and the reason
    # names `stale usage (+5)` on the `usage['age_s'] > STALE_S` leg. A fresh 56% is
    # under the 60% task ceiling with its +3 projection (59), a stale one is 61 and
    # is not: the penalty is the whole decision, and it is what the reason must report.
    # Closest existing test: test_routing_units.py:255 (the stale penalty) asserts
    # only `result != 'selected'`, and no test in the suite mentions `stale usage`:
    # dropping the penalty would run the work, and reporting `usage at 61%` for a
    # reading that is 56% and merely old would tell the user a number they never saw.
    s = snap([harness('h')], [with_usage(acct('acc_a', 'h'), {'5h': 56.0}, age=999)])
    d = R.route(task(), s)                     # task ceiling 60, PROJECTED['M'] = 3
    assert (d['result'], d['selected']) == ('ask', None)
    assert steps(d) == {'acc_a': 'allocation'}
    assert field(d, 'acc_a', 'usage') == 61.0
    assert reason(d, 'acc_a') == ('stale usage (+5) at 61% (+3 projected) is not '
                                  'under its 60% ceiling for tasks')
    # the same snapshot with a fresh reading is under the ceiling: 56 + 3 < 60
    d = R.route(task(), snap([harness('h')], [
        with_usage(acct('acc_a', 'h'), {'5h': 56.0}, age=0)]))
    assert (d['result'], d['selected'], d['unblock_at']) == ('selected', 'acc_a', None)
    assert field(d, 'acc_a', 'usage') == 56.0 and reason(d, 'acc_a') is None


def test_a_constrained_account_is_an_ordinary_candidate_and_never_a_fallback_state():
    # router.py:326-329 `_health`: `if a['health'] not in ROUTABLE:` with the module's
    # ROUTABLE = ('AVAILABLE', 'CONSTRAINED') (router.py:60, resource-router.md:192
    # `health ... c.account.health in (AVAILABLE, CONSTRAINED)`): a CONSTRAINED
    # account is routed as any other, and only the states outside the tuple take the
    # `account is %s` refusal - whose `fallbackable` grant belongs to DEGRADED alone.
    # Closest existing test: test_routing_units.py:490-495 walks the five states OUTSIDE
    # the tuple (blocked) plus the DEGRADED fallback, and :531-532 draws a random
    # health for the determinism property without ever asserting what a CONSTRAINED
    # one decides: taking CONSTRAINED out of the routable set - the whole state then
    # refused, and not even a fallback, since it is not DEGRADED - passes every test
    # in the suite.
    s = snap([harness('h')], [acct('acc_a', 'h', usage=10.0, health='CONSTRAINED'),
                              acct('acc_b', 'h', priority=2, health='DEGRADED',
                                   fallback='allow')])
    d = R.route(task(), s)
    assert (d['result'], d['selected']) == ('selected', 'acc_a')
    assert steps(d) == {'acc_a': None, 'acc_b': 'health'}
    assert reason(d, 'acc_b') == 'account is DEGRADED'
    assert field(d, 'acc_a', 'fallbackable') is False     # elected, never a fallback
    # alone it is CHOSEN and not asked for: `fallback: deny` costs it nothing extra
    d = R.route(task(), snap([harness('h')], [acct('acc_a', 'h', usage=10.0,
                                                   health='CONSTRAINED', fallback='deny')]))
    assert (d['result'], d['selected'], d['fallback_from'], d['unblock_at']) == (
        'selected', 'acc_a', [], None)
    # and its ceiling still governs it: full, it is exhausted and never a fallback
    d = R.route(task(), snap([harness('h')], [acct('acc_a', 'h', usage=100.0,
                                                   health='CONSTRAINED', fallback='allow')]))
    assert (d['result'], d['selected']) == ('blocked', None)
    assert (steps(d)['acc_a'], field(d, 'acc_a', 'fallbackable')) == ('health', False)


def test_a_requirement_that_names_an_explicit_only_account_lifts_it_for_that_work_only():
    # router.py:301-303 `_named`: the lift is `preferred - conversational` UNION
    # `required` accounts, so a requirement from a user device makes an
    # `explicit_only` account a candidate, while a preference a conversation added
    # subtracts and never lifts it (router.py:290-291 keeps it refused).
    # Closest existing test: test_ap1_units.py:88 lifts an explicit_only account with
    # `preferred` only and refuses a bare one; test_routing_units.py:486 requires an
    # account that is not explicit_only at all. Neither puts a required name beside an
    # `explicit_only` class, so dropping `| _ids(req.get('required'), 'accounts')`
    # would refuse work a user explicitly asked to run there, and dropping the
    # conversational subtraction would let a chat message lift a class it may not.
    protected = acct('acc_a', 'h', consumption='explicit_only')
    accts = [protected, acct('acc_b', 'h', priority=2)]
    s = snap([harness('h')], accts)
    d0 = R.route(task(), s)
    assert (d0['selected'], steps(d0)) == ('acc_b', {'acc_a': 'restriction', 'acc_b': None})
    assert reason(d0, 'acc_a') == 'used only when you name it (explicit_only)'
    # the requirement lifts it, and the same requirement refuses everything else
    d = R.route(task(required={'accounts': ['acc_a']}), s)
    assert (d['result'], d['selected'], d['why']) == ('selected', 'acc_a',
                                                     'it is your priority-1 account')
    assert steps(d) == {'acc_a': None, 'acc_b': 'restriction'}
    # a preference that came from the conversation orders, it makes nothing eligible
    d = R.route(task(preferred={'accounts': ['acc_a']},
                     conversational={'accounts': ['acc_a']}), s)
    assert (d['selected'], steps(d)['acc_a']) == ('acc_b', 'restriction')


# ── 3. the paths a decision reports ───────────────────────────────────────────────

def test_only_a_blocked_decision_may_promise_a_time_when_the_resource_frees():
    # router.py:509-510 `route`: `'unblock_at': min(waits, ...) if waits and result
    # == 'blocked' else None` - a candidate stopped at `allocation` contributes its
    # reset to `waits` (router.py:492-493), but the promise belongs to `blocked`
    # alone: a `selected` decision has run, and an `ask` one is waiting for a
    # person, not for the clock.
    # Closest existing test: test_gaps_core_routing_router.py's reset test reads the
    # unblock time of a BLOCKED decision and asserts None for a world with no waits,
    # and test_routing_units.py:311 same; none carries a future reset beside a
    # decision that is not blocked, so writing the wait for an `ask` would pass them
    # all - and the task would sit waiting for a reset instead of asking the user.
    spent = with_usage(acct('acc_a', 'h', fallback='ask'), {'5h': 70.0}, reset=FUTURE)
    dead = with_usage(acct('acc_b', 'h', priority=2, fallback='deny'), {'5h': 100.0})
    d = R.route(task(), snap([harness('h')], [dict(spent),
                                              with_usage(acct('acc_b', 'h', priority=2),
                                                         {'5h': 10.0})]))
    assert (d['result'], d['selected']) == ('selected', 'acc_b')
    assert steps(d)['acc_a'] == 'allocation' and d['unblock_at'] is None
    assert d['fallback_from'] == []                       # only fallback and ask carry it
    # the same account alone, askable: the user is asked, and no time is promised
    d = R.route(task(), snap([harness('h')], [dict(spent), dict(dead)]))
    assert (d['result'], d['selected'], d['fallback_from']) == ('ask', None, ['acc_b'])
    assert steps(d) == {'acc_a': 'allocation', 'acc_b': 'health'}
    assert d['unblock_at'] is None
    # and refused outright the same reset becomes the unblock time it does promise
    d = R.route(task(), snap([harness('h')], [
        with_usage(acct('acc_a', 'h', fallback='deny'), {'5h': 70.0}, reset=FUTURE)]))
    assert (d['result'], d['unblock_at']) == ('blocked', FUTURE)


def test_a_mission_already_running_on_a_harnesss_own_account_stays_on_it():
    # router.py:406-407 `order_key`: `affine = bool(aff) and (c['harness'], _key(c))
    # == (aff.get('harness'), aff.get('account'))`, where `_key` (router.py:116) is
    # `c['account'] or c['account_ref'] or c['harness']` - the continuity key of an
    # UNREGISTERED account is its ref, so affinity to `h:default` outranks priority
    # and the resource id.
    # Closest existing test: test_routing_units.py:406-411 keeps continuity for a
    # REGISTERED account, and :417-419 points affinity at an own account that is
    # refused for capability anyway; test_gaps_core_routing_router.py:195-214 reads
    # `_key` for an own account but at the APPROVED-FALLBACK pick (router.py:477-479)
    # with no affinity in the snapshot, and it passes when the affinity comparison is
    # degraded to the harness alone. No test asserts that continuity to a default
    # account WINS the election: comparing the affinity on the harness only would
    # honour a continuity record for an account the mission never ran on, and reading
    # `_key` as `c['account']` alone would compare None with 'h:default', lose the
    # affinity and hop the task onto another account mid-mission.
    # the two harnesses would be ordered by resource id, so `h` winning is continuity
    s = snap([harness('g'), harness('h')], [own('g'), own('h')],
             affinity={'harness': 'h', 'account': 'h:default'})
    d = R.route(task(), s)
    assert (d['result'], d['selected'], d['account_id'], d['account_ref']) == (
        'selected', 'h', None, 'h:default')
    assert steps(d) == {'g': 'election', 'h': None}
    assert d['why'] == "it is h's own account, and this mission was already running there"
    # continuity outranks priority on the same harness: the registered account is the
    # one with a policy, and the mission is already running on the default one
    s = snap([harness('h')], [own('h'), acct('acc_a', 'h')],
             affinity={'harness': 'h', 'account': 'h:default'})
    d = R.route(task(), s)
    assert (d['selected'], steps(d)) == ('h', {'h': None, 'acc_a': 'election'})
    # the affinity is exact: an account element that matches nothing decides by id
    s = snap([harness('g'), harness('h')], [own('g'), own('h')],
             affinity={'harness': 'h', 'account': 'acc_zzz'})
    assert R.route(task(), s)['selected'] == 'g'
