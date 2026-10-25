from copy import deepcopy
import re
from urllib.parse import unquote

import pytest

from archeus.core import ports
from archeus.core.application import calls, queries, resources, verification
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.core.homes import public_account_id
from archeus.core.routing import router
from archeus.core.routing.usage import FakeUsageFeed
from archeus.harnesses import base
from archeus.harnesses.fake import FakeCaller
from archeus.infra.db import rows
from v1.integration.test_routing import Rig


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def _no_leak(body, homes, keys):
    for text in _strings(body):
        normalized = _normalized(text)
        for private in (*homes, *keys):
            assert _normalized(private) not in normalized, text


def _normalized(text):
    text = unquote(text).lower().replace('\\', '/')
    text = re.sub(r'file:(?://localhost)?/+(?=[a-z]:)', '', text)
    text = re.sub(r'//[?.]/(?=[a-z]:)', '', text)
    text = re.sub(r'/(?:mnt/|cygdrive/)?([a-z])/', r'\1:/', text)
    return re.sub('/+', '/', text)


def _stored(conn):
    return {t: [tuple(row) for row in conn.execute('SELECT * FROM %s ORDER BY id' % t)]
            for t in ('route_decisions', 'usage_ledger', 'verifications', 'reviews', 'approvals')}


class HomeCaller(FakeCaller):
    def __init__(self, home, harness_id='historical'):
        super().__init__(harness_id)
        self.ref = base.default_ref(self.id, home)

    def default_account(self):
        return self.ref


def _record_call(r, home, source_id=None):
    caller = HomeCaller(home)
    r.do(calls.decide_provider_terms, who=r.user, harness_id=caller.id, headless='permitted')
    with r.db.read() as conn:
        req, snap, _ = resources.call_snapshot(conn, callers=[caller], feed=r.feed,
            preference=ports.OwnCallPreference(), purpose='brain', schema=None,
            project_id=None, min_tier=None)
    req['preferred']['accounts'] = [caller.ref.account_id]
    got = r.do(resources.record_call_route, purpose='brain',
               source={'kind': 'mission', 'id': source_id or ids.new_id('mission')},
               workspace_id=ids.GLOBAL_WORKSPACE, project_id=None,
               requirements=req, snapshot=snap)
    return got['route_decision_id'], caller.ref.account_id


@pytest.mark.parametrize('home_first', [True, False])
def test_homeless_snapshot_ordering_keeps_projection(db, tmp_path, home_first):
    from dataclasses import replace

    r = Rig(db)
    home = str(tmp_path / 'Shared-Default')
    caller = HomeCaller(home)
    key = caller.ref.account_id
    r.do(calls.decide_provider_terms, who=r.user, harness_id=caller.id, headless='permitted')
    records = []
    for stored_home in ((home, None) if home_first else (None, home)):
        caller.ref = replace(caller.ref, home_ref=stored_home)
        with db.read() as conn:
            req, snap, _ = resources.call_snapshot(conn, callers=[caller], feed=r.feed,
                preference=ports.OwnCallPreference(), purpose='brain', schema=None,
                project_id=None, min_tier=None)
        got = r.do(resources.record_call_route, purpose='brain',
            source={'kind': 'mission', 'id': ids.new_id('mission')},
            workspace_id=ids.GLOBAL_WORKSPACE, project_id=None, requirements=req, snapshot=snap)
        rd_id = got['route_decision_id']
        records.append(rd_id)
        r.do(calls.end_call, route_decision_id=rd_id,
             outcome={'state': 'ok', 'account_ref': key, 'reason': 'stderr ' + home})
    with db.read() as conn:
        for callers in ((), [caller]):
            h = resources.homes(conn, r.registry, callers, shorts=lambda _: None)
            assert h.keys[key] == public_account_id(key)
            for rd_id in records:
                assert queries.get_route_decision(conn, rd_id, homes=h)['outcome'][
                    'reason'] == 'stderr its home'


