"""The remaining grammar verbs and the explanation card over a real Core (P19
B10, ADR-0042 §1, C-33; testing-strategy §8 G2's conversational half, G5).
`emergency stop` only asks: its card runs the strip's own command. `stop` on a
running mission answers with one card that, confirmed, pauses then cancels it
in the confirming turn's transaction. `why` attaches a `route_explanation`
card naming the RouteDecision its words are."""

import time

import pytest

from archeus.core import engine, ports, runtime
from archeus.core.application import grammar
from archeus.core.domain import entities, ids
from archeus.harnesses.fake import FakeHarness
from archeus.infra.db import rows
from archeus.node.local import LocalNode
from claude_sessions import proc
from v1.judge.http import TempCore

SLOW = {'work': [{'emit': {'type': 'working'}}, {'sleep': 30}]}


@pytest.fixture
def core(archeus_home):
    tc = TempCore(archeus_home, ports=runtime.Ports(
        brain=ports.FixedPlanBrain(engine.SKELETON_PLAN), scenarios=dict(SLOW),
        executors=[FakeHarness()])).start()
    yield tc
    for p in list(tc.core.manager._procs.values()):
        proc.kill_pid_tree(p['handle'].pid, p['handle'].create_time)
    tc.stop(kill=True)
    LocalNode.clear_estop()


def _key():
    return ids.new_ulid()


def _wait(fn, what, timeout=30):
    deadline = time.monotonic() + timeout
    while True:
        got = fn()
        if got:
            return got
        assert time.monotonic() < deadline, 'timed out: %s' % what
        time.sleep(0.05)


def _messages(tc, conversation='primary'):
    return tc.http('GET', '/v1/conversations/%s/messages' % conversation).json()['messages']


def _say(tc, text, conversation='primary'):
    """Post a turn and return Archeus's reply to it."""
    r = tc.http('POST', '/v1/conversations/%s/messages' % conversation,
                body={'text': text, 'idempotency_key': _key()})
    assert r.status == 200, r.body
    mid = r.json()['message_id']
    return _wait(lambda: next((m for m in _messages(tc, conversation)
                               if m.get('in_reply_to') == mid), None), 'a reply to %r' % text)


def _state(tc, mid):
    return tc.http('GET', '/v1/missions/' + mid).json()['state']


def _executing(tc, title):
    mid = tc.http('POST', '/v1/missions', body={'title': title, 'objective': 'o',
                                                'idempotency_key': _key()}).json()['id']
    _wait(lambda: _state(tc, mid) == 'EXECUTING', '%s executing' % title)
    return mid


def _confirm(tc, card_message, conversation='primary', key=None, text='stop'):
    return tc.http('POST', '/v1/conversations/%s/messages' % conversation, body={
        'text': text, 'confirm': {'message_id': card_message},
        'idempotency_key': key or _key()})


def _armed(tc):
    return tc.http('GET', '/v1/status').json()['armed']


def test_the_grammar_reads_emergency_stop_and_stop_by_the_missions_state(core):
    mid = _executing(core, 'Running one')
    with core.core.db.read() as conn:
        assert grammar.resolve(conn, 'emergency stop') == grammar.Control('estop', None, '')
        assert grammar.resolve(conn, 'Emergency  STOP!') == grammar.Control('estop', None, '')
        assert grammar.resolve(conn, 'emergency stop everything') is None     # the brain's
        assert grammar.resolve(conn, 'stop Running one') == grammar.Control(
            'stop_running', {'kind': 'mission', 'id': mid}, 'Running one')
        assert grammar.resolve(conn, 'stop', mission=mid).verb == 'stop_running'
        assert grammar.resolve(conn, 'cancel Running one').verb == 'cancel'     # unchanged


def test_emergency_stop_asks_and_its_card_is_the_strips_command(core):
    reply = _say(core, 'emergency stop')
    assert [c['type'] for c in reply['cards']] == ['estop']
    assert 'Confirm it on the card' in reply['text']
    time.sleep(0.5)
    assert _armed(core) is True                    # the words engaged nothing
    # the card's button is the strip's command, the same route and scope
    r = core.http('POST', '/v1/estop', body={'idempotency_key': _key()})
    assert r.status == 200 and _armed(core) is False


def test_stop_on_a_running_mission_asks_then_pauses_and_cancels_it_in_one_turn(core):
    mid = _executing(core, 'Stop me')
    reply = _say(core, 'stop Stop me')
    assert [(c['type'], c['ref']) for c in reply['cards']] == [
        ('stop', {'kind': 'mission', 'id': mid})]
    time.sleep(0.5)
    assert _state(core, mid) == 'EXECUTING'        # the words stopped nothing
    key = _key()
    r = _confirm(core, reply['id'], key=key)
    assert r.status == 200, r.body
    assert _state(core, mid) == 'CANCELLED'
    events = core.http('GET', '/v1/missions/%s/timeline' % mid).json()
    moves = {(e['payload'].get('from'), e['payload'].get('to')) for e in events['events']
             if e['type'] == 'mission.state_changed'}
    assert {('EXECUTING', 'PAUSED'), ('PAUSED', 'CANCELLED')} <= moves
    assert _confirm(core, reply['id'], key=key).json() == r.json()        # a replay
    before = len(_messages(core))
    again = _confirm(core, reply['id'])
    assert again.status == 422, again.body       # cancelled: nothing more to stop
    assert len(_messages(core)) == before          # and the refused turn wrote nothing


def test_a_confirmation_must_name_a_stop_card_and_say_stop(core):
    mid = _executing(core, 'Keep me')
    status = _say(core, 'status')
    before = len(_messages(core))
    assert _confirm(core, status['id']).status == 400          # no stop card there
    stop = _say(core, 'stop Keep me')
    assert _confirm(core, stop['id'], text='approve').status == 400
    assert len(_messages(core)) == before + 2                   # only the `stop` turn and reply
    assert _state(core, mid) == 'EXECUTING'


def test_stop_on_a_mission_that_is_not_running_cancels_it_as_before(core):
    # under `careful` a mission waits in CREATED for its start (B6)
    assert core.http('POST', '/v1/policies/profile', body={
        'scope': 'user', 'profile': 'careful', 'idempotency_key': _key()}).status == 200
    mid = core.http('POST', '/v1/missions', body={'title': 'Idle', 'objective': 'o',
                                                  'idempotency_key': _key()}).json()['id']
    time.sleep(0.5)
    assert _state(core, mid) == 'CREATED'
    reply = _say(core, 'stop Idle')
    assert [c['type'] for c in reply['cards']] == ['mission']
    assert _state(core, mid) == 'CANCELLED'


def test_why_attaches_the_route_explanation_card_equal_to_the_record(core):
    mid = _executing(core, 'Explain me')
    def execution():
        with core.core.db.read() as conn:
            return [r.entity.to_dict() for r in rows.where(conn, entities.Execution,
                                                            mission_id=mid)
                    if r.entity.route_decision_id]
    (e,) = _wait(execution, 'its execution')
    rd = core.http('GET', '/v1/route-decisions/' + e['route_decision_id']).json()
    reply = _say(core, 'why %s' % rd['id'])
    assert [(c['type'], c['ref']) for c in reply['cards']] == [
        ('route_explanation', {'kind': 'route_decision', 'id': rd['id']})]
    assert reply['text'] == rd['explanation']               # the words are the record's
    reply = _say(core, 'why %s' % e['id'])                   # an execution: its own decision
    assert [c['ref']['id'] for c in reply['cards'] if c['type'] == 'route_explanation'] == [
        rd['id']]
    assert rd['explanation'] in reply['text']
