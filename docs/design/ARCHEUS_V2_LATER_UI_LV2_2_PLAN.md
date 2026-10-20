# Archeus later-V2 UI — LV2-2 plan: building Direction E

**Status: PROPOSED (2026-10-07). Not started. No production file is changed by this document.**
Production work needs the owner's explicit authorisation of this phase. It also still follows **P26** (V1
complete), as recorded (§16, G-1), unless the owner changes that order.

This plan **replaces** the LV2-2 plan of 2026-10-05. That plan built LD-2's three places (Now · Needs you ·
Missions) under V1's names, deferred the phone to LV2-3, and sent resuming "through P20's step-up". Each of those is
superseded (§2.2). It is not kept as a second plan; its surviving substance (the decision surface, the honest-record
voice, visible verification, the context line, the two-press stop, the data fixes) is carried into §5–§13 under E.

**What this plan is.** An implementation-ready specification of LV2-2. It answers one question: *if Archeus builds
E, exactly what changes in the frontend, Core, API, data model and tests, and in what order?* It contains no code,
and authorising it does not start anything before the dependencies in §14 are met.

---

## 0. The answer first

- **The direction is E, frozen.**
  - Five places: Overview · Missions · Ideas · Projects · Control.
  - Desktop: a safety bar holding Tell and Stop, and a left bar with the places and the projects.
  - Phone: bottom tabs, pushed pages with Back, the running-work strip, and full-page approvals.
  - The source of truth is the prototype `prototypes/v2-later/lvx/` at `?d=e2`, together with the LV2-X records
    (§1). The phone sizing is the one the owner approved after the real-phone pass (X.3 §9.7).
- **Most of E can be built on what Core already serves.** Every screen of E has a version that is honest today.
  Category A in §8 is about four-fifths of the design: places, frame, mission page, decisions, verification, context
  line, overview, missions, projects, the current-Core subset of Ideas, Control, the two-press stop, Tell, phone
  layout. It needs **no Core or API change**.
- **What is not buildable honestly today stays prototype-only, or is built as an honest workaround that is labelled as
  one.** This covers cancel, retrying a failed mission, idea research and editing, notes to an agent, what follows an
  expired approval, notifications and D10's PIN on resume. The workaround is used only where the owner already
  accepted it (Q14a cancel through Tell; Q14c start an idea through Tell).
- **Three Core defects are recorded and do not block LV2-2.** M-15, M-16 and M-17 are each handled by copy that reads
  the recorded truth.
- **Decisions are due before the first slice.** Four of them decide the work order: G-1, G-4, G-5 and G-6. The rest
  gate one slice each (§16).
- **Readiness of this plan:** see §18.

## 1. Inputs, and what each one decides

| Record | What it supplies |
|---|---|
| [LV2-1 gate](ARCHEUS_V2_LATER_UI_LV2_1_GATE.md) §1.1 | LD-3, LD-5, LD-7, LD-9, D-1 (approved); D-4 (price in-bundle); D-6 (a) (§F stays) |
| [Reassessment](ARCHEUS_V2_PRODUCT_UX_REASSESSMENT.md) §8, §12–§14, §18, **§19** | SS safety rules; DR list; V-1…V-4; E as decided (S-1…S-21); the decision register; LD-2 and D-2 (place names) superseded |
| [LV2-X.2](ARCHEUS_V2_LV2_X2_REFINEMENT.md) §2–§11, §14.2 | Core facts; the full state inventory; PX-1…PX-21 as built; motion proposal; Qt parity method |
| [LV2-X.3 / X.4 / X.5](ARCHEUS_V2_LV2_X3_CORRECTION.md) §1–§4, **§9** | M-1…M-20; the owner's Q12–Q18 decisions; the six replay fixes; dependencies by owner; the phone pass (§9.7) |
| [DR-1, 2, 3, 4, 8 gates](../architecture/) (`lv2-dr*.md`) | drafted data contracts, none decided |
| [P20 gate](../architecture/p20-design-gate.md) §4.1 (D8, D10), §14.F (V2-1…V2-5) | safety invariants; D10 blocked on V2-3; push moved to P21 |
| [V2 UI architecture](ARCHEUS_V2_UI_ARCHITECTURE.md) §T.2, [V2 UI research](ARCHEUS_V2_UI_RESEARCH.md) roadmap | P26; V2-U0 conditions; V2-U1 foundation (tokens v2, spine ADR); budgets |
| The prototype, `prototypes/v2-later/lvx/e2.js`, `e2.css`, `e2fx.js`, `e2replay.js`, and the gates in `prototypes/v2-later/tools/lvx_*.py` | the reference behaviour and the automated evidence ported in §11 |

Where these records disagree, the later decision holds, in this order: X.3 §9 / §9.7 → reassessment §19 → X.2 → LV2-1
§1.1. This plan adds no product decision. Where it had to choose a working default, the choice is labelled
**default** and has a reason. Every genuinely open question is in §16.

## 2. Decisions carried, and assumptions removed

### 2.1 Carried as accepted

