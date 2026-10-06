"""The adapter registry — and the P9 gate as code (plan §31.4, H3).

No real agent with tools may run before the real policy engine exists. So the
registry REFUSES any adapter that is not the fake harness while the policy it
was built with is a stub. It fails closed on both axes:

- "fake" is decided by class identity (`type(adapter) is FakeHarness`), not by
  anything an adapter says about itself — an `id = 'fake'` on another class,
  or a subclass, is a real adapter;
- a policy is real only if it states `is_stub = False` exactly. A missing
  attribute, `None`, `0` or any other value is treated as a stub.

The check runs at registration AND at every lookup, so swapping a stub policy
in after a real adapter was admitted still refuses it.

What this is NOT: a security or trust boundary. `is_stub` is a declaration made
by code in this repository, and any object can make it; the gate exists so no
phase can wire a real adapter up before the policy engine is built, by mistake.
Whether an action is allowed is decided by the real Policy engine (P9) together
with capability removal (execution-architecture §2) — never by this flag.
"""

from .base import HarnessAdapter
from .fake import FakeHarness


class PolicyStubError(RuntimeError):
    """A real harness adapter was offered while policy is still the P1 stub."""


def _is_fake(adapter):
    return type(adapter) is FakeHarness


def _policy_is_real(policy):
    return getattr(policy, 'is_stub', True) is False


class AdapterRegistry:
    def __init__(self, policy):
        self.policy = policy
        self._adapters = {}

    def _admit(self, adapter):
        if not _is_fake(adapter) and not _policy_is_real(self.policy):
            raise PolicyStubError(
                'refusing real harness adapter %r: policy is still a stub, and real '
                'tool-using execution needs the P9 policy engine'
                % getattr(adapter, 'id', adapter))

    def register(self, adapter):
        if not isinstance(adapter, HarnessAdapter):
            raise TypeError('%r does not implement the harness adapter contract' % (adapter,))
        self._admit(adapter)
        if adapter.id in self._adapters:
            raise ValueError('an adapter with id %r is already registered' % adapter.id)
        self._adapters[adapter.id] = adapter
        return adapter

    def get(self, harness_id):
        adapter = self._adapters[harness_id]
        self._admit(adapter)
        return adapter

    def ids(self):
        return sorted(self._adapters)
