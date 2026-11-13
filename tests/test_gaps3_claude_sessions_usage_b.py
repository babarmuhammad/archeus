"""T-1172: the ten highest-risk uncovered branches of claude_sessions/usage.py
lines 244-459 (inclusive) at tip 56d53504, as tests. Fail-closed / denial first,
then boundaries, then error paths:

 1. windows_snapshot: a config dir the poller never answered for reports
    ([], None, 'unknown') and NEVER the cached capacity of another account
    (usage.py:254-259).
 2. windows_snapshot: poll=False must not start the background worker;
    poll=True starts exactly one thread running _background (usage.py:252-253).
 3. _extract_windows: non-dict rows inside limits[] are dropped, and a hostile
    string row cannot crash the banner via .get (usage.py:331-332, 334-335).
    [replaces probe 4 only in ordering; the probe list itself keeps its numbers]
 4. _extract_windows: a boolean percent/utilization is float(True)=1.0, not a
    full window, and False stays an observed 0.0 row (usage.py:320-324,
    333-335).
 5. usage_status_line: the daily-token badge needs the threshold, is skipped
    when unset, and a raising stats cache cannot break the banner
    (usage.py:451-457). [replaces probe 3 "nondict payload": that branch
    (317-318) is already covered by tests/test_usage.py::test_empty_and_nondict
    and tests/test_tui_stats.py, so it is not a gap; this one is]
 6. _extract_windows: the limits[] array is authoritative when it disagrees
    with the legacy top-level dicts, and the legacy fallback runs ONLY when
    limits said nothing usable (usage.py:339).
 7. _pct_color: the 50 and 80 thresholds are inclusive and checked in that
    order (usage.py:278-282).
 8. _account_grid: the same label across accounts shares one column, an
    all-zero column is dropped, an all-zero table keeps one column, and
    accounts with no windows at all are named as notes, never bars
    (usage.py:368-384, 395-398).
 9. _extract_windows norm(): inf/1e999 clamp to 100.0, -inf clamps to 0.0,
    'abc'/missing are dropped — and NaN must not be published as an observed
    0% window (usage.py:320-324). The NaN leg is a strict xfail: the source
    defect is documented on the marker. [probe 6; finite negatives were already
    covered by tests/test_regressions.py::test_usage_clamp_and_zero, so this
    test pins only the uncalled extreme/unparsable legs]
10. _fmt_reset / _one_account_line: a garbage or missing reset stamp renders
    '?' or nothing and can never promise a time; the today/weekday/Z legs of
    _fmt_reset and the arrow leg of _one_account_line were never executed
    (usage.py:267-274, 415-416).

Everything here is faked through the module's own seams: the poller state dict,
the started/ready flags, threading.Thread, config.load_settings and the
claude_sessions.stats cache functions. No test reads the host config dir, the
network, a credential file or the real environment; all paths come from
tmp_path. Runs unchanged on Linux and Windows.
"""

import os
import re
from datetime import datetime, timedelta, timezone

import pytest

from claude_sessions import config as _c
from claude_sessions import render, stats as stats_mod
from claude_sessions import usage as u


def _wdict(windows):
    return {label: pct for label, pct, _reset in windows}


@pytest.fixture(autouse=True)
def _no_live_poller(monkeypatch):
    """Fresh module state for every test, and a thread factory that refuses."""
    monkeypatch.setattr(u, '_acct_state', {}, raising=False)
    monkeypatch.setattr(u, '_data', None, raising=False)
    monkeypatch.setattr(u, '_ready', False, raising=False)
    monkeypatch.setattr(u, '_started', True, raising=False)  # _ensure_started = no-op
    monkeypatch.setattr(_c, 'load_settings', lambda: {}, raising=False)

    class _NeverThread:
        def __init__(self, *a, **k):
            raise AssertionError('this test may not create a poller thread')

    monkeypatch.setattr(u.threading, 'Thread', _NeverThread)


# ── 1. denial: the snapshot may only ever report what THIS dir observed ──────

