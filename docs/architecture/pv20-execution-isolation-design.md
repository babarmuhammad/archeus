# PV-20 — Execution OS-isolation: design decisions

**Status:** ARCHITECTURE DECISIONS APPROVED AND DOCUMENTED (§6 items 1–17, and the blocker decisions
A1–A6 with the A7 correction, §6 items 18–24) — **not implementation authorization**; implementation: slice S0 only (§7.4 Gap A, the three-state sentinel determination, 2026-10-08), the isolation mechanism backend selected 2026-10-29 (Microsoft MXC, ADR-0053 amended) but not implemented or authorised for native runs; empirical evidence outstanding · **Track:** V1.x
security remediation · **Date:** 2026-10-07 · **Prerequisite:** [PV-13 study](pv13-windows-os-confinement-study.md)
(delivered 2026-10-07) · **Source:** ADR-0051 §5; the P20 slice-G verification findings G1 and G2
(both Critical, open — see [p20-design-gate.md](p20-design-gate.md) §12 items 92–97) · **ADR:**
[ADR-0053](decisions/ADR-0053.md) (written 2026-10-07, as ADR-0051 Decision 5 requires)

> **No implementation.** This document records the PV-20 design decisions the user has ruled on,
> the boundaries PV-20 must define, and the evidence it must produce. It builds nothing, changes no
> production code, and does not claim the boundary exists — that claim is earned only when the
> implementation and the acceptance evidence below both pass. Attack surface is described at the
> boundary / capability / evidence / impact level; no real secret value and no extraction procedure
> appears here, and the acceptance plan uses synthetic fixtures, sentinels and boolean assertions
> throughout.
>
> **Evidence status.** The PV-13 empirical capability/ACE spike was **not performed**. Every
> statement below about the exact grants, capabilities or Windows behaviour an isolated execution
> needs is marked **DESIGN PROPOSAL — UNVERIFIED** and stays so until evidence exists. Reasoning in
> this document is not a substitute for that evidence.

## 1. What PV-20 is remediating

Slice G's verification pass confirmed the ADR-0051 §3 OS-confinement gap is reachable in practice.
At the capability level, and with no procedure given:

- **Finding G1 (Critical, open) — reach of user-owned credential authorities.** An execution
  running under the user's OS identity can reach user-owned credential authorities and stores
  whose secrets would authorise pushing, publishing, or registry/SSH access. P11's environment
  hygiene (`CAPABILITY_ENV`: prompts off, `GIT_ASKPASS` empty, `SSH_AUTH_SOCK` removed, empty
  `credential.helper`) works exactly as designed, but the secrets do not live in the environment —
  they live in **stores the OS identity owns**, which clearing an environment variable cannot
  remove.
- **Finding G2 (Critical, open) — reach of the local Core control boundary.** An execution can
  reach the local Core authentication/control material (the privileged local token and `run/`
  control state), which to Core's loopback API is the full-scope local principal past step-up —
  enough to defeat approval, policy and the e-stop if used.
- **Finding G3 (Medium) — network egress — is P23's,** not PV-20's. PV-20 records it as a
  dependency and does not solve it.

**These are OS-boundary issues, not P11 implementation defects.** P11's four settings function as
designed; the gap is that nothing below the per-tool hook confines what a process with the user's
identity can physically reach. This framing is load-bearing and must not be rewritten as a P11 bug.

## 2. Mechanism (confirmed, §6.1)

**Mechanism replacement:** The PV-20 baseline remains AppContainer + Core-held Job object. Following the owner’s 2026-10-29 decision, Microsoft MXC’s `processcontainer` backend supplies AppContainer establishment and launch. Core supplies and exclusively holds the outer kill-on-close Job. MXC replaces the hand-built profile/token/AppContainer-spawn implementation, not the identity, authority, resource or lifecycle contracts. ADR-0053 §1 governs policy, network, UI and dependency constraints.

- **A separate standard user** remains the later escalation/fallback design path, used only if
  AppContainer evidence later proves insufficient and only by a **new owner decision** (ADR-0053
  §1); every boundary below is expressed so it can be substituted without re-deciding the
  contracts.
- **Windows Sandbox** remains an optional maximum-isolation tier, not the V1.x baseline.

Whether AppContainer can run a legitimate code-change turn under deny-by-default is the open
empirical question of §3.1: **DESIGN PROPOSAL — UNVERIFIED.**

OS isolation and Core effect-bounding (§3.6) are **complementary layers**; neither substitutes for
the other, and both are required.

## 3. The boundaries PV-20 must define

### 3.1 Identity boundary

- **What executes untrusted agent work.** An **execution identity that is not the user's OS
  identity**: under the baseline, an AppContainer identity; under the escalation path, a dedicated
  standard user.
- **Creation / lifecycle replacement:** MXC establishes and disposes the AppContainer resources for each execution-specific principal. Archeus records the observed principal, generation and owned resources, proves separation and admission invariants, and refuses uncertain or reused authority. Fresh verifier principals remain mandatory. No standing OS account, stored OS credential or elevation is introduced by this backend decision. Windows-managed registrations and storage effects require an explicit run inventory; no account-home access is implicitly authorized.
- **Granularity (R7 — implementation constraint, not an owner decision; §6).** One
  execution-specific identity/principal, created before spawn and torn down after the execution;
  other executions' state is inaccessible to it; grants on shared runtime material (install paths)
  are read/execute only, and that material holds no user secrets; Core-owned state is never
  granted. Whether the per-execution principal is a separate profile or a per-execution capability
  is a mechanism choice: **DESIGN PROPOSAL — UNVERIFIED**. Sharing a principal between executions
  would need a new owner decision.
- **Grants it receives.** Deny-by-default. The proposed runtime grant inventory — every component
  that must execute or be read inside the boundary — is below. **Every row is DESIGN PROPOSAL —
  UNVERIFIED**: neither the set nor the access level of any row has been established.

  | Component inside the boundary | Proposed access | Status |
  |---|---|---|
  | The Claude CLI and the runtime it needs (install paths, required runtime paths) | read/execute | DESIGN PROPOSAL — UNVERIFIED |
  | The child shells and tools a code-change turn runs (shell, git) | read/execute | DESIGN PROPOSAL — UNVERIFIED |
  | The Core-provided hook: its interpreter (today Core's own Python, `manager.py`) and the hook script (`harnesses/hook.py`) | read/execute | DESIGN PROPOSAL — UNVERIFIED |
  | The execution's own workspace content (its separate execution repository, or for an execution with no project an empty execution-private workspace — §3.2, A1) | read/write (§3.2) | DESIGN PROPOSAL — UNVERIFIED |
  | The execution repository's own metadata a legitimate local code change needs (never the user's `.git`) | per §3.2 categories 2–3 | DESIGN PROPOSAL — UNVERIFIED |
  | Its own request input, Core's responses to it, and the sentinel state | per §3.3 authority table and §7.5 classes 1–3 | DESIGN PROPOSAL — UNVERIFIED |
  | Core-authored spawn configuration (Archeus's hook settings, the MCP configuration, any Core-materialised ADR-0049 opt-in — A2) | read only; Core writes (class 2's authority) | DESIGN PROPOSAL — UNVERIFIED |
  | Per-execution runtime state (temporary and home-equivalent directories the processes need, including the per-execution `CLAUDE_CONFIG_DIR`, which holds no provider login — A2) | read/write, per execution (class 7) | DESIGN PROPOSAL — UNVERIFIED |
  | Model-provider access | only through Core's broker (R3-B, §6.15); **no provider credential inside the boundary** | approved target — production CLI feasibility UNVERIFIED |
  | Network, including reach of Core's loopback listener | P23's decision; any loopback reach R3-B needs is subject to R1 | not proposed here |

  Nothing outside this inventory is granted. Any row found necessary but absent, or any row that
  proves to widen reach beyond the intended boundary, is a design change, not an implementation
  detail.
- **What it explicitly cannot access.** The user's profile and home-directory secret material; any
  user-owned credential authority or secret store; the account home (the Claude configuration
  directory holding the provider login), a copy of it, or any configuration from it except as
  Core-materialised data (A2); the user's project root and the user's repository metadata (§3.2,
  A1); `run/local-token` and all Core-private and lifecycle state (§7.5 classes 4–6); other
  executions' state; the rest of `ARCHEUS_HOME`.
- **Opt-ins inside the boundary (A2, §6 item 22).** ADR-0049 opt-ins enter only as Core-materialised
  data, and only when they carry no credential authority. **No MCP opt-in is admitted to an
  isolated execution** (confirmed by the owner, 2026-10-07; changing it needs a new owner
  decision): Core cannot establish from a server definition that it carries no credential. A settings item or plugin that would bring an MCP
  server, an environment block or a credential helper is excluded and recorded. The account-level
  CLAUDE.md loads only if opted in. No legacy account-home behaviour is preserved silently.
- **Network containment.** MXC implements the selected backend’s network restrictions; Archeus does not maintain a parallel hand-built firewall mechanism for this path. P23 retains network-policy ownership. Default egress, ingress and host-loopback access are denied. Any broker transport exception is explicit, narrowly scoped and tested for both intended reachability and forbidden destinations, including descendants and alternate connection APIs. Proxy environment variables are routing hints, not containment. No machine-wide firewall rule or loopback exemption is silently installed. Broker routing never grants execution-origin requests privileged Core authority.

