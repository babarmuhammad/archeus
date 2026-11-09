# N5 native run: owner review sheet (2026-11-09)

Status: written, NOT run. Unit tests and lint NOT run by this author. No owner authorization exists. This sheet is review material, not permission to run.

Script: `tools/pv20_mxc/native/n5_check.py`. Tests: `tests/v1/unit/test_pv20_native_n5.py`. Target: branch `pv20-n5`, from `pv20-int4`.

## 1. What N5 is, and what this script makes of it

Completion-plan section 2 E5 requires the activated candidate in a fixture Core, with all frozen N5 rows. This script covers the ten rows in `STAGES['N5']` in order, exercising available production lifecycle seams. It does **not** construct an activated Core, enable production admission, start an independent watchdog executable, or claim to finish E5. Those missing native contracts remain explicit INCONCLUSIVE evidence, including one row for each of the six invariants. This is a limited probe package, not the final activation acceptance run.

Production paths used: `MxcLaunch`, native transport and Win32 API, `WindowsBoundary` Jobs, `Ledger`/reconcile, cancellation, `WatchdogHost`, heartbeat `Channel`, `bind_outcome`, and `a4_eligibility`. N2's fixture harness supplies SDK staging, counting transport, Job ownership, loop workload and cleanup. No copies of production lifecycle algorithms are introduced.

Stand-ins: host logic shares this script process; its Core identity is this script's identity; silence means no heartbeat, not a frozen manager. Host termination ends the already-held Job, not the production process registry. Sentinel denial is an injected `PermissionError`, not an ACL change. Fresh Ledger stands for restart. Job close stands for Core death. Launcher absence is N2's resource-reader stand-in; it does not establish MXC disposal. SDK pins come from the staged copy; schema validator returns True. Launcher exit is N2's outcome stand-in, never sufficient N5 qualification.

## 2. Rows, and what PASS, FAIL and INCONCLUSIVE mean

Each available control is checked before its INCONCLUSIVE row. First failed control records FAIL durably and stops immediately. No N5 PASS is emitted. A fact the package cannot establish never becomes qualification by implication.

| Frozen case | What runs | FAIL | What remains INCONCLUSIVE |
|---|---|---|---|
| candidate-dispatch-identities-jobs | Two direct production launchers, durable intent/ownership, live PID/creation-time observation, distinct held Jobs, cancel and empty Job | Identity/ownership mismatch, shared Job, nonempty Job after cancel | Activated dispatch, effective execution identities, actual switch bundle |
| e-stop-rearm-refusal | Live tree cancelled with `reason='estop'`; no successful completion, quarantine, empty Job | Incorrect journal or surviving Job members | Sentinel-first real e-stop, manager admission/dispatch/resume and rearm refusal; this does not call `LocalNode.estop_without_core` |
| hung-core-sentinel-registry-kill | Production host consumes ledger-backed registration; 0.2 s silence deadline; read-back sentinel before identity-checked held-Job termination | Cannot arm/fire, wrong order or sentinel report, Job remains populated | Independent host, hung real Core, native registry kill |
| core-death | Close script-owned Job; verify retained launcher identity no longer alive | Confirmed launcher survives close | Real fixture Core death, descendant identity read-back and independent watchdog survival |
| restart-reconciliation | Fresh production Ledger leaves live owner STILL_RUNNING; close Job; missing resource reader yields DEAD_UNVERIFIED/quarantine | Live owner lost, surviving launcher, or missing disposal evidence called clean | Production boot wiring, admission after restart, MXC registration disposal |
| each-invariant-no-spawn | Six explicit missing-contract rows: identity, grants, no_broad_grants, job, mailbox, isolated_path | No native assertion is available in this row | Native per-condition faults and zero CreateProcessW/ResumeThread under activated admission; legacy SID/ACL checks cannot substitute |
| unsupported-routes-no-fallback | A4 helper rejects fake, test and empty harness IDs despite other positive inputs | Helper accepts those IDs | Actual unsupported real harness routes, router/adapter fallback and zero detached spawns |
| sentinel-present-absent-denied | Three fresh launches; existing STOP, absent STOP then creation, injected denied sentinel; kill proceeds even when sentinel unverifiable | Wrong host state/order/report or remaining Job members | Native access denial, hooks seeing STOP, whole-Core sentinel semantics |
| forged-replayed-lifecycle | Unknown journal registration rejected; valid heartbeat control, replay becomes UNCERTAIN without kill; valid bound outcome control, wrong nonce/peer/stale outcome refused | Forgery/replay accepted, valid control refused, unexpected kill | Hostile execution's actual access to lifecycle files; full lifecycle message matrix |
| outer-job-sole-ownership | Close held Job, verify launcher absent | Launcher survives | No duplicate/inherited Job handle in another process; handle inventory and whole tree read-back |

