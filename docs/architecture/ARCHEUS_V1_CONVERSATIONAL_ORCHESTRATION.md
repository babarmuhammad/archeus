# Archeus V1 — Conversational orchestration, live work and account policy (third orchestration pass)

Status: **DECIDED — architecture only; implementation not started.** Written 2026-09-30 on
`archeus-v1-rearchitecture` at `0b950b8` (audit, `9dc1098`); the user's decision pass the same day
resolved D-13, D-16, D-18 and D-21 (Part H), which adopts ADR-0041…0043 as DECIDED, adds
ADR-0044 (application theme) and the AP-1 account-protection slice. No code, Core/API or UI change
was made to produce it. P18 remains open; P19.5 stays paused after the travelling marker
(`04eabe9`) and nothing here starts or changes a visual slice. ADR-0036…0040 of the orchestration
plan remain PROPOSED (its D-1…D-12).

This is the third orchestration pass. It builds on, and does not restate:

- [ARCHEUS_V1_ORCHESTRATION_RECONCILIATION.md](ARCHEUS_V1_ORCHESTRATION_RECONCILIATION.md) with
  ADR-0031…0035 (DECIDED): catalogue, evidence classes, evidence in routing, artifact hand-off,
  data class;
- [ARCHEUS_V1_ORCHESTRATION_PLAN.md](ARCHEUS_V1_ORCHESTRATION_PLAN.md) with ADR-0036…0040
  (PROPOSED): availability, harness descriptor, control modes, evaluation, architecture binding;
- the visual rulebook [../design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md](../design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md)
  with ADR-0024…0030 (DECIDED), in particular its operational-presence mechanisms O-1…O-8 (§6).

It answers the user's directive "Additional architectural requirements — conversational
architecture, agent orchestration visibility, and multi-account resource control" (sections A–O,
cited as §A…§O). Three ADRs were proposed (ADR-0041…0043) and are now DECIDED; the decision pass added ADR-0044. Decision ids continue the plan's
(D-13…D-24); conflict ids continue its appendix (C-30…C-40).

Method: the V1 code was read at source for the conversation write path, the grammar, intent,
mission resource preferences, the router's allocation and ordering, the ledger, the reads the SPA
composes, the deployment shells and the theme tokens. Every file:line below was read first-hand
or re-checked after a delegated search (`grammar.py`, `conversation.py`, `router.py`,
`resources.py` spot-checked directly).

## Contents

- Part A — What already exists (by directive section)
- Part B — What is missing, and the conflicts found
- Part C — What this pass adds to the architecture (ADR-0041…0043)
- Part D — How it works, conceptually (report items 8–12)
- Part E — Traceability table
- Part F — Phase ownership, Core/API dependencies, UI placement, gates
- Part G — Decisions for the user, undecided items, implementation order
- Part H — The decision pass (D-13, D-16, D-18, D-21) and the sixteen traced requirements
- Appendix — the acceptance checklist of §O

---

## Part A — What already exists

The short answer: **Archeus was designed conversation-first, and most of what the directive asks
for already has an architectural home.** The product definition is "Tell Archeus what you want.
It figures out what needs to happen" with "the JARVIS-like mental model" named as important
(`reference/Archeus_v1_prompt.txt:120-122`); the conversation model is ADR-0015; the brain and
the deterministic control verbs are ADR-0006; the intent pipeline was built in P7. What is
missing is a small number of seams, listed in Part B.

### A1. Conversational interface (§A)

| Capability the directive lists | Exists as | Evidence | State |
|---|---|---|---|
| conversation / session state | one persistent primary conversation per user; mission threads specified | ADR-0015; `infra/db/migrations/0006_conversation.sql:10-60`; domain-model §6 | built (primary); per-mission threads are P16 seam **S1 → P19** |
| intent extraction | deterministic grammar first, then a brain call with schema `intent.v1`: question / new_work / continue_work / feedback / preference / idea | `core/application/grammar.py:23-25`; `core/brain/intent.py:18,32-59` | built |
| challenge when evidence disagrees | Challenge and clarification cards | `core/application/conversation.py:203-241` | built |
| task decomposition, planning | planner = `archeus_call(purpose planner, plan.v1)` on tier `large`; DAG validated by Core | plan §12; `core/calls.py:44` | built |
| delegation, execution | routed tasks on harness/account/model; checkpoint hand-off | P10–P12 | built |
| verification, review | Core verification; independent review routed away from the executor | `core/verification/reviewer.py:94-107` | built |
| approval gates | P9 plan/task/action/route Approvals; approval cards in conversation | P9; `entities.py:561-563` | built; the chat verbs `approve`/`reject` are seam **S3 → P19** |
| resumability | `resume` verb → PAUSED → RESUMED → redispatch from the approved plan in force; execution resume when harness and route allow, else checkpoint redispatch | `commands.py:380-402`; `states.py:96-114`; `core/execution/manager.py:402-512`; `application/executions.py:653-685` | built |
| contextual / recent-work memory | ContextPackage per call; knowledge with provenance; since-you-left digest | P5, P6; `/v1/digest` | built |
| model / provider selection | the router, one decision per subject, persisted and replayable | ADR-0005; `core/routing/router.py` | built |
| tool selection | derived from action classes; capability removal | ADR-0007 | built |
| execution status, structured progress | progress computed from the task DAG, never agent-reported; mission status line | plan §11; `clients/app/src/state/present.ts` | built |
| human-in-the-loop control | pause / resume / cancel / e-stop; approvals; Attention | P9, P11; `/v1/estop` (`api/routes.py:571-584`) | built; **Pause all** is the P19.5 Core slice |
| "why did you choose that" | `why <id>` answered from `RouteDecision.explanation` (generated from the record, never written by a model) | `conversation.py:165-166,530-537`; resource-router §8 | built as text; the `route_explanation` **card** is declared and never emitted (C-31) |

The governing rule the directive asks for — *a conversational command must resolve into the same
governed operations that structured controls use* — is already the design: the brain's principal
has the `propose` scope only and can never approve (ADR-0006, domain-model §3); control verbs are
parsed without a model; brain outputs are schema-validated and applied **as commands by Core**,
through the same authorisation as a button (plan §11, §27).

### A2. Conversation → plan → agents → execution (§B)

The lifecycle exists end to end in existing objects: `Message` → `Intent` → `Mission` (explicit
and inferred requirements separated) → `PlanVersion` (tasks with the four-part contract,
`min_model_tier`, `touches[]`, approval points) → per task a `RouteDecision` (harness, account,
model, effort, every elimination with its reason) → `Execution` → `Checkpoint` → `Verification`
→ `Review` → mission verification → `Feedback` and knowledge promotion. Provenance links each
step: `Intent.route_decision_id` and `context_package_id`, `Execution.route_decision_id`,
`Verification.performed_by`, `UsageLedger.route_decision_id`. Reconciliation §14.1 and ADR-0034
express "analyse, then implement, then another model reviews" as separate governed steps with an
artifact hand-off; ADR-0040 (PROPOSED) makes the architecture artifact bind the implementation.

Missing: the plan view does not show, per step, *who would run it* before approval — the route
preview (C-39) — nor, after dispatch, the routed resource on the task row (the Now tab shows it
per execution: `clients/app/src/surfaces/Mission.tsx:259-305`).

### A3. Live agent / execution control room (§C)

The visual rulebook already decided what a control room is for Archeus (§6 of the rulebook): a
status display in which *the representation is the status*, with the mission — not the agent —
as the unit, following the specification's "do not treat agents as the user's primary
abstraction" (`reference/Archeus_v1_System_Specification.md:1114`). Its mechanisms: O-1
operations strip ("2 running · 1 needs you · 3 clients", Pause all, e-stop), O-2 Happening now
rows with the current-action chip and the resource line, O-4 operations map (bounded, active
missions and their executions, ADR-0027), O-7 activity stream, O-8 presence. The halo, pulse and
travelling marker exist and are driven only by real `execution.*` frames (ADR-0024 §7: no fake
activity).

What exists in data: every execution row carries `harness_id`, `account_id`, `model`, `effort`,
`route_decision_id`, `plan_id`, `workdir`, `branch`, `session_id`, `attempt`, `stop_reason`,
`exit_reason`, `failure`, `usage` (`entities.py:899-948`); the execution machine distinguishes
INTENT, STARTING, RUNNING, AWAITING_APPROVAL, PAUSING, PAUSED, HANDING_OFF, STOPPING, LOST and the
ENDED_* states, and the task machine adds READY, ROUTING, VERIFYING, BLOCKED (`states.py:133-207`).
The SPA shows harness/model/account on execution rows and in the execution inspector
(`present.ts:66-80`, `Mission.tsx:296-305,569`).

Missing: see B3 (no fleet-wide read, own calls invisible, no ledger read).

### A4. Multiple harnesses, accounts, models, providers, workers (§D)

Already separate concepts (resource-router §1, domain-model §8, reconciliation §8):

| Directive's concept | Archeus object | Relationship |
|---|---|---|
| MODEL | `Model` (catalogue facts, ADR-0031) | offered by many accounts through `ModelOffer` |
| PROVIDER | a property of `Model` and of an account's `auth_kind` — deliberately not a fifth routing object | a model has one provider; a proxy account may reach many (`route_kind: proxy`, ADR-0031) |
| HARNESS | `Harness` + adapter contract (+ descriptor, ADR-0037) | one harness has many accounts; supports many models |
| ACCOUNT / CREDENTIAL | `Account` (`auth_kind` subscription_oauth / api_key / provider_proxy; node-bound, credentials never leave the node) | an account offers many models |
| WORKER / EXECUTION ENVIRONMENT | `ExecutionNode` (ADR-0008) | one node hosts many harnesses; V1 ships only the local node, remote nodes are deferred past V1 (plan §31.2) |
| SESSION | `Session`, bound to (harness, account) | moving accounts is always a checkpoint hand-off |

