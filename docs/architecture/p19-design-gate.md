# P19 design gate — client unification

Status: **APPROVED** (B1–B13, the user, 2026-10-03, with the decisions recorded in §4.1).
Implementation follows §5. Anything implementation finds that departs from an approved decision
is recorded in §12 for the user's review, never applied silently.

Sources read, in precedence order: the plan (§31.1 P16–P19.5, §31.3), this repository at
`df1b492` (P19.5 implementation-complete and verified, nothing pushed; the user's uncommitted
documentation edits are not quoted for any P19 fact, §1.0), the user's P19 brief of 2026-10-03,
[p16-design-gate.md](p16-design-gate.md) (§3.2 D2/D6, §3.3 S1–S7, §13.5, §26–§28),
[p17-design-gate.md](p17-design-gate.md) (A2, A3, A6, §5), [p18-design-gate.md](p18-design-gate.md)
(A1, V2, V8, §18.2, §22 I3/D1), [p9-design-gate.md](p9-design-gate.md) (D5, D14, D19),
[p8-design-gate.md](p8-design-gate.md) (D12, D15), the rulebook
[../design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md](../design/ARCHEUS_V1_VISUAL_ARCHITECTURE_RECONCILIATION.md)
(§11, §29, A-05, X-24, X-27, §46.2, §46.3), the design system (§2, §3.3, §13, the TUI table),
the design research (§18, §19, wireframe A.2), [ui-architecture.md](ui-architecture.md),
[ARCHEUS_V1_CONVERSATIONAL_ORCHESTRATION.md](ARCHEUS_V1_CONVERSATIONAL_ORCHESTRATION.md) (C-30,
C-31, C-33, F1, F4, K14–K18, Part H), ADR-0015, ADR-0026, ADR-0042, ADR-0044,
[testing-strategy.md](testing-strategy.md) (§2 G3, §7 thread row, the conversational and theme
gates), [target-architecture.md](target-architecture.md) §5, [api-and-realtime.md](api-and-realtime.md) §5.1,
[execution-architecture.md](execution-architecture.md) (e-stop).

---

## 0. What P19 is, and what it is not

The plan's entry (§31.1), committed:

> **P19 — Client unification.** Depends: P16–P18. Work: remove any logic that crept into
> clients; generated client everywhere. Carried from P18: … P19 moves the Relations tab and the
> TUI onto `/v1/world/graph?focus=<object>&depth=1`, deletes the two client edge mappers and
> carries their cases to the route's tests; `EDGE_WORDS` stays the client's vocabulary.
> Inherited from P16: S1 per-mission conversation threads, S2 plan edit, S3 the chat verbs
> `approve`/`reject` bound to a displayed card's `action_hash`, S4 mission confirmation before
> `start` under `careful`, S6 offline snapshot, S7 the Qt shell attach with the legacy "Open V1"
> link. Carried from P19.5: the mission Now tab, T2's changed rule on the Relations list and the
> TUI, Pause all in the tray with S7. Decided 2026-09-30 (ADR-0042, ADR-0044, Part H):
> conversational resource directives for accounts and harnesses; the `route_explanation` card on
> `why`; the application theme and contrast preference in Control → Appearance. Test: the
> unification scenario (create on desktop → observe on mobile → approve on mobile → execute on PC
> → review on desktop → inspect on TUI). Acceptance: G3 fully passes.

P19 is therefore **four kinds of work**, not one:

1. **Consolidation** (no new behaviour): one edge implementation; one generated client per
   language; the client logic named by p17 A2 and p18 A1 removed or generated.
2. **Seven Core seams** the P16 gate left with P19 as owner (S1–S4, S6, S7) and the two ADR-0042
   items (directives, explanation card). Several are Core write-path changes.
3. **Three P19.5 behaviours** that wait for P19 (rulebook §46.3): the mission Now tab, T2 on the
   Relations list and the TUI, Pause all in the tray.
4. **One client preference** (ADR-0044, fully specified).

It is **not**: P20 hardening, XR-14 / ADR-0052, V2, the legacy context migration (P22/P25.5),
the activity chip (P21), thread tints (P22), the Q-A5 key change (verified before P26, rulebook
§46.3; P19 has no dependency on it), `what is running` / live work (P21), model and location
directive kinds (P22), or any change to a P19.5 disposition.

