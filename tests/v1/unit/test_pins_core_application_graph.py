"""T-830: hand-mutant pins for `archeus/core/application/graph.py`.

Every test here names one condition in that module that no existing test would
notice inverted, removed or loosened (the read of the twenty most
security-relevant ones is in the card's report). Nothing is read from a
database, a filesystem or a process: `rows`, `outbox` and the artifact store's
`get` are answered from lists, and the rows are namespaces shaped like the
entities, as in `test_graph_parity.py`. Each test is quoted red against a
mutated copy of the source under `/work/scratch`.
"""

import dataclasses
import json
import re
from types import SimpleNamespace

import pytest

from archeus.core.application import graph as G
from archeus.core.domain import entities as E, ids
from archeus.core.domain.values import Ref
from archeus.infra.db import rows as rowcodec
from archeus.infra.db.writer import NotFound

WS = ids.GLOBAL_WORKSPACE
OTHER_WS = 'ws_not_the_workspace'
OLD = '2026-01-01T00:00:00Z'
NEW = '2026-06-01T00:00:00Z'
_ABSENT = object()


def _snake(name):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


_BY_NAME = {table: cls for cls, table in rowcodec.TABLES.items()}
CLS = {_snake(cls.__name__): cls for cls, table in rowcodec.TABLES.items()}
_SHA = iter(range(1, 10000))


def a_sha():
    """A payload sha no other test uses: `_payload` caches for the process."""
    return '%064x' % next(_SHA)


def ent(cls, **kw):
    """An entity-shaped namespace: every field None unless the test gives it.
    A field the entity does not have is a bug in the test, not a free column."""
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = set(kw) - names
    if unknown:
        raise KeyError('%s has no field %s' % (cls.__name__, sorted(unknown)))
    data = {f.name: None for f in dataclasses.fields(cls)}
    data.update(kw)
    return SimpleNamespace(**data)


def row_of(e, updated_at=OLD):
    return SimpleNamespace(entity=e, version=1, created_at=OLD, updated_at=updated_at,
                           created_by='prd_1', updated_by='prd_1')


class Result:
    def __init__(self, fetched):
        self.fetched = fetched

    def fetchone(self):
        return self.fetched[0] if self.fetched else None

    def fetchall(self):
        return self.fetched


class Db:
    """`rows.get`/`rows.where` and the four statements `_counts` runs, answered
    from lists. A filter of None matches nothing, as `col = NULL` does in SQL,
    and each WHERE clause is read back out of the SQL text, so a query that
    drops one really returns the other workspace's rows.
    """

    def __init__(self):
        self.by_kind = {}
        self.updated = {}
        self.count = {}
        self.sql = []
        self.reads = []

    def add(self, kind, updated_at=None, **kw):
        cls = CLS[kind]
        self.count[kind] = self.count.get(kind, 0) + 1
        kw.setdefault('id', '%s_%02d' % (kind, self.count[kind]))
        e = ent(cls, **kw)
        self.by_kind.setdefault(kind, []).append(e)
        self.updated[e.id] = updated_at or OLD
        return e

    def get(self, conn, cls, entity_id):
        if entity_id is None:
            return None                     # `WHERE id = ?` with no id answers with no row
        found = self._pick(cls, entity_id, None)
        return found[0] if found else None

    def where(self, conn, cls, **eq):
        return self._pick(cls, None, eq)

    def _pick(self, cls, entity_id, eq):
        kind = _snake(cls.__name__)
        names = {f.name for f in dataclasses.fields(cls)}
        unknown = set() if eq is None else set(eq) - names
        if unknown:
            raise LookupError('%s has no column %s' % (kind, sorted(unknown)))
        self.reads.append((kind, entity_id if entity_id is not None else tuple(sorted(eq))))
        out = []
        for e in self.by_kind.get(kind, ()):
            if entity_id is not None:
                if e.id != entity_id:
                    continue
            elif not all(v is not None and getattr(e, k, _ABSENT) == v for k, v in eq.items()):
                continue
            out.append(row_of(e, self.updated.get(e.id, OLD)))
        return out

    def execute(self, sql, params=()):
        s = ' '.join(sql.split())
        self.sql.append((s, tuple(params)))
        table = s.split(' FROM ')[1].split()[0]
        found = list(self.by_kind.get(_snake(_BY_NAME[table].__name__), ()))
        for column, value in zip(re.findall(r'(\w+) = \?', s), params):
            found = [e for e in found if getattr(e, column, _ABSENT) == value]
        if 'GROUP BY' in s:
            hist = {}
            for e in found:
                hist[e.state] = hist.get(e.state, 0) + 1
            return Result(sorted(hist.items()))
        return Result([(len(found),)])


@pytest.fixture
def db(monkeypatch):
    """The module's whole world: rows, the outbox head, and the `_MISSING` set
    of shas already logged, which lives for the life of the process."""
    d = Db()
    monkeypatch.setattr(G, 'rows', d)
    monkeypatch.setattr(G, 'outbox', SimpleNamespace(head=lambda conn: 42))
    before = set(G._MISSING)
    yield d
    G._MISSING.clear()
    G._MISSING.update(before)


def keys(g):
    return [(n['kind'], n['id']) for n in g['nodes']]


def real(g):
    return [(n['kind'], n['id']) for n in g['nodes'] if not n.get('endpoint')]


def fields_of(edges, field):
    return [(x['to']['kind'], x['to']['id']) for x in edges if x['field'] == field]


def assert_ends_are_drawn(g):
    """Nothing may point at a node the answer does not carry."""
    drawn = {(n['kind'], n['id']) for n in g['nodes']}
    for x in g['edges']:
        assert (x['from']['kind'], x['from']['id']) in drawn, x
        assert (x['to']['kind'], x['to']['id']) in drawn, x


