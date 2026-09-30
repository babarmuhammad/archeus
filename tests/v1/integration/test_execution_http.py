"""P11 over HTTP (p11-design-gate §21): the execution routes, their scopes and
errors, the e-stop and re-arm on the real Core runtime (the `archeus-exec`
thread spawning the fake agent), and the `pause` / `estop` CLI verbs."""

import time

import pytest

from archeus.core import engine, ports, runtime
from archeus.core.domain import ids
from archeus.harnesses.fake import FakeHarness
from archeus.infra import paths
from archeus.node.local import LocalNode
from claude_sessions import proc

SLOW = {'work': [{'emit': {'type': 'working'}}, {'sleep': 30}]}


def _post(tc, path, body=None, token=None):
    body = dict(body or {})
    body.setdefault('idempotency_key', ids.new_ulid())
    return tc.http('POST', path, body=body, **({'token': token} if token else {}))


def _wait(fn, what, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = fn()
        if got:
            return got
        time.sleep(0.1)
    raise AssertionError('timed out: %s' % what)


@pytest.fixture
def core(archeus_home):
    from v1.judge.http import TempCore
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), scenarios=dict(SLOW),
        executors=[FakeHarness()])).start()
    yield tc
    for p in list(tc.core.manager._procs.values()):
        proc.kill_pid_tree(p['handle'].pid, p['handle'].create_time)
    tc.stop()
    LocalNode.clear_estop()


def _running(tc):
    mid = _post(tc, '/v1/missions', {'title': 'Run', 'objective': 'o'}).json()['id']

    def started():
        evs = tc.client().events(0)
        got = [e for e in evs if e['type'] == 'execution.started']
        return got and got[0]['subject']['id']
    eid = _wait(started, 'a running execution')
    return mid, eid


def _observe_token(tc):
    code = tc.http('POST', '/v1/devices/launch/code', body={}).json()['code']
    return tc.http('POST', '/v1/devices/launch/redeem',
                   body={'code': code, 'platform': 'web'}).json()['token']


def test_X01_an_execution_and_its_tasks_attempts_are_readable(core):
    mid, eid = _running(core)
    e = core.http('GET', '/v1/executions/%s' % eid).json()
    assert (e['id'], e['process_seq'], e['state']) == (eid, 1, e['state'])
    assert 'hook_token_hash' not in e
    got = core.http('GET', '/v1/tasks/%s/executions' % e['task_id']).json()['executions']
    assert [x['id'] for x in got] == [eid]
    assert core.http('GET', '/v1/executions/%s' % ids.new_id('execution')).status == 404
    assert core.http('GET', '/v1/tasks/%s/executions' % ids.new_id('task')).status == 404


def test_X02_stopping_an_execution_kills_it_and_the_mission_waits(core):
    mid, eid = _running(core)
    r = _post(core, '/v1/executions/%s/stop' % eid)
    assert r.status == 200 and r.json()['state'] == 'STOPPING'
    _wait(lambda: core.http('GET', '/v1/executions/%s' % eid).json()['state'] ==
          'ENDED_KILLED', 'the stop')
    assert core.http('GET', '/v1/missions/%s' % mid).json()['state'] == 'BLOCKED'
    again = _post(core, '/v1/executions/%s/stop' % eid)
    assert again.status == 422                      # a second stop changes nothing


def test_X03_a_mission_stop_stops_its_executions(core):
    mid, eid = _running(core)
    r = _post(core, '/v1/missions/%s/stop' % mid)
    assert r.status == 200 and r.json()['stopped'] == [eid]
    _wait(lambda: core.http('GET', '/v1/executions/%s' % eid).json()['state'] ==
          'ENDED_KILLED', 'the stop')


def test_X04_the_estop_disarms_core_until_a_rearm(core):
    mid, eid = _running(core)
    r = _post(core, '/v1/estop')
    assert r.status == 200 and r.json() == {'stopped': [eid], 'armed': False}
    assert core.http('GET', '/v1/health').json()['armed'] is False
    _wait(lambda: core.http('GET', '/v1/executions/%s' % eid).json()['state'] ==
          'ENDED_KILLED', 'the kill')
    r = _post(core, '/v1/rearm')
    assert r.status == 200 and r.json() == {'armed': True}
    assert core.http('GET', '/v1/health').json()['armed'] is True


def test_X05_stopping_needs_control_and_a_token_and_a_key(core):
    mid, eid = _running(core)
    obs = _observe_token(core)
    for path in ('/v1/executions/%s/stop' % eid, '/v1/missions/%s/stop' % mid, '/v1/estop',
                 '/v1/rearm'):
        assert _post(core, path, token=obs).status == 403, path
        assert core.http('POST', path, body={}).status == 400, path
    assert core.http('GET', '/v1/health').json()['armed'] is True


def test_X06_the_cli_pauses_a_mission_and_engages_the_estop(core, capsys):
    from archeus.cli import main as cli
    mid, eid = _running(core)
    capsys.readouterr()
    assert cli.main(['pause', mid]) == 0
    assert 'PAUSED' in capsys.readouterr().out
    assert cli.main(['estop']) == 0
    assert 'disarmed' in capsys.readouterr().out
    health = core.http('GET', '/v1/health').json()
    assert health['armed'] is False
    import os
    assert os.path.exists(paths.stop_sentinel())
    assert cli.main(['pause', 'all', '--later']) == 2              # usage


def test_X07_the_estop_without_core_is_p20s(archeus_home, capsys):
    from archeus.cli import main as cli
    assert cli.main(['estop']) == 2
    assert 'P20' in capsys.readouterr().err
