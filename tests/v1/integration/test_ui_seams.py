"""P16's backend seams (p16-design-gate §3.2, D2–D6): the attention read, a
mission's timeline, an execution's output tail, the launch code's grant and the
PWA's root files. Each is a read over rows (or a transport change): the tests
insert the rows a phase would have written and check what the read shows —
and, as much, what it must not show."""

import json
import os

import pytest

from archeus.api import auth
from archeus.core.application import attention, commands
from archeus.core.domain import entities, ids
from archeus.core.domain.values import Ref
from archeus.core.execution import output
from archeus.harnesses.fake import FakeHarness
from archeus.infra.paths import ExecPaths
from v1.judge.http import request

WS = ids.GLOBAL_WORKSPACE


def _tx(db, fn):
    """Run *fn* as one writer command: a row a phase would have written. The
    writer refuses a mutation with no event, so each carries one about a
    mission no test reads."""
    from archeus.core.domain.events import new_event

    def run(tx, **_):
        fn(tx)
        tx.append(new_event('mission.updated', Ref('mission', ids.new_id('mission')),
                            Ref('user_device', ids.new_id('principal')), payload={},
                            workspace=WS))
    return db.writer.execute(run, {})


def _mission(db, actor, title='M'):
    return db.writer.execute(commands.create_mission,
                             {'actor': actor, 'title': title, 'objective': 'o'})['id']


def _plan(db, actor, mid, state='PROPOSED'):
    pid = ids.new_id('plan')
    _tx(db, lambda tx: tx.insert(entities.Plan(id=pid, mission_id=mid, plan_version=1,
                                               state=state), actor=actor))
    return pid


def _task(db, actor, mid, pid, key='t1'):
    tid = ids.new_id('task')
    _tx(db, lambda tx: tx.insert(entities.Task(id=tid, plan_id=pid, mission_id=mid, key=key,
                                               title='T', kind='code_change'), actor=actor))
    return tid


def _approval(db, actor, mid, pid, state='PENDING'):
    aid = ids.new_id('approval')
    _tx(db, lambda tx: tx.insert(entities.Approval(
        id=aid, subject=Ref('plan', pid), action_hash=os.urandom(32).hex(), requested_by=actor.id,
        kind='plan', mission_id=mid, plan_id=pid, plan_version=1, state=state,
        expires_at='2999-01-01T00:00:00.000Z'), actor=actor))
    return aid


def _verification(db, actor, pid, subject, state, holds=False):
    vid = ids.new_id('verification')
    _tx(db, lambda tx: tx.insert(entities.Verification(
        id=vid, subject=subject, verifier='generic_human', plan_id=pid, state=state,
        holds_mission=holds, error='runner missing' if state == 'ERROR' else None,
        criterion=0 if subject.kind == 'mission' else None),
        actor=actor))
    return vid


def _knowledge(db, actor, state):
    kid = ids.new_id('knowledge_item')
    _tx(db, lambda tx: tx.insert(entities.KnowledgeItem(
        id=kid, workspace_id=WS, type='PREFERENCE', title='use tabs', state=state),
        actor=actor))
    return kid


def _kinds(db):
    with db.read() as conn:
        return [(i['kind'], i['ref']['id'], i['state']) for i in attention.attention(conn)['items']]


# ── D3: attention ──

def test_attention_lists_exactly_what_waits_on_the_user(db, actor):
    mid = _mission(db, actor)
    pid = _plan(db, actor, mid)
    tid = _task(db, actor, mid, pid)
    pending = _approval(db, actor, mid, pid)
    _approval(db, actor, mid, pid, state='APPROVED')          # decided: waits on nobody
    human = _verification(db, actor, pid, Ref('task', tid), 'AWAITING_HUMAN')
    held = _verification(db, actor, pid, Ref('mission', mid), 'ERROR', holds=True)
    _verification(db, actor, pid, Ref('task', tid), 'ERROR')  # Core retries it
    _verification(db, actor, pid, Ref('task', tid), 'PASSED')
    cand = _knowledge(db, actor, 'CANDIDATE')
    _knowledge(db, actor, 'CONFIRMED')
    got = _kinds(db)
    assert got == [('approval', pending, 'PENDING'),
                   ('verification', human, 'AWAITING_HUMAN'),
                   ('verification', held, 'ERROR'),
                   ('knowledge', cand, 'CANDIDATE')]
    with db.read() as conn:
        items = attention.attention(conn)['items']
    a = items[0]
    assert (a['reason_code'], a['mission_id'], a['expires_at']) == (
        'plan', mid, '2999-01-01T00:00:00.000Z')
    assert 'eligible' in a                  # P9's own judgement, reused
    assert items[1]['mission_id'] == mid    # a task's verification names its mission
    assert (items[1]['reason_code'], items[2]['reason_code']) == ('acceptance', 'verifier_error')


