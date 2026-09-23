"""The six ports, their P1 stubs, and the gate that keeps real adapters out
while policy is a stub (plan §31.4 — the P9 gate as code)."""

import pytest

from archeus.core import ports
from archeus.core.domain import actions, entities as E, ids
from archeus.core.domain.values import Ref
from archeus.harnesses.fake import FakeHarness
from archeus.harnesses.registry import AdapterRegistry, PolicyStubError


def test_all_six_ports_exist_as_protocols():
    for name in ('Policy', 'Router', 'Brain', 'Verifier', 'Review', 'Node'):
        port = getattr(ports, name)
        assert getattr(port, '_is_protocol', False), name


@pytest.mark.parametrize('stub,port', [
    (ports.AllowAllPolicy(), ports.Policy),
    (ports.FixedCandidateRouter('acc_x'), ports.Router),
    (ports.ScriptedBrain({}), ports.Brain),
    (ports.AutoPassVerifier(), ports.Verifier),
    (ports.AutoAcceptReview(), ports.Review),
])
def test_each_stub_satisfies_its_port(stub, port):
    assert isinstance(stub, port)


def test_the_stubs_return_valid_domain_objects():
    act = actions.Action(action_class='deploy', target='prod')
    d = ports.AllowAllPolicy().evaluate(act, {})
    assert isinstance(d, E.PolicyDecision) and d.decision == 'ALLOW' and 'stub' in d.reason
    subj = Ref('task', ids.new_id('task'))
    r = ports.FixedCandidateRouter('acc_A').route(subj, 0.0)
    assert r.selected == 'acc_A' and r.subject == subj
    assert ports.AutoPassVerifier().verify(subj).state == 'PASSED'
    m = E.Mission(id=ids.new_id('mission'), workspace_id=ids.GLOBAL_WORKSPACE,
                  title='t', objective='o')
    rv = ports.AutoAcceptReview().review(m)
    assert (rv.mission_id, rv.verdict, rv.state, rv.independent) == (m.id, 'accept',
                                                                       'ACCEPTED', False)


def test_the_scripted_brain_answers_in_order_and_never_invents():
    brain = ports.ScriptedBrain({'plan.v1': [{'tasks': [1]}, {'tasks': [2]}]})
    assert brain.call('plan.v1', 'p1') == {'tasks': [1]}
    assert brain.call('plan.v1', 'p2') == {'tasks': [2]}
    with pytest.raises(LookupError):
        brain.call('plan.v1', 'p3')
    with pytest.raises(LookupError):
        brain.call('intent.v1', 'p')
    assert [c[0] for c in brain.calls] == ['plan.v1'] * 3 + ['intent.v1']


# ── the adapter registry gate ───────────────────────────────────────────────

class RealLookingAdapter:
    """Implements the whole contract; any non-fake adapter looks like this."""
    id = 'claude_code'

    def discover(self): ...
    def capabilities(self, account): ...
    def authenticate(self, account): ...
    def start(self, spec): raise AssertionError('a refused adapter must never start')
    def send(self, handle, message): ...
    def pause(self, handle): ...
    def resume(self, spec, state): ...
    def stop(self, handle, *, grace_s): ...
    def inspect(self, handle): ...
    def status(self, handle): ...
    def handoff(self, checkpoint): ...
    def collect_result(self, handle): ...


class NotFakeAtAll(FakeHarness):
    """A subclass is not the fake: class identity decides, not inheritance."""


class ImpostorAdapter(RealLookingAdapter):
    id = 'fake'                    # claiming the id does not make it the fake


class RealPolicy:
    is_stub = False                 # only the P9 engine will ever say this

    def evaluate(self, action, ctx): ...


def test_the_fake_adapter_is_allowed_under_the_stub_policy():
    reg = AdapterRegistry(ports.AllowAllPolicy())
    fake = reg.register(FakeHarness())
    assert reg.get('fake') is fake and reg.ids() == ['fake']


@pytest.mark.parametrize('adapter', [RealLookingAdapter(), ImpostorAdapter(), NotFakeAtAll()],
                         ids=['real', 'impostor-id', 'fake-subclass'])
def test_a_real_adapter_is_refused_while_policy_is_a_stub(adapter):
    reg = AdapterRegistry(ports.AllowAllPolicy())
    with pytest.raises(PolicyStubError):
        reg.register(adapter)
    assert reg.ids() == []


@pytest.mark.parametrize('flag', [True, None, 0, 'no', 'False'])
def test_anything_but_an_explicit_is_stub_false_counts_as_a_stub(flag):
    class Policy:
        is_stub = flag

        def evaluate(self, action, ctx): ...
    with pytest.raises(PolicyStubError):
        AdapterRegistry(Policy()).register(RealLookingAdapter())


def test_a_policy_that_says_nothing_is_a_stub():
    class Silent:
        def evaluate(self, action, ctx): ...
    with pytest.raises(PolicyStubError):
        AdapterRegistry(Silent()).register(RealLookingAdapter())


def test_only_a_real_policy_opens_the_gate():
    reg = AdapterRegistry(RealPolicy())
    assert reg.register(RealLookingAdapter()).id == 'claude_code'


def test_the_gate_is_rechecked_on_every_lookup():
    reg = AdapterRegistry(RealPolicy())
    reg.register(RealLookingAdapter())
    reg.policy = ports.AllowAllPolicy()             # policy regressed to the stub
    with pytest.raises(PolicyStubError):
        reg.get('claude_code')


def test_the_registry_refuses_what_is_not_an_adapter_and_duplicates():
    reg = AdapterRegistry(ports.AllowAllPolicy())
    with pytest.raises(TypeError):
        reg.register(object())
    reg.register(FakeHarness())
    with pytest.raises(ValueError):
        reg.register(FakeHarness())
