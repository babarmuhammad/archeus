"""Plan edit over a real Core (P19 S2; p19-design-gate B4): `POST
/v1/plans/{id}/edit` is a person's next PlanVersion of the plan awaiting them.
Only the plan in force of an APPROVAL_REQUIRED mission, with the `approve`
scope; the mission is sent back and the edit proposed in one transaction, so
the validator (a refusal is the route's 422, writing nothing), the supersession
of approvals and the auto-approve / needs-approval split run as for a planner's
version. Core keys the tasks in the order sent; Core's serialisation edges are
derived again, never adopted as the person's."""

import time
import uuid

import pytest

from archeus.core import engine, ports, runtime
from v1.judge.http import TempCore

R1 = {'handle': 'r1', 'kind': 'requirement', 'origin': 'explicit', 'text': 'deploy it'}
DEPLOY = dict(engine.SKELETON_PLAN, inputs=[R1],
              coverage=[{'requirement': 'r1', 'origin': 'explicit', 'tasks': ['work']}],
              tasks=[dict(engine.SKELETON_PLAN['tasks'][0], action_classes=['deploy'],
                          serves=['r1'])])
DONE = [{'text': 'it is done', 'check': 'automatic'}]


@pytest.fixture
def core(archeus_home):
    tc = TempCore(archeus_home, ports=runtime.Ports(brain=ports.FixedPlanBrain(DEPLOY))).start()
    yield tc
    tc.stop(kill=True)


def _key():
    return 'k-' + uuid.uuid4().hex


def _wait(tc, mid, pred, what):
    deadline = time.monotonic() + 30
    while True:
        m = tc.http('GET', '/v1/missions/' + mid).json()
        if pred(m['state']):
            return m
        assert time.monotonic() < deadline, what
        time.sleep(0.05)


def _asking(tc, title):
    mid = tc.http('POST', '/v1/missions', body={'title': title, 'objective': 'o',
                                                'idempotency_key': _key()}).json()['id']
    _wait(tc, mid, lambda s: s == 'APPROVAL_REQUIRED', 'the mission never asked')
    return mid, tc.http('GET', '/v1/missions/%s/plan' % mid).json()['plan']


def _approvals(tc, mid):
    return tc.http('GET', '/v1/approvals?mission=' + mid).json()['approvals']


def _versions(tc, mid):
    return tc.http('GET', '/v1/missions/%s/plan' % mid).json()['versions']


def _edit(tc, plan, tasks, **kw):
    body = dict({'tasks': tasks, 'expected_version': plan['version'],
                 'idempotency_key': _key()}, **kw)
    return tc.http('POST', '/v1/plans/%s/edit' % plan['id'], body=body)


def _task(key, title, *, kind='research', classes=('read',), deps=(), serves=(), touches=()):
    return {'key': key, 'title': title, 'kind': kind, 'objective': 'Do: ' + title,
            'action_classes': list(classes), 'depends_on': list(deps), 'serves': list(serves),
            'touches': list(touches), 'acceptance': DONE}


def test_an_edit_is_the_persons_next_version_and_asks_again(core):
    mid, p1 = _asking(core, 'Edit me')
    (a1,) = _approvals(core, mid)
    tasks = [_task('prep', 'Prepare'),
             _task(p1['tasks'][0]['key'], 'Deploy it', kind='code_change', classes=('deploy',),
                   deps=('prep',), serves=('r1',))]
    r = _edit(core, p1, tasks)
    assert r.status == 200, r.body
    out = r.json()
    assert (out['plan_version'], out['changed']) == (2, True)
    p2 = core.http('GET', '/v1/plans/' + out['plan_id']).json()
    me = core.http('GET', '/v1/sync').json()['client']['principal_id']
    assert p2['edited_by'] == me and p2['supersedes_plan_id'] == p1['id']
    # the person's version: no planner provenance, the replaced version's lists
    assert (p2['round_seq'], p2['route_decision_id'], p2['context_package_id']) == (None,) * 3
    assert p2['summary'] == p1['summary'] and p2['inputs'] == p1['inputs']
    assert p2['coverage'] == [{'requirement': 'r1', 'origin': 'explicit', 'tasks': ['t2']}]
    # keyed by Core in the order sent, dependencies following the keys
    assert [(t['key'], t['title'], t['depends_on']) for t in p2['tasks']] == [
        ('t1', 'Prepare', []), ('t2', 'Deploy it', ['t1'])]
    # the replaced version and its approval ended with it (P9 D14) ...
    assert core.http('GET', '/v1/plans/' + p1['id']).json()['state'] == 'SUPERSEDED'
    assert core.http('GET', '/v1/approvals/' + a1['id']).json()['state'] == 'SUPERSEDED'
    # ... and the edit still deploys, so the plan gate asks again, for v2
    assert core.http('GET', '/v1/missions/' + mid).json()['state'] == 'APPROVAL_REQUIRED'
    live = [a for a in _approvals(core, mid) if a['state'] == 'PENDING']
    assert [a['plan_id'] for a in live] == [p2['id']]
    msgs = core.http('GET', '/v1/conversations/primary/messages').json()['messages']
    assert any(c['type'] == 'approval' and c['ref']['id'] == live[0]['id']
               for m in msgs for c in m['cards'])


