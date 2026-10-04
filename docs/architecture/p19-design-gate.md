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

**Slice 1 (B1 + B2), 2026-10-03.**

1. **The TUI's thread rule is `│`, not the design system's `›`** (deviation). Since P17 `›` is
   the TUI's cursor marker (`app.py`, drawn in the column before every row), so a `›` rule would
   make a changed row and the focused row look the same — focus ≠ attention (rulebook §15). The
   rule is `│` in thread ink on the row's own left edge (the column the row's indent already
   leaves, so nothing moves; `|` on an ASCII terminal), on every row that names an object the
   digest names, the digest's own rows included as the SPA's are. The design system's TUI row
   records it as built. Reversible: the glyph is one constant.
2. **A Relations list now shows the reverse edges the route reaches** (consequence of B1, not a
   deviation). The old mappers listed what each object's own read carried; the route at depth 1
   lists every non-structural edge incident to the object. A mission's list now also names its
   attempts (`executions.mission_id`), the runs that created it and the verifications of it; an
   execution's, the attempt that continues it and the verification that checked it.
3. **Reverse edges the route does not reach** (found, not changed). `graph._holders` has no
   branch for a session's executions (`Execution.session_id`), nor for context packages, route
   decisions or policy decisions. So a session's list does not name the attempts that ran in it
   (it never did); the other three kinds have no Relations tab. Adding holder branches is a Core
   change to the P18 route; not made here. `test_every_relations_list_is_its_objects_one_hop_of_the_graph`
   asserts what holds: no row the graph lacks, every edge the object holds.
4. **A plan version's number moved from the row's words to its label**: the old list said
   "plan v2"; the route's words are "plan" and the link names the version ("plan v2", the
   existing `RefLabel`), so the relationship filter shows one "plan" chip, not one per version.
5. **Mutants moved** (B1, B13): p16 M06, M11, M12 re-anchored on `graph.py`, guarded by
   `test_graph_parity.py` over the frozen cases the mappers carried
   (`tests/v1/unit/fixtures/graph_edge_cases.json`); p18 M67 and M68 retired (the fault, a
   client's own list dropping an edge, can no longer be written; M66 keeps it in Core). All
   re-run killed, with p17 M24 and p18 M02, M04, M66.

**Slice 2 (B11), 2026-10-03.**

6. **The Python client's namespace is `endpoints`, not `paths`.** The SPA's builders are
   `paths.*` (generated.ts); in Python the TUI's boundary test already forbids the name `paths`,
   which there means the filesystem. `archeus/cli/_api.py` (generated by `gen_api_docs.py`)
   builds the path of every route, reads and commands both, so a call site stays
   `core.post(endpoints.pause_mission(mid), body)`; no Python `api` wrapper was generated, since
   the transport already sends. The TUI's import boundary names it as its fourth seam.
7. **`/v1/sessions` declares its query** (`project`, `mission`, `state`) in `routes.QUERY`, the
   table the generators read; the handler already read all three. Documentation only: no
   request changes.
8. **A query value is percent-encoded** by both generated clients (`focus=mission%3Amsn_…`,
   `encodeURIComponent` / `quote(safe='')`), where hand-written paths sent the colon raw; Core
   decodes either. Two tests that pinned the raw string now pin the encoded one.
9. **A new CLI form, `archeus status <mission-id>`**, prints the mission's state as Core reports
   it, so G3's `test_every_client_agrees` reads the CLI as a client (B11 (4)); `rig.cli` runs the
   CLI in-process. The CLI's `_get` now uses the TUI's transport and prints Core's refusal in
   words (`sync.explain`) on stderr before the caller's own line, where it used to drop it.
10. **Command-bar invalidation narrowed** from every `/v1/conversations/` read to the primary
    conversation's (the only one that existed); B3 widens it to the mission threads it adds.
11. **P19.5's N199 re-anchored** (`depth: 1, limit: MAP_CAP`, the map's read now built by
    `paths.worldGraph`): same fault, same guard, killed. No P19.5 behaviour changed.

**Slice 3 (B3, the mission Now tab), 2026-10-03.**