def test_attention_names_blocked_planning_drift_suspension_and_reauth(db, actor):
    mid = _mission(db, actor)
    _tx(db, lambda tx: tx.update(entities.Mission, mid, {'planning_blocked': {
        'kind': 'clarification', 'questions': ['Which chart library?'], 'missing': [],
        'conflicts': []}}, actor=actor))
    prj = ids.new_id('project')
    rep, aut, acc = ids.new_id('repository'), ids.new_id('automation'), ids.new_id('account')

    def world(tx):
        tx.insert(entities.Project(id=prj, workspace_id=WS, name='P', root_paths=[]), actor=actor)
        tx.insert(entities.Repository(id=rep, workspace_id=WS, project_id=prj, path='C:/r',
                                      path_key='c:/r', architecture_state='DRIFTED'), actor=actor)
        tx.insert(entities.Repository(id=ids.new_id('repository'), workspace_id=WS,
                                      project_id=prj, path='C:/s', path_key='c:/s',
                                      architecture_state='CONSISTENT'), actor=actor)
        tx.insert(entities.Automation(id=aut, workspace_id=WS, name='docs', state='SUSPENDED'),
                  actor=actor)
        tx.insert(entities.Account(id=acc, harness_id='fake', label='B', auth_kind='api_key',
                                   health='UNAUTHENTICATED'), actor=actor)
        tx.insert(entities.Account(id=ids.new_id('account'), harness_id='fake', label='A',
                                   auth_kind='api_key', health='AVAILABLE'), actor=actor)
    _tx(db, world)
    assert _kinds(db) == [('mission', mid, 'CREATED'), ('drift', rep, 'DRIFTED'),
                          ('automation', aut, 'SUSPENDED'), ('account', acc, 'UNAUTHENTICATED')]
    with db.read() as conn:
        m = attention.attention(conn)['items'][0]
    assert (m['reason_code'], m['reason']) == ('clarification', 'Which chart library?')


def test_a_finished_mission_waits_on_nobody_even_with_a_stale_block(db, actor):
    mid = _mission(db, actor)
    _tx(db, lambda tx: tx.update(entities.Mission, mid, {'planning_blocked': {
        'kind': 'policy'}}, actor=actor))
    assert _kinds(db) == [('mission', mid, 'CREATED')]
    _tx(db, lambda tx: tx.conn.execute("UPDATE missions SET state = 'CANCELLED' WHERE id = ?",
                                       (mid,)))
    assert _kinds(db) == []


# ── D5: the mission timeline ──

def test_the_timeline_holds_the_missions_own_events_and_no_other(db, actor):
    mine, other = _mission(db, actor, 'mine'), _mission(db, actor, 'other')
    pid, opid = _plan(db, actor, mine), _plan(db, actor, other)
    tid, otid = _task(db, actor, mine, pid), _task(db, actor, other, opid)
    from archeus.core.domain.events import new_event

    def emit(kind, eid):
        return lambda tx: tx.append(new_event('%s.state_changed' % kind if kind != 'mission'
                                              else 'mission.updated', Ref(kind, eid), actor,
                                              payload={}, workspace=WS))
    for fn in (emit('task', tid), emit('task', otid), emit('plan', pid), emit('plan', opid)):
        _tx(db, fn)
    with db.read() as conn:
        t = attention.timeline(conn, mine)
    subjects = [(e['subject']['kind'], e['subject']['id']) for e in t['events']]
    assert ('task', tid) in subjects and ('plan', pid) in subjects
    assert ('task', otid) not in subjects and ('plan', opid) not in subjects
    assert ('mission', mine) in subjects                         # its own creation
    seqs = [e['seq'] for e in t['events']]
    assert seqs == sorted(seqs, reverse=True) and t['next_before'] is None
    with db.read() as conn:
        page = attention.timeline(conn, mine, limit=1)
        older = attention.timeline(conn, mine, before=page['next_before'], limit=100)
    assert len(page['events']) == 1 and page['next_before'] == seqs[0]
    assert [e['seq'] for e in older['events']] == seqs[1:]


def test_the_timeline_of_an_unknown_mission_is_not_found(db):
    from archeus.infra.db.writer import NotFound
    with db.read() as conn, pytest.raises(NotFound):
        attention.timeline(conn, ids.new_id('mission'))


# ── D4: the output tail ──

def test_the_output_tail_is_redacted_resumable_and_empty_before_a_process(tmp_path):
    exe = entities.Execution(id=ids.new_id('execution'), task_id=ids.new_id('task'),
                             mission_id=ids.new_id('mission'), harness_id='fake')
    assert output.read(exe, FakeHarness())['available'] is False        # no process yet
    exe = entities.Execution(**dict(exe.to_dict(), pid=os.getpid(), create_time=1.0))
    p = ExecPaths(exe.id)
    os.makedirs(p.dir, exist_ok=True)
    secret = 'dev_' + 'x' * 30
    with open(p.stream, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'type': 'text', 'text': 'token %s here' % secret}) + '\n')
        f.write(json.dumps({'type': 'tool', 'args': {'auth': 'Bearer abcdefghijkl'}}) + '\n')
        f.write('{"type": "partial"')                          # not yet a whole line
    got = output.read(exe, FakeHarness())
    assert got['available'] and [e['type'] for e in got['events']] == ['text', 'tool']
    assert secret not in json.dumps(got) and 'abcdefghijkl' not in json.dumps(got)
    assert '[redacted]' in got['events'][0]['text']
    again = output.read(exe, FakeHarness(), got['next_offset'])
    assert again['events'] == [] and again['next_offset'] == got['next_offset']
    assert output.read(exe, None)['available'] is False                  # no adapter