# ── clean_label and _label: what a node says about itself ───────────────────

def test_a_label_of_nothing_is_empty_not_the_word_none(db):
    assert G.clean_label(None) == ''
    assert G.clean_label(0) == ''
    assert G.clean_label(False) == ''


def test_a_label_is_cut_at_the_cap_with_one_marker(db):
    keep = 'y' * G.LABEL_MAX
    assert G.clean_label(keep) == keep
    cut = G.clean_label('x' * (G.LABEL_MAX + 1))
    assert len(cut) == G.LABEL_MAX and cut.endswith('…')
    assert cut.count('…') == 1


@pytest.mark.parametrize('title, key, want', [
    (None, 'TK-9', 'TK-9'),
    ('', 'TK-9', 'TK-9'),
    ('Write it', 'TK-9', 'Write it'),
], ids=['title-none', 'title-empty', 'title-set'])
def test_a_task_labels_by_title_and_falls_back_to_its_key(title, key, want, db):
    assert G._label('task', ent(E.Task, id='tsk_1', title=title, key=key)) == want


@pytest.mark.parametrize('verdict, want', [
    (None, 'Review'),
    ('', 'Review'),
    ('ACCEPTED', 'Review — ACCEPTED'),
], ids=['no-verdict', 'empty-verdict', 'verdict'])
def test_a_review_names_its_verdict_only_when_it_has_one(verdict, want, db):
    assert G._label('review', ent(E.Review, id='rvw_1', verdict=verdict)) == want


@pytest.mark.parametrize('harness, model, want', [
    (None, None, 'Route decision'),
    ('', '', 'Route decision'),
    ('fake', None, 'fake'),
    (None, 'm-large', 'm-large'),
    ('fake', 'm-large', 'fake · m-large'),
], ids=['neither', 'empty', 'harness', 'model', 'both'])
def test_a_route_decision_label_never_reads_as_an_empty_join(harness, model, want, db):
    e = ent(E.RouteDecision, id='rdt_1', harness_id=harness, model=model)
    assert G._label('route_decision', e) == want


@pytest.mark.parametrize('path, want', [
    ('Z:/one/two/three/', 'three'),
    ('Z:\\one\\two\\three', 'three'),
    ('C:/one/two/three', 'three'),
    ('///', '///'),
], ids=['slash-trailing', 'backslash', 'plain', 'no-folder'])
def test_a_repository_labels_its_last_folder_on_either_separator(path, want, db):
    assert G._label('repository', ent(E.Repository, id='rep_1', path=path)) == want


def test_an_unknown_kind_labels_as_itself(db):
    assert G._label('person', SimpleNamespace()) == 'person'


def test_a_knowledge_item_node_carries_its_type_and_state(db):
    e = ent(E.KnowledgeItem, id='kn_1', title='Why it is so', type='DECISION',
            project_id='prj_1', state='CONFIRMED')
    n = G.node_of('knowledge_item', row_of(e))
    assert n['type'] == 'DECISION'                      # drawn as a diamond (A3, V7)
    assert n['machine'] == 'knowledge_item' and n['state'] == 'CONFIRMED'
    assert n['label'] == 'Why it is so'
    m = G.node_of('mission', row_of(ent(E.Mission, id='msn_1', title='M',
                                        state='EXECUTING')))
    assert 'type' not in m and m['machine'] == 'mission' and m['state'] == 'EXECUTING'
    r = G.node_of('repository', row_of(ent(E.Repository, id='rep_1', path='Z:/a/b',
                                           architecture_state='CONSISTENT')))
    assert r['machine'] == 'architecture' and r['state'] == 'CONSISTENT'   # not the kind


def test_an_endpoint_label_is_the_kind_and_the_head_of_its_id(db):
    e = G.endpoint({'kind': 'knowledge_item', 'id': 'kn_abcdefghijklmnop'})
    assert e['label'] == 'knowledge item kn_abcdefghi'      # the id cut to twelve
    assert e['endpoint'] is True and e['missing'] is False
    assert G.endpoint({'kind': 'task', 'id': 'tsk_1'})['label'] == 'task tsk_1'
    assert G.endpoint({'kind': 'task', 'id': 'tsk_1'}, missing=True)['missing'] is True


# ── _parent: what the renderer collapses a node into ────────────────────────

def test_a_parent_is_named_only_when_its_id_is_recorded(db):
    assert G._parent('session', ent(E.Session, id='ses_1')) is None
    assert G._parent('session', ent(E.Session, id='ses_1', project_id='prj_1')) == \
        {'kind': 'project', 'id': 'prj_1'}
    assert G._parent('session', ent(E.Session, id='ses_1', mission_id='msn_1',
                                   project_id='prj_1')) == {'kind': 'mission', 'id': 'msn_1'}
    assert G._parent('task', ent(E.Task, id='tsk_1', plan_id=None)) is None


def test_a_route_decision_parent_prefers_the_task_it_routed(db):
    assert G._parent('route_decision', ent(E.RouteDecision, id='rdt_1')) is None
    assert G._parent('route_decision', ent(E.RouteDecision, id='rdt_1', task_id='tsk_1',
                                          mission_id='msn_1')) == {'kind': 'task', 'id': 'tsk_1'}
    assert G._parent('route_decision', ent(E.RouteDecision, id='rdt_1',
                                          mission_id='msn_1')) == {'kind': 'mission',
                                                                   'id': 'msn_1'}


# ── held_edges: the columns a row holds ────────────────────────────────────

def test_an_edge_is_emitted_only_for_a_non_empty_string_id(db):
    me = {'kind': 'mission', 'id': 'msn_1'}
    out = []
    for value in (None, '', 17, Ref('mission', 'msn_2'), ['msn_2'], {'id': 'msn_2'}):
        G._edge(out, me, 'missions.project_id', 'project', value)
    assert out == []
    G._edge(out, me, 'missions.project_id', 'project', 'prj_1')
    assert [(x['to']['kind'], x['to']['id'], x['field']) for x in out] == \
        [('project', 'prj_1', 'missions.project_id')]