Healthy result: exit 2, all ten cases INCONCLUSIVE, fixture preserved. No all-PASS exit exists. Unknown process observations abort with setup/error exit 3, rather than being treated as absence. The evidence rows written before an abort remain available; later rows are not claimed executed.

Evidence: `n5_journal.jsonl`, redacted `{case,status,detail}` JSON lines matching N2/N4's verdict format, flushed and fsynced before first-failure stop. Production ownership journals retain their checksummed `length/sha256/record` envelopes in `ledger`. This is not the controller's complete SUMMARY_FIELDS acceptance report. The absence of that full report is another reason this package cannot qualify E5.

## 3. Exact command and authorization interlock

Do not run now. A separate owner act must authorize N5; N1-N4 permission does not apply. After review, the coordinator must use its approved test lock at below-normal priority. The module invocation inside that wrapper would be:

```text
py -m tools.pv20_mxc.native.n5_check D:\pv20-fixtures\run --owner-authorized-n5-2026-11-09
```

The flag alone does not authorize anything. Before root creation or native module setup, the script requires operator-supplied `n5-manifest.json` and `n5-authorization.json` directly under that parent. It creates neither file. It uses existing `controller.authorize`, `verify_manifest` and no-follow readers. The older N2/N4 native entry points have no owner-token check; the shared controller does, so this script uses that existing token format plus an explicit N5 command marker.

Manifest must name stage N5, exact ordered frozen cases, exact fixture parent, canonical fresh UUID, N4 PASS prerequisite, and `n5_script_hash` (SHA-256 of reviewed script bytes). Supply all `controller.verify_manifest` metadata: candidate SHA, protocol hash, batch/OS/architecture/command/runtime/capability/fixture inventories and staged executed-artifact hashes. Token must bind manifest digest, stage, UUID, parent, nonempty owner authorization ID and `fixture_only: true`. Changed artifacts, wrong scope, missing token, stale script hash or incomplete prerequisites refuse. Owner must verify the metadata corresponds to the reviewed candidate: the helper validates shape and staged artifact hashes, not the truth of an asserted N4 PASS or candidate SHA.

Root uses shared `fixtures.create_root` and its `.pv20-created` marker, with the owner-token UUID. Parent first passes N2/common canonical, no-link, outside-repo/profile restrictions and must be under `D:\pv20-fixtures`. Existing UUID root refuses. This script never creates a token, manufactures prerequisite acceptance, or changes a prerequisite result.

Budget: 1700 s checked between cases and launches, below frozen 1800 s. Each loop policy timeout is 120 s; host waits and teardown are bounded observations. Native calls themselves are synchronous and cannot be forcibly bounded by this process. About eleven short-lived fixture trees are launched. No live provider case exists.

## 4. What it touches

Reads: the two owner-provided JSON files and their ancestor metadata; reviewed script bytes; artifact paths under approved fixture parent; staged SDK under `<parent>\sdk\node_modules\@microsoft\mxc-sdk`; `SystemRoot` for `cmd.exe`; fixture files; owned launcher creation times/process exit status and Job membership. Source imports execute repository code. Production config imports are redirected by N2 to empty `envhome` first; already-loaded config refuses at prepare.

Writes: only fresh UUID child: shared fixture directories and marker, copied SDK, protected policy files, ledger, private/empty-home/localappdata/runtime/outside/fault/rev and P/Q/core synthetic directories, seeds, heartbeat channels/status/STOP files, redacted verdict journal. Sentinel cases never touch the machine's real STOP file or registry. Imports may use Python's normal bytecode cache behavior in the source tree; run with `PYTHONDONTWRITEBYTECODE=1` if no cache writes are desired.

Processes/kernel objects: script process, one unnamed kill-on-close Core Job per direct launch, production suspended `wxc-exec.exe` and synthetic `cmd.exe` trees. No independent host process is started. Jobs are assigned/checked before resume. Host callback only ends the held Job associated with that exact recorded PID/creation time; no PID sweep or journal-only process adoption. No Job handle duplication is requested.

