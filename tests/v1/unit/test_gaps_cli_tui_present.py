"""T-332: the ten highest-risk GAPs of archeus/cli/tui/present.py, as tests.

Fail-closed and denial paths first: a policy denial must stay a denial even when
the same row also carries questions; a missing pending_approval row must not
crash the status line nor invent an approval prompt; `offers` must be False for
machines and states it has never heard of, never an exception; an approval with
`eligible: None` must not be shown as blocked; a reset instant that cannot be
read must never be shown as "reset due" while Core still says LIMITED. Then the
boundary values: a naive timestamp read as UTC whatever the machine's zone,
JavaScript's half-up rounding, the "just now" / minute / hour / day boundaries,
0% reported as 0% and not "unknown". Then the error paths: unparsable or
non-string times shown as the em dash, ROUTING counted as running and SKIPPED
as done, non-string resource fields shown as missing, and an unknown presence
state raising instead of guessing a label.

Same style and fixtures as tests/v1/tui/test_parity.py (import the module, call
it directly, plain asserts over recorded strings). No source file is edited and
nothing here touches an OS seam beyond the timezone seam used through
monkeypatch + time.tzset(), which exists only on Unix.
"""

import time

import pytest

from archeus.cli.tui import present as P

# 2026-09-29T12:00:00Z, the same instant the parity fixtures use as `now`.
NOW = 1790683200000


# ── fail-closed and denial paths ─────────────────────────────────────────────


def test_status_line_policy_denial_outranks_questions():
    # present.py:77 says the denial even though questions exist; checking the
    # questions first (present.py:79) would dress a denial up as a question.
    m = {'state': 'PLANNING',
         'planning_blocked': {'kind': 'policy', 'questions': ['Which branch?']}}
    assert P.status_line(m) == 'Blocked: the policy denies this plan'


def test_status_line_approval_required_without_a_pending_row():
    # present.py:69's `and pa` guard: a mission claiming APPROVAL_REQUIRED with
    # no pending_approval row falls through to '' — it must not crash and must
    # not say 'Waiting: approve'.
    assert P.status_line({'state': 'APPROVAL_REQUIRED', 'pending_approval': None}) == ''
    assert P.status_line({'state': 'APPROVAL_REQUIRED'}) == ''


def test_offers_is_false_for_unknown_machine_and_state():
    # present.py:17's `.get(machine, {}).get(state, [])`: without the defaults
    # these calls raise KeyError/AttributeError instead of offering nothing.
    assert P.offers('nope', 'X', 'start') is False
    assert P.offers('mission', 'NOT_A_STATE', 'start') is False


def test_offers_is_false_when_no_trigger_is_named():
    # present.py:18's any(...) over an empty trigger list: asking "does this
    # state have anything" must be False, not True-by-vacuity.
    assert P.offers('mission', 'EXECUTING') is False


def test_explain_state_says_nothing_when_eligible_is_none():
    # present.py:122 checks `is False`: an approval row whose eligible field is
    # simply absent (None) must not gain 'It cannot be decided now', because
    # that would deny the reader an action Core never denied.
    out = P.explain_state({'mission': {'state': 'EXECUTING'},
                           'approval': {'kind': 'plan', 'state': 'PENDING',
                                        'eligible': None, 'eligible_why': 'maybe'}})
    assert out == [{'text': 'A plan approval waits for you.', 'source': 'approval'}]


def test_reset_text_without_a_readable_instant_never_says_due():
    # present.py:194's `then is not None` guard: an unreadable or missing reset
    # must fall to 'resets —', never to 'reset due', which would invite using
    # an account Core still reports LIMITED.
    assert P.reset_text(None, NOW) == 'resets —'
    assert P.reset_text('not a time', NOW) == 'resets —'


def test_reset_text_says_due_at_and_after_the_instant():
    # present.py:194's `then <= now_ms`: the instant itself and any moment
    # after it are 'reset due'; inverting to `<` or `>` would miss the due
    # state (or claim it too early) while Core still reports LIMITED.
    assert P.reset_text('2026-09-29T12:00:00Z', NOW) == 'reset due'
    assert P.reset_text('2026-09-29T11:59:30Z', NOW) == 'reset due'
    # and not yet due: the future side of the same branch.
    assert P.reset_text('2026-09-29T12:30:00Z', NOW) == 'resets in 30 min'


# ── boundary values ──────────────────────────────────────────────────────────


@pytest.mark.skipif(not hasattr(time, 'tzset'),
                    reason='the local-zone seam (time.tzset) exists only on Unix; '
                           'without it the naive-vs-UTC distinction is not observable')