def test_an_edit_within_policy_is_approved_as_a_planners_would_be(core):
    mid, p1 = _asking(core, 'Edit me within policy')
    r = _edit(core, p1, [_task('work', 'Write it', kind='code_change', classes=('write_repo',),
                               serves=('r1',))])
    assert r.status == 200, r.body
    _wait(core, mid, lambda s: s != 'APPROVAL_REQUIRED', 'the edited plan was never decided')
    assert core.http('GET', '/v1/plans/' + r.json()['plan_id']).json()['state'] == 'APPROVED'
    assert not [a for a in _approvals(core, mid) if a['state'] == 'PENDING']


@pytest.mark.parametrize('tasks, why', [
    ([], 'at least one task'),
    ([_task('a', 'A', deps=('b',), serves=('r1',)), _task('b', 'B', deps=('a',))], 'cycle'),
    ([_task('a', 'A', deps=('nope',), serves=('r1',))], 'not in the plan'),
    ([dict(_task('a', 'A', serves=('r1',)), acceptance=[])], 'no acceptance criterion'),
    ([_task('a', 'A')], 'explicit requirement r1'),
    ([dict(_task('a', 'A', serves=('r1',)), inputs=[{'from_task': 'zz', 'what': 'x'}])],
     'input from zz'),
])
def test_the_validator_refuses_with_a_422_and_nothing_is_written(core, tasks, why):
    mid, p1 = _asking(core, 'Refuse my edit')
    r = _edit(core, p1, tasks)
    assert (r.status, r.json()['error']) == (422, 'guard_failed'), r.body
    assert why in r.json()['detail']['reason']
    assert [v['plan_version'] for v in _versions(core, mid)] == [1]
    assert core.http('GET', '/v1/missions/' + mid).json()['state'] == 'APPROVAL_REQUIRED'
    assert [a['state'] for a in _approvals(core, mid)] == ['PENDING']


def test_a_replay_is_one_edit_and_a_stale_or_replaced_version_is_refused(core):
    mid, p1 = _asking(core, 'Edit me once')
    tasks = [_task('work', 'Deploy it', kind='code_change', classes=('deploy',), serves=('r1',))]
    stale = _edit(core, p1, tasks, expected_version=p1['version'] + 1)
    assert (stale.status, stale.json()['error']) == (409, 'version_conflict'), stale.body
    assert len(_versions(core, mid)) == 1
    key = _key()
    first = _edit(core, p1, tasks, idempotency_key=key)
    again = _edit(core, p1, tasks, idempotency_key=key)
    assert first.status == again.status == 200, (first.body, again.body)
    assert again.json()['plan_id'] == first.json()['plan_id']
    assert [v['plan_version'] for v in _versions(core, mid)] == [1, 2]
    # v1 is no longer the plan in force: editing it is refused
    old = _edit(core, dict(p1, version=None), tasks)
    assert (old.status, old.json()['error']) == (422, 'invalid_transition'), old.body


def test_only_the_approve_scope_and_only_while_the_plan_awaits_approval(core):
    mid, p1 = _asking(core, 'Guard my plan')
    tasks = [_task('work', 'Deploy it', kind='code_change', classes=('deploy',), serves=('r1',))]
    code = core.http('POST', '/v1/devices/launch/code', body={'scopes': ['observe', 'control']})
    token = core.http('POST', '/v1/devices/launch/redeem', token=None,
                      body={'code': code.json()['code'], 'platform': 'web'}).json()['token']
    no = core.http('POST', '/v1/plans/%s/edit' % p1['id'], token=token,
                   body={'tasks': tasks, 'idempotency_key': _key()})
    assert (no.status, no.json()['error']) == (403, 'scope_required'), no.body
    (a,) = _approvals(core, mid)
    ok = core.http('POST', '/v1/approvals/%s/decide' % a['id'], body={
        'decision': 'approve', 'action_hash': a['action_hash'], 'idempotency_key': _key()})
    assert ok.status == 200, ok.body
    _wait(core, mid, lambda s: s != 'APPROVAL_REQUIRED', 'the approved mission never moved')
    late = _edit(core, dict(p1, version=None), tasks)
    assert (late.status, late.json()['error']) == (422, 'invalid_transition'), late.body
    assert len(_versions(core, mid)) == 1


def test_cores_serialisation_edges_are_derived_again_not_adopted(core):
    mid, p1 = _asking(core, 'Serialise my edit')
    same = ('src/app.py',)
    r = _edit(core, p1, [
        _task('a', 'A', kind='code_change', classes=('deploy',), serves=('r1',), touches=same),
        _task('b', 'B', kind='code_change', classes=('write_repo',), touches=same)])
    assert r.status == 200, r.body
    p2 = core.http('GET', '/v1/plans/' + r.json()['plan_id']).json()
    assert [(s['task'], s['after']) for s in p2['serialised']] == [('t2', 't1')]
    # sent back exactly as read, Core's edge is still Core's, not the person's
    keep = ('key', 'title', 'kind', 'objective', 'action_classes', 'depends_on', 'serves',
            'touches', 'acceptance')
    r3 = _edit(core, p2, [{k: t[k] for k in keep} for t in p2['tasks']])
    assert r3.status == 200, r3.body
    p3 = core.http('GET', '/v1/plans/' + r3.json()['plan_id']).json()
    assert [(s['task'], s['after']) for s in p3['serialised']] == [('t2', 't1')]
    assert p3['plan_version'] == 3 and p3['edited_by'] == p2['edited_by']
