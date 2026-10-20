"""P12 over HTTP (p12-design-gate §19): the session and checkpoint routes, their
scopes and errors on the real Core runtime, and the `sessions` / `resume` /
`handoff` CLI verbs. The Core offers two fake session harnesses and records
terminals instead of opening them."""

import json
import os

import pytest

from archeus.core import engine, ports, runtime
from archeus.core.domain import ids
from archeus.harnesses.fake import FakeHarness
from archeus.harnesses.sessions import FakeSessions

from v1.integration.test_execution_http import _observe_token, _post, _wait
from v1.judge.support import JudgeTerminal, session_adapters


@pytest.fixture
def core(archeus_home):
    from v1.judge.http import TempCore
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), executors=[FakeHarness()],
        sessions=session_adapters(), terminal=JudgeTerminal(archeus_home))).start()
    yield tc
    tc.stop()


def _register(tc, cwd, harness='fake_a', turns=(('user', 'hello'),)):
    ref = 'ref-' + ids.new_ulid()
    FakeSessions(harness).write(ref, list(turns))
    r = _post(tc, '/v1/sessions', {'harness_id': harness, 'cwd': str(cwd),
                                   'provider_session_ref': ref, 'model': 'fake-model'})
    assert r.status == 200, r.body
    return r.json()


def test_H01_register_read_list_resume_handoff_and_close(core, tmp_path):
    s = _register(core, tmp_path)
    assert core.http('GET', '/v1/sessions/%s' % s['id']).json()['state'] == 'OPEN'
    assert [x['id'] for x in core.http('GET', '/v1/sessions').json()['sessions']] == [s['id']]
    brief = core.http('GET', '/v1/sessions/%s/brief' % s['id']).json()
    assert brief['session']['id'] == s['id'] and 'changes' in brief
    r = _post(core, '/v1/sessions/%s/resume' % s['id'], {'request_id': 'r1'})
    assert r.status == 200 and r.json()['launch']['launched'], r.body
    r = _post(core, '/v1/sessions/%s/handoff' % s['id'], {'request_id': 'h1',
                                                           'harness_id': 'fake_b'})
    assert r.status == 200 and r.json()['handoff_from_session_id'] == s['id'], r.body
    r = _post(core, '/v1/sessions/%s/close' % s['id'])
    assert r.status == 200 and r.json()['state'] == 'CLOSED'
    assert len(JudgeTerminal(core.home).launches()) == 2


def test_H02_changing_a_session_needs_control_a_token_and_a_key(core, tmp_path):
    s = _register(core, tmp_path)
    obs = _observe_token(core)
    for path, body in (('/v1/sessions', {'harness_id': 'fake_a', 'cwd': str(tmp_path)}),
                       ('/v1/sessions/%s/resume' % s['id'], {'request_id': 'r'}),
                       ('/v1/sessions/%s/handoff' % s['id'], {'request_id': 'h',
                                                              'harness_id': 'fake_b'}),
                       ('/v1/sessions/%s/link' % s['id'], {}),
                       ('/v1/sessions/%s/close' % s['id'], {})):
        assert _post(core, path, body, token=obs).status == 403, path
        assert core.http('POST', path, body=body).status == 400, path      # no key
    assert core.http('GET', '/v1/sessions/%s' % s['id'], token=obs).status == 200


def test_H03_a_forged_or_unknown_session_is_404_and_a_refusal_is_409(core, tmp_path):
    assert core.http('GET', '/v1/sessions/ses_%s' % ('Z' * 26)).status in (400, 404)
    assert core.http('GET', '/v1/sessions/../etc').status in (400, 404)
    s = _register(core, tmp_path)
    ref = core.http('GET', '/v1/sessions/%s' % s['id']).json()['provider_session_ref']
    os.remove(FakeSessions('fake_a').path(ref))                 # the provider session is gone
    r = _post(core, '/v1/sessions/%s/resume' % s['id'], {'request_id': 'r'})
    assert r.status == 409 and r.json()['error'] == 'conflict'
    r = _post(core, '/v1/sessions/%s/handoff' % s['id'], {'request_id': 'h',
                                                           'harness_id': 'no_such'})
    assert r.status == 409


def test_H04_an_executions_checkpoints_and_its_handoff(core):
    mid = _post(core, '/v1/missions', {'title': 'Run', 'objective': 'o'}).json()['id']

    def ended():
        got = [e for e in core.client().events(0) if e['type'] == 'execution.ended']
        return got and got[0]['subject']['id']
    eid = _wait(ended, 'an ended execution')
    (cp,) = core.http('GET', '/v1/executions/%s/checkpoints' % eid).json()['checkpoints']
    assert (cp['execution_id'], cp['mission_id'], cp['trigger']) == (eid, mid, 'task_boundary')
    r = _post(core, '/v1/executions/%s/handoff' % eid)        # it ended: nothing to hand off
    assert r.status == 422
    assert core.http('GET', '/v1/executions/exe_%s/checkpoints' % ('Z' * 26)).status in (400,
                                                                                         404)


def test_H05_the_cli_lists_resumes_and_hands_off(core, tmp_path, capsys):
    from archeus.cli import main as cli
    s = _register(core, tmp_path)
    capsys.readouterr()
    assert cli.main(['sessions']) == 0
    assert s['id'] in capsys.readouterr().out
    assert cli.main(['resume', s['id'], '--model', 'fake-large']) == 0
    assert 'resumed on fake_a (fake-large)' in capsys.readouterr().out
    assert cli.main(['handoff', s['id'], '--to', 'fake_b']) == 0
    assert '-> ses_' in capsys.readouterr().out
    assert cli.main(['handoff', s['id']]) == 2                         # usage
    assert json.loads(json.dumps(JudgeTerminal(core.home).launches()))[-1]['argv'][0] == \
        'fake-session'


def test_H06_the_session_verbs_without_core_say_so(archeus_home, capsys):
    from archeus.cli import main as cli
    assert cli.main(['sessions']) == 1
    assert 'not running' in capsys.readouterr().err
