# P10 design gate: the resource router

Status: **IMPLEMENTED (P10).** Built 2026-09-26 on the accepted P9 baseline (`6b5ceac`). The
decisions were taken inline while building rather than approved in a separate pass first, so
this document records the design and the as-built result together; §4 lists every conflict with
a frozen document and how it was resolved, §16 the decisions, §21 the deviations. Items are
marked as in the earlier gates:

- **[spec]** already specified by the V1 architecture (plan, domain model, state machines, ADRs);
- **[clar]** a clarification of an existing contract the documents leave open, or that the code
  had already settled differently;
- **[new]** a new contract decision.

Sources read, in precedence order: the plan (**§14**, §31.1 **P6–P10**, §31.4), **ADR-0005,
ADR-0006, ADR-0021, ADR-0022, ADR-0023**, resource-router **§1–§10**, domain-model **§8**,
state-machines **§5, §9**, testing-strategy **§1.1, §2 (S3, S4, S12, K1, K2)**, the P6 and P9
gates (**p6 §5**, **p9 §13, §14**), and the code: `archeus/core/{ports,engine,runtime,calls}.py`,
`core/domain/{entities,states,actions,events}.py`, `core/application/{work,authorization,calls,
commands,queries}.py`, `harnesses/{base,calls,fake,registry}.py`, `claude_sessions/usage.py`
and the judge. Where a document and the code disagreed, the code said what existed.

---

## 1. What P10 is

P9 answers *may this happen*; P10 answers *where does the authorised thing run*; P11 runs it.
The resource hierarchy is **harness → account → model**, three separate things (domain-model
§8). P10 chooses one of each for two subjects:

| Subject | What routes it | Recorded as |
|---|---|---|
| `archeus_call` | Archeus's own tool-less structured calls (knowledge, lesson, brain, planner; ADR-0022) | `RouteDecision(subject=archeus_call:<purpose>)`, usage ledgered against it |
| `task` | a task's dispatch, after P9 recorded a `covered` dispatch decision | `RouteDecision(subject=task:<id>, policy_decision_id=…)`, the Execution names it |

