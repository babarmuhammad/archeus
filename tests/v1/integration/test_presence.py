"""P15 over the real HTTP stack (p15-design-gate §19): pairing, presence,
remote hosts, resync, offline intent and the boundaries around them.

Each test names its scenario (P01–P30, R1–R5). Clients are made the real way:
the local token (admin) starts a pairing, the new client redeems it."""

import os
import threading
import time

import pytest

from archeus.api import auth, sse
from archeus.core import engine, ports, runtime
from archeus.core.domain import ids
from archeus.harnesses.fake import FakeHarness
from archeus.harnesses.sessions import FakeSessions
from archeus.infra import paths
from archeus.infra.db import connection
from claude_sessions import proc
from v1.judge.http import SSEClient, TempCore, request
from v1.judge.support import FixtureRepo, JudgeTerminal, session_adapters

DEPLOY = dict(engine.SKELETON_PLAN, tasks=[dict(engine.SKELETON_PLAN['tasks'][0],
                                                 action_classes=['deploy'])])
SLOW = {'work': [{'emit': {'type': 'working'}}, {'sleep': 30}]}
REMOTE = 'pc.tailnet.ts.net'
SECRETS = []


# ── helpers ──

def _wait(fn, what, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = fn()
        if got:
            return got
        time.sleep(0.05)
    raise AssertionError('timed out: %s' % what)


def _post(tc, path, body=None, token=None, headers=None):
    body = dict(body or {})
    body.setdefault('idempotency_key', ids.new_ulid())
    return tc.http('POST', path, body=body, headers=headers,
                   **({'token': token} if token else {}))


def _get(tc, path, token=None):
    return tc.http('GET', path, **({'token': token} if token else {}))


def start(tc, token=None, **body):
    r = tc.http('POST', '/v1/devices/pair/start', body=body,
                **({'token': token} if token else {}))
    if r.status == 200:
        SECRETS.append(r.json()['code'])
    return r


def redeem(tc, code, platform='android', **body):
    r = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                body=dict({'code': code, 'platform': platform}, **body))
    if r.status == 200:
        SECRETS.append(r.json()['token'])
    return r


def pair(tc, scopes=None, platform='android', pin=None, name='phone', host_label=None):
    """(device_id, token) of a client paired the real way."""
    body = {'name': name, 'host_label': host_label}
    if scopes is not None:
        body['scopes'] = list(scopes)
    s = start(tc, **body)
    assert s.status == 200, s.body
    r = redeem(tc, s.json()['code'], platform=platform, pin=pin)
    assert r.status == 200, r.body
    if pin:
        SECRETS.append(pin)
    return r.json()['device_id'], r.json()['token']


def _events(tc):
    return tc.client().events(0)


def _head(tc):
    return _events(tc)[-1]['seq']


def _mission(tc, token=None):
    r = _post(tc, '/v1/missions', {'title': 'M', 'objective': 'o'}, token=token)
    assert r.status == 200, r.body
    return r.json()['id']


def _device(tc, device_id):
    (d,) = [d for d in _get(tc, '/v1/devices').json()['devices'] if d['id'] == device_id]
    return d


def _settle(tc):
    client = tc.client()
    _wait(client._idle, 'Core idle')


# ── fixtures ──

@pytest.fixture
def slow(archeus_home, clock):
    """A Core whose one task runs for 30 s on the fake harness, with the
    judge's session harnesses."""
    tc = TempCore(archeus_home, launch_clock=clock, heartbeat_s=0.1, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), scenarios=dict(SLOW),
        executors=[FakeHarness()], sessions=session_adapters(),
        terminal=JudgeTerminal(archeus_home))).start()
    yield tc
    for p in list(tc.core.manager._procs.values()):
        proc.kill_pid_tree(p['handle'].pid, p['handle'].create_time)
    tc.stop()


@pytest.fixture
def deploy(archeus_home, clock):
    """A Core whose plan deploys: its approval needs step-up (P9 D16)."""
    tc = TempCore(archeus_home, launch_clock=clock,
                  ports=runtime.Ports(brain=ports.FixedPlanBrain(DEPLOY))).start()
    yield tc
    tc.stop()


@pytest.fixture
def remote(archeus_home, clock):
    tc = TempCore(archeus_home, launch_clock=clock, remote_hosts=(REMOTE,)).start()
    yield tc
    tc.stop()


