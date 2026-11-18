"""An approval card in the TUI's conversation (P19 S3; p19-design-gate B5): its
Approve and Reject post the turn to the thread with the card's hash and
version, so Core decides it as Attention does (G1); a client whose step-up is
a PIN is sent to Attention instead."""

from archeus.cli._api import endpoints

from .test_acceptance import _StubApp

MID, AID = 'msn_1', 'apr_1'


def _app(step_up=False, capability='local'):
    msgs = {'messages': [
        {'id': 'msg_1', 'author': 'archeus', 'text': '"Ship" needs your approval: deploy.',
         'created_at': '2026-10-03T12:00:00Z',
         'cards': [{'type': 'approval', 'ref': {'kind': 'approval', 'id': AID}}],
         'links': [{'ref': {'kind': 'mission', 'id': MID}}]}]}
    app = _StubApp({
        endpoints.get_mission(MID): {'id': MID, 'title': 'Ship', 'state': 'APPROVAL_REQUIRED',
                                     'objective': 'o', 'version': 2},
        endpoints.get_mission_plan(MID): {'versions': [], 'plan': {'tasks': []}},
        endpoints.list_messages(MID): msgs,
        endpoints.get_approval(AID): {'id': AID, 'kind': 'plan', 'state': 'PENDING',
                                      'eligible': True, 'step_up': step_up, 'version': 3,
                                      'action_hash': 'h' * 64, 'presented': {'scope': 'deploy'}},
        endpoints.attention_items(): {'items': [], 'count': 0}, endpoints.digest(): {'groups': []},
        endpoints.sync(): {'client': {'scopes': ['observe', 'control', 'approve'],
                                      'capabilities': {'step_up': capability}}}})
    app.open('mission', MID, 'now')
    app.frame()
    return app


def _acts(app):
    return {a['label']: a for x in app._doc.lines for a in x['acts']
            if a['label'] in ('Approve', 'Reject')}


def test_approve_posts_the_turn_with_the_cards_hash_and_version_to_the_thread():
    app = _app()
    acts = _acts(app)
    assert acts['Approve']['disabled'] is None and acts['Approve']['scope'] == 'approve'
    sent = []
    app.core.post = lambda path, body: sent.append((path, body)) or {}
    acts['Approve']['run']('k1', {})
    acts['Reject']['run']('k2', {})
    decision = {'approval_id': AID, 'action_hash': 'h' * 64, 'expected_version': 3}
    assert sent == [
        (endpoints.post_message(MID), {'text': 'approve', 'decision': decision,
                                       'idempotency_key': 'k1'}),
        (endpoints.post_message(MID), {'text': 'reject', 'decision': decision,
                                       'idempotency_key': 'k2'})]


def test_a_pin_step_up_is_given_in_attention_not_here():
    acts = _acts(_app(step_up=True, capability='pin'))
    assert 'Attention' in acts['Approve']['disabled'] and acts['Reject']['disabled']
    assert _acts(_app(step_up=True, capability='local'))['Approve']['disabled'] is None
