"""T-1391: the highest-risk uncovered branches of `archeus/core/application/automations.py`
lines 334-400 (`_armed_window`, `_guard`, `_view`, `_lazy`, `_rationale`, `_run_view`), as tests.

Selected branches, denial and fail-closed first:
- `_guard` fires `loop_guard_tripped` only when `matcher.should_suspend` says so; with False no
  event is fired and the run id comes back unchanged.
- A second trip on a SUSPENDED automation is refused by the machine (`loop_guard_tripped` is an
  edge only from ENABLED), and `candidates` lists only ENABLED automations, so `_guard` cannot
  reach that trip. The premise that it fires twice is not a defect.
- `_armed_window` excludes a run whose triggering seq equals `armed_seq` (strict `>`), and includes
  one created exactly at `since` (`>=`), excluding one a millisecond before it.
- `_view` shows no next time for a disabled or suspended schedule; `waiting` is computed only for
  an ENABLED schedule (trigger kind `schedule`); a non-schedule trigger has `waiting` None; created
  and updated times come from the row; the `waiting` key is present for disabled automations.
- `_lazy` builds the homes at most once across repeated `get()` calls and never when `get` is not
  called.
- `_rationale` returns a falsy rationale unchanged without building homes; a non-empty rationale is
  passed to `system_value` with one `('where', key, 'test')` authored entry per key.
- `_run_view` takes its rationale from the projection and its version, created and updated times
  from the row, overriding a `version` key the entity dict carries.

Not selected: `_guard` second-trip idempotency as a defect (see above), and the schedule trigger
branches already asserted in tests/v1/unit/test_gaps_core_automation_worker.py.

Seam: a fake transaction with a fixed `now` and a `where` that returns the rows it was given; the
module's `_homes`, `_waiting`, `system_value` and `lifecycle.fire` are monkeypatched; `matcher` is
the real module (WINDOW_S 3600, SUSPEND_AFTER 3) except where a test replaces `should_suspend`.
No database, no clock, no network.

Each test names the source branch whose removal or inversion it catches.
"""

import pytest

from archeus.core.application import automations as A
from archeus.core.application import lifecycle
from archeus.core.automation import matcher
from archeus.core.domain import entities, ids
from archeus.infra.db import rows

NOW = '2026-11-14T12:00:00.000Z'
SINCE = '2026-11-14T11:00:00.000Z'


class FakeTx:
    def __init__(self, stored=()):
        self.now = NOW
        self.stored = list(stored)
        self.calls = []

    def where(self, cls, **eq):
        self.calls.append((cls, eq))
        return [r for r in self.stored if all(getattr(r.entity, k) == v for k, v in eq.items())]


def _automation(**kw):
    base = dict(id=ids.new_id('automation'), workspace_id=ids.new_id('workspace'), name='a',
                trigger={'kind': 'event', 'type': 'x.y'}, armed_seq=10, state='ENABLED')
    base.update(kw)
    return entities.Automation(**base)


def _run(a, seq, created_at, state='CLAIMED', reason_code=None):
    run = entities.AutomationRun(id=ids.new_id('automation_run'), automation_id=a.id,
                                 triggering_event_seq=seq, state=state, reason_code=reason_code)
    return rows.Row(run, 1, created_at, created_at, 'p', 'p')


def test_a_run_for_the_arming_event_itself_is_not_in_the_window_and_the_next_one_is():
    # automations.py _armed_window: `triggering_event_seq > a.armed_seq` is strict; a re-enabled
    # automation must not inherit the run it had for the event that armed it (seq 10), but does
    # count the run for the event after it (seq 11)
    a = _automation(armed_seq=10)
    tx = FakeTx([_run(a, 10, '2026-11-14T11:30:00.000Z'), _run(a, 11, '2026-11-14T11:30:00.000Z')])
    got = A._armed_window(tx, a)
    assert [r.triggering_event_seq for r in got] == [11]


