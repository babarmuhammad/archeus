"""T-1452: the branches of `archeus/core/execution/checkpoint.py` that
test_session_units.py and test_gaps_core_execution_checkpoint.py leave open:
the trigger of an end whose stop reason the state does not use (trigger_of
38-44), a row without a text key (_text 52-53), and what _clip hands on (56-57):
the homes it was given, a non-text item, the empty input.
"""

from types import SimpleNamespace

import pytest

from archeus.core.execution import checkpoint
from archeus.core.homes import Homes


def _e(state, stop_reason=None):
    return SimpleNamespace(state=state, stop_reason=stop_reason, process_seq=1,
                           failure=None, exit_code=None, usage=None)


@pytest.mark.parametrize('state, stop, trigger', [
    ('ENDED_OK', 'pressure', 'task_boundary'),
    ('ENDED_OK', 'pause_timeout', 'task_boundary'),
    ('ENDED_KILLED', 'cancel', 'failure'),
    ('ENDED_REJECTED', 'pause_timeout', 'failure'),
    ('ENDED_ERROR', 'pause_timeout', 'failure'),
], ids=['ok-pressure', 'ok-pause', 'killed-cancel', 'rejected-pause', 'error-pause'])
def test_the_stop_reason_only_names_a_trigger_where_the_state_uses_it(state, stop, trigger):
    """checkpoint.py:38-44 — ENDED_OK returns before the stop reason is read, and
    'pause' needs ENDED_KILLED with pause_timeout; the same reason on any other
    state falls through to 'failure'. Returning `_TRIGGER.get(stop)` for every
    state, or dropping the state test from line 42, changes one of these rows."""
    assert checkpoint.trigger_of(_e(state, stop)) == trigger


def test_a_row_without_a_text_key_renders_as_the_string_None():
    """checkpoint.py:52-53 — `x.get('text')` on a dict that has none gives None,
    and str(None) is the one thing a constraint row without text can say. Current
    behaviour, pinned as it is; the cap never sees a None, it sees this string."""
    assert checkpoint._text({'origin': 'inferred', 'source_ref': 'msg_x'}) == 'None'


def test_clip_hands_the_homes_it_was_given_to_cut_safe_unchanged(monkeypatch):
    """checkpoint.py:57 — `cut_safe(redact(str(i)), homes, 300)`: the homes
    argument reaches the cut as the same object, not a copy and not None. Passing
    `Homes()` in its place would cut without the account-home projection that
    test_gaps_core_execution_checkpoint.py:378 relies on."""
    seen = []
    real = checkpoint.cut_safe

    def spy(text, homes, limit):
        seen.append(homes)
        return real(text, homes, limit)

    monkeypatch.setattr(checkpoint, 'cut_safe', spy)
    homes = Homes()
    assert checkpoint._clip(['a line'], homes) == ('a line',)
    assert len(seen) == 1 and seen[0] is homes


def test_clip_of_nothing_is_an_empty_tuple_and_every_item_is_str_ed():
    """checkpoint.py:57 — the result is always a tuple (the Checkpoint entity
    stores tuples), an empty input included; a non-text item is str()-ed, so a
    number, a tuple or None reaches the prompt as its text."""
    homes = Homes()
    assert checkpoint._clip([], homes) == ()
    assert type(checkpoint._clip([], homes)) is tuple
    assert checkpoint._clip([7, ('a', 1), None], homes) == ('7', "('a', 1)", 'None')

