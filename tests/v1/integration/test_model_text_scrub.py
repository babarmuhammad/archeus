import pytest

from archeus.core.application import attention, queries
from archeus.core.domain import entities, ids
from archeus.core.homes import Homes
from v1.integration.test_ui_seams import _mission, _tx

HOME = 'C:/Scrub/Work-Claude'


@pytest.fixture
def homes():
    return Homes([HOME], [], shorts=lambda _: None, path_flavour='windows')


def _blocked(db, actor):
    mid = _mission(db, actor)
    _tx(db, lambda tx: tx.update(entities.Mission, mid, {'planning_blocked': {
        'kind': 'clarification', 'questions': ['Is %s the target?' % HOME]}}, actor=actor))
    return mid


def _message(db, actor, author, text):
    cid, mid = ids.new_id('conversation'), ids.new_id('message')
    _tx(db, lambda tx: (tx.insert(entities.Conversation(id=cid, kind='primary'), actor=actor),
                        tx.insert(entities.Message(id=mid, conversation_id=cid, author=author,
                                                   text=text), actor=actor)))
    return cid


def test_attention_scrubs_a_planning_question(db, actor, homes):
    _blocked(db, actor)
    with db.read() as conn:
        item = next(i for i in attention.attention(conn, homes=homes)['items'] if i['kind'] == 'mission')
    assert item['reason'] == 'Is its home the target?'


def test_mission_view_and_list_scrub_planning_blocked(db, actor, homes):
    mid = _blocked(db, actor)
    with db.read() as conn:
        one = queries.get_mission(conn, mid, homes=homes)
        many = queries.list_missions(conn, homes=homes)
        stored = conn.execute('SELECT body FROM missions WHERE id = ?', (mid,)).fetchone()[0]
    assert one['planning_blocked']['questions'] == ['Is its home the target?']
    assert many[0]['planning_blocked']['questions'] == ['Is its home the target?']
    assert HOME in stored


def test_messages_scrub_archeus_text_and_keep_the_user_raw(db, actor, homes):
    cid = _message(db, actor, 'archeus', 'Check ' + HOME)
    with db.read() as conn:
        assert queries.messages(conn, cid, homes=homes)[0]['text'] == 'Check its home'
    user = _message(db, actor, 'user', 'Check ' + HOME)
    with db.read() as conn:
        assert queries.messages(conn, user, homes=homes)[0]['text'] == 'Check ' + HOME


def test_intent_scrubs_the_model_reading_and_keeps_the_utterance(db, actor, homes):
    cid = _message(db, actor, 'user', 'x')
    with db.read() as conn:
        message = queries.messages(conn, cid, homes=homes)[0]['id']
    iid = ids.new_id('intent')
    _tx(db, lambda tx: tx.insert(entities.Intent(
        id=iid, message_id=message, utterance='use ' + HOME, kind='question',
        reason='asked about ' + HOME, proposal={'summary': 'in ' + HOME}), actor=actor))
    with db.read() as conn:
        out = queries.get_intent(conn, iid, homes=homes)
    assert out['reason'] == 'asked about its home'
    assert out['proposal'] == {'summary': 'in its home'}
    assert out['utterance'] == 'use ' + HOME
