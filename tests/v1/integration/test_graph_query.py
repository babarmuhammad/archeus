"""P18's graph queries over a real database (p18-design-gate A1, A2, A4-A6):
what a neighbourhood contains, in what order, how the cap and the depth hold,
and — as much — what it must never contain: an inferred edge, a body, a
routing explanation, a credential, a node beyond its depth."""

import json

import pytest

from archeus.core.application import commands, graph as G
from archeus.core.domain import entities as E, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.artifacts import store
from archeus.infra.db import rows
from archeus.infra.db.writer import NotFound

WS = ids.GLOBAL_WORKSPACE


def put(db, *entities_):
    """Insert rows a phase would have written, as one writer command (the
    writer refuses a mutation with no event)."""
    def run(tx, **_):
        for x in entities_:
            tx.insert(x, actor=Ref('user_device', ids.new_id('principal')))
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                            Ref('user_device', ids.new_id('principal')), payload={},
                            workspace=WS))
    db.writer.execute(run, {})


def read(db, fn, *a):
    with db.read() as conn:
        return fn(conn, *a)


def mission(db, actor, title='M', project=None):
    mid = db.writer.execute(commands.create_mission,
                            {'actor': actor, 'title': title, 'objective': 'o'})['id']
    if project:
        db.writer.execute(lambda tx, **_: (
            tx.update(E.Mission, mid, {'project_id': project}, actor=actor),
            tx.append(new_event('mission.updated', Ref('mission', mid), actor, payload={},
                                workspace=WS))), {})
    return mid


@pytest.fixture
def world(db, actor):
    """project → mission → plan v1 (superseded) + v2 → two tasks (t2 after t1)
    → an execution each (the second a hand-off of the first) → a route and a
    policy decision; a session; a verification; knowledge with tiered
    relations, one to a decision (no table) and one to a missing row."""
    prj = ids.new_id('project')
    put(db, E.Project(id=prj, workspace_id=WS, name='Atlas', root_paths=[]))
    mid = mission(db, actor, 'Ship the chart', project=prj)
    p1, p2 = ids.new_id('plan'), ids.new_id('plan')
    t1, t2 = ids.new_id('task'), ids.new_id('task')
    rd, pd = ids.new_id('route_decision'), ids.new_id('policy_decision')
    x1, x2 = ids.new_id('execution'), ids.new_id('execution')
    ses, ver = ids.new_id('session'), ids.new_id('verification')
    k1, k2 = ids.new_id('knowledge_item'), ids.new_id('knowledge_item')
    put(db, E.Plan(id=p1, mission_id=mid, plan_version=1, state='SUPERSEDED'),
        E.Plan(id=p2, mission_id=mid, plan_version=2, state='APPROVED', supersedes_plan_id=p1),
        E.Task(id=t1, plan_id=p2, mission_id=mid, key='t1', title='Write it', kind='code_change'),
        E.Task(id=t2, plan_id=p2, mission_id=mid, key='t2', title='Test it', kind='code_change',
               depends_on=['t1']),
        E.RouteDecision(id=rd, subject=Ref('task', t1), selected='fake', harness_id='fake',
                        model='m-large', effort='high', result='selected', task_id=t1,
                        mission_id=mid, explanation='SECRET-EXPLANATION ranked by headroom',
                        requirements={'tier': 'large'}, input_snapshot={'x': 1},
                        candidates=[{'resource': 'a', 'eliminated_at_step': 'health'},
                                    {'resource': 'fake', 'eliminated_at_step': None}]),
        E.PolicyDecision(id=pd, decision='ALLOW', action='run', reason='ok', stage='dispatch',
                         subject=Ref('task', t1), mission_id=mid, task_id=t1),
        E.Execution(id=x1, task_id=t1, mission_id=mid, attempt=1, state='ENDED_HANDOFF',
                    route_decision_id=rd, policy_decision_id=pd, plan_id=p2),
        E.Execution(id=x2, task_id=t1, mission_id=mid, attempt=2, state='RUNNING',
                    handoff_from=x1, plan_id=p2),
        E.Session(id=ses, harness_id='fake', workspace_id=WS, cwd='C:/x', mode='manual',
                  project_id=prj, mission_id=mid, state='OPEN'),
        E.Verification(id=ver, subject=Ref('task', t1), verifier='code', plan_id=p2,
                       execution_id=x1, state='PASSED'),
        E.KnowledgeItem(id=k1, workspace_id=WS, type='DECISION', title='Use bars',
                        text='THE BODY OF THE ITEM', project_id=prj, state='CONFIRMED'),
        E.KnowledgeItem(id=k2, workspace_id=WS, type='FACT', title='sk-livekeyabcdef1234 leaked',
                        project_id=prj, state='CONFIRMED'),
        E.Relation(id=ids.new_id('relation'), src_kind='knowledge_item', src_id=k1,
                   rel='learned_from', dst_kind='mission', dst_id=mid, confidence_tier='INFERRED'),
        E.Relation(id=ids.new_id('relation'), src_kind='knowledge_item', src_id=k2,
                   rel='relates_to', dst_kind='knowledge_item', dst_id=k1,
                   confidence_tier='AMBIGUOUS'),
        E.Relation(id=ids.new_id('relation'), src_kind='decision', src_id='dec_nothere',
                   rel='motivated', dst_kind='knowledge_item', dst_id=k1),
        E.Relation(id=ids.new_id('relation'), src_kind='knowledge_item', src_id=k1,
                   rel='mentions', dst_kind='repository', dst_id=ids.new_id('repository')))
    return dict(prj=prj, mid=mid, p1=p1, p2=p2, t1=t1, t2=t2, rd=rd, pd=pd, x1=x1, x2=x2,
                ses=ses, ver=ver, k1=k1, k2=k2)


