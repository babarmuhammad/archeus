# PV-20 threat model (committed, refreshed 2026-11-01)

**Status: slice G stays PAUSED, NOT CLOSED. G1 and G2 stay Critical and open.** V1 is not OS-confined
and no document may say it is (ADR-0051 Decision 4, ADR-0053). PV-20 is built in parts behind injected
fakes and is not admitted to production dispatch (design, "As built, 2026-11-01"). Every row below is
a statement about code and test evidence at the integration tip, not about a property a real process
has. Nothing here promotes an acceptance row (ADR-0053: no row moves without its native evidence).

This document satisfies ADR-0051 Decision 3 ("P20's threat model names the gap explicitly") and is the
committed form of the Qwen draft of 2026-10-21 (`.collab/PV20-threat-model-draft.md`), refreshed for the
MXC backend decision (ADR-0053, amended 2026-10-29 and 2026-10-30) and the code that has landed since.
The p20 design gate (section 10) requires no High finding open before slice G closes: eight are open
(next section), so it cannot close.

Tip checked: branch `pv20-g1` over `pv20-mxc` `fadd2b18`. Paths are repo-relative; `file:line` is where
the control sits at that tip. Line numbers drift: re-check them, do not trust them.

## How to read a row

- **Threat**: what an attacker in one of five starting positions does. **S-run** a hostile agent run,
  **S-repo** a hostile repository, **S-vcmd** a hostile verifier command, **S-peer** another execution,
  **S-client** a forged client.
- **Mitigation as built**: the control that exists in code, with the closed switch that keeps it from
  governing a real process. A control behind a closed switch protects nothing today.
- **Evidence**, one of:
  - **unit**: tests against fakes pass; the logic is as described. Not a statement about Windows.
  - **fake-only**: built and tested, but only a test builds the caller (for example the T-457 agent
    and verifier paths, which drive the production `MxcBoundary` over a scripted Win32 transport in
    `tests/v1/integration/test_pv20_mxc_agent_path.py`); no production code does.
  - **native partial**: a fixture-only native run (N1, N3 of 2026-11-01) showed the narrow fact named.
  - **native NOT_RUN**: nothing was run against the real boundary; the row is unevidenced, never safe.
- **Open**: what keeps the row from being closed. **High** means it blocks slice G (gate section 10).

## The switches that keep everything above closed