**R13 does not run in P19.** When P19 is built and the three carried behaviours are integrated,
the branch is reported R13-ready and stops (rulebook §46.3).

## 1. What exists [V = verified at `df1b492`]

### 1.0 Documentation state

The uncommitted working-copy edits (ADR-0007/0037/0042/0047, the orchestration documents, the
plan from line 1109, domain-model 242–244, execution-architecture line 32) touch voice, V2,
ADR-0050 and research notes. None changes a line this gate relies on [V: `git diff HEAD`]. They
stay uncommitted and untouched.

### 1.1 Edges (the P18 carry) [V]

- Route: `GET /v1/world/graph` (`routes.py:352-367`, `observe`), `focus=<kind>:<id>` over
  `graph.KINDS` (17 kinds), `depth` 1..2 — **default 1 only for a project, 2 for everything
  else** (`graph.py:327-328`) — `limit` 1..1000 (default 500). Response `{focus, depth, limit,
  as_of_seq, nodes, edges, truncated, hidden}`; edge `{id, from, to, field, rel, tier, inactive,
  structural}`; node `{kind, id, label, parent, machine, state, type?, attrs?, endpoint?,
  missing?}`. Structural edges: `tasks.plan_id`, `knowledge_items.project_id`,
  `repositories.project_id`, `reviews.plan_id`.
- SPA mappers to delete: `relations.ts` `missionEdges`, `planEdges`, `taskDependencies`,
  `executionEdges`, `verificationEdges`, `sessionEdges`, `knowledgeEdges`, `runEdges` (+ `edge`,
  `ORIGIN_REF_KIND`). Callers: `Mission.tsx` (Relations tab, the "after …" hint on a task row,
  the execution tab), `Inspector.tsx` (`EDGES` for plan, verification, automation run),
  `Control.tsx` (session), `World.tsx` (knowledge).
- Vocabulary that stays: `EDGE_WORDS` (30 fields), `edgeWords`, `TIER_STYLE`, `TIER_WORD`,
  `tierOf`, type `Edge`; read by `Relations.tsx`, `GraphView.tsx`, `mirror.ts`, `encoding.ts`,
  `legend.ts`, `model.ts`.
- TUI mappers to delete: `present.py:179-300` (`mission_edges` … `run_edges`), words hard-coded,
  no `EDGE_WORDS`. Callers in `screens.py` (`relations()` renderer, the plan view's dependency
  hint, execution, session, knowledge, `row_insp`).
- Parity: `clients/app/test/fixtures/parity.json` (18 edge cases among the present/sync cases),
  read by `parity.test.ts`, `tests/v1/tui/test_parity.py`, `tests/v1/unit/test_graph_parity.py`;
  the route test `test_graph_routes.py::test_the_route_and_the_tui_list_show_the_same_edges`.
- Mutants anchored on the mappers: p16 M06, M11, M12; p17 M24 (renderer, stays); p18 M04
  (vocabulary, stays), M67, M68; p18 M02, M66 guarded by `test_graph_parity.py`. Every engine
  refuses a missing anchor, so deleting a mapper stops those runs until the mutants move.

### 1.2 The changed rule (T2) [V]