| # | Decision | How LV2-2 honours it |
|---|---|---|
| S-1 | Places **Overview · Missions · Ideas · Projects · Control**, desktop and phone | L1 navigation; supersedes LD-2's three places and D-2's names |
| S-2, S-3, S-4 | Desktop safety/Tell/Stop bar, left bar with places then projects; mission lines on Missions only; phone tabs, and a mission, project or idea is its own pushed page with Back and no tabs | L1, L3, L7 |
| LD-3 | Rebuilt overview, approval screen, plain-language labels, visible verification | L3, L4, L6 |
| LD-5 | Phone approvals are a full page; the answers are a fixed bar; **no modal-sheet approval** | L4. The only sheet is P20's existing PIN step-up, which comes *after* choosing Approve, not instead of the page |
| LD-7 | Two presses, a 3 s lapse, no dialog; the word "armed" never appears in V2 | L8. The live prototype lapses after 2 s; production uses LD-7's **3 s** |
| LD-9 | Every user-facing factual clause traceable to a recorded field | L0 provenance rule; §11 gate |
| D-1 | Rows carry project · branch; remote, operation and environment are not shown until DR-2, DR-6 and DR-4 exist | L2 context line; §11 honesty gate |
| Q12 | No device asks a PIN to resume today; D10 shown nowhere in production until built | L8 copy, per device |
| Q13 | "Nothing runs until you resume"; a Tell request while stopped is "not accepted", read from the intent's reason | L9 |
| Q14a/c | Cancel… and Start… prepare a message in Tell, which the user sends | L5, L7 |
| Q14b | Blocked: Run again / Start over (the resume route). Failed: no button, said plainly | L5 |
| Q14d | Expired plan approval shown as it is, tagged "what happens next is not defined" | L5 |
| Q15 | Identity = title · project · branch tail (quiet ink); objective added for a look-alike | L2 |
| Q16 | Notifications: approvals and the stop only; never answer anything; a tap opens the mission | Prototype-only until P21 (§8 D) |
| Q17 | The strip counts live executions only; queued is named apart; waiting never counts; absent when idle, stopped, offline or loading. The safety line says **Not stopped · accepts new work** | L6 |
| Q18 | In a card, an action that changes something is a row: verb + one line of what it does. In the fixed bar the label carries the outcome (*Approve & run · Send back · Reject & cancel*). Desktop and phone alike | L4, L5, L7 |
| X.4 #3 | Amber and *Next deadline* only within **2 h** | L6 |
| X.4 #4 | The left bar keeps the place a page was opened from | L1 |
| X.5 | Two-button rows: **Cancel first, the primary action last** (right), in DOM order too; desktop rows sit at the dialog's right edge | L0 component rule |
| X.5 | The phone's compact sizing (§10.2) | L0 tokens |
| PX-1…PX-21 | X.2's refinements as built and kept by X.3/X.4 | per slice |
| P20 | Every safety semantic in §9 | §9, §11 |

### 2.2 Removed (obsolete; not carried forward)

| Old assumption | Why it is gone | Replaced by |
|---|---|---|
| Three places, Now · Needs you · Missions, V1 names Now/Attention/Work (old S1) | LD-2 and D-2 superseded by S-1 (reassessment §19.2) | E's five places |
| The phone is LV2-3 | E is one product on two layouts. The phone pass is done. The V2-U4 dependency on "P20's push and credential review" is stale: push moved to P21 (P20 D8, §14.F V2-4) | The phone layout is built in the same slices as the desktop |
| "Re-arm goes through P20's PIN step-up" (old S7, gate row) | Q12; D10 is not built, applies to paired devices only, and is blocked on V2-3 | Device-specific copy that claims no PIN; D10 is P20's (§8 D) |
| "Resuming needs a PIN" on every surface (SS-4, SS-6) | Amended by Q12 | as above |
| "Working normally" as the safety state (SS-1) | Q17 / X.4 #1 | "Not stopped · accepts new work" |
| Cancel mission, Ask Archeus to fix it, a note field, Explain, as buttons (S-11…S-13) | Q14; Core has no route for them | §8 rows; honest workarounds or prototype-only |
| S-21 "no text under buttons" as written | Q18 decided treatment *d* | Consequence rows in cards; outcomes in labels |
| The LE8 presentation pass and 20 px headers (old S8) | D-5 superseded: "E's presentation is now the target" (§19.2) | E's CSS, rebuilt on generated tokens |
| An approval as a bottom sheet on the phone | LD-5 | full page with a fixed answer bar |
| "N running" counting queued missions; a 24 h approval drawn amber | X.4 #2, #3 | §2.1 |

## 3. Objective and scope

**Objective.** Replace V1's surfaces with E in the production client `clients/app`, on desktop (browser and the Qt
shell) and phone (PWA), using only what Core serves, so that a new user can tell within seconds:
- what Archeus is doing;
- what waits for them;
- what went wrong;
- what each action will do;
- which mission they are looking at.

Every fact on screen must come from a recorded field.

**In scope**
- **The shell.** Navigation (five places), the desktop frame, the phone frame (tabs, pushed pages, Back with origin,
  the strip).
