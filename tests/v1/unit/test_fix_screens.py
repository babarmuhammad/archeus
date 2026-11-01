"""T-608: Core text put on a line the TUI paints must be cleaned like every
other Core string, and a cut relationship list says it is cut."""

import pytest

from archeus.cli.tui import screens as SC
from archeus.cli.tui.view import Style
from v1.tui.test_acceptance import _StubCore
from v1.tui.test_security import inert, plain
from archeus.cli.tui import app as A

BAD = '\x1b]0;owned\x07\x1b]52;c;cHduZWQ=\x1b\\\x9d0;owned\x9c'
SYNC = {'client': {'scopes': ['observe', 'control', 'approve', 'admin'], 'origin': 'local',
                   'capabilities': {'step_up': 'local'}}}


class App(A.App):
    def __init__(self, data):
        super().__init__(_StubCore(dict(data, **{'/v1/sync': SYNC})), Style(),
                         size=lambda: (120, 40), stream=False)
        self.signal('stream_open')


def card(type_, kind, id_):
    return {'/v1/conversations/primary/messages': {'messages': [
        {'id': 'm1', 'author': 'archeus', 'text': 'hi', 'cards': [
            {'type': type_, 'ref': {'kind': kind, 'id': id_}}]}]},
        '/v1/missions': {'missions': []}, '/v1/attention': {'items': [], 'count': 0},
        '/v1/ideas': {'ideas': []}}


def shown(app, route):
    app.go(route)
    frame = app.frame()
    assert inert(frame), route
    return plain(app)


def test_an_approval_card_in_the_conversation_is_inert():
    data = card('approval', 'approval', 'apr_1')
    data['/v1/approvals/apr_1'] = {
        'id': 'apr_1', 'kind': 'plan', 'state': 'PENDING', 'eligible': False, 'version': 1,
        'action_hash': 'h' * 64, 'eligible_why': 'why' + BAD,
        'presented': {'scope': 'deploy' + BAD}}
    assert 'deploy' in shown(App(data), {'view': 'now'})


def test_a_stop_card_with_a_hostile_mission_title_is_inert():
    data = card('stop', 'mission', 'msn_1')
    data['/v1/missions/msn_1'] = {'id': 'msn_1', 'title': 'Title' + BAD, 'state': 'EXECUTING',
                                  'version': 1}
    assert 'Title' in shown(App(data), {'view': 'now'})


def test_the_opt_in_line_is_inert_and_a_non_integer_version_does_not_crash():
    data = {'/v1/opt-ins': {'opt_ins': [{'kind': 'hook', 'name': 'n', 'owner': 'own' + BAD,
                                         'owner_id': 'id' + BAD, 'opted_in': True,
                                         'version': '3'}]}}
    assert 'own' in shown(App(data), {'view': 'control', 'section': 'resources'})


def test_the_keys_of_a_generic_row_are_inert():
    data = {'/v1/policy-decisions/pd_1': {'key' + BAD: 'v'}}
    assert 'key' in shown(App(data), {'view': 'object', 'kind': 'policy_decision',
                                      'id': 'pd_1', 'tab': None})


@pytest.mark.parametrize('edges,truncated', [([], True)])
def test_a_truncated_relationship_list_does_not_claim_there_are_none(edges, truncated):
    graph = {'focus': 'mission:msn_1', 'nodes': [], 'edges': edges, 'truncated': truncated,
             'hidden': []}
    path = SC.endpoints.world_graph(focus='mission:msn_1', depth=1, limit=1000)
    data = {path: graph, '/v1/missions/msn_1': {'id': 'msn_1', 'title': 't', 'state': 'EXECUTING',
                                                'version': 1}}
    text = shown(App(data), {'view': 'object', 'kind': 'mission', 'id': 'msn_1',
                             'tab': 'relations'})
    assert 'No recorded relationships' not in text
    assert 'not all' in text