def keys(g):
    return [(n['kind'], n['id']) for n in g['nodes']]


def edge(g, field, a, b):
    return [e for e in g['edges'] if e['field'] == field
            and {(e['from']['kind'], e['from']['id']), (e['to']['kind'], e['to']['id'])} == {a, b}]


# ── A4: the world level and the focus ──

def test_the_world_level_is_projects_only_collapsed_with_counts(db, world):
    g = read(db, G.world_graph, None, None, 500)
    assert g['focus']['kind'] == 'workspace' and g['edges'] == []
    assert keys(g) == [('project', world['prj'])]
    c = g['nodes'][0]['counts']
    assert (c['missions'], c['sessions'], c['knowledge_items']) == (1, 1, 2)
    assert c['mission_states'] == {'CREATED': 1}


def test_the_focus_is_the_first_node_and_the_depth_holds(db, world):
    for focus in (('mission', world['mid']), ('execution', world['x2']), ('task', world['t2'])):
        g = read(db, G.world_graph, focus, 1, 500)
        assert keys(g)[0] == focus
    near = read(db, G.world_graph, ('execution', world['x2']), 1, 500)
    far = read(db, G.world_graph, ('execution', world['x2']), 2, 500)
    # plan v2 is two hops from the running attempt (execution → task → plan)
    assert ('plan', world['p2']) not in keys(near) and ('plan', world['p2']) in keys(far)
    assert ('task', world['t1']) in keys(near)


def test_a_project_focus_reaches_its_missions_sessions_and_knowledge(db, world):
    g = read(db, G.world_graph, ('project', world['prj']), None, 500)
    assert g['depth'] == 1
    got = set(keys(g))
    assert {('mission', world['mid']), ('session', world['ses']),
            ('knowledge_item', world['k1']), ('knowledge_item', world['k2'])} <= got
    assert ('plan', world['p2']) not in got          # a project is never loaded whole


def test_an_unknown_focus_is_not_found(db, world):
    with pytest.raises(NotFound):
        read(db, G.world_graph, ('mission', ids.new_id('mission')), 2, 500)


# ── A1: edges are recorded columns and relation rows, nothing else ──

