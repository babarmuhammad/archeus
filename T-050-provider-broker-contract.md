# T-050 · R3-B provider broker: minimum feasibility and ownership contract

Prepared by Claude (a read-only fork), 2026-10-13. Analysis only. Code is cited at the reviewed S2 baseline `5dfac53` (`D:/archeus-pv20-s2-l`), read with Read/Grep only. Nothing was executed: no CLI or version call, no provider or model request, no network change, no test, no native call, no secret or environment value read. Three pages of Claude Code's public documentation were read with WebFetch, as untrusted data, and no page file was saved.

Labels: **[DOC]** stated by primary documentation (URL and section given); **[CODE]** read at `5dfac53`; **[ADR]** canonical decision text; **[CAND]** this note's proposal; **[UNK]** unknown or unverified.

**No token name, prefix or shape proves anything here.** A `brk_…` string proves possession of that string, not who presented it, from where, or that the broker is feasible. Origin is T-053's. Feasibility needs the real-run evidence in §8.

## 0. Bottom line

- **The wire shape is documented, so R3-B is not blocked by the CLI's interface [DOC].** Claude Code documents running against an Anthropic-format gateway: `ANTHROPIC_BASE_URL` plus a gateway credential. "The provider key stays server-side; developers hold gateway credentials instead."
- **Three things still block it:**
  1. **Loopback reach [UNK].** The isolated execution has zero AppContainer capabilities (`isolation.py:67`), so whether it can reach any loopback listener is unknown. This is P23/T-053's to decide, not the broker's.
  2. **The upstream credential kind [DOC][UNK].** The docs describe a gateway credential replacing the subscription login. They never describe a server that injects a claude.ai subscription login, and today's router prefers subscription accounts (`router.py:214-218`).
  3. **Traffic outside the gateway path [DOC].** Some of the CLI's own requests ignore `ANTHROPIC_BASE_URL`.
- **If the target is unsupported, nothing falls back.** Scoped credentials inside the boundary (R3-A) need a separate owner security decision, and until one of the two is viable, isolated Claude Code executions do not run (ADR-0053 R3, lines 120-127).

## 1. What the primary documentation states [DOC]

Sources:
- G1 = https://code.claude.com/docs/en/llm-gateway ("What a gateway provides", "Subscriptions and gateways").
- G2 = https://code.claude.com/docs/en/llm-gateway-protocol ("API formats", "Optional endpoints and startup traffic", "Streaming", "Request headers", "Response headers", "Feature pass-through", "Model discovery").
- G3 = https://code.claude.com/docs/en/llm-gateway-connect ("How the credential variable maps to a header", "Conflicts with an existing login", "Rotate credentials with apiKeyHelper", "Turn off traffic outside the gateway path").

These pages describe the current CLI. The installed CLI's version was not read, so behaviour that the docs tie to a version is unverified for this machine.

