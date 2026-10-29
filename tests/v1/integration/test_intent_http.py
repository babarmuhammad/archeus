"""P7 over HTTP (p7-design-gate §9, H01–H04): the routes are thin, so this
checks what the HTTP layer adds — the reply arrives as a message after the
POST returns, a retried POST is the same message, the challenge choice and a
clarification's answer, undated notes only on opt-in, and a refused request is
a 400 or 404, never a 500."""

import time

from archeus.core import ports, runtime
from archeus.harnesses.fake import FakeCaller
from v1.judge.http import TempCore

CONFLICT = {'kind': 'new_work', 'title': 'Query SQLite', 'objective': 'the core queries it',
            'conflicts': [{'ref': 'k1', 'why': 'the notes decided otherwise'}]}


def _core(archeus_home, callers=()):
    return TempCore(archeus_home, ports=runtime.Ports(
        callers=list(callers), preference=ports.FixedOwnCallPreference())).start()


def _reply(tc, mid, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = [m for m in tc.http('GET', '/v1/conversations/primary/messages').json()[
            'messages'] if m['in_reply_to'] == mid]
        if got:
            return got[0]
        time.sleep(0.05)
    raise AssertionError('no reply to %s' % mid)


def test_h01_a_posted_message_returns_its_id_and_the_reply_arrives_as_a_message(archeus_home):
    tc = _core(archeus_home, [FakeCaller('fake')])
    try:
        body = {'text': 'status', 'idempotency_key': 'x1'}
        a = tc.http('POST', '/v1/conversations/primary/messages', body=body).json()
        b = tc.http('POST', '/v1/conversations/primary/messages', body=body).json()
        assert a['message_id'] == b['message_id']                   # a retry, not a second turn
        reply = _reply(tc, a['message_id'])
        assert reply['author'] == 'archeus' and reply['cards'][0]['type'] == 'status'
        it = tc.http('GET', '/v1/intents/%s' % reply['intent_id']).json()
        assert (it['kind'], it['via'], it['resolution']) == ('control_verb', 'grammar',
                                                             'answered')
        assert tc.http('POST', '/v1/conversations/primary/messages', body={
            'text': '  ', 'idempotency_key': 'x2'}).status == 400
        assert tc.http('GET', '/v1/conversations/cnv_nope/messages').status in (400, 404)
        assert tc.http('GET', '/v1/intents/int_01M3DGX0000000000000000000').status == 404
        assert tc.http('GET', '/v1/ideas').json() == {'ideas': []}
        assert tc.http('GET', '/v1/health').json()['intent']['state'] in ('idle', 'running')
    finally:
        tc.stop()


def test_h02_undated_notes_need_the_opt_in_and_then_archeus_asks(archeus_home, tmp_path):
    notes = tmp_path / 'review.md'
    notes.write_text('# Review\nDECISION: the core never talks to the database.\n',
                     encoding='utf-8')
    fake = FakeCaller('fake', replies={'knowledge_extraction': [{'parsed': {'decisions': [
        {'statement': 'The core never talks to the database'}]}}],
        'brain': [{'parsed': CONFLICT}]})
    tc = _core(archeus_home, [fake])
    try:
        assert tc.http('POST', '/v1/meetings/import', body={
            'path': str(notes), 'idempotency_key': 'm1'}).status == 400           # N31 holds
        ok = tc.http('POST', '/v1/meetings/import', body={
            'path': str(notes), 'allow_undated': True, 'idempotency_key': 'm2'})
        assert ok.status == 200 and ok.json()['meeting']['held_at'] is None
        msgs = tc.http('GET', '/v1/conversations/primary/messages').json()['messages']
        assert [m['cards'][0]['asks'] for m in msgs] == ['held_at']
        # the question is answered by replying to it
        a = tc.http('POST', '/v1/conversations/primary/messages', body={
            'text': 'held on 2026-09-20', 'in_reply_to': msgs[0]['id'],
            'idempotency_key': 'm3'}).json()
        assert 'held 2026-09-20' in _reply(tc, a['message_id'])['text']
    finally:
        tc.stop()


def test_h03_a_challenge_is_answered_by_its_choice_route(archeus_home, tmp_path):
    notes = tmp_path / 'review-2026-09-20.md'
    notes.write_text('# Review\nDECISION: the core never talks to the database.\n',
                     encoding='utf-8')
    fake = FakeCaller('fake', replies={'knowledge_extraction': [{'parsed': {'decisions': [
        {'statement': 'The core never talks to the database'}]}}],
        'brain': [{'parsed': CONFLICT}]})
    tc = _core(archeus_home, [fake])
    try:
        tc.http('POST', '/v1/meetings/import', body={'path': str(notes),
                                                      'idempotency_key': 'm1'})
        a = tc.http('POST', '/v1/conversations/primary/messages', body={
            'text': 'Have the core query SQLite.', 'idempotency_key': 'c1'}).json()
        reply = _reply(tc, a['message_id'])
        assert reply['cards'][0]['type'] == 'challenge'
        iid = reply['intent_id']
        assert tc.http('POST', '/v1/intents/%s/clarify' % iid, body={
            'idempotency_key': 'c2'}).status == 400                    # neither choice nor text
        assert tc.http('POST', '/v1/intents/%s/clarify' % iid, body={
            'choice': 'maybe', 'idempotency_key': 'c3'}).status == 400
        out = tc.http('POST', '/v1/intents/%s/clarify' % iid, body={
            'choice': 'drop', 'idempotency_key': 'c4'})
        assert out.status == 200 and out.json()['resolution'] == 'declined'
        assert tc.http('GET', '/v1/missions').json()['missions'] == []
        assert tc.http('POST', '/v1/intents/%s/clarify' % iid, body={
            'choice': 'proceed', 'idempotency_key': 'c5'}).status == 400    # already chosen
    finally:
        tc.stop()


def test_h04_a_clarification_is_answered_with_text_through_the_same_route(archeus_home):
    ask = {'kind': 'new_work', 'title': 'Redo it', 'objective': 'redo the dashboard',
           'ambiguities': [{'question': 'Web or TUI?', 'material': True}]}
    fake = FakeCaller('fake', replies={'brain': [
        {'when': 'This message answers', 'parsed': dict(ask, ambiguities=[])},
        {'parsed': ask}]})
    tc = _core(archeus_home, [fake])
    try:
        a = tc.http('POST', '/v1/conversations/primary/messages', body={
            'text': 'Redo the dashboard.', 'idempotency_key': 'd1'}).json()
        reply = _reply(tc, a['message_id'])
        assert reply['cards'][0]['type'] == 'clarification'
        out = tc.http('POST', '/v1/intents/%s/clarify' % reply['intent_id'], body={
            'text': 'The web one.', 'idempotency_key': 'd2'}).json()
        answer = _reply(tc, out['message_id'])
        assert answer['cards'][0]['type'] == 'mission_proposal'
        it = tc.http('GET', '/v1/intents/%s' % answer['intent_id']).json()
        assert it['answers_intent_id'] == reply['intent_id']
    finally:
        tc.stop()
