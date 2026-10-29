"""T-144 slice 4 fix round 2: what a size cap, a model prompt or a hand-off turn
carries of an account home. A cap cuts without splitting a home, the planner's
replan prompt and the hand-off's assistant turns are projected with the live
homes, and the registry half of the writer binding is pinned. Stored rows stay raw."""

import json

from archeus.core import ports
from archeus.core.application import queries, sessions
from archeus.core.domain import entities, ids
from archeus.infra.artifacts import store
from v1.integration.test_planning import ONE, fake, make  # noqa: F401  (make is a fixture)
from v1.integration.test_policy import Rig as PolicyRig
from v1.integration.test_routing import Rig, task
from v1.integration.test_t144_leak_sweep import HomeCaller
from v1.integration.test_t144_live_bound_writes import (  # noqa: F401
    _bind, _live, _session_world, new_event_created, no_8dot3_probe)


class _Registry:
    def __init__(self, adapter):
        self.adapter = adapter

    def ids(self):
        return [self.adapter.id]

    def get(self, _):
        return self.adapter


def test_S1_a_default_home_known_only_to_the_bound_registry_is_scrubbed(db, tmp_path):
    r, live, sid, _ = _session_world(db, tmp_path)
    db.writer.live = (_Registry(HomeCaller(live, 'registry-only')), ())
    out = r.do(sessions.resume, who=r.user, session_id=sid, request_id='r1')
    text = store.get(out['artifact_sha']).decode('utf-8')
    assert live not in text and 'its home/settings.json' in text


def test_R1_the_replan_prompt_projects_checkpoint_open_problems(make, tmp_path):  # noqa: F811
    f = fake(ONE)
    r = make([f], policy='ALLOW')
    live = _bind(r.db, tmp_path)
    r.scenarios['t1'] = [{'emit': {'type': 'stderr',
                                   'text': 'cannot read ' + live + '/settings.json'}},
                         {'exit': 1}]
    r.mission()
    r.settle()
    assert live in ' '.join(r.all(entities.Checkpoint)[0].open_problems), 'the row stays raw'
    replans = [p for _, p in f.sent if 'Where t1 stopped' in p]
    assert replans and all(live not in p for _, p in f.sent)
    assert 'cannot read its home/settings.json' in replans[0]


def _cut_world(db, tmp_path):
    r = Rig(db)
    live = _bind(db, tmp_path)
    mid = r.ready()
    return r, live, r.one(entities.Execution, id=r.dispatch(mid)['execution_id'])


def _event_payload(db, type_, subject):
    with db.read() as conn:
        (payload,) = [json.loads(p) for (p,) in conn.execute(
            'SELECT payload FROM events WHERE type = ? AND subject_id = ?', (type_, subject))]
    return payload


def test_R2_a_home_cut_by_the_checkpoint_cap_leaves_no_readable_prefix(db, tmp_path):
    from archeus.core.application import executions
    from archeus.core.execution import checkpoint
    r, live, ex = _cut_world(db, tmp_path)
    pad = 'x' * (300 - len('last error: ') - 16) + ' '
    r.do(checkpoint.derive, execution=ex, facts={'last_error': pad + live + '/x'})
    cp = r.one(entities.Checkpoint, execution_id=ex.id)
    assert cp.open_problems == ('last error: ' + pad,)
    with db.read() as conn:
        api = executions.checkpoints(conn, ex.id)[0]['open_problems']
    assert live[:15] not in store.get(cp.artifact_sha).decode('utf-8')
    assert list(api) == ['last error: ' + pad]


def test_R2_the_manager_facts_keep_enough_for_the_writer_to_cut_safely(db, tmp_path):
    from archeus.core.execution import checkpoint
    from archeus.core.execution.manager import _facts_from
    r, live, ex = _cut_world(db, tmp_path)
    p = {'decisions': [], 'last_error': None}
    _facts_from({'type': 'stderr', 'text': 'x' * 271 + ' ' + live + '/x'}, p)
    r.do(checkpoint.derive, execution=ex, facts=dict(p))
    assert live[:15] not in ' '.join(r.one(entities.Checkpoint, execution_id=ex.id).open_problems)


def test_R2_a_handoff_reason_cut_at_500_does_not_split_a_home(db, tmp_path):
    r, live, sid, _ = _session_world(db, tmp_path)
    _bind(db, tmp_path)
    pad = 'y' * (500 - 16) + ' '
    t = r.do(sessions.handoff, who=r.user, source_session_id=sid, request_id='h1',
             harness_id='fake', reason=pad + live + '/x')
    assert _event_payload(db, 'session.handed_off', t['id'])['reason'] == pad


