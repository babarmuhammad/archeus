# T-071 · Strict-storage mechanism decision: bounded namespace alternatives survey

Prepared by **Qwen** (pi, `spark/qwen3.8-flash-next`), 2026-10-14, card T-071 (standing
parallel-request auth; owner preventive-routing policy of 2026-10-12 — routing justified by
the prior classifier-stopped strict creator/namespace family, **no new refusal claimed on
this card and no withheld content reconstructed**). Analysis only.

**Scope compliance.** Read-only repo reads plus read-only fetches of the public
documentation named below (`curl`/interpreter, output kept only in a system-temp scratch
outside `D:\Claude` — nothing fetched was stored in the project; practice as T-046/T-050
declared their WebFetch reads) **(superseded by Correction r2, finding 1)**. **Not done, by the card's exclusions:** any check of what
is installed or enabled on this machine (edition, Hyper-V state, container feature state —
deliberately uninspected), any CLI/account/credential/env inspection, any experiment, any
native operation, any process of the system under test, any code/test change, any
deployment, any price, any package or vendor choice. Two family descriptions only, per the
card. The mechanism stays unchosen until an owner decision plus evidence.

Label discipline (as in T-052, extended):
- **PINNED** — direct quotation from a primary documentation page fetched this session, URL cited.
- **OBSERVED** — a repo/collab artifact exists and is cited (file:line at the recorded commit, or a board/closeout record).
- **INFERRED** — reasoned from the pinned material; the pin it leans on is named; not tested.
- **UNKNOWN** — no evidence either way; only a named, separately authorized run settles it.

## 1. The decision this informs, and what it must not become

