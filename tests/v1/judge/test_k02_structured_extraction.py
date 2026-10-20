"""K2 — structured extraction across mechanisms (testing-strategy §6, ADR-0006,
ADR-0022): a `native` and a `prompted` harness both yield items that pass Core's
validation; invalid output is retried once, then the call fails and nothing is
learned; the knowledge names the harness and the model that produced it."""

import pytest

from .support import knowledge_pass

GOOD = {'entities': [{'name': 'core', 'kind': 'module', 'module': 'app/core',
                      'summary': 'The domain.'}]}


@pytest.mark.parametrize('mechanism', ['native', 'prompted'])
def test_both_mechanisms_yield_the_same_valid_knowledge(own_calls, mechanism):
    client, rig = own_calls([{'id': 'fake_' + mechanism, 'structured': mechanism,
                              'replies': {'knowledge_extraction': [{'parsed': GOOD}]}}])
    repo = rig.fixture_repo('layered-python')
    kp = knowledge_pass(client, repo.project_id)
    assert (kp['state'], kp['items']) == ('ok', 1)
    (item,) = client.list_knowledge(project_id=repo.project_id, state='CANDIDATE')
    assert (item['type'], item['title'], item['origin'], list(item['anchors'])) == (
        'ENTITY', 'core', 'inferred', ['app/core'])


def test_invalid_output_is_retried_once_then_accepted(own_calls):
    client, rig = own_calls([{'id': 'fake_prompted', 'structured': 'prompted', 'replies': {
        'knowledge_extraction': [{'text': 'I looked at it and it is fine.'},
                                 {'parsed': GOOD}]}}])
    repo = rig.fixture_repo('layered-python')
    kp = knowledge_pass(client, repo.project_id)
    assert kp['state'] == 'ok'
    assert client.route_why(kp['route_decision_id'])['outcome']['attempts'] == 2


def test_invalid_twice_fails_the_call_and_learns_nothing(own_calls):
    wrong = {'parsed': {'entities': [{'name': 'core'}]}}          # no kind, no summary
    client, rig = own_calls([{'id': 'fake_native', 'replies': {
        'knowledge_extraction': [wrong]}}])
    repo = rig.fixture_repo('layered-python')
    kp = knowledge_pass(client, repo.project_id)
    assert (kp['state'], kp['items']) == ('invalid', 0)
    assert 'kind' in kp['reason']
    assert client.list_knowledge(project_id=repo.project_id, state='CANDIDATE') == []


def test_every_item_names_the_harness_and_model_that_produced_it(own_calls):
    client, rig = own_calls([{'id': 'fake_prompted', 'structured': 'prompted',
                              'models': ['local/llama'], 'replies': {
                                  'knowledge_extraction': [{'parsed': GOOD}]}}],
        preference={'harness': 'fake_prompted', 'model': 'local/llama'})
    repo = rig.fixture_repo('layered-python')
    knowledge_pass(client, repo.project_id)
    (item,) = client.list_knowledge(project_id=repo.project_id, state='CANDIDATE')
    rd = client.route_why(item['route_decision_id'])
    assert (rd['selected'], rd['model']) == ('fake_prompted', 'local/llama')
    assert item['source_ref'] == {'kind': 'repository_inspection',
                                  'id': item['source_ref']['id']}
    assert item['context_package_id'] == rd['context_package_id']