ADR-0026 §1: "a static 2 px rule on the left edge of a row whose object changed since the user
last looked (digest cursor); removed by acknowledgement". SPA: `ui.tsx` `useChanged()` reads
`/v1/digest` only, `thread()` sets `data-thread`, `<Changed>` says "changed since you looked";
built on every digest-nameable list except the Relations list (testing-strategy §7: "Not here:
the Relations list and the TUI (P19)"). **The TUI has no T2 at all.** The design system's TUI
table specifies it: "Thread | `›` marker on rows changed since last look".

### 1.3 Conversations (S1, the mission Now tab) [V]

- Schema `0006_conversation.sql`: `conversations(kind, mission_id REFERENCES missions)` — no
  unique index on `mission_id`; `entities.Conversation` kinds `primary` / `mission`.
- **No mission conversation is ever created**: the only constructor is `conversation.primary()`;
  `post_message` defaults to primary; `ask_meeting_date` and `Planning.hold` write to primary.
  A reply always follows its turn's conversation.
- Routes: `GET/POST /v1/conversations/{id}/messages` (`?after=`; post `control`, idempotent),
  `POST /v1/intents/{id}/clarify`. No by-mission lookup. Every client posts to `primary`.
- Mission inspector tabs (`navigation.json` → `table.ts`): outcome, plan, now, evidence, why,
  timeline, relations. `NowTab` shows the plan-in-force tasks and their executions. No Thread tab.
- T1 thread travel (A-05) exists on the primary conversation only (`Now.tsx`, `state/thread.ts`).

### 1.4 Plan edit (S2) [V]

No `/v1/plans/{id}/edit`. A Plan is one immutable PlanVersion (`FROZEN_ALL`, `plan_version`,
`supersedes_plan_id`). The only writer is `Work.propose_plan`, guarded to missions in
REASONING / PLANNING / REPLANNING, through `validate.problems()`, `supersede_for` (P9 D14) and the
auto-approve / needs-approval split. Revision today: `request_changes` (APPROVAL_REQUIRED →
PLANNING) and the conversation.

### 1.5 Chat approve / reject (S3) [V]

`POST /v1/approvals/{id}/decide` (`approve` scope, idempotent, echoes `action_hash` and
`expected_version`, `_refuse_hash`). Grammar `VERBS` has `approve` / `reject`, answered by
`NOT_YET = {'approve': 'P9 (approvals)', …}` — stale since P9 D19 (C-30). **No message carries an
`approval` card**: `CARD_TYPES` declares it; nothing writes it. The message route is `control`
and the intent worker acts as Core's own actor, so nothing today carries the poster's `approve`
scope or step-up into a decision.

### 1.6 Confirmation under `careful` (S4) [V]

`PROFILES['careful']` is action-class rules only (read/web ALLOW, the rest ASK). `CREATED →
UNDERSTANDING: start` fires unconditionally in `Engine._step` (`engine.py:189-192`). P9 D5:
"mission auto-start unchanged (P16)"; P16 §28: "a lifecycle rule … recommends P19 with a small
P9/P3 design note". **No specification of the confirmation exists.**

### 1.7 Offline snapshot (S6) [V]

`sw.js` caches the shell only and never `/v1/*` (P16 D6, §13.5: "no API response, no token, no
event is ever cached by it"). `data/cache.ts` is in memory only. Persisted today: the device
token (IndexedDB), motion, inspector width and pins (localStorage). Nothing implements S6.

### 1.8 Qt shell, tray, Pause all (S7) [V]

`claude_sessions/gui_qt.py` (135 lines) loads the **legacy** server (`/?k=<token>`), default
QtWebEngine profile, hard-coded legacy background. No tray, no `QWebEngineProfile`, no launch
code, no "Open V1" link anywhere. The V1 CLI has no `gui` verb; `archeus core --open` mints a
launch code with observe+control+approve+admin (`cli/main.py:146-165`, D2) and opens a browser.
Design system §13 (amended `ae52847`): "tray menu (Open, Pause all, Emergency stop, Quit)";
"`attention` is the only colour allowed to appear in the tab bar badge and the tray icon" (:103).
execution-architecture: e-stop is "`archeus estop` (or the desktop shell's tray item, which runs
the same code, dispatched without starting Core)". Pause all: `POST /v1/missions/pause-all`
(`control`, idempotent), built on the strip and Work (R10a).

### 1.9 Theme preference (ADR-0044) [V]

Fully specified: `theme` ∈ system | dark | light, `contrast` ∈ system | standard | high,
`forced-colors` always wins, per client storage, a `'self'` boot script before first paint, the
generator emitting attribute selectors plus the `system` media mapping, no token value change,
the Qt shell's persistent profile and OS-following pre-load background, the TUI unchanged
(§6). Today: no Appearance section, tokens only under media queries, no boot script,
`theme-color` hard-coded `#0E1116`, motion lives in About. Gates T1–T6 (testing-strategy).

### 1.10 Directives and the explanation card (ADR-0042) [V]

Mission preference fields exist (`RESOURCE_PREFERENCE_KEYS`: preferred/forbidden accounts and
harnesses, `max_cost_band`) behind `/v1/missions/{id}/resources`. `intent.v1` has no
`resource_directive`; the grammar has no `use` / `don't use`, `emergency stop` or `stop <running
mission>`; `why` answers in text only (C-31); `route_explanation` is declared, never emitted.
Gates G1, G3 (orchestration), G4, G5, G14.

### 1.11 Generated clients [V]

`tools/gen_api_docs.py` generates the SPA's `api/generated.ts` (49 GET, 50 POST helpers).
Commands use it; **reads do not**: 204 raw `/v1/` path literals outside it (`useRead('/v1/…')`).
No Python client is generated: the TUI has a hand-rolled transport (`cli/tui/client.py`, 167
literals, p17 A3), the CLI its own `_get` (24 literals; "untouched until P19", p17 A3). p17 A2's
thin Python copies (explanations, `resource_line`, connection machine, refusal wording) are held
equal to the SPA by golden fixtures. The G3 judge `test_every_client_agrees` is
`xfail(strict, phase:P19)` and `rig.cli` is still a stub (`support.py:418`).

## 2. Contradictions in the repository this gate cannot resolve alone

These are stated, not chosen. Each has a recommendation in §4.

| # | Where | One source says | Another says |
|---|---|---|---|
| X1 | the **mission Now tab** | rulebook §46.2: "It is the per-mission conversation, P16 seam S1"; A-05 surfaces "Now, mission Now tab" | ui-architecture §5 and research wireframe A.2: tabs "Outcome · Plan · **Now** · Evidence · **Thread** · Why · Timeline", Now = executions, Thread = the conversation; P16 built Now as executions; design system TUI row: "There is no Thread tab" (an as-built note) |
| X2 | the route's `focus` | plan: `focus=<object>` | the route: `focus=<kind>:<id>`, depth defaulting to 2 for non-projects |
| X3 | structural edges on the Relations tab | p18 I3: "none is on a Relations tab until P19" | p18 V8: "P19 unifies" (no rule given) |
| X4 | `EDGE_WORDS` home | p18 §4.1 (2): "moves into `relations.ts`" | the TUI needs the same words and cannot import TypeScript |
| X5 | S6 vs D6 | S6: "last snapshot persisted for a cold offline start" | D6/§13.5: "data is never cached" (the service worker) |
| X6 | ADR-0042 §1 verbs | K15 owner "P19.5 Core slice, P19" | ADR-0042 as-built: `emergency stop` and `stop <running mission>` "not part of this slice"; no P19 line names them |
| X7 | steering | rulebook §32: "queued-message steering into a running mission — DEFERRED with per-mission threads — P19" | not in the plan's P19 entry |

## 3. Scope

**In scope:** §0 items 1–4, each as a slice in §5.
**Out of scope (owner):** activity chip (P21), thread tints (P22), Q-A5 keys (before P26),
`what is running` and `live_work` (P21), model/location directives and the Resources UI for
ADR-0041 fields (P22), the 60 fps and touch manual evidence still owed by P18, the travelling-
marker flake (pre-existing, not fixed here), legacy migration (P22/P25.5), any P20 work.
**Ownership boundaries:** Core decides; clients render Core's reads and send Core's commands
(ADR-0011). Every new write is a Core command through an existing guard path; no client gains a
rule.

## 4. Decisions requiring approval

Each: problem · design · alternatives · test. **Bold = the recommendation.**

### B1 — One edge implementation (the P18 carry)

**Problem.** Three edge implementations (Core, SPA, TUI) held equal by a fixture (p18 V2).

**Design.** The Relations tab (SPA) and the TUI relations view read
`/v1/world/graph?focus=<kind>:<id>&depth=1&limit=1000` (X2: the plan's `<object>` is the route's
`<kind>:<id>`; `depth=1` is always sent). A client adapter (`toRows(read, focus)`, the only new
client code) turns each non-structural edge incident to the focus into today's `Edge` row: the
other end's node `label`, words from `edgeWords(field, isHolder, rel)`, `tier`, `inactive`. The
eight SPA mappers and the eight TUI mappers are deleted; their 18 `parity.json` cases move into
the route's tests as fixtures of real rows (the p18 A1 promise). `test_graph_parity.py` keeps
only the "every field Core emits has words" check. The p16 M06/M11/M12 and p18 M67/M68 mutants
are re-anchored on `graph.py` (same faults, now in the one implementation) and recorded in each
suite.
- **X3: structural edges stay off the Relations tab** (they are containment, already shown by
  the Plan tab and the project page; V8's "unifies" is satisfied by one source, not by more
  rows). Alternative: show them under a "contains" group.
- **X4: `EDGE_WORDS` moves to `tokens/edges.json`, generated by `gen_ui.py` into `relations.ts`
  (unchanged export) and the TUI's `_tables.py`**, like every other shared table (P17).
  Amends p18 §4.1 (2) in letter, not intent. Alternative: the TUI keeps hand-written words held by
  a parity test (a fourth copy of the vocabulary).
- The task row's "after …" hint (`Mission.tsx:326`, `screens.py:1041`) reads the task's own
  `depends_on` column; it is a field, not an edge assembly, and stays.

**Test.** Route tests carry the 18 cases; e2e: every Relations tab and the TUI relations view
equal the route's non-structural incident edges in words; a design gate fails if a client
module assembles an edge from a column.

### B2 — T2 on the Relations list and the TUI

**Design.** SPA: each Relations row carries `thread(changed(kind, id))` — the same `useChanged`
over `/v1/digest`, the same rule, words and A-06 fade as every other list. **TUI: the design
system's `›` marker on every TUI row whose object the digest names (Work, World, Attention,
Control lists and the relations view), plus the words in the row's screen-reader / plain text
form, cleared by the digest's own acknowledgement** — one digest read per screen refresh, no new
cursor. Alternative: the TUI relations view only (narrower than the design-system row).
**Test.** `test_spa_rows.py` extended to Relations; a TUI frame test row by row against Core's
digest before and after an acknowledgement; mutants on both.

