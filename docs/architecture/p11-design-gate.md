# P11 design gate: the execution orchestrator

Status: **FROZEN (P11), implemented; as built in §28.** Written 2026-09-26 on the P10 baseline
(`2101e07`), **before any P11 code**; the as-built record and its deviations are §28. Items are
marked as in the earlier gates:

- **[spec]** already specified by the V1 architecture (plan, domain model, state machines, ADRs);
- **[clar]** a clarification of an existing contract the documents leave open, or that the code has
  already settled differently;
- **[new]** a new contract decision.

Every [new] item and every change to a frozen P1–P10 contract is a numbered decision (§25); the
conflicts with frozen documents are listed on their own (§4) with their resolution.

Sources read, in precedence order: the plan (§14, §15, §31.1 **P3.5, P9, P10, P11, P12, P13,
P20**, §31.4), **ADR-0004, ADR-0007, ADR-0008, ADR-0019, ADR-0021, ADR-0022, ADR-0023**,
execution-architecture **§1–§10**, state-machines **§2, §3, §4, §5, §9, §13**, domain-model
**§7.3–§7.6, §8, §9**, api-and-realtime **§2, §5.3**, target-architecture **§3, §5.1**,
testing-strategy **§2 (S1, S4, S5, G1, G5, G6, G7), §6 (R1, H1)**, the P3.5b gate (**§3, §5.4,
§18.1, D2, D6, D8, A13, A17, A36**), the P9 gate (**§6, §7, §13, §14, §29.3**) and the P10 gate
(**§21**); the code: `archeus/core/{engine,runtime,calls,ports}.py`,
`core/application/{work,authorization,resources,commands}.py`, `core/policy/{rules,engine}.py`,
`core/domain/{states,entities,actions,ids}.py`, `harnesses/{base,fake,fake_agent,registry,calls}.py`,
`infra/paths.py`, the P0.5 seams in `claude_sessions/{proc,llmcall,config,quota,worktrees}.py`
and the legacy hooks' `ARCHEUS_EXECUTION_ID` guard (`recall_hook`, `worklog_hook`,
`memdirty_hook`, `limit_hook`), the judge (`client.py`, `http.py`, `support.py`, G1, G5, G6, S5)
and `tests/v1/contract/test_adapter_contract.py`. Where a document and the code disagree, the code
says what exists.

---

## 1. What P11 is

P8 decides what should happen, P9 whether it may, P10 where; **P11 makes it happen and records
what happened**. It turns a dispatched task — an Execution committed in INTENT with its P9
authorisation and its P10 RouteDecision — into a real process on the chosen harness and account,
supervises it until it ends, keeps every concrete action inside its authorisation, and leaves the
evidence P13 verifies. **A process that exits 0 is evidence, never success**: the task goes to
VERIFYING, and only P13 decides whether the work is right [spec, state-machines §4].

## 2. Scope and non-goals

**P11 owns:** the execution lifecycle and the Execution record; spawning, supervising, adopting and
reconciling processes; the process registry; harness adapter invocation (the fake harness and the
real Claude Code adapter); the execution hook and its channel; action-stage canonicalisation
(class, target, argv, paths, branch, host, environment, `unclassified`) and the concrete boundary
checks (working directory, branch, host); pause, resume, stop and the e-stop with Core running;
runtime usage observation, the runtime ceiling, provider limit errors and the account error
breaker; live output capture, tailing and `execution.progress`; restart recovery; parallel
dispatch; worktrees; the execution routes and the `pause` / `estop` CLI verbs.

