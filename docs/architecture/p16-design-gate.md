# P16 design gate — GUI information architecture, visual system, interaction and motion

Status: **DESIGN GATE** (before implementation). Branch `archeus-v1-rearchitecture` at `93df428`
(P15 complete, CI green). Implementation starts only after this document is committed. Every
item marked **[new]** and every change to a frozen P1–P15 contract is a numbered decision (§25).

Evidence labels: **[V]** verified in source or by running it; **[D]** stated by an earlier gate or
the plan; **[I]** this gate's interpretation.

Sources read, in precedence order: the plan (§5, §21–§26, §28, §31.1 P3.5–P19, §33 Q4–Q8),
ui-architecture.md (whole, including §5.1, the graph carry-forward), the design research and
design system documents (whole), api-and-realtime.md (whole), domain-model.md (§1–§10),
state-machines.md (whole), testing-strategy.md (whole), external-references.md R7, and every
design gate from P4 to P15 for the items they deferred to P16 (§3.2). The code: `archeus/api/*`
(route table, server, auth, SSE, schemas, presence), `archeus/core/application/{queries,
executions,sessions,automations,authorization}.py`, `archeus/core/domain/{states,entities}.py`,
`archeus/core/world/{digest,status,inspection,drift}.py`, `archeus/harnesses/{base,fake}.py`,
`archeus/node/local.py`, `archeus/core/redact.py`, the migrations `0001`–`0011`, the P3.5b SPA
(`clients/app/*`), its e2e test and the `v1-client` CI job. Three inventories were made by
reading source, not documents: the legacy GUI (`claude_sessions/web/*`, `gui*.py`), every graph
capability in both codebases, and the Ship Notes Components repository (§22).

---

## 0. What P16 is, and what it is not

P16 turns the disposable P3.5b SPA (two read-only lists) into the V1 client: the information
architecture, the visual system, the interaction and motion system, responsive and accessible
behaviour, and the P15 surfaces that were deferred to it (pairing screen, QR, PWA manifest and
service worker, mobile layouts, device management).

**P16 owns** presentation. **P16 does not own** authorization (P9), routing (P10), execution
(P11), sessions and continuity (P12), verification and review (P13), events and automation
(P14), or access (P15). The client holds no business logic: every state on screen is a state
Core returned, every action is one Core command, and when the client needs a fact Core does not
expose, this gate names the missing seam (§3.3) instead of reconstructing it from unrelated data.

The rule that decides every conflict in this document: **the client may only *present*
authoritative rows. It may never *decide*** — not whether something is allowed, where it runs,
whether it is done, or what state it is in.

---

## 1. What exists [V]

### 1.1 The client

`clients/app/` is the P3.5b walking skeleton: `App.tsx` (two tabs, Now and Work, over
`GET /v1/missions`), `api/generated.ts` (the typed client, generated from the route table),
`api/stream.ts` (one SSE connection per browser: Web Locks leader + `BroadcastChannel`, ids-only
frames, re-query on notice, `RESYNC` on 410/`cursor_expired`), `api/transport.ts` (device token in
IndexedDB, launch-code bootstrap, `CoreError`). React 19 + Vite 8 + TypeScript 5.9, no router, no
query library (p3.5b D1 moved Q4 to P16). Strict CSP (`script-src 'self'`), no inline script, no
source maps. Core serves `index.html` at `/` and hashed files at `/assets/*` and nothing else.
The e2e test (`tests/v1/e2e/test_spa_skeleton.py`) asserts the launch device is read-only, the
page never polls, two tabs share one stream and the page survives a Core restart.

### 1.2 The API the client can use

95 routes (§3.1). Everything P4–P15 built is reachable except what §3.3 lists. Two facts that
shape the IA:

