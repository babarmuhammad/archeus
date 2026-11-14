"""T-1392: the highest-risk uncovered branches of `archeus/core/application/graph.py`, lines 261-330
(`_relations`, the node section `_load`, `node_of`, `states_field`, `endpoint`, `_order_key`,
`_desc`, `_key`).

Selected branches, ranked fail-closed first, then boundaries, then error paths:

 1. graph.py:261-263  _relations: a node that is neither end of a relation has none.
 2. graph.py:261-263  _relations: the outgoing leg comes first, each leg matches kind AND id.
 3. graph.py:261-263  _relations: an unknown kind matches no rows and raises nothing.
 4. graph.py:268-271  _load: an unknown kind is None and reads no row.
 5. graph.py:278-280  node_of: a kind with no machine gets no 'machine', no 'state', and
                      states_field is never called.
 6. graph.py:292-293  states_field: the first field of the entity's _STATE, not the last.
 7. graph.py:301-304  _order_key: a lower hop beats a settled state at a higher hop.
 8. graph.py:301-304  _order_key: a lower kind rank beats a settled state at the same hop.
 9. graph.py:307-313  _desc and _order_key: equal times fall to the ascending id.
10. graph.py:296-298  endpoint: a short id is kept whole in the label.

The T-709 file (tests/v1/unit/test_gaps_core_application_graph.py) and tests/v1/unit/test_pins_core_application_graph.py
already cover the endpoint of a missing row, the route decision eliminated count, the knowledge item
type and the settled order of a live row against a settled one; those probes are not repeated.

Rejected premise: relation whose src and dst are the same node appears twice in `_relations`. The caller
world_graph (graph.py:344, 370) keys every edge by `_edge_key` in the `edges` dict (graph.py:345-348,
372), so the duplicate never reaches the view. Not a defect; no xfail kept.

Seams: a FakeRows object replaces the module's `rows`, recording each `where` and `get` call; fake
Relation rows are SimpleNamespace records. No database, no filesystem, no environment value.
"""

from types import SimpleNamespace

import pytest

from archeus.core.application import graph as G
from archeus.core.domain import entities as E, states


class FakeRows:
    def __init__(self, relations=(), calls=None):
        self.relations = list(relations)
        self.calls = [] if calls is None else calls

    def where(self, conn, cls, **filters):
        self.calls.append((cls, filters))
        return [SimpleNamespace(entity=r) for r in self.relations
                if all(getattr(r, k) == v for k, v in filters.items())]

    def get(self, conn, cls, id_):
        self.calls.append((cls, id_))
        return None


def rel(src_kind, src_id, dst_kind, dst_id, rel_name='blocks'):
    return SimpleNamespace(src_kind=src_kind, src_id=src_id, dst_kind=dst_kind, dst_id=dst_id,
                           rel=rel_name, confidence_tier=None, valid_until=None)


def test_a_node_that_is_neither_end_of_a_relation_has_none(monkeypatch):
    monkeypatch.setattr(G, 'rows', FakeRows([rel('task', 't1', 'mission', 'm1')]))
    assert G._relations(None, 'task', 't2') == []
    assert G._relations(None, 'mission', 'm2') == []


def test_outgoing_relations_come_before_incoming_and_each_leg_matches_kind_and_id(monkeypatch):
    out_rel = rel('task', 't1', 'mission', 'm1')
    in_rel = rel('mission', 'm1', 'task', 't1', 'owns')
    same_id_other_kind = rel('plan', 't1', 'mission', 'm1', 'other')
    same_kind_other_id = rel('task', 't9', 'mission', 'm1', 'elsewhere')
    calls = []
    monkeypatch.setattr(G, 'rows', FakeRows(
        [in_rel, same_id_other_kind, out_rel, same_kind_other_id], calls))
    got = G._relations(None, 'task', 't1')
    assert [id(x) for x in got] == [id(out_rel), id(in_rel)]
    assert calls == [(E.Relation, {'src_kind': 'task', 'src_id': 't1'}),
                     (E.Relation, {'dst_kind': 'task', 'dst_id': 't1'})]


