"""T-769: the highest-risk uncovered branches of archeus/core/domain/instants.py, as tests.

Fail-closed and denial paths first (a stored NULL where a reset belongs, a provider's
prose, a reset whose UTC form leaves the calendar, a reset that is not ahead of now),
then the boundary values (the millisecond cut, the exact instant of now, the offset
table, the calendar edges), then the error paths (what the parse guard may swallow, and
what the module may never touch: the clock, the local zone, the platform's range).

instants.py is a parser and nothing else, and every "no" it answers is a `None` and
never an exception, because its three callers parse what they are handed without
checking it first: the snapshot builder parses a provider's free text
(resources.py:356), the replay parses a recorded snapshot's own `now`
(resources.py:607, :613), and P11 parses a stored limit (executions.py:1107). A reset
that is not a time must mean "no wait", not a dead Core; and a reset that IS a time must
never be read through the platform (T-106 r2: `timestamp()` is an OSError on Windows
outside 1970-2038) or in the machine's zone (T-106 r4: a naive value is UTC).

Nothing here reads the OS, the clock, the network, the registry or a file: every value is
built in the test, so the file runs unchanged on Linux and on Windows, in any local zone.
Same import and naming style as test_routing_units.py and test_gaps_core_routing_router.py.

Each test names the source branch it kills; removing or inverting that branch fails it.
"""

import ast
import inspect
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from archeus.core.domain import instants

UTC = timezone.utc
NOW = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)             # 10:00:00.000Z, the snapshot's now
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)                   # what test_routing_units.py uses
MIN = datetime(1, 1, 1, tzinfo=UTC)                        # the first instant there is
TZ14 = timezone(timedelta(hours=14))                       # the east edge of the offset table


def zone(hours, minutes=0):
    """An explicit offset, so no row of the table depends on a named zone or on tzdata."""
    return timezone(timedelta(hours=hours, minutes=minutes))


class _ProviderValue:
    """What a feed decoder can hand over: not a str, and yet it prints as an instant."""

    def __str__(self):
        return '2026-09-26T10:00:01Z'


# ── 1. fail-closed: a value that is not a string is no instant, and no crash ──────

@pytest.mark.parametrize('value', [
    pytest.param(None, id='null'),                       # the NULL a stored limit reads back as
    pytest.param(True, id='bool'),
    pytest.param(1234, id='int'),                         # seconds, a provider may hand these over
    pytest.param(1.5, id='float'),
    pytest.param([], id='list'),
    pytest.param({}, id='dict'),                          # {'5h': ...} where a value belongs
    pytest.param((), id='tuple'),
    pytest.param(object(), id='object'),
    pytest.param(_ProviderValue(), id='prints-like-one'),   # not a str, whatever it prints
])
def test_a_value_that_is_not_a_string_is_no_instant_and_never_crashes(value):
    """instants.py:19-20, the `AttributeError` leg of `except (AttributeError, TypeError,
    ValueError): return None`, reached from :18 because `iso.replace` is the first thing
    the value is asked to do.

    Kills: dropping `AttributeError` from the tuple (a reset column that is NULL, or an
    int a provider fed, raises AttributeError inside the snapshot builder and stops Core
    instead of meaning "this account has no reset ahead"), and replacing the guard with
    `str(iso)` — which would read `None` and `1234` as text and answer "not a time" by
    accident while accepting every object with a usable `__str__`."""
    assert instants.instant(value) is None
    assert instants.ahead(value, NOW) is None


@pytest.mark.parametrize('value', [
    pytest.param(b'2026-09-26T10:00:00Z', id='bytes'),     # bytes.replace wants bytes arguments
    pytest.param(datetime(2026, 9, 26, 10, tzinfo=UTC), id='datetime'),   # replace takes keywords
    pytest.param(date(2026, 9, 26), id='date'),
])
def test_bytes_a_datetime_and_a_date_are_no_instant_and_never_crashes(value):
    """instants.py:19-20, the `TypeError` leg of the same guard.

    Kills: narrowing the guard to `except ValueError` — `bytes.replace('Z', '+00:00')`
    and a positional `datetime.replace('Z', '+00:00')` both raise TypeError, so a feed
    decoded as bytes (which is exactly what a raw provider response is) would raise
    through resources.py:356 rather than carry no reset. The two other legs are covered
    by the tests above and below, so this row is what pins the tuple's width."""
    assert instants.instant(value) is None
    assert instants.ahead(value, NOW) is None