The spec calls the second subject `action_execution`; the domain already calls it `task`
(`Ref('task', …)`, the task's `ROUTING` state), and P10 uses the existing name [clar].

## 2. Boundaries

P10 **does**: capability and model offers, eligibility, harness/account/model/effort selection,
structured-output matching, preferences and restrictions, allocation ceilings and budgets, usage
observation and the usage ledger, provider-terms gating (both checks), fallback, continuity,
deterministic and replayable decisions, their explanation, and the read/admin routes for all of
it.

P10 **does not**: authorise or approve anything, change a policy rule, classify an action, spawn
or supervise a process, pause/stop/e-stop, hand a session off, verify, review, automate, pair a
device, or render an approval card. The execution-time halts resource-router §4 describes
(`must_halt`) and the failure-driven account moves (§7: limit errors, error storms) are P11/P12.

## 3. What already existed, and what was reused

- **Entities** [spec]: `Account`, `ResourcePolicy`, `UsageSnapshot`, `UsageLedger`,
  `RouteDecision`, `Model`/`ModelOffer` existed as P1 shapes; P10 extends them (§5) and adds no
  parallel `RoutingDecision` type.
- **Machines** [spec]: account health (state-machines §9) and the task's `ROUTING → BLOCKED:
  no_eligible_resource` / `ROUTING → AWAITING_APPROVAL: route_needs_approval`, `approved`,
  `rejected`, `unblock` already existed. **No state machine changed.**
- **Ports** [spec]: `ports.Router.route(subject, now)` gains `**context` (§9); the P1
  `FixedCandidateRouter` stays for the P3.5–P9 tests that do not route.
- **P6 own calls** [spec]: `OwnCalls.run`, `calls.end_call`, `calls.terms` (the one ADR-0021
  reader), `Capabilities.structured_output` (`native` | `prompted`) and the adapters' own
  accounts (`account(rotation=…)`) are reused unchanged; only the election is replaced.
- **P9** [spec]: the dispatch decision record (per-item decision and boundary), the approval
  machinery (`action_hash`, `live_approval`, `decide`) and its TTLs.
- **Legacy usage** [spec, plan P10 preparation seam]: the poller's cache and `_extract_windows`,
  exposed as `usage.windows_snapshot(cfgdir) -> (windows, observed_at, status)` — additive, and
  unknown is never 0% (the reason `quota.worst_window` is not used).

## 4. Conflicts with frozen documents, and their resolution

1. **Synchronous refresh (resource-router §4).** The design asks the router to refresh stale
   usage with a 3 s timeout. The router runs inside the writer's transaction, where a network
   wait would stall every command. The feed is read in memory (the legacy poller refreshes on its
   own thread); a reading older than 120 s carries the +5 penalty and its age is recorded [clar].
2. **The `policy` elimination step (resource-router §5).** It asks the policy engine resource
   questions, but P9 has no resource rules (p9 §14.1) and P10 must not become a second policy
   engine. Resource restrictions are the account's `ResourcePolicy` (`project_allow`,
   `project_deny`) and the mission's `forbidden_*`; the policy input the router does read is the
   P9 decision's per-item record, for enforcement (§6.2) [clar].
3. **`CONSTRAINED` as an ordering key.** Nothing fires `near_ceiling` yet; the ordering computes
   the same condition (`worst ≥ ceiling − 5`, state-machines §9) from the decision's own
   snapshot, so the key is replayable [clar]. The usage-driven health moves are not fired by P10.
4. **Cost and latency ordering keys.** No V1 adapter reports either; they are not keys rather
   than keys that are always equal [clar].
5. **The pre-router election (P6, ADR-0022 "until P10").** Replaced for every own call; its
   rules (user's choice, else Claude Code, else first) are gone, and no rule names a harness
   (§8) [spec].
6. **An `ask` fallback's approval (resource-router §7).** P9's approval kinds were plan, task,
   action. Consent to run on a fallback account is a fourth kind, `route` (§9.3): it covers no
   action, so the task's next dispatch is judged by P9 again [new].
7. **`UsageLedger` "execution XOR route decision" (P6).** Every row now names its
   RouteDecision; an execution's row names both (§7.4) [new].

## 5. Domain and storage — migration `0009_resources.sql`

- `accounts` (health on the `account_health` machine; `harness_id`, `auth_kind`, `node_id`
  frozen; `home_ref` opaque to Core), `resource_policies` (one per account, UNIQUE; priority,
  `allocation_pct`, `reserve_pct`, `brain_reserve_pct`, `fallback` allow | ask | deny,
  `budgets` {tokens_per_day, cost_per_day, concurrency}, `project_allow`, `project_deny`;
  reserves may not exceed the allocation), `usage_snapshots` (one window of one account, frozen
  whole, `observed_at`, `resets_at`, source `usage_api | rate_limit_headers | rollout_file |
  scripted`).
- `route_decisions` gains `mission_id`, `task_id`; `usage_ledger` gains `account_id`. Rows
  written before keep NULL there.
- `RouteDecision` (body fields): `requirements`, `input_snapshot`, `candidates` (each with
  `eliminated_at_step` and `reason`), `harness_id`, `account_id` | `account_ref`, `model`,
  `effort`, `result` (selected | fallback | ask | blocked), `fallback_from`,
  `policy_decision_id`, `unblock_at`, `explanation`, `decided_by` (`router`; `pre_router` stays
  valid for rows P6 wrote). Every field is frozen but an own call's `outcome`, written once.
- `Execution` gains `route_decision_id`, `account_id`, `model`, `effort` (the decision's choice,
  denormalised for queries). `Mission.resource_preferences` holds `preferred_accounts`,
  `preferred_harnesses`, `forbidden_accounts`, `forbidden_harnesses`, `max_cost_band`, `since`.
- `base.ModelInfo(id, tier, context_window)`: an offer in its harness's vocabulary;
  `Capabilities.models` holds ids or ModelInfo.
- Events: `account.registered`, `account_health.state_changed`, `resource_policy.updated`,
  `usage.observed` (system visibility); `route.decided` gains the result, harness, account,
  task and mission.

## 6. The router — `core/routing/router.py`

`route(req, snap)` is a pure function of two JSON values; it imports nothing and reads no clock.

### 6.1 Candidates
Every (harness, account) in the snapshot, harnesses sorted by id and accounts by id. A harness
with no registered account offers its own (`account` None, `account_ref` the adapter's; priority
after every registered account). Model and effort are resolved per candidate (§6.3).

### 6.2 Elimination — `STEPS`, in order; a candidate stops at the first it fails
| Step | Eliminates |
|---|---|
| `installed` | a harness the adapter says is not installed |
| `headless` | an own call on a harness that does not declare `headless` |
| `capability` | missing any required capability; a schema asked of a harness with neither `native` nor `prompted` structured output |
| `model` | a required model that is not an offer meeting the tier/context minimum; no offer meeting the minimum; a required effort not declared |
| `enforcement` | (task) an item P9 decided that the harness cannot enforce: `hook` enforces all, `sandbox` only `ALLOW_WITHIN_BOUNDARY` on path boundaries, `none` only `ALLOW` |
| `provider_terms` | ADR-0021 headless use not `permitted`; a second subscription account of a harness whose rotation is not `permitted` (scripted adapters exempt by class) |
| `restriction` | required/forbidden harness or account; the account's project rules |
| `health` | no account; an unregistered one the adapter cannot spend; health not AVAILABLE/CONSTRAINED (DEGRADED stays a fallback candidate); an exhausted window (≥ 100%, never a fallback) |
| `allocation` | observed `worst + projected ≥ ceiling`; no readable window and no budget; a budget reached |

A preference never touches elimination: a preferred, required or affine resource that fails a
step is eliminated like any other (capability before preference).

### 6.3 Model and effort vocabulary
`req.models` is `{harness_id: model}` — a preference in THAT harness's vocabulary, never carried
to another. It is used only when it is an offer of the candidate's harness that meets the
minimum; otherwise it is dropped (or eliminates, when `model_required`), never translated. With
a minimum and no usable preference, the smallest offer that meets it wins (the adapter's own
order within a tier). An unknown tier counts as the smallest and a minimum excludes it
(ADR-0022). Effort is kept only when the harness declares it.

### 6.4 Ordering (smallest first)
`(affinity, preferred, priority, tier rank of the chosen model, near its ceiling, resource id)`.
Affinity only reorders survivors, so continuity never overrides capability, authorisation or
allocation. `explain` names the first key that separated the winner from the runner-up.

### 6.5 Fallback
Nothing survived: among the candidates stopped only at `health` (DEGRADED) or `allocation`, in
the same order, one the user already approved for this task wins, else the first whose policy
says `allow` (`fallback`); else the first `ask` is returned as `ask` with nothing selected; else
`blocked`, with the earliest `resets_at` of the stopped candidates as `unblock_at`. The router
never answers its own `ask`.

### 6.6 Replay and explanation
`replay(decision) == route(decision.requirements, decision.input_snapshot)`. `explain` is
generated from the record (resource-router §8), never by a model.

## 7. Usage — `core/routing/usage.py`, `application/resources.py`

### 7.1 Feeds
`read(account) -> {windows {5h|7d|monthly: pct}, resets_at, observed_at, source} | None`, an
in-memory read. `LegacyUsageFeed` (Claude Code accounts with a home, through the P10 seam;
labels `session → 5h`, `weekly → 7d`; per-model weekly limits are not an account ceiling),
`FakeUsageFeed` (scripted, `source: scripted`), `NoUsageFeed`.

### 7.2 Ceiling [spec, resource-router §4]
`ceiling = allocation − reserve` for own calls, `− brain_reserve` for tasks; a task starts only
while `worst + projected(size) < ceiling`, `projected` = S 1, M 3, L 8 (size from the 1–5
estimate: 1 S, 2–3 M, 4–5 L); stale (> 120 s) +5. Allocation is a ceiling: a lower-priority
account with room is never chosen to use up its share.

### 7.3 Observation
The decision's command records every reading it was made from as `UsageSnapshot` rows (only
when the value changed, or the stored one is stale) with `usage.observed`. Without a feed
reading, the newest stored snapshot is used, with its age.

### 7.4 Ledger
`UsageLedger` always names its RouteDecision and the account (registered id, else
`account_ref`). An own call's row is written by `end_call`; an execution's by `record_exit`
from the adapter's reported usage. `ledger_totals` (tokens and cost since midnight UTC, live
executions) feeds the budget path.

## 8. Own calls — `core/calls.py`

`call_snapshot` builds the requirements (`headless`, structured output when a schema is asked,
`min_model_tier` from `CALL_TIERS` — the planner needs `large` — the user's own-call preference
as `preferred.harnesses` and `models[harness]`) and the snapshot over every own-call adapter.
The decision is committed before anything runs (P6's INTENT rule); a blocked decision ends the
call `gated` when provider terms stopped a candidate, else `unavailable` with the most specific
reason; an `ask` is never asked for an own call. ADR-0021's second check is a fresh read of the terms immediately before the
spawn. The adapter runs on the decided account (`AccountRef(id, home_ref)`) with the decided
model. Nothing in the module names a harness.

## 9. Tasks — the P9 → P10 contract

### 9.1 Only what P9 authorised routes
`Work.dispatch_task` calls the router only after P9 recorded a `covered` dispatch decision.
`current_authorization` checks it again inside the router's command: it must exist, be a
`dispatch` + `covered` decision of this task, this plan id and digest, carry no DENY in its
record, and be the task's latest dispatch decision. Otherwise `NotAuthorised`, nothing is
recorded. Routing writes no policy decision, rule or approval of its own authority.

### 9.2 Outcomes
`selected` / `fallback` → `routed`, Execution INTENT naming the decision, account, model,
effort. `blocked` → task `no_eligible_resource` and the mission `block`s with the explanation; a
resume unblocks the task and routes again. `ask` → §9.3.

### 9.3 The `route` approval [new]
The dispatch command (never the router) calls `request_route`: a PENDING approval of kind
`route` whose `action_hash` binds (task of this plan version, harness, account), found again if
asked twice; the task goes `route_needs_approval` and the mission blocks. Only a user device
decides it, through P9's `decide`: approve → task `approved` (READY), mission resumed, and the
next dispatch — judged by P9 again — finds it in `approved_fallbacks`; reject → task `rejected`
(BLOCKED). It authorises no action.

### 9.4 Continuity
Affinity is the mission's latest `selected`/`fallback` task decision, cleared by the user
setting the mission's resources (`since`).

### 9.5 Execution-side terms check
The engine reads the terms again after the decision and before `adapter.start()`; not permitted
→ the execution is reconciled and nothing is spawned (fake adapters exempt by class).

### 9.6 The auto-approve ceiling (P9 deferral)
`Mission.resource_preferences.max_cost_band` (a user device only) replaces P3.5's fixed
`medium` for that mission's plan gate.

## 10. API

| Route | Scope | |
|---|---|---|
| `GET /v1/harnesses` | observe | every adapter, what it declares, whether it executes and/or calls |
| `GET /v1/accounts` | observe | accounts with policy and latest usage |
| `POST /v1/accounts` | admin, idempotent | register; the adapter probes the login first, outside the transaction |
| `POST /v1/accounts/{id}/state` | admin, idempotent | disable / enable (re-probed) |
| `POST /v1/resource-policies/{id}` | admin, idempotent | priority, allocation, reserves, fallback, budgets, project rules |
| `POST /v1/missions/{id}/resources` | admin, idempotent | the mission's preferences and `max_cost_band` |

`GET /v1/route-decisions[/{id}]` (P6) serves both subjects; `?source=` matches the subject too.
Every resource command is a user device's; the brain and the system get 403 from the command.

## 11. Events

Four new types (§5): `account.registered`, `account_health.state_changed` (the machine's moves,
which the writer requires), `resource_policy.updated`, `usage.observed`. A decision is
`route.decided`; a mission's resources are `mission.updated`; a route approval is P9's
`approval.requested` / `approval.state_changed`.

## 12. Provider terms (ADR-0021, unchanged)

Checked twice for both subjects: as the `provider_terms` elimination step over the snapshot's
terms, and as a fresh read immediately before the adapter runs (`OwnCalls.run` for own calls,
`Engine` before `start()` for tasks). Rotation across a harness's subscription accounts needs
its own `rotation: permitted`; an API key is not rotation. Scripted adapters are exempt by
class, never by id.

## 13. Determinism and replay

The router reads only its arguments and never modifies them (B1 proves it imports nothing;
`test_the_router_reads_nothing_but_its_arguments` that its inputs come back unchanged). Candidates are sorted by id before anything else, the ordering ends
in the resource id, and the input snapshot is recorded whole, so a persisted decision replays to
itself (I-H2) and a shuffled input gives the same decision (the property tests).

## 14. History

A RouteDecision is frozen whole but for an own call's `outcome`, written once. A later decision
is a new row; the Execution and the usage rows name the decision they ran under, so a changed
account, policy or usage never rewrites why something ran where it did.

## 15. Security

- The router is pure; it cannot authorise, approve, change a policy or spawn (§18).
- A forged `covered` decision carrying a DENY, another plan's decision, a superseded one or
  another task's cannot route (§9.1).
- Capabilities are reported as the adapter declares them, never widened.
- Adapter probes never run inside a command (a side effect inside a transaction).
- Provider terms are checked at election and again at the adapter, for both subjects.
- Every resource command is a user device's; the brain and the system are refused.

## 16. Decisions

| # | Decision |
|---|---|
| D1 | One `RouteDecision` for both subjects, extended; no parallel type. |
| D2 | The router is a pure function over (requirements, snapshot); the application gathers the snapshot and records it, so every decision replays. |
| D3 | Subject `task` (the domain's name) for action execution. |
| D4 | Structured output: `native` OR `prompted` satisfies a schema; neither is required. |
| D5 | Models are per-harness offers; a preference is harness-scoped, dropped when invalid, never translated; unknown tier = smallest. |
| D6 | Allocation per resource-router §4; unknown usage is never 0% (budgets, else fallback only); an exhausted window is health, never fallback. |
| D7 | Feeds read in memory; stale readings penalised, not refreshed synchronously. |
| D8 | Enforcement reads the P9 decision's per-item record. |
| D9 | Affinity orders survivors only; cleared when the mission's resources are set. |
| D10 | `route` approval kind for `ask` fallbacks, requested by the dispatch command, decided by P9. |
| D11 | Every usage row names its RouteDecision. |
| D12 | A blocked task blocks its mission; a resume routes it again. |
| D13 | `max_cost_band` from the mission's resources (the P9 → P10 deferral). |
| D14 | A harness with no registered account offers its own, after every registered one. |
| D15 | Cost and latency are not ordering keys until an adapter reports them. |

## 17. Tests

- `tests/v1/unit/test_routing_units.py` — the pure router: U-B basic selection, U-M multi-harness
  (Claude, pi, both, neither; no harness preferred by name), U-S structured output, U-V model and
  effort vocabulary, U-A allocation, U-F fallback, U-C continuity, U-E enforcement, U-T provider
  terms (first check), U-R restrictions, U-D determinism, replay, generated-world properties
  (`test_P_properties_over_generated_worlds`: input order never changes the winner, replay is
  equal, the winner is never over its ceiling at start, never eliminated), explanation.
- `tests/v1/integration/test_routing.py` — the real database: I-A the P9 → P10 contract
  (authorised routes; denied, pending, stale, superseded, foreign and forged cannot; routing
  writes no policy row), I-F fallback and the route approval, I-T provider terms at the adapter
  (both subjects), I-H immutable history and replay, I-U usage attribution and observation, I-R
  registration, health, continuity, the mission's resources, tier blocks.
- `tests/v1/integration/test_routing_http.py` — H01–H07 over HTTP on the real runtime.

## 18. Phase-boundary tests — `tests/v1/unit/test_routing_boundaries.py`

B1 the router imports nothing; B2 no P10 module spawns or opens a socket; B3 never executes,
verifies, reviews or calls a model; B4 never authorises, approves or changes policy — no P9
function is called, the one Approval P10 writes is a PENDING `route` question with no state or
decision, and the only account moves it fires are the probe's and the user's; B5 the router
names no harness; B6 a snapshot reports capabilities exactly as declared; B7 (in
`test_routing.py`, a run-time spy) dispatch-and-route never starts, calls, authenticates or
inspects an adapter; B8 only the fake harness is registered for execution;
B9 no later-phase module exists; B10 a decision is frozen but for an own call's outcome, and a
usage row cannot detach from its decision; B11 no adapter probe inside a command; B12 the fake
adapters declare a known tier.

## 19. Mutation suite — `tools/mutate_p10.py`

37 mutants, each replacing one exact snippet and requiring its named tests to fail: eligibility
(R01–R11, R37), allocation (R12–R16), ordering, continuity and determinism (R17–R22), the P9 →
P10 contract (R23–R28), provider terms, history and usage (R29–R36). They cover every mutation
the phase specification lists: incapable harness selected (R01), denied action routed (R24, R26),
pending approval routed (R23), preference overriding capability (R02), ceiling ignored (R12,
R16), fallback skipped (R17), nondeterministic ordering (R19, R20), model leaked across harnesses
(R05), native structured output required (R03), prompted structured output rejected (R04),
continuity overriding capability (R37) and allocation (R21), terms second check removed (R29,
R30), historical decision mutated (R31), usage detached (R32, R33), the router creating an
approval (R28), the router bypassing P9 (R24–R27).

## 20. Judge

S3 (both functions), S4 `test_no_execution_starts_on_an_account_at_its_ceiling` and
`test_fallback_follows_the_account_policy` (allow / ask / deny), S12 (both functions) and K1's
`test_the_router_not_the_pre_router_election_decides` pass on both bindings; K1's other functions
now assert `decided_by: router`. S4's mid-run crossing stays P12. The judge's HTTP binding runs
with a `FakeUsageFeed`, and `rig.usage` reports through it.

## 21. As built

Commits (on `archeus-v1-rearchitecture`):

1. archeus: P10 resource domain and storage
2. archeus: P10 resource router
3. archeus: P10 routing in dispatch and own calls, usage, runtime and API
4. tests: P10 judge, boundaries and mutation suite; docs (this record)

### 21.1 Deviations

1. **The gate was written with the build, not before it** (see Status).
2. **No synchronous usage refresh** (§4 item 1): stale readings are penalised and their age recorded.
3. **Account health moves on usage are not fired**: `near_ceiling`, `window_exhausted` and
   `reset_time_passed` are computed by the router from the snapshot; the machine moves only on
   the probe (`auth_ok`/`auth_failed`) and the user (`user_disables`/`user_enables`). The breaker
   and limit-error moves are P11's, with execution failures.
4. **The `policy` step of resource-router §5 is not a policy-engine call** (§4 item 2).
5. **The router does not lower effort on a CONSTRAINED account** (resource-router §6): no
   planner sets effort yet.
6. **`retry_of` is not recorded**: a retry is a new decision linked by its task.
7. **`/v1/accounts/{id}/usage`, `/v1/models` and `/v1/route/preview`** (api-and-realtime §2) are
   not built: accounts carry their latest usage and the adapters' offers are in
   `/v1/harnesses`; a preview has no caller before P16.
8. **The P6 pre-router recorder `calls.decide_route` is removed** (it had no production caller);
   its three tests use a test helper.

### 21.2 Remaining concerns (for later phases)

- **P11:** mid-execution halts and hand-off on crossing a ceiling, limit errors → LIMITED, the
  error-storm breaker, the real adapters' usage reports, effort chosen by the planner.
- **P12:** S4's crossing-the-ceiling function.
- **P16:** the route-approval card and the resources UI.

**DESIGN_GATE = IMPLEMENTED.**