def test_windows_snapshot_of_an_unqueried_dir_is_unknown_not_a_cached_accounts_capacity(tmp_path, monkeypatch):
    """usage.py:254-259 (`want = normcase(abspath(...))`, the `== want`
    predicate of the next(), `if not st: return [], None, 'unknown'`).

    Kills: dropping the `== want` predicate (the first cached account would
    answer for every queried dir — the V1 router would then honour one
    account's empty windows as another's, exactly the "unknown reported as 0%"
    the docstring at 244-250 forbids), or widening it to a prefix test (the
    'acctAB' near-miss would inherit 'acctA's windows)."""
    a = str(tmp_path / 'acctA')
    b = str(tmp_path / 'acctB')
    hostile = {'limits': [{'kind': 'session', 'percent': 0, 'resets_at': None}]}
    u._acct_state[a] = {'name': 'A', 'status': 'ok', 'data': hostile,
                        'fetched_at': 111.0}

    assert u.windows_snapshot(a) == ([(('session'), 0.0, None)], 111.0, 'ok')
    assert u.windows_snapshot(b) == ([], None, 'unknown')
    assert u.windows_snapshot(a + 'B') == ([], None, 'unknown')
    assert u.windows_snapshot(os.path.join(a, '')) == ([('session', 0.0, None)],
                                                        111.0, 'ok')

    # the default cfgdir follows config.config_dir, and an entry with neither
    # data nor status is 'unknown', not a fabricated 0% (258-259, 262)
    monkeypatch.setattr(_c, 'config_dir', b)
    assert u.windows_snapshot() == ([], None, 'unknown')
    u._acct_state[b] = {'status': '', 'fetched_at': 5.0}
    assert u.windows_snapshot(b) == ([], 5.0, 'unknown')
    u._acct_state[b] = {'status': 'ok', 'data': [], 'fetched_at': 7.0}
    assert u.windows_snapshot(b) == ([], 7.0, 'ok')

    # a read must never write: no new entries, no promotion into _data
    assert u._data is None
    assert sorted(u._acct_state) == sorted([a, b])


def test_windows_snapshot_without_poll_never_starts_the_worker_thread(tmp_path, monkeypatch):
    """usage.py:252-253 (`if poll: _ensure_started()`).

    Kills: (a) starting the poller regardless of `poll` — every V1 router read
    would spawn the background loop from a path documented as cache-only, with
    no one having asked; (b) never honouring `poll=True` — the cache would stay
    empty forever, because nothing else in this module starts the loop for a
    first read. `Thread` is faked, so the assertion cannot depend on real
    thread inventories."""
    started = []

    class _Recorder:
        def __init__(self, *a, **k):
            self.target = k.get('target')

        def start(self):
            started.append(self.target)

    monkeypatch.setattr(u.threading, 'Thread', _Recorder)
    real_ensure = u._ensure_started
    calls = []

    def spy():
        calls.append(1)
        return real_ensure()

    monkeypatch.setattr(u, '_ensure_started', spy)
    monkeypatch.setattr(u, '_started', False)

    d = str(tmp_path / 'acct')
    u._acct_state[d] = {'status': 'ok', 'data': None}

    u.windows_snapshot(d)                       # the documented default: False
    u.windows_snapshot(d, poll=False)
    assert calls == [] and started == []

    u.windows_snapshot(d, poll=True)
    assert calls == [1]
    assert started == [u._background]           # exactly one worker, the loop itself
    assert u.windows_snapshot(d, poll=True)     # started now; no second thread
    assert len(started) == 1


# ── 2. denial: hostile payload shapes cannot crash or inflate the banner ──────

def test_non_dict_rows_in_the_limits_array_are_dropped_not_trusted():
    """usage.py:331-332 (`if not isinstance(item, dict): continue`) and the
    `pct is None` skip at 334-335.

    Kills: (a) removing the isinstance guard — a string row then raises
    AttributeError inside the poller-facing extractor, and `usage_status_line`
    (the caller the GUI/TUI reaches with no try/except of its own around
    _extract_windows) dies instead of degrading to no line; (b) turning the
    `continue` into an append of a fabricated 0% row. Note the non-dict PAYLOAD
    case itself (317-318) is NOT a gap: tests/test_usage.py::test_empty_and_nondict
    already pins it for None/{} — only the limits-row shape was."""
    data = {'limits': ['session:100', None, 7,
                       {'kind': 'weekly_all'},                    # no percent
                       {'kind': 'session', 'percent': 40, 'resets_at': None}]}
    assert u._extract_windows(data) == [('session', 40.0, None)]


