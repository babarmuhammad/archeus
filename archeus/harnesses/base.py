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
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Mapping, Optional, Protocol, runtime_checkable

from claude_sessions import config, proc

from ..infra.paths import REQUEST_DIR, ExecPaths, archeus_home, run_dir

log = logging.getLogger('archeus.harnesses')

#: the environment every execution runs in (execution-architecture §2): it can
#: commit locally, it cannot push with the user's credentials
CAPABILITY_ENV = {'GIT_TERMINAL_PROMPT': '0', 'GIT_ASKPASS': '', 'SSH_AUTH_SOCK': None,
                  'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'credential.helper',
                  'GIT_CONFIG_VALUE_0': ''}
#: the Windows rows of an isolated environment apply where the isolation exists;
#: a test pins it to exercise them anywhere
_WINDOWS = os.name == 'nt'
_HOOK_TOKEN = re.compile(r'hook_[A-Za-z0-9_-]+')


# ── the contract's vocabulary ───────────────────────────────────────────────

@dataclass(frozen=True)
class AccountRef:
    account_id: str
    home_ref: Optional[str] = None      # harness home dir; opaque to Core


def canonical_home(home):
    """The canonical form of a home path (ADR-0048 D-25.2): absolute, and
    case-folded where the filesystem is. One real home, one key."""
    return os.path.normcase(os.path.abspath(os.path.expanduser(home)))


def default_ref(harness_id, home):
    """A harness's default account (ADR-0048 D-25.1): keyed `<harness>:<canonical
    home>`, the key policy, ledger and provenance name it by; its `home_ref`
    stays the real path, so the process runs exactly where it always did."""
    return AccountRef('%s:%s' % (harness_id, canonical_home(home)),
                      os.path.abspath(os.path.expanduser(home)))


@dataclass(frozen=True)
class HarnessInfo:
    id: str
    installed: bool
    version: Optional[str] = None
    executable: Optional[str] = None


@dataclass(frozen=True)
class ModelInfo:
    """A model an account can run, in its harness's vocabulary (domain-model
    §8.3). `tier` / `context_window` None: unknown, which the router counts as
    the smallest (ADR-0022) — a requirement's minimum excludes it."""
    id: str
    tier: Optional[str] = None          # small | mid | large
    context_window: Optional[int] = None


@dataclass(frozen=True)
class Capabilities:
    capabilities: frozenset             # code_edit, shell, web, mcp, headless, interactive, …
    enforcement: str                    # hook | sandbox | none
    models: tuple = ()                  # model ids (tier unknown) or ModelInfo
    # how a `headless` adapter asks for a schema (ADR-0022): `native` (a flag of
    # the harness) or `prompted` (the schema in the prompt). Core validates the
    # result either way, so neither is preferred and neither is required.
    structured_output: Optional[str] = None
    efforts: tuple = ()                 # the levels it accepts, in its own scale
    # why `models` is empty when the adapter could not find out what this
    # account can run (C-22): a failed discovery offers nothing, and says so
    models_note: Optional[str] = None
    # the usage measures this account's figures report as the provider's own
    # (ADR-0048 D-25.3): ⊆ {tokens, cost}; a budget on any other is refused
    usage_measures: frozenset = frozenset()


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
    # merged over the parent's environment; a None value REMOVES the variable
    # (capability removal, p11-design-gate §18)
    env: Mapping = field(default_factory=dict)
    model: Optional[str] = None
    effort: Optional[str] = None
    limits: Mapping = field(default_factory=dict)
    allowed_tools: tuple = ()
    resume_ref: Optional[str] = None
    # the hook command (an argv list, P11): how the adapter installs it is its own
    # business (Claude Code: a --settings file; the fake agent: an env variable)
    hook_settings: Optional[tuple] = None
    # P11: the process number within the execution (1: its first spawn; a resume
    # is the next) and the account it runs on
    process_seq: int = 1
    account: Optional['AccountRef'] = None
    # P20 (ADR-0049, D6): the (owner, kind, name) opt-ins of exactly this
    # execution's account and project, and the inventory recorded from them,
    # whose flags the adapter's argv reads (None: every source excluded)
    opt_ins: tuple = ()
    inventory: Optional[Mapping] = None
    # PV-20 S1 (§3.4): Core's isolated launch for this process, or None for the
    # detached one. An object and not a flag, on purpose: a flag without the launcher
    # would be a fallback, and an isolated execution has none — `spawn` below reaches
    # `proc.spawn_detached` only when this is None.
    isolation: Optional[object] = None


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
    # True: no tool at all, not even the harness's read-only set (K-O2: a call
    # whose prompt carries execution-influenced data must not be able to read
    # Core's own files). An adapter that cannot express it refuses the call.
    no_tools: bool = False


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
    # True: `usage` is the harness's own total for this process (ADR-0048 §3);
    # otherwise it is at most a lower bound
    usage_total: bool = False
    session_ref: Optional[str] = None
    transcript_path: Optional[str] = None
    files_changed: Optional[tuple] = None
    # P11 (p11-design-gate §9.1): who owns the end (resource | task | auth | limit),
    # whether the hook halted the process (a pause, an ASK, a stop flag), and the
    # adapter's opaque state for a resume (a provider session, a scripted step)
    failure: Optional[str] = None
    halted: bool = False
    adapter_state: Optional[Mapping] = None