- **UI policy — proposal pending evidence and owner decision.** The proposed default blocks the UI subsystem. Exact `ui.disable` and `ui.allowWindows` values and their interaction must be verified against the pinned SDK schema; neither may be inferred from a tool’s failure. Tools requiring a window station or UI subsystem remain unsupported under that default until separately tested and explicitly admitted. No automatic UI enablement or retry occurs after an initialization failure. Enabling UI does not imply permission for desktop input, screen capture, clipboard, microphone, interactive login or other user-session authority.

- **Dependency and update policy.** The implementation uses an exact reviewed MXC SDK/runtime version, locked transitive dependencies and recorded artifact hashes. Package installation uses `--ignore-scripts`; required artifacts must be verified without silently re-enabling lifecycle scripts. License notices, dependency inventory, package integrity, provenance where available, vulnerability findings and runtime DLL inventory are reviewed before admission. Updates require a reviewed change, compatibility and security evidence, and explicit activation of the new pinned version; no runtime auto-update, floating version or automatic weaker fallback is permitted.

### 3.2 Workspace and repository boundary (§6.7)

- **Repository topology (R4a-B, §6.13): a separate execution repository, imported as data.** An
  execution works in an execution repository separate from the user's repository. The user's
  `.git` (config, hooks, refs, objects) is **not** exposed to it through a linked worktree: a linked
  worktree shares refs, packed refs, objects, config and hooks with the user's repository at
  directory level, so it cannot isolate repository metadata. Core brings an execution's result into
  the user's repository by an import that treats it as data and never honours the execution
  repository's configuration, hooks or refs. Today's location
  (`<ARCHEUS_HOME>/worktrees/<project>/<mission>/<task>`, `manager._workspace`) is the starting
  point; the exact location and on-disk layout are implementation details. That the import can be
  made data-only is **DESIGN PROPOSAL — UNVERIFIED**.
- **Every execution's workspace (A1, §6 item 19).** Every isolated execution, of every task kind,
  runs in a Core-established workspace distinct from the user's project root, the user's `.git`, and
  §7.5 classes 1–6:

  | Project | Workspace |
  |---|---|
  | first root is a git repository (any task kind) | a separate execution repository seeded from the recorded base revision (P13 D12: the mission branch when it exists, otherwise HEAD) |
  | first root is a git repository with a detached HEAD | the same, seeded from the recorded commit |
  | no project | an empty execution-private workspace in class 7 — never the bare `run/exec/<id>/` |
  | first root is not a git repository | **structurally refused** |

  `workspace_mode: in_place` is withdrawn for isolated executions. A structural workspace
  impossibility is rejected **before dispatch** and never enters a spawn/retry loop; a transient
  workspace or isolation failure is an isolation-establishment failure (§3.4: no spawn, charged and
  re-dispatched as P11's O7 decides). Repository changes of every task kind reach the user's
  repository only through the import below and P13's merge-back. An execution therefore sees only
  the seeded revision — not the user's uncommitted, untracked or ignored files.
- **Seeding, import and the canonical revision (A5, §6 item 20).**
  - **Seed:** a copy of the base revision only. Never a linked worktree, shared objects,
    alternates, hardlinks, or any other mechanism that exposes the user's `.git`.
  - **Untrusted:** everything in the execution repository — its `.git/config`, hooks, refs, objects
    and index, and the attribute and configuration files that affect git behaviour (in-tree
    `.gitattributes`, `.gitmodules`, `.lfsconfig`). No Core git operation honours any of it.
  - **Core never runs git, or any program that reads git configuration, against an execution
    repository under the user's identity.** Reading its HEAD or branch, its status, a merge base, or
    snapshotting inside it are all excluded.
  - **Import:** after the execution, Core copies its working tree **as data** into a Core-owned
    import repository. **Core's pinned import commit is the canonical revision**, recorded in Core
    state; the execution's own commits and HEAD are claims. Core's snapshot is that import commit,
    taken after the copy.
  - **Core-pinned configuration:** every Core git operation over execution-derived content — the
    import commit, diffs and other git facts, the merge into the mission branch, materialising a
    verification checkout, push — runs under a Core-pinned configuration that prevents
    execution-controlled hooks, drivers and configuration from running.
  - **Verification:** R4b verifies a fresh checkout of the Core-recorded revision, materialised by
    Core (§3.9).
  - That the copy seed, the working-tree import and the pinned configuration can be built as stated
    is **DESIGN PROPOSAL — UNVERIFIED**; the exact mechanics (including link and reparse-point
    handling) are implementation details.
- **"Workspace writable" does not mean "repository fully writable."** Four categories, kept apart:
  1. **Task content the execution may modify:** the files of its own workspace, as its authorised
     work.
  2. **Repository metadata it may read:** what the local Git operations of a legitimate
     `code_change` need to read — in its own execution repository, never the user's. The exact set
     is **DESIGN PROPOSAL — UNVERIFIED**.
  3. **Repository metadata it may modify:** only what the local Git operations required for a
     legitimate `code_change` on its own task branch need — in its own execution repository. The
     execution receives **no authority over the user's repository metadata**. The exact set is
     **DESIGN PROPOSAL — UNVERIFIED**.
  4. **Operations Core performs under the user's identity:** push, publish and every other
     privileged repository effect, plus Core's own snapshot, the data-only import and merge-back.
     Core stays authoritative for these; the execution holds no push credential. None of them
     honours configuration or hooks an execution influenced, and **none of them executes
     execution-influenced code** — running such code is verification, which is not a category-4
     operation (§3.9). Under A5 none of them runs against the execution repository, and each runs
     under the Core-pinned configuration. **Confirmed by the owner (2026-10-07; ADR-0053 §7 A5):**
     no repository-controlled or execution-derived git extension executes during these operations —
     repository-controlled hooks (the user's own included), filters, fsmonitor, diff and merge
     drivers, submodules, LFS transfer mechanisms, and any other execution-derived git extension —
     and the Core-pinned configuration prevents their execution. **Core does not push content whose
     publication requires executing any of those mechanisms** (for example LFS-dependent content);
     that capability needs a separate owner decision.
- **Execution-produced repository state is untrusted input.** When Core later operates on state an
  execution produced, it treats that state as untrusted. This is enforced by structure — the
  data-only import (R4a-B) — and by R4b: execution-influenced code never runs under the user's
  identity (§3.9).
- **In-place / live-project-root behaviour (P11 §17) is not an approved PV-20 fallback.** A1
  withdraws it for isolated executions: no execution runs in the user's project root, and no
  failure falls back to it (§3.4). Any future supported alternative needs its own security analysis
  and explicit architectural approval (§6.3).
- **Cleanup replacement:** On clean end, crash or e-stop, Core first proves the owned process tree quiescent, then invokes the pinned MXC disposal path and verifies grant/resource disposition. Unknown ownership, incomplete disposal or stale access quarantines the generation and blocks reuse. Restart reconciliation never adopts a live isolated process or deletes resources based only on a stale journal entry or name.

### 3.3 Core boundary and mailbox authority (§6.6)

**Mailbox insertion:** MXC policy implements filesystem exposure for the existing seven resource classes. Requests are writable; responses, spawn configuration and sentinels are readable but not writable; lifecycle, halt and Core-private state remain inaccessible. Broad writable ancestor grants are forbidden. Hostile creator descriptors, inherited handles and aliases require native evidence; policy serialization alone does not establish this table.

- **The mailbox is a split-authority boundary,** not a generic execution-writable directory. The
  execution reaches Core only through its own request/response mailbox and reads the STOP
  sentinel. It receives only the data its task needs.

  | Artifact | Written by | Read by | Authoritative |
  |---|---|---|---|
  | Request files | execution | Core | Core decides; a request is only a request |
  | Response files | Core | execution | Core |
  | Core-authored spawn configuration (hook settings, MCP configuration, materialised opt-ins — A2) | Core | execution | Core |
  | STOP sentinel (global) and per-execution STOP / PAUSE / HANDOFF flags | Core | execution | Core |
  | Core-owned lifecycle/control state (spawning marker, pid record, `ended` tombstone, prompt, stream) | Core | Core | Core |
  | Halt / pause / handoff / approval state | Core only — the execution cannot author it | — | Core |
  | `run/local-token` | — | **not accessible to the execution** | Core |
  | Other executions' directories | — | **not accessible to the execution** | — |

  The prompt and stream reach the process as Core-opened handles (`base.spawn`), not as files the
  execution opens. A file's location inside the execution's filesystem view never makes it
  trusted. The stream's **content** is execution-authored even though Core holds its handle: a
  `result` in it is a claim, never a process exit (A7). An `ended` tombstone Core wrote itself is a
  Core observation. **The exact Windows ACE implementation of this table is DESIGN PROPOSAL — UNVERIFIED.**
- **The hook's halt and PreCompact records (R5 / H2, §6.16).** Today the hook writes `halted.json`
  and `precompact.json` into the execution directory, and Core reads the first as
  `ExecutionResult.halted`. Under this table:
  - **Core's classification is authoritative**, held in Core-owned durable state (§7.5 class 5).
  - The hook's halt and PreCompact records are **untrusted reports** carried on the execution's
    request input (§7.5 class 1). H2 governs their effect: a report can move an execution's
    classification **only toward a non-advancing state**. It can never manufacture success, an
    approval, a response, a flag or any other Core-authored state. A PreCompact report can only
    raise context pressure; Core decides any handoff.
  - An execution that ends while PAUSING or HANDING_OFF and that Core cannot classify from its own
    state resolves to halted at the boundary, **never ENDED_OK**.
  - After a Core restart, reports found are read as claims.
  - **The lifecycle contract (A7, §6 item 24).** `ENDED_OK` is an execution-level fact, not
    success: Core records it only from its own observed exit 0 of an execution that was RUNNING
    with no outstanding Core control request. From PAUSING or HANDING_OFF it needs a cause Core can
    classify from its own state, and no execution report is one: PAUSING otherwise resolves to
    PAUSED and HANDING_OFF to ENDED_HANDOFF, or either to ENDED_ERROR on a non-zero exit. An
    execution-authored stream `result` is never a process exit; an `ended` tombstone Core wrote
    itself is. Ambiguous termination is non-advancing. ENDED_OK moves a task only to VERIFYING;
    PASSED needs authoritative verification evidence, and a missing verifier never yields it.
    ERROR versus AWAITING_HUMAN, and PAUSED versus failed for an execution PAUSING at a Core
    restart, are non-security policy details.
- **What authentication is exposed to the execution.** The per-execution hook token
  (`ARCHEUS_HOOK_TOKEN`), which authorises the mailbox and nothing else; and, under R3-B (§6.15),
  whatever execution-scoped credential Core's provider broker issues, which carries **zero Core
  scopes**, is never accepted by Core's API, and is meaningful only to the broker. Neither confers
  a privileged Core action (§3.6). **No provider credential and no user-owned credential is exposed,
  and the privileged local token is never exposed.** R3-B is an approved target architecture, not
  an established fact: whether the production Claude CLI can work through a broker is
  **UNVERIFIED**, and if it cannot, scoped per-execution credentials (R3-A) need a separate,
  explicit owner security decision — until one of the two is viable, isolated Claude Code
  executions do not run.
- **Two layers, both required:**
  1. **Read-bounding (OS):** the execution identity cannot read the local token or Core control
     state.
  2. **Effect-bounding (Core) — a hard requirement, not *merely* defence in depth (§6.2, ADR-0051
     superseding decision):** Core independently refuses every privileged effect to an
     execution-originated request, whatever the execution has managed to reach (§3.6).
     **Origin (R1-A, §6.14; scope A3, §6 item 23):** the OS attests the connecting peer's origin,
     and R1-A is an **allowlist**:
     - A trusted local §3.6 request requires **both** (1) an OS-attested connection origin that
       satisfies the approved user-origin condition **and** (2) arrival through an approved trusted
       path that is neither an execution-influenced deputy nor a forwarding hop. User identity
       alone is not sufficient.
     - Direct approved user-origin requests may receive §3.6 authority; approved paired-device
       requests receive only what P15 and D10 permit.
     - **No §3.6 authority, whatever credential is presented:** execution-originated requests;
       verifier-originated requests; forwarding hops; proxies; undetermined origins;
       execution-influenced user-identity deputies. A forwarded request is never direct local origin
       merely because the forwarder runs as the user.
     - **Hop rule:** a hop that does not carry its originator's origin is permitted only if no
       execution or verification identity can reach it, or if it has no route to Core — the provider
       broker (no Core route), the remote-access tunnel (paired credentials only, never local), and
       any user-identity proxy (must be unreachable; P23).
     - **Deputy rule:** no Archeus-owned process running as the user executes, or loads as
       configuration, execution-influenced content; Archeus's own model calls (planner, review,
       knowledge passes) take it only as prompt data, and clients render it only as data.
     - The verifier has no Core route and cannot become a privileged deputy (§3.9).

     R1-A is sound only because every path by which execution-influenced code could run under the
     user's identity is closed: verification (R4b, A6), the import and Core's repository operations
     (R4a, A5), every harness (A4), Archeus's own calls and clients (A3), and forwarding hops (P23).
     Attestation on Core's local transport is **DESIGN PROPOSAL — UNVERIFIED** and its mechanism is
     not chosen here; if it cannot be established, nothing is substituted silently — a transport
     change, or step-up / presence for the whole closed set (R1-B), is a new owner decision.

### 3.4 Process boundary and isolation establishment (§6.11)

- **How processes are spawned.** `base.spawn` today launches a hidden-console detached process
  (`proc.spawn_detached`). Under isolation it launches the child **into the execution identity,
  inside its Job object**. This is a new spawn mechanism behind the existing seam.
- **How confinement is inherited.** The design requires every descendant to stay inside the
  execution identity and the Job. That AppContainer and the Job provide this for the real CLI and
  its child shells is **DESIGN PROPOSAL — UNVERIFIED**.
- **"Isolation established" is an explicit pre-spawn invariant.** Before untrusted execution
  starts, all of the following must hold:
  1. the execution identity exists;
  2. the required resource grants (§3.1 inventory) are established, including the execution's
     Core-established workspace (§3.2, A1);
  3. prohibited broad grants are absent;
  4. the Job object exists;
  5. the required Core/mailbox boundary (§3.3) exists;
  6. the isolated spawn path is selected.
- **If any condition does not hold: fail closed — the untrusted execution does not start.** No
  silent fallback to the interactive user's security context (§6.3), and no configuration setting
  disables the invariant. The invariant governs every execution a production Core dispatches,
  whatever its harness (A4, §3.8). That these conditions can be established and checked is
  **DESIGN PROPOSAL — UNVERIFIED**.
- **SpawnFailed / O7 — external P11 dependency (R8).** How an isolation-establishment failure is
  charged and whether it re-dispatches interacts with P11's `SpawnFailed` behaviour (O7, deferred
  to P11; p20-design-gate §12 item 72). PV-20 does not resolve O7; it requires P11's decision
  before implementation. Whatever O7 decides, a spawn failure never bypasses isolation.
