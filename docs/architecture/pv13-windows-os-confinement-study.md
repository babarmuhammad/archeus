# PV-13 — Windows OS-confinement mechanisms study

**Status:** DELIVERED (technical study, research only) · **Date:** 2026-10-07 · **Owner input to:** PV-20 (the OS-level sandbox ADR, ADR-0051 §5) · Register: [ARCHEUS_V2_ASSISTANT_LAYER.md](ARCHEUS_V2_ASSISTANT_LAYER.md) §5 PV-13 (deliverable: "dated report: confinement achievable for a Node CLI plus its child shells")

> **No implementation.** This is the authorised PV-13 study. It evaluates mechanisms and
> recommends one for PV-20 to decide on. It changes no production code, builds no sandbox, and
> does not authorise PV-20. It describes attack surface only at the boundary / capability /
> evidence / impact level, never as a runnable procedure, and names no real secret.
>
> **Evidence status (2026-10-07).** This study's recommendation is a recommendation, not proof.
> The empirical capability/ACE spike it names (§5) was **attempted on 2026-10-07 and did not
> complete**; the capability/ACE model and every AppContainer behaviour stated below remain
> **DESIGN PROPOSAL — UNVERIFIED**. The decisions taken on this study are recorded in
> [pv20-execution-isolation-design.md](pv20-execution-isolation-design.md) §6.
>
> **Current status (2026-10-07, after the PV-20 evidence review).**
>
> - **Confirmed as the architectural mechanism choice:** AppContainer as the primary identity/ACL
>   boundary, wrapped in a Job object (PV-20 §2, §6.1). That is a decision about which mechanism to
>   build — not a measurement of whether it works.
> - **Empirically unverified:** AppContainer viability, and with it the exact capability/ACE set a
>   legitimate code-change turn needs. The spike this study named was attempted and did not complete
>   (§5, PV-20 §7.3). AppContainer is **neither proven nor disproven**.
> - **Escalation path unchanged:** the separate standard user (B2) remains the stronger isolation
>   escalation — required where a credential authority proves not to be governed by the AppContainer
>   boundary, or where DPAPI-grade isolation is needed.
> - **Windows Sandbox / a disposable VM remains an optional maximum-isolation tier,** not the V1.x
>   baseline (Home unavailability, per-execution startup cost).
> - **The OS-confinement gap is acknowledged, not resolved.** Findings G1 and G2 stay open and
>   Critical; P20 slice G stays PAUSED and NOT CLOSED.
> - **Superseded in part by PV-20's approved architecture ([ADR-0053](decisions/ADR-0053.md),
>   2026-10-07).** Where this study and PV-20 differ, PV-20 and ADR-0053 are current. In
>   particular: the Core-channel grant on the whole `run/exec/<id>/` subtree (§3.A.4 and its
>   echoes) is replaced by PV-20's seven separate resource classes (PV-20 §7.5); the worktree-only
>   grant (§3.A.3) is replaced by a separate execution repository imported as data (R4a-B); making
>   the local token unreadable (§3.A.10) is read-bounding only, and Core's effect boundary (R1-A
>   origin attestation, R4b confined verification) is a separate, required layer; and the
>   per-execution profile (§3.A.6) is PV-20's R7 implementation constraint. The corrections are
>   marked inline.

## 1. Why this study exists

ADR-0051 Decision 1 accepted, for V1, that a Claude Code execution runs with the **user's OS
identity** and is confined only by the application-level boundary (policy, action classes, the
fail-closed hook, environment hygiene) plus harness-provided sandboxes. ADR-0051 §3 named the
OS-confinement gap and routed its remediation to **PV-20**, whose own ADR is to be "informed by
the PV-13 study of the Windows mechanisms." Slice G's verification pass then confirmed the gap is
reachable in practice (two Critical findings, recorded in the P20 gate), so the PV-13 study is the
prerequisite that was always named and is now on the critical path.

The gap, stated as a capability rather than a procedure: a process holding the user's OS identity
keeps the user's **reach** into user-owned credential authorities and into local Core control
state, and clearing environment variables cannot remove a store the OS identity owns. The study's
question is therefore narrow and concrete: **which Windows mechanism can run the Node/Claude CLI
and every child process it spawns under an execution identity that is meaningfully separated from
the user's, while still permitting a legitimate code-change task.**