# ── D2: the launch code's grant, and the HTTP rows of D3–D6 ──

def _redeem(tc, code):
    return request(tc.base_url, 'POST', '/v1/devices/launch/redeem',
                   body={'code': code, 'platform': 'web'})


def test_a_launch_code_carries_the_grant_its_minter_chose(tc):
    plain = tc.http('POST', '/v1/devices/launch/code', body={})
    assert plain.status == 200 and plain.json()['scopes'] == ['observe']      # default
    r = _redeem(tc, plain.json()['code'])
    assert r.json()['scopes'] == ['observe']
    denied = tc.http('POST', '/v1/missions', token=r.json()['token'],
                     body={'title': 't', 'objective': 'o', 'idempotency_key': 'k1'})
    assert (denied.status, denied.json()['detail']) == (403, {'scope': 'control'})

    full = tc.http('POST', '/v1/devices/launch/code',
                   body={'scopes': ['admin', 'observe', 'control', 'approve']})
    assert full.json()['scopes'] == ['observe', 'control', 'approve', 'admin']  # ordered
    token = _redeem(tc, full.json()['code']).json()['token']
    ok = tc.http('POST', '/v1/missions', token=token,
                 body={'title': 't', 'objective': 'o', 'idempotency_key': 'k2'})
    assert ok.status == 200
    (d,) = [d for d in tc.http('GET', '/v1/devices').json()['devices']
            if d['scopes'] == ['observe', 'control', 'approve', 'admin']
            and d['name'] == 'browser (web)']
    assert d['capabilities'] == {'step_up': 'local'}

    assert tc.http('POST', '/v1/devices/launch/code',
                   body={'scopes': ['control']}).status == 400          # observe always


def test_a_launch_grant_never_exceeds_the_minters_own_scopes(tc):
    s = tc.http('POST', '/v1/devices/pair/start', body={'scopes': ['observe', 'admin']})
    token = request(tc.base_url, 'POST', '/v1/devices/pair/redeem',
                    body={'code': s.json()['code'], 'platform': 'web'}).json()['token']
    r = tc.http('POST', '/v1/devices/launch/code', token=token,
                body={'scopes': ['observe', 'control']})
    assert (r.status, r.json()['error'], r.json()['detail']) == (
        403, 'scope_required', {'scope': 'control'})
    assert tc.http('POST', '/v1/devices/launch/code', token=token,
                   body={'scopes': ['observe', 'admin']}).status == 200
    assert auth.LAUNCH_SCOPES == ('observe',)


def test_the_p16_reads_answer_over_http_with_their_scopes(tc):
    r = tc.http('GET', '/v1/attention')
    assert r.status == 200 and set(r.json()) == {'items', 'count'}
    assert r.headers.get('X-Archeus-Seq') is not None
    mid = tc.http('POST', '/v1/missions', body={'title': 't', 'objective': 'o',
                                                'idempotency_key': 'k3'}).json()['id']
    t = tc.http('GET', '/v1/missions/%s/timeline?limit=5' % mid)
    assert t.status == 200 and t.json()['events'][0]['subject'] in (
        {'kind': 'mission', 'id': mid}, {'kind': t.json()['events'][0]['subject']['kind'],
                                         'id': t.json()['events'][0]['subject']['id']})
    assert tc.http('GET', '/v1/missions/%s/timeline?limit=0' % mid).status == 400
    assert tc.http('GET', '/v1/missions/%s/timeline' % ids.new_id('mission')).status == 404
    assert tc.http('GET', '/v1/executions/%s/stream' % ids.new_id('execution')).status == 404
    assert tc.http('GET', '/v1/executions/x/stream?from=-1').status == 400
    for path in ('/v1/attention', '/v1/missions/%s/timeline' % mid):
        assert request(tc.base_url, 'GET', path).status == 401            # no token


def test_the_pwa_root_files_are_served_with_their_types_and_the_csp(tc, tmp_path):
    root = tc.core.api.static.dir = str(tmp_path)
    for name, body in (('sw.js', 'self.addEventListener("fetch", () => {});'),
                       ('manifest.webmanifest', '{"name": "Archeus"}')):
        with open(os.path.join(root, name), 'w', encoding='utf-8') as f:
            f.write(body)
    sw = request(tc.base_url, 'GET', '/sw.js')
    assert sw.status == 200 and sw.headers['Content-Type'].startswith('text/javascript')
    assert sw.headers['Content-Security-Policy'] == auth.CSP
    m = request(tc.base_url, 'GET', '/manifest.webmanifest')
    assert m.headers['Content-Type'] == 'application/manifest+json'
    assert request(tc.base_url, 'GET', '/icon.png').status == 404            # names only