12. **No migration, no `Mission.conversation_id`, no back-fill** (deviation from B3's storage
    design; the behaviour is B3's). A mission's id names its thread, as `primary` already names
    the primary conversation: `GET/POST /v1/conversations/<mission-id>/messages`. The thread is
    made by `conversation.thread()` on the first turn posted to it, and Core's one writer makes
    "at most one per mission" hold without the unique index (`tx.where` then insert in one
    serialised transaction). An existing mission needs nothing back-filled: its thread is empty
    until used, and already shows the primary messages that link it. Reversible: the index and
    the column can still be added if a second writer ever exists.
13. **Cards stay in the primary conversation** (B3 said "to its thread and stay visible in
    primary"). Nothing is copied: `Planning.hold`'s blocked card is written once, in primary,
    with links naming the mission, and the thread read shows it (ADR-0015 "linked into its
    thread"). The same holds for B5's approval card.
14. **A bare verb in a thread** (`pause`, `resume`, `stop`) is about the thread's mission
    (grammar `resolve(…, mission=)`); `reprioritise`, `status` and `why` keep their objects. The
    brain path reads a thread turn as it reads any turn (its context is unchanged); its reply
    lands in the thread.
15. **Found while building it:** the thread's line had picked the reply's own link card as its
    "row" — on Now the conversation sits outside `.now-main`, so it never could; on the mission
    tab it is inside the scope. A message's card is never a row now (`rowOf`), and the line is
    rendered into `document.body`, since the inspector is a size container and a size container
    is the containing block of a fixed descendant. Neither changes Now. A row below the fold
    still gets no line (A-05), so the conversation above the work can leave an attempt off
    screen on a short window.

**Slice 4a (B5, chat approve / reject), 2026-10-03.**

16. **The approval card carries the ref, not the hash** (deviation from B5 (1), which listed
    `action_hash` and `expected_version` on the card). The card is `{type: 'approval', ref}`, the
    existing card type; a client reads the hash, version, state and eligibility from
    `GET /v1/approvals/{id}`, the same read Attention's card makes. A hash copied into a message
    would be a second copy of the approval that a supersede leaves stale; read live, the card
    always sends what the approval now is, and a superseded one shows as closed.
17. **A bare `approve` / `reject` is a declined reply listing the pending approvals' cards**
    (B5 said "a clarification card"). Up to ten, and in a mission's thread only that mission's.
    A clarification would ask the user to pick one, and the pick would still have to be a card
    carrying its hash, so the cards are the choice; nothing is ever decided from the words alone.
    `NOT_YET` is gone (C-30).
18. **A PIN step-up is given in Attention, not in the conversation.** The message post accepts
    `step_up` exactly as `/decide` does (G1 holds over both, `test_presence.py`), but neither
    client's composer asks for a PIN: on a paired client whose step-up is a PIN the card says so
    and links Attention; on one with no PIN it says it cannot. A local client meets step-up by
    being local and decides in the conversation.
19. **One transaction, and a refusal writes nothing.** The route checks the `approve` scope
    before running anything; Core then records the turn, reads it (`control_verb`, via
    `grammar`, target the approval), decides through `authorization.decide` with the poster's
    principal, and replies, in the turn's transaction. A wrong hash, a missing PIN or a word other
    than approve / reject rolls the turn back with the decision. A DENY found at decide time is
    `423 policy_denied`, as on `/decide`. The reply carries the approval's card again, so the
    thread shows the decided state where the decision was made.
20. **Mutants P31-P40** (B5): the card never posted, the card not linking its mission, the scope
    check removed, the client's hash ignored, the step-up proof dropped, a bare `approve` pointing
    at nothing, the SPA's and the TUI's card sending a bare word, the SPA's card deciding in the
    primary conversation, and the TUI offering a PIN step-up it cannot take. All ten killed.
21. **`test_one_name_per_command` reads a turn's word as its decision.** The card's two buttons
    send `postMessage` with `text: 'approve'` / `'reject'`, so the gate's parser now takes `text`
    beside `decision`/`verdict`/`action`/`choice`; otherwise the composer's Send and the card's
    Approve would read as one command with two names. The card's calls are written inline in its
    buttons, as the gate requires of every command.
22. **Found, not changed:** two e2e tests are intermittent on this machine independent of B5 —
    `test_spa_marker.py::test_the_marker_travels_once_from_the_execution_to_its_task` (passes
    and fails on consecutive runs alone; no approval in its path) and
    `test_spa_resources.py::test_an_accounts_policy_is_a_form_over_cores_route` (failed once in
    the full run, passes alone).

**Slice 4b (B6, confirmation under `careful`), 2026-10-03.**

23. **A migration after all** (deviation from §6, which said B6 adds "a policy table value, no
    schema"). `approvals.plan_id` was `NOT NULL`, and a start approval exists before the mission
    has a plan. `0014_start_approvals.sql` rebuilds `approvals` with `plan_id` nullable (SQLite
    cannot drop a `NOT NULL`) and copies every row across unchanged. The `action_hash` of a
    `start` approval binds the mission alone, and `actions.action_hash` refuses a start binding
    that names anything else.
24. **`mission.start` is a Core class, not a task class.** It lives in `actions.CORE_CLASSES`;
    `RULE_CLASSES = ACTION_CLASSES + CORE_CLASSES` is what a rule and a judged action may name.
    The planner, the plan validator and `Task` still read `ACTION_CLASSES`, so no plan can declare
    it. `standard` and `autonomous` ALLOW it, `careful` ASKs. The profile table changed, so
    `PROFILES_VERSION` is 2 and the built-in rule ids are `@2`.
25. **The e-stop does not hold a start (for the user's review).** Before B6 the engine started a
    CREATED mission while disarmed: the e-stop holds what runs, and starting only leads to
    understanding and planning, both of which stay held at dispatch. B6 keeps that rather than
    change it quietly: `judge_start` evaluates with `estop=False`, so `standard` still starts
    under the e-stop and `careful` still asks. If the e-stop should also hold starts, it is one
    line and one test.
26. **A user's DENY rule on `mission.start` holds the mission without asking.** It waits in
    CREATED, nothing is recorded (it is judged again on every pass, and recording each pass would
    flood the decisions), and it starts once the rule is retired.
27. **The stub policy exempts Core classes.** `FixedPolicy('ASK')` means "every task's action
    asks"; without the exemption every test built on it stalled in CREATED. `by_class` can still
    name `mission.start`.
28. **The clients take the class list from Core.** The TUI's Control matrix and Simulate field
    and the SPA's `Control.tsx` had each kept a hand copy of the thirteen classes, which B6 would
    have left a row short. Both now read the classes off `GET /v1/policies`' profiles.
29. **Mutants P41-P50** (B6): `careful` allowing the start, the engine firing START without
    asking, a waiting start asking again on every pass, approving not starting, rejecting not
    cancelling, a start approval judged eligible like a plan approval, the e-stop holding a start,
    a DENY rule asking, the stub policy holding every mission at its start, and the TUI's matrix
    dropping a class. All ten killed. P43 survived the first run: the engine passes over a
    waiting mission once, so the test now restarts Core and asserts the start is still asked only
    once.

**Slice 5a (B10: `emergency stop`, `stop <running mission>`, the explanation card), 2026-10-03.**
The user chose, before implementation: the mixed confirmation path, change cards in the
conversation only, and B10 in two commits (5a, then 5b).

30. **`emergency stop` only asks.** The grammar reads exactly `emergency stop` (case, spacing and
    end punctuation aside; anything longer is the brain's). The reply carries an `estop` card and
    nothing is engaged. The card's button is the strip's own command, `POST /v1/estop` with the
    `control` scope, so the sentinel is written first exactly as from the strip (G2). A client
    shows "The emergency stop is engaged." instead of the button while `/v1/status` says
    disarmed.
31. **`stop <running mission>` is one confirmation card** (C-33). `stop` on an EXECUTING mission
    (named, or bare in its thread) answers with a `stop` card and stops nothing; `stop` on any
    other mission cancels it as before, and `cancel` is unchanged. Confirming the card posts a
    turn that says `stop` and carries `confirm: {message_id}`, the message holding the card. Core
    reads the mission from that card, never from the words, and in the turn's transaction
    pauses it if it is EXECUTING and then cancels it: two existing edges, no new one. A mission
    that can no longer be cancelled is `422 invalid_transition` and the turn is rolled back. A
    confirmation naming a message without a `stop` card, or not saying `stop`, is `400` and
    writes nothing.
32. **One new optional field on the message post** (deviation from §7, which lists only
    `decision` for the message post): `confirm: {message_id}`. A body carrying both `decision`
    and `confirm` is refused. Scope: the route's `control`.
33. **Two card types** (`estop`, `stop`), added to `CARD_TYPES`. The `estop` card's ref is the
    global workspace, as the `status` card's is.
34. **`why` attaches a `route_explanation` card** whose ref is the RouteDecision, and the
    reply's text is that record's `explanation` (G5). For `why <execution>` the text is the live
    explanation (P12's `explain`, which quotes the record) and the card names the execution's own
    RouteDecision. As with the approval card (item 16), the card carries the ref and a client
    reads the record itself.
35. **Not built here:** `stop all` (C-33 maps "stop/pause all" to Pause all; ADR-0042 §1 and B10
    name only `pause all`), so `stop all` still resolves a mission titled "all" or goes to the
    brain.
36. **Mutants P51-P62** (B10a): `emergency stop` read from longer words, the card missing, `stop`
    on a running mission a plain cancel, the confirmation not pausing first, accepting any
    message or any word, `why` without its card or with words that differ from the record, the
    TUI's and the SPA's stop card confirming the mission instead of its own card, and both
    clients' emergency-stop card running another command. All twelve killed.

**Slice 5b (B10: resource directives for accounts and harnesses), 2026-10-03.**

37. **The grammar.** `use <account|harness> [for <mission>]` and `don't use` / `do not use` the
    same. With no mission named, the thread's mission, and the scope is read as ambiguous; in
    the primary conversation a mission must be named. An account is named by its label or id,
    a harness by its id among the execution harnesses Core has (the adapter registry's, handed
    to `Conversations`, since harnesses are not rows); "account X" / "harness X" says which.
    Anything that does not resolve to exactly one object goes to the brain, never guessed.
38. **The brain.** `intent.v1` gains `resource_directive`: `scope` (mission, task, standing,
    ambiguous) and `prefer` / `forbid`, each `{accounts, harnesses}` as names said. Core resolves
    every name; one that resolves to none or several is a clarification and nothing is written
    (G4). It applies to the mission the request creates or continues. With no such request it
    applies to the thread's mission, is a standing proposal, or, in the primary conversation,
    asks which mission. A `preference` message carrying a directive is not also a knowledge
    candidate.
39. **Narrowing and preference apply at once, with their source** (G4). A forbid joins the
    mission's forbidden list (and leaves its preferred list); a preference of a `normal` account
    or of a harness joins the preferred list. Each entry is recorded in a new
    `resource_preferences.directives` list as `{key, id, message_id, intent_id}`, and the
    `mission.updated` event carries both ids. Deviation from ADR-0042 §3's "on the preference
    version it produced": mission preferences are not versioned, so the provenance rides on
    the entries. A user device setting the mission's resources replaces the lists and clears
    `directives`. `since` is reset, as the route resets it.
40. **Widening and standing are only proposed** (G3), on a `change` card (a new card type) that
    carries Core's command: `{name, id, body}` plus `says`, `scope` and `based_on`. Widening is a
    preference for a `last_resort` or `explicit_only` account, or for something the mission
    forbids: the card's command is `setMissionResources` with the full lists that would result,
    and `based_on` is the mission's `since`, so a client closes the card once the mission's
    resources were set again. Standing is H2's example: a standing forbid of an account proposes
    `setResourcePolicy` with `consumption: explicit_only`. A standing preference and a standing
    harness rule have no existing route, so the reply says so and proposes nothing. An
    ambiguous `don't use <account>` applies to the mission and also offers the standing card. A
    `task` scope applies to the whole mission and the reply says so. Confirming runs the
    existing `admin` route from a user device; the brain's principal writes nothing.
41. **A conversation's preference never lifts a protected account** (G14). The router's `_named`
    no longer counts the preferred accounts a directive added (`conversational` in the task's
    requirement), so such a preference orders candidates and makes nothing eligible (ADR-0042
    §3), even if the account's class changes after the directive applied. A small router change,
    beyond §7's list.
42. **Only a user device's message carries a directive.** Any other principal's message is
    declined and nothing is changed.
43. **Clients.** The SPA renders the `change` card with the commands' existing names ("Save
    preferences", "Save policy"; one name per command) and marks each directive entry on the
    mission's resource line "(from your message)". The TUI's card uses its own existing name for
    the mission route, "Set routing preferences", and "Save policy" for the account policy. The
    change card is in the conversation only, not in Attention (the user's decision; ADR-0042's
    UI row says Attention).
44. **Not built here, as the gate says:** model and location directives, tier requirements and
    pins (P22), "keep this work local" (data class, ADR-0035), and project defaults (P22, G11).
45. **Mutants P63-P74** (B10b): a forbid that narrows nothing, a directive without its source
    message, a protected account preferred without a confirmation, a forbid lifted at once, an
    unresolved name guessed, an ambiguous `don't use` changing the global policy, a non-device
    message carrying a directive, the router lifting a protected account for a conversation's
    preference, the router not told which preferences a conversation added, a standing directive
    applied to the mission, and both clients' change card sending a body of their own. All
    twelve killed. Two earlier mutants' anchors moved with this slice and were re-anchored, and
    both are still killed: p19 P26 (the intent worker's grammar call gained `harnesses`) and
    ap1 A06 (`_named` gained `conversational`).
46. **Found by the full run after 5a was committed:** 5a changed `why`'s reply (it now carries
    the card), and two tests pinned the old shape: `test_spa_thread.py`'s "a link with no card"
    case (Alpha is still a bare link; the one card is the route decision's) and
    `test_context_capacity.py`, which called `_why` directly. Both are updated in 5b. The 5a
    commit was made on the targeted suites only.
47. **A documentation fix to B6.** B6's commit staged only its own lines of `domain-model.md`
    with a zero-context patch, and the other session's uncommitted lines above it shifted the
    position, so B6's `start`-approval paragraph landed inside §9.4's first lines. 5b's commit
    puts it back at the end of §9.3, where the working copy always had it.
48. **The final full run** (B10a + B10b): 2517 passed, 3 failed, 13 skipped, 5 xfailed. The
    three failures are timeouts under full-suite load, and each passes alone (three runs each
    for the last two): `test_spa_marker.py` (the known flake, §3), `test_spa_resources.py`'s
    account-policy form (item 22) and, newly seen, `test_spa_arrival.py::test_reduced_motion_says_the_rise_and_pulses_nothing`
    ("the arrival is still announced"). None is in code B10 changed. They are recorded, not
    fixed.

**Slice 6 (B4, plan edit), 2026-10-03.**

49. **The route as B4 designed it.** `POST /v1/plans/{id}/edit`, `approve` scope, idempotent.
    The body is `tasks` (the whole list in the planner's resolved task shape, `PlanTaskSpec`)
    and an optional `expected_version`, which is the plan row's version, as an approval's is
    on `/decide`. Core checks the principal itself as well (a user device holding `approve`).
    Only the plan in force (PROPOSED) of an APPROVAL_REQUIRED mission is edited. Anything
    else is `422 invalid_transition`, and a stale version is `409 version_conflict`. Core
    fires `request_changes`, then `propose_plan` with the edit, in one transaction. The
    validator, the supersession of approvals (P9 D14) and the plan gate's auto-approve /
    needs-approval split are not touched, so an edit that still needs approval asks again with
    a new approval and card.
50. **No migration** (deviation from §6, which said B4 adds `edited_by` "(schema)"). Plan
    fields live in the row's JSON body, so `edited_by` is an entity field (`_REFS` principal,
    frozen like the rest). The digest includes it only when it is set. A planner's version
    hashes exactly as it did before B4, so every stored digest stays valid.
51. **A validator refusal is `422 guard_failed`**, the refusal of the version's own `ready`
    guard (plan DRAFT → PROPOSED), with the validator's sentences as its reason. Nothing is
    written. Beyond `validate.problems`, an edit also refuses an input taken from a task that
    is not in the plan, which the planner's handle check covers on its path. The planner's
    path itself is unchanged.
52. **Reordering is the order sent** (B4 named "reorder" without saying how it is carried).
    Core keys the tasks `t1…tN` in dependency order, stable in the order sent, exactly as it
    keys a planner's labels (`planner.resolve`). It remaps `depends_on` and `inputs.from_task`.
    A task's labels in the body are only labels.
53. **What the edit does not carry, it inherits.** The new version keeps the replaced
    version's `summary`, `inputs`, `assumptions`, `questions`, `risks`, `refs` and `rollback`.
    Its `coverage` is recomputed from its own tasks' `serves` (`planner.coverage`, now shared
    with the planner). It is judged on the replaced version's explicit requirements
    (`planner.explicit_handles`), so an edit cannot drop the only task serving one. Planner
    provenance (`round_seq`, `route_decision_id`, `context_package_id`) is None.
54. **Core's serialisation edges are derived again, never adopted.** A client sending back the
    task list as read also sends the dependencies Core added (D8). The replaced version's
    `serialised` edges are dropped from the body before validation, and `serialise()` adds
    them again, with their reason, wherever `touches` still overlap. So the new version's
    `serialised` still lists exactly Core's edges.
55. **Found, not changed: an edit spends a replan.** The replan budget counts
    `plan_version - 1`, so each edit, like each `request_changes` re-plan before it, is one
    replan of `max_replans`.
56. **Clients.** The SPA's Plan tab offers "Edit plan…" only while the plan is in force and
    PROPOSED and the mission's table has `request_changes` from its state. The editor
    renames, sets the description (`objective`) and the acceptance criteria (text and check),
    reorders, adds and removes a task, and sets what a task waits for. Every other field is
    sent back as read. "Save plan" is the command's one name. The new task's kind is chosen
    from `TASK_KINDS`, which `gen_api_docs.py` now generates beside `MISSION_STATES` rather
    than the client keeping a copy. Both clients mark a person's version "edited by a
    person". The TUI shows it and never edits (a test fails if any TUI module names the
    command).
57. **Pins B4 moved.** P8's boundary that no plan route takes a command (E7 in
    `test_api_structure.py`, H04 in `test_planning_http.py`) now admits exactly
    `/v1/plans/{id}/edit`. The `approve` scope, which reached only decisions, also reaches
    the edit, a decision on the plan awaiting approval. Moving the planner's `inputs` line into
    the shared `coverage` helper moved p8 M06a's anchor; it is re-anchored on the same line
    and still killed.
58. **Mutants P75-P89** (B4): a replaced version edited, the validator's 422 skipped, the
    explicit requirements ignored, Core's serialisation edges adopted, the labels kept instead
    of Core's keys, the author not recorded, the replaced version's lists dropped, its
    coverage copied, the mission not sent back first, a stale version accepted, the route on
    `control`, a planner's digest changed, the SPA sending another order, the SPA offering the
    editor in any state, and the TUI not marking a person's version. All fifteen killed. P87
    survived the first run: the e2e's only reorder was also forced by a dependency, so a
    reversed list keyed the same. The e2e now saves the reorder alone and the dependency as a
    second edit.
59. **The full run** (B4 on B10): 2535 passed, 1 failed, 13 skipped, 5 xfailed. The failure is
    `test_spa_marker.py`, the known flake (§3, item 22); B4 does not touch the code it runs.
    The two other intermittent tests of item 48 passed in this run, which says nothing about
    whether they are fixed.

**Slice 7 (B9, Appearance), 2026-10-04.**

60. **As B9 chose.** Control → Appearance is a new section (between Clients and About) holding
    theme (System · Dark · Light), contrast (System · Standard · High) and motion, which moved
    there from About. The choice is stored under `archeus-appearance` in localStorage beside
    `archeus-motion`, per client and never synced; nothing in Core reads it (ADR-0044 "Core/API:
    none" holds: no route, schema or Core file changed).
61. **The boot is generated and emitted as a hashed asset** (B9 did not say how a `'self'` boot
    script is built or cached). `tools/gen_ui.py` writes `src/state/appearance.js` from
    `tokens.json`, so its theme list is the token sets and nothing else. It is a classic
    parser-blocking script: a module is deferred and cannot promise to run before the
    stylesheet paints. Vite does not bundle a classic script, so a small plugin in
    `vite.config.ts` emits it as `assets/appearance-<hash>.js` and points `index.html`'s tag at
    it. That puts it under Core's existing `/assets/*` route and the service worker's
    cache-first asset rule, so the offline start (T5) needed no Core route and no worker change.
    The build prints Vite's "can't be bundled without type=module" note for it, which is the
    intent. The boot owns the storage: Control → Appearance calls `archeusAppearance(next)`,
    which stores the choice and applies it, so the key and the allowlist live in one file.
62. **The attributes and the `system` mapping.** The boot always sets `data-theme` (system,
    dark, light) and `data-contrast` (system, standard, high) on `<html>`; a stored value that
    is not a token set (a legacy palette name) is `system`. `tokens.css` maps `system` with
    `:root:not([data-theme='dark'])` under `prefers-color-scheme: light` and
    `:root:not([data-contrast='standard'])` under `prefers-contrast: more`, so a page whose
    boot did not run still follows the OS as before. Explicit choices are
    `:root[data-theme='light']`, `:root[data-theme='dark']` (only `color-scheme`) and
    `:root[data-contrast='high']`. No token value changed.
63. **The high-contrast component rules follow the same switch, and forced colours still win.**
    `app.css`'s `prefers-contrast: more` block (thicker borders, the thread rule and line in
    `focus`) now also applies under an explicit High and not under an explicit Standard. Its
    prefixes are wrapped in `:where()` so they add no specificity: the forced-colours block
    after it keeps winning on source order (T3), as it did before B9.
64. **The theme colour is no longer hard-coded** (§1.9 listed `#0E1116`). `index.html` carries
    two `theme-color` metas, one per OS scheme; the boot fills them from the token `bg`s, both
    with the chosen theme's when one is chosen, and sets `color-scheme` to match. The PWA
    manifest's `background_color` stays the dark `bg`: a manifest has no per-scheme value.
65. **The TUI's Appearance section** (deviation: B9 and ADR-0044 §6 say the TUI is unchanged,
    but the Control sections are one shared table, p17-design-gate A1). The TUI's Appearance
    names its own theme (`--light` / `ARCHEUS_TUI_THEME`), says the app chooses its own, and
    holds the motion line that moved out of About. It offers no command and reads no app
    preference; the TUI's theme selection is unchanged.
66. **T5's Qt half is B8's.** The persistent QtWebEngine profile and the OS-following pre-load
    background are B8's (§4 B8, "Profile"); B9 tests a reload, another tab of the client and an
    offline start from the service worker with Core out of reach.
67. **Tests.** `test_spa_appearance.py` (T1, T2, T3, T5, T6 in a real browser, with a check
    floor), `test_design_gates.py::test_t6_*` (the selectable themes are exactly the token sets
    the contrast gates run over, T4; the boot is a classic script ahead of every stylesheet and
    module, T6), `tests/v1/tui/test_appearance.py`. A fast reload can open the event stream
    before Core has seen the old page's close, which Core answers 429; the e2e's console check
    ignores that one status.
68. **Mutants P90-P100** (B9): an explicit Light not applied, the OS's light scheme over an
    explicit Dark, an explicit Standard not holding off the OS's contrast, an explicit High not
    applied, a theme stopping a forced colour, the high-contrast rule outranking the
    forced-colours block, any stored name taken as a theme, the choice kept for one tab, the
    theme colour fixed at dark, the boot deferred, and the TUI naming a theme not its own. All
    eleven killed. P92 survived the first run: under an explicit Light the theme's own rule
    outranks a mutated `:root`, so the e2e's Light case could not see it; it now also checks
    Dark with Standard under an OS asking for more contrast. **A pin B9 moved:** P19.5's N151
    (the high-contrast thread line) anchored on the old `.thread-line` rule inside
    `prefers-contrast: more`; it is re-anchored on the same rule under its new `:where()`
    prefix and still killed. No P19.5 behaviour or test changed.
69. **The full run** (B9 on B4, `tests/v1`): 2542 passed, 2 failed, 13 skipped, 5 xfailed. The
    failures are the two intermittent tests of item 48, `test_spa_arrival.py`'s reduced-motion
    test and `test_spa_resources.py`'s account-policy form. Neither uses the motion control B9
    moved (the first emulates `reduced_motion`; `applyMotion` and `data-motion` are unchanged)
    and together they passed five of six isolated runs, so they stay classed as already known,
    not as B9's. `test_spa_marker.py`, the known flake, passed in this run, which says nothing
    about whether it is fixed. A run over the whole tree also failed
    `tests/test_cli_help.py::test_a_deferred_v1_verb_imports_only_its_dispatcher`
    (`archeus.cli._api` imported with the dispatcher); it fails the same way on `67a032c`, before
    B9, and is outside the `tests/v1` baseline.

**Slice 8 (B7, the offline snapshot), 2026-10-04.**

70. **As B7 designed it.** The service worker is unchanged and stays shell-only (D6). The SPA
    keeps the Now composition in IndexedDB (`archeus-snapshot`, store `now`, a separate database
    from the device token's), one entry per read keyed `<Core origin> <path>`, each with its
    origin, its data, the `X-Archeus-Seq` it was read at and the time. It is written after every
    successful read of those paths (the read cache's new `onRead`), and once from what is
    already read when the client's own record arrives, so a read that finished before `/v1/sync`
    answered is not lost. Nothing else is kept: no token, no event, no other read. Appearance is
    not part of it (B9's preference stays in localStorage).
71. **The missions read** (deviation: B7 names `/v1/missions?state=active`, which Core refuses,
    since `state` must be a mission state). The snapshot keeps `/v1/missions`, the read Now
    already makes, filtered at write to the unsettled missions (`activeMissions`, what Now's
    Happening now and Upcoming show). No Core query was added, and no settled mission is kept.
72. **The cold start.** When the stored token's first read fails for want of a network (status
    0) and every Now read is kept for this origin, the app opens on the snapshot instead of "could
    not start". `OfflineNow` is its own small view, read-only by construction: plain text under
    "Offline — as of <time> (<age>)", with the state sentence, the running count (and the
    emergency stop, if engaged), Needs you, Happening now, Since you last looked and Upcoming.
    No link, button or field, no read of its own, and no state colour or glyph beyond the
    existing badges. "As of" is the oldest kept read's time. A missing read means no snapshot.
    The live Now's map, automation line, decisions and conversation are other reads and are not
    shown. Its heading has no `tabIndex` because the view has no navigation, which also keeps
    an older mutation anchor on Now's heading unique.
73. **Cleared** on every route out of the credential. The client revokes itself (Control →
    Clients: the existing Revoke on "this client", which is how a user leaves the device; no
    new control). Any 401 while open (the connection's `unauthenticated` or `revoked`): nothing
    is written after it. A 401 on the next online start, read before anything is shown (§8).
74. **Never written on a client paired `observe`-only** (B7: "from another network"). Core
    cannot tell networks apart, so the rule is the client's own record: `origin: paired` and
    no scope but `observe`. A local client, or a paired one with any other scope, keeps one.
75. **§13.5 amended for the SPA** in p16-design-gate: the worker's sentence holds; the SPA's
    own snapshot is this slice's. The security note stands: a phone paired with more than
    `observe` keeps mission titles, attention text and status at rest.
76. **Tests.** `test_spa_offline_snapshot.py`: what is kept (four paths keyed by origin, with
    seq and time; no token, no event, no settled mission), the offline cold start through the
    service worker (as of, the rows, no command, link or field, Tab reaches nothing, nothing
    sent), clearing (self-revoke, revoked while open, revoked while away), and an
    `observe`-only paired client keeping nothing, and, on a quiet Core with `/v1/sync` held
    until the Now reads have answered, those reads kept once the client is known.
    `test/snapshot.test.ts`: the kept paths, the
    missions filter, the `observe`-only rule, "as of", and the worker still never touching
    `/v1/`. One run of the e2e file failed, once in over 30 runs; the
    failure's output was not captured and it did not recur, so it is recorded here rather than
    explained.
77. **Mutants P101-P110** (B7): every read kept, a settled mission kept, an `observe`-only
    paired client keeping one, "as of" the newest read, no snapshot on a cold start without
    Core, a client revoked while away or while open keeping its snapshot, the offline Now
    linking a mission, what was read before the client was known never kept, and the entries
    not keyed by origin. All ten killed. P109 survived the first run: on the `slow` Core the
    stream re-reads the Now paths, so the catch-up was never the only writer. The quiet-Core
    test above was added and P109 is guarded by it (killed twice by it).
78. **The full run** (B7 on B9, `tests/v1`): 2548 passed, 0 failed, 13 skipped, 5 xfailed. The
    known intermittent tests (item 22's `test_spa_marker.py`, item 48's two) all passed in this
    run, which says nothing about whether they are fixed.

## 13. As built

(empty until implementation)