## 2. What must survive confinement (the compatibility floor)

A candidate is only viable if, under it, all of the following still hold. These come from the code
the execution boundary is built on, read for this study.

- **The Node runtime and the Claude CLI run a normal turn.** `claude.exe` on this machine is a
  native PE launcher (x86-64 console) that spawns Node (v24.15.0); both must start and run tool
  calls.
- **Child processes stay confined.** The agent spawns shells and tools (`Bash`, `PowerShell`, git,
  the hook itself); confinement that a child can shed is no confinement.
- **The worktree is read-write.** A `code_change` task edits and commits inside its worktree
  (`<ARCHEUS_HOME>/worktrees/<project>/<mission>/<task>`, `manager._workspace`). *(Under PV-20 the
  workspace becomes a separate execution repository, R4a-B; the requirement — a writable workspace
  where a legitimate local commit works — is unchanged.)*
- **The Core channel still works.** The hook talks to Core through a **file mailbox**
  (`<ARCHEUS_HOME>/run/exec/<id>/hook/<seq>.req.json` → `<seq>.res.json`, `harnesses/hook.py`) and
  reads the **STOP sentinel** (`<ARCHEUS_HOME>/run/STOP`). It needs the mailbox and the sentinel
  reachable — and **only those** — never `run/local-token`.
- **The e-stop still halts.** Two halves: the kill (today `proc.kill_pid_tree(pid, create_time)`,
  by recorded pid and create time — not by a retained handle) and the Core-down sentinel the hook
  reads from inside the process tree. Under PV-20 the Job object is the process-lifetime authority
  and the e-stop acts through the Job/kill contract (PV-20 §3.7).
- **Fail-closed is honoured.** If isolation cannot be established, the execution must **not spawn**
  (the P11 pattern for a workspace that cannot be made).

## 3. Candidates

### A. AppContainer (lowbox token)

A Win32 process launched into an AppContainer runs under a **lowbox token**: a package/capability
SID with **deny-by-default** access to securable objects. It reaches a securable object only
through an explicit capability or an ACE naming the container SID.

1. **Node / CLI run normally:** expected yes, with caveats — **DESIGN PROPOSAL — UNVERIFIED** (the
   spike did not complete, §5). A console Win32 app runs in an AppContainer, but
   deny-by-default means Node and the CLI need read/execute ACEs on their own install directories
   and whatever runtime paths they touch. The one empirical unknown PV-20 must close with a spike
   is the exact capability/ACE set a code-change turn needs — this is what PV-13's deliverable
   ("confinement achievable for a Node CLI plus its child shells") asks PV-20 to confirm.
2. **Child inheritance:** **strongest of the three.** A child spawned by an AppContainer process
   stays in the same AppContainer — the lowbox token propagates and cannot be shed by spawning.
3. **Workspace:** grant the container SID read/write on its own workspace. Everything else
   (user profile, credential authorities, `run/`) is denied because the model is deny-by-default —
   the correct shape: isolation is the default and each grant is deliberate. *Superseded in part
   (PV-20 §3.2, ADR-0053 R4a-B):* a **linked worktree does not isolate repository metadata** — a
   commit in one writes the user repository's shared objects and refs and its worktree entry, and
   the worktree shares the user repository's config and hooks — so "the worktree only" cannot be
   granted without granting the user's `.git`. The approved topology is a separate execution
   repository whose results Core imports as data; the user's `.git` is not exposed.
4. **Core channel:** *superseded (PV-20 §3.3, §7.5; ADR-0053).* This study proposed read/write on
   the whole `run/exec/<id>/` subtree plus read on the sentinel. That subtree also holds Core's
   lifecycle files, and one subtree cannot express "read this, not that". The approved model keeps
   **seven resource classes on separate boundaries**: (1) request input; (2) Core response; (3)
   STOP / PAUSE / HANDOFF sentinel state; (4) lifecycle/control state; (5) halt state; (6)
   local-token / Core-private state; (7) private execution state. Lifecycle/control state and
   authoritative halt state are **Core-only**, and `run/local-token` is never granted. The exact
   ACEs are **DESIGN PROPOSAL — UNVERIFIED**.
