"""The native origin backend: bind the peer's process at accept, re-check per request.

No socket-owner, PID, token or SID probe lives here: every outside fact arrives
through the injected `origin.AttestationReaders` bundle and is decided by the
pure attestor (`archeus/node/attest.py`). `attest` answers once per accepted
connection and keeps the returned `ProcessBinding` on the evidence the connection
holds; `valid` re-checks that binding before any privileged effect, and a missing,
expired, dead, recycled or unreadable binding is refused. Built with no readers
this shipped backend authorizes nothing, exactly as before: activation waits for
the native readers and the separately evidenced Core-owned path registry.
"""
from ..api.origin import OriginClass, OriginEvidence
from . import attest as _attest

ATTESTED = 'attested'
NO_EVIDENCE = 'no_evidence'


class WindowsOriginBackend:
    def __init__(self, *, readers=None):
        self.readers = readers

    def attest(self, context):
        if self.readers is None:
            return OriginEvidence(accept_generation=context.accept_generation)
        result = _attest.attest_owner(**self.readers.attest_kwargs(_remote_port(context)))
        if not result.ok or result.binding is None:
            return OriginEvidence(accept_generation=context.accept_generation,
                                  reason=_reason(result))
        binding = result.binding
        # a peer proven to sit under the launcher inside Core's Job is an execution's
        # process, never the user's; the path stays unapproved until Core's registry says
        return OriginEvidence(origin=OriginClass.EXECUTION,
                              identity='process:%d:%s' % (binding.pid, binding.creation_time),
                              process_binding=binding,
                              accept_generation=context.accept_generation,
                              reason=ATTESTED)

    def valid(self, context, evidence):
        if self.readers is None:
            return False
        binding = getattr(evidence, 'process_binding', None)
        if getattr(binding, 'remote_port', None) != _remote_port(context):
            return False
        return _attest.binding_valid(binding, **self.readers.recheck_kwargs()).ok

    def release(self, context, evidence):
        pass


def _remote_port(context):
    """The accepted peer's port: the only key the owner lookup may take."""
    return context.remote_endpoint[1]


def _reason(result):
    return result.failures[0] if result.failures else NO_EVIDENCE