# ── 2. fail-closed: text that is not an instant is no instant ─────────────────────

@pytest.mark.parametrize('text', [
    pytest.param('', id='empty'),
    pytest.param('   ', id='blank'),
    pytest.param('now', id='word-now'),
    pytest.param('soon', id='word-soon'),                  # what test_T106r4 leaves at the router
    pytest.param('never', id='word-never'),
    pytest.param('null', id='word-null'),
    pytest.param('None', id='word-none'),
    pytest.param('true', id='word-true'),
    pytest.param('-', id='dash'),
    pytest.param('in 5 hours', id='prose-hours'),
    pytest.param('PT5H', id='duration'),                   # an ISO duration is not an instant
    pytest.param('5h', id='window'),                       # a window name is a key of resets_at
    pytest.param('acc_1', id='account-id'),                # an id never parses as a date
    pytest.param('pdc_x', id='decision-id'),
    pytest.param('msn_x', id='mission-id'),
    pytest.param('2026-09-26T10:00:00z', id='lower-z'),    # only the capital Z is rewritten
    pytest.param(' 2026-09-26T10:00:00Z', id='lead-space'),
    pytest.param('2026-09-26T10:00:00Z ', id='tail-space'),
    pytest.param('Resets in 1h at 2026-09-26T10:00:00Z', id='prose-wrapped'),
    pytest.param('2026-09-26T10:00:00ZZ', id='double-z'),
    pytest.param('2026-09-26T10:00:00+00:00Z', id='offset-and-z'),
    pytest.param('2026-13-01T00:00:00Z', id='month-13'),
    pytest.param('2026-02-30T00:00:00', id='feb-30'),
    pytest.param('2026-09-26T25:00:00Z', id='hour-25'),
    pytest.param('2026-09-26T10:60:00Z', id='minute-60'),
    pytest.param('9999-12-31T23:59:60Z', id='second-60'),
    pytest.param('10000-01-01T00:00:00Z', id='year-10000'),
    pytest.param('0000-01-01T00:00:00Z', id='year-0'),
])
def test_text_that_is_not_an_instant_is_no_instant_and_no_wait(text):
    """instants.py:19-20, the `ValueError` leg, and the parse attempt at :18 that decides
    what counts as an instant at all.

    Kills the four ways of widening it that all read a wait out of junk and then block
    the router on it: `re.search`/`fromisoformat(text[-25:])` (which would find the
    instant inside `prose-wrapped` and honour a provider's sentence), `.strip()` and
    `.upper()`/`.casefold()` (which would accept `lead-space`, `tail-space` and
    `lower-z`), and a lenient parser (`dateutil`, `fromisoformat(fuzzy)`) which would
    take `prose-hours`, `duration` and `minute-60`. An id is rejected because nothing
    here extracts a date from a value: the text is parsed as written or not at all."""
    assert instants.instant(text) is None
    assert instants.ahead(text, NOW) is None


def test_ahead_of_a_value_that_is_not_a_time_is_no_wait_and_not_an_error():
    """instants.py:43-44, the `if at is None: return None` of `ahead`.

    Kills: deleting the guard, which hands `None` to `_ms` at :45 (`None.replace` is an
    AttributeError) — the snapshot builder's `{w: instants.ahead(v, now_dt) for w, v in
    resets.items()}` (resources.py:356) iterates a provider's own mapping, so one junk
    window would raise in the middle of building a snapshot. The `is None` form matters
    too: `if not at` would answer no-wait for no datetime at all, since a datetime is
    always truthy, so the inversion is only visible through the values that ARE times."""
    assert instants.ahead('soon', NOW) is None
    assert instants.ahead(None, NOW) is None
    assert instants.ahead(1758873600, NOW) is None
    # and a value that IS a time still comes through the other side of the guard
    assert instants.ahead('2026-09-26T10:00:00.001Z', NOW) == {
        'at': '2026-09-26T10:00:00.001Z', 'key': '2026-09-26T10:00:00.001Z'}