- **MXC launch contract.** Core compiles a closed, versioned policy from its approved resource inventory; execution-controlled policy fragments, backend selection and launcher flags are refused. The launcher/runtime and policy schema are pinned. Core starts the launcher suspended, assigns it to the Core-held Job, verifies assignment and permitted handle inheritance, then resumes it. Equivalent atomic assignment is acceptable only when verified. A launcher that cannot satisfy this ordering is not admitted. Filesystem, network, UI, environment and resource controls are independently checked against the actual launched process. No permissive backend or unisolated fallback is allowed.

### 3.5 Credential boundary

The design must ensure an execution **cannot rely on the user's credential authority merely
because it runs under the user's OS identity** — which is why the identity boundary exists at all.
Covered at the boundary/capability level, no store named with a procedure and no value reproduced:

- **Git / provider credentials** — governed by denying the execution identity access to the stores
  and authorities these live in (and, under the escalation path, by DPAPI's per-user binding).
- **SSH credentials** — the user's key material and agent are outside the execution identity's
  granted set.
- **Package / registry credentials** — user-profile token files and OS credential-vault entries are
  ungranted.
- **Windows credential stores** — the user's vault is per-user and outside the granted set.
- **Other user-owned secret stores** — excluded by deny-by-default; any that proves reachable under
  AppContainer is the trigger to consider escalating to the separate-user path, which is a new
  owner decision (§2).
- **Model-provider credentials** — the execution holds none: Core brokers provider access (R3-B,
  §6.15), conditional on production Claude CLI feasibility (§3.3).

That this coverage is complete is **DESIGN PROPOSAL — UNVERIFIED**.

### 3.6 Effect boundary (hard requirement, §6.2)

"Cannot read the secret" is **not** the only requirement. Core must independently enforce the
authorization boundary for privileged effects. An execution-originated request does not acquire a
privilege because the execution environment has reached some resource, and possessing an
execution-context credential (the hook token) grants none of the following. The privileged set is
**closed and explicitly enumerated**:

- publishing / pushing — Core's action, gated by approval;
- privileged Core control (the local principal's scope);
- approving any pending request, including the execution's own;
- policy modification;
- re-arm after a halt — refused to an execution origin by this boundary, through R1-A origin
  attestation (§3.3). **D10 is not the mechanism that refuses an execution:** D10 is the
  paired-device rule only (PIN step-up on `POST /v1/rearm` from a paired, non-local device; the
  local desktop asks none), it is approved but blocked on V2-3 (p20-design-gate §14.B), and under
  P9 D16 / P15 §6.6 a local client satisfies step-up by being local;
- authoring halt / pause / handoff / approval state (§3.3).

**This list is the canonical closed set.** Any other document's enumeration (ADR-0051's 2026-10-07
note, ADR-0053 §2) defers to it. Anything not in an execution's authorised capability set is
refused. Adding an effect to the privileged set is a design change. Execution origin is established
by R1-A (§3.3). That Core enforces this is **DESIGN PROPOSAL — UNVERIFIED** until implemented and
tested.

### 3.7 Lifecycle, failure and recovery (§6.8, §6.10)

**Lifecycle insertion:** R6-A applies to the outer Core-held Job. MXC may own inner containment Jobs, but must not hold or recover the outer Job. Core death must terminate launcher, bridge, agent, children and grandchildren, including processes already running when the Core dies. The smoke’s two-process observation is corroboration, not acceptance of this product-path property.

- **Job = process-lifetime authority.** An execution's processes live and end with its Job.
- **Core registry = accounting/state,** not lifetime authority.
- **Job ownership (R6-A, §6.17): Core only.** Core is the sole holder of each isolated execution's
  Job, and the Job is configured so that Core's death terminates the isolated process tree. No
  non-Core component holds lifetime authority, and no reference that could recover the Job exists
  outside Core's process. That a Job can be configured and held this way is **DESIGN PROPOSAL —
  UNVERIFIED**.
- **Core restart = reconciliation of records.** Under R6-A no isolated process outlives the Core
  that held its Job, so a restarted Core has nothing live to adopt: it reconciles its records and
  resolves every remaining non-terminal execution through terminate / reap / fail, and reclaims
  stale profiles and grants. It must not silently detach an execution from its Job, nor create a
  new security relationship around an orphaned process. **A live isolated process is never
  re-adopted**, and nothing is trusted from an execution-writable file (§3.3). An exit Core
  committed before it died stays recorded; an `ended` tombstone Core wrote is collected; nothing
  the execution wrote (stream `result`, `pid.json`, halt or PreCompact report) is collected as an
  exit (A7). The same holds for verifier principals (A6): their Jobs die with Core, and a
  verification cut short is missing evidence, never PASSED.
- **Deterministic lifecycle takes precedence over re-attachment.** The restart re-attach guarantee
  of the current process I/O contract (`base.py`; execution-architecture §3.1, §4; p11-design-gate
  §15.3) is **withdrawn for isolated executions**.
- **e-stop — one Core-less stop mechanism (item 83).** Core up: Core ends the execution's Job. Core
  dead: under R6-A no isolated process survives. Core hung or unreachable: the item-83 path — the
  STOP sentinel plus the registry kill (`archeus estop`, execution-architecture §10 path 2) — stays
  **the only Core-less stop mechanism**. The Job is the execution lifetime boundary, **not a second,
  independent Core-down stop authority**; the registry is the Core-less kill's instrument and the
  accounting record, not lifetime authority. That the registry kill can terminate an isolated
  process, and that the whole arrangement holds across the restart boundary, is **DESIGN PROPOSAL —
  UNVERIFIED**.
- **Sentinel state has three values (§6.10):** absent, present, and **cannot be determined**. If
  the execution cannot reliably determine the STOP sentinel's state, the requirement is
  **fail-closed** (halt), never "treat as absent". This is a PV-20 design and acceptance
  requirement; the hook makes the determination since slice S0 (§7.4 Gap A), which is not its
  verification under PV-20. **Ordering requirement:** the explicit three-state determination must
  be implemented **no later than** the change that separates the sentinel from the mailbox (§7.5);
  S0 satisfies it. Before S0 an inaccessible sentinel read as absent, and the observed fail-closed
  result came from the mailbox write failing beside it; separating the two without the
  determination would have failed open. The item-83 sentinel stays valid under PV-20
  only with this requirement met.
- **Isolation setup failure** → fail closed, do not spawn (§3.4); charging is O7's (P11-owned, R8).
- **Child-process failure** → unchanged from P11; the Job reaps the tree.
- **Core communication failure** → the hook's existing fail-closed path (no answer / unreadable /
  crash → deny and halt) is preserved.