| # | Fact | Source |
|---|---|---|
| D1 | The Anthropic Messages format is selected by `ANTHROPIC_BASE_URL`. Its endpoints are `/v1/messages` (inference posts to `/v1/messages?beta=true`) and `/v1/messages/count_tokens`, which is optional; without it the CLI estimates by characters. | G2 API formats, Optional endpoints |
| D2 | Startup sends a `HEAD /api/hello` warming probe, which "it can reject without breaking anything". `GET /v1/models?limit=1000` is sent only with `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`; it is off by default and "any redirect is treated as failure so the credential can't leak". | G2 Optional endpoints, Model discovery |
| D3 | `ANTHROPIC_AUTH_TOKEN` is sent as `Authorization: Bearer`, `ANTHROPIC_API_KEY` as `x-api-key`, and `apiKeyHelper` in both. `ANTHROPIC_API_KEY` needs a one-time approval in interactive mode; `ANTHROPIC_AUTH_TOKEN` "takes precedence immediately" over a saved login. | G3 header mapping, Conflicts |
| D4 | `apiKeyHelper` is "any shell command"; the CLI runs it "through your system shell", caching the result for 5 min (`CLAUDE_CODE_API_KEY_HELPER_TTL_MS`). | G3 Rotate credentials |
| D5 | With a gateway credential active, requests carry it "in place of a developer's claude.ai subscription login", the subscription's limits don't apply, and the traffic is "billed per token to whoever owns the credential the gateway forwards". `ANTHROPIC_BASE_URL` alone leaves the claude.ai login active, and a gateway must then forward its OAuth `anthropic-beta` value. | G1 Subscriptions and gateways; G2 Request headers |
| D6 | `anthropic-version` and `anthropic-beta` must be forwarded unchanged, and headers and body fields treated "as open lists". A gateway that "rewrites or redacts request bodies… breaks the pairing", so it should "inspect without modifying". Error bodies must be forwarded unmodified, because the CLI's retry logic matches their wording. | G2 Request headers, Forward as open lists, Feature pass-through |
| D7 | Streaming is relayed event by event: a gateway that buffers stalls the CLI, and stripping SSE `ping`s can trip its idle timeout. The CLI reads `retry-after` (integer seconds), `x-should-retry` and `anthropic-ratelimit-unified-*`. | G2 Streaming, Response headers |
| D8 | Some of the CLI's own requests bypass `ANTHROPIC_BASE_URL`. The fast-mode availability check and the WebFetch domain safety check call `api.anthropic.com` directly, and telemetry goes to Anthropic. `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` turns off version checks, telemetry, release notes, auto-updates and the fast-mode check, but not the WebFetch preflight (that needs `skipWebFetchPreflight: true` in settings). | G2 Optional endpoints; G3 Turn off traffic |
| D9 | Requests carry `x-claude-code-session-id` (and agent ids for subagents). `ANTHROPIC_CUSTOM_HEADERS` adds headers. | G2 Request headers |

Not stated anywhere in these pages, so **[UNK]**:
- a server-side broker substituting a claude.ai subscription OAuth credential;
- the CLI reaching a gateway on `127.0.0.1` from inside an AppContainer;
- whether `-p` (headless) mode applies the `ANTHROPIC_API_KEY` approval rule.

## 2. Existing seams at 5dfac53 [CODE]