@pytest.mark.parametrize('id_ref', [False, True], ids=['old-home-ref', 'new-id-ref'])
def test_T8_reads_preserve_stored_refs_replay_and_snapshots(db, tmp_path, monkeypatch, id_ref):
    monkeypatch.setattr('archeus.core.homes._win_short', lambda _: None)
    r = Rig(db)
    home = str(tmp_path / 'Work-Claude')
    account = r.account('Work', home_ref=home)
    out = r.dispatch(r.ready())
    rd = r.rds()[0]
    if id_ref:
        snap = deepcopy(rd.input_snapshot)
        snap['accounts'][0]['ref'] = account
        d = router.route(rd.requirements, snap)
        recorded = r.do(resources.record_route, subject=rd.subject, requirements=rd.requirements,
                        snapshot=snap, decision=d)
        with db.read() as conn:
            rd = rows.get(conn, entities.RouteDecision, recorded['entity']['id']).entity
    expected_ref = account if id_ref else home
    assert rd.account_ref == expected_ref
    snapshot = deepcopy(rd.input_snapshot)
    before_replay = resources.replay(rd)
    with db.read() as conn:
        before = _stored(conn)
        public_homes = resources.homes(conn, r.registry, (), shorts=lambda _: None)
        one = queries.get_route_decision(conn, rd.id, homes=public_homes)
        queries.route_decisions(conn, homes=public_homes)
        assert _stored(conn) == before
    _no_leak(one, [home], [])
    assert resources.replay(rd) == before_replay
    assert resources.replay(rd)['account_ref'] == expected_ref
    assert rd.input_snapshot == snapshot
    r.finish(out, usage={'tokens_in': 7})
    ledger = r.all(entities.UsageLedger)[0]
    assert ledger.account_id == account and ledger.account_ref is None


def test_T8_historical_keys_stay_private_stable_and_out_of_ledgers(db, tmp_path, monkeypatch):
    def forbidden(_):
        pytest.fail('historical read probed a home')

    monkeypatch.setattr('archeus.core.homes._win_short', forbidden)
    r = Rig(db)
    private_homes = [str(tmp_path / name) for name in ('Old-Default', 'New-Default')]
    records = [_record_call(r, h) for h in private_homes]
    for rd_id, key in records:
        r.do(calls.end_call, route_decision_id=rd_id,
             outcome={'state': 'ok', 'account_ref': key, 'reason': 'ran on ' + key},
             usage={'tokens_in': 9})
    keys = [k for _, k in records]
    with db.read() as conn:
        before = _stored(conn)
        # No adapters: both keys must come from historical stored snapshots.
        first = resources.homes(conn, None, (), shorts=forbidden)
        second = resources.homes(conn, None, (), shorts=forbidden)
        bodies = [queries.get_route_decision(conn, i, homes=first) for i, _ in records]
        assert first.keys == second.keys == {k: public_account_id(k) for k in keys}
        assert _stored(conn) == before
        stored_rds = [rows.get(conn, entities.RouteDecision, i).entity for i, _ in records]
    assert len(set(first.keys.values())) == 2
    _no_leak(bodies, private_homes, keys)
    for body, rd, key in zip(bodies, stored_rds, keys):
        assert body['outcome']['account_ref'] == public_account_id(key)
        assert body['outcome']['reason'] == 'ran on ' + public_account_id(key)
        assert resources.replay(rd)['account_ref'] == key
        assert rd.input_snapshot['accounts'][0]['ref'] == key
    assert {u.account_ref for u in r.all(entities.UsageLedger)} == set(keys)


def test_S09_real_verification_list_and_get_keep_stored_performer(db, tmp_path, monkeypatch):
    monkeypatch.setattr('archeus.core.homes._win_short', lambda _: None)
    r = Rig(db)
    home = str(tmp_path / 'Verifier-Home')
    account = r.account('Work', home_ref=home)
    mid = r.ready()
    out = r.dispatch(mid)
    r.finish(out)
    task = r.one(entities.Task, mission_id=mid)
    got = r.do(verification.start, missions=r.missions, subject=Ref('task', task.id),
               verifier='generic_human', execution_id=out['execution_id'])
    with db.read() as conn:
        (stored,) = rows.where(conn, entities.Verification)
        assert stored.entity.performed_by['account_ref'] == home
        before = _stored(conn)
        listed = queries.list_verifications(conn, mid)['verifications']
        one = queries.get_verification(conn, stored.entity.id)
        assert _stored(conn) == before
    assert listed and got
    for body in [*listed, one]:
        assert body['performed_by']['account_id'] == account
        assert 'account_ref' not in body['performed_by']
        _no_leak(body, [home], [])


