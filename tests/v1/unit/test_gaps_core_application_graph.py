"""T-709: the highest-risk uncovered branches of `archeus/core/application/graph.py`.

Fail-closed and denial paths first - a focus of a kind Core never shows, a
candidate holder whose own columns do not name the node, an approval whose
mission row Core never found, a verification with no subject, a dependency that
names no task, an edge whose end the cap cut, a repository that was never
inspected and a payload that cannot be read - then the boundary values (the cap
at 0 and 1, the label at LABEL_MAX and LABEL_MAX+1, the rank key of a row with
no `updated_at`), then the error paths (a `read` that raises, a payload that is
not the JSON object the extractor promised).

The module's existing tests are tests/v1/integration/test_graph_query.py (the
closest one: real rows, and the `put`/`read`/`rg` fixtures and world/repository
fixtures whose shape is copied here), tests/v1/unit/test_graph_boundaries.py
(static properties of the source), tests/v1/unit/test_graph_parity.py (whose
`SimpleNamespace` row and `_holders`/`_load` seam is copied for the reads no
schema allows a row for) and tests/v1/integration/test_graph_routes.py (the two
routes). The database fixtures follow the sibling gap tests
(tests/v1/unit/test_gaps_core_application_verification.py): `Database.open()`
under the test's own `ARCHEUS_HOME` (the autouse fixture of tests/v1/conftest.py)
and `db.writer.execute`, never a command of another module.

Platform: nothing here shells out, reads the network or touches a real working
tree - the repository rows name a path that does not exist, and the only bytes
written go through the content-addressed artifact store. Every payload path is
ASCII with forward slashes and no `?` or `:`, no test reads an environment value
or an OS error message, and no assertion depends on a path being absolute or on
a separator, so the same answers are expected on Linux and Windows. Payload
addresses are unique per test because `_payload` is `lru_cache`d process-wide;
the missing-payload log set is module state, so the test that reads the log uses
addresses no other test can reach.

The ten branches this file exists for are listed in /work/QWEN-DONE-T-709.md
with their file:line, and the ones the source gets wrong are marked
`xfail(strict=True)` rather than weakened.
"""

import dataclasses
import hashlib
import json
from types import SimpleNamespace

import pytest

from archeus.core.application import graph as G
from archeus.core.domain import entities as E, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.artifacts import store
from archeus.infra.db import Database, rows
from archeus.infra.db.writer import NotFound
from archeus.infra.eventlog import outbox

WS = ids.GLOBAL_WORKSPACE


# -- fixtures and seeding: one transaction each, no command, no process ------

@pytest.fixture
def db(archeus_home):
    d = Database.open()
    try:
        yield d
    finally:
        d.close()


@pytest.fixture
def actor():
    return Ref('user_device', ids.new_id('principal'))


def put(db, actor, *entities_):
    """Insert rows as one writer command (the writer refuses a mutation with no
    event), in the order given: `held_edges` reads the LAST pending approval."""
    def run(tx, **_):
        for x in entities_:
            tx.insert(x, actor=actor)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')), actor,
                            payload={}, workspace=WS))
    db.writer.execute(run, {})


def q(db, fn, *a):
    """One read: the graph function over its own read connection, nothing else."""
    with db.read() as conn:
        return fn(conn, *a)


def held(db, kind, entity):
    with db.read() as conn:
        return G.held_edges(conn, kind, entity)


def row_of(db, cls, entity_id):
    with db.read() as conn:
        return rows.get(conn, cls, entity_id)


def fake(kind, **over):
    """An entity-shaped row of *kind* with every field None unless given (the
    `SimpleNamespace` seam tests/v1/unit/test_graph_parity.py uses)."""
    data = {f.name: None for f in dataclasses.fields(G.KINDS[kind][0])}
    data.update(over)
    data['id'] = data.get('id') or ids.new_id(kind)
    return SimpleNamespace(**data)


def outbox_head(conn):
    """The event head an answer carries (A4): the same cursor on every replay."""
    return outbox.head(conn)


def a_project(name='Atlas', state='ACTIVE', **over):
    return E.Project(id=ids.new_id('project'), workspace_id=WS, name=name, state=state,
                     root_paths=(), **over)


def a_mission(**over):
    over.setdefault('title', 'Ship the graph')
    return E.Mission(id=ids.new_id('mission'), workspace_id=WS, objective='an objective',
                     state='CREATED', **over)


def a_plan(mission_id, **over):
    return E.Plan(id=ids.new_id('plan'), mission_id=mission_id, plan_version=1,
                  state='APPROVED', **over)


def a_task(plan_id, mission_id, key='t1', **over):
    return E.Task(id=ids.new_id('task'), plan_id=plan_id, mission_id=mission_id, key=key,
                  title='Task ' + key, kind='code_change', **over)


def an_execution(task_id, mission_id, **over):
    over.setdefault('attempt', 1)
    return E.Execution(id=ids.new_id('execution'), task_id=task_id, mission_id=mission_id,
                       state='RUNNING', **over)


def a_verification(subject, plan_id, **over):
    return E.Verification(id=ids.new_id('verification'), subject=subject, plan_id=plan_id,
                          verifier='code', state='PASSED', **over)


def an_approval(mission_id, **over):
    aid = over.pop('id', None) or ids.new_id('approval')
    over.setdefault('state', 'PENDING')
    over.setdefault('expires_at', '2026-12-01T00:00:00.000Z')      # the column is NOT NULL
    return E.Approval(id=aid, subject=over.pop('subject', None) or Ref('mission', mission_id),
                      action_hash=hashlib.sha256(aid.encode('utf-8')).hexdigest(),
                      requested_by=ids.new_id('principal'), kind='plan',
                      mission_id=mission_id, **over)


def a_knowledge(project_id, **over):
    over.setdefault('title', 'A fact')
    return E.KnowledgeItem(id=ids.new_id('knowledge_item'), workspace_id=WS, type='FACT',
                           project_id=project_id, state='CONFIRMED', **over)


