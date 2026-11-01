"""Socket-bound origin contract; no OS probes or credential authority.

Every backend call the server makes runs under `bounded`: a call that does not
answer within BACKEND_DEADLINE_S is a timeout, which the server reads as
undetermined origin. A call that hangs keeps one of MAX_HUNG_CALLS slots until it
really returns, so a stuck native probe cannot take more than that many threads.
"""
from dataclasses import dataclass
from enum import Enum
import ipaddress
import re
import threading
from typing import Callable, Protocol

ORIGIN_ENFORCEMENT_ENABLED = False

#: seconds one backend call may take before it counts as a timeout (undetermined)
BACKEND_DEADLINE_S = 0.5
#: calls that may be hung in the background at once; the next one fails at once
MAX_HUNG_CALLS = 16
_slots = threading.BoundedSemaphore(MAX_HUNG_CALLS)


def bounded(call, *args):
    """call(*args) in a daemon thread, or TimeoutError once the deadline passes."""
    if not _slots.acquire(blocking=False):
        raise TimeoutError('origin backend saturated')
    done, box = threading.Event(), []

    def run():
        try:
            box.append((True, call(*args)))
        except BaseException as error:
            box.append((False, error))
        finally:
            done.set()
            _slots.release()

    threading.Thread(target=run, daemon=True).start()
    if not done.wait(BACKEND_DEADLINE_S):
        raise TimeoutError('origin backend call timed out')
    ok, value = box[0]
    if not ok:
        raise value
    return value

#: seconds between two re-attestations of one long-lived connection, whatever
#: the request rate: a peer cannot make Core probe the process table faster
REATTEST_INTERVAL_S = 2.0


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
#: keeps the attestor's own default. `reattest` (T-806, off by default) lets a
#: binding older than `max_age_s` be re-attested once per request, kept only for
#: the same PID and creation time. A backend built without readers answers
#: exactly as it does today: nothing changes before the native readers exist.
@dataclass(frozen=True)
class AttestationReaders:
    resolve_owner: Callable
    read_process: Callable
    clock: Callable
    launcher: "str | None" = None
    max_age_s: "float | None" = None
    reattest: bool = False

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


def _loopback(endpoint):
    try:
        return ipaddress.ip_address(endpoint[0]) in (ipaddress.ip_address('127.0.0.1'),
                                                     ipaddress.ip_address('::1'))
    except (TypeError, ValueError, IndexError):
        return False


def direct_loopback(context):
    """Both ends of the accepted connection are the loopback address itself."""
    return _loopback(context.local_endpoint) and _loopback(context.remote_endpoint)


class CorePathRegistry:
    """Core's own list of listener ports whose direct loopback path it approves.

    Approves one thing: a USER origin on the direct local path, to a registered
    listener port, loopback to loopback. An execution or verifier origin, a tunnel,
    a hop and a deputy are never approved here; neither is anything inferred from a
    Host header, a SID or an executable name.
    """

    def __init__(self, direct_local_ports):
        ports = frozenset(direct_local_ports)
        if not all(type(p) is int and 0 < p < 65536 for p in ports):
            raise ValueError('ports must be integers in 1..65535')
        self._ports = ports

    def approved(self, context, evidence):
        return (isinstance(context, ConnectionContext) and isinstance(evidence, OriginEvidence)
                and evidence.origin == OriginClass.USER
                and evidence.path == PathClass.DIRECT_LOCAL
                and direct_loopback(context)
                and context.local_endpoint[1] in self._ports)


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
