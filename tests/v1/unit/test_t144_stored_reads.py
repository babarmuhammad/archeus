from copy import deepcopy
from types import SimpleNamespace

import pytest

from archeus.core.application import public, queries, resources
from archeus.core.domain import entities
from archeus.core.homes import Homes, public_account_id

HOME = 'C:/T144/Work-Claude'
OLD = 'C:/T144/Old-Claude'
KEY = 'h:' + HOME.lower()
OLD_KEY = 'h:' + OLD.lower()


@pytest.fixture
def homes():
    return Homes([HOME], [('h', KEY, HOME), ('h', OLD_KEY, OLD)],
                 shorts=lambda _: None, path_flavour='windows')


def decision():
    return {'account_ref': HOME, 'account_id': 'acc_registered',
            'explanation': 'failed at ' + HOME,
            'candidates': [{'account_ref': KEY, 'reason': 'no login in ' + HOME}],
            'outcome': {'account_ref': KEY, 'reason': 'stderr ' + HOME},
            'requirements': {k: {'accounts': [KEY, OLD_KEY, 'acc_registered']}
                             for k in ('forbidden', 'required', 'preferred')},
            'input_snapshot': {
                'accounts': [{'ref': KEY, 'home_ref': HOME, 'home_key': HOME.lower(),
                              'why_not': 'no login in ' + HOME, 'label': HOME}],
                'affinity': {'account': KEY}, 'approved_fallbacks': [OLD_KEY]},
            'usage': [{'account_ref': KEY, 'account_id': 'acc_registered'}]}


def test_decision_outcome_and_system_reasons_are_projected(homes):
    out = queries._public_decision(decision(), homes)
    assert out['outcome'] == {'account_ref': public_account_id(KEY), 'reason': 'stderr its home'}
    assert out['explanation'] == 'failed at its home'
    assert out['candidates'] == [{'account_ref': public_account_id(KEY),
                                  'reason': 'no login in its home'}]
    assert out['account_ref'] is None
    assert out['usage'][0]['account_ref'] == public_account_id(KEY)
    assert out['account_id'] == 'acc_registered'


def test_decision_requirements_map_every_account_lane(homes):
    out = queries._public_decision(decision(), homes)
    for lane in ('forbidden', 'required', 'preferred'):
        assert out['requirements'][lane]['accounts'] == [
            public_account_id(KEY), public_account_id(OLD_KEY), 'acc_registered']


def test_snapshot_affinity_and_fallbacks_are_projected(homes):
    out = queries._public_decision(decision(), homes)['input_snapshot']
    assert out['affinity']['account'] == public_account_id(KEY)
    assert out['approved_fallbacks'] == [public_account_id(OLD_KEY)]
    assert out['accounts'][0]['ref'] == public_account_id(KEY)
    assert not {'home_ref', 'home_key'} & out['accounts'][0].keys()


@pytest.mark.parametrize('ref', ['fake:fake_local', 'acc_registered', KEY])
def test_decision_keeps_registered_refs_and_projects_default_keys(homes, ref):
    body = decision()
    body['account_ref'] = ref
    body['outcome']['account_ref'] = ref
    body['candidates'][0]['account_ref'] = ref
    body['usage'][0]['account_ref'] = ref
    body['input_snapshot']['accounts'][0]['ref'] = ref
    body['input_snapshot']['affinity']['account'] = ref
    body['input_snapshot']['approved_fallbacks'] = [ref]
    for lane in ('forbidden', 'required', 'preferred'):
        body['requirements'][lane]['accounts'] = [ref]
    before = deepcopy(body)

    out = queries._public_decision(body, homes)

    expected = public_account_id(KEY) if ref == KEY else ref
    assert out['account_ref'] == out['outcome']['account_ref'] == expected
    assert out['candidates'][0]['account_ref'] == expected
    assert out['usage'][0]['account_ref'] == expected
    assert out['input_snapshot']['accounts'][0]['ref'] == expected
    assert out['input_snapshot']['affinity']['account'] == expected
    assert out['input_snapshot']['approved_fallbacks'] == [expected]
    for lane in ('forbidden', 'required', 'preferred'):
        assert out['requirements'][lane]['accounts'] == [expected]
    assert body == before


def test_snapshot_why_not_is_scrubbed(homes):
    out = queries._public_decision(decision(), homes)
    assert out['input_snapshot']['accounts'][0]['why_not'] == 'no login in its home'