def test_R2_a_hook_reason_cut_at_500_does_not_split_a_home(db, tmp_path):
    from archeus.core.application import executions
    r, live, ex = _cut_world(db, tmp_path)
    pad = 'z' * (500 - 16) + ' '
    r.do(lambda tx, *, actor: executions._hook_answer(tx, actor, ex, None, 'deny', pad + live))
    assert _event_payload(db, 'execution.hook', ex.id)['reason'] == pad


def test_R2_a_progress_line_cut_at_200_does_not_split_a_home(db, tmp_path):
    from archeus.core.application import executions
    from archeus.core.execution.manager import line_of
    r, live, ex = _cut_world(db, tmp_path)
    pad = 'w' * (200 - len('stderr: ') - 16) + ' '
    line = line_of({'type': 'stderr', 'text': pad + live + '/x'})
    r.do(executions.record_progress, execution_id=ex.id, offset=10, events=1, lines=[line])
    assert _event_payload(db, 'execution.progress', ex.id)['last'] == ['stderr: ' + pad]


def test_S3_a_handoff_without_a_mission_scrubs_assistant_turns_and_keeps_user_turns(db, tmp_path):
    r = Rig(db)
    live = _bind(db, tmp_path)
    sid = ids.new_id('session')

    def session(tx, *, actor):
        tx.insert(entities.Session(id=sid, harness_id='fake', workspace_id=ids.GLOBAL_WORKSPACE,
                                   cwd=str(tmp_path), mode='interactive_attached'), actor=actor)
        tx.append(new_event_created(sid, None, actor))
    r.do(session)
    t = r.do(sessions.handoff, who=r.user, source_session_id=sid, request_id='h1',
             harness_id='fake', turns=[['user', 'look at ' + live],
                                       ['assistant', 'I read ' + live + '/settings.json'],
                                       ['system', 'cwd ' + live]])
    text = store.get(t['handoff_artifact_sha']).decode('utf-8')
    assert 'I read its home/settings.json' in text and 'cwd its home' in text
    assert 'look at ' + live in text and text.count(live) == 1


def test_get_plan_orders_numeric_keys_first_then_plain_and_never_raises(db):
    r = Rig(db)

    def keys(*names):
        mid = r.ready(*[task(k, 'write_repo') for k in names])
        with db.read() as conn:
            return [x['key'] for x in queries.get_plan(
                conn, queries.get_mission(conn, mid)['plan_id'])['tasks']]
    assert keys('t2', 'work', 't10') == ['t2', 't10', 'work']
    assert keys('b', 'a', 'c') == ['a', 'b', 'c']
    assert keys('t10', 't2', 't1') == ['t1', 't2', 't10']


def test_the_policy_simulation_echoes_the_caller_and_the_stored_rules_not_system_text(
        db, tmp_path):
    r = PolicyRig(db)
    live = _live(tmp_path)
    r.db.writer.live = (None, [HomeCaller(live, 'live-only')])
    mid = r.mission(title='work in ' + live)
    with r.db.read() as conn:
        out = r.authz.simulate(conn, now='2026-09-26T00:00:00Z', mission_id=mid,
                               action={'class': 'git_push', 'target': 'origin/x'})
    assert out['simulated'] and live not in json.dumps(out)


def _req(db, caller, **params):
    from types import SimpleNamespace
    resources = SimpleNamespace(registry=None, callers=[caller])
    return SimpleNamespace(api=SimpleNamespace(db=db, resources=resources), params=params, query={})


def _live_homes(db, live):
    from archeus.core.application import resources
    with db.read() as conn:
        return resources.homes(conn, None, [HomeCaller(live, 'live-only')])


