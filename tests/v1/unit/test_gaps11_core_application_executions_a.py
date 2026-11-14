"""T-1412: the uncovered branches of `archeus/core/application/executions.py` lines
1101-1174 inclusive (`limit_until`, `limit_passed`, `account_limited`, `accounts_tick`)
at tip 6a32dc14 (re-located at 81d83030). No source file is edited.

Ten selected branches, denial and fail-closed first, then boundaries, then error paths:

1. 1106-1108 limit_until: a reset that is not a time, or already past, holds now + LIMIT_DEFAULT_S.
   Catches: the past check dropped, or the past value stored.
2. 1120-1122 limit_passed: a non-string, a malformed string or an unrepresentable time counts as passed.
   Catches: the except clause returning False.
3. 1120 limit_passed: a 'Z' value and a '+00:00' value agree; a value with no offset is read as local time.
   Catches: the 'Z' replacement dropped, or naive values read as UTC.
4. 1107 limit_until: reset exactly equal to now is past and gets the default window.
   Catches: `<=` changed to `<`.
5. 1109 limit_until: a future reset is written in milliseconds with a Z suffix and round-trips.
   Catches: the timespec or the Z replacement dropped.
6. 1130-1133 account_limited: only AVAILABLE or CONSTRAINED fire 'window_exhausted'.
   Catches: the health tuple widened to LIMITED, DEGRADED or OPEN.
7. 1144-1149 accounts_tick: a LIMITED account past its reset moves to AVAILABLE and is not evaluated by the breaker.
   Catches: the `continue` removed, or the reset field not cleared.
8. 1156-1171 accounts_tick breaker: exactly STORM resource/auth errors inside STORM_WINDOW_S move
   AVAILABLE to DEGRADED; one fewer does not; policy failures, missing ended_at and ENDED_OK never count.
   Catches: `>=` changed to `>`, the failure filter, the ended_at filter, the window edge.
9. 1160-1163 accounts_tick: DEGRADED moves to OPEN only with `beat` and PERSIST errors after `since`;
   to AVAILABLE on probe_ok only with `beat` and a success after `since`.
   Catches: the beat check dropped, or the `since` comparison inverted.
10. 1164-1165 accounts_tick: OPEN returns to DEGRADED only after COOLDOWN_S from `since`.
    Catches: the cooldown comparison, or the trigger for OPEN.

Closest existing tests: tests/v1/unit/test_gaps_core_application_executions.py and
tests/v1/unit/test_gaps7_core_application_executions.py (neither names these functions).
Fakes only: a fake tx with `where(cls)`, `lifecycle.fire` recorded, `now` passed explicitly.
No database, no real clock, no user home.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from archeus.core.application import executions as X
from archeus.core.application import lifecycle
from archeus.core.domain import entities

NOW = 1_800_000_000.0


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _ts(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()


class Tx:
    def __init__(self, accounts=(), executions=()):
        self.accounts = [SimpleNamespace(entity=a, updated_at=_iso(since)) for a, since in accounts]
        self.executions = [SimpleNamespace(entity=e) for e in executions]

    def where(self, cls):
        if cls is entities.Account:
            return list(self.accounts)
        if cls is entities.Execution:
            return list(self.executions)
        raise AssertionError(cls)


def _account(health, limited_until=None, id='acc_1'):
    return SimpleNamespace(id=id, health=health, limited_until=limited_until)


_RECENT = object()


def _execution(account_id='acc_1', state='ENDED_ERROR', failure='resource', ended_at=_RECENT):
    return SimpleNamespace(account_id=account_id, state=state, failure=failure,
                           ended_at=_iso(NOW - 1) if ended_at is _RECENT else ended_at)


@pytest.fixture
def fired(monkeypatch):
    calls = []

    def fire(tx, cls, id_, trigger, *, actor, reason, fields=None):
        calls.append((cls, id_, trigger, fields))

    monkeypatch.setattr(lifecycle, 'fire', fire)
    return calls


# 1. 1106-1108: a non-time or past reset holds the default window
@pytest.mark.parametrize('resets_at', [None, 'not a time', '2000-01-01T00:00:00Z'])
def test_limit_until_defaults_when_reset_is_not_a_future_time(resets_at):
    until = X.limit_until(resets_at, NOW)
    assert _ts(until) == NOW + X.LIMIT_DEFAULT_S
    assert X.limit_passed(until, NOW) is False


# 2. 1120-1122: an unreadable stored value counts as passed
@pytest.mark.parametrize('stored', [None, 5, 'soon', '0001-01-01T00:00:00'])
def test_limit_passed_treats_an_unreadable_value_as_passed(stored):
    assert X.limit_passed(stored, NOW) is True


# 3. 1120: 'Z' and '+00:00' agree; a value with no offset is local time
def test_limit_passed_reads_z_and_zero_offset_alike_and_naive_as_local():
    assert X.limit_passed('2027-01-15T08:00:00Z', NOW) is True
    assert X.limit_passed('2027-01-15T08:00:00+00:00', NOW) is True
    assert X.limit_passed('2027-01-15T08:00:01+00:00', NOW) is False
    local = datetime(2027, 1, 15, 8, 0, 0)
    stamp = local.timestamp()
    assert X.limit_passed(local.isoformat(), stamp) is True
    assert X.limit_passed(local.isoformat(), stamp - 1) is False


# 4. 1107: a reset exactly at now is past
def test_limit_until_reset_equal_to_now_gets_the_default_window():
    until = X.limit_until(_iso(NOW), NOW)
    assert _ts(until) == NOW + X.LIMIT_DEFAULT_S


# 5. 1109: a future reset keeps milliseconds, writes Z and round-trips
def test_limit_until_writes_future_reset_in_milliseconds_with_z():
    until = X.limit_until('2099-01-01T00:00:00.123456Z', NOW)
    assert until == '2099-01-01T00:00:00.123Z'
    assert X.limit_passed(until, _ts(until) - 0.5) is False
    assert X.limit_passed(until, _ts(until)) is True


def test_limit_until_keeps_a_non_utc_offset_as_written():
    until = X.limit_until('2099-01-01T02:00:00.500+02:00', NOW)
    assert until == '2099-01-01T02:00:00.500+02:00'
    assert X.limit_passed(until, _ts(until) - 0.5) is False
    assert X.limit_passed(until, _ts(until)) is True


# 6. 1130-1133: only AVAILABLE or CONSTRAINED fire the window
@pytest.mark.parametrize('health', ['AVAILABLE', 'CONSTRAINED'])
def test_account_limited_fires_window_exhausted_from_available_or_constrained(
        monkeypatch, fired, health):
    monkeypatch.setattr(lifecycle, 'load', lambda tx, cls, id_: SimpleNamespace(
        entity=_account(health)))
    out = X.account_limited(Tx(), actor='a', account_id='acc_1', resets_at=_iso(NOW + 60),
                            now=NOW)
    assert out == {'account_id': 'acc_1', 'limited_until': out['limited_until']}
    assert _ts(out['limited_until']) == NOW + 60
    assert fired == [(entities.Account, 'acc_1', 'window_exhausted',
                      {'limited_until': out['limited_until']})]


@pytest.mark.parametrize('health', ['LIMITED', 'DEGRADED', 'OPEN'])
def test_account_limited_leaves_other_health_states_without_a_trigger(
        monkeypatch, fired, health):
    monkeypatch.setattr(lifecycle, 'load', lambda tx, cls, id_: SimpleNamespace(
        entity=_account(health)))
    out = X.account_limited(Tx(), actor='a', account_id='acc_1', resets_at=_iso(NOW + 60),
                            now=NOW)
    assert _ts(out['limited_until']) == NOW + 60
    assert fired == []


# 7. 1144-1149: a passed reset moves to AVAILABLE and skips the breaker for that account
def test_accounts_tick_moves_a_passed_limit_to_available_without_breaker_review(fired):
    stale = [_execution(state='ENDED_ERROR', failure='resource') for _ in range(X.STORM)]
    tx = Tx(accounts=[(_account('LIMITED', _iso(NOW - 1)), NOW - 10_000)], executions=stale)
    out = X.accounts_tick(tx, actor='a', now=NOW)
    assert out == {'moved': [('acc_1', 'AVAILABLE')]}
    assert fired == [(entities.Account, 'acc_1', 'reset_time_passed', {'limited_until': None})]


def test_accounts_tick_keeps_a_limit_that_has_not_reset(fired):
    tx = Tx(accounts=[(_account('LIMITED', _iso(NOW + 1)), NOW - 10_000)])
    assert X.accounts_tick(tx, actor='a', now=NOW) == {'moved': []}
    assert fired == []


# 8. 1156-1171: the storm trips at exactly STORM recent resource/auth errors
def _storm_tx(errors):
    return Tx(accounts=[(_account('AVAILABLE'), NOW - 10_000)], executions=errors)


def test_accounts_tick_trips_the_breaker_at_exactly_storm_errors(fired):
    errs = [_execution(ended_at=_iso(NOW - 1 - i)) for i in range(X.STORM)]
    assert X.accounts_tick(_storm_tx(errs), actor='a', now=NOW) == {
        'moved': [('acc_1', 'DEGRADED')]}
    assert fired[0][2] == 'error_storm'


def test_accounts_tick_does_not_trip_one_error_short_of_storm(fired):
    errs = [_execution(ended_at=_iso(NOW - 1 - i)) for i in range(X.STORM - 1)]
    assert X.accounts_tick(_storm_tx(errs), actor='a', now=NOW) == {'moved': []}
    assert fired == []


def test_accounts_tick_counts_neither_policy_failures_nor_unended_or_ok_rows(fired):
    errs = [_execution(ended_at=_iso(NOW - 1 - i)) for i in range(X.STORM - 1)]
    errs += [_execution(failure='policy', ended_at=_iso(NOW - 2)),
             _execution(ended_at=None),
             _execution(state='ENDED_OK', failure=None, ended_at=_iso(NOW - 3))]
    assert X.accounts_tick(_storm_tx(errs), actor='a', now=NOW) == {'moved': []}
    assert fired == []


def test_accounts_tick_does_not_count_an_error_at_the_window_edge(fired):
    edge = _iso(NOW - X.STORM_WINDOW_S)
    errs = [_execution(ended_at=_iso(NOW - 1 - i)) for i in range(X.STORM - 1)]
    errs.append(_execution(ended_at=edge))
    assert X.accounts_tick(_storm_tx(errs), actor='a', now=NOW) == {'moved': []}


# 9. 1160-1163: DEGRADED to OPEN and to AVAILABLE need the beat and a row after since
def _degraded_tx(*, since, errors=(), oks=()):
    return Tx(accounts=[(_account('DEGRADED'), since)], executions=list(errors) + list(oks))


def test_degraded_opens_on_persistent_errors_after_the_beat(fired):
    errs = [_execution(ended_at=_iso(NOW - 5)) for _ in range(X.PERSIST)]
    out = X.accounts_tick(_degraded_tx(since=NOW - X.BEAT_S, errors=errs), actor='a', now=NOW)
    assert out == {'moved': [('acc_1', 'OPEN')]}
    assert fired[0][2] == 'errors_persist'


def test_degraded_stays_with_one_persistent_error_too_few(fired):
    errs = [_execution(ended_at=_iso(NOW - 5)) for _ in range(X.PERSIST - 1)]
    out = X.accounts_tick(_degraded_tx(since=NOW - X.BEAT_S, errors=errs), actor='a', now=NOW)
    assert out == {'moved': []}


def test_degraded_does_not_open_before_the_beat(fired):
    errs = [_execution(ended_at=_iso(NOW - 5)) for _ in range(X.PERSIST)]
    out = X.accounts_tick(_degraded_tx(since=NOW - X.BEAT_S + 1, errors=errs), actor='a',
                          now=NOW)
    assert out == {'moved': []}


def test_degraded_returns_to_available_on_a_probe_success_after_the_beat(fired):
    oks = [_execution(state='ENDED_OK', failure=None, ended_at=_iso(NOW - 5))]
    out = X.accounts_tick(_degraded_tx(since=NOW - X.BEAT_S, oks=oks), actor='a', now=NOW)
    assert out == {'moved': [('acc_1', 'AVAILABLE')]}
    assert fired[0][2] == 'probe_ok'


def test_degraded_ignores_a_success_from_before_since(fired):
    oks = [_execution(state='ENDED_OK', failure=None, ended_at=_iso(NOW - X.BEAT_S - 5))]
    out = X.accounts_tick(_degraded_tx(since=NOW - X.BEAT_S, oks=oks), actor='a', now=NOW)
    assert out == {'moved': []}


def test_degraded_does_not_recover_before_the_beat(fired):
    oks = [_execution(state='ENDED_OK', failure=None, ended_at=_iso(NOW - 5))]
    out = X.accounts_tick(_degraded_tx(since=NOW - X.BEAT_S + 1, oks=oks), actor='a', now=NOW)
    assert out == {'moved': []}


# 10. 1164-1165: OPEN returns to DEGRADED only after COOLDOWN_S
def test_open_moves_to_degraded_once_the_cooldown_has_elapsed(fired):
    tx = Tx(accounts=[(_account('OPEN'), NOW - X.COOLDOWN_S)])
    assert X.accounts_tick(tx, actor='a', now=NOW) == {'moved': [('acc_1', 'DEGRADED')]}
    assert fired[0][2] == 'cooldown_elapsed'


def test_open_stays_open_one_second_before_the_cooldown_ends(fired):
    tx = Tx(accounts=[(_account('OPEN'), NOW - X.COOLDOWN_S + 1)])
    assert X.accounts_tick(tx, actor='a', now=NOW) == {'moved': []}
    assert fired == []
