"""The CoreClient contract (testing-strategy §1.1): every binding implements
every operation with the Protocol's exact signature, and an operation that has
no implementation yet fails loudly instead of returning something."""

import inspect

import pytest

from v1.judge.client import IMPLEMENTED, OPERATIONS, CoreClient, CoreClientError, InProcessClient

BINDINGS = (InProcessClient,)

#: The operations testing-strategy §1.1 freezes. Adding one is a contract
#: change: it goes in the document first.
DOCUMENTED = ('submit_message', 'create_mission', 'get_mission', 'list_missions',
              'decide_approval', 'pause', 'resume', 'stop', 'route_why', 'status',
              'digest', 'ack', 'import_meeting', 'register_account',
              'set_resource_policy', 'events')


def test_the_contract_is_exactly_the_documented_operations():
    assert set(OPERATIONS) == set(DOCUMENTED)


@pytest.mark.parametrize('binding', BINDINGS)
def test_each_binding_matches_the_protocol(binding, tmp_path):
    client = binding(tmp_path)
    assert isinstance(client, CoreClient)
    for op in OPERATIONS:
        assert inspect.signature(getattr(binding, op)) == inspect.signature(
            getattr(CoreClient, op)), op


@pytest.mark.parametrize('op', [op for op in OPERATIONS if op not in IMPLEMENTED])
def test_an_unimplemented_operation_fails_loudly(op, tmp_path):
    with pytest.raises(NotImplementedError, match=op):
        getattr(InProcessClient(tmp_path), op)('x')


@pytest.fixture
def client(archeus_home):
    c = InProcessClient(archeus_home)
    yield c
    c.close()


def test_an_illegal_transition_is_422_naming_machine_from_and_to(client):
    """plan §31.1 P3 acceptance, at the contract level (the HTTP status in P3.5)."""
    m = client.create_mission(title='t', objective='o')
    before = client.events(0)
    with pytest.raises(CoreClientError) as err:
        client.pause(m['id'])                       # CREATED has no pause edge
    e = err.value
    assert (e.status, e.code) == (422, 'invalid_transition')
    assert e.detail == {'machine': 'mission', 'from': 'CREATED', 'to': 'PAUSED',
                        'trigger': 'pause'}
    with pytest.raises(CoreClientError) as err:
        client.resume(m['id'])
    assert (err.value.status, err.value.detail['to']) == (422, 'RESUMED')
    assert client.events(0) == before and client.get_mission(m['id'])['version'] == 1


def test_a_refused_guard_is_422_guard_failed_not_invalid_transition(client):
    from archeus.core.application.lifecycle import GuardFailed
    from archeus.core.domain.guards import GuardResult
    from archeus.infra.db.writer import VersionConflict

    def refused():
        raise GuardFailed('mission', 'EXECUTING', 'VERIFYING', 'all_tasks_done',
                          GuardResult('all_tasks_done', False, 'tasks not done: t1'))
    with pytest.raises(CoreClientError) as err:
        client._call(refused)
    assert (err.value.status, err.value.code) == (422, 'guard_failed')
    assert err.value.detail == {'machine': 'mission', 'from': 'EXECUTING', 'to': 'VERIFYING',
                                'trigger': 'all_tasks_done', 'guard': 'all_tasks_done',
                                'reason': 'tasks not done: t1'}

    def stale():
        raise VersionConflict('msn_x', 1, 2)
    with pytest.raises(CoreClientError) as err:
        client._call(stale)
    assert (err.value.status, err.value.code, err.value.detail) == (409, 'version_conflict',
                                                                     {'current': 2})


def test_control_verbs_reach_only_missions_until_p11(client):
    with pytest.raises(NotImplementedError, match='P11'):
        client.pause('exe_01J0000000000000000000000Z')


def test_errors_carry_status_and_code():
    e = CoreClientError(422, 'invalid_transition', {'machine': 'mission'})
    assert (e.status, e.code, e.detail['machine']) == (422, 'invalid_transition', 'mission')