def test_a_mission_shows_only_its_last_pending_approval(db):
    m = db.add('mission', id='msn_1', title='M', workspace_id=WS, state='CREATED')
    db.add('approval', id='apr_1', mission_id='msn_1', state='APPROVED')
    db.add('approval', id='apr_2', mission_id='msn_1', state='PENDING')
    db.add('approval', id='apr_3', mission_id='msn_1', state='PENDING')
    db.add('approval', id='apr_4', mission_id='msn_1', state='REJECTED')   # the last row
    out = G.held_edges(db, 'mission', m)
    assert fields_of(out, 'approvals.mission_id') == [('approval', 'apr_3')]


@pytest.mark.parametrize('state, inactive', [
    ('APPROVED', False), ('SUPERSEDED', True), ('REJECTED', True), ('DRAFT', False),
], ids=['approved', 'superseded', 'rejected', 'open'])
def test_a_plan_edge_is_inactive_only_for_a_settled_plan(state, inactive, db):
    p = db.add('plan', id='pln_1', mission_id='msn_1', plan_version=1, state=state)
    (x,) = [e for e in G.held_edges(db, 'plan', p) if e['field'] == 'plans.mission_id']
    assert x['inactive'] is inactive


def test_a_dependency_is_resolved_by_key_inside_its_own_plan_only(db):
    db.add('task', id='tsk_1', plan_id='pln_1', key='shared', state='READY')
    dep = db.add('task', id='tsk_2', plan_id='pln_1', key='dep', depends_on=['shared'],
                 state='READY')
    db.add('task', id='tsk_3', plan_id='pln_2', key='shared', state='READY')
    out = G.held_edges(db, 'task', dep)
    assert fields_of(out, 'Task.depends_on') == [('task', 'tsk_1')]


@pytest.mark.parametrize('subject', [None, SimpleNamespace(kind=None, id='tsk_9')],
                         ids=['no-subject', 'kindless-subject'])
def test_a_verification_holds_a_subject_edge_only_when_it_names_one(subject, db):
    v = db.add('verification', id='ver_1', subject=subject, plan_id='pln_1',
               execution_id='exe_1', state='PASSED', verifier='code')
    out = G.held_edges(db, 'verification', v)
    assert fields_of(out, 'Verification.subject') == []
    assert fields_of(out, 'verifications.plan_id') == [('plan', 'pln_1')]
    assert fields_of(out, 'Verification.execution_id') == [('execution', 'exe_1')]
    v2 = db.add('verification', id='ver_2', subject=Ref('task', 'tsk_9'), plan_id='pln_1',
                state='PASSED', verifier='code')
    assert fields_of(G.held_edges(db, 'verification', v2),
                     'Verification.subject') == [('task', 'tsk_9')]


# ── _holders: who holds an edge towards a node ──────────────────────────────

def held_by(conn, kind, node_id, holder):
    return sorted((k, r.entity.id) for k, r in G._holders(conn, kind, node_id) if k == holder)


def test_only_the_task_that_records_the_dependency_is_a_holder(db):
    db.add('task', id='tsk_1', plan_id='pln_1', key='base', state='READY')
    db.add('task', id='tsk_2', plan_id='pln_1', key='one', depends_on=['base'], state='READY')
    db.add('task', id='tsk_3', plan_id='pln_1', key='two', depends_on=['other'], state='READY')
    db.add('task', id='tsk_4', plan_id='pln_1', key='three', depends_on=None, state='READY')
    assert held_by(db, 'task', 'tsk_1', 'task') == [('task', 'tsk_2')]


def test_an_execution_is_a_holder_only_through_its_recorded_hand_off(db):
    db.add('execution', id='exe_1', task_id='tsk_1', state='ENDED_HANDOFF')
    db.add('execution', id='exe_2', task_id='tsk_1', handoff_from='exe_1', state='RUNNING')
    db.add('execution', id='exe_3', task_id='tsk_1', handoff_from=None, state='RUNNING')
    db.add('execution', id='exe_4', task_id='tsk_1', handoff_from='exe_9', state='RUNNING')
    db.add('execution', id='exe_5', task_id='tsk_2', handoff_from='exe_1', state='RUNNING')
    assert held_by(db, 'execution', 'exe_1', 'execution') == [('execution', 'exe_2')]


def test_a_verification_holds_its_execution_only_inside_its_plan(db):
    db.add('execution', id='exe_1', task_id='tsk_1', plan_id='pln_1', state='RUNNING')
    db.add('verification', id='ver_1', plan_id='pln_1', execution_id='exe_1', state='PASSED')
    db.add('verification', id='ver_2', plan_id='pln_1', execution_id=None, state='PASSED')
    db.add('verification', id='ver_3', plan_id='pln_2', execution_id='exe_1', state='PASSED')
    db.add('verification', id='ver_4', plan_id=None, execution_id='exe_1', state='PASSED')
    assert held_by(db, 'execution', 'exe_1', 'verification') == [('verification', 'ver_1')]


def test_a_mission_is_a_holder_of_a_verification_about_it(db):
    db.add('plan', id='pln_1', mission_id='msn_1', plan_version=1, state='APPROVED')
    db.add('verification', id='ver_1', subject=Ref('mission', 'msn_1'), plan_id='pln_1',
           state='PASSED')
    db.add('verification', id='ver_2', subject=Ref('mission', 'msn_2'), plan_id='pln_1',
           state='PASSED')
    db.add('verification', id='ver_3', subject=Ref('task', 'tsk_1'), plan_id='pln_1',
           state='PASSED')
    db.add('verification', id='ver_4', subject=None, plan_id='pln_1', state='PASSED')
    # an id that looks like a mission id is not a mission subject
    db.add('verification', id='ver_5', subject=Ref('task', 'msn_1'), plan_id='pln_1',
           state='PASSED')
    assert held_by(db, 'mission', 'msn_1', 'verification') == [('verification', 'ver_1')]


