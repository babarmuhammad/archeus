"""T-741: the highest-risk uncovered branches of archeus/core/domain/ids.py.

The value rules and denial paths of the id namespace: the `encode` range guard,
every shape `is_ulid` must refuse (length, the Crockford exclusions, the 48-bit
first character, a value that is not a string at all), the `ulid_ms` refusal, the
monotonic mint (same millisecond, a stepped-back clock, a random-part carry) and
the pin path that must not disturb it, and the two name-spaces `token_kind` /
`kind_of` keep apart — including the reserved `ws_global`.

Pure functions plus one clock seam and one randomness seam: `ids.time` and
`ids.secrets` are replaced on the module the code looks them up on, so nothing
here reads the real clock, the real RNG, the environment or the OS, and nothing
is Windows-specific. Style and fixtures follow tests/v1/unit/test_domain.py (the
ids section) and tests/v1/unit/test_gaps_core_domain_guards.py; only the gaps
those files leave are re-opened here. No source file is edited.
"""

import math
import threading

import pytest

from archeus.core.domain import ids

# A whole second in milliseconds: `int(clock() * 1000)` round-trips exactly for
# it on every platform, so a faked clock cannot drift by a millisecond between
# the test and the code under test.
BASE_MS = 1_700_000_000_000
# One pinned id every test below can rebuild byte for byte.
ULID = ids.encode(BASE_MS, 123456789012345678901234)


def _tick(ms):
    """A float that `int(time.time() * 1000)` (ids.py:76) reads back as exactly
    `ms`: the millisecond -> second -> millisecond round trip is not exact for
    every value and the direction of the error is not something to assume across
    platforms, so it is verified here and nudged by an ULP until it holds."""
    f = ms / 1000.0
    for _ in range(64):
        got = int(f * 1000)
        if got == ms:
            return f
        f = math.nextafter(f, math.inf) if got < ms else math.nextafter(f, -math.inf)
    raise AssertionError('no float clock reads back as %d ms' % ms)


class _Clock:
    """The seam for `ids.time`: one fixed millisecond, and a read counter."""

    def __init__(self, ms=BASE_MS):
        self.ms = ms
        self.reads = 0
        self._tick = _tick(ms)

    def time(self):
        self.reads += 1
        return self._tick


class _Draws:
    """The seam for `ids.secrets`: queued widths->values; an unasked-for draw is
    an AssertionError, so a branch that must not spend randomness says so."""

    def __init__(self, *widths):
        self.widths = list(widths)
        self.asked = []

    def randbits(self, bits):
        self.asked.append(bits)
        if not self.widths:
            raise AssertionError('unexpected secrets.randbits(%d)' % bits)
        want = self.widths.pop(0)
        assert want == bits, 'asked for %d bits, this branch draws %d' % (want, bits)
        return 0


class _Never:
    """Both seams at once: reading either one is the failure."""

    def time(self):
        raise AssertionError('the clock must not be read for a pinned ULID')

    def randbits(self, bits):
        raise AssertionError('randomness must not be spent for a pinned ULID')


def _crockford(n):
    """Reference encoder, written independently of ids.py: the 128-bit value as
    26 groups of 5 bits, left-padded (26 * 5 = 130), Crockford-indexed."""
    assert n < (1 << 128)
    bits = format(n, '0130b')
    return ''.join(ids.ALPHABET[int(bits[i:i + 5], 2)] for i in range(0, 130, 5))


def _crockford_value(text):
    """Reference decoder: the integer a 26-character ULID carries."""
    n = 0
    for c in text:
        n = n * 32 + ids.ALPHABET.index(c)
    return n


def hook_token():
    """A credential of the execution kind: `hook_` + the shape of a real ULID,
    which is what a token looks like when it is delivered as
    ARCHEUS_HOOK_TOKEN. Opaque to Core, so any tail is legal for it."""
    return '%s_%s' % (ids.TOKEN_PREFIXES['execution'], ULID)


def _fake(monkeypatch, clock=None, draws=None):
    monkeypatch.setattr(ids, 'time', clock or _Clock())
    monkeypatch.setattr(ids, 'secrets', draws or _Never())


# ── the alphabet and the two prefix tables (ids.py:17, 25-41, 49-53) ─────────