def test_get_mission_projects_its_embedded_context_package_with_the_read_homes(db, tmp_path):
    from archeus.core.domain.events import new_event
    from archeus.core.domain.values import Ref
    from archeus.infra.eventlog import outbox
    r = Rig(db)
    live = _live(tmp_path)
    mid = r.ready()
    pkg_id = ids.new_id('context_package')
    with db.read() as conn:
        head = outbox.head(conn)

    def seed(tx, *, actor):
        tx.insert(entities.ContextPackage(
            id=pkg_id, workspace_id=ids.GLOBAL_WORKSPACE, subject_kind='mission', subject_id=mid,
            as_of_seq=head, items=({'ref': {'kind': 'event', 'id': 'e'}, 'level': 'L3',
                                    'store': 'history', 'type': 'x', 'reason': 'at ' + live},)),
            actor=actor)
        tx.update(entities.Mission, mid, {'context_package_id': pkg_id}, actor=actor)
        tx.append(new_event('context_package.created', Ref('context_package', pkg_id), actor,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    r.do(seed)
    homes = _live_homes(db, live)
    with db.read() as conn:
        got = queries.get_mission(conn, mid, homes=homes)['context_package']['items'][0]['reason']
        assert queries.get_context_package(conn, pkg_id, homes=homes)['items'][0]['reason'] == got
    assert got == 'at its home'
    from archeus.api import routes
    body = routes.get_mission(_req(db, HomeCaller(live, 'live-only'), id=mid))[1]
    assert body['context_package']['items'][0]['reason'] == 'at its home'


def test_execution_why_and_handoff_reason_project_recorded_reasons_with_the_read_homes(
        db, tmp_path):
    import dataclasses
    from archeus.core.application import executions, live as live_work
    from archeus.core.domain.events import new_event
    from archeus.core.domain.values import Ref
    r, live, ex = _cut_world(db, tmp_path)
    child = dataclasses.replace(ex, id=ids.new_id('execution'), handoff_from=ex.id, attempt=ex.attempt + 1)
    asking = dataclasses.replace(ex, id=ids.new_id('execution'), state='HANDING_OFF',
                                 attempt=ex.attempt + 2)

    def seed(tx, *, actor):
        tx.append(new_event('execution.state_changed', Ref('execution', ex.id), actor, payload={
            'from': 'RUNNING', 'to': 'HANDING_OFF', 'reason': 'read ' + live + '/settings.json'}))
        tx.insert(child, actor=actor)
        tx.insert(asking, actor=actor)
        tx.append(new_event('execution.state_changed', Ref('execution', asking.id), actor, payload={
            'from': 'RUNNING', 'to': 'HANDING_OFF', 'reason': 'pressure at ' + live}))
        tx.append(new_event('execution.state_changed', Ref('execution', child.id), actor, payload={
            'from': 'STARTING', 'to': 'RUNNING', 'reason': 'ok'}))
    r.do(seed)
    homes = _live_homes(db, live)
    with db.read() as conn:
        shown = executions.view(conn, child.id, homes=homes)
        raw = executions.view(conn, child.id)
        direct = live_work.explain(conn, ex, homes)
    assert live in raw['handoff']['reason'] and live in raw['why'], 'the control: no homes'
    assert shown['handoff']['reason'] == 'read its home/settings.json'
    assert live not in shown['why'] and 'its home/settings.json' in shown['why']
    assert live not in direct
    with db.read() as conn:
        (item,) = [w for w in live_work.live_work(conn, homes=homes) if w['id'] == asking.id]
    assert item['handing_off'] == 'pressure at its home'
    from archeus.api import routes
    body = routes.get_execution(_req(db, HomeCaller(live, 'live-only'), id=child.id))[1]
    assert body['handoff']['reason'] == 'read its home/settings.json' and live not in body['why']


def test_status_knowledge_pass_reason_is_projected_with_the_read_homes(db, tmp_path):
    from archeus.core.application import calls, resources
    from archeus.core.world import status
    r = Rig(db)
    live = _live(tmp_path)
    project = ids.new_id('project')

    def seed(tx, *, actor):
        from archeus.core.domain.events import new_event
        from archeus.core.domain.values import Ref
        tx.insert(entities.Project(id=project, workspace_id=ids.GLOBAL_WORKSPACE, name='P'),
                  actor=actor)
        tx.append(new_event('project.created', Ref('project', project), actor,
                            payload={'name': 'P'}, workspace=ids.GLOBAL_WORKSPACE))
    r.do(seed)
    caller = HomeCaller(live)
    r.do(calls.decide_provider_terms, who=r.user, harness_id=caller.id, headless='permitted')
    with db.read() as conn:
        req, snap, _ = resources.call_snapshot(
            conn, callers=[caller], feed=r.feed, preference=ports.OwnCallPreference(),
            purpose='knowledge_extraction', schema=None, project_id=project, min_tier=None)
    got = r.do(resources.record_call_route, purpose='knowledge_extraction',
               source={'kind': 'repository_inspection', 'id': ids.new_id('repository_inspection')},
               workspace_id=ids.GLOBAL_WORKSPACE, project_id=project, requirements=req,
               snapshot=snap)
    r.do(calls.end_call, route_decision_id=got['route_decision_id'],
         outcome={'state': 'failed', 'reason': 'could not read ' + live})
    with db.read() as conn:
        homes = resources.homes(conn, None, [caller])
        body = status.status(conn, project, homes)['projects'][0]['knowledge_pass']
    assert body['reason'] == 'could not read its home'
    from archeus.api import routes
    served = routes.status(_req(db, caller))[1]['projects'][0]['knowledge_pass']
    assert served['reason'] == 'could not read its home'
