"""T-144 slice 3 over a real database: the event and text surfaces S12-S23 leave
the store untouched and read without a home or a default account key."""

import json
from copy import deepcopy

import pytest

from archeus.core import ports
from archeus.core.application import attention, calls, commands, executions, queries, resources, trace
from archeus.core.context import assemble as A
from archeus.core.domain import entities, ids
from archeus.core.domain.actions import Action
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes, public_account_id
from archeus.infra.db import rows
from v1.integration.test_automation import rig  # noqa: F401  (fixture)
from v1.integration.test_planning import ONE, fake, make  # noqa: F401  (make is a fixture)
from v1.integration.test_routing import Rig
from v1.integration.test_t144_leak_sweep import _no_leak, _record_call


@pytest.fixture(autouse=True)
def no_8dot3_probe(monkeypatch):
    monkeypatch.setattr('archeus.core.homes._win_short', lambda _: None)


def _events_table(conn):
    return [tuple(r) for r in conn.execute('SELECT * FROM events ORDER BY seq')]


def _stored(conn):
    return {t: [tuple(r) for r in conn.execute('SELECT * FROM %s ORDER BY id' % t)]
            for t in ('route_decisions', 'policy_decisions', 'context_packages')} | {
        'events': _events_table(conn)}


def _append(r, specs, *, actor=None, mission=None):
    m = r.m(mission) if mission else None

    def cmd(tx, *, actor):
        return [tx.append(new_event(
            type_, subject, actor, payload=payload,
            workspace=m.workspace_id if m else ids.GLOBAL_WORKSPACE,
            project=m.project_id if m else None)).seq for type_, subject, payload in specs]
    return r.do(cmd, who=actor or r.user)


def _world(db, tmp_path):
    r = Rig(db)
    home = str(tmp_path / 'Work-Claude')
    r.account('Work', home_ref=home)
    dhome = str(tmp_path / 'Default-Claude')
    rd_id, key = _record_call(r, dhome)
    r.do(calls.end_call, route_decision_id=rd_id, outcome={
        'state': 'failed', 'account_ref': key, 'reason': 'stderr ' + home + ' and ' + dhome,
        'unlisted': {'nested': [{'deep': 'on ' + key}]}})
    return r, home, dhome, key, rd_id, r.ready()


def _seed_events(r, mid, home, dhome, key):
    ref = Ref('mission', mid)
    return _append(r, [
        ('mission.state_changed', ref, {'from': 'A', 'to': 'B',
                                        'reason': 'waiting on ' + key + ' in ' + home,
                                        'unlisted': {'deep': [{'x': dhome}]}}),
        ('mission.updated', ref, {'fields': ['requirements'],
                                  'added': {'requirements': [{'text': home}], 'constraints': []},
                                  'resource_preferences': {'preferred_accounts': [key]}}),
        ('mission.created', ref, {'title': home, 'origin': 'user', 'origin_ref': dhome}),
    ], mission=mid)


def _expected(home, dhome, key):
    pid = public_account_id(key)
    return {'mission.state_changed': {'from': 'A', 'to': 'B',
                                      'reason': 'waiting on ' + pid + ' in its home',
                                      'unlisted': {'deep': [{'x': 'its home'}]}},
            'mission.updated': {'fields': ['requirements'],
                                'added': {'requirements': [{'text': home}], 'constraints': []},
                                'resource_preferences': {'preferred_accounts': [pid]}},
            'mission.created': {'title': home, 'origin': 'user', 'origin_ref': 'its home'}}