def _pending(tc, mid):
    def got():
        ap = _get(tc, '/v1/approvals?state=PENDING&mission=%s' % mid).json()['approvals']
        return ap[0] if ap else None
    return _wait(got, 'an approval for %s' % mid)


def _running(tc):
    mid = _mission(tc)

    def started():
        got = [e for e in _events(tc) if e['type'] == 'execution.started']
        return got and got[0]['subject']['id']
    return mid, _wait(started, 'a running execution')


# ── P01–P03, P28, R4: pairing ──

def test_P01_a_new_client_pairs_with_exactly_the_scopes_chosen_at_the_start(tc):
    s = start(tc, name='Pixel', host_label="Babar's phone")
    assert s.status == 200 and s.json()['scopes'] == ['observe', 'control', 'approve']
    assert s.json()['expires_in'] == 120 and s.json()['url'] is None       # no remote host
    r = redeem(tc, s.json()['code'], name='ignored: the start named it')
    assert r.status == 200
    out = r.json()
    assert out['token'].startswith('dev_') and out['scopes'] == ['observe', 'control', 'approve']
    assert _get(tc, '/v1/version', out['token']).status == 200
    assert _post(tc, '/v1/projects', {'name': 'x', 'root_paths': []},
                 token=out['token']).json()['error'] == 'scope_required'     # no admin
    d = _device(tc, out['device_id'])
    assert (d['name'], d['host_label'], d['origin'], d['client_type'], d['platform']) == (
        'Pixel', "Babar's phone", 'paired', 'spa', 'android')
    assert d['expires_at'] > auth.now_iso() and d['capabilities'] == {'step_up': 'none'}
    # an observe-only grant stays observe-only: the redeemer cannot widen it
    _did, viewer = pair(tc, scopes=['observe'])
    mid = _mission(tc)
    r = _post(tc, '/v1/missions/%s/pause' % mid, token=viewer)
    assert (r.status, r.json()['error']) == (403, 'scope_required')
    # and a start must keep observe, and knows only the four scopes
    assert start(tc, scopes=['control']).status == 400
    assert start(tc, scopes=['observe', 'root']).status == 400


def test_P01_only_a_local_admin_starts_a_pairing(tc):
    _d, phone = pair(tc)                                   # observe control approve
    assert start(tc, token=phone).status == 403


def test_P02_a_pairing_code_expires(tc, clock):
    code = start(tc).json()['code']
    clock.advance(121)
    r = redeem(tc, code)
    assert (r.status, r.json()['error']) == (401, 'invalid_pairing_code')