@runtime_checkable
class HarnessAdapter(Protocol):
    id: str

    def discover(self) -> HarnessInfo: ...
    def capabilities(self, account: AccountRef) -> Capabilities: ...
    # the one account the harness offers when none is registered (ADR-0048
    # D-25.1): fixed, never elected among others — choosing is the router's
    def default_account(self) -> AccountRef: ...
    def authenticate(self, account: AccountRef) -> AuthStatus: ...
    def start(self, spec: ExecutionSpec) -> ProcessHandle: ...
    def send(self, handle: ProcessHandle, message: str) -> None: ...
    def pause(self, handle: ProcessHandle) -> PauseResult: ...
    def resume(self, spec: ExecutionSpec, state: Mapping) -> ProcessHandle: ...
    def stop(self, handle: ProcessHandle, *, grace_s: float) -> None: ...
    def inspect(self, handle: ProcessHandle, offset: int = 0) -> Snapshot: ...
    def status(self, handle: ProcessHandle) -> ProcStatus: ...
    # no handoff(): a continuation is an ordinary INTENT whose prompt carries the
    # checkpoint's rendering (p12-design-gate D19)
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


def halted_path(exec_dir):
    """`req/halted.json`: written by the hook when it halts the process (P11). It is
    in the execution's own class-1 directory because the execution writes it, so it
    is the execution's claim (PV-20 §7.5; what Core makes of it is S7's, H2)."""
    return os.path.join(exec_dir, REQUEST_DIR, 'halted.json')


def spawn(spec, argv):
    """Start *argv* for *spec* under the process I/O contract.

    Returns `(ProcessHandle, Popen)`. The Popen is for the caller that started
    the process (its exit code); everything durable is in the handle and the
    files. The child's environment carries `ARCHEUS_EXECUTION_ID` (which makes
    the legacy account hooks stand down — the P0.5 guard) and `ARCHEUS_HOME`.

    Process 1 of an execution needs no marker yet (a marker means a process may
    exist). Process k > 1 (a resume, P11) needs the marker of process k - 1 AND
    its `ended` tombstone — proof the last one is gone — and replaces both, so
    one execution never has two processes at once. The stream is appended to.
    """
    paths = ExecPaths(spec.execution_id)
    seq = spec.process_seq
    if seq <= 1:
        if os.path.exists(paths.spawning):
            raise AlreadySpawned(spec.execution_id)
    else:
        last = read_json(paths.spawning) or {}
        if last.get('process_seq', 1) != seq - 1 or not os.path.exists(paths.ended):
            raise AlreadySpawned('%s: process %d may still be running'
                                 % (spec.execution_id, seq - 1))
    # Core creates every class directory (PV-20 §7.5): the execution is never the
    # one to make a directory inside its own Core-owned one
    for d in (paths.dir, paths.req, paths.res, paths.ctl):
        os.makedirs(d, exist_ok=True)
    _write_json(paths.spawning, {'execution_id': spec.execution_id, 'attempt': spec.attempt,
                                 'process_seq': seq, 'at': time.time()})
    for stale in (paths.ended, halted_path(paths.dir)):
        try:
            os.remove(stale)
        except FileNotFoundError:
            pass
        except OSError as err:
            # a halt report left over from the last process would be read as this
            # one's: nothing starts
            _refuse(paths, 'could not remove %s: %s' % (os.path.basename(stale), err), err)
    if not config.write_atomic(paths.prompt, spec.prompt):
        raise OSError('could not write %s' % paths.prompt)
    if spec.isolation is not None:
        # PV-20 §3.4/§6.3: the isolated path, or nothing. It never falls through to
        # `spawn_detached` below — an unisolated child would run in the interactive
        # user's own security context, the failure mode this path exists to prevent —
        # and its failure is SpawnFailed with the reason recorded (§3.4, O7).
        try:
            _private_dirs(paths, seq)
        except OSError as err:
            _refuse(paths, str(err), err)
        try:
            env = _isolated_env(spec, paths)
        except ValueError as err:
            _refuse(paths, str(err), err)
        child, err = spec.isolation.launch(list(argv), cwd=spec.workdir, env=env,
                                           paths=paths)
    else:
        env = dict(os.environ)
        for k, v in spec.env.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
        env['ARCHEUS_EXECUTION_ID'] = spec.execution_id
        env['ARCHEUS_HOME'] = archeus_home()
        # a hidden console, not none: the agent runs its hooks and tools as console
        # programs, and each would otherwise open a visible window of its own
        child, err = proc.spawn_detached(list(argv), cwd=spec.workdir, env=env,
                                         log=paths.stream, stdin_path=paths.prompt,
                                         hidden_console=True)
    if child is None:
        # we KNOW nothing started, so say so: a marker without `ended` would
        # otherwise read as "a process may exist" to reconciliation
        _refuse(paths, err, None)
    create_time = proc.process_create_time(child.pid)
    _write_json(paths.pid, {'pid': child.pid, 'create_time': create_time, 'process_seq': seq})
    return ProcessHandle(spec.execution_id, child.pid, create_time, paths.dir), child