def a_session(**over):
    over.setdefault('harness_id', 'fake')
    over.setdefault('cwd', 'repo/work')
    over.setdefault('mode', 'manual')
    return E.Session(id=ids.new_id('session'), workspace_id=WS, state='OPEN', **over)


def a_route_decision(**over):
    over.setdefault('subject', Ref('task', ids.new_id('task')))
    over.setdefault('purpose', 'planner')
    over.setdefault('decided_by', 'router')
    return E.RouteDecision(id=ids.new_id('route_decision'), **over)


def a_repository(project_id, **over):
    rid = over.pop('id', None) or ids.new_id('repository')
    over.setdefault('path', 'repo/' + rid)
    over.setdefault('path_key', 'repo/' + rid)
    over.setdefault('architecture_state', 'CONSISTENT')
    return E.Repository(id=rid, workspace_id=WS, project_id=project_id, **over)


def an_inspection(repository_id, **over):
    over.setdefault('extractor_version', 1)
    over.setdefault('state', 'COMPLETED')
    over.setdefault('revision', 'r1')
    return E.RepositoryInspection(id=over.pop('id', None) or ids.new_id('repository_inspection'),
                                  repository_id=repository_id, **over)


def keys(g):
    return [(n['kind'], n['id']) for n in g['nodes']]


def unique_sha(nonce):
    """An address no other test's payload can share: `_payload` is `lru_cache`d
    and `_MISSING` is module state, so a shared sha would leak between tests."""
    return hashlib.sha256(('t709/' + str(nonce)).encode('utf-8')).hexdigest()


# -- empty and hostile input --------------------------------------------------

def test_an_empty_database_answers_for_every_query_without_inventing_anything(db, actor):
    """A1, A4, A5 on nothing: the world level is an empty list, not a null; a
    focus that is not there is NotFound; a repository that is not there is
    NotFound; a row with nothing recorded in it holds no edge, never an edge to
    None."""
    g = q(db, G.world_graph, None, None, 500)
    assert g['focus'] == {'kind': 'workspace', 'id': WS} and g['depth'] == 1
    assert g['nodes'] == [] and g['edges'] == [] and g['hidden'] == []
    assert g['truncated'] is False and g['as_of_seq'] == 0
    with pytest.raises(NotFound):
        q(db, G.world_graph, ('mission', ids.new_id('mission')), 2, 500)
    with pytest.raises(NotFound):
        q(db, G.repository_graph, ids.new_id('repository'), lambda sha: b'{}')
    assert held(db, 'mission', a_mission()) == []
    assert held(db, 'review', fake('review', plan_id=None)) == []
    assert held(db, 'plan', fake('plan', state='APPROVED', mission_id=None,
                                 supersedes_plan_id='', context_package_id=None,
                                 route_decision_id=None)) == []
    assert held(db, 'session', fake('session', mission_id=None, project_id=None,
                                    handoff_from_session_id='')) == []


@pytest.mark.parametrize('kind', ['idea', 'account', 'principal', 'device', 'message',
                                  'usage_snapshot', 'Mission', '', 'mission'])
def test_a_focus_of_a_kind_core_never_shows_is_not_found(db, actor, kind):
    """graph.py:268-270 then 326-327 - the allowlist is the gate, not the table.
    An `idea` row exists and still no node, no edge and no 500: only NotFound."""
    idea = E.Idea(id=ids.new_id('idea'), workspace_id=WS, text='an idea, never a node')
    put(db, actor, idea)
    with pytest.raises(NotFound):                             # never KeyError, TypeError ..
        q(db, G.world_graph, (kind, idea.id if kind == 'idea' else ids.new_id('mission')), 2,
          500)
    for bad in ('not-a-mission-id', '', None, 7):             # a malformed focus too
        with pytest.raises(NotFound):
            q(db, G.world_graph, ('mission' if kind not in G.KINDS else kind, bad), 1, 50)
    assert 'idea' not in G.KINDS and 'idea' not in G.RANK


def test_a_focus_row_that_does_not_exist_is_not_found_though_its_kind_is_known(db, actor):
    """The same raise on the other side of the gate: `rows.get` found nothing."""
    put(db, actor, a_project())                               # one project, none of these
    for kind in ('mission', 'plan', 'task', 'execution', 'session', 'knowledge_item',
                 'verification', 'review', 'approval', 'route_decision', 'policy_decision',
                 'context_package', 'meeting', 'automation', 'automation_run', 'repository'):
        with pytest.raises(NotFound):
            q(db, G.world_graph, (kind, ids.new_id(kind)), 1, 50)


# -- denial and fail-closed paths ---------------------------------------------

@pytest.fixture
def neighbourhood(db, actor):
    """project -> mission -> plan -> task -> an attempt, plus a second attempt of
    the same task whose own `mission_id` column names ANOTHER mission (the
    denormalized, hostile row), plus a session and a knowledge item."""
    prj = a_project()
    mid, foreign = a_mission(project_id=prj.id), a_mission(project_id=prj.id)
    plan = a_plan(mid.id)
    t1 = a_task(plan.id, mid.id, key='t1')
    x1 = an_execution(t1.id, mid.id)
    x2 = an_execution(t1.id, foreign.id, attempt=2)                 # its columns lie
    ses = a_session(project_id=prj.id, mission_id=mid.id)
    know = a_knowledge(prj.id, title='A fact')
    put(db, actor, prj, mid, foreign, plan, t1, x1, x2, ses, know)
    return dict(prj=prj.id, mid=mid.id, foreign=foreign.id, plan=plan.id, t1=t1.id,
                x1=x1.id, x2=x2.id, ses=ses.id, know=know.id)


