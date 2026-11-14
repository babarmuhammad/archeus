"""K1 — knowledge builds with no Claude Code installed (testing-strategy §6,
ADR-0022): the pass runs on the one `headless` harness there is, a harness that
does not declare `headless` is never elected, and your own-call choice is
honoured when it is installed and capable. The RouteDecision records the
election and every rejected candidate."""

from .support import knowledge_pass

ENTITIES = {'entities': [
    {'name': 'core', 'kind': 'module', 'module': 'app/core', 'summary': 'The domain.'},
    {'name': 'api', 'kind': 'module', 'module': 'app/api', 'summary': 'The HTTP layer.'}],
    'relations': [{'from': 'api', 'rel': 'depends_on', 'to': 'core'}]}


def local(id_='fake_local', **kw):
    return dict({'id': id_, 'structured': 'prompted',
                 'replies': {'knowledge_extraction': [{'parsed': ENTITIES}]}}, **kw)


def test_the_pass_runs_on_a_harness_that_is_not_claude_code(own_calls):
    client, rig = own_calls([local()])
    repo = rig.fixture_repo('layered-python')
    kp = knowledge_pass(client, repo.project_id)
    assert (kp['state'], kp['items']) == ('ok', 2)
    items = client.list_knowledge(project_id=repo.project_id, state='CANDIDATE')
    assert sorted(i['title'] for i in items if i['type'] == 'ENTITY') == ['api', 'core']
    rd = client.route_why(kp['route_decision_id'])
    assert (rd['selected'], rd['decided_by'], rd['purpose']) == (
        'fake_local', 'router', 'knowledge_extraction')
    assert 'claude_code' not in {c['resource'] for c in rd['candidates']}


def test_a_harness_without_headless_is_never_elected(own_calls):
    client, rig = own_calls([local('aaa_interactive', headless=False), local()])
    repo = rig.fixture_repo('layered-python')
    rd = client.route_why(knowledge_pass(client, repo.project_id)['route_decision_id'])
    assert rd['selected'] == 'fake_local'
    (no,) = [c for c in rd['candidates'] if c['resource'] == 'aaa_interactive']
    assert no['eliminated_at_step'] == 'headless'


def test_with_no_capable_harness_the_pass_is_unavailable_and_nothing_is_learned(own_calls):
    client, rig = own_calls([local('only_interactive', headless=False),
                             local('not_installed', installed=False)])
    repo = rig.fixture_repo('layered-python')
    kp = knowledge_pass(client, repo.project_id)
    assert (kp['state'], kp['items']) == ('unavailable', 0)
    assert client.route_why(kp['route_decision_id'])['selected'] is None
    assert client.list_knowledge(project_id=repo.project_id, state='CANDIDATE') == []


def test_your_choice_is_honoured_with_its_own_model_when_installed_and_capable(own_calls):
    client, rig = own_calls([local('fake_a'), local('fake_b', models=['spark/qwen3.8'])],
                            preference={'harness': 'fake_b', 'model': 'spark/qwen3.8'})
    repo = rig.fixture_repo('layered-python')
    rd = client.route_why(knowledge_pass(client, repo.project_id)['route_decision_id'])
    assert (rd['selected'], rd['model']) == ('fake_b', 'spark/qwen3.8')
    (a,) = [c for c in rd['candidates'] if c['resource'] == 'fake_a']
    assert a['eliminated_at_step'] == 'election'


def test_a_choice_that_is_not_installed_falls_back_and_drops_its_model(own_calls):
    client, rig = own_calls([local('fake_a'), local('fake_b', installed=False)],
                            preference={'harness': 'fake_b', 'model': 'spark/qwen3.8'})
    repo = rig.fixture_repo('layered-python')
    rd = client.route_why(knowledge_pass(client, repo.project_id)['route_decision_id'])
    assert (rd['selected'], rd['model']) == ('fake_a', None)      # never translated


def test_the_router_not_the_pre_router_election_decides(own_calls):
    client, rig = own_calls([local()])
    repo = rig.fixture_repo('layered-python')
    rd = client.route_why(knowledge_pass(client, repo.project_id)['route_decision_id'])
    assert rd['decided_by'] == 'router'