def test_the_window_includes_a_run_created_at_since_and_excludes_one_just_before():
    # automations.py _armed_window: `created_at >= since` (inclusive); a run one millisecond
    # earlier is outside the hour, so removing the bound or inverting it changes this result
    a = _automation(armed_seq=0)
    at_since = _run(a, 1, SINCE)
    just_before = _run(a, 2, '2026-11-14T10:59:59.999Z')
    tx = FakeTx([at_since, just_before])
    got = A._armed_window(tx, a)
    assert [r.triggering_event_seq for r in got] == [1]
    assert tx.calls == [(entities.AutomationRun, {'automation_id': a.id})]


def test_the_loop_guard_fires_nothing_when_the_matcher_says_no(monkeypatch):
    # automations.py _guard: `if matcher.should_suspend(recent)` is the only way to fire; with
    # False no lifecycle event is recorded and the run id is returned unchanged
    a = _automation()
    fired = []
    monkeypatch.setattr(matcher, 'should_suspend', lambda recent: False)
    monkeypatch.setattr(lifecycle, 'fire', lambda *args, **kw: fired.append((args, kw)))
    assert A._guard(FakeTx(), 'actor', a, 'automation_run_1') == 'automation_run_1'
    assert fired == []


def test_the_loop_guard_fires_the_trip_once_when_the_matcher_says_yes(monkeypatch):
    # automations.py _guard: the trip fires `loop_guard_tripped` on this automation with the
    # matcher's count in the reason, and still returns the run id
    a = _automation()
    fired = []
    monkeypatch.setattr(matcher, 'should_suspend', lambda recent: True)
    monkeypatch.setattr(lifecycle, 'fire', lambda tx, cls, eid, trigger, **kw: fired.append(
        (cls, eid, trigger, kw['reason'])))
    assert A._guard(FakeTx(), 'actor', a, 'automation_run_2') == 'automation_run_2'
    assert fired == [(entities.Automation, a.id, 'loop_guard_tripped',
                      '%d escalated or rate-limited runs in the last hour: suspended until you '
                      're-enable it' % matcher.SUSPEND_AFTER)]


def test_a_second_trip_on_a_suspended_automation_is_refused_by_the_machine():
    # automations.py _guard + states.py: `loop_guard_tripped` is an edge only from ENABLED, so
    # a SUSPENDED automation cannot be tripped again by lifecycle.fire; and react only claims for
    # ENABLED automations (candidates), so the second trip is never reached in practice
    with pytest.raises(lifecycle.IllegalTrigger):
        lifecycle.resolve('automation', 'SUSPENDED', 'loop_guard_tripped')
    assert lifecycle.resolve('automation', 'ENABLED', 'loop_guard_tripped')[0] == 'SUSPENDED'


@pytest.mark.parametrize('state', ['DISABLED', 'SUSPENDED'], ids=['disabled', 'suspended'])
def test_a_schedule_that_is_not_enabled_shows_no_next_time_and_no_waiting(monkeypatch, state):
    # automations.py _view: `nxt = a.next_run_at if a.state == 'ENABLED' else None`; and the
    # `waiting` probe runs only when nxt is truthy, so neither is asked for a stale schedule
    monkeypatch.setattr(A, '_waiting', lambda *args: pytest.fail('asked about a held time'))
    a = _automation(state=state, trigger={'kind': 'schedule', 'every': '15m'},
                    next_run_at='2026-11-14T12:15:00.000Z')
    view = A._view(None, rows.Row(a, 4, 'c-row', 'u-row', 'p', 'p'))
    assert view['next_run_at'] is None and view['waiting'] is None


def test_an_enabled_non_schedule_trigger_is_never_waiting(monkeypatch):
    # automations.py _view: `and a.trigger.get('kind') == 'schedule'`: an enabled event trigger
    # with a stored time is not held, and `_waiting` is not consulted for it
    monkeypatch.setattr(A, '_waiting', lambda *args: pytest.fail('asked about an event trigger'))
    a = _automation(state='ENABLED', trigger={'kind': 'event', 'type': 'x.y'},
                    next_run_at='2026-11-14T12:15:00.000Z')
    view = A._view(None, rows.Row(a, 2, 'c', 'u', 'p', 'p'))
    assert view['waiting'] is None


