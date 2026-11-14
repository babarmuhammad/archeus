"""T-1261: the uncovered branches of archeus/harnesses/registry.py lines 31-66
(the P9 gate on adapter admission), denial and fail-closed first.

Selected branches, with the source line each test is built to catch:
- 45  a real adapter is refused while the policy is a stub, whatever its id
- 36  only the singleton False admits: None, 0, '', objects and a missing attribute refuse
- 32  a subclass of FakeHarness is real even though it inherits id 'fake'; the exact class admits
- 62  an admitted real adapter is refused at lookup once a stub policy is swapped in
- 54  the policy is judged again at each registration; earlier entries survive
- 52  a non-HarnessAdapter with a fake-looking id is a TypeError, before admission
- 55  a duplicate id under a real policy refuses and keeps the first object
- 54  a duplicate real id under a stub policy is an admission refusal, not a duplicate error
- 61  an unknown id is a KeyError: no default adapter is synthesised, nothing is admitted
- 66  ids are sorted after failed admissions; listing neither bypasses lookup nor mutates policy

Rig: an in-memory HarnessAdapter subclass as the real adapter, FakeHarness as
the only fake, and policy objects that carry only `is_stub`. Nothing spawns a
process, opens a socket or reads the environment; no Windows-specific call.
"""

import pytest

from archeus.harnesses import base
from archeus.harnesses.fake import FakeHarness
from archeus.harnesses.registry import AdapterRegistry, PolicyStubError


class Real(base.HarnessAdapter):
    """A real adapter: a HarnessAdapter that is not FakeHarness."""

    def __init__(self, id):
        self.id = id


class Policy:
    def __init__(self, is_stub):
        self.is_stub = is_stub


class Unmarked:
    """A policy that never declared is_stub at all."""


REAL = Policy(False)
STUB = Policy(True)


def _registry(policy):
    return AdapterRegistry(policy)


def test_a_real_adapter_is_refused_under_a_stub_policy_even_with_id_fake():
    reg = _registry(STUB)
    with pytest.raises(PolicyStubError, match='policy is still a stub'):
        reg.register(Real('fake'))
    assert reg.ids() == []


def test_a_missing_is_stub_attribute_is_treated_as_a_stub():
    reg = _registry(Unmarked())
    with pytest.raises(PolicyStubError):
        reg.register(Real('r'))
    assert reg.ids() == []


@pytest.mark.parametrize('value', [None, 0, '', 'no', object(), True])
def test_only_the_singleton_false_admits_a_real_adapter(value):
    reg = _registry(Policy(value))
    with pytest.raises(PolicyStubError):
        reg.register(Real('r'))
    assert reg.ids() == []


def test_is_stub_false_admits_a_real_adapter():
    reg = _registry(REAL)
    adapter = Real('r')
    assert reg.register(adapter) is adapter
    assert reg.get('r') is adapter


class SubFake(FakeHarness):
    pass


def test_a_subclass_of_fake_harness_is_real_under_a_stub_policy():
    sub = SubFake()
    assert sub.id == 'fake'
    reg = _registry(STUB)
    with pytest.raises(PolicyStubError):
        reg.register(sub)
    assert reg.ids() == []


def test_the_exact_fake_harness_class_is_admitted_under_a_stub_policy():
    reg = _registry(STUB)
    fake = FakeHarness()
    assert reg.register(fake) is fake
    assert reg.get('fake') is fake


def test_an_admitted_real_adapter_is_refused_at_lookup_after_a_stub_swap():
    reg = _registry(Policy(False))
    reg.register(Real('r'))
    reg.policy = Policy(True)
    with pytest.raises(PolicyStubError):
        reg.get('r')
    assert reg.ids() == ['r']


def test_policy_changes_between_registrations_keep_earlier_entries():
    policy = Policy(False)
    reg = _registry(policy)
    first = reg.register(Real('a'))
    reg.policy = STUB
    with pytest.raises(PolicyStubError):
        reg.register(Real('b'))
    fake = reg.register(FakeHarness(id='f'))
    assert reg.ids() == ['a', 'f']
    assert fake.id == 'f'
    reg.policy = policy
    assert reg.get('a') is first


class Imposter:
    """Claims id 'fake' and nothing else: no adapter contract, no class identity."""
    id = 'fake'


def test_a_non_adapter_with_a_fake_looking_id_is_a_type_error_before_admission():
    reg = _registry(STUB)
    with pytest.raises(TypeError, match='does not implement the harness adapter contract'):
        reg.register(Imposter())
    assert reg.ids() == []


def test_a_duplicate_id_under_a_real_policy_keeps_the_first_object():
    reg = _registry(REAL)
    first = reg.register(Real('r'))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(Real('r'))
    assert reg.get('r') is first
    assert reg.ids() == ['r']


def test_a_duplicate_real_id_under_a_stub_policy_is_refused_as_admission_not_duplicate():
    reg = _registry(REAL)
    first = reg.register(Real('r'))
    reg.policy = STUB
    with pytest.raises(PolicyStubError):
        reg.register(Real('r'))
    assert reg.ids() == ['r']
    reg.policy = REAL
    assert reg.get('r') is first


def test_an_unknown_id_is_a_key_error_and_nothing_is_synthesised():
    reg = _registry(STUB)
    reg.register(FakeHarness())
    with pytest.raises(KeyError):
        reg.get('nope')
    assert reg.ids() == ['fake']


def test_ids_are_sorted_after_failed_admissions_and_listing_never_bypasses_lookup():
    reg = _registry(REAL)
    reg.register(FakeHarness(id='zeta'))
    reg.register(FakeHarness(id='alpha'))
    reg.register(Real('mid'))
    reg.policy = STUB
    with pytest.raises(PolicyStubError):
        reg.register(Real('late'))
    assert reg.ids() == ['alpha', 'mid', 'zeta']
    assert reg.policy is STUB
    with pytest.raises(PolicyStubError):
        reg.get('mid')
    assert reg.get('zeta').id == 'zeta'
    assert reg.policy is STUB