COLUMN = {  # field -> (holder kind, attribute on the holder holding the referent id)
    'missions.project_id': ('mission', 'project_id'),
    'Mission.context_package_id': ('mission', 'context_package_id'),
    'plans.mission_id': ('plan', 'mission_id'), 'plans.supersedes_plan_id': ('plan', 'supersedes_plan_id'),
    'Plan.context_package_id': ('plan', 'context_package_id'),
    'Plan.route_decision_id': ('plan', 'route_decision_id'),
    'tasks.plan_id': ('task', 'plan_id'),
    'executions.task_id': ('execution', 'task_id'), 'executions.mission_id': ('execution', 'mission_id'),
    'Execution.handoff_from': ('execution', 'handoff_from'),
    'Execution.session_id': ('execution', 'session_id'),
    'Execution.route_decision_id': ('execution', 'route_decision_id'),
    'Execution.policy_decision_id': ('execution', 'policy_decision_id'),
    'verifications.plan_id': ('verification', 'plan_id'),
    'Verification.execution_id': ('verification', 'execution_id'),
    'sessions.mission_id': ('session', 'mission_id'), 'sessions.project_id': ('session', 'project_id'),
    'sessions.handoff_from_session_id': ('session', 'handoff_from_session_id'),
    'KnowledgeItem.supersedes_id': ('knowledge_item', 'supersedes_id'),
    'KnowledgeItem.superseded_by_id': ('knowledge_item', 'superseded_by_id'),
    'KnowledgeItem.route_decision_id': ('knowledge_item', 'route_decision_id'),
    'knowledge_items.project_id': ('knowledge_item', 'project_id'),
    'repositories.project_id': ('repository', 'project_id'),
    'reviews.plan_id': ('review', 'plan_id'), 'approvals.mission_id': ('approval', 'mission_id'),
    'automation_runs.automation_id': ('automation_run', 'automation_id'),
    'automation_runs.mission_id': ('automation_run', 'mission_id'),
}


def test_every_edge_is_a_recorded_column_or_relation_row(db, world):
    """No inferred edge (M22): every edge names a field whose value on the
    holding row IS the other end, or a Relation row with exactly those ends."""
    for focus in (('mission', world['mid']), ('knowledge_item', world['k1']),
                  ('project', world['prj'])):
        g = read(db, G.world_graph, focus, 2, 1000)
        with db.read() as conn:
            for e in g['edges']:
                f, a, b = e['field'], e['from'], e['to']
                if f.startswith('relations.'):
                    found = rows.where(conn, E.Relation, src_kind=a['kind'], src_id=a['id'],
                                       rel=e['rel'])
                    assert any(r.entity.dst_kind == b['kind'] and r.entity.dst_id == b['id']
                               for r in found), e
                elif f == 'Task.depends_on':
                    h = rows.get(conn, E.Task, a['id']).entity
                    dep = rows.get(conn, E.Task, b['id']).entity
                    assert dep.key in h.depends_on and dep.plan_id == h.plan_id, e
                elif f == 'Verification.subject':
                    h = rows.get(conn, E.Verification, a['id']).entity
                    assert (h.subject.kind, h.subject.id) == (b['kind'], b['id']), e
                elif f == 'Mission.origin_ref':
                    h = rows.get(conn, E.Mission, a['id']).entity
                    assert (h.origin_ref.kind, h.origin_ref.id) == (b['kind'], b['id']), e
                elif f == 'approvals.mission_id' and a['kind'] == 'mission':
                    ap = rows.get(conn, E.Approval, b['id']).entity
                    assert ap.mission_id == a['id'] and ap.state == 'PENDING', e
                else:
                    kind, attr = COLUMN[f]
                    assert a['kind'] == kind, e
                    h = rows.get(conn, G.KINDS[kind][0], a['id']).entity
                    assert getattr(h, attr) == b['id'], e


def test_no_edge_is_emitted_for_an_empty_field(db, world):
    """M01: attempt 1 has no hand-off source, no session; nothing points at None."""
    g = read(db, G.world_graph, ('execution', world['x1']), 1, 500)
    for e in g['edges']:
        assert e['from']['id'] and e['to']['id']
    held = [e for e in g['edges'] if e['from'] == {'kind': 'execution', 'id': world['x1']}]
    assert {e['field'] for e in held} == {'executions.task_id', 'executions.mission_id',
                                          'Execution.route_decision_id',
                                          'Execution.policy_decision_id'}


def test_the_hand_off_and_the_dependency_point_the_recorded_way(db, world):
    g = read(db, G.world_graph, ('task', world['t1']), 2, 500)
    (h,) = edge(g, 'Execution.handoff_from', ('execution', world['x2']), ('execution', world['x1']))
    assert h['from']['id'] == world['x2'] and h['to']['id'] == world['x1']
    (d,) = edge(g, 'Task.depends_on', ('task', world['t2']), ('task', world['t1']))
    assert d['from']['id'] == world['t2']