### B3 — Per-mission conversations (S1) and the mission Now tab (X1)

**Core design (shared by every option).** A mission's thread is a `Conversation(kind='mission',
mission_id)` created **in the same transaction as the mission** (one per mission, enforced by a
new migration adding a unique partial index on `conversations(mission_id)`). Writes:
- a turn posted to the mission's conversation is the mission's: its intent resolves "this" /
  "the mission" to that mission (ADR-0042's "the single active mission" becomes "the thread's
  mission"); the reply follows the turn's conversation (unchanged rule);
- `Planning.hold`'s blocked card and a plan-approval card for the mission go to its thread
  **and** stay visible in primary (Needs you);
- a primary-conversation message whose `links[]` name the mission is shown in the thread by the
  read, not copied (ADR-0015 "linked into its thread").
Reads: `Mission` gains `conversation_id`; `GET /v1/conversations/{id}/messages` for a mission
conversation returns its own messages merged with linked primary ones by seq. No new route.
Existing missions get their conversation on first read (the migration back-fills one per mission).

**Surface (X1) — choose one:**
- **(a) The mission's Now tab is the mission's operational surface: its thread (composer and
  messages, T1 / A-05 travel to rows on the tab) above the executions it already shows** — the
  Now destination's own composition at mission scope (conversation + happening now). Matches the
  rulebook (the latest approved authority, §46.2/§46.3) and A-05's registry; adds no tab; keeps
  "execution detail opens within the Now tab".
- (b) A separate **Thread** tab as research/ui-architecture specify; Now keeps executions only.
  Requires amending §46.2, A-05's surface list and the design system's TUI row.
- (c) The Now tab becomes the conversation only; executions move elsewhere. Contradicts
  ui-architecture and P16; not recommended.

TUI: the same tab gains the thread as text with a `:` composer posting to the mission's
conversation.

**X7 steering.** **Out of P19**: delivering a queued message into a running execution is a harness
input path (P11) no ADR specifies; a turn on a running mission's thread is answered by Core like
any other turn. Recorded as a deviation for the user; alternative: specify it now (needs an ADR).

**Test.** Unit: one conversation per mission, the default mission of a thread turn, cards in both
places; integration over the routes; e2e: the tab, A-05 to a row on the tab, once; mutants.

### B4 — Plan edit (S2)

**Problem.** Specified only as "`POST /v1/plans/{id}/edit` → a new PlanVersion through P8's
validator" and "supersedes approvals". When an edit is allowed and what is editable are not.

**Design.** `POST /v1/plans/{id}/edit` (`approve` scope, idempotent, `expected_version`), body =
the full task list in the planner's own task shape. Allowed **only for the mission's current plan
while the mission is APPROVAL_REQUIRED** (the plan is awaiting the user): Core fires
`request_changes` and then `propose_plan` with the edited tasks, inside one transaction, with the
human as author (planner provenance fields `None`, `edited_by` = principal); the validator, the
supersession of approvals (P9 D14) and the auto-approve/needs-approval split run unchanged — an
edited plan that needs approval asks again. The SPA editor: rename, reorder, edit description and
acceptance, add/remove a task, change `depends_on`; the TUI shows the version, never edits.
Alternatives: (b) also while executing (a replan from the user — needs REPLANNING semantics P9 did
not give); (c) no editor, only the route (CLI).
**Test.** Validator refusals surface as the route's 422; supersession; idempotency; a stale
`expected_version` refused; mutants.

### B5 — Chat `approve` / `reject` (S3)

**Problem.** No approval card is ever posted, and a chat turn carries neither the poster's
`approve` scope nor step-up (§1.5). G1: "same `action_hash`, step-up, idempotency".

**Design.** (1) Core posts an `approval` card (approval id, `action_hash`, `expected_version`, the
action in words) to the mission's thread and to primary when an approval is created. (2) **A
message post may carry `decision: {approval_id, action_hash, expected_version}` from the card the
user is looking at; such a post requires the `approve` scope and the approval's step-up exactly
as `/decide` does, and the grammar's `approve` / `reject` then calls `authorization.decide` with
the poster's principal** — one decision path. A bare "approve" with no displayed card, or more
than one pending, is a clarification card. `NOT_YET` loses `approve`/`reject` (C-30).
Alternative: (b) the client recognises the words and calls `/decide` itself (simpler, but
grammar in the client — the logic P19 removes).
**Test.** G1 over both paths' PolicyDecision rows; a hash for another action refused; no step-up
refused; replay idempotent; mutants.

### B6 — Mission confirmation under `careful` (S4)

**Problem.** Unspecified beyond "a lifecycle rule, a small P9/P3 design note".

**Design.** **Reuse P9: a new action class `mission.start`; the engine asks policy before firing
START; under `careful` (and any profile whose rule for it is ASK) an Approval is created and the
mission waits in CREATED; deciding it (card, Attention, chat via B5) fires START; rejecting it
cancels.** No new route, card type or lifecycle edge; `standard` keeps auto-start (its rule
ALLOWs). Alternative: (b) a mission flag and `POST /v1/missions/{id}/start` (a new command).
**Test.** Each profile × start; a CREATED mission under careful never starts without the
decision; e-stop/pause interplay; mutants.

### B7 — Offline snapshot (S6, X5)

**Problem.** Persisting Core data in the browser contradicts D6's wording and puts world data at
rest on a device.

**Design.** The service worker stays shell-only (D6 holds for it). **The SPA itself writes, after
each successful read, the Now composition only (`/v1/status`, `/v1/digest`, `/v1/attention`,
`/v1/missions?state=active`) to IndexedDB keyed by Core origin, with `as_of_seq` and time. On a
cold start with no Core it renders that read-only under "Offline — as of <time>", with no command
enabled; cleared when the device's credential is revoked or the user leaves the device (Control →
Clients), and never written on a device paired as `observe`-only from another network.** Amends
§13.5's sentence for the SPA (not the worker). Alternatives: (b) nothing persisted (S6 not built,
recorded as a deviation); (c) every read cached.
**Security note.** This stores mission titles, attention text and status on the device. It is the
user's call whether that is acceptable on phones paired remotely.
**Test.** Offline cold start shows the snapshot read-only; no command reachable; revoke clears it;
no token or event stored.

### B8 — Qt shell attach, the "Open V1" link and the tray (S7 + carried Pause all)

**Design.**
- **Entry:** a V1 CLI verb `archeus gui` (target-architecture §5 names it) runs the existing Qt
  lineage in a V1 mode: discover Core via `core.json` (start it if absent, as `archeus core`
  does), mint a launch code with D2 scopes (observe+control+approve+admin, loopback only), load
  `<origin>/#launch=<code>`. The legacy `python -m claude_sessions gui` path is unchanged.
