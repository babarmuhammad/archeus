"""P21 slice D Health (p21-design-gate D2, D12; plan K7, D-11): the accounts and
missions that wait on the user join the Attention read, and Control -> About ->
Health reads metrics_daily through `/v1/metrics`."""

import re
from pathlib import Path

import pytest

from archeus.api import schemas
from archeus.cli.tui import screens
from archeus.core import metrics
from archeus.core.application import attention
from archeus.core.domain import entities, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.infra.db import rows
from v1.judge.support import wait_for

WS = ids.GLOBAL_WORKSPACE
ACTOR = Ref('user_device', ids.new_id('principal'))


def put(db, *rows):
    def run(tx, **_):
        for r in rows:
            tx.insert(r, actor=ACTOR)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')), ACTOR,
                            payload={}, workspace=WS))
    db.writer.execute(run, {})


def items(db, kind):
    with db.read() as conn:
        return [i for i in attention.attention(conn)['items'] if i['kind'] == kind]


def test_H01_accounts_a_provider_or_the_breaker_stopped_wait_on_the_user(db):
    acc = {h: ids.new_id('account') for h in ('UNAUTHENTICATED', 'LIMITED', 'DEGRADED', 'OPEN',
                                               'AVAILABLE', 'CONSTRAINED', 'DISABLED',
                                               'UNVERIFIED')}
    put(db, *[entities.Account(id=a, harness_id='fake', label='acct ' + h, auth_kind='api_key',
                               health=h, limited_until='2999-01-01T00:00:00.000Z'
                               if h == 'LIMITED' else None) for h, a in acc.items()])
    got = {i['state']: i for i in items(db, 'account')}
    assert {s: i['reason_code'] for s, i in got.items()} == {
        'UNAUTHENTICATED': 'reauth', 'LIMITED': 'limited', 'DEGRADED': 'degraded', 'OPEN': 'open'}
    assert got['LIMITED']['until'] == '2999-01-01T00:00:00.000Z'
    assert 'until' not in got['OPEN']
    assert got['DEGRADED']['ref'] == {'kind': 'account', 'id': acc['DEGRADED']}
    assert got['DEGRADED']['reason'] == 'acct DEGRADED'


def _blocked_mission(db, held='EXECUTING'):
    mid, pid, tid = ids.new_id('mission'), ids.new_id('plan'), ids.new_id('task')
    put(db, entities.Mission(id=mid, workspace_id=WS, title='M', objective='o', state='BLOCKED',
                             held_from=held),
        entities.Plan(id=pid, mission_id=mid, plan_version=1, state='APPROVED'),
        entities.Task(id=tid, plan_id=pid, mission_id=mid, key='t1', title='T',
                      kind='code_change', state='BLOCKED'))
    return mid, tid


def _route(db, mid, tid, result, explanation='x', unblock_at=None):
    put(db, entities.RouteDecision(id=ids.new_id('route_decision'), subject=Ref('task', tid),
                                   result=result, task_id=tid, mission_id=mid,
                                   explanation=explanation, unblock_at=unblock_at,
                                   selected='fake' if result != 'blocked' else None))


def test_H02_a_mission_no_resource_can_run_waits_with_the_routes_reason(db):
    mid, tid = _blocked_mission(db)
    _route(db, mid, tid, 'selected')
    _route(db, mid, tid, 'blocked', 'no eligible resource: acct LIMITED until 15:00',
           '2999-01-01T15:00:00.000Z')
    [m] = items(db, 'mission')
    assert (m['ref']['id'], m['state'], m['reason_code']) == (mid, 'BLOCKED', 'no_resource')
    assert m['reason'] == 'no eligible resource: acct LIMITED until 15:00'
    assert (m['mission_id'], m['unblock_at']) == (mid, '2999-01-01T15:00:00.000Z')
    with db.read() as conn:
        schemas.validate(attention.attention(conn), schemas.TYPES['Attention'])


def test_H03_only_a_route_that_found_no_resource_makes_the_item(db):
    # BLOCKED from EXECUTING with no route recorded for its task (a stop, a merge conflict)
    _blocked_mission(db)
    # a rejected route approval: the task is BLOCKED, its last route asked
    asked, atid = _blocked_mission(db)
    _route(db, asked, atid, 'ask')
    # a route that found nothing, later superseded by one that did
    later, ltid = _blocked_mission(db)
    _route(db, later, ltid, 'blocked')
    _route(db, later, ltid, 'fallback')
    # held from verification, whatever its task says
    verifying, vtid = _blocked_mission(db, held='VERIFYING')
    _route(db, verifying, vtid, 'blocked')
    assert items(db, 'mission') == []


def test_H04_metrics_newest_first_bounded_and_unknown_kept_unknown(tc):
    w = tc.core.db.writer
    for day, done in (('2026-10-15', 1), ('2026-10-16', 2), ('2026-10-17', 3)):
        w.execute(metrics.record, {'day': day, 'metrics': {
            'missions_completed': done, 'missions_failed': 0, 'median_time_to_complete_s': None,
            'approvals_per_mission': None, 'fallback_rate': 0.5,
            'verification_failure_rate': None, 'cost_per_mission_band': {},
            'context_tokens_per_task_kind': {}}})
    r = tc.http('GET', '/v1/metrics?days=2')
    assert r.status == 200
    got = r.json()
    schemas.validate(got, schemas.TYPES['MetricsDaily'])
    assert [d['day'] for d in got['days']] == ['2026-10-17', '2026-10-16']
    assert got['days'][0]['metrics']['median_time_to_complete_s'] is None
    assert got['days'][0]['metrics']['missions_completed'] == 3
    assert len(tc.http('GET', '/v1/metrics').json()['days']) == 3
    for bad in ('0', '91', 'x'):
        assert tc.http('GET', '/v1/metrics?days=' + bad).status == 400


