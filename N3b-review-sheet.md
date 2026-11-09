# N3b native run owner review sheet

2026-11-09. Written for branch `pv20-n3b`. NOT RUN. Owner authorization does not exist. This sheet grants no authorization. Native execution must remain blocked.

Script `tools/pv20_mxc/native/n3b_check.py`. Fake-backed tests `tests/v1/unit/test_pv20_native_n3b.py`. Neither tests nor lint were executed by this author because Python execution is prohibited in this worktree and no standalone ruff executable was found.

## 1. What N3b is

N3b uses the frozen N3 case names. It replaces N3's script attestor and fake proxy with production `native_readers`, `Win32OriginApi`, `WindowsOriginBackend`, `CorePathRegistry`, `broker_listener.loopback_broker`, `Broker`, `MxcLaunch`, Win32 transport, Jobs and ledger. Broker upstream responses are generated in memory. Every credential-shaped value belongs to the fixture.

N3's run record had four missing measurements, IPv6 and descendants, malformed/replay/destination/model/redirect/limits, privileged effects, and revocation/Core/launcher death. N3b attempts each. It retains explicit residual rows where the native observation cannot support the broader claim.

The effect server subclasses production API `Handler` and retains its accept-time attestation, `transport_evidence`, recheck and registry. Its effect handlers append fixture markers only after production transport authorization. It enumerates production routes classified privileged or authority, including routes with the default privileged classification, across bootstrap, local and paired fixture credential labels. Business handlers and real device credentials are outside this fixture contract. Synthetic policy rows separately cover USER, EXECUTION, VERIFIER and UNDETERMINED.

This script does not repeat N3's storage/junction/hardlink phase. Production grant scans still run on every launch. Existing N3 storage evidence remains separate.

## 2. Rows and verdicts

Every FAIL persists a redacted JSONL evidence row before `Recorder` raises `StopRun`. Processing stops immediately. A missing control fails before a denial can establish coverage. Setup failures stop with exit 3. Journals use frozen N3 names and include `script=N3b`, authorization ID, timestamp, case, status and detail. These rows accompany the production per-execution ledger. They do not constitute the protocol's complete batch summary or activation certificate.

| Case | Attempt and PASS meaning | FAIL meaning | INCONCLUSIVE by design |
|---|---|---|---|
| host-controls | Broker request reaches synthetic sender. Host curl reaches each forbidden IPv4/IPv6 listener with observed hit and exact response. Container denial chains print a control marker. | Control absent or wrong. | Source-derived SDK pins and accepting schema-validator stand-in. No native token, effective-policy or MXC registration-disposal read-back. |
| broker-reach | Production listener attests live EXECUTION at accept, maps its held Job to fixture principal, checks token and forwards exactly once to synthetic sender. | Wrong HTTP outcome, no native EXECUTION, missing or extra send. | Native success remains conditional on reviewed SDK/schema evidence. |
| deny-all-both-directions | Direct outbound curl to live IPv4 and IPv6 listeners fails with exit 7, zero new hits and same-chain control. | Reachability, unexpected exit or absent control. | Inbound reach into container has no independently discoverable endpoint. |
| forbidden-ipv4-ipv6-descendants | Under proxy policy, direct forbidden IPv4/IPv6 requests from direct client and nested cmd descendant remain blocked. Same-form host controls precede them. | Any hit, wrong exit or absent control. IPv6 unavailable stops setup. | No claim that production owner lookup attests IPv6 clients. Its broker path is IPv4. |
| wrong-peer-squatting-replacement | Host child with correct token gets closed unread and causes no synthetic send. | Host request is served. | Endpoint squatting, executable replacement and every possible forwarding deputy are broader than this host-child probe. |
| malformed-replay-destination-model-redirect-limits | Invalid JSON, wrong model, absolute-form destination, oversized body and duplicate lengths refused locally. Revoked token replay refused at fresh listener. Redirect produces 502 after one send. Response and request ceilings hold. | Wrong status, unexpected sender call, oversized response or accepted exhausted token. | Concurrency, idle/deadline timing and live upstream destination changes remain unmeasured. Current-generation token reuse is permitted until its ceiling. |
| privileged-effect-origin-matrix | Real contained requests traverse production HTTP origin gate for every privileged/authority route and three credential labels. Each gets 403 and zero fixture effects. Production registry rejects observed non-USER evidence. Synthetic origin policy matrix matches expected local/bootstrap/paired rules. | Fixture effect, missing batch control/completion or unexpected status. | Real independent USER positive control, native VERIFIER producer and real application business effects require an owner-defined fixture API contract. Synthetic matrix entries are labelled. |
| pid-exit-reuse-races | Production binding recheck refuses a client after completed request. | Binding remains valid. | Forced native PID recycling is not reliably observable on demand. |
| revocation-broker-core-death | Three real spawned fixture Cores first report an attested open synthetic upstream session. One revokes its grant. One terminates its owned launcher by retained process handle. One is killed by parent's retained multiprocessing handle. Parent opens and validates launcher generation before death and waits on held handle for Core-death proof. Listener becomes unavailable. Graceful variants report empty held Job. | Missing open-session proof, missing acknowledgement, surviving held launcher/Job or reachable listener. | Fixture Core runs production components but is separate from activated application runtime. After Core death only retained launcher's death is independently read back. MXC registrations and full descendant absence remain unverified. |