def test_P03_a_pairing_code_works_once_even_when_raced(tc):
    code = start(tc).json()['code']
    assert redeem(tc, code).status == 200
    assert redeem(tc, code).json()['error'] == 'invalid_pairing_code'
    code = start(tc).json()['code']
    got = []
    ts = [threading.Thread(target=lambda: got.append(redeem(tc, code).status))
          for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(got) == [200, 401, 401, 401]


def test_P28_pairing_exposes_no_permanent_credential(remote):
    s = start(remote, host_label='phone')
    code = s.json()['code']
    assert 'token' not in s.json() and not code.startswith('dev_')
    assert s.json()['url'] == 'https://%s/#pair=%s' % (REMOTE, code)       # a fragment
    r = redeem(remote, code, pin='482913')
    token = r.json()['token']
    events = _events(remote)
    remote.stop()
    with open(connection.db_path(), 'rb') as f:
        db = f.read()
    log, logs = b'', os.path.join(paths.archeus_home(), 'logs')
    for name in os.listdir(logs):
        with open(os.path.join(logs, name), 'rb') as f:
            log += f.read()
    for secret in (code, token, '482913'):
        assert secret.encode() not in db and secret.encode() not in log, secret
        assert secret not in repr(events)
    assert auth.token_hash(token).encode() in db                           # only its hash


def test_R4_failed_redemptions_burn_every_live_code_and_lock_pairing(tc, clock):
    good = start(tc).json()['code']
    got = [redeem(tc, 'x' * 22).status for _ in range(11)]
    assert got[:10] == [401] * 10 and got[10] == 429
    r = redeem(tc, good)
    assert (r.status, r.json()['error']) == (429, 'pairing_locked')
    clock.advance(61)
    assert redeem(tc, good).json()['error'] == 'invalid_pairing_code'      # burned
    assert redeem(tc, start(tc).json()['code']).status == 200


# ── P04, P05, P21, P22, R5: clients and connections ──

def test_P04_P21_a_revoked_client_loses_its_stream_now_and_cannot_come_back(tc):
    did, phone = pair(tc)
    s = SSEClient(tc.base_url, phone)
    try:
        assert s.status == 200
        assert _post(tc, '/v1/devices/%s/revoke' % did).status == 200
        assert s.wait_eof(2.0)                         # closed before the revoke answered
    finally:
        s.close()
    assert _get(tc, '/v1/version', phone).status == 401
    assert SSEClient(tc.base_url, phone).status == 401
    assert _device(tc, did)['presence']['state'] == 'revoked'


def test_P05_two_clients_of_one_user_coexist_and_revoke_independently(tc):
    a, ta = pair(tc, name='phone')
    b, tb = pair(tc, name='tablet', platform='ios')
    got = {d['id']: d for d in _get(tc, '/v1/devices').json()['devices']}
    assert got[a]['state'] == got[b]['state'] == 'ACTIVE' and ta != tb
    assert got[a]['principal_id'] != got[b]['principal_id']
    local = [d for d in got.values() if d['origin'] == 'local']
    assert [d['client_type'] for d in local] == ['cli']
    _post(tc, '/v1/devices/%s/revoke' % a)
    assert _get(tc, '/v1/version', ta).status == 401
    assert _get(tc, '/v1/version', tb).status == 200


def test_P22_two_tabs_of_one_client_see_the_same_frames_and_a_third_is_refused(tc):
    _d, phone = pair(tc)
    one, two = SSEClient(tc.base_url, phone), SSEClient(tc.base_url, phone)
    try:
        assert SSEClient(tc.base_url, phone).status == 429         # 2 per client
        mid = _mission(tc)
        f1 = [f for f in one.frames(1) if f['event'] == 'mission.created']
        f2 = [f for f in two.frames(1) if f['event'] == 'mission.created']
        assert f1 == f2 and f1[0]['data']['subject']['id'] == mid
    finally:
        one.close()
        two.close()


@pytest.mark.core(heartbeat_s=0.1)       # a dropped socket is found at the next write
def test_R5_presence_is_traced_on_transitions_only_with_the_connection(tc):
    did, phone = pair(tc)
    before = _head(tc)
    one = SSEClient(tc.base_url, phone)
    two = SSEClient(tc.base_url, phone)
    p = _device(tc, did)['presence']
    assert (p['state'], p['connections']) == ('connected', 2)
    one.close()
    _wait(lambda: _device(tc, did)['presence']['connections'] == 1, 'one connection left')
    two.close()
    _wait(lambda: _device(tc, did)['presence']['connections'] == 0, 'no connection left')
    traces = [e for e in _events(tc) if e['seq'] > before and e['subject']['id'] == did]
    assert [e['type'] for e in traces] == ['device.stream_opened', 'device.stream_closed']
    assert all(e['payload']['connection_id'] for e in traces)
    assert traces[1]['payload']['reason'] == 'client_gone'
    assert all(e['visibility'] == 'system' and e['actor']['kind'] == 'user_device'
               for e in traces)
    assert _device(tc, did)['presence']['state'] == 'recent'        # it asked a moment ago


# ── P06, P18, P09, P10, P25, P26, P27: state, realtime and resync ──

def test_P06_P18_desktop_and_phone_see_the_same_state_and_the_same_frames(tc):
    _d, phone = pair(tc)
    desk, mob = SSEClient(tc.base_url, tc.token), SSEClient(tc.base_url, phone)
    try:
        mid = _mission(tc)

        def created(s):         # the desktop also hears the phone connect (R5)
            return [f for f in s.frames(1) if f['event'] == 'mission.created'] or created(s)
        want = created(desk)
        assert created(mob) == want and want[0]['data']['subject']['id'] == mid
    finally:
        desk.close()
        mob.close()
    _settle(tc)
    assert _get(tc, '/v1/missions/%s' % mid).json() == _get(tc, '/v1/missions/%s' % mid,
                                                              phone).json()


def test_P09_P26_the_sync_anchor_says_who_where_and_from_which_cursor(tc):
    did, phone = pair(tc, host_label='phone')
    a = _get(tc, '/v1/sync', phone).json()
    assert a['client']['id'] == did and a['client']['origin'] == 'paired'
    assert a['head_seq'] == _head(tc) and 0 <= a['floor_seq'] <= a['head_seq']
    assert a['core']['instance'] == _get(tc, '/v1/sync', phone).json()['core']['instance']
    tc.restart(kill=True)
    b = _get(tc, '/v1/sync', phone).json()
    assert b['core']['instance'] != a['core']['instance'] and b['head_seq'] >= a['head_seq']
    assert b['client']['presence']['state'] == 'recent'        # a new process: seen just now


def test_P10_missed_frames_are_replayed_from_the_cursor_or_refused_410(tc):
    _d, phone = pair(tc)
    cursor = _head(tc)
    mid = _mission(tc)                                 # while the phone was away
    s = SSEClient(tc.base_url, phone, last_event_id=cursor)
    try:
        assert any(f['data']['subject']['id'] == mid for f in s.frames(1))
    finally:
        s.close()
    ahead = SSEClient(tc.base_url, phone, last_event_id=10 ** 9)
    assert ahead.status == 410                         # a restored backup: resync


def test_P25_a_client_can_tell_current_from_stale(slow):
    tc = slow
    _d, phone = pair(tc)
    mid, _eid = _running(tc)
    s = SSEClient(tc.base_url, phone)
    try:
        r = _get(tc, '/v1/missions/%s' % mid, phone)
        read_at = int(r.headers['X-Archeus-Seq'])
        assert read_at <= _head(tc) and r.json()['version'] >= 1
        _post(tc, '/v1/missions/%s/pause' % mid)                   # changed elsewhere
        f = []
        while not f:
            f = [f for f in s.frames(1) if f['data']['subject']['id'] == mid
                 and f['event'] == 'mission.state_changed']
        f = f[0]
        assert f['id'] > read_at                                    # so the view is stale
        again = _get(tc, '/v1/missions/%s' % mid, phone)
        assert int(again.headers['X-Archeus-Seq']) >= f['id']
        assert again.json()['state'] == 'PAUSED'
    finally:
        s.close()
    assert 'X-Archeus-Seq' not in _post(tc, '/v1/missions', {'title': 't',
                                                             'objective': 'o'}).headers


def test_P27_constrained_links_narrow_the_stream_and_page_the_catch_up(tc):
    _d, phone = pair(tc)
    s = SSEClient(tc.base_url, phone, query={'type': 'approval.'})
    t = SSEClient(tc.base_url, phone, query={'type': ['mission.state_', 'mission.created']})
    try:
        mid = _mission(tc)
        got = t.frames(1)
        assert got[0]['event'] == 'mission.created' and got[0]['data']['subject']['id'] == mid
        with pytest.raises(TimeoutError):
            s.frames(1, timeout=1.0)
    finally:
        s.close()
        t.close()
    page = _get(tc, '/v1/events?after=0&limit=2', phone).json()['events']
    assert len(page) == 2


def test_P20_a_stream_narrowed_to_a_project_carries_no_other_projects_frames(tc, tmp_path):
    ids_ = []
    for name in ('one', 'two'):
        parent = tmp_path / name
        parent.mkdir()
        repo = FixtureRepo.create('layered-python', str(parent))
        r = _post(tc, '/v1/projects', {'name': name, 'root_paths': [repo.path]})
        ids_.append(r.json()['project']['id'])
    _settle(tc)
    _d, phone = pair(tc)
    s = SSEClient(tc.base_url, phone, query={'project': ids_[0]})
    try:
        _post(tc, '/v1/missions', {'title': 'B', 'objective': 'o', 'project_id': ids_[1]})
        mid = _post(tc, '/v1/missions', {'title': 'A', 'objective': 'o',
                                         'project_id': ids_[0]}).json()['id']
        seen = []
        while not any(f['data']['subject']['id'] == mid for f in seen):
            seen += s.frames(1)
        assert all(f['data']['scope']['project'] in (ids_[0], None) for f in seen)
    finally:
        s.close()


# ── P11, P12, P13: reconnect, offline intent, stale mutations ──

def test_P11_a_retry_after_a_lost_answer_does_nothing_twice(slow):
    tc = slow
    _d, phone = pair(tc)
    mid, _eid = _running(tc)
    body = {'idempotency_key': 'pause-once'}
    first = _post(tc, '/v1/missions/%s/pause' % mid, body, token=phone)
    again = _post(tc, '/v1/missions/%s/pause' % mid, body, token=phone)
    assert first.status == again.status == 200 and first.json() == again.json()
    moves = [e for e in _events(tc) if e['type'] == 'mission.state_changed'
             and e['subject']['id'] == mid and e['payload']['to'] == 'PAUSED']
    assert len(moves) == 1


def test_P12_a_queued_command_is_refused_unless_declared_replayable(slow):
    tc = slow
    _d, phone = pair(tc)
    mid, _eid = _running(tc)
    before = _head(tc)
    queued = {'X-Archeus-Queued': '1'}
    r = _post(tc, '/v1/missions/%s/pause' % mid, token=phone, headers=queued)
    assert (r.status, r.json()['error']) == (409, 'queued_intent_refused')
    assert [e['type'] for e in _events(tc) if e['seq'] > before
            and e['subject']['id'] == mid] == []                     # nothing written
    ack = tc.http('POST', '/v1/digest/ack', body={'up_to_seq': before}, token=phone,
                  headers=queued)
    assert ack.status == 200
    assert _post(tc, '/v1/missions/%s/pause' % mid, token=phone).status == 200     # live


def test_P13_a_mutation_built_on_a_stale_read_is_refused(slow):
    tc = slow
    _d, phone = pair(tc)
    mid, _eid = _running(tc)
    seen = _get(tc, '/v1/missions/%s' % mid, phone).json()['version']
    assert _post(tc, '/v1/missions/%s/pause' % mid).status == 200   # the desktop moves it
    r = _post(tc, '/v1/missions/%s/resume' % mid, {'expected_version': seen}, token=phone)
    assert (r.status, r.json()['error']) == (409, 'version_conflict')
    assert r.json()['detail']['current'] > seen
    fresh = _get(tc, '/v1/missions/%s' % mid, phone).json()['version']
    r = _post(tc, '/v1/missions/%s/resume' % mid, {'expected_version': fresh}, token=phone)
    assert r.status == 200, r.body


# ── P07, P08, P15, P16, P23, P30: nothing a connection does owns work ──

def test_P07_P08_P23_a_client_going_away_ends_nothing_and_reconnecting_repeats_nothing(slow):
    _d, phone = pair(slow)
    mid, eid = _running(slow)
    did = _device(slow, _d)['id']
    s = SSEClient(slow.base_url, phone)
    s.close()                                               # the phone drops off the network
    _wait(lambda: [e for e in _events(slow) if e['type'] == 'device.stream_closed'
                   and e['subject']['id'] == did], 'Core to see the phone go')
    time.sleep(0.3)                                         # anything it set off has run
    assert _get(slow, '/v1/missions/%s' % mid).json()['state'] == 'EXECUTING'
    assert _get(slow, '/v1/executions/%s' % eid).json()['state'] not in (
        'ENDED_OK', 'ENDED_ERROR', 'ENDED_KILLED')
    cursor = _head(slow)
    back = SSEClient(slow.base_url, phone, last_event_id=cursor)
    try:
        assert back.status == 200
    finally:
        back.close()
    started = [e for e in _events(slow) if e['type'] == 'execution.started']
    assert len(started) == 1
    assert _get(slow, '/v1/missions/%s' % mid).json()['state'] == 'EXECUTING'


def test_P15_remote_execution_control_is_p11s_stop(slow):
    did, phone = pair(slow)
    mid, eid = _running(slow)
    r = _post(slow, '/v1/executions/%s/stop' % eid, token=phone)
    assert r.status == 200, r.body
    _wait(lambda: _get(slow, '/v1/executions/%s' % eid).json()['state'].startswith('ENDED'),
          'the execution ends')
    stops = [e for e in _events(slow) if e['subject']['id'] == eid
             and e['actor']['id'] == _device(slow, did)['principal_id']]
    assert stops, 'the stop is recorded as the phone principal'


def test_P16_P30_resuming_is_p12s_and_a_connection_is_never_a_session(slow, tmp_path):
    _d, phone = pair(slow)
    ref = 'ref-' + ids.new_ulid()
    FakeSessions('fake_a').write(ref, [('user', 'hello')])
    sid = _post(slow, '/v1/sessions', {'harness_id': 'fake_a', 'cwd': str(tmp_path),
                                       'provider_session_ref': ref}).json()['id']
    before = _get(slow, '/v1/sessions').json()['sessions']
    head = _head(slow)
    for _ in range(2):                                           # connect, drop, reconnect
        SSEClient(slow.base_url, phone).close()
    _wait(lambda: {e['type'] for e in _events(slow) if e['seq'] > head} ==
          {'device.stream_opened', 'device.stream_closed'}, 'the traces')
    assert _get(slow, '/v1/sessions').json()['sessions'] == before       # P30
    r = _post(slow, '/v1/sessions/%s/resume' % sid, {'request_id': 'r1'}, token=phone)
    assert r.status == 200 and r.json()['id'] == sid and r.json()['launch'], r.body
    assert [s['id'] for s in _get(slow, '/v1/sessions').json()['sessions']] == [sid]


def test_P17_verification_state_is_p13s_rows_read_by_the_phone(tc):
    _d, phone = pair(tc)
    mid = _mission(tc)
    _settle(tc)
    mine = _get(tc, '/v1/missions/%s/verifications' % mid, phone)
    assert mine.status == 200
    assert mine.json() == _get(tc, '/v1/missions/%s/verifications' % mid).json()


# ── P14, P24, R1: approvals from a paired client ──

def test_P14_R1_a_paired_client_approves_through_p9_with_its_pin(deploy):
    _d, phone = pair(deploy, platform='web', pin='482913')       # `web`, yet paired (R1)
    mid = _mission(deploy)
    a = _pending(deploy, mid)
    assert a['step_up']
    body = {'decision': 'approve', 'action_hash': a['action_hash']}
    r = _post(deploy, '/v1/approvals/%s/decide' % a['id'], body, token=phone)
    assert (r.status, r.json()['error']) == (422, 'guard_failed')           # no proof
    r = _post(deploy, '/v1/approvals/%s/decide' % a['id'],
              dict(body, action_hash='0' * 64, step_up='482913'), token=phone)
    assert (r.status, r.json()['error']) == (422, 'guard_failed')           # other action
    r = _post(deploy, '/v1/approvals/%s/decide' % a['id'], dict(body, step_up='482913'),
              token=phone)
    assert r.status == 200 and r.json()['state'] == 'APPROVED', r.body
    outcomes = [d['outcome'] for d in _get(deploy, '/v1/policy-decisions?mission=%s'
                                           % mid).json()['policy_decisions']]
    assert 'approved' in outcomes


def test_R1_five_wrong_pins_revoke_the_client_and_no_pin_means_no_step_up(deploy):
    did, phone = pair(deploy, pin='482913')
    _n, nopin = pair(deploy, platform='web')
    assert _device(deploy, _n)['capabilities'] == {'step_up': 'none'}
    mid = _mission(deploy)
    a = _pending(deploy, mid)
    body = {'decision': 'approve', 'action_hash': a['action_hash']}
    assert _post(deploy, '/v1/approvals/%s/decide' % a['id'], body,
                 token=nopin).json()['error'] == 'guard_failed'
    for i in range(5):
        r = _post(deploy, '/v1/approvals/%s/decide' % a['id'], dict(body, step_up='000000'),
                  token=phone)
        assert r.json()['error'] == 'guard_failed', i
    assert _get(deploy, '/v1/version', phone).status == 401
    assert _device(deploy, did)['state'] == 'REVOKED'
    assert _get(deploy, '/v1/approvals/%s' % a['id']).json()['state'] == 'PENDING'


def test_P24_reconnecting_during_an_approval_decides_it_once(deploy):
    _d, phone = pair(deploy, pin='482913')
    mid = _mission(deploy)
    a = _pending(deploy, mid)
    SSEClient(deploy.base_url, phone).close()                     # connection lost
    assert _get(deploy, '/v1/approvals/%s' % a['id'], phone).json()['state'] == 'PENDING'
    body = {'decision': 'approve', 'action_hash': a['action_hash'], 'step_up': '482913',
            'idempotency_key': 'once'}
    first = _post(deploy, '/v1/approvals/%s/decide' % a['id'], body, token=phone)
    again = _post(deploy, '/v1/approvals/%s/decide' % a['id'], body, token=phone)
    assert first.status == 200 and first.json() == again.json()
    decided = [e for e in _events(deploy) if e['type'] == 'approval.state_changed'
               and e['subject']['id'] == a['id'] and e['payload']['to'] == 'APPROVED']
    assert len(decided) == 1


# ── P19, P29: who may see, and who did it ──

def test_P19_a_non_user_principal_cannot_read_or_subscribe(tc):
    brain = tc.client()._principal_client('brain')
    assert _get(tc, '/v1/missions', brain.token).json()['error'] == 'scope_required'
    assert SSEClient(tc.base_url, brain.token).status == 403
    assert _get(tc, '/v1/devices', brain.token).status == 403


def test_P29_a_client_originated_mutation_is_traceable_to_its_client(slow):
    tc = slow
    did, phone = pair(tc, name='Pixel', host_label='phone')
    s = SSEClient(tc.base_url, phone)
    mid, _eid = _running(tc)
    assert _post(tc, '/v1/missions/%s/pause' % mid, token=phone).status == 200
    s.close()
    d = _device(tc, did)
    (pause,) = [e for e in _events(tc) if e['type'] == 'mission.state_changed'
                and e['subject']['id'] == mid and e['payload']['to'] == 'PAUSED']
    assert pause['actor'] == {'kind': 'user_device', 'id': d['principal_id']}
    assert (d['name'], d['host_label'], d['origin']) == ('Pixel', 'phone', 'paired')
    opened = [e for e in _events(tc) if e['type'] == 'device.stream_opened'
              and e['subject']['id'] == did]
    assert opened and opened[0]['payload']['connection_id']


# ── R2, R3: remote hosts ──

def test_R2_a_tunnel_forwarded_request_cannot_reach_a_local_only_route(remote):
    tunnel = {'Host': REMOTE}                   # the peer is loopback: the tunnel forwards
    for path, body in (('/v1/devices/pair/start', {}), ('/v1/devices/launch/code', {}),
                       ('/v1/devices/launch/redeem', {'code': 'x', 'platform': 'web'})):
        r = remote.http('POST', path, body=body, headers=tunnel)
        assert (r.status, r.json()['error']) == (403, 'host_not_allowed'), path
    assert start(remote).status == 200                            # from this machine


def test_R3_a_remote_host_is_accepted_only_as_itself_over_https(remote):
    _d, phone = pair(remote)
    ok = {'Host': REMOTE, 'Origin': 'https://' + REMOTE, 'Sec-Fetch-Site': 'same-origin'}
    assert remote.http('GET', '/v1/version', token=phone, headers=ok).status == 200
    plain = dict(ok, Origin='http://' + REMOTE)
    assert remote.http('GET', '/v1/version', token=phone,
                       headers=plain).json()['error'] == 'cross_site'
    other = {'Host': 'evil.ts.net'}
    assert remote.http('GET', '/v1/version', token=phone,
                       headers=other).json()['error'] == 'host_not_allowed'
    assert remote.http('GET', '/v1/version', token=None,
                       headers={'Host': REMOTE}).status == 401
    # the CLI's local token is honoured on this machine only (D21)
    r = remote.http('GET', '/v1/version', headers=ok)
    assert (r.status, r.json()['error']) == (403, 'host_not_allowed')
    code = start(remote).json()['code']
    r = request(remote.base_url, 'POST', '/v1/devices/pair/redeem', headers=ok,
                body={'code': code, 'platform': 'ios'})
    assert r.status == 200                                       # redemption is remote


def test_the_local_token_and_a_launch_browser_stay_local_after_p15(tc):
    got = {d['client_type']: d for d in _get(tc, '/v1/devices').json()['devices']}
    assert got['cli']['origin'] == 'local' and got['cli']['capabilities'] == {'step_up': 'local'}
    code = tc.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    r = tc.http('POST', '/v1/devices/launch/redeem', body={'code': code, 'platform': 'web'})
    d = _device(tc, r.json()['device_id'])
    assert (d['origin'], d['client_type'], d['scopes']) == ('local', 'spa', ['observe'])


# ── the CLI (§18) ──

def test_the_cli_pairs_lists_and_revokes(tc, capsys):
    from archeus.cli import main as cli
    assert cli.main(['pair', '--name', 'Pixel', '--scopes', 'observe,control']) == 0
    out = capsys.readouterr().out
    code = out.split('once): ')[1].split()[0]
    assert 'scopes: observe, control' in out and '--remote-host' in out
    did = redeem(tc, code).json()['device_id']
    assert cli.main(['devices']) == 0
    listed = capsys.readouterr().out
    assert did in listed and 'paired' in listed and 'Pixel' in listed
    assert cli.main(['devices', 'revoke', did]) == 0
    assert _device(tc, did)['state'] == 'REVOKED'
    assert cli.main(['pair', '--scopes', 'control']) == 2          # observe is required
    assert cli.main(['core', '--remote-host', '*.ts.net']) == 2      # refused, nothing started