def test_S10_real_review_reader_preserves_authored_content_and_stored_identity(
        db, tmp_path, monkeypatch):
    monkeypatch.setattr('archeus.core.homes._win_short', lambda _: None)
    r = Rig(db)
    home = str(tmp_path / 'Reviewer-Home')
    rd_id, key = _record_call(r, home)
    r.account('Work', home_ref=str(tmp_path / 'Executor-Home'))
    mid = r.ready()
    out = r.dispatch(mid)
    r.finish(out)
    task = r.one(entities.Task, mission_id=mid)
    r.do(r.work.record_task_verification, task_id=task.id, verdict='PASSED', verifier='code')
    r.do(r.missions.advance, mission_id=mid)
    r.do(r.work.verify_mission, mission_id=mid,
         verdicts=[{'criterion': 0, 'verdict': 'PASSED', 'verifier': 'code'}])
    assert r.m(mid).state == 'REVIEWING'
    result = r.do(verification.record_review, missions=r.missions, mission_id=mid,
                  verdict='reject', reviewer='model', route_decision_id=rd_id,
                  reviewer_resource={'harness': 'historical', 'account': key},
                  summary=home, risks=[key])
    with db.read() as conn:
        before = _stored(conn)
        stored = rows.get(conn, entities.Review, result['review_id']).entity
        assert stored.reviewer_resource['account'] == key
        assert stored.summary == home and stored.risks == (key,)
        (body,) = queries.list_reviews(conn, mid)['reviews']
        assert body['reviewer_resource']['account'] == public_account_id(key)
        # Authored fields retain the entity's tuple shape and exact text. The
        # default account key is canonicalized separately from the authored home.
        assert body['summary'] == home and body['risks'] == (key,)
        assert _stored(conn) == before


def test_S04_review_route_projects_forbidden_default_key_without_changing_routing(
        db, tmp_path, monkeypatch):
    from archeus.core.verification import reviewer

    monkeypatch.setattr('archeus.core.homes._win_short', lambda _: None)
    r = Rig(db)
    author_home = str(tmp_path / 'Author-Default')
    _, author_key = _record_call(r, author_home)
    other_home = str(tmp_path / 'historical-review-Reviewer-Default')
    callers = [HomeCaller(author_home), HomeCaller(other_home, 'fake')]
    r.do(calls.decide_provider_terms, who=r.user, harness_id=callers[1].id,
         headless='permitted')
    forbidden = reviewer.forbidden([('historical', author_key, None)])
    with db.read() as conn:
        req, snap, _ = resources.call_snapshot(conn, callers=callers, feed=r.feed,
            preference=ports.OwnCallPreference(), purpose='review', schema=None,
            project_id=None, min_tier=None, forbidden=forbidden)
    result = r.do(resources.record_call_route, purpose='review',
                  source={'kind': 'mission', 'id': ids.new_id('mission')},
                  workspace_id=ids.GLOBAL_WORKSPACE, project_id=None,
                  requirements=req, snapshot=snap)
    with db.read() as conn:
        rd = rows.get(conn, entities.RouteDecision, result['route_decision_id']).entity
        assert rd.account_ref == callers[1].ref.account_id
        assert rd.requirements['forbidden']['accounts'] == [author_key]
        before = _stored(conn)
        body = queries.get_route_decision(conn, rd.id)
        assert body['requirements']['forbidden']['accounts'] == [public_account_id(author_key)]
        _no_leak(body, [author_home, other_home], [author_key, callers[1].ref.account_id])
        assert resources.replay(rd)['account_ref'] == callers[1].ref.account_id
        assert _stored(conn) == before


def test_S11_actual_fallback_ask_views_keep_approval_and_routing_immutable(
        db, tmp_path, monkeypatch):
    from archeus.core.application import attention

    monkeypatch.setattr('archeus.core.homes._win_short', lambda _: None)
    r = Rig(db)
    homes = [str(tmp_path / name) for name in ('Primary-Home', 'Fallback-Home')]
    first = r.account('Primary', home_ref=homes[0], priority=1)
    second = r.account('Fallback', home_ref=homes[1], priority=2, fallback='ask')
    r.feed.set(first, '5h', 100)
    r.feed.set(second, '5h', 79)
    mid = r.ready()
    out = r.dispatch(mid)
    assert out['execution_id'] is None
    approval = r.pending(mid)
    assert approval.kind == 'route' and approval.items[0]['resource']['account'] == second
    with db.read() as conn:
        before = _stored(conn)
        bodies = [queries.get_approval(conn, approval.id), queries.list_approvals(conn),
                  attention.attention(conn)]
        assert bodies[0]['eligible'] is True
        _no_leak(bodies, homes, [])
        assert _stored(conn) == before
    assert r.decide(approval)['mission']['state'] == 'EXECUTING'
    assert r.dispatch(mid)['account_id'] == second


