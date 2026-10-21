"""P10 over HTTP (p10-design-gate §10, §17 H-*): the resource routes, their
scopes and errors, and a task routed by the real Core runtime (the P3.5 stub
brain plans the skeleton plan; the policy is the real engine; usage is the
scripted feed)."""

import time

import pytest

from archeus.core import engine, ports, runtime
from archeus.core.application import resources
from archeus.core.domain import entities, ids
from archeus.core.routing.usage import FakeUsageFeed
from archeus.harnesses.fake import FakeCaller
from archeus.infra.db import rows


def _post(tc, path, body, token=None):
    return tc.http('POST', path, body=dict(body, idempotency_key=body.get(
        'idempotency_key') or ids.new_ulid()), **({'token': token} if token else {}))


def _wait(fn, what, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = fn()
        if got:
            return got
        time.sleep(0.05)
    raise AssertionError('timed out: %s' % what)


@pytest.fixture
def core(archeus_home):
    from v1.judge.http import TempCore
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), usage=FakeUsageFeed())).start()
    yield tc
    tc.stop()


@pytest.fixture
def own_core(archeus_home):
    """As `core`, with a scripted own-call caller, so an own call can be in flight."""
    from v1.judge.http import TempCore
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), usage=FakeUsageFeed(),
        callers=[FakeCaller('fake')])).start()
    yield tc
    tc.stop()


def _browser(tc):
    code = tc.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    return tc.http('POST', '/v1/devices/launch/redeem',
                   body={'code': code, 'platform': 'web'}).json()['token']


def test_H01_register_list_and_set_a_policy(core):
    a = _post(core, '/v1/accounts', {'harness_id': 'fake', 'label': 'Work',
                                     'auth_kind': 'api_key'})
    assert a.status == 200
    acc = a.json()
    assert (acc['health'], acc['resource_policy']['priority'],
            acc['resource_policy']['allocation_pct']) == ('AVAILABLE', 1, 80)
    got = _post(core, '/v1/resource-policies/%s' % acc['id'],
                {'priority': 2, 'fallback': 'allow', 'budgets': {'tokens_per_day': 1000}})
    assert got.status == 200 and (got.json()['priority'], got.json()['fallback']) == (2, 'allow')
    (listed,) = core.http('GET', '/v1/accounts').json()['accounts']
    assert listed['resource_policy']['budgets'] == {'tokens_per_day': 1000}


def test_H02_an_account_no_adapter_can_probe_stays_unverified(core):
    acc = _post(core, '/v1/accounts', {'harness_id': 'nobody', 'label': 'x',
                                       'auth_kind': 'api_key'}).json()
    assert acc['health'] == 'UNVERIFIED'


def test_H03_resource_changes_need_admin_and_bad_values_are_400(core):
    browser = _browser(core)
    got = _post(core, '/v1/accounts', {'harness_id': 'fake', 'label': 'x',
                                       'auth_kind': 'api_key'}, token=browser)
    assert (got.status, got.json()['error']) == (403, 'scope_required')
    assert core.http('GET', '/v1/accounts', token=browser).status == 200
    acc = _post(core, '/v1/accounts', {'harness_id': 'fake', 'label': 'x',
                                       'auth_kind': 'api_key'}).json()
    bad = _post(core, '/v1/resource-policies/%s' % acc['id'], {'allocation_pct': 150})
    assert (bad.status, bad.json()['error']) == (400, 'invalid_request')
    bad = _post(core, '/v1/accounts', {'harness_id': 'fake', 'label': 'x',
                                       'auth_kind': 'nonsense'})
    assert bad.status == 400
    gone = _post(core, '/v1/resource-policies/acc_01M3FAAAAAAAAAAAAAAAAAAAAA', {'priority': 1})
    assert gone.status == 404


