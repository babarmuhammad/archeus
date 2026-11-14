"""T-1432 - authorization.py 182-270 (_tasks, intact, bind, plan_items, plan_hash,
task_hash, judge_start, plan_approval_state, current, _slim), round-15 gap probes.

Selected branches, in rank order:
  1 _tasks filters by plan_id                         (authorization.py:183)
  2 plan_items sorts tasks by key                     (201)
  3 empty items_of and no tasks contribute nothing    (201-202)
  4 several classes per task keep their order         (201)
  5 _slim replaces matched by rule ids, no mutation   (266-270)
  6 _slim with no or None matched records []          (270)
  7 plan_hash ignores the order of the task rows      (206)
  8 intact short-circuits on an empty digest          (186-189)
  9 current: no package recorded, or package row gone (255-258)
 10 current: floor equal to as_of_seq does not trip   (259-260)
"""

from types import SimpleNamespace

import pytest

from archeus.core.application import authorization as A
from archeus.core.domain import actions, entities
from archeus.core.domain.actions import Action
from archeus.core.planning import planner, validate
from archeus.infra.db import rows
from archeus.infra.eventlog import outbox

PLAN = SimpleNamespace(id='p1', mission_id='m1', plan_version=1, digest='dg',
                       context_package_id=None)
MISSION = object()
ACT_A = Action(action_class='deploy', target='svc:a')
ACT_B = Action(action_class='read', target='svc:b')
ACT_C = Action(action_class='destructive', target='svc:c')


def _task(key, plan_id='p1'):
    return SimpleNamespace(id='t_' + key, key=key, plan_id=plan_id)


def _where(monkeypatch, tasks):
    seen = []

    def where(conn, cls, **kw):
        seen.append((cls, kw))
        return [SimpleNamespace(entity=t) for t in tasks if t.plan_id == kw['plan_id']]

    monkeypatch.setattr(rows, 'where', where)
    return seen


def _items(monkeypatch, by_key):
    monkeypatch.setattr(A, 'items_of', lambda t: by_key.get(t.key, []))


def test_tasks_returns_only_the_rows_of_the_plan_asked_for(monkeypatch):
    """authorization.py:183 - the plan_id filter is the query: removed, the
    tasks of every plan would feed plan_items and the plan's digest."""
    tasks = [_task('a'), _task('b', plan_id='p2')]
    seen = _where(monkeypatch, tasks)
    got = A._tasks(object(), PLAN)
    assert [t.key for t in got] == ['a']
    assert seen == [(entities.Task, {'plan_id': 'p1'})]


def test_plan_items_orders_tasks_by_key_not_by_insertion(monkeypatch):
    """authorization.py:200-202 - sorted by key before the concatenation:
    inserted as b then a, the a items still come first. Removed, plan_hash
    of the same plan would depend on the insertion order."""
    _where(monkeypatch, [_task('b'), _task('a')])
    _items(monkeypatch, {'a': [('deploy', None, ACT_A)], 'b': [('read', None, ACT_B)]})
    assert A.plan_items(object(), PLAN) == [
        actions.item('a', ACT_A), actions.item('b', ACT_B)]


def test_plan_items_is_empty_for_no_tasks_and_for_a_task_with_no_items(monkeypatch):
    """authorization.py:201-202 - a task whose items_of yields nothing adds no
    entry and does not raise; a plan with no task rows returns []. Removed,
    an empty task would add a None item the hash would then cover."""
    _where(monkeypatch, [])
    assert A.plan_items(object(), PLAN) == []
    _where(monkeypatch, [_task('a'), _task('b')])
    _items(monkeypatch, {'a': []})
    assert A.plan_items(object(), PLAN) == []


def test_plan_items_keeps_the_classes_of_one_task_in_their_order(monkeypatch):
    """authorization.py:201 - the inner loop over items_of(t): the classes of
    one task stay in the order items_of gave them, not re-sorted by class.
    Removed (sorted by class), a read before a destructive would swap."""
    _where(monkeypatch, [_task('a')])
    _items(monkeypatch, {'a': [('destructive', None, ACT_C), ('deploy', None, ACT_A)]})
    assert A.plan_items(object(), PLAN) == [
        actions.item('a', ACT_C), actions.item('a', ACT_A)]