def test_S01_S11_http_stored_row_leak_sweep(archeus_home, tmp_path, monkeypatch):
    from v1.integration.test_routing_http import _post, _wait
    from v1.judge.http import TempCore

    monkeypatch.setattr('archeus.core.homes._win_short', lambda _: None)
    from archeus.core import engine, runtime
    core = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), callers=[FakeCaller()],
        preference=ports.FixedOwnCallPreference(), usage=FakeUsageFeed())).start()
    try:
        home = str(tmp_path / 'Work-Claude')
        acc = _post(core, '/v1/accounts', {'harness_id': 'fake', 'label': 'Work',
                                          'auth_kind': 'api_key', 'home_ref': home}).json()
        mid = _post(core, '/v1/missions', {'title': 'Leak sweep', 'objective': 'o'}).json()['id']
        _wait(lambda: core.http('GET', '/v1/missions/' + mid).json()['state'] == 'COMPLETED',
              'mission completed')
        _wait(lambda: core.core.exec.state == 'idle' and not core.core.manager._procs,
              'execution manager idle with no live processes')
        # COMPLETED is not a barrier for background passes. Stop and join all
        # producers before seeding historical rows (including review.requested),
        # so only the HTTP reads can change stored rows during the sweep.
        # Keep the server and DB writer alive: a GET that writes must still fail.
        workers = [worker for worker in (
            core.core.metrics, core.core.automation, core.core.policy, core.core.plan,
            core.core.verify, core.core.intent, core.core.knowledge, core.core.world,
            core.core.exec, core.core.loop) if worker is not None]
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join(10)
            assert not worker._thread.is_alive(), worker._thread.name
            assert worker.state == 'stopped', (worker._thread.name, worker.state)
        r = Rig(core.core.db)
        live_default = str(tmp_path / 'Live-Only-Default')
        core.core.api.resources.callers.append(HomeCaller(live_default, 'live-only'))
        private_default = str(tmp_path / 'Historical-Default')
        rd_id, key = _record_call(r, private_default, source_id=mid)
        r.do(calls.end_call, route_decision_id=rd_id,
             outcome={'state': 'ok', 'account_ref': key,
                      'reason': 'failed in ' + private_default + '; auth ' + live_default,
                      'unlisted': {'nested': [private_default, 'waiting on ' + key]}},
             usage={'tokens_in': 1})
        with r.db.read() as conn:
            (task,) = rows.where(conn, entities.Task, mission_id=mid)
            (execution,) = rows.where(conn, entities.Execution, mission_id=mid)
            route = rows.get(conn, entities.RouteDecision, execution.entity.route_decision_id).entity
            assert route.account_ref == home
            performer = verification.performed_by(conn, execution.entity)
            plan = rows.get(conn, entities.Plan, task.entity.plan_id).entity
            mission = rows.get(conn, entities.Mission, mid).entity

        def historical_rows(tx, actor):
            from archeus.core.domain.events import new_event
            v = entities.Verification(id=ids.new_id('verification'), subject=Ref('task', task.entity.id),
                verifier='generic_human', plan_id=plan.id, performed_by=performer,
                state='ERROR', holds_mission=True,
                error='verifier crashed reading ' + home + '; auth ' + live_default)
            review = entities.Review(id=ids.new_id('review'), mission_id=mid, reviewer='model',
                plan_id=plan.id, reviewer_resource={'harness': 'historical', 'account': key})
            tx.insert(v, actor=actor)
            tx.append(new_event('verification.created', Ref('verification', v.id), actor,
                payload={}, workspace=mission.workspace_id))
            tx.append(new_event('mission.state_changed', Ref('mission', mid), actor,
                payload={'from': 'a', 'to': 'b', 'reason': 'auth ' + live_default},
                workspace=mission.workspace_id))
            tx.insert(review, actor=actor)
            tx.append(new_event('review.requested', Ref('review', review.id), actor,
                payload={'reviewer_resource': review.reviewer_resource},
                workspace=mission.workspace_id))
            return v.id

        vid = r.do(historical_rows)
        from dataclasses import replace
        approval, _ = r.do(resources.request_route, mission=mission, plan=plan, task=task.entity,
            route=replace(route, account_id=None, account_ref=key, harness_id='historical'))
        paths = ['/v1/route-decisions', '/v1/route-decisions/' + rd_id,
                 '/v1/route-decisions/' + route.id, '/v1/accounts', '/v1/status',
                 '/v1/verifications/' + vid, '/v1/missions/%s/verifications' % mid,
                 '/v1/missions/%s/reviews' % mid, '/v1/approvals',
                 '/v1/approvals/' + approval['id'], '/v1/attention', '/v1/policy-decisions',
                 '/v1/missions/%s/timeline?limit=100' % mid]
        with r.db.read() as conn:
            before = _stored(conn)
            from archeus.core.application import attention
            assert all(_normalized(live_default) not in _normalized(text)
                       for rd in rows.where(conn, entities.RouteDecision)
                       for text in _strings(rd.entity.input_snapshot))
            assert all(row.entity.home_ref != live_default for row in rows.where(conn, entities.Account))
            live_homes = resources.homes(conn, core.core.api.resources.registry,
                                         core.core.api.resources.callers)
            items = attention.attention(conn, homes=live_homes)['items']
            item = next(i for i in items if i['ref']['id'] == vid)
            assert item['reason'] == 'verifier crashed reading its home; auth its home'
            raw_live = attention.attention(conn)['items']
            assert live_default in next(i for i in raw_live if i['ref']['id'] == vid)['reason']
            assert rows.get(conn, entities.Verification, vid).entity.performed_by['account_ref'] == home
            assert any(x.entity.reviewer_resource and x.entity.reviewer_resource['account'] == key
                       for x in rows.where(conn, entities.Review, mission_id=mid))
            assert rows.get(conn, entities.RouteDecision, rd_id).entity.outcome['account_ref'] == key
            assert rows.get(conn, entities.RouteDecision, rd_id).entity.requirements[
                'preferred']['accounts'] == [key]
        for path in paths:
            response = core.http('GET', path)
            assert response.status == 200, (path, response.body)
            _no_leak(response.json(), [home, private_default, live_default], [key])
            if path == '/v1/attention':
                item = next(i for i in response.json()['items'] if i['ref']['id'] == vid)
                assert item['reason'] == 'verifier crashed reading its home; auth its home'
        trace_response = core.http('GET', '/v1/missions/%s/trace' % mid)
        assert trace_response.status == 200
        trace_decisions = trace_response.json()['route_decisions']
        assert rd_id in {d['id'] for d in trace_decisions}
        private = [home, private_default, live_default]
        _no_leak(trace_response.json(), private, [key])
        feed, after = [], 0
        while True:
            page = core.http('GET', '/v1/events?after=%d&limit=1000' % after).json()['events']
            feed += page
            if len(page) < 1000:
                break
            after = page[-1]['seq']
        types = {e['type'] for e in feed}
        assert {'archeus_call.ended', 'review.requested', 'verification.created'} <= types
        _no_leak(feed, private, [key])
        ended = next(e for e in feed if e['type'] == 'archeus_call.ended'
                     and e['subject']['id'] == rd_id)
        assert ended['payload']['outcome']['account_ref'] == public_account_id(key)
        preview = core.http('POST', '/v1/context/preview',
                            body={'subject': {'kind': 'mission', 'id': mid}})
        assert preview.status == 200, preview.body
        _no_leak(preview.json(), private, [key])
        stream = {'execution_id': execution.entity.id, 'offset': 0, 'next_offset': 1,
                  'truncated': False, 'available': True,
                  'events': [{'type': 'assistant', 'text': 'HOME is ' + home + ' / ' + key + ' / ' + live_default}]}
        monkeypatch.setattr('archeus.core.execution.output.read', lambda e, a, offset=0: stream)
        tail = core.http('GET', '/v1/executions/%s/stream' % execution.entity.id)
        assert tail.status == 200, tail.body
        assert tail.json()['events'] == [{'type': 'assistant', 'text': 'HOME is its home / ' + public_account_id(key) + ' / its home'}]
        assert stream['events'][0]['text'] == 'HOME is ' + home + ' / ' + key + ' / ' + live_default
        with r.db.read() as conn:
            assert _stored(conn) == before
        assert acc['id'] == route.account_id
    finally:
        core.stop()


@pytest.mark.parametrize('spelling', [
    'C:/T144/Work-Claude/x', r'c:\t144\work-claude\x',
    r'C:\\T144\\Work-Claude\\x', 'file:///C:/T144/Work-Claude/x',
    'file://localhost/C:/T144/Work-Claude/x', r'\\?\C:\T144\Work-Claude\x',
    '/c/T144/Work-Claude/x', '/mnt/c/T144/Work-Claude/x',
    '/cygdrive/c/T144/Work-Claude/x', 'C:%2FT144%2FWork-Claude/x'])
def test_independent_detector_rejects_seeded_aliases(spelling):
    with pytest.raises(AssertionError):
        _no_leak({'nested': [spelling]}, ['C:/T144/Work-Claude'], [])
