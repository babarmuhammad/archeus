"""G1 over a real Core (P19 S3; p19-design-gate B5; testing-strategy §8): a
chat `approve` is the card's decision. A new approval is said in the primary
conversation as a card linked to its mission (so its thread shows it too); a
turn sent with that card's hash and version is decided by the poster's
principal in the same transaction, with the same scope, hash, step-up and
idempotency as `/decide`; a refusal writes nothing; a bare "approve" decides
nothing and points at the card."""

import time

import pytest

from archeus.core import engine, ports, runtime
from v1.judge.http import TempCore

DEPLOY = dict(engine.SKELETON_PLAN, tasks=[dict(engine.SKELETON_PLAN['tasks'][0],
                                                action_classes=['deploy'])])


@pytest.fixture
def core(archeus_home):
    tc = TempCore(archeus_home, ports=runtime.Ports(brain=ports.FixedPlanBrain(DEPLOY))).start()
    yield tc
    tc.stop(kill=True)


def _key():
    return 'k-%f' % time.monotonic()


def _asking(tc, title):
    mid = tc.http('POST', '/v1/missions', body={'title': title, 'objective': 'o',
                                                'idempotency_key': _key()}).json()['id']
    deadline = time.monotonic() + 30
    while tc.http('GET', '/v1/missions/' + mid).json()['state'] != 'APPROVAL_REQUIRED':
        assert time.monotonic() < deadline, 'the mission never asked'
        time.sleep(0.05)
    (a,) = tc.http('GET', '/v1/approvals?mission=' + mid).json()['approvals']
    return mid, a


def _messages(tc, conversation):
    return tc.http('GET', '/v1/conversations/%s/messages' % conversation).json()['messages']


def _decision(a, **over):
    return dict({'approval_id': a['id'], 'action_hash': a['action_hash'],
                 'expected_version': a['version']}, **over)


def test_an_approval_is_a_card_in_the_conversation_and_in_its_missions_thread(core):
    mid, a = _asking(core, 'Card me')
    cards = [m for m in _messages(core, 'primary')
             if any(c['type'] == 'approval' and c['ref']['id'] == a['id'] for c in m['cards'])]
    assert len(cards) == 1 and cards[0]['author'] == 'archeus'
    assert {'kind': 'mission', 'id': mid} in [l['ref'] for l in cards[0]['links']]
    assert cards[0]['id'] in [m['id'] for m in _messages(core, mid)]


def test_a_chat_approve_is_the_cards_decision_by_the_poster(core):
    mid, a = _asking(core, 'Approve me in chat')
    key = _key()
    r = core.http('POST', '/v1/conversations/%s/messages' % mid,
                  body={'text': 'approve', 'decision': _decision(a), 'idempotency_key': key})
    assert r.status == 200, r.body
    out = r.json()
    got = core.http('GET', '/v1/approvals/' + a['id']).json()
    assert got['state'] in ('APPROVED', 'CONSUMED')
    me = core.http('GET', '/v1/sync').json()['client']['principal_id']
    assert got['decided_by'] == me                                  # the poster, not Core
    thread = _messages(core, mid)
    turn = [m for m in thread if m['id'] == out['message_id']]
    reply = [m for m in thread if m.get('in_reply_to') == out['message_id']]
    assert turn and turn[0]['author'] == 'user' and turn[0]['text'] == 'approve'
    assert reply and reply[0]['author'] == 'archeus' and 'Approved' in reply[0]['text']
    intent = core.http('GET', '/v1/intents/%s' % reply[0]['intent_id']).json()
    assert (intent['via'], intent['kind']) == ('grammar', 'control_verb')
    # the same request again is the same answer, deciding nothing twice
    again = core.http('POST', '/v1/conversations/%s/messages' % mid,
                      body={'text': 'approve', 'decision': _decision(a), 'idempotency_key': key})
    assert again.status == 200 and again.json()['message_id'] == out['message_id']
    assert len([m for m in _messages(core, mid) if m['text'] == 'approve']) == 1
    # and the mission goes on exactly as after the card's button
    deadline = time.monotonic() + 30
    while core.http('GET', '/v1/missions/' + mid).json()['state'] == 'APPROVAL_REQUIRED':
        assert time.monotonic() < deadline, 'the approved mission never moved'
        time.sleep(0.05)
    # read once, in the turn's own transaction: the intent worker adds no second reply
    assert len([m for m in _messages(core, mid) if m.get('in_reply_to') == out['message_id']]) == 1


def test_a_wrong_hash_a_missing_scope_or_another_word_writes_nothing(core):
    mid, a = _asking(core, 'Refuse me')
    before = len(_messages(core, mid))
    bad = core.http('POST', '/v1/conversations/%s/messages' % mid, body={
        'text': 'approve', 'decision': _decision(a, action_hash='0' * 64),
        'idempotency_key': _key()})
    assert bad.status >= 400, bad.body
    word = core.http('POST', '/v1/conversations/%s/messages' % mid, body={
        'text': 'pause', 'decision': _decision(a), 'idempotency_key': _key()})
    assert word.status == 400, word.body
    observe = core.http('POST', '/v1/devices/launch/code', body={'scopes': ['observe', 'control']})
    assert observe.status == 200, observe.body
    red = core.http('POST', '/v1/devices/launch/redeem', token=None,
                    body={'code': observe.json()['code'], 'platform': 'web'})
    token = red.json()['token']
    no = core.http('POST', '/v1/conversations/%s/messages' % mid, token=token, body={
        'text': 'approve', 'decision': _decision(a), 'idempotency_key': _key()})
    assert (no.status, no.json()['error'], no.json()['detail']['scope']) == (
        403, 'scope_required', 'approve')
    assert len(_messages(core, mid)) == before                     # nothing was written
    assert core.http('GET', '/v1/approvals/' + a['id']).json()['state'] == 'PENDING'


def test_a_bare_approve_decides_nothing_and_points_at_the_card(core):
    mid, a = _asking(core, 'Point me')
    r = core.http('POST', '/v1/conversations/%s/messages' % mid,
                  body={'text': 'approve', 'idempotency_key': _key()})
    sent = r.json()['message_id']
    deadline = time.monotonic() + 30
    while True:
        reply = [m for m in _messages(core, mid) if m.get('in_reply_to') == sent]
        if reply:
            break
        assert time.monotonic() < deadline, 'no reply'
        time.sleep(0.05)
    assert [c['ref'] for c in reply[0]['cards']] == [{'kind': 'approval', 'id': a['id']}]
    assert core.http('GET', '/v1/approvals/' + a['id']).json()['state'] == 'PENDING'