def test_ago_reads_a_naive_timestamp_as_utc(monkeypatch):
    # present.py:172 stamps naive timestamps UTC. Without it, .timestamp()
    # reads them in the machine's zone: under EST5 the same string is 5 h in
    # the future and ago() says 'in 5 h' — a different instant per machine.
    with monkeypatch.context() as m:
        m.setenv('TZ', 'EST5')
        time.tzset()
        try:
            assert P.ago('2026-09-29T12:00:00', NOW) == 'just now'
        finally:
            m.undo()
            time.tzset()


def test_ago_rounds_half_up_like_the_spa():
    # present.py:156 floors x+0.5: 150 s is 2.5 min and must show '3 min ago'.
    # Python's banker's round(2.5) is 2, so a swapped _round shows '2 min ago'.
    assert P.ago('2026-09-29T11:57:30Z', NOW) == '3 min ago'


def test_ago_just_now_boundary_at_forty_five_seconds():
    # present.py:187's `s < 45`: 44 s and the same instant are 'just now',
    # 45 s is already '1 min ago' (present.py:161's max(1, ...) keeps it ≥ 1).
    assert P.ago('2026-09-29T12:00:00Z', NOW) == 'just now'
    assert P.ago('2026-09-29T11:59:16Z', NOW) == 'just now'
    assert P.ago('2026-09-29T11:59:15Z', NOW) == '1 min ago'
    # the future side: present.py:185's `s < 0` — 10 s ahead is still shown,
    # as 'in 1 min', not '0 min' and not 'just now'.
    assert P.ago('2026-09-29T12:00:10Z', NOW) == 'in 1 min'


def test_ago_switches_units_at_the_exact_boundaries():
    # present.py:160/162 compare seconds against 3600/86400 strictly: one
    # second below each boundary still uses the smaller unit (60 min, 24 h),
    # the boundary itself uses the larger. An <= here changes only the last
    # second of each unit's display and goes unnoticed otherwise.
    assert P.ago('2026-09-29T11:00:01Z', NOW) == '60 min ago'   # 3599 s
    assert P.ago('2026-09-29T11:00:00Z', NOW) == '1 h ago'      # 3600 s
    assert P.ago('2026-09-28T12:00:01Z', NOW) == '24 h ago'     # 86399 s
    assert P.ago('2026-09-28T12:00:00Z', NOW) == '1 d ago'      # 86400 s


def test_usage_text_reports_zero_percent_as_zero():
    # present.py:230 checks `pct is None`, not truthiness: a window reported
    # at 0% is real information, and a truthiness test would hide it as
    # 'unknown' — a reading that quietly disappears.
    assert P.usage_text({'windows': {'five_hour': 0}}, NOW) == 'five hour 0%'


def test_usage_text_ignores_a_bool_observed_at():
    # present.py:234's `not isinstance(observed, bool)`: True is an int to
    # isinstance, so without the bool guard the row would claim the reading
    # was observed at epoch + 1 ms — a fabricated observation time.
    assert P.usage_text({'windows': {'five_hour': 10}, 'observed_at': True}, NOW) \
        == 'five hour 10%'


# ── error paths ──────────────────────────────────────────────────────────────


def test_ago_shows_the_em_dash_for_non_string_and_unparsable_times():
    # present.py:170 catches AttributeError as well as ValueError: a number,
    # an empty value and a structurally invalid date all say '—', never a
    # crash and never a guessed time.
    assert P.ago(123, NOW) == '—'
    assert P.ago('', NOW) == '—'
    assert P.ago('2026-13-45T00:00:00Z', NOW) == '—'


def test_status_line_counts_routing_as_running_and_skipped_as_done():
    # present.py:82/84's membership tuples: ROUTING is a running task (the
    # line names it) and SKIPPED counts as done next to SUCCEEDED; dropping
    # either word from the tuple changes the count and the named task.
    m = {'state': 'EXECUTING', 'tasks': [
        {'state': 'SUCCEEDED', 'title': 'a'},
        {'state': 'SKIPPED', 'title': 'b'},
        {'state': 'ROUTING', 'title': 'Route it'}]}
    assert P.status_line(m) == 'Route it · 2 of 3 tasks done'


def test_resource_line_shows_non_string_and_empty_fields_as_missing():
    # present.py:51's `_str` accepts only non-empty strings: a numeric
    # harness_id and an empty account show '—' instead of borrowed or raw
    # values, and an empty effort adds no fourth row at all (present.py:60).
    out = P.resource_line({'harness_id': 42, 'model': 'opus', 'account_id': '',
                           'effort': ''})
    assert out == [{'key': 'harness', 'label': 'Harness', 'value': '—'},
                   {'key': 'model', 'label': 'Model', 'value': 'opus'},
                   {'key': 'account', 'label': 'Account', 'value': '—'}]


def test_presence_label_refuses_an_unknown_state():
    # present.py:45's dict[...] lookup: an unknown presence state raises
    # instead of guessing a label — a transport observation is never invented.
    with pytest.raises(KeyError):
        P.presence_label({'state': 'weird', 'connections': 0})
