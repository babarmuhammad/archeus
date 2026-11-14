"""T-1321 — the ten highest-risk uncovered branches of pi's usage accounting.

Source slice: ``claude_sessions/pi.py`` lines 205-261 inclusive at tip
51f4af3f (at tip d429bf96 the same code is ``fold`` 207-268: the error counter
at 250, the usage guard at 254-256, the all-or-none validation at 258-261).
Only ``fold`` is driven; it is pure over the stats dict, so nothing is faked
and no file, process or clock is touched.

Selected branches, denial and fail-closed first:

 1. pi.py:259-261  a nonnumeric figure after valid siblings banks NOTHING from
    that record, and the walk continues with the next record.
 2. pi.py:259-261  a dict in cacheRead and a list in cacheWrite are refused
    without raising.
 3. pi.py:259  the ``isinstance(c, bool)`` arm: ``True`` is an int in Python
    and must not be banked as one.
 4. pi.py:259-261  ``c < 0``: a negative counter leaves the spend already banked
    exact and does not block the next good message.
 5. pi.py:254-256 + 262  a toolResult with a malformed figure cannot poison the
    following assistant turn under the same model.
 6. pi.py:262  a malformed record with no model cannot create the ``pi``
    fallback bucket.
 7. pi.py:261-268  a malformed record after a model change cannot touch the
    previous model's aggregate.
 8. pi.py:255  a usage that is not an object (string, list) still counts the
    turn and banks nothing.
 9. pi.py:259, 263-268  all-zero counts are a real row, and cacheRead and
    cacheWrite never cross into each other's field.
10. pi.py:250  an error turn whose usage is malformed still counts as an error,
    and the corpus walk goes on.

Existing coverage, not copied: tests/test_gaps3_claude_sessions_pi_a.py
(``test_a_hostile_token_count_must_not_take_the_walk_down`` covers a string
input and a None output; ``test_usage_pi_never_reported_is_never_banked`` covers
absent, empty and None usage; ``test_every_error_record_counts_once_*`` covers
the error counter without usage). Probe 3 of the card (a numeric string) is the
branch that existing test already holds, so the boolean arm replaces it; the
card's probe 8 (missing usage) is held by the existing test above, so the
non-object usage replaces it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_sessions import pi  # noqa: E402

TS = '2026-09-14T21:39:%02d.000Z'


def _stats():
    return {'preview': '', 'count': 0, 'title': '', 'usage_by_model': {},
            'models': [], 'first_ts': None, 'last_ts': None, 'branch': '',
            'cwd': '', 'api_errors': 0, 'headless': False}


def _msg(s, n, role='assistant', model='m', usage=None, **extra):
    m = {'role': role, 'content': []}
    if model is not None:
        m['model'] = model
    if usage is not None:
        m['usage'] = usage
    m.update(extra)
    pi.fold({'type': 'message', 'timestamp': TS % n, 'message': m}, s)


def _row(i=0, o=0, cr=0, cw=0):
    return {'in': i, 'out': o, 'cache_read': cr, 'cache_create': cw}


def test_a_nonnumeric_figure_after_valid_siblings_banks_nothing_from_its_record():
    """Kills: removing the all-or-none `any(...)` check at pi.py:259 would bank
    `input` and `cacheRead` from the bad record before `output` raised, leaving
    a partly corrupt row. The existing hostile test only puts the bad figure
    FIRST, so the valid fields are never seen before it."""
    s = _stats()
    _msg(s, 0, usage={'input': 5, 'output': 1, 'cacheRead': 0, 'cacheWrite': 0})
    _msg(s, 1, usage={'input': 5, 'output': 'x', 'cacheRead': 9, 'cacheWrite': 0})
    assert s['usage_by_model'] == {'m': _row(5, 1)}, s['usage_by_model']
    _msg(s, 2, usage={'input': 2, 'output': 2, 'cacheRead': 0, 'cacheWrite': 0})
    assert s['usage_by_model'] == {'m': _row(7, 3)}
    assert s['count'] == 3


def test_a_container_as_a_cache_count_is_refused_without_raising():
    """Kills: dropping `isinstance(c, int)` at pi.py:259 — a dict or list in
    cacheRead/cacheWrite would reach `agg[...] += ...` and raise TypeError out
    of the walk. Both containers are refused whole; the next record is banked."""
    s = _stats()
    _msg(s, 0, usage={'input': 1, 'output': 1, 'cacheRead': {'x': 1}, 'cacheWrite': 0})
    _msg(s, 1, usage={'input': 1, 'output': 1, 'cacheRead': 0, 'cacheWrite': [1]})
    assert s['usage_by_model'] == {}, s['usage_by_model']
    assert s['count'] == 2
    _msg(s, 2, usage={'input': 3, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0})
    assert s['usage_by_model'] == {'m': _row(3, 0)}


def test_a_boolean_count_is_refused_and_is_not_read_as_one():
    """Kills: removing `isinstance(c, bool)` at pi.py:259. Python reads True as
    1, so without that arm a hand-edited `"input": true` would bank a token that
    pi never charged for. Both a leading and a trailing boolean are refused."""
    s = _stats()
    _msg(s, 0, usage={'input': True, 'output': 1, 'cacheRead': 0, 'cacheWrite': 0})
    _msg(s, 1, usage={'input': 1, 'output': 1, 'cacheRead': 0, 'cacheWrite': False})
    assert s['usage_by_model'] == {}, s['usage_by_model']
    _msg(s, 2, usage={'input': 1, 'output': 1, 'cacheRead': 0, 'cacheWrite': 0})
    assert s['usage_by_model'] == {'m': _row(1, 1)}


def test_a_negative_counter_leaves_prior_spend_exact_and_the_next_message_banked():
    """Kills: dropping `c < 0` at pi.py:259. A negative cacheRead would subtract
    from the running aggregate, so the spend banked BEFORE the bad record must
    survive unchanged, and the record after it must still land."""
    s = _stats()
    _msg(s, 0, usage={'input': 5, 'output': 3, 'cacheRead': 0, 'cacheWrite': 0})
    _msg(s, 1, usage={'input': 9, 'output': 9, 'cacheRead': -1, 'cacheWrite': 2})
    assert s['usage_by_model'] == {'m': _row(5, 3)}, s['usage_by_model']
    _msg(s, 2, usage={'input': 1, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0})
    assert s['usage_by_model'] == {'m': _row(6, 3)}


def test_a_bad_tool_result_cannot_poison_the_next_assistant_turn_on_the_same_model():
    """Kills: any state the refused record could leave behind — a row created
    before the check, or a half-banked figure — at pi.py:254-262. The toolResult
    carries no conversational role, so it counts nothing; its refused usage must
    leave the same model's next good turn exact, and no 'pi' row appears."""
    s = _stats()
    _msg(s, 0, role='toolResult', model=None,
         usage={'input': 'bad', 'output': 1, 'cacheRead': 0, 'cacheWrite': 0})
    assert s['usage_by_model'] == {}
    _msg(s, 1, model='m', usage={'input': 4, 'output': 2, 'cacheRead': 1, 'cacheWrite': 0})
    assert s['usage_by_model'] == {'m': _row(4, 2, 1, 0)}, s['usage_by_model']
    assert s['count'] == 1