def _refuse(paths, error, cause):
    # the tombstone says why nothing started if it can be written; one that cannot
    # is added to the reason, never a reason to start anyway or to leave the
    # SpawnFailed route callers handle
    try:
        mark_ended(paths, None, error=error)
    except OSError as tomb:
        error = '%s; the ended tombstone was not written: %s' % (error, tomb)
    raise SpawnFailed(error) from cause


def _private_dirs(paths, seq):
    # a resume continues the session its first process left in this config dir, so
    # it must find the dir as it was: never re-created empty, never the account home
    if seq > 1 and not os.path.isdir(paths.config):
        raise OSError('the private config of %s is gone: a resume cannot start without it'
                      % paths.execution_id)
    for d in (paths.config, paths.tmp) + _profile(paths.home)[1:]:
        os.makedirs(d, exist_ok=True)


def _profile(home):
    """(home, roaming, local): an isolated execution's own profile, never the account's."""
    return (home, os.path.join(home, 'AppData', 'Roaming'),
            os.path.join(home, 'AppData', 'Local'))


def _inside(path, roots):
    a = os.path.normcase(os.path.realpath(path))
    for root in roots:
        b = os.path.normcase(os.path.realpath(root))
        if a == b or a.startswith(b.rstrip(os.sep) + os.sep):
            return True
    return False


def _absolute(entry):
    # on Windows an absolute entry with a drive letter: never relative, drive-relative,
    # rooted without a drive, or UNC
    drive = os.path.splitdrive(entry)[0]
    return os.path.isabs(entry) and (os.name != 'nt' or (len(drive) == 2 and drive[1] == ':'))


def _windows_rows(banned):
    """The Windows rows of a built-from-nothing environment: SystemRoot and what is
    derived from it, never from a directory in *banned*."""
    root = os.environ.get('SystemRoot')
    if not (root and os.path.isabs(root) and os.path.isdir(root)) or _inside(root, banned):
        raise ValueError('SystemRoot is not a usable Windows directory')
    comspec = os.path.join(root, 'System32', 'cmd.exe')
    if not os.path.isfile(comspec):
        raise ValueError('ComSpec, derived from SystemRoot, does not exist')
    return {'SystemRoot': root, 'windir': root, 'SystemDrive': os.path.splitdrive(root)[0],
            'ComSpec': comspec}


def _verifier_env(toolchain_dirs, scratch):
    """A confined verifier's whole environment, built from nothing (T-054 A6-2): its
    scratch is its profile and temp, PATH is the Core-staged toolchain and nothing
    else, and no caller adds a name - no Archeus, hook, broker, provider, Git or proxy
    variable can reach it. Raises ValueError naming what is wrong, never a value."""
    if not (_absolute(scratch) and os.path.isdir(scratch)):
        raise ValueError('scratch is not an absolute directory')
    dirs = list(toolchain_dirs)
    if not dirs:
        raise ValueError('a verifier runs only a Core-staged toolchain, and none was given')
    for d in dirs:
        if not (_absolute(d) and os.path.isdir(d)) or _inside(d, [scratch]):
            raise ValueError('a toolchain entry is not a staged directory outside scratch')
    home, roaming, local = _profile(scratch)
    tmp = os.path.join(scratch, 'tmp')
    out = {'TEMP': tmp, 'TMP': tmp, 'USERPROFILE': home, 'HOME': home, 'APPDATA': roaming,
           'LOCALAPPDATA': local, 'HOMEDRIVE': os.path.splitdrive(home)[0],
           'HOMEPATH': os.path.splitdrive(home)[1], 'PATH': os.pathsep.join(dirs)}
    if _WINDOWS:
        banned = [os.path.expanduser('~'), archeus_home(), scratch,
                  os.environ.get('TEMP'), os.environ.get('TMP')]
        out.update(_windows_rows([b for b in banned if b]))
    return out