# ── 3. denial: a reset whose UTC form leaves the calendar is no wait ──────────────

@pytest.mark.parametrize('text', [
    pytest.param('9999-12-31T23:59:59.999-12:00', id='west-12'),    # UTC would be 10000-01-01
    pytest.param('9999-12-31T23:59:59.999999-14:00', id='west-14'),  # the furthest west there is
])
def test_a_reset_whose_utc_form_leaves_the_calendar_is_no_wait(text):
    """instants.py:32-35, the `except (OverflowError, ValueError): return None` of
    `_written`, reached at :46 because the instant itself IS after `now`.

    Kills: deleting the try (a provider's year-9999 reset with a west offset raises
    OverflowError out of `at.astimezone(timezone.utc)` and stops the builder — this is
    the whole reason T-106 r2 forbids the platform path: the value is legal, only its
    UTC form is not), and turning the answer into `{}` or `{'at': None, 'key': None}`,
    which the router reads as a reset it can sort (`resets_at` is a dict either way)."""
    assert instants.ahead(text, NOW) is None


def test_the_written_guard_holds_at_the_min_edge_of_the_calendar_too():
    """instants.py:32-35 at the other edge: 0001-01-01 with an east offset is a legal
    instant whose UTC form (year 0) is not, and `_written` must answer None.

    Kills: an `except OverflowError` narrowed to the max side only, or a guard that
    tests `at.year == 9999` instead of letting the conversion answer. The public path
    cannot reach this row — an instant below `datetime.min` in UTC is necessarily
    `<= now` at :46, since every `now` is a valid datetime — so the guard is tested
    where it lives, as the last line of defence for a caller that judges at its own now.
    """
    assert instants._written(datetime(1, 1, 1, 0, 0, tzinfo=TZ14)) is None


# ── 4. denial: a reset that is not ahead of now is no wait, to the millisecond ────

def test_a_reset_exactly_at_now_is_no_wait_and_one_millisecond_after_is():
    """instants.py:46, the `at <= now` of `None if at <= now else _written(at)`.

    Kills: `<=` -> `<`, which writes a wait for an instant that has already arrived (a
    decision that promises the user it may run again at `now`, and one extra pass), and
    `<=` -> `>=` / `>` which turns every past reset into a future one and blocks the
    router on a reset that has long gone. `now` is 10:00:00.000Z and the cut of :26 is a
    whole millisecond, so the rows below are the exact boundary and its neighbours, not
    approximations of it."""
    assert instants.ahead('2026-09-26T10:00:00.000Z', NOW) is None
    assert instants.ahead('2026-09-26T09:59:59.999Z', NOW) is None
    assert instants.ahead('2026-09-26T10:00:00.001Z', NOW) == {
        'at': '2026-09-26T10:00:00.001Z', 'key': '2026-09-26T10:00:00.001Z'}
    # the same boundary reached as another zone's wall clock: 12:00+02:00 IS 10:00Z
    assert instants.ahead('2026-09-26T12:00:00+02:00', NOW) is None
    assert instants.ahead('2026-09-26T12:00:00.001+02:00', NOW) == {
        'at': '2026-09-26T12:00:00.001+02:00', 'key': '2026-09-26T10:00:00.001Z'}


def test_a_reset_is_judged_at_the_instant_it_is_written_at():
    """instants.py:45 and :46 together: the check reads `_ms(at)` and the text comes from
    the same `_ms(at)` — one instant, twice used (T-106 r5). `now` carries microseconds
    here, which no existing test does.

    Kills: comparing the untruncated instant while writing the truncated one (the
    `.000999` row would become a wait 0.499 ms long and the written `.000` would name an
    instant that is not the one that was checked), and truncating nothing at all (same
    row flips: `.000999` is after `now`, `.000` is not)."""
    with_us = datetime(2026, 9, 26, 10, 0, 0, 500, tzinfo=UTC)        # now 10:00:00.000500Z
    assert instants.ahead('2026-09-26T10:00:00.000999Z', with_us) is None
    assert instants.ahead('2026-09-26T10:00:00.001999Z', with_us) == {
        'at': '2026-09-26T10:00:00.001Z', 'key': '2026-09-26T10:00:00.001Z'}


