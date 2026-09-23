"""The CoreClient contract (testing-strategy §1.1): every binding implements
every operation with the Protocol's exact signature, and an operation that has
no implementation yet fails loudly instead of returning something."""

import inspect

import pytest

from v1.judge.client import OPERATIONS, CoreClient, CoreClientError, InProcessClient

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


@pytest.mark.parametrize('op', OPERATIONS)
def test_an_unimplemented_operation_fails_loudly(op, tmp_path):
    with pytest.raises(NotImplementedError, match=op):
        getattr(InProcessClient(tmp_path), op)('x')


def test_errors_carry_status_and_code():
    e = CoreClientError(422, 'invalid_transition', {'machine': 'mission'})
    assert (e.status, e.code, e.detail['machine']) == (422, 'invalid_transition', 'mission')