def test_S12_S18_S19_events_timeline_and_trace_project_payloads_and_store_nothing(db, tmp_path):
    r, home, dhome, key, rd_id, mid = _world(db, tmp_path)
    seqs = _seed_events(r, mid, home, dhome, key)
    want = _expected(home, dhome, key)
    with db.read() as conn:
        before = _stored(conn)
        rd = rows.get(conn, entities.RouteDecision, rd_id).entity
        replayed = resources.replay(rd)
        paged = queries.events(conn, 0, limit=1000)
        one_page = queries.events(conn, seqs[0] - 1, limit=3)
        line = attention.timeline(conn, mid, limit=100)['events']
        traced = trace.trace(conn, mid, r.registry)
        assert _stored(conn) == before
        assert resources.replay(rd) == replayed
    for body in (paged, one_page, line, traced['events']):
        got = {e['seq']: e['payload'] for e in body if e['seq'] in seqs}
        assert got == dict(zip(seqs, [want['mission.state_changed'], want['mission.updated'],
                                      want['mission.created']]))
    ended = next(e for e in paged if e['type'] == 'archeus_call.ended')
    assert ended['payload']['outcome']['account_ref'] == public_account_id(key)
    assert ended['payload']['outcome']['reason'] == 'stderr its home and its home'
    assert ended['payload']['outcome']['unlisted'] == {
        'nested': [{'deep': 'on ' + public_account_id(key)}]}
    for body in (paged, line, traced['events']):
        _no_leak([e for e in body if e['type'] != 'mission.created'
                  and e['payload'].get('added') is None], [home, dhome], [key])


def test_event_exemptions_follow_provenance_not_the_actor_on_real_rows(db, tmp_path):
    r, home, dhome, key, _, mid = _world(db, tmp_path)
    ref = Ref('mission', mid)
    (user_system_text,) = _append(r, [('mission.state_changed', ref, {'reason': home})],
                                  mission=mid)
    (system_authored,) = _append(r, [('mission.created', ref, {'title': dhome})],
                                 actor=r.system, mission=mid)
    with db.read() as conn:
        got = {e['seq']: e for e in queries.events(conn, user_system_text - 1)}
    assert got[user_system_text]['actor']['kind'] == 'user_device'
    assert got[user_system_text]['payload'] == {'reason': 'its home'}
    assert got[system_authored]['actor']['kind'] == 'system'
    assert got[system_authored]['payload'] == {'title': dhome}


def test_S17_S17a_policy_decisions_project_action_and_items_directly_and_in_trace(db, tmp_path):
    r, home, dhome, key, _, mid = _world(db, tmp_path)
    did = ids.new_id('policy_decision')
    item = {'task': 't1', 'decision': 'DENY', 'reason': 'a read of ' + home,
            'action': {'class': 'write_repo', 'target': home + '/x', 'paths': [home],
                       'argv': ['cat', dhome], 'unlisted': {'n': [key]}}}

    def seed(tx, *, actor):
        tx.insert(entities.PolicyDecision(
            id=did, decision='DENY', stage='action', mission_id=mid, outcome='deny',
            reason='denied ' + home, action=Action(action_class='write_repo', target=home + '/x',
                          argv=('cat', dhome), paths=(home,)),
            items=(item,), matched_rules=({'pattern': home + '/*'},)), actor=actor)
        tx.append(new_event('policy_decision.created', Ref('policy_decision', did), actor,
                            payload={'stage': 'action'}))
    r.do(seed)
    with db.read() as conn:
        before = _stored(conn)
        one = queries.get_policy_decision(conn, did)
        listed = {d['id']: d for d in queries.list_policy_decisions(conn, mid)}
        in_trace = {d['id']: d for d in trace.trace(conn, mid, r.registry)['policy_decisions']}
        assert _stored(conn) == before
    for body in (one, listed[did], in_trace[did]):
        assert body['reason'] == 'denied its home'
        assert body['action']['target'] == 'its home/x'
        assert body['action']['paths'] == ['its home'] and body['action']['argv'] == ['cat', 'its home']
        assert body['items'][0]['action'] == {
            'class': 'write_repo', 'target': 'its home/x', 'paths': ['its home'],
            'argv': ['cat', 'its home'], 'unlisted': {'n': [public_account_id(key)]}}
        assert body['items'][0]['reason'] == 'a read of its home'
        assert list(body['matched_rules']) == [{'pattern': home + '/*'}]


def test_S23a_trace_lanes_scrub_agent_output_before_the_text_is_cut(db, tmp_path, monkeypatch):
    r, home, dhome, key, _, mid = _world(db, tmp_path)
    r.dispatch(mid)
    long_text = 'x' * 480 + ' ' + home + '/projects/a.jsonl and ' + key
    stored = {'execution_id': 'e', 'offset': 0, 'next_offset': 9, 'truncated': False,
              'available': True, 'events': [
                  {'type': 'assistant', 'text': long_text},
                  {'type': 'tool', 'name': 'Read', 'id': 'c1', 'lane': 'main'},
                  {'type': 'tool_result', 'tool_use_id': 'c1', 'is_error': False,
                   'text': home}]}
    monkeypatch.setattr(trace.output, 'read', lambda e, adapter, offset=0: deepcopy(stored))
    with db.read() as conn:
        got = trace.trace(conn, mid, r.registry)
    (ex,) = got['executions']
    (lane,) = ex['lanes']
    assert lane['steps'][0]['text'] == ('x' * 480 + ' its home/projects/a.jsonl and ' + public_account_id(key))[:500]
    _no_leak(got['executions'], [home, dhome], [key])


