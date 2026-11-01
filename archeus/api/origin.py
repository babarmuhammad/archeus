"""Socket-bound origin contract; no OS probes or credential authority.

ACTIVATION BLOCKER (PV20-11, before ORIGIN_ENFORCEMENT_ENABLED goes on): nothing
bounds backend attest, valid or release in time. A hung call holds a request
slot (32 slots, then 503 busy) and a stream thread, and never reaches the
undetermined answer. Each native call must have a deadline that maps to
undetermined, or the server must impose one. Recorded by the xfail test
test_backend_calls_are_time_bounded (tests/v1/integration/test_api_origin_transport.py).
"""
from dataclasses import dataclass
from enum import Enum
import re
from typing import Callable, Protocol

ORIGIN_ENFORCEMENT_ENABLED = False


class OriginClass(str, Enum):
    USER = 'user'
    EXECUTION = 'execution'
    VERIFIER = 'verifier'
    UNDETERMINED = 'undetermined'


class PathClass(str, Enum):
    DIRECT_LOCAL = 'direct_local'
    REGISTERED_TUNNEL = 'registered_tunnel'
    HOP = 'hop'
    DEPUTY = 'deputy'
    UNAPPROVED = 'unapproved'


@dataclass(frozen=True)
class ConnectionContext:
    socket: object
    local_endpoint: tuple
    remote_endpoint: tuple
    accept_generation: str


@dataclass(frozen=True)
class OriginEvidence:
    origin: OriginClass = OriginClass.UNDETERMINED
    path: PathClass = PathClass.UNAPPROVED
    identity: str | None = None
    process_binding: object | None = None
    accept_generation: str = ''
    reason: str = 'unavailable'


#: The attestor's outside facts, all injected (T-456). Core owns no probe: the
#: caller supplies the port -> owner and PID -> process observations and the
#: clock the attestor runs on, so the accept-time binding and the per-request
#: re-check are decided by the pure attestor against a fake table in a test and
#: against the native tables on Windows. `launcher` or `max_age_s` left as None
#: keeps the attestor's own default. A backend built without readers answers
#: exactly as it does today: nothing changes before the native readers exist.
@dataclass(frozen=True)
class AttestationReaders:
    resolve_owner: Callable
    read_process: Callable
    clock: Callable
    launcher: "str | None" = None
    max_age_s: "float | None" = None

    def attest_kwargs(self, remote_port):
        """The keyword arguments of one accept-time attestation of *remote_port*."""
        kwargs = {'remote_port': remote_port, 'resolve_owner': self.resolve_owner,
                  'read_process': self.read_process, 'clock': self.clock}
        if self.launcher is not None:
            kwargs['launcher'] = self.launcher
        return kwargs

    def recheck_kwargs(self):
        """The keyword arguments of one re-check of an accept-time binding."""
        kwargs = {'read_process': self.read_process, 'clock': self.clock}
        if self.launcher is not None:
            kwargs['launcher'] = self.launcher
        if self.max_age_s is not None:
            kwargs['max_age_s'] = self.max_age_s
        return kwargs


class OriginBackend(Protocol):
    """Retain identity until release; validate every request, with bounded calls.

    Paths require Core registry approval, deputy checks and tunnel origin
    distinction. A user SID or PID alone never establishes an approved path.
    Timeout, ambiguity and races must return undetermined evidence.
    """

    def attest(self, context: ConnectionContext) -> OriginEvidence: ...
    def valid(self, context: ConnectionContext, evidence: OriginEvidence) -> bool: ...
    def release(self, context: ConnectionContext, evidence: object) -> None: ...


class OriginRegistry(Protocol):
    """Core-owned process/path approval, independent of OS observation.

    Approve direct paths only with deputy closures; approve tunnels only when
    registered transport preserves execution/verifier origin distinction.
    Never infer approval from Host, forwarding headers, SID or executable name.
    """

    def approved(self, context: ConnectionContext, evidence: OriginEvidence) -> bool: ...


class UnapprovedRegistry:
    def approved(self, context, evidence):
        return False


def validate_evidence(context, evidence):
    return (isinstance(context, ConnectionContext)
            and isinstance(evidence, OriginEvidence)
            and isinstance(evidence.origin, OriginClass)
            and isinstance(evidence.path, PathClass)
            and evidence.accept_generation == context.accept_generation
            and bool(context.accept_generation)
            and evidence.process_binding is not None
            and (evidence.identity is None or
                 isinstance(evidence.identity, str) and 0 < len(evidence.identity) <= 128)
            and isinstance(evidence.reason, str)
            and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', evidence.reason) is not None
            and (evidence.origin not in (OriginClass.EXECUTION, OriginClass.VERIFIER)
                 or evidence.identity is not None))


def authorize_transport(evidence, *, local_host, remote_host, credential_origin=None,
                        tunnel_route=True):
    """Transport gate, then credential branch check. Hosts are Core-configured.

    None credential selects the pre-credential stage, including bootstrap.
    Only the local device credential works on the direct local path; a paired
    one is refused there (owner, 2026-10-21). tunnel_route False keeps a route
    off the tunnel. Forwarding headers never establish a path or a host.
    """
    if not isinstance(evidence, OriginEvidence) or evidence.origin != OriginClass.USER:
        return False
    if not isinstance(evidence.origin, OriginClass) or not isinstance(evidence.path, PathClass):
        return False
    if evidence.path == PathClass.DIRECT_LOCAL:
        return bool(local_host) and credential_origin in (None, 'local')
    if evidence.path == PathClass.REGISTERED_TUNNEL:
        return bool(remote_host and tunnel_route and credential_origin in (None, 'paired'))
    return False