def test_H04_disable_and_enable_an_account(core):
    acc = _post(core, '/v1/accounts', {'harness_id': 'fake', 'label': 'x',
                                       'auth_kind': 'api_key'}).json()
    off = _post(core, '/v1/accounts/%s/state' % acc['id'], {'enabled': False}).json()
    on = _post(core, '/v1/accounts/%s/state' % acc['id'], {'enabled': True}).json()
    assert (off['health'], on['health']) == ('DISABLED', 'AVAILABLE')


def test_H05_the_harnesses_say_what_they_declare(core):
    hs = {h['id']: h for h in core.http('GET', '/v1/harnesses').json()['harnesses']}
    assert hs['fake']['execution'] is True and 'code_edit' in hs['fake']['capabilities']
    assert hs['fake']['models'][0] == {'id': 'fake-model', 'tier': 'large',
                                       'context_window': 200000}


def test_H06_a_task_is_routed_to_the_registered_account_and_the_decision_is_readable(core):
    acc = _post(core, '/v1/accounts', {'harness_id': 'fake', 'label': 'Work',
                                       'auth_kind': 'api_key'}).json()
    mid = _post(core, '/v1/missions', {'title': 'Route', 'objective': 'o'}).json()['id']

    def done():
        return core.http('GET', '/v1/missions/%s' % mid).json()['state'] == 'COMPLETED'
    _wait(done, 'mission completed')
    got = core.http('GET', '/v1/route-decisions?source=%s' % mid).json()['route_decisions']
    (task_rd,) = [d for d in got if d['subject']['kind'] == 'task']
    one = core.http('GET', '/v1/route-decisions/%s' % task_rd['id']).json()
    assert (one['selected'], one['result'], one['decided_by']) == (acc['id'], 'selected',
                                                                  'router')
    assert 'priority-1' in one['explanation'] and one['input_snapshot']['accounts']


def test_H08_the_cli_says_why_from_the_persisted_decision(core, capsys):
    """`archeus route why` (p3.5b gate: `route why` is P10's): by decision id,
    or by what it is about; an unknown id sends nothing back and exits 2."""
    from archeus.cli import main as cli
    mid = _post(core, '/v1/missions', {'title': 'Why', 'objective': 'o'}).json()['id']
    _wait(lambda: core.http('GET', '/v1/missions/%s' % mid).json()['state'] == 'COMPLETED',
          'mission completed')
    got = core.http('GET', '/v1/route-decisions?source=%s' % mid).json()['route_decisions']
    (rd,) = [d for d in got if d['subject']['kind'] == 'task']
    capsys.readouterr()
    assert cli.main(['route', 'why', rd['id']]) == 0
    by_id = capsys.readouterr().out.strip()
    assert by_id == '%s (selected): %s' % (rd['id'], rd['explanation'])
    assert cli.main(['route', 'why', rd['subject']['id']]) == 0     # the task: its latest
    assert capsys.readouterr().out.strip() == by_id
    assert cli.main(['route', 'why', ids.new_id('route_decision')]) == 2
    assert cli.main(['route', 'maybe']) == 2                        # usage


def test_H07_a_missions_resources_are_admin_and_validated(core):
    mid = _post(core, '/v1/missions', {'title': 'R', 'objective': 'o'}).json()['id']
    got = _post(core, '/v1/missions/%s/resources' % mid, {'max_cost_band': 'high',
                                                          'preferred_accounts': ['acc_x']})
    assert got.status == 200
    assert got.json()['resource_preferences']['max_cost_band'] == 'high'
    bad = _post(core, '/v1/missions/%s/resources' % mid, {'max_cost_band': 'huge'})
    assert bad.status == 400
    assert _post(core, '/v1/missions/%s/resources' % mid, {'max_cost_band': 'low'},
                 token=_browser(core)).status == 403


def _keys(x):
    """Every key of a decoded JSON body, at any depth."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from _keys(v)
    elif isinstance(x, list):
        for v in x:
            yield from _keys(v)


def _strings(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def _stored_snapshots(core):
    """The input snapshot of every route decision row, read from Core's database as written."""
    import json
    import os
    import sqlite3
    con = sqlite3.connect(os.path.join(core.home, 'archeus.db'))
    try:
        return [json.loads(body).get('input_snapshot') or {}
                for (body,) in con.execute('SELECT body FROM route_decisions')]
    finally:
        con.close()