def test_a_holder_read_survives_a_row_that_is_not_there(db):
    assert held_by(db, 'approval', 'apr_missing', 'mission') == []
    assert held_by(db, 'task', 'tsk_missing', 'task') == []
    assert held_by(db, 'execution', 'exe_missing', 'verification') == []
    assert G._holders(db, 'approval', 'apr_missing') == []


def test_an_approval_towards_a_mission_that_is_not_there_holds_no_edge(db):
    db.add('mission', id='msn_1', title='M', workspace_id=WS, state='CREATED')
    db.add('approval', id='apr_1', mission_id='msn_1', state='PENDING')
    db.add('approval', id='apr_2', mission_id='msn_gone', state='PENDING')
    assert held_by(db, 'approval', 'apr_1', 'mission') == [('mission', 'msn_1')]
    assert held_by(db, 'approval', 'apr_2', 'mission') == []


def test_a_kind_with_no_table_is_never_loaded(db):
    db.add('mission', id='msn_1', title='M', workspace_id=WS, state='CREATED')
    assert G._load(db, 'person', 'msn_1') is None
    assert G._load(db, 'mission', 'msn_missing') is None
    with pytest.raises(NotFound):
        G.world_graph(db, ('person', 'msn_1'), 1, 500)
    assert ('message', 'msn_1') not in db.reads       # no read was even attempted


def test_kinds_are_ranked_in_one_fixed_order(db):
    """Two rings' worth of neighbours at one hop: the cap and the node order
    rank them by kind, and only by kind (A6)."""
    db.add('mission', id='msn_1', title='M', workspace_id=WS, state='EXECUTING')
    db.add('task', id='tsk_1', plan_id='pln_a', mission_id='msn_1', key='t1', state='READY')
    db.add('plan', id='pln_a', mission_id='msn_1', plan_version=1, state='APPROVED',
           updated_at=NEW)                              # the newest row, and the first id
    db.add('execution', id='exe_b', task_id='tsk_1', mission_id='msn_1', attempt=1,
           state='RUNNING', updated_at=OLD)
    g = G.world_graph(db, ('mission', 'msn_1'), 1, 500)
    # the task has no edge back to the mission, so it is not a neighbour at all;
    # of what is, the execution ranks first by kind, not by its older timestamp
    assert [n['kind'] for n in g['nodes'] if not n.get('endpoint')] == \
        ['mission', 'execution', 'plan']


def test_a_route_decision_counts_only_candidates_that_say_when(db):
    e = ent(E.RouteDecision, id='rdt_1', harness_id='fake', model='m', effort='high',
            result='selected', account_id='acc_1', fallback_from=['rdt_0', 'rdt_a'],
            explanation='SECRET-EXPLANATION', requirements={'tier': 'large'},
            input_snapshot={'x': 1},
            candidates=['a bare string', 7, {'eliminated_at_step': 'health'},
                        {'eliminated_at_step': None}, {}, {'eliminated_at_step': 0}])
    n = G.node_of('route_decision', row_of(e))
    assert n['attrs']['eliminated'] == 1
    assert n['attrs']['harness_id'] == 'fake' and n['attrs']['model'] == 'm'
    assert 'machine' not in n and 'state' not in n      # it has no machine (A2)
    assert set(n['attrs']) == set(G.ROUTE_ATTRS) | {'eliminated'}
    assert n['attrs']['fallback_from'] == ['rdt_0', 'rdt_a']
    text = json.dumps(n)
    for secret in ('SECRET-EXPLANATION', 'requirements', 'input_snapshot', 'candidates'):
        assert secret not in text


def test_a_route_decision_shows_no_fallback_when_there_was_none(db):
    e = ent(E.RouteDecision, id='rdt_1', harness_id='fake', model='m', result='selected')
    assert G.node_of('route_decision', row_of(e))['attrs']['fallback_from'] == []


# ── world_graph: the rings, the cap, the order ──────────────────────────────

def two_executions(db):
    """One task, two open attempts whose ids and times order the opposite way."""
    db.add('task', id='tsk_1', plan_id='pln_1', key='t1', state='READY')
    db.add('execution', id='exe_aaa', task_id='tsk_1', attempt=1, state='RUNNING',
           updated_at=OLD)
    db.add('execution', id='exe_bbb', task_id='tsk_1', attempt=2, state='RUNNING',
           updated_at=NEW)


def test_the_newer_row_of_a_kind_comes_first(db):
    two_executions(db)
    g = G.world_graph(db, ('task', 'tsk_1'), 1, 500)
    assert [n['id'] for n in g['nodes'] if n['kind'] == 'execution'] == ['exe_bbb', 'exe_aaa']


def test_an_open_attempt_ranks_before_a_settled_one(db):
    db.add('task', id='tsk_1', plan_id='pln_1', key='t1', state='READY')
    db.add('execution', id='exe_aaa', task_id='tsk_1', attempt=1, state='ENDED_OK',
           updated_at=NEW)                                    # settled, and the newer row
    db.add('execution', id='exe_bbb', task_id='tsk_1', attempt=2, state='RUNNING',
           updated_at=OLD)
    g = G.world_graph(db, ('task', 'tsk_1'), 1, 500)
    assert [n['id'] for n in g['nodes'] if n['kind'] == 'execution'] == ['exe_bbb', 'exe_aaa']


