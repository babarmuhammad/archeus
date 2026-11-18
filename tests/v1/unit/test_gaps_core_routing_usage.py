"""T-760: the ten highest-risk uncovered branches of archeus/core/routing/usage.py,
as tests. Fail-closed and denial paths first (a feed that must report *nothing*
rather than a number it did not observe: an unset script with no default, a poller
that did not answer `ok`, windows that are not the account's, a window nobody ever
read, a foreign harness, an account with no home), then the boundary values (an
observed 0% is a reading while nothing is unknown; the last script word; the
freshest observation; the exact label translation), then the error paths (a percent
written as text, the poller asked at the expanded home with `poll=True`).
Nothing here reads the OS, the clock, the network or a process: the legacy poller is
faked through its own documented seam (`claude_sessions.usage.windows_snapshot`,
the P10 preparation seam named in the module docstring) and `os.path.expanduser`
is scripted so no assertion depends on the shape of a home directory; the file runs
unchanged on Linux and on Windows. Same builders as test_routing_units.py, imported
and not copied (the style of test_gaps_core_routing_router.py).

Each test names the source branch it kills; removing or inverting that branch fails
the test.
"""

import os

import pytest

from archeus.core.routing import router as R
from archeus.core.routing import usage as U
from archeus.core.routing.usage import FakeUsageFeed, LegacyUsageFeed, NoUsageFeed
from claude_sessions import usage as poller          # the windows_snapshot seam
from v1.unit.test_routing_units import acct, harness, snap, steps, task


def account(**kw):
    """The account dict a feed is asked about, exactly as resources._registered
    builds it: id, harness and home."""
    a = {'id': 'acc_a', 'harness_id': 'claude_code', 'home_ref': 'acct-home'}
    a.update(kw)
    return a


def poller_answers(monkeypatch, windows, observed_at, status):
    """Fake the legacy poller through its seam: records every call, answers with
    the scripted (windows, observed_at, status) triple."""
    calls = []

    def snapshot(cfgdir, poll=False):
        calls.append((cfgdir, poll))
        return windows, observed_at, status

    monkeypatch.setattr(poller, 'windows_snapshot', snapshot)
    return calls


def usage_of(feed, acct_dict, now=1000.0):
    """The reading as resources._registered turns it into the snapshot's `usage`:
    the windows as read, an age against `now`, the feed's own source (a reading
    of None stays None: unknown is carried, never invented)."""
    rd = feed.read(acct_dict)
    if rd is None:
        return None
    return {'windows': dict(rd['windows']), 'resets_at': {},
            'age_s': max(0, round(now - rd['observed_at'], 3)), 'source': rd['source']}


# ── 1. fail-closed: nothing observed is reported as nothing ─────────────────

def test_an_account_the_script_never_set_with_no_default_is_unknown_not_zero():
    """usage.py:36-37, `if got is None: if self.default_pct is None: return None`.

    Kills: replacing that `return None` with a manufactured 0% reading (the exact
    confusion the module docstring forbids — an unobserved 0% would route work to
    an account whose provider was never asked, and a 0% is the best standing an
    account can have, so the invented reading wins every election). The scripted
    script of ANOTHER account must not leak in either: a set for `acc_x` is not a
    reading for `acc_a`."""
    feed = FakeUsageFeed(default_pct=None, clock=lambda: 1234.5)
    assert feed.read(account()) is None
    assert feed.read({'id': 'acc_other'}) is None
    feed.set('acc_x', '5h', 5.0)
    assert feed.read(account()) is None                       # still nothing known


@pytest.mark.parametrize('status', ['unknown', 'no_creds', 'expired', 'error'],
                         ids=['never_polled', 'no_creds', 'expired', 'error'])
def test_a_poller_that_did_not_answer_ok_tells_nothing_even_with_windows_behind_it(
        monkeypatch, status):
    """usage.py:67, the left leg `status != 'ok'` of the fail-closed guard.

    Kills: dropping the status test, which would report the stale cache of a
    failed, never-run or credentialed-out poll as a fresh reading — the poller
    keeps the last windows it fetched, so an account whose fetch has been failing
    for hours would keep its old percentages and the router would honour them.
    Every status here is one the poller really answers (claude_sessions/usage.py
    STATUS_TEXT / windows_snapshot: 'unknown' before it ever polled)."""
    poller_answers(monkeypatch, [('session', 20.0, 'in 5m')], 1000.0, status)
    assert LegacyUsageFeed().read(account()) is None