5. **e-stop:** the tree-kill runs as the user, through the Job/kill contract (the Job is the
   process-lifetime authority; PV-20 §3.7), and the item-83 STOP sentinel plus registry kill stays
   the only Core-less stop mechanism. The sentinel-driven halt needs the sentinel state
   determinable — by an explicit three-state determination on its own boundary (PV-20 §7.5 class
   3), not by a shared grant; an undeterminable state must halt (PV-20 §3.7). Both are
   **unverified**.
6. **Lifecycle / cleanup:** per-execution profile (PV-20's R7 implementation constraint: one
   execution-specific principal, created before spawn and torn down after); cleanup is removing the
   workspace ACEs and deleting the profile. Low residue.
7. **Failure:** if the lowbox token or the ACEs cannot be created, fail closed — do not spawn.
8. **Performance / startup:** token derivation plus a process-attribute list — a few milliseconds
   over normal `CreateProcess`, negligible against a model turn. No per-tool-call cost.
9. **Operational complexity / Windows-version:** **available on all editions, including Home**;
   **no elevation** to create a profile and launch into it as the current user. The complexity is
   the capability/ACE plumbing (userenv/advapi32, `CreateProcess` with a security-capabilities
   attribute). Moderate, and entirely offline.
10. **Migration:** smallest of the three. Workspaces gain a container-SID ACE (under PV-20 they
    become separate execution repositories, R4a-B); the token stops being readable; the hook
    channel moves off the bare `run/` — a scoped code change, not a data migration. *Superseded in
    part (PV-20 §6.2, §7.5; ADR-0053):* making the token unreadable is **read-bounding only and is
    not sufficient**. Core's effect boundary is a separate, required layer — Core refuses the
    closed privileged-effect set to an execution origin established by OS attestation (R1-A), and
    execution-influenced code never runs under the user's identity, including in verification
    (R4b). And the hook channel moves to PV-20's seven separate resource classes, not into one
    granted per-execution directory.

**Limitations to state honestly.** Deny-by-default is a compatibility burden (a missing capability
makes the CLI fail in opaque ways). It is an in-token sandbox, not a VM, so it does not stop a
kernel or privilege-escalation exploit — but the threat model is a prompt-injected or misbehaving
agent **with the user's ordinary privileges**, and the user's credential authorities and the local
token are **securable objects**, which is exactly what an ACL/capability boundary governs.

### B. Restricted token / separate execution identity

Two sub-variants, materially different.

- **B1, a restricted token** (`CreateRestrictedToken`: drop privileges, deny-only SIDs, restricting
  SIDs). It lowers what the process may do, but on its own it does **not** reliably deny reads of
  the user's own files: read checks still see the user SID in the normal group list unless the
  deny-only-plus-restricting-SID combination is built very carefully. This is the historically
  leaky "sandbox via restricted token" (the pre-AppContainer Chromium experience). **Too weak for
  the read-isolation property** on its own.
- **B2, a separate standard user** (a dedicated local account, e.g. `archeus-exec`, launched via
  `CreateProcessAsUser`/`CreateProcessWithLogon`). This is the **most robust read boundary**: a
  different user SID means the user's profile, `.ssh`/`.npmrc` material, the local token file, and —
  decisively — **DPAPI-protected secrets**, whose master key is per-user, are not usable by the
  exec identity. Even a readable file would not decrypt under another user.

For B2 against the ten criteria: Node/CLI run normally as the other user (1); children inherit the
identity automatically (2); the workspace needs an exec-user ACE (3); the Core channel is granted
the same way as AppContainer — PV-20's seven resource classes (4); **the e-stop is the complication (5)** — the live Core can kill
via the handle it retained at creation, but the **Core-down** path (`archeus estop`) opens the
process **by pid**, and a non-admin process cannot `TerminateProcess` another user's process, so
the Core-less kill would be denied unless the process's security descriptor is set at creation to
grant the launching user terminate rights; cleanup must also tear down the account's profile (6);
fail-closed on logon/token failure (7); `LogonUser` + profile load is slightly heavier than an
AppContainer launch but still negligible per turn (8); **operational complexity is the real cost
(9)** — provisioning the account and managing its secret (Core would hold a Windows credential, or
the account is created with admin once), and the per-user-installed `claude.exe`/Node under the
launching user's profile is **not readable by another user by default** and must be relocated or
ACL-granted; migration is therefore larger than AppContainer (10).