- **Cleanup failure** → a grant or profile that cannot be removed is quarantined and retried on
  boot; a stale grant must never widen another execution's reach.
- **Upgrade / migration** — PV-20 ships as a **V1.x security remediation** (§6.4). Every
  execution's workspace becomes a Core-established workspace — a separate execution repository for
  git projects (§3.2, A1, A5); executions stop receiving the account home (§3.1, A2); the local token
  stops being readable by executions; the hook channel moves to the split-authority mailbox (§3.3,
  §7.5); verification moves to per-verification confined principals (§3.9, A6). How existing
  worktrees, and existing tasks recorded with `workspace_mode: in_place`, migrate is implementation
  work; neither may fall back to the user's project root.

### 3.8 Harness scope (§6.9)

- **The real Claude Code execution path is the production security target.** Every PV-20 property
  is claimed for it, and only on evidence from it.
- **Fake-agent and test harnesses** need not reproduce AppContainer mechanics. A harness that
  claims to test a PV-20 property must model the corresponding authority restriction. **Passing a
  fake-harness test is never proof that Windows AppContainer confinement works.**
- **Sandbox harnesses** (Codex `--sandbox`) remain separate security mechanisms; PV-20 does not
  claim their properties or substitute for them.
- **Every harness runs under PV-20 (A4, §6 item 18).** Every execution a production Core
  dispatches, whatever its harness, runs under the PV-20 execution identity and inside its
  Core-held Job. A harness's own sandbox is an additional inner layer, never a substitute; a harness
  that cannot launch inside the PV-20 identity is **not eligible for production dispatch**; no
  harness has an exception. Fake and test harnesses are not production-dispatchable. Evidence:

  | Path | What its evidence can establish | What it can never establish |
  |---|---|---|
  | Production Claude Code | every PV-20 property, on evidence from this path | — |
  | A sandbox harness (Codex) | a PV-20 property, only on evidence from its own real path once it launches inside PV-20 | anything from its own sandbox's evidence alone |
  | Fake / test harness | that a modelled authority restriction behaves as modelled | AppContainer confinement, or any production property |

  Codex is not installed (p20-design-gate §1.5), so today no harness loses eligibility.

### 3.9 Verification boundary (R4b, §6.12)

Core-run verification is **inside PV-20's security boundary**. A check's test and build commands
are category-1 content (§3.2): the execution can write them. Today Core runs them in the workspace
under the user's identity (`node.run_check`, called from `core/verification/evidence.py`), which
gives execution-written code the reach behind G1 and G2 outside every other layer, and would make
R1-A's attestation see that code as the user.

- **Execution-influenced code never runs under the user's identity.** This covers task and mission
  verification alike: the mission branch holds merged execution output.
- **It runs under a confined verification identity** (Option 2): distinct from both the user's and
  the execution's identity; no access to Core state, credentials or the local token; its own Job;
  a checkout at the recorded revision with no live writer; network per P23's policy.