def test_a_settled_state_is_one_with_no_way_out(db):
    assert G.TERMINAL['mission'] == frozenset({'COMPLETED', 'CANCELLED'})
    assert G.TERMINAL['plan'] == frozenset({'REJECTED', 'SUPERSEDED'})
    assert G.TERMINAL['route_decision'] == frozenset()      # it has no machine at all


def test_a_row_holding_no_edge_here_is_not_a_neighbour(db):
    db.add('mission', id='msn_1', title='M', workspace_id=WS, state='EXECUTING')
    db.add('task', id='tsk_1', plan_id='pln_1', mission_id='msn_1', key='t1', state='READY')
    db.add('execution', id='exe_1', task_id='tsk_1', mission_id=None, state='RUNNING')
    db.add('execution', id='exe_2', task_id='tsk_1', mission_id='msn_1', state='RUNNING')
    g = G.world_graph(db, ('mission', 'msn_1'), 1, 500)
    assert real(g) == [('mission', 'msn_1'), ('execution', 'exe_2')]
    assert_ends_are_drawn(g)


def test_the_last_ring_invents_no_node_beyond_the_depth(db):
    """A session found in the last ring holds an edge to its project: the depth
    holds, so neither the project nor an endpoint for it appears (A6)."""
    db.add('mission', id='msn_1', title='M', workspace_id=WS, state='EXECUTING')
    db.add('session', id='ses_1', mission_id='msn_1', project_id='prj_9', harness_id='fake')
    g = G.world_graph(db, ('mission', 'msn_1'), 1, 500)
    assert real(g) == [('mission', 'msn_1'), ('session', 'ses_1')]
    assert_ends_are_drawn(g)
    assert [x for x in g['edges'] if 'prj_9' in (x['from']['id'], x['to']['id'])] == []


def test_a_relation_is_an_edge_from_either_end(db):
    db.add('task', id='tsk_1', plan_id='pln_1', key='t1', state='READY')
    db.add('task', id='tsk_2', plan_id='pln_1', key='t2', state='READY')
    db.add('relation', id='rel_1', src_kind='task', src_id='tsk_2', dst_kind='task',
           dst_id='tsk_1', rel='reuses', confidence_tier=None,
           valid_until='2026-01-01T00:00:00Z')
    g = G.world_graph(db, ('task', 'tsk_1'), 1, 500)
    assert ('task', 'tsk_2') in real(g)
    assert [(x['from']['id'], x['to']['id'], x['rel'], x['tier'], x['inactive'])
            for x in g['edges'] if x['field'] == 'relations.reuses'] == \
        [('tsk_2', 'tsk_1', 'reuses', 'EXTRACTED', True)]
    assert_ends_are_drawn(g)


def test_a_limit_of_zero_loads_no_neighbour_but_counts_them(db):
    two_executions(db)
    g = G.world_graph(db, ('task', 'tsk_1'), 1, 0)
    assert real(g) == [('task', 'tsk_1')]
    assert g['truncated'] is True
    assert sum(h['count'] for h in g['hidden']) == 2
    assert_ends_are_drawn(g)


def test_a_row_that_is_not_there_is_an_endpoint_not_a_node(db):
    db.add('task', id='tsk_1', plan_id='pln_gone', key='t1', state='READY')
    g = G.world_graph(db, ('task', 'tsk_1'), 1, 500)
    assert real(g) == [('task', 'tsk_1')]
    assert [(n['kind'], n['id'], n['missing']) for n in g['nodes'] if n.get('endpoint')] == \
        [('plan', 'pln_gone', True)]
    assert [(x['from']['id'], x['to']['id'], x['field']) for x in g['edges']] == \
        [('tsk_1', 'pln_gone', 'tasks.plan_id')]


def test_an_edge_to_a_kind_with_no_table_is_an_endpoint_that_is_not_missing(db):
    """A mission born from a conversation names a message: it was never a row,
    so the endpoint says so (A2: an endpoint, never an invented node)."""
    db.add('mission', id='msn_1', title='M', workspace_id=WS, state='CREATED',
           origin='conversation', origin_ref='msg_1')
    db.add('message', id='msg_1', conversation_id='cnv_1', author='usr_1', text='hello')
    db.add('mission', id='msn_2', title='M2', workspace_id=WS, state='CREATED',
           origin='nothing-such', origin_ref='msg_2')
    g = G.world_graph(db, ('mission', 'msn_1'), 1, 500)
    assert real(g) == [('mission', 'msn_1')]        # the message row is never a node
    assert [(n['kind'], n['id'], n['missing']) for n in g['nodes'] if n.get('endpoint')] == \
        [('message', 'msg_1', False)]
    assert [(x['from']['id'], x['to']['id'], x['field']) for x in g['edges']] == \
        [('msn_1', 'msg_1', 'Mission.origin_ref')]
    plain = G.world_graph(db, ('mission', 'msn_2'), 1, 500)
    assert [n['id'] for n in plain['nodes'] if n.get('endpoint')] == []
    assert plain['edges'] == []
    assert ('message', 'msg_1') not in db.reads        # its table was never read


def test_the_depth_default_is_two_hops_for_everything_but_a_project(db):
    db.add('project', id='prj_1', name='Atlas', workspace_id=WS, state='ACTIVE')
    db.add('mission', id='msn_1', title='M', workspace_id=WS, project_id='prj_1',
           state='CREATED')
    db.add('plan', id='pln_1', mission_id='msn_1', plan_version=1, state='APPROVED')
    db.add('task', id='tsk_1', plan_id='pln_1', mission_id='msn_1', key='t1', state='READY')
    g = G.world_graph(db, ('mission', 'msn_1'), None, 500)
    assert g['depth'] == 2
    assert ('task', 'tsk_1') in keys(g)
    assert G.world_graph(db, ('project', 'prj_1'), None, 500)['depth'] == 1