**Verdict for B:** B2 is the stronger boundary where DPAPI-grade credential isolation is required,
but it carries account provisioning, the install-location problem, and the Core-down-e-stop
complication. It is the **escalation path**, not the baseline.

### C. Windows Sandbox (or an equivalent disposable VM)

A disposable lightweight VM — a separate OS instance, so the user's profile, credential
authorities and local token are simply **absent** unless explicitly mapped in. Strongest isolation.

Against the criteria: inside the VM, Node/CLI run but are **not installed** — a clean sandbox each
start means a per-execution install (minutes) unless a custom base image is maintained (1);
confinement is total and children inherit it trivially (2); the worktree is a minimal read-write
mapped folder and nothing else is mapped, so credential stores and the token stay unreachable
(3, and this is the whole isolation argument — it holds only if the mapping is minimal); the Core
channel is the existing file mailbox over a mapped `run/exec/<id>/` with `run/local-token`
**unmapped** (4; *superseded for any tier by PV-20's seven resource classes, §7.5*); the e-stop can be "discard the VM," which is clean, but scripting a precise
per-execution teardown from the Core-down path is awkward (5); **cleanup is the best of the three**
— the VM is discarded (6); fail-closed if the VM cannot start (7) — **but on Home that is every
time**; startup is seconds-to-minutes, far heavier than A or B, and keeping a VM warm breaks the
clean-every-time guarantee (8).

**Decisive limitation (9):** Windows Sandbox requires **Pro/Enterprise/Education plus
virtualization** and is **not available on Windows Home.** This machine is Windows 11 Home and the
`Containers-DisposableClientVM` feature query failed, consistent with the feature being absent.
Archeus is Windows-first and targets general users, many on Home. Migration (10) is the largest —
an execution-in-VM model, a mapped-folder contract, and image management.

**Equivalents** (WSL2, a Hyper-V child partition, Docker Desktop, or an off-machine microVM) each
either change the workspace/credential semantics of a Windows code-change task, add a heavy
dependency, or move code off the machine against the local-first design. None is a V1.x baseline.

### Supporting control — the Job object (named in ADR-0051, not an identity boundary)

A Job object is **not** an ACL/identity boundary — it cannot deny a read of a credential store or
the token. What it does give, on **all editions with no admin**, is an atomic **kill-on-close of
the whole process tree** (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`), resource caps, and UI restrictions.
It strengthens the e-stop's "kill the whole tree" guarantee and the "children stay confined and
killable" property. **Recommendation: adopt the Job object as the kill/containment envelope
regardless of which identity mechanism is chosen,** paired with an identity boundary — never
instead of one. PV-20 adopted it as the **process-lifetime authority**: a Core restart reconciles
with the Job or terminates and fails the execution (PV-20 §3.7). *Superseded 2026-10-07 by R6-A
(ADR-0053):* Core is the Job's only holder and Core's death ends the isolated tree, so a restarted
Core has no Job to reconcile with — it reconciles its records and terminates, reaps and fails; a
live isolated process is never re-adopted.

## 4. Comparison

| Criterion | A. AppContainer | B2. Separate user | C. Windows Sandbox |
|---|---|---|---|
| Node + CLI run | yes (capability/ACE profiling needed) | yes (install must be exec-readable) | yes (install into VM / image) |
| Child inheritance | automatic (lowbox propagates) | automatic (identity inherited) | total (whole VM) |
| Workspace R/W | ACE on the execution's own workspace (a separate execution repository, PV-20 R4a-B; the user's `.git` never granted) | the same, exec-user ACE | minimal mapped folder |
| Core channel reachable, token not | PV-20's seven separate resource classes (§7.5); token never granted | the same | the same classes mapped separately; token unmapped |
| e-stop | both halves work | **Core-down kill needs handle/SD grant** | VM teardown; precise teardown awkward |
| Cleanup | remove ACEs, delete profile | remove ACEs, tear down profile | discard VM (best) |
| Fail-closed | yes | yes | yes — **but always, on Home** |
| Startup cost | negligible | small (logon/profile) | **seconds–minutes** |
| Editions / admin | **all editions, no admin** | all editions; account provisioning | **Pro/Ent/Edu only; not Home** |
| Migration weight | **smallest** | medium–large | largest |
| Credential-read isolation | strong (securable objects) | **strongest (DPAPI per-user)** | strongest (absent in VM) |

## 5. Recommendation

For V1/V1.x on Windows, the most viable mechanism is **AppContainer as the primary identity/ACL
boundary, wrapped in a Job object for tree-kill and resource caps**, with the **separate-standard-
user identity (B2) documented as the escalation path** where a specific credential authority
proves not to be governed by the AppContainer boundary or where DPAPI-grade isolation is required.

Why AppContainer is the baseline:

- It **works on every edition, including Home** (this machine), and needs **no elevation and no
  separate account or password to manage** — the two operational costs that make B2 and C heavy.
- Its deny-by-default model makes the user's **securable** credential authorities and the local
  Core token unreachable by the simple act of **not granting** their ACEs, which is precisely the
  requirement behind the two Critical findings.
- It **is designed to confine child processes automatically** (lowbox propagation), which is the
  stated PV-13 deliverable ("a Node CLI plus its child shells") — **DESIGN PROPOSAL — UNVERIFIED**.
- Its **startup cost is negligible** and its **migration is the smallest** — ACE the execution's
  workspace and split the hook channel into PV-20's seven resource classes.

Why not the others as the baseline:

- **Windows Sandbox** is the strongest isolation but is **disqualified as the default** by its Home
  unavailability, its heavy per-execution startup, and the size of the architectural change. Keep
  it as an **optional maximum-isolation tier** for Pro/Enterprise users and as a candidate for the
  future V2-A5 desktop-control risk class — not the V1.x baseline.
- **Restricted token alone (B1)** is too leaky for read-isolation. **Separate user (B2)** is robust
  but adds account provisioning, the per-user install-location problem, and the Core-down-e-stop
  complication; it is the escalation path, not the baseline.

### The one empirical step PV-20 must take before committing

PV-13's named deliverable is *confinement achievable for a Node CLI plus its child shells.* This
study **expects** AppContainer to achieve it — an expectation, not a proven result (**DESIGN
PROPOSAL — UNVERIFIED**); the single unknown that only a spike can close is the
**exact capability/ACE set** a real code-change turn needs under deny-by-default. PV-20's first
build step should therefore be a minimal confinement proof, asserted as booleans only: a Node
process launched into an AppContainer spawns a child shell; both are confined; the worktree is
writable; a **synthetic sentinel** planted in a user-owned store and the local-token path both read
**access-denied**. That proof is the go/no-go for the mechanism and the "before" baseline for
PV-20's acceptance delta. **This step was attempted on 2026-10-07 and did not complete** (PV-20
§7.3): the spike harness's `SECURITY_CAPABILITIES` payload was accepted by the process-attribute
call, the launch under test then returned `ERROR_NOT_APPCONTAINER` for every identity tried, and the
one launch that did start was **discarded** because the child's token carried no AppContainer SID and
so proved nothing. That is a shortfall of the spike harness, not a verdict on the mechanism. The
result is therefore **still unknown and the recommendation above remains unproven.**

## 6. What this study does not decide

- It does not authorise PV-20 or choose PV-20's final design — that is PV-20's ADR, the user's
  decision.
- It does not solve the **network-egress** gap (Finding 3), which **P23 owns** with the sandbox
  harness. AppContainer can also gate network via the `internetClient` capability, which overlaps
  P23's concern; PV-20 records the overlap as a dependency and does not solve it here.
- It does not change ADR-0051's historical V1 decision: the OS gap is an **acknowledged existing
  limitation**, not an accepted security state. Its concrete form, findings G1 and G2, stays open
  as Critical until PV-20 lands and proves the boundary with evidence.