def test_a_holder_that_holds_no_edge_here_is_not_a_neighbour(db, neighbourhood):
    """graph.py:338-342 - an indexed column may PROPOSE a holder; only its own
    edges admit it. The foreign attempt is proposed along `executions.task_id`,
    but nothing it holds names this mission, so at depth 1 it is neither a node
    nor an edge end. Three levels down it does appear, through the task its own
    column does name: the gate is the row's word, not a deny list."""
    near = q(db, G.world_graph, ('mission', neighbourhood['mid']), 1, 500)
    assert ('execution', neighbourhood['x1']) in keys(near)
    assert ('execution', neighbourhood['x2']) not in keys(near)
    assert neighbourhood['x2'] not in json.dumps(near)
    assert ('mission', neighbourhood['foreign']) not in keys(near)
    far = q(db, G.world_graph, ('mission', neighbourhood['mid']), 3, 500)
    assert ('execution', neighbourhood['x2']) in keys(far)
    (mine,) = [e for e in near['edges'] if e['field'] == 'executions.mission_id']
    assert mine['from']['id'] == neighbourhood['x1']
    assert mine['to'] == {'kind': 'mission', 'id': neighbourhood['mid']}


def test_an_approval_whose_mission_row_core_never_found_holds_no_neighbour(db, actor,
                                                                           monkeypatch):
    """graph.py:253-258 - the only reverse edge an approval has is its mission's
    "waiting on" (the list's): the mission has to be there to be drawn beside it,
    and an approval that records no containment, or whose own row is gone, holds
    nothing at all. No schema lets such a row exist (the column is NOT NULL and
    references a mission), so this is the seam tests/v1/unit/test_graph_parity.py
    uses; the control under it runs on real rows."""
    prj, mid = a_project(), a_mission()                              # the control, real rows
    put(db, actor, prj, mid)
    taken = an_approval(mid.id)
    put(db, actor, taken)
    g = q(db, G.world_graph, ('approval', taken.id), 2, 50)
    assert ('mission', mid.id) in keys(g)
    assert len(g['edges']) == 1 and g['edges'][0]['field'] == 'approvals.mission_id'
    waiting = fake('mission', state='PENDING')
    here = an_approval(waiting.id)
    dangling = an_approval(ids.new_id('mission'))                   # its column names no row
    orphan = fake('approval', id=ids.new_id('approval'), mission_id=None)
    table = {'Approval:%s' % a.id: SimpleNamespace(entity=a) for a in (here, dangling, orphan)}
    table['Mission:%s' % waiting.id] = SimpleNamespace(entity=waiting)
    monkeypatch.setattr(G.rows, 'get',
                        lambda c, cls, i: table.get('%s:%s' % (cls.__name__, i)))
    assert [x[1].entity.id for x in G._holders(None, 'approval', here.id)] == [waiting.id]
    assert G._holders(None, 'approval', dangling.id) == []           # the row was never found
    assert G._holders(None, 'approval', orphan.id) == []             # nothing recorded
    assert G._holders(None, 'approval', ids.new_id('approval')) == []   # the holder is gone


def test_a_verification_without_a_subject_holds_no_subject_edge(db, actor):
    """graph.py:173-175 - the subject edge is the Ref's own kind and id, never
    the holder's plan and never a nameless kind; a row with no subject still
    holds its plan and execution edges, and the reads do not choke on it. The
    entity refuses a subjectless row, so the empty case is the decoded-row seam
    (a body that was written by something other than a command)."""
    prj, mid = a_project(), a_mission()
    plan = a_plan(mid.id)
    t1 = a_task(plan.id, mid.id)
    x1 = an_execution(t1.id, mid.id)
    of_task = a_verification(Ref('task', t1.id), plan.id, execution_id=x1.id)
    of_mission = a_verification(Ref('mission', mid.id), plan.id, criterion=0)
    put(db, actor, prj, mid, plan, t1, x1, of_task, of_mission)
    fields = {e['field'] for e in held(db, 'verification', row_of(db, E.Verification,
                                                                   of_task.id).entity)}
    assert fields == {'Verification.subject', 'verifications.plan_id',
                      'Verification.execution_id'}
    g = q(db, G.world_graph, ('plan', plan.id), 1, 500)
    assert ('verification', of_task.id) in keys(g) and ('verification', of_mission.id) in keys(g)
    sub = {e['from']['id']: e['to'] for e in g['edges'] if e['field'] == 'Verification.subject'}
    assert sub == {of_task.id: {'kind': 'task', 'id': t1.id},
                   of_mission.id: {'kind': 'mission', 'id': mid.id}}
    silent = SimpleNamespace(id=ids.new_id('verification'), plan_id=plan.id, execution_id=None,
                             subject=None)
    assert [e['field'] for e in held(db, 'verification', silent)] == ['verifications.plan_id']
    blank = SimpleNamespace(id=ids.new_id('verification'), plan_id=plan.id, execution_id=None,
                            subject=SimpleNamespace(kind='plan', id=''))
    assert [e['field'] for e in held(db, 'verification', blank)] == ['verifications.plan_id']
    assert held(db, 'verification', fake('verification', plan_id=None, execution_id=None,
                                         subject=None)) == []


def test_a_dependency_that_names_no_task_emits_no_edge(db, actor):
    """graph.py:158-163 - `Task.depends_on` is a JSON list read as
    written: a key no task in the plan holds, and the scalars a body can hold
    (an int, a null, an empty string), all hold no edge, and the neighbourhood
    built over them still answers."""
    prj, mid = a_project(), a_mission()
    plan = a_plan(mid.id)
    t1 = a_task(plan.id, mid.id, key='t1')
    t2 = a_task(plan.id, mid.id, key='t2', depends_on=('t1', 'no-such-key', 7, None, ''))
    put(db, actor, prj, mid, plan, t1, t2)
    deps = [e for e in held(db, 'task', row_of(db, E.Task, t2.id).entity)
            if e['field'] == 'Task.depends_on']
    assert [e['to']['id'] for e in deps] == [t1.id]
    assert [e['to']['kind'] for e in deps] == ['task']
    g = q(db, G.world_graph, ('task', t2.id), 1, 500)
    assert {e['field'] for e in g['edges']} == {'tasks.plan_id', 'Task.depends_on'}
    for e in g['edges']:
        assert isinstance(e['to']['id'], str) and e['to']['id']
    back = q(db, G.world_graph, ('task', t1.id), 1, 500)      # the same edge from the other
    assert ('task', t2.id) in keys(back)                      # end of the dependency


