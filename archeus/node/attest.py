"""Pure origin attestor: bind a peer port to a process instance (PV-20 F9, T-231).

No archeus imports and no OS, socket, ctypes or filesystem calls: every outside
fact arrives through an injected callable, so the whole decision runs against a
fake process table. Contract (PV20-08, F9): bind PID plus process creation time
at accept; a PID that is not alive, or a creation time that differs from the
bound one, fails closed; attest at accept, never after the response. Any
exception, timeout, malformed answer or ambiguous owner is "no evidence": a
non-empty failures tuple and no binding, never a partial pass. Reason codes
are stable lowercase and carry no secrets or paths.
"""

import math
from typing import Callable, NamedTuple


class PeerOwner(NamedTuple):
    pid: "int | None"


class ProcessInfo(NamedTuple):
    # 'alive' must not be derived from OpenProcess success or IsProcessInJob:
    # F9C observed both report TRUE for an already-dead PID. The reader must
    # supply a real liveness signal; creation_time None means unreadable.
    alive: bool
    creation_time: "int | float | None"
    ancestors: "tuple[str, ...]"
    in_core_job: bool


class ProcessBinding(NamedTuple):
    remote_port: int
    pid: int
    creation_time: "int | float"
    accepted_at: float
    core_job_at_accept: bool


class AttestResult(NamedTuple):
    ok: bool
    binding: "ProcessBinding | None"
    failures: "tuple[str, ...]"


NO_OWNER = 'no_owner'
MALFORMED_OWNER = 'malformed_owner'
READER_ERROR = 'reader_error'
MALFORMED = 'malformed'
DEAD = 'dead'
CREATION_TIME_UNREADABLE = 'creation_time_unreadable'
CREATION_TIME_MISMATCH = 'creation_time_mismatch'   # PID-recycle signature
LAUNCHER_UNPROVEN = 'launcher_unproven'
OUTSIDE_CORE_JOB = 'outside_core_job'
EXPIRED = 'expired'
NO_BINDING = 'no_binding'

# Deliberately small: F9C saw the TCP table keep naming a dead owner for at
# least 1.5 s, so a stale accept-time answer must not stay trusted for long.
# Integration pins the real value in Core configuration, never execution-side.
DEFAULT_MAX_AGE_S = 2.0
DEFAULT_LAUNCHER = 'wxc-exec'


def attest_owner(
    *,
    remote_port: int,
    resolve_owner: "Callable[[int], PeerOwner]",
    read_process: "Callable[[int], ProcessInfo]",
    clock: "Callable[[], float]",
    launcher: str = DEFAULT_LAUNCHER,
) -> AttestResult:
    """Map the peer port to a process instance and attest it, or fail closed.

    Called by the server exactly once, at accept, before request handling.
    All OS facts arrive through the injected readers and clock; a binding is
    issued only when every check passes, never a partial pass.
    """
    try:
        owner = resolve_owner(remote_port)
    except Exception:
        return AttestResult(False, None, (READER_ERROR,))
    if not isinstance(owner, PeerOwner):
        return AttestResult(False, None, (MALFORMED_OWNER,))
    if owner.pid is None:
        return AttestResult(False, None, (NO_OWNER,))
    pid = owner.pid
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return AttestResult(False, None, (MALFORMED_OWNER,))

    try:
        info = read_process(pid)
    except Exception:
        return AttestResult(False, None, (READER_ERROR,))
    if not isinstance(info, ProcessInfo):
        return AttestResult(False, None, (MALFORMED,))

    failures: list[str] = []
    if info.alive is not True:
        failures.append(DEAD)
    if info.creation_time is None or not _finite(info.creation_time):
        failures.append(CREATION_TIME_UNREADABLE)
    reason = _launcher_missing(info.ancestors, launcher)
    if reason is not None:
        failures.append(reason)
    if info.in_core_job is not True:
        failures.append(OUTSIDE_CORE_JOB)
    if failures:
        return AttestResult(False, None, tuple(failures))

    binding = ProcessBinding(
        remote_port=remote_port,
        pid=pid,
        creation_time=info.creation_time,
        accepted_at=float(clock()),
        core_job_at_accept=True,
    )
    return AttestResult(True, binding, ())


def binding_valid(
    binding: "ProcessBinding | None",
    *,
    read_process: "Callable[[int], ProcessInfo]",
    clock: "Callable[[], float]",
    max_age_s: float = DEFAULT_MAX_AGE_S,
    launcher: str = DEFAULT_LAUNCHER,
) -> AttestResult:
    """Re-validate an accept-time binding against the current process table.

    Per request, before any privileged effect: the bound PID may have died,
    been recycled to a new instance (creation_time differs) or lost the
    launcher ancestry / Core-Job membership. A missing or expired binding
    fails closed without consulting any reader.
    """
    if not isinstance(binding, ProcessBinding):
        return AttestResult(False, None, (NO_BINDING,))
    try:
        now = float(clock())
    except Exception:
        return AttestResult(False, None, (READER_ERROR,))
    if not _finite(now) or now - binding.accepted_at > max_age_s:
        return AttestResult(False, None, (EXPIRED,))

    try:
        info = read_process(binding.pid)
    except Exception:
        return AttestResult(False, None, (READER_ERROR,))
    if not isinstance(info, ProcessInfo):
        return AttestResult(False, None, (MALFORMED,))

    failures: list[str] = []
    if info.alive is not True:
        failures.append(DEAD)
    if info.creation_time is None or not _finite(info.creation_time):
        failures.append(CREATION_TIME_UNREADABLE)
    elif info.creation_time != binding.creation_time:
        failures.append(CREATION_TIME_MISMATCH)
    reason = _launcher_missing(info.ancestors, launcher)
    if reason is not None:
        failures.append(reason)
    if info.in_core_job is not True:
        failures.append(OUTSIDE_CORE_JOB)
    if failures:
        return AttestResult(False, None, tuple(failures))
    return AttestResult(True, binding, ())


def _launcher_missing(ancestors: object, launcher: str) -> "str | None":
    if not isinstance(ancestors, tuple) or not all(isinstance(a, str) for a in ancestors):
        return MALFORMED
    if launcher.lower() not in tuple(a.lower() for a in ancestors):
        return LAUNCHER_UNPROVEN
    return None


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