def test_slim_records_rule_ids_and_leaves_the_judged_item_alone():
    """authorization.py:266-270 - matched is replaced by the rule ids in the
    copy; the item the policy returned keeps its full rule dicts. Removed,
    the rule contents would leak into the decision row twice or the judged
    item would be altered after it was recorded."""
    item = {'task': 't', 'decision': 'DENY', 'matched': [{'id': 'R1', 'x': 1}, {'id': 'R2'}]}
    out = A._slim(item)
    assert out == {'task': 't', 'decision': 'DENY', 'matched': ['R1', 'R2']}
    assert item['matched'] == [{'id': 'R1', 'x': 1}, {'id': 'R2'}]


def test_slim_records_an_empty_match_list_when_matched_is_absent_or_none():
    """authorization.py:270 - the `or ()` arm: an item with no matched key, or
    with matched None, records matched []. Removed, both raise TypeError in
    the recorder, so an ALLOW with no rules could not be written."""
    assert A._slim({'decision': 'ALLOW'}) == {'decision': 'ALLOW', 'matched': []}
    assert A._slim({'matched': None}) == {'matched': []}


def test_plan_hash_does_not_depend_on_the_order_of_the_task_rows(monkeypatch):
    """authorization.py:206 - determinism rides on the sort in plan_items. With
    the same two tasks listed in either order, plan_hash is the same. Removed
    (the sort), the hash of a stored plan would change with row order."""
    tasks = [_task('a'), _task('b')]
    _items(monkeypatch, {'a': [('deploy', None, ACT_A)], 'b': [('read', None, ACT_B)]})
    _where(monkeypatch, tasks)
    first = A.plan_hash(object(), PLAN)
    _where(monkeypatch, list(reversed(tasks)))
    assert A.plan_hash(object(), PLAN) == first
    assert len(A.plan_items(object(), PLAN)) == 2


def test_intact_is_false_for_an_empty_digest_without_recomputing(monkeypatch):
    """authorization.py:186-189 - `bool(plan.digest) and ...`: an empty or None
    digest answers False before validate.digest or the task rows are read.
    Removed, the recompute runs on a plan with no digest to compare against."""
    calls = []
    monkeypatch.setattr(validate, 'digest', lambda *a: calls.append(a) or 'dg')

    def no_rows(*a, **k):
        raise AssertionError('task rows read for a plan with no digest')

    monkeypatch.setattr(rows, 'where', no_rows)
    assert A.intact(object(), SimpleNamespace(digest='')) is False
    assert A.intact(object(), SimpleNamespace(digest=None)) is False
    assert calls == []


def test_current_is_true_without_a_package_and_asks_the_planner_when_the_package_is_gone(
        monkeypatch):
    """authorization.py:255-258 - no context_package_id answers (True, the
    'planned without' reason) with no planner call; a package id whose row is
    gone is not floor-checked and goes straight to planner.currency. Removed,
    a plan with no package would be judged stale, or a missing row would
    raise in the floor comparison."""
    asked = []
    monkeypatch.setattr(planner, 'currency',
                        lambda conn, m, pid: asked.append(pid) or (True, 'cur'))
    monkeypatch.setattr(rows, 'get', lambda conn, cls, eid: None)
    assert A.current(object(), MISSION, SimpleNamespace(context_package_id=None)) == (
        True, 'planned without a recorded context package')
    assert asked == []
    assert A.current(object(), MISSION, SimpleNamespace(context_package_id=7)) == (True, 'cur')
    assert asked == [7]


@pytest.mark.parametrize('floor, tripped', [(6, True), (5, False)])
def test_current_trips_only_when_the_log_floor_passes_the_package(monkeypatch, floor, tripped):
    """authorization.py:259-260 - `outbox.floor > as_of_seq`: a floor one past
    the package is stale (the log no longer reaches back); a floor equal to it
    is not. Removed or turned to >=, the boundary answer is wrong either way."""
    asked = []
    monkeypatch.setattr(planner, 'currency',
                        lambda conn, m, pid: asked.append(pid) or (True, 'cur'))
    monkeypatch.setattr(rows, 'get', lambda conn, cls, eid: SimpleNamespace(
        entity=SimpleNamespace(as_of_seq=5)))
    monkeypatch.setattr(outbox, 'floor', lambda conn: floor)
    got = A.current(object(), MISSION, SimpleNamespace(context_package_id=7))
    if tripped:
        assert got == (False, 'the event log no longer reaches back to its context package')
        assert asked == []
    else:
        assert got == (True, 'cur') and asked == [7]
