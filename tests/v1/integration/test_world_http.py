"""P4 acceptance over HTTP and across a real process (p4-design-gate §13.2:
W18, W26–W30, and the worker-failure row of §11). The in-process scenarios
are test_world.py."""

import ast
import json
import os
import time

import pytest

from archeus.core import runtime
from archeus.core.world import worker as world_worker
from v1.judge.http import CoreProcess, SSEClient, request
from v1.judge.support import FixtureRepo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
NO_CORE_API = {'statement': 'core must not import api', 'kind': 'forbid_dependency',
               'spec': {'from': 'app/core/**', 'to': 'app/api/**'}}


def _wait(fn, timeout=30, what='a condition'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = fn()
        if got:
            return got
        time.sleep(0.05)
    raise AssertionError('timed out waiting for %s' % what)


def _register(core, repo, constraints=()):
    r = core.http('POST', '/v1/projects', body={'name': 'p', 'root_paths': [repo.path],
                                                'idempotency_key': 'reg-' + repo.path})
    assert r.status == 200, r.body
    out = r.json()
    for i, c in enumerate(constraints):
        d = core.http('POST', '/v1/projects/%s/constraints' % out['project']['id'],
                      body=dict(c, idempotency_key='c%d' % i))
        assert d.status == 200, d.body
    return out['project']['id'], out['repositories'][0]['id']


def _repository(core, pid, rid):
    (r,) = [x for x in core.http('GET', '/v1/projects/%s' % pid).json()['repositories']
            if x['id'] == rid]
    return r


@pytest.fixture
def repo(tmp_path):
    parent = tmp_path / 'repos'
    parent.mkdir()
    return FixtureRepo.create('layered-python', str(parent))


# ── W18 Core killed mid-inspection ──

def test_w18_a_core_killed_mid_walk_leaves_one_completed_inspection(archeus_home, repo):
    gate = os.path.join(str(archeus_home), 'walk-gate')
    first = CoreProcess(archeus_home, hold_inspection=gate).start()
    pid, rid = _register(first, repo)

    def running():
        got = first.http('GET', '/v1/repositories/%s/inspections' % rid).json()['inspections']
        return [i for i in got if i['state'] == 'RUNNING']
    (held,) = _wait(running, what='the walk to start')
    first.kill()
    again = CoreProcess(archeus_home).start()
    try:
        _wait(lambda: _repository(again, pid, rid)['architecture_state'] == 'CONSISTENT',
              what='the assessment after the restart')
        got = again.http('GET', '/v1/repositories/%s/inspections' % rid).json()['inspections']
        assert [(i['id'], i['state'], i['revision']) for i in got] == [
            (held['id'], 'COMPLETED', repo.head())]
        moves = [e['payload'] for e in again.http('GET', '/v1/events?limit=1000').json()['events']
                 if e['type'] == 'repository_inspection.state_changed'
                 and e['subject']['id'] == held['id']]
        assert [(m['to'], m['reason']) for m in moves][-4:] == [
            ('FAILED', 'core_restarted'), ('SCHEDULED', 'retry after core_restarted'),
            ('RUNNING', 'inspecting %s' % repo.head()), ('COMPLETED', 'inspected %s' % repo.head())]
    finally:
        again.kill()


# ── the worker's own failure (§11) ──

def test_a_world_worker_that_fails_stops_core_with_exit_3(tc, monkeypatch):
    def broken(self):
        raise RuntimeError('a bug in the world loop')
    tc.core.world.stop()
    tc.core.world.join(10)
    monkeypatch.setattr(world_worker.World, 'pass_once', broken)
    loop = runtime.WorldLoop(tc.core.world.world, tc.core.db, on_fail=tc.core._engine_failed)
    loop.start()
    assert tc.core._done.wait(10), 'Core did not stop'
    assert (tc.core.exit_code, loop.state) == (3, 'failed')


# ── W26 the idle signal sees work the worker has not reached ──

@pytest.mark.core(world_poll_s=3600.0)
def test_w26_a_commit_is_pending_work_before_the_worker_notices_it(tc, repo):
    client = tc.client()
    pid, rid = _register(tc, repo, [NO_CORE_API])
    _wait(lambda: client._idle(), what='the first assessment')
    repo.commit('core imports api', {'app/core/x.py': 'import app.api\n'})
    assert tc.http('GET', '/v1/health').json()['world']['pending'] == 1
    assert client._idle() is False
    # the health check woke the worker: with an hour-long poll, only that finds it
    _wait(lambda: _repository(tc, pid, rid)['architecture_state'] == 'DRIFTED', 10,
          'the drift, found without waiting for the poll')
    assert _wait(lambda: client._idle(), 10, 'idle again')


# ── W27 scope: the table, and no model anywhere in the world ──

def test_w27_the_world_imports_no_model_runner_router_or_brain():
    banned = ('llmcall', 'memory', 'rotate', 'quota', 'brain', 'anthropic', 'openai', 'usage')
    files = [os.path.join(ROOT, 'archeus', 'core', 'application', 'world.py')] + [
        os.path.join(ROOT, 'archeus', 'core', 'world', f)
        for f in os.listdir(os.path.join(ROOT, 'archeus', 'core', 'world')) if f.endswith('.py')]
    for path in files:
        tree = ast.parse(open(path, encoding='utf-8').read())
        for n in ast.walk(tree):
            names = ([a.name for a in n.names] if isinstance(n, (ast.Import, ast.ImportFrom))
                     else [])
            mod = getattr(n, 'module', None) or ''
            for name in names + [mod]:
                assert not any(b in name.split('.') for b in banned), (path, name)
    # P7 built the brain (archeus/core/brain): the world still reaches none of it
    assert os.path.isdir(os.path.join(ROOT, 'archeus', 'core', 'brain'))


# ── W28 scopes ──

def test_w28_an_observe_device_reads_the_world_and_changes_nothing(tc, repo):
    code = tc.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    token = request(tc.base_url, 'POST', '/v1/devices/launch/redeem',
                    body={'code': code, 'platform': 'web'}).json()['token']
    pid, _rid = _register(tc, repo)
    for method, path, body in (
            ('POST', '/v1/projects', {'name': 'x', 'root_paths': [repo.path],
                                      'idempotency_key': 'o1'}),
            ('POST', '/v1/projects/%s/constraints' % pid, dict(NO_CORE_API, idempotency_key='o2')),
            ('POST', '/v1/digest/ack', {'up_to_seq': 0})):
        r = request(tc.base_url, method, path, token=token, body=body)
        assert (r.status, r.json()['error']) == (403, 'scope_required'), path
    for path in ('/v1/status', '/v1/digest', '/v1/projects', '/v1/projects/%s' % pid):
        assert request(tc.base_url, 'GET', path, token=token).status == 200, path


# ── W29 refused input over HTTP ──

def test_w29_bad_world_input_is_a_400_and_a_conflict_is_a_409(tc, repo, tmp_path):
    pid, _rid = _register(tc, repo)
    f = tmp_path / 'a-file'
    f.write_text('x')
    for body in ({'name': 'x', 'root_paths': [str(f)], 'idempotency_key': 'b1'},
                 {'name': 'x', 'root_paths': ['relative'], 'idempotency_key': 'b2'}):
        r = tc.http('POST', '/v1/projects', body=body)
        assert (r.status, r.json()['error']) == (400, 'invalid_request'), body
    for spec in ({'from': '/etc/**', 'to': 'b'}, {'from': '../x', 'to': 'b'}, {'from': 'a'}):
        r = tc.http('POST', '/v1/projects/%s/constraints' % pid,
                    body={'statement': 's', 'kind': 'forbid_dependency', 'spec': spec,
                          'idempotency_key': json.dumps(spec)})
        assert (r.status, r.json()['error']) == (400, 'invalid_request'), spec
    r = tc.http('POST', '/v1/projects', body={'name': 'y', 'root_paths': [repo.path],
                                             'idempotency_key': 'dup'})
    assert (r.status, r.json()['error']) == (409, 'conflict')
    assert r.json()['detail']['repositories'][0]['project_id'] == pid
    for path in ('/v1/projects/prj_01M3BYC7XZZS8VNDPW3KKNQDBA', '/v1/status?project=prj_x',
                 '/v1/repositories/rep_01M3BYC7XZZS8VNDPW3KKNQDBA/inspections',
                 '/v1/missions?project=prj_x'):
        assert tc.http('GET', path).status == 404, path
    head = tc.http('GET', '/v1/digest').json()['up_to_seq']
    r = tc.http('POST', '/v1/digest/ack', body={'up_to_seq': head + 5})
    assert (r.status, r.json()['error']) == (400, 'invalid_request')


# ── W30 drift reaches the stream, ids only ──

def test_w30_drift_found_is_an_ids_only_stream_frame(tc, repo):
    client = tc.client()
    pid, rid = _register(tc, repo, [NO_CORE_API])
    _wait(lambda: client._idle(), what='the first assessment')
    head = tc.http('GET', '/v1/events?after=0&limit=1000').json()['events'][-1]['seq']
    s = SSEClient(tc.base_url, tc.token, last_event_id=head)
    try:
        assert s.status == 200
        repo.commit('core imports api', {'app/core/x.py': 'import app.api\n'})
        client._idle()                  # a health check wakes the worker
        drifted = None
        while drifted is None:
            f = s.frames(1, timeout=10)[0]
            if f['event'] == 'architecture.state_changed':
                got = tc.http('GET', '/v1/events?after=%d&limit=1' % (f['id'] - 1)).json()
                if got['events'][0]['payload']['to'] == 'DRIFTED':
                    drifted = f
        assert drifted['data'] == {'subject': {'kind': 'repository', 'id': rid},
                                   'scope': {'workspace': 'ws_global', 'project': pid}}
    finally:
        s.close()
