# F8 native run owner review sheet

2026-11-09. Written for branch `pv20-n3b`. NOT RUN. F8 authorization expressly absent. This sheet grants no authorization. Native execution must remain blocked.

Script `tools/pv20_mxc/native/f8_check.py`. Tests `tests/v1/unit/test_pv20_native_f8.py`. Shared authorization, evidence and production launch helpers come from `n3b_check.py` and `n2_check.py`. Python tests and lint remain unexecuted by author.

## 1. What F8 is

Three synthetic credential-authority fixtures hold a per-run random ASCII payload. One is an ordinary file outside the container grant. One is an agent-like IPC named pipe. One is a separately named vault-like pipe. Both pipes serve bytes and contain no credential or real authority protocol. No real vault, agent, account, credential file or external network is consulted.

Each fixture is read successfully by host `cmd.exe /d /c type` before denial. Container then executes same `type` target inside a chain with a separately granted random control file and terminal `F8_DONE` marker. Host repeats successful same-command read after denial. A pipe counts accepted clients independently of output. Access without returned bytes still fails when accepted-client count changes.

Containers use production `MxcLaunch`, policy compiler, Win32 transport, held Job and ledger. UI stays disabled and network policy stays deny-all. No broker listener or network socket is created by F8.

## 2. Rows and verdicts

| Case | PASS | FAIL | INCONCLUSIVE by design |
|---|---|---|---|
| authority-positive-controls | Each host same-command read returns fixture payload before and after denial. Pipe records successful host acceptance and stays healthy. | Wrong/missing payload, failed host read or pipe error. Denial is never reached after failed pre-control. | Native compatibility of Windows `type` with Python AF_PIPE framing remains unknown until authorized measurement. Incompatibility causes failed control, never successful denial. |
| synthetic-file-agent-ipc-denial | Container emits its granted random control and terminal marker, returns integer exit status, exposes no authority payload, and causes no extra pipe accept. All three fixtures tested separately. | Payload leak, extra pipe acceptance, missing control/completion or launch error. First failure stops. | Evidence covers synthetic file and byte-serving pipes. Real credential protocols, inherited handle transfer, effective token and registration disposal remain unproven. SDK pins derive from staged source and schema validator accepts without validation. |

Container chain's final echo returns its own status. Denial is judged by payload absence, observed pipe acceptance and bracketing controls, never by `type` exit status alone. A container timeout stops with setup error before denial evaluation.

Rows are redacted JSONL with stage/script F8, authorization ID, timestamp, case, status and detail. FAIL is flushed to disk before stop. Production ledger records each launch separately. These files accompany a future ledger review and do not supply the complete protocol batch-summary schema.

## 3. Entry and preflight

Future entry takes one canonical fixture parent at or below `<fixture-parent>`. Current state forbids execution. No native execution command is supplied here.

Before creating a root, entry requires `F8-owner-authorization.json` directly under fixture parent. Marker must be regular, single-link, no reparse point and at most 8192 bytes. Parent ancestry must be alias-free. Exact keys are `authorization_id`, `script`, `scopes`, `approved`. `script` must equal `F8`, `approved` must be true, ID must contain 1–64 ASCII letters, digits, underscores or hyphens. Marker is an administrative assertion and has no cryptographic authentication. Agent must never fabricate it.

Scope list must exactly match this order.

1. `fixture-files`
2. `mxc-profiles`
3. `jobs-processes`
4. `synthetic-agent-pipe`
5. `synthetic-vault-pipe`

Operator separately stages SDK under `<parent>\sdk\node_modules\@microsoft\mxc-sdk`. No installation occurs here. SystemRoot must identify plain drive `Windows` directory with cmd.exe. No standalone agent or vault installation is needed.

Launch budget is 570 seconds, checked before production launches. Three containers have 30-second policy bounds. Six host controls each have 8-second subprocess bound. Pipe shutdown wakes server with its own synthetic client then joins thread for 3 seconds. Windows pipe-client connect may itself wait for platform timeout. Cleanup can exceed launch budget.

## 4. What it touches

Disk writes stay under one marker-verified UUID root. Shared N2 preparation creates SDK copy, private policies, ledger, empty home/config/temp folders, outside file, ordinary p/q/core fixture folders and their synthetic seed files. F8 adds three granted control files and verdict JSONL. No project or account data is copied.

