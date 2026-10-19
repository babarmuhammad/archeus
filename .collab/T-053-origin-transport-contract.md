# T-053 · R1-A origin, hop and deputy transport contract

Claude, 2026-10-13. Analysis only, at the reviewed baseline `5dfac53` (`D:/archeus-pv20-s2-l`). Nothing here is implemented, run or accepted evidence. Labels used throughout: **FACT** is cited source or primary documentation; **CANDIDATE** is proposed here and not decided; **UNVERIFIED** is a claim nobody has sourced or observed. The authority is ADR-0053: §3 item 3 (R1-A, lines 107-119), §7 A3 (lines 283-303), Consequences (lines 412-415) and "Not decided here" (lines 421-433). The attestation mechanism is explicitly undecided there (line 300 and line 425), and this note does not decide it either.

## 1. What carries authority today (FACT)

There are two transports into Core and one discovery directory.

**HTTP API.** A `ThreadingHTTPServer` is bound to `127.0.0.1` with exclusive address use (`archeus/api/server.py:407-421`). Each request goes through a fixed pipeline (`server.py:3-21`, enforced at `:297-366`):
1. the Host header is checked (`:313`, `auth.Origin.host_ok`, `auth.py:100-101`);
2. fetch metadata and Origin are checked (`:316`, `auth.py:113-121`);
3. the bearer device token is checked (`:338-341`, `Api.authenticate` at `:210-220`);
4. the route's scope is checked (`:342-343`);
5. a local-origin credential is honoured only on the loopback Host (`:344-350`).

The peer address is stored on the request (`:302`), but the pipeline never checks it. Only `_loopback` reads it (`routes.py:100-105`), and only on the launch-code and pairing routes (`:206-262`). Two consequences follow:
- **Who the connecting process is never decides any scoped route, privileged or not.** What decides is whether the caller holds a live credential (`auth.live`, `auth.py:75-84`) and what Host header it sent.
- **Credential locality is a property of the device record, not of the transport.** `device_origin` comes from the credential's device row (`queries.py:110-120`). Step-up for a local client "is satisfied by being local", meaning by that record (`core/application/authorization.py:562-570`).

**The local token.** The local token holds every scope (`auth.py:24-26`, `runtime.py:545`). It is `dev_` plus 256 random bits, and its only plaintext copy at rest is `run/local-token` (`auth.py:8-11`; `infra/discovery.py:3-5`, `:42-43`). The port is in `run/core.json` (`discovery.py:4`, `:38-39`). The run directory is created with `mode=0o700` (`discovery.py:46-49`). On Windows that mode does not set an ACL, so the directory inherits the user's ACL. That is UNVERIFIED here, but the ADR's G2 finding (`ADR-0053.md:21-22`) states the effect: any process with the user's identity reaches the full-scope principal.

**Hook mailbox (file transport).** The execution's hook takes its identity from three environment variables: `ARCHEUS_HOME`, `ARCHEUS_EXECUTION_ID` and `ARCHEUS_HOOK_TOKEN` (`harnesses/hook.py:130-136`).
- **The request.** The hook writes `run/exec/<id>/req/<seq>.req.json` with the token inside the body (`:160-161`). It accepts only Core's answer in `res/` (`:162-180`; `node/local.py:248-279`).
- **The token.**
  - **Mint and record:** Core mints a fresh `hook_` token for every process (`core/execution/manager.py:227`), passes it in the environment (`:246`), and records only its digest (`:275`; `core/application/executions.py:95-128`).
  - **Clear:** the digest is cleared at every end (`executions.py:148, 264, 270, 276, 297, 354, 564, 598`).
- **The check.** `serve_hook` refuses three cases and halts the process:
  - a sequence number already answered (`:626-627`);
  - a token whose digest differs (`:629-631`);
  - any state other than STARTING or RUNNING (`:624-625`).