# ── S20 context ──

def _account_row(h, home):
    return h.run(resources.register_account, harness_id='fake', label='A',
                 auth_kind='api_key', home_ref=home)


@pytest.fixture
def harness(db, tmp_path):
    from v1.integration.test_world import Harness
    home = tmp_path / 'Work-Claude'
    parent = home / 'repos'
    parent.mkdir(parents=True)
    return Harness(db, str(parent)), str(home)


def _project_with_history(h, home, payload):
    repo = h.register('layered-python')
    pid = repo.project_id
    h.pump()
    _account_row(h, home)
    h.db.writer.execute(lambda tx, *, actor: tx.append(new_event(
        'project.changed', Ref('project', pid), actor, project=pid, payload=payload)),
        {'actor': h.user})
    mid = h.run(commands.create_mission, title='Dashboard', objective='o', project_id=pid)['id']
    return repo, pid, mid


def test_S20_new_history_text_is_built_from_the_projected_payload(harness):
    h, home = harness
    _, pid, mid = _project_with_history(h, home, {'why': 'seen ' + home, 'unlisted': {'n': [home]}})
    for homes in (None, Homes([home], shorts=lambda _: None)):
        with h.db.read() as conn:
            before = _stored(conn)
            g = A.gather(conn, 'mission', mid, homes)
            assert _stored(conn) == before
        hist = [c for c in g['candidates'] if c['store'] == 'history' and c['type'] == 'project.changed']
        assert hist and all(home not in c['text'] and 'its home' in c['text'] for c in hist)


def test_S20_a_recorded_package_is_scrubbed_at_write_and_reads_back_projected(harness):
    h, home = harness
    repo, pid, mid = _project_with_history(h, home, {'why': 'x'})
    for t in ('start', 'understood'):
        h.run(commands.Missions(policy=ports.AllowAllPolicy()).fire, mission_id=mid,
              trigger=t, reason='test')
    pkg_id = h.db.writer.execute(commands.Missions(policy=ports.AllowAllPolicy()).context_ready,
                                 {'actor': h.system, 'mission_id': mid})['context_package_id']
    with h.db.read() as conn:
        stored = rows.get(conn, entities.ContextPackage, pkg_id).entity.to_dict()
        raw = A.assemble(conn, 'mission', mid, homes=Homes([], shorts=lambda _: None))
        got = queries.get_context_package(conn, pkg_id)
    assert any(home in i['reason'] for i in raw['items']), 'the fixture must put a home in a reason'
    _no_leak(stored, [home], [])
    assert any('its home' in i['reason'] for i in stored['items'])
    assert json.loads(json.dumps(got)) == json.loads(json.dumps(
        dict(stored, version=got['version'], created_at=got['created_at'],
             updated_at=got['updated_at'])))