def test_the_alphabet_is_the_32_crockford_symbols_and_no_ambiguity():
    """ids.py:17 — `ALPHABET[(n >> 5*i) & 31]` is only a bijection while the
    table has 32 distinct symbols; a duplicate would make `ulid_ms` (ids.py:100,
    `ALPHABET.index(c)`) decode to the wrong half, and an added I/L/O/U would
    make two visually different ids read the same in a transcript."""
    assert len(ids.ALPHABET) == 32 and len(set(ids.ALPHABET)) == 32
    assert not set(ids.ALPHABET) & set('ILOUilou'), 'a Crockford-excluded letter is back'
    assert ids.ALPHABET == ids.ALPHABET.upper(), 'the alphabet is not uppercase-only'
    assert [ids.ALPHABET.index(c) for c in ids.ALPHABET] == list(range(32))


def test_id_prefixes_are_lowercase_heads_that_no_token_can_share():
    """ids.py:41 and ids.py:52-53 are `assert` statements, so they vanish under
    `python -O`. Re-derived from the data: a prefix carrying '_' or a non-letter
    could never match `partition('_')` (ids.py:135/122), so that kind would
    become unrecognisable, and a prefix shared with TOKEN_PREFIXES would make an
    id and a credential the same string."""
    kinds = list(ids.PREFIXES)
    assert len(set(ids.PREFIXES[k] for k in kinds)) == len(kinds), 'two kinds share a prefix'
    for kind, prefix in ids.PREFIXES.items():
        assert prefix and '_' not in prefix and ' ' not in prefix, kind
        assert prefix == prefix.lower(), kind
        assert all(c.isalpha() and c.isascii() for c in prefix), (kind, prefix)
    shared = set(ids.TOKEN_PREFIXES.values()) & set(ids.PREFIXES.values())
    assert not shared, 'a token prefix collides with an id prefix: %s' % sorted(shared)
    assert set(ids.TOKEN_PREFIXES.values()) == {'dev', 'node', 'hook', 'brk'}
    assert ids.GLOBAL_WORKSPACE == 'ws_global'


# ── encode: the range guard and the bit order (ids.py:60-65) ─────────────────

@pytest.mark.parametrize('ms,rand', [
    (-1, 0),                        # ids.py:62 lower bound, time
    (0, -1),                        # ids.py:62 lower bound, random
    (-1, -1),
    (ids._MAX_MS + 1, 0),           # ids.py:62 upper bound, time (`<=`, not `<`)
    (0, ids._MAX_RAND + 1),         # ids.py:62 upper bound, random
    (ids._MAX_MS + 1, ids._MAX_RAND + 1),
    (ids._MAX_MS, ids._MAX_RAND + 1),
], ids=['ms_below', 'rand_below', 'both_below', 'ms_above', 'rand_above', 'both_above',
        'rand_above_at_ms_max'])
def test_encode_refuses_a_component_outside_its_bits(ms, rand):
    """A 48-bit time plus 80 random bits is the whole 128-bit shape: an
    out-of-range component would silently overflow into the other half and mint
    an id whose decoded time is a lie, so ids.py:62-63 must raise."""
    with pytest.raises(ValueError) as got:
        ids.encode(ms, rand)
    assert 'out of range' in str(got.value)


def test_encode_accepts_exactly_its_bounds_and_wraps_high_bits_first():
    """The same guard's accept side: `<=` turned into `<` (or `>=` on the lower
    bound) rejects a legal id, and reversing ids.py:65's `range(25, -1, -1)`
    turns every id into its own mirror while keeping the length."""
    assert ids.encode(0, 0) == '0' * 26
    assert ids.encode(0, ids._MAX_RAND) == '0' * 10 + 'Z' * 16   # 48 time + 80 random bits
    assert ids.encode(ids._MAX_MS, 0) == '7' + 'Z' * 9 + '0' * 16
    assert ids.encode(ids._MAX_MS, ids._MAX_RAND) == '7' + 'Z' * 25
    assert ids.encode(1, 0) == '0' * 9 + '1' + '0' * 16
    assert ids.encode(0, 1) == '0' * 25 + '1'
    for ms, rand in [(0, 0), (1, 0), (0, 1), (BASE_MS, 42), (BASE_MS, ids._MAX_RAND),
                     (ids._MAX_MS, 0), (ids._MAX_MS, ids._MAX_RAND), (BASE_MS + 7, 31)]:
        assert ids.encode(ms, rand) == _crockford((ms << 80) | rand), (ms, rand)
        assert _crockford_value(ids.encode(ms, rand)) == (ms << 80) | rand, (ms, rand)


# ── is_ulid: every shape that must be refused (ids.py:88-91) ─────────────────