**P11 does not:** evaluate policy or add rules (it calls P9's `evaluate_action` /
`check_dispatch`); choose a resource (it calls P10's router when it needs a decision); plan or
replan; verify or review; hand a session off or derive checkpoints (P12); merge back into a branch
(the Integration machine runs after verification, P13); automate (P14); pair or step up (P15);
render approvals or output (P16, including the `/v1/executions/{id}/stream` route, frozen to P16
by P3.5b D8); run on a remote node (deferred); or stop processes with Core down (P20).

## 3. What exists, and what is reused

| Existing | Where | Reused as |
|---|---|---|
| process I/O contract: spawning marker, `prompt.txt` as stdin, `stream.jsonl`, `pid.json`, `ended` | `harnesses/base.py`, `infra/paths.ExecPaths` [spec, P1] | unchanged; P11 adds the registry append and the hook mailbox beside it |
| `proc.spawn_detached(stdin_path=)`, `process_create_time` (Windows `GetProcessTimes`, macOS libproc µs, `/proc` starttime), `kill_pid_tree(pid, create_time)`, `pid_alive` | P0.5 seams | the only spawn and kill primitives; nothing else calls `Popen` for an execution |
| `ARCHEUS_EXECUTION_ID` guard in the legacy account hooks | P0.5 | unchanged: every execution process carries it, so recall/worklog/memdirty stand down and `limit_hook` does not offer rotation |
| `Engine._start` / `_finish` / `_reconcile`, `reconcile_orphans` | P3.5 | moved into the execution manager (§6); the kill-and-retry branch stays, the adopt branch is added |
| `Work.dispatch_task` (P9 check, P10 route, INTENT in one transaction), `record_spawn`, `record_exit`, `reconcile` | P3.5, P9, P10 | unchanged entry; `record_exit` gains the usage and failure classification of §12 |
| `authorization.evaluate_action` (records the decision, single-use action approvals, ASK → approval) | P9 | the one action-stage judge; P11 only feeds it canonical actions |
| `authorization.check_dispatch`, `resources.ResourceRouter`, `resources.terms_permit` | P9, P10 | re-used on resume (§14) — never re-implemented |
| `quota.is_limit_error` / `is_window_limit` | current product | the Claude Code adapter's limit classifier |
| `config.account_env` | current product | the Claude Code account environment |
| `proc.git`, `worktrees.remove` | current product | worktree creation and removal (§17) |
| `STOP` sentinel path, `processes_registry()` path | P1 paths; P9 reads the sentinel | written and consumed here |
| `FakeHarness` / `fake_agent.py` (stdlib-only scripted agent) | P1, P3.5 | gains the simulated hook (§10.6) and resume |

## 4. Conflicts with frozen documents, and their resolution

1. **Task vs execution during a pause or an approval wait.** The task machine moves
   `RUNNING → PAUSED → READY` and `RUNNING → AWAITING_APPROVAL → READY`, i.e. re-dispatch a new
   execution; the execution machine resumes the SAME execution (`PAUSED → STARTING: resume`,
   `AWAITING_APPROVAL → STARTING: resume_approved`). Both cannot hold. **Resolution (D7):** a task
   stays RUNNING for the whole life of its execution, including execution-level pauses and approval
   waits; the task moves only when its execution ends. The task's `pause`/`resume` and
   `action_needs_approval`/`approved` edges from RUNNING are not taken in V1 (kept in the table,
   documented as unused). `route_needs_approval` (P10) is unaffected: it happens before any
   execution.
2. **Terminal states the execution machine cannot reach.** A PAUSED or AWAITING_APPROVAL
   execution whose mission is cancelled or e-stopped has no edge to an end, STARTING and PAUSING
   cannot be stopped, and a process that finishes during PAUSING has nowhere to go.
   **Resolution (D8):** six edges are added (§8.2). No state is added.
3. **The hook's HTTP channel.** execution-architecture §5 and api-and-realtime §2 name
   `POST /v1/hook/evaluate` with an `ARCHEUS_HOOK_TOKEN`. Three facts make HTTP the wrong channel
   for V1: the in-process judge binding has no HTTP server at all, so every G6/S5 action-stage
   function could only run on one binding; an adopted process keeps the port and URL it was started
   with, which a restarted Core need not have; and a hook that cannot reach Core must fail closed,
   which a file protocol does by construction. **Resolution (D12):** the hook talks to Core through
   a per-execution mailbox in `run/exec/<id>/hook/` (§10.2). The token, its scopes and its
   fail-closed rule are unchanged; `/v1/hook/*` is not built (a remote node, deferred, will need an
   HTTP channel and gets it with the node transport).
4. **Fail-closed "allows pure reads"** (execution-architecture §5). The hook cannot classify an
   action — classification is Core's (§11) — so a hook that cannot reach Core **denies every
   tool call and halts** (D13). A read is cheap to repeat once Core is back.
5. **`Action` has no branch or host.** P9's `rules._values` returns None for `branch_glob`,
   `host_glob`, `branches`, `hosts` ("only the action stage knows them (P11)"), which makes every
   permissive branch/host rule unreachable and every restrictive one match. **Resolution (D16):**
   `Action` gains `branch` and `host`, `canonical_dict` includes them when set (so they are part of
   `action_hash`), and `_values` reads them. This is the slot P9 left, not a change to its
   semantics.
6. **Hand-off on ceiling crossing** (resource-router §4, execution-architecture §6). A crossing
   halts the execution and "hands off via checkpoint". Checkpoints and hand-off are P12's.
   **Resolution (D22):** P11 halts at the next boundary and ends the execution as a resource stop;
   the task re-routes without being charged an attempt; continuity through a checkpoint is P12's
   (S4's third function stays P12).
7. **R1 (a session resumes on its own harness's configuration)** is scheduled in P11 by
   testing-strategy §6, and plan P11 lists user sessions (`interactive_attached`, `manual`)
   launched and resumed through their adapter. The P11 phase specification excludes user-session
   resume and hand-off as a general feature. **Resolution (D29):** R1 and the user-session modes
   move to P12 with H1; P11's `resume` is only the resume of an execution Archeus paused (§14).
8. **The Codex adapter** (plan P11, G7). Codex is not installed on the development machine and no
   recorded Codex stream exists, so an adapter written now would be written against documentation,
   not a recording. **Resolution (D30):** the Codex adapter and its G7 function are deferred
   (re-tagged to P20, the hardening phase that owns adapter drills); Claude Code and the fake
   harness are P11's adapters. A new adapter needs no Core change (§9), which is the property G7
   exists to prove.
9. **The P3.5b "reconcile, never adopt" rule and the boot sweep.** Replaced by adopt-or-reconcile
   (§15) as the P3.5b gate scheduled; the orphan kill stays for anything not adoptable.
10. **`archeus estop` with Core down.** P3.5b and G5 put the Core-less form in P20; P11 builds the
    registry it needs and the Core-running form only (§13.4).
11. **Integration (merge-back).** state-machines §13 starts on `task_verified`, which is P13's
    event; P11 creates worktrees and never merges (§17).

## 5. Architecture

```text
engine thread (archeus-engine)          execution thread (archeus-exec)            node (V1: in-process)
──────────────────────────────          ──────────────────────────────            ─────────────────────
mission steps: verify, advance,         ExecutionManager.tick() every 100 ms:      LocalNode
ready_tasks, admission (§16)            • INTENT  -> prepare, spawn (via node)      • spawn(adapter, spec)
  -> Work.dispatch_task                 • live    -> exit? tail? hook requests?     • registry append/tombstone
     (P9 check + P10 route + INTENT)                   controls? ceiling? limit?    • alive(identity)
                                        • STOPPING/PAUSING -> flags, grace, kill    • kill(identity)
                                        • PAUSED  -> resume when the mission is     • tail(path, offset)
                                                     EXECUTING again (§14)          • worktree add/remove
                                        • boot: adopt or reconcile (§15)
           \______________________ one writer (every state change is one command) _______________/
```

- **`archeus/core/execution/manager.py`** — `ExecutionManager`: every decision about an execution.
  Never inside a transaction: it reads, acts on the world through the node, and records through a
  writer command. Non-blocking: one `tick()` does bounded work for every live execution, which
  removes the P3.5b blocking `_finish` (A17) and makes tasks run in parallel.
- **`archeus/node/local.py`** — `LocalNode`: the node contract of execution-architecture §9 for the
  local machine. Spawns through the adapter, keeps `run/processes.jsonl`, checks and kills by
  identity, tails streams, creates and removes worktrees. It never opens the database, never
  evaluates policy and never routes (boundary test).
- **`archeus/core/execution/canonical.py`** — pure: a tool call → canonical actions (§11).
- **`archeus/core/application/executions.py`** — the P11 writer commands (§20).
- **`archeus/harnesses/hook.py`** — the execution hook: one stdlib-only script, the same file for
  the real Claude Code harness (a PreToolUse command) and the fake agent (which runs it exactly as
  Claude Code would, §10.6).
- **`archeus/harnesses/claude_code/adapter.py`** — the real adapter (§9.2).

The in-process judge binding pumps `manager.tick()` from `_idle()` as it pumps the engine; the Core
runtime runs it on the `archeus-exec` thread, stopped and joined like the other workers.

## 6. Execution identity (question 1)

```text
Mission ─< PlanVersion (immutable, digest) ─< Task (frozen dispatch contract)
                                                 ─< Execution (attempt n, one per dispatch)
                                                       ─< process k (pid, create_time, argv0)
                                                       ─ RouteDecision (P10), PolicyDecision (P9)
```

- **One Execution per dispatch**, numbered `attempt = 1, 2, …` per task [spec]. A retry is always a
  new Execution; nothing ends a row and reopens it; an ended row is never written again.
- **Processes within one Execution.** Resuming a paused execution or one released by an approval
  starts a new process of the SAME execution (§14). `process_seq` counts them; the row holds the
  current `{pid, create_time}`; the history of every process is the append-only registry and one
  `execution.started` event per process (each with its pid, create time and `process_seq`) — never
  a rewritten row.
- **Charged attempts** (D9). `max_attempts` bounds the executions that ended for a reason the task
  owns (`ok` then failed verification, `error`, `lost`, `rejected`). An execution ended by the user
  (`stop`), the e-stop, a runtime ceiling, a limit error, the breaker, a cancelled mission or an
  unresumable pause is **not charged**: the task goes back to READY without spending its budget.
  The counting is `_failed`'s, extended by that one predicate.
- The Execution records the binding it was dispatched under: `plan_id`, `plan_digest` and
  `policy_decision_id` (the covered dispatch decision), and keeps `route_decision_id` (P10).

## 7. Exact plan binding (question 2)

At **dispatch** P9 (`check_dispatch`) and P10 (`current_authorization`) already require the active,
intact plan version, the exact task and a current `covered` decision [spec]. P11 adds the same test
at every point where the world changes after that — **immediately before each process start**
(first spawn and every resume) and **at every hook request** — as one function,
`executions.binding_current(conn, execution)`:

- the task's plan is the mission's plan in force (`active_plan`) and `intact` (its digest recomputed
  from its rows equals the stored one) and equals the execution's recorded `plan_id` / `plan_digest`;
- the task is the execution's task, in that plan, in state RUNNING;
- the execution's `policy_decision_id` is still the task's latest dispatch decision and `covered`
  (for a resume: `check_dispatch` is asked again, §14).

Stale, superseded or tampered → the process is not started (the execution ends uncharged, the task
is re-dispatched and judged afresh) or, for a hook request, the action is denied and the execution
halted and stopped.

## 8. State machines (question 13)

### 8.1 Execution — the frozen machine, and what fires each edge

| Edge | Fired by | Guard / precondition | Event |
|---|---|---|---|
| `INTENT → STARTING: spawn` | manager after the node reports `{pid, create_time}` | binding current, terms permitted, not disarmed, process exists | `execution.started` |
| `INTENT → ABANDONED: spawn_failed` | manager / reconciliation | no process was created (spawn error, e-stop before spawn, binding stale) | `execution.state_changed` |
| `INTENT → LOST: spawn_unconfirmed` | reconciliation | marker without `pid.json` | same |
| `STARTING → RUNNING: first_output` | manager | the stream has a first event | same |
| `STARTING → LOST: start_timeout` | manager | no output for `start_timeout` (60 s) and the process is gone | same |
| `RUNNING → AWAITING_APPROVAL: hook_asked` | manager serving a hook request | P9 answered ASK and no approval covers it | `approval.requested` (P9) |
| `AWAITING_APPROVAL → STARTING: resume_approved` | manager | the action approval is APPROVED, resume checks (§14) pass | `execution.started` |
| `AWAITING_APPROVAL → ENDED_REJECTED: rejected` | manager | the action approval is REJECTED or EXPIRED | `execution.ended` |
| `RUNNING → PAUSING: pause_requested` | `executions.pause` (mission paused) | — | state_changed |
| `PAUSING → PAUSED: halted_at_boundary` | manager | the process exited after the hook halted it for pause | state_changed |
| `PAUSING → STOPPING: pause_timeout` | manager | no boundary within `pause_timeout` (120 s) | state_changed |
| `PAUSED → STARTING: resume` | manager | mission EXECUTING again, resume checks (§14) | `execution.started` |
| `RUNNING → STOPPING: stop` | `executions.stop` / e-stop / ceiling / limit / breaker | — | state_changed |
| `STOPPING → ENDED_KILLED: process_gone` | manager | the process is gone (by identity) | `execution.ended` |
| `RUNNING → ENDED_OK: exited_success` / `ENDED_ERROR: exited_error` | manager | exit observed, exit code 0 / non-0 | `execution.ended` |
| `RUNNING → LOST: heartbeat_missing` | reconciliation | the process is gone and no exit was recorded | state_changed |
| `LOST → RUNNING: adopted` | reconciliation | pid + create time match a live process | `execution.adopted` |
| `LOST → ENDED_KILLED: reconciled_kill` | reconciliation | not adoptable | `execution.ended` |
| `RUNNING → HANDING_OFF`, `HANDING_OFF → ENDED_HANDOFF` | **P12** | — | — |

### 8.2 Edges added (D8)

| Edge | Why |
|---|---|
| `STARTING → STOPPING: stop` | a stop, e-stop or ceiling before the first output |
| `PAUSING → STOPPING: stop` | a stop while a pause is pending |
| `PAUSING → ENDED_OK: exited_success`, `PAUSING → ENDED_ERROR: exited_error` | the work finished before it reached a boundary |
| `PAUSED → ENDED_KILLED: discarded` | no process exists: the mission was cancelled or e-stopped, or the resume checks failed |
| `AWAITING_APPROVAL → ENDED_KILLED: discarded` | same, while waiting for an action approval |

No state is added; the task and mission machines are unchanged (D7). A test pins the execution
table to exactly the P1 edges plus these six.

### 8.3 Task and mission responses (questions 14, 15)

| Execution ends | Task | Mission |
|---|---|---|
| ENDED_OK | `execution_succeeded` → VERIFYING (P13 decides) | — |
| ENDED_ERROR / LOST→ENDED_KILLED (charged) | `execution_failed_retry` → READY, or `execution_failed_final` → FAILED when the charged budget is spent | P3/P8 `advance` as today |
| ENDED_REJECTED | `execution_failed_final`, `failure_class: rejected` | P3/P8 `advance` (a replan or FAILED) |
| ENDED_KILLED by stop / e-stop / cancel (uncharged) | `execution_failed_retry` → READY (uncharged) | `block` with the reason (user stop, e-stop); nothing for a cancel |
| ENDED_KILLED by ceiling / limit / breaker (uncharged) | `execution_failed_retry` → READY (uncharged) | — (the task re-routes; P10 blocks or asks the mission if nothing is eligible) |
| ABANDONED (stale binding, e-stop before spawn) | READY (uncharged) | as above |

P11 never fires `all_tasks_done`, `verified` or `accepted`; a dependency is satisfied only by a
SUCCEEDED task (P3.5 `ready_tasks`), so a failed or stopped dependency never releases its
dependents [spec].

## 9. The adapter contract, as used

### 9.1 Additions to the P1 contract [clar]

- `start(spec)` receives `spec.env` with the capability-removal environment (§18) and the hook
  variables; `spec.resume_ref` for a resumed process.
- `inspect(handle, offset=0)` → normalised events from `offset` and the next offset (the tailer's
  read; P1's full read is `offset=0`).
- `ExecutionResult` gains `failure: resource | task | auth | limit | None` (the adapter's
  classification of how it ended, §12.3), `halted` (the process ended because the hook halted it:
  a pause, an ASK or a stop flag — not because the work finished) and `adapter_state` (opaque: a
  provider session ref, the fake agent's step) — kept on the Execution, never interpreted by Core.
  In PAUSING, `halted` decides `halted_at_boundary` against `exited_success`/`exited_error`; in
  RUNNING, a halted exit that Core did not ask for (no ASK, no flag) is an error, never success.
- `Capabilities.capabilities` declaring `resume` is what makes a paused execution resumable.

A new adapter implements this contract and nothing else: no Core table, event or state changes
(G7's property).

### 9.2 Claude Code (`harnesses/claude_code/adapter.py`) [spec, execution-architecture §3]

`claude -p --output-format stream-json --verbose --session-id <uuid> [--model m] [--effort e]
--max-turns N --settings <run/exec/<id>/settings.json>` with the prompt on stdin; resume adds
`--resume <session uuid>` on the same account. The settings file installs the one PreToolUse hook
(`<python> harnesses/hook.py`) for this execution only (ADR-0019: never the user's
`settings.json`). The environment is `config.account_env(home)` plus §18. Normalisation maps
stream-json lines to `{type: assistant | tool | tool_result | usage | result | limit | error |
stderr}`; a limit is recognised by `quota.is_limit_error`. Its contract test runs a recorded stream
in CI and the real CLI only in the opt-in suite (`ARCHEUS_REAL_HARNESS=1`), never on shared
runners. Registered in the runtime only when `Ports.executors` does not name the adapters (§23).

## 10. Hooks (question 5)

### 10.1 Which hook, when

One hook, **PreToolUse**, before every tool call of an execution whose harness declares
`enforcement: hook`. No other hook is installed by P11 (PreCompact is P12's pressure backstop). A
`sandbox` or `none` harness has no per-call hook: its actions are bounded by capability removal and
by P10's enforcement step, which already refuses such a harness for work it cannot enforce.

### 10.2 The channel: a mailbox (D12)

```text
run/exec/<execution_id>/hook/<seq>.req.json    written by the hook (atomic rename)
run/exec/<execution_id>/hook/<seq>.res.json    written by Core after the decision commits
run/exec/<execution_id>/PAUSE | STOP           control flags Core writes
<ARCHEUS_HOME>/run/STOP                          the e-stop sentinel
```

The hook, in order: (1) the global `STOP` sentinel → **halt**; (2) this execution's `STOP` or
`PAUSE` flag → **halt**; (3) write the request `{seq, token, tool, input, cwd}`; (4) wait for the
response up to `HOOK_WAIT` (60 s, polling); no response → **deny and halt** (fail closed, D13).
Decisions are `allow`, `deny` (with the reason, the agent may adapt) and `halt` (the agent stops).

### 10.3 Identity and authorisation

- Every process gets `ARCHEUS_EXECUTION_ID`, `ARCHEUS_HOME` and `ARCHEUS_HOOK_TOKEN` (`hook_` +
  32 random bytes, typed per api-and-realtime §5.3). Core stores only `sha256(token)` on the
  Execution; each process start mints a new token (the plaintext never persists), so an adopted
  process keeps its own and a resumed one gets a new one; a terminal execution has no hash and
  every request is refused.
- Core serves a request only when: the execution is live (STARTING/RUNNING), the request sits in
  that execution's own directory, `hmac.compare_digest` of the token hash (bytes) holds, and `seq`
  is greater than the last served (`hook_seq`) — a replayed or reordered request is refused.
- **Impersonation**: a request in execution A's mailbox with B's token fails the hash; a forged
  `execution_id` inside a request is ignored (the directory is the identity).
- **Recursion**: the hook runs no tools and starts no agent; a nested agent an execution starts
  inherits its environment but not the `--settings` file, and its own requests would carry the
  same token into the same mailbox, so they are judged as this execution's actions, never as
  another's. The hook refuses to run when `ARCHEUS_HOOK_ACTIVE` is already set in its environment
  (a hook invoking itself), and sets it for its own duration.
- A hook request is distinguished from task output by channel: the stream is output, the mailbox
  is the control plane; nothing in `stream.jsonl` is ever read as a decision.

### 10.4 What Core decides for one request (`executions.serve_hook`, one transaction)

1. identity and freshness checks (§10.3); disarmed → halt;
2. `binding_current` (§7) → else deny, halt, and the execution is stopped (uncharged);
3. **working directory**: the request's `cwd` must resolve inside the execution's `workdir` →
   else deny + halt (`workdir escape`);
4. **branch**: for a git workspace, HEAD must be the execution's recorded branch → else deny + halt
   (`branch mismatch`);
5. canonicalise (§11) → one or more actions and `unclassified`;
6. each action → `authorization.evaluate_action` (P9 records a PolicyDecision; a covered action
   approval is consumed there, single-use);
7. any DENY → `deny` (the reasons); any uncovered ASK → `halt`, `hook_asked` (the execution waits,
   the task stays RUNNING, D7); else `allow`.

The response file is written only after the transaction commits; a Core that dies between leaves
the hook to time out, which denies (fail closed).

### 10.5 Hook failures and output

A hook that crashes, cannot write its request or reads a malformed response **denies and halts**.
Its stderr goes to the stream (typed `stderr`); its decisions are PolicyDecisions and the
execution's `hook_seq`, not log lines.

### 10.6 The fake agent's hook [clar]

`fake_agent.py` stays stdlib-only. For an emitted event of `type: tool` it runs `hook.py` as a
subprocess exactly as Claude Code does (the tool call as JSON on stdin), then: `allow` → emits the
event; `deny` → emits `{type: tool_denied, reason}` and exits 3 (a scripted agent cannot adapt);
`halt` → emits `{type: halted, at: <step>}` and exits 0. Resume starts it again at `resume_ref`
(the step it halted at). The judge's G6 and S5 scripts run unchanged.

## 11. Concrete action canonicalisation (question 4)

`canonical.canonicalise(tool, input, ctx) -> (actions, unclassified)`, pure, over `ctx =
{workdir, branch, remote_hosts}` that the manager reads before the command (a git read is a side
effect-free read outside the transaction; its value is recorded in the decision).

| Tool (Claude Code names) | Class | target | extra |
|---|---|---|---|
| Read, Glob, Grep, LS | `read` | path | `paths` |
| Write, Edit, MultiEdit, NotebookEdit | `write_repo` | path | `paths` |
| WebFetch | `web` | URL | `host` |
| WebSearch | `web` | `search` | — |
| Bash | by the command (below) | argv0 | `argv`, and `paths` / `branch` / `host` / `environment` where the command names them |
| anything else | `exec` | the tool name | `unclassified` |

**Paths** are resolved against `workdir` and made workspace-relative; anything outside, absolute or
containing `..` after resolution stays absolute, which P9's containment treats as **never inside**
(p9 §6.2). **Bash**: `shlex` (POSIX) on the command; a command containing any shell operator
outside quotes (`| ; & && || > < $( \``), `eval`, `exec`, `source`, a `-c` payload to a shell or
interpreter, `base64 -d`, or a parse error is **one `exec` action with `unclassified: true`**, which
P9 judges as every class the task holds plus `exec`, strictest wins (p9 §6.3). Otherwise by the
first word:

| Command | Class |
|---|---|
| `git status|log|diff|show|rev-parse|ls-files|branch` (no delete flag) | `read` |
| `git add|checkout|switch|restore|stash|merge|rebase|cherry-pick` | `write_repo` |
| `git commit` | `git_commit`, `branch` = current HEAD |
| `git push` | `git_push`, `branch` = the refspec or HEAD, `host` = the remote's host |
| `git reset --hard`, `git clean -f…`, `git branch -D`, `git push --force|-f|--delete` | `destructive` (a forced/deleting push is both `git_push` and `destructive`) |
| `rm -r|-rf|-fr`, `terraform destroy`, `kubectl delete`, `drop …` in a DB client | `destructive` |
| `terraform apply`, `kubectl apply`, `vercel`, `npm|yarn|pnpm publish`, `docker push`, `gh release` | `deploy` |
| `pip|npm|yarn|pnpm|cargo|go|gem install|add|get` | `install` |
| `curl`, `wget` (GET) | `web`, `host`; with `-X POST|PUT|PATCH|DELETE`, `-d`, `--data*`, `-F` → `external_comm` |
| `ssh`, `scp`, `rsync` to a host | `external_comm`, `host` |
| `ls cat head tail wc grep rg find pwd echo which` (no `-exec`/`-delete`) | `read` |
| `rm`, `mv`, `cp`, `mkdir`, `touch` | `write_repo`, `paths` |
| anything else (python, node, make, pytest, npm test, …) | `exec`, `paths: ['.']` |

`environment` is set only where the command names it (`--prod`, `--production`, `-e prod`,
`workspace select prod`); otherwise it is absent, and an absent attribute matches a restrictive rule
(p9 §6.1): `terraform destroy` with no environment meets the floor's destructive DENY. The table is
data in `canonical.py`; an unknown or ambiguous command is never guessed permissive. The classifier
is a convenience; capability removal (§18) is the guarantee [spec, execution-architecture §5].

## 12. Runtime usage, ceilings, limits and the breaker (questions 9, 10, 11)

### 12.1 Usage (question 10)

- Adapters report usage only as the provider states it (Claude Code: stream-json `usage` blocks and
  the `result` event; the fake agent: scripted `usage` events). Nothing is estimated.
- The manager keeps the latest cumulative usage on the Execution (`usage`) through
  `record_progress` (coalesced, ≤ 1/s); the authoritative figure is the adapter's final result,
  written once by `record_exit` as the UsageLedger row that names the execution, its
  RouteDecision and its account (P10 contract). A second exit report is an invalid transition, so
  usage is never counted twice.
- Unknown usage (no report) writes no ledger row and leaves `usage` empty: never zero.

### 12.2 The runtime ceiling (question 9)

For every account with a live execution the manager reads the usage feed every 30 s (the feed is an
in-memory read, P10) and records changed readings as UsageSnapshots. When `worst ≥
allocation_pct` (resource-router §4 `must_halt`) every live execution on that account is stopped
**gracefully**: the execution's STOP flag halts it at its next tool boundary; after `grace_s`
(10 s) it is killed. The end is a resource stop (uncharged), the task re-routes, and the affinity
to that account is dropped (resource-router §7) so P10 does not route straight back to it.

### 12.3 Limit errors

An adapter reports `{type: limit, window, resets_at}` when the provider refuses for a limit. For a
registered account the manager fires `window_exhausted` (→ LIMITED, `limited_until = resets_at`,
or one hour when unknown) and stops every execution on it immediately (the agent cannot proceed);
uncharged; affinity dropped. `reset_time_passed` (LIMITED → AVAILABLE) is fired by the manager
when `limited_until` passes. A harness's own unregistered account has no health: the execution ends
charged (`failure: limit`), so a limit there cannot loop forever.

### 12.4 The error breaker (question 11)

Scope: **one registered account** (state-machines §9); never global, never a mission or a task.
Counted: executions on that account that ended ENDED_ERROR with the adapter's
`failure: resource` (API errors, overload, transport failures — not the agent's own failure) or
`auth`. A task-attributable error never counts.

| Move | When |
|---|---|
| `error_storm` AVAILABLE/CONSTRAINED → DEGRADED | 5 resource errors within 10 min |
| `errors_persist` DEGRADED → OPEN | 2 more resource errors while DEGRADED, and at least one beat (60 s) since the last move |
| `cooldown_elapsed` OPEN → DEGRADED | 5 min in OPEN |
| `probe_ok` DEGRADED → AVAILABLE | an execution on it ends ENDED_OK, or the adapter's `authenticate` probe succeeds after a beat |
| `auth_failed` → UNAUTHENTICATED | an adapter reports `failure: auth` |

At most one level per beat. P10 already routes DEGRADED only as a fallback and never OPEN. A user
can disable the account at any time; no user action is required to recover.

## 13. Pause, stop and the e-stop (question 8)

| | pause | stop | e-stop |
|---|---|---|---|
| asked by | a mission pause (`POST /v1/missions/{id}/pause`, `archeus pause <mission>`) | `POST /v1/executions/{id}/stop`, `stop(<mission or execution>)` | `POST /v1/estop`, `archeus estop`, `archeus pause all --now`, `stop('all')` |
| state | RUNNING → PAUSING → PAUSED | → STOPPING → ENDED_KILLED | every live execution → ENDED_KILLED (or ABANDONED / discarded) |
| process | halted by the hook at its next tool boundary (the process exits); `pause_timeout` (120 s) → stop | STOP flag (halt at a boundary), `grace_s` 10 s, then `kill_pid_tree` by identity | the sentinel first, then `kill_pid_tree` of every live process at once, no grace |
| child processes | exit with the agent | killed with the tree | killed with the tree |
| stdin / output | stdin is a file (nothing to close); the stream is kept | same | same |
| resumable | yes: the same execution, same account (§14), when the adapter declares `resume` | no: the task goes back to READY (uncharged) and is re-dispatched when the mission is resumed | no; Core stays **disarmed** until `rearm` |
| authorisation | re-checked at resume | a new dispatch is judged afresh | nothing is dispatched, resumed or routed while disarmed |
| routing | re-asked at resume (§14) | a new decision at the next dispatch | refused while disarmed |
| mission | PAUSED (P3) | `block`, reason "stopped by the user" | every mission with live work `block`s, reason "emergency stop" |

- **A stop is by identity.** `kill_pid_tree(pid, create_time)` refuses a recycled pid; a refusal
  while another process holds the pid means ours has gone: `process_gone`. A second stop of a
  STOPPING execution is an invalid transition: nothing changes.
- **E-stop is fail-safe and model-free.** The sentinel is written before anything else, so a hook
  halts even if Core dies in the middle; P9 already denies every decision while it exists; the
  manager checks it immediately before and immediately after every spawn (a process that started
  in the race is killed). No model call is involved anywhere on the path.
- **Disarmed Core.** With the sentinel present Core reconciles and reports but spawns, resumes,
  dispatches and routes nothing (own calls included) until `POST /v1/rearm` from a user device with
  the `control` scope deletes it and records `core.rearmed`. `health` reports `armed`.
- **13.4 Without Core** (`archeus estop` when Core is down: the sentinel plus a registry kill) is
  P20, as P3.5b and G5 schedule it; P11 writes the registry it needs. With Core down the CLI says
  so and exits 2.

## 14. Resume (paused or released by an approval)

Resume is **only** of an execution Archeus itself halted, on its own harness and account
[spec, state-machines §4]; a user's own session is P12 (D29). Before the new process starts, in
order, and any failure discards the paused execution (uncharged) so the task is re-dispatched and
judged from scratch:

1. not disarmed; the mission is EXECUTING;
2. `binding_current` (§7) and P9's `check_dispatch` answers `covered` for this task now;
3. P10 is asked again (`ResourceRouter.route`, a new RouteDecision) and must select the same
   harness and account — a provider session lives in one account (domain-model §7.5), so any other
   answer means the continuity is gone and the task starts over through normal dispatch;
4. provider terms permitted (ADR-0021's second check);
5. the adapter declares `resume`.

The execution keeps its attempt number; `process_seq` increments; a new hook token is minted.

## 15. Registry, reconciliation, adoption and restart (questions 6, 7, 19)

### 15.1 Process identity

A process is `(execution_id, process_seq, pid, create_time)` on the local node. **A pid alone
never identifies a process**: every liveness check, kill and adoption compares the recorded create
time with a fresh reading (`proc.process_create_time`, the P0.5 seam: `GetProcessTimes` on
Windows, libproc microseconds on macOS — the P4/P3.5b fix for same-second reuse — `/proc` starttime
on Linux). Unknown create time = not ours.

### 15.2 The registry

`run/processes.jsonl`, append-only: `{op: spawn, execution_id, process_seq, pid, create_time,
argv0, started_at}` after `pid.json`, and `{op: end, execution_id, process_seq, ended_at}` on exit.
The database is authoritative whenever Core runs; the registry exists for the Core-less e-stop
(P20) and as a cross-check at boot. Rewritten (atomically) at boot to its live entries.

### 15.3 Boot: adopt or reconcile

Before the engine or the manager serves anything, every non-terminal execution is examined:

| State at boot | Files / process | Result |
|---|---|---|
| INTENT | no marker | `spawn_failed` → ABANDONED (uncharged) |
| INTENT | marker, no `pid.json` | `spawn_unconfirmed` → LOST → `reconciled_kill` (charged: a process may have run) |
| INTENT | marker + `pid.json`, process alive by identity | `spawn` with the recorded identity → adopted |
| STARTING / RUNNING / PAUSING / STOPPING | process alive by identity | **adopted**: `execution.adopted`, tailing resumes from the stored offset, the hook mailbox is served; STOPPING / PAUSING continue their control |
| STARTING / RUNNING | process gone, `ended` tombstone or exit known | the exit is collected and recorded as if observed (P3.5b A17's collect-on-boot) |
| STARTING / RUNNING | process gone, nothing known | LOST → `reconciled_kill` (charged) |
| PAUSING / STOPPING | process gone | PAUSED (`halted_at_boundary`) / `process_gone` |
| pid alive with another create time (reused) | — | treated as gone; the stranger is never touched |
| LOST | alive by identity | `adopted` → RUNNING; else `reconciled_kill` |
| any, disarmed | alive | killed by identity, then as "gone" |

Adoption is the manager beginning to watch; no process is ever spawned twice for one
`process_seq`. The one-engine-per-Core rule (P3.5b) and the Core lock make the boot sweep the only
reconciler, so reconciliation cannot race another Core. A crash inside a transition leaves either
the old or the new row (one transaction); a crash between a transaction and its side effect is
covered by the marker/`pid.json`/tombstone rules above.

### 15.4 Liveness while running

Each tick checks every live process by identity. Gone without an observed exit → the exit is
collected (the adapter reads `ended` / the stream's `result`); nothing collectable within
`lost_after` (90 s) → `heartbeat_missing` → LOST → `reconciled_kill`. **A vanished process is
never success**: without an observed exit code 0 there is no ENDED_OK.

## 16. Parallel execution (question 16)

The engine dispatches READY tasks one per step (each dispatch is P9 + P10 + INTENT, unchanged) as
long as admission allows; the manager runs them concurrently. Admission, in the engine, checked
against the database:

- not disarmed;
- the mission has fewer than `MISSION_PARALLEL` (3) live executions;
- **workspace conflicts**: an `in_place` task never runs beside another live execution in the same
  project; two tasks whose `touches` overlap (glob prefix overlap, conservative) never run at once;
  a task with no `touches` is exclusive within its project;
- the account's own `concurrency` budget is P10's (the ledger's `running`).

Dependencies are P8's graph as `ready_tasks` reads it; P11 adds no planning. The engine loop's
parking is keyed on the mission's version **and** a stamp over its tasks and executions (the
per-task wakeup P3.5b left to P11), so an execution ending wakes its mission.

## 17. Workspaces, branches and worktrees (question 17)

| Task | Workdir | Branch |
|---|---|---|
| no project | `run/exec/<id>/` (as P3.5) | none |
| project, `workspace_mode: worktree`, the project's first root is a git repository | `<ARCHEUS_HOME>/worktrees/<project-id>/<mission-id>/<task-key>` created by the node (`git worktree add -b archeus/<mission-id>/<task-key>` from HEAD) | `archeus/<mission-id>/<task-key>` |
| project, `in_place` (or not a git repository) | the project's first root | HEAD at spawn, recorded |

The workdir and branch are recorded on the Execution before the process starts; the process is
started there and nowhere else; every hook request is checked against both (§10.4). A worktree is
removed only by the node that created it and only when `git worktree list` confirms it
(execution-architecture §7); P11 removes one only for an execution that ended ABANDONED; merge-back
and the removal of verified worktrees are P13's.

## 18. The execution environment (capability removal) [spec, execution-architecture §2]

Every process: `ARCHEUS_EXECUTION_ID`, `ARCHEUS_HOME`, `ARCHEUS_HOOK_TOKEN`; the legacy
`HEADLESS_MARK` appended to the prompt; `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=` (empty),
`SSH_AUTH_SOCK` removed, `GIT_CONFIG_COUNT=1`, `GIT_CONFIG_KEY_0=credential.helper`,
`GIT_CONFIG_VALUE_0=` (empty) — the agent can commit locally and cannot push with the user's
credentials; `git_push` authorised by P9 is still attempted by the agent and fails without them,
which is the documented V1 posture (Core-performed push is P13's merge-back). Claude Code adds
`config.account_env(home)` and `--max-turns` from the task estimate.

## 19. Live output (question 12)

- **Capture**: stdout and stderr of the process go to `stream.jsonl` (P1 contract); a non-JSON
  line is kept as `{type: stderr}`.
- **Tailing**: each tick reads at most 256 KiB past the execution's stored `stream_offset`,
  through the adapter's `inspect(handle, offset)` (normalisation is the adapter's).
- **Events**: `record_progress` (coalesced, ≤ 1/s per execution) stores the new offset and the
  cumulative usage and appends **`execution.progress`** `{offset, events, last: [≤ 20 lines, ≤ 2
  KiB]}`. The offset is monotonic: a progress report behind the stored offset is refused.
  `execution.ended` carries `final_offset` — the termination marker.
- **Ordering and replay**: events are ordered by the outbox `seq` and, within an execution, by
  offset; a reconnecting client catches up through `/v1/events` / SSE (P3.5b), and the file is the
  full record. **Transport**: the existing event stream; no second channel. The client route
  `/v1/executions/{id}/stream` stays P16's (P3.5b D8) and reads through `adapter.inspect`.
- **Backpressure**: the per-tick cap bounds work; progress coalescing bounds events; the file is
  not truncated by P11 (retention is P21's).
- **Sensitive output**: lines placed in events pass a redactor (Archeus token prefixes `hook_`,
  `dev_`, `node_`; `sk-…`, `ghp_…`, `github_pat_…`, `AKIA…`, `Bearer …`, and the execution's own
  token); the file is local to `ARCHEUS_HOME`, which already holds the database.
- **Forged output**: output is data. No decision, state or usage is taken from a line that claims
  to be one; usage comes only from the adapter's normalisation of the provider's own events, and a
  `result` summary is recorded as the reported summary, never as success.

## 20. Data model and commands

### 20.1 Migration `0010_execution.sql`

Promoted columns on `executions`: `plan_id`, `workdir` (index for the admission check is by
mission). Execution body fields [new]: `plan_digest`, `policy_decision_id`, `workdir`, `branch`,
`process_seq`, `hook_token_hash`, `hook_seq`, `stream_offset`, `usage`, `adapter_state`,
`stop_reason` (`user | estop | ceiling | limit | breaker | pause_timeout | cancel | binding |
disarmed`), `failure` (the adapter's), `charged`, `started_at`, `ended_at`. Account gains
`limited_until`. No new table: the registry and the mailbox are files (they must work without the
database).

### 20.2 Events [new]

`execution.progress`, `execution.adopted`, `core.estopped`, `core.rearmed`. `execution.started`
gains `process_seq`; `execution.ended` gains `final_offset`, `stop_reason`, `charged`.

### 20.3 Commands (`application/executions.py`)

`prepare_process` (binding check, workdir, branch, token hash, `process_seq`), `record_spawn`
(existing), `record_progress`, `record_exit` (existing, extended), `serve_hook`, `pause_mission_work`,
`stop_execution`, `stop_mission`, `estop`, `rearm`, `mark_paused`, `resume_checked`, `discard`,
`adopt`, `account_limit`, `account_breaker`. Every one is a single transaction whose state moves go
through `lifecycle.fire` (audited), with the event the table requires.

## 21. API and CLI

| Surface | Scope | |
|---|---|---|
| `GET /v1/executions/{id}` | observe | the execution, its process identity, offset, usage, state |
| `GET /v1/tasks/{id}/executions` | observe | every attempt of a task, in order |
| `POST /v1/executions/{id}/stop` | control, idempotent | stop one execution |
| `POST /v1/missions/{id}/stop` | control, idempotent | stop every live execution of a mission and block it |
| `POST /v1/estop` | control, idempotent | e-stop with Core running |
| `POST /v1/rearm` | control (user device), idempotent | clear the sentinel |
| `archeus pause <mission-id>` / `archeus pause all --now` | CLI | the mission pause / the e-stop |
| `archeus estop` | CLI | the e-stop (Core running; Core down is P20) |

Mission pause and resume already exist (P3). `/v1/hook/*` is not built (D12); the stream route is
P16's; `retry` and `handoff` (api-and-realtime §2) are P12's. The judge client's `stop(target)`
and `pause(target)` gain execution and `all` targets.

## 22. Security model

Threats and the control for each (the tests are §24.2):

| Threat | Control |
|---|---|
| forged execution id | the mailbox directory is the identity; `ExecPaths` accepts only well-formed ids; no route takes a pid |
| forged / reused pid, wrong start identity | identity is (pid, create_time); every kill and adoption re-reads it |
| wrong task / plan, stale or superseded plan | `binding_current` at every spawn, resume and hook request |
| stale approval, approval for another action | P9's `action_hash` (with `execution_id`, branch, host) and single-use consumption |
| unauthorised command, ambiguous parse | canonicalisation never guesses permissive; `unclassified` is judged strictest |
| branch / host mismatch, workdir escape | §10.4 checks; `branch`/`host` in the hash |
| hook recursion / impersonation | §10.3 |
| forged output | §19: output is never a decision, a state or a success |
| duplicate completion / stop | one transition per end; a second is an invalid transition |
| stop after pid reuse | kill by identity |
| e-stop race, restart race | sentinel first, checked before and after every spawn; one reconciler per home |
| check-then-use | every decision re-reads state inside its transaction; the hook's allow is for one action; the residual window between a decision and the agent's use is the one P9 accepts for action approvals |
| usage tampering | usage only from adapter normalisation; ledger row written once per execution against its recorded decision and account |
| success without evidence | ENDED_OK → VERIFYING only; P11 has no path to SUCCEEDED |
| bypassing P9 / P10 | P11 imports neither `policy.engine` nor `routing.router`; it calls `authorization` and `resources` entry points (boundary tests) |

## 23. Runtime wiring

`Ports.executors` (None → the real adapters: Claude Code, gated by the P9 registry check, ADR-0021
terms and P10's enforcement step) replaces the hard-coded `FakeHarness()` registration; tests and
the judge pass `[FakeHarness()]`. The P10 boundary test B8 ("only the fake harness is registered")
migrates to "exactly `Ports.executors`, and real adapters only behind a real policy" (§26).

## 24. Acceptance, tests, mutation, boundaries

### 24.1 Judge

G1 (adopt the live process: runs once), G5 (`stop('all')` kills; exit reason `killed`), G6
(`terraform destroy` on prod is denied by the locked floor at the action stage), S5
(single-use action approval), and G7's Claude Code function (recorded stream) move to passing on
both bindings. G5's Core-less function stays P20; G7's Codex function is re-tagged P20 (D30).
S1 against the real Claude Code adapter runs in the opt-in contract suite.

### 24.2 Tests

- **Unit** (`tests/v1/unit/test_execution_units.py`): canonicalisation table (every row, operator
  detection, paths inside/outside, branch/host/environment, unknown → unclassified); redaction;
  charged-attempt predicate; breaker thresholds; state table = P1 + D8.
- **Integration** (`tests/v1/integration/test_execution.py`), over the real database and the fake
  agent's real processes: basics (authorised executes; denied, pending, stale authorisation,
  superseded plan, wrong digest, wrong task never start); process safety (identity required, pid
  reuse never killed, orphan, already exited, vanished, kill-tree takes children, stdin is the file,
  output captured); lifecycle (start, pause, resume, stop, e-stop, fail, retry, duplicate commands,
  invalid transitions); runtime (ceiling crossing, limit error, breaker, resource failure, usage
  update, unknown usage, attribution); hooks (runs, receives identity, recursion refused, failure
  denies, impersonation refused, replay refused, fail-closed without Core); concrete boundaries
  (branch, host, command, unclassified, workdir, argument canonicalisation); parallel
  (independent tasks overlap in time, dependencies wait, a failed dependency blocks, overlapping
  touches serialise); recovery (restart while running, after exit, pid reuse during recovery,
  orphan, duplicate recovery, crash between transaction and side effect); output (stdout, stderr,
  ordering, persistence, replay after restart, cap, completion marker).
- **HTTP** (`test_execution_http.py`): the §21 routes, scopes, idempotency, errors; the CLI verbs.
- **Contract**: the Claude Code adapter normalises a recorded stream; opt-in real run.
- **Security** (`test_execution_security.py`): every row of §22.

### 24.3 Mutation suite (`tools/mutate_p11.py`)

Each mutant has its own killing test (no mutant may be killed only by a different safeguard): P9
authorisation skipped at the hook; stale approval accepted; superseded plan accepted; digest
ignored; task binding ignored; pid-only identity; reused pid killed; hook guard skipped (token /
seq / directory, one mutant each); branch check skipped; host dropped from the action; workdir
check skipped; unauthorised command classified permissive; ceiling not enforced; e-stop ignored at
spawn; duplicate completion accepted; duplicate stop accepted; usage detached from the execution;
ENDED_OK straight to SUCCEEDED; vanished process recorded as success; orphan left running;
restart reconciliation skipped; breaker disabled; progress offset allowed to go backwards;
uncharged ends charged (and the reverse); resume without re-routing; resume without P9.

### 24.4 Boundary tests (`test_execution_boundaries.py`)

P11 modules never import `policy.engine`, `policy.rules` or `routing.router`; never write
`policy_rules`, `approvals` (other than through P9's commands), `route_decisions` (other than
through P10's `record_route`); never fire a plan, verification or review transition, `all_tasks_done`,
`verified`, `accepted` or `checks_passed`; create no Session, Checkpoint or Integration row; no
module under `core/execution` or `node` calls a model; the node imports no database, policy or
routing module; no P12–P16 module exists (`execution/checkpoint.py`, `execution/handoff.py`,
pairing, automation).

## 24.5 The phase questions, answered

| # | Question | Where |
|---|---|---|
| 1 | execution identity, attempts, retries | §6 |
| 2 | exact plan binding | §7 |
| 3 | P9 authorisation | §7, §10.4, §14 |
| 4 | concrete action canonicalisation | §11 |
| 5 | hooks | §10 |
| 6 | process registry and identity | §15.1, §15.2 |
| 7 | spawn, adoption, reconciliation | §15.3, §15.4 |
| 8 | pause / stop / e-stop | §13 |
| 9 | runtime resource ceilings | §12.2, §12.3 |
| 10 | usage reporting | §12.1 |
| 11 | error breaker | §12.4 |
| 12 | live output | §19 |
| 13 | execution state machine | §8 |
| 14 | task vs execution state | §4.1, §8.3 (D7) |
| 15 | mission interaction | §8.3 |
| 16 | parallel execution | §16 |
| 17 | branch / worktree boundaries | §17, §10.4 |
| 18 | remote / local | V1 is the local node only (§5, `LocalNode`); remote nodes and their transport stay DEFERRED (execution-architecture §9) and nothing in P11 assumes a remote node cannot exist: the manager talks to the node through its contract, never to `proc` directly |
| 19 | resume after Core restart | §15.3 |
| 20 | checkpoints | P11 writes **no** Checkpoint row and stores no transcript. It keeps the facts a checkpoint is derived from — the stream and its offset, the exit, the usage, the workdir's diff in place — and P12 derives checkpoints from them (ADR-0004: derived by Core, never a transcript dump) |

## 25. Decisions

| # | Decision |
|---|---|
| D1 | An `ExecutionManager` on its own thread owns every process; the engine keeps mission logic and dispatch; `LocalNode` is the node contract for the local machine. |
| D2 | Non-blocking supervision replaces `_finish`; tasks run in parallel under §16 admission. |
| D3 | One Execution per dispatch; retries are new rows; processes within an execution are numbered, never overwritten. |
| D4 | `binding_current` at every spawn, resume and hook request. |
| D5 | P9's action stage is the only judge; P11 feeds it canonical actions. |
| D6 | P10's router is asked again on resume and must answer the same account. |
| D7 | A task stays RUNNING for its execution's life; pause and approval waits are execution states. |
| D8 | Six execution edges added (§8.2); no state added. |
| D9 | Charged vs uncharged ends; only task-owned ends spend `max_attempts`. |
| D10 | Resource-attributable ends drop affinity (resource-router §7) — a one-predicate change to P10's `_affinity`. |
| D11 | The e-stop writes the sentinel first, kills by identity, blocks missions, leaves Core disarmed until `rearm`. |
| D12 | The hook channel is a per-execution file mailbox, not HTTP. |
| D13 | A hook that cannot get an answer denies and halts. |
| D14 | Hook tokens: per process, hashed, `hmac.compare_digest` on bytes, monotonic `seq`. |
| D15 | The fake agent runs the real hook script as a subprocess. |
| D16 | `Action` gains `branch` and `host` (in the hash; read by P9's `_values`). |
| D17 | Canonicalisation is a data table; operators and unknowns are `unclassified`. |
| D18 | Workdir and branch recorded before spawn and checked at every hook request. |
| D19 | Worktrees at node-computed paths for `worktree` tasks; no merge in P11. |
| D20 | Usage: adapter-reported only, cumulative on the row, ledgered once at exit. |
| D21 | Runtime ceiling: graceful stop at `must_halt`, uncharged, affinity dropped. |
| D22 | Limit errors: account LIMITED with `limited_until`; own accounts charged. |
| D23 | Breaker: per registered account, resource/auth failures only, state-machines §9 thresholds. |
| D24 | Output: `execution.progress` coalesced, monotonic offsets, redacted, `final_offset` on end; no new transport. |
| D25 | Adopt-or-reconcile at boot; a vanished process is never success. |
| D26 | Registry `run/processes.jsonl`, append-only, compacted at boot. |
| D27 | Real adapters through `Ports.executors`; Claude Code is P11's real adapter. |
| D28 | The engine's parking stamp includes its tasks and executions. |
| D29 | R1 and user-session modes move to P12. |
| D30 | The Codex adapter and G7's Codex function move to P20. |
| D31 | The endpoint-floor fuzz (`test_no_input_to_any_route_is_a_500`) stops multiplying the unauthenticated half of its matrix by bodies and queries, which the server refuses before reading either (§26). |

## 26. CI strategy

- The suite runs on every OS in the matrix as today; P11's process tests use the fake agent (a
  real child process) and never the real Claude CLI. The opt-in real-adapter suite is local only.
- **Windows port exhaustion.** CI run 36258820504 (the P10 push) failed on all four Windows jobs
  from 66 % on with `WinError 10048`: the endpoint-floor test opens a new loopback socket for each
  of `paths × queries × bodies × tokens` per route — up to 840 per `{id}` POST route — and P10's six
  routes pushed the run past the ephemeral-port budget while the earlier sockets sat in TIME_WAIT.
  This is test churn, not a product defect: the server answers every one of them. P11 adds routes,
  so without a change every Windows job fails. Two remedies were weighed. Keep-alive (the
  server moving to HTTP/1.1) is a product change for a test's sake and touches SSE framing; it is
  rejected. **D31** is test-only: the server's documented check order (server.py §4: credential at
  step 6, body at step 8, the query parsed before the route) means a request without a token is
  refused at step 6 whatever its body and query are, so the tokenless half of the matrix is sent
  once per path instead of `queries × bodies` times. Every authenticated input is still sent, every
  route still gets a tokenless request, and a test asserts the order assumption (a tokenless
  request with each junk body is a 401, never a 400 or 500) on one route, so the reduction cannot
  hide a regression. It halves the sockets the test opens; no threshold is lowered.
- Writer throughput stays separate, with its documented Windows floor.
- Mutation suites (P9, P10, P11) run locally before each phase commit, as before.
- The boundary tests of P9 and P10 that P11 legitimately changes (P10 B8, B9 — `core/execution`
  and `node` now exist) are migrated in the same commit that changes them, with the reason in the
  test.

## 27. Deferrals

| To | What |
|---|---|
| P12 | checkpoints, HANDING_OFF / hand-off, pressure and PreCompact, resume of a user's own session (R1), user-session modes, S4's mid-run crossing with hand-off, `retry`/`handoff` routes |
| P13 | verification, review, Integration (merge-back, Core-performed push), removal of verified worktrees |
| P14 | automations (and pausing them on e-stop) |
| P15 | step-up for paired devices, remote stop from a phone beyond the routes above |
| P16 | approval cards, the `/v1/executions/{id}/stream` route, execution UI |
| P20 | `archeus estop` with Core down (registry kill), the Codex adapter, breaker and e-stop drills, fuzzing the canonicaliser |
| deferred | remote execution nodes and their HTTP hook channel |

## 28. As built

**What landed.** `core/execution/{manager,canonical}.py`, `core/application/executions.py`,
`node/local.py`, `harnesses/hook.py`, `harnesses/claude_code/adapter.py`; the engine now only
dispatches and admits (§16), the manager runs on its own `archeus-exec` thread (D1), and the
runtime registers its execution adapters through `Ports.executors` (D27). Six routes and the
`archeus pause` / `archeus estop` verbs (§21). G1 (adoption), G5 (`stop('all')`), G6 (the
action-stage deny), S5 (single-use action approval) and G7's Claude Code function pass on both
bindings.

**Deviations from this gate.**

1. **No migration.** §20.1 promoted `plan_id` and `workdir` to columns. Every new field lives in
   the row's JSON body instead: the admission check (§16) reads a mission's executions, which
   is already an indexed query, and nothing else filters on either field. `Account.limited_until`
   is a body field for the same reason.
2. **Command names** (§20.3) are the ones the code reads as: `record_process` (was
   `record_spawn`), `record_end` (`record_exit`), `pause_work`, `pause_timed_out`, `refuse`
   (`discard`, which also covers an INTENT that never spawned), `adopted`, `lost`,
   `account_limited`, `accounts_tick` (the breaker) and `approval_answered`. `Work.record_spawn`
   and `Work.record_exit` survive as thin delegates to them, so there is one implementation; the
   P3.5 `Work.reconcile` is gone, replaced by the manager's adopt-or-reconcile.
3. **Three events beyond §20.2**: `execution.prepared`, `execution.hook` and `execution.halted`.
   The writer requires an event for every mutation, and these three commands change a row
   without moving its state.
4. **Task branches are `archeus/<mission-id>.<task-key>`**, one segment, not the
   `archeus/<mission-id>/<task-key>` of §17: P9's profiles bound commits to `archeus/*`, and
   `*` never crosses a `/`, so the two-segment name was a branch no profile could ever allow.
5. **Worktrees are never removed by P11.** §17 removed one for an execution that ended
   ABANDONED. A task's attempts share one worktree path and branch, so removing it after a
   later attempt was abandoned would discard an earlier attempt's work, and the next attempt's
   `worktree add -b` would then fail on the branch left behind. Removal is P13's, with
   merge-back.
6. **G5 waits for `execution.started`**, not for the mission to be EXECUTING: EXECUTING now
   precedes the first dispatch (D7), so the old wait raced the spawn.
7. **Charging (D9) gained two rules.** A resource or auth failure on a harness's OWN account
   (one with no registered Account) is charged, because no breaker can see that account and
   an uncharged end there would retry forever. A halt that Core did not ask for (the hook
   failed closed) is charged for the same reason.
8. **The opt-in real-adapter suite** is `tests/v1/integration/test_claude_code_live.py`
   (`ARCHEUS_REAL_HARNESS=1`), not a contract-suite file, because it needs the integration rig's
   database fixture. It has not been run: it spends real quota. The recorded stream G7 reads was
   made from ONE real headless call (Haiku, one turn, no tools, about $0.12), stripped of the
   recording machine's hook output, thinking text and tool inventory.
9. **Restart semantics changed for P3.5's tests.** P3.5 killed a live process at boot and
   retried the task; §15.3 adopts it. The five P3.5 restart tests, P9's E7 and P10's B8 ("only
   the fake harness is registered") were migrated with the reason written in each.
10. **Two plan items this gate did not name went with D29.** The plan's P11 lists a pi adapter
    for user sessions and the `main.build_launch_command` preparation seam for the
    interactive-attach path. Both exist only to serve user sessions, which D29 moved to P12,
    so both are P12's too; P11 builds neither.

**Defects found while building it, all fixed with a test.** `binding()` accepted a SUPERSEDED
plan that was still the highest version; resuming a mission while disarmed let `advance` read
P9's e-stop DENY as the mission's failure (the engine now does not advance live missions while
disarmed); two concurrent hooks could take the same request number (`_reserve` now takes the
number with an exclusive lock file); `git push origin :branch` was not classed as destructive;
the endpoint-floor fuzz exhausted Windows' ephemeral ports once P10's routes were added (D31).

**Mutation.** `tools/mutate_p11.py`: 30 mutants, one per §24.3 invariant, all killed. Three
needed a test of their own rather than a different safeguard: `E14` (nothing starts while
disarmed), `S07` (a resume asks P9 again), and E10's `Blunt` adapter, which proves the node's
own identity check and not only the adapter's. Two model an acknowledging command rather than a
new edge (X19, X20): the state table is the last guard against a duplicate end or stop, and
what those mutants measure is that the command refuses instead of answering as if it had
worked. P9's suite (36) and P10's (36) still kill everything; P10's R30, R33 and R36 were
retargeted to where P11 moved the code they guard.