Unreadable native state never establishes a PASS. Native production readers fail closed. Failure to acquire the launcher-generation handle stops the death probe. The earlier `wait_dead` reader used by shared teardown remains a process-generation cleanup check, so a cleanup result cannot establish registration disposal.

## 3. Entry and preflight

Future entry accepts exactly one canonical fixture parent at or below `D:\pv20-fixtures`. Execution is forbidden under current authorization state. No native command is provided for execution here.

Before creating a root, the entry requires an existing, regular, single-link, at most 8192-byte `N3b-owner-authorization.json` directly under that parent. Parent ancestry and marker must be free of aliases. Required keys are exactly `authorization_id`, `script`, `scopes`, `approved`. `script` must equal `N3b`, `approved` must be boolean true, and authorization ID must contain 1–64 ASCII letters, digits, underscores or hyphens. The marker records an owner's approval and has no cryptographic authentication. It must never be fabricated by an agent.

Scope list must exactly match this order.

1. `fixture-files`
2. `mxc-profiles`
3. `jobs-processes`
4. `loopback-ipv4-ipv6`
5. `synthetic-broker`
6. `fixture-core-death`
7. `launcher-death`

SDK must already be staged at `<parent>\sdk\node_modules\@microsoft\mxc-sdk`, through separate authorization. SystemRoot must resolve to a plain drive `Windows` directory with cmd.exe. curl.exe must be available there. No installer or network fetch exists in this script. Importing the module creates no native object or socket.

Budget is 1170 seconds for main run, checked before launches. Each normal container has 30-second policy timeout. Effect batches contain up to six requests, each with 3-second curl bound. Death workers have 90-second launch budgets, open-session wait of 15 seconds, channel acknowledgement bounds of 90 seconds and synthetic upstream hold bound of 20 seconds. Cleanup and interprocess waits can exceed the main launch budget. Exhaustion is setup failure with preserved evidence.

## 4. Machine touches requiring authorization

Disk writes stay under fresh marker-verified UUID fixture roots. Main root contains staged SDK copy, protected policies, ledger, environment/config folders, ordinary N2 fixture folders, request bodies, effect batch files and JSONL verdicts. Each death probe creates another sibling UUID root with its own SDK copy and ledger. Each root is retained. Child paths can be found by comparing fixture-parent inventory before and after the future run.

All home/profile/temp/config variables are pinned to an empty fixture `envhome` before production imports and held there throughout execution. Death workers pin their own environment before imports. Original parent environment is restored on exit. Script reads SystemRoot to locate Windows tools. No account-home file, credential store, real API key, real account or external endpoint is needed.

Kernel/process operations include real KILL_ON_JOB_CLOSE Jobs, suspended launchers, assignment and membership checks, resume, process/ancestry/session/TCP owner observation, launcher termination, fixture-Core termination and handle close. MXC itself may create/delete profiles and leave registrations. Observation cannot verify those registrations' absence.

Network operations are restricted to script-owned `127.0.0.1` and `::1` listeners and clients. No upstream socket is opened by broker sender. All host curls disable proxies explicitly. Forbidden-endpoint policies deny egress except the intended loopback proxy route. Firewall configuration and ACLs receive no script-side writes.