# ── 5. boundary: the millisecond cut floors, it never rounds ─────────────────────

@pytest.mark.parametrize('text, millis', [
    pytest.param('2026-09-26T10:00:01.000000Z', '000', id='exact'),
    pytest.param('2026-09-26T10:00:01.000999Z', '000', id='under-1ms'),   # .999 of a ms goes away
    pytest.param('2026-09-26T10:00:01.500999Z', '500', id='half'),        # round() would say 501
    pytest.param('2026-09-26T10:00:01.999999Z', '999', id='almost-a-second'),  # round: 02.000
])
def test_microseconds_are_cut_to_milliseconds_never_rounded(text, millis):
    """instants.py:26, `at.replace(microsecond=at.microsecond // 1000 * 1000)` — the
    integer division that CUTS.

    Kills: `round(at.microsecond / 1000) * 1000` (a wait promised a millisecond later
    than the provider's reset, and the `.000999` row flips from no-wait to a wait), and
    dropping `_ms` at :45 entirely (the `.000999` row below is the one that notices:
    untruncated it is after `now`). The written form is checked as well, because the
    router sorts on `key` and a rounded key is a different instant than the decision."""
    assert instants.ahead('2026-09-26T10:00:00.000999Z', NOW) is None       # floor, not 001
    assert instants.ahead(text, NOW) == {
        'at': '2026-09-26T10:00:01.%sZ' % millis, 'key': '2026-09-26T10:00:01.%sZ' % millis}


# ── 6. boundary: `at` as written, `key` in UTC, one instant between them ──────────

@pytest.mark.parametrize('text, at, key', [
    pytest.param('2026-09-26T10:00:01Z', '2026-09-26T10:00:01.000Z', '2026-09-26T10:00:01.000Z',
                 id='zulu'),
    pytest.param('2026-09-26T10:00:01+00:00', '2026-09-26T10:00:01.000Z',
                 '2026-09-26T10:00:01.000Z', id='explicit-utc'),
    pytest.param('2026-09-26T12:00:01.001+02:00', '2026-09-26T12:00:01.001+02:00',
                 '2026-09-26T10:00:01.001Z', id='east-2'),
    pytest.param('2026-09-26T21:00:01-11:00', '2026-09-26T21:00:01.000-11:00',
                 '2026-09-27T08:00:01.000Z', id='west-11-day'),
    pytest.param('2026-09-26T23:45:01.001+13:45', '2026-09-26T23:45:01.001+13:45',
                 '2026-09-26T10:00:01.001Z', id='east-1345'),
    pytest.param('2026-09-26T15:30:01.001+05:30', '2026-09-26T15:30:01.001+05:30',
                 '2026-09-26T10:00:01.001Z', id='east-530'),
])
def test_at_is_the_reset_as_written_and_key_the_same_instant_in_utc(text, at, key):
    """instants.py:36, both legs of `{'at': at.isoformat(...).replace('+00:00', 'Z'),
    'key': at.astimezone(timezone.utc).isoformat(...).replace('+00:00', 'Z')}`.

    Kills: writing `at` in UTC (the decision replays as text that is not what the
    provider said — 533e3e9, and `test_T106r8_the_router_orders_readings_by_instant_not_
    by_text` only holds because `at` is free text and `key` is the sort field), writing
    `key` with the offset (readings in different zones then sort by wall clock), and
    dropping either `.replace('+00:00', 'Z')`: the two `zulu`/`explicit-utc` rows pin
    the Z form, and the offset rows pin that only a UTC offset becomes Z — an offset
    that merely ENDS in digits (`+05:30`) must survive untouched."""
    w = instants.ahead(text, NOW)
    assert w == {'at': at, 'key': key}
    assert set(w) == {'at', 'key'}                                # nothing extra to replay
    assert instants.instant(w['at']) == instants.instant(w['key'])    # one instant, two texts
    assert json.dumps(w, sort_keys=True).isascii()                   # it goes into a record