def test_relation_tiers_are_the_rows_own_and_superseded_plans_are_kept_marked(db, world):
    """M03, M05."""
    g = read(db, G.world_graph, ('knowledge_item', world['k1']), 1, 500)
    tiers = {e['field']: e['tier'] for e in g['edges'] if e['field'].startswith('relations.')}
    assert tiers == {'relations.learned_from': 'INFERRED', 'relations.relates_to': 'AMBIGUOUS',
                     'relations.motivated': 'EXTRACTED', 'relations.mentions': 'EXTRACTED'}
    m = read(db, G.world_graph, ('mission', world['mid']), 1, 500)
    (old,) = edge(m, 'plans.mission_id', ('plan', world['p1']), ('mission', world['mid']))
    (cur,) = edge(m, 'plans.mission_id', ('plan', world['p2']), ('mission', world['mid']))
    assert old['inactive'] is True and cur['inactive'] is False


def test_a_tableless_kind_and_a_missing_row_are_endpoints_not_nodes(db, world):
    g = read(db, G.world_graph, ('knowledge_item', world['k1']), 1, 500)
    ends = {n['kind']: n for n in g['nodes'] if n.get('endpoint')}
    assert ends['decision']['missing'] is False          # no Decision table (A2)
    assert ends['repository']['missing'] is True         # a row that does not exist
    for n in ends.values():
        assert set(n) == {'kind', 'id', 'endpoint', 'missing', 'label'}


def test_structural_edges_are_marked_and_the_lists_own_edge_wins(db, world, actor):
    apr = ids.new_id('approval')
    put(db, E.Approval(id=apr, subject=Ref('plan', world['p2']), action_hash='a' * 64,
                       requested_by=actor.id, kind='plan', mission_id=world['mid'],
                       plan_id=world['p2'], plan_version=2, state='PENDING',
                       expires_at='2999-01-01T00:00:00.000Z'))
    g = read(db, G.world_graph, ('mission', world['mid']), 1, 500)
    (a,) = edge(g, 'approvals.mission_id', ('mission', world['mid']), ('approval', apr))
    assert a['structural'] is False                       # the pending edge, not membership
    t = read(db, G.world_graph, ('plan', world['p2']), 1, 500)
    assert all(e['structural'] for e in t['edges'] if e['field'] == 'tasks.plan_id')


# ── A6: order, cap, allowlist, labels ──

def test_nodes_come_in_hop_then_kind_rank_order_and_the_same_bytes_twice(db, world):
    """M12: one ring is one hop, so its kinds never go back up the rank table,
    and within a kind an open row comes before a settled one."""
    g = read(db, G.world_graph, ('mission', world['mid']), 1, 500)
    ring = [n for n in g['nodes'][1:] if not n.get('endpoint')]
    assert len(ring) >= 4
    assert [G.RANK[n['kind']] for n in ring] == sorted(G.RANK[n['kind']] for n in ring)
    ex = [n['state'] for n in ring if n['kind'] == 'execution']
    assert ex == ['RUNNING', 'ENDED_HANDOFF']
    again = read(db, G.world_graph, ('mission', world['mid']), 1, 500)
    assert json.dumps(g, sort_keys=True) == json.dumps(again, sort_keys=True)


def test_edges_are_sorted_and_ids_are_stable(db, world):
    g = read(db, G.world_graph, ('mission', world['mid']), 2, 500)
    ids_ = [e['id'] for e in g['edges']]
    assert len(set(ids_)) == len(ids_)
    for e in g['edges']:
        assert e['id'] == '%s|%s:%s|%s:%s' % (e['field'], e['from']['kind'], e['from']['id'],
                                              e['to']['kind'], e['to']['id'])


def test_the_running_attempt_ranks_before_the_ended_one(db, world):
    """Open before settled (§22 G1): with room for one execution, the live one stays."""
    g = read(db, G.world_graph, ('task', world['t1']), 1, 2)
    got = keys(g)
    assert got[0] == ('task', world['t1'])
    assert ('execution', world['x2']) in got and ('execution', world['x1']) not in got