def test_an_unknown_kind_matches_no_relation_and_raises_nothing(monkeypatch):
    monkeypatch.setattr(G, 'rows', FakeRows([rel('task', 't1', 'mission', 'm1')]))
    assert G._relations(None, 'person', 't1') == []


def test_an_unknown_kind_is_never_read(monkeypatch):
    def no_read(*a):
        pytest.fail('a kind Core does not show was read')
    monkeypatch.setattr(G, 'rows', SimpleNamespace(get=no_read))
    assert G._load(None, 'person', 'p1') is None


def test_a_kind_without_a_machine_has_no_machine_or_state_and_asks_for_no_state_field(monkeypatch):
    def no_field(kind):
        pytest.fail('states_field asked for a kind with no machine')
    monkeypatch.setattr(G, 'states_field', no_field)
    row = SimpleNamespace(entity=SimpleNamespace(id='p1', name='Project One'))
    n = G.node_of('project', row)
    assert 'machine' not in n and 'state' not in n
    assert n == {'kind': 'project', 'id': 'p1', 'label': 'Project One', 'parent': None}


def test_the_state_field_is_the_first_declared_state_of_the_kind(monkeypatch):
    class Fake:
        _STATE = ('status', 'lifecycle')
    monkeypatch.setitem(G.KINDS, 'fake_kind', (Fake, 'fake_machine'))
    assert G.states_field('fake_kind') == 'status'


def test_a_lower_hop_beats_a_settled_row_at_a_higher_hop(monkeypatch):
    class Fake:
        _STATE = ('status',)
    monkeypatch.setitem(G.KINDS, 'fake_kind', (Fake, 'fake_machine'))
    monkeypatch.setitem(G.RANK, 'fake_kind', 0)
    monkeypatch.setitem(G.TERMINAL, 'fake_kind', frozenset({'DONE'}))
    settled = SimpleNamespace(entity=SimpleNamespace(id='a', status='DONE'), updated_at=None)
    open_row = SimpleNamespace(entity=SimpleNamespace(id='b', status='OPEN'), updated_at=None)
    near_settled = G._order_key('fake_kind', settled, 1)
    far_open = G._order_key('fake_kind', open_row, 2)
    assert near_settled < far_open
    assert G._order_key('fake_kind', open_row, 1) < near_settled


def test_a_lower_kind_rank_beats_a_settled_row_at_the_same_hop():
    assert G.TERMINAL['mission'], 'the mission machine has terminal states'
    open_state = next(s for s in states.states('mission') if s not in G.TERMINAL['mission'])
    settled_state = next(iter(G.TERMINAL['mission']))
    settled_execution = SimpleNamespace(entity=SimpleNamespace(id='x'), updated_at=None)
    open_mission = SimpleNamespace(
        entity=SimpleNamespace(id='y', **{E.Mission._STATE[0]: open_state}), updated_at=None)
    settled_mission = SimpleNamespace(
        entity=SimpleNamespace(id='z', **{E.Mission._STATE[0]: settled_state}), updated_at=None)
    assert G.RANK['mission'] < G.RANK['execution']
    assert G._order_key('mission', open_mission, 1) < G._order_key(
        'execution', settled_execution, 1)
    assert G._order_key('mission', settled_mission, 1)[2] is True


def test_equal_times_fall_to_the_ascending_id_and_a_missing_time_is_empty():
    b = SimpleNamespace(entity=SimpleNamespace(id='b'), updated_at='2026-11-14T10:00:00Z')
    a = SimpleNamespace(entity=SimpleNamespace(id='a'), updated_at='2026-11-14T10:00:00Z')
    ordered = sorted([b, a], key=lambda r: G._order_key('project', r, 1))
    assert [r.entity.id for r in ordered] == ['a', 'b']
    assert G._desc(None) == G._desc('') == ()


def test_an_endpoint_keeps_a_short_id_whole_and_truncates_a_long_one():
    short = G.endpoint({'kind': 'mission', 'id': 'm1'})
    assert short['label'] == 'mission m1'
    assert G._key({'kind': 'mission', 'id': 'm1', 'extra': 1}) == ('mission', 'm1')
    long = G.endpoint({'kind': 'mission', 'id': 'abcdefghijklmnop'})
    assert long['label'] == 'mission abcdefghijkl'