def test_boolean_utilization_is_one_percent_and_false_is_an_observed_zero_row():
    """usage.py:320-324 (`float(v)` inside norm) with bool inputs, and the
    `if pct is None: continue` identity-tests at 333-335 / 344-345.

    Kills: (a) any truthiness shortcut (`100.0 if v else None`, or dropping the
    float() and letting `True` pass through into `pct:>4.0f`) — a hostile body
    of {'percent': true} must read as 1.0, never as a full window; (b) an
    `if not pct: continue` widening — False is float 0.0, an OBSERVED row, and
    dropping it would turn a measured-empty window into the same nothing as
    never having been polled (the P10 distinction of the windows_snapshot
    docstring)."""
    assert u._extract_windows({'limits': [{'kind': 'session',
                                           'percent': True}]}) == [('session', 1.0, None)]
    assert u._extract_windows({'limits': [{'kind': 'session',
                                           'percent': False}]}) == [('session', 0.0, None)]
    assert u._extract_windows({'five_hour': {'utilization': True}}) == [('session', 1.0, None)]
    assert _wdict(u._extract_windows({'five_hour': {'utilization': False}})) == {'session': 0.0}


def test_daily_token_alert_badge_needs_the_threshold_and_never_breaks_the_banner(monkeypatch):
    """usage.py:451-457: the `or 0` default, `if alert:` (452), `tot >= alert`
    (455) and the `except Exception: pass` (457).

    Kills: (a) the badge appearing below the threshold (`>=` → `>`, or the
    comparison dropped), (b) the stats cache being consulted when no alert is
    configured — `today_tokens` walks every session file, which the docstring
    promises only "cache-only, cheap" when an alert exists, (c) a raising stats
    cache taking the whole banner down (the except must swallow), and (d) any
    write-back into the poller's state from a display call. `load_settings` is
    faked, so no host settings file is read; `today_tokens`/`fmt_tok` are faked
    before the lazy import at 453 can reach the real cache."""
    win = {'limits': [{'kind': 'session', 'group': 'session', 'percent': 12,
                       'resets_at': None}]}
    monkeypatch.setattr(u, '_ready', True)
    monkeypatch.setattr(u, '_data', win)
    monkeypatch.setattr(_c, 'load_settings', lambda: {'daily_token_alert': 1000})
    consulted = []
    monkeypatch.setattr(stats_mod, 'today_tokens',
                        lambda: (consulted.append(1), 1500)[1])
    monkeypatch.setattr(stats_mod, 'fmt_tok', lambda n: f'{n // 1000}k')

    line = u.usage_status_line()
    assert 'session' in line and 'today 1k tok ⚠' in line      # at/above: badge

    monkeypatch.setattr(stats_mod, 'today_tokens',
                        lambda: (consulted.append(1), 999)[1])
    assert '⚠' not in u.usage_status_line()                     # below: no badge

    monkeypatch.setattr(stats_mod, 'today_tokens',
                        lambda: (consulted.append(1), 1000)[1])
    assert '⚠' in u.usage_status_line()                         # boundary: >= keeps it

    consulted.clear()
    monkeypatch.setattr(_c, 'load_settings', lambda: {'daily_token_alert': 0})
    assert '⚠' not in u.usage_status_line()
    assert consulted == []                                      # never consulted

    def boom():
        raise RuntimeError('stats cache sits on a dead disk')
    monkeypatch.setattr(_c, 'load_settings', lambda: {'daily_token_alert': 1000})
    monkeypatch.setattr(stats_mod, 'today_tokens', boom)
    line = u.usage_status_line()
    assert 'session' in line and '⚠' not in line                # swallowed at 457
    assert u._data is win and u._acct_state == {}               # read-only display


# ── 3. boundaries: which source wins, where a color flips, one column ───────

def test_the_limits_array_is_authoritative_and_the_legacy_dicts_fill_only_its_silence():
    """usage.py:339 (`if not out:`).

    Kills: dropping `if not out:` — tests/test_usage.py::test_real_shape_uses_limits_array
    cannot see this: its REAL payload carries legacy utilizations of 18/23 and
    limits percents of 18/23, IDENTICAL values, so a mutant that also appends
    the legacy rows produces the same answer. Here the two sources DISAGREE
    (10/20 vs 95/88) and the exact list pins precedence, including row order
    from the sort at 348-349. The second half kills inverting `if not out` to
    `if out`: with every limits percent unparsable, the legacy fallback must
    still answer."""
    data = {'limits': [{'kind': 'session', 'percent': 10},
                       {'kind': 'weekly_all', 'percent': 20}],
            'five_hour': {'utilization': 95}, 'seven_day': {'utilization': 88}}
    assert u._extract_windows(data) == [('session', 10.0, None),
                                        ('weekly', 20.0, None)]
    fallback = {'limits': [{'kind': 'session', 'percent': 'oops'}],
                'five_hour': {'utilization': 33}}
    assert u._extract_windows(fallback) == [('session', 33.0, None)]