def test_malformed_counters_with_no_model_never_create_the_pi_bucket():
    """Kills: moving the `model or ...` fallback at pi.py:262 above the
    validation. The fallback key is the one place a refused record could mint a
    permanent line item, so it must stay empty until a figure is good."""
    s = _stats()
    _msg(s, 0, model=None, usage={'input': 'x', 'output': 1, 'cacheRead': 0, 'cacheWrite': 0})
    assert s['usage_by_model'] == {}, s['usage_by_model']
    _msg(s, 1, model=None, usage={'input': 1, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0})
    assert s['usage_by_model'] == {'pi': _row(1, 0)}


def test_malformed_counters_after_a_model_change_leave_the_prior_aggregate_alone():
    """Kills: resolving the key from `s['models'][-1]` before the check at
    pi.py:262, or writing the row before validation. Model a is banked, the
    session switches to b, and b's bad record must leave a's aggregate exactly
    as it was."""
    s = _stats()
    _msg(s, 0, model='a', usage={'input': 2, 'output': 2, 'cacheRead': 0, 'cacheWrite': 0})
    pi.fold({'type': 'model_change', 'modelId': 'b', 'timestamp': TS % 1}, s)
    _msg(s, 2, model='b', usage={'input': 7, 'output': 'x', 'cacheRead': 0, 'cacheWrite': 0})
    assert s['usage_by_model'] == {'a': _row(2, 2)}, s['usage_by_model']


def test_a_usage_that_is_not_an_object_counts_the_turn_and_banks_nothing():
    """Kills: dropping `not isinstance(u, dict)` at pi.py:255. A truthy string or
    list passes `or {}` and would reach `u.get(...)`, raising AttributeError out
    of the walk. The turn itself still counts: _turn runs before usage."""
    s = _stats()
    _msg(s, 0, usage='oops')
    _msg(s, 1, usage=[1, 2])
    assert s['usage_by_model'] == {}, s['usage_by_model']
    assert s['count'] == 2


def test_all_zero_counts_are_a_real_row_and_cache_fields_never_cross():
    """Kills: swapping cacheRead and cacheWrite in the aggregate at pi.py:266-268,
    and treating a zero as absent (`c is not None` at pi.py:259). An all-zero
    record is a real, banked zero, and the two cache fields keep their own sums."""
    s = _stats()
    _msg(s, 0, usage={'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0})
    assert s['usage_by_model'] == {'m': _row()}, s['usage_by_model']
    _msg(s, 1, usage={'input': 1, 'output': 2, 'cacheRead': 3, 'cacheWrite': 4})
    _msg(s, 2, usage={'input': 0, 'output': 0, 'cacheRead': 10, 'cacheWrite': 0})
    assert s['usage_by_model'] == {'m': _row(1, 2, 13, 4)}, s['usage_by_model']


def test_an_error_turn_with_malformed_usage_still_counts_and_the_walk_goes_on():
    """Kills: moving the `api_errors` increment at pi.py:250 below the usage
    guard at pi.py:254-256 — a refused figure would then drop the refusal from
    the error count. The record after it must be read normally."""
    s = _stats()
    _msg(s, 0, stopReason='error', errorMessage='overloaded',
         usage={'input': 'bad', 'output': 0, 'cacheRead': 0, 'cacheWrite': 0})
    assert s['api_errors'] == 1, s['api_errors']
    assert s['usage_by_model'] == {}
    _msg(s, 1, usage={'input': 2, 'output': 1, 'cacheRead': 0, 'cacheWrite': 0})
    assert s['api_errors'] == 1
    assert s['usage_by_model'] == {'m': _row(2, 1)}
    assert s['count'] == 2