@pytest.mark.parametrize('windows', [
    [],                                                        # the poller fetched nothing
    [('model_weekly', 99.0, 'soon'), ('week', 50.0, 'later')],  # not account-wide labels
], ids=['nothing_fetched', 'per_model_only'])
def test_windows_that_are_not_the_accounts_own_tell_nothing(monkeypatch, windows):
    """usage.py:65-66 (`if label in LEGACY_WINDOWS`) and usage.py:67's middle leg
    `not got`.

    Kills: dropping the label filter (a per-model weekly limit — NOT the account's
    ceiling, the constant's own comment — would enter the windows the router takes
    the worst of, at 99% here, and a mis-named label raises KeyError at
    `LEGACY_WINDOWS[label]` all the same), and dropping `not got` (an empty
    reading would then carry `windows: {}`, which the router reads as unknown
    anyway but without a source or an observed_at it never had)."""
    poller_answers(monkeypatch, windows, 1000.0, 'ok')
    assert LegacyUsageFeed().read(account()) is None


def test_a_window_nobody_ever_read_is_unknown_though_the_poller_answered_ok(monkeypatch):
    """usage.py:67, the right leg `observed_at is None`.

    Kills: dropping that leg: an `ok` status with a never-fetched window (the
    poller answers `observed_at=None` before its first good fetch) would become a
    reading whose `observed_at` is None — and resources._registered computes
    `age_s = max(0, round(now - rd['observed_at'], 3))`, a TypeError inside the
    writer's transaction, with no reading to fail closed on."""
    poller_answers(monkeypatch, [('session', 20.0, 'in 5m')], None, 'ok')
    assert LegacyUsageFeed().read(account()) is None


@pytest.mark.parametrize('other', ['codex', 'gemini_cli', 'Claude_Code'],
                         ids=['codex', 'gemini_cli', 'upper_claude_code'])
def test_a_foreign_harness_never_reaches_the_claude_poller(monkeypatch, other):
    """usage.py:60-61, the left leg `account['harness_id'] != 'claude_code'` of the
    refusal, and the `return None` it guards.

    Kills: inverting or dropping the test — reading the Claude Code poller for
    ANOTHER harness's home would lend one vendor's plan window to a different
    vendor's account (the module: every other harness "reports no window here, so
    its accounts are governed by budgets"). The `Claude_Code` case kills a widened
    comparison (`casefold()` / `lower()`): the id is an exact key, and a
    case-insensitive match would route the poller off a home that holds no Claude
    state. The recorded calls prove the poller was never touched."""
    calls = poller_answers(monkeypatch, [('session', 20.0, 'in 5m')], 1000.0, 'ok')
    assert LegacyUsageFeed().read(account(harness_id=other)) is None
    assert calls == []


@pytest.mark.parametrize('home', ['', None, 'missing'], ids=['empty', 'none', 'missing'])
def test_a_claude_account_with_no_home_tells_nothing_without_reading_the_poller(
        monkeypatch, home):
    """usage.py:60, the right leg `not account.get('home_ref')`.

    Kills: (a) dropping the leg — a home-less account would be polled at the
    poller's DEFAULT config dir, reading whoever-the-machine-is-signed-in's
    credentials as that account's usage; (b) reading the leg as
    `account['home_ref']` — the `missing` case (no key at all, the shape a
    snapshot from before home_ref carried) would raise KeyError instead of
    reporting nothing."""
    calls = poller_answers(monkeypatch, [('session', 20.0, 'in 5m')], 1000.0, 'ok')
    a = {'id': 'acc_a', 'harness_id': 'claude_code'}
    if home != 'missing':
        a['home_ref'] = home or None
    assert LegacyUsageFeed().read(a) is None
    assert calls == []


# ── 2. the boundaries: empty against unknown, last word, freshest reading ───

def test_an_observed_empty_window_is_a_reading_not_an_unknown():
    """usage.py:36 (`got is None`) and usage.py:39 (`got = {'5h': (float(self
    .default_pct), None, self.clock())}`) — with the DEFAULT `default_pct=0.0`.

    Kills: widening line 36-37 to a truthiness test (`if not self.default_pct:
    return None`) — 0.0 is falsy, and an observed-empty window would become
    unknown, which at the router is a DIFFERENT decision (an account with no
    budget and no reading is fallback-only, an account read at 0% is selected —
    see test_a_route_selects_the_account_whose_window_was_read_empty below).
    The comparison is `is None` on both legs, and this pins it at both ends."""
    feed = FakeUsageFeed(clock=lambda: 1234.5)                 # default_pct 0.0
    rd = feed.read(account())
    assert (rd['windows'], rd['resets_at'], rd['observed_at'], rd['source']) == (
        {'5h': 0.0}, {}, 1234.5, 'scripted')