T-004 stays **BLOCKED BY OWNER**: strict R7 (design §3.1 line 74 "other executions' state
is inaccessible to it"; §6 line 646 "IMPLEMENTATION CONSTRAINT"; ADR-0053:163) is open
because an execution chooses the creation descriptor of objects it creates — observed: P
created `explicit.txt` naming peer Q and Q read and wrote it, with no WRITE_DAC anywhere
for P (writer/creator closeout obs. 1–6, as separated in T-052 Correction C-1013-T052
§1–§2). Whether the user-mode M1 closes this is UNKNOWN until actual token semantics
(traversal privileges, LUID names looked up, not assumed). This note surveys **two of**
the privileged families T-052 §3-M4 named "never surveyed, priced or run"; it is that
bounded first pass, not the mechanism spike, and it selects nothing.

Two constraints carried, not re-argued:

- **"A separate account is not a namespace."** T-052 correction §3 stands: separate
  machine accounts alone are not proof of a separate object namespace or of creator-DACL
  containment. Each family below must therefore earn its isolation claim from the
  **documented kernel/namespace boundary it crosses**, never from "the peer has a
  different account". Anything that only changes the username answers a different question.
- **Same-user deputies are in scope** (T-052 correction §4, per ADR-0053 lines 111-115,
  288-303): any helper, agent or daemon introduced by a family below is itself an
  Archeus-managed component and inherits R4a/A5 + R4b/A6 — it must never execute or load
  execution-influenced content, and it must not become the side door the boundary was
  meant to close.

What T-052 already settled is *reused*, not repeated: the five levers (§2), M1's UNKNOWN
coverage pending token semantics, the F1 (applied-ACE ledger / DACL read-back) and F5
(mask gate) carry-overs, the E1/E2 evidence plan, and the refusal to offer R7 narrowing.

## 2. Family A — per-execution VM-backed namespace (the Hyper-V family on this host class)

The shape: each execution runs inside its own virtual machine; execution-created objects
live on guest storage the peer executions cannot address at all, because they are in a
different OS instance. The host-relevant primitive on Windows client is Hyper-V.

### A1 — Required host privilege and edition (PINNED)

- Hyper-V itself: "Windows 10 (Pro or Enterprise), or Windows 11 (Pro or Enterprise)
  64-bit Processor with Second Level Address Translation (SLAT)"; and to enable it,
  "You must run PowerShell as an Administrator, or the commands fail." —
  `virtualization/hyper-v-on-windows/quick-start/enable-hyper-v`.
- Windows Sandbox (the disposable-VM variant): "not supported on Windows Home edition",
  supported on Pro / Enterprise / Education / Pro Education-SE; "It relies on the Microsoft
  hypervisor to run a separate kernel that isolates Windows Sandbox from the host." —
  `windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-overview`.
- Host→guest control: PowerShell Direct "On the Hyper-V host, open PowerShell as
  Administrator" for every documented invocation; failure cause documented verbatim as
  "You're not a Hyper-V Administrator."; guest access needs explicit credentials —
  "Since virtual machines don't give the host implied administrator access, you need to
  explicitly enter credentials."; "PowerShell Direct supports Just Enough Administration
  (JEA)." — `virtualization/hyper-v-on-windows/user-guide/powershell-direct`.

**Consequence (INFERRED from A1, primary pins named):** Archeus Core runs today as an
ordinary user process (the whole S1/S2-G design assumes no elevation; T-052 §3-M1
"Privilege: none beyond the current user-mode design"). Nothing in the pinned material
lets a non-elevated process create, manage or drive VMs. Family A therefore **requires a
new privileged component** — an elevated helper (system service or JEA endpoint) owned by
the deployment — before any per-execution VM shape exists at all. That helper is the
family's central security obligation, not an implementation nicety **(superseded by Correction r2, finding 2; see "Finding 2" below)**.

### A2 — Identity and creation authority (the actual R7 question)

- Inside the boundary: the pinned separate-kernel sentence (Sandbox) is the strongest
  documented isolation statement fetched for this family; the FAQ sentence for Hyper-V
  isolation containers (§3 below) is its container-management analogue. Under it, an
  execution's creator-chosen descriptors only ever name peers **within the same guest**,
  and there is no second execution in that guest in this shape — so the cross-execution
  creator-descriptor breach (obs. 5) has no two reachable objects to occur between
  *inside the guest*. INFERRED from A1/A3 plus the guest-internal shape; it is a
  structural argument, not a test: no run in this repo has ever exercised a VM boundary.
- Host side of the boundary: every artifact that matters to Archeus — the imported tree
  (K3), logs, evidence — crosses back as a file **created by the host-side copier**
  (Core or the A1 helper), so the creator-authority question does not vanish; it moves to
  that copier, which is Core-owned code subject to F1/F5 and the deputy rule. That is
  exactly the shape T-052 M3 could not achieve for arbitrary third-party writers in user
  mode: here "all writes to shared storage are Core-mediated creates" is enforced by the
  boundary (INFERRED — the enforcement point "guest cannot write host paths that are not
  mounted" rests on A3's exclusion list; no guest escape is claimed or tested).
- Separate account? The guest is a full OS instance, not an account on this one. But note
  the trap named in §1: an implementation that merely runs each execution under a
  different *local domain account* on the same host is NOT this family and gains nothing
  pinned here.

### A3 — Shared-volume exclusions (PINNED for the analogue, INFERRED here)

- Pinned for containers (§3, same platform's shared list): host↔guest sharing exists only
  as explicit documented mounts (files/volumes, named pipes, ports, network namespace,
  device visibility) — that page is the design rule: **share nothing execution-reachable**;
  seed (K2) and import (K3) cross via Core-mediated copies through the A1 helper channel.
- For full VMs the equivalent exclusion is stronger by default (no host filesystem is
  visible to a Windows guest without a configured share/agent): **INFERRED** — the
  Hyper-V "drive resource"/enhanced-mode sharing docs were NOT FETCHED this session;
  named pin-target before relying on the default-deny sharing claim.

### A4 — Handles, deputies, network paths

- Handle passing across the boundary: **no documented primitive was fetched**, and none
  exists in the repo's observations; recorded as UNKNOWN in the sense "no mechanism here
  claims it is closed by documentation" — any host-side helper holding privileged handles
  or RPC into guests is itself the new T-052 §2(d) surface and needs the C6-style probe
  against *it*.
- **Job/R6-A:** Core's containment today is the Core-held kill-on-close Job (T-030 §1
  fence, T-054 §1 order; ADR-0053 R6-A: no isolated process outlives the Core that holds
  its Job — pinned in-repo at `docs/architecture/execution-architecture.md:351`, which
  also says remote nodes are deferred and "before one runs isolated executions it needs
  its own PV-20 analysis — nothing here decides it"). A VM is the same shape one level
  up: the *helper* becomes the holder whose lifetime matters; R6-A does not translate
  automatically. INFERRED; a family-A design owes its own R6 analysis (exactly what
  :351 requires of a remote node).
- Network/broker (T-050): pinned "Windows Sandbox enables network connection by default.
  It can be disabled using the Windows Sandbox configuration file." For the VM family, an
  execution's loopback is the *guest's* loopback: the broker listener cannot live where
  it was designed (host loopback reachable from the execution) unless routed through the
  guest-reachable network; per-VM network policy = virtual-switch configuration, docs
  NOT FETCHED, named pin-target. T-053 origin attestation: mapping a host-side connection
  to a process inside a VM is outside the host TCP-table evidence T-053 assumed —
  attestation there would depend on a **trusted in-guest agent**, which is new trusted
  code inside adversary territory (deputy rule applies). INFERRED; both are design
  consequences to verify, not claims.

### A5 — Retention

Pinned: "The sandbox is temporary; closing it deletes all software, files, and state" and
"Everything is discarded when the user closes the application" — the disposable shape
directly conflicts with the project's keep-all/reversible-defaults rule (README standing
rule; T-030/T-039 keep-all precedents). A per-execution VM family therefore *retains*
per-execution disks and state files under `ARCHEUS_HOME` (keep-all default), a
GB-per-execution-class material owner decision, with cleanup only under its own card.
The same pinned page kills the zero-effort lifecycle shortcut: "Windows Sandbox currently
doesn't allow multiple instances to run simultaneously" — **no per-execution parallel
Sandbox**, so the only shape left is the full VM-management stack behind the A1 helper.

### A6 — Minimum Archeus seams (where this would bolt on)

The seam already exists and was built for exactly this: `archeus/core/ports.py:62`
`Node` Protocol (`spawn/stop/pause/inspect`) and `archeus/node/local.py:9` — "it is what
a remote node would be, in-process". The single early isolation decision (T-023), its
durable record (T-036) and lifecycle fallback (T-038) flow `isolated=` into
`node.spawn`; a family-A node implementation consumes that value without re-deciding.
Concretely (future scopes, none executed here — §5): one new `archeus/node/vm_node.py`
(fake-testable), one helper-RPC contract module, `paths.py` additions for per-execution
VM storage in `V1_OWNED` (keep-all), and zero edits to the manager decision plumbing.
What must NOT be quietly reused: `LocalNode`'s Job/kill and the AppContainer profile
machinery do not cross the boundary; a family-A node's stop/kill contract is the helper's
VM lifecycle plus whatever in-guest control channel A1's helper exposes.

## 3. Family B — documented OS-enforced container/namespace variants

The shape: executions run as OS-level containers on this host's kernel (process
isolation / namespace technologies) or in the container-management stack's VM-isolated
mode; on this host class the documented management stack is Windows containers.
(Linux-namespace execution via WSL 2 is treated inside this family as its documented
Linux-namespace shape, B6.)

### B1 — The two documented modes, pinned (all from `virtualization/windowscontainers/…`)

- Two modes exist: "Windows containers offer two distinct modes of runtime isolation:
  process and Hyper-V isolation." (`manage-containers/hyperv-container`)
- Process isolation is namespace technology on the shared kernel: "multiple container
  instances run concurrently on a given host with isolation provided through namespace,
  resource control, and other process isolation technologies"; the overview page pins the
  shared-kernel premise ("Containers run on top of the host operating system's kernel")
  with its own hedge ("While a container shares the host operating system's kernel, the
  container doesn't get unfettered access to it"). (`about/`, `hyperv-container`)
- Hyper-V isolation is Family A wearing a container face: "each container runs inside of a
  highly optimized virtual machine and effectively gets its own kernel", and the
  strongest isolation sentence fetched this session: "Hyper-V isolation… ensures that
  code running in one container can't compromise or impact the host operating system or
  other containers running on the same host." (`hyperv-container`, `about/faq`) —
  **PINNED, but stated for containers; adopting it for per-execution untrusted workloads
  is an extension of the documented claim, not its test.**

### B2 — Client-SKU supportability for this deployment (PINNED — the load-bearing evidence)

- "Windows containers running on Windows 10 Pro and Enterprise default to running with
  Hyper-V isolation." "Running with process isolation on Windows 10 Pro and Enterprise is
  meant for development/testing." "Starting with the Windows 10 October 2018 update,
  users running a Windows 10 Pro or Enterprise host can run a Windows container with
  process isolation [via explicit request]." (`hyperv-container`)
- FAQ: "The number of containers a user is allowed to run depends upon the host OS
  edition and the isolation mode… as well as whether these containers are running for
  dev/test purposes or in production." — and its table lists, for the client row
  `Windows Pro and Enterprise`, both container-limit columns reading
  `Unlimited (for test or development purposes only)` — the **same** wording for the
  process- and the Hyper-V-isolated columns; production container-image use
  is routed through commercial agreements (IoT). (`about/faq`; fetched text may carry
  layout noise — quotations taken from the table row verbatim, edition-coverage sentence
  paraphrased)

**Reading (INFERRED from the pins, bounded):** on a client host of this class, the
genuinely-OS-namespace variant (process isolation) is *documented as development/testing
only* — running untrusted peer executions in it as a production control is **outside the
documented support surface: unsupported evidence, not impossibility** (the card's exact
requirement). And the mode the docs do point production users toward on client (Hyper-V
isolation) converges into Family A's hypervisor boundary — so "container variant" on this
host buys a management stack, not a different security boundary from §2's VM family **(the production clause is superseded by Correction r2, finding 3; the convergence clause stands)**. The
host's actual edition/feature state is intentionally uninspected (card exclusion); even
the best case inherits A1's edition gate and the FAQ's dev/test wording.

### B3 — Shared-volume exclusions and mounts (PINNED, and the reason mounts are the design risk)

Pinned support list: "mapping shared files or volumes from host into the container /
mapping a named pipe from host into the container / mapping a port from the host into
the container / customizing and sharing the network namespace / sharing host device
visibility into the container"; pinned non-support, one run-on fetched string quoted with
separators restored: "shared memory sharing / synchronization objects (semaphores,
mutexes, etc) / shared process namespaces" — shared memory, synchronization objects and
shared process namespaces are not supported (separators inferred from the stripped table
text; layout caveat). (`hyperv-container`) — Design consequence (INFERRED): sharing is opt-in, so
the storage design must mount **nothing execution-reachable**; K2 seed-in / K3 import-out
cross via the Core-mediated copy channel only. The moment an execution-writable host
directory is bind-mounted in, the *exact* obs. 5 creator-descriptor breach reappears on
that mount, kernel sharing or not — a container is not an ACL **(superseded by Correction r2, finding 4 — conditional risk, not a reproduced breach)**. Process-namespace
non-sharing is pinned (good for handle-passing); the **container identity that lands on
mounted host files** (which SID a containerized process writes as on the host) was NOT
FETCHED — named pin-target; without it, host-side peer exclusion on any shared surface
under Family B is UNKNOWN.

### B4 — Creation authority and network/attestation paths

- Container create/list/run goes through a host privileged management path (daemon /
  Host Compute Service surface): the fetched pages show elevated host setup; no direct
  quotation about non-admin container permission was fetched — **INFERRED with named
  pin-target** (`docker setup`/`hcs` surfaces). Same conclusion shape as A1 but milder:
  likely one setup-time grant per deployment, not a per-spawn elevated broker — to be
  pinned before relying on it.
- Network: containers get a configurable network namespace (pinned, B3); the execution↔
  broker loopback (T-050 Q2, still unresolved even for AppContainers on T-008) becomes a
  *per-mode* question: under Hyper-V isolation it is Family A's problem; under process
  isolation it is an HNS/NAT configuration whose loopback semantics were NOT FETCHED —
  UNKNOWN. Origin attestation (T-053): the host-side TCP-table identity behind the K-O1
  attestor covers a container's processes only as far as the shared kernel exposes them —
  process isolation likely observable (host shares the kernel; INFERRED), Hyper-V
  isolation not (Family A's in-guest-agent problem). UNKNOWN either way until probed.

### B5 — Peer exclusion *inside* Family B (the R7 question, per mode)

- Hyper-V isolation: inherits §2's structural argument (per-instance kernel).
- Process isolation: peers share the kernel; peer exclusion then depends on exactly the
  documented "namespace, resource control" machinery plus **ordinary NT ACLs on the
  container-visible storage** — i.e. the obs. 5 gap unchanged for any object peers can
  both reach **(superseded by Correction r3, finding 3 — "gap unchanged" is not
  established either way; mechanism-specific peer exclusion is UNKNOWN until r2 Finding 4's
  peer-reach and mounted-identity/creation-authority conditions are settled)**. Its isolation claim collapses to B2's dev/test wording plus the mount
  exclusion of B3: no separate storage, no boundary; documented, and not production-
  supported.
- Retention: containers are image+layer artifacts whose removal is the documented
  lifecycle; keep-all conflicts the same way A5 does (cleanup card required either way).
  INFERRED from the pinned "container is an isolated, lightweight package" framing; no
  retention doc fetched — pin-target if pursued.

### B6 — The documented Linux-namespace shape on this host (WSL 2), kept short

Linux namespaces proper on this deployment mean WSL 2 (documented as running a real
Linux kernel in a lightweight utility VM — the WSL pages **returned only a JS shell to
this session's fetches; treated as an un-fetched pin-target, not asserted**). The
execution harness today launches Windows binaries (the recorded real call ran
`claude.exe` under `C:/Users/mab/.local/bin/claude.exe`, board T-060 verify) and the hook
is Windows stdlib Python (T-032). Running executions under Linux namespaces therefore
means replacing the CLI/hook/runtime stack, i.e. an architecture migration of the harness
boundary, not a switch — and the Node seam (A6) is exactly the place such a shape would
attach. Reported as **UNKNOWN/unsupported-for-current-harness evidence, not
impossibility**: no WSL doc pin, no trial, no claim.

## 4. The two families against the requirements that already exist (bounded comparison)

| requirement | A · per-execution VM | B · OS container/namespace |
|---|---|---|
| closes obs. 5 (creator descriptor) where objects actually live | yes **structurally** (INFERRED A2) | process mode: **no** on shared storage (B5) **(superseded by Correction r3, finding 3 — process-mode peer exclusion is UNKNOWN pending r2 Finding 4's two conditions, not an established "no")**; Hyper-V mode: as A (convergence B1) |
| client-SKU production support documented | edition+elevation gates pinned (A1); workload shape itself untested here | **unsupported wording** for client (B2); Hyper-V mode inherits it too |
| new privileged component | **required** (INFERRED A1) **(superseded by Correction r3, finding 1 — only the documented operations' privileges are pinned; the component's existence and shape are UNKNOWN)** | daemon grant (B4, pin-target); Hyper-V mode: A's helper **(same marker — "A's helper" is an undecided shape, not a pinned component)** |
| R6-A job/lifetime | must be re-derived (A4; :351's own demand) | process: shared-kernel, new analysis; Hyper-V: as A |
| T-050 broker loopback | guest-network redesign (A4) | per-mode, HNS loopback unfetched (B4) |
| T-053 origin attestation | in-guest agent needed (A4) | process: maybe host-visible (INFERRED); Hyper-V: as A |
| K1–K3 seed/import | copy-channel via helper; store stays host-side Core-owned (A3) | mounts forbidden; same copy channel (B3) |
| deputy surface (ADR-0053 111-115/288-303) | helper+agent are in scope (A4) | daemon is; agent-free under process isolation (INFERRED) |
| keep-all retention | per-VM disks, GB/exec (A5) | layer artifacts, same conflict (B5) |
| per-execution parallel | full VM stack (Sandbox pinned single-instance) | concurrent by definition (B1 pinned) |
| reuses existing seams | Node Protocol + isolated decision (A6) | same seam, thinner helper |

No cell is a coverage guarantee; each names its label above. This is a comparison of two
documented families, not a survey of mechanisms — nothing in the table has ever been run
against this repo's threat model.

## 5. Bounded owner decision options (input to T-004; unchosen until owner + evidence)

- **O1 — settle the user-mode question first (cheap, sequenced):** run T-052's E1
  (two-worker temp-fixture: positive control, no-peer-allow ancestor, explicit-peer-deny
  ancestor doubling as E2, handle probe with C6, alias probe) under its own named
  authorization. It prices M1 honestly and is *the fallback test either way* — O2/O3 do
  not withdraw it. Changes nothing about T-004's blockage by itself.
- **O2 — Hyper-V-isolated containers as the mechanism shape:** strongest pinned isolation
  sentence (§3 B1), existing management stack, but carries B2's client-SKU dev/test
  wording as an accepted support risk or requires further primary evidence the owner
  commissions; needs the B4 daemon-grant pin and B3's mounted-identity pin before any
  claim; storage still Core-mediated copies. Unchosen.
- **O3 — per-execution full VMs with an owned privileged helper (A1's JEA shape):** the
  most complete structural answer to obs. 5 (A2), at the cost listed in A1–A6 — new
  trusted helper, own R6 analysis, network/attestation redesign, GB-class retention,
  pinned Sandbox-instance limit forcing the full stack. **No documentation fetched
  documents this per-ephemeral-execution usage; its fit is UNKNOWN pending a spike.**
  Unchosen.
- **O4 — process-isolated containers for untrusted peer executions:** recorded as the
  card asked — **unsupported evidence on this host class** (B2), not a generic
  impossibility claim. Available only as the owner knowingly accepting dev/test-scoped
  documentation for a production control, which this note does not recommend and cannot
  disprove.

Each option names what the owner signs (support risk / new trusted helper / retention
volume) and the evidence card that precedes it **(superseded by Correction r2, finding 5 — the per-option manifests below replace this blanket sentence)**. T-004 remains blocked; R7 unchanged; no
mechanism selected here; E1's result informs O1's value and every fallback, so nothing
above substitutes for it.

## 6. Exact future file scopes (named here, none touched by this note)

- Family A code (later cards, fake-only slices first): `archeus/node/vm_node.py` (new,
  Node Protocol implementer), `archeus/node/helper_rpc.py` (contract module),
  `archeus/infra/paths.py` (`V1_OWNED` addition + per-execution storage helpers),
  `tests/v1/unit/test_pv20_vm_node.py` (fake helper, zero native). Manager/decision files
  (T-023/T-036/T-038 seams) deliberately absent — consumed, not edited.
- Family B code (later cards): same Node seam + a `container_node.py` sibling,
  `paths.py` staging helpers; mounts never named in code without a card naming B3's pins **(superseded by Correction r2, finding 5 — Family B's fake-test and native file scopes are named per-option in "Finding 5" below)**.
- Native/evidence cards either family would need (owner authorization **naming each
  operation** — README hard rule; nothing here authorizes any): the feature/edition
  *query* (read-only, replaces the inventory this card deliberately skipped), one
  disposable boundary fixture, boundary-crossing copy round-trip, in-guest/in-container
  broker reach, kill/lifetime observation, container-mount SID-identity observation.

## 7. Named unknowns and un-fetched pin-targets (no claim rests on any of these)

Traversal/token semantics still gate M1 (T-052 correction §1, unchanged); Hyper-V
drive-resource/enhanced-mode sharing; per-VM virtual-switch policy docs; PowerShell Direct
JEA delegation details; non-admin container-permission statement; container-write SID
identity on host mounts; HNS loopback semantics for process isolation; WSL 2 utility-VM
architecture pages (JS shell returned to fetches — recorded as un-fetched, not asserted);
this host's edition/feature state (uninspected by rule); no Git/version or perf data for
any family; whether either management stack can run *two* boundary fixtures at once under
one Core (parallel-closeout rule untested).

## 8. What this note does not claim

No mechanism is asserted to work; every cell above carries its label and none has been
run. No third family surveyed (the card's limit), no vendor/product named or priced, no
installed-state inventory, no experiment, no native operation, no R7 relaxation, no
T-004 unblock, no claim that any privileged helper exists yet, no statement about whether
this machine can enable anything. Ordinary implementation stays Claude's; this note is
analysis, by Qwen, under T-071's preventive-routing auth — which carries no execution,
authoring, validation or run permission beyond reading what is cited here.

Fetched sources (all learn.microsoft.com, fetched 2026-10-14, quotations extracted from
page text — short quotes kept verbatim; where fetched text looked like table/layout
noise the sentence is paraphrased and labelled INFERRED):
`virtualization/hyper-v-on-windows/quick-start/enable-hyper-v` ·
`windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-overview` ·
`virtualization/hyper-v-on-windows/user-guide/powershell-direct` ·
`virtualization/windowscontainers/manage-containers/hyperv-container` ·
`virtualization/windowscontainers/about/faq` ·
`virtualization/windowscontainers/about/`.

---

## Correction r2 (2026-10-15, Qwen)

Appended in answer to Codex's `reviews/T-071-analysis.md` (VERDICT: CHANGES, five findings)
on card T-071. Append-only: no earlier line was deleted or reworded; each passage Codex
named now carries an inline "(superseded by Correction r2, finding N)" marker where it was
said, and the corrected statement is here under its finding number. This session ran no
web fetch, no experiment, no process of the system under test, no native or ACL operation,
no test, and changed no file except this note and the T-071 card; the file paths in
"Finding 5" were found by read-only directory listing of `archeus/` and `tests/v1/` in
`D:\Claude` (`archeus-v1-rearchitecture`) and of `archeus/node` and `tests/v1/unit` in the
`D:\archeus-pv20-s2-l` worktree (`pv20-s2`) — listings only, no command against any product
file. Mechanism stays unchosen; T-004 stays BLOCKED BY OWNER; R7 unchanged.

### Finding 1 — the fetch scratch *was* fetched-page-file storage; the verify line was NOT fully honored

What the note said (§Scope compliance, line 9): the six page reads were `curl` plus an
interpreter tag-stripper, "output kept only in a system-temp scratch outside `D:\Claude`
— nothing fetched was stored in the project". Codex is right that this conflicts with the
card's verify line, which excludes **"no fetched page files"** without restricting that to
the repository. Reading the exclusion as repo-only was the deviation.

- **Where, and in what form (correcting the record, from the delivering session's own
  declaration):** the six `learn.microsoft.com` pages were saved as **files in the Windows
  system-temp scratch directory of the delivering session's account**, outside the project
  tree, in two forms: the raw HTML captured from `curl`, and the tag-stripped plain text
  the quotations were copied out of by the interpreter stripper. So fetched page files
  **were written** — outside `D:\Claude`, not inside it.
- **The verify line "no fetched page files" was NOT fully honored.** The claim that stays
  true is narrower: no fetched page file was stored in the project, and no product file
  was touched. What must be withdrawn is any implication that the run left no fetched page
  files anywhere. (OBSERVED — this correction's own record: the card's `notes:` deviation
  sentence, and this note's line 9, both described the scratch and neither recorded a path
  or filename.)
- **Those files were not deleted and were not re-inspected here.** The delivering session
  recorded only "a system-temp scratch", with no path and no filenames, so they cannot now
  be enumerated, audited or reproduced from the record; no hash or byte-exact archive of
  the six pages was kept in the repo either. Deleting or preserving them is an **owner
  decision**, not this session's — nothing was removed. This session ran no fetch, so it
  could not and did not re-inspect them.
- **What this does to the PINNED label (stated exactly, not softened):** every PINNED
  quotation above means *copied verbatim from the fetched text as it was captured in that
  scratch*, and Codex's own "Not checked" line records that it did not compare quotations
  to the originals. So no PINNED sentence here is verified against the live page. That
  reaches the load-bearing pins: B2's client-SKU table cells, A1's enablement/
  PowerShell-Direct sentences, B3's support and non-support lists. Each stays PINNED-as-
  fetched and **unverified-against-source** until a re-fetch under a card authorizing it.
- **Card-side consequence for `verify:`** (for the owner/Codex to record, not for me to
  rewrite): the verify line needs either the exclusion stated as "no fetched page files in
  the project" or the scratch archival requirement added, so the next analysis card cannot
  read the wording either way.

### Finding 2 — documented privileges ≠ a required new elevated helper

The A1 quotations establish privilege requirements **for the documented operations**,
nothing more: "You must run PowerShell as an Administrator, or the commands fail"
(enablement), the edition/SLAT gate, Sandbox "not supported on Windows Home edition",
and for PowerShell Direct — host-side "open PowerShell as Administrator", the
"You're not a Hyper-V Administrator." failure text, explicit guest credentials, and
"PowerShell Direct supports Just Enough Administration (JEA)."

What the pins support, and no further:

- **PINNED:** the documented enablement and drive operations require the named privileges.
- **INFERRED (weakened from "requires a new privileged component"):** nothing in the
  material fetched shows a non-elevated process creating, managing or driving VMs, so on
  the evidence in hand a family-A deployment needs **an elevated privileged management path
  of some shape** somewhere between Core and the hypervisor.
- **UNKNOWN (was asserted):** that this must be a *new, deployment-owned, always-on helper
  (system service or JEA endpoint)*. Whether a non-elevated or delegated management shape
  exists — a JEA endpoint configured by the deployment, pre-provisioned VM definitions, a
  one-time admin provisioning step leaving an ordinary-process control path, per-VM
  delegation, or any other delegated-management surface — is **UNKNOWN pending applicable
  documentation**, which was not fetched. The single JEA sentence is a pointer to a
  capability that exists, not evidence for or against any of these shapes. Named
  pin-targets before this is closed: JEA configuration docs, Hyper-V role-delegation docs,
  any non-admin VM-management statement (§7 already lists the PowerShell Direct JEA
  delegation detail as un-fetched).
- **What survives of "central security obligation", restated conditionally:** *if* the
  deployment chooses an always-on privileged helper, then that helper is the family's
  central security obligation and inherits the deputy rule (ADR-0053:111-115, 288-303) and
  the C6-style probe named in A4 — as before. Read O3's cost line as "a privileged
  management path whose shape is undecided", not "a new service".

### Finding 3 — no production recommendation toward Hyper-V isolation

The clause at :216 ("the mode the docs do point production users toward on client") is
removed. It contradicts the pins it sits on: the FAQ table's client row
`Windows Pro and Enterprise` reads `Unlimited (for test or development purposes only)` in
**both** container-limit columns, and production container-image use is routed through
commercial agreements (IoT). Nothing fetched names a production-recommended client mode.

Corrected, bounded:

- **PINNED (unchanged):** "Windows containers running on Windows 10 Pro and Enterprise
  default to running with Hyper-V isolation"; "Running with process isolation on Windows
  10 Pro and Enterprise is meant for development/testing". These are defaults and a
  stated-purpose sentence for process isolation; **neither is a statement about production
  use of either mode on a client SKU**, and no production endorsement was fetched for
  Hyper-V isolation either.
- **INFERRED (replaces the removed inference):** for a client SKU used for *this*
  workload — untrusted peer executions as a production control — the supportability of
  **either** mode is **UNKNOWN / unsupported evidence**, because the only client-row
  wording the pins carry is dev/test-only in both columns. Not impossibility, per the
  card's requirement.
- **Stands on its own pins, independent of any production claim:** "each container runs
  inside of a highly optimized virtual machine and effectively gets its own kernel" — so a
  Hyper-V-isolated container crosses the same hypervisor boundary as Family A. That is the
  convergence claim, and it needs no production recommendation.
- **Corrected consequence of the paragraph:** using a container on this host class buys a
  management stack, not a different security boundary from §2's VM family **(superseded by
  Correction r3, finding 2 — the convergence clause covers Hyper-V-isolated containers only;
  process isolation shares the kernel per B1, so its namespace and storage guarantees stay
  conditional on applicable evidence)** — and no client
  production-support posture for untrusted peers is documented for either mode.

### Finding 4 — an execution-writable shared mount is a *candidate* breach surface, not a reproduced breach

:234 asserted that the moment an execution-writable host directory is bind-mounted in,
"the *exact* obs. 5 creator-descriptor breach reappears". obs. 5 is a specific observation
(T-052 Correction C-1013-T052 §1–§2; writer/creator closeout obs. 1–6): two executions of
the **same user**, both able to reach the object, P naming peer Q in the creation
descriptor, Q reading and writing it. Two of its conditions are **not established** for a
container mount, and this note earlier admitted as much in the same paragraph:

- **Peer reach — UNKNOWN:** whether two containerized executions see the same mounted
  surface at all depends on the deployment mounting one host directory shared by both, or
  a per-execution directory. Not fetched, not probed, not designed.
- **Mounted identity / creation authority — UNKNOWN:** which SID a containerized process
  writes as on the host was NOT FETCHED (§7, named pin-target). Without it, whether one
  containerized execution has the creation authority to name the other in a descriptor on
  host storage is unknown, and host-side peer exclusion on that surface is UNKNOWN — as
  this note already said.

**Corrected statement (conditional risk):** a host directory mounted into **more than
one** execution's container is a *candidate reproduction surface* for the obs. 5
creator-descriptor breach. It reproduces that breach **only if** the same peer identities
can both reach the mount **and** the containerized write identity carries the creation
authority that lets one execution name the other in a descriptor there. Both conditions are
UNKNOWN; **no breach is asserted as reproduced**, on any mount, kernel sharing or not.

The design stance survives, labelled as stance and not as evidence: mount nothing
execution-reachable; cross K2/K3 only via the Core-mediated copy channel; pin the
mounted-write-SID question before designing any mount. "A container is not an ACL" stays
**INFERRED** caution. The stronger claim this paragraph used to make is superseded.

### Finding 5 — per-option prerequisite manifests (O1–O4), each with its own evidence and file scope

Codex: the options named a sign-off and "the evidence card" but carried no individual
prerequisite or file manifest, and Family B had no fake-test or native file scope at all
(§6's Family B bullet is superseded by this section). Paths below were confirmed by the
read-only listings described at the head of this correction. Unless marked `(pv20-s2)`, a
path exists in `D:\Claude` on `archeus-v1-rearchitecture`; `(pv20-s2)` marks the files that
live on the `pv20-s2` worktree `D:\archeus-pv20-s2-l`. `(new)` = does not exist yet.
Consumed-never-edited seams for every option: `archeus/core/ports.py` (Node Protocol),
`archeus/core/execution/manager.py` (the one early isolation decision, T-023/T-036/T-038),
`archeus/node/local.py`.

**O1 — settle the user-mode question first (run T-052's E1/E2).**
- Documentation still needed: the token/traversal pins T-052 §5 named as E1 prerequisites
  (privilege-name lookup for the observed LUID, traversal-token semantics) — un-fetched.
- Architecture gate(s): none opens. `docs/architecture/p20-design-gate.md` §12 gains one
  dated item recording E1/E2's result. `docs/architecture/pv20-execution-isolation-design.md`
  §3.1:74 / §6:646 (R7) and `docs/architecture/decisions/ADR-0053.md`:163 stay untouched.
- Evidence cards that must precede it: none — E1 **is** the evidence card; it needs its own
  `auth:` naming the two-worker temp fixture, its writes, the handle probe (shared with
  T-008's still-unrun C6) and the alias probe, per the README hard rule naming each operation.
- Code: none. E1 changes no product source.
- Fake tests: `tests/v1/unit/test_pv20_isolation.py` — interpretation/assertion cases only,
  and only if E1's result changes what the fakes pin; otherwise no fake work.
- Native tests: `tests/v1/integration/test_pv20_isolation_windows.py` (existing, opt-in,
  `ARCHEUS_REAL_BOUNDARY=1`) — the E1/E2 cases live there under the card naming them.
- Cannot do: price M1 without unblocking T-004. **(superseded by Correction r3, finding 4 —
  this reversed the evidence-before-decision sequence; read the line below instead)**
- Can do (Correction r3, finding 4): run E1/E2 under their own `auth:` **while T-004 stays
  BLOCKED BY OWNER**; their bounded results may inform M1's assessment. They do not unblock
  T-004, price or accept a mechanism, close F1/F5, or touch R7.

**O2 — Hyper-V-isolated containers.**
- Documentation still needed: (i) the container-management permission statement for a
  non-admin create/list/run path (B4's daemon/HCS pin-target); (ii) the container-write SID
  identity on host mounts (B3/§7); (iii) HNS/loopback semantics under Hyper-V isolation
  (T-050 Q2); (iv) image/layer retention/lifecycle docs behind B5; (v) a primary statement
  covering *execution-chosen* descriptors on shared storage — the pinned FAQ sentence is
  about containers generally, not this workload, and stays an extension of the documented
  claim (B1 caveat).
- Architecture gate(s): a new `p20-design-gate.md` §12 item; `docs/architecture/execution-architecture.md`:351's
  own demand — a node shape that runs isolated executions needs its own PV-20 analysis
  before one runs them; the deputy scope `ADR-0053.md`:111-115, 288-303 for the daemon and
  any in-container agent; F1 (applied-ACE ledger / DACL read-back) and F5 (mask gate)
  carry-overs from T-052 stay open and must be satisfied for the copy channel.
- Evidence cards that must precede any claim: read-only feature/edition **query** card
  (names the query only, replaces the inventory this note skipped); one disposable boundary
  fixture; boundary-crossing copy round-trip (K2 seed-in / K3 import-out through the Core
  channel); the mount-SID observation card; native loopback reach for the containerized
  process (T-064's shape); origin attestation for it (T-068's shape); and the decisive
  two-execution cross-reach probe on the real boundary in obs. 5's shape.
- Code: `archeus/node/container_node.py` (new, Node Protocol implementer),
  `archeus/node/container_rpc.py` (new contract module), `archeus/infra/paths.py`
  (per-execution staging/import paths under `V1_OWNED`, keep-all).
- Fake tests: `tests/v1/unit/test_pv20_container_node.py` (new, fake daemon, zero native),
  `tests/v1/unit/test_paths.py` (additions), and — because T-024's private-config surface
  must be re-proved for a new node — `tests/v1/unit/test_pv20_private_config.py` (pv20-s2,
  additions).
- Native tests: `tests/v1/integration/test_pv20_container_windows.py` (new, opt-in, gated
  like `test_pv20_isolation_windows.py`), plus a mount-SID observation case in the same file
  under its own named authorization.

**O3 — per-execution full VMs behind an owned privileged path.**
- Documentation still needed: Hyper-V drive-resource / enhanced-mode sharing (A3's
  pin-target, which the default-deny sharing claim rests on); per-VM virtual-switch policy
  (A4 network); PowerShell Direct JEA delegation detail and the non-elevated/delegated
  management question of Finding 2; VM lifecycle/retention semantics behind A5; and a
  primary statement on **per-ephemeral-execution** VM use — none was fetched, so A2's and
  O3's fit stay UNKNOWN (as O3 already says).
- Architecture gate(s): a new `p20-design-gate.md` §12 item; `execution-architecture.md`:351
  (its own PV-20 analysis for a remote-shaped node — this node is exactly that shape); an
  R6-A re-derivation for helper-held VM lifetime (ADR-0053 R6-A; A4 says it does not
  translate automatically); `ADR-0053.md`:111-115, 288-303 for helper **and** any in-guest
  agent; F1/F5 carry-overs for the host-side copier; the pinned Sandbox single-instance
  limit forces the full VM stack (A5), so the stack itself is in scope, not an add-on.
- Evidence cards that must precede any claim: read-only edition/SLAT/Hyper-V feature
  **query**; one disposable single-VM fixture; copy round-trip through the helper channel
  (guest → host import, creator = the Core-owned copier); in-guest broker reach (T-064's
  shape, one level up); in-guest attestation, which needs a trusted in-guest agent — new
  trusted code in adversary territory, deputy rule applies (T-068's shape);
  kill/lifetime (R6) observation of a VM-hosted process tree; and the cross-execution probe
  showing obs. 5's shape cannot occur between two guests.
- Code: `archeus/node/vm_node.py` (new), `archeus/node/helper_rpc.py` (new contract module),
  `archeus/infra/paths.py` (per-execution VM storage in `V1_OWNED`, keep-all). The helper
  itself (service or JEA endpoint, shape per Finding 2) is a **separate card with its own**
  `auth:` naming every operation it performs — never folded into a node card.
- Fake tests: `tests/v1/unit/test_pv20_vm_node.py` (new, fake helper RPC, zero native),
  `tests/v1/unit/test_paths.py` (additions), `tests/v1/unit/test_pv20_private_config.py`
  (pv20-s2, additions for the new node).
- Native tests: `tests/v1/integration/test_pv20_vm_windows.py` (new, opt-in) for the single
  fixture, copy round-trip, in-guest reach and lifetime observation — each operation named
  in that card's `auth:`.

**O4 — process-isolated containers for untrusted peer executions.**
- Documentation still needed: everything in O2's list (same management stack), **plus** a
  primary statement that addresses production use on a client SKU — the pins carry only
  dev/test-only wording for both columns, which is why this option is recorded as
  unsupported evidence, not a plan.
- Architecture gate(s): O2's gates **plus** an owner-commissioned ADR in
  `docs/architecture/decisions/` recording that the owner knowingly accepts dev/test-scoped
  documentation as a production control (an owner/canonical-doc action, not this note's),
  and an explicit owner narrowing decision if that ADR touches R7 wording at
  `pv20-execution-isolation-design.md` §3.1:74 / §6:646 — which this note does not propose.
- Evidence cards that must precede any claim: O2's set, and because the kernel is shared,
  additionally a two-execution peer-reach probe on the shared kernel (obs. 5's shape under
  process isolation), an ancestor-DACL/traversal check on the container-visible storage
  (B5: peer exclusion here is ordinary NT ACLs, i.e. the obs. 5 gap unchanged) **(superseded
  by Correction r3, finding 3 — carry r2 Finding 4's two conditions here; mechanism-specific
  exclusion UNKNOWN)**, and the
  F1/F5 evidence on that storage.
- Code: same `archeus/node/container_node.py` / `container_rpc.py` as O2 with an explicit
  isolation-mode field (new); no second node module for the mode.
- Fake tests: `tests/v1/unit/test_pv20_container_node.py` (new) parameterized over mode;
  `tests/v1/unit/test_paths.py` additions.
- Native tests: `tests/v1/integration/test_pv20_container_windows.py` (new) with a
  process-isolation parameter, plus the shared-kernel peer-reach case in the same file.

**Accepting support risk does not establish strict R7.** An owner's acceptance of B2's
dev/test-only wording is a stance toward *documentation*: it says who will support the
platform, not what the platform enforces. Strict R7 (design §3.1:74, §6:646; ADR-0053:163)
is established only by observed peer exclusion on the actual boundary — two executions,
one naming the other's object the way obs. 5 did, both directions denied; the F1
applied-ACE/DACL read-back and F5 mask-gate carry-overs satisfied on the real writes; the
mounted-identity and peer-reach UNKNOWNs above closed — plus the deputy review for whatever
helper or daemon the option brings. No support-risk acceptance substitutes for any of that,
and no option above is available on support-risk acceptance alone. T-004 stays blocked;
R7 unchanged; nothing here selects a mechanism. *Correction r2 authored by Qwen
(`pi`, `spark/qwen3.8-flash-next`), 2026-10-15, card T-071 — read-only analysis; this
pass made no fetch and ran no test, code, process or native operation.*

---

## Correction r3 (2026-10-15, Qwen)

Appended in answer to Codex's `reviews/T-071-analysis.r2.md` (VERDICT: CHANGES, four
findings) on card T-071. Append-only again: no earlier line was deleted or reworded; each
passage Codex named now carries an inline "(superseded by Correction r3, finding N)" marker
where it was said, and the corrected statement sits here under its finding number. This
pass ran no web fetch, no experiment, no process of the system under test, no native or ACL
operation, no test and no code change, and touched no file except this note and the T-071
card. Nothing below is a new PINNED quotation — no page was fetched, so every quote here is
one r2 already carried, and r2 Finding 1's caveat (unverified against the fetched source,
per Codex's own "Not checked" line) keeps applying to all of them. The unavailable
readiness/creator-closeout originals were not re-read this pass. Mechanism stays unchosen;
T-004 stays BLOCKED BY OWNER; R7 unchanged.

### Finding 1 (§4 table, :291) — the "new privileged component" row still said **required**

Codex is right that the row contradicted r2's Finding 2: r2 made the always-on helper
UNKNOWN and the table went on asserting a component. Corrected, with the original cell left
above and the separation Codex asks for:

- **Documented-operation privileges (PINNED, A1's pins, unchanged and the only settled
  half):** enablement "You must run PowerShell as an Administrator, or the commands fail";
  the edition/SLAT gate; PowerShell Direct's host-side "open PowerShell as Administrator",
  the "You're not a Hyper-V Administrator." failure text, the explicit-credentials
  sentence, and "PowerShell Direct supports Just Enough Administration (JEA)." These are
  privileges the *documented operations* need — nothing more.
- **INFERRED, no further:** some privileged management path must sit between Core (an
  ordinary user process) and the hypervisor/container daemon, because nothing fetched shows
  a non-elevated process creating, managing or driving them.
- **UNKNOWN:** that this path is a *new, deployment-owned, always-on component* (service, JEA
  endpoint or anything else), or that any such shape is required rather than chosen.
- So the cell reads, corrected: **A** — "documented operations need the named privileges
  (PINNED A1); the component carrying them is an undecided shape (UNKNOWN)"; **B** — "a
  container-management grant whose permission statement is an unfetched pin-target (B4);
  Hyper-V mode inherits A's *undecided* shape". "A's helper" in that cell is shorthand for
  the path, not evidence of a service.
- **Consequence for the neighbouring cells and sections that say "helper":** §4's "deputy
  surface", "K1–K3 seed/import" and "reuses existing seams (thinner helper)" rows, A2/A3/A4's
  "A1 helper" references (:96, :112, :122, :130, :154, :164-168) and O3's code line all read
  as "**the privileged management path, whatever shape the deployment chooses**". The deputy
  rule (`ADR-0053.md`:111-115, 288-303), the C6-style probe named in A4 and the F1/F5
  carry-overs apply to whichever path is chosen; choosing an always-on privileged component
  is what makes it the family's central security obligation — this note does not choose one.

### Finding 2 (:490) — the convergence claim stops at Hyper-V-isolated containers

:490 said "using a container on this host class buys a management stack, not a different
security boundary from §2's VM family" — i.e. the hypervisor boundary of Family A credited
to containers generally, over B1's own shared-kernel distinction. Corrected:

- **The convergence is scoped to the mode its pin names.** "each container runs inside of a
  highly optimized virtual machine and effectively gets its own kernel" is a statement about
  **Hyper-V isolation**, and that mode — only that mode — crosses the same hypervisor
  boundary as Family A.
- **Process isolation gets no hypervisor boundary from anything fetched.** On B1's pins it
  is namespace technology on the shared kernel ("multiple container instances run
  concurrently on a given host with isolation provided through namespace, resource control,
  and other process isolation technologies"; "Containers run on top of the host operating
  system's kernel"). So it is not "the same boundary as A" and, equally, there is no pinned
  boundary there to compare against A's; r2's sentence overstates in both directions.
- **Process-mode namespace and storage guarantees are therefore conditional on applicable
  evidence, not settled here:** the isolation machinery is only the documented "namespace,
  resource control" wording; the storage surface is governed by B3's mount pins; the
  mounted-write SID identity is unfetched (§7); the client-SKU support wording is dev/test
  only (B2); and nothing fetched addresses execution-chosen creator descriptors or peer
  exclusion for untrusted peer workloads (B1's caveat, O2's documentation item (v)). Until an
  applicable primary statement and a run exist: **UNKNOWN**.
- **What survives unchanged:** a container on this host class still comes with a management
  stack (B4's daemon/HCS grant, unfetched pin-target) — a cost both modes carry.

### Finding 3 (:626, with B5 :262-264 and §4 :289) — process-mode peer exclusion is UNKNOWN, not an established "gap unchanged"

Three sites stated the mechanism-specific outcome as fact: B5's "the obs. 5 gap unchanged
for any object peers can both reach", §4's "process mode: **no** on shared storage (B5)",
and O4's "(B5: peer exclusion here is ordinary NT ACLs, i.e. the obs. 5 gap unchanged)". All
three now carry the marker. r2's Finding 4 conditions are carried into all three:

- **Condition 1 — peer reach: UNKNOWN.** Whether two containerized executions see the same
  mounted surface at all (one shared host directory versus a per-execution one) is not
  fetched, not probed, not designed.
- **Condition 2 — mounted identity / creation authority: UNKNOWN.** The SID a containerized
  process writes as on the host is unfetched (§7), so whether one execution can name the
  other in a creation descriptor on that surface is unknown.
- **Corrected statement (conditional, in place of the assertion):** under process isolation
  no *additional* isolation mechanism is pinned between two executions on a shared mount —
  shared kernel, namespace machinery, host-visible storage — so **if** both conditions hold,
  peer exclusion rests on whatever NT ACL and namespace state that surface carries, and
  nothing fetched shows that state denying a same-user peer a creation-time descriptor
  (obs. 5's shape, T-052 Correction C-1013-T052 §1–§2); the residual risk therefore stands
  as the design assumption, and mounting nothing execution-reachable stays the stance.
  **If either condition fails**, the obs. 5 shape has not been shown reachable there and the
  label is **UNKNOWN** — neither "gap unchanged" nor "closed".
- **What B5 still establishes, unchanged:** the shared kernel (B1's pin), B3's mount
  exclusion, B2's dev/test-only wording, the keep-all retention conflict. **What would
  settle the exclusion question** is already listed in O2's and O4's manifests: the
  mount-SID observation card, the two-execution cross-reach probe in obs. 5's shape, the
  ancestor-DACL/traversal check, and the F1 (applied-ACE/DACL read-back) and F5 (mask-gate)
  carry-overs on the real writes.

### Finding 4 (:550) — E1/E2 may inform M1 while T-004 stays blocked

:550 read "Cannot do: price M1 without unblocking T-004", which puts the evidence behind
the decision it exists to inform — the reverse of the sequence the board proposes. That
line is marked superseded in place; O1's manifest now carries the corrected pair.

- **May do:** E1/E2 are the evidence cards (T-052 §5's two-worker temp fixture, the
  no-peer-allow and explicit-peer-deny ancestors, the handle probe shared with T-008's
  still-unrun C6, the alias probe). They may be prepared — and, under their own `auth:`
  naming every operation per the README hard rule — run **while T-004 stays BLOCKED BY
  OWNER**, and their bounded results **may inform M1's assessment** (the user-mode
  traversal/token-semantic question T-052's correction §1 leaves open).
- **Still cannot do:** unblock T-004, price or accept a mechanism, close F1/F5, satisfy the
  deputy review, or touch R7 wording (`pv20-execution-isolation-design.md` §3.1:74,
  §6:646; `ADR-0053.md`:163). **Bounded results alone do not unblock implementation.**
- **The sequence, stated straight:** run E1/E2 under named authorization → record the result
  as a dated `docs/architecture/p20-design-gate.md` §12 item → the owner weighs T-004's
  mechanism choice with that evidence in hand. T-004's block is an owner decision about a
  creation-permitting design (the S2G readiness finding), not a queue position behind E1.

**Unchanged by this correction:** no mechanism is chosen; accepting support risk still
establishes nothing about strict R7 (r2's Finding 5 closing paragraph stands in full); the
fetched-page storage deviation in r2 Finding 1 stands as recorded, and nothing was deleted
— the owner decides; T-004 stays BLOCKED BY OWNER; R7 unchanged; no vendor, price or
installed-state inventory was taken; the host's edition and feature state remain
deliberately uninspected.

*Correction r3 authored by Qwen (`pi`, `spark/qwen3.8-flash-next`), 2026-10-15, card T-071 —
read-only analysis; this pass made no fetch and ran no test, code, process or native
operation.*