No account home/credential-store reads, admin request, network/listener, live key, ACL tool/API, firewall/transport change, or explicit profile-management API. Policies deny ingress/egress and block UI. MXC itself can create profiles/registrations and leave residue; launcher logging/temp behavior is outside script control. Common safety/redaction helpers inspect environment names and path metadata, not account content.

Separate authorization categories: MXC-managed profile creation/deletion and possible retained registrations; Job/process creation, assignment, termination and close; process/Job/file observations; fixture writes and SDK copy. ACL writes: none. Transport/firewall changes: none.

## 5. What it deletes, and when

No fixture tree deletion on any exit, including future code changes producing exit 0. This stricter retention rule satisfies “delete only on exit 0”; it never implies permission to clean elsewhere. Production closes remove owned protected policy files. Sentinel/status writes stay inside fixture. Shared fixture root uses `.pv20-created`, not `common.MARKER`; **do not pass it to `common.remove_fixture`**. Later cleanup needs a separately reviewed no-follow UUID/marker-bound procedure, never recursive shell deletion following junctions.

## 6. How to stop

Ctrl+C: unwind to close every retained Job through N2 cleanup, wait up to 5 s per retained launcher, preserve fixture, exit 3. Cleanup can terminate only retained launcher identities that still match. Cleanup error or survivor also yields exit 3. Forced process death relies on OS closing its Job handles; it does not prove registration disposal. Keep surviving-resource findings for owner review; do not retry against guessed PIDs.

## 7. Exit codes

0 reserved by shared recorder; unreachable in current `run`. 1 first failed control. 2 no failed control with declared INCONCLUSIVE rows. 3 authorization/setup/budget/interrupt/unexpected observation/cleanup failure. No success exit means no fixture deletion.

## 8. Open questions for the owner

1. Authorize these limited probes separately from final activated-Core E5, or require missing Core/host/native-reader contracts before any N5 run? Recommendation: complete those contracts first; this package cannot discharge E5.
2. Are E1-E3 green and E4/B12/B13 prerequisites reviewed? Who supplies actual candidate SHA, N4 acceptance evidence and frozen inventories? Local fake tests cannot supply them.
3. Accept source-derived SDK pins and permissive schema stand-in for limited probes, or require independently reviewed pins and pinned validator first?
4. Authorize MXC profile creation/deletion, potential registration residue, suspended launcher/Job operations, identity/file observations and fixture writes as separately named above? No ACL/firewall operation is requested.
5. Accept same-process host and held-Job termination as explicitly limited observations? They cannot prove native registry kill, independent watchdog survival or real Core death.
6. What native disposal/effective-identity/handle-inventory readers will be accepted? Who supplies each invariant's real no-spawn fault and real unsupported-route/fallback observation?
7. What exact real e-stop/rearm authorization boundary must be refused? This script only checks cancellation, never clears the real STOP sentinel, and cannot validate rearm.
8. Accept injected sentinel denial, or require a separately reviewed way to produce native denial without ACL writes? What real hook evidence must accompany STOP read-back?
9. Approve 1700 s budget, per-launch 120 s timeout and cleanup bounds? Which independent supervisor enforces a hard total limit if a native call hangs?
10. Who retains/redacts evidence and reviews possible SDK residue? Who authorizes eventual marker-bound cleanup? No cleanup authorization or token is supplied here.

## 9. Reconciliation and coordinator validation

N2 helpers are reused rather than copied. New execution IDs use ledger-compatible underscores and production `journal_name`; Job termination uses boundary API without closing caller's handle. Unknown process reads raise rather than being declared dead. Production host and heartbeat activation constants stay closed; direct dependency-injected host logic is called explicitly, not its closed executable entry point.

The new drift test runs script `prepare` and every available case through production MxcLaunch, native transport, Ledger, WatchdogHost, Channel and outcome/A4 code over the existing signature-checked fake Win32/Job machine. It replaces OS observations and time only; no native process, socket or script entry point runs. Frozen-case/limitation tests catch catalog changes. Token tests cover scope, script hash, manifest binding and staged artifact drift before fixture creation. Failure tests check durable evidence and immediate stop.

Coordinator commands, not executed here:

```text
py -m pytest -q tests/v1/unit/test_pv20_native_n5.py tests/v1/unit/test_pv20_native_drift.py
ruff check tools/pv20_mxc/native/n5_check.py tests/v1/unit/test_pv20_native_n5.py
```

Fake-backed checks cannot prove MXC policy acceptance, containment, true host/process timing, real Core death, registration absence or activated admission. No test result is claimed until the coordinator runs them.
