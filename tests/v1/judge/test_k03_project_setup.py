"""K3 — project setup completes after the knowledge pass (testing-strategy §6,
plan P6): create project -> deterministic assessment -> the initial knowledge
pass. The project is usable from its assessment whatever the pass does — it
succeeds, fails, or is gated by ADR-0021 — and its result is a count."""

from .support import knowledge_pass

GOOD = {'entities': [{'name': 'core', 'kind': 'module', 'summary': 'The domain.'},
                     {'name': 'api', 'kind': 'module', 'summary': 'The HTTP layer.'}]}


def _usable(client, repo):
    (p,) = client.status(project_id=repo.project_id)['projects']
    assert p['state'] == 'ACTIVE'
    assert p['repositories'][0]['architecture_state'] in ('CONSISTENT', 'DRIFTED')
    m = client.create_mission(title='After setup', objective='o', project_id=repo.project_id)
    assert client.get_mission(m['id'])['project_id'] == repo.project_id


def test_a_successful_pass_is_counted_and_the_project_is_usable(own_calls):
    client, rig = own_calls([{'id': 'fake', 'replies': {
        'knowledge_extraction': [{'parsed': GOOD}]}}])
    repo = rig.fixture_repo('layered-python')
    kp = knowledge_pass(client, repo.project_id)
    assert kp['state'] == 'ok' and isinstance(kp['items'], int) and kp['items'] == 2
    assert len(client.list_knowledge(project_id=repo.project_id, state='CANDIDATE')) == 2
    _usable(client, repo)


def test_a_failed_pass_never_fails_the_project(own_calls):
    client, rig = own_calls([{'id': 'fake', 'replies': {
        'knowledge_extraction': [{'error': 'failed', 'detail': 'the model crashed'}]}}])
    repo = rig.fixture_repo('layered-python')
    kp = knowledge_pass(client, repo.project_id)
    assert (kp['state'], kp['items'], kp['reason']) == ('failed', 0, 'the model crashed')
    _usable(client, repo)


def test_a_pass_gated_by_the_provider_terms_never_fails_the_project(own_calls):
    client, rig = own_calls([{'id': 'real_like', 'gated': True, 'replies': {
        'knowledge_extraction': [{'parsed': GOOD}]}}])
    repo = rig.fixture_repo('layered-python')
    kp = knowledge_pass(client, repo.project_id)
    assert (kp['state'], kp['items']) == ('gated', 0)
    (c,) = client.route_why(kp['route_decision_id'])['candidates']
    assert c['eliminated_at_step'] == 'provider_terms'
    assert client.list_knowledge(project_id=repo.project_id, state='CANDIDATE') == []
    _usable(client, repo)


def test_a_model_claiming_it_is_done_is_not_knowledge(own_calls):
    client, rig = own_calls([{'id': 'fake', 'structured': 'prompted', 'replies': {
        'knowledge_extraction': [{'text': 'Done! The project is fully set up.'}]}}])
    repo = rig.fixture_repo('layered-python')
    kp = knowledge_pass(client, repo.project_id)
    assert (kp['state'], kp['items']) == ('invalid', 0)
    assert client.list_knowledge(project_id=repo.project_id, state='CANDIDATE') == []
    _usable(client, repo)