def test_H05_health_names_the_metrics_worker(tc):
    def started():
        h = tc.http('GET', '/v1/health').json()
        return h if h['metrics']['state'] in ('running', 'idle') else None
    h = wait_for(started)           # the started worker reaches running or idle, never stopped
    # the Health schema is closed and predates exec/verify/automation (not this slice)
    schemas.validate(h['metrics'], schemas.TYPES['Worker'])
    assert 'metrics' in schemas.TYPES['Health']['required']


def test_H11_settle_takes_a_never_started_worker_and_never_a_crashed_one():
    from v1.judge.http import HttpClient
    health = {'engine': {'state': 'idle', 'observed_seq': 7},
              'world': {'state': 'idle', 'pending': 0},
              'exec': {'state': 'idle', 'live': 0, 'observed_seq': 7},
              'knowledge': {'state': 'idle', 'pending': 0},
              'intent': {'state': 'idle', 'pending': 0},
              'plan': {'state': 'stopped', 'pending': 0},
              'verify': {'state': 'stopped', 'pending': 0},
              'automation': {'state': 'idle', 'pending': 0}}
    client = object.__new__(HttpClient)

    def settled(**worker):
        h = dict(health, **worker)
        client._call = lambda method, path, body=None: (
            {'events': []} if path.startswith('/v1/events') else h)
        return client._idle()
    assert settled()                                                   # plan, verify unwired
    assert not settled(plan={'state': 'failed', 'pending': 0})         # a crashed worker
    assert not settled(knowledge={'state': 'failed', 'pending': 0})
    assert not settled(verify={'state': 'idle', 'pending': 2})
    assert not settled(automation={'state': 'stopped', 'pending': 0})  # always started
    assert not settled(knowledge={'state': 'stopped', 'pending': 0})


def test_H12_an_engine_whose_writer_closed_reads_failed_not_stopped():
    from types import SimpleNamespace
    from archeus.core import runtime

    def closed():
        raise runtime.errors.WriterClosed()
    loop = runtime.EngineLoop(SimpleNamespace(reconcile_orphans=closed), None)
    loop._run()
    assert loop.state == 'failed'


@pytest.mark.parametrize('path', ['/v1/metrics'])
def test_H06_metrics_needs_a_token(tc, path):
    from v1.judge.http import request
    assert request(tc.base_url, 'GET', path).status == 401


def test_H07_every_blocked_task_must_be_blocked_on_a_resource(db):
    mid, tid = _blocked_mission(db)
    _route(db, mid, tid, 'blocked', 'no eligible resource', '2999-01-01T15:00:00.000Z')
    with db.read() as conn:
        pid = rows.get(conn, entities.Task, tid).entity.plan_id
    # a second BLOCKED task stopped for another reason: no route at all
    other = ids.new_id('task')
    put(db, entities.Task(id=other, plan_id=pid, mission_id=mid, key='t2', title='T2',
                          kind='code_change', state='BLOCKED'))
    assert items(db, 'mission') == []
    # its last route did not block
    _route(db, mid, other, 'fallback')
    assert items(db, 'mission') == []
    # once its last route blocked on a resource too, the mission waits for one
    _route(db, mid, other, 'blocked', 'no eligible resource')
    assert [m['reason_code'] for m in items(db, 'mission')] == ['no_resource']


def test_H08_a_metrics_worker_never_started_is_stopped_not_idle(tc, monkeypatch):
    monkeypatch.setattr(tc.core, 'metrics', None)
    h = tc.http('GET', '/v1/health').json()
    schemas.validate(h['metrics'], schemas.TYPES['Worker'])
    assert h['metrics'] == {'state': 'stopped', 'pending': 0}


def test_H09_the_spa_and_the_tui_name_an_attention_item_the_same():
    spa_src = (Path(__file__).resolve().parents[3] / 'clients/app/src/state/present.ts').read_text(
        encoding='utf-8')
    reasons = spa_src.split('const REASON_LABEL')[1].split('};')[0]
    assert dict(re.findall(r"'([a-z_]+\.[a-z_]+)': '([^']+)'", reasons)) == dict(screens.ATTENTION_REASON)
    kinds = spa_src.split('const KIND_LABEL')[1].split('};')[0]
    assert dict(re.findall(r"^\s*(\w+): '([^']+)',", kinds, re.M)) == screens.ATTENTION_KIND


@pytest.mark.parametrize('worker', ['plan', 'policy', 'verify', 'automation'])
def test_H10_a_never_started_worker_reads_stopped_not_idle(tc, monkeypatch, worker):
    monkeypatch.setattr(tc.core, worker, None)
    h = tc.http('GET', '/v1/health').json()
    schemas.validate(h[worker], schemas.TYPES['Worker'])
    assert h[worker] == {'state': 'stopped', 'pending': 0}