def test_H09_the_three_projected_reads_name_no_home_field(core, tmp_path):
    """Owner, 2026-10-21: field projection on /v1/accounts, /v1/route-decisions (list and
    one) and /v1/status. The stored rows name the home (the precondition), and no body of
    those reads names it in a home field, a `ref` of a snapshot account or an `account_ref`."""
    home = str(tmp_path / 'Work-Claude')
    _post(core, '/v1/accounts', {'harness_id': 'fake', 'label': 'Work', 'auth_kind': 'api_key',
                                 'home_ref': home})
    mid = _post(core, '/v1/missions', {'title': 'Route', 'objective': 'o'}).json()['id']
    _wait(lambda: core.http('GET', '/v1/missions/%s' % mid).json()['state'] == 'COMPLETED',
          'mission completed')
    decisions = core.http('GET', '/v1/route-decisions?source=%s' % mid).json()['route_decisions']
    # precondition: the stored snapshots name the home, so only the projection removes it here
    assert decisions and any(a.get('home_ref') == home for snap in _stored_snapshots(core)
                             for a in snap.get('accounts') or ())
    reads = ['/v1/accounts', '/v1/status', '/v1/route-decisions?source=%s' % mid]
    reads += ['/v1/route-decisions/%s' % d['id'] for d in decisions]
    for path in reads:
        got = core.http('GET', path)
        assert got.status == 200, path
        body = got.json()
        assert not {'home_ref', 'home_key', 'account_ref'} & set(_keys(body)), path
        assert not any(home in v for v in _strings(body)), path
        if path.startswith('/v1/route-decisions/'):
            accounts = (body.get('input_snapshot') or {}).get('accounts') or ()
            assert all('ref' not in a for a in accounts), path


def _own_call_in_flight(core, mission_id):
    """An own call decided and not ended, recorded by Core's own writer as its planner
    would record it (nothing runs it): in flight until its maximum run."""
    db = core.core.db
    with db.read() as conn:
        req, snap, _ = resources.call_snapshot(
            conn, callers=[FakeCaller('fake')], feed=FakeUsageFeed(),
            preference=ports.OwnCallPreference(), purpose='brain', schema=None,
            project_id=None, min_tier=None, max_run_s=1200)
    got = db.writer.execute(resources.record_call_route, dict(
        actor=core.core.system, purpose='brain', source={'kind': 'mission', 'id': mission_id},
        workspace_id=ids.GLOBAL_WORKSPACE, project_id=None,
        requirements=dict(req, max_run_s=1200), snapshot=snap))
    return got['route_decision_id']


def test_H09_the_status_read_with_a_live_own_call_names_no_home_field(own_core, tmp_path):
    """Owner, 2026-10-21: /v1/status leaves an own call's `account_ref` out. Here the call is
    in flight when the status is read (the status read above has no live call), so the
    projection runs over HTTP and not only on `live_work`."""
    home = str(tmp_path / 'Work-Claude')
    acct = _post(own_core, '/v1/accounts', {'harness_id': 'fake', 'label': 'Work',
                                            'auth_kind': 'api_key', 'home_ref': home}).json()['id']
    mid = _post(own_core, '/v1/missions', {'title': 'Flying', 'objective': 'o'}).json()['id']
    rid = _own_call_in_flight(own_core, mid)
    with own_core.core.db.read() as conn:
        stored = rows.get(conn, entities.RouteDecision, rid).entity
    assert stored.account_ref == home                    # precondition: the row names the home
    body = own_core.http('GET', '/v1/status').json()
    (item,) = [x for x in body['live'] if x['kind'] == 'own_call']
    assert item['id'] == rid and item['account_id'] == acct
    assert 'account_ref' not in item
    assert not {'home_ref', 'home_key', 'account_ref'} & set(_keys(body))
    assert not any(home in v for v in _strings(body))