def test_the_cap_holds_and_hidden_counts_what_it_cut(db, world):
    g = read(db, G.world_graph, ('mission', world['mid']), 2, 3)
    real = [n for n in g['nodes'] if not n.get('endpoint')]
    assert len(real) == 3 and g['truncated'] is True
    assert sum(h['count'] for h in g['hidden']) > 0
    full = read(db, G.world_graph, ('mission', world['mid']), 2, 1000)
    n_full = len([n for n in full['nodes'] if not n.get('endpoint')])
    assert len(real) + sum(h['count'] for h in g['hidden']) <= n_full
    for e in g['edges']:                                  # never an edge to a cut node
        for end in (e['from'], e['to']):
            assert (end['kind'], end['id']) in {(n['kind'], n['id']) for n in g['nodes']}


def test_a_route_decision_shows_recorded_selection_facts_only(db, world):
    """P10's decision, never its reasoning (A2, M11)."""
    g = read(db, G.world_graph, ('execution', world['x1']), 1, 500)
    (rd,) = [n for n in g['nodes'] if n['kind'] == 'route_decision']
    assert set(rd) == {'kind', 'id', 'label', 'parent', 'attrs'}
    assert rd['attrs'] == {'harness_id': 'fake', 'account_id': None, 'model': 'm-large',
                           'effort': 'high', 'result': 'selected', 'fallback_from': [],
                           'eliminated': 1}
    text = json.dumps(read(db, G.world_graph, ('mission', world['mid']), 2, 1000))
    for secret in ('SECRET-EXPLANATION', 'input_snapshot', 'requirements', 'THE BODY OF THE ITEM',
                   'candidates', 'explanation'):
        assert secret not in text


def test_every_node_carries_only_allowlisted_keys(db, world):
    g = read(db, G.world_graph, ('mission', world['mid']), 2, 1000)
    allowed = {'kind', 'id', 'label', 'parent', 'machine', 'state', 'attrs', 'counts',
               'endpoint', 'missing'}
    for n in g['nodes']:
        assert set(n) <= allowed, n


def test_labels_are_redacted_one_line_and_capped(db, world, actor):
    g = read(db, G.world_graph, ('knowledge_item', world['k2']), 1, 500)
    (k,) = [n for n in g['nodes'] if n['id'] == world['k2']]
    assert 'sk-livekey' not in k['label'] and '[redacted]' in k['label']
    long = mission(db, actor, 'x' * 300 + '\x1b]0;owned\x07\nsecond line')
    (m,) = read(db, G.world_graph, ('mission', long), 1, 500)['nodes'][:1]
    assert len(m['label']) <= G.LABEL_MAX and '\x1b' not in m['label'] and '\n' not in m['label']


# ── A5: the repository import graph ──

PAYLOAD = {'extractor_version': 1, 'truncated': False, 'nested': [], 'dependencies': [],
           'files': ['README.md', 'app/main.py', 'app/util.py', 'app/ghost.py',
                     'lib/core/a.py', 'lib/core/b.py', 'lib/io.py'],
           'edges': [['app/main.py', 'app/util.py'], ['app/main.py', 'lib/core/a.py'],
                     ['app/util.py', 'lib/core/b.py'], ['lib/core/a.py', 'lib/core/b.py'],
                     ['app/ghost.py', 'lib/io.py']]}


@pytest.fixture
def repo(db, world):
    """A repository whose working tree does not exist: everything below comes
    from the stored payload (M21)."""
    sha = store.put(json.dumps(PAYLOAD).encode('utf-8'))
    rep, ins = ids.new_id('repository'), ids.new_id('repository_inspection')
    put(db, E.Repository(id=rep, workspace_id=WS, project_id=world['prj'], path='Z:/no/such/tree',
                         path_key='z:/no/such/tree', architecture_state='CONSISTENT',
                         last_inspection_id=ins, last_revision='r1'),
        E.RepositoryInspection(id=ins, repository_id=rep, extractor_version=1,
                               revision='r1', state='COMPLETED', payload_sha256=sha,
                               inspected_at='2026-09-29T10:00:00Z'))
    return rep


def rg(db, rep, focus='', depth=1, limit=500):
    return read(db, G.repository_graph, rep, store.get, focus, depth, limit)


def test_the_repository_graph_is_the_stored_payload_at_the_focus(db, repo):
    g = rg(db, repo)
    assert g['available'] is True and g['stale'] is False and g['revision'] == 'r1'
    ids_ = [n['id'] for n in g['nodes'] if not n.get('endpoint')]
    assert ids_ == ['app', 'lib', 'README.md']           # directories first, then path
    counts = {e['from']['id'] + '>' + e['to']['id']: e['count'] for e in g['edges']}
    # main→a, util→b and ghost→io lift to app→lib; edges inside one node vanish
    assert counts == {'app>lib': 3}


