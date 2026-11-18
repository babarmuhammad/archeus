"""T-770: the highest-risk uncovered branches of archeus/core/context/levels.py.

test_context_units.py pins WEIGHTS' values and one composite relevance case,
and the assemble tests pin what `select()` does with the constants. The gaps
this file sits on are the guard statements and invariants of the policy module
itself: the import-time fail-closed assert on the share total (levels.py:12),
the two failure paths of `relevance` (levels.py:45: unknown term, non-numeric
signal), the penalty/addition branch that decides the sign of every term, the
zero weights that keep the P6 terms inert, the boundary values of the share,
authority, level and store tables, and the budget/window scalars.

Pure: no database, no I/O, no clock, no OS, no process, no network. Every
input is a literal, so these read the same on Linux and Windows. Each test
docstring names the source branch whose removal or inversion it would catch;
the companion list is in /work/QWEN-DONE-T-770.md.
"""

import inspect
import re

import pytest

from archeus.core.context import levels as P

SHARES_LITERAL = re.compile(r"^SHARES = \{[^}]*\}", re.M)


# ── fail-closed: the import-time budget guard (levels.py:12) ─────────────────

def test_a_broken_share_total_refuses_to_import():
    """`assert abs(sum(SHARES.values()) - 1.0) < 1e-9` (line 12): the module
    must be unimportable when the shares do not add up, so a typo fails at
    import, not as a silently wrong budget. Delete the assert (or widen its
    tolerance past 1.0) and this exec returns instead of raising."""
    broken = {'L0': 0.80, 'L1': 0.60, 'L2': 0.30, 'L3': 0.20, 'L4': 0.10}  # sums to 2.0
    src, n = SHARES_LITERAL.subn("SHARES = %r" % (broken,), inspect.getsource(P), count=1)
    assert n == 1, 'the SHARES literal moved out of this pattern: retarget the test'
    with pytest.raises(AssertionError):
        exec(compile(src, '<levels-under-test>', 'exec'), {'__name__': 'levels_test'})


def test_the_untampered_source_still_passes_its_own_guard():
    """Control for the test above: the real literals exec through the very same
    harness, so the AssertionError there can only come from the line-12 assert.
    Invert that assert (`<` -> `>=`) and this control is the test that fires."""
    exec(compile(inspect.getsource(P), '<levels-untampered>', 'exec'),
         {'__name__': 'levels_control'})


# ── fail-closed: relevance's two refusal paths (levels.py:45) ────────────────

def test_an_unknown_signal_name_is_a_keyerror_not_a_silent_zero():
    """`WEIGHTS[k]` (line 45): a signal name with no weight must raise, so a
    typo'd or premature term can never score as 0 and pass as 'no evidence'.
    Replace the lookup with `WEIGHTS.get(k, 0)` and both raises below go away."""
    with pytest.raises(KeyError):
        P.relevance({'bogus': 1.0})
    with pytest.raises(KeyError):                        # typo of 'stale' mid-formula
        P.relevance({'lex': 1.0, 'stale_e': 1.0})


def test_a_non_numeric_signal_value_raises_rather_than_being_coerced():
    """The multiplication `WEIGHTS[k] * v` (line 45) is the only place a
    malformed signal is checked: a string must blow up, not be coerced. Wrap
    the value in `float(...)` and this raises nothing."""
    with pytest.raises(TypeError):
        P.relevance({'lex': '1.0'})


# ── the one branch in the module: penalty vs addition (levels.py:35, 45) ─────

def test_stale_is_subtracted_not_added():
    """`-1 if k in PENALTIES else 1` with `PENALTIES = ('stale', 'useless')`
    (lines 35, 45): a stale item must score BELOW a scoreless one. Flip the
    signs on line 45 and {'stale': 1.0} returns +0.5 instead of -0.5; drop
    'stale' from PENALTIES and it returns +0.5 as well."""
    assert P.PENALTIES == ('stale', 'useless')
    assert set(P.PENALTIES) <= set(P.WEIGHTS), 'a penalty with no weight'
    assert P.relevance({'stale': 0.0}) == pytest.approx(0.0)
    assert P.relevance({'stale': 0.5}) == pytest.approx(-0.25)
    assert P.relevance({'stale': 1.0}) == pytest.approx(-0.5)


@pytest.mark.parametrize('term,value,want', [
    ('lex', 0.5, 0.5), ('rec', 0.4, 0.2), ('auth', 0.9, 0.9), ('stale', 1.0, -0.5),
], ids=['lex', 'rec', 'auth', 'stale'])
def test_each_live_term_contributes_exactly_its_weight(term, value, want):
    """The addition half of the generator on line 45, per term and isolated:
    the expected values are hardcoded here, so any weight change or sign flip
    on lines 32-33/45 shows up even if the other terms compensate (which the
    one composite case in test_context_units.py could miss)."""
    assert P.relevance({term: value}) == pytest.approx(want)


def test_the_reserved_p6_terms_cannot_move_the_score_yet():
    """`'anchor': 0.0, 'link': 0.0, 'conf': 0.0, 'useless': 0.0` (lines 32-33):
    the weights stay 0 until a phase produces their inputs. Turn any of them
    on early (0.0 -> 0.5) and this full-mark injection stops returning 0.0.
    This is also the only place 'useless''s penalty membership is observable:
    its weight is 0, so only the PENALTIES pin on line 35 guards it."""
    assert P.relevance({'anchor': 1.0, 'link': 1.0, 'conf': 1.0, 'useless': 1.0}) == 0.0


