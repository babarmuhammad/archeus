"""P19 S1 over a real database (p19-design-gate B3, §12): a mission's own
conversation. A mission's id names its thread; the one writer makes it on first
use, so there is one per mission; a turn there is the mission's (a bare mission
verb is about it) and its reply stays there; the thread also shows every
primary message whose links name the mission, read, never copied."""

import pytest

from archeus.core.application import commands, queries
from archeus.core.application.conversation import post_message
from archeus.core.domain import entities, ids
from archeus.infra.db.writer import NotFound
from v1.integration.test_intent import make  # noqa: F401 (a fixture)


def _mission(r, title='Thread me'):
    return r.run(commands.create_mission, title=title, objective='o')['id']


def test_a_missions_id_names_its_one_thread_made_on_first_use(make):  # noqa: F811
    r = make([])
    mid = _mission(r)
    assert not r.all(entities.Conversation, mission_id=mid)
    assert r.read(queries.messages, mid) == []                # nothing yet: an empty thread
    a = r.run(post_message, text='first', conversation_id=mid)
    b = r.run(post_message, text='second', conversation_id=mid)
    (c,) = r.all(entities.Conversation, mission_id=mid)
    assert (c.kind, a['conversation_id'], b['conversation_id']) == ('mission', c.id, c.id)
    assert [m['text'] for m in r.read(queries.messages, mid)] == ['first', 'second']
    assert [m['text'] for m in r.read(queries.messages, 'primary')] == []


def test_an_unknown_mission_has_no_thread(make):  # noqa: F811
    r = make([])
    nobody = ids.new_id('mission')
    with pytest.raises(NotFound):
        r.read(queries.messages, nobody)
    with pytest.raises(Exception):
        r.run(post_message, text='hello', conversation_id=nobody)
    assert not r.all(entities.Conversation, kind='mission')


def test_a_bare_mission_verb_in_a_thread_is_about_its_mission_and_answered_there(make):  # noqa: F811
    r = make([])
    mid = _mission(r)
    other = _mission(r, 'Another one')
    posted = r.run(post_message, text='stop', conversation_id=mid)
    r.settle()
    reply = r.read(queries.reply_to, posted['message_id'])
    assert reply['conversation_id'] == posted['conversation_id']          # stays in the thread
    (it,) = r.all(entities.Intent, message_id=posted['message_id'])
    assert (it.via, it.kind, [t['id'] for t in it.target_refs]) == ('grammar', 'control_verb', [mid])
    states = {m.id: m.state for m in r.all(entities.Mission)}
    assert states[mid] == 'CANCELLED' and states[other] != 'CANCELLED'
    # the same word in the primary conversation names no mission: not the grammar's
    p = r.run(post_message, text='stop')
    r.settle()
    (it2,) = r.all(entities.Intent, message_id=p['message_id'])
    assert it2.via == 'brain' or it2.resolution == 'declined'


def test_the_thread_shows_the_primary_messages_that_link_its_mission_in_order(make):  # noqa: F811
    r = make([])
    mid = _mission(r)
    other = _mission(r, 'Another one')
    r.run(post_message, text='in the thread', conversation_id=mid)
    said = r.run(post_message, text='reprioritise Thread me to 3')    # primary; reply links it
    r.settle()
    r.run(post_message, text='reprioritise Another one to 2')          # links the other only
    r.settle()
    thread = r.read(queries.messages, mid)
    texts = [m['text'] for m in thread]
    assert texts[0] == 'in the thread'
    replies = [m for m in thread if m.get('in_reply_to') == said['message_id']]
    assert len(replies) == 1 and replies[0]['author'] == 'archeus'
    assert not any('Another one' in t for t in texts)
    assert all(m['conversation_id'] != mid for m in thread)              # real conversation ids
    stamps = [(m['created_at'], m['id']) for m in thread]
    assert stamps == sorted(stamps)
    # not copied: the primary conversation still holds the reply, once
    assert [m['id'] for m in r.read(queries.messages, 'primary')].count(replies[0]['id']) == 1
    assert [m['author'] for m in r.read(queries.messages, other)] == ['archeus']   # its own reply