def test_a_dependency_that_holds_a_mapping_is_not_an_edge_and_not_a_crash(db, actor):
    """The same list, the one entry a JSON body can hold that the reader cannot:
    A4 says nothing here ranks, infers or raises."""
    prj, mid = a_project(), a_mission()
    plan = a_plan(mid.id)
    t1 = a_task(plan.id, mid.id, key='t1')
    t2 = a_task(plan.id, mid.id, key='t2', depends_on=('t1', {'key': 't1'}))
    put(db, actor, prj, mid, plan, t1, t2)
    deps = [e for e in held(db, 'task', row_of(db, E.Task, t2.id).entity)
            if e['field'] == 'Task.depends_on']
    assert [e['to']['id'] for e in deps] == [t1.id]


def test_only_the_last_pending_approval_of_a_mission_is_shown(db, actor):
    """graph.py:148-152 - the list shows the mission waiting on ONE approval:
    the decided ones are history and are never a node, and among the pending ones
    the view holds exactly the last row it read."""
    prj, mid = a_project(), a_mission()
    plan = a_plan(mid.id)
    first, last = an_approval(mid.id), an_approval(mid.id)
    decided = [an_approval(mid.id, state=st) for st in ('APPROVED', 'REJECTED', 'CONSUMED')]
    put(db, actor, prj, mid, plan, first, *decided, last)
    g = q(db, G.world_graph, ('mission', mid.id), 1, 500)
    (a,) = [e for e in g['edges'] if e['field'] == 'approvals.mission_id']
    assert a['to'] == {'kind': 'approval', 'id': last.id} and a['from']['id'] == mid.id
    assert ('approval', first.id) not in keys(g)
    assert not [n for n in g['nodes'] if n['kind'] == 'approval' and n['id'] != last.id]


def test_an_edge_to_a_cut_or_unloaded_node_is_never_drawn(db, actor):
    """graph.py:383-406 - the cap counts, it does not draw: an edge whose far end
    went to `cut` is dropped whole (not turned into an endpoint), an edge with
    neither end loaded never existed at all, and a kind with no table is an
    endpoint with `missing` False where a missing row of a real kind has it True."""
    focus = {'kind': 'mission', 'id': 'mission_a'}
    m = SimpleNamespace(entity=fake('mission', id='mission_a', project_id=None),
                        updated_at='2026-10-01T00:00:00.000Z')
    x = SimpleNamespace(entity=fake('execution', id='execution_x', task_id='task_t',
                                    mission_id='mission_a'),
                        updated_at='2026-10-01T00:00:00.000Z')
    loaded = {('mission', 'mission_a'): (0, m)}
    cut = {('execution', 'execution_x'): x}

    def edge(field, from_kind, from_id, to_kind, to_id):
        return {'from': {'kind': from_kind, 'id': from_id}, 'to': {'kind': to_kind, 'id': to_id},
                'field': field, 'rel': None, 'tier': None, 'inactive': False, 'structural': False}

    to_cut = edge('executions.mission_id', 'execution', 'execution_x', 'mission', 'mission_a')
    between = edge('missions.project_id', 'project', 'project_z', 'mission', 'mission_a')
    ghost = edge('relations.mentions', 'decision', 'decision_g', 'person', 'person_h')
    tableless = edge('Mission.origin_ref', 'mission', 'mission_a', 'message', 'message_m')
    g = G._assemble(7, focus, 1, 1, loaded, cut, {G._edge_key(e): e
                                                 for e in (to_cut, between, ghost, tableless)})
    assert [e['id'] for e in g['edges']] == ['Mission.origin_ref|mission:mission_a|'
                                             'message:message_m',
                                             'missions.project_id|project:project_z|'
                                             'mission:mission_a']
    assert keys(g) == [('mission', 'mission_a'), ('message', 'message_m'),
                       ('project', 'project_z')]
    assert g['nodes'][1]['endpoint'] is True and g['nodes'][1]['missing'] is False
    assert g['nodes'][1]['label'] == 'message message_m'
    assert g['nodes'][2]['missing'] is True            # a real kind, and the row is not there
    assert g['truncated'] is True and g['as_of_seq'] == 7
    assert g['hidden'] == [{'parent': {'kind': 'task', 'id': 'task_t'},
                            'kind': 'execution', 'count': 1}]
    text = json.dumps(g)
    assert 'execution_x' not in text and 'decision_g' not in text and 'person_h' not in text


def test_the_cap_never_draws_more_than_it_promised(db, neighbourhood):
    """graph.py:355-364 - the focus already occupies a seat: limit 0 and limit 1
    both answer the focus alone, and what was capped away is counted in `hidden`
    under its own parent (never drawn as a node with a missing id, and never as
    an edge with a cut end); limit 2 adds exactly one more node. The cap counts
    real neighbours only: the attempt whose own columns name a different mission
    is not a neighbour, so it is not counted either."""
    focus = ('mission', neighbourhood['mid'])
    g = q(db, G.world_graph, focus, 2, 0)
    assert keys(g) == [focus] and g['edges'] == [] and g['truncated'] is True
    assert g['limit'] == 0
    assert sum(h['count'] for h in g['hidden']) == 4     # project, plan, session, one attempt
    assert {h['kind'] for h in g['hidden']} == {'project', 'plan', 'session', 'execution'}
    assert [h['count'] for h in g['hidden'] if h['kind'] == 'execution'] == [1]
    assert all(h['parent'] in ({'kind': 'workspace', 'id': WS},
                               {'kind': 'mission', 'id': neighbourhood['mid']},
                               {'kind': 'task', 'id': neighbourhood['t1']}) for h in g['hidden'])
    one = q(db, G.world_graph, focus, 2, 1)
    assert keys(one) == [focus] and one['truncated'] is True  # the focus took the only seat
    assert json.dumps(one['hidden'], sort_keys=True) == json.dumps(g['hidden'], sort_keys=True)
    two = q(db, G.world_graph, focus, 2, 2)                   # one seat left: exactly one more
    assert keys(two)[0] == focus
    assert keys(two)[1] in ([('project', neighbourhood['prj']), ('plan', neighbourhood['plan']),
                             ('session', neighbourhood['ses']), ('execution', neighbourhood['x1'])])
    assert len(two['nodes']) == 2
    full = q(db, G.world_graph, focus, 2, 500)
    assert not full['truncated'] and len(full['nodes']) > 2   # the rest was only capped away