def test_S20_a_historical_package_is_projected_on_get_and_in_its_mission(harness):
    h, home = harness
    _, pid, mid = _project_with_history(h, home, {'why': 'x'})
    pkg_id = ids.new_id('context_package')
    items = ({'ref': {'kind': 'event', 'id': 'e', 'seq': 1}, 'level': 'L3', 'store': 'history',
              'type': 'x', 'reason': 'was at ' + home, 'text': 'on ' + home,
              'unlisted': {'deep': [home]}},)

    def seed(tx, *, actor):
        tx.insert(entities.ContextPackage(
            id=pkg_id, workspace_id=ids.GLOBAL_WORKSPACE, subject_kind='mission', subject_id=mid,
            project_id=pid, query=home, items=items, missing_information=(home + ' is gone',)),
            actor=actor)
        tx.update(entities.Mission, mid, {'context_package_id': pkg_id}, actor=actor)
        tx.append(new_event('context_package.created', Ref('context_package', pkg_id), actor,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    h.db.writer.execute(seed, {'actor': h.system})
    with h.db.read() as conn:
        before = _stored(conn)
        direct = queries.get_context_package(conn, pkg_id)
        via_mission = queries.get_mission(conn, mid)['context_package']
        assert _stored(conn) == before
        raw = rows.get(conn, entities.ContextPackage, pkg_id).entity
    assert raw.items == items and raw.query == home
    for body in (direct, via_mission):
        assert body['query'] == home
        assert body['items'][0]['reason'] == 'was at its home'
        assert body['items'][0]['text'] == 'on its home'
        assert body['items'][0]['unlisted'] == {'deep': ['its home']}
        assert body['missing_information'] == ['its home is gone']


def test_S20_a_reused_historical_package_reaches_the_planner_projected(
        make, tmp_path, monkeypatch):  # noqa: F811
    from archeus.core.planning import worker as W
    from archeus.infra.eventlog import outbox

    r = make([fake(ONE)], policy='ALLOW')
    home = str(tmp_path / 'Work-Claude')
    r.run(resources.register_account, harness_id='zzz', label='A', auth_kind='api_key',
          home_ref=home)
    mid = r.mission()
    r.to_reasoning(mid)
    seq = [e['seq'] for e in r.events('mission.state_changed')
           if e['payload']['to'] == 'REASONING'][-1]
    pkg_id = ids.new_id('context_package')
    with r.db.read() as conn:
        head = outbox.head(conn)

    def seed(tx, *, actor):
        tx.insert(entities.ContextPackage(
            id=pkg_id, workspace_id=ids.GLOBAL_WORKSPACE, subject_kind='mission', subject_id=mid,
            as_of_seq=head, items=({'ref': {'kind': 'event', 'id': 'e'}, 'level': 'L3',
                                    'store': 'history', 'type': 'x', 'reason': 'at ' + home},)),
            actor=actor)
        tx.update(entities.Mission, mid, {'context_package_id': pkg_id}, actor=actor)
        tx.append(new_event('context_package.created', Ref('context_package', pkg_id), actor,
                            payload={}, workspace=ids.GLOBAL_WORKSPACE))
    r.sys(seed)
    seen = []
    real = W.planner.describe
    monkeypatch.setattr(W.planner, 'describe', lambda conn, pkg, m: seen.append(pkg) or real(conn, pkg, m))
    assert r.planner.plan(mid, seq, 'first plan').startswith('plan:')
    assert [p['id'] for p in seen] == [pkg_id]
    assert seen[0]['items'][0]['reason'] == 'at its home'
    with r.db.read() as conn:
        assert rows.get(conn, entities.ContextPackage, pkg_id).entity.items[0]['reason'] == 'at ' + home


def test_S21_automation_render_is_projected_and_matching_keeps_the_raw_payload(
        rig, tmp_path):  # noqa: F811
    home = str(tmp_path / 'Work-Claude')
    rig.do(resources.register_account, harness_id='zzz', label='A', auth_kind='api_key',
           home_ref=home)
    rig.automation(trigger={'type': 'mission.state_changed',
                            'where': {'reason': {'glob': '*Work-Claude*'}}},
                   template={'title': 'saw {payload.reason}', 'objective': 'obj {payload.reason}'})
    mid = rig.seed(title='other')
    seq = rig.raw('mission.state_changed', Ref('mission', mid), {'to': 'CREATED', 'reason': 'read ' + home + '/x'})
    rig.pump()
    (made,) = rig.made()
    assert (made.title, made.objective) == ('saw read its home/x', 'obj read its home/x')
    (run,) = [x for x in rig.runs() if x.triggering_event_seq == seq]
    assert run.state == 'MISSION_CREATED' and 'Work-Claude' in str(run.rationale)
    with rig.db.read() as conn:
        stored = conn.execute('SELECT payload FROM events WHERE seq = ?', (seq,)).fetchone()[0]
    assert json.loads(stored)['reason'] == 'read ' + home + '/x'



def test_R1_automation_reads_project_the_matching_rationale(rig, tmp_path):  # noqa: F811
    from archeus.core.application import automations
    home = str(tmp_path / 'Work-Claude')
    rig.do(resources.register_account, harness_id='zzz', label='A', auth_kind='api_key',
           home_ref=home)
    glob = '*' + home + '*'
    aid = rig.automation(trigger={'type': 'mission.state_changed',
                                  'where': {'reason': {'glob': glob}}},
                         template={'title': 'saw {payload.reason}', 'objective': 'o'})
    mid = rig.seed(title='other')
    seq = rig.raw('mission.state_changed', Ref('mission', mid), {'to': 'CREATED', 'reason': 'read ' + home + '/x'})
    rig.pump()
    (run,) = [x for x in rig.runs() if x.triggering_event_seq == seq]
    assert run.rationale['where']['reason']['value'] == 'read ' + home + '/x'
    with rig.db.read() as conn:
        before = [tuple(r) for r in conn.execute('SELECT * FROM automation_runs')]
        got = automations.get_automation(conn, aid)
        why = automations.explain(conn, run.id)
        sim = automations.simulate(conn, aid, now=queries._now())
        assert [tuple(r) for r in conn.execute('SELECT * FROM automation_runs')] == before
    want = {'reason': {'test': {'glob': glob}, 'value': 'read its home/x'}}
    (shown,) = [r for r in got['runs'] if r['id'] == run.id]
    (hit,) = sim['matched']
    for rationale in (shown['rationale'], why['run']['rationale'], why['why']['rationale'],
                      hit['rationale']):
        assert rationale['where'] == want and rationale['type'] == 'mission.state_changed'


def _checkpoint(r, mid, home, key):
    (ex,) = r.all(entities.Execution, mission_id=mid)

    def seed(tx, *, actor):
        cp = entities.Checkpoint(
            id=ids.new_id('checkpoint'), execution_id=ex.id, mission_id=mid, task_id=ex.task_id,
            trigger='failure', objective='fix ' + home, constraints=('keep ' + home,),
            success_criteria=(home,), completed_steps=('t1 ' + home,),
            files_changed=(home + '/a',), decisions=('use ' + key,),
            open_problems=('deny: read of ' + home + '/settings.json',
                           'last error: cannot read ' + home + '/settings.json on ' + key))
        tx.insert(cp, actor=actor)
        tx.append(new_event('checkpoint.created', Ref('checkpoint', cp.id), actor, payload={
            'execution': ex.id, 'trigger': 'failure', 'task_id': ex.task_id}))
    r.do(seed)
    return ex


def test_R2_checkpoints_and_the_brief_project_open_problems(db, tmp_path):
    from archeus.core.application import sessions
    from archeus.core.sessions import continuity
    r, home, dhome, key, _, mid = _world(db, tmp_path)
    r.dispatch(mid)
    ex = _checkpoint(r, mid, home, key)
    sid = ids.new_id('session')

    def session(tx, *, actor):
        tx.insert(entities.Session(id=sid, harness_id='fake', workspace_id=ids.GLOBAL_WORKSPACE,
                                   cwd=str(tmp_path), mode='interactive_attached',
                                   mission_id=mid), actor=actor)
        tx.append(new_event('session.created', Ref('session', sid), actor, payload={
            'mode': 'interactive_attached', 'harness_id': 'fake', 'account_id': None,
            'mission_id': mid, 'handoff_from': None}))
    r.do(session)
    pid = public_account_id(key)
    problems = ['deny: read of its home/settings.json',
                'last error: cannot read its home/settings.json on ' + pid]
    with db.read() as conn:
        before = [tuple(x) for x in conn.execute('SELECT * FROM checkpoints')]
        (cp,) = executions.checkpoints(conn, ex.id)
        brief = sessions.preview_brief(conn, sid)
        handoff = continuity.handoff_state(conn, rows.get(conn, entities.Session, sid).entity, {})
        assert [tuple(x) for x in conn.execute('SELECT * FROM checkpoints')] == before
    assert list(cp['open_problems']) == problems
    assert cp['completed_steps'] == ['t1 its home'] and cp['files_changed'] == ['its home/a']
    assert cp['decisions'] == ['use ' + pid]
    assert (cp['objective'], cp['constraints'], cp['success_criteria']) == (
        'fix ' + home, ('keep ' + home,), (home,))
    for body in (brief, handoff):
        (item,) = body['open_problems']
        assert item['open_problems'] == problems