- **Profile:** a named persistent `QWebEngineProfile` under `ARCHEUS_HOME/QtWebEngine/` (the
  directory target-architecture §5 already reserves) — ADR-0044 T5; pre-load background from the
  OS scheme, never a hard-coded dark (ADR-0044 §4). GPU stays on (the legacy flicker rules).
- **Tray (design system §13):** `QSystemTrayIcon` with Open, Pause all, Emergency stop, Quit.
  **Pause all** sends `POST /v1/missions/pause-all` with the shell's own credential: the shell
  redeems a second launch code for itself with `observe`+`control` (a device row "desktop shell")
  and keeps it in memory only. **Emergency stop** runs `archeus estop`'s code without starting Core
  (execution-architecture). The icon shows the attention colour only while Attention's count is
  non-zero (design system :103), **read when the tray menu opens and when the window is hidden
  to the tray** — the shell holds no timer. Alternative: no attention colour on the icon in V1.
  Alternative for Pause all: drive the page (`runJavaScript` → `api.pauseAll`) — fails when the
  window is closed to the tray.
- **Legacy "Open V1" link:** the legacy GUI's sidebar foot gains "Open Archeus V1", which mints a
  launch code through the running Core (or says Core is not running) and opens it in the system
  browser (api-and-realtime §5.1 names this minter).