def test_no_signals_score_exactly_zero_and_mixed_signals_are_the_term_sum():
    """The empty-generator boundary of line 45: an item with no signals scores
    0, not 1 (`sum((), ...)` seeded wrong) and never negative (penalty sign
    applied unconditionally). The mixed case re-checks full-linearity, and the
    call must not consume the caller's dict (a `pop` in the generator fails
    the final line)."""
    assert P.relevance({}) == 0.0
    assert P.relevance({'lex': 0.25, 'rec': 1.0, 'auth': 0.5, 'stale': 1.0,
                        'useless': 1.0}) == pytest.approx(0.25 + 0.5 + 0.5 - 0.5)
    signals = {'lex': 0.3, 'stale': 1.0}
    P.relevance(signals)
    assert signals == {'lex': 0.3, 'stale': 1.0}


# ── budget boundaries: the share table (levels.py:11) ─────────────────────────

def test_shares_are_keyed_to_levels_positive_and_non_increasing():
    """`SHARES` (line 11), the budget boundaries of every level: keyed to
    exactly P.LEVELS (a stale key would KeyError at assemble.py:385), each
    level has a share of its own (a 0 share starves it to carry alone), and
    the non-increasing order L0 >= ... >= L4 is what makes the budget flow
    DOWN. Swapping 0.40/0.30 keeps the line-12 sum assert happy and fails
    only here."""
    assert tuple(P.SHARES) == P.LEVELS
    assert all(0.0 < s < 1.0 for s in P.SHARES.values())
    ordered = [P.SHARES[lv] for lv in P.LEVELS]
    assert ordered == sorted(ordered, reverse=True)
    assert abs(sum(ordered) - 1.0) < 1e-9


# ── level selection: the tables select() and assemble() index by ──────────────

def test_the_five_levels_have_one_name_each_and_fill_in_order():
    """`LEVELS` (line 7) is iterated and `.index()`-ed by assemble.py:384/405,
    so its ORDER is the fill order and the budget-carry direction; a swapped
    pair is invisible to every other test. `LEVEL_NAMES` (lines 8-9) must name
    each level exactly once, or a selected level renders nameless."""
    assert isinstance(P.LEVELS, tuple) and len(set(P.LEVELS)) == 5
    assert P.LEVELS == ('L0', 'L1', 'L2', 'L3', 'L4')
    assert P.LEVEL_NAMES == {'L0': 'immediate', 'L1': 'project', 'L2': 'related',
                             'L3': 'historical', 'L4': 'global'}


def test_the_stores_are_ordered_state_then_knowledge_then_history():
    """`STORES` (line 16): assemble.py:404-405 turns this tuple into the
    within-level sort key, so the order is the promise that a stale fact
    never reads first. Swap 'knowledge' and 'history' and items start with
    the stalest store; this tuple is the only statement of that rule."""
    assert isinstance(P.STORES, tuple) and len(set(P.STORES)) == 3
    assert P.STORES == ('state', 'knowledge', 'history')


def test_authority_ladder_is_strictly_ordered_and_in_range():
    """`AUTHORITY` (lines 39-40), consumed at assemble.py:371 with weight 1.0
    (the joint-highest): explicit > confirmed > extracted > inferred >
    candidate, strictly (no ties), every rung inside (0, 1] and the top rung
    exactly 1.0. Swap two adjacent rungs, or scale the whole table, and every
    downstream ranking silently inverts while all value tests still pass."""
    assert set(P.AUTHORITY) == {'explicit', 'confirmed', 'extracted', 'inferred',
                                'candidate'}
    ladder = [P.AUTHORITY[k] for k in ('explicit', 'confirmed', 'extracted', 'inferred',
                                       'candidate')]
    assert all(0.0 < a <= 1.0 for a in ladder)
    assert ladder == sorted(ladder, reverse=True) and len(set(ladder)) == 5
    assert P.AUTHORITY['explicit'] == 1.0


# ── the module's scalar boundaries (levels.py:19, 23, 26) ─────────────────────

def test_default_budget_and_retrieval_bounds_are_positive_ints_at_their_docs():
    """DEFAULT_BUDGET_TOKENS = 12000 (line 19, §2.3), HISTORY_WINDOW_DAYS = 7
    (line 23, also the divisor of _recency at assemble.py:322 and the zero
    point of the recency horizon), HISTORY_CANDIDATES = 50 (line 26, a SQL
    LIMIT at assemble.py:204). A 0 or float window days still divides but
    skews or crashes ranking; a 0 budget empties every default package;
    changing any value away from the doc fails here."""
    for value in (P.DEFAULT_BUDGET_TOKENS, P.HISTORY_WINDOW_DAYS, P.HISTORY_CANDIDATES):
        assert isinstance(value, int) and not isinstance(value, bool) and value > 0
    assert (P.DEFAULT_BUDGET_TOKENS, P.HISTORY_WINDOW_DAYS, P.HISTORY_CANDIDATES) == (
        12000, 7, 50)