- **One fresh verifier principal per verification (A6, V-1, §6 item 21).**

  | Dimension | Rule |
  |---|---|
  | identity | distinct from the user and from every execution; created for one verification (one task revision's check run, one retry, or one mission-criterion run); never reused; destroyed after Core records the result |
  | Job | its own, held only by Core, so it dies with Core (R6-A applies); recorded in the process registry the item-83 stop uses (§3.7) |
  | workspace | a fresh checkout of the Core-recorded revision (§3.2, A5), materialised by Core |
  | writable state | its own scratch, home and temporary state, for that verification only |
  | cache | **none persistent or shared** |
  | toolchain | only the minimum runtime/toolchain grants the verification needs; shared material read/execute and holding no user secrets |
  | network | only if P23 explicitly permits it |
  | repository access | its own checkout only — no execution repository, no import repository, no user `.git` |
  | Core | no Core database or state, no mailbox, no hook token, no local token, no route to Core's listener or other loopback |
  | credentials | no user, provider or broker credential |

  **Maximum authority:** a subset of the execution runtime/tool grants plus its own checkout and
  scratch state, with network only if P23 explicitly permits it. One verification can never
  influence another verification's state, credentials, authority or result. A check that needs
  anything outside these grants yields missing evidence — ERROR or AWAITING_HUMAN — never PASSED.
- **Core holds the process handles and records the exit code and output itself.** The verifier
  writes no evidence. This keeps P13's "authoritative" class meaning *Core observed the outcome of a
  command at the recorded revision* (p13-design-gate §8.1).
- **Fail-closed degraded mode** (Option 3): if the confined verification identity cannot be
  established, no execution-influenced code runs, and the check is missing evidence — ERROR or
  AWAITING_HUMAN under p13-design-gate §8.4, **never PASSED**.
- **Not decided here:** the verification identity's exact grants and toolchain inventory, which are
  project-dependent and bounded by the A6 ceiling above (the earlier wording "wider than an
  execution's" is withdrawn), and how dependencies are provisioned inside one verification —
  **DESIGN PROPOSAL — UNVERIFIED**. Toolchains installed beside user credential material are not
  grantable as they stand.

## 4. Acceptance evidence plan (synthetic fixtures / sentinels / booleans only)

Every check asserts a **security property**, never demonstrates extraction. Sentinels are planted
synthetic values; assertions are boolean; a sentinel value is never printed. Every row is evidence
**to be produced** against the real Claude Code path (§3.8); none exists today. §8 classifies each
row's status as of the 2026-10-07 evidence review.

| # | Property | Shape of the check |
|---|---|---|
| 1 | Legitimate code change still works | Under isolation, a `code_change` task edits and commits **locally** in its execution repository, reaching its model provider only through Core's broker, and hands its push to Core; asserts the commit exists, Core's data-only import brought it into the user's repository, and the push went through Core. |
| 2 | Credential authorities unreachable | A **synthetic sentinel** in each user-owned store class (an approved class list, names only); under isolation each retrieval is denied (boolean). The same retrieval under today's identity succeeds — the test asserts the delta. |
| 3 | Local Core token unreachable | Under isolation, reading `run/local-token` is denied (boolean). |
| 4 | Core effect boundary | Every action in §3.6's closed set, requested from an execution origin (including with the hook token), is refused at Core. |
| 5 | No re-arm after a halt | The execution cannot re-arm after an e-stop: a re-arm request from an execution origin — attested, or with origin undeterminable — is refused at Core by the §3.6 boundary (R1-A), including when it presents the hook token or any other credential it holds. D10's paired-device PIN step-up is a separate rule and is not what this row tests. |
| 6 | Mailbox authority | The execution can write requests and read responses and flags; it cannot author a response, a flag, or halt/pause/handoff/approval state, cannot alter Core lifecycle state, and cannot reach another execution's directory. |
| 7 | Sentinel state | Present → halt; absent → proceed; cannot be determined → halt — by an explicit three-state determination, including with the sentinel unreadable while the mailbox stays writable. |
| 8 | e-stop still works | Core up: ending the Job reaps the whole tree. Core hung: the sentinel halts a hook harness and the item-83 registry kill stops the tree — no second Core-down mechanism exists. Core dead: no isolated process survives (R6-A). |
| 9 | Children remain confined | A grandchild shell is inside the execution identity and the Job, and is itself subject to rows 2–3. |
| 10 | Isolation-establishment invariant | With any §3.4 condition unmet, the execution does not spawn; no configuration disables this. |
| 11 | Core restart | With an execution live, Core dies and restarts: the isolated tree did not outlive Core (R6-A); the restarted Core reconciles its records and resolves the execution through terminate / reap / fail — it is never re-adopted and never left running outside its Job. |
| 12 | Repository boundary | The execution modifies only §3.2 categories 1 and 3, in its own execution repository; the user's repository metadata is unreachable from it; Core's import of its output is data-only and honours none of its configuration, hooks or refs. |
| 13 | Cleanup | After end, the grants are gone, the execution-specific identity torn down, and that identity can no longer reach the workspace. |
| 14 | Verification identity | Core runs a check's commands under the confined verification identity: planted synthetic sentinels in user-owned stores, the local-token path and Core state all read access-denied (boolean) from inside the command; with the identity unavailable, no command runs and the Verification is ERROR or AWAITING_HUMAN, never PASSED. |
| 15 | Halt classification | An execution that ends while PAUSING or HANDING_OFF without a cause Core can classify from its own state is never ENDED_OK; a forged or replayed halt report can move a classification only toward non-advancing, and never yields success, an approval or Core-authored state. |

**The "before" baseline.** Slice G's probe method (names/booleans only) and its boundary-class
inventory are the pre-isolation baseline — the "reachable today" side of each delta test. What
inverts is the **expected result** under isolation.

## 5. Existing P20 gates/tests to extend or replace

- **ADR-0051 §2 credential-removal and workdir boundary tests (slice G's own work) must be written
  against the ISOLATED identity.** A version written against today's identity would assert the
  wrong thing, so these tests are **deferred into PV-20's suite** and are `xfail` until isolation
  lands. This is why G is paused rather than completed.
- **The `CAPABILITY_ENV` test that does not yet exist** becomes part of the isolation suite,
  asserting both environment hygiene **and** identity reach.
- **A spawn-identity contract test** on `base.spawn` / the adapter: the isolated launch is built
  only when the §3.4 invariant holds, and otherwise the execution fails closed.
- **The two live findings become regression tie-backs** (`xfail` today, flipping to pass under
  isolation).
- **G6** gains an `os_isolation` boundary-scenario set.
- **New mutants:** dropping the identity boundary; granting the workspace to the wrong identity;
  granting the bare `run/` instead of the separate resource classes; Core honouring an
  execution-origin request for a §3.6 effect; Core accepting an execution-authored response or
  flag; an undeterminable sentinel read as absent; a spawn proceeding with a §3.4 condition unmet;
  a check's command run under the user's identity; a missing confined verifier recorded as PASSED;
  a hook halt report turning an end into ENDED_OK; an ambiguous PAUSING / HANDING_OFF end recorded
  as ENDED_OK; a live isolated process re-adopted at boot; Core's import honouring the execution
  repository's configuration or hooks; *(added with A1–A7)* an isolated execution started in the
  user's project root or in the bare `run/exec/<id>/`; a non-git project task dispatched; a seed that
  links, shares or hardlinks the user's `.git`; Core running git in an execution repository; a Core
  git operation over execution-derived content without the pinned configuration; the execution's
  claimed HEAD recorded as the canonical revision; a verifier principal reused or sharing writable
  state with another verification; a verifier reaching Core's listener; an isolated execution
  started with the account home as `CLAUDE_CONFIG_DIR`; an MCP opt-in admitted to an isolated
  execution; Core-authored spawn configuration writable by the execution; a forwarded or
  verifier-origin request granted a §3.6 effect; a harness dispatched outside the PV-20 identity; a
  stream `result` collected as an exit.
- **Unchanged and still valid** (orthogonal to the OS gap): E's ADR-0049 exclusion/inventory and
  the O4 fail-closed hook, F's tool removal, and A's registry kill (which stays the only Core-less
  stop mechanism, §3.7). **A's sentinel is valid under PV-20 only with the explicit three-state
  determination** (§3.7, §7.4 Gap A): today its fail-closed result under an inaccessible sentinel
  comes from the mailbox write failing beside it, a coupling §7.5's separation removes, so the
  determination must land no later than that separation.

## 6. Decisions (ruled by the user, 2026-10-07)

None of these rulings authorises implementation. Each records a design decision only.

1. **Mechanism: CONFIRMED.** AppContainer + Job object is the baseline (§2). Separate standard
   user: later escalation path. Windows Sandbox: optional maximum-isolation tier, not the V1.x
   baseline.
2. **Effect boundary: CONFIRMED AS A HARD REQUIREMENT.** OS isolation alone is insufficient. Core
   independently enforces the authorization boundary for privileged effects; execution origin
   confers no privilege (§3.3, §3.6).
3. **Silent fallback: REJECTED.** If the required isolation cannot be established, fail closed and
   do not start the untrusted execution. Any future supported fallback, including the P11 §17
   in-place case, needs its own security analysis and explicit architectural approval and is not
   equivalent to the baseline.
4. **Timing: V1.x SECURITY REMEDIATION.** Not deferrable indefinitely. G1 and G2 stay open until
   the boundary is implemented and its evidence passes; they are not downgraded or waived because
   the remediation is larger than the remaining P20 work.
5. **Critical findings / P20 gate: KEPT OPEN.** G = PAUSED, NOT CLOSED; the no-open-Critical rule
   applies. ADR-0051 records an **acknowledged existing limitation**, which is distinct from the
   **security property PV-20 requires**; the latter has not been demonstrated.
6. **Mailbox authority: CONFIRMED** — the split-authority model of §3.3.
7. **Repository metadata: CONFIRMED** — the four categories of §3.2; Core authoritative for
   privileged repository effects; execution-produced state is untrusted input.
8. **Job lifetime vs Core restart: CONFIRMED** — Job is lifetime authority; restart is
   reconciliation of records. *Wording updated 2026-10-07 for R6-A (item 17):* no isolated process
   outlives the Core that held its Job, so restart resolves every remaining non-terminal execution
   through terminate / reap / fail and never re-adopts (§3.7).
9. **Harness scope: CONFIRMED** — §3.8; amended by item 18 (every production-dispatched execution
   runs under PV-20, whatever its harness).
10. **Sentinel state: CONFIRMED REQUIREMENT** — undeterminable state fails closed (§3.7).
11. **Isolation establishment: CONFIRMED REQUIREMENT** — the pre-spawn invariant of §3.4.

**The §7.2 decisions (approved by the owner, 2026-10-07; recorded in [ADR-0053](decisions/ADR-0053.md)).**
Approved in the direction the PV-20 decision matrix recommended. Like items 1–11, none authorises
implementation.

12. **R4b — verification authority: APPROVED, Option 2** (confined verification identity), with
    Option 3 as the fail-closed degraded mode; Option 1 rejected. Execution-influenced code never
    runs under the user's identity (§3.9).
13. **R4a — repository topology: APPROVED, R4a-B** (a separate execution repository, imported as
    data). The user's `.git` is not exposed through a linked worktree (§3.2).
14. **R1 — execution origin: APPROVED, R1-A** (OS-attested origin at the connecting peer). No
    silent substitution: if attestation cannot be established, a transport change or R1-B is a new
    owner decision (§3.3).
15. **R3 — provider access: APPROVED, R3-B as the target** (Core-brokered; no provider credential
    inside the boundary). If the production Claude CLI cannot support it, R3-A needs a separate,
    explicit owner security decision; until one is viable, isolated execution fails closed (§3.3,
    §3.5).
16. **R5 — halt state: APPROVED, H2.** Core owns authoritative halt state; hook halt / PreCompact
    records are untrusted reports that can only move classification toward a non-advancing state;
    an ambiguous PAUSING / HANDING_OFF end never becomes ENDED_OK (§3.3).
17. **R6 — Job ownership: APPROVED, R6-A** (Core only). Core's death terminates the isolated tree;
    restart reconciles records and resolves remaining executions through terminate / reap / fail; a
    live isolated process is never re-adopted (§3.7).

**The blocker decisions (approved by the owner, 2026-10-07, after the PV-20 architecture audit;
recorded in [ADR-0053](decisions/ADR-0053.md) §7).** Approved in the direction the PV-20 blocker
decision matrix recommended. None authorises implementation.

18. **A4 — harness identity: APPROVED, H-1.** Every production-dispatched execution, whatever its
    harness, runs under the PV-20 identity inside its Core-held Job; a harness sandbox is an inner
    layer only; a harness that cannot launch inside PV-20 is not eligible; fake/test harnesses are
    not production-dispatchable (§3.8).
19. **A1 — workspace: APPROVED, A1-1.** A Core-established workspace for every isolated execution of
    every task kind; a seeded execution repository for git roots (detached HEAD from the recorded
    commit); an empty class-7 workspace with no project; non-git roots structurally refused before
    dispatch; `workspace_mode: in_place` withdrawn; never the user's project root (§3.2).
20. **A5 — repository and git boundary: APPROVED, G-4.** Copy seed of the base revision only; Core
    never runs git against an execution repository as the user; the working tree is imported as data
    into a Core-owned repository whose pinned import commit is the canonical revision; Core-pinned
    configuration for every Core git operation over execution-derived content; R4b verifies a fresh
    checkout of that revision (§3.2, §3.9). *Confirmed by the owner, 2026-10-07:* no
    repository-controlled hook (the user's own included), filter, fsmonitor, diff/merge driver,
    submodule, LFS transfer mechanism or other execution-derived git extension executes in those
    operations, and Core pushes no content whose publication requires one (a separate owner
    decision).
21. **A6 — verifier: APPROVED, V-1.** One fresh verifier principal per verification, never reused;
    authority a subset of the execution runtime/tool grants plus its own checkout and scratch, with
    network only if P23 permits; no persistent or shared cache (§3.9).
22. **A2 — account home and configuration: APPROVED, A2-1.** A fresh per-execution
    `CLAUDE_CONFIG_DIR` with no provider login; never the account home; Core-authored spawn
    configuration Core-write / execution-read; opt-ins only as Core-materialised data carrying no
    credential authority; **no MCP opt-in is admitted to an isolated execution** (confirmed by the
    owner, 2026-10-07; changing it needs a new owner decision) (§3.1, §3.3).
23. **A3 — R1 origin scope: APPROVED** — allowlist + hop rule + deputy rule, with the owner's
    clarification that a trusted local §3.6 request needs both the attested user-origin condition
    and an approved trusted path (§3.3). The attestation mechanism is left to the empirical phase.
24. **A7 — lifecycle authority: DOCUMENTATION CORRECTION** of R5 and R6-A (§3.3, §3.7): ENDED_OK is an
    execution-level fact Core records only from its own observed exit 0; a stream result is never an
    exit; PAUSING / HANDING_OFF never reach ENDED_OK on an execution's report; ambiguous termination
    is non-advancing; no adoption after restart; a Core-written `ended` tombstone is a Core
    observation; PASSED needs authoritative verification evidence. ERROR versus AWAITING_HUMAN, and
    PAUSED versus failed at restart, stay **non-security policy details**.

**Not owner decisions.**

- **R2 — resource layout: IMPLEMENTATION CONSTRAINT.** The seven classes of §7.5 stay on separate
  boundaries; access rules, directories and filenames are implementation work. Core-authored spawn
  configuration has class 2's authority; the workspace and `CLAUDE_CONFIG_DIR` are class 7 (A1, A2).
- **R7 — profile granularity: IMPLEMENTATION CONSTRAINT.** One execution-specific
  identity/principal, created before spawn and torn down after; other executions inaccessible;
  shared runtime grants read/execute only, holding no user secrets; Core-owned state never granted
  (§3.1).
- **R8 — O7: EXTERNAL DEPENDENCY,** owned by P11 (§3.4).

## 7. Status

**`PV-20 ARCHITECTURE DECISIONS APPROVED AND DOCUMENTED (ADR-0053); IMPLEMENTATION: SLICE S0 ONLY;
EMPIRICAL EVIDENCE OUTSTANDING`.** Only slice S0 (§7.4 Gap A) has been implemented; no acceptance evidence has been produced, and the security boundary is not claimed to exist. The audit blockers
A1–A6 are decided and A7 is corrected (§6 items 18–24); that closes architecture questions, not
implementation authorization.

**Evidence status, 2026-10-29:** `.collab/PV20-mxc-feasibility.md` records eight successful smoke checks and a separately authorized `claude.exe` 2.1.312 `--version`/`--help` addendum on Windows 11 Home build 26300.9711, using `@microsoft/mxc-sdk@1.0.1`, `wxc-exec.exe` x64 and the `processcontainer` backend. These establish bounded startup, filesystem/network-denial and short process-tree cleanup observations only. They do not establish any N1–N5 acceptance result, a real agent session, strict peer exclusion, credential-authority denial, broker reach, origin attestation, or production lifecycle correctness. G1 and G2 remain Critical and open; slice G remains PAUSED and NOT CLOSED.

### 7.1 Unverified (DESIGN PROPOSAL — UNVERIFIED)

The PV-13 capability/ACE spike was attempted on 2026-10-07 and did not complete (§7.3). All of the
following remain unverified:

- the **minimum AppContainer capability/ACE set** (§3.1 inventory);
- normal Node / Claude CLI / child-shell execution under that set;
- child and grandchild confinement (§3.4);
- Job lifetime and Core-restart behaviour in implementation (§3.7);
- exact mailbox ACE enforcement (§3.3);
- repository-metadata behaviour under the isolated identity (§3.2);
- complete credential-boundary coverage (§3.5);
- execution-origin enforcement at Core (§3.6);
- isolation-establishment enforcement (§3.4);
- undeterminable-sentinel behaviour as an **explicit three-state determination** (§3.7, §7.4 Gap A).
  The outcome-level fail-closed result observed on 2026-10-07 came from the hook's crash path, not
  from a determination, and is therefore not this verification. S0 (§7.4) implements the
  determination and tests it with injected errors under the current identity; that a denied lookup
  under the isolated identity is reported as an error, never as not-found, is unverified;
- OS attestation of the connecting peer on Core's local transport (R1-A, §3.3);
- that the production Claude CLI can reach its provider through Core's broker, whether it calls
  anything outside it, and the loopback reach the broker needs (R3-B, §3.3);
- that the import of an execution's result is data-only (R4a-B, §3.2);
- the confined verification identity's grants and toolchain, and that Core-held handles return the
  exit code and output (R4b, §3.9);
- Core as the Job's sole holder, kill-on-close on Core's death, an execution's inability to obtain a
  reference to its own Job, and the registry kill's reach to an isolated process (R6-A, §3.7);
- what the CLI's exit code and stream show after a halt (R5, §3.3);
- *(added with A1–A6)* that a copy seed exposes nothing of the user's `.git`, that the working-tree
  import follows no link or reparse point, and that the Core-pinned configuration stops every
  execution-controlled hook, driver and configuration (A1, A5, §3.2);
- that the production CLI runs with a fresh per-execution `CLAUDE_CONFIG_DIR` holding no provider
  login, with Core-authored configuration read-only and its settings precedence holding, and where
  its session transcripts and resume state live (A2, §3.1);
- that a verifier principal can be created and destroyed per verification, with representative
  toolchains granted and dependencies provisioned inside it (A6, §3.9);
- that no execution or verification identity can reach a forwarding hop or user-identity proxy, and
  that Core can tell a forwarded request from a direct one (A3, §3.3).

### 7.2 Design questions — resolved 2026-10-07

Every architectural question previously listed here is decided (§6 items 12–17) or classified; what
remains is implementation work, evidence (§7.1) and one external dependency.

| Former question | Resolution |
|---|---|
| Profile granularity, and which identity holds shared runtime grants | **R7, implementation constraint** (§3.1, §6) |
| How the CLI authenticates to its model provider; the network capability, including Core's loopback listener | **R3-B approved as the target** (§6.15) — production CLI feasibility unverified; network is **P23's** |
| Repository metadata of §3.2 categories 2–3, and how Core treats execution-produced state as untrusted | **R4a-B approved** (§6.13); exact metadata sets are implementation work |
| *(added 2026-10-07)* Under what identity Core runs execution-influenced verification code | **R4b Option 2 approved**, Option 3 as fail-closed mode (§6.12, §3.9) |
| How Core establishes execution origin | **R1-A approved** (§6.14) — attestation on Core's transport unverified |
| How the hook's halt and PreCompact records are carried | **H2 approved** (§6.16, §3.3) |
| How the Job relationship is carried across a Core restart | **R6-A approved** (§6.17, §3.7) |
| The resource layout of the mailbox split | **R2, implementation constraint** (§7.5, §6) |
| O7: charging and re-dispatch of an isolation-establishment failure | **R8, external dependency: P11** — still open, and required before implementation (§3.4) |
| The PV-20 ADR required by ADR-0051 §5 | **Written: [ADR-0053](decisions/ADR-0053.md)** |
| *(audit 2026-10-07)* A4: identity of non-Claude-Code and sandbox harness executions | **H-1 approved** (§6 item 18, §3.8) |
| *(audit)* A1: workspace for non-worktree, non-git and no-project executions | **A1-1 approved** (§6 item 19, §3.2) |
| *(audit)* A5: Core git operations on execution-produced state; canonical revision | **G-4 approved** (§6 item 20, §3.2) |
| *(audit)* A6: verifier granularity, state lifetime and ceiling | **V-1 approved** (§6 item 21, §3.9) |
| *(audit)* A2: account home, opt-ins and Claude configuration inside the boundary | **A2-1 approved** (§6 item 22, §3.1) |
| *(audit)* A3: R1-A scope — verifier, forwarding hops, proxies, deputies | **Allowlist + hop rule + deputy rule approved** (§6 item 23, §3.3) |
| *(audit)* A7: lifecycle authority from execution-authored content | **Documentation correction** (§6 item 24) |

**Conditional decisions that are not resolved and must not be inferred:** R1-B or a transport change
(if attestation fails); R3-A (if the broker is infeasible); sharing a principal between executions
(if per-execution principals prove infeasible); escalation to the separate standard user. Each is a
new owner decision.

### 7.3 Evidence review of 2026-10-07 (read-only; synthetic fixtures only)

A read-only review ran against synthetic fixtures in a disposable home. It accessed no real
credential, token, key or store, printed no secret, performed no push or publish, changed no policy,
authorization or re-arm state, modified no production code, and left no process, fixture or grant
behind.

**Evidenced now**

- **The hook fails closed at the outcome level.** Driven through its real entry point
  (`python -m archeus.harnesses.hook`) against a synthetic `ARCHEUS_HOME`: sentinel absent → `allow`
  with one request written; sentinel present → halt, `halted.json`, no request; STOP / PAUSE /
  HANDOFF → halt; `run/` traversal denied (the denial itself was confirmed) → deny, **never allow**,
  even with a responder standing by to answer `allow`.
- **The production path exists and is identified.** Claude Code **2.1.292** is installed on this
  machine and runs (`claude --version`, exit 0). It is the §3.8 target; no isolation property was
  exercised on it.
- **The mailbox split is not enforced today.** From the execution's own position, against synthetic
  fixtures, it authored its own `.res.json`, created a `HANDOFF` flag, wrote the global `run/STOP`,
  read a **synthetic** `run/local-token` fixture, and wrote another execution's directory. The §3.3
  table forbids every one of these. This is the table being *unenforced*, not a control being
  bypassed: the test ran under the ordinary user identity, where no such control exists yet.
- **The "before" side of the credential delta.** Under today's identity a Node process read and wrote
  a user-owned synthetic fixture — finding G1's shape, on synthetic material only. Finding G2's
  standing rests on the gate's own record (p20-design-gate §12 item 93), **not** on this review: this
  review read a synthetic fixture and did not read the real `run/local-token`.

**Not implemented, therefore not testable**

The tree contains no PV-20 implementation: no AppContainer launch path, no alternate execution
identity, no Job-object integration, no grant/ACE establishment, and no execution-origin mechanism at
Core. `base.spawn` still launches through the ordinary detached-spawn path with the user environment.
This means these are **not yet implemented — not that the architecture has failed**:

- the AppContainer boundary (§3.1, §3.4);
- Job-object lifetime authority and kill-on-close (§3.7);
- the mailbox ACL boundary (§3.3);
- the credential boundary (§3.5);
- child and grandchild confinement (§3.4);
- Core's execution-origin effect boundary (§3.6);
- the isolation-establishment invariant (§3.4);
- Job-based restart reconciliation (§3.7).

**Unverified**

- the exact AppContainer capability/ACE set (§3.1);
- production-path AppContainer confinement (§3.8);
- the model-provider authentication boundary (§7.2);
- the repository-metadata boundary (§3.2).

**The spike attempt, and what it did and did not settle**

The PV-13 spike (that study, §5) was attempted. Its `SECURITY_CAPABILITIES` payload was accepted by
the process-attribute call; the launch under test then returned `ERROR_NOT_APPCONTAINER` for every
identity tried, including well-known AppContainer SIDs — a failure of the spike harness's
construction, not a verdict on the mechanism. One further launch that did start was **discarded**
because the child's token carried no AppContainer SID, so it proved nothing. The capability/ACE set
was reached no further: no C toolchain or SDK-level binding was available in that environment and the
AppContainer profile-creation entry point could not be resolved. **AppContainer viability is DESIGN
PROPOSAL — UNVERIFIED: neither proven nor disproven, and the spike is not complete.**

### 7.4 Implementation gaps recorded (not solved here)

- **Gap A — explicit tri-state determination.** The hook asks `os.path.exists()` for the sentinel, so
  it cannot distinguish **present** from **absent** from **indeterminate**; the fail-closed result
  observed under denied traversal is an exception-derived outcome, not a determination. PV-20 requires
  the architecture to represent all three states explicitly and to **fail closed on `indeterminate`**
  (§3.7, acceptance row 7). Precisely: `os.path.exists` reports an inaccessible sentinel as absent,
  and the halt observed came from the mailbox write that follows failing under the same denied
  traversal and the hook's catch-all turning that into a halt. **Ordering:** the determination must
  land no later than the sentinel/mailbox separation of §7.5, which removes that coupling.
  **Implemented as slice S0 (2026-10-08; p20-design-gate §12 item 101), the first and only PV-20
  slice the owner has authorised.** All five sentinel reads in `archeus/harnesses/hook.py` — the
  global STOP before the request, the execution's STOP, PAUSE and HANDOFF flags, and the global
  STOP inside the wait loop — go through one determination: a successful `os.lstat` is
  **present** (a dangling link included), `FileNotFoundError` is **absent**, and every other
  `OSError` is **indeterminate**, which halts with its own reason. Tests use injected errors only;
  no ACL, no confinement. What S0 does **not** settle:
  - **Row 7 stays implementation-blocked:** on the §7.5 sentinel/mailbox separation, and on
    isolated-identity evidence that a denied lookup is reported as an error, never as not-found.
  - **Gap B is untouched:** a `halted.json` the execution cannot write is still lost, so Core can
    still record ENDED_OK after a halt it did not ask for. That remains R5 / H2's Core-authoritative
    halt state (row 15).
  - **PV-20 is not verified; G stays PAUSED and NOT CLOSED; G1 and G2 stay Critical and open.**
- **Gap B — halt-state durability (resolved in architecture by R5 / H2, §6.16).** `halted.json` is
  not durable when the execution legitimately lacks write access to its own directory — `_halted`
  swallows the write failure — and Core today tells a halted execution from one that finished by
  that file. The earlier wording here ("an authoritative durable channel" for the hook's record) is
  **superseded**: no record the hook writes can be authoritative, because it is execution-authored.
  Under H2, **Core's classification is the authoritative halt state**, held in Core-owned durable
  state that does not depend on any execution write; the hook's halt and PreCompact records are
  untrusted evidence that can move a classification only toward non-advancing; and an end Core
  cannot classify while PAUSING or HANDING_OFF never becomes ENDED_OK (§3.3). *Recorded;
  implementation not started.*

### 7.5 Architectural implementation requirement: separate resource boundaries

The 2026-10-07 review showed that the existing `run/exec/<id>/` layout does **not** by itself guarantee
the §3.3 authority split: the sentinel and the mailbox sit inside one filesystem subtree, so denying
the sentinel necessarily denies the mailbox too. One shared subtree cannot express "read this, not
that".

PV-20's implementation must therefore establish **separate resource/ACL boundaries** for these seven
classes (R2; an implementation may divide a class further, never join two). Core-authored spawn
configuration carries class 2's authority; an isolated execution's workspace and
`CLAUDE_CONFIG_DIR` belong to class 7, never to the directory classes 1–6 occupy (A1, A2):

1. the execution's request input (which also carries the hook's untrusted halt and PreCompact
   reports, R5 / H2);
2. Core's authored response;
3. the STOP / PAUSE / HANDOFF sentinel state;
4. lifecycle/control state — **Core-only**;
5. halt state — Core's authoritative classification, **Core-only**;
6. `run/local-token` and other Core-private state — **never granted**;
7. execution-private state.

**This is a requirement on the future implementation only (R2, an implementation constraint, §6).**
The ACEs, the grant mechanism, the directory layout and the filenames are deliberately not designed
here. No lifecycle or classification decision may read an execution-writable file as authority —
today `pid.json`, `halted.json` and `precompact.json` all are — nor read the stream's content as an
exit (A7). The process registry (`processes.jsonl`), the item-83 stop's instrument, is Core-only
state like classes 4–6; which of them holds it is layout. Class 3's separation lands together
with, or after, the explicit three-state sentinel determination (§7.4 Gap A).

### 7.6 Known stale reference outside this pass (C16)

The V2 register ([ARCHEUS_V2_ASSISTANT_LAYER.md](ARCHEUS_V2_ASSISTANT_LAYER.md)) still carries
PV-20 as "post-V1" and "parked", PV-13 as "ready-to-research", "may be pulled into V1.x by a new
decision" (that decision is taken: ADR-0051's superseding timing decision, §6.4), and a PV-20
acceptance line naming "network denied" (network is P23's, §1). It is V2-track material and is
**left unchanged here** for the V2 documentation pass; where it disagrees, this document, ADR-0051's
superseding decision and ADR-0053 are current.

## 8. Acceptance-row classification (2026-10-07)

**Ledger qualification:** Historical 2026-10-07 classifications remain historical. The 2026-10-29 MXC smoke and Claude version/help addendum are feasibility evidence only. No acceptance row is promoted to PASS by backend adoption. Maintain a current row-by-row ledger containing candidate and artifact hashes, effective backend/policy/identity, commands, controls, outcomes, cleanup, reviewer and authorization scope. Missing mandatory cases remain evidence-blocked.

Every §4 row is **implementation-blocked**: none can be executed until PV-20 exists. **None is
passed, and no row is passed by the design existing.** Labels:

- **design-complete** — settled by §3/§6 and buildable as written;
- **implementation-blocked** — cannot run, because the mechanism is not implemented;
- **evidence-blocked** — cannot yet be proven even once built, because a named dependency has no
  evidence yet;
- **design-open** — a question the row depends on is still undecided, **or** the approved design
  rests on a mechanism with no evidence whose failure would need a new owner decision, so the row is
  **not** design-complete and must not be scheduled as though it were.

*Reclassified 2026-10-07 after the six approvals (§6 items 12–17), and again after the blocker
decisions (§6 items 18–24): row 1 moves to design-open under this section's own definition, because
it rests on R3-B, whose failure needs a separate R3-A decision.* **Every row also rests on
AppContainer viability, whose failure would need the escalation owner decision (§2).** That shared
dependency is stated once here rather than on each row; no row may be scheduled as though
AppContainer were evidenced.

| Row | Property | Classification | Blocked by / note |
|---|---|---|---|
| 1 | legitimate code change works | **design-open** · implementation-blocked · evidence-blocked | needs the isolated identity (§7.3); provider access through Core's broker, with a fresh per-execution `CLAUDE_CONFIG_DIR` (A2), is unverified on the production CLI, and if infeasible R3-A is a separate owner decision (§6.15) |
| 2 | credential authorities unreachable | design-complete · implementation-blocked · evidence-blocked | AppContainer viability unverified; the baseline side is measured |
| 3 | local Core token unreachable | design-complete · implementation-blocked | shown unenforced today (§7.3), synthetic fixture only |
| 4 | Core effect boundary | **design-open** · implementation-blocked · evidence-blocked | origin is decided (R1-A, §6.14), but attestation on Core's transport has no evidence, and its failure would need a new owner decision (R1-B or a transport change); §3.6's closed set cannot be enforced against an origin Core cannot identify |
| 5 | no re-arm after a halt | **design-open** · implementation-blocked · evidence-blocked | re-arm is a §3.6 member, refused to an execution through R1-A — the same open point as row 4. D10's paired-device step-up is not the mechanism (§3.6) |
| 6 | mailbox authority | design-complete · implementation-blocked · evidence-blocked | authority model ruled (§6.6), halt reports decided (H2), layout an implementation constraint (R2, §7.5); ACE enforcement unverified |
| 7 | sentinel three states | design-complete · implementation-blocked · evidence-blocked | Gap A's determination is built (S0, §7.4; injected-error tests only); still blocked on the §7.5 separation, and on evidence that a denied lookup under the isolated identity is reported as an error, never as not-found |
| 8 | e-stop still works | design-complete · implementation-blocked · evidence-blocked | no Job object exists; R6-A and item 83 settle the design; Job behaviour and the registry kill's reach to an isolated process are unverified |
| 9 | children remain confined | design-complete · implementation-blocked · evidence-blocked | confinement inheritance unverified |
| 10 | establishment invariant | design-complete · implementation-blocked | O7 still open (P11's, R8; §3.4) |
| 11 | Core restart | design-complete · implementation-blocked · evidence-blocked | R6-A decided (§6.17); kill-on-close and sole holding unverified |
| 12 | repository boundary | design-complete · implementation-blocked · evidence-blocked | R4a-B decided (§6.13), completed by A1 and A5 (§6 items 19–20); the copy seed, the working-tree import and the Core-pinned configuration unverified |
| 13 | cleanup | design-complete · implementation-blocked | no grants or profiles are created today |
| 14 | verification identity | design-complete · implementation-blocked · evidence-blocked | R4b decided (§6.12), completed by A6 (§6 item 21); per-verification principals, grants and toolchain unverified; today verification runs as the user (§3.9) |
| 15 | halt classification | design-complete · implementation-blocked | H2 decided (§6.16), contracts corrected by A7 (§6 item 24); `record_end` still classifies as before |

Rows 4 and 5 stay **design-open** until R1-A's attestation exists and is evidenced; row 1 until the
production CLI is shown to work through R3-B. Every row is implementation-blocked, and none is
passed.

**Acceptance evidence the blocker decisions add (to be produced; none exists).** Synthetic fixtures
and booleans only, like §4:

- *A1:* a non-git project task produces zero spawn attempts; no isolated execution starts in the
  user's project root or the bare `run/exec/<id>/`.
- *A5:* a hostile execution repository (configuration, hooks, attributes, sub-repository and
  large-file configuration, replaced refs) leaves a planted sentinel uncreated through seeding,
  import, git facts, merge, checkout and push; the recorded revision is Core's import commit.
- *A6:* two verifications in sequence cannot reach each other's state; a verifier cannot reach
  Core's listener or any loopback service and reads every credential sentinel access-denied.
- *A2:* an isolated execution's `CLAUDE_CONFIG_DIR` holds no provider login, the account home reads
  access-denied, and Core-authored configuration is not writable from inside.
- *A3:* a forwarded request and a verifier-origin request are refused every §3.6 effect.
- *A4:* the router refuses a harness that cannot launch inside the PV-20 identity.

## MXC backend risk register and evidence ledger (proposed, 2026-10-29)

Proposed register entries for the MXC backend decision (ADR-0053 amendment, 2026-10-29):

| ID | Risk/evidence status | Required treatment |
|---|---|---|
| MXC-R01 | GA date 2026-10-07 supplied by task; **not independently verified**. At review date, only 22 days since stated GA. | Treat maturity as limited; pin, stage, retain rollback artifact and require regression evidence. |
| MXC-R02 | Pre-GA README “not a security boundary” statement supplied by task; exact revision/context/current disposition **unverified**. | Retrieve and preserve dated source in separately authorized research. Do not claim GA alone resolves statement. Boundary claims require evidence and upstream clarification. |
| MXC-R03 | git-bash/MSYS2 issue `microsoft/mxc#1061` recorded by smoke; issue content/status **unverified**. | Exclude git-bash-dependent agent routes until pinned reproducer passes. No native-shell fallback outside isolation. |
| MXC-R04 | BaseContainer crash reports supplied by task; affected builds/reproducer **unverified**. | Capture actual selected tier, crash/exit diagnostics and no-survivor result. Crash means unavailable, never fallback. |
| MXC-R05 | BitLocker-locked volume failure supplied by task; exact behavior **unverified**. | Use reviewed volume inventory; refuse unsupported placement. No unlocking, mounting or modifying owner volumes in N1–N5. |
| MXC-R06 | Window-station/UI denial: smoke records PowerShell/choice initialization failure `0xC0000142`. | UI-blocked default proposed; per-tool tests and explicit decision before enabling UI. |
| MXC-R07 | Malicious/changed SDK, transitive dependency or native binary. Lock integrity is not publisher authenticity. | Exact version/lock/hashes, provenance and license/dependency review; offline runtime inventory; verify distributed binary separately. |
| MXC-R08 | Package lifecycle scripts or absent artifacts with `--ignore-scripts`. | Keep scripts disabled. Verify package contains required runtime; missing artifact blocks installation, never triggers silent script enablement. |
| MXC-R09 | Vendor update changes policy semantics, principals, Jobs or cleanup. | No auto-update. Reviewed version change; rerun affected N stages before activation. |
| MXC-R10 | MXC profile residue/opaque cleanup. Smoke notes 173 mappings, attribution unknown. | Do not attribute or delete existing registrations. Owned-resource disposal evidence and quarantine required; storage absence remains unverified without authorized proof. |
| MXC-R11 | Nested Jobs, shared principal or broker deputy defeats contract. | Prove outer Job sole ownership, actual principal separation and origin preservation. Wrapper success insufficient. |

Proposed initial evidence-ledger rows (the ledger file `.collab/PV20-mxc-evidence-ledger.md` does not exist yet):

| Evidence ID | Recorded scope | Acceptance disposition |
|---|---|---|
| MXC-SMOKE-T1 | Fixture `cmd.exe` startup | Feasibility only |
| MXC-SMOKE-T2 | Allowed write; sibling write/read denied | Partial filesystem corroboration |
| MXC-SMOKE-T3 | Host positive control; contained curl denied; zero listener connections | Partial network corroboration |
| MXC-SMOKE-T4 | Two-process tree gone within 5 s, launcher kill and Core-owned Job close | Partial lifetime corroboration |
| MXC-CLAUDE-INFO | Version/help exit 0, under 2.5 s | CLI startup only |
| MXC-N1…N5 | No runs recorded | NOT_RUN |

Never equate eight checks with eight acceptance rows.