| Switch | Value | Where |
|---|---|---|
| Production dispatch | `False` | `archeus/node/isolation.py:49` |
| A4 eligibility enforced | `False` | `archeus/node/isolation.py:391` |
| Windows boundary available | returns `False`; profile create/delete raise `mxc_lifecycle_unverified`; launch raises `mxc_policy_required` | `archeus/node/isolation.py:1885`, `:1895-1913`, `:2251` |
| Native MXC run | `False` | `archeus/node/mxc.py:22` (guards `:256`, `:278`) |
| Broker dispatch | `False`; the native broker pipe refuses | `archeus/node/broker.py:62`, `:226-234` |
| Confined verification | `False` | `archeus/core/application/verification.py:36` |
| Store fetch accepted | `False` | `archeus/node/local.py:1253` |
| Origin enforcement | `False` | `archeus/api/origin.py:15` |
| Isolated dispatch qualified | returns `False` unconditionally | `archeus/api/server.py:239-241` |
| Router isolated dispatch | `None` | `archeus/core/application/resources.py:33` |
| Isolated project workspace | built behind the closed switches above: the manager seeds a Core-built repository from the store (`resolve_base`, `store_fetch`, `seed_workspace`), refuses a root that is not a repository before any process, and a resume reuses the recorded base; the fetch itself stays closed by the row below | `archeus/core/execution/manager.py:496`, `:511` |
| Heartbeat channel (Core's sender and the watchdog proxy) | `False`; both refuse to be built | `archeus/node/mxc_heartbeat.py` (`HEARTBEAT_ENABLED`) |
| Watchdog host entry point | `False`; also refuses to start without native readers, which are not built | `archeus/node/mxc_watchdog_host.py` (`HOST_ENABLED`, `main`) |

No production code constructs `MxcBoundary` (`archeus/node/mxc_boundary.py`), `MxcLaunch`, the ledger,
the watchdog, the heartbeat channel, the watchdog host or the Win32 API. `MxcBoundary` is available only with the native api, SDK pins that verify
against the staged copy, the ledger, the schema validator and an open `NATIVE_RUN_ENABLED`; given none
of them, or with the switch above closed, it is not. Opening admission
is one reviewed activation (completion plan C1, A1); it is not done.

## Open High items (these block closing slice G)

| ID | Item | State |
|---|---|---|
| H1 | **G1 (Critical):** an execution keeps the user's reach into credential authorities (Credential Manager, package registries, SSH keys and agent, Git tokens) | no control governs a real process; credential-authority denial was never probed (MXC-CRED NOT_RUN, F8 unwritten) |
| H2 | **G2 (Critical):** an execution keeps the user's reach to `run/local-token` and Core control state | same; G6 row 3 drafted, skipped |
| H3 | **USER by exclusion is unproven.** `WindowsOriginBackend` attests the peer USER when it is in no Core Job, has no launcher ancestor, is in Core's session and is on the direct loopback path (`archeus/node/origin_windows.py:31-52`, `archeus/node/attest.py:81`). That is sound only if no process an execution can cause to exist or to connect runs outside every Core Job and off the launcher's tree: a user-session helper, a scheduled task, a COM or WMI service, an orphaned descendant (`_ancestors` stops at a dead parent, `archeus/node/origin_native.py:74-86`). Whether a base-container workload can induce any of these is UNKNOWN | un-evidenced; N3b (production attestor, hostile-peer matrix) not written |
| H4 | **The real CLI may not run in MXC base-container.** Measured: `claude.exe --version/--help` runs; node, git and powershell fail `0xC0000142` unless `ui.disable=false`; Git Bash fails either way; `compile_policy` refuses `ui=True` (`archeus/node/mxc.py:120`, `:202-203`). Until viable, isolated Claude Code executions do not run (ADR-0053 R3), so there is nothing to confine and nothing to evidence | N4a not run |
| H5 | **Check commands still run under the user's identity.** The confined verifier is not built on MXC; `CONFINED_VERIFICATION_ENABLED` is `False`. A check's test and build commands are content the execution can write | designed; fake-only path only |
| H6 | **Core runs git over execution-written repositories as the user** (`git_head`, `dirty`, `snapshot`, `merge_base`, the hook HEAD read). The manager now dispatches through the seed and import helpers (`archeus/core/execution/manager.py:511`; `archeus/node/local.py`) behind the closed switches: `store_fetch_accepted` stays `False` (T-046 C1) until the source side is accepted on native evidence, so nothing seeds a real project | as built, a boundary violation PV-20 removes |
| H7 | **Hardlink planted after the scan.** Detect and refuse are evidenced natively (N3 Phase A); a link planted after the last scan, with the container already running, is UNKNOWN and its disposition is an owner decision (OD-4, MXC-R12). The upstream question to Microsoft has not been asked | open |
| H8 | **No reviewed SDK pins or pinned schema validator are committed.** `staging.verify_mxc` (`archeus/node/staging.py:299`) checks reviewed pins, but the repository holds none; N2 computes them from the staged copy and stubs the validator (MXC-R07, R08, R09) | open (completion plan C16, B0) |

## Boundary 1: execution (identity, Job, own state)

| # | Threat | Mitigation as built | Evidence | Open |
|---|---|---|---|---|
| T01 | S-run reads a credential authority the user owns (G1) | none governs a real process. Application layer only: `CAPABILITY_ENV` clears push/prompt variables (`archeus/harnesses/base.py:35`, `:527-532`), which cannot remove material held in OS stores. Reach-denial would rest on the MXC process security environment plus Core's grants, not on a distinct token (F1a: the User SID is the host user's) | native NOT_RUN. G6 row 2 drafted, skipped (`tests/v1/integration/test_g06_os_isolation.py`) | H1 |
| T02 | S-run reads `run/local-token` or Core control state (G2) | same. Core home refused for isolated work and a private `CLAUDE_CONFIG_DIR` are built behind the closed gate (`base.py:563-566`) | unit (config refusal); reach: native NOT_RUN. G6 row 3 drafted, skipped | H2 |
| T03 | S-run or S-repo reaches an outside file through a hardlink inside a granted tree (F2c/F2d: readable and writable) | link-count scan at grant construction (`archeus/node/local.py:274-275`), at start (`:319-320`), in seed and verifier prepare (`:1236`), by `staging.scan_grants` (`archeus/node/staging.py:270`) and the policy gate (`archeus/node/mxc.py:139`) | unit; native partial: N3 A5 detect, A6 launcher refused over a planted link, A7 clean rescan. Symlink, hostile creator ACEs, handle transfer UNKNOWN | H7 |
| T04 | S-run floods stdout/stderr to exhaust Core memory | per-stream and total bounds, a deadline, a 64 KiB read, input read one chunk at a time, kill and close on every fault (`archeus/node/mxc_native.py:40-48`, `:223-285`) | unit: `tests/v1/unit/test_pv20_g_regressions.py` (B1 section), hand mutants MG01-MG08. Native: never streamed natively (N2 stand-in only) | defect: after a drain faulted on a bound, `Process.poll()` can read a clean exit 0 (`mxc_native.py:192`, `:214`), strict xfail in the same file; latent until a production child object exists |
| T05 | Launcher or policy tampered; a changed SDK | reviewed-pin check (`staging.py:299`), policy validation of the exact compiler output (`mxc.py:139`), protected policy file with a deny-write lease (`mxc_native.py:52-60`) | unit; native partial: N2 not yet run | H8 |
| T06 | A resume or a verifier key collides with another journal name, or an id escapes the ledger directory | one name per process generation (`archeus/node/mxc_ledger.py:17-31`) | unit: B2 section of `test_pv20_g_regressions.py`, mutants MG10-MG17. No native need | none |
| T07 | The tree survives an end, or an end is recorded clean while it lives | revoke, terminate the Job without closing, read the member count through the open handle, read back resources, record; clean only with a Core-owned outcome and a verified disposal (`archeus/node/local.py:504-546`, `:549-580`, `:608-640`; `archeus/node/mxc_cancel.py:62-132`; `archeus/node/isolation.py:1967`) | unit and fake-only: B3 section, mutants MG20-MG27. Native partial: N1 outer-job-close PASS; real Core death and `terminate_job` through the production boundary only stand-in | the Job is the Core-death authority (decision below); the host is built behind fakes and unwired |
| T08 | The launcher's exit or the stream is taken for the workload's result (A7) | Core-owned outcome reader or bound workload nonce (`local.py:481-496`); without one every end is DEAD_UNVERIFIED | unit; G6 row 15 over the fake boundary. MXC supplies no independent workload outcome | success needs an outcome source (OD-2, OD-3) |
| T09 | Core crashes or hangs with an execution live | boot reclaim exists for the legacy isolation (`local.py:757`, `manager.py:1117`); the ledger `reconcile` (`mxc_ledger.py:109`, `:240`) is not called by the manager. A watchdog host (`archeus/node/mxc_watchdog_host.py`) runs `Watchdog` over a heartbeat channel (`mxc_heartbeat.py`, one beat per manager sweep): a stale heartbeat engages the STOP sentinel and then ends only what the ledger's ownership record names, by pid and creation time; a dead Core is ended for without the sentinel | unit and fake-only: `tests/v1/unit/test_mxc_watchdog_host.py`, mutants WH01 to WH45. Real Core death and a real hung Core NOT_RUN (N5 `hung-core-sentinel-registry-kill`, `core-death`) | native readers (process identity by creation time, termination, sentinel), the launch of the host from Core's start-up and the deadline value are not built |
| T10 | A condition of the establishment invariant is unmet and the execution starts anyway | `check_invariant` (`isolation.py:232`), `Isolation.requested` (`:648-661`) refuse; no switch disables it | unit; G6 row 10 scenarios (nine causes, no spawn, no fallback) | conditions 1 to 3 now have an MXC mapping (header of `mxc_boundary.py`: a reserved name and a `psec` marker, the policy's path lists plus the hardlink gate, a DACL read for broad writers and reachability of Core paths); every mapping is INFERRED, none has native evidence |

## Boundary 2: verifier

| # | Threat | Mitigation as built | Evidence | Open |
|---|---|---|---|---|
| T11 | S-vcmd runs a check command as the user and reads credentials, Core state or loopback | `run_confined_check` over `MxcLaunch` (`MxcBoundary.launch_confined`, output drained into the attempt's own log by `archeus/node/mxc_verifier.py`, one journal `verify_<vid>_<n>-p1` per attempt) is reached only by a test; production check path is `run_check` as the user (`local.py:1168`) | fake-only (T-457 verifier tests). Native NOT_RUN | H5 |
| T12 | A missing confined verifier is recorded PASSED | Option 3: no confined identity means ERROR or AWAITING_HUMAN (ADR-0053 R4b); G6 row 14 shows no command runs and no exit code returns | unit and fake-only | none beyond H5 |

## Boundary 3: broker

| # | Threat | Mitigation as built | Evidence | Open |
|---|---|---|---|---|
| T13 | A provider credential lives inside the boundary | the broker issues execution-scoped grants with zero Core scopes, scrubs, revokes at every end (`archeus/node/broker.py`, `broker_bridge.py`); `BROKER_ELIGIBLE` limits harnesses (`base.py:46`) | unit; fake-only. The native pipe transport refuses (`broker.py:226-234`); only the loopback proxy was reached in N3 B1/B2/B5 | H4 (a CLI that cannot use the broker cannot run isolated); the MXC transport for the broker is unbuilt |
| T14 | The broker becomes a Core route (an R1 path) | no Core route, no local-token acceptance, no TCP fallback by design | unit | native reach rows N3b not written |

## Boundary 4: Core effect boundary and origin

| # | Threat | Mitigation as built | Evidence | Open |
|---|---|---|---|---|
| T15 | S-run or S-client uses the local or hook token to cause a privileged effect (publish, re-arm, approve, policy change, author halt state) | the origin gate: backend attests at accept, `valid` re-checks per request, Core's path registry must approve, then `authorize_transport` admits only USER on a permitted path (`archeus/api/server.py:291-303`, `:454-461`; `archeus/node/origin_windows.py:31-98`; `archeus/api/origin.py:163-216`; `archeus/node/attest.py:81`, `:154`) | unit: B9 section, mutants MG30-MG47; G6 rows 4 and 5 drive the real HTTP gate over a fake process table. Switch closed (`origin.py:15`). Native partial: N3 used a script attestor and a fake proxy; the production readers (`origin_native.py:48-72`, `Win32OriginApi`) were never run natively | H3 |
| T16 | An undetermined, hung, dead, recycled or unreadable origin is admitted | every failure is "no evidence"; calls are deadline-bounded (`origin.py:18`, `:24-47`); a binding expires and is held to its creation time and kind (`attest.py:154`); the shipped backend with no readers authorizes nothing (`origin_windows.py:31-33`, `:55-57`) | unit: `test_pv20_g_regressions.py` (B9 section) over every listed failure. PID reuse was never observed natively and cannot be forced from the fixture (F9C: a dead PID resolved for at least 1.5 s) | none beyond H3 |
| T17 | The verifier's own origin | not produced anywhere | not built | origin for a verifier peer is UNDETERMINED, so refused; no positive path |
| T18 | Re-arm after a halt by an execution | refused at the gate (G6 row 5); D10 paired-device step-up is separate and recorded blocked in the gate | unit; fake | gate section 14.B |
| T19 | Sentinel and halt state | the hook reads a three-state sentinel (`archeus/harnesses/hook.py:109-120`, `os.lstat`, indeterminate halts); registry kill is the only Core-less stop | unit | Core-side disarm checks still two-state: `archeus/core/application/authorization.py:115`, `archeus/core/calls.py:109`, `archeus/core/runtime.py:257`, `archeus/node/local.py:876`, each `os.path.exists(stop_sentinel())`, so a denied or dangling lookup reads "absent" (Medium, unowned) |

## Boundary 5: user and Core home

| # | Threat | Mitigation as built | Evidence | Open |
|---|---|---|---|---|
| T20 | The account home or provider login reaches the execution | isolated launch sets a private `CLAUDE_CONFIG_DIR` and refuses any other (`base.py:527`, `:563-566`); no MCP opt-in admitted | unit | in force only when isolation is |
| T21 | Plaintext hook tokens linger in `run/exec/<id>/req/` after the end (I-F3, Low) | none | none | owner's to dispose |
| T22 | Secrets at rest | CSPRNG credentials, hashes only, cleared on every end path (gate item 109) | unit | none |

## Boundary 6 to 8: peer, proxy and hop, deputy

| # | Threat | Mitigation as built | Evidence | Open |
|---|---|---|---|---|
| T23 | A forwarder running as the user launders origin | a forwarded request is never direct local; `direct_loopback` requires both ends to be loopback (`origin.py:158`); the tunnel carries paired credentials only | unit; G6 rows 4 and 5 | "no execution can reach a forwarding hop or user-identity proxy" is UNVERIFIED (design 7.1) |
| T24 | Archeus code running as the user loads execution-influenced content (deputy) | git and model-call rules designed (A3, A5); `store_fetch_accepted` `False` (`local.py:1253`) | unit for the helpers | H6 |

## Decision: the Job is the Core-death authority (OD-4b, recorded 2026-11-01)

**Status: ASSUMED.** The owner has not answered OD-4b. The completion plan recommends option (a) and
B13 takes it, so the assumption is written here where a reversal can find it.

1. **Core dead.** The Core-held `KILL_ON_JOB_CLOSE` Job is the authority: the handle closes with
   Core and the tree ends (design R6-A, section 3.7). Evidence is N1 outer-job-close PASS, where a
   stand-in closed the handle; a real Core process dying under real executions was never observed
   (N5).
2. **Core hung or unreachable.** The authority stays item 83: the STOP sentinel and the registry
   kill checked by creation time. The watchdog host adds no second mechanism and no authority. On a
   stale heartbeat it engages that same sentinel and then asks for the same identity-checked kill,
   from the ledger's ownership record instead of the registry line; on a dead Core it ends only what
   outlived the Job, with no sentinel, as a belt. It is an automatic trigger of item 83. It never
   adopts a process the ledger does not name, never kills by pid alone, and a lost reading is
   UNCERTAIN with no kill. A sentinel that cannot be read back is recorded and does not withhold the
   kill: stopping wins over the unverified halt flag.
3. **What is built, and what is not.** The host, the channel, Core's sender (`LocalNode.heartbeat`,
   beaten once per manager sweep) and the registration proxy for `MxcLaunch` exist behind fakes and
   behind two closed flags. Nothing in production builds any of them, Core start-up does not launch
   the host, and the host refuses to start because the native readers it needs (process identity by
   creation time, termination, the sentinel) are not built. If the owner answers OD-4b with "build
   it now", what remains is those readers, the launch of the host with Core's pid and creation
   time, a measured deadline, and N5 `hung-core-sentinel-registry-kill` and `core-death` run
   against it.
4. **Consequences accepted under this decision.** An execution that escapes its Job (breakaway is
   UNKNOWN natively) runs until the next boot reconcile, which quarantines and does not kill. A hung
   Core is stopped only by a person (`archeus estop`) unless the host is deployed. With the host
   deployed, a Core that is only slow past the deadline loses its executions; the deadline has no
   measured value. The beat comes from the manager sweep, so a stuck sweep reads as hung while a
   live sweep with a stuck API does not.
5. **Limits of the host as built.** The channel is a file with no rotation. Core and the host share a
   clock by injection; a clock both can read monotonically is UNVERIFIED. Once the watch has fired or
   gone uncertain the host ends and re-adopts nothing.

## Residual risks (recorded, not solved)

- **G3 network egress.** P23's, not PV-20's. A task whose policy denies network can still reach it through
  an in-boundary `exec` today. MXC policy compiles `egress: deny` (`mxc.py:120`) but no real agent has run
  under it.
- **MXC viability.** Replaces the AppContainer risk the 2026-10-21 draft carried. The boundary is the MXC
  process security environment, token User is the host user's SID, separation was observed only as
  behaviour, and the from-inside token read is OPEN (MXC-R13). The register MXC-R01 to R14 stands.
- **R1-A attestation.** The mechanism is chosen (owner of port, process creation time, Job membership);
  its soundness is H3.
- **O7 charging** of an isolation-establishment failure is P11's and open.
- **Future surfaces (none exist in V1):** microphone (V2-A1), screen capture (V2-A5), desktop input
  injection (V2-A5). Desktop injection acts at the desktop, not on Core's request path, so neither the
  effect boundary nor the mailbox can refuse it; an OS sandbox is required before V2-A5 reaches production.

## What would change a label

Nothing here moves on code alone. A row changes only with its native evidence: the N-protocol stages
N2, N3b, N4, N4a, F8 and N5 of `.collab/PV20-completion-plan-2026-11-01.md`, each separately authorized,
fixtures only, recorded in `.collab/PV20-mxc-evidence-ledger.md` (which does not exist yet). Until then
the honest summary is: the application layer governs V1; PV-20 is a set of built, fake-tested parts with
every switch closed; G1 and G2 are open.