@pytest.mark.parametrize('value', [
    '',                             # ids.py:89 length
    '0' * 25,                       # ids.py:89 one short
    '0' * 27,                       # ids.py:89 one long
    ULID[:-1], ULID + '0',
    'msn_' + ULID,                  # the whole id is not a bare ULID
    ULID + '\n', ' ' + ULID, ULID + ' ',
    None, 0, 42, 3.5, True,          # ids.py:89 `isinstance(value, str)`
    b'0' * 26,                       # bytes are not 26 characters
    ['0'] * 26, ('0' * 26,), {'0' * 26}, {'a': ULID},
], ids=['empty', 'short25', 'long27', 'ulid_short', 'ulid_long', 'whole_id', 'newline',
        'leading_space', 'trailing_space', 'none', 'zero', 'int', 'float', 'true', 'bytes',
        'list', 'tuple', 'set', 'dict'])
def test_is_ulid_refuses_anything_that_is_not_exactly_26_characters(value):
    """The length/`isinstance` guard is what stops a truncated id, a whole id
    with its prefix still on it, or a non-string arriving from a boundary
    (JSON, SQLite, argv) from being read as a ULID."""
    assert ids.is_ulid(value) is False


@pytest.mark.parametrize('bad', ['I', 'L', 'O', 'U', 'i', 'l', 'o', 'u'])
def test_is_ulid_refuses_the_four_letters_crockford_drops(bad):
    """ids.py:91 `all(c in ALPHABET for c in value)`: dropping I/L/O/U from the
    alphabet is a deliberate ambiguity rule, so an id that differs from another
    only by an O/0 or I/1 must not be accepted."""
    for position in (1, 12, 25):
        assert ids.is_ulid(ULID[:position] + bad + ULID[position + 1:]) is False


@pytest.mark.parametrize('bad', ['-', '_', '!', '+', '~', ' ', '\t', '.', ',', ':', '/',
                                 '\\', '#', '\u0669', '\u2460'],
                         ids=['dash', 'underscore', 'bang', 'plus', 'tilde', 'space', 'tab',
                              'dot', 'comma', 'colon', 'slash', 'backslash', 'hash',
                              'arabic_indic_nine', 'circled_one'])
def test_is_ulid_refuses_every_character_outside_the_alphabet(bad):
    """ids.py:91 again, and specifically against a rewrite as
    `value.isalnum()`: '\\u0669' (Arabic-Indic nine) and '\\u2460' (circled one)
    are alnum/decimal but are not Crockford symbols, so they must not pass."""
    for position in (1, 25):
        assert ids.is_ulid(ULID[:position] + bad + ULID[position + 1:]) is False


@pytest.mark.parametrize('first', list('01234567'))
def test_is_ulid_accepts_a_time_head_inside_48_bits(first):
    """ids.py:90 positive side: the leading character carries the top 3 bits of
    the 48-bit time, so all eight Crockford symbols 0-7 must pass — every value
    `encode` can legally mint lands here."""
    assert ids.is_ulid(first + ULID[1:]) is True


@pytest.mark.parametrize('first', list('89ABCDEFGHJKMNPQRSTVWXYZ') + ['8', '9'])
def test_is_ulid_refuses_a_time_head_past_48_bits(first):
    """ids.py:90 denial side: '8' would decode to a 5-bit time head, i.e. a
    53-bit timestamp that `ulid_ms` cannot represent; widening the membership
    test to the whole alphabet accepts ids no clock can mint."""
    assert ids.is_ulid(first + ULID[1:]) is False


def test_every_ulid_encode_can_mint_is_one_is_ulid_accepts():
    """The two halves must agree: for every legal (ms, rand) — including both
    corners of ids.py:62 — `encode` output passes ids.py:88-91 and `ulid_ms`
    (ids.py:94-101) reads the time back. An over-strict accept test here would
    reject ids the mint itself produced."""
    for ms, rand in [(0, 0), (0, ids._MAX_RAND), (ids._MAX_MS, 0), (ids._MAX_MS, ids._MAX_RAND),
                     (BASE_MS, 7), (1, 1 << 79)]:
        u = ids.encode(ms, rand)
        assert ids.is_ulid(u) is True, (ms, rand, u)
        assert ids.ulid_ms(u) == ms, (ms, rand, u)


# ── ulid_ms: the read path (ids.py:94-101) ───────────────────────────────────

@pytest.mark.parametrize('value', [
    '', 'x', None, 42, b'0' * 26,
    '_' + '0' * 25,                 # 26 characters, but '_' is not a symbol
    'msn_' + ULID,                  # a whole id, not a ULID
    ULID[:-1], ULID + '0',
    'O' + ULID[1:],                 # past the 48-bit head
    'A' * 26,
], ids=['empty', 'one_char', 'none', 'int', 'bytes', 'underscore_head', 'whole_id',
        'short', 'long', 'letter_O', 'letter_A_all'])
