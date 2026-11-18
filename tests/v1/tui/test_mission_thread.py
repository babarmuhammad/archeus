"""The mission's Now tab in the TUI (P19 S1; p19-design-gate B3): the mission's
own conversation, read by the mission's id, above what is running for it; its
Message command posts to that thread, never to the primary conversation."""

from archeus.cli._api import endpoints
from claude_sessions import render

from .test_acceptance import _StubApp

MID = 'msn_1'


def _app():
    msgs = {'messages': [
        {'id': 'msg_1', 'author': 'user', 'text': 'pause', 'created_at': '2026-10-03T12:00:00Z',
         'cards': [], 'links': []},
        {'id': 'msg_2', 'author': 'archeus', 'text': 'Paused "Thread me": EXECUTING -> PAUSED.',
         'created_at': '2026-10-03T12:00:01Z', 'cards': [], 'links': []}]}
    app = _StubApp({
        endpoints.get_mission(MID): {'id': MID, 'title': 'Thread me', 'state': 'PAUSED',
                                     'objective': 'o', 'version': 2},
        endpoints.get_mission_plan(MID): {'versions': [], 'plan': {'tasks': []}},
        endpoints.list_messages(MID): msgs,
        endpoints.list_messages('primary'): {'messages': []},
        endpoints.attention_items(): {'items': [], 'count': 0}, endpoints.digest(): {'groups': []},
        endpoints.sync(): {'client': {'scopes': ['observe', 'control']}}})
    app.open('mission', MID, 'now')
    return app


def test_the_now_tab_reads_the_missions_thread_above_its_work():
    app = _app()
    text = [render.strip_ansi(x['text']) for x in (app.frame() and app._doc.lines)]
    head = next(i for i, t in enumerate(text) if "This mission's conversation" in t)
    assert any('Paused "Thread me"' in t for t in text[head:])
    work = next(i for i, t in enumerate(text) if 'Nothing is running' in t)
    assert head < work
    assert endpoints.list_messages(MID) in app.core.gets
    assert endpoints.list_messages('primary') not in app.core.gets


def test_its_message_command_posts_to_the_thread():
    app = _app()
    app.frame()
    (act,) = [a for a in app._doc.acts if a['label'] == 'Message']
    sent = []
    app.core.post = lambda path, body: sent.append((path, body)) or {}
    act['run']('k1', {'text': 'resume'})
    assert sent == [(endpoints.post_message(MID), {'text': 'resume', 'idempotency_key': 'k1'})]
    assert act['reread'] == [endpoints.list_messages(MID)]