def test_the_repository_graph_goes_one_level_down_and_keeps_outside_ends(db, repo):
    g = rg(db, repo, 'app', 1)
    real = [n['id'] for n in g['nodes'] if not n.get('endpoint')]
    assert real == ['app/ghost.py', 'app/main.py', 'app/util.py']   # ghost is not on disk
    ends = {n['id'] for n in g['nodes'] if n.get('endpoint')}
    assert ends == {'outside:lib'}
    counts = {(e['from']['id'], e['to']['id']): e['count'] for e in g['edges']}
    assert counts == {('app/main.py', 'app/util.py'): 1, ('app/main.py', 'outside:lib'): 1,
                      ('app/util.py', 'outside:lib'): 1, ('app/ghost.py', 'outside:lib'): 1}
    deep = rg(db, repo, 'lib', 2)
    assert {n['id'] for n in deep['nodes'] if not n.get('endpoint')} == {
        'lib/core', 'lib/core/a.py', 'lib/core/b.py', 'lib/io.py'}


def test_the_repository_graph_caps_and_orders(db, repo):
    g = rg(db, repo, 'app', 1, 2)
    assert [n['id'] for n in g['nodes'] if not n.get('endpoint')] == ['app/ghost.py',
                                                                       'app/main.py']
    assert g['truncated'] is True and g['hidden'][0]['count'] == 1


def test_an_unknown_path_is_not_found(db, repo):
    with pytest.raises(NotFound):
        rg(db, repo, 'nowhere')


def test_stale_not_inspected_and_missing_payload_are_said_not_guessed(db, repo, world, actor):
    db.writer.execute(lambda tx, **_: (
        tx.update(E.Repository, repo, {'last_revision': 'r2'}, actor=actor),
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')), actor,
                            payload={}, workspace=WS))), {})
    assert rg(db, repo)['stale'] is True                  # M29
    bare = ids.new_id('repository')
    put(db, E.Repository(id=bare, workspace_id=WS, project_id=world['prj'], path='Z:/b',
                         path_key='z:/b'))
    assert rg(db, bare) == dict(rg(db, bare), available=False, reason='not_inspected')
    rep2, ins2 = ids.new_id('repository'), ids.new_id('repository_inspection')
    put(db, E.Repository(id=rep2, workspace_id=WS, project_id=world['prj'], path='Z:/c',
                         path_key='z:/c', last_inspection_id=ins2, last_revision='r1'),
        E.RepositoryInspection(id=ins2, repository_id=rep2, extractor_version=1,
                               revision='r1', state='COMPLETED', payload_sha256='0' * 64))
    assert rg(db, rep2)['reason'] == 'payload_missing'
    with pytest.raises(NotFound):
        rg(db, ids.new_id('repository'))


# ── A15, A10: what the scope does not isolate, and the server's cost ──

def test_one_observe_reader_sees_every_projects_graph(db, world):
    """A15, stated as a test so changing it is deliberate: V1 has one workspace
    and no project scopes, so the world level lists every project."""
    other = ids.new_id('project')
    put(db, E.Project(id=other, workspace_id=WS, name='Borealis', root_paths=[]))
    got = {n['id'] for n in read(db, G.world_graph, None, None, 500)['nodes']}
    assert got == {world['prj'], other}


def test_a_thousand_node_neighbourhood_is_built_within_budget(db, world):
    """A10 proxy (4): the server's work for the largest answer it gives. A
    regression gate with a wide margin, not a claim about any client's frames."""
    import time
    put(db, *[E.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=WS, type='FACT',
                              title='fact %d' % i, project_id=world['prj'], state='CONFIRMED')
              for i in range(1100)])
    t = time.perf_counter()
    g = read(db, G.world_graph, ('project', world['prj']), 1, 1000)
    took = time.perf_counter() - t
    assert len([n for n in g['nodes'] if not n.get('endpoint')]) == 1000 and g['truncated']
    assert took < BUDGET_S, took


#: 0.10 s measured 2026-09-29 on the development machine; CI runners are slower,
#: so the gate is 15x the measurement (p18-design-gate A10)
BUDGET_S = 1.5