def test_an_edge_key_is_its_field_and_both_ends(db):
    m = {'kind': 'mission', 'id': 'msn_1'}
    p = {'kind': 'plan', 'id': 'pln_1'}
    a = {'field': 'plans.mission_id', 'from': m, 'to': p}
    assert G._edge_key(a) == G._edge_key(dict(a, rel='x'))
    other = {'field': 'plans.supersedes_plan_id', 'from': m, 'to': p}
    assert G._edge_key(a) != G._edge_key(other)


def test_no_answer_carries_more_than_the_edge_cap(db):
    m = db.add('mission', id='msn_1', title='M', workspace_id=WS, state='CREATED')
    edges = {}
    for i in range(G.EDGE_MAX + 5):
        x = {'from': {'kind': 'mission', 'id': 'msn_1'}, 'to': {'kind': 'task',
             'id': 'tsk_%05d' % i}, 'field': 'executions.task_id', 'rel': None,
             'tier': None, 'inactive': False, 'structural': False}
        edges[G._edge_key(x)] = x
    g = G._assemble(42, {'kind': 'mission', 'id': 'msn_1'}, 1, 500,
                    {('mission', 'msn_1'): (0, row_of(m))}, {}, edges)
    assert len(g['edges']) == G.EDGE_MAX
    assert g['truncated'] is True


def test_the_hidden_count_groups_by_parent_and_kind(db):
    db.add('mission', id='msn_1', title='M', workspace_id=WS, state='CREATED')
    loaded = {('mission', 'msn_1'): (0, row_of(db.by_kind['mission'][0]))}
    cut = {}
    for tid, plan in (('tsk_1', 'pln_1'), ('tsk_2', 'pln_2'), ('tsk_3', 'pln_1')):
        t = db.add('task', id=tid, plan_id=plan, mission_id='msn_1', key=tid, state='READY')
        cut[('task', tid)] = row_of(t)
    g = G._assemble(42, {'kind': 'mission', 'id': 'msn_1'}, 2, 1, loaded, cut, {})
    assert g['hidden'] == [
        {'parent': {'kind': 'plan', 'id': 'pln_1'}, 'kind': 'task', 'count': 2},
        {'parent': {'kind': 'plan', 'id': 'pln_2'}, 'kind': 'task', 'count': 1}]
    assert g['truncated'] is True


# ── the world level and its counts ──────────────────────────────────────────

def test_projects_are_listed_active_first_then_by_name(db):
    db.add('project', id='prj_1', name='Zeta', workspace_id=WS, state='ACTIVE')
    db.add('project', id='prj_2', name='Alpha', workspace_id=WS, state='ACTIVE')
    db.add('project', id='prj_3', name='Aaa', workspace_id=WS, state='ARCHIVED')
    assert [n['id'] for n in G.world_graph(db, None, None, 500)['nodes']] == \
        ['prj_2', 'prj_1', 'prj_3']


def test_the_world_level_caps_its_projects_and_says_so(db):
    db.add('project', id='prj_1', name='Zeta', workspace_id=WS, state='ACTIVE')
    db.add('project', id='prj_2', name='Alpha', workspace_id=WS, state='ACTIVE')
    g = G.world_graph(db, None, None, 1)
    assert [n['id'] for n in g['nodes']] == ['prj_2']
    assert g['truncated'] is True
    assert g['hidden'] == [{'parent': {'kind': 'workspace', 'id': WS},
                            'kind': 'project', 'count': 1}]
    whole = G.world_graph(db, None, None, 500)
    assert whole['truncated'] is False and whole['hidden'] == []


def test_a_mission_count_adds_its_rows_not_its_states(db):
    db.add('project', id='prj_1', name='Atlas', workspace_id=WS, state='ACTIVE')
    for mid, state in (('msn_1', 'CREATED'), ('msn_2', 'CREATED'), ('msn_3', 'COMPLETED')):
        db.add('mission', id=mid, title=mid, workspace_id=WS, project_id='prj_1', state=state)
    c = G.world_graph(db, None, None, 500)['nodes'][0]['counts']
    assert c['missions'] == 3 and c['mission_states'] == {'CREATED': 2, 'COMPLETED': 1}


def test_the_rows_of_a_project_are_counted_where_they_are_kept(db):
    db.add('project', id='prj_1', name='Atlas', workspace_id=WS, state='ACTIVE')
    db.add('project', id='prj_2', name='Borealis', workspace_id=WS, state='ACTIVE')
    db.add('repository', id='rep_1', path='Z:/a', project_id='prj_1', workspace_id=WS,
           architecture_state='CONSISTENT')
    db.add('session', id='ses_1', harness_id='fake', project_id='prj_1', workspace_id=WS)
    db.add('knowledge_item', id='kn_1', title='k', project_id='prj_1', workspace_id=WS,
           type='NOTE', state='CONFIRMED')
    # another project's rows: counted for it, never for Atlas
    db.add('repository', id='rep_2', path='Z:/b', project_id='prj_2', workspace_id=WS,
           architecture_state='CONSISTENT')
    db.add('session', id='ses_2', harness_id='fake', project_id='prj_2', workspace_id=WS)
    db.add('knowledge_item', id='kn_2', title='k2', project_id='prj_2', workspace_id=WS,
           type='NOTE', state='CONFIRMED')
    c = G._counts(db, 'prj_1')
    assert c['repositories'] == 1 and c['sessions'] == 1 and c['knowledge_items'] == 1
    assert c['missions'] == 0 and c['mission_states'] == {}
    assert G._counts(db, 'prj_2')['repositories'] == 1


def test_the_world_level_lists_only_this_workspaces_projects(db):
    db.add('project', id='prj_1', name='Atlas', workspace_id=WS, state='ACTIVE')
    db.add('project', id='prj_2', name='Borealis', workspace_id=OTHER_WS, state='ACTIVE')
    assert [n['id'] for n in G.world_graph(db, None, None, 500)['nodes']] == ['prj_1']