def test_ulid_ms_refuses_a_value_that_is_not_a_ulid(value):
    """ids.py:96-97: without the fail-closed guard a 26-character string with a
    '_' in it dies in `ALPHABET.index` with a message about a character, and a
    25-character string decodes to a *plausible wrong timestamp* instead of
    raising. The ordering key of an event may never be guessed at."""
    with pytest.raises(ValueError) as got:
        ids.ulid_ms(value)
    assert 'not a ULID' in str(got.value)


@pytest.mark.parametrize('rand', [0, 1, ids._MAX_RAND, BASE_MS],
                         ids=['zero', 'one', 'max_rand', 'base_ms'])
def test_ulid_ms_reads_the_time_and_only_the_time(rand):
    """ids.py:101 `n >> 80`: shifting by anything but the random-part width (or
    forgetting the shift) makes the ordering key depend on the random bits, so
    two ids minted in the same millisecond would disagree about their time."""
    assert ids.ulid_ms(ids.encode(BASE_MS, rand)) == BASE_MS


# ── new_ulid: the pin path (ids.py:68-74) ────────────────────────────────────

def test_zero_is_a_pin_not_a_missing_pin(monkeypatch):
    """ids.py:71-73 test `is not None` on purpose: written as `if at_ms or
    entropy`, the legal value 0 falls through to the minting branch and a test
    that pins `at_ms=0, entropy=0` silently gets wall-clock randomness instead of
    ids.py:64's fixed encoding."""
    monkeypatch.setattr(ids, '_last', [0, 0])
    _fake(monkeypatch, clock=_Never(), draws=_Never())
    assert ids.new_ulid(at_ms=0, entropy=0) == '0' * 26
    assert ids.new_ulid(at_ms=BASE_MS, entropy=0) == ids.encode(BASE_MS, 0)
    assert ids.new_ulid(at_ms=0, entropy=ids._MAX_RAND) == '0' * 10 + 'Z' * 16
    # one side pinned: the other still comes from the seam, never from the state
    clock, draws = _Clock(BASE_MS), _Draws(80)
    monkeypatch.setattr(ids, 'time', clock)
    monkeypatch.setattr(ids, 'secrets', draws)
    assert ids.new_ulid(at_ms=BASE_MS) == ids.encode(BASE_MS, 0)      # draws 80 random bits
    assert ids.new_ulid(entropy=0) == ids.encode(BASE_MS, 0)          # reads the clock
    assert draws.asked == [80] and clock.reads == 1
    assert ids._last == [0, 0], 'a pinned mint must not advance the monotonic state'


def test_a_pinned_ulid_never_touches_the_monotonic_state(monkeypatch):
    """ids.py:71-74 returns before ids.py:75-84: if `_last[:] = [ms, rand]` ever
    ran for a pinned call, every id minted afterwards would be pushed off the
    real clock by whatever a test pinned."""
    sentinel = [42, 4242]
    monkeypatch.setattr(ids, '_last', list(sentinel))
    _fake(monkeypatch, clock=_Never(), draws=_Never())
    assert ids.new_ulid(at_ms=BASE_MS, entropy=5) == ids.encode(BASE_MS, 5)
    assert ids.new_ulid(at_ms=0, entropy=0) == '0' * 26
    assert ids._last == sentinel


def test_the_first_ulid_of_a_new_millisecond_spends_randomness(monkeypatch):
    """ids.py:82-84 (the else of the same-ms guard): the fresh-millisecond
    branch must draw `randbits(80)` and must store what it minted into the
    module's own list (ids.py:84 `_last[:] =`, not a rebind), or monotonicity
    silently dies with the next call."""
    clock, draws = _Clock(BASE_MS), _Draws(80)
    monkeypatch.setattr(ids, '_last', [0, 0])
    _fake(monkeypatch, clock=clock, draws=draws)
    assert ids.new_ulid() == ids.encode(BASE_MS, 0)
    assert draws.asked == [80] and clock.reads == 1
    assert ids._last == [BASE_MS, 0]


def test_two_ulids_in_one_millisecond_stay_in_creation_order(monkeypatch):
    """ids.py:77-79: inside the clock's own millisecond the next id must be the
    previous random part +1 with NO new draw (ids.py:79). Drop the branch and two
    ids minted together are two independent draws that can sort either way, so
    the ordering key stops being an ordering key."""
    clock, draws = _Clock(BASE_MS), _Draws()          # any draw is a failure here
    monkeypatch.setattr(ids, '_last', [BASE_MS, 5])
    _fake(monkeypatch, clock=clock, draws=draws)
    got = ids.new_ulid()
    assert got == ids.encode(BASE_MS, 6)
    assert ids.ulid_ms(got) == BASE_MS and ids._last == [BASE_MS, 6]
    assert clock.reads == 1 and draws.asked == []


