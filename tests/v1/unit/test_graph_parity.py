"""P18 A1 (1): Core's graph edges against the shared parity cases.

`parity.json` already holds the SPA's `relations.ts` and the TUI's `present.py`
to the same outputs. Here Core's holder edges (`archeus/core/application/graph.py`)
are held to them too, so the three edge implementations that exist until P19
(p18-design-gate V2) cannot drift apart. A list function shows an object's edges
from where it stands; Core emits each edge once, from the row that holds its
field. So each case is compared as the set of (field, neighbour, tier, inactive)
around the object, with the holders the list function's own inputs name.
Structural (containment) edges are Core's only (V8) and are left out."""

import dataclasses
import json
import os
from types import SimpleNamespace

import pytest

from archeus.core.application import graph as G
from archeus.core.domain import entities as E

CASES = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'clients', 'app', 'test',
                     'fixtures', 'parity.json')
with open(CASES, encoding='utf-8') as _f:
    EDGE_CASES = [c for c in json.load(_f)['cases'] if c['fn'].endswith(('Edges', 'Dependencies'))]

CLASS = {'mission': E.Mission, 'plan': E.Plan, 'task': E.Task, 'execution': E.Execution,
         'verification': E.Verification, 'session': E.Session, 'knowledge_item': E.KnowledgeItem,
         'automation_run': E.AutomationRun}


def _ns(v):
    return SimpleNamespace(**v) if isinstance(v, dict) else v


def row(kind, d, **extra):
    """An entity-shaped object from a case's partial dict: every field None
    unless the case (or *extra*) gives it."""
    data = {f.name: None for f in dataclasses.fields(CLASS[kind])}
    data.update({k: _ns(v) for k, v in dict(d, **extra).items()})
    data.setdefault('id', None)
    data['id'] = data['id'] or '%s_case' % kind
    return SimpleNamespace(**data)


class FakeRows:
    """`rows.where` for the two derived reads a holder makes: a mission's
    pending approval (as `get_mission` derives it) and a plan's tasks by key."""

    def __init__(self, approvals=(), tasks=()):
        self.approvals, self.tasks = list(approvals), list(tasks)

    def where(self, conn, cls, **eq):
        pick = self.approvals if cls is E.Approval else self.tasks if cls is E.Task else []
        return [SimpleNamespace(entity=x) for x in pick]


def around(me, edges):
    out = set()
    for x in edges:
        if x['structural']:
            continue
        a, b = (x['from']['kind'], x['from']['id']), (x['to']['kind'], x['to']['id'])
        other = b if a == me else a
        out.add((x['field'], other, x['tier'], x['inactive']))
    return out


def listed(out):
    return {(x['field'], (x['to']['kind'], x['to']['id']), x.get('tier'), x.get('inactive', False))
            for x in out}


def core_edges(case, monkeypatch):
    fn, args = case['fn'], case['args']
    if fn == 'missionEdges':
        m, plan, sessions = args
        me = row('mission', m)
        pending = m.get('pending_approval_id')
        monkeypatch.setattr(G, 'rows', FakeRows(
            approvals=[SimpleNamespace(id=pending, state='PENDING')] if pending else ()))
        out = G.held_edges(None, 'mission', me)
        for v in (plan or {}).get('versions') or []:
            out += G.held_edges(None, 'plan', row('plan', v, mission_id=me.id))
        for s in sessions:
            if s.get('id'):
                out += G.held_edges(None, 'session', row('session', s, mission_id=me.id))
        return ('mission', me.id), out
    if fn == 'taskDependencies':
        t, by_key = args
        monkeypatch.setattr(G, 'rows', FakeRows(tasks=[SimpleNamespace(key=k, id=v.get('id'))
                                                       for k, v in by_key.items()]))
        me = row('task', t, plan_id='pln_case')
        return ('task', me.id), G.held_edges(None, 'task', me)
    if fn == 'sessionEdges':
        x, view = (list(args) + [None])[:2]
        me = row('session', x)
        out = G.held_edges(None, 'session', me)
        for t in (view or {}).get('targets') or []:
            out += G.held_edges(None, 'session',
                                row('session', t, handoff_from_session_id=me.id))
        return ('session', me.id), out
    if fn == 'knowledgeEdges':
        (k,) = args
        me = row('knowledge_item', {x: v for x, v in k.items() if x != 'relations'})
        out = G.held_edges(None, 'knowledge_item', me)
        out += [G.relation_edge(SimpleNamespace(**dict({'valid_until': None, 'confidence_tier': None}, **r)))
                for r in k.get('relations') or []]
        return ('knowledge_item', me.id), out
    kind = {'planEdges': 'plan', 'executionEdges': 'execution',
            'verificationEdges': 'verification', 'runEdges': 'automation_run'}[fn]
    me = row(kind, args[0])
    return (kind, me.id), G.held_edges(None, kind, me)


@pytest.mark.parametrize('case', EDGE_CASES, ids=lambda c: c['fn'])
def test_core_edges_equal_the_list_mapper_on_every_shared_case(case, monkeypatch):
    me, got = core_edges(case, monkeypatch)
    want = listed(case['out'])
    # the list shows a relation's tier; a column edge has none
    assert around(me, got) == want, case['args']


def test_every_list_edge_function_has_a_case_here():
    assert {c['fn'] for c in EDGE_CASES} == {
        'missionEdges', 'planEdges', 'taskDependencies', 'executionEdges', 'verificationEdges',
        'sessionEdges', 'knowledgeEdges', 'runEdges'}


def test_every_field_core_emits_has_its_words_and_no_word_is_orphaned():
    """A1 (3): the graph names a field, the client says its words — so the
    vocabulary in relations.ts covers exactly the fields Core can emit."""
    import inspect
    import re
    ts = os.path.join(os.path.dirname(CASES), '..', '..', 'src', 'graph', 'relations.ts')
    with open(ts, encoding='utf-8') as f:
        block = f.read().split('export const EDGE_WORDS', 1)[1].split('};', 1)[0]
    words = set(re.findall(r"'([A-Za-z_]+\.[A-Za-z_]+)': \[", block))
    core = set(re.findall(r"_edge\(out, me, '([A-Za-z_]+\.[A-Za-z_]+)'",
                          inspect.getsource(G.held_edges)))
    assert core and core == words, (core ^ words)
