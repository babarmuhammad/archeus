"""P14 over HTTP (p14-design-gate §17): the six routes against the real Core
runtime — scopes, idempotency, validation — and the runtime's own
`archeus-automation` worker claiming a run on its own thread."""

import time

from archeus.core.domain import ids

RULE = {'name': 'follow up', 'trigger': {'type': 'mission.created', 'where': {'title': 'seed'}},
        'template': {'title': 'follow up {subject.id}', 'objective': 'look at it'}}


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


def test_the_routes_write_read_simulate_and_explain(tc):
    made = _post(tc, '/v1/automations', dict(RULE, idempotency_key='k1'))
    assert made.status == 200 and made.json()['state'] == 'DRAFT'
    again = _post(tc, '/v1/automations', dict(RULE, idempotency_key='k1'))
    assert again.json()['id'] == made.json()['id']                        # idempotent
    aid = made.json()['id']
    assert _post(tc, '/v1/automations/%s/state' % aid,
                 {'action': 'enable'}).json()['state'] == 'ENABLED'
    _post(tc, '/v1/missions', {'title': 'seed', 'objective': 'o'})

    def run():
        runs = tc.http('GET', '/v1/automations/%s' % aid).json()['runs']
        return runs and runs[0]['mission_id'] and runs[0]
    r = _wait(run, 'the runtime worker claims a run')
    why = tc.http('GET', '/v1/automation-runs/%s' % r['id']).json()
    assert why['event']['type'] == 'mission.created' and why['mission']['origin'] == 'automation'
    sim = tc.http('GET', '/v1/automations/%s/simulate?days=1' % aid).json()
    assert len(sim['matched']) == 1 and sim['days'] == 1
    listed = tc.http('GET', '/v1/automations').json()
    assert [a['id'] for a in listed['automations']] == [aid] and listed['quarantined'] == []
    health = tc.http('GET', '/v1/health').json()['automation']
    assert health['quarantined'] == 0 and health['retrying'] == {}


def test_bad_input_is_a_400_and_an_unknown_id_a_404(tc):
    bad = _post(tc, '/v1/automations', dict(RULE, template=dict(RULE['template'],
                                                                harness='codex')))
    assert bad.status == 400
    loop = _post(tc, '/v1/automations', dict(RULE, trigger={'type': 'automation.created'}))
    assert loop.status == 400
    assert _post(tc, '/v1/automations/aut_nope/state', {'action': 'enable'}).status == 404
    assert tc.http('GET', '/v1/automation-runs/arn_nope').status == 404
    aid = _post(tc, '/v1/automations', RULE).json()['id']
    assert tc.http('GET', '/v1/automations/%s/simulate?days=0' % aid).status == 400
    assert _post(tc, '/v1/automations/%s/state' % aid, {'action': 'run-now'}).status == 400


def test_a_device_without_admin_reads_but_cannot_write_or_enable(tc):
    code = tc.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    browser = tc.http('POST', '/v1/devices/launch/redeem',
                      body={'code': code, 'platform': 'web'}).json()['token']
    got = _post(tc, '/v1/automations', RULE, token=browser)
    assert (got.status, got.json()['error']) == (403, 'scope_required')
    aid = _post(tc, '/v1/automations', RULE).json()['id']
    got = _post(tc, '/v1/automations/%s/state' % aid, {'action': 'enable'}, token=browser)
    assert got.status == 403
    assert tc.http('GET', '/v1/automations', token=browser).status == 200