Two named pipes use `\\.\pipe\pv20_f8_agent_<random>` and `\\.\pipe\pv20_f8_vault_<random>`. They use Python stdlib AF_PIPE framing without authentication and publish only synthetic bytes. Names contain 128 random bits. Server records client counts. A same-user unrelated process reaching a pipe can invalidate denial measurement, producing failure. Nothing binds these pipes to real agent/vault names.

Processes include six bounded host cmd controls, three production wxc-exec launchers, cmd children inside MXC and pipe-serving daemon threads. Jobs have KILL_ON_JOB_CLOSE. Production transport creates protected policy handles and starts launcher suspended before Job assignment/resume.

Home/profile/temp/config variables are pinned to empty fixture folder before production imports, remain pinned during run and restore at exit. Only SystemRoot locates host executable. No account-home or credential-store file is opened. MXC can create/delete profiles or leave registrations. No script-side profile, ACL, firewall or transport configuration change occurs.

## 5. Deletion and retention

Fixture root remains on every exit, including hypothetical exit 0. Production transport may remove its own protected policy files on close. No fixture deletion or registration cleanup occurs. Named-pipe listeners close during teardown and pipe-server threads must finish. Cleanup error forces exit 3.

Payload is synthetic but raw fixture artifacts and production process identities still require review before sharing. Authorization ID must never contain a credential.

## 6. How to stop

Ctrl+C forces exit 3, closes synthetic pipe listeners and Jobs and checks owned launcher generations. Shared N2 fallback termination is limited to generations recorded by its own counting API. No sweep by process name, command line or account occurs. A surviving launcher or failed cleanup keeps evidence and produces exit 3. Console death closes process-owned Jobs and pipes through Windows. Real abrupt-close behavior remains unmeasured.

## 7. Exit codes

0 all PASS, currently unreachable with explicit residual row. 1 first FAIL. 2 no FAIL plus INCONCLUSIVE, expected after complete measurements. 3 missing authorization, setup failure, timeout, interruption, unexpected exception, cleanup failure or surviving owned launcher. All preserve root.

## 8. Owner questions before any future run

1. Is new F8 authorization explicitly granted after reviewing exact revision, hashes and this sheet, under test lock at below-normal priority?
2. Are three synthetic payload authorities an accepted first measurement for completion-plan rows 2/3 and G1? What additional authority protocol evidence is required before closure?
3. Are random unauthenticated byte-serving agent/vault pipes acceptable? Confirm they contain synthetic payload only and their names avoid real service names.
4. Are host same-command positive controls before and after each denial required as written? A failed Windows `type`/AF_PIPE control stops the run and cannot support denial.
5. Are MXC profile side effects, Jobs, process launch/termination and fixture file observation separately authorized?
6. Must reviewed SDK inventory and pinned schema validator replace current stand-ins before first run?
7. Is UI-disabled deny-all policy and empty launcher environment the intended first attempt?
8. Are timing bounds, pipe shutdown delay, interruption handling and fixture retention approved? Who inspects and cleans MXC registration residue later?
9. Are inherited-handle transfer, effective token and real authority protocol gaps accepted as explicit residuals, or must native contracts be built first?
10. Who issues approval marker through owner's authorized channel and reviews evidence before any publication? No marker exists in this checkout.

## 9. Verification and drift guard

Fake-based tests drive full F8 case sequence, verify six host controls and three container probes, fail leaks even without returned payload, fail missing controls and check distinct authorization scope. Windows-only drift guard uses production launch, compiler, transport and ledger over existing signature-checked Win32/Job fakes. It pins deny-all/no-proxy policy and quarantine without resource read-back.

Coordinator commands from worktree root follow. Native modules must remain unexecuted.

```text
pytest -q tests/v1/unit/test_pv20_native_n3b.py tests/v1/unit/test_pv20_native_f8.py tests/v1/unit/test_pv20_native_drift.py
ruff check tools/pv20_mxc/native/n3b_check.py tools/pv20_mxc/native/f8_check.py tests/v1/unit/test_pv20_native_n3b.py tests/v1/unit/test_pv20_native_f8.py
```

No fake proves real AF_PIPE reachability, Windows type compatibility, MXC isolation, profile disposal or admission. Coordinator results remain pending.