def test_a_stepped_back_clock_cannot_take_an_id_backwards(monkeypatch):
    """ids.py:77 `ms <= _last[0]` — the `<=` is the NTP case: written as `==` (or
    as `ms < _last[0]`) a clock that jumps back mints an id that sorts BEFORE
    ids already handed out, and a store keyed on the id reorders history."""
    clock, draws = _Clock(BASE_MS - 60_000), _Draws()
    monkeypatch.setattr(ids, '_last', [BASE_MS, 500])
    _fake(monkeypatch, clock=clock, draws=draws)
    got = ids.new_ulid()
    assert got == ids.encode(BASE_MS, 501)             # stays on the last ms, not the clock
    assert ids.ulid_ms(got) == BASE_MS and ids._last == [BASE_MS, 501]


def test_an_exhausted_random_part_carries_into_the_time(monkeypatch):
    """ids.py:80-81: at `_MAX_RAND` the increment must carry to ms+1 and refill
    with a 79-bit draw (never a full 80-bit one, which could land above the
    carried value's own bound). Without the guard `encode` raises out of
    `new_ulid()`, or the counter wraps to 0 and reissues an already-minted id."""
    clock, draws = _Clock(BASE_MS), _Draws(79)
    monkeypatch.setattr(ids, '_last', [BASE_MS, ids._MAX_RAND])
    _fake(monkeypatch, clock=clock, draws=draws)
    got = ids.new_ulid()
    assert draws.asked == [79], 'the carry must refill with 79 bits, not 80'
    assert got == ids.encode(BASE_MS + 1, 0)
    assert ids.ulid_ms(got) == BASE_MS + 1 and ids._last == [BASE_MS + 1, 0]


def test_the_carry_at_the_end_of_the_48bit_clock_still_fails_closed(monkeypatch):
    """ids.py:80-81 -> ids.py:62: a carry past `_MAX_MS` is out of the shape, so
    the mint must raise rather than wrap the timestamp to 0."""
    clock, draws = _Clock(ids._MAX_MS), _Draws(79)
    monkeypatch.setattr(ids, '_last', [ids._MAX_MS, ids._MAX_RAND])
    _fake(monkeypatch, clock=clock, draws=draws)
    with pytest.raises(ValueError):
        ids.new_ulid()