**Test.** Shell unit tests with a fake Core (launch, profile path, tray actions → the right
routes/code); manual on Windows: restart keeps theme, tray Pause all pauses, e-stop works with
Core down.

### B9 — Theme and contrast (ADR-0044) — implementation choices only

Fully decided; two choices: **a new Control → Appearance section (theme, contrast, and motion
moved there from About, as ui-architecture §6 lists motion under Appearance)**; storage key
`archeus-appearance` in localStorage beside `archeus-motion`. Gates T1–T6 as written.
Alternative: motion stays in About.

### B10 — Directives, the explanation card, the remaining grammar verbs (ADR-0042, X6)

**Design.** As ADR-0042 §1–§3 and Part H2 decide, for **accounts and harnesses only**: grammar
`use` / `don't use <account|harness>` for a named or the thread's mission; `intent.v1` gains
`resource_directive` (brain path); narrowing/preference applied to the mission's existing
preference fields with `message_id`/`intent_id` recorded; widening and standing → a PROPOSED
change card confirmed from a user device (`admin` for standing); unresolved names → clarification.
`why` emits the `route_explanation` card equal to the RouteDecision record (G5). **X6:
`emergency stop` (confirmation card) and `stop <running mission>` (one card doing pause then
cancel, C-33) land here too**, since ADR-0042 §1 lists them, K15 names P19 and nothing else owns
them. Alternative: leave those two unowned and record it.
**Test.** G3 (orchestration), G4, G5, G14 as written; G2's conversational half for e-stop.