def test_the_world_level_caps_orders_by_state_and_counts_what_it_cut(db, actor):
    """graph.py:416-431 - an ARCHIVED project never outranks an ACTIVE one of a
    later name, the cap is the limit and what it cut is counted once, and a
    project with no rows at all reads as zeros rather than a null or a missing
    key."""
    zephyr, atlas = a_project('Zephyr'), a_project('Atlas')
    archived, empty = a_project('Aardvark', state='ARCHIVED'), a_project('Empty')
    mid = a_mission(project_id=atlas.id)
    put(db, actor, zephyr, atlas, archived, empty, mid)
    g = q(db, G.world_graph, None, None, 4)
    assert [n['id'] for n in g['nodes']] == [atlas.id, empty.id, zephyr.id, archived.id]
    assert g['nodes'][0]['counts'] == {'missions': 1, 'mission_states': {'CREATED': 1},
                                       'repositories': 0, 'sessions': 0, 'knowledge_items': 0}
    assert g['nodes'][3]['counts'] == {'missions': 0, 'mission_states': {}, 'repositories': 0,
                                       'sessions': 0, 'knowledge_items': 0}
    assert g['truncated'] is False and g['edges'] == [] and g['hidden'] == []
    two = q(db, G.world_graph, None, None, 2)
    assert [n['id'] for n in two['nodes']] == [atlas.id, empty.id]
    assert two['truncated'] is True and two['hidden'] == [
        {'parent': {'kind': 'workspace', 'id': WS}, 'kind': 'project', 'count': 2}]
    none = q(db, G.world_graph, None, None, 0)
    assert none['nodes'] == [] and none['edges'] == [] and none['truncated'] is True
    assert none['hidden'] == [{'parent': {'kind': 'workspace', 'id': WS},
                               'kind': 'project', 'count': 4}]
    assert none['depth'] == 1 and none['focus'] == {'kind': 'workspace', 'id': WS}


# -- A5: the stored import graph, its refusals and its errors -----------------

TREE = {'extractor_version': 1, 'truncated': False,
        'files': ['top.md', 'app/a/one.py', 'app/a/two.py', 'app/b/three.py', 'lib/io.py'],
        'edges': [['app/a/one.py', 'app/a/two.py'], ['app/a/one.py', 'lib/io.py'],
                  ['app/b/three.py', 'lib/io.py'], ['top.md', 'app/a/two.py']]}


def a_repo(db, actor, project_id, payload=None, *, sha=None, state='COMPLETED', revision='r1',
           last_revision='r1', architecture_state='CONSISTENT', attach=True, row=True):
    """A repository and its latest inspection. A dict payload goes to the store
    under its own content hash (a per-row nonce keeps each test's address unique,
    `_payload` being `lru_cache`d); with no payload the inspection records `sha`,
    which the test knows has no blob behind it. `attach=False` leaves the
    repository pointing at no inspection, `row=False` refuses to write the
    inspection at all."""
    rid, iid = ids.new_id('repository'), ids.new_id('repository_inspection')
    if isinstance(payload, dict):
        sha = store.put(json.dumps(dict(payload, _nonce=rid)).encode('utf-8'))
    ins = an_inspection(rid, id=iid, state=state, revision=revision, payload_sha256=sha)
    rep = a_repository(project_id, id=rid, last_inspection_id=iid if attach else None,
                       last_revision=last_revision, architecture_state=architecture_state)
    put(db, actor, rep, *([ins] if row else []))
    return rep.id


def rg(db, rep, focus='', depth=1, limit=500, read=None):
    return q(db, G.repository_graph, rep, store.get if read is None else read, focus, depth,
             limit)


def test_a_focus_outside_the_stored_tree_is_not_found(db, actor):
    """graph.py:487-492 - the view reads only what the payload recorded. A focus
    that is neither a recorded file nor a prefix of one, including the traversal a
    client may send, is NotFound and never a tree of its own; the slashes a caller
    may add are stripped, not trusted."""
    prj = a_project()
    put(db, actor, prj)
    rep = a_repo(db, actor, prj.id, TREE)
    for focus in ('nowhere', 'app/a/one.py/extra', '..', '../top.md', 'app/../../lib',
                  '/nowhere/', 'app/c', 'top.md/x', './app'):
        with pytest.raises(NotFound):
            rg(db, rep, focus)
    assert [n['id'] for n in rg(db, rep, '///')['nodes']] \
        == [n['id'] for n in rg(db, rep, '')['nodes']]
    top = rg(db, rep, '/app/a/')
    assert sorted(n['id'] for n in top['nodes'] if not n.get('endpoint')) \
        == ['app/a/one.py', 'app/a/two.py']


def test_a_repository_that_was_never_inspected_says_so_and_reads_nothing(db, actor):
    """graph.py:463-470 - the refusals that must never reach the artifact store:
    no `last_inspection_id`, an inspection id that names no row, a latest
    inspection that is not COMPLETED, and a COMPLETED inspection with no payload
    address (null or empty). The `read` raises, so a view that opened the store
    would fail here instead of passing."""
    prj = a_project()
    put(db, actor, prj)

    def hostile_read(sha):
        raise AssertionError('the artifact store was read for %s' % sha)

    no_link = a_repo(db, actor, prj.id, attach=False, row=False)
    assert rg(db, no_link)['reason'] == 'not_inspected'         # nothing recorded at all
    ghost = a_repo(db, actor, prj.id, attach=True, row=False)   # the id names no row
    assert rg(db, ghost, 'app', 2, 10, hostile_read)['reason'] == 'not_inspected'
    for state, sha in (('RUNNING', unique_sha('never-read')), ('FAILED', unique_sha('never-r2')),
                       ('SCHEDULED', unique_sha('never-r3')), ('COMPLETED', None)):
        rep = a_repo(db, actor, prj.id, state=state, sha=sha)   # never stored a payload
        g = rg(db, rep, 'app', 2, 10, hostile_read)
        assert g['available'] is False and g['reason'] == 'not_inspected', (state, sha)
        assert 'nodes' not in g and 'edges' not in g and 'revision' not in g
        assert g['repository_id'] == rep and g['focus'] == 'app' and g['depth'] == 2