| Seam | Where | What it means for R3-B |
|---|---|---|
| Isolated env is a pinned table built from nothing; an unknown `spec.env` name refuses | `harnesses/base.py:408-472` (table `:423-427`, refusal `:458-460`) | Broker variables must be added to the table, derived by Core. They can't be passed through. |
| `CAPABILITY_ENV` (Git credential-helper off) | `base.py:32-34` | Unrelated to provider access; stays. |
| Adapter env: isolated → `ExecPaths.config`; `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` default to removal | `claude_code/adapter.py:161-170`, docstring `:18-23` ("no login is put there (that is R3-B's broker)") | Today an isolated execution has **no** provider credential at all, so it can't reach a model. That is R3's fail-closed state. |
| `authenticate` reads the account home's login | `adapter.py:115-118` | Account secrets live in the account home, outside the boundary (A2). |
| Private config dir | `infra/paths.py:157` | A fresh `CLAUDE_CONFIG_DIR` with no login (A2). |
| Account auth kinds | `core/domain/entities.py:1307` (`subscription_oauth`, `api_key`, `provider_proxy`) | The broker must branch on these. Only some can be injected (§5 X1). |
| Router prefers subscription accounts | `core/routing/router.py:214-218` | The default route is the one kind the docs do not cover. |
| Provider terms (ADR-0021) | `entities.py:1312-1322` | `headless` must already be `permitted` for any automated call; the broker does not change that gate. |
| Core API accepts only device tokens | `api/auth.py:58-64` (`token_kind(...) != 'device'` → None) | A broker credential with its own prefix is refused by the Core API by construction. |
| Token prefixes / kind | `core/domain/ids.py:47`, `:117-126` | A new `brk` prefix is one dict entry. The prefix proves nothing about origin. |
| Hook token: minted per process, digest stored, cleared on every end path | `core/execution/manager.py:227`, `:275`; `core/application/executions.py:95-136`, compare `:629-631`, clears `:148, :264, :270, :276, :297, :354, :564, :598` | This is the lifetime/revoke pattern to copy for the broker credential. |
| No AppContainer capability | `node/isolation.py:67` (`CAPABILITIES = ()`), `:69-70`, `:1963` | No network for the execution today. Any loopback reach is a P23/native decision. |
| Existing local forwarder (failover) | `claude_sessions/failover.py:249-257` (strips hop-by-hop, injects `Authorization`/`x-api-key`), `:267` (forwards `self.path` verbatim) | This is a forwarder, not a broker: its client already holds the upstream key (`config.py:1421-1422`), and it forwards any path. |
| Front-door checks | `claude_sessions/proxy_base.py:272-305` (Host allowlist, browser-metadata refusal, constant-time key compare) | The Host and browser checks are reusable. Its single-key model is not (§3 S1). |
| Routed-session env | `claude_sessions/config.py:1389-1432` (`ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` = profile key, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`) | The product already drives the CLI through `ANTHROPIC_BASE_URL`, but for interactive, non-isolated sessions only. That is not evidence for isolated ones. |

## 3. The three separations the card requires [CAND]

- **S1: the execution's broker credential vs every account secret.**
  - The execution holds only `brk_` plus 256 random bits, minted by Core for one execution process.
  - Core stores only its sha256 on the Execution row, beside `hook_token_hash`, and clears it on every end path.
  - It carries zero Core scopes, the Core API refuses it (`auth.py:62`), and only the broker reads it.
  - The account secret (API key, proxy key, or anything in the account home) stays in Core's process. The broker attaches it to the outbound request after the inbound one is authenticated.
  - The two never share a header slot on the same leg: inbound `Authorization`/`x-api-key` are stripped before the upstream headers are built. This is the opposite of `failover.py`, where the client's key *is* the upstream key.
- **S2: HTTP request authority vs model stream reports.**
  - What the broker counts (requests, bytes, the usage figures in the upstream's own SSE `message_delta`, read without modification) is the broker's observation of a request it authenticated.
  - The execution's stream-json on stdout (`adapter.normalise`) stays an execution-authored report under ADR-0048 and T-025: never authority to grant more quota, and never proof of what was called.
  - The broker's counts feed ceilings and audit. They do not become a Core state transition except through the existing usage/limit paths.
- **S3: the external provider path vs forwarding or deputy traffic.**
  - The broker serves one purpose: a known execution reaching its routed provider on an allowlisted path.
  - It has no Core route and never forwards to Core, a node, a tunnel or any user-identity service.
  - It never takes a destination from the request (Host, absolute URI, `CONNECT`, a redirect).
  - It serves no non-execution caller: Archeus's own calls (planner, review, knowledge) keep their path under the deputy rule (ADR-0053 A3, lines 341-345).
  - A broker that accepted user-device tokens or forwarded arbitrary paths would become an R1 path, which ADR-0053 forbids (line 124).

## 4. The minimum candidate, B1 [CAND]

One Core-owned loopback HTTP listener, separate from Core's API listener and port. It speaks only the Anthropic Messages format (D1), has no Core route, and holds no state but an in-memory credential map that is rebuilt from the database.

| Pin | B1 |
|---|---|
| Inbound endpoints | `POST /v1/messages` (query `beta=true` only). `POST /v1/messages/count_tokens` is optional, off in B1, and its absence is documented harmless (D1). `HEAD /api/hello` gets a local `204` with nothing forwarded (D2). Everything else gets a local `404` with nothing forwarded, including `/v1/models` (discovery left off) and any `CONNECT` or absolute-form request. |
| Front door | `Host` must equal `127.0.0.1:<broker port>`; reject `Origin`/`Referer`/`Sec-Fetch-*` (both checks as in `proxy_base.py:286-293`); a bounded request size and header count. |
| Credential check | Bearer or `x-api-key` value → sha256 → constant-time match against the live map. The map holds an entry only for an execution in STARTING/RUNNING/PAUSING/HANDING_OFF with a non-null broker digest **and** isolated True (non-isolated executions keep today's path). No entry → `401` with nothing forwarded. |
| Hop / upstream | Destination = the upstream of the account named by the execution's own `RouteDecision`, resolved by Core from rows. Allowlisted scheme `https` (or loopback `http` for a registered `provider_proxy`), fixed host and port, no redirect following. Same path, method and query; body forwarded byte-for-byte (D6). |
| Headers out | Drop inbound hop-by-hop headers, `Authorization`, `x-api-key` and `Host`; keep `anthropic-*` and all other headers unchanged (open list, D6); add the account credential in the header its kind requires. |
| Response | Status, headers and body relayed unbuffered, pings kept (D7); error bodies unmodified (D6). |
| Model | Read-only check of the body's `model` against the route decision's model: mismatch → `403` with nothing forwarded. Compatible with D5/G2's statement that with `ANTHROPIC_AUTH_TOKEN` background tasks use the main model. A subagent pinned to another model fails closed (§5 X5). |
| Credential origin | Minted in the manager beside the hook token (`manager.py:227`), digest written by `prepare_process`, value given to the child only through the pinned env table as `ANTHROPIC_AUTH_TOKEN` (never `ANTHROPIC_API_KEY`, D3; never `apiKeyHelper`, D4: it runs a shell command, and the helper itself would be execution-influenced config). |
| Lifetime | One credential per process (`process_seq`); a resume gets a new one; never written to disk by Core; the private config dir holds none. |
| Revoke | Cleared in the same transaction as `hook_token_hash` on every end path (§2). The broker re-validates per request and closes in-flight streams of an execution that leaves the live set; emergency stop (disarm) empties the map. |
| Ceilings | Per execution: concurrent streams (1–2), request count, request and response bytes, a per-request wall clock, and total lifetime bounded by the execution's. Usage figures from the upstream's `message_delta` count against the existing per-task budget; exhaustion → `429` with integer `retry-after` (D7) and a Core-recorded reason. Values are candidates. |
| Audit | One record per request: execution id, route decision id, account id, model, path, status, bytes, duration and upstream usage. Never a body or any header value. |
| Redaction | No credential (inbound or upstream) in any log, event, error or audit row. Upstream error bodies go to the client verbatim (D6) but into logs only as status and length. |
| Env in the pinned table | `ANTHROPIC_BASE_URL` = broker URL; `ANTHROPIC_AUTH_TOKEN` = this process's `brk_` value; `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` (D8). `skipWebFetchPreflight: true` in the Core-authored `settings.json` (`adapter.py:120-133`, class 2). All derived by Core; a request for any other value refuses (`base.py:469-470`). |

What B1 deliberately is not: a general proxy, a `CONNECT` tunnel, a gateway with its own model routing, an MCP or Git broker, or a path for anything that is not an isolated execution.

## 5. Concrete incompatible cases

- **X1: subscription accounts [DOC][UNK].** The docs describe a gateway credential *replacing* the claude.ai login (D5). They do not describe a server injecting a subscription OAuth credential on the client's behalf. Doing that would also put the user's login in a Core-run forwarder's hands under ADR-0021 terms. B1 therefore serves only `api_key` and `provider_proxy` accounts, and a route to a `subscription_oauth` account is refused before spawn. With `router.py:214-218` preferring subscriptions, most current routes fail closed. Owner Q1.
- **X2: bypass traffic [DOC].** The WebFetch preflight, the fast-mode check and telemetry go to `api.anthropic.com` (D8). B1 turns off the documented ones (env plus settings); anything undocumented is P23's egress policy, not the broker's. The WebFetch *tool* fetches arbitrary URLs: that is network egress and has nothing to do with provider access.
- **X3: loopback reach [UNK].** The CLI needs a TCP URL (D1). The execution has no capability (`isolation.py:67`). Whether an AppContainer process can connect to a specific loopback port, and by which mechanism (a capability, a loopback exemption, or something else), is unverified, and every option is a native/P23 decision. B1 is inert until that is answered. Owner Q2.
- **X4: `apiKeyHelper` or `ANTHROPIC_API_KEY` [DOC].** The helper runs a shell command (D4), and the API key may need interactive approval (D3). Both are excluded; B1 relies on `ANTHROPIC_AUTH_TOKEN` alone.
- **X5: body rewriting [DOC].** Any rewrite (model substitution, redaction, injecting system text) breaks header/body pairing and preserved thinking (D6). B1 refuses rather than rewrites, so a subagent or setting that names another model gets `403`. That failure is visible, not silent. Owner Q3.
- **X6: Bedrock/Vertex/Foundry formats [DOC].** Each needs its own variables and endpoints (G2). Out of B1; each would be a separate card.
- **X7: `failover.py` reuse [CODE].** It forwards every path and gives the client the upstream key (`failover.py:249-267`, `config.py:1421-1422`). It is reusable only for its Host/browser checks and SSE relay technique, never as the broker.

## 6. Dependencies outside the broker

- **T-053 (origin):** possession of `brk_` is not origin. A process that obtains the value can spend the execution's ceiling until revoke; that is bounded, not prevented. The broker grants no §3.6 authority to anyone, and it does not need attestation for that reason only. Whether the broker port must also be unreachable to non-execution processes is T-053's to decide.
- **P23 (network):** loopback reach (X3) and all non-provider egress.
- **A4:** the harness must launch inside the PV-20 identity; B1 adds nothing there.
- **ADR-0021 terms:** `headless: permitted` remains a precondition of every broker request.
- **K1/T-048:** no relation. Git never crosses the broker; the execution has no push (ADR-0053 R4a/A5).

## 7. Unknowns, unverified [UNK]

1. AppContainer → loopback TCP reach and its mechanism (X3).
2. The installed CLI's version, and whether every D-fact holds for it (no version call made).
3. Whether headless `-p` sends any other startup request to the base URL besides D1/D2, or bypasses it in ways not in D8.
4. Whether `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` covers every non-provider host for this version.
5. Subscription OAuth injection (X1): undocumented, not attempted.
6. SSE relay latency and the idle timeout under the broker's ceilings.
7. Whether `x-claude-code-session-id` matches the execution's recorded session (it is a client claim; use it only as a correlation hint, never as authority).

## 8. Smallest separate cards (none authorised here)

1. **BR-1, credential row (fake only).** `ids.py` adds the `brk` prefix; the Execution gets `broker_token_hash`; mint, store and clear follow the hook-token pattern on every end path; a test that `api/auth.bearer` refuses `brk_`.
   - Files: `ids.py`, `entities.py` (+ migration), `executions.py`, `manager.py`, unit tests.
2. **BR-2, broker listener (fakes plus pytest-owned loopback sockets).** A new `archeus/node/broker.py` (or `core/` beside the API) holding everything in §4, against a fake upstream on a pytest-owned port.
   - Tests: path allowlist, `CONNECT`/absolute-URI refusal, credential map, revoke mid-stream, header strip and inject, byte-identical body, unbuffered SSE with pings, error body pass-through, model mismatch, ceilings, redaction (no secret in logs or audit).
   - Needs an explicit owner grant for local sockets in tests.
3. **BR-3, env and settings wiring (fake only).** The three env names in `_isolated_env`'s pinned table, `skipWebFetchPreflight` in `adapter._settings`, refusal of a `subscription_oauth` route for isolated executions. Production switches stay off.
4. **P23/native loopback evidence (owner-gated).** Can an AppContainer process with the minimum grant reach one specific loopback port and nothing else? This is not a broker card.
5. **BR-4, real-run evidence (owner-gated, provider calls).** The production CLI through the broker, first under the ordinary identity with an `api_key` test account, then isolated after card 4.
   - Records every host contacted, all requests, and that no secret reached the execution's env or files.
   - Its failure goes to an R3-A owner decision, never a fallback.

## Owner questions

1. **Which account kinds may the broker serve?**
   - **A (recommended):** `api_key` and `provider_proxy` only. An isolated execution routed to a `subscription_oauth` account is refused before spawn (X1), so subscription-only users can't run isolated Claude executions yet.
   - **B:** investigate server-side subscription OAuth injection. It is undocumented, puts the login in a Core forwarder and interacts with ADR-0021, so it would itself need a security decision.
2. **Where is loopback reach decided?**
   - **A (recommended):** route X3 to a P23/native evidence card (card 4) before BR-2 code. No capability or exemption is granted implicitly.
   - **B:** build BR-1 to BR-3 first while reach stays unknown. That is cheap, but it leaves the code inert, and nothing may run on the assumption that reach exists.
3. **What happens when a request names a model other than the routed one?**
   - **A (recommended):** refuse with `403`. No rewrite is possible (D6), so a subagent pinned to another model fails visibly.
   - **B:** allow any model the account serves within the same ceilings. This loosens the route decision's authority over what runs.
