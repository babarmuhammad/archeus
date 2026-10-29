"""Native backend interface stub. No socket-owner, PID, token or SID probes.

Activation requires separately evidenced native binding and Core-owned path
registry. This shipped backend cannot authorize any connection.
"""
from ..api.origin import OriginEvidence


class WindowsOriginBackend:
    def attest(self, context):
        return OriginEvidence(accept_generation=context.accept_generation)

    def valid(self, context, evidence):
        return False

    def release(self, context, evidence):
        pass