## 5. Deletion and evidence retention

Every fixture root is preserved on every exit, including hypothetical exit 0. This deliberately chooses stricter retention than older N2's remove-on-success behavior. Production transport can remove its own protected policy files during handle close. No recursive deletion, SDK-source modification or registration cleanup occurs.

Evidence files contain fixture requests, route names, process identities in production ledgers and redacted verdict details. Broker tokens appear in container command lines and request arguments. Upstream credential-shaped string is synthetic. Review all retained raw artifacts before sharing. Authorization ID is an inventory identifier, never a credential.

## 6. Stop behavior

Ctrl+C causes exit 3, broker revocation and Job closure through `wind_down`, then bounded owned-launcher checks. Death-probe `finally` terminates its own multiprocessing child if still alive and closes retained launcher/IPC handles. Cleanup errors force exit 3. Abrupt parent console death closes its own Jobs. A spawned fixture Core is separately bounded by its channel/open-stream waits and has its own Job handles. Console-close behavior of that worker remains a native observation, so use controlled interruption for first review.

No PID/name sweep is used. Workers are addressed through retained process objects. Launcher-death action uses its retained production process handle. Shared N2 cleanup targets only generations recorded by its counting API.

## 7. Exit codes

0 all PASS, currently unreachable with declared residual rows. 1 first FAIL. 2 no FAIL and explicit INCONCLUSIVE, expected after completed measurements. 3 refused setup, budget exhaustion, interruption, unexpected exception, cleanup error or surviving owned launcher. All preserve fixtures.

## 8. Owner questions before any future run

1. Is a new N3b authorization granted after reviewing exact script revision, hashes and this sheet, under test lock at below-normal priority?
2. Are loopback IPv4 and IPv6 listeners authorized, including host positive controls and descendant curls? Is unavailable IPv6 correctly treated as setup failure?
3. Are MXC profile side effects, Job creation/termination, process/TCP/ancestry/session reads, and retained artifacts authorized separately?
4. Are real fixture-Core and wxc-exec termination during attested open sessions authorized? Confirm no production Core may be targeted.
5. Which reviewed SDK inventory and schema validator should replace current stand-ins? Is measurement with declared stand-ins acceptable first?
6. Is fixture-effect HTTP server acceptable for transport-gate evidence? Who supplies independent USER positive control and native VERIFIER producer before claiming full application privileged-effect coverage?
7. Are unmeasured inbound access, endpoint squatting/replacement, concurrency/deadline timing, forced PID reuse, post-Core-death descendant absence and registration disposal accepted as residuals, or must their native contracts be built first?
8. Are unchanged UI-disabled policy and empty launcher environment the intended first attempt, with failures reported directly?
9. Is full retention of main root plus three sibling death roots approved? Who inventories and later cleans registrations and files using marker/no-follow safeguards?
10. Are timeout bounds and interruption limitations acceptable? Confirm owner will review raw artifacts before publication.
11. Who issues authorization marker through an approved channel? This checkout contains none and must remain unexecuted.

## 9. Verification and drift guard

Tests exercise script request construction and case driver over production broker, listener, native-reader reduction and Windows origin backend, with fake sockets/process table and in-memory upstream. Effect test invokes real production HTTP gate over fake observations. Death orchestration uses fake child/channel/held handles. Windows-only drift test uses shared scripted Win32 API and Jobs with production `MxcLaunch`, transport, policy and ledger. Existing drift suite checks fake method signatures against production bindings. F8 adds a corresponding deny-all launch guard.

Coordinator must run these from worktree root, without native scripts.

```text
pytest -q tests/v1/unit/test_pv20_native_n3b.py tests/v1/unit/test_pv20_native_f8.py tests/v1/unit/test_pv20_native_drift.py
ruff check tools/pv20_mxc/native/n3b_check.py tools/pv20_mxc/native/f8_check.py tests/v1/unit/test_pv20_native_n3b.py tests/v1/unit/test_pv20_native_f8.py
```

Fakes cannot prove Windows/MXC reachability, exit-code framing, pipe behavior, real process death or production admission. Coordinator test results remain pending.