- **The launch-code device is `observe` only** (p3.5b D-scope, "because the P3.5b SPA is
  read-only"). The P16 client must approve, pause and pair, so this is revisited in **D2**
  (the user's decision, 2026-09-28: *the minter chooses*).
- **`pair/start` is local admin only** (P15 §6.1: "from `archeus pair` today, from the desktop
  SPA in P16"). With D2 the desktop SPA can start a pairing; a paired phone cannot.

### 1.3 Deferred to P16 by earlier gates [V]

| From | Deferred item | This gate |
|---|---|---|
| P3.5b D1 | Q4: TanStack Query, React Router | **D8**: neither |
| P3.5b D8, P11 §2/§14 | `GET /v1/executions/{id}/stream`, read through `adapter.inspect` | **D4**: built |
| P4 D4, §17 | `/v1/now` (embedding the digest); drift proposals in the UI; World views | **D3** (Attention) built; `/v1/now` **not built** (§3.3) |
| P4 §17 | "whether an observe device may ack" | unchanged: ack is `control` (§13) |
| P5 §3 | the *Why* tab rendering reasons and exclusions | built (§6.5) |
| P7 §3, P12 §4 | per-mission conversation threads (ADR-0015) | **DEFERRED** — backend seam S1 (§3.3) |
| P8 D15 | `POST /v1/plans/{id}/edit` | **DEFERRED** — seam S2 |
| P9 D19, §28 | approval cards; the chat verbs `approve`/`reject`; confirming a mission before `start` under `careful` | cards **built**; verbs and confirmation **DEFERRED** — seams S3, S4 |
| P10 §20 | the route-approval card and the resources UI | built (§6.4, §6.11) |
| P12 D17, §26 | `retry` if a surface needs it; a GUI for choosing hand-off targets | `retry` not needed (§6.9); hand-off dialog built |
| P14 §22 | the Attention surface ("there is no Attention entity; P16 builds that surface") | **D3** |
| P15 D20 | pairing and device screens, QR, PWA manifest and service worker, mobile layouts | built (§6.12, §16, **D6**) |
| plan §31.1 | "Qt shell attach" | **DEFERRED to P19** (deviation, §27) |
| ui-arch §5.1 | the Graph Capability & Graph Interaction System section | §20 |
| R7 | the Ship Notes evaluation | §22 |

---

## 2. The ontology the GUI exposes (§B)

Every noun below is a distinct thing on screen, with its own identity, state glyph and label.
None is collapsed into "job", "run", "agent" or "chat". The table is the contract the
presentation code (`clients/app/src/state/*`, `graph/relations.ts`) implements and the tests pin.

| Concept | What it is (authority) | Where it appears | Never shown as |
|---|---|---|---|
| **User** | the owner (single-user V1) | the presence line, "you" in decisions | a client |
| **Client** | one credentialed installation of a client program — the `Device` entity (P15 §4) | Control → Devices | physical hardware ("your phone") |
| **Device registration** | the Device row: `origin` local/paired, `client_type`, `host_label` (your name for it), declared `platform` | Devices row detail | a verified device identity |
| **Connection** | one open event stream of a client (P15 presence, in memory) | Devices row: `connected (2)`; the app's own connection status | a session, or "user is active" |
| **Session** | a durable provider conversation, bound to one harness and one account (P12) | Control → Sessions; mission Why/Relations | a mission, a connection, an execution |
| **Mission** | the outcome Archeus owns (Mission machine) | Work, mission inspector, Now | a chat, a job |
| **Task** | one unit of the plan's DAG (Task machine) | mission Plan tab | an execution |
| **Plan** / **plan version** | one immutable PlanVersion row; a mission's lineage of them | Plan tab with the version list | an approval, an execution |
| **Approval** | a PENDING/APPROVED/… row bound to an `action_hash` (P9) | Attention, mission header, cards | a policy decision |
| **Policy decision** | one evaluation, frozen (P9) | Why → Policy | an approval |
| **Execution** | one concrete attempt of one task (Execution machine, P11) | mission Now tab, execution detail | a session, a task |
| **Harness** | the runtime (`claude_code`, `fake`, …) | execution metadata, Resources | a model |
| **Model** | that harness's model id, a per-execution attribute | execution metadata, route decisions | the harness |
| **Account / resource** | an authenticated instance of a harness with its resource policy (P10) | execution metadata, Resources | a model or a harness |
| **Context** | an immutable ContextPackage: what was selected and why (P5) | Why → Context | knowledge |
| **Knowledge** | a KnowledgeItem with provenance, state and supersession chain (P6) | World → Knowledge, Attention proposals | context |
| **World / project / repository** | Project, Repository (+ architecture state, findings), inspections (P4) | World | a mission |
| **Verification** | evidence Core observed, per task or criterion (P13) | Evidence tab | an execution result |
| **Review** | a verdict on the mission result (P13) | Evidence tab | a verification |
| **Automation** / **automation run** | a rule and one of its firings (P14) | Control → Automations; Work lane | a mission |
| **Event** | a fact in the log (ids on the stream) | Timeline, Relations | a command |

The pairs the gate calls out, and how the screen keeps them apart [I]:

| Pair | How the UI keeps them distinct |
|---|---|
| session ≠ mission | Sessions live in Control → Sessions (infrastructure); a mission links to its sessions in Relations. A session row never shows a mission state glyph; a mission row never shows a session id. |
| session ≠ execution | an execution lists `session_id` as a relation, not as its name; a session lists the executions that ran in it |
| connection ≠ session | a connection appears only in Devices (count + presence); no session is created, resumed or named by a connection (P15 M13 is re-killed by P16's own test, §24) |
| client ≠ hardware | Devices groups by `host_label` and says "client" and "registered as"; "platform: ios (declared)" is labelled declared |
| harness ≠ model ≠ account | three labelled fields in every place resources appear, never one "AI model" string (§6.11, `resourceLine()` test) |
| plan ≠ execution | the Plan tab shows tasks; the Now tab shows executions; a task links to its attempts |
| verification ≠ execution | Evidence reads verifications; an `ENDED_OK` execution is rendered "exited ok — awaiting verification", never ✓ |
| automation ≠ mission | a run links to the mission it created; the run's own state is its own machine |
| event ≠ command | the Timeline lists events (past tense, actor, reason); commands are buttons, never listed as history until their event exists |

---

## 3. Backend surface (§S seams, §19)

### 3.1 Used as-is [V]

Missions (list, get, plan, plan versions, pause, resume, stop, resources), approvals (list, get,
decide), policies (get, rules, profile, simulate, decisions), verifications and reviews (list,
get, decide, review), executions (get, per task, stop, checkpoints, hand-off), sessions (list,
get, brief, create, resume, hand-off, link, close), conversation (messages, post, intent,
clarify), ideas, projects (list, get, create, constraints, inspections), status, digest + ack,
context package + preview, knowledge (list, get, confirm/reject/retract/supersede/forget),
feedback, route decisions, provider terms, harnesses, accounts, resource policies, automations
(list, get, simulate, run explanation, create, state), devices (list, revoke, pair start/redeem),
sync, health, e-stop, rearm, events and the stream.

### 3.2 Built by P16 [new] — four read routes, one command change, two static files

Each is a *query over authoritative rows* or a *transport* change. None adds a state, a guard, an
event type or a decision.

| Route | Scope | Why P16 and not later | Decision |
|---|---|---|---|
| `POST /v1/devices/launch/code` gains optional `{scopes}` | admin (unchanged, local only) | the interactive SPA needs `control`/`approve`/`admin` | **D2** |
| `GET /v1/attention` | observe | P14 §22: "P16 builds that surface"; composing it from per-mission lists is N+1 and would put "what needs you" logic in the client | **D3** |
| `GET /v1/executions/{id}/stream?from=` | observe | frozen to P16 by P3.5b D8 and P11 | **D4** |
| `GET /v1/missions/{id}/timeline?before=&limit=` | observe | the inspector's Timeline and "what changed on this mission" need events of the mission's rows; `/v1/events` has no subject filter | **D5** |
| `GET /sw.js`, `GET /manifest.webmanifest` | public (like `/`) | a service worker must be served from the scope it controls | **D6** |

### 3.3 Missing seams, not built [D17]

| Seam | What the GUI would need | Why not now | Where it goes |
|---|---|---|---|
| **S1** per-mission conversation | a Conversation per mission and the linking of turns (ADR-0015) | a P7 write-path change (which conversation a turn belongs to is intent's) | P19 |
| **S2** plan edit | `POST /v1/plans/{id}/edit` → a new PlanVersion through P8's validator | P8 plan semantics and P9 re-evaluation; an editor is a large surface; users revise through `request_changes` today | P19 |
| **S3** chat `approve`/`reject` verbs | a verb bound to a displayed card's `action_hash` | the P7 grammar change and the binding are P9's; cards cover the need | P19 |
| **S4** mission confirmation before `start` under `careful` | a lifecycle rule (P9 D5 "unchanged (P16)") | a mission-machine and policy change, not presentation | P19 (flagged to the user, §28) |
| **S5** `/v1/now` | one call for the Now surface | the SPA composes Now from digest + missions + attention (three existing reads); a fourth route would duplicate them | not planned |
| **S6** offline snapshot | last snapshot persisted for a cold offline start | the service worker caches the shell only; data is never cached (D6) | P19 |
| **S7** Qt shell attach | the desktop shell minting a launch code with D2 scopes and loading the V1 URL | touches the legacy shell; D2 is the mechanism it needs | P19 |
| **S8** `/v1/world/graph` | a focused neighbourhood query | P18 (§20.5) | P18 |
| **S9** meetings, decisions, people lists | World list kinds | no route lists meetings; Decision/Person/Organization have no table | P22 / later |
| **S10** Health metrics | `metrics_daily`, trace view | P21 | P21 |

---

## 4. Information architecture (§A, §C)

### 4.1 Decision

The IA of ADR-0014 is **adopted, re-derived from the P4–P15 ontology rather than from the design
research's wireframes** [I]. The test applied to every candidate destination: *is this a place the
user returns to, whose content is a set of domain objects the user acts on?* Only four pass; two
things are layers over every place; everything else is contextual.

| Level | What | Content (authoritative source) |
|---|---|---|
| Primary destination | **Now** | presence line (counts), since-you-left digest (`/v1/digest`), happening now (active missions), the top of Attention, the primary conversation and composer |
| Primary destination | **Work** | missions grouped by presentational state; ideas; automation runs (via automations); manual sessions are *not* here (they are infrastructure, §4.3) |
| Primary destination | **World** | projects (repositories, architecture state, findings, inspections), knowledge (with supersession and relations) |
| Primary destination | **Control** | Autonomy (policy), Automations, Resources (harnesses, accounts, route decisions, provider terms), Sessions, Devices, About (health, sync) |
| Global layer | **Attention** | `/v1/attention`: approvals, verifications waiting on a human, knowledge proposals, drift, missions blocked on you, suspended automations, accounts needing re-authentication |
| Global layer | **Command bar** (Ctrl/⌘+K) | jump to any loaded object; "Tell Archeus…" posts to the primary conversation — Core's grammar and intent pipeline decide what it means |
| Contextual | **Inspector** | one per object kind, opened over any destination by a deep link `#/o/<kind>/<id>` |
| Contextual | **Timeline** | inside the mission inspector (D5); global activity is the digest |
| Contextual | **Relations** (graph capability, §20) | a tab of every inspector: the object's authoritative relationships as a navigable structured list |

What is **not** a destination, with the reason:

| Candidate | Why not top-level |
|---|---|
| Conversation | a surface *inside* Now (principle 1: talk to Archeus, look at the world). Conversation can initiate and explain; it never holds state (§5) |
| Sessions | infrastructure (ADR-0004: mission is continuity); a return to work is a *mission* return. Sessions live in Control and in every mission's Relations |
| Executions / tasks | children of a mission; reached through it |
| Plans / approvals / policy decisions | children of a mission; approvals also surface in Attention |
| Graph | a capability and a visual language, not the IA (§20.5); P18's spatial view is a mode of World and of the Relations tab |
| Devices | rare; Control → Devices (and the pairing deep link) |

### 4.2 The navigation table

One flat table, `clients/app/src/nav/destinations.ts` — the repo's NAV lesson: one declaration,
everything derived (sidebar, bottom tabs, shortcuts, the command bar's "go to", the tests):

| id | Label | Desktop | Tablet | Phone | Shortcut |
|---|---|---|---|---|---|
| `now` | Now | sidebar | rail | tab 1 | Ctrl/⌘+1 |
| `work` | Work | sidebar | rail | tab 2 | Ctrl/⌘+2 |
| `world` | World | sidebar | rail | tab 3 | Ctrl/⌘+3 |
| `attention` | Attention | sidebar + badge | rail + badge | tab 4 + badge | Ctrl/⌘+J |
| `control` | Control | sidebar | rail | header menu | Ctrl/⌘+, |

Control's sections (the only second level): `autonomy`, `automations`, `resources`, `sessions`,
`devices`, `about`. *Notifications* and *Appearance* from ADR-0014 are cut to what exists:
notification channels are P20 (ntfy, D20 of P15), and appearance follows the OS (design system
§3.3) with one in-app choice, motion (§18.4), which lives in About.

Routes (hash-based, **D7**): `#/now`, `#/work`, `#/world`, `#/world/<project>`, `#/attention`,
`#/control/<section>`, `#/o/<kind>/<id>[/<tab>]`. The fragment keys `launch=` and `pair=` are the
two bootstraps and never routes.

### 4.3 Movement between the ontology's objects

```text
Now ──► mission inspector ──► Plan (versions) ──► task ──► executions ──► execution detail
 │            │   Evidence (verifications, reviews)          │ session, account, harness, model
 │            │   Why (context, policy decisions, routes)    └─► Control › Sessions › session
 │            │   Timeline (D5)   Relations (§20)
 ├─► Attention ──► the approval / verification / proposal inline, or its mission
 ├─► World ──► project ──► repositories, findings, inspections ──► its missions (Work filtered)
 │            knowledge ──► item (chain, relations) ──► source mission / meeting / decision
 └─► Control ──► Autonomy · Automations (runs ─► mission) · Resources · Sessions · Devices · About
```

Every edge in this diagram is an authoritative reference (a column or a body field listed in
§20.2), so a user can walk it without the client inferring anything.

---

## 5. Conversation (§D)

- **Surface, not application.** The primary conversation is a panel of Now: messages
  (`GET /v1/conversations/primary/messages`), the composer (`POST …/messages`). It is also
  reachable from the command bar ("Tell Archeus…").
- **Authority stays in objects.** A message renders its text plus its **cards** (P7 card types:
  mission, plan, approval, route_explanation, verification, digest, challenge, clarification,
  knowledge, idea, status, mission_proposal, diff). A card never renders a copy of the object from
  the message: it renders the *live row* its `ref` names (re-queried like any other view), so a
  card cannot be stale. A card whose ref cannot be read shows "unavailable".
- **Replies arrive whole** when `message.created` fires (ids-only stream; no token streaming).
  While a turn is being read, the composer shows the posted message with "sent — Archeus is
  reading it" from the `MessagePosted` response, and nothing else (no invented progress).
- **Challenge / clarification cards** are answered through `POST /v1/intents/{id}/clarify`
  (`proceed`/`drop` buttons, or a text answer) — P7's command, unchanged.
- **Control verbs are Core's.** The composer and the command bar send text. The client never
  parses `pause dashboard`: Core's grammar answers without a model. A client-side preview of a
  verb would be a second grammar, so the "Archeus will…" preview of the design system (§11) is
  **not built** [I]; the command bar instead offers the object actions (Pause mission *Dashboard*)
  as explicit buttons that call the route.
- **Disclosure:** Archeus's messages carry `aria-roledescription="AI-generated message"` and the
  label "Archeus" (design research §18).
- **Not built:** per-mission threads (S1), chat verbs `approve`/`reject` (S3).

---

## 6. Surfaces

### 6.1 Missions and the mission lifecycle (§E)

A mission row: state glyph + state label + title + project + one derived status line + age. The
**status line is derived only from rows**: the current task title while EXECUTING ("t3 of 5 ·
Implementing chart components" — "of" counts the plan's tasks), "Waiting: approve plan v2"
(APPROVAL_REQUIRED + its pending approval), the planning_blocked reason, the blocked reason, or
the state label. Never a token count, a session id or model prose.

**Presentation classes** (design system §10), generated from `clients/app/tokens/presentation.json`
into `src/state/presentation.ts`; a test fails when any state of any machine in `states.py` has
no class (**D9**):

| Class | Glyph | Mission states | Rule |
|---|---|---|---|
| planning | ◌ | CREATED, UNDERSTANDING, CONTEXT_GATHERING, REASONING, PLANNING, REPLANNING | Archeus is working it out; nothing runs |
| needs_you | ◆ | APPROVAL_REQUIRED | by definition waits on a human decision |
| approved | ◇ | APPROVED | approved, **not executing** yet |
| active | ● | EXECUTING, RESUMED | work may be running |
| verifying | ● + "Verifying" | VERIFYING | an Active sub-label, own label |
| reviewing | ● + "Reviewing" | REVIEWING | verified, **not accepted** |
| blocked | ■ | BLOCKED | cannot proceed; **"waiting on you"** is added only when Attention holds an item for the mission (§6.3) |
| paused | ‖ | PAUSED | |
| failed | ✕ | FAILED | red shared with blocked, glyph and label differ |
| done | ✓ | COMPLETED | verified **and** reviewed (the only ✓ for a mission) |
| inactive | – | CANCELLED | |

The four distinctions the gate requires are each a different glyph **and** label: proposed ≠
approved (◌/◆ vs ◇), approved ≠ executing (◇ vs ●), executing ≠ verified (● vs ● "Verifying"),
verified ≠ accepted (● "Reviewing" vs ✓). The mapping is a mutation target (§24: M01–M04).

**Mission inspector** — tabs, fixed order: **Outcome** (objective, success criteria with origin
explicit/inferred, requirements, constraints, project, autonomy profile, resource preferences) ·
**Plan** (§6.2) · **Now** (tasks in flight and their executions, §6.6) · **Evidence** (§6.7) ·
**Why** (§6.5) · **Timeline** (D5) · **Relations** (§20). Header: state, title, project, and the
mission's own actions — Pause / Resume (`control`, with `expected_version`), Stop (`control`),
"Request changes" and "Review" on REVIEWING (`approve`). Every action is disabled with its reason
when the client lacks the scope, when the connection is not live (§13), or when the state has no
such edge (the button is offered only from states whose table has the trigger; Core still judges).

### 6.2 Plans and plan versions (§G)

- The Plan tab reads `GET /v1/missions/{id}/plan`: the plan in force (tasks, `waves`,
  `serialised`, `estimated_cost` band, `current`/`current_why`, `in_force`, `eligible`) and every
  version (`plan_version`, `state`, `supersedes_plan_id`, `digest`).
- The version list is a lineage: `v3 PROPOSED ← v2 SUPERSEDED ← v1 SUPERSEDED`; any version opens
  read-only (`GET /v1/plans/{id}`). A superseded version is visibly distinct (struck state label,
  `text-3`), never rendered as current.
- Tasks are rendered by wave (parallel lanes), each with its key, title, kind, state glyph,
  `depends_on`, and approval points (tasks whose dispatch asked). Core's `serialised` edges are
  labelled "added by Core: may touch the same files" (P8's reason field).
- **Plan state vs approval vs execution** are three columns of fact, not one badge: "Plan v2 ·
  PROPOSED · validated, not approved" / "approval PENDING (expires 14:02)" / "no task running".
- Editing a plan is **not offered** (S2); the user asks for changes on the approval card
  (`request_changes`), which P9 turns into a new planning round.

### 6.3 Approvals and policy decisions (§H)

**Attention** (`GET /v1/attention`, D3) returns items, each `{kind, ref, mission_id, project_id,
state, reason_code, reason, since}` built from rows:

| kind | Source rows | reason_code |
|---|---|---|
| `approval` | Approval PENDING | `plan` / `task` / `action` / `route` (its kind) |
| `verification` | Verification AWAITING_HUMAN; ERROR holding its mission | `acceptance` / `verifier_error` |
| `knowledge` | KnowledgeItem CANDIDATE | its type |
| `drift` | Repository DRIFTED | `drifted` |
| `mission` | Mission BLOCKED with `planning_blocked` (a question or a policy block) | `planning_blocked.kind` |
| `automation` | Automation SUSPENDED | `suspended` |
| `account` | Account UNAUTHENTICATED | `reauth` |

Ordering is fixed and explained (kind order above, then oldest first); there is no score. The
route adds **nothing** a row does not say: whether an approval is *eligible* is P9's
`approval_view`, reused.

**The approval card** (the cross-surface contract, ui-architecture §4.10), from the Approval row
only: kind, **the canonical action** (`presented` in mono: items, target, argv, diff hash — never
model prose alone), **why it asks** (the PolicyDecision behind it: matched rules, scope, locked),
**what a rejection does** ("the mission stops at this step" for a task/action; "planning resumes
with your note" for request_changes), **expiry** (absolute time + relative), step-up requirement
from `step_up` and the client's derived capability (`local` / `pin` / `none` — `none` disables
Approve with "this client has no PIN: it cannot satisfy step-up"). Approve and Reject are equal
size; `step_up` or a destructive item puts Reject first. The decide command echoes the displayed
`action_hash`, carries an idempotency key per *card instance* (a double tap is one decision) and
`expected_version`. After deciding, the card re-reads the row: "Approved on *this client* 14:02",
or, when another client decided first, the row's state ("Approved — decided on another client").
The eligibility reason (`eligible_why`) is shown verbatim when not eligible, and Approve is
disabled.

A **policy decision** is never rendered as an approval: Why → Policy lists decisions (stage,
decision, outcome, reason, matched rules, policy version), each linking to the approval it
produced, if any.

"Why is this blocked / awaiting / denied / executing / failed / awaiting verification?" (§P) —
answered by one component, `explainState()`, fed only by rows: planning_blocked (kind, question
or policy reason), pending approval (kind, expiry, eligibility), the latest policy decision of
stage dispatch/action when DENY, the latest route decision (`result` blocked/ask with its
explanation and `unblock_at`), the execution's `stop_reason`/`exit_reason`, the verification's
state and failing checks, the review verdict. When no row explains a state, it says so
("no recorded reason") rather than guessing.

### 6.4 Model × harness × account (§9)

Traced through P9–P15 [V]: P9's decisions bind actions, never resources; P10's RouteDecision
records `harness_id`, `account_id`, `model`, `effort`, `result`, `fallback_from`, candidates and
the explanation; P11's Execution carries `harness_id`, `account_id`, `model`, `effort`,
`route_decision_id`; P12's Session is bound to (harness, account) with its recorded model/effort,
and a hand-off names a target harness (and optional account/model/effort); P15 carries none
(verified: no P15 route or field accepts one).

The GUI:

- shows **harness, model and account as three labelled fields** everywhere they appear
  (execution metadata, route decision rows, session rows, review `reviewer_resource`), through one
  function `resourceLine()` whose test fails if any two are merged or one is dropped;
- explains a selection from the RouteDecision only: selected (harness · account · model · effort),
  result (selected / fallback / ask / blocked), `fallback_from`, candidates with the step that
  eliminated each and its reason, the explanation text Core generated — **no model reasoning is
  shown or implied**;
- offers **selection controls only where the backend has a command**, and each control calls that
  command: mission resource preferences (`POST /v1/missions/{id}/resources`, admin: preferred /
  forbidden harnesses and accounts, `max_cost_band` — two separate multi-selects, never a merged
  "model" picker), session resume (`model`, `effort` in the session's own harness vocabulary) and
  session hand-off (target **harness** required; account, model, effort optional — separate
  fields). A route approval (fallback `ask`) is an Attention item decided through P9;
- never filters, orders or pre-selects candidates itself: the harness list and account list are
  shown as Core returns them; a model field is free text validated by Core (a harness's model
  vocabulary is the adapter's, ADR-0022);
- supports future multi-harness workflows because nothing on screen assumes one harness: a
  mission's executions may each name a different harness; a session hand-off crosses harnesses.

### 6.5 Context and knowledge (§F)

- **Why → Context** renders the mission's ContextPackage (embedded in `GET /v1/missions/{id}`):
  per level L0–L4 the items (ref, store, type, freshness, reason, tokens, conflicts_with), the
  budget used/limit, **excluded** items with their reason and freshness, conflicts with the
  preferred item and why, `assumptions` and `missing_information`. `stale` and `superseded`
  are labelled, never hidden. The package's `as_of_seq` is shown ("as of event 18233").
- **World → Knowledge** lists items (type, state, scope, provenance: `source_kind`, `source_ref`,
  `observed_at`, the route decision and context package that produced a model-derived item). An
  item's inspector shows its supersession **chain** (oldest first, the current one marked) and its
  **relations** with `rel` and `confidence_tier` (EXTRACTED / INFERRED / AMBIGUOUS, drawn solid /
  dashed / dotted in the Relations tab and labelled in text). Actions: confirm, reject, retract,
  supersede (title + text), forget (dry-run first, then confirm) — P6's commands.
- Knowledge ≠ context: the Why tab says "selected for this mission"; World says "known".

### 6.6 Execution and live runtime (§I)

- The **Now** tab lists the mission's tasks that are ROUTING / RUNNING / AWAITING_APPROVAL /
  VERIFYING / PAUSED, each with its executions (`GET /v1/tasks/{id}/executions`), attempt number,
  execution state glyph, harness · account · model, started/ended, `stop_reason`, `exit_reason`,
  `handoff_from` (a hand-off chain is rendered as "continued from attempt 2's execution").
- **Execution presentation** (its own table in `presentation.json`): INTENT/STARTING
  "starting", RUNNING "running", AWAITING_APPROVAL ◆, PAUSING/PAUSED ‖, HANDING_OFF "handing
  off", STOPPING, LOST "lost (Core is reconciling)", ENDED_OK **"exited ok — not verified"** (never
  ✓), ENDED_HANDOFF "handed off", ENDED_ERROR/ENDED_KILLED/ENDED_REJECTED/ABANDONED ✕ with the
  reason. The task's own state (VERIFYING, SUCCEEDED) is what may show ✓.
- **Execution detail** (`#/o/execution/<id>`): metadata, checkpoints
  (`GET /v1/executions/{id}/checkpoints`: trigger, next action, files changed, decisions, open
  problems), Stop and Hand off buttons (`control`), and the **output tail** read from
  `GET /v1/executions/{id}/stream` (D4) — subscribed only while the detail is open, re-read on
  `execution.progress` for this execution, rendered as the last 200 events in a windowed list,
  every string redacted by Core. Output is data: rendered as text, never HTML or markdown.
- Live: `execution.*`, `task.*` events re-query the rows on screen (§14). No row animates because
  it exists; an execution that produced output since the last look gets one opacity pulse (§18).

### 6.7 Verification and review (§J)

- **Evidence** reads `GET /v1/missions/{id}/verifications` and `…/reviews`. A verification
  renders its subject (task key or criterion text), verifier, state (PENDING / RUNNING / PASSED ✓
  / FAILED ✕ / ERROR "verifier error — not a failure of the work" / AWAITING_HUMAN ◆), the revision
  checked, every check (name, kind, result, exit code, detail, evidence availability from
  `GET /v1/verifications/{id}`), `independent`, and who performed/decided it.
- A **review** renders reviewer, verdict, `independent` (false → the caption "reviewed on the same
  resource — no other was free"), requirements met/missing, risks, regressions, follow-ups.
- Human actions (scope `approve`): accept/reject an AWAITING_HUMAN verification
  (`POST /v1/verifications/{id}/decide`), record your own review on a REVIEWING mission
  (`POST /v1/missions/{id}/review`: accept / changes_requested / reject + note), abandon a
  conflicting merge (`POST /v1/tasks/{id}/integration/abandon`, `control`).
- The mission is "Done ✓" only in COMPLETED, which only P13's accepting review reaches. The GUI
  never infers completion from verifications.

### 6.8 World, projects, repositories (§K)

- **World** lists projects (`/v1/projects`: name, state, root paths, repositories with kind
  repo/submodule/worktree and `architecture_state`), with a "missions" count linking to Work
  filtered by project (`?project=`). Knowledge is World's second list.
- **Project page** (`#/world/<id>`): repositories with architecture state (UNKNOWN, CONSISTENT,
  STALE, DRIFTED — its own presentation table), last revision, findings (constraint, status
  violated/satisfied/unchecked, reason, violations), inspections (`…/inspections`: revision,
  state, failure), declared constraints (knowledge items with a `constraint`); actions: declare a
  constraint (`control`), create a project (`admin`, from World).
- Drift appears in Attention as a `drift` item linking here. Its three resolutions (update
  architecture, accept, fix mission) are not fired by any P4–P15 route (P4 §5: "not fired before
  P6"; P6 did not add routes), so the page shows the findings and **no resolution buttons** [V] —
  seam recorded with S9's world gaps.

### 6.9 Sessions, continuity, resume, hand-off (§M, §8)

The P12 model shown correctly [V]:

- **Control → Sessions** lists sessions (`/v1/sessions`: harness, mode, state OPEN/CLOSED/LOST,
  project, mission, account, model, effort, `handoff_from_session_id`). A session row shows
  **no mission state** and **is not a mission**.
- **Session inspector**: identity (harness, account, model, effort, mode, cwd), **lineage**
  (`lineage` ancestors and `targets` from `GET /v1/sessions/{id}`), the linked mission, and the
  **brief** (`GET /v1/sessions/{id}/brief`): **what mattered** (the mission's objective, criteria
  and current state from `brief.mission`), **what changed** (`brief.changes` since the session's
  own cursor, P4's digest scoped), **what is unresolved** (open problems / next action from the
  latest checkpoint; pending approvals of the mission), **what to see next** (the mission's
  current explain-state, §6.3). The transcript is **never replayed** (continuity is
  reconstruction, P12 D6/H1); the brief says "as of event N" and flags a stale context package
  ("rebuilt at resume").
- Actions: **Resume** (`POST /v1/sessions/{id}/resume`: request id per click, optional model and
  effort *of this session's harness*, deliver the brief), **Hand off** (target harness required,
  account/model/effort optional, reason; the source is unchanged and the dialog says so), **Link
  to mission**, **Close**. A duplicate request (`duplicate: true`) is shown as "already requested"
  (§14).
- **Interruption / recovery**: LOST is rendered "provider session not found — Core looked and it
  is gone"; a Core restart changes no session, and the UI does not show one as interrupted
  because the stream reconnected (connection ≠ session).
- **Cross-harness continuity**: lineage rows name each session's harness, so a chain
  `claude_code → pi` reads as two sessions of two harnesses continuing one mission — the harness is
  an attribute of each session, never the identity of the continuity.
- "What changed while I was away" at the product level is the **digest** on Now (§6.10) —
  grouped, headline per group, acknowledged per user on any client; not a replay.

### 6.10 Now (the return)

Composed from three reads (S5): the digest (`/v1/digest`: groups with headline needs_you /
drift_found / failed / completed / drift_cleared / progressed, counts, `truncated`), missions not
settled (Happening now), and the first three Attention items. The presence line is counts only:
"Archeus · 2 missions active · 1 needs you" (never personality text). **Dismiss** acks the
digest up to its `up_to_seq` (`control`); acknowledging on one client clears it on all (S14).

### 6.11 Control

- **Autonomy**: the user profile (careful / standard / autonomous) with each profile's table
  (from `/v1/policies`), user rules (scope, class, decision, locked, match, boundary, revision,
  retired), create/retire rule and set profile (`admin`), and **Simulate** (`POST
  /v1/policies/simulate`, observe): an action class + target → decision + reason. The client
  never evaluates a rule.
- **Automations** (§L — automation ≠ mission: a run is its own machine and *links* to the
  mission it created; Work shows a mission's `origin: automation` with a link to its run): list with state (DRAFT / PENDING_APPROVAL / ENABLED / DISABLED / SUSPENDED /
  ARCHIVED), trigger and template shown as the stored JSON rendered as a readable rule, recent
  runs (state, depth, reason_code, reason, mission link), simulate (last N days, observe),
  enable/disable/archive (`admin`), a run's explanation (`GET /v1/automation-runs/{id}`: event →
  run → why → mission and its lineage).
- **Resources**: harnesses (installed, capabilities, enforcement, structured output, models,
  execution/calls), accounts (health, auth kind, resource policy: priority, allocation, reserves,
  fallback, budgets; latest usage), route decisions (list; each opens the explanation), provider
  terms. Resource-policy edits and account enable/disable are `admin` commands.
- **Sessions**: §6.9.
- **Devices**: §6.12.
- **About**: `/v1/health` (Core version, schema, ports, workers), `/v1/sync` (this client, Core
  instance, head/floor seq, server time), the motion preference, e-stop / rearm (`control`, with a
  confirmation dialog in full prose).

### 6.12 Clients, devices, presence, pairing (§N, §13)

- **Devices** lists clients (`/v1/devices`) grouped by `host_label` ("unlabelled" otherwise),
  each: name, `client_type`, declared platform ("declared"), origin (local / paired), scopes,
  expiry, step-up capability, state (ACTIVE / REVOKED), presence (`connected (n streams)` /
  `recent` / `absent` / `revoked`, with `last_seen_at`). This client is marked "this client". The
  copy says what presence means: "connected = an event stream is open; it does not mean someone is
  using it."
- **Revoke** (`admin`) with a full-prose confirmation ("This client loses access at once and its
  open streams close. It cannot be undone; the client must be paired again."). Revoking *this*
  client signs this page out.
- **Pair a client** (`admin`, **local only** — the button is offered only when this client's
  origin is local, and Core enforces it): name, host label, scopes (observe always; control,
  approve; admin opt-in with a warning) → `POST /v1/devices/pair/start` → the code, a 120-second
  countdown, the `url` when a remote host is configured, and a **QR code** of that URL (drawn
  locally, **D10**). Without a remote host, the screen explains that pairing a phone needs
  `archeus core --remote-host <name>` and a tunnel (ADR-0010, PROPOSED), and still shows the code
  for a client on this machine or network path.
- **Redeem** (`#pair=<code>`, public): the SPA reads the fragment, removes it at once, asks for a
  client name and an optional 6–12 digit PIN ("used to confirm step-up approvals"), and calls
  `POST /v1/devices/pair/redeem`. `401 invalid_pairing_code` → "this code is not valid any more —
  start a new pairing on the computer running Archeus"; `429 pairing_locked` → the lockout and
  `Retry-After`.
- A **disconnected client never cancels anything**; the UI states it on the reconnect banner
  ("work on the computer continues").

---

## 7. Graph / provenance / causality (§O) — summary; §20 is the full section

The graph is **a capability and a visual language**, not the IA. P16 builds its *relationship
view as structured lists* — the Relations tab and the provenance chains — from authoritative
fields only (`graph/relations.ts`, a typed edge mapper whose every edge names the column it came
from), and P18 builds the spatial renderer over the same mapping. No inferred edge, no event
graph, no reasoning.

---

## 8. Responsive and mobile (§P, §15) — summary; §16 is the full section

Three layouts from one table: desktop (sidebar + main + inspector column), tablet (icon rail +
main; inspector as an overlay panel), phone (bottom tab bar Now · Work · World · Attention;
Control in the header menu; inspectors and approvals as full-height sheets). What is primary on a
phone: Attention and Now. Graph (P18) is hidden below 600 px; its list equivalent (Relations) is
the default everywhere.

---

## 9. Accessibility (§Q) — summary; §17 is the full section

Landmarks, skip link, one `h1` per view, focus moved to the view heading on navigation and
restored when an inspector or dialog closes, `Esc` closes the topmost overlay, roving tabindex in
tablists, every state glyph paired with a text label, live regions (polite rate-limited; one
assertive announcement per new approval), reduced motion and forced colours honoured, targets
≥ 28 px desktop / 44 px phone, axe-core run in the e2e suite.

---

## 10. Error, stale, reconnect, offline (§R) — summary; §13–§14 are the full sections

The app has one **connection state** (connecting · live · reconnecting · resynced · offline ·
unauthenticated · revoked) and every view has a **freshness** (current · stale · reconnecting ·
unavailable), derived from the stream status and `X-Archeus-Seq`. Stale data is shown *labelled*,
never as current; commands are disabled while not live.

---

## 11. Migration from the legacy GUI (§S) — summary; §21 is the table

The legacy GUI (`claude_sessions/web/*`, 21 pages + 9 project tabs) keeps running unchanged until
the P22 retirement gate. Its IA is not preserved; its disciplines are (flat tables, transform-only
motion, one parked loop, container queries, contrast floors, dead-space audits). Harness
configuration pages (hooks, plugins, skills, agents, MCP, output styles) have **no V1 backend** and
stay LEGACY in the legacy app.

---

## 12. Performance for long and live lists (§T)

| Data | Strategy |
|---|---|
| mission list | fetched once per view; re-queried on `mission.*` (coalesced, §14.2); rendered grouped; groups beyond 50 rows render the first 50 + "show N more" (no virtualization dependency; a mission list is small) |
| event timeline (D5) | pages of 50 by `before=` cursor, "load older"; newest first; nothing loads until the tab opens |
| execution output (D4) | read only while the detail is open; offset-resumed (`from=`); the client keeps the last 500 events and renders the last 200 in a windowed list (`content-visibility: auto` rows); `ponytail:` the route reads the remainder of the stream file from the offset — fine for a tail, a byte cap is the upgrade |
| conversation | the primary conversation, newest 100 rendered, "load older" |
| knowledge / sessions / devices / automations | full lists (single-user sizes); filtered client-side |
| graph (P18) | focus-first, depth 2, 1,000-node budget (§20.15) |
| SSE | one stream per browser; frames only *invalidate* cache keys; invalidations coalesce per animation-free tick (one microtask/50 ms batch), so a burst of 100 `execution.progress` frames is one re-query per visible key |
| motion | never per row across a list; one pulse per changed object at most every 2 s |

Rendering discipline: a frame invalidates **keys**, and only components subscribed to those keys
re-render (the cache's per-key listeners); the application never re-renders the whole tree on an
event (§14.2, tested by counting fetches per frame).

---

## 13. Realtime, freshness, offline and reconnect (§R, §14) — full

### 13.1 Connection state (one machine, `src/data/connection.ts`)

| State | Entered when | UI |
|---|---|---|
| `connecting` | first load, before the stream answers | "Connecting…" |
| `live` | the stream is open and has delivered its first frame or heartbeat | nothing (quiet) |
| `reconnecting` | the stream dropped; retrying with back-off | banner "Reconnecting — what you see may be out of date"; views **stale** |
| `resynced` | a new stream opened after a drop, or 410 `cursor_expired` | every cache key invalidated and re-read; banner "Back — refreshed" for 4 s, then `live` |
| `offline` | `navigator.onLine === false` or fetches fail with a network error | banner "Offline since 14:02 — nothing you do here is sent. Work on the computer running Archeus continues." |
| `unauthenticated` | 401 on the stream or a read | the sign-in explanation (open from the desktop / pair again) |
| `revoked` | 401 after this client was listed REVOKED, or the stream closed by revocation | "This client's access was revoked" |

### 13.2 Freshness per view

Each cached read records the `X-Archeus-Seq` Core sent with it (P15: the head read before the
handler's own read) and the connection generation it was read in. A view is:

- **current** — read in the current live generation;
- **stale** — the connection is not `live`, or the view's seq is older than a stream frame that
  invalidated it and the re-read has not arrived (shown "updating…" only after 1 s);
- **reconnecting** — during `reconnecting`;
- **unavailable** — the read failed (404, 403, network): the view says which, never an empty
  list.

The freshness is a mutation target (M07, M08). Stale data stays on screen *labelled*; nothing is
removed because the connection dropped.

### 13.3 Commands under each state

| Case | Behaviour |
|---|---|
| not `live` | every command button disabled: "Not connected — nothing is sent while reconnecting" |
| queued command | **the SPA never queues** a command (P15 D18 allows only the digest ack; the SPA does not queue even that). A command is sent now or not at all |
| queued intent refused (`409 queued_intent_refused`) | shown verbatim if ever received ("Archeus refused a command sent late") |
| duplicate / idempotent retry | each command carries a key generated **per user action**; a network retry reuses it, so Core applies it once; a replayed answer (`changed: false`, `duplicate: true`) is shown "already done" |
| `409 version_conflict` | "This changed since you opened it" + the view re-reads; the user acts again on the new state (never auto-retried) |
| `403 scope_required` / `not_permitted` | "This client does not hold the *approve* scope" (the scope Core named) |
| `422 guard_failed` / `invalid_transition` | Core's reason verbatim ("the plan in force is not newer than the one decided") |
| `423 policy_denied` | the decision and reason; links to the policy decision |
| `409 approval_not_eligible` | `why` verbatim |
| revoked client | the `revoked` state (§13.1) |
| remote-access restriction (`403 host_not_allowed`, local-only route through a tunnel) | "Only from the computer running Archeus" |
| `503 core_starting` / `busy` | "Archeus is starting" / retried once after `Retry-After`, with the same key |

No optimistic state: after a command the view re-reads; the new state appears when Core has it.

### 13.4 Reconnect protocol (P15 §13, used as designed)

On a new stream after a drop: `GET /v1/sync`; if `core.instance` changed (Core restarted) or the
stored cursor is below `floor_seq`, the leader resumes live from the head and invalidates every
key; otherwise it resumes with `Last-Event-ID` (the existing `stream.ts`). Either way views
re-read authoritative state; the client never replays local assumptions.

### 13.5 Service worker and offline shell (D6)

`/sw.js` caches the **shell** only (`/`, the hashed `/assets/*`), network-first for `/` so an
upgraded Core's SPA wins, cache-first for hashed assets. It never touches `/v1/*`: no API
response, no token, no event is ever cached by it. Offline with a cached shell, the app opens,
finds no Core, and shows `offline` with nothing to act on.

---

## 14. Data layer (D8)

### 14.1 Cache

`src/data/cache.ts`: a map `path → {data, seq, gen, error, listeners}`; `useRead(path)` subscribes
a component to one key and fetches on first use; `invalidate(pred)` marks keys and re-reads only
those with listeners. No TanStack Query (Q4): the only semantics needed are "cache by path,
invalidate by event, re-read"; one hook does it, in ~100 lines, with no dependency to audit [I].

### 14.2 Invalidation (one table, `src/data/invalidation.ts`)

A frame `{type, subject}` maps to key predicates by rule, e.g. `mission.*` with subject
`mission/<id>` → `/v1/missions`, `/v1/missions/<id>*`, `/v1/attention`, `/v1/digest`;
`execution.progress` → `/v1/executions/<id>*` only; `approval.*` → `/v1/approvals*`,
`/v1/attention`, the approval's mission; `device.*` → `/v1/devices`; unknown types → nothing
(re-read is the only effect; a missing rule makes a view late, never wrong — ADR-0009). Frames
coalesce per 50 ms batch. The table is tested (every registered event type in
`core/domain/events.py` has a rule or an explicit "none").

---

## 15. Visual system (§U, §11)

Built only after §2–§14. The design system (ARCHEUS_V1_DESIGN_SYSTEM.md) is **adopted** with the
values below frozen by the contrast gate (Q5).

### 15.1 Tokens (one table, D9)

`clients/app/tokens/tokens.json` (hex-first) → generated `src/styles/tokens.css` (custom
properties, per theme under `prefers-color-scheme` / `prefers-contrast: more`) and
`src/state/tokens.ts`; the P17 TUI reads the same JSON (ANSI derivation is P17's). A test
regenerates and compares; the contrast test reads the JSON.

| Role | Dark | Light | Floor (tested) |
|---|---|---|---|
| `bg` | `#0E1116` | `#F7F8FA` | — |
| `surface-1` | `#141922` | `#FFFFFF` | — |
| `surface-2` | `#1A2130` | `#F1F3F6` | — |
| `surface-3` | `#202838` | `#FFFFFF` | — |
| `line` / `line-strong` | `#2A3344` / `#3A4558` | `#DDE1E7` / `#B9C0CB` | — |
| `text` | `#E6EAF0` | `#11151C` | ≥ 4.5 on every surface |
| `text-2` | `#AAB3C0` | `#4A5463` | ≥ 4.5 on every surface |
| `text-3` | `#8A94A3` | `#6A7382` | ≥ 3.0 on every surface |
| `primary` (fill) / `on-primary` | `#E6EAF0` / `#0E1116` | `#11151C` / `#FFFFFF` | ≥ 4.5 |
| `thread` | `#F4F1EA` | `#11151C` | ≥ 3.0 on `surface-1` |
| `focus` | `#FFD166` | `#8A4B00` | ≥ 3.0 on every surface |
| `state.active` | `#5AA9FF` | `#0B63CE` | ≥ 4.5 on `surface-1` (labels use it) |
| `state.attention` | `#F2B544` | `#8A5600` | ≥ 4.5 |
| `state.blocked` | `#F07178` | `#B3261E` | ≥ 4.5 |
| `state.paused` | `#A7B0BD` | `#5B6472` | ≥ 4.5 |
| `state.thinking` | `#B79CFF` | `#6A45C9` | ≥ 4.5 |
| `state.done` | `#5FD08B` | `#1E7F45` | ≥ 4.5 |

(Light `state.attention` moves `#9A6100` → `#8A5600` and light `focus` is set to `#8A4B00`: the
proposed values are validated, and nudged where they miss a floor, by the gate itself, as the repo
does for palettes.) Any two state colours differ by CIE76 ΔE ≥ 20 within a theme, except
blocked/failed, which share red by design (design system §3.2) and are told apart by glyph.

High contrast (`prefers-contrast: more`): solid surfaces, `text-3` → `text-2`, 2 px lines,
no row tints. `forced-colors: active`: system colours, glyphs and labels carry every state.

### 15.2 Typography, spacing, surfaces, density

- Type scale as design system §4 (desktop 13/20 body, phone 17/24 below 600 px), rem-based,
  `tabular-nums` for numbers, system fonts only (Segoe UI Variable / system-ui; Cascadia Mono /
  Consolas / ui-monospace), no web fonts.
- 4 px spacing scale `0 2 4 8 12 16 24 32 48 64`; comfortable density (compact is not built).
- Layers: base (`surface-1`, no border, hairline separators, radius 0), raised (inspector, cards:
  `surface-2`, 1 px line, radius 8), overlay (sheets, dialogs, command bar: `surface-3`, 1 px
  line-strong, radius 12/16). No gradients, no `backdrop-filter`, no blur, no blend modes (Qt tear
  lesson); overlays are opaque.
- **Lists over cards**: a mission is a row; cards are the unit only inside the conversation and
  Attention.

### 15.3 Iconography

No icon font, no CDN: a handful of inline SVG glyphs drawn on a 20 px grid at 1.5 px stroke for
the five destinations and the object kinds, each with a text label or accessible name. The state
glyphs are text characters (● ◆ ■ ‖ ◌ ✓ ✕ – ◇), the same set the TUI will use.

### 15.4 Status treatment, authority and provenance

- A state is always **glyph + label** (+ colour); never colour alone.
- **Authority**: a value Core computed (a count, a state, a band) is plain; a value that is
  *derived by the client for display* (the status line, relative times) is never styled as data
  (no mono, no badge); a value a model produced (a plan summary, a review summary, a knowledge
  item from a pass) carries the provenance line ("from the planner · route rd_…").
- **Confidence/provenance** of relations: EXTRACTED solid, INFERRED dashed, AMBIGUOUS dotted, and
  the word, always.
- **Attention** uses the one attention colour; **blocking** uses red ■ with the reason; **stale**
  uses `text-3` plus the word "stale" / "as of …"; **errors** are inline next to the thing.

### 15.5 Controls, focus, keyboard

Buttons: primary = neutral inverted fill (one per view), secondary = outlined, destructive =
outlined red text + confirmation. Disabled = 40% opacity **and** a reason (`title` and
`aria-describedby`). Focus: 2 px `focus` ring at 2 px offset on `:focus-visible`, never removed.
Keyboard: see §17.

### 15.6 Breakpoints

Chrome only (media queries): phone `< 600 px`, tablet `600–999 px`, desktop `≥ 1000 px`.
Components read their container (`@container`), the repo's rule, tested (§24).

### 15.7 Data visualization and graph language

Numbers as numbers (tables with right-aligned tabular figures); at most one inline bar for
usage (utilisation vs ceiling, reserve hatched — the only chart P16 draws). The graph language
(§20.10) is fine lines, state colour only on missions, neutral for everything else.

---

## 16. Responsive and mobile — full (§15)

| Element | Desktop ≥ 1000 | Tablet 600–999 | Phone < 600 |
|---|---|---|---|
| Navigation | sidebar 232 px | icon rail 64 px (labels as accessible names + tooltips) | bottom tab bar (Now, Work, World, Attention), Control in the header menu |
| Inspector | right column (min 360, max 560) beside the list | overlay panel from the right, focus-trapped | full-height sheet, grabber, `Esc`/back closes; swiping down is "decide later" |
| Approvals | inline in Attention and the inspector | same | a sheet with the canonical action, step-up PIN pad when the client's step-up is `pin`; Approve/Reject in the lower half |
| Execution status | Now tab of the inspector | same | the mission sheet's Now section; output tail collapsed behind "Show output" |
| Conversation + mission context | side by side on Now (conversation left, happening now right) | stacked | Now shows digest + happening now + composer; the conversation below |
| Graph (P18) | a mode of World/Relations | same | hidden; Relations list only |
| Persistent | connection banner, Attention badge | same | same, plus the tab bar |

Touch: 44 px targets below 600 px, no hover-only information (hover styles only under
`@media (hover: hover)`), safe-area insets for the tab bar. PWA: `manifest.webmanifest`
(name, short name, start URL `/`, display standalone, theme and background colours from the
tokens, one SVG icon + a PNG). Text scaling: layouts survive 200% at 390 px wide without
horizontal scroll (audited, §24).

---

## 17. Accessibility — full (§Q, §16)

| Concern | Design | Test |
|---|---|---|
| structure | `header`, `nav` (labelled "Destinations"), `main`, `aside` (inspector, labelled by its title), one `h1` per view | e2e + axe |
| skip link | "Skip to content" first focusable | e2e |
| keyboard | Tab order follows reading order; Ctrl/⌘+1…4, Ctrl/⌘+J, Ctrl/⌘+K, `Esc`; tablists with roving tabindex (←/→/Home/End); lists: ↑/↓ moves between rows, Enter opens | e2e (keyboard-only journey) |
| focus management | on route change focus moves to the view's `h1` (`tabindex=-1`); opening an inspector/dialog moves focus into it and traps it (dialogs); closing restores the opener | e2e |
| screen readers | state glyphs are `aria-hidden` with the label as text; cards are `article` with `aria-label`; Archeus messages carry `aria-roledescription`; counts in badges have text ("2 need you") | unit + axe |
| live updates | one polite live region, rate-limited to one announcement per 5 s ("Mission *X* is now verifying"); one assertive announcement per new approval; nothing announces per execution progress frame | unit (rate limiter) |
| dialogs | `role=dialog`, `aria-modal`, labelled, `Esc` closes, focus trapped and restored | e2e |
| approval flows | the canonical action is text, not an image; buttons say what they do ("Approve push", "Reject"); step-up PIN input has a label and `inputmode=numeric` | e2e |
| colour independence | every state has glyph + label; relation tiers have line style + word | unit (presentation table has glyph and label for every class) |
| contrast | §15.1 floors over tokens × themes | `tests/v1/design/test_contrast.py` |
| reduced motion | `prefers-reduced-motion: reduce` or the About setting → no travel, no pulse, cross-fades only | design test + e2e (emulated) |
| forced colours | `forced-colors: active` rules keep outlines and glyphs | design test (rule present) |
| targets | 28 px desktop, 44 px phone | e2e (measures interactive elements at 390 px) |
| graph | P18 renderer has a list equivalent; P16's Relations *is* the list | §20.13 |

---

## 18. Motion and interaction system (§V)

Designed after §15; it reports **real state changes only**.

### 18.1 Rules (binding, carried from the repo and the design system)

1. Animate only `transform` and `opacity`. No other property in any `@keyframes` or
   `transition` (test parses the built CSS).
2. No ambient or infinite loop: no `infinite`, no `animation-iteration-count` > 1, no `steps()`.
3. No animation because an item exists: lists mount without entrance animation; a row animates
   only when **its object changed state** while on screen.
4. No per-item animation across long or live lists: at most one pulse per object per 2 s, and
   the pulse is one 240 ms opacity step.
5. One animation loop for the app and it parks: P16 needs **no** `requestAnimationFrame` loop
   at all (CSS only). P18's renderer will own the one loop (parked on hidden/blur/reduced
   motion/context loss — Ship Notes' voice-orb lifecycle is the same rule, §22).
6. Reduced motion (OS or the About setting): transitions become 0 ms, pulses and the thread
   travel are removed; state still changes instantly with glyph + label.
7. Motion never carries state alone: every animated change also changes text.
8. Hidden model reasoning is never animated: no "thinking" orb, spinner or shimmer stands for a
   model at work. "Planning" is a glyph ◌ and a label from the mission state; an in-flight command
   shows an inline spinner **inside the button that sent it**, stopped by the response.

### 18.2 The motion table

| Motion | Trigger (a real state change) | Duration / easing | Properties |
|---|---|---|---|
| state change | a row's state differs from the last render of that row | 160 ms, `cubic-bezier(.22,.8,.18,1)` | glyph `opacity` 0→1, `translateY(2px)`→0 |
| changed-since-you-looked rule (the thread in lists) | the row's object changed after the digest cursor | static 2 px left rule; removed by `opacity` 200 ms on ack | opacity |
| output pulse | `execution.progress` for a visible execution, ≤ 1 per 2 s | 240 ms ease-out, once | opacity |
| inspector open/close | user opens/closes | 220 ms `cubic-bezier(.22,.8,.18,1)` | `translateX` + opacity |
| sheet open/close (phone) | user | 280 ms same curve | `translateY` + opacity |
| dialog | user | 160 ms | opacity + `scale(.98)`→1 |
| button press | pointer down | instant | `scale(.98)` |
| link-out affordance | hover (pointer: fine only) | 160 ms | `translate(2px,-2px)` of the arrow |
| toast | an off-screen success | 160 ms in, 4 s, 160 ms out | opacity |

The one easing curve is Ship Notes' `cubic-bezier(.22,.8,.18,1)` (ADAPT, §22) at the design
system's durations, not its 750 ms.

### 18.3 Interaction patterns

Roving-tabindex tablists (Ship Notes' project-stack keyboard pattern, ADOPT), pressed scale,
focus-visible ring, confirmation dialogs for irreversible actions in full prose, undo is not
offered where Core has no inverse command (the UI never simulates one), inline errors next to the
control, one toast at a time and only for off-screen outcomes.

### 18.4 The motion preference

`About → Motion: follow the system | reduced`. Stored in `localStorage` (a display preference,
not state). `html[data-motion="reduced"]` applies the reduced-motion rules. Tested by emulation.

---

## 19. Boundaries — the GUI holds no shadow system (§19)

| Temptation | What the GUI does instead | Test |
|---|---|---|
| decide if an action is allowed (shadow P9) | calls the route; renders `eligible`/`eligible_why`, scopes and the error; disables only to explain, Core still judges | a static test: no module under `src/` imports or re-implements policy terms (`ALLOW_WITHIN_BOUNDARY` evaluation); e2e: a disabled button is enabled when the scope is present and Core still refuses a stale version |
| pick a resource (shadow P10) | shows RouteDecisions; controls call `missions/{id}/resources` or session commands | `resourceLine` test; no client code orders candidates |
| infer execution state (shadow P11) | renders Execution rows; never marks ENDED_OK as success | presentation mutation M05 |
| build a session from a connection (shadow P12) | connection state never touches sessions | M13 re-killed (P16 test) |
| infer verification (shadow P13) | renders Verification rows; "Done" only for COMPLETED | M03, M04 |
| treat an event payload as state (shadow P14) | frames only invalidate cache keys | a unit test: the stream handler reads `type`/`subject` only |
| optimistic state | none: every command is followed by a re-read | e2e counts: no state appears before its GET |
| client grammar | text goes to Core | static test: no verb table in `src/` |

---

## 20. Graph Capability & Graph Interaction System (ui-architecture §5.1)

### 20.1 Existing graph capability inventory [V]

Read from source (file:line in the inventory notes kept with this gate's working papers; the key
locations are below).

| # | Existing capability | Technical location | What it represents | Current consumer | Current UI exposure | Architectural value | P16 disposition | Reason |
|---|---|---|---|---|---|---|---|---|
| G1 | Code hierarchy + import graph builder | `claude_sessions/connections.py:build_hierarchy` (Python AST, C/C++, C#, relative JS resolvers) | root/repo/dir/file nodes with containment; file→file dependency edges weighted by import count; caps (12k files, depth 12, 8k edges) and `truncated` | legacy `/graph`, graph-lite, TUI, `memory._module_graph`, **V1 `world/inspection.inspect`** | legacy `/graph` window, TUI | high: it is P4's authoritative import-graph extractor | **ADOPT** (already adopted by P4; unchanged) | the V1 world's repository structure and P4 drift both stand on it |
| G2 | `top_repos` | `connections.py:top_repos` | top-N depth-1 repos | TUI, graph-lite | TUI list | low | **PRESERVE-BEHIND-UI** | legacy consumers only; V1 has repositories as rows |
| G3 | Memory graph as a hierarchy | `connections.py:build_memory_hierarchy` | graph.json entities/lessons/agents as the hierarchy schema | legacy `/graph` Memory view | legacy | medium (legacy knowledge view) | **PRESERVE-BEHIND-UI** until P22 | V1 knowledge is KnowledgeItem + Relation; the legacy graph.json is imported by P22 (`ENTITY` items) |
| G4 | 2D canvas graph renderer (progressive disclosure, edge lifting to visible ancestor, zones, force layout with spatial grid, cage/dot LOD at 250 nodes, search-to-expand, focus+context dimming) | `connections.py:_HTML_TEMPLATE`, `render_html` | an interactive standalone page | legacy `/graph`, TUI `o` | legacy window | high as *interaction design*; not reusable as code (inline template string, CPU canvas, no keyboard/ARIA/reduced motion) | **ADAPT** → P18 | P18 reuses its proven mechanisms — edge lifting to the nearest visible ancestor, expand/collapse by parent, focus+context neighbourhood dimming, search-expands-ancestors, the 250-node dot fallback as LOD — in `clients/app/src/graph/`, adding the keyboard, ARIA and reduced-motion layer it lacks |
| G5 | legacy `/graph` route | `claude_sessions/gui.py:630`, `_serve_graph` | the renderer over a project | legacy tab strip | legacy window | legacy | **PRESERVE-BEHIND-UI** (LEGACY) until P22 | legacy app keeps working (ui-arch §8) |
| G6 | Semantic memory graph (`graph.json`) | `claude_sessions/memory.py` | LLM + deterministic entities, relations (name-keyed, no tier), module edges, lessons | recall hook, Memory tab, digests | legacy Memory tab | high (current product's memory) | **PRESERVE-BEHIND-UI** (LEGACY), imported by **P22** | V1's knowledge store is `knowledge_items` + `relations` (ADR-0012/0013); graph.json is legacy-owned until cutover (ADR-0019) |
| G7 | Recall graph expansion (BM25 RRF seeds + 1–2 hop relation expansion, token budget) | `claude_sessions/recall.py:expand_relations`, `retrieve` | task-relevant subgraph selection | `recall_hook` (every prompt) | Memory tab preview | high | **PRESERVE-BEHIND-UI** | a retrieval algorithm, not a view; V1 context (P5) reuses `lexical.py` from it; relation expansion in V1 context is a P5 follow-up, not a UI concern |
| G8 | Lexical BM25 | `claude_sessions/lexical.py` | scoring | recall, V1 `infra/search/bm25.py` | none | high | **ADOPT** (already, P5) | unchanged |
| G9 | Entity one-hop drill-down ("Connected to", open neighbour) | `gui_api.py:api_memory_entity`, `app.js entDetail` | walk the graph one node at a time from a list | legacy Memory drawer | legacy drawer | **high as a pattern** — it is the accessible list form of graph traversal | **ADAPT** → P16 Relations tab | the Relations tab is exactly this pattern over V1's authoritative edges: each relation a row, each neighbour a link that opens its inspector |
| G10 | Memory state counts | `gui_api.py:api_memory_state` | counts | legacy Memory tab | legacy | low | **PRESERVE-BEHIND-UI** | legacy |
| G11 | graph-lite | `gui_api.py:api_graph_lite` | compact module shape | TUI palette only | none | low | **PRESERVE-BEHIND-UI** | TUI-only consumer; V1 has no module-graph route (S8) |
| G12 | Session flow graph builder (event DAG over time; lanes = sidechains; call→result edges; claude/codex/pi parsers; streaming, 20k-event cap) | `claude_sessions/flowgraph.py` | one transcript as a causal timeline | legacy `/flow`, `/api/flow/live` | legacy "Flow" window, dashboard strip | high (the one real causal-timeline builder) | **DEFER** to P19/P21 | a *transcript* view: V1 continuity is reconstruction, not replay (P12); its V1 role is an investigation view of one execution's output (P21 trace), over P11's normalised stream (D4), not a session UI |
| G13 | Flow page renderer (lanes, gap clamping, label thinning, culling, Space play, Esc) | `claude_sessions/web/flow.js` | timeline canvas | `/flow` | legacy window | medium | **DEFER** with G12 | same |
| G14 | Live flow strip (trail instrument) | `gui_api._strip_of`, `instruments.js trail` | last N events per live session | legacy dashboard | legacy | low | **REJECT** for V1 | an ambient per-session ticker on the home screen is the "metrics dashboard home" V1 replaces (research §8); P16's output tail lives in execution detail |
| G15 | Workspace node map instrument (projects sized by tokens, linked by shared account) | `app.js:1885`, `instruments.js flow` | projects × accounts | legacy dashboard | legacy | low; the "shared account" edge is not a domain relation in V1 | **REJECT** for V1 | encodes spend, not world relationships; V1 World lists projects |
| G16 | Background three.js graph scene (40 synthetic clusters) | `claude_sessions/web/stage.js:graph` | decoration, not data | legacy app background | legacy | none as data; high as craft | **REJECT** as a V1 surface (ADR-0016); its flat-scene lineage stays the **DEFERRED** candidate for P18's optional 3D mode | not data-driven; V1 motion reports state only |
| G17 | Cluster spec, single source + generator + parity test | `claude_sessions/cluster_spec.py`, `tools/gen_cluster_spec.py`, `tests/test_cluster_parity.py` | visual constants of the cluster glyph | connections.py, stage.js, www scene | indirect | medium (the *pattern* of one generated visual spec) | **PRESERVE-BEHIND-UI**; its pattern **ADOPTED** by D9 | the one-spec-many-renderers discipline is what `tokens.json` + `presentation.json` + `gen_ui.py` repeat |
| G18 | www journey scene | `www/components/journey/scene.ts` | decorative stations | website | site | marketing | **PRESERVE-BEHIND-UI** (P25 owns the site) | not an app surface |
| G19 | "graph" skin/world | `themes.py`, `app.js` | theme | legacy | legacy | none for V1 (ADR-0017) | **REJECT** for V1 (Q7) | V1 has one product language |
| G20 | CLAUDE.md import map | `claude_md.resolve_memory_files` | instruction file tree | legacy CLAUDE.md tab | legacy | low | **PRESERVE-BEHIND-UI** (LEGACY) | harness configuration, legacy |
| G21 | Graph GIF capture | `tools/capture_graph_gif.py` | docs asset tool | docs | n/a | low | **PRESERVE-BEHIND-UI** | tooling |
| G22 | V1 Relation entity + table (typed, polymorphic, tiered EXTRACTED/INFERRED/AMBIGUOUS; indexes both ends) | `entities.Relation`, `0005_knowledge.sql` | the world/knowledge graph of record | knowledge commands, `get_knowledge` | none | **the** V1 knowledge graph | **ADOPT** | Relations tab renders it (knowledge items); P18 renders it spatially |
| G23 | `relate()` writer | `application/knowledge.py:relate` | dedupe + `relation.created` | knowledge passes, supersede, feedback, decisions, lessons | none | high | **ADOPT** (unchanged; P16 writes no relation) | the GUI never writes an edge |
| G24 | Knowledge supersession chain | `knowledge.confirm/supersede`, `queries.get_knowledge` | linear chain + `supersedes` relations | `GET /v1/knowledge/{id}` | none | high | **ADOPT** | Knowledge inspector renders `chain` + relations |
| G25 | Plan task DAG + waves + Core `serialised` edges | `planning/validate.py`, `queries.get_plan` | task dependency graph | `GET /v1/plans/{id}` | none | high | **ADOPT** | Plan tab lanes; Relations "depends on" |
| G26 | Plan version lineage | `queries.mission_plan` | `supersedes_plan_id` chain | `GET /v1/missions/{id}/plan` | none | high | **ADOPT** | Plan tab version list; Relations |
| G27 | Automation run explanation (event → run → why → mission → plans/decisions/routes/executions/verifications/reviews) | `automations.explain` | provenance fan-out of one run | `GET /v1/automation-runs/{id}` | none | **high — the only built causal chain across P9–P14** | **ADOPT** | Automations run inspector renders it as the causal chain (§20.8) |
| G28 | Event `cause_chain` | `domain/events.py`, writer | causes of an event (automation-populated) | events, explain | none | medium | **ADOPT** for display only | Timeline shows "caused by" when present; never inferred when absent |
| G29 | Session hand-off lineage (`lineage`, `targets`) | `sessions.view` | session → session | `GET /v1/sessions/{id}` | none | high | **ADOPT** | Session inspector lineage; Relations |
| G30 | Execution hand-off chain (`handoff_from`) | `execution/manager.py`, body field | execution → execution | execution view | none | high | **ADOPT** | Now tab "continued from"; Relations |
| G31 | Verification lineage (task → execution → route/session) | `application/verification.py` | what was verified, on which attempt | verification rows (`execution_id`, `performed_by`) | none | high | **ADOPT** through its rows | Evidence and Relations read `execution_id` |
| G32 | V1 repository import-graph payload (files, edges) | `world/inspection.inspect`, artifact | per-revision module graph | drift, diff, knowledge pass | **not exposed** (no route) | high | **PRESERVE-BEHIND-UI** now; **DEFER** exposure to P18 (S8) | a graph route is P18's; P16 shows findings, not the graph |
| G33 | Drift evaluation over import edges | `world/drift.py:evaluate` | constraint checks | world worker → `Repository.findings` | project view | high | **ADOPT** | Project page renders findings with violating edges as text |
| G34 | Digest grouping (event → mission folding) | `world/digest.py` | what changed, per object | `GET /v1/digest` | none | high | **ADOPT** | Now digest |
| G35 | Context package references + conflicts | `context/assemble.py` | selected/excluded refs and constraint conflicts | missions, `GET /v1/context/{id}` | none | high | **ADOPT** | Why → Context |

### 20.2 Graph-to-ontology mapping — which things are genuinely relationships

Authoritative edges only; each names the field it is read from. Everything not listed stays a
list, table, timeline or detail view.

| Edge (source → target) | Field | Genuinely a graph relationship? | Shown as |
|---|---|---|---|
| project → repository | `repositories.project_id` | containment | project page list; Relations |
| repository → inspection | `repository_inspections.repository_id` | history | inspections table |
| repository → finding (constraint) | `Repository.findings[].constraint_id` | constraint | findings table |
| mission → project | `missions.project_id` | scope | header; Relations |
| mission → plan version | `plans.mission_id`; version → previous `supersedes_plan_id` | **lineage** | Plan version list; Relations |
| plan → task | `tasks.plan_id` | containment | Plan tab |
| task → task | `Task.depends_on`, `Plan.serialised` | **dependency DAG** | Plan lanes; Relations |
| task → execution | `executions.task_id` | attempts | Now tab |
| execution → execution | `Execution.handoff_from` | **continuation** | "continued from" |
| execution → session | `Execution.session_id` | runs-in | Relations |
| execution → route decision | `Execution.route_decision_id` | **selection** | Why → Route |
| execution → harness / account / model | `harness_id`, `account_id`, `model` | attributes (not nodes in P16) | metadata row |
| execution → checkpoint | `checkpoints.execution_id` | derived state | execution detail |
| session → session | `handoff_from_session_id` | **lineage** | session lineage |
| session → mission | `sessions.mission_id` | link | Relations |
| verification → task / mission criterion | `Verification.subject` | evidence | Evidence |
| verification → execution | `Verification.execution_id` | **provenance** | Evidence; Relations |
| review → mission (+ plan) | `reviews.mission_id`, `plan_id` | verdict | Evidence |
| approval → mission / plan / task / execution | `approvals.*_id` | gate | Attention; Relations |
| policy decision → approval | `PolicyDecision.approval_id` | decision→gate | Why → Policy |
| mission → context package | `Mission.context_package_id` | selection | Why → Context |
| knowledge → knowledge | `Relation` (`rel`, `confidence_tier`); `supersedes_id` | **world/knowledge graph** | Knowledge inspector; Relations |
| knowledge → meeting / mission | `Relation decided_in / learned_from` | provenance | Relations |
| automation → run → mission | `automation_runs.automation_id`, `mission_id` | **causality** | run explanation |
| event → run | `automation_runs.triggering_event_seq` | **causality** | run explanation |
| event → cause events | `cause_chain` | causality (automation only) | Timeline "caused by" |
| mission → origin (message / idea / run) | `Mission.origin_ref` | provenance | Outcome |
| message → cards/links | `Message.cards[].ref`, `links[].ref` | reference | conversation cards |
| idea → mission | `Idea.promoted_mission_id` | promotion | idea row |
| device → presence | presence (memory) | **not a graph edge** | Devices list |
| account → usage | usage snapshots | **not a graph** | table |
| policy rules, profiles | rows | **not a graph** | tables |
| events generally | the log | **not one graph** — investigated per object (Timeline) | timeline |

Requirement ↔ task coverage (`Plan.coverage`, `Task.serves`) is a genuine relation but P8 exposes
`serves` only as task handles; it is listed as a row attribute until P18 [V].

### 20.3 Capability preservation assessment

- **Preserved and reused as-is (ADOPT):** `build_hierarchy` inside P4 inspection (G1), BM25 (G8),
  the Relation store and writer (G22–G23), supersession (G24), plan DAG/waves/lineage (G25–G26),
  the automation causal explanation (G27), cause chains (G28), session and execution lineage
  (G29–G30), verification lineage (G31), drift (G33), digest folding (G34), context references
  (G35). None of these is re-implemented in the client; the client reads their outputs.
- **Needs adaptation because its presentation belongs to the legacy UI (ADAPT):** the 2D renderer's
  interaction mechanisms (G4) → P18's `src/graph/`; the one-hop drill-down pattern (G9) → P16's
  Relations tab.
- **Stays internal/backend, not exposed directly (PRESERVE-BEHIND-UI):** recall expansion (G7), the
  import-graph payload (G32, until P18 exposes a focused query), the legacy graph.json and its
  hierarchy and route (G3, G5, G6, G10, G11, G20) until P22 imports and retires them, the cluster
  spec (G17), the site scene (G18).
- **Deferred with a named role (DEFER):** the flow graph (G12–G13) as P21's execution trace over
  D4's normalised stream.
- **Rejected for V1, with reason (REJECT):** the live strip and workspace node map (G14–G15:
  metrics-home instruments), the background scene (G16: decoration; its lineage is the deferred 3D
  candidate), the graph skin/world (G19: ADR-0017).

**The acceptance question** — *how is the substantial graph work preserved rather than thrown
away?* — answered by module: `connections.build_hierarchy` is the V1 world's import-graph
extractor today and stays so; the Relation/supersession/lineage machinery of P6–P14 is what the
P16 Relations tab and every provenance chain render; `automations.explain` is the P16 causal-chain
view; `connections.py`'s renderer mechanisms are P18's specification (§20.16); `flowgraph.py` is
P21's trace builder; `memory.py`/`recall.py` keep serving the legacy product until P22 imports
graph.json into knowledge items. Nothing is deleted by P16.

### 20.4 Dispositions

Table §20.1, column *P16 disposition*, with its reason. REJECT is used only where the capability
itself (not its look) conflicts with a decided V1 principle.

### 20.5 IA role

- The **Relations** tab of every inspector is the first-class relationship view in P16: the
  object's authoritative edges grouped by relationship type, each neighbour a link to its
  inspector, each edge explainable (the field it came from, its tier where it has one, "superseded"
  / "stale" marks).
- **Focused chains** served now (from rows): mission → plan versions → tasks → executions →
  checkpoints / verifications → review; task → route decision (selection) → execution → evidence
  → verification; session → hand-off lineage → mission; event → automation run → mission →
  resulting work (G27); knowledge item → supersession chain → relations → source.
- **P18** adds the spatial mode over the same edge mapper (`graph/relations.ts`), reached as a
  toggle on World and on Relations, plus `/v1/world/graph?focus=&depth=` (S8). It is never the only
  way to any fact: every fact on it is in a list first.

### 20.6 Navigation model

One model for list and graph: a node is an object → its canonical inspector (`#/o/<kind>/<id>`);
an edge → its explanation (field, tier, provenance); focus = the inspector's object; expand = open
the neighbour's Relations; filter by relationship type (chips); back = browser history (every
step is a URL, so "back to previous graph context" is Back); deep links everywhere. Pin, search
within a neighbourhood and path tracing are P18's on the spatial view; in P16, search is the
command bar and tracing is following Relations links.

### 20.7 Provenance (P13)

The Relations tab renders plan → task → execution → verification → review only from the columns
in §20.2. No edge is inferred (a verification without `execution_id` has no execution edge);
superseded plan versions, SUPERSEDED/RETRACTED knowledge and ENDED executions are visibly distinct
(state label + `text-3`); verification state is P13's row; the view is never a source of truth
(it has no write action).

### 20.8 Event causality (P14)

The automation run inspector renders `explain()`: triggering event (type, subject, seq,
`cause_chain`) → automation (trigger, template) → run (state, depth vs max_depth, reason) →
mission → its plans, policy decisions, approvals, route decisions, executions, verifications,
reviews. It is an investigation target per run, not a global event graph; it shows no model
reasoning.

### 20.9 Model/harness selection

Task → RouteDecision (requirements, candidates with elimination step and reason, selected harness
· account · model · effort, `result`, `fallback_from`) → execution(s) that ran on it → evidence →
verification. Structured selection facts only (§6.4); never chain-of-thought.

### 20.10 Visual graph language

Fine 1 px lines; node shape by kind (circle mission, square repository, diamond decision, ring
session, dot knowledge — research §26); state colour only on missions/tasks/executions, neutral
elsewhere; EXTRACTED solid / INFERRED dashed / AMBIGUOUS dotted; distance = graph proximity; no
glow, no ambient motion. In P16's list form, the same language appears as the edge-style swatch
beside each relation row.

### 20.11 Interaction model

List form (P16): Tab/↑↓ through relation rows, Enter opens the neighbour, chips filter by type.
Spatial form (P18): arrow keys move focus along edges, Enter opens the inspector, `+/-` zoom, `0`
fit, `/` search — keyboard equal to pointer.

### 20.12 Motion model

Motion only for focus change, expand/collapse, traversal and a real state change; layout computed
once per focus (deterministic seed) then static; energy only on edges with a live execution (one
opacity pulse per progress batch); no perpetual motion, no animated layout; reduced motion → none.

### 20.13 Accessibility

The Relations list *is* the structured, navigable, position-independent representation. P18's
canvas carries `role=application` with an off-screen list mirror and announces the focused node
and its relation count.

### 20.14 Responsive/mobile

Phone: Relations list only (focused neighbourhood of the open object, relationship groups
collapsible), tap-to-open neighbour sheets; the spatial view is hidden below 600 px (research
§4.4).

### 20.15 Performance/scaling

Start focused (one object's edges), expand deliberately (one neighbour at a time), filter by type,
never load the world. P18 budget: 1,000 nodes at 60 fps on integrated graphics, dot LOD above 250
visible nodes (G4's threshold), clusters collapse beyond the budget, layout once per focus.

### 20.16 Migration/reuse strategy per ADOPT/ADAPT/PRESERVE item

- ADOPT items: read through their existing routes; no code moves.
- G4 (ADAPT → P18): port the four mechanisms as TypeScript in `src/graph/` with tests (edge lifting,
  expand/collapse, focus+context, search-expands-ancestors), draw with Canvas 2D; the legacy page
  stays until P22.
- G9 (ADAPT → P16): the Relations tab.
- G32 (PRESERVE → P18): P18 adds a focused, scope-checked query over the stored payload.
- G3/G5/G6/G7/G10/G11/G20 (PRESERVE, LEGACY): untouched; P22 imports graph.json entities and
  relations as ENTITY knowledge items and `Relation` rows (INFERRED for LLM-derived, EXTRACTED for
  module edges) before retiring the legacy views.
- G12/G13 (DEFER → P21): a trace view builder over D4's normalised events reusing flowgraph's lane
  and call→result pairing.

### 20.17 Tests and acceptance criteria

`graph/relations.ts` is unit-tested per edge (each edge from its field; none without the field;
superseded marked); mutation M11/M12 (§24) swap an edge's direction and drop the field check.
P18's own acceptance (keyboard traversal, 1,000-node budget, reduced motion, list equivalent) is
recorded in the plan and not claimed here.

---

## 21. Legacy GUI migration table (§S, §18)

| Legacy surface | Route / component | Backend | Tests | Disposition | Migration |
|---|---|---|---|---|---|
| Dashboard (Spend/Work/Workspace bands, instruments) | `home`, `drawHome` | `/api/dashboard`, `/api/flow/live`, `/api/usage/plan` | test_gui_parity, smoke | **ADAPT** | V1 **Now** replaces it: digest + happening now + attention; spend moves to Control → Resources (usage per account) |
| Project page (9 tabs) | `drawProject`, TABS | many | smoke, test_gui* | **ADAPT** | V1 **World → project**: repositories, findings, inspections, missions; Memory/CLAUDE.md/Audit → knowledge + context (P6/P5 rows); Plan → Execute → a **mission**; Code Review → a mission (review) |
| Sessions tab | `drawSessions` | `/api/sessions`, `/api/transcript` | test_gui 58–101 | **ADAPT** | V1 **Control → Sessions** over P12 (brief, resume, hand-off); transcript browsing stays legacy |
| Plan → Execute | `drawPlanExec`, jobs | `/api/job plan_*` | test_gui_parity 646+ | **REJECT** (as a flow) | replaced by the mission lifecycle (P8–P13); its approve/edit ideas → approval card; edit → S2 |
| Code Review | `drawReview` | job `review` | test_gui_parity 622 | **ADAPT** | a mission template (P19) |
| Jobs inline + escalate-to-modal on a real gate | `inlineJob`, `#jovl` | `/api/job` | test_gui_flicker 351 | **ADAPT** (the pattern) | Attention + approval card: work runs without a modal; only a real approval asks (the same rule, now P9-backed) |
| Memory tab (graph, rules, lessons) | `drawMemory` | `/api/memory/*`, `/graph` | memory surface tests | **PRESERVE-BEHIND-UI** (LEGACY) | P22 imports; V1 World → Knowledge meanwhile |
| CLAUDE.md, Global CLAUDE.md, Audit | `drawClaudeMd`, `pgGlobalMd`, `drawAudit` | `/api/claude-md*`, `/api/ctxaudit` | parity tests | **LEGACY** | harness configuration; no V1 backend |
| MCP, Agents, Skills, Hooks, Plugins, Output styles | `pgMcp` … `pgOStyles` | `/api/mcp` … | parity tests | **LEGACY** | "Claude Code harness configuration" (research §17): relocated under Control → Resources → harness in a later phase when V1 has routes for it; stays in the legacy app |
| Usage & cost, Project usage | `pgUsage`, `drawProjUsage` | `/api/usage/*` | parity | **ADAPT** | Control → Resources: account usage from P10's snapshots; per-mission cost bands from plans |
| Loops | `pgLoops` | `/api/loops` | smoke | **DEFER** | P22: migrated as automations (plan §17) |
| Logs | `pgLogs` | `/api/logs` | content grid | **ADAPT** | Timeline (per mission) + Health (P21) |
| Accounts, Harnesses, Client | `pgAccounts`, `pgHarness`, `pgClient` | `/api/accounts`, `/api/harness/*` | parity | **ADAPT** | Control → Resources over P10 (accounts, harnesses); rotation/sync provisioning stays legacy (V1 accounts are registered, not provisioned) |
| Settings (Launch, Appearance, Paths, Models, Updates) | `pgSettings` | `/api/settings` | test_gui | **ADAPT** partly | Launch defaults → Autonomy (policy) + mission resources; Appearance → OS + motion preference; Models → Resources; Paths/Updates → LEGACY |
| Search (transcripts) | `pgSearch` | `/api/search-index` | content grid | **ADAPT** | command bar jump-to-object; transcript search stays legacy (ui-arch §4.8) |
| Help | `pgHelp` | none | smoke | **ADAPT** | shortcuts listed in the command bar |
| Launch modal, open-project modal, brief card | `#ovl`, `#oovl`, `drawBrief` | `/api/launch`, `/api/brief` | parity | **ADAPT** | session create/resume dialogs (P12 routes); brief → session brief |
| Command palette (Ctrl+K) | `palette()` | NAV/TABS | — | **ADOPT** (pattern) | V1 command bar |
| Themes (39 palettes, 8 skins, 4 worlds) | `themes.py`, `applyTheme` | `/api/state` | test_themes | **REJECT** for V1 (ADR-0017); **ADOPT** the contrast-floor method | one token table; palettes survive only as legacy |
| motion.js (one parked rAF, `MO.patch` keyed reconcile, arrive/burst) | `motion.js` | — | test_motion, test_gui_flicker | **ADOPT** rules, **REJECT** effects | transform/opacity only, park, keyed reconcile (React keys); no arrive stagger, no bursts |
| instruments.js gauges | ring/dial/spark/eq/flow | — | test_themes | **REJECT** | metrics-home instruments; one usage bar in Resources |
| stage.js background | three.js scene | — | test_stage | **REJECT** (ADR-0016); lineage DEFERRED to P18 3D | — |
| `/graph`, `/flow` windows | gui.py | — | test_gui, test_flowgraph | **PRESERVE-BEHIND-UI**; see §20 | P18/P21 |
| Guided tour | `tour.js` | `/api/tour` | — | **DEFER** | onboarding is P22 |
| Qt shell (`gui_qt.py`) | QWebEngineView over the legacy server | — | test_gui_flicker | **PRESERVE** | V1 attach is S7 (P19); the GPU/flicker lessons are carried as V1 gates |
| legacy→V1 link ("Open Archeus V1") | none exists | — | — | **DEFER** | P19 with S7 |

Gates carried into V1 (ui-architecture §7): keyframes transform/opacity only and no `steps()`
(`test_gui_flicker`), no `backdrop-filter`/blur/blend (Qt tear), container queries for component
layout, overflow + dead-space audit (a V1 audit in the e2e run, §24), contrast floors, no inline
handlers/script (CSP), nav table ↔ routes parity.

---

## 22. External reference evaluation — Ship Notes Components (R7)

**Source inspected** (not the demo only): `github.com/aqualang89/shipnotes-components`, branch
`main`, commit `c1b70d046c6b21c8f6bbae5899bf38e473eff9d2` (2026-09-26); **license MIT** (`LICENSE`,
"Copyright (c) 2026 Ship Notes"); four vanilla Custom Elements with Shadow DOM (project-stack,
pull-lamp, signal-orb, voice-orb), no dependencies, no build; motion by CSS `transition` and
hand-written rAF loops (exponential smoothing, damped springs); no `@keyframes`, no WAAPI; every
component handles `prefers-reduced-motion`. Inspected 2026-09-28. **No code is copied** (none is
needed; patterns only), so the MIT notice is not required in the bundle; the evaluation is recorded
here and in external-references R7.

| Pattern | Source | Archeus application | Decision | Reason |
|---|---|---|---|---|
| card reorder by transform with `cubic-bezier(.22,.8,.18,1)` | project-stack `.card` (L10) | the one easing curve of the motion table (§18.2) at 160–280 ms | **ADAPT** | the curve (fast out, soft settle) suits inspector/sheet entry; its 750 ms is too slow for state feedback |
| back cards dimmed by `filter: brightness` | project-stack L10 | — | **REJECT** | `filter` forces a readback (Qt tear rule) |
| tab pill background/colour transition | project-stack L13 | selected tab changes instantly | **REJECT** | animates paint properties; a state change should be instant and legible |
| press `scale(.96)` | project-stack L13, demo buttons | pressed buttons `scale(.98)` | **ADAPT** | transform-only, compositor-safe; design system's 0.98 |
| arrow nudge `translate(2px,-2px)` on hover | project-stack `.visit` | link-out affordances, `pointer: fine` only | **ADOPT** | transform-only, hover is not the only cue (the arrow exists at rest) |
| focus-visible 2 px outline with offset | all components | the focus ring (design system §9) | **ADOPT** | already the system's rule |
| roving tabindex tabs, ←/→/Home/End, `inert` + `aria-hidden` on hidden panels | project-stack L34 | inspector tablists, Control sections | **ADOPT** | accessible keyboard pattern; verified by the e2e keyboard journey |
| scoped `@media (prefers-reduced-motion) { * { transition: none } }` | project-stack L14 | global reduced-motion rule + `html[data-motion=reduced]` | **ADOPT** | honours the OS; the `recording` attribute's idea (a deterministic mode) → the manual setting |
| `@media (hover: hover)` guards on hover styles | voice-orb demo | every hover style | **ADOPT** | no hover dependence on touch |
| disabled `opacity:.5` + `cursor:wait` | voice-orb demo | disabled = 40% + a stated reason | **ADAPT** | opacity alone does not say why; Archeus states the reason |
| cord drag with springs, SVG path `d` and `left/top` per frame | pull-lamp | — | **REJECT** | decorative physics; animates geometry and layout |
| exponential light fade in rAF (τ≈111 ms) | pull-lamp | — | **REJECT** | UI state uses CSS transitions; no rAF for non-graph UI |
| state-morph orb (listening / thinking / searching / done) | signal-orb, voice-orb | — | **REJECT** | it performs a model's inner state ("thinking") — Archeus never animates hidden reasoning; infinite ambient loop |
| ambient spin, twinkle, belts | signal-orb, voice-orb | — | **REJECT** | ambient infinite motion |
| audio-reactive motion, onset bursts | voice-orb | — | **REJECT** | no voice channel in V1 (Q6); decorative |
| adaptive quality (drop particles after N slow frames, floor) | signal-orb L84, voice-orb L214 | P18 graph LOD degrade on frame time | **ADAPT** (DEFERRED to P18) | a sound budget mechanism for the spatial view |
| loop lifecycle: pause on `visibilitychange`, `webglcontextlost`, restore | voice-orb `_sync` | the P18 loop's parking rules | **ADOPT** (for P18) | identical to the repo's rule |
| Custom Elements + Shadow DOM packaging | all | — | **REJECT** | the SPA is React; shadow roots complicate testing and a11y tooling here |

Accessibility and performance of every ADOPT/ADAPT row are verified by §24's design and e2e
tests (transform/opacity parse, reduced-motion emulation, keyboard journey).

---

## 23. Model of the SPA (implementation outline)

```text
clients/app/
├── tokens/tokens.json            the visual tokens (D9)
├── tokens/presentation.json      domain state → presentation class, per machine (D9)
├── public/sw.js, manifest.webmanifest, icon.svg, icon-192.png   (D6)
├── src/
│   ├── api/generated.ts          (generated; gains the D2–D5 routes)
│   ├── api/stream.ts, transport.ts   (P3.5b; transport records X-Archeus-Seq)
│   ├── data/cache.ts, invalidation.ts, connection.ts, commands.ts
│   ├── state/presentation.ts, tokens.ts     (generated)
│   ├── state/present.ts          presentation lookups, status line, explainState, resourceLine
│   ├── graph/relations.ts        authoritative edge mapper (§20)
│   ├── nav/destinations.ts, router.ts
│   ├── a11y/announce.ts, focus.ts
│   ├── surfaces/{now,work,world,attention,control}/…, inspector/…
│   ├── components/…              (StateBadge, Row, Card, ApprovalCard, Sheet, Dialog, QR, …)
│   └── styles/{tokens.css (generated), app.css}
└── test/*.test.ts                node --test (type stripping), pure modules only
```

`tools/gen_ui.py` generates `tokens.css`, `tokens.ts` and `presentation.ts` and fails `--check`
when they are stale or when any state has no class. `tools/gen_api_docs.py` is unchanged in
behaviour (new routes appear in `generated.ts` and `api-reference.md`).

---

## 24. Tests and mutation (§20)

### 24.1 Tests

| Layer | File | What |
|---|---|---|
| unit (Python) | `tests/v1/unit/test_ui_seams.py` | attention item per source row and reason code, fixed ordering, nothing for non-waiting states; timeline scoping (only the mission's rows, paging); stream redaction and offset; launch scopes ⊆ minter's, default observe, observe always present |
| integration (HTTP) | `tests/v1/integration/test_ui_routes.py` | the four routes over a real Core (TempCore): scopes, 404s, 400s, `X-Archeus-Seq`, a launch device with requested scopes can act, one without cannot; `/sw.js` and manifest served with the right type and CSP; sw never caches `/v1/` (source check) |
| design | `tests/v1/design/test_design_gates.py` | tokens/presentation generated files fresh; every machine state has a class; contrast floors × themes; ΔE between state colours; built CSS: transitions/keyframes only transform/opacity, no `infinite`/`steps(`/`backdrop-filter`/`filter:`/`mix-blend-mode`; component rules use `@container` (no `@media` naming a component selector); `prefers-reduced-motion`, `prefers-contrast`, `forced-colors` blocks present; no inline script/handlers in the built HTML |
| TS unit | `clients/app/test/*.test.ts` (`node --test`) | presentation mapping per machine, the four distinctions, status line, explainState per case, resourceLine keeps three fields, connection machine and freshness, invalidation table, command error mapping, relations edges, nav table ↔ routes, reduced-motion preference, announce rate limit, responsive critical-state (a destination/attention reachable at every breakpoint by the nav table) |
| e2e | `tests/v1/e2e/test_spa_p16.py` (Playwright) | every destination and every inspector tab renders against a Core with a completed mission; a mission that asks: approve from Attention and watch the mission move; pause/resume; pairing start → QR/code → redeem in a second context → the device appears with presence; revoke closes its stream and its page shows revoked; reconnect after Core restart shows stale then current; keyboard-only journey; axe-core (no serious/critical); 390/768/1280/1920 overflow audit; reduced-motion emulation; a check floor derived from the nav table × inspector tabs |
| judge | `tests/v1/judge/test_g03_one_model.py` | the GUI function passes (`rig.gui()` implemented over Playwright on the HTTP binding); P17/P19 functions stay xfail |
| existing | `test_api_structure.py` | route pin gains `P16`; `graph` stays forbidden (P18); launch default stays observe |

### 24.2 Mutation suite `tools/mutate_p16.py` — every mutation must be killed

| # | Target | Mutation | Killed by |
|---|---|---|---|
| M01 | mission state mapping | APPROVAL_REQUIRED → `approved` class | TS presentation test |
| M02 | approved ≠ executing | APPROVED → `active` | TS |
| M03 | executing ≠ verified | VERIFYING → `done` | TS |
| M04 | verified ≠ accepted | REVIEWING → `done` | TS |
| M05 | execution ≠ success | ENDED_OK → `done` | TS |
| M06 | plan version mapping | superseded version marked current in the version list | TS (plan lineage) |
| M07 | stale/current | freshness returns `current` while reconnecting | TS (connection) |
| M08 | reconnect state | `resynced` does not invalidate every key | TS |
| M09 | P15 presence mapping | `recent` rendered as connected | TS |
| M10 | session/mission confusion | the session row takes its mission's state glyph | TS |
| M11 | graph relationship mapping | handoff edge direction reversed | TS (relations) |
| M12 | graph relationship mapping | a verification→execution edge emitted without `execution_id` | TS |
| M13 | model/harness confusion | `resourceLine` merges model into harness | TS |
| M14 | approval mapping | decide echoes the approval id instead of `action_hash` | TS (commands) |
| M15 | idempotency | a network retry generates a new key | TS (commands) |
| M16 | accessibility state | glyph rendered without a text label | TS (StateBadge contract) |
| M17 | reduced motion | `data-motion=reduced` not applied | TS (preference) |
| M18 | responsive critical state | Attention missing from the phone tab bar | TS (nav) |
| M19 | announcer | rate limit removed (announces every frame) | TS |
| M20 | attention (backend) | CANDIDATE knowledge omitted | pytest unit |
| M21 | attention (backend) | an APPROVED approval listed | pytest unit |
| M22 | stream (backend) | redaction skipped | pytest unit |
| M23 | timeline (backend) | another mission's task events included | pytest unit |
| M24 | launch scopes | scopes not bounded by the minter's | pytest unit |
| M25 | launch scopes | default widened beyond observe | pytest unit |
| M26 | design gate | a keyframe animating `background` passes the parse | design test (mutation of the checker's allowlist) |
| M27 | design gate | a state without a presentation class passes gen_ui `--check` | design test |
| M28 | invalidation | `mission.*` frames stop invalidating `/v1/attention` | TS |
| M29 | P15 M13 re-check | opening the stream creates/resumes a session (client side: connection code calls a session route) | TS static test |

P8–P15 mutation suites are re-run after implementation.

---

## 25. Decisions

| # | Decision | Status |
|---|---|---|
| D1 | IA: Now · Work · World · Control + Attention + command bar (ADR-0014), re-derived from P4–P15; Sessions and Devices under Control; mission inspector tabs Outcome · Plan · Now · Evidence · Why · Timeline · Relations (Thread deferred, S1) | this gate |
| D2 | `POST /v1/devices/launch/code` takes optional `scopes` ⊆ the minter's credential scopes, always including `observe`; default unchanged (`observe`); `archeus core --open` (and the runtime's own open) request observe+control+approve+admin; the redeemed credential is still honoured on the loopback Host only (P15 D21) and its step-up is `local` (P9 D16) | **user decision 2026-09-28** ("minter chooses"), supersedes P3.5b D-scope for launch devices whose minter asks |
| D3 | `GET /v1/attention` (observe): items from rows, fixed kinds and order, no score | this gate |
| D4 | `GET /v1/executions/{id}/stream?from=` (observe): normalised events through `adapter.inspect` from the byte offset, every string redacted by `core/redact.py`, `next_offset`; an execution with no process yet → empty | this gate (frozen to P16 by P3.5b D8) |
| D5 | `GET /v1/missions/{id}/timeline?before=&limit=` (observe): events whose subject is the mission or one of its plans, tasks, executions, approvals, verifications, reviews, sessions; newest first, ≤ 100 per page | this gate |
| D6 | PWA: `/manifest.webmanifest` and `/sw.js` served public like `/`; the service worker caches the shell only and never `/v1/*` | this gate (P15 D20) |
| D7 | hash router; deep links `#/o/<kind>/<id>` | this gate |
| D8 | Q4: no TanStack Query, no React Router — one cache hook and one invalidation table | this gate, **Q4 DECIDED** |
| D9 | tokens.json + presentation.json → generated CSS/TS by `tools/gen_ui.py`; coverage of every state enforced | this gate |
| D10 | QR drawn locally by a vetted MIT dependency (`qrcode-generator`), pinned in the lockfile; no network, no image service | this gate |
| D11 | Q5: token values of §15.1 frozen by the contrast gate | **Q5 DECIDED** |
| D12 | Q7: no legacy worlds/skins in the V1 client | **Q7 DECIDED** (ADR-0017) |
| D13 | Q8: English only at launch | **Q8 DECIDED** (reversible; copy is in components) |
| D14 | Q6: no voice channel in V1 | **Q6 DEFERRED** |
| D15 | Graph: P16 builds the Relations list view and the causal/provenance chains from authoritative fields; spatial view and `/v1/world/graph` stay P18 | this gate |
| D16 | Execution output tail only while the detail is open; last 200 rendered | this gate |
| D17 | Seams S1–S10 recorded, not built | this gate |
| D18 | The SPA queues no command offline | this gate (stricter than P15 D18, which permits the digest ack) |
| D19 | TS unit tests run with Node's built-in test runner and type stripping (no test framework dependency); CI `v1-client` runs them | this gate |
| D20 | axe-core as a dev dependency for the e2e accessibility check (not shipped) | this gate |

---

## 26. What P16 must not do (§19 restated as a checklist)

No policy evaluation, no candidate ordering, no execution state inference, no session creation or
resumption from presence, no verification inference, no event-payload state, no client grammar,
no optimistic state, no cached API data in the service worker, no physical-hardware claim, no
"user is active" from presence, no cancellation on disconnect, no animation of model reasoning.

## 27. Deviations from the plan's P16 entry, declared up front

1. **Qt shell attach** is deferred to P19 with the legacy "Open V1" link (S7): D2 is the mechanism
   it needs; the shell change belongs with client unification.
2. **Apple-skill five-lens review** is done by this gate's author as a self-review at the end of
   implementation (recorded in §28 of the as-built), not by an external reviewer.
3. **Dead-space audit**: the V1 e2e audit checks overflow at four widths and horizontal scroll;
   the legacy `SPACE_JS` metrics (ragged/dead/slack/cramped/measure) are tuned to the legacy grid
   and are not ported; the V1 layout is list-first, not a card grid.
4. **Per-mission thread tab** is not built (S1); the design research's Thread tab is absent.

## 28. Flagged for the user

- **S4**: P9 left "confirming a mission before `start` under `careful`" to P16. It is a lifecycle
  rule, not presentation; this gate does not build it and recommends P19 with a small P9/P3
  design note.
- **D2** is implemented as decided; the SPA opened by `archeus core --open` can approve, pause,
  revoke and start pairings from this machine only.

## 29. Implementation order

1. this gate (commit);
2. backend seams D2–D6 with unit + integration tests; regenerate the API reference and client;
3. tokens + presentation + `gen_ui.py` + design tests;
4. SPA: data layer, nav/router, shell, surfaces, inspectors, Attention, Control, pairing, PWA;
5. TS unit tests; e2e + axe + audits; G3 GUI function;
6. `tools/mutate_p16.py`; P8–P15 mutation suites; full suite; Ruff; type-check; mkdocs; API check;
   wheel;
7. as-built (§30) and plan entry; commit; push after validation; CI.

## 30. As built

Everything in §1–§29 is built as written, except the deviations below.

**Backend (four read routes, one command change, two static files; no migration, no state, no
event type).** New: `archeus/core/application/attention.py` (`attention()` — D3; `timeline()` —
D5), `archeus/core/execution/output.py` (`read()` — D4, through `adapter.inspect`, every string
through `core/redact.py`, at most 1,000 events per answer). Changed: `api/auth.py` (`LaunchCodes`
carries the minter's grant, D2; `LAUNCH_SCOPES` unchanged), `api/routes.py` (the five P16 rows,
`launch_code` bounds the grant by the minter's own scopes and always keeps `observe`,
`launch_redeem` registers exactly it), `api/schemas.py` (`LAUNCH_CODE`, `Attention`,
`AttentionItem`, `Timeline`, `ExecutionOutput`; `LaunchCode` and `Redeemed` name the grant),
`api/server.py` (`Static.root_file` serves `sw.js` and `manifest.webmanifest` by name only),
`core/application/executions.py` (`entity()`, so the API layer imports no row codec),
`core/runtime.py` (`launch_url(scopes)`; `archeus core --open` asks for every scope),
`cli/main.py` (the same for a Core already running), `tools/gen_api_docs.py` (the two new query
parameters). The route table went from 92 to 97 rows (§1.2's "95" was a miscount).

**Client.** `clients/app/`: `tokens/{tokens,presentation}.json` → `tools/gen_ui.py` →
`src/styles/tokens.css`, `src/state/{tokens,presentation}.ts` (presentation also carries the
per-state trigger table from `states.py`, so a button is offered only where the machine has the
trigger); `src/data/{cache,connection,invalidation,commands,core}.ts`; `src/state/present.ts`;
`src/graph/relations.ts`; `src/nav/destinations.ts`; `src/a11y/announce.ts`;
`src/components/{ui,Relations,QR}.tsx`; `src/surfaces/{Now,Work,World,Attention,Control,Mission,
Inspector,CommandBar}.tsx`; `src/App.tsx` (bootstraps, shell, keyboard, focus, the stream);
`public/{sw.js,manifest.webmanifest,assets/icon-192.png,assets/icon-512.png}`. Dependencies:
`qrcode-generator` 2.0.4 (MIT, no dependencies; the only runtime addition), dev-only `axe-core`
4.13.0 (MPL-2.0, e2e only, not shipped) and `@types/node` 22.20.4. Build: 360 KB JS (109 KB
gzip), 16 KB CSS.

**Tests.**

| Layer | File | Count |
|---|---|---|
| backend seams | `tests/v1/integration/test_ui_seams.py` | 10 |
| design gates | `tests/v1/design/test_design_gates.py` | 15 |
| client units | `clients/app/test/*.test.ts` (`npm test`) | 38 |
| e2e | `tests/v1/e2e/test_spa_p16.py` (12) + the reworked `test_spa_skeleton.py` (5) | 17 |
| judge | `test_g03_one_model.py::test_the_gui_shows_the_mission_the_api_reports` (P16 marker removed; `rig.gui()` = `SpaDriver`, HTTP binding only) | 1 |
| changed | `test_api_structure.py` (the `P16` set; `attention` no longer a forbidden word; `graph` still is), `test_api_auth_units.py`, `test_presence_units.py` (a launch code's payload carries its grant) | — |

`tools/mutate_p16.py`: **29/29 killed** (M01–M29 of §24.2 as implemented below).

**Deviations.**

1. **M10, M26 and M27 target the thing, not the checker.** §24.2 described M26 and M27 as
   mutations of the design test's own allowlist; as built they break the rule the test guards —
   a keyframe animating `background` in `app.css` (M26), a mission state removed from
   `presentation.json` (M27) — which is the repository's "watch the gate fail" rule. M10 is a
   session row given `machine="mission"` in `Control.tsx`, killed by a static client test.
2. **`text-3` is not used for essential text.** axe-core flagged the disabled-reason captions
   and the relation field names at 3:1; `text-3` meets its own 3:1 floor but the design system
   already says it is never for essential content. They, inactive rows and the `inactive` class
   use `text-2`; `text-3` stays a token with its floor tested.
3. **No animated spinner.** §18.1 forbids any iteration count above one; a busy button says
   "Approve…" instead of spinning.
4. **The inspector replaces the main column below 1,000 px** instead of overlaying it: one scroll
   and one focus order, and no focus trap needed. Desktop keeps the side column.
5. **Initial focus stays at the top** so the skip link is the first Tab stop; focus moves to the
   view's heading only on a navigation (found by the keyboard e2e test).
6. **Inspector tabs replace the history entry**; closing an inspector returns to the destination
   it was opened over (a Back through every tab visited was the first behaviour).
7. **A resync before anything is shown is not announced** as "Back — read again" (the new
   leader's own RESYNC at start-up); the generation still advances.
8. **Why on a settled mission** says it is completed (or cancelled) and stops; a route shown as the
   reason must be a *task's* route — an own call after the end (the lesson pass) is not a reason.
9. **CI**: the `v1-client` job gains `npm test` and the G3 judge function (the only CI change;
   made with the user's confirmation, §27 of the plan's rules).
10. Everything declared in §27 up front holds (Qt shell attach and the legacy link → P19; the
    five-lens review is the self-review below; `SPACE_JS` not ported; no Thread tab).

**Five-lens self-review (Apple Design Skill).**

| Lens | Finding | Severity |
|---|---|---|
| Accessibility | axe-core: no serious or critical violation on eight surfaces; keyboard-only journey (skip link, Ctrl+1–3/J/K, roving tabs, Esc) passes; every state is glyph + label; reduced motion removes all movement; phone targets ≥ 44 px | none open |
| Platform conventions | sidebar / rail / bottom tab bar by width; native `<dialog>` for confirmations and the command bar; Esc closes the topmost layer | Low: no desktop tray (legacy shell, P19) |
| Visual craft | one token table, contrast floors tested per theme, no hue accent, state colours only on state | Low: object references still fall back to a short id where a row has no name (route and policy decisions) |
| Interaction | every command re-reads, is disabled with a reason, confirms irreversible actions in prose; no optimistic state | Medium: no plan editor (S2) and no per-mission thread (S1) — deferred seams, not defects |
| Content | Core's refusal reasons verbatim; model-written text labelled as such; progress text only from rows | Low: English only (Q8) |

No Critical or High finding.

**Final architectural check (§24 of the P16 brief), with evidence.**

| Question | Answer | Evidence |
|---|---|---|
| A. ontology without collapse | yes — each noun has its own machine table, label and place | §2; `presentation.json`; `presentation.test.ts`; `present.test.ts` (M10, M13) |
| B. conversation a surface | yes — a panel of Now; cards render live rows | §5; `Now.tsx` `CardRef`; no verb parsing (`shell.test.ts`) |
| C. mission/plan/approval/execution/verification/review distinct | yes — six looks, three facts in the Plan tab, `ENDED_OK` never ✓ | M01–M05; `test_only_a_completed_mission_is_done…` |
| D. continuity is reconstruction | yes — the session brief (P12), never the transcript | `Control.tsx` `Brief`; §6.9 |
| E. cross-harness continuity ≠ harness | yes — lineage rows name each session's harness | `sessionEdges`; `relations.test.ts` |
| F. model × harness without a routing authority | yes — three fields; controls call P10/P12 commands only | `resourceLine` (M13); `ResourcePreferences`, `SessionActions` |
| G. P15 client/device/connection/presence | yes — client ≠ hardware ("declared"), presence ≠ activity, revocation signs out | `Devices`; M09; pairing e2e |
| H. stale / reconnect / offline explicit | yes — one connection machine and per-view freshness | `connection.ts`; M07, M08; restart e2e |
| I. graph work inventoried and preserved | yes — 35 capabilities with dispositions and future roles | §20.1, §20.3 |
| J. graph a capability, not the IA | yes — Relations tab + causal chains; spatial view P18 | §20.5; `Relations.tsx`; M11, M12 |
| K. Ship Notes as motion reference only | yes — source c1b70d0 (MIT) inspected; patterns only, no code | §22 |
| L. IA independent of the legacy dashboard | yes — derived from P4–P15; legacy mapped, not copied | §4, §21 |
| M. no shadow policy/routing/execution/verification/session | yes | §19; `shell.test.ts` scans; M14, M29 |
| N. accessibility and mobile first-class | yes | §16, §17; axe, keyboard, width and target e2e; M16–M18 |
| O. "what changed while I was away" without replay | yes — the digest (P4) and the session brief (P12) | `DigestSection`; `Brief` |
| P. why blocked / awaiting / executing / failed / verified / awaiting review | yes — `explainState()` from rows, "no recorded reason" otherwise | `present.test.ts` |
| Q. live data without noise | yes — frames invalidate keys in 50 ms batches; one pulse per changed object; no loops | §12; `invalidation.ts`; design gates |

**DESIGN_GATE = IMPLEMENTED.**