def test_verification_drops_only_private_performer_ref(homes):
    body = {'performed_by': {'account_ref': HOME, 'account_id': 'acc_registered'},
            'checks': [{'name': HOME, 'argv': [KEY], 'files': [HOME],
                        'detail': HOME, 'unlisted': {'nested': KEY}}],
            'criteria': [{'text': KEY, 'unlisted': HOME}], 'error': HOME}
    before = deepcopy(body)
    out = queries._public_verification(body, homes)
    assert out['performed_by'] == {'account_id': 'acc_registered'}
    assert out['checks'] == [{'name': HOME, 'argv': [KEY], 'files': [HOME],
                              'detail': 'its home',
                              'unlisted': {'nested': public_account_id(KEY)}}]
    assert out['criteria'] == [{'text': KEY, 'unlisted': 'its home'}]
    assert out['error'] == 'its home' and body == before


def test_review_resource_maps_historical_key_and_keeps_authored_review(homes):
    body = {'reviewer_resource': {'account': OLD_KEY}, 'summary': HOME,
            'risks': [KEY], 'new_system_field': HOME}
    out = queries._public_review(body, homes)
    assert out['reviewer_resource']['account'] == public_account_id(OLD_KEY)
    assert out['summary'] == HOME and out['risks'] == [KEY]
    assert out['new_system_field'] == 'its home'


def test_approval_items_presentation_consequences_and_against_are_projected(homes):
    body = {'items': [{'resource': {'account': KEY}, 'action': {'paths': [HOME]}}], 'presented': {
        'what': [{'account': OLD_KEY, 'title': KEY, 'paths': [HOME]}],
        'consequences': {'approve': 'run on ' + KEY},
        'against': {'account': KEY, 'mission': {'title': HOME, 'objective': KEY},
                    'plan': {'summary': HOME}}}, 'decision_note': HOME}
    before = deepcopy(body)
    out = queries._public_approval(body, homes)
    assert out['items'][0]['resource']['account'] == public_account_id(KEY)
    assert out['items'][0]['action']['paths'] == [HOME]
    assert out['presented']['what'] == [
        {'account': public_account_id(OLD_KEY), 'title': KEY, 'paths': [HOME]}]
    assert out['presented']['consequences']['approve'] == 'run on ' + public_account_id(KEY)
    assert out['presented']['against']['account'] == public_account_id(KEY)
    assert out['presented']['against']['mission'] == body['presented']['against']['mission']
    assert out['presented']['against']['plan'] == {'summary': HOME}
    assert out['decision_note'] == HOME and body == before


def test_read_projection_never_mutates_snapshot_or_input(homes):
    body = decision()
    before = deepcopy(body)
    out = queries._public_decision(body, homes)
    assert body == before
    out['input_snapshot']['accounts'][0]['label'] = 'changed'
    out['requirements']['required']['accounts'].append('changed')
    assert body == before


def test_old_home_ref_snapshot_stays_immutable_in_projection(homes):
    body = decision()
    body['input_snapshot']['accounts'][0].update(registered=True, id='acc_registered', ref=HOME)
    before = deepcopy(body)
    out = queries._public_decision(body, homes)
    assert out['input_snapshot']['accounts'][0]['ref'] is None
    assert body == before


def test_typed_home_refs_are_null_and_authored_labels_are_preserved(homes):
    body = decision()
    body['outcome']['account_ref'] = HOME
    body['candidates'][0]['label'] = KEY
    out = queries._public_decision(body, homes)
    assert out['outcome']['account_ref'] is None
    assert out['input_snapshot']['accounts'][0]['label'] == HOME
    assert out['candidates'][0]['label'] == KEY


def test_unlisted_nested_system_fields_receive_production_fallback(homes):
    body = decision()
    body['unlisted'] = {'nested': [HOME + '/x', 'waiting on ' + OLD_KEY]}
    out = queries._public_decision(body, homes)
    assert out['unlisted'] == {'nested': ['its home/x', 'waiting on ' + public_account_id(OLD_KEY)]}


@pytest.mark.parametrize('actor', ['user_device', 'system'])
def test_provenance_not_actor_controls_exemptions(homes, actor):
    body = {'actor': {'kind': actor}, 'summary': HOME, 'system': {'summary': HOME}}
    out = public.system_value(body, homes, authored=(('summary',),))
    assert out['summary'] == HOME
    assert out['system']['summary'] == 'its home'


