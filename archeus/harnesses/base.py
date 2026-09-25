"""The harness adapter contract, frozen in P1 (execution-architecture §3, §3.1).

Two halves:

1. `HarnessAdapter` — the Protocol every adapter (fake now; claude_code and
   codex in P11) implements, and the dataclasses it speaks in.
2. The **process I/O contract**, shared by every adapter so none can get it
   subtly different: before a process exists the spawning marker is written;
   the prompt is a file the process reads as stdin; stdout and stderr go to
   `stream.jsonl` (never a pipe, so a restarted Core can re-attach and tail it
   from the last offset); `{pid, create_time}` is recorded the moment the
   process exists; `ended` is the tombstone.

The spawn rule is idempotent under outbox re-delivery: an execution whose
spawning marker exists is NEVER spawned again — a retry is a new execution id
(a new attempt), and a marker without `ended` belongs to reconciliation.
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Mapping, Optional, Protocol, runtime_checkable

from claude_sessions import config, proc

from ..infra.paths import ExecPaths, archeus_home


# ── the contract's vocabulary ───────────────────────────────────────────────

@dataclass(frozen=True)
class AccountRef:
    account_id: str
    home_ref: Optional[str] = None      # harness home dir; opaque to Core


@dataclass(frozen=True)
class HarnessInfo:
    id: str
    installed: bool
    version: Optional[str] = None
    executable: Optional[str] = None


@dataclass(frozen=True)
class Capabilities:
    capabilities: frozenset             # code_edit, shell, web, mcp, headless, interactive, …
    enforcement: str                    # hook | sandbox | none
    models: tuple = ()
    # how a `headless` adapter asks for a schema (ADR-0022): `native` (a flag of
    # the harness) or `prompted` (the schema in the prompt). Core validates the
    # result either way, so neither is preferred and neither is required.
    structured_output: Optional[str] = None
    efforts: tuple = ()                 # the levels it accepts, in its own scale


@dataclass(frozen=True)
class AuthStatus:
    ok: bool
    detail: str = ''


@dataclass(frozen=True)
class ExecutionSpec:
    """What Core hands an adapter to start one execution (execution-architecture §3)."""
    execution_id: str
    prompt: str                         # stable prefix + variable suffix
    workdir: str
    attempt: int = 1
    task_contract: Mapping = field(default_factory=dict)
    env: Mapping = field(default_factory=dict)
    model: Optional[str] = None
    effort: Optional[str] = None
    limits: Mapping = field(default_factory=dict)
    allowed_tools: tuple = ()
    resume_ref: Optional[str] = None
    hook_settings: Optional[str] = None


@dataclass(frozen=True)
class CallSpec:
    """One of Archeus's own calls (execution-architecture §3, ADR-0022): tool-less,
    read-only and ephemeral. `model` is in the target harness's vocabulary or
    None (its own default); `schema` is what Core will validate the result
    against, and the adapter decides how to ask for it."""
    route_decision_id: str
    purpose: str
    prompt: str                         # stable prefix + variable suffix
    workdir: str
    account: AccountRef
    schema: Optional[Mapping] = None
    model: Optional[str] = None
    limits: Mapping = field(default_factory=dict)       # timeout_s


@dataclass(frozen=True)
class CallResult:
    """What one call produced. `error` is None on success, else one of
    `unavailable` (no binary), `model_unavailable`, `timeout`, `failed`; the
    reason is in `detail`. `parsed` is the adapter's reading of the answer and
    is not trusted: Core validates it."""
    text: str = ''
    parsed: object = None
    usage: Mapping = field(default_factory=dict)
    error: Optional[str] = None
    detail: str = ''


CALL_ERRORS = ('unavailable', 'model_unavailable', 'timeout', 'failed')


def prompted(prompt, schema):
    """The prompt a `prompted` adapter sends: the task, then the shape in words
    (the wording the current product uses for pi, main 94b90f9)."""
    return (prompt + '\n\nAnswer with ONLY one JSON object, no prose and no code fence, '
            'matching this JSON Schema:\n' + json.dumps(schema, sort_keys=True))


@dataclass(frozen=True)
class ProcessHandle:
    """Serialisable: everything needed to find the process again after a restart."""
    execution_id: str
    pid: int
    create_time: object                 # opaque; compare only (proc.process_create_time)
    exec_dir: str


@dataclass(frozen=True)
class ProcStatus:
    state: str                          # running | exited
    exit_code: Optional[int] = None


@dataclass(frozen=True)
class Snapshot:
    events: tuple                       # normalised stream events read so far
    offset: int                         # byte offset to resume tailing from


@dataclass(frozen=True)
class PauseResult:
    halted: bool
    provider_ref: Optional[str] = None


@dataclass(frozen=True)
class ExecutionResult:
    """The reported summary is NEVER the completion signal — verification is."""
    exit_reason: str                    # ok | error | killed
    exit_code: Optional[int] = None
    reported_summary: str = ''
    usage: Mapping = field(default_factory=dict)
    session_ref: Optional[str] = None
    transcript_path: Optional[str] = None
    files_changed: Optional[tuple] = None


@runtime_checkable
class HarnessAdapter(Protocol):
    id: str

    def discover(self) -> HarnessInfo: ...
    def capabilities(self, account: AccountRef) -> Capabilities: ...
    def authenticate(self, account: AccountRef) -> AuthStatus: ...
    def start(self, spec: ExecutionSpec) -> ProcessHandle: ...
    def send(self, handle: ProcessHandle, message: str) -> None: ...
    def pause(self, handle: ProcessHandle) -> PauseResult: ...
    def resume(self, spec: ExecutionSpec, state: Mapping) -> ProcessHandle: ...
    def stop(self, handle: ProcessHandle, *, grace_s: float) -> None: ...
    def inspect(self, handle: ProcessHandle) -> Snapshot: ...
    def status(self, handle: ProcessHandle) -> ProcStatus: ...
    def handoff(self, checkpoint) -> ExecutionSpec: ...
    def collect_result(self, handle: ProcessHandle) -> ExecutionResult: ...


# ── the process I/O contract ────────────────────────────────────────────────

class AlreadySpawned(RuntimeError):
    """The spawning marker exists: this execution may already have a process.
    It goes to reconciliation, never to a second spawn."""


class SpawnFailed(RuntimeError):
    """No process was created (the `ended` tombstone records why)."""


class StopRefused(RuntimeError):
    """The recorded pid is alive but is not the process we started (PID reuse)."""


def _write_json(path, obj):
    # through the module attribute, not an import-by-value copy: the test
    # suite's sandbox guard wraps config.write_atomic, and a copy would bypass it
    if not config.write_json_atomic(path, obj, indent=None):
        raise OSError('could not write %s' % path)


def read_json(path):
    """A contract file's contents, or None when it does not exist."""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def spawn(spec, argv):
    """Start *argv* for *spec* under the process I/O contract.

    Returns `(ProcessHandle, Popen)`. The Popen is for the caller that started
    the process (its exit code); everything durable is in the handle and the
    files. The child's environment carries `ARCHEUS_EXECUTION_ID` (which makes
    the legacy account hooks stand down — the P0.5 guard) and `ARCHEUS_HOME`.
    """
    paths = ExecPaths(spec.execution_id)
    if os.path.exists(paths.spawning):
        raise AlreadySpawned(spec.execution_id)
    os.makedirs(paths.dir, exist_ok=True)
    _write_json(paths.spawning, {'execution_id': spec.execution_id,
                                 'attempt': spec.attempt, 'at': time.time()})
    if not config.write_atomic(paths.prompt, spec.prompt):
        raise OSError('could not write %s' % paths.prompt)
    env = dict(os.environ)
    env.update(spec.env)
    env['ARCHEUS_EXECUTION_ID'] = spec.execution_id
    env['ARCHEUS_HOME'] = archeus_home()
    child, err = proc.spawn_detached(list(argv), cwd=spec.workdir, env=env,
                                     log=paths.stream, stdin_path=paths.prompt)
    if child is None:
        # we KNOW nothing started, so say so: a marker without `ended` would
        # otherwise read as "a process may exist" to reconciliation
        mark_ended(paths, None, error=err)
        raise SpawnFailed(err)
    create_time = proc.process_create_time(child.pid)
    _write_json(paths.pid, {'pid': child.pid, 'create_time': create_time})
    return ProcessHandle(spec.execution_id, child.pid, create_time, paths.dir), child


def mark_ended(paths, exit_code, **extra):
    """Write the `ended` tombstone (Core, when it observes the exit)."""
    _write_json(paths.ended, dict({'exit_code': exit_code, 'at': time.time()}, **extra))


def read_stream(path, offset=0):
    """Complete JSONL events from byte *offset* onward -> (events, new_offset).

    A trailing partial line is left for the next read. stderr shares the file,
    so a line that is not a JSON object is kept as `{"type": "stderr", "text"}`
    rather than dropped — a traceback is exactly what a crash leaves behind.
    """
    try:
        with open(path, 'rb') as f:
            f.seek(offset)
            data = f.read()
    except FileNotFoundError:
        return [], offset
    end = data.rfind(b'\n') + 1
    events = []
    for raw in data[:end].splitlines():
        line = raw.decode('utf-8', errors='replace').strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            ev = None
        events.append(ev if isinstance(ev, dict) else {'type': 'stderr', 'text': line})
    return events, offset + end