- **What it can grant.** Its only outputs are allow, deny or halt. An ASK moves the execution and waits for the user's approval (`:657-663`); nothing on this path approves.
- **Execution-authored files.** The hook also writes `halted.json` and `precompact.json` (`hook.py:83-91`, `:139-148`). Core already treats both as the execution's own claims (`manager.py:806`; `ADR-0053.md:132-138`, R5).

**Stream reports.** The model, usage and result in an execution's output stream are claims, not observations. They are recorded beside the routed identity (`core/domain/entities.py:1159-1160`, Verification `provenance`), and under A7 an execution-authored result is never a process exit (`ADR-0053.md:304-312`).

## 2. Origin map: every path that can reach Core

Status at `5dfac53` versus the A3 target. "§3.6" is the closed effect set (`ADR-0053.md:70-74`).

| # | Origin | How it reaches Core today | Credential | Attested? | A3 target |
|---|---|---|---|---|---|
| O1 | User at this machine: CLI/TUI, browser via launch code | HTTP loopback | local token or launch-code device | no | §3.6 only if the origin is attested as the user AND the path is approved |
| O2 | Paired client via a tunnel host | tunnel → loopback; Host is the tunnel name (`auth.py:87-98`; `server.py:344-350`) | paired device and PIN step-up | no | only what P15 and D10 permit; never "direct local" |
| O3 | Execution, isolated | hook mailbox; HTTP if loopback is reachable | hook token (mailbox only) | no | mailbox only; no `user_device` authority; refused all §3.6 |
| O3' | Execution, ordinary (as the user) | mailbox, plus HTTP with `run/local-token` readable | token readable by its identity | no | identical to O1 by identity: R1-A cannot hold (§5, Q2) |
| O4 | Verifier commands (`node.run_check`) | runs as the user, inheriting Core's environment minus `PYTEST_*`, so including `ARCHEUS_HOME` (`node/local.py:490-507`) | can read `run/local-token` | no | no Core route at all (R4b, A6; `ADR-0053.md:299`) |
| O5 | Forwarding hops: tunnel daemon, any local proxy or port-forward | loopback | whatever it forwards | no | hop rule: permitted only if unreachable by execution or verification identities, or with no route to Core |
| O6 | Archeus's own user-identity deputies (see below) | they run as the user | account login; Core's environment | no | deputy rule: execution-influenced content only as prompt or data |
| O7 | Core internal (workers, writer) | in process | system actor | n/a | unchanged |

The deputies in O6, with the FACT that places each one:
- **Model calls** run `claude -p` / `pi` with `cwd=spec.workdir` and `env=config.account_env(home)` (`harnesses/calls.py:92-96`, `:146-148`). The argv restricts write tools, turns and budget, but not which settings sources load (`claude_sessions/llmcall.py:52-56`).
- **Knowledge pass.** It runs with `cwd=repo.path`, the user's repository (`core/knowledge/passes.py:177-182`), which receives execution-derived content once it is merged.
  - **Why that matters:** Claude Code loads project-scoped settings, including hooks, from its working directory. That is documented Claude Code behaviour, but it was not re-read for this note, so it is UNVERIFIED here. If it holds, this call can run execution-influenced configuration as the user, which violates the deputy rule.
  - **The other calls** use `archeus_home()`, Core-owned: `core/verification/worker.py:391`, `core/missions/intent.py:137`, `core/knowledge/passes.py:205` and `:234`, `core/planning/worker.py:133`.
- **Core Git** in execution workdirs and in the user's repository (A5; interim guards in T-042, T-044 and T-048).
- **Verification commands** (O4 above).
- **Interactive sessions Archeus launches** (P12, `core/sessions/service.py:114`). Their cwd, settings sources and environment were not mapped here (UNVERIFIED).

## 3. Three things that are not attestation

