"""B10's cards in the TUI's conversation (P19 B10, C-33, G2, G5): the
emergency-stop card runs the strip's own command, the stop card posts the
confirming turn naming its own message, and the route explanation card shows
the RouteDecision's own words."""

from archeus.cli._api import endpoints

from .test_acceptance import _StubApp

MID, RD = 'msn_1', 'rtd_1'


def _app(mission_state='EXECUTING', armed=True):
    msgs = {'messages': [
        {'id': 'msg_1', 'author': 'archeus', 'text': 'Confirm it on the card.',
         'created_at': '2026-10-03T12:00:00Z',
         'cards': [{'type': 'estop', 'ref': {'kind': 'workspace', 'id': 'wsp_global'}}],
         'links': []},
        {'id': 'msg_2', 'author': 'archeus', 'text': 'Confirm it on the card.',
         'created_at': '2026-10-03T12:00:01Z',
         'cards': [{'type': 'stop', 'ref': {'kind': 'mission', 'id': MID}}],
         'links': [{'ref': {'kind': 'mission', 'id': MID}}]},
        {'id': 'msg_3', 'author': 'archeus', 'text': 'Chosen: account A.',
         'created_at': '2026-10-03T12:00:02Z',
         'cards': [{'type': 'route_explanation', 'ref': {'kind': 'route_decision', 'id': RD}}],
         'links': []}]}
    app = _StubApp({
        endpoints.get_mission(MID): {'id': MID, 'title': 'Ship', 'state': mission_state,
                                     'objective': 'o', 'version': 2},
        endpoints.get_mission_plan(MID): {'versions': [], 'plan': {'tasks': []}},
        endpoints.list_messages(MID): msgs,
        endpoints.status(): {'armed': armed},
        endpoints.get_route_decision(RD): {'id': RD, 'explanation': 'Chosen: account A, the '
                                                                    'only one eligible.'},
        endpoints.attention_items(): {'items': [], 'count': 0}, endpoints.digest(): {'groups': []},
        endpoints.sync(): {'client': {'scopes': ['observe', 'control', 'approve'],
                                      'capabilities': {'step_up': 'local'}}}})
    app.open('mission', MID, 'now')
    app.frame()
    return app


def _acts(app):
    return {a['label']: a for x in app._doc.lines for a in x['acts']
            if a['label'] in ('Emergency stop', 'Stop mission')}


def test_the_estop_card_runs_the_strips_command_and_says_when_it_is_engaged():
    app = _app()
    acts = _acts(app)
    assert acts['Emergency stop']['scope'] == 'control'
    sent = []
    app.core.post = lambda path, body: sent.append((path, body)) or {}
    acts['Emergency stop']['run']('k1', {})
    assert sent == [(endpoints.estop(), {'idempotency_key': 'k1'})]
    engaged = _app(armed=False)
    assert 'Emergency stop' not in _acts(engaged)
    assert 'The emergency stop is engaged.' in '\n'.join(engaged.frame())


def test_the_stop_card_posts_the_confirming_turn_naming_its_own_message():
    app = _app()
    act = _acts(app)['Stop mission']
    assert act['disabled'] is None and act['scope'] == 'control'
    sent = []
    app.core.post = lambda path, body: sent.append((path, body)) or {}
    act['run']('k2', {})
    assert sent == [(endpoints.post_message(MID), {
        'text': 'stop', 'confirm': {'message_id': 'msg_2'}, 'idempotency_key': 'k2'})]
    assert 'cancelled' in _acts(_app('CANCELLED'))['Stop mission']['disabled']


def test_the_route_explanation_card_is_the_records_own_words():
    assert 'Chosen: account A, the only one eligible.' in '\n'.join(_app().frame())
