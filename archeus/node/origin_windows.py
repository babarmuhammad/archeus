"""The native origin backend: bind the peer's process at accept, re-check per request.

No socket-owner, PID, token or SID probe lives here: every outside fact arrives
through the injected `origin.AttestationReaders` bundle and is decided by the
pure attestor (`archeus/node/attest.py`). `attest` answers once per accepted
connection and keeps the returned `ProcessBinding` on the evidence the connection
holds; `valid` re-checks that binding before any privileged effect, and a missing,
expired, dead, recycled or unreadable binding is refused. Built with no readers
this shipped backend authorizes nothing. A peer in no Core Job, with no launcher
ancestor, in Core's session, on the direct loopback path, is attested USER by
exclusion; the Core path registry (`origin.CorePathRegistry`) still has to approve it.
"""
import math

from ..api import origin
from ..api.origin import OriginClass, OriginEvidence, PathClass
from . import attest as _attest

ATTESTED = 'attested'
NO_EVIDENCE = 'no_evidence'
NOT_DIRECT = 'not_direct_loopback'


class WindowsOriginBackend:
    def __init__(self, *, readers=None):
        self.readers = readers
        # accept generation -> (first binding, current binding, last attempt); None once
        # a re-attestation failed. Each connection's handler thread is its only writer.
        self._rebound = {}

    def attest(self, context):
        if self.readers is None:
            return OriginEvidence(accept_generation=context.accept_generation)
        result = _attest.attest_peer(**self.readers.attest_kwargs(_remote_port(context)))
        if not result.ok or result.binding is None:
            return OriginEvidence(accept_generation=context.accept_generation,
                                  reason=_reason(result))
        if result.binding.core_job_at_accept:
            # a peer proven to sit under the launcher inside Core's Job is an execution's
            # process, never the user's; the path stays unapproved until Core's registry says
            return self._evidence(context, OriginClass.EXECUTION, PathClass.UNAPPROVED,
                                  result.binding)
        if not origin.direct_loopback(context):
            return OriginEvidence(accept_generation=context.accept_generation,
                                  reason=NOT_DIRECT)
        return self._evidence(context, OriginClass.USER, PathClass.DIRECT_LOCAL, result.binding)

    @staticmethod
    def _evidence(context, kind, path, binding):
        return OriginEvidence(origin=kind, path=path,
                              identity='process:%d:%s' % (binding.pid, binding.creation_time),
                              process_binding=binding,
                              accept_generation=context.accept_generation, reason=ATTESTED)

    def valid(self, context, evidence):
        if self.readers is None:
            return False
        binding = getattr(evidence, 'process_binding', None)
        if getattr(binding, 'remote_port', None) != _remote_port(context):
            return False
        key = context.accept_generation
        state = self._rebound.get(key, (binding, binding, None))
        if state is None or state[0] != binding:
            return False
        result = _attest.binding_valid(state[1], **self.readers.recheck_kwargs())
        if result.ok:
            return True
        if self.readers.reattest is not True or result.failures != (_attest.EXPIRED,):
            return False
        return self._reattest(key, binding, state[2])

    def _reattest(self, key, first, last):
        kwargs = self.readers.attest_kwargs(first.remote_port)
        try:
            now = float(kwargs['clock']())
        except Exception:
            return False
        if not math.isfinite(now) or (last is not None
                                      and now - last < origin.REATTEST_INTERVAL_S):
            return False
        self._rebound[key] = None
        try:
            result = _attest.attest_peer(**kwargs)
        except Exception:
            return False
        bound = result.binding
        if not result.ok or bound is None or (
                bound.pid, bound.creation_time, bound.core_job_at_accept) != (
                first.pid, first.creation_time, first.core_job_at_accept):
            return False
        self._rebound[key] = (first, bound, now)
        return True

    def release(self, context, evidence):
        self._rebound.pop(context.accept_generation, None)


def _remote_port(context):
    """The accepted peer's port: the only key the owner lookup may take."""
    return context.remote_endpoint[1]


def _reason(result):
    return result.failures[0] if result.failures else NO_EVIDENCE