def _isolated_env(spec, paths):
    """An isolated execution's whole environment, built from nothing (ADR-0053 A2; T-031
    Correction C-1012-T031): these names, each from its one authority, and no other.
    `spec.env` is a request: a name Core puts there is accepted only as the value Core
    derives itself, any other refuses. Raises ValueError naming a variable, never a value.

    PATH is an interim narrowing of Core's own, unverified: an entry kept is not shown
    to be unwritable by the execution, and no variable confines where DLLs or modules
    are searched for (that is the staged runtime's, T-017 C4)."""
    acct = spec.account.home_ref if spec.account else None
    banned = [os.path.expanduser(acct)] if acct else []
    banned += [os.path.expanduser('~'), archeus_home(), spec.workdir,
               os.environ.get('TEMP'), os.environ.get('TMP')]
    banned = [b for b in banned if b]
    home, roaming, local = _profile(paths.home)
    out = {'TEMP': paths.tmp, 'TMP': paths.tmp, 'CLAUDE_CONFIG_DIR': paths.config,
           'USERPROFILE': home, 'HOME': home, 'APPDATA': roaming, 'LOCALAPPDATA': local,
           'HOMEDRIVE': os.path.splitdrive(home)[0], 'HOMEPATH': os.path.splitdrive(home)[1],
           'ARCHEUS_EXECUTION_ID': spec.execution_id, 'ARCHEUS_HOME': archeus_home(),
           'GIT_CONFIG_NOSYSTEM': '1'}
    out.update((k, v) for k, v in CAPABILITY_ENV.items() if v is not None)
    if _WINDOWS:
        out.update(_windows_rows(banned))
    kept, seen = [], set()
    for entry in (os.environ.get('PATH') or '').split(os.pathsep):
        if not (entry and _absolute(entry) and os.path.isdir(entry)) or _inside(entry, banned):
            continue
        key = os.path.normcase(os.path.realpath(entry))
        if key not in seen:
            seen.add(key)
            kept.append(entry)
    out['PATH'] = os.pathsep.join(kept)
    derived = dict(out)
    if spec.hook_settings:
        derived['ARCHEUS_HOOK_CMD'] = json.dumps(list(spec.hook_settings))
    canon = {k.upper(): k for k in list(derived) + ['ARCHEUS_HOOK_TOKEN']}
    named = {}
    for k, v in spec.env.items():
        if k.upper() in named:
            raise ValueError('spec.env names %s and %s, one variable' % (named[k.upper()], k))
        named[k.upper()] = k
        if v is None:
            continue                       # a removal: absent by construction already
        name = canon.get(k.upper())
        if name is None:
            raise ValueError('%s is not a variable an isolated execution may be given' % k)
        if name == 'ARCHEUS_HOOK_TOKEN':
            if not _HOOK_TOKEN.fullmatch(v):
                raise ValueError('ARCHEUS_HOOK_TOKEN is not a hook token')
        elif name == 'CLAUDE_CONFIG_DIR':
            same = {os.path.normcase(os.path.realpath(x)) for x in (v, paths.config)}
            if len(same) != 1:
                raise ValueError('CLAUDE_CONFIG_DIR is not the private config')
            continue
        elif v != derived[name]:
            raise ValueError('%s is not the value Core derives for it' % name)
        out[name] = v
    return out


def mark_ended(paths, exit_code, **extra):
    """Write the `ended` tombstone (Core, when it observes the exit). Every end of a
    process passes here, so this is where its MCP config goes (T-099)."""
    _write_json(paths.ended, dict({'exit_code': exit_code, 'at': time.time()}, **extra))
    drop_mcp_config(paths)


def drop_mcp_config(paths):
    """Remove *paths*' MCP config: it holds the opted-in servers' keys. A failure is
    logged, never raised: the end it belongs to must still be recorded, and the boot
    sweep tries again."""
    try:
        os.remove(paths.mcp)
    except FileNotFoundError:
        pass
    except OSError as err:
        log.warning('execution %s: its MCP config was not removed: %s',
                    paths.execution_id, err)


def sweep_mcp_configs(keep):
    """At boot, the MCP config of every execution whose process this Core is not
    watching (*keep*): a Core that died while one ran never saw that end."""
    root = os.path.join(run_dir(), 'exec')
    try:
        names = os.listdir(root)
    except FileNotFoundError:
        return
    for name in names:
        if name in keep:
            continue
        try:
            paths = ExecPaths(name)
        except ValueError:
            continue                    # not an execution's directory
        drop_mcp_config(paths)


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