def test_a_payload_that_cannot_be_read_is_payload_missing_and_logged_once_per_sha(
        db, actor, caplog):
    """graph.py:470-479 - the store may say no in every way it has: no file
    (OSError), bytes that are not JSON (ValueError) and the store's own KeyError.
    The view says so on EVERY read; the log says it once per address, and never
    for a payload that read fine."""
    prj = a_project()
    put(db, actor, prj)

    def not_json(sha):
        return b'this is not json'

    def boom(sha):
        raise KeyError(sha)

    rep_ok = a_repo(db, actor, prj.id, {'files': [], 'edges': []})
    rep_missing = a_repo(db, actor, prj.id, sha=unique_sha('logged-missing'))
    rep_bad = a_repo(db, actor, prj.id, sha=unique_sha('logged-not-json'))
    rep_key = a_repo(db, actor, prj.id, sha=unique_sha('logged-keyerror'))
    with caplog.at_level('WARNING', logger='archeus.core'):
        assert rg(db, rep_ok)['available'] is True             # read fine: never logged
        for rep, read in ((rep_missing, store.get), (rep_bad, not_json), (rep_key, boom)):
            for _ in range(3):                                 # and every later read too
                g = rg(db, rep, 'app', 1, 10, read)
                assert g['available'] is False and g['reason'] == 'payload_missing'
                assert 'nodes' not in g and 'edges' not in g   # nothing half-built
    said = [r.getMessage() for r in caplog.records if 'missing' in r.getMessage()]
    assert len(said) == 3, said                                # once per address, no more
    for sha in (rep_missing, unique_sha('logged-not-json'), unique_sha('logged-keyerror')):
        assert any(sha in s for s in said), sha


def test_a_payload_that_is_not_an_object_is_refused_like_an_unreadable_one(db, actor):
    """A5's contract is that a payload Core cannot use is *said*, not raised: the
    catch around `_payload` names OSError, KeyError, ValueError and LookupError."""
    prj = a_project()
    put(db, actor, prj)
    rep = a_repo(db, actor, prj.id, sha=unique_sha('not-an-object'))
    g = rg(db, rep, '', 1, 500, lambda sha: b'[1, 2, 3]')
    assert g['available'] is False and g['reason'] == 'payload_missing'


def test_payload_edges_of_the_wrong_shape_are_refused_like_an_unreadable_one(db, actor):
    """The same contract one level in: `edges` is the payload's own list."""
    prj = a_project()
    put(db, actor, prj)
    bad = dict(TREE, edges=[['app/a/one.py', 'app/a/two.py', 'app/b/three.py']])
    rep = a_repo(db, actor, prj.id, sha=unique_sha('bad-edges'))
    g = rg(db, rep, '', 1, 500, lambda sha: json.dumps(bad).encode('utf-8'))
    assert g['available'] is False and g['reason'] == 'payload_missing'


def test_the_tree_honours_the_focus_the_depth_and_the_limit(db, actor):
    """graph.py:493-546 - a directory focus folds what is below it at that depth
    and shows it whole one level deeper, the directories between are nodes whose
    parent is the directory the cap kept, the cap cuts the sorted name list and
    counts the rest under the focus, and an edge out of the focus's subtree is one
    `outside:` endpoint with its own label - never a whole directory."""
    prj = a_project()
    put(db, actor, prj)
    rep = a_repo(db, actor, prj.id, TREE)
    whole = rg(db, rep)
    assert [n['id'] for n in whole['nodes'] if not n.get('endpoint')] == ['app', 'lib', 'top.md']
    assert [n['id'] for n in whole['nodes'] if n['kind'] == 'file'] == ['top.md']
    one = rg(db, rep, 'app', 1)
    dirs = [n for n in one['nodes'] if not n.get('endpoint')]
    assert sorted(n['id'] for n in dirs) == ['app/a', 'app/b']
    assert {n['id']: n['counts']['files'] for n in dirs} == {'app/a': 2, 'app/b': 1}
    assert all(n['parent'] is None for n in dirs)            # the focus is their parent
    deep = rg(db, rep, 'app', 2)
    assert sorted(n['id'] for n in deep['nodes'] if not n.get('endpoint')) == [
        'app/a', 'app/a/one.py', 'app/a/two.py', 'app/b', 'app/b/three.py']
    assert {n['id'] for n in deep['nodes'] if n.get('endpoint')} == {'outside:lib',
                                                                    'outside:top.md'}
    (under,) = [n for n in deep['nodes'] if n['id'] == 'app/a/one.py']
    assert under['kind'] == 'file' and under['parent'] == {'kind': 'directory', 'id': 'app/a'}
    capped = rg(db, rep, 'app', 2, 3)                        # the cap takes three seats
    assert capped['truncated'] is True
    assert [n['id'] for n in capped['nodes'] if not n.get('endpoint')] == ['app/a', 'app/b',
                                                                          'app/a/one.py']
    assert capped['hidden'] == [{'parent': {'kind': 'directory', 'id': 'app'}, 'kind': 'path',
                                 'count': 2}]                # the focus holds the count
    (under,) = [n for n in capped['nodes'] if n['id'] == 'app/a/one.py']
    assert under['parent'] == {'kind': 'directory', 'id': 'app/a'}   # the ring it was kept in
    # an import into what the cap cut away is not drawn (it is counted under `hidden`), and
    # is not mistaken for an edge out of the focus either
    assert {(e['from']['id'], e['to']['id']) for e in capped['edges']} == {
        ('app/a/one.py', 'outside:lib')}
    outside = rg(db, rep, 'app/b', 1)
    ends = {n['id']: n for n in outside['nodes'] if n.get('endpoint')}
    assert list(ends) == ['outside:lib'] and ends['outside:lib']['missing'] is False
    assert ends['outside:lib']['label'] == 'lib/'
    assert {(e['from']['id'], e['to']['id']) for e in outside['edges']} == \
        {('app/b/three.py', 'outside:lib')}