def test_authored_exempt_content_keeps_exact_keys_and_home_text(homes):
    body = {'summary': KEY, 'risks': [HOME], 'reviewer_resource': {'account': KEY}}
    out = queries._public_review(body, homes)
    assert out['summary'] == KEY and out['risks'] == [HOME]
    out['risks'].append('changed')
    assert body['risks'] == [HOME]


def test_builder_maps_all_historical_snapshots_without_home_probes(monkeypatch):
    snapshots = [SimpleNamespace(entity=SimpleNamespace(input_snapshot={'accounts': [
        {'harness': 'h', 'registered': False, 'ref': k, 'home_ref': h}]}))
        for k, h in ((KEY, HOME), (OLD_KEY, OLD))]
    monkeypatch.setattr(resources.rows, 'where',
                        lambda conn, cls: snapshots if cls is entities.RouteDecision else [])

    def forbidden(_):
        pytest.fail('historical mapping probed a home')

    first = resources.homes(None, None, (), shorts=forbidden)
    second = resources.homes(None, None, (), shorts=forbidden)
    assert first.keys == second.keys == {k: public_account_id(k) for k in (KEY, OLD_KEY)}
    assert len(set(first.keys.values())) == 2
    assert public.system_value([KEY, OLD_KEY, HOME, OLD], first) == [
        public_account_id(KEY), public_account_id(OLD_KEY), 'its home', 'its home']


def test_builder_current_adapter_failure_is_soft_and_shorts_are_injected(monkeypatch):
    row = SimpleNamespace(entity=SimpleNamespace(home_ref=HOME))
    monkeypatch.setattr(resources.rows, 'where',
                        lambda conn, cls: [row] if cls is entities.Account else [])
    probes = []

    class Broken:
        def default_account(self):
            raise RuntimeError('unavailable')

    got = resources.homes(None, None, [Broken()], shorts=lambda p: probes.append(p))
    assert probes and public.system_value(HOME, got) == 'its home'


def test_builder_includes_current_registry_and_callers_without_probing_defaults(monkeypatch):
    monkeypatch.setattr(resources.rows, 'where', lambda conn, cls: [])

    class Adapter:
        id = 'h'

        def default_account(self):
            return SimpleNamespace(account_id=KEY, home_ref=HOME)

    adapter = Adapter()
    registry = SimpleNamespace(ids=lambda: ['h'], get=lambda _: adapter)

    def forbidden(_):
        pytest.fail('default mapping probed a home')

    got = resources.homes(None, registry, [adapter], shorts=forbidden)
    assert got.keys == {KEY: public_account_id(KEY)}
    assert public.system_value('waiting on ' + KEY, got) == 'waiting on ' + public_account_id(KEY)


def test_builder_scrubs_retired_registered_homes_without_probing_them(monkeypatch):
    row = SimpleNamespace(entity=SimpleNamespace(input_snapshot={'accounts': [
        {'registered': True, 'id': 'acc_registered', 'ref': OLD, 'home_ref': OLD}]}))
    monkeypatch.setattr(resources.rows, 'where',
                        lambda conn, cls: [row] if cls is entities.RouteDecision else [])

    def forbidden(_):
        pytest.fail('historical registered home was probed')

    got = resources.homes(None, None, (), shorts=forbidden)
    assert public.system_value(OLD + '/x', got) == 'its home/x'
    assert public.system_value('acc_registered', got) == 'acc_registered'


def test_accounts_scrub_system_fields_and_preserve_authored_policy(homes, monkeypatch):
    body = {'id': 'acc_registered', 'home_ref': HOME, 'home_key': HOME.lower(),
            'label': KEY, 'why_not': 'login at ' + HOME,
            'resource_policy': {'project_allow': [HOME], 'project_deny': [KEY]},
            'unlisted': {'nested': 'retry ' + OLD_KEY}}
    before = deepcopy(body)
    monkeypatch.setattr(resources.rows, 'where', lambda conn, cls: [object()])
    monkeypatch.setattr(resources, 'account_view', lambda conn, row: body)
    (out,) = resources.accounts(None, homes)
    assert not {'home_ref', 'home_key'} & out.keys()
    assert out['label'] == KEY and out['resource_policy'] == body['resource_policy']
    assert out['why_not'] == 'login at its home'
    assert out['unlisted']['nested'] == 'retry ' + public_account_id(OLD_KEY)
    assert body == before