### B11 — Generated client everywhere; client logic removed

**Design.** (1) `gen_api_docs.py` also generates **typed read paths** for the SPA
(`paths.mission(id)` etc.) and every raw `/v1/` literal outside `generated.ts` is replaced; a
design gate fails on a new one. (2) It generates a **stdlib Python client** (`archeus/cli/_api.py`)
from the same tables; the TUI transport and the CLI's `_get` both call it (p17 A3's alternative
(b), deferred to P19); Core's status, code and reason are preserved. (3) p17 A2's Python copies:
the **edge** copies go (B1); the **presentation** copies (explanations, `resource_line`,
connection machine, refusal wording) are words, which the plan does not call domain logic — they
**stay, still held by the golden fixtures**. Alternative for (3): generate them from a token file
like B1's words. (4) `rig.cli` is implemented over the V1 CLI so G3's `test_every_client_agrees`
can pass.
**Test.** The literal gate; the generated Python client's own contract test against `routes.py`;
CLI/TUI suites unchanged in behaviour.

### B12 — The unification scenario and G3

**Design.** `tests/v1/judge/test_g03_one_model.py` loses its xfail; a new e2e
`test_unification.py` runs the plan's scenario over one real Core: create in the SPA at desktop
width → observe at 390 px → approve at 390 px (a second device credential) → the fake harness
executes ("execute on PC") → review in the SPA at desktop width → inspect the result in the TUI
driver. "G3" here is testing-strategy §2's G3 (one model), not the orchestration G3 (no widening),
which B10 covers.

### B13 — Mutation strategy

`tools/mutate_p19.py`, ids P01…, every gate's direct test kills its mutant; mutants moved from
p16/p17/p18 by B1 are recorded in those suites with the reason. The P19.5 suites stay as they are.

### 4.1 Decisions taken (the user, 2026-10-03)