The router never assumes one model = one account = one harness: candidates are
(harness, account, model) triples; multi-home per CLI (`CODEX_HOME`, `PI_CODING_AGENT_DIR`) and
several Claude config dirs are registered accounts. The one place this is not yet true in fact is
C-20 (Claude Code offers the same list for every account, P22) and C-22 (pi offers its catalogue,
the plan's defect slice).

### A5. Account priority and resource budgeting (§E)

Built (`entities.py:1277-1363`; `core/application/resources.py:27-28,69-71,93-123`;
`router.py:43-311`):

| Directive's item | Exists as | Gap |
|---|---|---|
| account priority | `ResourcePolicy.priority`, global per account; registration order by default | not per project/mission (only mission `preferred_*`) |
| harness priority, model preference | mission `preferred_harnesses`; own-call preference; `model_required` for own calls | task/mission model pins are V1.x-O2 |
| account allow / deny | account `project_allow` / `project_deny`; mission `forbidden_accounts/harnesses` | no project-level *preference* |
| resource ceilings | `allocation_pct` − `reserve_pct` (− `brain_reserve_pct` for tasks) on the provider's observed window; halt at the next tool boundary on crossing | — |
| usage budgets | `budgets` {`tokens_per_day`, `cost_per_day`, `concurrency`} | **enforced only when the account has no readable usage window** (`router.py:265-276`) — C-35 |
| remaining-capacity awareness | usage windows with `observed_at`, staleness penalty, projected bump; **unknown is `None`, never 0**; unknown + no budget = fallback-only (`router.py:70-79,267-268`, `usage.py:5-6`) | only Claude Code windows are polled; the SPA prints usage as raw JSON (`Control.tsx:217-296`) |
| concurrency limits | `budgets.concurrency` | only on the no-window path; no per-harness cap |
| fallback order | `fallback` allow / ask / deny + `route` Approval; `unblock_at` | — |
| **"preserve / protect this account"** | **nothing**: `reserve_pct` is headroom, and a lower-priority account that is eligible is elected silently whenever higher ones are eliminated | **C-34** |
| per-project policy | account-side allow/deny lists | no project default preferences |
| per-task override | none — `required` is hard-coded `{}` (`resources.py:348`) | V1.x-O2 already owns task pins |
| emergency / manual override | e-stop (`/v1/estop`, `/v1/rearm`); mission `resource_preferences` (clears affinity) | Pause all (non-destructive) is P19.5 |
| default policy visible | the priority number per account in Control → Resources; the ordering rule only after the fact in `why` | C-37 (effective policy not readable) |
| never silently consume a protected account | "Never silently violate policy to keep work moving" (resource-router §7) holds for *policy*, but there is no policy that says "protected" | C-34 |
| do not invent quota | holds by construction (`None` = unknown; ADR-0036 availability reasons) | — |

### A6. Intelligent model/harness selection (§F)

The router already selects by requirements, not cost: capability → model (tier by blast radius,
context window) → enforcement → provider terms → restriction → health → allocation → election
(ADR-0005, ADR-0033). Security, repository/tool access and approval requirements are elimination
steps *before* any preference. The explanation is generated from the record
(resource-router §8), `archeus route why` and `/v1/route-decisions` exist, and the user can
override by preference, forbid and (V1.x-O2) pin. Reconciliation §13 and ADR-0033 already decided
that evidence annotates by default and orders or excludes only under a named user rule, with no
weighted score. Requirement provenance ("classified as …") is K5 of the plan (P21).

### A7. Capability registry, versions, releases, evaluation (§G–§I)

All decided or proposed in the two earlier passes; nothing new is needed:

| Directive | Home |
|---|---|
| static/provider-declared vs Archeus-observed | DECLARED vs OBSERVED / INFERRED / UNKNOWN (ADR-0032) |
| version-aware; v1 ≠ v2 | evidence keyed by exact model revision and harness version; revision-keyed staleness; no historical row rewritten (ADR-0032 §4, ADR-0033 §6) |
| no "intelligence scores" | no scalar score anywhere (ADR-0032, ADR-0033 §4) |
| discovered → validated → profile → evaluation → approved | ingestion → validation → CATALOGUED → EVALUATING → APPROVED (ADR-0031 §2, §4); evaluation missions (ADR-0039) |
| no blind scraping; untrusted input | per-field source ladder; aggregator opt-in and off; fetched content is data (ADR-0031 §3; reconciliation §20) |
| new release never rewrites routing policy | "discovery is not authorisation to route"; routing status moved only by the user or a standing rule the user created (ADR-0031 §4) |
| observation vs policy; recommendation vs authority | annotate by default; `evidence_order` / `evidence_exclude` only by the user's rule (ADR-0033) |
| no self-grading | review independence (`reviewer.py:94-107`); evaluation verifiers mutation-verified (ADR-0039) |
| inspect why knowledge changed | `catalog.*` and `model.state_changed` events; per-field `source_ref` and `observed_at` (ADR-0031) |

### A8. User control and override (§J)

| Command | Governed path today |
|---|---|
| "Use Claude." / "Use the local model." / "Use this account." / "Don't use this account." | mission `resource_preferences` (`POST /v1/missions/{id}/resources`, user device only, `resources.py:42-43,110-123`) — **no conversational path writes it (C-32)** |
| "Use the strongest architecture model." / "the cheapest acceptable model" | tier requirement (`min_model_tier`) by blast radius; the router already picks the smallest tier that meets it — see C-40 for "strongest" |
| "Don't run anything remotely." | data class `local_only` on a project or, narrower, a mission (ADR-0035, V1.x-O4); location vocabulary D-5 |
| "Stop all agents." / "Pause this plan." / "Resume it." | e-stop; Pause all (P19.5); `pause` / `resume` verbs on a mission |
| "Why did you choose this model?" | `why <id>` → RouteDecision explanation |
| "Show me what is consuming my accounts." | **no read** (C-37); P21 already owns "model usage and cost" (plan §28) |

### A9. UI placement (§K)

ADR-0014 already fixes the information architecture — Now · Work · World · Control, with Attention
and the command bar as layers — and the directive's list maps onto it without a new destination:

| Directive | Existing surface |
|---|---|
| CONVERSATION | Now (composer always focused; `Now.tsx:100-148`), command bar "Tell Archeus" (`CommandBar.tsx:25-41`), mission threads (S1, P19) |
| NOW / CONTROL ROOM | Now + operations strip (O-1) + Happening now (O-2) + operations map (O-4) |
| GRAPH | World graph and the operations map (P18, P19.5) |
| INSPECTOR | mission inspector (Outcome · Plan · Now · Evidence · Why · Timeline · Relations) and the execution inspector |
| RESOURCES | Control → Resources (harnesses, accounts, models, route preview, sessions, nodes; ui-architecture §4.6) |
| SETTINGS / POLICY | Control → Autonomy (policy grid, simulate) and Control → Resources (resource policy, routing rules) |
| HISTORY / DECISIONS | the Why tab, `/v1/route-decisions`, O-6 Recent decisions, O-7 activity stream, P21 trace view |

### A10. Themes and deployment modes (§L)

| Mode | Specified | Built |
|---|---|---|
| browser tab | ui-architecture §1 | yes — `archeus core --open` opens the SPA with a launch code (`cli/main.py:146-155`, `core/runtime.py:625-652`) |
| desktop (Qt + WebEngine shell; Edge `--app` / browser fallback) | ui-architecture §1, target-architecture §4, migration-plan §3 ("REUSE WITH REFACTOR") | **no** — P16 seam **S7 "Qt shell attach" → P19** (`p16-design-gate.md:174,1176,1339`); the only Qt reference in `archeus/` is the ownership table (`infra/paths.py:31-33`) |
| PWA | ui-architecture §1, ADR-0010 | yes — `clients/app/public/manifest.webmanifest`, `sw.js`, `src/main.tsx:14`; installation needs the HTTPS tunnel path; manual install check still open in P18 |
| themes | design system §3.3, ADR-0017 | Archeus Dark, Archeus Light, High Contrast (dark + light), following the OS; thread tints from the 39 legacy palettes (`clients/app/tokens/tokens.json:17-35`); no app-level theme switch until D-21 — now a per-client preference, System by default (ADR-0044, P19); Control → Appearance (theme, contrast, tint, density, motion) not built |

Every surface is one SPA with no business logic (ADR-0011), so conversation and control-room
work cannot become dependent on one shell. Theme is presentation-only by construction: state
colours and glyphs are fixed across themes (ADR-0017), so no theme can change orchestration
semantics.

---

## Part B — What is missing, and the conflicts found

### B1. Conversation

1. **No conversational path writes resource preferences (C-32).** `intent.v1` has no account,
   harness, model or location field (`brain/intent.py:32-59`); a `preference` intent becomes
   Feedback plus a CANDIDATE PREFERENCE knowledge item (`conversation.py:355-385`) and never
   reaches `Mission.resource_preferences` or a ResourcePolicy. "Use account B" or "don't run
   remotely" therefore changes nothing the router reads.
2. **Recognised verbs are declined with a stale reason (C-30).** `approve`, `reject` and
   `reprioritise` are answered "acting on it arrives with P9/P10" (`grammar.py:26-28`,
   `conversation.py:152-156`) although P9 and P10 are built. Their owners exist: `approve`/`reject`
   bound to a displayed card's `action_hash` is S3 (P19); mission priority is the P19.5 Core slice.
3. **No all-scope or plan-scope verb.** "stop all", "pause all" and "stop the implementation"
   fall through to the brain (`grammar.py:84-86`); `stop` on an EXECUTING mission is declined
   "pause first" (`commands.py:404-407`) — C-33.
4. **`why` answers in text only (C-31)**; the `route_explanation` card type is declared
   (`entities.py:561-563`) and never emitted.
5. **Live questions are answered from the context package, not from state.** Bare `status`
   returns project, mission and drift counts (`conversation.py:160-164,517-527`); nothing answers
   "what are the agents doing" or "what is consuming my accounts" from executions, own calls or
   the ledger.

### B2. Accounts and resource policy

6. **No protected account (C-34).** Priority is ordering only (`router.py:284-293`); an eligible
   lower-priority account is elected silently whenever the higher ones are eliminated, so a
   shared account is consumed "because it is technically available" — exactly what §E forbids.
   `fallback: ask|deny` applies only when *no* candidate survives.
7. **Budgets are skipped for accounts with a usage window (C-35)** (`router.py:265-276`) — every
   Claude Code OAuth account. A `tokens_per_day` or `concurrency` the user sets would be silently
   ignored.
8. **No task-class limit on an account** ("use account A for low-cost work"), and no project-level
   default preferences.
9. **The effective policy is not readable (C-37).** Defaults are applied at registration
   (`resources.py:27-28,69-71`) but the resulting order and the rule that applies it are visible
   only after a decision, in `why`; the SPA cannot edit policy (no caller of the policy route).

### B3. Live work and consumption

10. **No fleet-wide read of live work (C-37).** Only `GET /v1/executions/{id}` and
    `GET /v1/tasks/{id}/executions` exist; `/v1/status` returns world status
    (`api/routes.py:283-285,909`); Now is composed from missions, attention and digest (P16 S5).
11. **Archeus's own calls are invisible as work.** A brain or planner call consumes an account and
    has a RouteDecision whose `outcome` is written only when it ends (domain-model §8.6), but no
    read presents "planner running on Account A" — yet the directive's "what is consuming my
    accounts" must include them.
12. **The ledger has no read** except nested in one route decision (`core/application/queries.py:199-205`);
    `ledger_totals` feeds the router but not `account_view` (`resources.py:164,524-526`).
13. **The plan view shows no resources per step (C-39)**: no route preview before plan approval
    (promised by the plan's C9 / ADR-0038), no routed resource on the task row after dispatch
    (`Mission.tsx:245-256`).

### B4. Deployment and themes

14. **The V1 desktop shell is not built (C-38)** — owned by P19 through P16 seam S7, but the P19
    entry of the rearchitecture plan names none of the P16 seams it inherited (S1, S2, S3, S4, S6,
    S7). This pass corrects the plan text; ownership does not change.
15. **Theme selection (C-36).** The directive asks that theme selection stay a first-class
    presentation concern with multiple themes. V1 has three themes following the OS and 39 thread
    tints, and *deliberately* no app-level theme switch (design system §3.3, plan Appendix B.3,
    citing the platform guidance "avoid offering an app-specific appearance setting"); the
    "Classic appearance" question is open as Q-C1. The audit did not override that; the user's
    decision D-21 does (Part H4, ADR-0044): a per-client theme preference, System by default,
    with the palettes kept as tints and Q-C1 untouched.

### B5. Conflicts added (continuing the plan's appendix)

| ID | Conflict | Evidence | Resolution proposed | Status |
|---|---|---|---|---|
| C-30 | Recognised verbs declined citing phases that are built | `grammar.py:26-28`; `conversation.py:152-156` | owners unchanged: S3 → P19 (`approve`/`reject`); P19.5 Core slice (`reprioritise`); the stale text changes with them | DECIDED |
| C-31 | `route_explanation` card declared, never emitted | `entities.py:561-563`; `conversation.py:165-166` | `why` attaches the card (ADR-0042 §4), P19 | DECIDED |
| C-32 | No conversational path to resource preferences | `brain/intent.py:32-59`; `conversation.py:355-385` | resource directives (ADR-0042) | DECIDED |
| C-33 | "stop" on a running mission is declined; "stop all" is not a verb | `commands.py:404-407`; `grammar.py:84-86` | "stop/pause all" → Pause all; "emergency stop" → e-stop behind confirmation; "stop <running mission>" → the same two-step the UI offers (pause, then cancel), as one confirmation card — no new edge (D-19) | DECIDED |
| C-34 | An eligible lower-priority account is consumed silently; no protected account | `router.py:284-293`; resource-router §4 | consumption class `normal / last_resort / explicit_only` (ADR-0041); §1 and §3 land in AP-1 before `rotation` is permitted (H3) | DECIDED |
| C-35 | Budgets ignored when a usage window is readable | `router.py:265-276` | budgets enforced whenever set, alongside the ceiling (ADR-0041 §3) | DECIDED |
| C-36 | "Theme selection first-class" vs "no app-level theme switch" | design system §3.3; plan Appendix B.3; rulebook Q-C1 | per-client theme preference, System default; tints stay tints (ADR-0044, H4) | DECIDED |
| C-37 | Live work, own calls in flight, ledger and effective policy have no read | `api/routes.py` route list; `queries.py:199-205`; `resources.py:524-526` | one live-work derivation, account consumption and effective policy in existing reads (ADR-0043) | DECIDED |
| C-38 | P19 inherited P16 seams S1–S4, S6, S7 but its plan entry names none | `p16-design-gate.md:168-174`; plan §31.1 P19 | plan text corrected in this pass (factual; ownership unchanged) | FIXED (text); confirmed D-22 |
| C-39 | No per-step route preview before plan approval; no routed resource on task rows | `Mission.tsx:245-256`; plan C9 | route preview read with the Resources route preview (P22); the plan card renders it | DECIDED |
| C-40 | A user's "use the strongest model" vs ADR-0033 §1 ("most powerful model is not an algorithm") | ADR-0033 §1 | a user's "strongest / best" is a **requirement** (`min_model_tier: large`, the top tier), or an explicit pin when a model is named; never a ranking the router invents; "cheapest acceptable" is today's behaviour (smallest tier meeting the requirement) (D-20) | DECIDED |

---

## Part C — What this pass adds to the architecture

The design rule is the one the two earlier passes used: **extend the router, policy, mission loop
and reads; add no parallel orchestrator, no Agent entity, no second approval system.** Three
decisions are needed; everything else is phase ownership. *As adopted (Part H1):* the three are
DECIDED with the smallest corrections listed in H1 — the ADR text is authoritative where this
summary is shorter — and the decision pass added a fourth, ADR-0044 (application theme, H4).

### C1. ADR-0041 — Account consumption policy

[ADR-0041](decisions/ADR-0041.md) (DECIDED). ResourcePolicy grows, it is not replaced:

1. **`consumption`** ∈ `normal` (default) | `last_resort` | `explicit_only`:
   - `normal` — today's behaviour.
   - `last_resort` ("do not consume account A unless necessary") — the candidate stays in the
     elimination steps, but **election considers it only when no `normal` candidate survived**;
     electing it is then a fallback governed by its `fallback` mode, default `ask`, so the user
     sees "Use *Shared team* (last resort) because *Personal* is at its ceiling until 14:30?". It
     is recorded as `fallback_from` like any fallback.
   - `explicit_only` ("never automatically") — eliminated at `restriction` with the reason
     "used only when you name it", unless the subject's preferences name the account — a
     mission/project preference or a pin set by a user device (never a brain inference; see
     ADR-0042 §3).
2. **`limits`** (optional): `subjects` ⊆ {`archeus_call`, `task`, `review`}, `max_tier`, and
   `task_families` (the last from V1.x-O1) — "use account A for low-cost work": the account is
   eliminated at `restriction` for any subject outside them, with the reason.
3. **Budgets are enforced whenever set**, in addition to the window ceiling — the ceiling answers
   "how much of the provider's window", the budget "how much Archeus may spend"; today the second
   is silently skipped for windowed accounts. `concurrency` becomes a real cap on any account.
   With no budget set nothing changes.
4. **Project defaults.** A project may carry default `resource_preferences` (the mission shape:
   preferred/forbidden accounts and harnesses, `max_cost_band`); a mission inherits them and may
   narrow or override them. Priority stays one global integer per account: a project that wants a
   different first account says so as a preference, which is already the ordering key before
   priority.
5. **The effective policy is readable** (with ADR-0043): per account, its consumption class,
   limits, ceiling arithmetic, budgets, fallback mode, priority and the ordering rule, plus what
   the defaults were — so "if no policy is specified" (§E) is a deterministic, visible default:
   registration order, `allocation 80 / reserve 10 / brain reserve 10`, `fallback: ask`,
   `consumption: normal`.

Nothing here is a score, and nothing lets evidence or a model promote a protected account.

### C2. ADR-0042 — Conversational directives resolve into governed operations

[ADR-0042](decisions/ADR-0042.md) (DECIDED). Three routes, in order, all ending at an existing
command:

1. **Deterministic grammar first** (ADR-0006), extended with verbs whose objects resolve exactly:
   `pause all`, `resume all`, `emergency stop` (confirmation), `stop <running mission>` (the
   two-step card, C-33), `approve` / `reject` bound to the card on screen (S3),
   `reprioritise <mission>`, `use <account|harness>` and `don't use <account|harness>`
   (for a named or the single active mission), `why <object>`, `status` / `what is running`.
   No model is called; an unresolved object falls through to the brain as today.
2. **The brain proposes a structured `resource_directive`** in `intent.v1`: scope
   (this request / a mission / a project / standing), prefer and forbid (accounts, harnesses,
   models, locations), a tier requirement, a pin. Core resolves every name to a real id; an
   unresolvable or ambiguous name is a clarification card, never a guess.
3. **Asymmetric application.**
   - A **narrowing** directive in the user's own request (forbid an account, harness, model or
     location; a tighter cost band) is applied to the mission that request creates or continues,
     shown on the mission card with "from your message", and reversible there. Narrowing can
     block work but never widens authority.
   - A **widening** directive (naming a `last_resort` or `explicit_only` account, a pin, a higher
     tier or cost band) and **every standing change** (project defaults, a ResourcePolicy, a
     routing rule) is a **PROPOSED change card** the user confirms from a user device — the policy
     route keeps its `admin` scope. The brain never writes policy (its principal cannot).
   - Every applied directive records its source (`message_id`, `intent_id`) on the preference or
     policy version it produced.
4. **Answers about state come from Core, not from the brain.** "What is running", "what is
   consuming my accounts" and "why" are answered from the ADR-0043 reads and the RouteDecision,
   with their cards (`status`, `route_explanation`); the brain may paraphrase, the card is the
   record (resource-router §8).

This is the "JARVIS-like" layer: not a new subsystem, but the guarantee that anything the user can
do with a control can be said, and anything said becomes the same command, under the same
authorisation, with the same approval, audit and provenance.

### C3. ADR-0043 — Live work is executions and in-flight own calls; one derivation

[ADR-0043](decisions/ADR-0043.md) (DECIDED).

1. **There is no Agent entity.** An "agent working" is an `Execution` in a live state or an own
   call whose RouteDecision has no `outcome` yet. Harness-internal subagents stay invisible to
   Core (C-16) unless an adapter records them; nothing is invented to fill the gap.
2. **One pure derivation, `live_work(conn)`**, returns per item: kind (execution / own call with
   its `purpose`), mission and task titles, project, repository, worktree/branch, harness, account,
   model, effort, the task and execution states, plan step (task key and position), what it has
   produced so far (checkpoints, artifacts recorded — the latter once P21's producer record
   exists), **what it waits on** (approval id, `limited_until` / `unblock_at`, human acceptance,
   a dependency), and the resource constraint affecting it (the eliminating reason of the
   decision that blocked it). It is exposed in `/v1/status` (a `live` section) — not a new route
   — and read by the `status` verb, the operations strip, Happening now, the operations map and
   Control → Resources.
3. **Account consumption** is added to `account_view` in `/v1/accounts`: live consumers from
   `live_work`, ledger totals (today / 7 days, per mission and per subject kind — task, review,
   own-call purpose), the window utilisation with `observed_at` and `resets_at`, and unknown shown
   as **unknown**, never as a number. Nothing is estimated.
4. **The effective policy** (ADR-0041 §5) rides in the same view.
5. **Visual DNA holds**: an item exists only while its row does; nothing animates without an
   `execution.*` frame; own calls produce no motion (they emit no frames) — they appear as text
   rows, and a model, provider or role is never a colour (ADR-0026 §3).

---

## Part D — How it works, conceptually

### D1. Multi-harness and multi-account orchestration (report item 8)

A unit of work is a **subject** (task, review, or one of Archeus's own calls with its purpose).
Its **requirement** is computed from the subject — capabilities from the task kind, action classes,
tier by blast radius, context window, data class, the mission's preferences. The **candidates** are
every (harness, account, model offer) triple the configured accounts can address (ADR-0036: only
configured providers; each offer with its availability state). The router eliminates in a fixed
order — installed, serves-this-subject, capability, model routing status, enforcement, provider
terms, restriction (project rules, data class, consumption class and limits), provenance, health,
allocation and budgets — recording each elimination's reason, then orders the survivors by
affinity, the user's preference, priority, tier fit, health and a stable tie-break, and elects one.
If none survives, it falls back only as the account's fallback mode and the material-substitution
rule allow, asks, or blocks with an unblock time. The decision is frozen and replayable. A
harness is one adapter plus a descriptor; Claude Code, Codex, pi and the fake are
interchangeable to the orchestration, which never branches on a harness id (ADR-0037). Work moves
between accounts only through a checkpoint into a new session.

### D2. Account priority and resource protection (report item 9)

Four layers, each explicit and each named in the explanation when it decides:

1. **Where an account may be used** — `project_allow/deny`, data class, `limits`, and the
   `explicit_only` class (eliminations with reasons).
2. **How much of it** — the window ceiling (`allocation_pct − reserve_pct`, less the brain reserve
   for tasks) and, when set, budgets and concurrency (eliminations with reasons; unknown usage is
   never read as zero).
3. **In which order** — affinity, the mission's or project's preference, priority, tier fit.
4. **Only if necessary** — `last_resort` accounts are elected only when no `normal` candidate
   survives, and then as a fallback that asks by default.

"Prefer account B" is a preference (layer 3); "don't consume account A unless necessary" is
`last_resort` (layer 4); "use A for low-cost work but preserve it" is `limits` plus a low
ceiling (layers 1–2); "this task is important enough for the best account" is a per-mission
preference or pin that names it (a widening directive, so confirmed). The default with no policy
is visible in Control → Resources and deterministic.

### D3. How model capability and version knowledge evolves (report item 10)

Unchanged from ADR-0031…0033 and ADR-0039: facts are catalogue rows with a source rung and
`observed_at`; a new model or revision enters CATALOGUED and routes nothing until the user (or a
standing rule the user created) moves it; an approved evaluation mission over fixture
repositories earns it EVALUATING evidence; real outcomes accumulate as OBSERVED evidence keyed to
(model revision, harness version, task family), promoted to INFERRED claims only on corroboration;
evidence annotates every decision and orders or excludes only under the user's named rule. A new
revision starts with no inherited evidence. Nothing changes a routing policy because a model
appeared.

### D4. The conversational, JARVIS-like interaction (report item 11)

The primary conversation on Now is the main way to operate Archeus; the command bar is the same
grammar from anywhere; mission threads (P19, S1) keep a mission's turns together. Each user turn
becomes at most one Intent: a grammar verb (no model), or a brain reading that Core checks,
resolves against real objects, and challenges when it conflicts with confirmed knowledge. New work
becomes a mission proposal with explicit and inferred requirements — and, with ADR-0042, the
resource directives the user stated — then a plan the user approves per the autonomy profile, whose
steps show who would run them (route preview), then routed executions whose progress, waits and
approvals come back into the same conversation as live cards. "Why", "what is running", "what is
consuming my accounts", "pause", "resume", "stop", "approve" are all answered or executed from
Core state. Archeus reports what it did, why (the record), what runs, what needs approval and what
remains — because each of those is an object with a card.

Voice ("spoken JARVIS") is a future input and output modality, owned post-V1 (Part H5): it
produces a user `Message` in the same conversation and goes through the same grammar, intent,
directive and command path (ADR-0042 §7); nothing in V1 depends on it or prevents it.

### D5. Live agent visibility (report item 12)

At a glance: the operations strip (counts, Pause all, e-stop) and the mark's orbit. In Now:
Happening now rows — one per active mission — with the current-action chip and the resource line
("implementing · Claude Code · claude-sonnet-5 · Personal"), and own calls in flight as plain rows
("planning · Personal"). Spatially: the operations map, bounded to active missions and their
executions. On demand: the mission inspector's Now and Plan tabs (per-step resource, route preview
before approval), the execution inspector (output, checkpoints), and Control → Resources
(what each account is running, what it has consumed, how much window is left or that it is
unknown, and the effective policy). Every one of these reads the same `live_work` derivation, and
every movement on screen is caused by a real `execution.*` frame.

---

## Part E — Traceability table

Status: **exists** = built; **owned** = assigned to a phase before this pass; **decided** = assigned
by this pass and adopted in the decision pass (Part H).

| # | Requirement | Architectural component | Phase | ADR | Core/API dependency | UI surface | Test / gate | Status |
|---|---|---|---|---|---|---|---|---|
| A-1 | Conversational operation | primary conversation, intent pipeline, brain | P7 | 0006, 0015 | — | Now composer, command bar | P7 grammar/intent tests | exists |
| A-2 | Per-mission threads | Conversation per mission | P19 (S1) | 0015 | intent write path | mission inspector Thread tab | — | owned |
| A-3 | Chat `approve`/`reject` | grammar bound to card `action_hash` | P19 (S3) | 0006, 0042 | grammar + P9 decide | Now, Attention | G1: chat approve = button approve (same PolicyDecision, step-up) | owned |
| A-4 | Pause all / resume all / emergency stop by voice-of-text | grammar → Pause all / e-stop | P19.5 Core slice | 0006, 0042 | Pause all command (P19.5) | strip, Now | G2 | owned (Pause all), added (verbs) |
| A-5 | Reprioritise by conversation | grammar → set mission priority | P19.5 Core slice | 0006 | mission priority (P19.5) | Work, Now | P19.5 tests | owned |
| A-6 | Resource directives from conversation | `resource_directive` in `intent.v1`; grammar `use`/`don't use` | P19 (write path); location/model kinds with P22 / V1.x-O2 | 0042 | schema, resolution, preference setter | mission card, change card | G3, G4 | decided |
| A-7 | "Why" with the record | `route_explanation` card | P19 | 0042 | card emission | Now, Why tab | G5 | decided |
| A-8 | Answers about live state from Core | `status` verb over `live_work` | P21 | 0042, 0043 | `live_work` | Now | G6 | decided |
| B-1 | Conversation → plan → steps → execution → verification → memory | Mission / Plan / Task / RouteDecision / Execution / Verification / Review / Knowledge | P7–P13 | 0004–0007, 0034 | — | mission inspector | judge S1 | exists |
| B-2 | Per-step agent/model/harness/account visible before approval | route preview per task | P22 | 0036, 0038 | router preview read | Plan tab, plan approval card | G7 | decided |
| B-3 | Routed resource on task rows after dispatch | task → current execution resource | P19.5 (client, existing reads) | — | none | Plan tab | P19.5 e2e | decided |
| B-4 | Provenance between steps | artifact producer, `inputs[]`, requirement provenance | P21, V1.x-O3 | 0034, 0040 | P21 fields | Why, Evidence | plan D4 gates | owned |
| C-1 | Which agents work, on what, where | `live_work` derivation | P21 | 0043 | `/v1/status` `live` section | strip, Happening now, map, Resources | G6, G8 | decided |
| C-2 | Own calls visible as work | in-flight RouteDecision (no outcome) | P21 | 0043 | same | Happening now, Resources | G8 | decided |
| C-3 | What each waits for / constraint affecting it | `live_work.waits_on`, blocking reason | P21 | 0043 | same | rows, inspector | G6 | decided |
| C-4 | Operations strip, map, chips, halo, marker | O-1…O-8 | P19.5 | 0024–0030 | Pause all | shell, Now, graph | rulebook §34 | owned (halo, marker built) |
| C-5 | No fake agents / activity | motion only on `execution.*` frames | P19.5 | 0024 §7 | — | all | idle invariant, framebuffer probes | exists |
| D-1 | Model / provider / harness / account / worker separate | Model, offer, Harness, Account, ExecutionNode | P1, P10, P22 | 0005, 0008, 0031, 0037 | P22 catalogue, descriptor | Resources | plan D4 | exists / owned |
| D-2 | Multiple harnesses first-class | adapter + descriptor; no harness-id branches | P22; Codex adapter for V1 release | 0037 | descriptor | Resources | harness-id gate | owned |
| D-3 | Multiple accounts first-class | Account + ResourcePolicy; multi-home | P10 | 0005 | — | Resources | routing tests | exists |
| D-4 | Remote workers | ExecutionNode remote contract | post-V1 | 0008 | — | Control → Resources → nodes | — | owned (deferred) |
| E-1 | Account priority | `priority`, preferences | P10 | 0005 | — | Resources form | routing tests | exists |
| E-2 | Protect an account from automatic use | `consumption` last_resort / explicit_only, partitioned before ordering | **AP-1** (Core); P22 (UI) | 0041 | router partition + restriction | policy route, CLI; Resources (P22) | AP-1 gate, G9 | decided |
| E-3 | Task-class account limits | `limits` | P22 (subjects, tier); V1.x-O1 (families) | 0041 | restriction step | Resources | G9 | decided |
| E-4 | Budgets and concurrency | budgets enforced whenever set; only on reported measures | **AP-1** | 0041 | allocation step | policy route; Resources (P22) | G10 | decided |
| E-5 | Per-project policy | project default preferences | P22 | 0041 | project field, inheritance | project Settings, Resources | G11 | decided |
| E-6 | Per-task override | task pins | V1.x-O2 | 0033 | requirement fields | Plan tab | O2 gates | owned |
| E-7 | Remaining capacity, unknown ≠ number | usage windows, `None` = unknown | P10; display P21 | 0005, 0036, 0043 | `account_view` consumption | Resources | G12 | exists / added (display) |
| E-8 | Default policy deterministic and visible | effective policy view | P21 (read), P22 (new fields) | 0041, 0043 | `account_view` | Resources | G13 | decided |
| E-9 | Never silently consume a protected account | last_resort → fallback `ask` by default; AP-1 before ADR-0021 `rotation: permitted`; material substitution asks (ADR-0038, PROPOSED) | AP-1, V1.x-O2 | 0041, 0021, 0038 | router | Attention | AP-1 gate, G9 | decided |
| E-10 | Emergency / manual override | e-stop, Pause all, mission preferences | P11, P19.5 | 0006 | — | strip, Control | drills (P20) | exists / owned |
| F-1 | Selection by task requirements | requirements + elimination steps | P10 | 0005, 0033 | — | Why | routing tests | exists |
| F-2 | Why a selection was made | RouteDecision explanation; requirement provenance | P10; P21 (K5) | 0005, 0033 | K5 | Why tab, card | plan D4 | exists / owned |
| F-3 | "Strongest" / "cheapest acceptable" | tier requirement or pin | P10; V1.x-O2 (pins) | 0033, 0042 | directive resolution | mission card | G4 | added (C-40) |
| F-4 | User override of a selection | preferences, forbids, pins | P10, V1.x-O2 | 0033 | — | mission Resources | routing tests | exists / owned |
| G-1 | Capability registry, declared vs observed | catalogue + evidence classes | P22, V1.x-O1 | 0031, 0032 | P22 | Resources → model inspector | plan D4 | owned |
| G-2 | Version-aware history | revision-keyed evidence, frozen snapshots | P21, V1.x-O1 | 0031–0033 | P21 fields | Why | plan D4 | owned |
| H-1 | Release discovery, candidate state | ingestion → CATALOGUED → EVALUATING → APPROVED | P22, V1.x-O1 | 0031 | P22 | Resources, Attention | P22 gates | owned |
| H-2 | Discovery never rewrites routing | routing status by user or user-made rule | P22 | 0031 | — | — | P22 gates | owned |
| I-1 | Evaluation without unsafe autonomy | evaluation missions; annotate-first evidence | V1.x-O1, O2 | 0033, 0039 | K8 | Work, Resources | evaluation isolation gate | owned |
| J-1 | Every command maps to a governed operation | ADR-0042 routes 1–3 | P19, P19.5, P21, P22 | 0006, 0042 | — | Now, command bar | G1–G4 | decided |
| K-1 | UI placement inside ADR-0014 IA | Now, Work, World, Control, Attention, inspector | P16–P22 | 0014 | — | — | design gates | exists |
| L-1 | Browser | SPA + launch code | P16 | 0011 | — | — | e2e | exists |
| L-2 | Desktop (Qt shell) | shell attach (S7) | P19 | 0011 | launch-code grant (D2 of P16) | — | P19 unification scenario; flicker gates carried | owned |
| L-3 | PWA | manifest + SW + tunnel | P15, P16 | 0010, 0011 | — | — | P18 manual install check | exists |
| L-4 | User-selectable themes | per-client `theme` / `contrast`, System default; Dark / Light / HC application themes; palettes stay tints | P19 | 0017, 0044 | — | Control → Appearance | T1–T6, contrast gates | decided |
| L-5 | Theme never changes orchestration semantics | fixed state colours; tints carry no meaning | P16, P19.5 | 0017, 0026 | — | all | design gates | exists |
| M-1 | Security never bypassed | brain `propose` only; policy route `admin`; narrowing-only auto-apply | P19, P24 | 0006, 0042 | — | — | G3, P24 cross-phase question | decided |

Gates G1–G14, AP-1 and T1–T6 are listed in F4 and in testing-strategy §8. The sixteen requirements
the decision pass named are traced with separate Core and API columns in Part H7.

---

## Part F — Phase ownership, Core/API dependencies, UI placement, gates

### F1. Phase ownership (§M questions 1–3)

**No new phase.** One standalone slice, **AP-1**, is added before multi-subscription routing can
be permitted (Part H3); everything else fits phases that exist:

| Phase | Owns from this pass |
|---|---|
| **AP-1** (standalone Core slice; after the C-22 slice, before any harness's ADR-0021 `rotation` is permitted) | ADR-0041 §1 consumption classes with the partition before ordering, §3 budgets always enforced on reported measures; set through the existing policy route and CLI |
| **P19** (inherited P16 seams, now named in the plan) | S1 per-mission threads; S3 chat `approve`/`reject`; S4 mission confirmation under `careful`; S7 Qt shell attach (with the persistent QtWebEngine profile ADR-0044 needs); S2 plan edit and S6 offline snapshot as before; **decided:** ADR-0042 routes 1–3 for account/harness directives (mission preferences already exist), the `route_explanation` card, the stale `NOT_YET` text; ADR-0044 theme and contrast preference in Control → Appearance |
| **P19.5** Core slice (unchanged scope) | Pause all; mission priority; **decided:** their grammar verbs (`pause all`, `resume all`, `reprioritise`) — the slice is already "ADR-0006 verbs through P9" |
| **P19.5** client | the routed resource on task rows (existing reads); the Resources form for *existing* policy fields (already listed) |
| **P21** | `live_work` in `/v1/status`; account consumption and the effective policy in `/v1/accounts`; the `status` verb over them; plan §28 gains "what is running" and "what is consuming each account" (already owns "model usage and cost") |
| **P22** | ADR-0041 §2 limits (subjects, tier), §4 project defaults and the Resources UI for every ADR-0041 field (AP-1's included); the route preview read and its use on the plan approval card; location/model directive kinds once the catalogue exists |
| **P24** | the cross-phase question below (F5) |
| **V1.x-O1 / O2** | `limits.task_families`; task pins; evidence-backed recommendations in the explanation |
| **post-V1** | remote worker nodes; the voice modality (Part H5) |

P20, P23, P25: no additions (P23's acceptance run covers what the phases build; P25's "how models
and harnesses are selected" page gains a paragraph on account consumption classes when built).

### F2. Core/API dependencies (§M questions 4–9)

| # | Dependency | Kind | Persistent record? | Security boundary | Phase |
|---|---|---|---|---|---|
| K12 | `ResourcePolicy.consumption` (AP-1); `.limits`, project `resource_preferences` (P22) | schema + router (partition before ordering, restriction reasons) | yes (policy versions, project field) | policy route keeps `admin`; project defaults set by user device | AP-1, P22 |
| K13 | budgets enforced whenever set, only on reported measures | router allocation step; policy write validation | no | — | AP-1 |
| K14 | `intent.v1.resource_directive`; resolution; asymmetric application; source recorded | brain schema + conversation write path | yes (directive source on preference/policy version) | brain `propose` only; widening/standing = user confirmation; policy change `admin` | P19 (accounts/harnesses), P22 (models/locations) |
| K15 | grammar verbs: `pause all`, `resume all`, `emergency stop`, `stop <running>`, `approve`/`reject` (S3), `reprioritise`, `use`/`don't use`, `what is running` | grammar | no | e-stop and destructive actions keep their confirmation and step-up | P19.5 Core slice, P19 |
| K16 | `live_work(conn)` → `/v1/status.live`; consumption + effective policy → `/v1/accounts` | read model (derivation) | no (derived from Execution, RouteDecision, UsageLedger, UsageSnapshot) | `observe` scope; no credentials or `home_ref` in the read | P21 |
| K17 | route preview per task | router in preview mode (pure, not recorded) | no | `observe` | P22 |
| K18 | `route_explanation` card on `why` | conversation | no (card references the decision) | — | P19 |

**Client-only** (§M question 5): the routed resource on task rows; rendering of the live and
consumption reads; the Resources form over existing fields; Control → Appearance for theme, contrast (ADR-0044,
P19), tint, density and motion (design system §3.3). **Orchestration-layer changes** (question 6): K12, K13, K17 only —
the mission loop is unchanged. **Provider/harness adapters** (question 7): none new beyond those
already owned (Codex for V1 release; the C-22 fix; pi execution adapter in V1.x-O4); remaining
capacity for non-Claude accounts needs each adapter to report a window or relies on budgets,
which is why K13 matters. **New persistent records** (question 8): only K12 fields and K14's source
reference; no new entity. **Security boundaries** (question 9): K14 and K15 (see F5).

### F3. UI placement (§K; Visual DNA mapping)

| Capability | Surface | Visual DNA rule |
|---|---|---|
| talk to Archeus; directives; answers | Now conversation; command bar; mission thread | reply arrives as a whole message with cards; the thread links a reply to what it touched (ADR-0026) |
| directive applied / proposed | mission card ("from your message"); change card in Attention | a proposal is attention (the user can act), never red |
| what is running, at a glance | operations strip; mark orbit | counts in words; still when idle (ADR-0024) |
| what each agent does | Happening now rows, chip, resource line; own-call rows | chip only from a re-read after an `execution.*` frame; own calls never animate |
| where work flows | operations map, graph halo / pulse / marker | motion only for real frames; no avatars, no office |
| per-step who and why | Plan tab (route preview before approval; resource after dispatch); Why tab | resource identity is text, never a colour (ADR-0026 §3) |
| accounts: running, consumed, left, policy | Control → Resources | unknown shown as "unknown"; a protected class is a word; nothing animates for a policy |
| decisions history | Why tab, O-6 Recent decisions, O-7 activity, P21 trace | — |

TUI parity through the same reads (P17 rule: both clients read one table).

### F4. Tests and gates (§M question 10)

Each gate is mutation-verified in the phase that builds it (testing-strategy §4).

| Gate | Asserts | Mutation it must kill |
|---|---|---|
| G1 | a chat `approve` produces the same PolicyDecision consumption, step-up and idempotency as the card button, bound to the displayed `action_hash` | approve without the hash; step-up skipped |
| G2 | `pause all`/`emergency stop` from conversation reach the same commands as the strip; e-stop asks for confirmation | verb bypasses confirmation |
| G3 | no brain output can apply a widening directive or any standing policy change without a user-device confirmation; the policy route stays `admin` | widening auto-applied; brain principal writes policy |
| G4 | a narrowing directive in the user's request appears on the mission's `resource_preferences` with its `message_id`; an unresolvable name yields a clarification, never a guessed id | guessed id; source dropped |
| G5 | `why` attaches a `route_explanation` card whose content equals the RouteDecision record | card text diverges from the record |
| G6 | `live_work` lists exactly the executions in live states and the own calls with no outcome; each item's `waits_on` matches its state; the `status` verb and `/v1/status` agree (one derivation) | an ended execution listed; verb and read diverge |
| G7 | the route preview for each plan task equals what the router decides at dispatch for an unchanged snapshot | preview computed differently from routing |
| G8 | an own call in flight is visible in `live_work` and in its account's consumers, and produces no motion | own call hidden; own call animates |
| G9 | a `last_resort` account is never elected while a `normal` candidate survives; when elected it follows its `fallback` (default ask); an `explicit_only` account is eliminated unless named by a user-device preference or pin | elected silently; brain-inferred preference unlocks it |
| G10 | a set budget eliminates a windowed account when reached; no budget → behaviour unchanged | budget skipped for windowed accounts |
| G11 | a mission inherits its project's default preferences and may narrow them; a project default is set only by a user device | inheritance lost; non-device write |
| G12 | consumption shows unknown capacity as unknown; no number is derived from `None` | `None` rendered as 0% or 100% |
| G13 | the effective policy read equals the inputs the router uses (parity over generated policies) | read and router diverge |
| G14 | a directive with an ambiguous or task scope applies to the mission only; "never" / "from now on" / project-wide produce a change card and change no policy until confirmed; a directive never removes an elimination made by policy, data class, limits, ceilings, budgets, provider terms or e-stop | "don't use A" mutates the global policy; a directive lifts a data-class elimination |
| AP-1 | **the protection invariant**: over generated snapshots, no `last_resort` account is elected while any `normal` candidate survives — whatever its affinity, preference or priority — and no `explicit_only` account is elected unless a user-device preference or pin names it; a budget set on a windowed account eliminates it when reached; a `cost_*` budget on an account that reports no cost is refused at write; unknown usage is never read as 0 | partition moved after ordering; affinity keeps a last-resort account; budget skipped when a window is readable; `None` read as 0 |
| T1–T6 | the theme gates of ADR-0044 (testing-strategy §8) | — |

### F5. Security

- The brain gains no scope. A directive is data in `intent.v1`, validated and resolved by Core;
  only narrowing applies without a confirmation, and only to the mission the user's own request
  creates or continues.
- Grammar verbs from a conversation carry the message's principal; they act only for a user
  principal (plan §27 "control verbs only from user principals"); a message whose text came from
  fetched content, meeting notes or agent output is never parsed as a command (existing rule).
- Destructive and irreversible verbs (e-stop, cancel) keep their confirmation and step-up; a chat
  `approve` is bound to the `action_hash` on screen, so text cannot approve an action the user has
  not seen (S3).
- A directive can only add constraints or preferences, or — once a user device confirms — lift a
  consumption class; it cannot remove any elimination (ADR-0042 §4, G14).
- `live_work` and consumption reads expose no credential, `home_ref` or key; they are `observe`.
- **P24 cross-phase question added:** "can any conversational message, brain reading or directive
  widen what an account, harness, model or location may be used for, or approve anything, without
  a user-device confirmation?" — no, by construction.

---

## Part G — Decisions for the user, undecided items, implementation order

### G1. Decisions (continuing the plan's D-1…D-12) — resolved in the decision pass

| ID | Decision | Resolution (Part H) |
|---|---|---|
| D-13 | Adopt ADR-0041…0043 | **DECIDED** — adopted with the smallest corrections (H1) |
| D-14 | Consumption classes `last_resort` and `explicit_only` | **DECIDED** with D-13 (ADR-0041 §1), plus the lift by a user-device preference |
| D-15 | Budgets enforced whenever set | **DECIDED** with D-13 (ADR-0041 §3), only on measures the adapter reports |
| D-16 | Narrowing directives | **DECIDED** — mission-scoped narrowing and preference apply, shown and reversible; widening and standing changes are confirmed; ambiguous scope reads as the mission (H2, ADR-0042 §3) |
| D-17 | Project default resource preferences | **DECIDED** with D-13 (ADR-0041 §4) |
| D-18 | When account protection lands | **DECIDED** — split: AP-1 (§1, §3) before any `rotation: permitted`; the rest in P21/P22 (H3) |
| D-19 | stop / pause all / emergency stop semantics | **DECIDED** with D-13 (ADR-0042 §1) |
| D-20 | "strongest" = top-tier requirement or pin | **DECIDED** with D-13 (ADR-0042 §2) |
| D-21 | Themes | **DECIDED** — per-client theme and contrast preference, System by default; palettes stay tints (H4, ADR-0044) |
| D-22 | P19 owns the inherited P16 seams | **DECIDED** — confirmed by the decision pass's P19 list |
| D-23 | live work and consumption inside existing reads | **DECIDED** with D-13 (ADR-0043 §2–§3) |
| D-24 | Carried: the orchestration plan's D-1…D-12 (ADR-0036…0040 PROPOSED), ADR-0021 (OPEN), Q-C1 | unchanged — still the user's |
| D-26 | Context capacity as a governed execution resource (context-capacity audit, 2026-10-01) | **OPEN** — ADR-0047 PROPOSED: the P12 pressure hand-off stays the mechanism; adds its recorded basis and derived quality, a no-progress guard, compaction unavailable in V1, `live_work.context`; owner P21 |

### G2. What remains undecided

- The orchestration plan's D-1…D-12, including D-2 (when the C-22 slice lands) and D-5
  (location values, which the location kind of ADR-0042 directives waits on).
- ADR-0021 provider terms per harness (OPEN) — the `rotation` answer is now bound to AP-1 (H3).
- Q-C1 (a "Classic appearance" from the legacy worlds) — untouched by D-21.
- Whether harness-internal subagents should ever be surfaced (only by an adapter recording
  SubagentStart/Stop; not proposed).
- Remaining-capacity reads for harnesses other than Claude Code (each adapter's to report; Codex
  rate limits from rollout files are specified in resource-router §4, not built).
- When the post-V1 voice modality and remote worker nodes are scheduled.

### G3. Recommended implementation order (report item 16)

Validated against the directive's proposed order (§N): its steps 1, 2, 4, 8, 9, 11, 12 are already
built or owned by P21/P22/V1.x-O; the order below inserts only what this pass adds.

1. **C-22 defect slice** (plan D-2) — unchanged, first.
2. **AP-1** — ADR-0041 §1 and §3; must precede any harness's ADR-0021 `rotation: permitted`
   (H3). Independent of P19.5 and of the C-22 slice's content; recommended right after it.
3. **P19.5** resumes at the user's word; its Core slice gains the `pause all` / `resume all` /
   `reprioritise` verbs (K15, part).
4. **P19** — client unification plus the named seams: Qt shell attach (S7), mission threads (S1),
   chat `approve`/`reject` (S3), mission confirmation (S4); ADR-0042 for accounts and harnesses
   (K14 part, K15 rest, K18); the ADR-0044 theme preference.
5. **P20** — unchanged.
6. **P21** — provenance and requirement provenance (owned) + `live_work`, consumption, effective
   policy (K16) + the Attention gap (plan K7).
7. **P22** — catalogue, descriptor, availability (owned) + the rest of ADR-0041 (K12) + route preview on
   the plan card (K17) + directive kinds for models and locations (K14 rest) + the Resources UI.
8. **P23 → P26** — unchanged.
9. **V1.x-O1…O5** — evidence, evaluation, pins, hand-off contracts, providers; `limits.task_families`.

Stop here: nothing above starts without the user's word; the decision pass recorded decisions,
not an instruction to implement.

---

## Part H — The decision pass (D-13, D-16, D-18, D-21)

Recorded 2026-09-30 at the user's direction ("architecture / decision pass only"). Every
resolution below is reflected in the ADRs, the plan, the orchestration plan, the resource router,
the domain model, the UI architecture, the design system and testing-strategy §8.

### H1. D-13 — ADR-0041, ADR-0042, ADR-0043: adopted

Each was checked against ADR-0005 (router), ADR-0006 (brain proposes, Core applies), ADR-0007
(policy first), ADR-0015 (conversation), ADR-0021 (provider terms), ADR-0024…0028 (Visual DNA),
ADR-0031…0035 (catalogue, evidence, data class) and the proposed ADR-0036…0040. None contradicts
them; all three are **DECIDED**. The smallest corrections made:

| ADR | Correction | Why |
|---|---|---|
| 0041 | `last_resort` is a **partition of the survivors before ordering**, not an ordering key; affinity cannot keep work on it once a `normal` candidate survives | the invariant must hold ahead of affinity, preference and priority |
| 0041 | a user-device preference or pin naming a protected account **lifts** its class for that scope only; a brain reading never does | "use account C only if I ask" needs a path, and it must not be conversational inference |
| 0041 | a budget is accepted only on a measure the adapter reports | a `cost_per_day` on an account whose ledger has no cost would be evaluated against a missing number |
| 0041 | implementation split into AP-1 / P21 / P22 / V1.x-O1 | D-18 |
| 0042 | the four directive kinds (narrowing, preference, widening, standing) and "ambiguous scope reads as the mission" | D-16: "don't use A for this" must never become a global policy change |
| 0042 | the explicit no-bypass list (§4) and one pipeline for every modality (§7) | the directive's "not an elevated privilege path" and the voice requirement |
| 0043 | model revision and served model in the live item | the visibility requirement names the revision |

Each ADR now closes with a record table: what it decides, what it amends, its phase, Core/API, UI,
tests, and what is intentionally deferred. **Model, Provider, Harness, Account, ExecutionNode and
Session remain six distinct concepts** (A4); no account is collapsed into a model, and "agent" is
execution metadata, not an entity (ADR-0043 §1).

### H2. D-16 — narrowing conversational directives: decided

**Mission-scoped narrowing versus standing resource policy** (ADR-0042 §3):

| The user says | Kind | What happens |
|---|---|---|
| "Don't use account A for this." | narrowing | A joins the mission's `forbidden_accounts`; card "from your message", reversible; the global policy is untouched |
| "Use account B for this mission." | preference (B `normal`) / widening (B protected) | B joins `preferred_accounts`; if B is `last_resort` or `explicit_only`, a change card first |
| "Keep this work local." | narrowing | the mission's data class narrows to `local_only` (ADR-0035) |
| "Don't use this harness for this task." | narrowing | the harness is forbidden for the **whole mission** until task-scoped preferences exist (V1.x-O2); the card says so |
| "Use this model if available." | preference | a model preference, applied among offers that already pass every step; a pin ("only this model") is widening |
| "Never use account A again." | standing | a change card proposing `consumption: explicit_only` (or DISABLED) on A's ResourcePolicy; confirmed only by a user device with `admin` |

A name Core cannot resolve to exactly one object is a clarification card. A directive only adds
constraints or preferences, or — once confirmed — lifts a consumption class; authorisation, P9
policy, project rules, data class, account limits, ceilings, budgets, provider terms, routing
rules, e-stop, verification and review apply unchanged. Only a message from a user principal can
carry one. **Conversation is another governed input path, not an elevated one.**

### H3. D-18 — when account protection lands: split, with an explicit dependency edge

**The fact that decides it.** Multi-subscription routing is already possible in the built router:
P10 and P11 route tasks across registered accounts, and the only thing stopping a second
subscription of a harness from being elected today is ADR-0021's `rotation` answer — while it is
not `permitted`, only the priority-1 subscription is used (`archeus/core/routing/router.py:198-206`).
Permitting rotation is one user command on an existing route, and nothing ties it to protection.
So the complete protection cannot simply wait for P22.

**A. What must exist before multi-account execution is allowed — slice AP-1:**

- `ResourcePolicy.consumption` (`normal` / `last_resort` / `explicit_only`) with the partition
  before ordering and the user-device lift (ADR-0041 §1);
- budgets, `concurrency` included, enforced whenever set, only on reported measures (§3) — this is
  what "do not consume all concurrent slots on account A" needs;
- both set through the existing `POST /v1/resource-policies/{id}` and the CLI — no new UI;
- every elimination and the partition recorded in the RouteDecision with its reason;
- the AP-1 gate (testing-strategy §8), mutation-verified.

Already built and part of the minimum: priority, preference, ceilings (`allocation_pct`,
`reserve_pct`, brain reserve), `project_allow` / `project_deny`, `fallback` modes, halting at the
ceiling, and unknown usage kept as `None` (never 0).

**B. What can safely remain later:** `limits` by subject and tier and project default preferences
(P22 — they refine *where*, not *whether*, and need project settings); the effective-policy read
(P21, with ADR-0043); the Resources UI for every field (P22); `limits.task_families`
(V1.x-O1). Until they land, "reserve account B for project X" is expressible with the built
`project_allow` plus a mission preference.

**C. Owners:** AP-1 — a standalone Core slice, like the C-22 defect slice; P21 — effective policy;
P22 — limits, project defaults, UI; V1.x-O1 — task-family limits.

**D. The dependency edge:** **AP-1 → ADR-0021 `rotation: permitted` for any harness.** Until AP-1
lands, `rotation` must stay unpermitted, so only one subscription per harness can be consumed and
no protected account can be reached by rotation at all. *(Finding 2026-10-01: incomplete for API-key
and proxy accounts and for Claude Code's unregistered own-call account — ADR-0041 "Why AP-1
first"; the extension is decision D-25.)* AP-1 depends on nothing after P10; it does
not touch P19.5 and does not expand its Core slice. Recommended order: right after the C-22 slice.

**Invariant, recorded in ADR-0041 and gated by AP-1: no router consumes a user-protected account
merely because it is eligible.**

### H4. D-21 — user-selectable themes: decided (ADR-0044)

- **Preferences:** `theme` ∈ `system` | `dark` | `light` and `contrast` ∈ `system` | `standard` |
  `high`, in Control → Appearance. First launch: `system` / `system`. `forced-colors` always wins.
- **Application themes are exactly** Archeus Dark, Archeus Light and High Contrast (dark and
  light). **Application theme ≠ thread tint**: the 39 legacy palettes stay tints; skins and worlds
  stay uncarried; a new application theme only as a full token set passing every gate, by
  amendment.
- **Stored per client registration** (the client's own storage, like the motion preference), not
  in the user profile, not synced; works offline (no Core read; a `'self'` boot script applies it
  before first paint; the cached shell includes it).
- **Per mode:** browser tab and Edge `--app` share the browser profile's storage for the Core
  origin (with an installed PWA on that origin); a tunnel PWA has its own; the Qt shell keeps a
  persistent QtWebEngine profile (part of S7) and never hardcodes a dark pre-load background; a
  non-default Core port shows `system` until chosen again.
- **Tokens:** one source; each theme emitted under an attribute selector plus the `system` media
  mapping; no value changes; every contrast gate runs over every theme × role as today.
- **TUI:** its own `--light` / `ARCHEUS_TUI_THEME` with the same names, default `dark`; it reads no
  SPA preference.
- **No semantic effect:** state colours fixed; nothing in orchestration reads the theme.
- **Phase:** P19. It is not a visual redesign and adds nothing to P19.5.

### H5. Validations the decision pass asked for

**JARVIS-like conversation.** Covered: natural-language requests and follow-ups (one primary
conversation with context packages; `continue_work`), clarification when information is missing
(clarification and challenge cards), explanation of decisions (`why` → the record; the
`route_explanation` card in P19), permission when required (approval cards; chat `approve`/`reject`
bound to the card, S3), control through natural language (grammar verbs and ADR-0042 directives),
mission interaction (mission threads, S1), status, resource and routing questions (ADR-0043 reads
through the `status` verb; P21). The boundary holds: **the brain proposes an intent or directive;
Core validates, authorises and executes the command**; no model mutates state; an unknown name is
a question.

**Voice** — a future modality, **owned post-V1** (plan §31.2 deferred list; design research D1
answered: not V1). It feeds the **same** pipeline: speech produces a user `Message` (its modality
recorded), which goes through the grammar, intent, directive and command path; replies may be
spoken; approvals and destructive confirmations are never accepted by voice alone (ADR-0042 §7).
Nothing in V1 prevents it: every interaction already is a message plus cards.

**Architecture → implementation → verification → review.** Covered by existing objects with
provenance: an architecture task producing an `architecture` artifact (ADR-0034), consumed at a
revision and binding implementation (ADR-0040, PROPOSED), routed per task by requirement
(ADR-0005/0033), verified by Core, reviewed independently away from the executor. **No role is
bound to a product**: "ChatGPT = architecture" or "Claude = implementation" can only be *routing
outcomes* of requirements, evidence under the user's rules, or the user's explicit pins; the
harness-id gate (ADR-0037) forbids writing them into orchestration code.

**Visibility.** Every item the decision pass lists — mission, task/plan step, harness, account,
model and revision, project/worktree, state, what it waits for, what it produced, the constraint
that affected routing — is a field of `live_work` (ADR-0043 §2) or of the RouteDecision, rendered in
Now (strip, Happening now), Work, the operations map, the inspector's Now/Plan/Why tabs and
Control → Resources. The mission stays the control-room unit; there is no agent dashboard.

**Account governance** — every phrase maps to a named, explained mechanism; none is a heuristic
and none branches on a provider:

| Phrase | Mechanism | When |
|---|---|---|
| "Prefer Claude account A." | preference (mission, project default) or priority | built (priority, mission); P22 (project) |
| "Don't use Claude account B unless necessary." | `consumption: last_resort` | AP-1 |
| "Reserve account B for project X." | `project_allow` on B + a project preference for B | built + P22 |
| "Never use account C automatically." | `consumption: explicit_only` | AP-1 |
| "Use account C only if I explicitly ask." | `explicit_only` lifted by a user-device preference or pin | AP-1 |
| "Keep at least part of account A's capacity available." | `reserve_pct` (ceiling = allocation − reserve) | built |
| "Do not consume all concurrent slots on account A." | `budgets.concurrency`, enforced always | AP-1 |
| "Use another eligible account if this one reaches its ceiling." | allocation elimination → next candidate; `fallback` modes; halt and hand-off | built |

**Model and harness evolution.** ADR-0031…0033 and ADR-0039 stand: models are catalogued with
exact revisions, harness versions are recorded (ADR-0037, P22), evidence is keyed to (revision,
harness version, task family), a new model routes nothing until approved, evidence annotates and
orders or excludes only under the user's standing rule, and releases, deprecations and capability
changes are catalogue events. No "strongest model wins" ranking exists; a top-tier need is an
explicit requirement or a pin (ADR-0042 §2).

**Advertised vs available (C-22).** Already properly assigned; not duplicated: ADR-0036 (PROPOSED)
separates *catalogued* (a model the harness advertises — kept and shown as catalogued, never hidden
globally) from an *offer* (a model this account can address) and gives each offer an availability
state with a reason; the defect fix is the standalone C-22 slice awaiting the orchestration plan's
D-2, and the Claude Code per-account list (C-20) is P22's. Control → Resources shows offers with
their state and the catalogue as a separate count ("1,354 more in pi's catalogue — not
configured").

### H6. Phase plan validation

| Phase | Checked | Result |
|---|---|---|
| C-22 slice | pi offers = pi's configured set | unchanged (plan D-2 pending) |
| AP-1 (new standalone slice) | minimum protection before `rotation: permitted` | **added**, edge AP-1 → ADR-0021 rotation |
| P19.5 | approved visual work separate; Core slice not expanded | unchanged: Pause all, readable e-stop, mission priority, and only the three verbs for those commands |
| P19 | Qt shell (S7, with a persistent profile), mission threads (S1), plan edit (S2), chat approve/reject (S3), confirmation (S4), offline snapshot (S6), account/harness directives, explanation card, theme preference | as listed; theme is the only addition beyond the audit |
| P20 | notifications (ntfy, P15 D20) and hardening | unchanged |
| P21 | live work, consumption, effective policy, status/resource answers, requirement provenance, Attention gap | unchanged from the audit |
| P22 | limits, project defaults, Resources UI, route preview, model/location directives, catalogue | account classes and budgets moved out to AP-1 (reason: H3) |
| V1.x-O | task pins, task-family limits, evidence-backed recommendations | unchanged |
| post-V1 | remote workers, voice | voice recorded here and in plan §31.2 |

No other work moved. The plan's dependency order (P19 → P19.5 → P20 → … ) is unchanged; AP-1 and the
C-22 slice are outside it, like other defect slices, bounded by the rotation edge.

### H7. The sixteen traced requirements

| # | Source requirement | Architectural decision | ADR | Phase | Core dependency | API dependency | UI surface | Test | Deferred |
|---|---|---|---|---|---|---|---|---|---|
| 1 | natural conversation | primary conversation + intent pipeline; context packages | 0006, 0015 | P7 (built); threads P19 | intent, brain | `POST /v1/conversations/{id}/messages` | Now composer, command bar | P7 grammar/intent tests | mission threads (P19) |
| 2 | JARVIS-like control | grammar verbs + directives → the same commands | 0042 | P19.5 (3 verbs), P19, P21 | grammar, `intent.v1.resource_directive` | existing command routes | Now cards, Attention change cards | G1–G5, G14 | voice (post-V1) |
| 3 | architecture → implementation delegation | architecture task → artifact → bound implementation → verification → review | 0034, 0040 | P21, V1.x-O3 | producer record, `inputs[]`, `conforms_to` | artifact reads | Plan, Evidence, Why | plan D4 "architecture binding" | ADR-0040 PROPOSED |
| 4 | multi-harness routing | (harness, account, offer) candidates; descriptor; no harness-id branches | 0005, 0037 | P10 (built), P22 | descriptor, Harness rows | `/v1/harnesses` | Resources | harness-id gate | Codex adapter for V1 release; ADR-0037 PROPOSED |
| 5 | multi-account routing | accounts as candidates; rotation behind ADR-0021 and AP-1 | 0005, 0021, 0041 | P10 (built), AP-1 | router | `/v1/accounts`, `/v1/provider-terms` | Resources | routing tests, AP-1 | — |
| 6 | account priority | priority + preference ahead of it | 0005, 0041 §4 | P10 (built), P22 (project) | router ordering | `/v1/resource-policies/{id}`, `/v1/missions/{id}/resources` | Resources, mission | routing tests, G11 | — |
| 7 | account protection | consumption classes partitioned before ordering; budgets always | 0041 | **AP-1**, P22 (UI) | router partition, allocation | existing policy route | policy route/CLI → Resources (P22) | AP-1, G9, G10 | limits by family (V1.x-O1) |
| 8 | account consumption visibility | consumption in `account_view`; unknown stays unknown | 0043 §3 | P21 | ledger aggregates | `/v1/accounts` | Resources | G8, G12 | other harnesses' windows |
| 9 | live-work visibility | `live_work`, no Agent entity | 0043 | P21 | `live_work(conn)` | `/v1/status.live` | strip, Happening now, map, inspector | G6, G8 | subagents (not proposed) |
| 10 | model / revision evolution | catalogue with revisions; routing status; revision-keyed evidence | 0031–0033, 0039 | P21, P22, V1.x-O1/O2 | Model/ModelOffer, `model_revision`, `served_model` | `/v1/models` | Resources → model inspector | P22 gates; plan D4 | evaluation (V1.x-O1) |
| 11 | harness evolution | `installed_version`, `harness.state_changed`, harness upgrade = catalogue diff | 0037, 0031 | P22 | discovery | `/v1/harnesses` | Resources | descriptor honesty gate | ADR-0037 PROPOSED |
| 12 | explanation of routing | RouteDecision explanation from the record; requirement provenance; card | 0005, 0033, 0042 | P10 (built), P21 (K5), P19 (card) | `requirements._source` | `/v1/route-decisions/{id}` | Why tab, `route_explanation` card | G5 | evidence annotation (V1.x-O2) |
| 13 | user-selectable themes | per-client theme + contrast, System default; tints stay tints | 0044, 0017 | P19 | none | none | Control → Appearance | T1–T6 | further application themes (by amendment); Q-C1 |
| 14 | browser / PWA / Qt compatibility | one SPA, no logic; per-mode theme storage; Qt attach with persistent profile | 0011, 0010, 0044 | P16 (browser), P15/P16 (PWA), P19 (Qt, S7) | launch-code grant | launch code, `/manifest.webmanifest`, `/sw.js` | all | P19 unification scenario, T5 | PWA manual install check (P18) |
| 15 | future voice | a modality feeding the same pipeline | 0042 §7 | post-V1 | none in V1 | none in V1 | Now | — (post-V1) | all of it |
| 16 | available vs advertised models | catalogue rows vs offers with availability and a reason | 0036 | C-22 slice, P22 | `offer_state`, pi `getAvailable()` | `/v1/models`, `/v1/harnesses` | Resources (offers vs catalogue count) | plan D4 rows 1–4 | ADR-0036 PROPOSED (D-1, D-2) |

### H8. Consistency check

The repository was searched for statements these decisions contradict (OS-only themes, no
conversational directives, advisory priority, skippable budgets, silently selectable protected
accounts, unavailable live work, an Agent entity, one harness/account only, evidence silently
steering, a separate voice pipeline, the Qt shell missing from P19, product-bound roles). Changed:
design system §3.3 and plan Appendix B.3 (OS-only theme rule, superseded by ADR-0044),
ui-architecture §4.6 (Appearance), resource-router §4–§5 (budgets and the partition), domain-model
§6 and §8.4, plan §11, §28 and §31.2 (directive, observability questions, voice, the AP-1 edge),
design research D1 (voice answered), the orchestration plan's pointer. Historical records (P16,
P17 design gates, the visual rulebook's question log) describe what was decided at the time and
are left as history. No product-bound role and no Agent entity was found anywhere in the V1
architecture; the only harness-id literals remain the two named legacy seams (ADR-0037 §4).

---

## Appendix — the acceptance checklist of §O

"Yes" means the architecture now has an explicit path with an owner; the right column says whether
it is built.

| Criterion | Answer | Where | Built? |
|---|---|---|---|
| Conversationally operated, not only form-operated | yes | A1; ADR-0006, 0015, 0042 | mostly (verbs, directives: P19/P19.5) |
| Conversation can produce governed plans | yes | A2 | yes |
| Plans contain multiple agent/model/harness steps | yes | A2; ADR-0034, 0040 | yes (per task routing) |
| Each execution has clear provenance | yes | A2; P21 fields | partly (P21) |
| I can see which agents are working and what they do | yes | C3, D5; ADR-0043 | partly (execution rows); P21 |
| I can see model/harness/account consumption | yes | ADR-0043 §3 | no — P21 |
| Multiple harnesses first-class | yes | A4; ADR-0037 | partly (Codex adapter, descriptor: V1 release, P22) |
| Multiple accounts first-class | yes | A4, A5 | yes |
| I can prioritise which account is consumed | yes | A5; D2 | yes (priority, preferences) |
| I can protect an account from automatic use | yes | ADR-0041; H3 | no — AP-1, before multi-subscription routing is permitted |
| Ceilings and account policies inspectable | yes | ADR-0041 §5, ADR-0043 §4 | partly — P21/P22 |
| Model selection considers task requirements | yes | A6 | yes |
| Selection decisions explainable | yes | A6; ADR-0005 | yes (text); card P19 |
| Model versions historically distinguishable | yes | A7; ADR-0031–0033 | P21/P22 |
| New releases discovered safely | yes | A7; ADR-0031 | P22 |
| New releases never silently rewrite routing | yes | ADR-0031 §4 | P22 |
| Observed performance can improve recommendations | yes | ADR-0032, 0033 | V1.x-O1/O2 |
| Critical routing changes stay under user control | yes | ADR-0033, 0038, 0041, 0042 | by construction |
| "Why did you choose this?" answerable | yes | `why`, RouteDecision | yes |
| "What is running now?" answerable | yes | ADR-0043 | partly — P21 |
| "What is consuming my accounts?" answerable | yes | ADR-0043 §3 | no — P21 |
| "Stop / pause / resume this work" governed | yes | A1; ADR-0042; D-19 | mostly (Pause all: P19.5) |
| Browser, desktop and PWA remain supported | yes | A10 | browser, PWA yes; Qt shell P19 (S7) |
| Multiple themes remain supported | yes | ADR-0044; H4 | three themes following the OS today; the per-client choice in P19 |
| None of this bypasses security | yes | F5; ADR-0042 §3 | by construction |
| No fake activity or decorative agent state | yes | ADR-0024 §7, ADR-0043 §5 | yes |
| Every new requirement has an owner | yes | Part E, F1 | — |
| Every Core dependency identified | yes | F2 (K12–K18) | — |
| Every UI requirement maps to the Visual DNA | yes | F3 | — |
| No implementation started because of the audit | yes | status line | — |
| Voice does not need a second pipeline | yes | ADR-0042 §7; H5 | post-V1 |