def test_a_percent_written_as_text_is_stored_as_a_number_and_the_last_word_wins():
    """usage.py:32, `self._set.setdefault(account_id, {})[window] = (float(pct),
    resets_at, self.clock())` — the `float(pct)` coercion, the per-account
    `setdefault` and the whole-window overwrite.

    Kills: (a) dropping `float(...)` — a provider-ish caller passing '27.5' would
    store the string, `read()` would hand it to the router and `max(windows
    .values())` (router.worst) raises TypeError comparing str to int inside the
    writer's transaction; (b) merging instead of overwriting, which would let a
    stale script of the same window survive the newer one; (c) a script for one
    account leaking into another."""
    feed = FakeUsageFeed(default_pct=None, clock=lambda: 7.0)
    feed.set('acc_a', '5h', '27.5')
    rd = feed.read(account())
    assert rd['windows'] == {'5h': 27.5} and type(rd['windows']['5h']) is float
    feed.set('acc_a', '5h', 12.5)                              # same window again
    assert feed.read(account())['windows'] == {'5h': 12.5}
    feed.set('acc_b', '7d', 5.0)                               # another account only
    assert feed.read(account(id='acc_b'))['windows'] == {'7d': 5.0}
    assert feed.read(account())['windows'] == {'5h': 12.5}     # acc_a untouched


def test_the_script_reads_at_its_freshest_window_and_drops_an_empty_reset():
    """usage.py:41 (`if v[1]` of the resets_at comprehension) and usage.py:42
    (`observed_at: max(v[2] for v in got.values())`).

    Kills: (a) dropping the resets filter — a `''` reset (the poller's own "no
    reset stated", and what `_extract_windows` leaves when a field is absent)
    would enter `resets_at`, and resources._registered would hand it to
    `instants.ahead`, making the router promise the user a wait at nothing; (b)
    taking the LAST reading (`list(got.values())[-1][2]`) or the EARLIEST
    (`min`) instead of the max: the windows were set at 100.0 then 90.0, so only
    `max` answers 100.0 — the age the router charges (and its stale penalty) is
    computed against the freshest observation, not the oldest."""
    ticks = [100.0, 90.0]
    feed = FakeUsageFeed(default_pct=None, clock=lambda: ticks.pop(0))
    feed.set('acc_a', '5h', 30.0, 'in 40m')
    feed.set('acc_a', '7d', 12.0, '')                           # no reset stated
    rd = feed.read(account())
    assert rd['windows'] == {'5h': 30.0, '7d': 12.0}
    assert rd['resets_at'] == {'5h': 'in 40m'}                  # the '' never enters
    assert rd['observed_at'] == 100.0                           # max, not 90.0


def test_the_pollers_own_labels_are_translated_to_the_v1_windows_exactly(monkeypatch):
    """usage.py:17 (LEGACY_WINDOWS itself), the mapping `LEGACY_WINDOWS[label]` at
    usage.py:65, and usage.py:69-70 (the reading's `resets_at` filter `if v[1]`
    and `observed_at` passed through untouched).

    Kills: (a) swapping the mapping ('session'->'7d', 'weekly'->'5h'): the
    5-hour window is the one the router's health step reads as exhausted at 100
    and the one whose resets become `unblock_at`, so a swapped pair applies the
    weekly percentage to the 5h ceiling and vice versa; (b) dropping the filter
    (KeyError on 'model_weekly'); (c) dropping the legacy resets filter, which
    would carry the weekly's None reset as a real one. The unmapped per-model
    label at 100.0 must contribute NOTHING, and `source` says where it came from."""
    poller_answers(monkeypatch, [('session', 99.5, 'in 40m'), ('weekly', 12.0, None),
                                 ('model_weekly', 100.0, 'soon')], 1234.0, 'ok')
    rd = LegacyUsageFeed().read(account())
    assert U.LEGACY_WINDOWS == {'session': '5h', 'weekly': '7d'}
    assert rd['windows'] == {'5h': 99.5, '7d': 12.0}            # not {'7d': 99.5, ...}
    assert rd['resets_at'] == {'5h': 'in 40m'}                  # the weekly's None, no
    assert rd['observed_at'] == 1234.0 and rd['source'] == 'usage_api'


# ── 3. the error paths at the seams the module itself names ──────────────────