def test_a_stale_or_mismatched_repository_is_said_stale(db, actor):
    """graph.py:477-485 - `stale` is the drift the assessment recorded OR a
    revision that no longer matches the inspection; neither is guessed from the
    tree, both come from the two rows, and the answer names the inspection it
    read."""
    prj = a_project()
    put(db, actor, prj)
    fresh = a_repo(db, actor, prj.id, TREE)
    assert rg(db, fresh)['stale'] is False
    drifted = a_repo(db, actor, prj.id, TREE, architecture_state='STALE')
    assert rg(db, drifted)['stale'] is True
    behind = a_repo(db, actor, prj.id, TREE, last_revision='r2')
    assert rg(db, behind)['stale'] is True
    g = rg(db, fresh)
    assert g['revision'] == 'r1' and g['inspected_at'] is None and g['extractor_version'] == 1
    assert g['extractor_truncated'] is False and g['as_of_seq'] >= 1


# -- boundary values ----------------------------------------------------------

def test_a_label_is_one_inert_line_of_at_most_the_cap(db, actor):
    """graph.py:63-67 - the exact cap, the cap plus one, the fold that must still
    be LABEL_MAX long, the control characters that are dropped, and the secret
    that never leaves the row. A label is the only free text the graph puts in
    front of a client, so its bounds are the bounds of what a client must render."""
    assert G.clean_label('') == '' and G.clean_label(None) == '' and G.clean_label(0) == ''
    assert G.clean_label(42) == '42'
    assert G.clean_label('a\t\n  b') == 'a b'
    assert G.clean_label('a\x00\x1b\t\n  b') == 'a b'
    assert 'sk-livekey' not in G.clean_label('sk-livekeyabcdef1234 leaked')
    assert '[redacted]' in G.clean_label('sk-livekeyabcdef1234 leaked')
    for n in (1, 59, G.LABEL_MAX - 1, G.LABEL_MAX):
        assert G.clean_label('x' * n) == 'x' * n
    for n in (G.LABEL_MAX + 1, G.LABEL_MAX + 40):
        cut = G.clean_label('x' * n)
        assert len(cut) == G.LABEL_MAX and cut == 'x' * (G.LABEL_MAX - 1) + '…'
    assert G.clean_label('x' * G.LABEL_MAX + '\n second line') == 'x' * (G.LABEL_MAX - 1) + '…'


def test_an_open_row_ranks_before_a_settled_one_and_a_row_without_a_time_still_sorts(db, actor):
    """graph.py:300-308 - the order is (hop, kind rank, settled, newest, id): an
    attempt that can still move beats one that cannot, a row the writer never
    stamped (`updated_at` NULL) sorts by an empty key instead of raising, and a
    kind with no machine is never "settled" - its row has no state to read."""
    t = ids.new_id('task')
    live = SimpleNamespace(entity=fake('execution', task_id=t, state='RUNNING'),
                           updated_at='2026-10-01T00:00:00.000Z')
    done = SimpleNamespace(entity=fake('execution', task_id=t, state='ENDED_OK'),
                           updated_at='2026-10-02T00:00:00.000Z')
    assert G._order_key('execution', live, 1)[2] is False
    assert G._order_key('execution', done, 1)[2] is True
    assert min(G._order_key('execution', done, 1), G._order_key('execution', live, 1)) \
        == G._order_key('execution', live, 1)                  # settled loses even when newer
    assert G._order_key('execution', live, 1)[:2] == (1, G.RANK['execution'])
    never_stamped = SimpleNamespace(entity=fake('execution', task_id=t, state='RUNNING'),
                                    updated_at=None)
    assert G._order_key('execution', never_stamped, 1)[3] == ()
    assert G._desc(None) == () and G._desc('a') > G._desc('b')     # descending as ascending
    project = SimpleNamespace(entity=fake('project', state=None), updated_at=None)
    assert G._order_key('project', project, 2)[:3] == (2, G.RANK['project'], False)


def test_an_endpoint_label_names_the_kind_and_the_head_of_its_id(db, actor):
    """graph.py:295-297 - an endpoint is the words for a kind plus the twelve
    leading characters of an id Core cannot resolve: never a whole address and
    never a body, and `missing` tells a tableless kind from a row that has gone."""
    e = G.endpoint({'kind': 'route_decision', 'id': 'x' * 30})
    assert e['label'] == 'route decision ' + 'x' * 12 and e['endpoint'] is True
    assert e['missing'] is False and e['kind'] == 'route_decision'
    assert set(e) == {'kind', 'id', 'endpoint', 'missing', 'label'}
    gone = G.endpoint({'kind': 'mission', 'id': ids.new_id('mission')}, missing=True)
    assert gone['missing'] is True and len(gone['label'].split()[-1]) == 12
    assert G.clean_label(gone['label']) == gone['label']       # already one inert line


