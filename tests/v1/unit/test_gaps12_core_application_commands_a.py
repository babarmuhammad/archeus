"""T-1433 - commands.py 255-345 (HOLDS, PLAN_DECISIONS, _record_hold, _result,
Missions.snapshot, Missions._fire up to the `fields` closure), round-15 gap probes.

Selected branches, in rank order:
  1 _record_hold: entering a hold from EXECUTING records held_from only  (commands.py:266-267)
  2 _record_hold: leaving RESUMED to a non-hold clears held_from to None (268-269)
  3 _record_hold: leaving PAUSED with a batch clears pause_batch_id      (270-271)
  4 _record_hold: an edge that changes nothing returns None, not {}      (272)
  5 _record_hold: PAUSED to BLOCKED records both held_from and the clear (266-271)
  6 fields: hold keys override a same-named extra key                   (340-341)
  7 fields: decided_plan_version only for PLAN_DECISIONS triggers       (342-343)
  8 fields: decided_plan_version is judged[-1].plan_version, None kept  (343)
  9 facts_of: a callable given is called with the row, a value is not  (336-338)
 10 facts_of default: snapshot gets declared=True and the actor         (333)

Probes 6-10 reach `fields` and `facts_of` through a fake lifecycle.fire that
captures the closures _fire builds, so no database is touched.
"""

from types import SimpleNamespace

import pytest

from archeus.core.application import authorization, commands, lifecycle


def _row(state, batch=None):
    return SimpleNamespace(entity=SimpleNamespace(state=state, pause_batch_id=batch))


def test_entering_a_hold_from_executing_records_only_where_it_came_from():
    """commands.py:266-267 - `to in HOLDS` sets held_from to the row's state; no
    batch was set so no clear is added. Removed, a hold would not remember
    where it came from and Resume could only guess."""
    assert commands._record_hold(_row('EXECUTING'), 'BLOCKED') == {'held_from': 'EXECUTING'}
    assert commands._record_hold(_row('EXECUTING'), 'PAUSED') == {'held_from': 'EXECUTING'}


def test_leaving_resumed_for_a_non_hold_clears_held_from_to_none():
    """commands.py:268-269 - the cleared value is None under the key, not a
    missing key. Removed, a stale held_from would survive the resume."""
    assert commands._record_hold(_row('RESUMED'), 'EXECUTING') == {'held_from': None}


def test_leaving_paused_by_any_edge_forgets_its_batch_and_only_when_it_has_one():
    """commands.py:270-271 - a PAUSED row with a batch returns pause_batch_id None
    on any exit edge; with no batch there is nothing to clear and the result is
    None. Removed, Resume all could resume a batch the row no longer holds."""
    assert commands._record_hold(_row('PAUSED', 'b1'), 'CANCELLED') == {'pause_batch_id': None}
    assert commands._record_hold(_row('PAUSED'), 'CANCELLED') is None


def test_an_edge_that_changes_no_hold_returns_none_not_an_empty_dict():
    """commands.py:272 - `out or None`: a transition that neither enters a hold
    nor leaves RESUMED or PAUSED writes nothing. Removed, an empty dict would be
    merged into every move and make the write path think there are fields."""
    assert commands._record_hold(_row('BLOCKED'), 'RESUMED') is None
    assert commands._record_hold(_row('EXECUTING'), 'SUCCEEDED') is None


def test_paused_to_blocked_records_the_origin_and_the_batch_clear_together():
    """commands.py:266-271 - both arms apply on one edge: PAUSED with a batch
    moving to a hold sets held_from PAUSED and clears the batch. Removed, one
    arm alone leaves the row with a hold origin of PAUSED and a live batch."""
    assert commands._record_hold(_row('PAUSED', 'b1'), 'BLOCKED') == {
        'held_from': 'PAUSED', 'pause_batch_id': None}