| Decision | Question | Answer |
|---|---|---|
| **B3 / X1** | What is the mission Now tab? | **(a)** The mission's thread (composer, messages, A-05 travel) above the executions the tab already shows; no Thread tab |
| **B7 / X5** | Build the offline snapshot? | **Yes, the Now reads only**, written by the SPA (never the service worker) to IndexedDB, shown read-only "Offline — as of <time>" with no command, cleared on revoke |
| **B5** | How does a chat `approve` reach the decision? | **Core decides**: the message post carries the displayed card's `{approval_id, action_hash, expected_version}`, requires `approve` and step-up as `/decide` does, and the grammar calls `authorization.decide` with the poster's principal |
| **B6** | Mechanism for confirmation under `careful` | **A P9 approval**: action class `mission.start`; under `careful` an Approval is created and the mission waits in CREATED; no new route or edge |
| **B1 / X3, X4** | Structural edges on the Relations tab; where `EDGE_WORDS` lives | **Structural edges stay graph-only; `EDGE_WORDS` moves to `tokens/edges.json`**, generated into `relations.ts` (same export) and the TUI's `_tables.py` |
| **B2** | Which TUI rows carry T2 | **Every digest-named row** (Work, World, Attention, Control lists, the relations view), `›` from `/v1/digest`, cleared by its acknowledgement |
| **B10 / X6, X7** | The unowned verbs; steering | **`emergency stop` and `stop <running mission>` land in P19 with B10; steering stays out of P19** (it needs its own ADR) and is recorded as a deviation |
| **the rest** | B4, B8, B9, B11, B12, B13, the order in §5 | **Approved as written** |

## 5. Slices and order (after approval)

1. **B1 + B2** edges and T2 (Relations list, TUI) — no Core change.
2. **B11** generated clients (unblocks every later client edit) and `rig.cli`.
3. **B3** S1 per-mission conversations + the mission Now tab (carried behaviour A).
4. **B5** chat approve/reject, then **B6** confirmation under careful (uses B5's card).
5. **B10** directives, explanation card, remaining verbs.
6. **B4** plan edit.
7. **B9** Appearance.
8. **B7** offline snapshot.
9. **B8** Qt attach, tray Pause all (carried behaviour C), legacy link.
10. **B12** unification scenario; full verification; P19 as-built (§13); report R13-ready and stop.

Each slice: its own commits, targeted tests, the relevant client/Core/TUI suites, its mutants.

## 6. Data model and storage impact

One migration (B3: unique partial index on `conversations(mission_id)`, back-fill one mission
conversation per existing mission; pre-migration backup as for 0012). B6 adds an action class (a
policy table value, no schema). B4 adds `edited_by` to Plan if approved (schema). IndexedDB store
for B7 (client). Qt profile directory (B8). Nothing else.

## 7. API, CLI, UI and TUI impact

New: `POST /v1/plans/{id}/edit` (B4); `decision` on the message post (B5); `Mission.conversation_id`
(B3); `archeus gui` (B8). Changed: message read merges linked primary messages for a mission
conversation (B3); `intent.v1` (B10). Regenerated: API reference, `generated.ts`, the new Python
client, `_tables.py`, tokens.

## 8. Failure modes and races

A thread turn racing a mission's end: the intent resolves against the state at apply time, as
every verb does. Two devices deciding one approval: the existing `expected_version` and the unique
live index. Offline snapshot older than a revoked credential: cleared on the next online start
(the revocation is read first). Tray Pause all with Core down: says Core is not running; e-stop
still works.

## 9. Security

B5 and B6 widen nothing: a decision still needs `approve` and step-up. B7 stores data at rest
(user decision). B8's shell credential is in memory, loopback, `observe`+`control` only. B10: only a
user principal's message carries a directive; widening needs confirmation (G3 orchestration).

## 10. Evidence required before P19 is declared complete

Every slice's tests and mutants; the full V1 suite, client typecheck and tests, every P19 mutant
killed, the P16/P17/P18/P19.5 suites still green after B1's re-anchoring; G3 passes; manual on
Windows: the Qt shell (launch, restart keeps theme, tray Pause all, e-stop with Core down); the
offline cold start on a phone.

## 11. Deviations declared up front

1. X2: the plan's `focus=<object>` is the route's `focus=<kind>:<id>`.
2. X4 (if B1 approved): `EDGE_WORDS` source moves to a token file; `relations.ts` keeps exporting it.
3. X7: steering into a running mission is not built in P19 (the user, 2026-10-03; it needs its
   own ADR). The rulebook's "DEFERRED … P19" row is answered by this record.
4. The travelling-marker flake is pre-existing and not touched.

## 12. Deviations and new decisions for the user's review

(empty until implementation)

## 13. As built

(empty until implementation)