def test_the_poller_is_asked_at_the_expanded_home_and_told_to_poll(monkeypatch):
    """usage.py:63-64, `usage.windows_snapshot(os.path.expanduser(account
    ['home_ref']), poll=True)` — both the expansion and the `poll=True` flag.

    Kills: (a) dropping `expanduser` — the poller keys its cache on
    `normcase(abspath(cfgdir))`, so the literal '~/acct' would be looked up as a
    directory
    literally named '~' and the account would report nothing forever, silently;
    (b) dropping `poll=True` — windows_snapshot only calls `_ensure_started()`
    when polled, so the background poller would never start and the cache would
    stay empty forever. `expanduser` is scripted to a marker, so the assertion
    cannot depend on what a home directory looks like on either OS."""
    seen = []

    def snapshot(cfgdir, poll=False):
        seen.append((cfgdir, poll))
        return [('session', 20.0, 'in 5m')], 1000.0, 'ok'

    monkeypatch.setattr(poller, 'windows_snapshot', snapshot)
    monkeypatch.setattr(os.path, 'expanduser', lambda p: '<HOME:%s>' % p)
    rd = LegacyUsageFeed().read(account(home_ref='~/acct'))
    assert seen == [('<HOME:~/acct>', True)]                    # expanded, and polled
    assert rd['windows'] == {'5h': 20.0}


def test_nothing_is_known_about_any_shape_of_account():
    """usage.py:49-50, NoUsageFeed.read's unconditional `return None` (and its
    `source = 'usage_api'` at usage.py:47, which is what the decision records as
    the origin of "we never read it").

    Kills: NoUsageFeed degenerating into a fake that answers `{}` or a 0% (a
    falsy `{}` would pass `if fed:` nowhere but still enter `rd = fed or
    latest_usage(...)` with the wrong precedence semantics downstream, and a
    0% would make every unread account the best candidate it has), and a subclass
    slip giving it Claude Code's poller read: no account shape — complete, bare
    or empty — may produce anything but None, and no poller is installed here to
    be read."""
    feed = NoUsageFeed()
    assert feed.source == 'usage_api'
    for a in (account(), {'id': 'acc_a', 'harness_id': 'codex'}, {}):
        assert feed.read(a) is None


# ── 4. the same facts as a routing choice at the limits ──────────────────────

def test_a_route_with_nothing_to_read_and_no_budget_never_selects_the_account():
    """usage.py:36-37 again (`return None`) at the choice it exists to make: the
    reading feeds the snapshot exactly as resources._registered builds it
    (`usage_of`), and the router must treat "nothing observed" as unknown.

    Kills: the manufactured 0% of branch 1 — with it, `usage_of` would hand the
    router windows {'5h': 0.0}, the account would be SELECTED, and work would run
    on an account whose provider was never asked. A NoUsageFeed reading must
    decide the identical way: the two feeds are interchangeable at unknown."""
    def route_with(feed):
        a = acct('acc_a', 'h')
        a['usage'] = usage_of(feed, account())                  # None: nothing read
        return R.route(task(), snap([harness('h')], [a]))

    for d in (route_with(FakeUsageFeed(default_pct=None)), route_with(NoUsageFeed())):
        assert (d['result'], d['selected'], d['account_id']) == ('ask', None, 'acc_a')
        assert steps(d) == {'acc_a': 'allocation'}
        c = next(x for x in d['candidates'] if x['resource'] == 'acc_a')
        assert (c['usage'], c['reason']) == (
            None, 'no readable usage window and no budget: used only as a fallback')
        assert d['unblock_at'] is None                          # a promise of nothing


def test_a_route_selects_the_account_whose_window_was_read_empty():
    """usage.py:36/39 (`got is None` / the 0.0 default) at the OTHER side of the
    same limit: the reading is real, and the choice it earns is a selection.

    Kills: the truthiness widening of branch 2 (a 0.0 read as unknown would make
    this test's account fall to `ask` above), which is the whole empty-versus-
    unknown contract: two accounts identical but for one line of the feed are
    `ask` and `selected`, and their candidates differ only by the reading."""
    a = acct('acc_a', 'h')
    a['usage'] = usage_of(FakeUsageFeed(clock=lambda: 1000.0), account())
    d = R.route(task(), snap([harness('h')], [a]))
    assert (d['result'], d['selected'], d['account_id']) == ('selected', 'acc_a', 'acc_a')
    assert steps(d) == {'acc_a': None}
    c = next(x for x in d['candidates'] if x['resource'] == 'acc_a')
    assert (c['usage'], c['constrained']) == (0.0, False)       # read, and far under