- **The places.** Overview, Missions, the mission page, Projects (list, page, timeboard), Ideas (current-Core subset),
  Control (Safety first, then V1's sections regrouped).
- **Interaction.** Tell (desktop dialog, phone page); the decision, error and outcome components.
- **Safety.** The two-press e-stop, the primed and stopped frames, resume.
- **States.** Loading, idle, empty, first run, Core unreachable, offline.
- **Presentation.** Light theme, forced colours, 200 % text, reduced motion; E's motion (§12) once its open choice is
  decided.
- **Data fixes in the client.** V-1, V-2 and V-3, where the owner places them (G-2).
- **Records.** The gates in §11 and the gate record.

**Out of scope:** §15.

## 4. Screen and state inventory

Every row has a desktop form (1,440 × 900 reference; nothing below 1,024 wide assumed to be "desktop") and a phone
form (390 × 844 reference, also 360 wide). The prototype query is the reference rendering and doubles as the
acceptance capture list (§11). D = desktop, P = phone.

| Place | States (each D and P unless marked) | Prototype query (`?d=e2&…`) |
|---|---|---|
| **Frame** | normal; primed; stopped; resuming (only Core's answer counts); resumed band; Core unreachable; offline; loading | `s=primed\|stopped\|resumed\|offline\|loading`, `resume=sending` |
| **Overview** | busy; stress day; quiet (idle); no missions yet; first run (no projects); one mission; real-Core replay | `v=home` + `s=idle\|empty\|noprojects\|one`, `corpus=x2\|core` |
| **Tell** | compose; reading; the work it made; a prepared command (cancel, start an idea); while stopped (before / not accepted) | `tell=1\|sent\|done`, `cmd=cancel\|start`, `s=stopped` |
| **Missions** | all; stress day; one project (chips); groups incl. *Queued for an agent* and *Stopped by the emergency stop* | `v=missions`, `f=<pid>`, `corpus=x2\|core` |
| **Mission** | running; verifying; planning; queued; plan approval; step approval; sending; approved + decision record; result review; accepted; rejected (earlier / just now); blocked (Run again / Start over); failed; cancelled; done; approval expired; stopped by the e-stop; approval while stopped; still blocked after a stop; Core unreachable; loading; long title; look-alike | `v=mission&id=…` (+ `did=`, `sending=`, `drawer=approval`) |
| **Approval step-up** (P) | PIN asked (client capability `pin`); this client has no PIN (`none`); local (`local`) | `pin=approve` |
| **Projects** | list; stress day; project page (identity, timeboard, done today, activity, ideas, details); first run with *Add a project…* (admin only) | `v=projects`, `v=project&pid=…` |
| **Ideas** | landing (per project, *+ Idea*); stress day; idea page; **current-Core subset** (list, Start… through Tell, "Tell Archeus an idea") | `v=ideas`, `core=1`, `v=idea&iid=…` |
| **Control** | normal; stopped; Core unreachable | `v=control` |
| **Journeys** | mission ↔ project (Back names the origin); overview → mission keeps *Overview* marked | `from=…` |
| **Theme / access** | light; forced colours; 200 % text; reduced motion | `theme=light` + the gates' emulation |

**Prototype-only (§8 E), not in the production inventory:**
- the notification entry and its "since then" landing (`v=notif`, `from=notif`);
- D10's resume PIN page (`pin=d10`);
- Explain and its answer (`dr9=1`);
- idea research, plan revision, comments, the composer's direct capture and *What it will take* as live data;
- the idea page's research facts marked `sample`.

## 5. Component and interaction inventory

| Component | Behaviour (from the prototype and its records) | Slice |
|---|---|---|
| **Place nav** (D left bar · P tabs) | Five places; Missions carries the waiting badge. On desktop, the projects list follows (monogram, name, one state dot, open count). An open project is *selected*; the project of the open mission is only *marked*. The place you came from stays marked on a pushed page | L1 |
| **System bar** (D) / app bar (P) | Safety words with a dot; "N running · N queued" pill (D); Tell; Stop. P: brand or *‹ origin*, "+" (Tell), Stop. Stopped: the bar becomes the stop band | L1, L8 |
| **Running-work strip** (P) | Docked above the tabs on root places only. Head: "Archeus is working on N missions" (+ "· N queued"), or "N missions wait for an agent". Sub: lead title · step · "+k more". Tap: one item → that mission; several → Missions#running | L6 |
| **Mission row** | Title (2-line clamp on P) · project monogram + name · branch tail (quietest ink) · state word + chip · mini line (Missions only) · objective for a look-alike · "asked HH:MM" when times differ | L2, L7 |
| **Mission line** | Six phases (Understand · Plan · Approve · Run · Verify · Review). Marks: done = tick; current = ring; failure = cross; stop = square; ended = bar; never = dashed. The state is drawn without motion. The mapping is generated from `states.py` (§7 L0) | L0, L3 |
| **Head sentence** | State word, then a sentence with Archeus as its subject ("Archeus is waiting for you to approve plan v2."), title, objective, where | L3 |
| **Decision component** | What you approve · why Archeus asks (the rule in words, the strings behind a disclosure) · what changed (client diff of the kept plan versions) · if you approve (Core's `presented.consequences` when present) · where · verified · what Archeus does not know. Expiry in its head. Sending → confirmation line → *Approved HH:MM ✓* opens the decision record | L4 |
| **Answer bar** (P) | Fixed at the bottom: expiry line, then **Reject & cancel · Send back · Approve & run…**, the confirming action last. Desktop: the same answers in the component, Approve first in the column (S-9) | L4 |
| **Step approval** | "Run this step?" with *Run this step* / *Don't run it* | L4 |
| **Error component** | The *because* chain (two hops) · Archeus knows · does not know · asked of you; action rows (Q18) | L5 |
| **Outcome component** | Rejected, cancelled, done, approval expired; neutral ink | L5 |
| **Action row** (Q18) | Verb + one line of consequence, ≥ 44 px tall. Harmless actions stay compact buttons | L0 |
| **Two-button row** | Cancel first, primary last; DOM order equals visual order | L0 |
| **E-stop** | Rest: outlined, "Stop all work" (D) / "Stop" (P). Primed: filled; "Press again to stop all work"; a hint saying how many *live* missions stop; a 3 s lapse bar (transform only); a live region. Stopped: *Resume work…*. No dialog | L8 |
| **Stop band / frame** | Primed: red across the desktop window (S-14), red band on P (S-15). Stopped: the frame on every page (S-16) with when, from where, what is held | L8 |
| **Tell** | D: centred dialog; P: its own page. Reading state. Result: the mission made (with its line) or the intent's reason. Prepared command shown before sending | L9 |
| **Context block** | Each fact labelled known / derived / not recorded. Not recorded: remote (DR-2), repository of a multi-repo project (DR-3), environment (DR-4), current operation (DR-6), check output (DR-8) | L3 |
| **Activity log** | Last 8 lines, terminal style, "Show all N lines"; from the timeline and the execution's redacted tail | L3 |
| **Timeboard** | Phase columns; half-width empty phases (one line on P); three tokens per phase with branch; "N more" | L7 |
| **Monogram** | Two letters in one of six neutral shapes; never a hue | L0 |
| **Gap tag** | A small dashed tag naming what Core lacks. In production, used only where a capability is visibly absent (for example "retrying it from here is not possible yet"); prototype provenance chips are not shipped (X.3 §5) | L0 |

## 6. Data dependencies — every element classified

Classes:
1. existing capability;
2. existing capability needing presentation work;
3. V1/Core defect;
4. data-contract gate;
5. P20 / P21 work;
6. future capability needing a new ADR or gate.

**Bold** marks the routes and fields used.

| Element | Class | Source today | Note |
|---|---|---|---|
| Places, frame, phone tabs, Back | 2 | client only | the navigation table changes (G-5) |
| Safety state words | 2 | `/v1/sync`, `/v1/status`, the stream | wording only; P20's states unchanged |
| Running vs queued | 2 | **`/v1/status` live items** + mission state EXECUTING | queued = EXECUTING with no live execution. An explicit queued state is optional class 4 |
| Waiting for you | 2 | **`/v1/attention`**, **`/v1/approvals`**, **`/v1/missions/{id}/reviews`** | waiting = any pending approval or review (M-3) |
| Expired approval still visible | 2 + 3 | the mission list + `approval.state_changed (ttl_elapsed)` | M-17: `/v1/attention` drops it silently. The client reads the mission and the expired approval instead |
| Next deadline (≤ 2 h) | 2 | `Approval.expires_at` | plan/task/start 24 h, action 2 h (M-7) |
| Project name on rows | 2 | **`/v1/projects`** client join (DR-1 option A) | V-3. No Core change |
| Branch | 2 | the mission id (`archeus/msn_<ULID>`); the single read returns it | rows derive the tail from the id (M-1) |
| Look-alike objective, "asked" | 1 | `Mission.objective`, `created_at` | rule: same title and project |
| Readable mission handle | **4** | none (ULID only) | not drafted; until then the branch tail is the handle (Q15) |
| Remote / provider / owner-repo | **4** (+ P20 slice I) | none | **DR-2**; shown as not recorded |
| Repository of a multi-repo project | **4** | single-repo rule only | **DR-3** |
| Environment of a deploy | **4** | none | **DR-4** (Part 1 not in LV2-2; old Q4 (b) kept) |
| Current operation | **5 (P21)** | none | **DR-6**, P21's activity record |
| Check names, results, exit codes | 1 | **`/v1/missions/{id}/verifications`** | visible verification (LD-3) |
| Check output | **4** (+ P20 D7) | kept by Core, not served | **DR-8** |
| Plan, versions, what changed | 2 | **`/v1/missions/{id}/plan`**, **`/v1/plans/{id}`** | the diff is computed client-side |
| Why Archeus asks | 2 | `PolicyDecision.matched_rules` | rule in words; strings behind a disclosure |
| Consequences | 1 | `presented.consequences` (M-14) | fallback: derived from `states.py` + `Plan.tasks` |
| Decide an approval | 1 | **`POST /v1/approvals/{id}/decide`** | approve / reject / request_changes |
| Approval step-up PIN | 1 (P20 built) | `step_up`, client capability `local\|pin\|none` | `none` → "This client has no PIN: it cannot satisfy a step-up" |
| Approve while stopped | 1 | refused, stays PENDING; reject / changes still work | Approve disabled with its reason (PX-10) |
| Result review | 1 | **`POST /v1/missions/{id}/review`** | copy says "Archeus plans it again"; the note does not reach the re-plan reason (X.4) |
| Run again / Start over | 1 | **`POST /v1/missions/{id}/resume`**, `held_from` | which label depends on `held_from` |
| Cancel | 2 (workaround) / **6** | the conversation's `cancel <id>` | Q14a accepted; a cancel route is class 6 (G-8) |
| Retry a FAILED mission | **6** | `replan` exists, nothing fires it | copy only (G-9) |
| What follows an expired plan approval | **3 + 6** | the mission stays APPROVAL_REQUIRED | M-17 + a Core decision (G-10) |
| Action-approval expiry end state | **3** | unpinned by any test (p11 vs code) | a Core test owed |
| Note to the agent, Explain | **6** | none | **DR-9** (Q9) |
| Per-mission pause / stop / reprioritise | 1 (unused) | routes exist | M-18: E draws none (G-7) |
| Activity log | 2 | **`/v1/missions/{id}/timeline`**, **`/v1/executions/{id}/stream`** (redacted tail) | — |
| Agent and step line | 2 | live item harness / model / step (V-2 type gap) | model may be null (M-12) |
| Done today, Today stats | 2 / **4** | `/v1/events` has `after` + `limit` only | default: client paging from the day's first sequence, measured. DR-7 if over budget (G-12) |
| Since you looked | 1 | `User.last_ack_event_seq` + **`/v1/digest`**, `POST /v1/digest/ack` | — |
| Projects list / page | 2 | **`/v1/projects`**, `/v1/projects/{id}`, repositories | default branch never written (M-11); not shown |
| Add a project | 1 | **`POST /v1/projects`** (admin) | disabled without admin scope |
| Ideas list, Start… via Tell | 2 | **`GET /v1/ideas`**; promotion in the conversation | Q14c accepted |
| Idea capture | 1 | through Tell (brain intent) | the direct button is class 6 |
| Idea research, edit, comments, time | **6** | none | **DR-10** (Q10), Q11 |
| Tell | 1 | **`POST /v1/conversations/{id}/messages`**, **`/v1/intents/{id}`** | the result reads `intent.reason` |
| Tell while stopped | 2 + **3** | declined; `reason: unavailable: emergency stop` | M-16 (wrong reply text); M-15 (`POST /v1/missions` while stopped) |
| E-stop | 2 | **`POST /v1/estop`** | replaces P20 slice B's confirm dialog (V2-2, §9) |
| Resume | 1 | **`POST /v1/rearm`**, counts only on Core's answer | no PIN today on any device |
| Resume PIN (D10) | **5 (P20)** | approved, not built, blocked on V2-3 | — |
| Missions blocked by the stop stay blocked after resume | 1 | P9 rule, P20 O1 | copy: "stay blocked … Show them" |
| Notifications (OS, push) | **5 (P21)** | none in V1 | D8 |
| Control sections | 2 | V1's Control reads | regrouped; no new authority |
| Offline / unreachable | 1 | `connection.ts` | V1's sentence kept |

## 7. What changes where

### 7.1 Frontend (`clients/app`) — all of category A

| Area | Change |
|---|---|
| `tokens/navigation.json` → `src/nav/table.ts`, `archeus/cli/tui/_tables.py` (through `tools/gen_ui.py`) | the five places, keys, phone tabs, blurbs. **The TUI reads the same table** (G-5) |
| `tokens/tokens.json`, `presentation.json`, `motion.json` → generated CSS / TS | §F desktop roles unchanged; **phone roles at the X.5 sizes** (§10.2); E's spacing, radius and control heights; state words and the phase mapping; safety words. Colours come from generated tokens. Whether `color-mix()` is allowed in generated output is a V2-U1 tokens-v2 decision (G-4) |
| `src/surfaces/` | **New:** Overview, Missions, Mission (rebuilt), Projects, Project, Ideas, Idea, Control (rebuilt), Tell. **Replaced:** Now, Work, Attention. World, Inspector and CommandBar depend on G-6 |
| `src/state/present.ts`, `presentation.ts` | the honest-record voice (no raw policy strings, no ISO times at depth 1–2); working / queued / waiting derivations; deadline window; look-alike rule; the context line; `armedText` is not used by V2 surfaces |
| `src/components/ui.tsx` | the action row, two-button row, decision, error and outcome components, the e-stop (two-press), the monogram, the gap tag; `ActionButton`'s `confirm` path is no longer used by the e-stop |
| `src/data/` | the DR-1 project join; reads listed in §6; invalidation entries for the new surfaces (`tokens/invalidation.json`) |
| `src/api/generated.ts` | V-2: `LiveItem` fields (`workdir`, `branch`, `task_title`, `waits_on`), regenerated, not hand-edited |
| `src/a11y/announce.ts` | live-region messages for primed, stopped, resumed, sending, confirmed |
| `src/styles/app.css` | E's layout, desktop and phone, and the forced-colours rules |
| `public/` (manifest, service worker) | cache version bump; `start_url` keeps working (§13) |

### 7.2 Core / API / data model

**Category A needs none.** Every Core, API or data-model change below belongs to another category and has its own
gate. None is part of LV2-2 unless the owner moves it in.

| Change | Category | Owner |
|---|---|---|
| M-15: a mission created while stopped is stuck in REASONING | V1/Core defect | V1 follow-up (P20 O1 context) |
| M-16: the declined-request reply text blames a missing harness | V1/Core defect | V1 follow-up |
| M-17: expired plan approval is dropped from `/v1/attention` with no event | V1/Core defect | V1 follow-up |
| Pin the end state of an expired **action** approval with a test | V1/Core defect | V1 follow-up |
| V-1 (`statusLine` without tasks), V-2 (`LiveItem` type), V-3 (project name on rows) | V1 defects (client) | V1 follow-up or LV2-2 L2 (G-2) |
| DR-1 option A | none (client join) | LV2-2 L2 |
| DR-2, DR-3, DR-4, DR-6, DR-8 | data-contract gates | each its own gate; DR-6 is P21's |
| Readable mission handle; explicit queued state; an event when attention drops an item | data-contract gates (not drafted) | new gates if wanted |
| Cancel route; retry a FAILED mission; what follows an expired approval; DR-9; DR-10; idea duration (Q11) | new capability, ADR + gate | each its own gate |
| D10; V2-3; "armed" in V1 copy and the policy reason (Q3 / V-4) | P20 | P20 |
| Notifications, push, the activity record | P21 | P21 |

### 7.3 Tests

| Suite | Change |
|---|---|
| `clients/app/test/*.test.ts` | new unit tests for the derivations (working / queued / waiting, deadline window, look-alike, context line, consequence wording, nav origin); rewritten `now`, `present`, `presentation`, `parity`, `shell` tests; fixtures regenerated (`test/fixtures/parity*.json`) |
| `tests/v1/e2e/test_spa_*.py` | one per place and per §4 state family, run against a real Core (the judge's TempCore), desktop and phone viewports; Qt (`test_gui_qt.py`) for the parity screens |
| `tests/v1/tui/test_parity.py` | follows G-5 |
| `tests/v1/design/test_design_gates.py` | extended with E's gates (§11) |
| `tests/v1/judge/` | unchanged; must stay green |
| A mutation tool (`tools/mutate_lv2_2.py`, modelled on `mutate_p20.py` and the prototype's `lvx_mutate_e2.py`) | every gate in §11 shown failing on a planted defect |

## 8. The five buckets

**A. Implement now from existing data and behaviour** (LV2-2's whole scope):
- **Frame and navigation:** the five places, both frames and the phone tabs; the safety words; the two-press stop and
  resume copy per device.
- **Overview:** two columns on desktop; counters, cards and the strip on the phone; deadline window; idle, empty and
  first run.
- **Missions and the mission page:** Missions with groups and chips; the mission page with its line, head sentence,
  steps, right now, context block, verified, decisions and activity.
- **Decisions and problems:** the decision, error and outcome components; the answer bar; the step approval; result
  review; Run again / Start over; Approve refused while stopped; the existing approval step-up PIN.
- **Workarounds the owner accepted:** Cancel… and Start… through Tell.
- **Projects, Ideas, Control:** Projects and the timeboard; Ideas as list + Start… + capture through Tell; Control.
- **Tell and states:** Tell, with the stopped behaviour read from the intent's reason; offline, unreachable and
  loading states.
- **Fixes:** V-1, V-2 and V-3 (if G-2 puts them here); DR-1 option A.

**B. Requires a V1 / Core / API change** (not in LV2-2; the UI is honest without them):
- M-15, M-16, M-17;
- the action-approval expiry test;
- V-1, V-2 and V-3 if G-2 keeps them in V1's follow-up.

**C. Requires a new data-contract gate:**
- DR-2 remote, DR-3 multi-repo repository, DR-4 environment, DR-8 check output;
- a readable mission handle; an explicit queued state; an attention-drop event;
- DR-7 only if the Today paging fails its budget (G-12).

New behaviour also needs an ADR and a gate: a cancel route, FAILED retry, what follows an expired approval, DR-9,
DR-10 and a duration for ideas.

**D. Waits for P20 / P21:**
- **P20:** D10's PIN on resume; V2-3 (whether the desktop asks too); "armed" in V1's copy and policy reason (Q3).
- **P21:** notifications and push, and whether a blocked mission notifies or a title may leave the computer; DR-6,
  the current operation.

**E. Prototype-only for now:**
- the notification lock screen, the desktop toast and the "since then" landing;
- D10's PIN page;
- Explain and the note field;
- idea research, revision, comments, direct capture and *What it will take*;
- per-mission pause, stop and reprioritise (until G-7);
- the mission-line *travel* motion (until G-15).

## 9. Safety invariants inherited from P20 (none may change in LV2-2)

1. **The stop when Core is down.** The e-stop stays available with Core down. Only the tray and `archeus estop` hold
   that local authority; the page holds none. When Core is unreachable, the page's Stop is disabled and points to
   the tray and `archeus estop` (PX-11).
2. **No new work until resumed.** A re-arm counts only once Core confirms it; the UI never shows "resumed" before
   that.
3. **Protection against accidental activation (item 83).** LD-7's two presses with a 3 s lapse replace slice B's
   confirmation dialog. That is contradiction V2-2, which the owner settles through LD-7. LV2-2 must:
   - keep item 83's tests green against the two-press form;
   - record the amendment of rulebook §19 ("e-stop (confirm)").
4. **D10's step-up on re-arm** from a paired device, when built. Until then no surface claims or denies a future PIN.
5. **The existing approval step-up** for actions that require it, with the client's `step_up` capability honoured.
6. **Authentication** before any action; the stream cap and takeover scope (D2); the shell's slot (D1); a client
   without admin scope never gets admin actions.
7. **A notification never approves** (when P21 builds one).
8. **"Armed" never appears on a V2 surface**, in any sense (V2-1).

## 10. Accessibility, responsive and phone requirements

### 10.1 Accessibility

- **Gates:** axe 0 violations on every §4 state; contrast floors from V1's gates, dark and light; forced colours,
  where every state stays distinct by word and shape.
- **Text and keyboard:** 200 % text with no sideways scroll and no clipped control; a skip link; a keyboard path to
  every action; focus order equals visual order (this is why the two-button order is in the DOM).
- **Announcements:** live regions for the stop (primed, stopped, resumed) and for sending and confirmation.
- **Motion and words:** reduced motion renders the end state with no animation; a state is never conveyed by colour
  alone.

### 10.2 Responsive and phone (the owner-approved sizing, X.3 §9.7)

| Token / element | Desktop | Phone |
|---|---|---|
| Body / strong | 13/20 (§F) | **13/18** |
| Row title (title2) | 16/22 | **14/20** |
| Title1 | 20/26 | **16/22** |
| Page title (headline) | 28/34 | **20/25** |
| Display | 32/38 | **24/30** |
| Caption / mono / label | 12/16 · 12/18 · 11/14 | **12/16 · 11.5/16 · 11/14** |
| Buttons | 32 tall | **40 tall, ≥ 44 wide**; answer bar **44** |
| E-stop | 36 | **34**; 40 on Resume and in Control |
| Bars | system bar 56; left bar 248 wide | app bar **48**; tab bar **50** + safe area; strip **42**; tab label 10 |
| Inputs | 13 (Tell 15) | **16** (below 16, iOS Safari zooms on focus) |
| Touch targets | — | fail when < 44 on both sides, or < 32 tall (HIG 44 pt; WCAG 2.5.8 24 px) |

**The phone sizing and §F.** These phone values amend §F's phone roles. The owner approved them after the phone pass;
the formal §F record line is a records step at authorisation (§17). §F's desktop roles are unchanged.

**Phone layout rules:**
- The layout is chosen by the viewport width (< 600 px), not by the device, so a narrow desktop window also gets it.
- The gutter is 16 px, and nothing scrolls sideways at 360 or 390.
- Pushed pages have Back (system Back pops one level and never exits) and no tabs.
- The strip sits above the tabs and never covers content.
- The approval is a full page with a fixed bar.
- Titles clamp to 2 lines in lists.

**Desktop shell:** `color-scheme` set; a stable, thin scrollbar gutter (PX-19). Qt = Chromium on every layout fact
(§11).

**Scrim:** the dimmed page behind Tell and the idea dialog follows **PR-3's measured ceilings** (≤ 0.30 dark,
≤ 0.18 light). The prototype's ~0.72 is a prototype value, not a target.

## 11. Acceptance tests and evidence

There is no human study. Per the owner (2026-10-07; P-4), LV2-2's evidence is:
- the accepted decisions;
- the owner's completed phone pass;
- automated checks against a **real Core**;
- desktop / Chromium / Qt parity;
- the owner's sign-off on the gate captures.

**Every gate is mutation-verified:** it is shown failing on a planted defect before it is trusted.

| Gate | Pass |
|---|---|
| **Capture set** | every §4 state, desktop and phone, rendered from a real Core (the X.3 replay ported: TempCore, workers, fake harness, scripted verifier, three repositories, the replay afternoon) plus a stress corpus; the owner reviews the set |
| **Honesty / provenance** (LD-9) | every factual clause carries the field it came from in test builds (`data-src`/`data-k`; **default:** stripped from the production bundle, because it costs bytes and no user reads it); 0 unsourced facts. 0 renderings of: remote, owner/repo, environment, operation, target branch or default branch as known; "Into main"; `undefined`, `NaN`, `null`; raw policy strings or ISO times at depth 1–2 |
| **Forbidden copy** | 0 of: "armed", "re-arm", "Working normally", "New work is refused", "kept, not read", "Ask Archeus to fix it", a *Cancel mission* button, a retry on a FAILED mission, any PIN claim on desktop resume or primed copy, any future-PIN copy on the phone, a phone push naming a mission |
| **Required copy** | "Not stopped" (normal); "Not accepted … Send it again after you resume" (Tell while stopped); "1 queued" (real-Core overview); *Next deadline* only within 2 h; Start…'s and Cancel…'s consequence rows |
| **Work vs waiting vs safety** | the strip and the pill count live executions only; queued is named apart; waiting never enters the strip; the strip is absent when idle, stopped, offline or loading (14 cases, as `q17`); the primed hint counts only what the stop ends |
| **Navigation** | five places; Back names the origin; the place a page came from stays marked (overview → mission marks Overview); system Back never exits on P |
| **Decision** | one page on P with a fixed bar; Reject left, Approve last; no dialog; closing decides nothing; Approve disabled while stopped with reject/changes live; nothing shown as approved before Core records it; step-up honoured for `pin` and `none` |
| **E-stop** (LD-7, item 83) | 2 presses; the first stops nothing and lapses after 3 s; the second stops; 0 dialogs; announced; distinct in forced colours; Stop present on every screen; disabled with the tray / `archeus estop` pointer when Core is unreachable |
| **Layout** | 0 sideways overflow at 360, 390 and 1,440, and at 200 % text; no card narrower than 240 px (P) / 150 px (D); targets as §10.2 |
| **Above the fold** | desktop 1,440 × 900, stress day: *Waiting*, *Blocked or failed* and *Running now* all start above the fold |
| **Accessibility** | §10.1 |
| **Motion** | §12 |
| **Qt parity** | x and width within 2 px, y and height within 1.5 %, on the parity screen set, in the real `QWebEngineView` |
| **Budget** | §13 |
| **Existing suites** | V1 unit, integration, contract, design-gate, TUI and judge suites green; CI green |

## 12. Motion

As X.2 §10 (PX-18), measured by the ported `lvx_motion.py`:
- **What may animate:** only `transform` and `opacity`, so no animation invalidates paint.
- **When:** only on a recorded phase change of a mission on screen.
  - The focus surface gets a travel of ≤ 600 ms plus a 240 ms landing.
  - Peripheral lines get a 160 ms fill.
- **Never:** at rest; while the stop is engaged (engaging it ends any travel); under reduced motion (end state at
  once).
- **Other motion allowed:** the waiting dots, only while something is actually awaited, and the stop's lapse bar.
- **Interruptions:** one travel at a time; any input renders the end state.
- **G-15 is open:** whether the travelling head is wanted, or only fill + ring. Until decided, production ships the
  **fill + ring** form, which is the subset common to both answers, and the head stays prototype-only.

## 13. Budget, migration and backward compatibility

**Budget**
- Price every slice minified and in-bundle (D-4), and record its delta.
- LD-1's ≈ 12.5 KB visual-behaviour cap and the V2 architecture's ≤ 10 KB gzip visual budget both apply to *visual
  behaviour* (motion, figures, depth). E's structure replaces V1's surfaces, so its markup and CSS are measured as a
  **net** change against the V1 build.
- No new runtime dependency.
- Any slice that grows the bundle more than it removes goes to the owner with its number. No figure is estimated here
  ahead of measurement.

**Migration**
- **Places and routes.** V1's place ids (`now`, `work`, `world`, `attention`) change.
  - A link saved on a paired phone or as a Home Screen app must still open the right place. **Default:** one table
    mapping each old route to its E place, because a saved PWA cannot be updated by us. It is removed when the owner
    says.
  - The manifest `start_url` keeps working; the service-worker cache version is bumped.
- **Keys.** Shortcuts and TUI keys come from the navigation table, so they change with it (G-5).
- **Local state.** Stored client state (pins, inspector width, appearance) is migrated where its surface survives and
  dropped where it does not (G-6).
- **P20 and API.** P20's `armedText` stays in V1's code for V1's surfaces until P20 decides Q3. The API is unchanged:
  no route, schema or event is added or removed by category A.
- **Test fixtures.** The parity fixtures are regenerated, never hand-edited.

## 14. Dependencies and implementation order

**Before any production slice:**
- P26 (G-1), or the owner's change to it;
- G-4, G-5 and G-6 decided;
- the records steps in §17.

These gate only the slices they name: G-2 → L2 · G-7 → L3 · G-12 → L6 · G-15 → L10.

| # | Slice | Contents | Needs | Why here |
|---|---|---|---|---|
| **L0** | Foundation | generated tokens (desktop §F, phone X.5 roles, controls, spacing); state words and the six-phase mapping generated from `states.py`; safety words; the action-row, two-button-row, monogram and gap-tag components; provenance attributes in test builds; the §11 gate harness ported (capture, honesty, targets, overflow, motion, Qt) and mutation-verified on V1 | G-4 (does V2-U1 come first, or is it folded in here) | every later slice renders through it; the gates must exist before the first screen |
| **L1** | Shell and navigation | the navigation table (five places; the TUI per G-5); desktop system bar and left bar with projects; phone tabs, pushed pages, Back with origin; route table for old links; the e-stop **as P20 built it** (dialog unchanged until L8) | G-5, G-6 | every probe navigates by it |
| **L2** | Data layer | DR-1 join; branch from id; working / queued / waiting; deadline window; look-alike rule; context line; V-1, V-2, V-3 if here | G-2 | rows on every place are built from it |
| **L3** | Mission page | head sentence, the line, steps, right now, context block, verified, decision record, activity (timeline + redacted tail), outcome component | L2; G-7 for any per-mission control | decisions and errors live on it |
| **L4** | Decisions | decision component, answer bar (P), desktop actions, sending and confirmation, step approval, result review, approval step-up (`pin`/`none`), approve-while-stopped | L3 | LD-3, LD-5 |
| **L5** | Problems | error component, Run again / Start over, the failed copy, Cancel… through Tell, expired-approval outcome | L3, L9's prepared-command path | Q14 |
| **L6** | Overview | desktop two columns with caps; phone counters, cards, strip; idle, empty, first run, one; Today (paging, measured) | L2–L5 | composes the others; G-12 for Today |
| **L7** | Missions, Projects, Ideas | Missions (groups, chips, lines); Projects list, page, timeboard, *Add a project…* (admin); Ideas current-Core subset with Start… | L2, L3, L9 | — |
| **L8** | Safety | two-press e-stop replacing the dialog; primed and stopped frames; resume and resumed bands, per-device copy; Control (Safety first, then V1's sections regrouped); offline / unreachable | L1; item 83 tests; rulebook §19 amendment | the one slice that changes a P20-built control, so it is isolated with its own gate |
| **L9** | Tell | desktop dialog, phone page, reading, result from the intent; prepared commands; while stopped | L1 | L5 and L7 depend on prepared commands; it can land before them |
| **L10** | Motion | fill + ring (head per G-15) | L3, L7 | presentation over finished structure |
| **L11** | Gate | full capture set on a real Core, all §11 gates, Qt parity, budget, the owner's review of the captures | all | exit |

Each slice ends with its gates green and its captures recorded. L9 may be built in parallel with L2–L4.

## 15. Out of scope

- Any Core, API, schema or event change (§7.2 lists them by owner).
- DR-2, DR-3's recorded field, DR-4, DR-6, DR-7 (unless G-12), DR-8, DR-9 and DR-10.
- A cancel route and FAILED retry.
- Notifications and push (P21); D10 and V2-3 (P20).
- Relations / World V2 (V2-U5); the day's light (LD-4); hero moments (PR-6); liveness (V2-U3); acknowledge / snooze
  (V2-U2's ADR).
- Renaming beyond S-1.
- Any human study or participant recruitment.
- Amending §F's desktop roles.

## 16. Open decisions (not chosen by this plan)

| # | Question | Options | Blocks | Recommendation |
|---|---|---|---|---|
| **G-1** | P26 ordering: does LV2-2 production start only after V1 is complete, as recorded? | (a) as recorded · (b) earlier | every slice | (a), as recorded; the owner's call |
| **G-2** | V-1, V-2, V-3: V1's follow-up before P26, or LV2-2 L2? | (a) V1 follow-up · (b) L2 | L2 | (a) for V-1/V-2 (V1 bugs with V1 tests); V-3 is client-only, either works |
| **G-3** | V2-U0's human conditions (PR-5 identification test with ≥ 4 participants; PR-1/PR-3 tearing glances; PR-6 dogfood). The owner said on 2026-10-07 that no participant study blocks LV2-2 | (a) amend §T.2: PR-5's participant test does not gate LV2-2; the tearing glances stay owner checks on real hardware, owed only if LV2-2 ships the thread light or the focus-plane scrim · (b) keep §T.2 as recorded | records | (a), recorded at authorisation, as the owner's own words |
| **G-4** | V2-U1 (tokens v2, spine ADR, state figures): a separate phase before LV2-2, or folded into L0? | (a) separate · (b) folded into L0 | L0 | (b): E's line *is* the spine, and LV2-2 cannot render without the mapping |
| **G-5** | The TUI shares the navigation table. Does it follow E's five places? | (a) yes, same five · (b) TUI keeps V1's screens (the table gains a per-surface split) | L1 | the owner's; (a) keeps one vocabulary, but no TUI design for E exists |
| **G-6** | V1 capabilities E gives no place: World (the P18 graph), knowledge review (confirm / reject / retract / forget), the inspector panel, the command bar (Ctrl+K), sessions | per capability: keep (where), defer to V2-U5, or retire | L1 | no recommendation without a design; nothing is removed silently |
| **G-7** | M-18: Core has pause, stop-this-mission and reprioritise; E draws none | (a) leave out · (b) add to the mission page with Q18 rows | L3 | the owner's |
| **G-8** | Q14a: keep Cancel… through Tell for LV2-2, or gate a cancel route first? | (a) Tell (accepted) · (b) route gate first | L5 | (a), as decided; (b) removes a workaround later |
| **G-9** | Q14b: FAILED stays a dead end apart from cancel, or gate a retry route? | (a) as is · (b) gate | none for LV2-2 | the owner's |
| **G-10** | Q14d / M-17: what should follow an expired plan approval? | Core decision | none for LV2-2 | — |
| **G-11** | Q9 DR-9 and Q10 DR-10: draft them? Q11: a duration for ideas? | draft / hold | none (Ideas ships its current-Core subset) | — |
| **G-12** | Today: client paging of `/v1/events`, or DR-7? | (a) paging, measured · (b) DR-7 | L6 | (a) unless it fails the budget |
| **G-13** | Q3: "armed" in V1's copy and Core's policy reason | P20's | none (V2 never shows it) | — |
| **G-14** | V2-3: does the desktop ask a PIN to resume? | P20's | none (copy is device-specific) | — |
| **G-15** | Motion: the travelling head, or fill + ring only? F-1's demotion rule when many missions move at once | — | L10 | ship fill + ring until decided |
| **G-16** | P21 brief: does a blocked mission notify; may a title or project leave the computer in a push? | P21's | none (notifications are out of scope) | — |

Non-blocking design notes, carried as known:
- approval density (six blocks on the twentieth decision of a kind);
- *Review* is both the overview button and the last phase's name;
- the project dot loses meaning on a busy day;
- amber carries too much.

## 17. Records steps at authorisation (documentation only)

1. **§F:** record the phone roles of §10.2 as the owner-approved amendment (X.3 §9.7); desktop roles unchanged.
2. **V2 architecture §T.2:** record G-3's answer.
3. **Rulebook §19 / P20 §14.F V2-2:** record that LD-7's two presses replace the confirm dialog in L8, with item 83's
   tests kept.
4. **P20 §14.F V2-4:** the V2 records no longer name P20 for push. This plan already says P21; the architecture
   document's stale line is corrected.
5. **Reassessment §19:** mark SS-1's wording ("Not stopped") and SS-4/SS-6's PIN clause as amended by Q12/Q17.

## 18. Exit criteria and readiness

**LV2-2 is done when:**
- every slice L0–L11 has landed with its gates green;
- every §11 gate passes on a real Core, mutation-verified, in Chromium and the Qt shell;
- the V1 suites and CI are green;
- the budget is recorded and within the caps, or accepted by the owner;
- no category B–E item is rendered as if it existed;
- the owner has signed off on the gate captures.

**Readiness of this plan: READY FOR THE OWNER'S AUTHORISATION.** It describes E only and carries every accepted
decision. Each dependency is classified, and no unresolved backend question is turned into a UI promise.

Authorising it does **not** start production:
- P26 still comes first unless the owner changes G-1;
- G-4, G-5 and G-6 must be answered before L0/L1;
- the records steps in §17 come first.

None of these needs another design phase. G-5 and G-6 need a short design note, because E never drew the TUI or a
home for World, knowledge, the inspector or the command bar.