1. **Possession or digest of a token** proves only that the presenter could read or receive a secret. Under G2, every process with the user's identity can (`ADR-0053.md:21-22`). The hook token is execution-scoped by construction, and is accepted only on the mailbox path for its own execution (`executions.py:629-631`).
2. **Request claims never establish origin.** These include the Host header, Origin, fetch metadata, `X-Archeus-*` headers, a `cwd` in a hook request, any PID or path in `halted.json`, and the stream's model, usage or result. They help refuse cross-site or tunnel-confused requests (`auth.py:100-121`). Any local process can send them all.
3. **The peer address** `127.0.0.1` proves only that the process is on this machine. A tunnel forwards from loopback (`routes.py:101-103`, D17), and so does any proxy.

**Attestation, the CANDIDATE definition:** Core's own observation, at accept time, of the security identity behind the connection. That means the token's user SID, whether it is an AppContainer token, and which execution or verification principal it is. Core checks the identity before it reads any credential, and records the result on the request as `origin ∈ {user, execution:<id>, verifier:<id>, undetermined}`. Three rules follow:
- an absent or failed observation is `undetermined`;
- `undetermined` never receives any `user_device` authority;
- the credential is still required: attestation is necessary, not sufficient (A3 (1) and (2)).

**Mechanism candidates.** None is chosen here (ADR line 300).
- **Named pipe.** FACT: `GetNamedPipeClientProcessId` returns the client process id of a pipe instance created with `CreateNamedPipe` (https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getnamedpipeclientprocessid, "Return value"). An approach that reads the client's token directly instead of resolving a PID is UNVERIFIED (not sourced here).
- **TCP loopback.** FACT: `GetExtendedTcpTable` with the `TCP_TABLE_OWNER_PID_*` classes returns `MIB_TCPTABLE_OWNER_PID` rows (https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable, Remarks). Two parts are UNVERIFIED and inferred: matching a connection to its row, and the race between that table snapshot and process exit or PID reuse.
- **AppContainer reach to loopback.** FACT for packaged apps: "loopback connections for IPC are blocked by default for packaged applications" (https://learn.microsoft.com/en-us/windows/uwp/communication/interprocess-communication, "Loopback"). Whether a raw AppContainer token created with `CreateAppContainerProfile`, which is not a package, behaves the same is UNVERIFIED. T-017 already records that question (`T-017-private-config-plan.md:117-118`).

## 4. Fail-closed pins (CANDIDATE contract)

**P1. Every scoped route requires the attested user origin.**
- An execution, a verifier or an undetermined peer gets 403 on every scoped HTTP route, `observe` included, before the credential is evaluated. That follows "receives no `user_device` authority" (ADR line 108-110). The refusal records the attested class and never a credential.
- A broker endpoint (T-050, sibling card) is a separate listener with its own principal kind. It is never an exception to this rule (ADR lines 120-124).

**P2. The §3.6 subset additionally requires the direct approved path.** Concretely:
- the credential's device origin is `local`;
- the request carries the loopback Host;
- no tunnel host is configured as the request's Host;
- the attested process is not a known hop or deputy (P5, P6).

The §3.6 subset at `5dfac53`, mapped from the route table (`routes.py:957-1150`):

| §3.6 effect | Routes |
|---|---|
| Privileged Core control: missions | create (`:973`), pause/resume (`:975-982`), reprioritise (`:984`), stop (`:1071-1073`) |
| Emergency stop and re-arm | estop (`:1075`), rearm (`:1076`) |
| Handoff | sessions handoff (`:1086`), execution handoff (`:1094`) |
| Approvals and decisions | plan edit (`:971`), approval decide (`:1120`), verification decide (`:1127`), mission review (`:1131`), integration abandon (`:1133`) |
| Policy modification | rules, retire, profile (`:1106-1110`) |
| Administration | devices (`:988-998`), projects (`:1006`), provider terms (`:1047`), accounts, resource policies, opt-ins (`:1052-1062`), automations (`:1147-1149`), meetings import (`:1039`) |

- **Paired clients:** keep exactly P15/D10 (`authorization.py:554-570`).
- **Unclassified routes:** adding a scoped route that this table does not classify fails a static test (CANDIDATE).
- **The canonical list stays PV-20 §3.6.** This mapping is only its route projection. A route whose classification is unclear is treated as §3.6.

**P3. Stale resume.** A hook request is answered only for a live process whose current digest matches (FACT, `executions.py:624-631`).
- **After a Core restart,** isolated executions are not adopted (R6-A, `ADR-0053.md:313`), so their mailboxes produce only halts.
- **Ordinary executions** are adopted with their recorded digest. Whether a pre-restart process can still use its token after the digest has been cleared or replaced was not traced here (UNVERIFIED). The pin: any request from a process Core has not adopted under its current `process_seq` is a halt, never a deny-and-continue.
- **HTTP:** a credential minted before a restart remains valid by design. Attestation runs per connection, so a resumed client is re-attested on every new connection.

**P4. Relay.**
- **Hook tokens:** a token valid for execution A, presented in B's mailbox, halts B (FACT, digest mismatch).
- **Mailbox writability:** whether B can write A's mailbox at all depends on the S2-G per-execution ACLs. ACL code was removed in S1 (CLAUDE.md gotcha; `test_the_boundary_has_no_acl_mutation_primitive`), so this is UNVERIFIED until S2-G.
- **HTTP relay:** an execution-influenced user-identity process relaying a request is, to attestation, the user. That is closed only structurally, by P6, never by inspecting the request.

**P5. Loopback and hops.**
- **The tunnel hop already exists.** It is the configured remote host. Its requests carry the tunnel's Host, so a local credential is refused through it (`server.py:344-350`).
- **The CANDIDATE rule:**
  - **Rewritten Host:** a hop that rewrites Host to `127.0.0.1:<port>` is indistinguishable from O1 by request content. It is permitted only if the hop rule holds for it (no execution or verification identity can reach it, or it has no route to Core).
  - **Host-system hops:** Core cannot enumerate the hops a user installs, so a hop the user adds outside Archeus is the user's own act, and a stated limit of R1-A.
  - **Archeus-owned hops:** if Archeus itself owns or launches one, it is registered, and its attested identity is refused §3.6 (P2).
- No automatic switch to R1-B or a network change: if attestation is unavailable, P1 makes everything `undetermined`, and the §3.6 set is refused instead of degrading (ADR lines 116-119).

**P6. Privileged actions and deputies.** No Archeus-owned process running as the user may do either of these with execution-influenced content:
- execute it, or load it as configuration;
- receive Core's environment, including `ARCHEUS_HOME`, unless it is part of Core.

The FACT violations listed in §2 under O6 each need a removal or a confinement:
- verification (R4b; interim T-042);
- Core Git (A5; T-044 and T-048 interim);
- model calls whose cwd is a repository receiving execution content (`passes.py:181`);
- `run_check`'s inherited environment (`local.py:499`).

Clients render execution content as data only. The SPA's CSP is `'self'` with no inline script (`auth.py:40-41`), and that stays a pin.

## 5. Soundness preconditions

R1-A attests identity, so it can only separate identities that differ. Any execution-influenced code running as the user is the user to it (ADR lines 111-112). Every path in §2 that runs as the user must therefore be closed before any acceptance row depending on R1-A can pass:
- **O3':** ordinary executions;
- **O4:** verification;
- **O6:** the deputies, including the `cwd=repo.path` call and interactive sessions.

At `5dfac53` none is closed in general; only the interim guards cover known-isolated cases. This note does not change PV-20 acceptance rows 4 and 5, which stay design-open (ADR lines 391-394).

## 6. Minimal manifests (CANDIDATE cards; none authorised)

- **K-O1, code (fake attestor):**
  - `archeus/api/server.py`: an attestor port called in `_serve` before `authenticate`, the result stored on the request; P1 and P2 enforced.
  - `archeus/api/routes.py`: a frozen `PRIVILEGED` route set and a classification table.
  - `archeus/api/auth.py`: the origin enum.
  - Tests in `tests/v1/unit/test_api_origin.py` (new), with an injected fake attestor:
    - execution, verifier and undetermined peers with a valid local token get 403 on every scoped route, observe included, and nothing is written;
    - an attestor that raises yields undetermined, then refusal;
    - a user peer with the tunnel Host and a local credential still gets 403;
    - a paired peer through the tunnel follows the unchanged P15 rules;
    - a scoped route missing from the classification table fails;
    - a static check that the request log never records the attested peer's token.
  - Production behaviour: the attestor defaults to `undetermined` only once the owner activates it. Until then the CANDIDATE is the identity "user" for every peer, which changes nothing, under a production switch that stays off.
- **K-O2, code (deputies):**
  - Move the knowledge pass's cwd to a Core-owned empty directory, keeping repository facts as prompt data.
  - Scrub `run_check`'s environment of `ARCHEUS_HOME` and the run discovery as an interim. That is not R4b: the user's identity can still read `run/` directly.
  - A static test that every `CallSpec(workdir=…)` is Core-owned.
- **K-O3, mailbox (fake):**
  - Tests pinning P3 and P4 on `serve_hook`: a request from a stale process, a cross-execution token, a replayed sequence number, and a request after the digest is cleared.
  - Several of these may already exist in `tests/v1/integration/test_execution.py`; to be checked, not assumed.
- **K-O4, real evidence (native; owner authorisation required, separate card):**
  1. whether an AppContainer process from the S2 path can open a TCP connection to Core's loopback port at all, and whether a pipe is reachable;
  2. the chosen mechanism's observation for each of a user process, an AppContainer process and a verifier principal;
  3. behaviour under PID reuse and early exit;
  4. the listener's and `run/` ACLs as actually set.

  No probe is run under this card.

## 7. Transport unknowns (UNVERIFIED)

- Raw (unpackaged) AppContainer loopback behaviour, with and without network capabilities, and whether a loopback exemption is needed, or must be refused, for the R3-B broker (T-050).
- Whether a TCP owner-PID lookup can be made race-free, or needs the client to prove possession of its own handle.
- Whether the browser client (SPA) can ever be attested beyond "a user process", and so whether browser §3.6 remains allowed under the direct-path rule.
- Windows ACL of `run/` and `run/local-token` as created today; what S2-G must set.
- Ordinary-execution token reuse across a Core restart (P3).
- The cwd and settings sources of P12 interactive sessions and of `pi` calls.
- `claude_sessions/failover.py` (claudectl's local provider proxy) as a hop: not inspected here.

## 8. Owner questions

**Q1. Transport for attested §3.6 requests.**
- **A (recommended):** keep the existing TCP loopback API and attest per connection. K-O4 decides whether that is reliable. If it is not, P1 leaves everything undetermined and the §3.6 set refused until Q1 is revisited. This changes no transport, consistent with ADR lines 116-119.
- **B:** add a second, pipe-only transport for §3.6 routes now. The CLI and TUI move to it, and the browser loses §3.6 or gets step-up. This is the transport change that ADR line 117 makes a new owner decision.

**Q2. Ordinary executions while R1-A is claimed.**
- **A (recommended):** claim R1-A's §3.6 refusal as sound only for a Core in which no ordinary execution, verification or Archeus deputy runs execution-influenced code as the user. A Core with ordinary dispatch enabled reports the R1-A rows as not met. This is the A4 router-eligibility consequence (ADR lines 396-397).
- **B:** allow mixed dispatch and claim R1-A for isolated executions only. That is unsound by ADR lines 111-112, because an ordinary execution reads `run/local-token` and is the user to attestation.

This is the open mixed-mission dispatch question seen from the transport side.