def test_real_mints_never_repeat_and_never_go_backwards():
    """The whole of ids.py:75-85 under concurrency: `_lock` (ids.py:75) is what
    makes `_last` (ids.py:79-84) a sequence rather than a race, so ids handed to
    two threads at once must still be unique and increasing per caller."""
    threads, minted, failures = [], [[] for _ in range(4)], []
    start = ids.ulid_ms(ids.new_ulid())

    def _mint(worker):
        try:
            worker.extend(ids.new_ulid() for _ in range(250))
        except Exception as exc:                       # a thread that died is a failure
            failures.append(repr(exc))

    for worker in minted:
        t = threading.Thread(target=_mint, args=(worker,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join(30)
    assert not failures, failures
    every = [u for worker in minted for u in worker]
    assert len(every) == 1000 and len(set(every)) == 1000, 'new_ulid minted a duplicate'
    for worker in minted:
        assert worker == sorted(worker), 'an id went backwards inside one thread'
    assert min(ids.ulid_ms(u) for u in every) >= start, 'an id predates the run'


# ── new_id: the prefixed mint (ids.py:104-106) ───────────────────────────────
@pytest.mark.parametrize('kind', sorted(ids.PREFIXES))
def test_new_id_prefixes_a_real_ulid_with_its_own_kind(kind):
    """ids.py:106 `'%s_%s' % (PREFIXES[kind], new_ulid(**pin))`: the separator is
    what `is_id`/`kind_of` partition on, so a dropped '_' or a wrong table
    lookup makes an id unreadable by the two functions that name its kind."""
    got = ids.new_id(kind, at_ms=BASE_MS, entropy=42)
    assert got == ids.PREFIXES[kind] + '_' + ids.encode(BASE_MS, 42)
    assert len(got) == len(ids.PREFIXES[kind]) + 27
    assert ids.is_id(got, kind) is True and ids.kind_of(got) == kind


def test_new_id_passes_the_pins_through_and_refuses_an_unknown_kind():
    """ids.py:106: `PREFIXES[kind]` (KeyError on a typo) and `new_ulid(**pin)`
    (the pins must reach ids.py:71-74, and an out-of-range pin must reach the
    range guard at ids.py:62). Silently defaulting an unknown kind to some
    prefix, or dropping the kwargs, both read as a passing test here."""
    assert ids.new_id('task', at_ms=BASE_MS, entropy=9) == 'tsk_' + ids.encode(BASE_MS, 9)
    for kind in ('nope', 'Mission', 'mission ', '', None, 7):
        with pytest.raises(KeyError):
            ids.new_id(kind)
    with pytest.raises(ValueError):
        ids.new_id('mission', entropy=-1)
    with pytest.raises(ValueError):
        ids.new_id('mission', at_ms=ids._MAX_MS + 1)
    with pytest.raises(TypeError):
        ids.new_id('mission', pinned_instead=1)


# ── is_id: the kind check and the reserved workspace (ids.py:109-116) ────────
@pytest.mark.parametrize('kind', sorted(ids.PREFIXES))
def test_is_id_admits_only_its_own_kind(kind):
    """ids.py:114-116: the comparison is against `PREFIXES[kind] + '_'`, so a
    kind that admits another kind's id (a shared or prefix-of prefix, or a
    `startswith` on the bare prefix) lets a `task` id stand where a `mission` id
    is required."""
    mine = ids.new_id(kind, at_ms=BASE_MS, entropy=7)
    assert ids.is_id(mine, kind) is True
    for other in sorted(ids.PREFIXES):
        if other != kind:
            assert ids.is_id(ids.new_id(other, at_ms=BASE_MS, entropy=7), kind) is False, other
    assert ids.is_id(ULID, kind) is False, 'a bare ULID is not an id'
    assert ids.is_id(ids.PREFIXES[kind] + '_' + ULID.lower(), kind) is False


@pytest.mark.parametrize('value', [
    'msn_',                          # ids.py:115-116: prefix alone, empty tail
    'msn',
    'msn' + ULID,                    # ids.py:114: the '_' is part of the prefix
    'msn-' + ULID,
    'MSN_' + ULID,                   # ids.py:115 startswith is case-sensitive
    'msn_' + ULID[:-1], 'msn_' + ULID + '0',
    'msn_' + ULID[:20] + 'O' + ULID[21:],
    'msn_' + ULID[:20] + ' ' + ULID[21:],
    'tsk_' + ULID,                   # another kind's id
], ids=['empty_tail', 'no_separator', 'no_underscore', 'dash_separator', 'uppercase_prefix',
        'tail_short', 'tail_long', 'tail_letter_O', 'tail_space', 'other_kind'])
def test_is_id_refuses_an_id_shape_that_only_looks_right(value):
    """Every near-miss on ids.py:115-116: dropping the '_' from the prefix,
    relaxing `is_ulid` on the tail, or lowercasing the value, all accept one of
    these — and one of these is what an attacker (or a sloppy copy) hands the
    route layer."""
    assert ids.is_id(value, 'mission') is False


@pytest.mark.parametrize('value', [None, 0, 1, 42, 3.5, True, b'msn_' + ULID.encode(),
                                   ['msn_' + ULID], ('msn_' + ULID,), {'msn_' + ULID},
                                   {'id': 'msn_' + ULID}],
                         ids=['none', 'zero', 'one', 'int', 'float', 'true', 'bytes',
                              'list', 'tuple', 'set', 'dict'])
def test_is_id_refuses_a_value_that_is_not_a_string(value):
    """ids.py:115 `isinstance(value, str)`: without it a None or a dict arriving
    from JSON/SQLite reaches `startswith`/slicing and either raises inside a
    request or, with a duck-typed object, compares true."""
    assert ids.is_id(value, 'mission') is False
    assert ids.is_id(value, 'workspace') is False


@pytest.mark.parametrize('kind', ['', 'ws', 'Workspace', 'workspace_', 'global', None, 7],
                         ids=['empty', 'bare_ws', 'capitalised', 'trailing_underscore',
                              'global', 'none', 'int'])
def test_is_id_refuses_a_kind_it_never_declared(kind):
    """ids.py:114 `PREFIXES[kind]` must KeyError on an undeclared kind: rewritten
    as `PREFIXES.get(kind, '')` an unknown kind compares against `'_'`, and a
    guard meant to name a kind stops being a guard."""
    with pytest.raises(KeyError):
        ids.is_id('msn_' + ULID, kind)


@pytest.mark.parametrize('value', [
    ids.GLOBAL_WORKSPACE, 'ws_' + ULID, 'ws_' + ULID[:25] + '1',
], ids=['reserved', 'minted_shape', 'other_tail'])
def test_the_reserved_workspace_is_a_workspace_id_and_nothing_else(value):
    """ids.py:112-113: `ws_global` is accepted for `workspace` only, and only by
    exact equality — widened to `startswith`/`in`, `ws_globalanything` (or a
    mission id) becomes a workspace id and rows leak across the tenant boundary
    of domain-model §1 rule 8."""
    assert ids.is_id(value, 'workspace') is True
    if value != ids.GLOBAL_WORKSPACE:
        assert ids.kind_of(value) == 'workspace'


@pytest.mark.parametrize('value', [
    'ws_global_', 'ws_global2', ' ws_global', 'ws_global ', 'WS_GLOBAL', 'Ws_Global',
    'ws_global' + ULID, 'ws_globalX', 'global', 'ws_globa1', 'ws_' + 'gl0ba1' + '0' * 21,
], ids=['trailing_underscore', 'suffix_2', 'leading_space', 'trailing_space', 'upper',
        'mixed_case', 'padded', 'x_suffix', 'no_prefix', 'one_for_o', 'tail_with_l'])
def test_the_reserved_workspace_cannot_be_forged_by_lookalike(value):
    """ids.py:112 again: the reserved name is compared, not matched. Note 'l' and
    'o' are not Crockford symbols at all, so `ws_` + 'global' can never be a real
    workspace id either (ids.py:91 refuses its tail)."""
    assert ids.is_ulid('global') is False
    assert ids.is_id(value, 'workspace') is False
    assert ids.kind_of(value) is None


def test_the_reserved_workspace_is_never_minted(monkeypatch):
    """ids.py:106 + ids.py:56: a minted workspace id is `ws_` + a real ULID, so
    it can never collide with the reserved global row (`_last` forced low so the
    first id of the run is still not the reserved string)."""
    monkeypatch.setattr(ids, '_last', [0, 0])
    _fake(monkeypatch, clock=_Clock(0), draws=_Draws(80))
    got = ids.new_id('workspace')
    assert got != ids.GLOBAL_WORKSPACE and ids.is_id(got, 'workspace')
    assert ids.kind_of(got) == 'workspace' and ids.token_kind(got) is None


# ── token_kind: the credential namespace (ids.py:119-128) ────────────────────
@pytest.mark.parametrize('kind', sorted(ids.TOKEN_PREFIXES))
def test_token_kind_names_the_credential_kind_its_prefix_declares(kind):
    """ids.py:125-127: the loop maps `head -> kind` over TOKEN_PREFIXES. A
    missing `sep`/`tail` test (ids.py:123) or a `head in prefix` comparison
    instead of `prefix == head` turns a malformed string into a credential kind,
    which is exactly the wrong direction of failure."""
    assert ids.token_kind('%s_%s' % (ids.TOKEN_PREFIXES[kind], 'sekret123')) == kind
    assert ids.token_kind('%s_a_b' % ids.TOKEN_PREFIXES[kind]) == kind, 'split on the FIRST _'
    assert ids.token_kind('%s_x' % ids.TOKEN_PREFIXES[kind].upper()) is None, 'case matters'


@pytest.mark.parametrize('value', [
    'hook', 'dev', 'node', 'brk',                   # ids.py:123: no separator
    'hook_', 'dev_', 'node_', 'brk_',               # ids.py:123: separator, no secret
    '', '_', '__', 'x', 'hook x',
    '_hook', 'unknown_thing', 'msn_' + ULID, 'usr_x', 'ws_global',
    'exe_01ARZ3NDEKTSV4RRFFQ69G5FAV',
    None, 0, 7, True, 3.5, b'hook_x', ['hook_x'], {'hook_x'}, {'hook': 'x'},
], ids=['bare_hook', 'bare_dev', 'bare_node', 'bare_brk', 'empty_tail_hook', 'empty_tail_dev',
        'empty_tail_node', 'empty_tail_brk', 'empty', 'only_underscore', 'double_underscore',
        'single_char', 'inner_space', 'leading_underscore', 'unknown_prefix', 'an_id',
        'user_id', 'reserved_ws', 'old_exe_token', 'none', 'zero', 'int', 'true', 'float',
        'bytes', 'list', 'set', 'dict'])
def test_token_kind_refuses_anything_that_is_not_a_token(value):
    """The fail-closed side of ids.py:122-124 and ids.py:128: anything that is
    not `<token-prefix>_<non-empty tail>` names no credential kind, and an id
    (whose prefixes share no symbol with tokens, ids.py:52-53) must never read as
    one — otherwise a caller that checks `token_kind` before `kind_of` accepts an
    id as a credential."""
    assert ids.token_kind(value) is None


def test_the_id_and_token_namespaces_never_overlap():
    """ids.py:52-53 re-derived as behaviour, not as an import-time assert: for
    every credential kind and every entity kind, an id is never a token and a
    token is never an id of any kind. `exe_` once meant both, and the same
    collision re-opens that bug."""
    for token_kind_, prefix in ids.TOKEN_PREFIXES.items():
        token = '%s_%s' % (prefix, ULID)
        assert ids.token_kind(token) == token_kind_
        assert ids.kind_of(token) is None, token
        for kind in sorted(ids.PREFIXES):
            assert ids.is_id(token, kind) is False, (token, kind)
    for kind, prefix in ids.PREFIXES.items():
        ident = ids.new_id(kind, at_ms=BASE_MS, entropy=3)
        assert ids.token_kind(ident) is None, (kind, ident)
        assert ids.kind_of(ident) == kind


# ── kind_of: what an id is (ids.py:131-139) ─────────────────────────────────
@pytest.mark.parametrize('kind', sorted(ids.PREFIXES))
def test_kind_of_reads_back_the_kind_of_any_declared_id(kind):
    """ids.py:136-138: the lookup needs BOTH the prefix and a real ULID behind
    it; `is_id` and `kind_of` must agree for every kind in the one table."""
    ident = ids.new_id(kind, at_ms=BASE_MS, entropy=11)
    assert ids.kind_of(ident) == kind
    assert ids.is_id(ident, kind) is True


@pytest.mark.parametrize('value', [
    'msn_', 'msn', 'msn_nope', 'msn__01ARZ3NDEKTSV4RRFFQ69G5FAV',
    'msn_' + ULID[:-1], 'msn_' + ULID + '0',
    'msn_' + ULID[:12] + 'I' + ULID[13:],      # a Crockford-excluded letter in the tail
    'msn_' + ULID.lower(),                     # ids.py:137 is case-sensitive
    'MSN_' + ULID,                             # ids.py:136 head match is case-sensitive
    'msn-' + ULID,                             # ids.py:135 partition on '_'
    'msnx_' + ULID,                            # ids.py:136 `prefix == head`, not startswith
    'task_' + ULID,                            # a field name, not a declared prefix
    'mission_' + ULID,
    hook_token(),                              # a credential is never an id
    'dev_' + ULID,
], ids=['empty_tail', 'no_separator', 'short_tail', 'double_underscore', 'tail_short',
        'tail_long', 'tail_letter_I', 'lowercase', 'uppercase_prefix', 'dash_separator',
        'near_prefix', 'field_task', 'field_mission', 'hook_token', 'dev_token'])
def test_kind_of_refuses_a_head_it_does_not_declare_or_a_tail_that_is_not_a_ulid(value):
    """ids.py:136-137: `prefix == head and is_ulid(tail)` — dropping the tail
    check makes `msn_nope` a mission, and relaxing the head match makes a field
    name (`task_…`) or a credential (`hook_…`) name an entity kind."""
    assert ids.kind_of(value) is None


@pytest.mark.parametrize('value', [
    None, 0, 7, True, 3.5, b'ws_global', b'msn_' + ULID.encode(),
    ['ws_global'], ('msn_' + ULID,), {'msn_' + ULID}, {'id': 'msn_' + ULID}, object,
], ids=['none', 'zero', 'int', 'true', 'float', 'bytes_ws', 'bytes_id', 'list', 'tuple',
        'set', 'dict', 'builtin'])
def test_kind_of_refuses_a_value_that_is_not_a_string(value):
    """ids.py:134-135 `str(value).partition('_')`: the `str()` is what keeps a
    None / int / list arriving from a boundary a clean None instead of an
    AttributeError inside a request handler; removing it fails this test."""
    assert ids.kind_of(value) is None


def test_kind_of_and_is_id_never_disagree_about_a_value():
    """The two readers must answer the same question: for every value that
    `kind_of` names, `is_id` admits it under that kind, and for every value
    `kind_of` refuses, no kind admits it (ids.py:109-116 vs ids.py:131-139). A
    divergence is how an id passes a route's kind check and then fails the
    store's, or the other way round."""
    candidates = [ids.new_id(k, at_ms=BASE_MS, entropy=5) for k in sorted(ids.PREFIXES)]
    candidates += [ids.GLOBAL_WORKSPACE, 'ws_' + ULID, 'msn_nope', 'msn_', ULID, hook_token(),
                   'dev_' + ULID, 'ws_global_', 'MSN_' + ULID, '', 'x', 'no_such_x']
    for value in candidates:
        named = ids.kind_of(value)
        admitted = [k for k in sorted(ids.PREFIXES) if ids.is_id(value, k)]
        assert (named is not None) == bool(admitted), (value, named, admitted)
        if named is not None:
            assert admitted == [named], (value, named, admitted)