def test_only_this_workspaces_mission_holds_a_project_edge(db):
    db.add('mission', id='msn_1', title='mine', workspace_id=WS, project_id='prj_1',
           state='CREATED')
    db.add('mission', id='msn_2', title='theirs', workspace_id=OTHER_WS, project_id='prj_1',
           state='CREATED')
    assert held_by(db, 'project', 'prj_1', 'mission') == [('mission', 'msn_1')]


def test_the_project_counts_never_leave_the_workspace(db):
    db.add('project', id='prj_1', name='Atlas', workspace_id=WS, state='ACTIVE')
    db.add('mission', id='msn_1', title='mine', workspace_id=WS, project_id='prj_1',
           state='CREATED')
    db.add('mission', id='msn_2', title='theirs', workspace_id=OTHER_WS, project_id='prj_1',
           state='CREATED')
    c = G.world_graph(db, None, None, 500)['nodes'][0]['counts']
    assert c['missions'] == 1 and c['mission_states'] == {'CREATED': 1}


# ── repository_graph: the stored payload, and nothing else ──────────────────

FILES = ['README.md', 'app/a.py', 'app/b.py', 'lib/x.py', 'tools/t.py']
EDGES = [['app/a.py', 'lib/x.py'], ['tools/t.py', 'lib/x.py'], ['app/a.py', 'app/b.py']]


def repo_rows(db, inspection=None, **repo_kw):
    """A repository row and, unless `inspection` is None, its last inspection."""
    repo_kw.setdefault('path', 'Z:/no/such/tree')
    repo_kw.setdefault('project_id', 'prj_1')
    repo_kw.setdefault('workspace_id', WS)
    repo_kw.setdefault('architecture_state', 'CONSISTENT')
    if inspection is not None:
        repo_kw.setdefault('last_inspection_id', 'ins_1')
        inspection.setdefault('repository_id', 'rep_1')
    rep = db.add('repository', id='rep_1', **repo_kw)
    if inspection is not None:
        db.add('repository_inspection', id='ins_1', **inspection)
    return rep


def reader(payload=None, raises=None, raw=None):
    """The artifact store's `get`: answers from one dict, with one text, or raises."""
    calls = []

    def read(sha):
        calls.append(sha)
        if raises is not None:
            raise raises
        return raw if raw is not None else json.dumps(
            payload if payload is not None else {})

    read.calls = calls
    return read


def graph_of(db, read, focus='', depth=1, limit=500, repository='rep_1'):
    return G.repository_graph(db, repository, read, focus, depth, limit)


def test_an_unknown_repository_is_not_found(db):
    with pytest.raises(NotFound):
        graph_of(db, reader())


@pytest.mark.parametrize('last', ['none', 'dangling'], ids=['never-inspected', 'gone-row'])
def test_a_repository_with_no_completed_inspection_is_said_not_inspected(db, last):
    repo_rows(db, last_inspection_id=None if last == 'none' else 'ins_gone')
    read = reader({'files': FILES, 'edges': EDGES})
    g = graph_of(db, read)
    assert g['available'] is False and g['reason'] == 'not_inspected'
    assert read.calls == []


@pytest.mark.parametrize('state', ['RUNNING', 'FAILED', 'STARTING'],
                         ids=['running', 'failed', 'starting'])
def test_an_inspection_that_did_not_finish_is_never_shown(db, state):
    repo_rows(db, inspection={'repository_id': 'rep_1', 'state': state,
                             'payload_sha256': 'a' * 64, 'revision': 'r1'})
    read = reader({'files': FILES, 'edges': EDGES})
    g = graph_of(db, read)
    assert g['available'] is False and g['reason'] == 'not_inspected'
    assert read.calls == []


@pytest.mark.parametrize('sha', ['', None], ids=['empty-sha', 'no-sha'])

def test_an_inspection_with_no_payload_is_said_not_inspected(db, sha):
    repo_rows(db, inspection={'repository_id': 'rep_1', 'state': 'COMPLETED',
                              'payload_sha256': sha, 'revision': 'r1'})
    read = reader({'files': FILES, 'edges': EDGES})
    assert graph_of(db, read)['reason'] == 'not_inspected'
    assert read.calls == []


@pytest.mark.parametrize('broken', [
    OSError('no such object'), KeyError('objects/aa'), ValueError('not a document'),
    LookupError('gone'), 'not a document at all',
], ids=['oserror', 'keyerror', 'valueerror', 'lookuperror', 'bad-json'])
def test_a_payload_that_cannot_be_read_is_said_missing(db, broken):
    sha = a_sha()
    repo_rows(db, inspection={'repository_id': 'rep_1', 'state': 'COMPLETED',
                              'payload_sha256': sha, 'revision': 'r1'})
    if isinstance(broken, str):
        read = reader(raw=broken)
    else:
        read = reader(raises=broken)
    g = graph_of(db, read)
    assert g['available'] is False and g['reason'] == 'payload_missing'


@pytest.mark.parametrize('arch, revision, stale', [
    ('CONSISTENT', 'r1', False),
    ('STALE', 'r1', True),
    ('CONSISTENT', 'r2', True),
    ('STALE', 'r2', True),
], ids=['fresh', 'stale-state', 'newer-revision', 'both'])
def test_stale_is_the_architecture_state_or_a_newer_revision(db, arch, revision, stale):
    repo_rows(db, architecture_state=arch, last_revision=revision,
              inspection={'repository_id': 'rep_1', 'state': 'COMPLETED',
                          'payload_sha256': 'a' * 64, 'revision': 'r1'})
    read = reader({'files': FILES, 'edges': EDGES})
    assert graph_of(db, read)['stale'] is stale