def test_a_parent_that_is_not_recorded_is_no_parent(db, actor):
    """graph.py:104-128 - the containment column decides who a node collapses
    into, and a row whose column is empty has NO parent: never a parent with a
    null id, which a renderer would draw inside nothing. The fallbacks are the
    recorded ones only (a session falls back to its project, a route decision to
    its mission)."""
    prj, mid, pid, tid = (ids.new_id(k) for k in ('project', 'mission', 'plan', 'task'))
    assert G._parent('session', a_session(mission_id=mid, project_id=prj)) == \
        {'kind': 'mission', 'id': mid}
    assert G._parent('session', a_session(mission_id=None, project_id=prj)) == \
        {'kind': 'project', 'id': prj}
    assert G._parent('session', a_session(mission_id=None, project_id=None)) is None
    assert G._parent('route_decision', a_route_decision(task_id=tid, mission_id=mid)) == \
        {'kind': 'task', 'id': tid}
    assert G._parent('route_decision', a_route_decision(task_id=None, mission_id=mid)) == \
        {'kind': 'mission', 'id': mid}
    assert G._parent('route_decision', a_route_decision(task_id=None, mission_id=None)) is None
    assert G._parent('plan', a_plan(mid)) == {'kind': 'mission', 'id': mid}
    assert G._parent('task', a_task(pid, mid)) == {'kind': 'plan', 'id': pid}
    assert G._parent('task', fake('task', plan_id=None, mission_id=mid)) is None
    assert G._parent('execution', an_execution(tid, mid)) == {'kind': 'task', 'id': tid}
    assert G._parent('execution', fake('execution', task_id='', mission_id=mid)) is None
    assert G._parent('project', a_project()) is None           # a project holds itself
    assert G._parent('knowledge_item', a_knowledge(prj)) == {'kind': 'project', 'id': prj}
    assert G._parent('knowledge_item', fake('knowledge_item', project_id=None)) is None


def test_a_repository_label_is_the_last_part_of_its_path(db, actor):
    """graph.py:100-101 - the words for a repository are the last part of the path
    it recorded, with the separators the record may hold folded, and the path
    itself when nothing is left to show. Pure string work on the recorded text:
    nothing here asks the OS what a path means."""
    def label(**over):
        return G._label('repository', a_repository(ids.new_id('project'), **over))
    assert label(path='repo/Atlas') == 'Atlas'
    assert label(path='repo/Atlas/') == 'Atlas'
    assert label(path='libs\\sub\\core') == 'core'
    assert label(path='single') == 'single'
    assert label(path='///') == '///'                          # nothing left: the path itself
    assert label(path='repo/atlas.git') == 'atlas.git'


def test_a_route_decision_shows_selection_facts_and_counts_elimination_only(db, actor):
    """graph.py:282-287 and 47-49 - what a route decision may show is the six
    recorded selection fields plus the count of candidates the router dropped:
    its explanation, requirements, input snapshot and outcome never leave the
    row, a candidate that names no step is not counted, and a `fallback_from` the
    writer never filled reads as an empty list."""
    prj, mid = a_project(), a_mission()
    plan = a_plan(mid.id)
    t1 = a_task(plan.id, mid.id)
    rd = a_route_decision(task_id=t1.id, mission_id=mid.id, harness_id='fake', model='m-large',
                          effort='high', result='selected', fallback_from=None,
                          explanation='SECRET-ROUTING', requirements={'tier': 'large'},
                          input_snapshot={'body': 'SECRET-BODY'}, outcome={'r': 'SECRET-OUTCOME'},
                          candidates=({'eliminated_at_step': 'health'},
                                      {'eliminated_at_step': None},
                                      {'eliminated_at_step': ''}, {'other': 'step'}))
    put(db, actor, prj, mid, plan, t1, rd)
    node = q(db, lambda conn: G.node_of('route_decision', row_of(db, E.RouteDecision, rd.id)))
    assert set(node) == {'kind', 'id', 'label', 'parent', 'attrs'}
    assert node['attrs'] == {'harness_id': 'fake', 'account_id': None, 'model': 'm-large',
                             'effort': 'high', 'result': 'selected', 'fallback_from': [],
                             'eliminated': 1}
    assert node['parent'] == {'kind': 'task', 'id': t1.id} and node['label'] == 'fake · m-large'
    text = json.dumps(node)
    for secret in ('SECRET-ROUTING', 'SECRET-BODY', 'SECRET-OUTCOME', 'explanation',
                   'requirements', 'input_snapshot', 'candidates', 'health'):
        assert secret not in text
    bare = a_route_decision(harness_id=None, model=None, task_id=None, mission_id=mid.id)
    put(db, actor, bare)
    assert q(db, lambda conn: G.node_of('route_decision',
                                        row_of(db, E.RouteDecision, bare.id)))['label'] \
        == 'Route decision'


# -- idempotency and replay ---------------------------------------------------

def test_the_same_request_replayed_answers_the_same_bytes(db, actor, neighbourhood):
    """A4, A5, A6 replay: nothing here writes, infers or ranks by hand, so the
    same call twice - with an unrelated read in between - is the same JSON at the
    same `as_of_seq`; a stored payload answers the same however often the tree is
    asked for, and only a mutation moves the cursor."""
    focus = ('mission', neighbourhood['mid'])
    a = q(db, G.world_graph, focus, 2, 50)
    b = q(db, G.world_graph, focus, 2, 50)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a['as_of_seq'] == b['as_of_seq'] == q(db, outbox_head)
    q(db, G.world_graph, ('task', neighbourhood['t1']), 1, 5)
    assert json.dumps(q(db, G.world_graph, focus, 2, 50), sort_keys=True) \
        == json.dumps(a, sort_keys=True)
    prj = a_project(name='Second')
    put(db, actor, prj)
    rep = a_repo(db, actor, prj.id, TREE)
    first = rg(db, rep, 'app', 2)
    rg(db, rep, 'lib', 1)
    rg(db, rep, '', 1)
    again = rg(db, rep, 'app', 2)
    assert json.dumps(first, sort_keys=True) == json.dumps(again, sort_keys=True)
    assert again['as_of_seq'] == first['as_of_seq']
    world = q(db, G.world_graph, None, None, 500)
    put(db, actor, a_knowledge(prj.id, title='Another fact'))
    later = q(db, G.world_graph, None, None, 500)
    assert later['as_of_seq'] > world['as_of_seq']             # only a write moves the cursor
    assert json.dumps(later, sort_keys=True) != json.dumps(world, sort_keys=True)