class _Capture:
    """Stands in for lifecycle.fire and keeps the closures _fire builds. The
    closures are called by the test, so each call is the test's own."""

    def __init__(self, monkeypatch):
        self.kw = {}

        def fire(tx, cls, entity_id, trigger, **kw):
            self.kw = kw
            return (SimpleNamespace(entity=SimpleNamespace(state='EXECUTING')), None)

        monkeypatch.setattr(lifecycle, 'fire', fire)
        monkeypatch.setattr(authorization, 'record_plan_decision', lambda *a, **k: None)


def _fire(monkeypatch, trigger, *, facts=None, extra=None):
    cap = _Capture(monkeypatch)
    commands.Missions(policy=object())._fire(
        object(), 'm1', trigger, actor=object(), reason='r', facts=facts, extra=extra)
    return cap


def test_fields_lets_the_hold_keys_win_over_an_extra_of_the_same_name(monkeypatch):
    """commands.py:340-341 - dict(extra, **hold): the hold value replaces the
    extra one; an extra key with no collision survives. Removed or reversed,
    a caller could pin a held_from that does not match the row."""
    cap = _fire(monkeypatch, 'block', extra={'held_from': 'X', 'keep': 1})
    assert cap.kw['fields'](_row('EXECUTING'), 'BLOCKED') == {'held_from': 'EXECUTING', 'keep': 1}


@pytest.mark.parametrize('trigger, recorded', [
    ('plan_auto_approved', True), ('plan_needs_approval', True), ('start', False)])
def test_decided_plan_version_is_written_only_for_plan_decision_triggers(
        monkeypatch, trigger, recorded):
    """commands.py:342-343 - `trigger in PLAN_DECISIONS` gates the key. Removed,
    every move would stamp a decided version, including moves that were no
    plan decision at all."""
    cap = _fire(monkeypatch, trigger, facts=lambda row: SimpleNamespace(plan_version=3))
    cap.kw['facts'](_row('EXECUTING'))
    got = cap.kw['fields'](_row('EXECUTING'), 'EXECUTING')
    if recorded:
        assert got == {'decided_plan_version': 3}
    else:
        assert got is None


def test_decided_plan_version_is_the_judged_facts_version_even_when_none(monkeypatch):
    """commands.py:343 - judged[-1].plan_version, the facts the guard just judged,
    not the row. A None version is written as None, not dropped. Removed, the
    row's older plan version would be recorded as the decided one."""
    cap = _fire(monkeypatch, 'plan_auto_approved',
                facts=lambda row: SimpleNamespace(plan_version=None))
    cap.kw['facts'](_row('EXECUTING'))
    assert cap.kw['fields'](_row('EXECUTING'), 'EXECUTING') == {'decided_plan_version': None}


def test_a_callable_given_is_called_with_the_row_and_a_value_is_used_as_is(monkeypatch):
    """commands.py:336-338 - callable(given) calls it with the row and stores the
    result; a non-callable given is returned unchanged. Removed, a callable
    would be stored as the facts object and a value would be called and fail."""
    seen = []
    sentinel = object()
    row = _row('EXECUTING')
    cap = _fire(monkeypatch, 'start', facts=lambda r: seen.append(r) or sentinel)
    assert cap.kw['facts'](row) is sentinel and seen == [row]
    value = object()
    cap = _fire(monkeypatch, 'start', facts=value)
    assert cap.kw['facts'](row) is value


def test_default_facts_snapshot_the_row_as_a_declared_request(monkeypatch):
    """commands.py:333 - with no facts given, the closure calls
    self.snapshot(tx, row, actor, declared=True). Removed or declared=False,
    unrecoverable would read declared_by as None for an explicit request."""
    recorded = []
    monkeypatch.setattr(commands.Missions, 'snapshot',
                        lambda self, tx, row, actor=None, declared=False:
                        recorded.append((tx, row, actor, declared)) or 'snap')
    cap = _Capture(monkeypatch)
    actor, tx = object(), object()
    commands.Missions(policy=object())._fire(tx, 'm1', 'start', actor=actor, reason='r')
    row = _row('EXECUTING')
    assert cap.kw['facts'](row) == 'snap'
    assert recorded == [(tx, row, actor, True)]