def test_an_enabled_schedule_reports_the_reason_it_is_held(monkeypatch):
    # automations.py _view: the one case where `waiting` is computed, and its value is passed on
    monkeypatch.setattr(A, '_waiting', lambda conn, a, q: 'its project is archived')
    a = _automation(state='ENABLED', trigger={'kind': 'schedule', 'every': '15m'},
                    next_run_at='2026-11-14T12:15:00.000Z')
    view = A._view(None, rows.Row(a, 2, 'c', 'u', 'p', 'p'))
    assert view['waiting'] == 'its project is archived'
    assert view['next_run_at'] == '2026-11-14T12:15:00.000Z'


def test_the_view_takes_its_times_from_the_row_and_keeps_waiting_for_a_disabled_one():
    # automations.py _view: created_at and updated_at are the row's, not any the entity carries,
    # and the 'waiting' key is present (None) even when the automation is disabled
    a = _automation(state='DISABLED')
    view = A._view(None, rows.Row(a, 7, 'row-created', 'row-updated', 'p', 'p'))
    assert (view['created_at'], view['updated_at'], view['version']) == (
        'row-created', 'row-updated', 7)
    assert 'waiting' in view and view['waiting'] is None


def test_lazy_homes_are_built_once_across_repeated_gets(monkeypatch):
    # automations.py _lazy: `box` caches the first call, so a second get() reads the box
    built = []
    monkeypatch.setattr(A, '_homes', lambda conn, homes: built.append((conn, homes)) or 'H')
    get = A._lazy('conn', 'homes-arg')
    assert get() == 'H' and get() == 'H'
    assert built == [('conn', 'homes-arg')]


def test_lazy_homes_are_never_built_when_nothing_asks(monkeypatch):
    # automations.py _lazy: homes are computed inside get(), so an unused _lazy costs nothing
    built = []
    monkeypatch.setattr(A, '_homes', lambda conn, homes: built.append(1))
    A._lazy('conn', 'homes-arg')
    assert built == []


def test_a_falsy_rationale_is_returned_as_is_and_homes_are_not_built(monkeypatch):
    # automations.py _rationale: `if not rationale: return rationale` runs before homes(); an
    # empty rationale must not call system_value or build the homes
    monkeypatch.setattr(A, 'system_value', lambda *a, **k: pytest.fail('projected nothing'))

    def homes():
        pytest.fail('built homes for nothing')
    assert A._rationale(None, homes) is None
    assert A._rationale({}, homes) == {}


def test_a_rationale_is_projected_with_one_authored_test_per_where_key(monkeypatch):
    # automations.py _rationale: authored=(('where', k, 'test') ...) for each key of `where`, the
    # homes are the projection's input, and the projection's value is what comes back
    seen = {}

    def fake_system_value(rationale, shown, authored):
        seen.update(rationale=rationale, shown=shown, authored=authored)
        return 'PROJECTED'
    monkeypatch.setattr(A, 'system_value', fake_system_value)
    r = {'where': {'payload.title': 'x', 'payload.n': 1}, 'why': 'y'}
    got = A._rationale(r, lambda: {'H': 1})
    assert got == 'PROJECTED'
    assert seen['rationale'] is r and seen['shown'] == {'H': 1}
    assert seen['authored'] == (('where', 'payload.title', 'test'), ('where', 'payload.n', 'test'))


def test_the_run_view_takes_rationale_from_the_projection_and_version_from_the_row(monkeypatch):
    # automations.py _run_view: rationale replaces the entity's value, and the row's version
    # overrides a 'version' key the entity's own dict carries
    monkeypatch.setattr(A, 'system_value', lambda rationale, shown, authored: 'PROJ')
    entity = type('E', (), {'rationale': {'where': {'k': 1}},
                            'to_dict': lambda self: {'id': 'r1', 'rationale': 'stored',
                                                     'version': 99}})()
    row = rows.Row(entity, 3, 'row-c', 'row-u', 'p', 'p')
    view = A._run_view(row, lambda: {})
    assert view['rationale'] == 'PROJ'
    assert (view['version'], view['created_at'], view['updated_at']) == (3, 'row-c', 'row-u')
    assert view['id'] == 'r1'