# ── 7. boundary: the Z the guard rewrites, and the calendar edges ────────────────

def test_capital_z_is_utc_lowercase_z_is_not_a_time():
    """instants.py:18, `iso.replace('Z', '+00:00')` — the rewrite that makes a Zulu reset
    readable at all, and the reason the answer is the same as the explicit-offset form.

    Kills: deleting the replace (a provider's `...Z` reset raises ValueError, is answered
    None, and the router blocks with no `unblock_at` while a real reset is sitting in the
    text), and "fixing" that with `.upper()` or a case-insensitive replace, which would
    also accept the lowercase `z` no ISO 8601 producer writes and every `Z` that happens
    to sit in prose."""
    assert instants.instant('2026-09-26T10:00:01Z') == datetime(2026, 9, 26, 10, 0, 1, tzinfo=UTC)
    assert instants.ahead('2026-09-26T10:00:01Z', NOW) == instants.ahead(
        '2026-09-26T10:00:01+00:00', NOW)
    assert instants.ahead('2026-09-26T10:00:01z', NOW) is None


def test_a_zulu_reset_is_rewritten_before_the_parser_ever_sees_it(monkeypatch):
    """instants.py:18, `iso.replace('Z', '+00:00')` read as the guard it is: no Z may
    reach the parser at all.

    Kills: deleting the replace. Python 3.11 and later read a trailing Z by themselves,
    so on this interpreter the deletion is invisible from outside and the test above
    still passes; the package supports Python 3.10 (`requires-python`), where only the
    rewrite makes a Zulu reset readable — without it every `...Z` reset a provider hands
    over becomes no wait and the router blocks a user with no `unblock_at`. The parser is
    faked here and nowhere else: this is the one seam in the file, and it is a function,
    not an OS call, a clock or a zone."""
    real = datetime.fromisoformat

    def fromisoformat_without_z(text):
        if text[-1:] in ('Z', 'z'):                       # what the 3.10 floor does
            raise ValueError('%r holds a Z this interpreter cannot read' % text)
        return real(text)

    fake = type('DateTime310', (), {'fromisoformat': staticmethod(fromisoformat_without_z)})
    monkeypatch.setattr(instants, 'datetime', fake)
    assert instants.instant('2026-09-26T10:00:01Z') == datetime(2026, 9, 26, 10, 0, 1, tzinfo=UTC)
    assert instants.ahead('2026-09-26T10:00:01Z', NOW) == {
        'at': '2026-09-26T10:00:01.000Z', 'key': '2026-09-26T10:00:01.000Z'}
    assert instants.ahead('2026-09-26T10:00:01z', NOW) is None      # faked, not cleaned


def test_the_calendar_edges_are_read_without_the_platform():
    """instants.py:18, :21 and :36 at the two ends of the proleptic calendar, which is
    where a platform call would hurt (T-106 r2): `datetime(1960).timestamp()` and
    `datetime(9999).timestamp()` raise OSError on Windows.

    Kills: any route through `timestamp()`/`mktime`/the CRT (a 1960 reset would then
    raise instead of being no wait, and a year-9999 one would raise instead of being
    written), and a `fromtimestamp` that reads the clock while parsing."""
    assert instants.ahead('1960-01-01T00:00:00', NOW) is None                 # before the epoch
    assert instants.ahead('1960-01-01T00:00:00', EPOCH) is None           # judged at the epoch
    assert instants.ahead('1970-01-01T00:00:00.001', EPOCH) == {
        'at': '1970-01-01T00:00:00.001Z', 'key': '1970-01-01T00:00:00.001Z'}    # 1 ms after it
    assert instants.instant('1960-01-01T00:00:00') == datetime(1960, 1, 1, tzinfo=UTC)
    assert instants.ahead('0001-01-01T00:00:01', MIN) == {
        'at': '0001-01-01T00:00:01.000Z', 'key': '0001-01-01T00:00:01.000Z'}
    assert instants.ahead('9999-12-31T23:59:59.999999', NOW) == {
        'at': '9999-12-31T23:59:59.999Z', 'key': '9999-12-31T23:59:59.999Z'}