def test_pct_color_thresholds_are_inclusive_at_50_and_80():
    """usage.py:278-282 (`if pct >= 80`, `if pct >= 50`).

    Kills: (a) swapping the two thresholds — 80 must be C_ERR, and with the
    tests swapped a 50 would answer C_ERR while 80 never reaches the check;
    (b) `>` instead of `>=` on either — an account AT exactly 50/80 renders in
    the calm color, hiding the very escalation the colors exist to warn about.
    Nothing in the suite asserted any >=50 return value: the only rendered
    percentages were 5/11/18/23 (C_OK legs), see tests/test_usage.py."""
    assert len({_c.C_OK, _c.C_WARN, _c.C_ERR}) == 3
    for pct in (0.0, 1, 49.9, 49.999):
        assert u._pct_color(pct) == _c.C_OK, pct
    for pct in (50, 50.0, 60, 79.9):
        assert u._pct_color(pct) == _c.C_WARN, pct
    for pct in (80, 80.0, 100.0):
        assert u._pct_color(pct) == _c.C_ERR, pct


def test_one_shared_column_zero_only_columns_drop_and_silent_accounts_are_named():
    """usage.py:368-384: the column dedup at 374-378 (same label from two
    accounts = ONE column), `if not rows: return '\\n'.join(notes)` at 380-381,
    the `any(r[1].get(c, (0,))[0] ...)` prune at 382, `if not cols:
    cols = list(seen_cols)[:1]` at 383-384, the status gate at 369, and the
    truthy-reset leg at 398.

    Kills: (a) breaking the label dedup (two 'session' columns for two
    accounts); (b) dropping the prune (an account-wide 0% column, which nobody
    observed as anything but empty, still eats a grid column); (c) dropping
    `if not cols:` — an all-zero table would render a header-only frame with no
    column at all; (d) rendering bars for accounts with no data (the `not rows`
    early return and the status gate at 369: '' and 'ok' get NO note — a silent
    ok account must not be accused, an unknown-status account must not vanish
    silently). tests/test_usage.py::test_multi_account_bars shares ONE win dict
    between both accounts at 11%: dedup, prune, empty-cols and notes all never
    executed there."""
    reset_dt = datetime.now(timezone.utc) + timedelta(days=2)
    reset_iso = reset_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    shown = reset_dt.astimezone().strftime('%a %H:%M')

    def win(kind, pct, reset=None):
        return {'limits': [{'kind': kind, 'percent': pct, 'resets_at': reset}]}

    grid = render.strip_ansi(u._account_grid([
        ('acct-a', 'a@example.test', win('session', 5, reset_iso), 'ok'),
        ('acct-b', 'b@example.test', win('session', 60), 'ok'),
    ]))
    assert grid.count('session') == 1                           # ONE column
    assert grid.count('\n') == 2                                # header + 2 rows
    assert '   5%' in grid and '  60%' in grid                  # both percentages
    assert grid.count(shown) == 1                               # the truthy-reset leg

    grid = render.strip_ansi(u._account_grid([
        ('a', 'a@example.test', {'limits': [{'kind': 'session', 'percent': 0},
                                            {'kind': 'weekly_all', 'percent': 40}]}, 'ok'),
        ('b', 'b@example.test', {'limits': [{'kind': 'session', 'percent': 0},
                                            {'kind': 'weekly_all', 'percent': 60}]}, 'ok'),
    ]))
    assert 'session' not in grid.split('\n')[0]                 # zero-only column pruned
    assert 'weekly' in grid.split('\n')[0] and '  40%' in grid

    grid = render.strip_ansi(u._account_grid([
        ('a', 'a@example.test', win('session', 0.0), 'ok'),
        ('b', 'b@example.test', win('session', 0.0), 'ok'),
    ]))
    assert 'session' in grid.split('\n')[0]                     # all-zero keeps ONE column
    assert '   0%' in grid

    notes = render.strip_ansi(u._account_grid([
        ('old', 'old@example.test', None, 'expired'),
        ('nc', 'nc@example.test', None, 'no_creds'),
        ('blank', 'blank@example.test', {}, ''),               # no note: silent status
        ('ok', 'ok@example.test', {}, 'ok'),                    # no note: ok, nothing found
    ]))
    assert 'claude login' in notes and 'not logged in' in notes
    assert 'blank@example.test' not in notes and 'ok@example.test' not in notes
    assert '▕' not in notes                                     # no fabricated bars


