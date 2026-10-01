# Archeus V1 — Orchestration capability: availability, harnesses, control and delivery plan

Status: **PROPOSED — awaiting the user's approval; nothing here is implemented, and no code,
Core/API or UI change was made to produce it.** Written 2026-09-30 on
`archeus-v1-rearchitecture` at `04eabe9` (the travelling marker; P19.5 paused after it at the
user's direction). P18 remains open.

This document is the second orchestration pass. The first,
[ARCHEUS_V1_ORCHESTRATION_RECONCILIATION.md](ARCHEUS_V1_ORCHESTRATION_RECONCILIATION.md) with
ADR-0031…0035 (commit `687aaaf`, approved by the user), already decided the catalogue, the
evidence classes, evidence in routing, artifact hand-off and data class. **Everything it decided
stands and is referenced here, not restated.** This pass answers what the user's directive of
2026-09-30 (second) adds: **availability that is real** (the pi defect), **a harness contract
the orchestration can rely on**, **the four control modes**, **model evaluation**, **architecture
that binds implementation**, **degraded and offline behaviour**, **the UI architecture**, and
**the delivery plan**. Five new ADRs are proposed (ADR-0036…0040, all PROPOSED).

A third pass, [ARCHEUS_V1_CONVERSATIONAL_ORCHESTRATION.md](ARCHEUS_V1_CONVERSATIONAL_ORCHESTRATION.md)
(ADR-0041…0043, DECIDED in the user's decision pass of 2026-09-30, with ADR-0044 for the
application theme), adds conversational directives, live-work visibility and account consumption
policy; it continues this document's decision (D-13…) and conflict (C-30…) ids. That pass also
adds slice **AP-1** (account protection) and binds ADR-0021's `rotation` answer to it. This
document's own D-1…D-12 and ADR-0036…0040 remain PROPOSED.

Method: the V1 and legacy code was read at source for availability, harness, policy, economy,
evidence and evaluation (file:line below; the pi root cause and every claim marked *verified* was
re-read first-hand); pi v0.85.1 was run read-only on this machine (`pi --version`,
`pi --list-models`); `rahatarch/brud`, `badlogic/pi-mono`, `diegosouzapw/OmniRoute` and
`olsenbrands/fable-foreman` were cloned read-only and re-inspected. Fetched content was treated
as data.

## Contents

- Part A — What exists (report items 1–10)
- Part B — References (items 11–16)
- Part C — Proposed architecture (items 17–29)
- Part D — Delivery (items 30–36)
- Appendix — conflicts added (C-22…C-29), and the directive's sections traced

---

## Part A — What exists

### A1. Model/provider architecture (item 1)

The hierarchy is **harness → account → model offer → model** (resource-router §1; reconciliation
§8). A *provider* is a property of an offer and of an account's `auth_kind`, never a fifth routing
object (domain-model §1.7). As built:

- An offer is `ModelInfo{id, tier, context_window}` inside `Capabilities.models`
  (`archeus/harnesses/base.py:47-65`), computed **live by the adapter at snapshot time** — there
  are no offer rows. `Model`/`ModelOffer` entities exist and are unused
  (`archeus/core/domain/entities.py:1305-1322`); ADR-0031 moves the catalogue into Core in P22.
- Claude Code offers: four family aliases plus the newest id per family from the legacy roster,
  **the same list for every account** (`archeus/harnesses/calls.py:148-158`, *verified*) — the
  moving-alias defect C-20, already assigned to P22.
- pi offers: see A3.
- No Codex adapter exists yet (named in comments only, `calls.py:6`); it is a V1 release
  requirement (plan §31.2).

### A2. Harness architecture (item 2)

The adapter contract was frozen in P1 (execution-architecture §3): `discover`, `capabilities`,
`authenticate`, `start`, `send`, `pause`, `resume`, `stop`, `inspect`, `status`,
`collect_result`, and `call()` on adapters declaring `headless` (ADR-0022). As built
(`base.py:39-65`, `:166-199`):

| Concern | Exists as |
|---|---|
| what it can do | `Capabilities.capabilities` ⊆ {`code_edit`, `shell`, `web`, `mcp`, `headless`, `interactive`, `resume`, `structured_output`, `long_context`, `vision`} (`entities.py:813`) |
| permissions | `enforcement` ∈ {`hook`, `sandbox`, `none`} — capability removal is primary (ADR-0007) |
| streaming | the frozen process I/O contract: Core tails `stream.jsonl` (execution-architecture §3.1) |
| cancellation | `stop()` = tree kill; `pause()` cooperative only (`claude_code/adapter.py:149,172`) |
| result | `ExecutionResult{exit_reason, exit_code, reported_summary, usage, session_ref, transcript_path, files_changed, failure, halted, adapter_state}` (`base.py:166-180`) |
| version | `HarnessInfo.version` — **always `None` on every real adapter** (`calls.py:57`, `claude_code/adapter.py:84`, *verified*) |

Adapters: `ClaudeCodeAdapter` (tool-using execution, hook), `ClaudeCodeCaller` and `PiCaller`
(own calls), `ClaudeCodeSessions` and `PiSessions` (the user's interactive sessions), `FakeHarness`
/ `FakeCaller`. **pi has no tool-using execution adapter**: execution-architecture §3 marks it
DEFERRED, and plan §31.2 lists "pi/generic-CLI adapters" as deferred past V1. The Harness
*entity* is never instantiated and `harness.state_changed` is registered but never emitted
(`events.py:129`, *verified*); "installed" is a live `discover()` in each snapshot
(`archeus/core/application/resources.py:190-197`).

Core never branches on a harness id in routing: the only two literals are legacy seams — the
own-call preference import (`archeus/core/ports.py:205`) and the Claude usage poller
(`archeus/core/routing/usage.py:60`) (*verified*).

### A3. Why pi shows models that are not executable (item 3) — **defect C-22**

*Verified at source.* V1's `pi_models()` (`archeus/harnesses/calls.py:161-172`) merges two
sources and filters neither:

1. `pi.catalogue()` (`claude_sessions/pi.py:424-479`) — every JSON file under pi-ai's shipped
   `dist/providers/data/`: **1,354 models from 39 providers**, whether or not any is configured.
2. `pi.models(home)` (`pi.py:323-343`) — ids pi has run here (`model_change` entries, with the
   `provider` field discarded at `pi.py:336-338`) plus ids declared in `models.json`.

On this machine that is **1,356 offers**. pi itself says **one** model is runnable:
`pi --list-models` prints only `spark  qwen3.8-flash-next`. pi keeps two lists —
`ModelRegistry.getAll()` and `getAvailable()`, the latter filtered to providers whose auth
resolves (`pi-coding-agent/dist/core/model-registry.js:18-23`, `model-runtime.js:171-191`;
upstream `packages/coding-agent/src/core/model-runtime.ts:325-361`) — and both `--list-models`
and its `/model` picker use `getAvailable()`. The Archeus code avoids pi's answer deliberately,
on the comment that `--list-models` "needs the provider to be logged in" and would not cover a
custom provider (`pi.py:327-331`); for a `models.json` provider with an `apiKey` that is wrong —
pi lists it.

The excess then flows everywhere, unfiltered:

- `PiCaller.capabilities` and `PiSessions.capabilities` pass the list through
  (`calls.py:114-116`, `sessions.py:217-220`); `PiCaller.authenticate` only checks that the home
  directory exists (`calls.py:118-121`);
- the router's snapshot and `/v1/harnesses` copy every offer (`resources.py:179-197`,
  `archeus/api/routes.py:956`);
- the SPA's Control → Resources table joins all 1,356 ids into "Models it offers"
  (`clients/app/src/surfaces/Control.tsx:247`, *verified*);
- the router's model step treats every entry as a valid offer (`router.py:141-160`, *verified*);
- the legacy GUI's launch modal shows the 1,354 under "ships with this CLI"
  (`claude_sessions/web/app.js:7798-7815`; `gui_api.py:4405-4462`), and legacy `pi.auth_state`
  reports pi "missing" because `auth.json` is `{}` while pi works through `models.json`
  (`pi.py:482-499`).

Two further facts about the local model: its offer id is the bare `qwen3.8-flash-next` while
every catalogue id is `provider/id` (`pi.py:465`) — whether pi resolves the bare id was **not
verified**; and its declared context window (262,144) is lost because `_declared_models` keeps
only the id (`pi.py:346-365`), so the offer has `context_window: None`.

**Where the distinction is lost:** at `calls.py:167-168`, which treats "a model pi's package
knows" as "a model this account offers". Nothing anywhere separates *catalogued* from
*configured*, and nothing checks an endpoint.

### A4. The distinction the directive asks for (item 4)

Proposed precisely in C3 (ADR-0036). In one line: **catalogued** = a Model row exists;
**configured** = an account on a harness has a provider configuration for it; **available** = its
credentials, endpoint and quota are currently good, per offer; **executable** = the router would
elect it for a given subject — computed by the router, never stored.

### A5. The local-model path (item 5)

`~/.pi/agent/models.json` declares provider `spark` (`baseUrl http://192.168.1.113:8888/v1`,
`api: openai-completions`, an `apiKey`), model `qwen3.8-flash-next` (context 262,144, max 32,768).
The endpoint is on the user's **LAN**, not on this machine. In V1 it can serve:

| Use | Works today? | Why |
|---|---|---|
| the user's own interactive pi session | yes | `PiSessions` |
| Archeus own calls with no tier requirement | yes, by preference | `PiCaller`; the offer is first because run ids are listed first |
| the planner call | **no** | `CALL_TIERS = {'planner': 'large'}` (`archeus/core/calls.py:44`) and pi offers `tier: None` = smallest (`router.py:82-84`) |
| tool-using task execution | **no** | no pi execution adapter (DEFERRED); `enforcement: none` is eligible only when every action class is ALLOW (ADR-0007) |
| any use with a context requirement | **no** | the declared window is dropped (A3) |

Nothing health-checks the endpoint (no probe in Archeus or legacy; pi checks credentials only).
**So Archeus does not today "work when only the local model exists"**: it cannot plan or execute.

### A6. The remote-model path (item 6)

Claude Code accounts (subscription OAuth or API key) through `ClaudeCodeAdapter` (execution, hook
enforcement) and `ClaudeCodeCaller` (own calls). Availability is the account-health machine
(state-machines §9): UNVERIFIED → AVAILABLE / UNAUTHENTICATED; CONSTRAINED; LIMITED (on a limit
event, `executions.py:603-612`); DEGRADED → OPEN by the breaker (5 resource/auth failures in
600 s, `executions.py:615-648`); DISABLED. As built, `auth_ok`/`auth_failed` fire only at
registration and enable (`resources.py:74,88`) — there is no periodic probe — and `near_ceiling`
is computed by the router from the snapshot rather than fired (`router.py:256`). Provider terms
(ADR-0021, OPEN) gate every real headless call. Remote models through other providers exist only
in legacy (OmniRoute, A8).

### A7. Routing infrastructure (item 7)

The pure, replayable router (ADR-0005; `archeus/core/routing/router.py`): STEPS installed →
headless → capability → model → enforcement → provider_terms → restriction → health → allocation
→ election, each elimination recorded with step and reason in an immutable RouteDecision
(`router.py:327`; `resources.py:361-378`); `fallback_or_block` with account `fallback`
`allow|ask|deny` (default `ask`) and a `route` Approval (`resources.py:437-479`); `unblock_at` from
the eliminated candidates' resets; `archeus route why`. Reconciliation §4, §13 and ADR-0033 give
the full inventory and the decided extensions; nothing here changes the router's nature.

### A8. Economy / Free routing (item 8) — legacy only

*From the legacy code; none of it exists in `archeus/`* (`grep omniroute|failover|provider_env`
finds nothing; `AUTH_KINDS` has `provider_proxy`, unused — `entities.py:1240`):

- **Economy** is two things: the `extract_model` (`claude-haiku-4-5`) used for Archeus's own
  memory and generation calls (`claude_sessions/config.py:188-190`, `memory.py:358`); and
  launch economy — thinking cap, subagent model, `--fallback-model` (`config.py:205-217`,
  `:1107-1110`).
- **Free execution** routes only the *execute* half of Plan → Execute to the active provider
  profile (OmniRoute; `auto/coding` by default), while planning stays on Anthropic `plan_model`
  (`plan_execute.py:554-563`, `config.py:185-187`, `omniroute.py:49`); the council runs on
  `auto/best-*` (`plan_execute.py:306,597-601`). Health: daemon/gateway/catalogue checks
  (`omniroute.py:52-120`), a per-provider circuit CLOSED/HALF_OPEN/OPEN (`:173-196`), failure
  classes gone/limited/auth/timeout (`:279-294`), a dead/alive cache from live turns (`:386-404`),
  per-model live probes (`:407-420`), and a failover proxy that swaps the model on a turn that
  failed before any byte (`failover.py:1-17`).

In V1 terms: Economy is already expressible — own-call tiers (`CALL_TIERS`) and the own-call
preference (ADR-0022). Free execution is the V1.x-O4 provider-proxy account with the
`opaque_router` provenance rule (reconciliation §20, C-18; ADR-0031 §7).

### A9. Agent/orchestration capabilities (item 9)

The mission loop *is* the orchestrator (reconciliation §1, §14): planner own call (large) →
versioned plan approved per policy → task DAG on routed resources sized by blast radius → Core
verification → independent review routed away from the executing accounts → bounded retry /
replan / escalation to the human. Checkpoint hand-off by Core-derived artifact. Claude Code
subagents are harness-internal and invisible to Core (C-16).

### A10. Memory/evidence capabilities (item 10)

- Knowledge types FACT, DECISION, LESSON, PREFERENCE, STANDARD, ARCHITECTURE, REFERENCE, ENTITY
  (`entities.py:406-407`); lifecycle CANDIDATE → CONFIRMED / RETRACTED / SUPERSEDED / EXPIRED;
  lessons confirm at 2 distinct missions, model confidence ignored (`knowledge.py:24,355-360`).
- Per-execution record: `harness_id, account_id, model, effort, exit_reason, exit_code, usage,
  stop_reason, failure, started_at, ended_at, pressure, attempt` (`entities.py:914-956`) —
  duration derivable, not stored; `UsageLedger` with tokens and `cost_usd` per decision
  (`entities.py:1391-1411`).
- Verification `performed_by {harness_id, account_id, model, effort, route_decision_id,
  session_id}` (`verification.py:79-85`) and `provenance {routed_model, reported_model, match}`
  (`evidence.py:139-143`) — stored, never acted on (`worker.py:194-205`).
- Evaluation: **none**. The judge (`tests/v1/judge`) runs acceptance scenarios against the fake
  harness and a recorded brain; `tools/verify_model_routing.py` audits transcripts after the
  fact; legacy `omniroute.probe_models` is a one-request-per-model liveness probe.

---

## Part B — References (items 11–16)

The full audit is reconciliation §6, §7, §33 (re-inspected at source on 2026-09-30). This pass
re-inspected four sources for **availability, harness contracts and evaluation**, the angles the
first pass did not cover:

| Source | Idea | Archeus applicability | Verdict | Reason |
|---|---|---|---|---|
| **BRUD** (item 11) `rahatarch/brud`, latest commit 2026-09-30 (v0.1.3 in code; newest release v0.1.2) | manual paste-and-apply; no model calls (no `fetch`/`apiKey` anywhere in `packages/`, `apps/vscode/`); 20 operation kinds + `GET_TOOL_INFO`; per-session history/revert; regex blocklist (`packages/core/src/api/index.ts:104`); **new since the first pass:** a workspace-boundary toggle and per-tool allow-list (`file-operations/index.ts:107,218`), versioned "My Prompts", sequential/parallel/conditional terminal command groups (`terminal/executor.ts:49,303,335`) | per-tool allow-list = capability removal, which Archeus already enforces in Core; command groups = Core-owned execution | **REJECT** (verdict of reconciliation §7 unchanged) | orchestration, routing, delegation, multi-agent, evaluation, memory: not found; nothing new is stronger than what Archeus has |
| **OmniRoute** (item 12) | per-field catalogue precedence (kept, ADR-0031); **health vocabulary**: provider circuit CLOSED → DEGRADED → OPEN → HALF_OPEN (`src/shared/utils/circuitBreaker.ts:5-16`); model lockout with reason `quota_exhausted | rate_limit_exceeded | model_capacity | server_error | auth_error | unknown` and backoff 1-2-5-10-20 min (`open-sse/services/accountFallback.ts:137-152`, `open-sse/config/constants.ts:232-244`); model status `healthy | degraded | error | locked | idle` (`src/lib/monitoring/providerHealthMatrix.ts:12-13,309-319`) | per-offer availability **with a reason**, and *idle = no evidence yet*, not failure | **ADAPT** (reason vocabulary, idle ≠ broken) / REJECT (its weighted Auto-Combo, already rejected) | a reason is what makes an unavailable offer explainable |
| **fable-foreman** (item 13) | **"signed in is not usable"** (`skills/fable-foreman/SKILL.md:49`): a free probe (installed? signed in?) and a *consented, billable* one-token ping; verdicts LIVE, SIGNED_IN (capacity unproven), SIGNED_OUT, ENV_MISMATCH, BALANCE_EXHAUSTED, AUTH_FAILED, RATE_LIMITED, KEY_REJECTED, NO_KEY, DISABLED, NOT_INSTALLED, FAILED (`scripts/access-check.sh:13-15`); only LIVE/REACHABLE are routed (`routing-card.py:68`) | the ladder of C3: configured ≠ credentialed ≠ reachable ≠ proven; an inference probe spends money and needs consent | **KEEP** | the closest precedent for real availability |
| **Claude Code / code-review** (item 14) | subagent model resolution and hooks (C-16); per-step tier choice with a validator per finding | harness-internal delegation stays invisible; the critic step (ADR-0034) | KEEP (already adopted) | nothing new for availability |
| **claude-mem** (item 15) | compression on a configurable cheap model | summarisation as a small-tier task family | KEEP (already adopted) | — |
| **Cognee / Aider** (item 16) | Cognee valid-time, `unmapped`; Aider architect/editor split, repo-map budget, the leaderboard record | the leaderboard record is **the shape of an evaluation result row** (C9); architect/editor = architecture task → implementation tasks (C8) | ADAPT (as recorded in reconciliation §33) | — |
| **pi coding agent** `badlogic/pi-mono` | `getAll()` vs `getAvailable()`; local servers need a (dummy) key to be *available* (`docs/models.md:43-64,146`); llama.cpp router lists only loaded models (`docs/llama-cpp.md`) | **the harness's own availability answer is authoritative for "configured"** (C3) | **KEEP** | the fix for C-22 is to ask pi, not to re-derive it |

---

## Part C — Proposed architecture (items 17–29)

The design rule for everything below (the directive's §28): **extend the router, policy,
mission loop, catalogue, knowledge, verification and artifacts; add no parallel orchestrator.**
The separation the directive asks for (§2) maps onto existing homes:

| Concept | Home | New? |
|---|---|---|
| A. Model | `Model` row (ADR-0031) | P22 |
| B. Provider | a property of `Model` and of an account's `auth_kind` | no (reconciliation §8) |
| C. Harness | `Harness` + adapter contract + descriptor (C2) | descriptor fields |
| D. Agent role | derived from task `kind`/`task_family` and the routing subject (ADR-0034 §3) | no |
| E. Capability | harness capabilities (declared) + model facts (catalogue) + claims (knowledge) | no |
| F. Routing policy | ResourcePolicy + named routing rules (ADR-0033), P9 policy | no |
| G. Execution | Execution / Session / process contract | no |
| H. Verification | Verification / Review | no |
| I. Memory | knowledge + OBSERVED query (ADR-0032) | no |
| J. Catalogue | `Model`/`ModelOffer` with provenance, routing status **and availability** (C3) | availability |

### C1. Model registry (item 17)

As decided in ADR-0031 and reconciliation §8–§9, with three additions proposed here:

1. **Offers only for configured providers** (ADR-0036 §2): a `ModelOffer` exists only where an
   account can address the model; a catalogue row with no offer is shown as catalogued, never as
   something an account "offers".
2. **A harness-shipped catalogue rung** (decision D-6): the model tables a harness installs with
   itself (pi-ai's `providers/data/*.json`) are a DECLARED source between provider docs and an
   aggregator. It needs no new outbound host, and it updates when the harness upgrades — which
   gives release awareness for pi's 39 providers for free (C11).
3. **Location refined** (decision D-5): `location` ∈ `this_node | self_hosted | remote` instead of
   `local | remote`. The user's model runs on a LAN server: "local" for data class
   (`local_only`, ADR-0035) must mean *on infrastructure the user controls*, and the UI must not
   call a LAN server "this machine". `self_hosted` offers default to `price: 0` (user-declared,
   dated).

The directive's field list (§4) maps to: provider, `model_id`/`revision`, display name, release
and deprecation dates, context window, max output, tool use, structured output, efforts, modalities
(vision) and price — **catalogue facts** with a per-field source rung; speed and cost *as
measured* — **OBSERVED** from the ledger and durations (P10 D15: a key only once measured);
supported harnesses — the offers; availability, health and last verified — **ADR-0036 state on
the offer**; first seen — the ingestion event; strengths/weaknesses and limitations —
**claims** (ADR-0032), never catalogue columns. Benchmark numbers enter only as dated REFERENCE
claims about their own family (reconciliation §10.5). **No field is a capability score.**

### C2. Harness abstraction (item 18) — ADR-0037

The P1 contract already is the harness interface the directive describes; what is missing is a
**descriptor the orchestration can read instead of assuming**:

| Directive's item | Contract today | Proposed |
|---|---|---|
| execute task | `start()` / `collect_result()` | — |
| repository / filesystem access | `code_edit`; workdir rules (execution-architecture §2) | split `fs_read` / `code_edit` in the capability vocabulary |
| terminal | `shell` | — (renamed nowhere; `shell` is the term) |
| browser | not declared | add `browser` (declared only when the harness drives a browser, not `web` fetch) |
| tool invocation, MCP | `mcp`, action classes | — |
| patch application | the harness edits files; Core merges the verified worktree | stays Core's: a harness never applies a patch to the user's tree (ADR-0007) |
| structured output | `structured_output` native/prompted | — |
| streaming | `stream.jsonl` contract | — |
| cancellation | `stop()`, cooperative `pause()` | declare `pause: cooperative | none` |
| sandboxing, permissions | `enforcement` hook/sandbox/none | — |
| artifact collection | `collect_result()` | producer record P21 (ADR-0034) |
| verification hooks | — | **deliberately not a harness capability**: verification is Core's, independent of the executor |
| — | (implicit: which class implements what) | **`serves` ⊆ {`archeus_call`, `task`, `review`, `session`}**: the subjects the harness can run, declared, so "pi can plan but not execute" is a fact the router and the UI read |
| — | `version` always `None` | `installed_version` populated by `discover()`; the Harness row and `harness.state_changed` actually written (P22) |

Rules: orchestration code **never branches on a harness id** (a gate over `archeus/core/routing`,
`application`, `planning`; the two legacy seams in A2 are named exceptions until P22 retires
them). A new harness is a new adapter plus its descriptor, nothing else. Claude Code is one
implementation; pi another; the fake a third.

### C3. Availability and health (items 4, 12, 20) — ADR-0036

**Two independent axes, never merged:**

- **Routing status** (ADR-0031, trust): CATALOGUED → EVALUATING → APPROVED; RETIRED — *may Archeus
  route real work to this model at all?* The user decides.
- **Availability** (this ADR, operation): *can this offer run right now, and if not, why?* The
  world decides.

**The ladder** — each rung is a fact that already exists or is one probe; the offer's state is the
**first rung that fails**, with its reason and `since`:

| Rung | Question | Signal (existing unless marked) | Fails as |
|---|---|---|---|
| 1 catalogued | does a Model row exist? | catalogue ingestion (P22) | (not an offer) |
| 2 configured | does an account on a harness address this model's provider? | pi: its own `getAvailable()` — `pi --list-models`, cached by harness version and `models.json`/`auth.json` mtime (C-22 fix); Claude Code / Codex: a registered account; proxy: its `/v1/models` | **NOT_CONFIGURED** |
| 3 enabled | is the account enabled and the model not forbidden? | account DISABLED; mission/project `forbidden_*` | **DISABLED** |
| 4 harness | is the harness installed and correctly configured, and does it serve this subject? | `discover()`; descriptor `serves` (C2) | **HARNESS_UNSUPPORTED** |
| 5 credentials | are credentials valid? | account health UNVERIFIED / UNAUTHENTICATED | **AUTH_REQUIRED** |
| 6 reachable | does the endpoint answer, without inference? | account health DEGRADED/OPEN (breaker); **new:** a no-inference probe of a self-hosted `baseUrl` (`GET {baseUrl}/models`) | **HEALTH_CHECK_FAILED** |
| 7 capacity | is there quota? | LIMITED with `limited_until`; allocation | **UNAVAILABLE** (with `until`) |
| 8 proven | has it actually served a request? | the last SERVED/BILLED record (P21), or a consented probe | not a failure — `AVAILABLE (unproven)` vs `AVAILABLE (served <date>)` |

**CAPABILITY_UNSUPPORTED** is not an offer state: it is *subject-relative* (this offer lacks tool
use / the context / the tier this subject needs) and is exactly the router's `capability` and
`model` eliminations. Likewise **EXECUTABLE** is never stored: it is "the router, run in preview
for subject S, would not eliminate this offer" — the existing route preview (ui-architecture
§4.6). "Signed in is not usable" (fable-foreman) is rung 8's qualifier; "idle ≠ broken"
(OmniRoute) is why unproven is not a failure.

**One derivation, two readers.** `offer_state(offer, snapshot) → {state, reason, since, until?}`
is a pure function of the snapshot the router already takes; the router's `installed`, `health`
and `model` steps call it, and the read API returns its output. The UI renders the state and the
reason and never computes one — so the UI cannot present an offer the router would refuse. A
parity test holds them equal.

**Probes** (decision D-7): rung 6 for self-hosted endpoints is automatic, cheap and
no-inference (only user-configured URLs, GET only, no redirects, short timeout — C12); the
account auth probe gains a periodic run (today it fires only at registration). An **inference**
probe (rung 8) costs tokens: automatic only for `price: 0` self-hosted offers; for metered offers
only by the user's action or inside an approved evaluation mission (C9). Never a share of real
work.

### C4. Routing architecture (item 21)

The router stays ADR-0005 as extended by ADR-0033 — pure, replayable, policy-first, no score.
This pass adds only:

1. The availability derivation above feeds the existing steps (one source).
2. **Material substitution asks** (ADR-0038 §3): a fallback candidate that differs from the
   original selection in **provider, location, or a lower tier** is treated as `fallback: ask`
   even where the account says `allow` — "do not silently substitute a materially different
   capability" (directive §14). Same-provider, same-location, same-or-higher-tier fallback keeps
   today's `allow` behaviour.
3. **The routing trace** (item 16 of the directive) is the RouteDecision, plus the *provenance of
   the requirements*: each requirement records where it came from (`task_family` planner-proposed
   vs derived; `min_model_tier` from blast radius; data class from the project) — a P21 field.
   The explanation shows "classified as" from that record; no chain of thought is stored,
   because none is needed: every line is a recorded fact (resource-router §8).

The directive's decision list (§1) maps: *needs architecture first?* — the planner's plan shape,
validated by Core (C5); *which model for architecture / implementation / review?* — one routing
decision per subject; *same model for several stages?* — allowed, only review independence
constrains it (`reviewer.py:94-107`); *is a cheaper model sufficient?* — tier by blast radius,
then evidence under a rule (ADR-0033); *when to ask the human / delegate / verify / retry /
switch / stop* — the existing edges (reconciliation §14.1, §18), with material substitution (2)
and bounded escalation (ADR-0033 §7).

### C5. Architecture → implementation → verification (item 22) — ADR-0040

Reconciliation §14.1 already expresses the workflow in existing objects (planner → architecture
task producing an `architecture` artifact → implementation tasks naming it in `inputs[]` →
deterministic verification → independent review → mission verification). What the directive adds
is that **architecture binds implementation**:

1. **The consumed architecture is fixed.** A task that names an `architecture` artifact in
   `inputs[]` names it at a revision (ADR-0034 §2); its contract carries `conforms_to`.
2. **Deviation is declared, never silent.** The implementer reports any departure as a
   `DEVIATION:` line (the mechanism `DECISION:` lines already use for checkpoints) — recorded on
   the checkpoint, surfaced to the reviewer.
3. **The reviewer compares four things.** The review package (ADR-0034 §4) is the user's verbatim
   request, the architecture artifact, the diff and the verification evidence; the verdict states
   conformance, and an undeclared deviation is `changes_requested`.
4. **Changing the architecture is a plan-level act.** Only a replan produces a new architecture
   artifact revision; the new PlanVersion goes through P9 plan approval under the autonomy
   profile (decision D-10). An implementer cannot amend the architecture it consumes.
5. **Task-first decision:** whether a mission starts with an architecture task is the planner's
   proposal (by blast radius, as superpowers and fable-foreman do), validated by Core; the user can
   require it per project (a mission-template preference) — never a model's unrecorded choice.

### C6. Model evaluation (item 23) — ADR-0039

- **An evaluation suite** is versioned, repository-held data: a set of frozen task contracts over
  **fixture repositories** (the existing `FixtureRepo` fixtures, not user code), each with a
  `task_family` and a deterministic verifier; the suite's verifiers must be mutation-verified
  before any result is admitted (R5; testing-strategy §4).
- **An evaluation run is a mission** (kind `evaluation`), proposed by the user or an automation,
  approved like any mission because it spends quota; every case runs in an isolated worktree,
  is verified, and is **never merged**. A run includes a baseline (an APPROVED model on the same
  suite) and n repetitions (ponytail's method; reconciliation §12's shadow evaluation is the
  second form).
- **Results are the ordinary rows** — Execution with its served-model provenance, Verification,
  Review — tagged with the suite version, so the result row has Aider's leaderboard shape: pass at
  first/second attempt, well-formed output, errors by kind, exhausted context, timeouts, duration,
  cost, model revision, harness version, suite version, date.
- **Method, not class, separates them:** OBSERVED evidence gains `method: archeus_evaluation`
  beside `archeus_outcome`. Evaluation evidence is shown separately and **never counts toward the
  workspace sufficiency floor** (`n ≥ 5`, ADR-0032) that `evidence_order`/`evidence_exclude` need
  (decision D-9). It can justify, to the user, moving a model EVALUATING → APPROVED; it never
  moves it.
- Nothing is fabricated: until a suite has run, a model is "unprofiled".

### C7. Model learning / evidence (item 24)

Unchanged from ADR-0032/0033: OBSERVED is a deterministic query over Execution × Verification ×
Review × RouteDecision; INFERRED claims are `CAPABILITY` knowledge items promoted at ≥ 2 distinct
missions; grouped by (model revision, harness version, task family); annotate by default; order
or exclude only under a named rule. The directive's record list (§5) is already the row set:
task type (`task_family`), model and harness (with revision/version, P21), context class (the
ContextPackage), outcome and verification result, retries (attempt), human correction (Feedback,
`changes_requested`), duration (derivable; P21 stores it), cost (ledger), failure category
(`failure_class`, `exit_reason`). Decay: **revision-keyed staleness** in V1.x (a new revision or
harness version marks evidence stale); time half-life stays post-V1 (plan §31.2).

**Memory boundary** (directive §15): capability knowledge is **routing input only** — it is never
injected into a model's prompt (a model is not told what Archeus believes about it), and raw
execution history never becomes prompt context; the planner may receive a bounded, cited summary
of the evidence for the families in its plan, through the ContextPackage with provenance.

### C8. Release / update system (item 25)

ADR-0031 as decided (ingestion → validation → provenance → state → routing status; events
`catalog.model_released/changed/retired`, `model.state_changed`), with the harness-shipped rung
(C1.2): **a harness upgrade is a catalogue diff**. Lifecycle mapping to the directive's §6:
discovered = the ingestion event; inspected = CATALOGUED with facts; capability-tested = an
evaluation run (C6) while EVALUATING; available = the offer's ADR-0036 state; trusted for specific
roles = CONFIRMED claims per task family (ADR-0032) plus an optional `evidence_order` rule;
production candidate = APPROVED; deprecated/retired = RETIRED (rows kept). Changed ids,
deprecations, context limits and tool support are catalogue diffs; availability is refreshed by
probes (C3); every fact carries `observed_at` (last verified). **No routing changes because a
model appeared.**

### C9. Human approval boundaries (item 26) — ADR-0038

The four modes the directive names already exist; they are made explicit per orchestration act:

| Mode | Existing mechanism |
|---|---|
| **automatic** | P9 `ALLOW` / `ALLOW_WITHIN_BOUNDARY`; account `fallback: allow` (same provider, location and tier) |
| **suggested** | a **PROPOSED** object the user accepts — the brain's principal may `propose`, never `approve` (domain-model §3): a mission proposal, a PROPOSED plan, a knowledge proposal, an automation's proposal |
| **requires approval** | P9 `ASK` (plan, task, action, route Approvals; `authorization.py`, `resources.py:437-479`); `fallback: ask`; material substitution (C4) |
| **forbidden** | P9 `DENY`; the locked floor (destructive/prod; `rules.py:63-68`); `forbidden_*`; data class; `fallback: deny` |

| Orchestration act | Mode |
|---|---|
| routing a subject among eligible, same-provider offers | automatic |
| a fallback across provider, location or to a lower tier | requires approval |
| a model's routing status CATALOGUED → EVALUATING → APPROVED | the user, or a standing approval rule the user created (ADR-0031) — never Archeus |
| proposing an evaluation run, an architecture-first plan, a routing rule, a model pin | suggested |
| running an evaluation (spends quota) | requires approval (plan approval) |
| a metered inference probe | requires approval (the user's action) |
| enabling `evidence_order` / `evidence_exclude` / `escalate_on_repeated_failure` | the user only (admin scope) |
| a subject whose data class forbids the offer's provider/location | forbidden |

Before any of it, the user sees (directive §8): the plan (tasks, families, expected artifacts,
`touches[]`), and per task the route preview — harness, model, why, cost band, action classes and
required permissions, the tools derived from them — and can override by preference, pin or
forbid (reconciliation §19).

### C10. Security implications (item 27)

- No guarantee of P9, P10, P11, P13 or P15 changes. Model selection stays inside authorisation:
  a capable model gains no permission (elimination order: policy, enforcement, terms, restriction
  before any evidence).
- **Probes are a new outbound path.** Only URLs the user configured in a harness's own config
  (e.g. `models.json` `baseUrl`); GET only; no redirects; short timeout; response bodies are
  untrusted data, schema-validated, never rendered raw; credentials are the account's own and
  never leave the node or enter a decision row.
- **pi's `models.json` may hold a key in clear** (`apiKey`); Archeus reads the file only to learn
  provider names and endpoints, never copies the key (the legacy lesson: point `apiKey` at an
  environment variable).
- Evaluation runs on fixture repositories only, under ordinary policy, in isolated worktrees, never
  merged — so no user code reaches an unapproved model through an evaluation.
- A standing approval rule and an evidence rule are policy-grade objects: created only from a user
  device with the admin scope, versioned, cited.
- P24 adds the cross-phase question: "can an availability probe, a catalogue update, an
  evaluation or a material substitution send a project's content to a provider its data class
  forbids, or run without the user's approval?" — no, by construction.

### C11. Cost / economy implications (item 28)

Cost stays a constraint or a named ordering key, never a weight (ADR-0033 §4): the plan's cost
band and `max_cost_band` (exist); budgets from the ledger (V1.x); cost as a key only once
adapters report it (P10 D15). **Economy** is own-call tiers + the own-call preference (V1 already).
**Free execution** is V1.x-O4 (provider-proxy account; `opaque_router` needs guaranteed SERVED
recording). **A self-hosted model** is `price: 0` (user-declared) and becomes the natural target
of a user's "prefer free" preference for the families where its tier and evidence meet the
requirement — never preferred merely for being free, and never below the blast-radius floor.

### C12. Offline / degraded behaviour (item 29)

There is no "offline mode" to build: degradation **emerges from per-offer availability** (C3) and
the existing fallback edges, with one addition (material substitution) and one gap closed
(Attention):

| Situation | Behaviour |
|---|---|
| internet down | remote offers fail rung 6/5 (`HEALTH_CHECK_FAILED`/`AUTH_REQUIRED` as observed); self-hosted and this-node offers unaffected; the router elects among what remains |
| remote architect unavailable, local model available | the local offer is a **material substitution** (provider + location + usually tier) → an `ask` Approval "Use spark/qwen3.8-flash-next (self-hosted, declared tier small) because Account A cannot be reached?" — never silent |
| local model is not of the required tier | eliminated at `model`; BLOCKED with the reason "no offer of tier large is available" — unless the user declared the self-hosted model's tier (decision D-4) |
| credentials expired | `AUTH_REQUIRED` → the existing Attention item "log in" |
| harness unavailable | `HARNESS_UNSUPPORTED` → eliminated at `installed` |
| health check failing | `HEALTH_CHECK_FAILED` with `since`; breaker probes back (exists for accounts; per offer for self-hosted endpoints) |
| quota | `UNAVAILABLE until` → BLOCKED with `unblock_at` (exists) |
| **gap:** LIMITED / DEGRADED / OPEN accounts and resource-blocked missions have **no Attention item** today (`attention.py:39-45,73-75`, *verified*) | Attention gains them (decision D-11) |

**Local-only operation** (directive §13) therefore requires three things V1 lacks, each a
decision: offers derived from the harness's configured providers (C-22, D-2); a user-declared tier
for a self-hosted model, so the planner can run on it when the user says it is capable (D-4); and
a pi execution adapter for tool-using tasks (D-3). Without D-3, local-only Archeus can talk and
plan (with D-4) but not execute.

---

## Part D — Delivery (items 30–36)

### D1. Required Core/API changes (item 30)

| # | Existing capability | Missing | Exact data | Owner |
|---|---|---|---|---|
| K1 | pi offers from `pi_models()` | offers only for configured providers (C-22) | pi's `getAvailable()` list (via `--list-models`, cached per harness version + config mtime), ids `provider/id`, `context_window` from `models.json` | **defect fix** — D-2 (recommended: first, before P19.5 resumes) |
| K2 | `HarnessInfo.version` = None | `installed_version`; `serves`; `pause`; `browser`/`fs_read` in the vocabulary (ADR-0037) | descriptor fields | P22 (with the Harness rows) |
| K3 | none per offer | `offer_state` derivation; self-hosted reachability probe; periodic auth probe (ADR-0036) | `{state, reason, since, until?, proven_at?}` per offer; probe facts on `ModelOffer` | P22 |
| K4 | `/v1/harnesses` returns every offer | `/v1/models` (already P22) returning **catalogue rows and offers separately**, each offer with its state; `/v1/harnesses` returns offers with state, never the catalogue | read-model change only; no new write route | P22 |
| K5 | RouteDecision requirements | provenance of each requirement ("classified as") | `requirements._source` | P21 |
| K6 | fallback `allow|ask|deny` | material substitution → `ask` (ADR-0038 §3) | original selection's provider/location/tier in the decision | V1.x-O2 (before any second provider routes; own calls included) |
| K7 | Attention: approvals, UNAUTHENTICATED | LIMITED/DEGRADED/OPEN accounts; resource-blocked missions | Attention items | P21 (Health page) — D-11 |
| K8 | — | evaluation suites, `kind: evaluation` missions, `method: archeus_evaluation` (ADR-0039) | suite version on Execution/Verification | V1.x-O1 |
| K9 | architecture artifact as input (ADR-0034) | `conforms_to`, `DEVIATION:` lines, the four-way review package (ADR-0040) | contract field; checkpoint field | V1.x-O3 |
| K10 | pi own calls and sessions | pi tool-using execution adapter (RPC mode) | — | D-3 (recommended V1.x-O4) |
| K11 | `location: local|remote`; user override rung | `this_node|self_hosted|remote`; user-declared tier/facts for self-hosted models | Model fields | P22 (with the catalogue) — D-4, D-5 |

**Already owned and unchanged:** P21 provenance (`model_revision`, `served_model`, harness
version, `task_family`, `capability_snapshot`, artifact producer); P22 catalogue, routing status,
exact ids (C-20). **No endpoint is proposed beyond `/v1/models`, which P22 already owns.**

### D2. Client-only changes (item 31)

The client holds no availability logic (P19: "remove any logic that crept into clients"), so
**nothing correct can be shown before K4** — a client cannot know which pi models are configured.
Client work that follows the API:

- Control → Resources (P22, with K4): Harnesses (installed, version, serves, enforcement);
  Accounts (existing); **Models** — offers with their state word and reason, and the catalogue as
  a separate count per harness ("1,354 more in pi's catalogue — not configured"), never mixed;
  an offer inspector (facts with source rung and `observed_at`, routing status, availability,
  evaluation history, evidence classes); **Route preview** (already specified in ui-architecture
  §4.6) as the only place "executable" is shown, per subject; routing rules in force.
- The explanation card renders requirement provenance (K5) and material-substitution approvals.
- Visual DNA (ADR-0024…0028): states are **words**, never tints; no colour per model, provider or
  role (ADR-0026 §3); `AUTH_REQUIRED` is attention (the user can fix it); `NOT_CONFIGURED` and
  `unproven` are neutral (not a problem); `HEALTH_CHECK_FAILED` is red **only** when something
  depends on the offer (ADR-0028); nothing animates for an offer state (no event, no motion).
  The activity chip may carry the model label ("reviewing · claude-sonnet-5") — reconciliation
  §27. TUI parity through the same read.
- **Nothing in P19.5 changes.** No dashboard, no control-room imitation.

### D3. Required ADRs (item 32)

| ADR | Title | Status | Amends on approval |
|---|---|---|---|
| [ADR-0036](decisions/ADR-0036.md) | Availability is a per-offer state with one reason, separate from routing status; "executable" is the router's answer | PROPOSED | resource-router §2–§3, domain-model §8.3, state-machines §9 (a note), ui-architecture §4.6 |
| [ADR-0037](decisions/ADR-0037.md) | The harness descriptor declares what a harness serves; orchestration never branches on a harness id | PROPOSED | execution-architecture §3, entities `CAPABILITIES` |
| [ADR-0038](decisions/ADR-0038.md) | Four control modes for orchestration acts, all existing mechanisms; a material substitution asks | PROPOSED | resource-router §7, reconciliation §19 |
| [ADR-0039](decisions/ADR-0039.md) | Model evaluation is an approved mission over a versioned fixture suite; its evidence is kept apart | PROPOSED | ADR-0032 §2 (method list), reconciliation §12 |
| [ADR-0040](decisions/ADR-0040.md) | A consumed architecture artifact binds implementation; changing it is a plan-level act | PROPOSED | ADR-0034 (extends), domain-model §7.3 |

Not ADRs: the location refinement and user-declared tier (fields inside ADR-0031's user-override
rung — decisions D-4, D-5, recorded in ADR-0036's consequences); the harness-shipped rung (a rung
in ADR-0031's ladder — D-6); the Attention gap (a P21 item — D-11).

### D4. Required tests (item 33)

| Gate | Asserts | Mutation it must kill |
|---|---|---|
| pi offers = pi's available set | with a fixture pi home (catalogue of N, `models.json` with one keyed provider, `auth.json {}`), offers are exactly the configured provider's models, ids `provider/id`, context from `models.json`; a keyless provider follows pi's own rule | offers include the catalogue; `provider` dropped; context lost |
| catalogue ≠ offers in the read | `/v1/models` and `/v1/harnesses` never list a catalogue row as an offer | merged lists |
| one derivation | for every offer in a generated snapshot, `offer_state` and the router's eliminations agree (property test) | router and read diverge |
| no offer without a state | the SPA renders no offer without its state word and reason (unit + e2e) | state column dropped |
| material substitution | a fallback across provider/location/lower tier becomes `ask` even with `fallback: allow`; same-provider stays `allow` | rule bypassed |
| probe hygiene | probes hit only configured URLs, GET, no redirect, time out, never send a key to another host | redirect followed; arbitrary URL |
| harness-id gate | no `'claude_code'`/`'pi'`/`'codex'` literal in `archeus/core/{routing,application,planning}` outside the named legacy seams | a literal added |
| descriptor honesty | each adapter's declared `serves` and capabilities match the installed CLI's doctor/introspection | a false declaration |
| evaluation isolation | an evaluation mission never merges, runs only on fixtures, and its evidence never counts toward workspace sufficiency | counted; merged |
| architecture binding | an implementation task cannot write a new revision of its input architecture; an undeclared deviation fails review | silent amendment accepted |
| local-only | with only the self-hosted offer: own calls route to it; the planner BLOCKs with the tier reason (or runs if the user declared the tier); a remote-down fallback asks | silent substitution |

Every gate is mutation-verified in the phase that builds it (testing-strategy §4).

### D5. Phase placement (item 34)

**No new phase.** The work fits the existing structure — one defect fix now, P21/P22 foundations
(already owning the catalogue), and the V1.x-O family (already adopted, O-15):

| Item | Phase | Relationship |
|---|---|---|
| C-22 pi offer leak (K1) | **a standalone defect slice, on approval** (D-2) — small, adapter-level, no API shape change | independent of P19.5; lands before P19.5 resumes so Control → Resources stops listing 1,356 models |
| K5 requirement provenance, K7 Attention gap | **P21** (observability; Health page) | with the P21 provenance fields already assigned |
| K2 descriptor, K3 availability, K4 read split, K11 location/tier, Resources UI | **P22** (catalogue into Core, already assigned) | the availability state lives on the offer rows P22 creates |
| K8 evaluation | **V1.x-O1** (capability knowledge) | evaluation is how EVALUATING models earn evidence |
| K6 material substitution | **V1.x-O2** (evidence in routing) — or earlier if a second provider routes before it | must precede any cross-provider fallback |
| K9 architecture binding | **V1.x-O3** (hand-off contracts) | extends ADR-0034 |
| K10 pi execution adapter | **V1.x-O4** (providers) — D-3 | the local model as an executor |

Relationship to P19.5: none in either direction; the visual slices resume when the user says so.
Relationship to future orchestration work: this plan is the V1.x-O backlog's missing half
(availability, harness descriptor, evaluation, binding), slotted into the phases that already
exist.

### D6. Decisions requiring the user's approval (item 35)

| ID | Decision | Recommendation |
|---|---|---|
| D-1 | Adopt ADR-0036…0040 | approve as written |
| D-2 | When to fix C-22 (pi lists 1,356 offers, one runnable) | **now**, as a standalone defect slice before P19.5 resumes; alternative: with P22 |
| D-3 | pi tool-using execution (the local model as an executor) | **V1.x-O4**; alternatives: pull into V1 (a V1 scope change — plan §31.2 defers it), or keep post-V1 |
| D-4 | May the user declare a self-hosted model's tier and facts (ADR-0031 user-override rung, dated, recorded)? Without it the planner can never run on the local model | **yes** |
| D-5 | Location `this_node | self_hosted | remote` (the local model is on a LAN server); `local_only` data class means self-hosted | **yes** |
| D-6 | The harness-shipped catalogue (pi-ai data) as a DECLARED rung between provider docs and an aggregator | **yes** (no new outbound host) |
| D-7 | Probes: automatic no-inference reachability for self-hosted endpoints and a periodic auth probe; inference probes only for `price: 0` self-hosted offers or by user action/evaluation | **yes** |
| D-8 | "Material substitution" = different provider, different location, or lower tier than the original selection → `ask` | **yes** |
| D-9 | Evaluation evidence is shown separately and never counts toward the workspace `n ≥ 5` floor | **yes** |
| D-10 | Changing a consumed architecture only through a replan + plan approval (vs. the implementer amending with declared deviations accepted in review) | **replan + approval** |
| D-11 | Attention items for LIMITED/DEGRADED/OPEN accounts and resource-blocked missions, in P21 | **yes** |
| D-12 | Carried, unchanged: ADR-0021 provider terms (OPEN, the user's answer per harness); C-15 research-record correction (outstanding); C-20 (P22); the "DECIDED (direction set by…)" wording on ADR-0031…0035 | leave as they are unless the user says otherwise |

### D7. Implementation order once approved (item 36)

1. **C-22 defect slice** (D-2): pi offers from pi's own available set; ids `provider/id`;
   `models.json` context windows; legacy launch modal separates "configured" from "catalogue";
   `pi.auth_state` honours `models.json`. Tests of D4 row 1; one commit.
2. **P19.5 resumes** at the user's word (the activity chip is the next slice); nothing here blocks it.
3. **P21:** the already-assigned provenance fields + requirement provenance (K5) + the Attention
   gap (K7).
4. **P22:** catalogue into Core (assigned) together with the harness descriptor and rows (K2), the
   availability derivation, probes and read split (K3, K4), location and user-declared facts
   (K11), and the Resources UI (D2) — in that order, each gated.
5. **V1.x-O1:** `task_family`, the OBSERVED query, `CAPABILITY` claims, **evaluation suites** (K8).
6. **V1.x-O2:** evidence annotation and rules, **material substitution** (K6), escalation.
7. **V1.x-O3:** declared outputs, artifact inputs, critic, **architecture binding** (K9).
8. **V1.x-O4:** provider-proxy (Free execution), data class, **pi execution adapter** (K10).
9. **V1.x-O5:** skills as offers.

Stop after the architecture: nothing above starts without the user's approval of D-1…D-12.

---

## Appendix — conflicts added (continuing reconciliation §32)

| ID | Conflict | Evidence | Resolution proposed | Status |
|---|---|---|---|---|
| C-22 | **pi offers its whole shipped catalogue as available** (1,356 offers; pi says 1 is runnable) | `calls.py:161-172`; `pi.py:323-343,424-479`; `Control.tsx:247`; `pi --list-models` | offers = pi's `getAvailable()`; catalogue rows stay catalogue (ADR-0036) | **FIXED** (C-22 slice, 2026-10-01; see "C-22 as built" below) |
| C-23 | Local-only operation is impossible: the planner needs `large`, pi offers are `tier: None`; pi cannot execute | `core/calls.py:44`; `router.py:82-84`; execution-architecture §3 | user-declared tier (D-4); pi execution adapter (D-3) | PROPOSED |
| C-24 | "local" conflates this machine with the user's LAN server | `models.json` `baseUrl 192.168.1.113` | `this_node | self_hosted | remote` (D-5) | PROPOSED |
| C-25 | Harness version is never recorded, yet evidence is keyed on it (ADR-0032 §4) | `calls.py:57`; `claude_code/adapter.py:84` | `installed_version` populated (ADR-0037, P22) | PROPOSED |
| C-26 | Account auth is probed only at registration; availability goes stale silently | `resources.py:74,88` | periodic auth probe (ADR-0036, D-7) | PROPOSED |
| C-27 | `fallback: allow` can substitute a different provider/location/tier silently once a second provider exists | resource-router §7 | material substitution asks (ADR-0038, D-8) | PROPOSED |
| C-28 | Resource-starved work is invisible in Attention | `attention.py:39-45,73-75` | Attention items (D-11, P21) | PROPOSED |
| C-29 | Legacy `pi.auth_state` reports pi "missing" while `models.json` makes it work | `pi.py:482-499` | honour `models.json` providers (with C-22) | **FIXED** (with C-22) |

**C-22 as built (2026-10-01).** A defect against already-decided rules (domain-model §8.3,
ADR-0022, ADR-0031), fixed without ADR-0036, whose states stay unbuilt:

- **Discovery per home.** `claude_sessions/pi.py` `configured(home)` runs `pi --list-models` with
  `PI_CODING_AGENT_DIR` set to that home and parses pi's own table (pi prints exactly
  `getAvailable()`). Ids are `provider/model`. Context windows come from `models.json`, else the
  shipped catalogue's fact for the same id, else unknown. Results are cached per home on the pi
  executable, its version (package.json), the shim's stamp and the stamps of `models.json`,
  `auth.json` and `settings.json`; a failed answer is retried after 60 s even with nothing
  changed, a successful one lives until its key changes.
- **Failure offers nothing.** A failed run, an unrecognised table or row, no executable or no
  home is `ok: False` with its reason, and never falls back to the catalogue. pi's own
  "No models available" is an empty answer, not a failure.
- **Offers per account.** `PiCaller` and `PiSessions` answer `capabilities(account)` from that
  account's home, and `Capabilities.models_note` carries why the list is empty.
  `resources._account_offers` puts each account's own offers in the snapshot. The router's model
  step reads the candidate account's offers when present, else the harness's (so older
  RouteDecision snapshots replay unchanged). An account whose own discovery found nothing is
  eliminated at `model` with that reason. The P12 session service validates a model against the
  target account's home.
- **Catalogue stays catalogue.** `pi.catalogue()` is unchanged. The legacy launch modal lists
  "configured for this account" (`configured`, `configured_why`) apart from "run here" and
  "ships with this CLI".
- **Unchanged:** `/v1/harnesses` shape (its `models` is the default home's configured set);
  Claude offers; tiers (pi models stay tier-unknown, D-4); probes (D-7); rotation, AP-1, D-25.
- **Tests:** `tests/v1/unit/test_pi_discovery.py` and
  `tests/test_harnesses.py::test_the_launch_modal_keeps_configured_apart_from_the_catalogue`,
  18 of 18 mutants killed (M01–M18, the final run on a scratch copy; an earlier run of 16
  preceded the two cache-expiry mutants M17–M18).

**The directive's sections traced:** §1–§2 → Part C preamble; §3, §12 → A3, C3; §4 → C1; §5 →
C7; §6 → C8; §7 → C4; §8 → C9; §9 → C5; §10 → C4 (independence only); §11 → C2; §13 → A5, C12;
§14 → C12; §15 → C7; §16 → C4.3; §17 → C10; §18 → C11; §19 → C6; §20 → A1–A10; §21 → Part B;
§22 → D2; §23 → D3; §24 → D1; §25 → D5; §26–§29 → the status line and D7.