def test_a_naive_reset_is_utc_itself_and_not_the_machines_zone():
    """instants.py:21, the `else at.replace(tzinfo=timezone.utc)` leg: a naive value is
    labelled UTC, it is never converted from anywhere (T-106 r4).

    Kills: `at.astimezone()` (no zone -> the LOCAL zone, the bug r4 was written for: a
    provider's `2026-09-26T10:02:00` would then be 08:02Z on a UTC+2 machine and the
    router would wait two hours too long), and `at.replace(tzinfo=None)`, which leaves
    the comparison at :46 to raise on an aware `now`. The last two assertions make the
    same judgement through a `now` that is NOT UTC, so their answer cannot come from the
    wall clock of the machine running the test."""
    naive = instants.instant('2026-09-26T10:00:01')
    assert naive.tzinfo is UTC and naive.utcoffset() == timedelta(0)
    assert instants.instant('2026-09-26T10:00:01Z').utcoffset() == timedelta(0)
    assert instants.ahead('2026-09-26T10:00:01Z', datetime(2026, 9, 26, 12, 0, 1, tzinfo=zone(2))) \
        is None
    assert instants.ahead('2026-09-26T10:00:01Z', datetime(2026, 9, 26, 11, 59, 0,
                                                           tzinfo=zone(1, 59))) == {
        'at': '2026-09-26T10:00:01.000Z', 'key': '2026-09-26T10:00:01.000Z'}


# ── 8. error path: what the module may not do at all ──────────────────────────────

FORBIDDEN_CALLS = {'timestamp', 'localtime', 'gmtime', 'mktime', 'tzset', 'utcnow',
                   'now', 'today', 'fromtimestamp', 'strptime', 'tzname',
                   'upper', 'lower', 'casefold', 'strip', 'lstrip', 'rstrip'}


def test_the_module_touches_no_clock_no_zone_and_no_lenient_text():
    """instants.py:18 and :33 by structure rather than by value: the module imports
    `datetime` only, never names a clock or zone call, never converts to the local zone
    with an argument-less `astimezone()`, and never widens the text it parses with a
    `strip()`/`upper()`; and no handler swallows everything.

    Kills: the two regressions this module exists to prevent (`timestamp()` -> OSError on
    Windows outside 1970-2038, a local-zone read -> a wait in the wrong hours), plus the
    two accident paths: `except Exception: return None` (a real bug in the parser then
    answers "no wait" quietly, and the router blocks with no reason) and a text-cleaning
    `strip()` that turns junk into a wait."""
    tree = ast.parse(inspect.getsource(instants))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported == {'datetime'}                       # no time, os, locale, dateutil
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
                assert not (node.func.attr == 'astimezone' and not node.args), \
                    'astimezone() with no zone reads the local zone (T-106 r4)'
    assert not called & FORBIDDEN_CALLS, sorted(called & FORBIDDEN_CALLS)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            assert node.type is not None, 'a bare except swallows every bug'
            names = {n.id for n in ([node.type] if isinstance(node.type, ast.Name)
                                    else node.type.elts)}
            assert 'Exception' not in names and 'BaseException' not in names


@pytest.mark.xfail(strict=True, raises=TypeError,
                   reason='instants.py:46 compares with `now` unguarded: ahead(text, None) '
                          'raises TypeError instead of answering no wait, and resources.py:613 '
                          'hands it exactly that None when a recorded snapshot has no readable '
                          '`now`')
def test_ahead_judged_at_no_instant_at_all_is_no_wait():
    """instants.py:46, the `now` side of `None if at <= now else _written(at)`.

    Every other unreadable input to this module is answered with no wait — that is its
    contract, and the reason Core survives a provider's junk. `now` is the one argument
    that is compared without a guard, and `resources._written_resets` computes it as
    `instants.instant(snap['now'])` (:607), which is None for a decision record whose
    snapshot lost its `now`: replaying that one record raises TypeError (:613) instead
    of replaying it with no waits. Kills: the missing guard; the fix belongs at :46
    (`if now is None: return None`, next to the guard at :43) and this test is then no
    longer an xfail."""
    assert instants.ahead('2026-09-26T12:00:00.001+02:00', None) is None