def test_a_focus_of_a_directory_is_read_without_its_slashes(db):
    repo_rows(db, inspection={'repository_id': 'rep_1', 'state': 'COMPLETED',
                              'payload_sha256': 'a' * 64, 'revision': 'r1'})
    read = reader({'files': FILES, 'edges': EDGES})
    assert [n['id'] for n in graph_of(db, read, '/app/')['nodes']] == \
        ['app/a.py', 'app/b.py', 'outside:lib']
    assert [n['id'] for n in graph_of(db, read, 'app')['nodes']] == \
        ['app/a.py', 'app/b.py', 'outside:lib']
    with pytest.raises(NotFound):
        graph_of(db, read, 'nowhere')


def test_a_file_focus_shows_that_file_and_never_a_parent_it_keeps_back(db):
    repo_rows(db, inspection={'repository_id': 'rep_1', 'state': 'COMPLETED',
                              'payload_sha256': 'a' * 64, 'revision': 'r1'})
    read = reader({'files': FILES, 'edges': EDGES})
    g = graph_of(db, read, 'app/a.py')
    assert [(n['id'], n['kind'], n['parent']) for n in g['nodes'] if not n.get('endpoint')] \
        == [('app/a.py', 'file', None)]


def test_a_directory_node_is_parented_by_the_directory_kept_with_it(db):
    files = ['app/a.py', 'app/sub/deep.py', 'app/sub/other.py']
    repo_rows(db, inspection={'repository_id': 'rep_1', 'state': 'COMPLETED',
                              'payload_sha256': a_sha(), 'revision': 'r1'})
    read = reader({'files': files, 'edges': []})
    deep = {n['id']: n for n in graph_of(db, read, '', 3)['nodes']}
    assert deep['app']['parent'] is None                       # the focus holds it
    assert deep['app/sub']['parent'] == {'kind': 'directory', 'id': 'app'}
    assert deep['app/sub']['counts'] == {'files': 2}
    assert deep['app/sub/deep.py']['parent'] == {'kind': 'directory', 'id': 'app/sub'}
    assert 'counts' not in deep['app/a.py'] and deep['app/a.py']['kind'] == 'file'
    mid = {n['id']: n for n in graph_of(db, read, '', 2)['nodes']}
    assert 'app/sub' in mid and 'app/sub/deep.py' not in mid    # folded into its directory
    near = {n['id']: n for n in graph_of(db, read, '', 1)['nodes']}
    assert near['app']['parent'] is None and near['app']['counts'] == {'files': 3}
    assert 'app/sub' not in near                               # the depth bound holds


def test_a_directory_node_counts_the_files_beneath_it(db):
    repo_rows(db, inspection={'repository_id': 'rep_1', 'state': 'COMPLETED',
                              'payload_sha256': 'a' * 64, 'revision': 'r1'})
    read = reader({'files': FILES, 'edges': EDGES})
    nodes = {n['id']: n for n in graph_of(db, read, '')['nodes']}
    assert nodes['app']['kind'] == 'directory'
    assert nodes['app']['counts'] == {'files': 2}
    assert nodes['tools']['counts'] == {'files': 1}
    deep = {n['id']: n for n in graph_of(db, read, '', 2)['nodes']}
    assert deep['app']['counts'] == {'files': 2}
    assert 'counts' not in deep['app/a.py'] and deep['app/a.py']['kind'] == 'file'


def test_an_edge_wholly_outside_the_focus_is_neither_drawn_nor_counted(db):
    repo_rows(db, inspection={'repository_id': 'rep_1', 'state': 'COMPLETED',
                              'payload_sha256': 'a' * 64, 'revision': 'r1'})
    read = reader({'files': FILES, 'edges': EDGES})
    g = graph_of(db, read, 'app')
    assert {(e['from']['id'], e['to']['id']) for e in g['edges']} == \
        {('app/a.py', 'app/b.py'), ('app/a.py', 'outside:lib')}
    kept = [n['id'] for n in g['nodes'] if not n.get('endpoint')]
    assert kept == ['app/a.py', 'app/b.py']            # tools/t.py and lib/x.py are not here
    ends = [(n['id'], n['kind']) for n in g['nodes'] if n.get('endpoint')]
    assert ends == [('outside:lib', 'directory')]
    assert g['truncated'] is False


def test_a_focus_with_more_nodes_than_the_limit_says_what_it_kept_back(db):
    repo_rows(db, inspection={'repository_id': 'rep_1', 'state': 'COMPLETED',
                              'payload_sha256': a_sha(), 'revision': 'r1'})
    read = reader({'files': FILES, 'edges': EDGES})
    g = graph_of(db, read, '', 1, 2)
    assert [n['id'] for n in g['nodes'] if not n.get('endpoint')] == ['app', 'lib']
    assert {(e['from']['id'], e['to']['id']) for e in g['edges']} == \
        {('app', 'lib')}                    # tools is in focus but cut: its edge goes with it
    assert not [n for n in g['nodes'] if n.get('endpoint')]
    assert g['truncated'] is True
    assert g['hidden'] == [{'parent': {'kind': 'directory', 'id': ''},
                            'kind': 'path', 'count': 2}]


def test_the_payload_edges_are_capped_too(db):
    files = ['app/f%03d.py' % i for i in range(100)]
    edges = [[a, b] for i, a in enumerate(files) for b in files[i + 1:]]
    assert len(edges) > G.EDGE_MAX
    repo_rows(db, inspection={'repository_id': 'rep_1', 'state': 'COMPLETED',
                              'payload_sha256': 'a' * 64, 'revision': 'r1'})
    read = reader({'files': files, 'edges': edges})
    g = graph_of(db, read, 'app', 1)
    assert len(g['edges']) == G.EDGE_MAX and g['truncated'] is True