# ── 4. error paths: extreme percents and broken reset stamps ─────────────────

@pytest.mark.xfail(strict=True, reason="source defect: norm() at claude_sessions/usage.py:320-324 "
                                       "accepts float('nan') — min(nan, 100.0) stays nan and max(0.0, nan) "
                                       "returns 0.0 — so a corrupt 'NaN' percent is published as an OBSERVED "
                                       "0% window instead of returning None like 'abc'/None; the try/except at "
                                       "323-324 exists precisely to drop values that are not numbers, and the "
                                       "windows_snapshot docstring (claude_sessions/usage.py:248-249) forbids "
                                       "reporting the unread as 0% — a hostile NaN answer would read to the V1 "
                                       "router as a perfectly empty window")
def test_nan_inf_and_garbage_percents_cannot_fabricate_a_window():
    """usage.py:320-324 (norm's float()/clamp legs) + 333-335.

    Pins first what the source gets RIGHT: 'inf'/'1e999' clamp DOWN to 100.0 (a
    huge number never reads as more empty than full, and never as a crash),
    '-inf' clamps UP to 0.0, and 'abc'/missing percent return None and drop the
    row (ValueError/TypeError legs at 323-324). Finite negatives were already
    pinned by tests/test_regressions.py::test_usage_clamp_and_zero — those are
    not re-asserted. Then the NaN leg: NaN is not a number, so the function's
    own contract says None (drop), not an observed 0.0. That assertion fails on
    today's source — kept strict-xfail per the card rather than weakening it."""
    w = u._extract_windows({'limits': [
        {'kind': 'session', 'percent': 'inf'},
        {'kind': 'weekly_all', 'percent': '1e999'},
        {'kind': 'other_a', 'percent': '-inf'},
        {'kind': 'other_b', 'percent': 'abc'},
        {'kind': 'other_c'},
    ]})
    assert _wdict(w) == {'session': 100.0, 'weekly': 100.0, 'other_a': 0.0}
    # the NaN leg (expected failure on the current source):
    assert u._extract_windows({'limits': [{'kind': 'session', 'percent': 'NaN'}]}) == []
    assert u._extract_windows({'five_hour': {'utilization': float('nan')}}) == []


def test_missing_or_garbage_reset_stamps_never_promise_a_time():
    """usage.py:267-274 (_fmt_reset: the Z-substitution, the try/except → '?',
    the today vs '%a %H:%M' split) and usage.py:415-416 (the `if resets:`
    arrow leg of _one_account_line).

    Kills: (a) removing the try/except — a corrupt resets_at then raises inside
    the banner render instead of showing '?'; (b) a date comparison inverted or
    dropped — same-day resets must render 'HH:MM', a future day must render the
    weekday form (both legs were NEVER executed with an assertable value: the
    only ISO strings the existing tests fed were 2026-06-* passed into grid
    lines whose assertions check names, not the reset text); (c) the `if
    resets:` leg widening so a None reset still renders '→ ?' — no reset means
    no arrow, not a question mark pretending to be a schedule."""
    for garbage in ('garbage', '', None, 12345, '2026-13-40T99:99:99Z'):
        assert u._fmt_reset(garbage) == '?', garbage

    now = datetime.now()
    assert u._fmt_reset(now.strftime('%Y-%m-%dT%H:%M:%S')) == now.strftime('%H:%M')

    later = now + timedelta(days=3)
    assert re.fullmatch(r'[A-Za-z]{3} \d{2}:\d{2}', u._fmt_reset(later.isoformat()))

    z_dt = datetime.now(timezone.utc) + timedelta(days=2)
    assert u._fmt_reset(z_dt.strftime('%Y-%m-%dT%H:%M:%SZ')) == \
        z_dt.astimezone().strftime('%a %H:%M')

    plain = u._one_account_line([('session', 10.0, None)])
    assert 'session' in plain and '→' not in plain
    assert '→ ?' in u._one_account_line([('session', 10.0, 'garbage')])
