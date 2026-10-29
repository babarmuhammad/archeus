"""T-144 slice 3: the event and text surfaces (S12-S23) as pure projections."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from archeus.api import sse
from archeus.core.application import public, queries
from archeus.core.domain import events, ids
from archeus.core.domain.events import new_event
from archeus.core.domain.values import Ref
from archeus.core.homes import Homes, public_account_id

HOME = 'C:/T144/Work-Claude'
KEY = 'h:' + HOME.lower()
OLD_KEY = 'h:c:/t144/old-claude'
OLD = 'C:/T144/Old-Claude'


@pytest.fixture
def homes():
    return Homes([HOME], [('h', KEY, HOME), ('h', OLD_KEY, OLD)],
                 shorts=lambda _: None, path_flavour='windows')


def envelope(type_, payload, kind='user_device'):
    return {'seq': 7, 'id': 'ev', 'type': type_, 'at': 'then', 'actor': {'kind': kind, 'id': 'prn_x'},
            'cause_chain': [], 'subject': {'kind': 'mission', 'id': 'mis_x'},
            'scope': {'workspace': 'w', 'project': None}, 'visibility': 'user', 'payload': payload}



SYSTEM_TEXT = [
    ('archeus_call.ended', {'purpose': 'brain', 'outcome': {
        'state': 'failed', 'account_ref': KEY, 'reason': 'stderr ' + HOME + '/x'}, 'usage': {}},
     {'purpose': 'brain', 'outcome': {
         'state': 'failed', 'account_ref': '<PID>', 'reason': 'stderr its home/x'}, 'usage': {}}),
    ('account_health.state_changed', {'from': 'A', 'to': 'B', 'reason': 'no Claude login in ' + HOME},
     {'from': 'A', 'to': 'B', 'reason': 'no Claude login in its home'}),
    ('review.requested', {'reviewer_resource': {'harness': 'h', 'account': KEY}},
     {'reviewer_resource': {'harness': 'h', 'account': '<PID>'}}),
    ('mission.state_changed', {'reason': 'waiting for your approval to run task T1 on ' + KEY},
     {'reason': 'waiting for your approval to run task T1 on <PID>'}),
    ('execution.hook', {'seq': 1, 'decision': 'DENY', 'reason': 'a read of ' + HOME + ' is denied'},
     {'seq': 1, 'decision': 'DENY', 'reason': 'a read of its home is denied'}),
    ('execution.progress', {'offset': 3, 'events': [{'text': 'HOME=' + HOME}], 'last': [HOME]},
     {'offset': 3, 'events': [{'text': 'HOME=its home'}], 'last': ['its home']}),
    ('session.observed', {'transcript_path': HOME + '/projects/a.jsonl', 'error': None},
     {'transcript_path': 'its home/projects/a.jsonl', 'error': None}),
]


@pytest.mark.parametrize('type_,payload,expected', SYSTEM_TEXT, ids=[c[0] for c in SYSTEM_TEXT])
def test_public_event_projects_system_payloads_without_touching_the_input(
        homes, type_, payload, expected):
    env = envelope(type_, payload)
    before = deepcopy(env)
    out = public.public_event(env, homes)
    expected = json.loads(json.dumps(expected).replace('<PID>', public_account_id(KEY)))
    assert out['payload'] == expected
    assert {k: v for k, v in out.items() if k != 'payload'} == {
        k: v for k, v in env.items() if k != 'payload'}
    assert env == before
    out['payload'].clear()
    assert env == before
    assert public.public_event(out, homes) == out


def test_home_path_under_a_path_key_becomes_null_and_other_values_stay():
    h = Homes([HOME], shorts=lambda _: None, path_flavour='windows')
    out = public.public_event(envelope('mission.updated', {
        'resource_preferences': {'account_ref': HOME}, 'other': HOME + '/x'}), h)
    assert out['payload'] == {'resource_preferences': {'account_ref': None}, 'other': 'its home/x'}


@pytest.mark.parametrize('actor', ['user_device', 'system'])
def test_event_exemptions_follow_provenance_not_the_actor(homes, actor):
    authored = public.public_event(envelope('mission.created', {
        'title': HOME, 'origin': 'user', 'unlisted': HOME}, actor), homes)['payload']
    assert authored == {'title': HOME, 'origin': 'user', 'unlisted': 'its home'}
    system = public.public_event(envelope('mission.state_changed', {
        'reason': HOME, 'title': HOME}, actor), homes)['payload']
    assert system == {'reason': 'its home', 'title': 'its home'}


def test_authored_leaves_of_a_system_envelope_are_exact(homes):
    out = public.public_event(envelope('mission.updated', {
        'fields': ['requirements'], 'added': {'requirements': [{'text': HOME + ' ' + KEY}],
                                              'constraints': [HOME], 'notes': HOME},
        'planning_blocked': {'questions': [HOME], 'detail': HOME},
        'message_id': 'msg'}), homes)['payload']
    assert out['added'] == {'requirements': [{'text': HOME + ' ' + KEY}], 'constraints': [HOME],
                            'notes': 'its home'}
    assert out['planning_blocked'] == {'questions': ['its home'], 'detail': 'its home'}


def test_authored_leaves_are_copies(homes):
    env = envelope('mission.created', {'title': ['x']})
    out = public.public_event(env, homes)
    out['payload']['title'].append('y')
    assert env['payload']['title'] == ['x']


def test_unlisted_nested_system_field_gets_the_production_fallback(homes):
    out = public.public_event(envelope('execution.prepared', {
        'workdir': 'D:/w', 'unlisted': {'a': [{'b': ['x ' + HOME, KEY, OLD_KEY + '/y']}]}}), homes)
    assert out['payload']['unlisted'] == {'a': [{'b': [
        'x its home', public_account_id(KEY), public_account_id(OLD_KEY) + '/y']}]}
    assert out['payload']['workdir'] == 'D:/w'


def test_S28_starting_keeps_worktree_workdir_and_branch(homes):
    payload = {'workdir': 'D:/worktrees/mission.t1', 'branch': 'archeus/mission.t1'}
    assert public.public_event(envelope('execution.starting', payload), homes)['payload'] == payload


def test_every_authored_event_type_is_registered():
    assert set(public.EVENT_AUTHORED) <= set(events.REGISTRY)


def test_output_events_are_scrubbed_whole_and_the_read_is_not_mutated(homes):
    out = {'execution_id': 'e', 'offset': 0, 'events': [
        {'type': 'assistant', 'text': 'my home is ' + HOME + '/x', 'lane': 'main'},
        {'type': 'tool', 'name': 'Read', 'id': 't', 'input': {'path': KEY}}], 'available': True}
    before = deepcopy(out)
    got = public.public_output(out, homes)
    assert got['events'][0]['text'] == 'my home is its home/x'
    assert got['events'][1]['input'] == {'path': public_account_id(KEY)}
    assert got['execution_id'] == 'e' and got['available'] is True
    assert out == before


def test_context_package_scrubs_system_text_and_keeps_the_query(homes):
    body = {'query': HOME, 'items': [{'reason': 'seen at ' + HOME, 'text': 'on ' + KEY,
                                      'ref': {'kind': 'event', 'id': 'ev'}}],
            'excluded': [{'reason': OLD_KEY}], 'missing_information': [HOME + '/r no inspection']}
    before = deepcopy(body)
    got = public.public_context(body, homes)
    assert got['query'] == HOME
    assert got['items'][0]['reason'] == 'seen at its home' and got['items'][0]['text'] == 'on ' + public_account_id(KEY)
    assert got['excluded'] == [{'reason': public_account_id(OLD_KEY)}]
    assert got['missing_information'] == ['its home/r no inspection']
    assert body == before


def test_policy_decision_projects_action_and_items_and_keeps_rule_snapshots(homes):
    body = {'reason': 'read ' + HOME, 'action': {
        'class': 'read_file', 'target': HOME + '/x', 'argv': ['cat', HOME], 'paths': [KEY]},
        'items': [{'task': 't', 'reason': HOME, 'action': {'target': HOME}, 'extra': {'n': [HOME]}}],
        'matched_rules': [{'pattern': HOME + '/*'}]}
    before = deepcopy(body)
    got = queries._public_policy_decision(body, homes)
    assert got['reason'] == 'read its home'
    assert got['action'] == {'class': 'read_file', 'target': 'its home/x', 'argv': ['cat', 'its home'],
                             'paths': [public_account_id(KEY)]}
    assert got['items'] == [{'task': 't', 'reason': 'its home', 'action': {'target': 'its home'},
                             'extra': {'n': ['its home']}}]
    assert got['matched_rules'] == body['matched_rules']
    assert body == before


def test_S22_sse_frames_carry_identities_only():
    mid = ids.new_id('mission')
    e = new_event('mission.state_changed', Ref('mission', mid),
                  Ref('system', ids.new_id('principal')), payload={'reason': HOME}, project=None)
    raw = sse.frame(replace(e, seq=9))
    head, data = raw.decode().split('\n')[:3], json.loads(raw.decode().split('data: ')[1])
    assert head[0] == 'id: 9' and head[1] == 'event: mission.state_changed'
    assert data == {'subject': {'kind': 'mission', 'id': mid},
                    'scope': {'workspace': e.workspace, 'project': None}}
    assert HOME not in raw.decode()


def _leaf(path, value):
    out = value
    for k in reversed(path):
        out = {k: out}
    return out


def _with_sibling(payload, path):
    node = payload
    for k in path[:-1]:
        node = node[k]
    node['zz_sibling'] = HOME
    return payload


# written out, not read from the table, so that dropping an entry fails here
EXEMPT = [
    ('mission.created', ('title',)),
    ('mission.updated', ('added', 'requirements')), ('mission.updated', ('added', 'constraints')),
    ('idea.created', ('title',)),
    ('feedback.received', ('promoted', 'title')), ('feedback.received', ('promoted', 'text')),
    ('feedback.received', ('promoted', 'anchors')),
    ('feedback.received', ('promoted', 'constraint')),
    ('meeting.imported', ('name',)),
    ('automation.created', ('name',)), ('automation.created', ('trigger',)),
    ('project.created', ('name',)),
    ('repository.registered', ('path',)), ('repository.model_added', ('path',)),
    ('repository.file_added', ('path',)),
    ('policy_rule.created', ('before',)), ('policy_rule.created', ('after',)),
    ('policy_rule.retired', ('before',)),
]


def test_S2_the_exemption_table_is_exactly_the_owner_list():
    assert sorted(EXEMPT) == sorted((t, p) for t, ps in public.EVENT_AUTHORED.items() for p in ps)


@pytest.mark.parametrize('type_,path', EXEMPT, ids=['%s.%s' % (t, '.'.join(p)) for t, p in EXEMPT])
def test_S2_every_exemption_entry_keeps_its_authored_leaf_and_scrubs_the_rest(homes, type_, path):
    leaf = {'k': [HOME + '/x', KEY]}
    payload = _with_sibling(_leaf(path, deepcopy(leaf)), path)
    got = public.public_event(envelope(type_, deepcopy(payload)), homes)['payload']
    node, want = got, deepcopy(payload)
    for k in path[:-1]:
        node, want = node[k], want[k]
    assert node[path[-1]] == leaf
    assert node['zz_sibling'] == 'its home'
    system = public.public_event(envelope('mission.state_changed', deepcopy(payload)), homes)['payload']
    node = system
    for k in path[:-1]:
        node = node[k]
    assert node[path[-1]] == {'k': ['its home/x', public_account_id(KEY)]}
    sys_actor = public.public_event(envelope(type_, deepcopy(payload), 'system'), homes)['payload']
    node = sys_actor
    for k in path[:-1]:
        node = node[k]
    assert node[path[-1]] == leaf


@pytest.mark.parametrize('type_,path', [
    ('mission.updated', ('planning_blocked', 'questions')),
    ('knowledge_item.created', ('title',))], ids=['planning_blocked.questions', 'knowledge_title'])
def test_OB_model_authored_leaves_are_scrubbed(homes, type_, path):
    got = public.public_event(envelope(type_, _leaf(path, [HOME + '/x'])), homes)['payload']
    node = got
    for k in path:
        node = node[k]
    assert node == ['its home/x']
